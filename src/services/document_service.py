import logging
import io
from typing import Dict, Any, Optional
import httpx
import PyPDF2
from docx import Document as DocxDocument
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class TeamsDocumentService:
    """Process PDF and DOCX files from Teams attachments."""
    
    def __init__(self, project_id: str, location: str = "us-east4"):
        """Initialize service."""
        self.project_id = project_id
        self.location = location
        
        self.gemini_client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location
        )
        logger.info("✅ Teams Document Service initialized")
    
    def sanitize_text(self, text: str, max_length: int = 100000) -> str:
        """
        Remove null bytes and other problematic characters for PostgreSQL.
        
        Args:
            text: Raw extracted text
            max_length: Maximum character length (default 100k)
            
        Returns:
            Sanitized text safe for PostgreSQL JSONB storage
        """
        if not text:
            return ""
        
        text = text.replace('\x00', '')
        
        text = ''.join(
            char for char in text 
            if char in ('\n', '\t', '\r') or ord(char) >= 32
        )
        
        lines = text.split('\n')
        normalized_lines = [' '.join(line.split()) for line in lines]
        text = '\n'.join(line for line in normalized_lines if line)
        
        if len(text) > max_length:
            text = text[:max_length] + "\n\n[... Content truncated due to length ...]"
            logger.warning(f"⚠️ Text truncated from {len(text)} to {max_length} chars")
        
        return text
    
    async def download_file(
        self, 
        download_url: str, 
        bot_token: Optional[str] = None
    ) -> bytes:
        """
        Download file from Teams.
        
        Args:
            download_url: URL from Teams attachment
            bot_token: Bot Framework token (required for some files)
            
        Returns:
            File content as bytes
        """
        headers = {}
        if bot_token:
            headers["Authorization"] = f"Bearer {bot_token}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(download_url, headers=headers)
                response.raise_for_status()
                
                logger.info(f"✅ Downloaded {len(response.content)} bytes")
                return response.content
                
        except Exception as e:
            logger.error(f"❌ Download failed: {e}")
            raise
    
    async def extract_text_from_pdf(self, file_content: bytes) -> Dict[str, Any]:
        """Extract text from PDF using PyPDF2."""
        try:
            pdf_file = io.BytesIO(file_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            text_parts = []
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            
            full_text = "\n\n".join(text_parts)
            
            full_text = self.sanitize_text(full_text)
            
            logger.info(f"✅ Extracted and sanitized {len(full_text)} chars from PDF")
            
            return {
                "success": True,
                "text": full_text,
                "page_count": len(pdf_reader.pages),
                "char_count": len(full_text),
                "method": "pypdf2"
            }
            
        except Exception as e:
            logger.error(f"❌ PDF extraction failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def extract_text_from_docx(self, file_content: bytes) -> Dict[str, Any]:
        """Extract text from DOCX."""
        try:
            docx_file = io.BytesIO(file_content)
            doc = DocxDocument(docx_file)
            
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            full_text = "\n\n".join(paragraphs)
            
            full_text = self.sanitize_text(full_text)
            
            logger.info(f"✅ Extracted and sanitized {len(full_text)} chars from DOCX")
            
            return {
                "success": True,
                "text": full_text,
                "paragraph_count": len(paragraphs),
                "char_count": len(full_text),
                "method": "python-docx"
            }
            
        except Exception as e:
            logger.error(f"❌ DOCX extraction failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def process_file_with_gemini(
        self,
        file_content: bytes,
        mime_type: str,
        user_question: str,
        filename: str
    ) -> Dict[str, Any]:
        """
        Process file directly with Gemini (alternative to text extraction).
        
        Args:
            file_content: File bytes
            mime_type: MIME type
            user_question: User's question about the file
            filename: Original filename
            
        Returns:
            Gemini's response
        """
        try:
            logger.info(f"🤖 Processing {filename} with Gemini")
            
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(
                        data=file_content,
                        mime_type=mime_type
                    ),
                    types.Part.from_text(
                        text=f"File: {filename}\n\nQuestion: {user_question}"
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=8192
                )
            )
            
            response_text = self.sanitize_text(response.text)
            
            return {
                "success": True,
                "response": response_text,
                "method": "gemini_native"
            }
            
        except Exception as e:
            logger.error(f"❌ Gemini processing failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
