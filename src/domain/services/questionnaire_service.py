"""Service for questionnaire generation and management."""

import json
import logging
from typing import List, Dict, Any, Optional
from uuid import UUID

from google import genai
from google.genai import types

from src.domain.ports.policy_repository import PolicyRepository
from src.domain.models.policy_models import (
    Policy, Questionnaire, Question, QuestionAttempt,
    QuestionType
)
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class QuestionnaireService:
    """Service for questionnaire generation and validation."""

    def __init__(
        self,
        repository: PolicyRepository,
        gemini_model: str = "gemini-2.0-flash-exp"
    ):
        """
        Initialize questionnaire service.

        Args:
            repository: Policy repository
            gemini_model: Gemini model name for question generation
        """
        self.repository = repository
        self.gemini_model = gemini_model
        self.client = genai.Client()

    async def generate_questionnaire(
        self,
        policy_id: UUID,
        user_id: str,
        num_questions: int = 5,
        difficulty_mix: Optional[Dict[str, int]] = None
    ) -> Questionnaire:
        """
        Generate questionnaire from policy content using Gemini.

        Args:
            policy_id: Policy ID
            user_id: User generating questionnaire (must be owner)
            num_questions: Number of questions to generate
            difficulty_mix: Optional mix of difficulties {"easy": 2, "medium": 2, "hard": 1}

        Returns:
            Generated questionnaire with questions
        """
        # Get policy
        policy = await self.repository.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")

        if policy.owner_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        if not policy.content:
            raise HTTPException(
                status_code=400,
                detail="Policy content is empty. Cannot generate questionnaire."
            )

        logger.info(f"Generating questionnaire for policy {policy_id}")

        # Default difficulty mix
        if difficulty_mix is None:
            difficulty_mix = {
                "easy": max(1, num_questions // 3),
                "medium": max(1, num_questions // 3),
                "hard": num_questions - (2 * (num_questions // 3))
            }

        # Generate questions using Gemini
        questions_data = await self._generate_questions_with_gemini(
            policy_content=policy.content,
            policy_title=policy.title,
            num_questions=num_questions,
            difficulty_mix=difficulty_mix
        )

        # Create questionnaire
        questionnaire = await self.repository.create_questionnaire(
            policy_id=policy_id,
            title=f"{policy.title} - Knowledge Check",
            description=f"Test your understanding of the {policy.title} policy",
            pass_threshold_percentage=70
        )

        # Add questions to database
        for idx, q_data in enumerate(questions_data):
            await self.repository.add_question(
                questionnaire_id=questionnaire.questionnaire_id,
                question_text=q_data["question_text"],
                question_type=q_data["question_type"],
                correct_answer=q_data["correct_answer"],
                options=q_data.get("options"),
                explanation=q_data.get("explanation"),
                difficulty=q_data.get("difficulty", "medium"),
                points=q_data.get("points", 1),
                display_order=idx,
                metadata={"generated_by": "gemini", "model": self.gemini_model}
            )

        logger.info(f"Questionnaire created with {len(questions_data)} questions")
        return questionnaire

    async def _generate_questions_with_gemini(
        self,
        policy_content: str,
        policy_title: str,
        num_questions: int,
        difficulty_mix: Dict[str, int]
    ) -> List[Dict[str, Any]]:
        """
        Use Gemini to generate questions from policy content.

        Args:
            policy_content: Policy text content
            policy_title: Policy title
            num_questions: Number of questions to generate
            difficulty_mix: Difficulty distribution

        Returns:
            List of question dictionaries
        """
        # Construct prompt
        prompt = f"""You are an expert at creating educational assessments. Generate {num_questions} multiple-choice questions to test understanding of the following policy:

Policy Title: {policy_title}

Policy Content:
{policy_content[:3000]}  # Limit to first 3000 chars to avoid token limits

Generate questions with the following difficulty distribution:
- Easy: {difficulty_mix.get('easy', 0)} questions
- Medium: {difficulty_mix.get('medium', 0)} questions
- Hard: {difficulty_mix.get('hard', 0)} questions

For each question, provide:
1. question_text: The question itself
2. question_type: Always "multiple_choice"
3. options: Array of 4 options with format [{{"id": "a", "text": "Option A"}}, ...]
4. correct_answer: The ID of the correct option (e.g., "b")
5. explanation: Brief explanation of why the answer is correct
6. difficulty: "easy", "medium", or "hard"

Return ONLY a valid JSON array of questions in this exact format:
[
  {{
    "question_text": "What is the primary purpose of this policy?",
    "question_type": "multiple_choice",
    "options": [
      {{"id": "a", "text": "Option A text"}},
      {{"id": "b", "text": "Option B text"}},
      {{"id": "c", "text": "Option C text"}},
      {{"id": "d", "text": "Option D text"}}
    ],
    "correct_answer": "b",
    "explanation": "The correct answer is B because...",
    "difficulty": "medium",
    "points": 1
  }}
]
"""

        try:
            # Call Gemini API
            response = self.client.models.generate_content(
                model=self.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=2048,
                    response_mime_type="application/json"
                )
            )

            # Parse JSON response
            questions_json = response.text.strip()
            questions_data = json.loads(questions_json)

            # Validate structure
            if not isinstance(questions_data, list):
                raise ValueError("Response is not a JSON array")

            # Validate each question has required fields
            for q in questions_data:
                if not all(k in q for k in ["question_text", "question_type", "correct_answer"]):
                    raise ValueError(f"Missing required fields in question: {q}")

            logger.info(f"Generated {len(questions_data)} questions with Gemini")
            return questions_data[:num_questions]  # Ensure we don't exceed requested count

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            # Fallback: create simple questions
            return self._create_fallback_questions(policy_content, num_questions)
        except Exception as e:
            logger.error(f"Error generating questions with Gemini: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate questionnaire: {str(e)}"
            )

    def _create_fallback_questions(
        self,
        policy_content: str,
        num_questions: int
    ) -> List[Dict[str, Any]]:
        """Create simple fallback questions if Gemini fails."""
        logger.warning("Using fallback question generation")

        # Extract first few sentences for basic questions
        sentences = policy_content.split('.')[:5]

        questions = []
        for i in range(min(num_questions, len(sentences))):
            questions.append({
                "question_text": f"Based on the policy, is the following statement accurate: \"{sentences[i].strip()}\"?",
                "question_type": "true_false",
                "options": [
                    {"id": "true", "text": "True"},
                    {"id": "false", "text": "False"}
                ],
                "correct_answer": "true",
                "explanation": "This statement is directly from the policy content.",
                "difficulty": "easy",
                "points": 1
            })

        return questions

    async def update_correct_answer(
        self,
        question_id: UUID,
        user_id: str,
        correct_answer: Any
    ) -> Question:
        """
        Update the correct answer for a question (user validation).

        Args:
            question_id: Question ID
            user_id: User updating (must be policy owner)
            correct_answer: New correct answer

        Returns:
            Updated question
        """
        # Get question and verify ownership
        questions = await self.repository.get_questions(question_id)
        if not questions:
            raise HTTPException(status_code=404, detail="Question not found")

        # Note: This is simplified - should verify via questionnaire -> policy ownership
        updated_question = await self.repository.update_question(
            question_id=question_id,
            correct_answer=correct_answer
        )

        if not updated_question:
            raise HTTPException(status_code=404, detail="Question not found")

        logger.info(f"Question {question_id} updated by user {user_id}")
        return updated_question

    async def submit_attempt(
        self,
        question_id: UUID,
        user_id: str,
        user_answer: Any,
        time_spent_seconds: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Submit user's answer and record attempt.

        Args:
            question_id: Question ID
            user_id: User submitting answer
            user_answer: User's answer
            time_spent_seconds: Time spent on question

        Returns:
            Result with correctness and explanation
        """
        # Get question
        # Note: This is simplified - should get via repository method
        # For now, we'll just record the attempt

        # Compare answer (this should be more sophisticated based on question type)
        # Simplified: just check if answers match
        # In production, implement proper comparison logic per question type

        is_correct = False  # Placeholder - implement proper comparison

        # Record attempt
        attempt = await self.repository.record_attempt(
            question_id=question_id,
            user_id=user_id,
            user_answer=user_answer,
            is_correct=is_correct,
            time_spent_seconds=time_spent_seconds
        )

        logger.info(f"Recorded attempt for question {question_id} by user {user_id}")

        return {
            "attempt_id": str(attempt.attempt_id),
            "is_correct": is_correct,
            "time_spent_seconds": time_spent_seconds
        }

    async def calculate_score(
        self,
        questionnaire_id: UUID,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Calculate user's score on questionnaire.

        Args:
            questionnaire_id: Questionnaire ID
            user_id: User ID

        Returns:
            Score data with pass/fail status
        """
        # Get questionnaire
        questionnaire = await self.repository.get_questionnaire_by_policy(questionnaire_id)
        if not questionnaire:
            # Try direct lookup - this is simplified
            pass

        # Get user's attempts
        attempts = await self.repository.get_user_attempts(
            user_id=user_id,
            questionnaire_id=questionnaire_id
        )

        if not attempts:
            return {
                "total_questions": 0,
                "attempted": 0,
                "correct": 0,
                "score_percentage": 0,
                "passed": False
            }

        # Calculate score
        total = len(attempts)
        correct = sum(1 for a in attempts if a.is_correct)
        score_percentage = (correct / total * 100) if total > 0 else 0

        passed = score_percentage >= (questionnaire.pass_threshold_percentage if questionnaire else 70)

        return {
            "total_questions": total,
            "attempted": total,
            "correct": correct,
            "score_percentage": score_percentage,
            "passed": passed,
            "threshold": questionnaire.pass_threshold_percentage if questionnaire else 70
        }
