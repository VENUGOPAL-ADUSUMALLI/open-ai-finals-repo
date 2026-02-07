from datetime import datetime

from job_search.services.agents.contracts import clamp_score


def _ordinal(value):
    if value is None:
        return 0
    if hasattr(value, 'toordinal'):
        return value.toordinal()
    if isinstance(value, datetime):
        return int(value.timestamp())
    return 0


def run_agent_pipeline(jobs, preferences, candidate_profile=None):
    """Run deterministic fallback implementation of 5-agent pipeline with strict JSON payloads.

    This is OpenAI-ready architecture, but uses local deterministic heuristics by default
    so the backend works without external LLM dependencies.
    """
    jobs = list(jobs)
    candidate_profile = candidate_profile or {}

    # Agent 1: preference interpreter
    priority_weights = {
        'skill_match': 0.35,
        'stipend': 0.25,
        'location': 0.20,
        'company_type': 0.20,
    }
    context = {
        'priority_weights': priority_weights,
        'career_stage': candidate_profile.get('career_stage', 'EARLY'),
        'risk_tolerance': candidate_profile.get('risk_tolerance', 'LOW'),
    }

    # Agent 2 + 3 + 4 heuristic scoring
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

        fit = 0.35
        reasons = []

        if (job.work_mode or '') == preferences.get('work_mode'):
            fit += 0.20
            reasons.append('Work mode match')

        if (job.employment_type or '') == preferences.get('employment_type'):
            fit += 0.20
            reasons.append('Employment type match')

        if preferences.get('location', '') and preferences['location'] in (job.location or '').lower():
            fit += 0.10
            reasons.append('Location alignment')

        if (job.company_size or '') == preferences.get('company_size_preference'):
            fit += 0.10
            reasons.append('Company size preference match')

        stipend_min = preferences.get('stipend_min')
        stipend_max = preferences.get('stipend_max')
        if stipend_min is not None and stipend_max is not None:
            if job.stipend_min is not None and job.stipend_max is not None:
                fit += 0.05
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

    top_rows = result_rows[:5]
    top_jobs = []
    for idx, row in enumerate(top_rows, start=1):
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
        'fallback_applied': len(top_jobs) < 5,
        'fallback_reason': 'INSUFFICIENT_HIGH_CONFIDENCE_MATCHES' if len(top_jobs) < 5 else '',
    }
