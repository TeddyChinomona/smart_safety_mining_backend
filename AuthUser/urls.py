from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *
from rest_framework_simplejwt.views import TokenRefreshView


urlpatterns = [
    path('register/', UserRegistrationView.as_view(), name='user-registration'),
    path('login/', UserLoginView.as_view(), name='user-login'),
    path('user/profile/', UserProfileView.as_view(), name='user-profile'),
    path('user/update/', UserUpdateView.as_view(), name='user-update'),
    path('user/delete/', UserDeleteView.as_view(), name='user-delete'),
    path('worker/list/', WorkerListView.as_view(), name='user-list'),
    path('user/<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', LogoutView.as_view(), name='logout')
]