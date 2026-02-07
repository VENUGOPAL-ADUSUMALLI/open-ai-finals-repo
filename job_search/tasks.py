from celery import shared_task

from job_search.models import MatchingRun
from job_search.services.matching_orchestrator import run_matching_for_run


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 2}, soft_time_limit=120)
def run_matching_pipeline(self, run_id):
    matching_run = MatchingRun.objects.filter(id=run_id).first()
    if not matching_run:
        return {'status': 'MISSING'}

    if matching_run.status in (MatchingRun.STATUS_COMPLETED, MatchingRun.STATUS_FAILED):
        return {'status': matching_run.status}

    try:
        run_matching_for_run(matching_run)
        return {'status': MatchingRun.STATUS_COMPLETED}
    except Exception as exc:
        matching_run.status = MatchingRun.STATUS_FAILED
        matching_run.error_code = 'AGENT_PIPELINE_ERROR'
        matching_run.error_message = str(exc)
        matching_run.save(update_fields=['status', 'error_code', 'error_message', 'updated_at'])
        raise
