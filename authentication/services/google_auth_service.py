from typing import Optional, Dict, Any
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from django.conf import settings


class GoogleAuthError(Exception):
    pass


class GoogleAuthService:

    def __init__(self):
        self.client_id = getattr(settings, 'GOOGLE_OAUTH2_CLIENT_ID', None)

    def verify_id_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not self.client_id:
            raise GoogleAuthError("Google OAuth client ID not configured")

        try:
            idinfo = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                self.client_id
            )

            if idinfo.get('iss') not in ['accounts.google.com', 'https://accounts.google.com']:
                raise GoogleAuthError("Invalid issuer in token")

            if not idinfo.get('email_verified', False):
                raise GoogleAuthError("Email not verified by Google")

            return {
                'google_id': idinfo['sub'],
                'email': idinfo['email'],
                'email_verified': idinfo.get('email_verified', False),
                'name': idinfo.get('name', ''),
                'given_name': idinfo.get('given_name', ''),
                'family_name': idinfo.get('family_name', ''),
                'picture': idinfo.get('picture', ''),
            }

        except ValueError as e:
            raise GoogleAuthError(f"Token verification failed: {str(e)}")
