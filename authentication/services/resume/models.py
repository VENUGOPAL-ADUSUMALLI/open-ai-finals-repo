from dataclasses import dataclass, field
from typing import Any


@dataclass
class PersonalInfo:
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "linkedin": self.linkedin,
            "github": self.github,
            "portfolio": self.portfolio,
        }


@dataclass
class ParsedResume:
    personal_info: PersonalInfo = field(default_factory=PersonalInfo)
    summary: str | None = None
    experience: list[dict[str, Any]] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)
    skills: list[dict[str, Any]] = field(default_factory=list)
    certifications: list[dict[str, Any]] = field(default_factory=list)
    projects: list[dict[str, Any]] = field(default_factory=list)
    languages: list[dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    parsing_method: str = "llm_openai"
    processing_time: float = 0.0

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "personal_info": self.personal_info.to_dict(),
            "summary": self.summary,
            "experience": self.experience,
            "education": self.education,
            "skills": self.skills,
            "certifications": self.certifications,
            "projects": self.projects,
            "languages": self.languages,
        }
