from django.conf import settings
from rest_framework import status
from rest_framework.authentication import BasicAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import JobPreference, MatchingRun
from .serializers import (
    JobPreferenceRequestSerializer,
    JobSerializer,
    MatchingRunCreateSerializer,
    MatchingRunDetailSerializer,
    MatchingRunListSerializer,
)
from .services.filtering import filter_jobs
from .services.preferences import normalize_preferences, to_json_safe
from .tasks import run_matching_pipeline


class MatchJobsByPreferenceView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = JobPreferenceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        normalized = normalize_preferences(validated)

        if validated.get('save_preference', True):
            defaults = serializer.to_model_defaults()
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
        results = JobSerializer(paginated_jobs if paginated_jobs is not None else jobs, many=True).data

        preference_echo = serializer.to_model_defaults()
        preference_echo['location'] = normalized['location']
        return Response(
            {
                'preference': preference_echo,
                'count': filtering_result['total_considered'],
                'next': paginator.get_next_link() if paginated_jobs is not None else None,
                'previous': paginator.get_previous_link() if paginated_jobs is not None else None,
                'results': results,
            },
            status=status.HTTP_200_OK,
        )


class MatchingRunCreateView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not getattr(settings, 'AGENT_MATCHING_ENABLED', True):
            return Response(
                {'detail': 'Agentic matching is disabled.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = MatchingRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        preferences_data = serializer.validated_data['preferences']
        preferences_serializer = JobPreferenceRequestSerializer(data=preferences_data)
        preferences_serializer.is_valid(raise_exception=True)
        preferences = preferences_serializer.validated_data
        normalized_preferences = normalize_preferences(preferences)

        save_preference = preferences.get('save_preference', True)
        if save_preference:
            defaults = preferences_serializer.to_model_defaults()
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
                serializer.validated_data.get('candidate_profile') or {}
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
                'submitted_at': run.created_at,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class MatchingRunListView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = MatchingRun.objects.filter(user=request.user).order_by('-created_at')
        paginator = PageNumberPagination()
        paginator.page_size = 10
        page = paginator.paginate_queryset(queryset, request)
        data = MatchingRunListSerializer(page if page is not None else queryset, many=True).data
        return Response(
            {
                'count': queryset.count(),
                'next': paginator.get_next_link() if page is not None else None,
                'previous': paginator.get_previous_link() if page is not None else None,
                'results': data,
            },
            status=status.HTTP_200_OK,
        )


class MatchingRunDetailView(APIView):
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        run = MatchingRun.objects.filter(id=run_id, user=request.user).first()
        if not run:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        data = MatchingRunDetailSerializer(run).data
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
