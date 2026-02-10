import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from rest_framework import status
from rest_framework.authentication import BasicAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    COMPANY_SIZE_CHOICES,
    EMPLOYMENT_TYPE_CHOICES,
    WORK_MODE_CHOICES,
    CandidateRankingRun,
    CandidateRankingResult,
    CompanyTaskJob,
    JobCandidate,
    Job,
    JobPreference,
    MatchingRun,
    RECRUITER_COLLEGE_TIERS,
    RecruiterJobPreference,
)
from .process_sheet_and_parse_candidates_data import (
    extract_spreadsheet_id,
    fetch_rows_from_sheet,
    parse_resume_from_drive_link,
)
from .services.filtering import filter_jobs
from .services.preferences import normalize_preferences, to_json_safe
from .services.skill_matching import extract_skills_from_resume, score_and_rank_jobs
from .tasks import run_candidate_ranking_pipeline, run_matching_pipeline
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


def _find_column_index(header_row, accepted_names):
    lookup = {str(col).strip().lower(): index for index, col in enumerate(header_row or [])}
    for name in accepted_names:
        idx = lookup.get(name.lower())
        if idx is not None:
            return idx
    return None


def _chunked(items, batch_size):
    for start in range(0, len(items), batch_size):
        yield start, items[start:start + batch_size]


def _validate_coding_platform_criteria(criteria):
    if criteria is None:
        return []
    if not isinstance(criteria, list):
        return None, 'Must be a list.'

    normalized = []
    allowed_operators = {'gte', 'lte', 'eq'}
    for index, rule in enumerate(criteria):
        if not isinstance(rule, dict):
            return None, f'Rule at index {index} must be an object.'

        required = {'platform', 'metric', 'operator', 'value'}
        missing = required - set(rule.keys())
        if missing:
            return None, f'Rule at index {index} missing fields: {sorted(missing)}'

        platform = str(rule.get('platform', '')).strip()
        metric = str(rule.get('metric', '')).strip()
        operator = str(rule.get('operator', '')).strip().lower()
        value = rule.get('value')

        if not platform:
            return None, f'Rule at index {index}: platform is required.'
        if not metric:
            return None, f'Rule at index {index}: metric is required.'
        if operator not in allowed_operators:
            return None, f'Rule at index {index}: operator must be one of {sorted(allowed_operators)}.'
        if not isinstance(value, (int, float)):
            return None, f'Rule at index {index}: value must be numeric.'

        normalized.append(
            {
                'platform': platform,
                'metric': metric,
                'operator': operator,
                'value': value,
            }
        )
    return normalized, None
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


def _serialize_candidate_ranking_run(run):
    return {
        'run_id': str(run.id),
        'job_id': run.job_id,
        'status': run.status,
        'total_candidates': run.total_candidates,
        'processed_candidates': run.processed_candidates,
        'shortlisted_count': run.shortlisted_count,
        'batch_size': run.batch_size,
        'model_name': run.model_name,
        'error_code': run.error_code,
        'error_message': run.error_message,
        'timing_metrics': run.timing_metrics,
        'started_at': run.started_at.isoformat() if run.started_at else None,
        'completed_at': run.completed_at.isoformat() if run.completed_at else None,
        'created_at': run.created_at.isoformat() if run.created_at else None,
    }


def _serialize_candidate_ranking_result(result):
    return {
        'rank': result.rank,
        'candidate_id': result.candidate_id,
        'name': result.candidate.name,
        'email': result.candidate.email,
        'is_shortlisted': result.is_shortlisted,
        'passes_hard_filter': result.passes_hard_filter,
        'final_score': str(result.final_score),
        'sub_scores': result.sub_scores,
        'filter_reasons': result.filter_reasons,
        'summary': result.summary,
    }


@api_view(['POST'])
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


@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def company_task_job_create_view(request):
    job_description = request.data.get('job_description')
    if job_description is None or str(job_description).strip() == '':
        return Response(
            {'job_description': 'This field is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    created_job = CompanyTaskJob.objects.create(job_description=str(job_description).strip())
    return Response(
        {
            'id': created_job.id,
            'job_description': created_job.job_description,
            'created_at': created_job.created_at.isoformat() if created_job.created_at else None,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def company_task_job_import_candidates_view(request):
    spreadsheet_url = request.data.get('spreadsheet_url')
    job_id_raw = request.data.get('job_id')
    range_name = (request.data.get('range_name') or 'Sheet1!A1:Z1000').strip()
    batch_size_raw = request.data.get('batch_size', 10)

    errors = {}
    if not spreadsheet_url:
        errors['spreadsheet_url'] = 'This field is required.'

    try:
        job_id = int(job_id_raw)
    except (TypeError, ValueError):
        errors['job_id'] = 'Must be an integer.'
        job_id = None

    try:
        batch_size = int(batch_size_raw)
        if batch_size < 1 or batch_size > 100:
            errors['batch_size'] = 'Must be between 1 and 100.'
    except (TypeError, ValueError):
        errors['batch_size'] = 'Must be an integer.'
        batch_size = 10

    spreadsheet_id = extract_spreadsheet_id(spreadsheet_url or '')
    if not spreadsheet_id:
        errors['spreadsheet_url'] = 'Invalid Google Spreadsheet URL or ID.'

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    job = CompanyTaskJob.objects.filter(id=job_id).first()
    if not job:
        return Response({'detail': 'Job not found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        rows = fetch_rows_from_sheet(spreadsheet_id=spreadsheet_id, range_name=range_name)
    except Exception as exc:
        return Response(
            {'detail': f'Failed to read spreadsheet: {str(exc)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not rows:
        return Response(
            {
                'job_id': job.id,
                'spreadsheet_id': spreadsheet_id,
                'range_name': range_name,
                'total_rows': 0,
                'processed': 0,
                'created': 0,
                'skipped': 0,
                'failed': 0,
                'batches': [],
                'errors': [],
            },
            status=status.HTTP_200_OK,
        )

    header = rows[0]
    data_rows = rows[1:]

    name_idx = _find_column_index(header, ['name'])
    email_idx = _find_column_index(header, ['email'])
    resume_idx = _find_column_index(header, ['resume_link', 'resume link'])

    if name_idx is None:
        return Response(
            {'detail': 'Required column not found: name'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if email_idx is None:
        return Response(
            {'detail': 'Required column not found: email'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if resume_idx is None:
        return Response(
            {'detail': 'Required column not found: resume_link/Resume Link'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    created_count = 0
    skipped_count = 0
    failed_count = 0
    errors_list = []
    batch_summaries = []

    for batch_start, batch_rows in _chunked(data_rows, batch_size):
        batch_created = 0
        batch_skipped = 0
        batch_failed = 0

        for offset, row in enumerate(batch_rows):
            row_number = batch_start + offset + 2
            try:
                name = (
                    str(row[name_idx]).strip()
                    if len(row) > name_idx and row[name_idx]
                    else ''
                )
                email = (
                    str(row[email_idx]).strip().lower()
                    if len(row) > email_idx and row[email_idx]
                    else ''
                )
                resume_link = (
                    str(row[resume_idx]).strip()
                    if len(row) > resume_idx and row[resume_idx]
                    else ''
                )

                if not name:
                    failed_count += 1
                    batch_failed += 1
                    errors_list.append({'row': row_number, 'error': 'Name is missing.'})
                    continue

                if not email:
                    failed_count += 1
                    batch_failed += 1
                    errors_list.append({'row': row_number, 'error': 'Email is missing.'})
                    continue

                if not resume_link:
                    failed_count += 1
                    batch_failed += 1
                    errors_list.append({'row': row_number, 'error': 'Resume link is missing.'})
                    continue

                if JobCandidate.objects.filter(job=job, email__iexact=email).exists():
                    skipped_count += 1
                    batch_skipped += 1
                    continue

                sections = parse_resume_from_drive_link(resume_link)
                resume_payload = {
                    'name': name,
                    'email': email,
                    'sections': dict(sections),
                }

                JobCandidate.objects.create(
                    job=job,
                    name=name,
                    email=email,
                    resume_data=json.dumps(resume_payload, ensure_ascii=False),
                )
                created_count += 1
                batch_created += 1
            except Exception as exc:
                failed_count += 1
                batch_failed += 1
                errors_list.append({'row': row_number, 'error': str(exc)})

        batch_summaries.append(
            {
                'start_row': batch_start + 2,
                'end_row': batch_start + 1 + len(batch_rows),
                'created': batch_created,
                'skipped': batch_skipped,
                'failed': batch_failed,
            }
        )
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
            'job_id': job.id,
            'spreadsheet_id': spreadsheet_id,
            'range_name': range_name,
            'batch_size': batch_size,
            'total_rows': len(data_rows),
            'processed': len(data_rows),
            'created': created_count,
            'skipped': skipped_count,
            'failed': failed_count,
            'batches': batch_summaries,
            'errors': errors_list,
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
def company_task_job_preference_upsert_view(request):
    payload = request.data
    errors = {}

    job_id = _coerce_int(payload.get('job_id'), 'job_id', errors, min_value=100)

    college_tiers = payload.get('college_tiers')
    allowed_tiers = {item[0] for item in RECRUITER_COLLEGE_TIERS}
    normalized_tiers = []
    if not isinstance(college_tiers, list) or not college_tiers:
        errors['college_tiers'] = 'Must be a non-empty list.'
    else:
        seen = set()
        for tier in college_tiers:
            if not isinstance(tier, str):
                errors['college_tiers'] = 'Each tier must be a string.'
                break
            normalized = tier.strip().upper()
            if normalized not in allowed_tiers:
                errors['college_tiers'] = f'Allowed values: {sorted(allowed_tiers)}'
                break
            if normalized in seen:
                errors['college_tiers'] = 'Duplicate tiers are not allowed.'
                break
            seen.add(normalized)
            normalized_tiers.append(normalized)

    min_experience_years = _coerce_decimal(
        payload.get('min_experience_years'),
        'min_experience_years',
        errors,
    )
    max_experience_years = _coerce_decimal(
        payload.get('max_experience_years'),
        'max_experience_years',
        errors,
    )

    if min_experience_years is None:
        errors['min_experience_years'] = 'This field is required.'
    elif min_experience_years < 0:
        errors['min_experience_years'] = 'Must be >= 0.'

    if max_experience_years is None:
        errors['max_experience_years'] = 'This field is required.'
    elif max_experience_years < 0:
        errors['max_experience_years'] = 'Must be >= 0.'

    if (
        min_experience_years is not None
        and max_experience_years is not None
        and min_experience_years > max_experience_years
    ):
        errors['max_experience_years'] = 'Must be >= min_experience_years.'

    number_of_openings = _coerce_int(
        payload.get('number_of_openings'),
        'number_of_openings',
        errors,
        min_value=1,
    )
    if number_of_openings is None:
        errors['number_of_openings'] = 'This field is required.'

    coding_platform_criteria, coding_err = _validate_coding_platform_criteria(
        payload.get('coding_platform_criteria', [])
    )
    if coding_err:
        errors['coding_platform_criteria'] = coding_err

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    job = CompanyTaskJob.objects.filter(id=job_id).first()
    if not job:
        return Response({'detail': 'Job not found.'}, status=status.HTTP_404_NOT_FOUND)

    existing = RecruiterJobPreference.objects.filter(job=job).first()
    if existing:
        existing.college_tiers = normalized_tiers
        existing.min_experience_years = min_experience_years
        existing.max_experience_years = max_experience_years
        existing.coding_platform_criteria = coding_platform_criteria
        existing.number_of_openings = number_of_openings
        existing.full_clean()
        existing.save(
            update_fields=[
                'college_tiers',
                'min_experience_years',
                'max_experience_years',
                'coding_platform_criteria',
                'number_of_openings',
                'updated_at',
            ]
        )
        preference = existing
        response_status = status.HTTP_200_OK
    else:
        preference = RecruiterJobPreference(
            job=job,
            college_tiers=normalized_tiers,
            min_experience_years=min_experience_years,
            max_experience_years=max_experience_years,
            coding_platform_criteria=coding_platform_criteria,
            number_of_openings=number_of_openings,
        )
        preference.full_clean()
        preference.save()
        response_status = status.HTTP_201_CREATED

    return Response(
        {
            'job_id': preference.job_id,
            'college_tiers': preference.college_tiers,
            'min_experience_years': str(preference.min_experience_years),
            'max_experience_years': str(preference.max_experience_years),
            'number_of_openings': preference.number_of_openings,
            'coding_platform_criteria': preference.coding_platform_criteria,
            'updated_at': preference.updated_at.isoformat() if preference.updated_at else None,
        },
        status=response_status,
    )


@api_view(['POST'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def candidate_ranking_run_create_view(request):
    if not getattr(settings, 'CANDIDATE_AI_ENABLED', True):
        return Response(
            {'detail': 'Candidate AI ranking is disabled.'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    job_id = request.data.get('job_id')
    batch_size_raw = request.data.get('batch_size', 20)
    force_recompute = _coerce_bool(
        request.data.get('force_recompute'),
        'force_recompute',
        errors={},
        default=False,
    )

    errors = {}
    parsed_job_id = _coerce_int(job_id, 'job_id', errors, min_value=100)
    parsed_batch_size = _coerce_int(batch_size_raw, 'batch_size', errors, min_value=1)
    if parsed_batch_size is None:
        errors['batch_size'] = 'This field is required.'
    elif parsed_batch_size > 100:
        errors['batch_size'] = 'Must be <= 100.'

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    job = CompanyTaskJob.objects.filter(id=parsed_job_id).first()
    if not job:
        return Response({'detail': 'Job not found.'}, status=status.HTTP_404_NOT_FOUND)

    if not hasattr(job, 'recruiter_preference'):
        return Response(
            {'detail': 'Recruiter preference must be configured before ranking.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not force_recompute:
        existing = CandidateRankingRun.objects.filter(
            job=job, status=CandidateRankingRun.STATUS_COMPLETED
        ).order_by('-created_at').first()
        if existing:
            return Response(
                {
                    'run_id': str(existing.id),
                    'status': existing.status,
                    'reused': True,
                },
                status=status.HTTP_200_OK,
            )

    run = CandidateRankingRun.objects.create(
        job=job,
        status=CandidateRankingRun.STATUS_PENDING,
        batch_size=parsed_batch_size,
        model_name=getattr(settings, 'OPENAI_MODEL', 'gpt-4.1') or 'gpt-4.1',
    )
    try:
        run_candidate_ranking_pipeline.delay(str(run.id))
    except Exception:
        run_candidate_ranking_pipeline.run(str(run.id))

    return Response(
        {
            'run_id': str(run.id),
            'status': run.status,
            'reused': False,
            'submitted_at': run.created_at.isoformat() if run.created_at else None,
        },
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(['GET'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def candidate_ranking_run_detail_view(request, run_id):
    run = CandidateRankingRun.objects.filter(id=run_id).select_related('job').first()
    if not run:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    results = CandidateRankingResult.objects.filter(run=run).select_related('candidate').order_by('rank')
    return Response(
        {
            **_serialize_candidate_ranking_run(run),
            'results': [_serialize_candidate_ranking_result(item) for item in results],
        },
        status=status.HTTP_200_OK,
    )


@api_view(['GET'])
@authentication_classes([BasicAuthentication])
@permission_classes([IsAuthenticated])
def candidate_ranking_run_list_view(request, job_id):
    run_queryset = CandidateRankingRun.objects.filter(job_id=job_id).order_by('-created_at')
    paginator = PageNumberPagination()
    paginator.page_size = 10
    page = paginator.paginate_queryset(run_queryset, request)
    page_queryset = page if page is not None else run_queryset

    return Response(
        {
            'count': run_queryset.count(),
            'next': paginator.get_next_link() if page is not None else None,
            'previous': paginator.get_previous_link() if page is not None else None,
            'results': [_serialize_candidate_ranking_run(run) for run in page_queryset],
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
