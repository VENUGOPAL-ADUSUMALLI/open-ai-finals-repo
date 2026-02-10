import json
import re
from decimal import Decimal
from typing import Any

from job_search.models import CollegeTierLookupCache, RecruiterJobPreference
from job_search.services.candidate_ranking.agents.openai_adapter import OpenAIJsonAdapter


def _safe_json_loads(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or '{}')
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _normalize_resume(candidate):
    resume = _safe_json_loads(candidate.resume_data)
    sections = resume.get('sections') or {}
    education_lines = sections.get('Education') or []
    experience_lines = sections.get('Experience') or []
    projects_lines = sections.get('Projects') or []
    skills_lines = sections.get('Technical Skills') or []

    return {
        'name': candidate.name,
        'email': candidate.email,
        'education_text': '\n'.join(education_lines),
        'experience_text': '\n'.join(experience_lines),
        'projects_text': '\n'.join(projects_lines),
        'skills_text': '\n'.join(skills_lines),
        'raw_sections': sections,
    }


def candidate_normalizer_agent(candidate):
    normalized = _normalize_resume(candidate)
    return {
        'normalized_candidate': normalized,
    }


def college_tier_classifier_agent(normalized_candidate, adapter: OpenAIJsonAdapter, model_name: str):
    education_text = normalized_candidate.get('education_text', '')
    institution_key = re.sub(r'\s+', ' ', education_text.strip().lower())[:255]

    if institution_key:
        cached = CollegeTierLookupCache.objects.filter(institution_normalized=institution_key).first()
        if cached:
            return {
                'college_tier': cached.tier,
                'confidence': float(cached.confidence),
                'evidence': cached.evidence or [],
                'cache_hit': True,
            }

    if not education_text:
        return {
            'college_tier': 'UNKNOWN',
            'confidence': 0.0,
            'evidence': ['No education data'],
            'cache_hit': False,
        }

    try:
        payload, _, used_model = adapter.run_json(
            system_prompt=(
                'Classify candidate college tier into TIER_1, TIER_2, TIER_3 or UNKNOWN. '
                'Return valid JSON with keys: college_tier, confidence, evidence.'
            ),
            user_prompt=f'Education details:\n{education_text}',
        )
        tier = str(payload.get('college_tier', 'UNKNOWN')).strip().upper()
        if tier not in {'TIER_1', 'TIER_2', 'TIER_3', 'UNKNOWN'}:
            tier = 'UNKNOWN'
        confidence = float(payload.get('confidence', 0) or 0)
        evidence = payload.get('evidence') if isinstance(payload.get('evidence'), list) else []
    except Exception:
        tier = 'UNKNOWN'
        confidence = 0.0
        evidence = ['fallback_used']
        used_model = model_name

    if institution_key and tier != 'UNKNOWN':
        CollegeTierLookupCache.objects.update_or_create(
            institution_normalized=institution_key,
            defaults={
                'tier': tier,
                'confidence': Decimal(str(max(0.0, min(1.0, confidence)))),
                'evidence': evidence,
                'source_model': used_model,
            },
        )

    return {
        'college_tier': tier,
        'confidence': confidence,
        'evidence': evidence,
        'cache_hit': False,
    }


def experience_extraction_agent(normalized_candidate):
    text = normalized_candidate.get('experience_text', '')
    years = 0.0
    ranges = re.findall(r'(\d+)\s*\+?\s*(?:years|yrs|year|yr)', text.lower())
    if ranges:
        years = float(max(int(num) for num in ranges))
    return {
        'years_of_experience': years,
        'experience_band': f'{int(years)}+ years' if years > 0 else '0 years',
        'confidence': 0.5 if years > 0 else 0.2,
        'evidence': ['regex_extraction'],
    }


def coding_profile_signal_agent(normalized_candidate, recruiter_preference: RecruiterJobPreference):
    text = ' '.join([
        normalized_candidate.get('skills_text', ''),
        normalized_candidate.get('projects_text', ''),
        normalized_candidate.get('experience_text', ''),
    ]).lower()

    extracted = []
    cf_rating_match = re.search(r'codeforces[^\d]*(\d{3,5})', text)
    if cf_rating_match:
        extracted.append({'platform': 'codeforces', 'metric': 'rating', 'value': int(cf_rating_match.group(1))})

    lc_rank_match = re.search(r'leetcode[^\d]*(\d{1,7})', text)
    if lc_rank_match:
        extracted.append({'platform': 'leetcode', 'metric': 'contest_rank', 'value': int(lc_rank_match.group(1))})

    comparisons = []
    for rule in recruiter_preference.coding_platform_criteria or []:
        platform = str(rule.get('platform', '')).strip().lower()
        metric = str(rule.get('metric', '')).strip().lower()
        operator = str(rule.get('operator', '')).strip().lower()
        try:
            target_value = float(rule.get('value'))
        except Exception:
            comparisons.append({'rule': rule, 'matched': False, 'reason': 'invalid_rule'})
            continue

        matched_signal = next(
            (
                signal for signal in extracted
                if signal['platform'].lower() == platform and signal['metric'].lower() == metric
            ),
            None,
        )
        if not matched_signal:
            comparisons.append({'rule': rule, 'matched': False, 'reason': 'signal_not_found'})
            continue

        value = float(matched_signal['value'])
        if operator == 'gte':
            matched = value >= target_value
        elif operator == 'lte':
            matched = value <= target_value
        elif operator == 'eq':
            matched = value == target_value
        else:
            matched = False

        comparisons.append(
            {
                'rule': rule,
                'matched': matched,
                'found_value': value,
            }
        )

    return {
        'extracted_platform_signals': extracted,
        'criteria_comparisons': comparisons,
    }


def hard_filter_agent(recruiter_preference: RecruiterJobPreference, college_tier_output, experience_output, coding_output):
    reasons = []
    passes = True

    tier = college_tier_output.get('college_tier', 'UNKNOWN')
    if tier not in recruiter_preference.college_tiers:
        passes = False
        reasons.append(f'College tier mismatch: {tier}')

    years = float(experience_output.get('years_of_experience', 0) or 0)
    if years < float(recruiter_preference.min_experience_years) or years > float(recruiter_preference.max_experience_years):
        passes = False
        reasons.append('Experience outside preferred range')

    comparisons = coding_output.get('criteria_comparisons') or []
    if comparisons:
        failed_rules = [item for item in comparisons if not item.get('matched')]
        if failed_rules:
            passes = False
            reasons.append('Coding criteria mismatch')

    return {
        'passes_hard_filter': passes,
        'rejected_reasons': reasons,
    }


def fit_scoring_agent(normalized_candidate, hard_filter_output, college_tier_output, experience_output, coding_output, recruiter_preference):
    if not hard_filter_output.get('passes_hard_filter'):
        return {
            'sub_scores': {
                'education_fit': 0,
                'experience_fit': 0,
                'coding_fit': 0,
                'jd_relevance': 0,
            },
            'final_score': 0,
            'summary': 'Rejected by hard filters',
        }

    education_fit = 100 if college_tier_output.get('college_tier') in recruiter_preference.college_tiers else 0
    years = float(experience_output.get('years_of_experience', 0) or 0)
    exp_min = float(recruiter_preference.min_experience_years)
    exp_max = float(recruiter_preference.max_experience_years)
    experience_fit = 100 if exp_min <= years <= exp_max else 0

    comparisons = coding_output.get('criteria_comparisons') or []
    if comparisons:
        coding_fit = int(100 * (sum(1 for x in comparisons if x.get('matched')) / len(comparisons)))
    else:
        coding_fit = 70

    jd_text = (recruiter_preference.job.job_description or '').lower()
    profile_text = ' '.join([
        normalized_candidate.get('skills_text', '').lower(),
        normalized_candidate.get('projects_text', '').lower(),
    ])
    jd_hits = 0
    for token in set(jd_text.split()[:40]):
        if len(token) > 3 and token in profile_text:
            jd_hits += 1
    jd_relevance = min(100, jd_hits * 5)

    final_score = round(0.25 * education_fit + 0.25 * experience_fit + 0.30 * coding_fit + 0.20 * jd_relevance, 2)
    return {
        'sub_scores': {
            'education_fit': education_fit,
            'experience_fit': experience_fit,
            'coding_fit': coding_fit,
            'jd_relevance': jd_relevance,
        },
        'final_score': final_score,
        'summary': 'Composite candidate fit score',
    }


def ranker_agent(scored_rows, openings):
    ranked = sorted(
        scored_rows,
        key=lambda row: (
            -row['final_score'],
            -(row['sub_scores'].get('coding_fit', 0)),
            -(row['sub_scores'].get('experience_fit', 0)),
            row['candidate'].created_at,
        ),
    )

    for idx, row in enumerate(ranked, start=1):
        row['rank'] = idx
        row['is_shortlisted'] = idx <= openings
    return ranked
