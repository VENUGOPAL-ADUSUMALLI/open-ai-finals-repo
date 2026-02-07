from django.db import models


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
