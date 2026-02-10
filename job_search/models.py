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


from django.db import models


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
