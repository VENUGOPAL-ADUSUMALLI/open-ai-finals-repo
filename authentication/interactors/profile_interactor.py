from rest_framework import status
from rest_framework.response import Response
from authentication.presenters.profile_presenter import present_profile_success


class ProfileInteractor:


    def __init__(self):
        self.profile_interactor = self

    def profile_interactor(self, user) -> Response:
        return Response(present_profile_success(user), status=status.HTTP_200_OK)
