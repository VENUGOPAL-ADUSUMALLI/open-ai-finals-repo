def present_signin_success(tokens_dict: dict) -> dict:

    return {
        'access': tokens_dict['access'],
        'refresh': tokens_dict['refresh'],
    }


def present_invalid_credentials() -> dict:

    return {
        'success': False,
        'message': 'Invalid email or password',
        'error': 'INVALID_CREDENTIALS',
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
