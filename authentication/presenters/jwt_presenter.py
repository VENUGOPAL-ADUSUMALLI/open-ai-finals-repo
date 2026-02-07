from rest_framework_simplejwt.tokens import RefreshToken
from authentication.models import User


def generate_tokens_for_user(user: User) -> dict:

    refresh = RefreshToken.for_user(user)


    refresh['email'] = user.email
    refresh['username'] = user.username


    access_token = refresh.access_token
    access_token['email'] = user.email
    access_token['username'] = user.username

    return {
        'access': str(access_token),
        'refresh': str(refresh),
    }
