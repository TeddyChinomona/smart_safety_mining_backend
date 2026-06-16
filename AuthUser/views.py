from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import authenticate
from .serializers import UserRegistrationSerializer, UserLoginSerializer
from django.contrib.auth import get_user_model
from .permissions import IsAdminRole, IsSafetyOfficerRole, IsManagerRole, IsWorkerRole
from rest_framework_simplejwt.views import (
    TokenObtainPairView, TokenRefreshView
)
from loguru import logger
from rest_framework.permissions import AllowAny


User = get_user_model()

class Authentication(APIView):
    """
    Base class for authentication-related views.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

class UserRegistrationView(Authentication):
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)   
    
class UserLoginView(APIView):
    permission_classes = [AllowAny]
    serializer_class = UserLoginSerializer
    def post(self, request, *args, **kwargs):
        user_data = request.data
        logger.info(user_data)
        user_authentication = authenticate(request=request, username=user_data['username'], password=user_data['password'])
        if user_authentication:
            refresh = RefreshToken.for_user(user_authentication)
            return Response(
                {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response({"error": "Invalid Credentials"},
                status=status.HTTP_401_UNAUTHORIZED
            )
           

class UserProfileView(Authentication):
    def get(self, request):
        user = request.user
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role
        }, status=status.HTTP_200_OK)


class UserUpdateView(Authentication):
    def put(self, request):
        user = request.user
        serializer = UserRegistrationSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserDeleteView(Authentication):
    def delete(self, request):
        user = request.user
        user.delete()
        return Response({"message": "User deleted successfully"}, status=status.HTTP_204_NO_CONTENT)


class WorkerListView(Authentication):
    def get(self, request):
        users = User.objects.filter(role = "worker").values()
        serializer = UserRegistrationSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class UserDetailView(Authentication):
    def get(self, request, pk):
        user = User.objects.get(pk=pk)
        serializer = UserRegistrationSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogoutView(Authentication):
    """
    Blacklists the refresh token to log the user out.
    Expects a 'refresh' token in the request body.
    """
    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)