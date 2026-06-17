from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    UserRegistrationView,
    UserLoginView,
    UserProfileView,
    UserUpdateView,
    UserDeleteView,
    WorkerListView,
    UserListView,
    UserDetailView,
    LogoutView,
)

urlpatterns = [
    # Auth
    path('register/',        UserRegistrationView.as_view(), name='user-registration'),
    path('login/',           UserLoginView.as_view(),        name='user-login'),
    path('logout/',          LogoutView.as_view(),           name='logout'),
    path('token/refresh/',   TokenRefreshView.as_view(),     name='token-refresh'),

    # Profile management
    path('user/profile/',    UserProfileView.as_view(),      name='user-profile'),
    path('user/update/',     UserUpdateView.as_view(),        name='user-update'),
    path('user/delete/',     UserDeleteView.as_view(),        name='user-delete'),

    # User listings
    # /auth/worker/list/  — role='worker' only   (Workers page)
    # /auth/user/list/    — all roles            (Admin/Manager/Officer: full userMap)
    path('worker/list/',     WorkerListView.as_view(),        name='worker-list'),
    path('user/list/',       UserListView.as_view(),          name='user-list'),
    path('user/<int:pk>/',   UserDetailView.as_view(),        name='user-detail'),
]