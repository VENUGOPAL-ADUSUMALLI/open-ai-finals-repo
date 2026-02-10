import json
from typing import Any

from django.conf import settings
from openai import AsyncOpenAI

from authentication.services.resume.models import ParsedResume, PersonalInfo


class LLMParserError(Exception):
    pass


class LLMParser:
    def __init__(self):
        self.model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
        self.api_key = getattr(settings, "OPENAI_API_KEY", "")
        self.openai_client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None

    async def parse(self, text: str) -> tuple[ParsedResume, float]:
        if not self.openai_client:
            raise LLMParserError("OpenAI API key is not configured.")
        if not text or not text.strip():
            raise LLMParserError("Resume text is empty.")

        try:
            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": self._user_prompt(text)},
                ],
                temperature=0.1,
                max_tokens=3000,
                response_format={"type": "json_object"},
                timeout=30,
            )
            content = response.choices[0].message.content
            payload = json.loads(content)
            parsed = self._convert(payload)
            confidence = self._calculate_confidence(parsed)
            parsed.confidence_score = confidence
            return parsed, confidence
        except json.JSONDecodeError as exc:
            raise LLMParserError("Model response was not valid JSON.") from exc
        except Exception as exc:
            raise LLMParserError("OpenAI parsing failed.") from exc

    def _convert(self, data: dict[str, Any]) -> ParsedResume:
        personal = data.get("personal_info") or {}
        parsed = ParsedResume(
            personal_info=PersonalInfo(
                full_name=personal.get("full_name"),
                email=personal.get("email"),
                phone=personal.get("phone"),
                address=personal.get("address"),
                linkedin=personal.get("linkedin"),
                github=personal.get("github"),
                portfolio=personal.get("portfolio"),
            ),
            summary=data.get("summary"),
            experience=data.get("experience") or [],
            education=data.get("education") or [],
            skills=data.get("skills") or [],
            certifications=data.get("certifications") or [],
            projects=data.get("projects") or [],
            languages=data.get("languages") or [],
            parsing_method="llm_openai",
        )
        return parsed

    def _calculate_confidence(self, parsed_resume: ParsedResume) -> float:
        score = 0.0
        checks = 0
        if parsed_resume.personal_info.full_name:
            score += 0.25
        checks += 1
        if parsed_resume.personal_info.email:
            score += 0.2
        checks += 1
        if parsed_resume.personal_info.phone:
            score += 0.15
        checks += 1
        if parsed_resume.experience:
            score += 0.2
        checks += 1
        if parsed_resume.skills:
            score += 0.2
        checks += 1
        return min(score / checks, 1.0) if checks else 0.0

    def _system_prompt(self) -> str:
        return (
            "You are an expert resume parser. Return only valid JSON and never include prose. "
            "Extract only explicit information from the resume."
        )

    def _user_prompt(self, text: str) -> str:
        return f"""
Parse this resume text and return only JSON in this shape:
{{
  "personal_info": {{
    "full_name": "string or null",
    "email": "string or null",
    "phone": "string or null",
    "address": "string or null",
    "linkedin": "string or null",
    "github": "string or null",
    "portfolio": "string or null"
  }},
  "summary": "string or null",
  "experience": [],
  "education": [],
  "skills": [],
  "certifications": [],
  "projects": [],
  "languages": []
}}

Resume:
{text}
""".strip()
