from typing import Optional
from django.contrib.auth.hashers import make_password, check_password
from authentication.models import User


class UserStorage:


    def create_user(self, data: dict) -> User:

        user = User(
            email=data['email'],
            username=data['username'],
            phone_number=data['phone_number'],
            age=data['age'],
            gender=data['gender'],
            address=data['address'],
        )


        user.password = make_password(data['password'])


        if 'profile_picture' in data and data['profile_picture']:
            user.profile_picture = data['profile_picture']

        user.save()
        return user

    def get_user_by_email(self, email: str) -> Optional[User]:

        try:
            return User.objects.get(email=email)
        except User.DoesNotExist:
            return None

    def get_user_by_username(self, username: str) -> Optional[User]:

        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            return None

    def get_user_by_phone_number(self, phone_number: str) -> Optional[User]:

        try:
            return User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return None

    def check_credentials(self, email: str, raw_password: str) -> Optional[User]:

        user = self.get_user_by_email(email)
        if user and check_password(raw_password, user.password):
            return user
        return None

    def get_user_by_google_id(self, google_id: str) -> Optional[User]:
        """Get a user by their Google ID."""
        try:
            return User.objects.get(google_id=google_id)
        except User.DoesNotExist:
            return None

    def create_google_user(self, data: dict) -> User:
        """Create a new user from Google OAuth data."""
        base_username = data.get('email', '').split('@')[0]
        username = self._generate_unique_username(base_username)

        user = User(
            email=data['email'],
            username=username,
            google_id=data['google_id'],
            auth_provider='google',
            is_profile_complete=False,
            first_name=data.get('given_name', ''),
            last_name=data.get('family_name', ''),
        )
        user.set_unusable_password()
        user.save()
        return user

    def link_google_account(self, user: User, google_id: str) -> User:
        """Link a Google account to an existing user."""
        user.google_id = google_id
        if user.auth_provider == 'email':
            user.auth_provider = 'email,google'
        user.save()
        return user

    def _generate_unique_username(self, base_username: str) -> str:
        """Generate a unique username by appending numbers if necessary."""
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        return username
