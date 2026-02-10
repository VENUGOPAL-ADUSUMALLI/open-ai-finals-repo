import re

from job_search.services.agents.contracts import clamp_score


def extract_skills_from_resume(resume_metadata):
    """Flatten all skills from resume_metadata into a set of lowercase strings."""
    all_skills = set()
    if not resume_metadata:
        return all_skills

    skills_list = resume_metadata.get('skills', [])
    for skill_group in skills_list:
        if isinstance(skill_group, dict):
            for skill in skill_group.get('skills', []):
                if isinstance(skill, str) and skill.strip():
                    all_skills.add(skill.strip().lower())
            category = skill_group.get('category', '')
            if isinstance(category, str) and category.strip():
                all_skills.add(category.strip().lower())
        elif isinstance(skill_group, str) and skill_group.strip():
            all_skills.add(skill_group.strip().lower())

    return all_skills


def calculate_skill_match_score(user_skills, job):
    """
    Compare user skills against a job's title + description using keyword matching.

    Returns (score: float 0.0-1.0, matched_skills: list[str])
    """
    if not user_skills:
        return 0.0, []

    text_parts = []
    if job.title:
        text_parts.append(job.title)
    if job.description:
        text_parts.append(job.description)
    if job.work_type:
        text_parts.append(job.work_type)
    if job.sector:
        text_parts.append(job.sector)

    job_text = ' '.join(text_parts).lower()

    matched = []
    for skill in user_skills:
        if len(skill) <= 2:
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, job_text):
                matched.append(skill)
        else:
            if skill in job_text:
                matched.append(skill)

    score = len(matched) / len(user_skills) if user_skills else 0.0
    return clamp_score(score), sorted(matched)


def score_and_rank_jobs(jobs, resume_metadata, top_n=10):
    """
    Score a queryset of jobs against the user's resume skills.
    Returns a list of dicts sorted by composite_score descending, capped to top_n.
    """
    user_skills = extract_skills_from_resume(resume_metadata)

    if not user_skills:
        results = []
        for job in jobs[:top_n]:
            results.append({
                'job': job,
                'skill_match_score': 0.0,
                'matched_skills': [],
                'composite_score': 0.0,
                'match_reasons': ['No skills found in resume for matching'],
            })
        return results

    scored = []
    for job in jobs:
        skill_score, matched = calculate_skill_match_score(user_skills, job)

        reasons = []
        if matched:
            displayed = matched[:5]
            reasons.append(
                f"Skills match: {', '.join(displayed)}"
                + (f' (+{len(matched) - 5} more)' if len(matched) > 5 else '')
            )
            reasons.append(f'{len(matched)}/{len(user_skills)} resume skills found in job')

        scored.append({
            'job': job,
            'skill_match_score': round(skill_score, 4),
            'matched_skills': matched,
            'composite_score': round(skill_score, 4),
            'match_reasons': reasons if reasons else ['No skill overlap found'],
        })

    scored.sort(
        key=lambda item: (
            -item['composite_score'],
            -(item['job'].published_at.toordinal() if item['job'].published_at else 0),
        )
    )

    return scored[:top_n]
