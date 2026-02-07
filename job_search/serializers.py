from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Job, JobPreference, MatchingResult, MatchingRun


class JobPreferenceRequestSerializer(serializers.Serializer):
    work_mode = serializers.ChoiceField(choices=JobPreference._meta.get_field('work_mode').choices)
    employment_type = serializers.ChoiceField(
        choices=JobPreference._meta.get_field('employment_type').choices
    )
    internship_duration_weeks = serializers.IntegerField(required=False, min_value=1)
    location = serializers.CharField(max_length=200)
    company_size_preference = serializers.ChoiceField(
        choices=JobPreference._meta.get_field('company_size_preference').choices
    )
    stipend_min = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    stipend_max = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    stipend_currency = serializers.CharField(max_length=3, required=False, default='INR')
    save_preference = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        employment_type = attrs.get('employment_type')
        duration = attrs.get('internship_duration_weeks')
        stipend_min = attrs.get('stipend_min')
        stipend_max = attrs.get('stipend_max')

        if employment_type == 'INTERNSHIP' and not duration:
            raise serializers.ValidationError(
                {'internship_duration_weeks': 'Required for internship employment type.'}
            )

        if employment_type == 'FULL_TIME' and duration is not None:
            raise serializers.ValidationError(
                {'internship_duration_weeks': 'Must be empty for full-time employment type.'}
            )

        stipend_bounds = [stipend_min, stipend_max]
        if any(bound is not None for bound in stipend_bounds) and any(
            bound is None for bound in stipend_bounds
        ):
            raise serializers.ValidationError(
                'Both stipend_min and stipend_max are required when stipend is provided.'
            )

        if stipend_min is not None and stipend_max is not None and stipend_min > stipend_max:
            raise serializers.ValidationError(
                {'stipend_min': 'stipend_min must be less than or equal to stipend_max.'}
            )

        return attrs

    def to_model_defaults(self):
        data = self.validated_data.copy()
        data.pop('save_preference', None)
        return data


class MatchingRunCreateSerializer(serializers.Serializer):
    preferences = JobPreferenceRequestSerializer()
    candidate_profile = serializers.JSONField(required=False, allow_null=True)


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            'id',
            'job_id',
            'title',
            'company_name',
            'location',
            'work_mode',
            'employment_type',
            'internship_duration_weeks',
            'company_size',
            'stipend_min',
            'stipend_max',
            'stipend_currency',
            'job_url',
            'apply_url',
            'apply_type',
            'published_at',
        ]


class JobPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobPreference
        fields = [
            'work_mode',
            'employment_type',
            'internship_duration_weeks',
            'location',
            'company_size_preference',
            'stipend_min',
            'stipend_max',
            'stipend_currency',
            'is_active',
        ]

    def validate(self, attrs):
        instance = JobPreference(**attrs)
        try:
            instance.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict if hasattr(exc, 'message_dict') else exc.messages
            )
        return attrs


class MatchingResultSerializer(serializers.ModelSerializer):
    job_id = serializers.CharField(source='job.job_id', read_only=True)

    class Meta:
        model = MatchingResult
        fields = [
            'rank',
            'job_id',
            'selection_probability',
            'fit_score',
            'job_quality_score',
            'why',
        ]


class MatchingRunListSerializer(serializers.ModelSerializer):
    run_id = serializers.UUIDField(source='id', read_only=True)

    class Meta:
        model = MatchingRun
        fields = ['run_id', 'status', 'filtered_jobs_count', 'created_at', 'completed_at']


class MatchingRunDetailSerializer(serializers.ModelSerializer):
    run_id = serializers.UUIDField(source='id', read_only=True)
    top_5_jobs = MatchingResultSerializer(source='results', many=True, read_only=True)

    class Meta:
        model = MatchingRun
        fields = [
            'run_id',
            'status',
            'preferences_snapshot',
            'filtered_jobs_count',
            'timing_metrics',
            'top_5_jobs',
            'error_code',
            'error_message',
            'started_at',
            'completed_at',
            'created_at',
        ]
