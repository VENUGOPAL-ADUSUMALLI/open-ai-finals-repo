from django.urls import path

from .views import (
    MatchingRunCreateView,
    MatchingRunDetailView,
    MatchingRunListView,
    MatchJobsByPreferenceView,
)

urlpatterns = [
    path('preferences/match-jobs/', MatchJobsByPreferenceView.as_view(), name='match-jobs-by-preference'),
    path('matching/runs/', MatchingRunCreateView.as_view(), name='matching-run-create'),
    path('matching/runs/list/', MatchingRunListView.as_view(), name='matching-run-list'),
    path('matching/runs/<uuid:run_id>/', MatchingRunDetailView.as_view(), name='matching-run-detail'),
]
