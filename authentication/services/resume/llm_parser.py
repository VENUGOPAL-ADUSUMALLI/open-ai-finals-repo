"""LLM-based resume parsing using OpenAI GPT models."""

import json
from typing import Any

import openai
from django.conf import settings

from authentication.services.resume.models import ParsedResume, PersonalInfo


class LLMParserError(Exception):
    pass


class LLMParser:
    """OpenAI GPT-based resume parser."""

    def __init__(self):
        self.model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
        self.skill_categories = {
            "Frontend": [
                "JavaScript", "TypeScript", "React", "Angular", "Vue.js",
                "Next.js", "Nuxt.js", "HTML", "CSS", "Sass/SCSS",
                "Tailwind CSS", "Bootstrap", "jQuery",
            ],
            "Backend": [
                "Node.js", "Express.js", "Python", "Django", "Flask", "FastAPI",
                "Java", "Spring Boot", "PHP", "Laravel", "Ruby on Rails",
                "Go", "C#", ".NET", "REST APIs", "GraphQL",
            ],
            "Database": [
                "MySQL", "PostgreSQL", "MongoDB", "Oracle", "SQL Server",
                "Redis", "Elasticsearch", "Firebase", "DynamoDB", "Cassandra",
            ],
            "Mobile": [
                "React Native", "Flutter", "Kotlin", "Java (Android)",
                "Swift", "iOS Development", "Ionic",
            ],
            "AI/ML": [
                "Python", "TensorFlow", "PyTorch", "Scikit-learn", "Keras",
                "Numpy", "Pandas", "Matplotlib", "Seaborn", "OpenCV",
                "NLTK", "Spacy", "Data Visualization", "Deep Learning",
                "Computer Vision", "Natural Language Processing (NLP)",
                "MLOps",
            ],
            "Generative AI": [
                "OpenAI", "Azure OpenAI", "Google Vertex AI", "Anthropic Claude", "Hugging Face",
                "LangChain", "LangGraph", "LlamaIndex", "Haystack",
                "RAG", "Embeddings", "FAISS", "Chroma", "Weaviate", "Pinecone", "PGVector",
                "LoRA", "QLoRA", "PEFT", "Parameter Efficient Fine-Tuning", "Knowledge Distillation",
                "vLLM", "Text Generation Inference (TGI)", "FastAPI", "gRPC",
                "Ragas", "TruLens", "Guardrails AI", "Prompt Evaluation", "Prompt Caching",
                "Prompt Engineering", "Function Calling", "Tool Use", "JSON Schema",
                "Stable Diffusion", "SDXL", "ControlNet", "ComfyUI", "Automatic1111",
                "Whisper", "Text-to-Speech (TTS)", "Image Captioning",
                "PII Redaction", "Content Moderation", "Hallucination Mitigation",
            ],
            "DevOps & Cloud": [
                "AWS", "Azure", "Google Cloud (GCP)", "Docker", "Kubernetes",
                "Jenkins", "CI/CD", "Terraform", "Ansible", "Linux",
                "Git", "GitHub Actions", "Prometheus", "Grafana",
            ],
            "Data & Analytics": [
                "SQL", "Python", "R", "Excel", "Power BI", "Tableau",
                "Looker", "Data Analysis", "Data Engineering", "ETL Pipelines",
                "BigQuery", "Hadoop", "Spark",
            ],
            "Cybersecurity": [
                "Network Security", "Penetration Testing", "Ethical Hacking",
                "OWASP", "Kali Linux", "Burp Suite", "SIEM", "Firewalls",
                "Cloud Security", "Identity & Access Management (IAM)",
            ],
            "Blockchain & Web3": [
                "Solidity", "Ethereum", "Smart Contracts", "Web3.js",
                "Polygon", "NFT Development", "DeFi", "Rust (Blockchain)",
            ],
            "Testing & QA": [
                "Selenium", "Cypress", "Playwright", "JUnit", "PyTest",
                "Postman", "JMeter", "TestNG", "Unit Testing", "Integration Testing",
            ],
            "Emerging Tech": ["IoT", "AR/VR", "Robotics", "Embedded Systems"],
        }

        api_key = getattr(settings, "OPENAI_API_KEY", "")
        self.openai_client = openai.AsyncOpenAI(api_key=api_key) if api_key else None

    async def parse(self, text: str) -> tuple[ParsedResume, float]:
        """Parse resume using OpenAI LLM."""
        if not self.openai_client:
            raise LLMParserError("OpenAI client not available or not configured")
        if not text or not text.strip():
            raise LLMParserError("Resume text is empty.")

        try:
            return await self._parse_with_openai(text)
        except Exception as exc:
            raise LLMParserError(f"LLM parsing failed: {str(exc)}") from exc

    async def _parse_with_openai(self, text: str) -> tuple[ParsedResume, float]:
        prompt = self._create_parsing_prompt(text)

        try:
            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=4000,
                response_format={"type": "json_object"},
                timeout=30,
            )

            content = response.choices[0].message.content if response.choices else None
            if not content:
                raise LLMParserError("OpenAI returned empty response content.")

            result = json.loads(content)
            parsed_resume = self._convert_to_parsed_resume(result)
            parsed_resume.parsing_method = "llm_openai"

            confidence = self._calculate_llm_confidence(parsed_resume)
            parsed_resume.confidence_score = confidence
            return parsed_resume, confidence
        except json.JSONDecodeError as exc:
            raise LLMParserError("Model response was not valid JSON.") from exc
        except Exception as exc:
            raise LLMParserError(f"OpenAI parsing error: {str(exc)}") from exc

    def _get_system_prompt(self) -> str:
        return """You are an expert resume parser. Extract information from resumes and return it in the specified JSON format.

Rules:
1. Extract only information that is explicitly present in the resume
2. Use null for missing information, don't make assumptions
3. For dates, preserve the original format when possible
4. For experience, separate each job into individual entries
5. IMPORTANT: Categorize skills into these specific categories based on the technology/skill mentioned:
   - Frontend: JavaScript, TypeScript, React, Angular, Vue.js, HTML, CSS, etc.
   - Backend: Node.js, Python, Django, Flask, FastAPI, Java, Spring Boot, etc.
   - Database: MySQL, PostgreSQL, MongoDB, Redis, etc.
   - Mobile: React Native, Flutter, Kotlin, Swift, etc.
   - AI/ML: TensorFlow, PyTorch, Scikit-learn, Machine Learning, etc.
   - Generative AI: OpenAI, LangChain, RAG, LLM, GPT, etc.
   - DevOps & Cloud: AWS, Azure, Docker, Kubernetes, CI/CD, etc.
   - Data & Analytics: SQL, Power BI, Tableau, Data Analysis, etc.
   - Cybersecurity: Network Security, Penetration Testing, etc.
   - Blockchain & Web3: Solidity, Ethereum, Smart Contracts, etc.
   - Testing & QA: Selenium, Cypress, Unit Testing, etc.
   - Emerging Tech: IoT, AR/VR, Robotics, etc.
6. Only include categories that have matching skills from the resume
7. Extract achievements and accomplishments from job descriptions
8. Return valid JSON only, no additional text

Return the data in this exact JSON structure:
{
  "personal_info": {
    "full_name": "string or null",
    "email": "string or null",
    "phone": "string or null",
    "address": "string or null",
    "linkedin": "string or null",
    "github": "string or null",
    "portfolio": "string or null"
  },
  "summary": "string or null",
  "experience": [
    {
      "company": "string or null",
      "position": "string or null",
      "start_date": "string or null",
      "end_date": "string or null",
      "is_current": "boolean",
      "description": "string or null",
      "achievements": ["array of strings"]
    }
  ],
  "education": [
    {
      "institution": "string or null",
      "degree": "string or null",
      "field_of_study": "string or null",
      "graduation_date": "string or null",
      "gpa": "string or null"
    }
  ],
  "skills": [
    {
      "category": "string",
      "skills": ["array of strings"]
    }
  ],
  "certifications": [
    {
      "name": "string or null",
      "issuer": "string or null",
      "date": "string or null",
      "credential_id": "string or null"
    }
  ],
  "projects": [
    {
      "name": "string or null",
      "description": "string or null",
      "technologies": ["array of strings"],
      "url": "string or null",
      "start_date": "string or null",
      "end_date": "string or null"
    }
  ],
  "languages": [
    {
      "language": "string or null",
      "proficiency": "string or null"
    }
  ]
}"""

    def _create_parsing_prompt(self, text: str) -> str:
        return f"""Please parse the following resume and extract all relevant information:

{text}

Extract all information accurately and return it in the specified JSON format. Focus on:
1. Personal information (name, email, phone, address, social links)
2. Professional summary
3. Work experience with details
4. Education history
5. Skills categorized by technology area
6. Certifications
7. Projects
8. Languages

Return only valid JSON, no additional text or explanations."""

    def _convert_to_parsed_resume(self, data: dict[str, Any]) -> ParsedResume:
        personal_info_data = data.get("personal_info", {})
        personal_info = PersonalInfo(
            full_name=personal_info_data.get("full_name"),
            email=personal_info_data.get("email"),
            phone=personal_info_data.get("phone"),
            address=personal_info_data.get("address"),
            linkedin=personal_info_data.get("linkedin"),
            github=personal_info_data.get("github"),
            portfolio=personal_info_data.get("portfolio"),
        )

        return ParsedResume(
            personal_info=personal_info,
            summary=data.get("summary"),
            experience=data.get("experience", []),
            education=data.get("education", []),
            skills=data.get("skills", []),
            certifications=data.get("certifications", []),
            projects=data.get("projects", []),
            languages=data.get("languages", []),
        )

    def _calculate_llm_confidence(self, parsed_resume: ParsedResume) -> float:
        score = 0.0
        total_checks = 0

        personal_info = parsed_resume.personal_info
        if personal_info.full_name:
            score += 0.2
        if personal_info.email:
            score += 0.2
        if personal_info.phone:
            score += 0.1
        total_checks += 3

        if parsed_resume.experience:
            score += 0.2
            total_checks += 1

        if parsed_resume.education:
            score += 0.1
            total_checks += 1

        if parsed_resume.skills:
            score += 0.1
            total_checks += 1

        if parsed_resume.summary:
            score += 0.1
            total_checks += 1

        return min(score / total_checks, 1.0) if total_checks > 0 else 0.0
