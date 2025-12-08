"""Utility for generating and parsing diff suggestions from AI output."""

import re
import uuid
import json
import logging
from typing import List, Tuple, Optional

from src.domain.models import DiffSuggestion, DiffType

logger = logging.getLogger(__name__)


class DiffGenerator:
    """
    Parses AI output for diff suggestions and generates proper diff objects.

    Supports multiple formats:
    1. JSON diff blocks in markdown code blocks (```diff)
    2. Inline JSON diff objects
    3. Comparison-based diff detection using difflib
    """

    # Regex pattern for diff code blocks
    DIFF_BLOCK_PATTERN = re.compile(
        r"```diff\s*\n(.*?)\n```",
        re.DOTALL | re.IGNORECASE
    )

    # Regex pattern for JSON objects with type field
    JSON_DIFF_PATTERN = re.compile(
        r'\{[^{}]*"type"\s*:\s*"(addition|deletion|modification)"[^{}]*\}',
        re.DOTALL | re.IGNORECASE
    )

    def extract_diffs(
        self,
        ai_output: str,
        original_content: str = ""
    ) -> Tuple[List[DiffSuggestion], str]:
        """
        Extract diff suggestions from AI output.

        Args:
            ai_output: The raw AI response text
            original_content: The original document content for index calculation

        Returns:
            Tuple of (list of DiffSuggestion, remaining text without diff blocks)
        """
        diffs = []
        seen_ids = set()

        # Extract from code blocks first
        for match in self.DIFF_BLOCK_PATTERN.finditer(ai_output):
            block_content = match.group(1).strip()
            try:
                diff = self._parse_diff_json(block_content, original_content)
                if diff and diff.id not in seen_ids:
                    diffs.append(diff)
                    seen_ids.add(diff.id)
            except Exception as e:
                logger.debug(f"Failed to parse diff block: {e}")

        # Also look for inline JSON diffs
        for match in self.JSON_DIFF_PATTERN.finditer(ai_output):
            try:
                json_str = match.group(0)
                diff = self._parse_diff_json(json_str, original_content)
                if diff and diff.id not in seen_ids:
                    diffs.append(diff)
                    seen_ids.add(diff.id)
            except Exception as e:
                logger.debug(f"Failed to parse inline diff: {e}")

        remaining = self.remove_diff_blocks(ai_output)

        return diffs, remaining

    def _parse_diff_json(
        self,
        json_str: str,
        original_content: str
    ) -> Optional[DiffSuggestion]:
        """Parse a JSON diff string into a DiffSuggestion."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Try to extract JSON from the string if it contains extra text
            match = re.search(r'\{.*\}', json_str, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except json.JSONDecodeError:
                    return None
            else:
                return None

        diff_type_str = data.get("type", "modification").lower()
        try:
            diff_type = DiffType(diff_type_str)
        except ValueError:
            diff_type = DiffType.MODIFICATION

        original_text = data.get("original", data.get("originalText", ""))
        new_text = data.get("new", data.get("newText", ""))

        # Calculate indices
        start_index = 0
        end_index = 0

        if original_text and original_content:
            idx = original_content.find(original_text)
            if idx >= 0:
                start_index = idx
                end_index = idx + len(original_text)
        elif data.get("position"):
            # Handle "after: [context]" format
            position = data.get("position", "")
            if "after:" in position.lower():
                context = position.split(":", 1)[1].strip().strip("[]\"'")
                idx = original_content.find(context)
                if idx >= 0:
                    start_index = idx + len(context)
                    end_index = start_index

        return DiffSuggestion(
            id=str(uuid.uuid4()),
            type=diff_type,
            original_text=original_text,
            new_text=new_text,
            start_index=start_index,
            end_index=end_index
        )

    def remove_diff_blocks(self, text: str) -> str:
        """Remove diff code blocks from text."""
        # Remove ```diff blocks
        text = self.DIFF_BLOCK_PATTERN.sub("", text)
        # Remove inline JSON diffs
        text = self.JSON_DIFF_PATTERN.sub("", text)
        # Clean up multiple newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def generate_diff_from_comparison(
        self,
        original: str,
        modified: str,
        context_size: int = 50
    ) -> List[DiffSuggestion]:
        """
        Generate diffs by comparing original and modified text.

        Uses difflib for cases where the AI provides a rewritten
        version without explicit diff markers.

        Args:
            original: Original text
            modified: Modified text
            context_size: Minimum context size for grouping changes

        Returns:
            List of DiffSuggestion objects
        """
        import difflib

        diffs = []
        matcher = difflib.SequenceMatcher(None, original, modified)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                diffs.append(DiffSuggestion(
                    id=str(uuid.uuid4()),
                    type=DiffType.MODIFICATION,
                    original_text=original[i1:i2],
                    new_text=modified[j1:j2],
                    start_index=i1,
                    end_index=i2
                ))
            elif tag == "delete":
                diffs.append(DiffSuggestion(
                    id=str(uuid.uuid4()),
                    type=DiffType.DELETION,
                    original_text=original[i1:i2],
                    new_text="",
                    start_index=i1,
                    end_index=i2
                ))
            elif tag == "insert":
                diffs.append(DiffSuggestion(
                    id=str(uuid.uuid4()),
                    type=DiffType.ADDITION,
                    original_text="",
                    new_text=modified[j1:j2],
                    start_index=i1,
                    end_index=i1
                ))

        return diffs

    def merge_adjacent_diffs(
        self,
        diffs: List[DiffSuggestion],
        max_gap: int = 10
    ) -> List[DiffSuggestion]:
        """
        Merge adjacent diff suggestions that are close together.

        Args:
            diffs: List of diff suggestions
            max_gap: Maximum gap between diffs to merge

        Returns:
            List of merged DiffSuggestion objects
        """
        if not diffs:
            return []

        # Sort by start index
        sorted_diffs = sorted(diffs, key=lambda d: d.start_index)

        merged = []
        current = sorted_diffs[0]

        for next_diff in sorted_diffs[1:]:
            # Check if diffs are close enough to merge
            if (next_diff.start_index - current.end_index <= max_gap and
                    current.type == next_diff.type):
                # Merge the diffs
                current = DiffSuggestion(
                    id=current.id,
                    type=current.type,
                    original_text=current.original_text + next_diff.original_text,
                    new_text=current.new_text + next_diff.new_text,
                    start_index=current.start_index,
                    end_index=next_diff.end_index
                )
            else:
                merged.append(current)
                current = next_diff

        merged.append(current)
        return merged
