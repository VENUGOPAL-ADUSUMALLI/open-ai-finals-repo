from rest_framework import status
from rest_framework.response import Response
from authentication.storage.user_storage import UserStorage
from authentication.services.google_auth_service import GoogleAuthService, GoogleAuthError
from authentication.interactors.exceptions import (
    ValidationError,
    GoogleAccountLinkError,
)
from authentication.presenters.google_auth_presenter import (
    present_google_auth_success,
    present_google_auth_new_user,
    present_google_token_error,
    present_validation_error,
    present_error,
)
from authentication.presenters.jwt_presenter import generate_tokens_for_user


class GoogleAuthInteractor:

    def __init__(self, user_storage: UserStorage, google_auth_service: GoogleAuthService = None):
        self.user_storage = user_storage
        self.google_auth_service = google_auth_service or GoogleAuthService()

    def authenticate_with_google(self, id_token: str) -> Response:
        try:
            if not id_token:
                raise ValidationError("Google ID token is required")

            try:
                google_user_info = self.google_auth_service.verify_id_token(id_token)
            except GoogleAuthError as e:
                return Response(
                    present_google_token_error(str(e)),
                    status=status.HTTP_401_UNAUTHORIZED
                )

            google_id = google_user_info['google_id']
            email = google_user_info['email']

            user = self.user_storage.get_user_by_google_id(google_id)
            is_new_user = False

            if user:
                pass
            else:
                user = self.user_storage.get_user_by_email(email)

                if user:
                    if user.google_id and user.google_id != google_id:
                        raise GoogleAccountLinkError(
                            "This email is already linked to a different Google account"
                        )
                    user = self.user_storage.link_google_account(user, google_id)
                else:
                    user = self.user_storage.create_google_user(google_user_info)
                    is_new_user = True

            tokens_dict = generate_tokens_for_user(user)

            if is_new_user:
                return Response(
                    present_google_auth_new_user(tokens_dict, user),
                    status=status.HTTP_201_CREATED
                )
            else:
                return Response(
                    present_google_auth_success(tokens_dict, user),
                    status=status.HTTP_200_OK
                )

        except ValidationError as e:
            return Response(
                present_validation_error(str(e)),
                status=status.HTTP_400_BAD_REQUEST
            )
        except GoogleAccountLinkError as e:
            return Response(
                present_error(str(e), 'ACCOUNT_LINK_ERROR'),
                status=status.HTTP_409_CONFLICT
            )
        except Exception as e:
            return Response(
                present_error(f"An error occurred: {str(e)}"),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
