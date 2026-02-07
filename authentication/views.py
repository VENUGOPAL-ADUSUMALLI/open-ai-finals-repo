from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from authentication.storage.user_storage import UserStorage
from authentication.interactors.signup_interactor import SignupInteractor
from authentication.interactors.signin_interactor import SigninInteractor
from authentication.interactors.profile_interactor import ProfileInteractor
from authentication.interactors.google_auth_interactor import GoogleAuthInteractor


@api_view(['POST'])
def signup_view(request):
    email = request.data.get('email')
    password = request.data.get('password')
    confirm_password = request.data.get('confirm_password')
    username = request.data.get('username')
    phone_number = request.data.get('phone_number')
    age = request.data.get('age')
    gender = request.data.get('gender')
    address = request.data.get('address')
    profile_picture = request.data.get('profile_picture')
    user_storage = UserStorage()
    response = SignupInteractor(user_storage).signup_interactor(email=email, password=password, confirm_password=confirm_password, username=username, phone_number=phone_number, age=age, gender=gender, address=address, profile_picture=profile_picture)
    return response


@api_view(['POST'])
def signin_view(request):
    data = request.data
    email = data.get('email') 
    password = data.get('password') 
    user_storage = UserStorage()
    response = SigninInteractor(user_storage).signin_interactor(email, password)
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile_view(request):
    user = request.user
    response = ProfileInteractor().profile_interactor.profile_interactor(user)
    return response


@api_view(['POST'])
def google_auth_view(request):
    id_token = request.data.get('id_token')
    user_storage = UserStorage()
    response = GoogleAuthInteractor(user_storage).authenticate_with_google(id_token)
    return response
