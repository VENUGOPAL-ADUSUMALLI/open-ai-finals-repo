from django.db.models import Q

from job_search.models import Job

MAX_AGENT_JOBS = 300


def filter_jobs(preferences):
    """Apply deterministic filters and return top jobs plus metrics."""
    jobs = Job.objects.all()
    metrics = {
        'initial_count': jobs.count(),
    }

    jobs = jobs.filter(
        work_mode=preferences['work_mode'],
        employment_type=preferences['employment_type'],
        location__icontains=preferences['location'],
        company_size=preferences['company_size_preference'],
    )
    metrics['after_primary_filters'] = jobs.count()

    if preferences['employment_type'] == 'INTERNSHIP':
        jobs = jobs.filter(internship_duration_weeks=preferences['internship_duration_weeks'])
        metrics['after_internship_duration'] = jobs.count()

    stipend_min = preferences.get('stipend_min')
    stipend_max = preferences.get('stipend_max')
    stipend_currency = preferences.get('stipend_currency', 'INR')

    if stipend_min is not None and stipend_max is not None:
        jobs = jobs.filter(
            stipend_min__isnull=False,
            stipend_max__isnull=False,
            stipend_currency=stipend_currency,
        ).filter(
            Q(stipend_max__gte=stipend_min) & Q(stipend_min__lte=stipend_max)
        )
        metrics['after_stipend_overlap'] = jobs.count()

    # Feature 1: Experience level filter
    experience_level = preferences.get('experience_level')
    if experience_level:
        jobs = jobs.filter(experience_level=experience_level)
        metrics['after_experience_level'] = jobs.count()

    # Feature 2: Sector preference filters
    preferred_sectors = preferences.get('preferred_sectors', [])
    excluded_sectors = preferences.get('excluded_sectors', [])

    if excluded_sectors:
        for sector in excluded_sectors:
            jobs = jobs.exclude(sector__icontains=sector)
        metrics['after_excluded_sectors'] = jobs.count()

    if preferred_sectors:
        sector_q = Q()
        for sector in preferred_sectors:
            sector_q |= Q(sector__icontains=sector)
        jobs = jobs.filter(sector_q)
        metrics['after_preferred_sectors'] = jobs.count()

    # Feature 3: Excluded keywords (hard filter on title)
    excluded_keywords = preferences.get('excluded_keywords', [])
    if excluded_keywords:
        for keyword in excluded_keywords:
            jobs = jobs.exclude(title__icontains=keyword)
        metrics['after_excluded_keywords'] = jobs.count()

    # Feature 4: Excluded companies (hard filter)
    excluded_companies = preferences.get('excluded_companies', [])
    if excluded_companies:
        for company in excluded_companies:
            jobs = jobs.exclude(company_name__icontains=company)
        metrics['after_excluded_companies'] = jobs.count()

    ordered_jobs = jobs.order_by('-published_at', '-created_at')
    full_count = ordered_jobs.count()
    metrics['ordered_count'] = full_count

    selected_job_ids = list(ordered_jobs.values_list('id', flat=True)[:MAX_AGENT_JOBS])
    metrics['capped_count'] = len(selected_job_ids)

    capped_jobs = Job.objects.filter(id__in=selected_job_ids).order_by('-published_at', '-created_at')
    return {
        'jobs': capped_jobs,
        'job_ids': selected_job_ids,
        'total_considered': full_count,
        'deterministic_metrics': metrics,
    }
