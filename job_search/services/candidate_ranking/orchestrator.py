from __future__ import annotations

import os
from time import perf_counter

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from job_search.models import (
    AgentTraceEvent,
    CandidateRankingResult,
    CandidateRankingRun,
    JobCandidate,
    RecruiterJobPreference,
)
from job_search.services.candidate_ranking.agents.openai_adapter import OpenAIJsonAdapter
from job_search.services.candidate_ranking.agents.stages import (
    candidate_normalizer_agent,
    coding_profile_signal_agent,
    college_tier_classifier_agent,
    experience_extraction_agent,
    fit_scoring_agent,
    hard_filter_agent,
    ranker_agent,
)
from job_search.services.candidate_ranking.protocols import A2AEnvelope

STAGE_MAX_RETRIES = int(os.getenv('CANDIDATE_AI_STAGE_RETRIES', '2'))
STAGE_MAX_ATTEMPTS = STAGE_MAX_RETRIES + 1

STAGE_REQUIRED_KEYS = {
    'A': {'normalized_candidate'},
    'B': {'college_tier', 'confidence', 'evidence', 'cache_hit'},
    'C': {'years_of_experience', 'experience_band', 'confidence', 'evidence'},
    'D': {'extracted_platform_signals', 'criteria_comparisons'},
    'E': {'passes_hard_filter', 'rejected_reasons'},
    'F': {'sub_scores', 'final_score', 'summary'},
}


def _chunked(items, size):
    for i in range(0, len(items), size):
        yield i // size + 1, items[i : i + size]


def _persist_trace(run, candidate, envelope: A2AEnvelope):
    AgentTraceEvent.objects.create(
        run=run,
        candidate=candidate,
        agent_name=envelope.agent_name,
        stage=envelope.stage,
        request_payload=envelope.request_payload,
        response_payload=envelope.response_payload,
        status=envelope.status,
        error_code=envelope.error_code,
        error_message=envelope.error_message,
        latency_ms=envelope.latency_ms,
        token_usage=envelope.token_usage,
        model_name=envelope.model_name,
    )


def _stage_fallback(stage, candidate=None):
    if stage == 'A':
        return {
            'normalized_candidate': {
                'name': getattr(candidate, 'name', '') or '',
                'email': getattr(candidate, 'email', '') or '',
                'education_text': '',
                'experience_text': '',
                'projects_text': '',
                'skills_text': '',
                'raw_sections': {},
            }
        }
    if stage == 'B':
        return {
            'college_tier': 'UNKNOWN',
            'confidence': 0.0,
            'evidence': ['stage_fallback'],
            'cache_hit': False,
        }
    if stage == 'C':
        return {
            'years_of_experience': 0.0,
            'experience_band': '0 years',
            'confidence': 0.0,
            'evidence': ['stage_fallback'],
        }
    if stage == 'D':
        return {
            'extracted_platform_signals': [],
            'criteria_comparisons': [],
        }
    if stage == 'E':
        return {
            'passes_hard_filter': False,
            'rejected_reasons': ['hard_filter_fallback'],
        }
    if stage == 'F':
        return {
            'sub_scores': {
                'education_fit': 0,
                'experience_fit': 0,
                'coding_fit': 0,
                'jd_relevance': 0,
            },
            'final_score': 0,
            'summary': 'fit_scoring_fallback',
        }
    return {}


def _validate_stage_output(stage, output):
    if not isinstance(output, dict):
        return False, 'Output must be an object.'
    required = STAGE_REQUIRED_KEYS.get(stage, set())
    missing = [key for key in required if key not in output]
    if missing:
        return False, f'Missing keys: {missing}'
    return True, ''


def _execute_stage_with_retry(run, batch_id, candidate, stage, agent_name, request_payload, fn):
    for attempt in range(1, STAGE_MAX_ATTEMPTS + 1):
        envelope = A2AEnvelope(
            run_id=str(run.id),
            batch_id=str(batch_id),
            candidate_id=candidate.id if candidate else None,
            agent_name=agent_name,
            stage=stage,
            request_payload=request_payload,
        )
        try:
            output = fn()
            is_valid, validation_error = _validate_stage_output(stage, output)
            if not is_valid:
                raise ValueError(f'Invalid stage output schema: {validation_error}')

            envelope.complete(
                {
                    **output,
                    'attempt': attempt,
                    'max_attempts': STAGE_MAX_ATTEMPTS,
                    'fallback_applied': False,
                }
            )
            _persist_trace(run, candidate, envelope)
            return output, True, attempt, False
        except Exception as exc:
            envelope.fail('AGENT_STAGE_ERROR', str(exc))
            envelope.response_payload = {
                'attempt': attempt,
                'max_attempts': STAGE_MAX_ATTEMPTS,
                'fallback_applied': False,
            }
            _persist_trace(run, candidate, envelope)

    fallback_output = _stage_fallback(stage, candidate)
    fallback_envelope = A2AEnvelope(
        run_id=str(run.id),
        batch_id=str(batch_id),
        candidate_id=candidate.id if candidate else None,
        agent_name=agent_name,
        stage=stage,
        request_payload=request_payload,
    )
    fallback_envelope.complete(
        {
            **fallback_output,
            'attempt': STAGE_MAX_ATTEMPTS,
            'max_attempts': STAGE_MAX_ATTEMPTS,
            'fallback_applied': True,
        }
    )
    fallback_envelope.status = 'SKIPPED'
    fallback_envelope.error_code = 'STAGE_FALLBACK_APPLIED'
    fallback_envelope.error_message = f'All {STAGE_MAX_ATTEMPTS} attempts failed.'
    _persist_trace(run, candidate, fallback_envelope)
    return fallback_output, False, STAGE_MAX_ATTEMPTS, True


def run_candidate_ranking_for_run(run: CandidateRankingRun):
    if run.status in (CandidateRankingRun.STATUS_COMPLETED, CandidateRankingRun.STATUS_FAILED):
        return run

    pref = RecruiterJobPreference.objects.filter(job=run.job).first()
    if not pref:
        run.status = CandidateRankingRun.STATUS_FAILED
        run.error_code = 'MISSING_PREFERENCE'
        run.error_message = 'Recruiter preference not found for the job.'
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'error_code', 'error_message', 'completed_at', 'updated_at'])
        return run

    run.status = CandidateRankingRun.STATUS_RUNNING
    run.started_at = timezone.now()
    run.model_name = getattr(settings, 'OPENAI_MODEL', 'gpt-4.1')
    run.save(update_fields=['status', 'started_at', 'model_name', 'updated_at'])

    started = perf_counter()
    candidates = list(JobCandidate.objects.filter(job=run.job).order_by('created_at', 'id'))
    run.total_candidates = len(candidates)
    run.save(update_fields=['total_candidates', 'updated_at'])

    adapter = OpenAIJsonAdapter()
    scored_rows = []
    processed = 0
    stage_metrics = {
        'candidate_normalizer_ms': 0,
        'college_tier_ms': 0,
        'experience_ms': 0,
        'coding_signal_ms': 0,
        'hard_filter_ms': 0,
        'fit_scoring_ms': 0,
        'retry_counts': {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'F': 0},
        'fallback_counts': {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'F': 0, 'G': 0},
        'total_retries_used': 0,
    }

    for batch_id, batch in _chunked(candidates, run.batch_size):
        for candidate in batch:
            t0 = perf_counter()
            normalized_out, ok_norm, attempts_a, fb_a = _execute_stage_with_retry(
                run,
                batch_id,
                candidate,
                stage='A',
                agent_name='CandidateNormalizerAgent',
                request_payload={'candidate_id': candidate.id},
                fn=lambda: candidate_normalizer_agent(candidate),
            )
            stage_metrics['retry_counts']['A'] += max(0, attempts_a - 1)
            stage_metrics['total_retries_used'] += max(0, attempts_a - 1)
            stage_metrics['fallback_counts']['A'] += 1 if fb_a else 0
            stage_metrics['candidate_normalizer_ms'] += int((perf_counter() - t0) * 1000)

            normalized = normalized_out.get('normalized_candidate') if ok_norm else {}

            t1 = perf_counter()
            college_out, _, attempts_b, fb_b = _execute_stage_with_retry(
                run,
                batch_id,
                candidate,
                stage='B',
                agent_name='CollegeTierClassifierAgent',
                request_payload={'education_text': normalized.get('education_text', '')},
                fn=lambda: college_tier_classifier_agent(normalized, adapter, run.model_name),
            )
            stage_metrics['retry_counts']['B'] += max(0, attempts_b - 1)
            stage_metrics['total_retries_used'] += max(0, attempts_b - 1)
            stage_metrics['fallback_counts']['B'] += 1 if fb_b else 0
            stage_metrics['college_tier_ms'] += int((perf_counter() - t1) * 1000)

            t2 = perf_counter()
            exp_out, _, attempts_c, fb_c = _execute_stage_with_retry(
                run,
                batch_id,
                candidate,
                stage='C',
                agent_name='ExperienceExtractionAgent',
                request_payload={'experience_text': normalized.get('experience_text', '')},
                fn=lambda: experience_extraction_agent(normalized),
            )
            stage_metrics['retry_counts']['C'] += max(0, attempts_c - 1)
            stage_metrics['total_retries_used'] += max(0, attempts_c - 1)
            stage_metrics['fallback_counts']['C'] += 1 if fb_c else 0
            stage_metrics['experience_ms'] += int((perf_counter() - t2) * 1000)

            t3 = perf_counter()
            coding_out, _, attempts_d, fb_d = _execute_stage_with_retry(
                run,
                batch_id,
                candidate,
                stage='D',
                agent_name='CodingProfileSignalAgent',
                request_payload={'criteria': pref.coding_platform_criteria},
                fn=lambda: coding_profile_signal_agent(normalized, pref),
            )
            stage_metrics['retry_counts']['D'] += max(0, attempts_d - 1)
            stage_metrics['total_retries_used'] += max(0, attempts_d - 1)
            stage_metrics['fallback_counts']['D'] += 1 if fb_d else 0
            stage_metrics['coding_signal_ms'] += int((perf_counter() - t3) * 1000)

            t4 = perf_counter()
            hard_out, _, attempts_e, fb_e = _execute_stage_with_retry(
                run,
                batch_id,
                candidate,
                stage='E',
                agent_name='HardFilterAgent',
                request_payload={'college_tiers': pref.college_tiers},
                fn=lambda: hard_filter_agent(pref, college_out, exp_out, coding_out),
            )
            stage_metrics['retry_counts']['E'] += max(0, attempts_e - 1)
            stage_metrics['total_retries_used'] += max(0, attempts_e - 1)
            stage_metrics['fallback_counts']['E'] += 1 if fb_e else 0
            stage_metrics['hard_filter_ms'] += int((perf_counter() - t4) * 1000)

            t5 = perf_counter()
            fit_out, _, attempts_f, fb_f = _execute_stage_with_retry(
                run,
                batch_id,
                candidate,
                stage='F',
                agent_name='FitScoringAgent',
                request_payload={'job_description': run.job.job_description or ''},
                fn=lambda: fit_scoring_agent(normalized, hard_out, college_out, exp_out, coding_out, pref),
            )
            stage_metrics['retry_counts']['F'] += max(0, attempts_f - 1)
            stage_metrics['total_retries_used'] += max(0, attempts_f - 1)
            stage_metrics['fallback_counts']['F'] += 1 if fb_f else 0
            stage_metrics['fit_scoring_ms'] += int((perf_counter() - t5) * 1000)

            scored_rows.append(
                {
                    'candidate': candidate,
                    'passes_hard_filter': bool(hard_out.get('passes_hard_filter')),
                    'filter_reasons': hard_out.get('rejected_reasons') or [],
                    'final_score': float(fit_out.get('final_score', 0) or 0),
                    'sub_scores': fit_out.get('sub_scores') or {},
                    'summary': fit_out.get('summary') or '',
                }
            )

            processed += 1
            run.processed_candidates = processed
            run.save(update_fields=['processed_candidates', 'updated_at'])

    t6 = perf_counter()
    try:
        ranked = ranker_agent(scored_rows, pref.number_of_openings)
    except Exception:
        stage_metrics['fallback_counts']['G'] += 1
        ranked = sorted(
            scored_rows,
            key=lambda row: (row['candidate'].created_at, row['candidate'].id),
        )
        for index, row in enumerate(ranked, start=1):
            row['rank'] = index
            row['is_shortlisted'] = index <= pref.number_of_openings
    ranker_ms = int((perf_counter() - t6) * 1000)

    with transaction.atomic():
        CandidateRankingResult.objects.filter(run=run).delete()
        for row in ranked:
            CandidateRankingResult.objects.create(
                run=run,
                candidate=row['candidate'],
                rank=row['rank'],
                is_shortlisted=row['is_shortlisted'],
                passes_hard_filter=row['passes_hard_filter'],
                final_score=row['final_score'],
                sub_scores=row['sub_scores'],
                filter_reasons=row['filter_reasons'],
                summary=row['summary'],
            )

    run.shortlisted_count = sum(1 for r in ranked if r.get('is_shortlisted'))
    run.timing_metrics = {
        **stage_metrics,
        'ranker_ms': ranker_ms,
        'total_ms': int((perf_counter() - started) * 1000),
    }
    run.status = CandidateRankingRun.STATUS_COMPLETED
    run.completed_at = timezone.now()
    run.save(
        update_fields=[
            'shortlisted_count',
            'timing_metrics',
            'status',
            'completed_at',
            'updated_at',
        ]
    )
    return run
