from time import perf_counter

from django.db import transaction
from django.utils import timezone

from job_search.models import MatchingResult, MatchingRun
from job_search.services.agents.orchestrator import run_agent_pipeline
from job_search.services.filtering import filter_jobs
from job_search.services.preferences import normalize_preferences


def run_matching_for_run(matching_run):
    if matching_run.status in (MatchingRun.STATUS_COMPLETED, MatchingRun.STATUS_FAILED):
        return matching_run

    started = perf_counter()
    matching_run.status = MatchingRun.STATUS_FILTERING
    matching_run.started_at = timezone.now()
    matching_run.save(update_fields=['status', 'started_at', 'updated_at'])

    normalized_preferences = normalize_preferences(matching_run.preferences_snapshot)
    filtering_start = perf_counter()
    filtering_result = filter_jobs(normalized_preferences)
    filtering_ms = int((perf_counter() - filtering_start) * 1000)

    matching_run.filtered_jobs_count = filtering_result['total_considered']
    timing_metrics = dict(matching_run.timing_metrics or {})
    timing_metrics['filtering_ms'] = filtering_ms
    timing_metrics['deterministic_metrics'] = filtering_result['deterministic_metrics']

    if filtering_result['total_considered'] == 0:
        matching_run.status = MatchingRun.STATUS_COMPLETED
        matching_run.completed_at = timezone.now()
        timing_metrics['agent_ms_total'] = 0
        timing_metrics['total_ms'] = int((perf_counter() - started) * 1000)
        matching_run.timing_metrics = timing_metrics
        matching_run.save(
            update_fields=[
                'status',
                'completed_at',
                'filtered_jobs_count',
                'timing_metrics',
                'updated_at',
            ]
        )
        return matching_run

    matching_run.status = MatchingRun.STATUS_AGENT_RUNNING
    matching_run.timing_metrics = timing_metrics
    matching_run.save(update_fields=['status', 'filtered_jobs_count', 'timing_metrics', 'updated_at'])

    agent_start = perf_counter()
    pipeline_result = run_agent_pipeline(
        jobs=filtering_result['jobs'],
        preferences=normalized_preferences,
        candidate_profile=matching_run.candidate_profile_snapshot or {},
    )
    agent_ms = int((perf_counter() - agent_start) * 1000)

    with transaction.atomic():
        MatchingResult.objects.filter(run=matching_run).delete()
        for top_job in pipeline_result['top_jobs']:
            MatchingResult.objects.create(
                run=matching_run,
                job_id=top_job['job_id'],
                rank=top_job['rank'],
                selection_probability=top_job['selection_probability'],
                fit_score=top_job['fit_score'],
                job_quality_score=top_job['job_quality_score'],
                why=top_job['why'],
                agent_trace=top_job['agent_trace'],
            )

    timing_metrics['agent_ms_total'] = agent_ms
    gpt_metrics = pipeline_result.get('gpt_metrics', {})
    if gpt_metrics:
        timing_metrics['gpt_scoring'] = gpt_metrics
    timing_metrics['total_ms'] = int((perf_counter() - started) * 1000)

    matching_run.status = MatchingRun.STATUS_COMPLETED
    matching_run.completed_at = timezone.now()
    matching_run.timing_metrics = timing_metrics
    matching_run.save(update_fields=['status', 'completed_at', 'timing_metrics', 'updated_at'])
    return matching_run
