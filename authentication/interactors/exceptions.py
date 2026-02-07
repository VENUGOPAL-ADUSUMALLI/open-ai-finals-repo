


class AuthenticationError(Exception):

    pass


class InvalidCredentialsError(AuthenticationError):

    pass


class UserAlreadyExistsError(AuthenticationError):

    pass


class ValidationError(AuthenticationError):

    pass


class GoogleAuthError(AuthenticationError):
    """Raised when Google token verification fails."""
    pass


class GoogleAccountLinkError(AuthenticationError):
    """Raised when there's an issue linking Google account to existing user."""
    pass
