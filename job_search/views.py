from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db.models import Q
from rest_framework import status
from rest_framework.authentication import BasicAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Job, JobPreference, MatchingRun, WORK_MODE_CHOICES, EMPLOYMENT_TYPE_CHOICES, COMPANY_SIZE_CHOICES
from .services.filtering import filter_jobs
from .services.preferences import normalize_preferences, to_json_safe
from .services.skill_matching import extract_skills_from_resume, score_and_rank_jobs
from .tasks import run_matching_pipeline


def _coerce_bool(value, field, errors, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ('true', '1', 'yes', 'y'):
            return True
        if normalized in ('false', '0', 'no', 'n'):
            return False
    errors[field] = 'Must be a boolean.'
    return default


def _coerce_int(value, field, errors, min_value=None):
    if value is None or value == '':
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        errors[field] = 'Must be an integer.'
        return None
    if min_value is not None and parsed < min_value:
        errors[field] = f'Must be at least {min_value}.'
        return None
    return parsed


def _coerce_decimal(value, field, errors):
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors[field] = 'Must be a number.'
        return None


def _coerce_str(value, field, errors, max_length=None, required=False):
    if value is None or value == '':
        if required:
            errors[field] = 'This field is required.'
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if required and not value:
        errors[field] = 'This field is required.'
        return None
    if max_length is not None and len(value) > max_length:
        errors[field] = f'Max length is {max_length}.'
        return None
    return value


def _validate_preference_payload(data):
    errors = {}
    valid_work_modes = [c[0] for c in WORK_MODE_CHOICES]
    valid_employment_types = [c[0] for c in EMPLOYMENT_TYPE_CHOICES]
    valid_company_sizes = [c[0] for c in COMPANY_SIZE_CHOICES]

    work_mode = data.get('work_mode')
    if work_mode is None or work_mode == '':
        errors['work_mode'] = 'This field is required.'
    elif work_mode not in valid_work_modes:
        errors['work_mode'] = f'Must be one of: {", ".join(valid_work_modes)}'

    employment_type = data.get('employment_type')
    if employment_type is None or employment_type == '':
        errors['employment_type'] = 'This field is required.'
    elif employment_type not in valid_employment_types:
        errors['employment_type'] = f'Must be one of: {", ".join(valid_employment_types)}'

    location = _coerce_str(data.get('location'), 'location', errors, max_length=200, required=True)

    company_size_preference = data.get('company_size_preference')
    if company_size_preference is None or company_size_preference == '':
        errors['company_size_preference'] = 'This field is required.'
    elif company_size_preference not in valid_company_sizes:
        errors['company_size_preference'] = f'Must be one of: {", ".join(valid_company_sizes)}'

    internship_duration_weeks = _coerce_int(
        data.get('internship_duration_weeks'),
        'internship_duration_weeks',
        errors,
        min_value=1,
    )

    stipend_min = _coerce_decimal(data.get('stipend_min'), 'stipend_min', errors)
    stipend_max = _coerce_decimal(data.get('stipend_max'), 'stipend_max', errors)

    stipend_currency = _coerce_str(
        data.get('stipend_currency'),
        'stipend_currency',
        errors,
        max_length=3,
        required=False,
    ) or 'INR'

    save_preference = _coerce_bool(data.get('save_preference'), 'save_preference', errors, default=True)

    if employment_type == 'INTERNSHIP' and not internship_duration_weeks:
        errors['internship_duration_weeks'] = 'Required for internship employment type.'
    if employment_type == 'FULL_TIME' and internship_duration_weeks is not None:
        errors['internship_duration_weeks'] = 'Must be empty for full-time employment type.'

    if (stipend_min is not None) != (stipend_max is not None):
        errors['stipend'] = 'Both stipend_min and stipend_max are required when stipend is provided.'
    if stipend_min is not None and stipend_max is not None and stipend_min > stipend_max:
        errors['stipend_min'] = 'stipend_min must be less than or equal to stipend_max.'

    if errors:
        return None, errors

    validated = {
        'work_mode': work_mode,
        'employment_type': employment_type,
        'internship_duration_weeks': internship_duration_weeks,
        'location': location,
        'company_size_preference': company_size_preference,
        'stipend_min': stipend_min,
        'stipend_max': stipend_max,
        'stipend_currency': stipend_currency,
        'save_preference': save_preference,
    }
    return validated, None


def _preference_defaults(validated):
    defaults = validated.copy()
    defaults.pop('save_preference', None)
    return defaults


def _serialize_job(job):
    return to_json_safe(
        {
            'id': job.id,
            'job_id': job.job_id,
            'title': job.title,
            'company_name': job.company_name,
            'location': job.location,
            'work_mode': job.work_mode,
            'employment_type': job.employment_type,
            'internship_duration_weeks': job.internship_duration_weeks,
            'company_size': job.company_size,
            'stipend_min': job.stipend_min,
            'stipend_max': job.stipend_max,
            'stipend_currency': job.stipend_currency,
            'job_url': job.job_url,
            'apply_url': job.apply_url,
            'apply_type': job.apply_type,
            'published_at': job.published_at.isoformat() if job.published_at else None,
        }
    )


def _serialize_matching_result(result):
    return to_json_safe(
        {
            'rank': result.rank,
            'job_id': result.job.job_id,
            'selection_probability': result.selection_probability,
            'fit_score': result.fit_score,
            'job_quality_score': result.job_quality_score,
            'why': result.why,
        }
    )


def _serialize_matching_run_list(run):
    return {
        'run_id': str(run.id),
        'status': run.status,
        'filtered_jobs_count': run.filtered_jobs_count,
        'created_at': run.created_at.isoformat() if run.created_at else None,
        'completed_at': run.completed_at.isoformat() if run.completed_at else None,
    }


def _serialize_matching_run_detail(run):
    return {
        'run_id': str(run.id),
        'status': run.status,
        'preferences_snapshot': to_json_safe(run.preferences_snapshot),
        'filtered_jobs_count': run.filtered_jobs_count,
        'timing_metrics': to_json_safe(run.timing_metrics),
        'top_5_jobs': [_serialize_matching_result(result) for result in run.results.all()],
        'error_code': run.error_code,
        'error_message': run.error_message,
        'started_at': run.started_at.isoformat() if run.started_at else None,
        'completed_at': run.completed_at.isoformat() if run.completed_at else None,
        'created_at': run.created_at.isoformat() if run.created_at else None,
    }


@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def match_jobs_by_preference_view(request):
    validated, errors = _validate_preference_payload(request.data)
    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    normalized = normalize_preferences(validated)

    if validated.get('save_preference', True):
        defaults = _preference_defaults(validated)
        defaults['location'] = normalized['location']
        JobPreference.objects.update_or_create(
            user=request.user,
            is_active=True,
            defaults=defaults,
        )

    filtering_result = filter_jobs(normalized)
    jobs = filtering_result['jobs']

    paginator = PageNumberPagination()
    paginator.page_size = 10
    paginated_jobs = paginator.paginate_queryset(jobs, request)
    results_queryset = paginated_jobs if paginated_jobs is not None else jobs
    results = [_serialize_job(job) for job in results_queryset]

    preference_echo = _preference_defaults(validated)
    preference_echo['location'] = normalized['location']
    return Response(
        {
            'preference': to_json_safe(preference_echo),
            'count': filtering_result['total_considered'],
            'next': paginator.get_next_link() if paginated_jobs is not None else None,
            'previous': paginator.get_previous_link() if paginated_jobs is not None else None,
            'results': results,
        },
        status=status.HTTP_200_OK,
    )


@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def matching_run_create_view(request):
    if not getattr(settings, 'AGENT_MATCHING_ENABLED', True):
        return Response(
            {'detail': 'Agentic matching is disabled.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    payload = request.data
    preferences_data = payload.get('preferences')
    if not isinstance(preferences_data, dict):
        return Response(
            {'preferences': 'This field is required and must be an object.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    preferences, errors = _validate_preference_payload(preferences_data)
    if errors:
        return Response({'preferences': errors}, status=status.HTTP_400_BAD_REQUEST)
    normalized_preferences = normalize_preferences(preferences)

    save_preference = preferences.get('save_preference', True)
    if save_preference:
        defaults = _preference_defaults(preferences)
        defaults['location'] = normalized_preferences['location']
        JobPreference.objects.update_or_create(
            user=request.user,
            is_active=True,
            defaults=defaults,
        )

    run = MatchingRun.objects.create(
        user=request.user,
        status=MatchingRun.STATUS_PENDING,
        preferences_snapshot=to_json_safe(
            {k: v for k, v in normalized_preferences.items() if k != 'save_preference'}
        ),
        candidate_profile_snapshot=to_json_safe(
            payload.get('candidate_profile') or {}
        ),
    )

    try:
        run_matching_pipeline.delay(str(run.id))
    except Exception:
        # Fallback to local execution when broker is unavailable.
        run_matching_pipeline.run(str(run.id))

    return Response(
        {
            'run_id': str(run.id),
            'status': run.status,
            'submitted_at': run.created_at.isoformat() if run.created_at else None,
        },
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(['GET'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def matching_run_list_view(request):
    queryset = MatchingRun.objects.filter(user=request.user).order_by('-created_at')
    paginator = PageNumberPagination()
    paginator.page_size = 10
    page = paginator.paginate_queryset(queryset, request)
    page_queryset = page if page is not None else queryset
    data = [_serialize_matching_run_list(run) for run in page_queryset]
    return Response(
        {
            'count': queryset.count(),
            'next': paginator.get_next_link() if page is not None else None,
            'previous': paginator.get_previous_link() if page is not None else None,
            'results': data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def matching_run_detail_view(request, run_id):
    run = MatchingRun.objects.filter(id=run_id, user=request.user).first()
    if not run:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    data = _serialize_matching_run_detail(run)
    return Response(
        {
            'run_id': data['run_id'],
            'status': data['status'],
            'filtered_jobs_count': data['filtered_jobs_count'],
            'preference_used': data['preferences_snapshot'],
            'timings': data['timing_metrics'],
            'top_5_jobs': data['top_5_jobs'] if run.status == MatchingRun.STATUS_COMPLETED else [],
            'error': {
                'code': data['error_code'],
                'message': data['error_message'],
            }
            if run.status == MatchingRun.STATUS_FAILED
            else None,
            'started_at': data['started_at'],
            'completed_at': data['completed_at'],
            'created_at': data['created_at'],
        },
        status=status.HTTP_200_OK,
    )


@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def job_recommendation_view(request):
    data = request.data
    errors = {}

    # Validate optional fields
    valid_work_modes = [c[0] for c in WORK_MODE_CHOICES]
    valid_employment_types = [c[0] for c in EMPLOYMENT_TYPE_CHOICES]
    valid_company_sizes = [c[0] for c in COMPANY_SIZE_CHOICES]

    work_mode = data.get('work_mode')
    if work_mode and work_mode not in valid_work_modes:
        errors['work_mode'] = f'Must be one of: {", ".join(valid_work_modes)}'

    employment_type = data.get('employment_type')
    if employment_type and employment_type not in valid_employment_types:
        errors['employment_type'] = f'Must be one of: {", ".join(valid_employment_types)}'

    company_size = data.get('company_size_preference')
    if company_size and company_size not in valid_company_sizes:
        errors['company_size_preference'] = f'Must be one of: {", ".join(valid_company_sizes)}'

    internship_duration = data.get('internship_duration_weeks')
    if employment_type == 'INTERNSHIP' and not internship_duration:
        errors['internship_duration_weeks'] = 'Required for internship employment type.'
    if employment_type == 'FULL_TIME' and internship_duration is not None:
        errors['internship_duration_weeks'] = 'Must be empty for full-time employment type.'

    stipend_min = data.get('stipend_min')
    stipend_max = data.get('stipend_max')
    if (stipend_min is not None) != (stipend_max is not None):
        errors['stipend'] = 'Both stipend_min and stipend_max are required when stipend is provided.'
    if stipend_min is not None and stipend_max is not None:
        try:
            stipend_min = float(stipend_min)
            stipend_max = float(stipend_max)
            if stipend_min > stipend_max:
                errors['stipend_min'] = 'stipend_min must be less than or equal to stipend_max.'
        except (ValueError, TypeError):
            errors['stipend'] = 'stipend_min and stipend_max must be numbers.'

    top_n = data.get('top_n', 10)
    try:
        top_n = int(top_n)
        if top_n < 1 or top_n > 50:
            errors['top_n'] = 'Must be between 1 and 50.'
    except (ValueError, TypeError):
        errors['top_n'] = 'Must be an integer.'

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    # Check resume
    resume_metadata = request.user.resume_metadata
    if not resume_metadata or not resume_metadata.get('skills'):
        return Response(
            {
                'detail': 'No resume data found. Please upload and parse your resume first.',
                'code': 'RESUME_NOT_FOUND',
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Build soft-filtered queryset
    jobs = Job.objects.all()

    if work_mode:
        jobs = jobs.filter(work_mode=work_mode)

    if employment_type:
        jobs = jobs.filter(employment_type=employment_type)

    location = data.get('location')
    if location:
        jobs = jobs.filter(location__icontains=str(location).strip().lower())

    if company_size:
        jobs = jobs.filter(company_size=company_size)

    if employment_type == 'INTERNSHIP' and internship_duration:
        jobs = jobs.filter(internship_duration_weeks=internship_duration)

    stipend_currency = data.get('stipend_currency', 'INR')
    if stipend_min is not None and stipend_max is not None:
        jobs = jobs.filter(
            stipend_min__isnull=False,
            stipend_max__isnull=False,
            stipend_currency=stipend_currency,
        ).filter(
            Q(stipend_max__gte=stipend_min) & Q(stipend_min__lte=stipend_max)
        )

    jobs = jobs.order_by('-published_at', '-created_at')
    total_considered = jobs.count()

    preferences_echo = {
        k: v for k, v in data.items()
        if k in ('work_mode', 'employment_type', 'location', 'company_size_preference',
                 'internship_duration_weeks', 'stipend_min', 'stipend_max', 'stipend_currency')
        and v is not None
    }

    if total_considered == 0:
        return Response(
            {
                'preferences': preferences_echo,
                'total_jobs_considered': 0,
                'resume_skills_count': len(extract_skills_from_resume(resume_metadata)),
                'recommendations': [],
            },
            status=status.HTTP_200_OK,
        )

    ranked = score_and_rank_jobs(jobs, resume_metadata, top_n=top_n)

    results = []
    for item in ranked:
        job = item['job']
        results.append({
            'id': job.id,
            'job_id': job.job_id,
            'title': job.title,
            'company_name': job.company_name,
            'location': job.location,
            'work_mode': job.work_mode,
            'employment_type': job.employment_type,
            'experience_level': job.experience_level,
            'sector': job.sector,
            'description': job.description,
            'job_url': job.job_url,
            'apply_url': job.apply_url,
            'apply_type': job.apply_type,
            'published_at': str(job.published_at) if job.published_at else None,
            'skill_match_score': item['skill_match_score'],
            'matched_skills': item['matched_skills'],
            'composite_score': item['composite_score'],
            'match_reasons': item['match_reasons'],
        })

    return Response(
        {
            'preferences': preferences_echo,
            'total_jobs_considered': total_considered,
            'resume_skills_count': len(extract_skills_from_resume(resume_metadata)),
            'recommendations': results,
        },
        status=status.HTTP_200_OK,
    )
