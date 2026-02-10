from django.urls import path

from .views import (
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
