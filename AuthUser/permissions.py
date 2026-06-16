from rest_framework import permissions

class IsAdminRole(permissions.BasePermission):
    """Allows access only to admin users."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and getattr(request.user, 'role', '') == 'admin')

class IsSafetyOfficerRole(permissions.BasePermission):
    """Allows access only to safety officers."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and getattr(request.user, 'role', '') == 'safety_officer')

class IsManagerRole(permissions.BasePermission):
    """Allows access only to managers."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and getattr(request.user, 'role', '') == 'manager')

class IsWorkerRole(permissions.BasePermission):
    """Allows access only to workers."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and getattr(request.user, 'role', '') == 'worker')