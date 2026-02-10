from decimal import Decimal, InvalidOperation

from django.conf import settings
from rest_framework import status
from rest_framework.authentication import BasicAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Job,
    JobAlert,
    JobPreference,
    MatchingRun,
    PreferenceChangeLog,
    WORK_MODE_CHOICES,
    EMPLOYMENT_TYPE_CHOICES,
    COMPANY_SIZE_CHOICES,
)
from .services.preferences import normalize_preferences, to_json_safe
from .tasks import run_matching_pipeline

VALID_WEIGHT_KEYS = {
    'work_mode', 'location', 'stipend', 'company_size',
    'experience_level', 'sector', 'role_match', 'company_preference', 'skill_match',
}


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


def _coerce_string_list(value, field, errors, max_items=50):
    if value is None:
        return []
    if not isinstance(value, list):
        errors[field] = 'Must be a list.'
        return []
    if len(value) > max_items:
        errors[field] = f'Maximum {max_items} items allowed.'
        return []
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            errors[field] = 'All items must be non-empty strings.'
            return []
        result.append(item.strip())
    return result


def _coerce_weights(value, field, errors):
    if value is None:
        return {}
    if not isinstance(value, dict):
        errors[field] = 'Must be an object.'
        return {}
    result = {}
    for key, weight in value.items():
        if key not in VALID_WEIGHT_KEYS:
            errors[field] = f'Invalid weight key: {key}. Valid keys: {", ".join(sorted(VALID_WEIGHT_KEYS))}'
            return {}
        try:
            w = float(weight)
        except (TypeError, ValueError):
            errors[field] = f'Weight for {key} must be a number.'
            return {}
        if w < 0.0 or w > 1.0:
            errors[field] = f'Weight for {key} must be between 0.0 and 1.0.'
            return {}
        result[key] = w
    return result


def _validate_preference_payload(data):
    errors = {}
    valid_work_modes = [c[0] for c in WORK_MODE_CHOICES]
    valid_employment_types = [c[0] for c in EMPLOYMENT_TYPE_CHOICES]
    valid_company_sizes = [c[0] for c in COMPANY_SIZE_CHOICES]
    valid_experience_levels = [c[0] for c in Job.EXPERIENCE_LEVEL_CHOICES]

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

    # Experience level (optional)
    experience_level = data.get('experience_level')
    if experience_level is not None and experience_level != '':
        if experience_level not in valid_experience_levels:
            errors['experience_level'] = f'Must be one of: {", ".join(valid_experience_levels)}'
    else:
        experience_level = None

    # List fields
    preferred_sectors = _coerce_string_list(data.get('preferred_sectors'), 'preferred_sectors', errors)
    excluded_sectors = _coerce_string_list(data.get('excluded_sectors'), 'excluded_sectors', errors)
    preferred_roles = _coerce_string_list(data.get('preferred_roles'), 'preferred_roles', errors)
    excluded_keywords = _coerce_string_list(data.get('excluded_keywords'), 'excluded_keywords', errors)
    excluded_companies = _coerce_string_list(data.get('excluded_companies'), 'excluded_companies', errors)
    preferred_companies = _coerce_string_list(data.get('preferred_companies'), 'preferred_companies', errors)

    # Cross-validation: no overlap between preferred and excluded
    if preferred_sectors and excluded_sectors:
        overlap = set(s.lower() for s in preferred_sectors) & set(s.lower() for s in excluded_sectors)
        if overlap:
            errors['preferred_sectors'] = f'Cannot overlap with excluded_sectors: {", ".join(overlap)}'

    if excluded_companies and preferred_companies:
        overlap = set(c.lower() for c in excluded_companies) & set(c.lower() for c in preferred_companies)
        if overlap:
            errors['preferred_companies'] = f'Cannot overlap with excluded_companies: {", ".join(overlap)}'

    # Weights
    weights = _coerce_weights(data.get('weights'), 'weights', errors)

    # Name (for multi-profile)
    name = _coerce_str(data.get('name'), 'name', errors, max_length=100) or 'Default'

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
        'experience_level': experience_level,
        'preferred_sectors': preferred_sectors,
        'excluded_sectors': excluded_sectors,
        'preferred_roles': preferred_roles,
        'excluded_keywords': excluded_keywords,
        'excluded_companies': excluded_companies,
        'preferred_companies': preferred_companies,
        'weights': weights,
        'name': name,
    }
    return validated, None


def _preference_defaults(validated):
    defaults = validated.copy()
    defaults.pop('save_preference', None)
    defaults.pop('name', None)
    return defaults


def _preference_from_model(preference):
    return {
        'id': preference.id,
        'name': preference.name,
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
        'weights': preference.weights,
    }


def _log_preference_change(user, preference, action, before=None, after=None):
    before = before or {}
    after = after or {}
    changes = {}
    all_keys = set(list(before.keys()) + list(after.keys()))
    for key in all_keys:
        old_val = before.get(key)
        new_val = after.get(key)
        if old_val != new_val:
            changes[key] = {'old': old_val, 'new': new_val}
    PreferenceChangeLog.objects.create(
        user=user,
        preference=preference,
        action=action,
        preference_name=preference.name if preference else '',
        snapshot_before=to_json_safe(before),
        snapshot_after=to_json_safe(after),
        changes=to_json_safe(changes),
    )


def _serialize_matching_result(result):
    return to_json_safe(
        {
            'rank': result.rank,
            'job_id': result.job.job_id,
            'title': result.job.title,
            'company_name': result.job.company_name,
            'location': result.job.location,
            'work_mode': result.job.work_mode,
            'sector': result.job.sector or '',
            'employment_type': result.job.employment_type,
            'apply_url': result.job.apply_url or result.job.job_url,
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
        'error_code': run.error_code,
        'error_message': run.error_message,
        'started_at': run.started_at.isoformat() if run.started_at else None,
        'completed_at': run.completed_at.isoformat() if run.completed_at else None,
        'created_at': run.created_at.isoformat() if run.created_at else None,
    }


@api_view(['GET', 'POST', 'DELETE'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def preferences_view(request):
    if request.method == 'GET':
        preferences = JobPreference.objects.filter(user=request.user, is_active=True)
        if not preferences.exists():
            return Response({'preference': None}, status=status.HTTP_200_OK)
        if preferences.count() == 1:
            return Response(
                {'preference': to_json_safe(_preference_from_model(preferences.first()))},
                status=status.HTTP_200_OK,
            )
        return Response(
            {'preferences': [to_json_safe(_preference_from_model(p)) for p in preferences]},
            status=status.HTTP_200_OK,
        )

    if request.method == 'DELETE':
        name = request.data.get('name') if request.data else None
        qs = JobPreference.objects.filter(user=request.user, is_active=True)
        if name:
            qs = qs.filter(name=name)
        preference = qs.first()
        if not preference:
            return Response(
                {'detail': 'No active preference to delete.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        before_snapshot = _preference_from_model(preference)
        preference.is_active = False
        preference.save(update_fields=['is_active', 'updated_at'])
        _log_preference_change(
            request.user, preference,
            PreferenceChangeLog.ACTION_DELETED,
            before=before_snapshot,
        )
        return Response({'detail': 'Preference deleted.'}, status=status.HTTP_200_OK)

    validated, errors = _validate_preference_payload(request.data)
    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    normalized = normalize_preferences(validated)

    if validated.get('save_preference', True):
        defaults = _preference_defaults(validated)
        defaults['location'] = normalized['location']
        name = validated.get('name', 'Default')

        existing = JobPreference.objects.filter(
            user=request.user, name=name, is_active=True
        ).first()
        before_snapshot = _preference_from_model(existing) if existing else {}

        preference, created = JobPreference.objects.update_or_create(
            user=request.user,
            name=name,
            is_active=True,
            defaults=defaults,
        )
        after_snapshot = _preference_from_model(preference)
        _log_preference_change(
            request.user, preference,
            PreferenceChangeLog.ACTION_CREATED if created else PreferenceChangeLog.ACTION_UPDATED,
            before=before_snapshot,
            after=after_snapshot,
        )

    preference_echo = _preference_defaults(validated)
    preference_echo['location'] = normalized['location']
    return Response(
        {
            'preference': to_json_safe(preference_echo),
        },
        status=status.HTTP_200_OK,
    )


@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def preference_detail_view(request, preference_id):
    preference = JobPreference.objects.filter(
        id=preference_id, user=request.user, is_active=True
    ).first()
    if not preference:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(
            {'preference': to_json_safe(_preference_from_model(preference))},
            status=status.HTTP_200_OK,
        )

    if request.method == 'DELETE':
        before_snapshot = _preference_from_model(preference)
        preference.is_active = False
        preference.save(update_fields=['is_active', 'updated_at'])
        _log_preference_change(
            request.user, preference,
            PreferenceChangeLog.ACTION_DELETED,
            before=before_snapshot,
        )
        return Response({'detail': 'Preference deleted.'}, status=status.HTTP_200_OK)

    # PUT
    validated, errors = _validate_preference_payload(request.data)
    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    normalized = normalize_preferences(validated)
    before_snapshot = _preference_from_model(preference)

    defaults = _preference_defaults(validated)
    defaults['location'] = normalized['location']
    for key, value in defaults.items():
        setattr(preference, key, value)
    preference.save()

    after_snapshot = _preference_from_model(preference)
    _log_preference_change(
        request.user, preference,
        PreferenceChangeLog.ACTION_UPDATED,
        before=before_snapshot,
        after=after_snapshot,
    )
    return Response(
        {'preference': to_json_safe(_preference_from_model(preference))},
        status=status.HTTP_200_OK,
    )


@api_view(['GET', 'POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def matches_runs_view(request):
    if request.method == 'GET':
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

    if not getattr(settings, 'AGENT_MATCHING_ENABLED', True):
        return Response(
            {'detail': 'Agentic matching is disabled.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    payload = request.data
    preferences_data = payload.get('preferences')
    if preferences_data is None:
        # Try preference_id or preference_name first, then fall back to most recent
        pref_id = payload.get('preference_id')
        pref_name = payload.get('preference_name')
        if pref_id:
            active_preference = JobPreference.objects.filter(
                id=pref_id, user=request.user, is_active=True
            ).first()
        elif pref_name:
            active_preference = JobPreference.objects.filter(
                name=pref_name, user=request.user, is_active=True
            ).first()
        else:
            active_preference = JobPreference.objects.filter(
                user=request.user, is_active=True
            ).order_by('-updated_at').first()

        if not active_preference:
            return Response(
                {
                    'detail': 'No active preference found. Save preferences before matching.',
                    'code': 'PREFERENCE_NOT_FOUND',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        preferences = _preference_from_model(active_preference)
    else:
        if not isinstance(preferences_data, dict):
            return Response(
                {'preferences': 'This field must be an object.'},
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
            name = preferences.get('name', 'Default')
            JobPreference.objects.update_or_create(
                user=request.user,
                name=name,
                is_active=True,
                defaults=defaults,
            )
    if preferences_data is None:
        normalized_preferences = normalize_preferences(preferences)

    candidate_profile = payload.get('candidate_profile') or {}
    user_resume_metadata = getattr(request.user, 'resume_metadata', None) or {}
    if user_resume_metadata:
        candidate_profile['resume_metadata'] = user_resume_metadata

    run = MatchingRun.objects.create(
        user=request.user,
        status=MatchingRun.STATUS_PENDING,
        preferences_snapshot=to_json_safe(
            {k: v for k, v in normalized_preferences.items() if k not in ('save_preference', 'name', 'id')}
        ),
        candidate_profile_snapshot=to_json_safe(candidate_profile),
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
def matches_run_detail_view(request, run_id):
    run = MatchingRun.objects.filter(id=run_id, user=request.user).first()
    if not run:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    data = _serialize_matching_run_detail(run)

    # Build matched_jobs with pagination
    matched_jobs_data = {}
    if run.status == MatchingRun.STATUS_COMPLETED:
        results_qs = run.results.select_related('job').all()

        # Optional min_score filter
        min_score = request.query_params.get('min_score')
        if min_score:
            try:
                min_score = float(min_score)
                results_qs = results_qs.filter(selection_probability__gte=min_score)
            except (ValueError, TypeError):
                pass

        total_matched = results_qs.count()
        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(results_qs, request)
        page_results = page if page is not None else results_qs

        matched_jobs_data = {
            'count': total_matched,
            'next': paginator.get_next_link() if page is not None else None,
            'previous': paginator.get_previous_link() if page is not None else None,
            'results': [_serialize_matching_result(r) for r in page_results],
        }
    else:
        matched_jobs_data = {
            'count': 0,
            'next': None,
            'previous': None,
            'results': [],
        }

    return Response(
        {
            'run_id': data['run_id'],
            'status': data['status'],
            'filtered_jobs_count': data['filtered_jobs_count'],
            'preference_used': data['preferences_snapshot'],
            'timings': data['timing_metrics'],
            'matched_jobs': matched_jobs_data,
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


@api_view(['GET'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def skill_gap_view(request, run_id):
    run = MatchingRun.objects.filter(id=run_id, user=request.user).first()
    if not run:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if run.status != MatchingRun.STATUS_COMPLETED:
        return Response(
            {'detail': 'Skill gap analysis is only available for completed runs.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from .services.skill_gap import analyze_skill_gaps
    results = run.results.select_related('job').all()
    resume_metadata = getattr(request.user, 'resume_metadata', None) or {}
    analysis = analyze_skill_gaps(results, resume_metadata)
    return Response(analysis, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def preference_history_view(request):
    queryset = PreferenceChangeLog.objects.filter(user=request.user).order_by('-created_at')
    paginator = PageNumberPagination()
    paginator.page_size = 20
    page = paginator.paginate_queryset(queryset, request)
    page_queryset = page if page is not None else queryset
    data = [
        {
            'id': log.id,
            'action': log.action,
            'preference_name': log.preference_name,
            'changes': log.changes,
            'snapshot_before': log.snapshot_before,
            'snapshot_after': log.snapshot_after,
            'created_at': log.created_at.isoformat() if log.created_at else None,
        }
        for log in page_queryset
    ]
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
def alerts_view(request):
    queryset = JobAlert.objects.filter(user=request.user).select_related('job', 'preference')
    unread_only = request.query_params.get('unread_only', '').lower()
    if unread_only in ('true', '1', 'yes'):
        queryset = queryset.filter(is_read=False)

    paginator = PageNumberPagination()
    paginator.page_size = 20
    page = paginator.paginate_queryset(queryset, request)
    page_queryset = page if page is not None else queryset
    data = [
        {
            'id': alert.id,
            'job_id': alert.job.job_id,
            'job_title': alert.job.title,
            'company_name': alert.job.company_name,
            'preference_name': alert.preference_name,
            'match_score': to_json_safe(alert.match_score),
            'match_reasons': alert.match_reasons,
            'is_read': alert.is_read,
            'created_at': alert.created_at.isoformat() if alert.created_at else None,
        }
        for alert in page_queryset
    ]
    return Response(
        {
            'count': queryset.count(),
            'next': paginator.get_next_link() if page is not None else None,
            'previous': paginator.get_previous_link() if page is not None else None,
            'results': data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def alerts_mark_read_view(request):
    alert_ids = request.data.get('alert_ids')
    if alert_ids is None:
        # Mark all as read
        updated = JobAlert.objects.filter(user=request.user, is_read=False).update(is_read=True)
    else:
        if not isinstance(alert_ids, list):
            return Response({'alert_ids': 'Must be a list.'}, status=status.HTTP_400_BAD_REQUEST)
        updated = JobAlert.objects.filter(
            user=request.user, id__in=alert_ids, is_read=False
        ).update(is_read=True)

    return Response({'marked_read': updated}, status=status.HTTP_200_OK)
