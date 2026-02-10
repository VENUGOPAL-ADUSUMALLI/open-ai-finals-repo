from io import BytesIO


class TextExtractionError(Exception):
    pass


class TextExtractor:
    SUPPORTED_EXTENSIONS = {".pdf", ".docx"}

    async def extract_text(self, file_content: bytes, filename: str) -> tuple[str, str]:
        if not file_content:
            raise TextExtractionError("Uploaded file is empty.")

        file_name = (filename or "").strip().lower()
        if file_name.endswith(".pdf"):
            return self._extract_pdf(file_content), "pdf"
        if file_name.endswith(".docx"):
            return self._extract_docx(file_content), "docx"

        raise TextExtractionError("Unsupported file type. Only PDF and DOCX are allowed.")

    def _extract_pdf(self, file_content: bytes) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise TextExtractionError("PDF parser dependency is not installed.") from exc

        try:
            reader = PdfReader(BytesIO(file_content))
            chunks = []
            for page in reader.pages:
                chunks.append(page.extract_text() or "")
            return "\n".join(chunks).strip()
        except Exception as exc:
            raise TextExtractionError("Failed to read PDF file.") from exc

    def _extract_docx(self, file_content: bytes) -> str:
        try:
            from docx import Document
        except ImportError as exc:
            raise TextExtractionError("DOCX parser dependency is not installed.") from exc

        try:
            doc = Document(BytesIO(file_content))
            return "\n".join(para.text for para in doc.paragraphs if para.text).strip()
        except Exception as exc:
            raise TextExtractionError("Failed to read DOCX file.") from exc
