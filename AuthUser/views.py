from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import authenticate
from .serializers import UserRegistrationSerializer, UserLoginSerializer
from django.contrib.auth import get_user_model
from .permissions import IsAdminRole, IsSafetyOfficerRole, IsManagerRole
from loguru import logger


User = get_user_model()


class Authentication(APIView):
    """Base class for authenticated views."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]


# ── Registration & Login ───────────────────────────────────────────────────────

class UserRegistrationView(Authentication):
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response(
                {'refresh': str(refresh), 'access': str(refresh.access_token)},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLoginView(APIView):
    permission_classes = [AllowAny]
    serializer_class   = UserLoginSerializer

    def post(self, request, *args, **kwargs):
        logger.info(request.data)
        user = authenticate(
            request=request,
            username=request.data.get('username'),
            password=request.data.get('password'),
        )
        if user:
            refresh = RefreshToken.for_user(user)
            return Response(
                {'refresh': str(refresh), 'access': str(refresh.access_token)},
                status=status.HTTP_200_OK,
            )
        return Response({'error': 'Invalid Credentials'}, status=status.HTTP_401_UNAUTHORIZED)


# ── Profile / Update / Delete ──────────────────────────────────────────────────

class UserProfileView(Authentication):
    def get(self, request):
        u = request.user
        return Response(
            {'id': u.id, 'username': u.username, 'email': u.email, 'role': u.role},
            status=status.HTTP_200_OK,
        )


class UserUpdateView(Authentication):
    def put(self, request):
        serializer = UserRegistrationSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserDeleteView(Authentication):
    def delete(self, request):
        request.user.delete()
        return Response({'message': 'User deleted successfully'}, status=status.HTTP_204_NO_CONTENT)


# ── User Listing ───────────────────────────────────────────────────────────────

class WorkerListView(Authentication):
    """Returns only users with role='worker' — used to populate the Workers page."""
    def get(self, request):
        workers = User.objects.filter(role='worker')
        serializer = UserRegistrationSerializer(workers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserListView(Authentication):
    """
    Returns ALL system users (any role).
    Restricted to Admin, Manager, and Safety Officer so that the frontend can
    build a complete userMap for alert / incident attribution.
    Workers who log in will receive 403 and the frontend falls back to the
    workers-only list gracefully.
    """
    def get_permissions(self):
        return [IsAdminRole() | IsManagerRole() | IsSafetyOfficerRole()]

    def get(self, request):
        users = User.objects.all()
        serializer = UserRegistrationSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserDetailView(Authentication):
    def get(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = UserRegistrationSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ── Logout ─────────────────────────────────────────────────────────────────────

class LogoutView(Authentication):
    """Blacklists the refresh token to invalidate the session."""
    def post(self, request):
        try:
            token = RefreshToken(request.data['refresh'])
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)