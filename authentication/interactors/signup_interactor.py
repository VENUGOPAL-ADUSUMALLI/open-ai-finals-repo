from rest_framework import status
from rest_framework.response import Response
from authentication.storage.user_storage import UserStorage
from authentication.interactors.exceptions import (
    UserAlreadyExistsError,
    ValidationError
)
from authentication.presenters.signup_presenter import (
    present_signup_success,
    present_user_already_exists,
    present_validation_error,
    present_error,
)
from authentication.presenters.jwt_presenter import generate_tokens_for_user


class SignupInteractor:


    def __init__(self, user_storage: UserStorage):
        self.user_storage = user_storage

    def signup_interactor(self, email: str, password: str, confirm_password: str, username: str, phone_number: str, age: int, gender: str, address: str, profile_picture: str) -> Response:
        try:

            required_fields = ['email', 'password', 'confirm_password', 'username', 'phone_number', 'age', 'gender', 'address']
            missing_fields = []
            if not email:
                missing_fields.append('email')
            if not password:
                missing_fields.append('password')
            if not confirm_password:
                missing_fields.append('confirm_password')
            if not username:
                missing_fields.append('username')
            if not phone_number:
                missing_fields.append('phone_number')
            if not age:
                missing_fields.append('age')
            if not gender:
                missing_fields.append('gender')
            if not address:
                missing_fields.append('address')

            if missing_fields:
                raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")

            if password != confirm_password:
                raise ValidationError("Password and confirm password do not match")


            try:
                age = int(age)
                if age <= 0:
                    raise ValidationError("Age must be a positive number")
            except (ValueError, TypeError):
                raise ValidationError("Age must be a valid positive integer")


            if self.user_storage.get_user_by_email(email):
                raise UserAlreadyExistsError("User with this email already exists")

            if self.user_storage.get_user_by_username(username):
                raise UserAlreadyExistsError("User with this username already exists")

            if self.user_storage.get_user_by_phone_number(phone_number):
                raise UserAlreadyExistsError("User with this phone number already exists")


            user = self.user_storage.create_user({
                'email': email,
                'password': password,
                'username': username,
                'phone_number': phone_number,
                'age': age,
                'gender': gender,
                'address': address,
                'profile_picture': profile_picture,
            })


            tokens_dict = generate_tokens_for_user(user)
            return Response(present_signup_success(tokens_dict), status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response(present_validation_error(str(e)), status=status.HTTP_400_BAD_REQUEST)
        except UserAlreadyExistsError as e:
            return Response(present_user_already_exists(str(e)), status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                present_error(f"An error occurred: {str(e)}"),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

       
