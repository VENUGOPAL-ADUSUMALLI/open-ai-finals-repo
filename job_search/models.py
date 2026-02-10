import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q

WORK_MODE_CHOICES = [
    ('REMOTE', 'Remote'),
    ('ONSITE', 'Onsite'),
]

EMPLOYMENT_TYPE_CHOICES = [
    ('FULL_TIME', 'Full Time'),
    ('INTERNSHIP', 'Internship'),
]

COMPANY_SIZE_CHOICES = [
    ('SME', 'SME'),
    ('STARTUP', 'Startup'),
    ('MNC', 'MNC'),
]

RECRUITER_COLLEGE_TIERS = [
    ('TIER_1', 'Tier 1'),
    ('TIER_2', 'Tier 2'),
    ('TIER_3', 'Tier 3'),
]


class Job(models.Model):
    APPLY_TYPE_CHOICES = [
        ('EASY_APPLY', 'Easy Apply'),
        ('EXTERNAL', 'External'),
    ]

    EXPERIENCE_LEVEL_CHOICES = [
        ('Entry level', 'Entry level'),
        ('Mid-Senior level', 'Mid-Senior level'),
        ('Associate', 'Associate'),
        ('Director', 'Director'),
        ('Executive', 'Executive'),
        ('Internship', 'Internship'),
    ]

    CONTRACT_TYPE_CHOICES = [
        ('Full-time', 'Full-time'),
        ('Part-time', 'Part-time'),
        ('Contract', 'Contract'),
        ('Temporary', 'Temporary'),
        ('Internship', 'Internship'),
        ('Volunteer', 'Volunteer'),
    ]

    job_id = models.CharField(max_length=50, unique=True, db_index=True)

    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    description_html = models.TextField(blank=True)

    company_name = models.CharField(max_length=500)
    company_id = models.CharField(max_length=50, blank=True)
    company_url = models.URLField(max_length=1000, blank=True)

    location = models.CharField(max_length=500, blank=True)
    contract_type = models.CharField(max_length=50, choices=CONTRACT_TYPE_CHOICES, blank=True)
    experience_level = models.CharField(max_length=50, choices=EXPERIENCE_LEVEL_CHOICES, blank=True)
    work_type = models.CharField(max_length=200, blank=True)
    sector = models.CharField(max_length=500, blank=True)
    work_mode = models.CharField(
        max_length=20,
        choices=WORK_MODE_CHOICES,
        blank=True,
        null=True,
        db_index=True,
    )
    employment_type = models.CharField(
        max_length=20,
        choices=EMPLOYMENT_TYPE_CHOICES,
        blank=True,
        null=True,
        db_index=True,
    )
    internship_duration_weeks = models.PositiveSmallIntegerField(blank=True, null=True)
    company_size = models.CharField(
        max_length=20,
        choices=COMPANY_SIZE_CHOICES,
        blank=True,
        null=True,
        db_index=True,
    )
    stipend_min = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stipend_max = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stipend_currency = models.CharField(max_length=3, blank=True, null=True)

    salary = models.CharField(max_length=200, blank=True)
    benefits = models.TextField(blank=True)

    job_url = models.URLField(max_length=1000)
    apply_url = models.URLField(max_length=1000, blank=True)
    apply_type = models.CharField(max_length=20, choices=APPLY_TYPE_CHOICES, blank=True)
    applications_count = models.CharField(max_length=100, blank=True)

    published_at = models.DateField(null=True, blank=True)
    posted_time = models.CharField(max_length=100, blank=True)

    poster_profile_url = models.URLField(max_length=1000, blank=True)
    poster_full_name = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-published_at', '-created_at']
        indexes = [
            models.Index(fields=['company_name']),
            models.Index(fields=['location']),
            models.Index(fields=['experience_level']),
            models.Index(fields=['published_at']),
        ]

    def __str__(self):
        return f"{self.title} at {self.company_name}"


class JobPreference(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='job_preferences',
    )
    name = models.CharField(max_length=100, default='Default', blank=True)
    work_mode = models.CharField(max_length=20, choices=WORK_MODE_CHOICES)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES)
    internship_duration_weeks = models.PositiveSmallIntegerField(blank=True, null=True)
    location = models.CharField(max_length=200, db_index=True)
    company_size_preference = models.CharField(max_length=20, choices=COMPANY_SIZE_CHOICES)
    experience_level = models.CharField(
        max_length=50,
        choices=Job.EXPERIENCE_LEVEL_CHOICES,
        blank=True,
        null=True,
    )
    stipend_min = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stipend_max = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stipend_currency = models.CharField(max_length=3, default='INR')
    preferred_sectors = models.JSONField(default=list, blank=True)
    excluded_sectors = models.JSONField(default=list, blank=True)
    preferred_roles = models.JSONField(default=list, blank=True)
    excluded_keywords = models.JSONField(default=list, blank=True)
    excluded_companies = models.JSONField(default=list, blank=True)
    preferred_companies = models.JSONField(default=list, blank=True)
    weights = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'name'],
                condition=Q(is_active=True),
                name='unique_active_pref_name_per_user',
            ),
            models.CheckConstraint(
                condition=(
                    Q(stipend_min__isnull=True, stipend_max__isnull=True)
                    | Q(stipend_min__lte=models.F('stipend_max'))
                ),
                name='job_pref_stipend_min_lte_max',
            ),
        ]

    def clean(self):
        if self.employment_type == 'INTERNSHIP' and not self.internship_duration_weeks:
            raise ValidationError(
                {'internship_duration_weeks': 'Required for internship employment type.'}
            )
        if self.employment_type == 'FULL_TIME' and self.internship_duration_weeks is not None:
            raise ValidationError(
                {'internship_duration_weeks': 'Must be empty for full-time employment type.'}
            )

        bounds = [self.stipend_min, self.stipend_max]
        if any(bound is not None for bound in bounds) and any(bound is None for bound in bounds):
            raise ValidationError(
                'Both stipend_min and stipend_max are required when stipend is provided.'
            )
        if (
            self.stipend_min is not None
            and self.stipend_max is not None
            and self.stipend_min > self.stipend_max
        ):
            raise ValidationError({'stipend_min': 'stipend_min must be <= stipend_max.'})


class MatchingRun(models.Model):
    STATUS_PENDING = 'PENDING'
    STATUS_FILTERING = 'FILTERING'
    STATUS_AGENT_RUNNING = 'AGENT_RUNNING'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_FAILED = 'FAILED'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_FILTERING, 'Filtering'),
        (STATUS_AGENT_RUNNING, 'Agent Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='matching_runs',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    preferences_snapshot = models.JSONField()
    candidate_profile_snapshot = models.JSONField(blank=True, null=True)
    filtered_jobs_count = models.IntegerField(default=0)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    timing_metrics = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status']),
        ]


class MatchingResult(models.Model):
    run = models.ForeignKey(MatchingRun, on_delete=models.CASCADE, related_name='results')
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='matching_results')
    rank = models.PositiveSmallIntegerField()
    selection_probability = models.DecimalField(max_digits=5, decimal_places=4)
    fit_score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    job_quality_score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    why = models.TextField()
    agent_trace = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['rank']
        constraints = [
            models.UniqueConstraint(fields=['run', 'rank'], name='unique_rank_per_run'),
            models.UniqueConstraint(fields=['run', 'job'], name='unique_job_per_run'),
        ]


class PreferenceChangeLog(models.Model):
    ACTION_CREATED = 'CREATED'
    ACTION_UPDATED = 'UPDATED'
    ACTION_DELETED = 'DELETED'

    ACTION_CHOICES = [
        (ACTION_CREATED, 'Created'),
        (ACTION_UPDATED, 'Updated'),
        (ACTION_DELETED, 'Deleted'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='preference_change_logs',
    )
    preference = models.ForeignKey(
        JobPreference,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='change_logs',
    )
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    preference_name = models.CharField(max_length=100, blank=True)
    snapshot_before = models.JSONField(default=dict, blank=True)
    snapshot_after = models.JSONField(default=dict, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]


class JobAlert(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='job_alerts',
    )
    preference = models.ForeignKey(
        JobPreference,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alerts',
    )
    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name='alerts',
    )
    preference_name = models.CharField(max_length=100, blank=True)
    match_score = models.DecimalField(max_digits=5, decimal_places=4)
    match_reasons = models.JSONField(default=list, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'preference', 'job'],
                name='unique_alert_per_user_pref_job',
            ),
        ]
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['is_read']),
        ]


class Task(models.Model):
    role = models.CharField(max_length=255)
    job_description = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.role


class Candidate(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="candidates"
    )

    name = models.CharField(max_length=255)

    resume_data = models.JSONField()   # parsed resume sections

    gpt_score = models.IntegerField(null=True, blank=True)
    gpt_verdict = models.CharField(max_length=100, null=True, blank=True)
    gpt_reason = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.task.role})"


class CompanyTaskJob(models.Model):
    id = models.IntegerField(primary_key=True, editable=False)
    job_description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'Job {self.id}'

    def save(self, *args, **kwargs):
        if self.id is None:
            with transaction.atomic():
                last_job = CompanyTaskJob.objects.select_for_update().order_by('-id').first()
                self.id = 100 if last_job is None else last_job.id + 1
        return super().save(*args, **kwargs)


class JobCandidate(models.Model):
    job = models.ForeignKey(
        CompanyTaskJob,
        on_delete=models.CASCADE,
        related_name='job_candidates',
    )
    name = models.CharField(max_length=255)
    email = models.EmailField()
    resume_data = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['job', 'created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['job', 'email'],
                name='unique_candidate_email_per_company_task_job',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.email})'


class RecruiterJobPreference(models.Model):
    CODING_OPERATORS = {'gte', 'lte', 'eq'}

    job = models.OneToOneField(
        CompanyTaskJob,
        on_delete=models.CASCADE,
        related_name='recruiter_preference',
    )
    college_tiers = models.JSONField(default=list)
    min_experience_years = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    max_experience_years = models.DecimalField(max_digits=4, decimal_places=1, default=2)
    coding_platform_criteria = models.JSONField(default=list)
    number_of_openings = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['updated_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(number_of_openings__gte=1),
                name='recruiter_pref_openings_gte_1',
            ),
            models.CheckConstraint(
                condition=Q(min_experience_years__lte=models.F('max_experience_years')),
                name='recruiter_pref_min_exp_lte_max_exp',
            ),
        ]

    def clean(self):
        allowed_tiers = {item[0] for item in RECRUITER_COLLEGE_TIERS}
        if not isinstance(self.college_tiers, list) or not self.college_tiers:
            raise ValidationError({'college_tiers': 'Must be a non-empty list.'})

        normalized_tiers = []
        for tier in self.college_tiers:
            if not isinstance(tier, str):
                raise ValidationError({'college_tiers': 'Each tier must be a string.'})
            normalized = tier.strip().upper()
            if normalized not in allowed_tiers:
                raise ValidationError(
                    {'college_tiers': f'Invalid tier "{tier}". Allowed: {sorted(allowed_tiers)}'}
                )
            normalized_tiers.append(normalized)

        if len(set(normalized_tiers)) != len(normalized_tiers):
            raise ValidationError({'college_tiers': 'Duplicate tiers are not allowed.'})
        self.college_tiers = normalized_tiers

        if self.min_experience_years is None or self.min_experience_years < 0:
            raise ValidationError({'min_experience_years': 'Must be >= 0.'})
        if self.max_experience_years is None or self.max_experience_years < 0:
            raise ValidationError({'max_experience_years': 'Must be >= 0.'})
        if self.min_experience_years > self.max_experience_years:
            raise ValidationError({'max_experience_years': 'Must be >= min_experience_years.'})

        if self.number_of_openings is None or self.number_of_openings < 1:
            raise ValidationError({'number_of_openings': 'Must be at least 1.'})

        if not isinstance(self.coding_platform_criteria, list):
            raise ValidationError({'coding_platform_criteria': 'Must be a list.'})

        for index, rule in enumerate(self.coding_platform_criteria):
            if not isinstance(rule, dict):
                raise ValidationError(
                    {'coding_platform_criteria': f'Rule at index {index} must be an object.'}
                )
            required_fields = {'platform', 'metric', 'operator', 'value'}
            missing = required_fields - set(rule.keys())
            if missing:
                raise ValidationError(
                    {'coding_platform_criteria': f'Rule at index {index} missing: {sorted(missing)}'}
                )

            operator = str(rule.get('operator', '')).strip().lower()
            if operator not in self.CODING_OPERATORS:
                raise ValidationError(
                    {
                        'coding_platform_criteria': (
                            f'Rule at index {index} has invalid operator "{rule.get("operator")}". '
                            f'Allowed: {sorted(self.CODING_OPERATORS)}'
                        )
                    }
                )

            if not isinstance(rule.get('platform'), str) or not rule['platform'].strip():
                raise ValidationError({'coding_platform_criteria': f'Rule at index {index}: platform required.'})
            if not isinstance(rule.get('metric'), str) or not rule['metric'].strip():
                raise ValidationError({'coding_platform_criteria': f'Rule at index {index}: metric required.'})
            if not isinstance(rule.get('value'), (int, float)):
                raise ValidationError({'coding_platform_criteria': f'Rule at index {index}: value must be numeric.'})

    def __str__(self):
        return f'RecruiterPreference(job={self.job_id})'


class CandidateRankingRun(models.Model):
    STATUS_PENDING = 'PENDING'
    STATUS_RUNNING = 'RUNNING'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_FAILED = 'FAILED'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        CompanyTaskJob,
        on_delete=models.CASCADE,
        related_name='ranking_runs',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    total_candidates = models.PositiveIntegerField(default=0)
    processed_candidates = models.PositiveIntegerField(default=0)
    shortlisted_count = models.PositiveIntegerField(default=0)
    batch_size = models.PositiveIntegerField(default=20)
    model_name = models.CharField(max_length=100, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    timing_metrics = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['job', '-created_at']),
            models.Index(fields=['status']),
        ]


class CandidateRankingResult(models.Model):
    run = models.ForeignKey(CandidateRankingRun, on_delete=models.CASCADE, related_name='results')
    candidate = models.ForeignKey(JobCandidate, on_delete=models.CASCADE, related_name='ranking_results')
    rank = models.PositiveIntegerField()
    is_shortlisted = models.BooleanField(default=False)
    passes_hard_filter = models.BooleanField(default=False)
    final_score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    sub_scores = models.JSONField(default=dict, blank=True)
    filter_reasons = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['rank']
        constraints = [
            models.UniqueConstraint(fields=['run', 'rank'], name='unique_candidate_rank_per_run'),
            models.UniqueConstraint(fields=['run', 'candidate'], name='unique_candidate_result_per_run'),
        ]


class AgentTraceEvent(models.Model):
    STATUS_SUCCESS = 'SUCCESS'
    STATUS_FAILED = 'FAILED'
    STATUS_SKIPPED = 'SKIPPED'

    STATUS_CHOICES = [
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_SKIPPED, 'Skipped'),
    ]

    run = models.ForeignKey(CandidateRankingRun, on_delete=models.CASCADE, related_name='trace_events')
    candidate = models.ForeignKey(
        JobCandidate,
        on_delete=models.CASCADE,
        related_name='trace_events',
        null=True,
        blank=True,
    )
    agent_name = models.CharField(max_length=100)
    stage = models.CharField(max_length=100)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    token_usage = models.JSONField(default=dict, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['run', 'stage']),
            models.Index(fields=['candidate', 'stage']),
        ]


class CollegeTierLookupCache(models.Model):
    institution_normalized = models.CharField(max_length=255, unique=True)
    tier = models.CharField(max_length=20, choices=RECRUITER_COLLEGE_TIERS)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    evidence = models.JSONField(default=list, blank=True)
    last_verified_at = models.DateTimeField(auto_now=True)
    source_model = models.CharField(max_length=100, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['tier']),
            models.Index(fields=['last_verified_at']),
        ]
