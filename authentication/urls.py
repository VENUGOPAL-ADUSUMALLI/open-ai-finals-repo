from django.urls import path
from authentication.views import (
    google_auth_view,
    parse_resume_v1_view,
    profile_view,
    signin_view,
    signup_view,
)

app_name = 'authentication'

urlpatterns = [
    path('signup/', signup_view, name='signup'),
    path('signin/', signin_view, name='signin'),
    path('profile/', profile_view, name='profile'),
    path('google/', google_auth_view, name='google_auth'),
    path('resume/parse/v1/', parse_resume_v1_view, name='parse_resume_v1'),
]
