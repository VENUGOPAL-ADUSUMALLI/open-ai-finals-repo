def present_signup_success(tokens_dict: dict) -> dict:

    return {
        'success': True,
        'message': 'User created successfully',
        'access': tokens_dict['access'],
        'refresh': tokens_dict['refresh'],
    }


def present_user_already_exists(message: str) -> dict:
    
    return {
        'success': False,
        'message': message,
        'error': 'USER_ALREADY_EXISTS',
    }


def present_validation_error(message: str) -> dict:

    return {
        'success': False,
        'message': message,
        'error': 'VALIDATION_ERROR',
    }


def present_error(message: str, error_code: str = 'ERROR') -> dict:

    return {
        'success': False,
        'message': message,
        'error': error_code,
    }
