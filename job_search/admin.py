from django.contrib import admin

from .models import Job, JobPreference, MatchingResult, MatchingRun


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('job_id', 'title', 'company_name', 'employment_type', 'work_mode')
    search_fields = ('job_id', 'title', 'company_name', 'location')
    list_filter = ('employment_type', 'work_mode', 'company_size')


@admin.register(JobPreference)
class JobPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'employment_type',
        'work_mode',
        'company_size_preference',
        'location',
        'is_active',
    )
    search_fields = ('user__username', 'location')
    list_filter = ('employment_type', 'work_mode', 'company_size_preference', 'is_active')


@admin.register(MatchingRun)
class MatchingRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'filtered_jobs_count', 'created_at', 'completed_at')
    list_filter = ('status', 'created_at')
    search_fields = ('id', 'user__username')


@admin.register(MatchingResult)
class MatchingResultAdmin(admin.ModelAdmin):
    list_display = ('run', 'rank', 'job', 'selection_probability')
    list_filter = ('rank',)
    search_fields = ('run__id', 'job__job_id', 'job__title')
