import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
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
    work_mode = models.CharField(max_length=20, choices=WORK_MODE_CHOICES)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES)
    internship_duration_weeks = models.PositiveSmallIntegerField(blank=True, null=True)
    location = models.CharField(max_length=200, db_index=True)
    company_size_preference = models.CharField(max_length=20, choices=COMPANY_SIZE_CHOICES)
    stipend_min = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stipend_max = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stipend_currency = models.CharField(max_length=3, default='INR')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=Q(is_active=True),
                name='unique_active_job_pref_per_user',
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
