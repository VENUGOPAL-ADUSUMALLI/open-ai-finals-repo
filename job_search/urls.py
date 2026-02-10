from django.urls import path

from .views import (
    candidate_ranking_run_create_view,
    candidate_ranking_run_detail_view,
    candidate_ranking_run_list_view,
    company_task_job_create_view,
    company_task_job_import_candidates_view,
    company_task_job_preference_upsert_view,
    job_recommendation_view,
    match_jobs_by_preference_view,
    matching_run_create_view,
    matching_run_detail_view,
    matching_run_list_view,
)

urlpatterns = [
    path('preferences/match-jobs/', match_jobs_by_preference_view, name='match-jobs-by-preference'),
    path('jobs/recommend/', job_recommendation_view, name='job-recommendations'),
    path('company-task-jobs/', company_task_job_create_view, name='company-task-job-create'),
    path(
        'company-task-jobs/import-candidates/',
        company_task_job_import_candidates_view,
        name='company-task-job-import-candidates',
    ),
    path(
        'company-task-jobs/preferences/',
        company_task_job_preference_upsert_view,
        name='company-task-job-preference-upsert',
    ),
    path(
        'company-task-jobs/ranking-runs/',
        candidate_ranking_run_create_view,
        name='candidate-ranking-run-create',
    ),
    path(
        'company-task-jobs/ranking-runs/<uuid:run_id>/',
        candidate_ranking_run_detail_view,
        name='candidate-ranking-run-detail',
    ),
    path(
        'company-task-jobs/<int:job_id>/ranking-runs/',
        candidate_ranking_run_list_view,
        name='candidate-ranking-run-list',
    ),
    path('matching/runs/', matching_run_create_view, name='matching-run-create'),
    path('matching/runs/list/', matching_run_list_view, name='matching-run-list'),
    path('matching/runs/<uuid:run_id>/', matching_run_detail_view, name='matching-run-detail'),
    alerts_mark_read_view,
    alerts_view,
    matches_run_detail_view,
    matches_runs_view,
    preference_detail_view,
    preference_history_view,
    preferences_view,
    skill_gap_view,
)

urlpatterns = [
    alerts_mark_read_view,
    alerts_view,
    matches_run_detail_view,
    matches_runs_view,
    preference_detail_view,
    preference_history_view,
    preferences_view,
    skill_gap_view,
)

urlpatterns = [
    path('preferences/', preferences_view, name='preferences'),
    path('preferences/history/', preference_history_view, name='preference-history'),
    path('preferences/<int:preference_id>/', preference_detail_view, name='preference-detail'),
    path('matches/runs/', matches_runs_view, name='matches-runs'),
    path('matches/runs/<uuid:run_id>/', matches_run_detail_view, name='matches-run-detail'),
    path('matches/runs/<uuid:run_id>/skill-gaps/', skill_gap_view, name='skill-gaps'),
    path('alerts/', alerts_view, name='alerts'),
    path('alerts/mark-read/', alerts_mark_read_view, name='alerts-mark-read'),
]
