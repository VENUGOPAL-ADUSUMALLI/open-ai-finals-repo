import logging
import time
from datetime import timedelta

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

            resume_metadata = parsed_resume.to_storage_dict()
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
            return self.presenter.successful_parse_and_store_response()

        except (TextExtractionError, LLMParserError):
            logger.exception("Resume parsing failed for user_id=%s", user.id)
            return self.presenter.parsing_error_response()
        except Exception:
            logger.exception("Unexpected parsing failure for user_id=%s", user.id)
            return self.presenter.parsing_error_response()
