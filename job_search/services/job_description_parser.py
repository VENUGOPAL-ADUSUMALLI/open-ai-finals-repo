from io import BytesIO


class JobDescriptionParseError(Exception):
    pass


def parse_job_description_file(uploaded_file) -> str:
    if uploaded_file is None:
        raise JobDescriptionParseError("No file uploaded.")

    filename = (getattr(uploaded_file, "name", "") or "").strip().lower()
    file_bytes = uploaded_file.read()
    if not file_bytes:
        raise JobDescriptionParseError("Uploaded file is empty.")

    if filename.endswith(".txt"):
        return _parse_txt(file_bytes)
    if filename.endswith(".pdf"):
        return _parse_pdf(file_bytes)
    if filename.endswith(".docx"):
        return _parse_docx(file_bytes)

    raise JobDescriptionParseError("Unsupported file type. Use .txt, .pdf, or .docx.")


def _parse_txt(file_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            text = file_bytes.decode(encoding).strip()
            if text:
                return text
        except UnicodeDecodeError:
            continue
    raise JobDescriptionParseError("Could not decode text file.")


def _parse_pdf(file_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise JobDescriptionParseError("PDF parser dependency is not installed.") from exc

    try:
        reader = PdfReader(BytesIO(file_bytes))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if not text:
            raise JobDescriptionParseError("No text could be extracted from PDF.")
        return text
    except JobDescriptionParseError:
        raise
    except Exception as exc:
        raise JobDescriptionParseError("Failed to parse PDF file.") from exc


def _parse_docx(file_bytes: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise JobDescriptionParseError("DOCX parser dependency is not installed.") from exc

    try:
        doc = Document(BytesIO(file_bytes))
        text = "\n".join(para.text for para in doc.paragraphs if para.text).strip()
        if not text:
            raise JobDescriptionParseError("No text could be extracted from DOCX.")
        return text
    except JobDescriptionParseError:
        raise
    except Exception as exc:
        raise JobDescriptionParseError("Failed to parse DOCX file.") from exc
