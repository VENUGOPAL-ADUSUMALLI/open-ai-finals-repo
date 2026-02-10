from celery import shared_task
from django.utils import timezone

from job_search.models import Job, JobAlert, JobPreference, MatchingRun
from job_search.services.filtering import filter_jobs
from job_search.services.matching_orchestrator import run_matching_for_run
from job_search.services.preferences import normalize_preferences

ALERT_SCORE_THRESHOLD = 0.5


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


@shared_task(bind=True, soft_time_limit=300)
def check_new_job_alerts(self, lookback_hours=24):
    """Check recently added jobs against all active preferences and create alerts."""
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(hours=lookback_hours)
    recent_jobs = Job.objects.filter(created_at__gte=cutoff)

    if not recent_jobs.exists():
        return {'alerts_created': 0, 'preferences_checked': 0}

    active_preferences = JobPreference.objects.filter(is_active=True).select_related('user')
    alerts_created = 0
    preferences_checked = 0

    for preference in active_preferences:
        preferences_checked += 1
        pref_data = {
            'work_mode': preference.work_mode,
            'employment_type': preference.employment_type,
            'internship_duration_weeks': preference.internship_duration_weeks,
            'location': preference.location,
            'company_size_preference': preference.company_size_preference,
            'experience_level': preference.experience_level,
            'stipend_min': preference.stipend_min,
            'stipend_max': preference.stipend_max,
            'stipend_currency': preference.stipend_currency,
            'preferred_sectors': preference.preferred_sectors,
            'excluded_sectors': preference.excluded_sectors,
            'preferred_roles': preference.preferred_roles,
            'excluded_keywords': preference.excluded_keywords,
            'excluded_companies': preference.excluded_companies,
            'preferred_companies': preference.preferred_companies,
        }
        normalized = normalize_preferences(pref_data)
        try:
            result = filter_jobs(normalized)
        except Exception:
            continue

        matched_jobs = result['jobs']
        recent_ids = set(recent_jobs.values_list('id', flat=True))
        for job in matched_jobs:
            if job.id not in recent_ids:
                continue

            score = 0.5
            reasons = ['Passed all preference filters']

            if preference.preferred_roles:
                title_lower = (job.title or '').lower()
                for role in preference.preferred_roles:
                    if role.lower() in title_lower:
                        score += 0.1
                        reasons.append(f'Role match: {role}')
                        break

            if preference.preferred_companies:
                company_lower = (job.company_name or '').lower()
                for company in preference.preferred_companies:
                    if company.lower() in company_lower:
                        score += 0.1
                        reasons.append(f'Preferred company: {company}')
                        break

            score = min(score, 1.0)

            if score >= ALERT_SCORE_THRESHOLD:
                _, created = JobAlert.objects.get_or_create(
                    user=preference.user,
                    preference=preference,
                    job=job,
                    defaults={
                        'preference_name': preference.name,
                        'match_score': score,
                        'match_reasons': reasons,
                    },
                )
                if created:
                    alerts_created += 1

    return {
        'alerts_created': alerts_created,
        'preferences_checked': preferences_checked,
    }
