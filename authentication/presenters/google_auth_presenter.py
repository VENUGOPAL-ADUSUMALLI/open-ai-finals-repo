def present_google_auth_success(tokens_dict: dict, user) -> dict:
    """Response for successful Google authentication of existing user."""
    return {
        'success': True,
        'message': 'Successfully authenticated with Google',
        'is_new_user': False,
        'is_profile_complete': user.is_profile_complete,
        'access': tokens_dict['access'],
        'refresh': tokens_dict['refresh'],
        'user': {
            'id': user.id,
            'email': user.email,
            'username': user.username,
        }
    }


def present_google_auth_new_user(tokens_dict: dict, user) -> dict:
    """Response for new user created via Google authentication."""
    return {
        'success': True,
        'message': 'Account created successfully with Google',
        'is_new_user': True,
        'is_profile_complete': False,
        'access': tokens_dict['access'],
        'refresh': tokens_dict['refresh'],
        'user': {
            'id': user.id,
            'email': user.email,
            'username': user.username,
        }
    }


def present_google_token_error(message: str) -> dict:
    """Response for invalid Google token."""
    return {
        'success': False,
        'message': message,
        'error': 'GOOGLE_TOKEN_INVALID',
    }


def present_validation_error(message: str) -> dict:
    """Response for validation errors."""
    return {
        'success': False,
        'message': message,
        'error': 'VALIDATION_ERROR',
    }


def present_error(message: str, error_code: str = 'ERROR') -> dict:
    """Generic error response."""
    return {
        'success': False,
        'message': message,
        'error': error_code,
    }
