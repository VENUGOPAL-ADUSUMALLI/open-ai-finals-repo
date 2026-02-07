from rest_framework import status
from rest_framework.response import Response
from authentication.storage.user_storage import UserStorage
from authentication.interactors.exceptions import (
    InvalidCredentialsError,
    ValidationError
)
from authentication.presenters.signin_presenter import (
    present_signin_success,
    present_invalid_credentials,
    present_validation_error,
    present_error,
)
from authentication.presenters.jwt_presenter import generate_tokens_for_user


class SigninInteractor:


    def __init__(self, user_storage: UserStorage):
        self.user_storage = user_storage

    def signin_interactor(self, email: str, password: str) -> Response:

        try:
            if not email or not password:
                raise ValidationError("Email and password are required")

            user = self.user_storage.check_credentials(email, password)

            if not user:
                raise InvalidCredentialsError("Invalid email or password")

            tokens_dict = generate_tokens_for_user(user)
            return Response(present_signin_success(tokens_dict), status=status.HTTP_200_OK)

        except ValidationError as e:
            return Response(present_validation_error(str(e)), status=status.HTTP_400_BAD_REQUEST)
        except InvalidCredentialsError:
            return Response(present_invalid_credentials(), status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response(
                present_error(f"An error occurred: {str(e)}"),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
