from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from authentication.storage.user_storage import UserStorage
from authentication.interactors.signup_interactor import SignupInteractor
from authentication.interactors.signin_interactor import SigninInteractor
from authentication.interactors.profile_interactor import ProfileInteractor
from authentication.interactors.google_auth_interactor import GoogleAuthInteractor
from authentication.interactors.resume_parser_interactor import ResumeParserInteractor
from authentication.presenters.resume_parser_presenter import ResumeParserPresenter


@api_view(['POST'])
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
def google_auth_view(request):
    id_token = request.data.get('id_token')
    user_storage = UserStorage()
    response = GoogleAuthInteractor(user_storage).authenticate_with_google(id_token)
    return response


@api_view(['POST'])
@authentication_classes([JWTAuthentication, SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def parse_resume_v1_view(request):
    resume_file = request.FILES.get('resume_file')
    if not resume_file:
        return ResumeParserPresenter().invalid_request_response("resume_file is required.")

    user_storage = UserStorage()
    presenter = ResumeParserPresenter()
    interactor = ResumeParserInteractor(storage=user_storage, presenter=presenter)
    return interactor.parse_resume_full_interactor(
        user=request.user,
        file_content=resume_file.read(),
        filename=resume_file.name,
    )
