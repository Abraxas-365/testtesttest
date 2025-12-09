"""Service for generating PDF and JPEG artifacts from policies."""

import io
import logging
from uuid import UUID
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import markdown
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from src.domain.ports.policy_repository import PolicyRepository
from src.domain.models.policy_models import Policy, ContentFormat
from src.services.storage_service import StorageService
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class PolicyGenerationService:
    """Service for generating policy artifacts (PDF, JPEG)."""

    def __init__(
        self,
        repository: PolicyRepository,
        storage_service: StorageService
    ):
        self.repository = repository
        self.storage = storage_service

    async def generate_and_publish_policy(
        self,
        policy_id: UUID,
        user_id: str
    ) -> Tuple[str, str]:
        """
        Generate PDF and JPEG, upload to GCS, and update policy.

        Args:
            policy_id: Policy ID
            user_id: User generating artifacts (must be owner)

        Returns:
            Tuple of (pdf_gcs_uri, jpeg_gcs_uri)
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
                detail="Policy content is empty. Cannot generate artifacts."
            )

        logger.info(f"Generating artifacts for policy {policy_id}")

        # Generate PDF
        pdf_bytes = self._generate_pdf(policy)

        # Generate JPEG
        jpeg_bytes = self._generate_jpeg(policy)

        # Upload to GCS
        pdf_blob_path = f"policies/{policy_id}/policy.pdf"
        jpeg_blob_path = f"policies/{policy_id}/policy.jpg"

        # Upload PDF
        pdf_blob = self.storage.bucket.blob(pdf_blob_path)
        pdf_blob.upload_from_string(
            pdf_bytes,
            content_type="application/pdf"
        )
        logger.info(f"PDF uploaded: {pdf_blob_path}")

        # Upload JPEG
        jpeg_blob = self.storage.bucket.blob(jpeg_blob_path)
        jpeg_blob.upload_from_string(
            jpeg_bytes,
            content_type="image/jpeg"
        )
        logger.info(f"JPEG uploaded: {jpeg_blob_path}")

        # Update policy with artifact paths
        await self.repository.update_policy_artifacts(
            policy_id=policy_id,
            pdf_blob_path=pdf_blob_path,
            jpeg_blob_path=jpeg_blob_path
        )

        pdf_gcs_uri = f"gs://{self.storage.bucket_name}/{pdf_blob_path}"
        jpeg_gcs_uri = f"gs://{self.storage.bucket_name}/{jpeg_blob_path}"

        logger.info(f"Policy {policy_id} published successfully")

        return pdf_gcs_uri, jpeg_gcs_uri

    def _generate_pdf(self, policy: Policy) -> bytes:
        """
        Generate PDF from policy content.

        Args:
            policy: Policy entity

        Returns:
            PDF bytes
        """
        buffer = io.BytesIO()

        # Create PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )

        # Container for flowables
        story = []

        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor='#1a73e8',
            spaceAfter=30,
            alignment=TA_CENTER
        )

        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['BodyText'],
            fontSize=11,
            alignment=TA_LEFT,
            spaceAfter=12
        )

        # Add title
        title = Paragraph(policy.title, title_style)
        story.append(title)
        story.append(Spacer(1, 0.2*inch))

        # Add description if present
        if policy.description:
            desc = Paragraph(f"<b>Description:</b> {policy.description}", body_style)
            story.append(desc)
            story.append(Spacer(1, 0.2*inch))

        # Convert content to HTML if markdown
        content_html = policy.content
        if policy.content_format == ContentFormat.MARKDOWN:
            content_html = markdown.markdown(policy.content)
        elif policy.content_format == ContentFormat.PLAIN:
            content_html = policy.content.replace('\n', '<br/>')

        # Add content - split by paragraphs
        if content_html:
            # Simple paragraph splitting (can be enhanced with HTML parser)
            paragraphs = content_html.split('\n')
            for para in paragraphs:
                if para.strip():
                    p = Paragraph(para, body_style)
                    story.append(p)

        # Build PDF
        doc.build(story)

        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(f"Generated PDF: {len(pdf_bytes)} bytes")
        return pdf_bytes

    def _generate_jpeg(self, policy: Policy) -> bytes:
        """
        Generate JPEG preview from policy content.

        Args:
            policy: Policy entity

        Returns:
            JPEG bytes
        """
        # Create image (A4 size at 150 DPI)
        width, height = 1240, 1754  # A4 at 150 DPI
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)

        # Try to use a nice font, fallback to default
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
            body_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        except Exception:
            logger.warning("Could not load TrueType fonts, using default")
            title_font = ImageFont.load_default()
            body_font = ImageFont.load_default()

        # Draw title
        title_bbox = draw.textbbox((0, 0), policy.title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(
            ((width - title_width) / 2, 100),
            policy.title,
            fill='#1a73e8',
            font=title_font
        )

        # Draw content preview (first 500 characters)
        y_offset = 200
        content_preview = policy.content[:500] if policy.content else "No content"

        # Wrap text
        words = content_preview.split()
        lines = []
        current_line = []

        for word in words:
            current_line.append(word)
            line_text = ' '.join(current_line)
            bbox = draw.textbbox((0, 0), line_text, font=body_font)
            line_width = bbox[2] - bbox[0]

            if line_width > width - 200:  # Leave margins
                current_line.pop()
                lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        # Draw lines
        for line in lines[:30]:  # Max 30 lines
            draw.text((100, y_offset), line, fill='black', font=body_font)
            y_offset += 30

        # Save to bytes
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        jpeg_bytes = buffer.getvalue()
        buffer.close()

        logger.info(f"Generated JPEG: {len(jpeg_bytes)} bytes")
        return jpeg_bytes

    async def generate_download_url(
        self,
        policy_id: UUID,
        format: str,
        user_id: str,
        user_groups: list[str],
        expiration_minutes: int = 60
    ) -> str:
        """
        Generate presigned download URL for policy artifact.

        Args:
            policy_id: Policy ID
            format: 'pdf' or 'jpeg'
            user_id: Requesting user
            user_groups: User's Azure AD groups
            expiration_minutes: URL expiration time

        Returns:
            Presigned download URL
        """
        # Check access
        has_access = await self.repository.check_user_access(
            policy_id=policy_id,
            user_id=user_id,
            user_groups=user_groups
        )

        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied")

        # Get policy
        policy = await self.repository.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")

        # Get blob path
        if format == 'pdf':
            blob_path = policy.pdf_blob_path
        elif format == 'jpeg' or format == 'jpg':
            blob_path = policy.jpeg_blob_path
        else:
            raise HTTPException(status_code=400, detail="Invalid format. Use 'pdf' or 'jpeg'")

        if not blob_path:
            raise HTTPException(
                status_code=404,
                detail=f"Policy {format.upper()} not generated yet"
            )

        # Generate presigned URL
        download_url = self.storage.generate_presigned_download_url(
            blob_path=blob_path,
            expiration_minutes=expiration_minutes
        )

        logger.info(f"Generated download URL for policy {policy_id} ({format})")
        return download_url
