from django.contrib import admin

from .models import Job, JobAlert, JobPreference, MatchingResult, MatchingRun, PreferenceChangeLog


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('job_id', 'title', 'company_name', 'employment_type', 'work_mode')
    search_fields = ('job_id', 'title', 'company_name', 'location')
    list_filter = ('employment_type', 'work_mode', 'company_size')


@admin.register(JobPreference)
class JobPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'name',
        'employment_type',
        'work_mode',
        'company_size_preference',
        'experience_level',
        'location',
        'is_active',
    )
    search_fields = ('user__username', 'location', 'name')
    list_filter = ('employment_type', 'work_mode', 'company_size_preference', 'is_active', 'experience_level')


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


@admin.register(PreferenceChangeLog)
class PreferenceChangeLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'preference_name', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('user__username', 'preference_name')


@admin.register(JobAlert)
class JobAlertAdmin(admin.ModelAdmin):
    list_display = ('user', 'job', 'preference_name', 'match_score', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('user__username', 'job__title', 'preference_name')
