from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shop.emails import send_email, send_password_reset_email

from .serializers import (
    ChangePasswordSerializer, LoginSerializer, PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer, ProfileUpdateSerializer, SignupSerializer,
    UserSerializer,
)


# authentication_classes = [] -> eski/yaroqsiz token yuborilsa ham
# signup, login va parol tiklash ishlayveradi.
class SignupView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        send_email(
            "Online Shop'ga xush kelibsiz!",
            f"Assalomu alaykum, {user.username}! Ro'yxatdan o'tganingiz bilan tabriklaymiz.",
            [user.email],
        )

        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {"user": UserSerializer(user).data, "token": token.key},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        token, _ = Token.objects.get_or_create(user=user)
        return Response({"user": UserSerializer(user).data, "token": token.key})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"detail": "Tizimdan chiqildi."})


class MeView(APIView):
    """
    GET    /api/auth/me/ - o'z profilim
    PATCH  /api/auth/me/ - first_name, last_name, email, phone o'zgartirish
    DELETE /api/auth/me/ - akkauntni o'chirish (body: {"password": "..."})
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)
        serializer.update(request.user, serializer.validated_data)
        user = User.objects.select_related("profile").get(pk=request.user.pk)
        return Response(UserSerializer(user).data)

    def delete(self, request):
        password = request.data.get("password", "")
        if not request.user.check_password(password):
            raise ValidationError({"password": "Parol noto'g'ri."})
        request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChangePasswordView(APIView):
    """POST /api/auth/change-password/ - eski token o'chadi, yangisi qaytariladi."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)
        return Response({"detail": "Parol o'zgartirildi.", "token": token.key})


class PasswordResetRequestView(APIView):
    """POST /api/auth/password-reset/ {"email": "..."} - emailga tiklash havolasi yuboradi."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        for user in User.objects.filter(email__iexact=email, is_active=True):
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            send_password_reset_email(user, uid, token)

        # Email bor-yo'qligini bildirmaslik uchun javob doim bir xil
        return Response(
            {"detail": "Agar bu email ro'yxatdan o'tgan bo'lsa, tiklash havolasi yuborildi."}
        )


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset/confirm/ {"uid","token","new_password","new_password2"}"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(data["uid"])))
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is None or not default_token_generator.check_token(user, data["token"]):
            raise ValidationError({"detail": "Havola yaroqsiz yoki muddati o'tgan."})

        user.set_password(data["new_password"])
        user.save()
        Token.objects.filter(user=user).delete()
        return Response({"detail": "Parol muvaffaqiyatli tiklandi."})
