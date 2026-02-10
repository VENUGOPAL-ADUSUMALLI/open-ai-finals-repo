import logging
import time
from datetime import timedelta
from typing import Any

from asgiref.sync import async_to_sync
from django.utils import timezone

from authentication.presenters.resume_parser_presenter import ResumeParserPresenter
from authentication.services.resume.llm_parser import LLMParser, LLMParserError
from authentication.services.resume.text_extractor import TextExtractionError, TextExtractor
from authentication.storage.user_storage import UserStorage

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024


class ResumeParserInteractor:
    def __init__(
        self,
        storage: UserStorage,
        presenter: ResumeParserPresenter,
        llm_parser: LLMParser | None = None,
        text_extractor: TextExtractor | None = None,
    ):
        self.storage = storage
        self.presenter = presenter
        self.llm_parser = llm_parser or LLMParser()
        self.text_extractor = text_extractor or TextExtractor()

    def parse_resume_full_interactor(self, user, file_content: bytes, filename: str):
        start_time = time.monotonic()

        try:
            if not file_content or not filename:
                return self.presenter.invalid_request_response("resume_file is required.")
            if len(file_content) > MAX_FILE_SIZE_BYTES:
                return self.presenter.invalid_request_response("File size exceeds 5 MB.")
            if not filename.lower().endswith((".pdf", ".docx")):
                return self.presenter.invalid_request_response(
                    "Unsupported file type. Only PDF and DOCX are allowed."
                )

            text, extraction_method = async_to_sync(self.text_extractor.extract_text)(file_content, filename)
            if not text.strip():
                return self.presenter.no_text_extracted_response()

            parsed_resume, llm_confidence = async_to_sync(self.llm_parser.parse)(text.strip())
            processing_time = float(timedelta(seconds=time.monotonic() - start_time).total_seconds())
            parsed_resume.processing_time = processing_time

            exact_payload = self._to_exact_schema_payload(parsed_resume)
            resume_metadata = dict(exact_payload)
            resume_metadata["parsing_metadata"] = {
                "processing_time": processing_time,
                "extraction_method": extraction_method,
                "llm_confidence": llm_confidence,
                "model": self.llm_parser.model,
                "parsed_at": timezone.now().isoformat(),
            }

            self.storage.save_resume_metadata(user=user, resume_metadata=resume_metadata)
            self.storage.seed_user_profile_from_personal_info(
                user=user, personal_info=parsed_resume.personal_info
            )
            return self.presenter.successful_parse_and_store_response(exact_payload)

        except (TextExtractionError, LLMParserError):
            logger.exception("Resume parsing failed for user_id=%s", user.id)
            return self.presenter.parsing_error_response()
        except Exception:
            logger.exception("Unexpected parsing failure for user_id=%s", user.id)
            return self.presenter.parsing_error_response()

    def _to_exact_schema_payload(self, parsed_resume) -> dict[str, Any]:
        personal_info = parsed_resume.personal_info

        def normalize_experience(item: dict[str, Any]) -> dict[str, Any]:
            return {
                "company": item.get("company"),
                "position": item.get("position"),
                "start_date": item.get("start_date"),
                "end_date": item.get("end_date"),
                "is_current": bool(item.get("is_current", False)),
                "description": item.get("description"),
                "achievements": item.get("achievements") or [],
            }

        def normalize_education(item: dict[str, Any]) -> dict[str, Any]:
            return {
                "institution": item.get("institution"),
                "degree": item.get("degree"),
                "field_of_study": item.get("field_of_study"),
                "graduation_date": item.get("graduation_date"),
                "gpa": item.get("gpa"),
            }

        def normalize_skill(item: dict[str, Any]) -> dict[str, Any]:
            return {
                "category": item.get("category"),
                "skills": item.get("skills") or [],
            }

        def normalize_certification(item: dict[str, Any]) -> dict[str, Any]:
            return {
                "name": item.get("name"),
                "issuer": item.get("issuer"),
                "date": item.get("date"),
                "credential_id": item.get("credential_id"),
            }

        def normalize_project(item: dict[str, Any]) -> dict[str, Any]:
            return {
                "name": item.get("name"),
                "description": item.get("description"),
                "technologies": item.get("technologies") or [],
                "url": item.get("url"),
                "start_date": item.get("start_date"),
                "end_date": item.get("end_date"),
            }

        def normalize_language(item: dict[str, Any]) -> dict[str, Any]:
            return {
                "language": item.get("language"),
                "proficiency": item.get("proficiency"),
            }

        return {
            "personal_info": {
                "full_name": personal_info.full_name,
                "email": personal_info.email,
                "phone": personal_info.phone,
                "address": personal_info.address,
                "linkedin": personal_info.linkedin,
                "github": personal_info.github,
                "portfolio": personal_info.portfolio,
            },
            "summary": parsed_resume.summary,
            "experience": [normalize_experience(item) for item in (parsed_resume.experience or [])],
            "education": [normalize_education(item) for item in (parsed_resume.education or [])],
            "skills": [normalize_skill(item) for item in (parsed_resume.skills or [])],
            "certifications": [
                normalize_certification(item) for item in (parsed_resume.certifications or [])
            ],
            "projects": [normalize_project(item) for item in (parsed_resume.projects or [])],
            "languages": [normalize_language(item) for item in (parsed_resume.languages or [])],
        }
