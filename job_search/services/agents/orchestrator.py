import logging
from datetime import datetime
from time import perf_counter

from job_search.services.agents.contracts import clamp_score
from job_search.services.skill_matching import (
    calculate_skill_match_score,
    extract_skills_from_resume,
)

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    'work_mode': 0.20,
    'location': 0.20,
    'stipend': 0.25,
    'company_size': 0.10,
    'experience_level': 0.10,
    'sector': 0.05,
    'role_match': 0.05,
    'company_preference': 0.05,
    'skill_match': 0.35,
}


def _ordinal(value):
    if value is None:
        return 0
    if hasattr(value, 'toordinal'):
        return value.toordinal()
    if isinstance(value, datetime):
        return int(value.timestamp())
    return 0


def _effective_weights(user_weights):
    """Merge user-provided weights with defaults, user weights take priority."""
    weights = DEFAULT_WEIGHTS.copy()
    if user_weights and isinstance(user_weights, dict):
        for key, value in user_weights.items():
            if key in weights:
                weights[key] = value
    return weights


def run_agent_pipeline(jobs, preferences, candidate_profile=None):
    """Run deterministic heuristic + optional GPT scoring pipeline.

    Phase 1: Heuristic-score all jobs (deterministic, includes resume skill matching)
    Phase 2: If GPT enabled, refine top N with GPT scoring and blend results
    """
    jobs = list(jobs)
    candidate_profile = candidate_profile or {}

    # Agent 1: preference interpreter — use user weights if provided
    user_weights = preferences.get('weights', {})
    effective = _effective_weights(user_weights)

    priority_weights = {
        'skill_match': effective['skill_match'],
        'stipend': effective['stipend'],
        'location': effective['location'],
        'company_type': effective['company_size'],
    }

    # Extract resume skills once before the loop
    resume_metadata = candidate_profile.get('resume_metadata', {})
    user_skills = extract_skills_from_resume(resume_metadata)

    context = {
        'priority_weights': priority_weights,
        'effective_weights': effective,
        'career_stage': candidate_profile.get('career_stage', 'EARLY'),
        'risk_tolerance': candidate_profile.get('risk_tolerance', 'LOW'),
        'skill_matching_active': len(user_skills) > 0,
        'user_skills_count': len(user_skills),
    }

    # Phase 1: Heuristic scoring
    result_rows = []
    for job in jobs:
        desc_len = len((job.description or '').strip())
        has_apply = bool(job.apply_url)
        has_company = bool(job.company_name)

        quality = 0.4
        quality += 0.2 if desc_len > 120 else 0.0
        quality += 0.2 if has_apply else 0.0
        quality += 0.2 if has_company else 0.0
        quality = clamp_score(quality)

        fit = 0.0
        reasons = []

        # Skill matching from resume
        if user_skills:
            skill_score, matched_skills = calculate_skill_match_score(user_skills, job)
            fit += effective['skill_match'] * skill_score
            if matched_skills:
                reasons.append(
                    f"Skill match ({len(matched_skills)}/{len(user_skills)}): "
                    f"{', '.join(matched_skills[:3])}"
                )

        if (job.work_mode or '') == preferences.get('work_mode'):
            fit += effective['work_mode']
            reasons.append('Work mode match')

        if (job.employment_type or '') == preferences.get('employment_type'):
            fit += 0.15
            reasons.append('Employment type match')

        if preferences.get('location', '') and preferences['location'] in (job.location or '').lower():
            fit += effective['location'] * 0.5
            reasons.append('Location alignment')

        if (job.company_size or '') == preferences.get('company_size_preference'):
            fit += effective['company_size']
            reasons.append('Company size preference match')

        # Experience level match
        exp_level = preferences.get('experience_level')
        if exp_level and (job.experience_level or '') == exp_level:
            fit += effective['experience_level']
            reasons.append('Experience level match')

        # Sector match (soft boost for preferred sectors)
        preferred_sectors = preferences.get('preferred_sectors', [])
        if preferred_sectors and job.sector:
            job_sector_lower = job.sector.lower()
            for sector in preferred_sectors:
                if sector.lower() in job_sector_lower:
                    fit += effective['sector']
                    reasons.append(f'Sector match: {sector}')
                    break

        # Role match (soft boost for preferred roles)
        preferred_roles = preferences.get('preferred_roles', [])
        if preferred_roles and job.title:
            title_lower = job.title.lower()
            for role in preferred_roles:
                if role.lower() in title_lower:
                    fit += effective['role_match']
                    reasons.append(f'Role match: {role}')
                    break

        # Preferred company boost
        preferred_companies = preferences.get('preferred_companies', [])
        if preferred_companies and job.company_name:
            company_lower = job.company_name.lower()
            for company in preferred_companies:
                if company.lower() in company_lower:
                    fit += effective['company_preference']
                    reasons.append(f'Preferred company: {company}')
                    break

        stipend_min = preferences.get('stipend_min')
        stipend_max = preferences.get('stipend_max')
        if stipend_min is not None and stipend_max is not None:
            if job.stipend_min is not None and job.stipend_max is not None:
                fit += effective['stipend'] * 0.2
                reasons.append('Stipend overlap available')

        fit = clamp_score(fit)

        weighted = context['priority_weights']
        selection = (
            0.45 * fit
            + 0.35 * quality
            + 0.10 * weighted['location']
            + 0.10 * weighted['company_type']
        )
        selection = clamp_score(selection)

        result_rows.append(
            {
                'job': job,
                'job_id': job.id,
                'job_quality_score': quality,
                'fit_score': fit,
                'selection_probability': selection,
                'why': '; '.join(reasons[:3]) if reasons else 'General alignment with preferences',
                'published_at_ord': _ordinal(job.published_at),
                'created_at_ord': _ordinal(job.created_at),
                'agent_trace': {
                    'context': context,
                    'fit_reasons': reasons,
                    'scoring_method': 'heuristic',
                },
            }
        )

    result_rows.sort(
        key=lambda item: (
            -item['selection_probability'],
            -item['published_at_ord'],
            -item['created_at_ord'],
            str(item['job'].job_id),
        )
    )

    # Phase 2: GPT scoring refinement (optional)
    gpt_metrics = _apply_gpt_scoring(result_rows, candidate_profile, preferences)

    # Re-sort after GPT blending if applied
    if gpt_metrics.get('applied'):
        result_rows.sort(
            key=lambda item: (
                -item['selection_probability'],
                -item['published_at_ord'],
                -item['created_at_ord'],
                str(item['job'].job_id),
            )
        )

    top_jobs = []
    for idx, row in enumerate(result_rows, start=1):
        top_jobs.append(
            {
                'rank': idx,
                'job_id': row['job'].id,
                'selection_probability': row['selection_probability'],
                'fit_score': row['fit_score'],
                'job_quality_score': row['job_quality_score'],
                'why': row['why'],
                'agent_trace': row['agent_trace'],
            }
        )

    return {
        'context': context,
        'top_jobs': top_jobs,
        'total_ranked': len(result_rows),
        'fallback_applied': len(result_rows) == 0,
        'fallback_reason': 'NO_MATCHING_JOBS' if len(result_rows) == 0 else '',
        'gpt_metrics': gpt_metrics,
    }


def _apply_gpt_scoring(result_rows, candidate_profile, preferences):
    """Phase 2: Optional GPT scoring refinement on top candidates."""
    from job_search.services.openai_client import is_gpt_scoring_enabled

    if not is_gpt_scoring_enabled() or not result_rows:
        return {'applied': False, 'reason': 'disabled_or_no_jobs'}

    try:
        from django.conf import settings as django_settings

        from job_search.services.agents.gpt_scorer import score_jobs_with_gpt

        top_n = getattr(django_settings, 'GPT_JOB_SCORING_TOP_N', 15)
        candidates = result_rows[:top_n]

        started = perf_counter()
        gpt_results = score_jobs_with_gpt(candidates, candidate_profile, preferences)
        elapsed_ms = int((perf_counter() - started) * 1000)

        scored_count = 0
        for row, gpt_score in zip(candidates, gpt_results):
            if gpt_score and gpt_score.get('success'):
                heuristic = row['selection_probability']
                gpt_overall = clamp_score(gpt_score.get('overall_score', 0.0))
                blended = 0.40 * heuristic + 0.60 * gpt_overall
                row['selection_probability'] = clamp_score(blended)
                row['agent_trace']['gpt_score'] = gpt_score
                row['agent_trace']['scoring_method'] = 'heuristic+gpt'
                gpt_reasoning = gpt_score.get('reasoning', '')
                if gpt_reasoning:
                    row['why'] = gpt_reasoning[:200]
                scored_count += 1

        return {
            'applied': True,
            'jobs_scored': scored_count,
            'jobs_attempted': len(candidates),
            'elapsed_ms': elapsed_ms,
        }
    except Exception:
        logger.exception('GPT scoring phase failed, using heuristic results')
        return {'applied': False, 'reason': 'gpt_error'}
