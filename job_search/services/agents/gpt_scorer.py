"""GPT-powered job scoring service."""

import json
import logging
from dataclasses import dataclass
from time import perf_counter

from django.conf import settings

from job_search.services.openai_client import get_model_name, get_sync_openai_client

logger = logging.getLogger(__name__)

GPT_SCORING_SYSTEM_PROMPT = """\
You are an expert career advisor and job matching specialist.
Score how well a candidate fits a specific job on 4 dimensions.

Return ONLY valid JSON with this exact structure:
{
    "role_fit": <float 0.0-1.0>,
    "skill_alignment": <float 0.0-1.0>,
    "career_trajectory": <float 0.0-1.0>,
    "culture_signals": <float 0.0-1.0>,
    "overall_score": <float 0.0-1.0>,
    "reasoning": "<1-2 sentence explanation of the match quality>"
}

Scoring guidelines:
- role_fit: How well does the candidate's experience match the role requirements?
- skill_alignment: What fraction of required skills does the candidate have?
- career_trajectory: Is this job a logical next step for the candidate's career?
- culture_signals: Company size, work mode, sector alignment with candidate preferences
- overall_score: Weighted average favoring skill_alignment and role_fit
- reasoning: Be specific about what makes this a good or poor fit"""


@dataclass
class GPTJobScore:
    success: bool = False
    role_fit: float = 0.0
    skill_alignment: float = 0.0
    career_trajectory: float = 0.0
    culture_signals: float = 0.0
    overall_score: float = 0.0
    reasoning: str = ''
    error: str = ''

    def to_dict(self):
        return {
            'success': self.success,
            'role_fit': self.role_fit,
            'skill_alignment': self.skill_alignment,
            'career_trajectory': self.career_trajectory,
            'culture_signals': self.culture_signals,
            'overall_score': self.overall_score,
            'reasoning': self.reasoning,
            'error': self.error,
        }


def _build_candidate_summary(candidate_profile, preferences):
    """Extract a concise candidate summary for the GPT prompt."""
    parts = []
    resume = candidate_profile.get('resume_metadata', {})

    summary = resume.get('summary', '')
    if summary:
        parts.append(f"Summary: {summary[:300]}")

    skills = resume.get('skills', [])
    if skills:
        skill_lines = []
        for group in skills[:6]:
            if isinstance(group, dict):
                cat = group.get('category', 'General')
                items = group.get('skills', [])
                skill_lines.append(f"  {cat}: {', '.join(items[:8])}")
            elif isinstance(group, str):
                skill_lines.append(f"  {group}")
        if skill_lines:
            parts.append("Skills:\n" + "\n".join(skill_lines))

    experience = resume.get('experience', [])
    for exp in experience[:2]:
        if isinstance(exp, dict):
            company = exp.get('company', 'Unknown')
            position = exp.get('position', 'Unknown')
            desc = (exp.get('description', '') or '')[:150]
            parts.append(f"Experience: {position} at {company}. {desc}")

    education = resume.get('education', [])
    for edu in education[:1]:
        if isinstance(edu, dict):
            inst = edu.get('institution', '')
            degree = edu.get('degree', '')
            field_val = edu.get('field_of_study', '')
            parts.append(f"Education: {degree} in {field_val} from {inst}")

    career_stage = candidate_profile.get('career_stage', 'EARLY')
    parts.append(f"Career stage: {career_stage}")

    if preferences.get('work_mode'):
        parts.append(f"Preferred work mode: {preferences['work_mode']}")
    if preferences.get('location'):
        parts.append(f"Preferred location: {preferences['location']}")

    return "\n".join(parts) if parts else "No candidate information available."


def _build_job_summary(job):
    """Extract a concise job summary for the GPT prompt."""
    parts = []
    if job.title:
        parts.append(f"Title: {job.title}")
    if job.company_name:
        parts.append(f"Company: {job.company_name}")
    if job.location:
        parts.append(f"Location: {job.location}")
    if job.work_mode:
        parts.append(f"Work mode: {job.work_mode}")
    if job.sector:
        parts.append(f"Sector: {job.sector}")
    if job.experience_level:
        parts.append(f"Experience level: {job.experience_level}")
    if job.company_size:
        parts.append(f"Company size: {job.company_size}")
    if job.description:
        parts.append(f"Description: {job.description[:800]}")
    return "\n".join(parts) if parts else "No job information available."


def score_single_job_with_gpt(job, candidate_profile, preferences):
    """Score a single job using GPT. Returns a GPTJobScore dict."""
    client = get_sync_openai_client()
    if not client:
        return GPTJobScore(error='OpenAI client not available').to_dict()

    timeout = getattr(settings, 'GPT_JOB_SCORING_TIMEOUT', 20)
    model = get_model_name()

    candidate_text = _build_candidate_summary(candidate_profile, preferences)
    job_text = _build_job_summary(job)

    user_prompt = (
        "Score how well this candidate fits the following job.\n\n"
        f"CANDIDATE:\n{candidate_text}\n\n"
        f"JOB:\n{job_text}\n\n"
        "Return ONLY the JSON scoring object."
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": GPT_SCORING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=500,
            response_format={"type": "json_object"},
            timeout=timeout,
        )

        content = response.choices[0].message.content if response.choices else None
        if not content:
            return GPTJobScore(error='Empty GPT response').to_dict()

        data = json.loads(content)
        return GPTJobScore(
            success=True,
            role_fit=float(data.get('role_fit', 0.0)),
            skill_alignment=float(data.get('skill_alignment', 0.0)),
            career_trajectory=float(data.get('career_trajectory', 0.0)),
            culture_signals=float(data.get('culture_signals', 0.0)),
            overall_score=float(data.get('overall_score', 0.0)),
            reasoning=str(data.get('reasoning', '')),
        ).to_dict()

    except json.JSONDecodeError:
        return GPTJobScore(error='Invalid JSON from GPT').to_dict()
    except Exception as exc:
        return GPTJobScore(error=f'GPT scoring failed: {str(exc)[:100]}').to_dict()


def score_jobs_with_gpt(result_rows, candidate_profile, preferences):
    """Score multiple jobs with GPT, respecting a total time budget.

    Returns a list of GPTJobScore dicts, one per input row.
    """
    budget_seconds = 80  # safety margin within 120s Celery limit
    started = perf_counter()
    results = []

    for row in result_rows:
        elapsed = perf_counter() - started
        if elapsed >= budget_seconds:
            logger.warning(
                'GPT scoring time budget exceeded (%.1fs), %d/%d jobs scored',
                elapsed, len(results), len(result_rows),
            )
            results.append(GPTJobScore(error='Time budget exceeded').to_dict())
            continue

        job = row['job']
        score = score_single_job_with_gpt(job, candidate_profile, preferences)
        results.append(score)

    return results
