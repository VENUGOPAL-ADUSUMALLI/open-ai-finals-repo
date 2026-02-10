from typing import Optional
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
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

    def save_resume_metadata(self, user: User, resume_metadata: dict) -> User:
        user.resume_metadata = resume_metadata
        user.resume_last_parsed_at = timezone.now()
        user.save(update_fields=["resume_metadata", "resume_last_parsed_at", "updated_at"])
        return user

    def seed_user_profile_from_personal_info(self, user: User, personal_info) -> User:
        updated_fields = []

        full_name = getattr(personal_info, "full_name", None)
        if full_name and not (user.first_name or user.last_name):
            parts = [part for part in full_name.strip().split(" ") if part]
            if parts:
                user.first_name = parts[0]
                updated_fields.append("first_name")
                if len(parts) > 1:
                    user.last_name = " ".join(parts[1:])
                    updated_fields.append("last_name")

        phone = getattr(personal_info, "phone", None)
        if phone and not user.phone_number:
            user.phone_number = phone.strip()
            updated_fields.append("phone_number")

        address = getattr(personal_info, "address", None)
        if address and not user.address:
            user.address = address.strip()
            updated_fields.append("address")
            if not user.location:
                city_guess = address.split(",")[0].strip()
                if len(city_guess) > 2:
                    user.location = city_guess
                    updated_fields.append("location")

        if updated_fields:
            user.save(update_fields=list(set(updated_fields + ["updated_at"])))
        return user
