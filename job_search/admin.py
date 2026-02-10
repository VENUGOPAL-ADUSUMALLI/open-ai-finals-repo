from django.contrib import admin

from .models import (
    AgentTraceEvent,
    CandidateRankingResult,
    CandidateRankingRun,
    CollegeTierLookupCache,
    CompanyTaskJob,
    JobCandidate,
    Job,
    JobPreference,
    MatchingResult,
    MatchingRun,
    RecruiterJobPreference,
)
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


@admin.register(CompanyTaskJob)
class CompanyTaskJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'updated_at')
    search_fields = ('id',)


@admin.register(JobCandidate)
class JobCandidateAdmin(admin.ModelAdmin):
    list_display = ('id', 'job', 'name', 'email', 'created_at')
    search_fields = ('name', 'email', 'job__id')
    list_filter = ('created_at',)


@admin.register(RecruiterJobPreference)
class RecruiterJobPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        'job',
        'number_of_openings',
        'min_experience_years',
        'max_experience_years',
        'updated_at',
    )
    search_fields = ('job__id',)
    list_filter = ('updated_at',)


@admin.register(CandidateRankingRun)
class CandidateRankingRunAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'job',
        'status',
        'total_candidates',
        'processed_candidates',
        'shortlisted_count',
        'created_at',
    )
    search_fields = ('id', 'job__id')
    list_filter = ('status', 'created_at')


@admin.register(CandidateRankingResult)
class CandidateRankingResultAdmin(admin.ModelAdmin):
    list_display = ('run', 'rank', 'candidate', 'final_score', 'is_shortlisted')
    search_fields = ('run__id', 'candidate__email', 'candidate__name')
    list_filter = ('is_shortlisted', 'passes_hard_filter')


@admin.register(AgentTraceEvent)
class AgentTraceEventAdmin(admin.ModelAdmin):
    list_display = ('run', 'candidate', 'agent_name', 'stage', 'status', 'latency_ms', 'created_at')
    search_fields = ('run__id', 'candidate__email', 'agent_name', 'stage')
    list_filter = ('status', 'stage')


@admin.register(CollegeTierLookupCache)
class CollegeTierLookupCacheAdmin(admin.ModelAdmin):
    list_display = ('institution_normalized', 'tier', 'confidence', 'last_verified_at')
    search_fields = ('institution_normalized',)
    list_filter = ('tier',)
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
