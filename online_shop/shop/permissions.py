from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdminOrReadOnly(BasePermission):
    """O'qish hamma uchun, yozish faqat admin (is_staff) uchun."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


class IsOwnerOrAdmin(BasePermission):
    """Obyektni faqat egasi yoki admin o'zgartira oladi."""

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user.is_staff or obj.user_id == request.user.id)
