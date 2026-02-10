from django.urls import path

from .views import (
    job_recommendation_view,
    match_jobs_by_preference_view,
    matching_run_create_view,
    matching_run_detail_view,
    matching_run_list_view,
)

urlpatterns = [
    path('preferences/match-jobs/', match_jobs_by_preference_view, name='match-jobs-by-preference'),
    path('jobs/recommend/', job_recommendation_view, name='job-recommendations'),
    path('matching/runs/', matching_run_create_view, name='matching-run-create'),
    path('matching/runs/list/', matching_run_list_view, name='matching-run-list'),
    path('matching/runs/<uuid:run_id>/', matching_run_detail_view, name='matching-run-detail'),
]
