from django.db import transaction

from rest_framework import status
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.views.generics import SerializerAPIView
from apps.identity.api.public.serializers import (
    AuthTokenResponseSerializer,
    OtpRequestResponseSerializer,
    OtpVerifyRequestSerializer,
    PasswordResetRequestSerializer,
    PasswordResetResponseSerializer,
    PhoneRequestSerializer,
    ProfileUpdateRequestSerializer,
    UserLoginRequestSerializer,
    UserRegisterRequestSerializer,
    UserSerializer,
)
from apps.identity.services import (
    authenticate_user,
    check_reset_code,
    issue_token,
    register_user,
    request_login_otp,
    reset_password,
    revoke_tokens,
    start_password_reset,
    verify_phone,
)

CLIENT_HINT_HEADERS = {"platform": "X-Platform", "app_version": "X-App-Version"}


def request_meta(request) -> dict:
    """Client hints sent with a request, kept for debugging only."""
    hints = {key: request.headers.get(header) for key, header in CLIENT_HINT_HEADERS.items()}
    return {key: value for key, value in hints.items() if value}


class PublicAuthAPIView(SerializerAPIView):
    permission_classes = [AllowAny]


class OtpRequestAPIView(PublicAuthAPIView):
    serializer_class = PhoneRequestSerializer

    def get(self, request):
        phone = self.validated_data(request, from_query=True)["phone"]
        state = request_login_otp(phone, request_meta(request))
        message = (
            "OTP sent."
            if not state["resend_in"]
            else "A code was sent recently. Please wait before requesting another."
        )
        return Response(OtpRequestResponseSerializer({**state, "message": message}).data)


class OtpVerifyAPIView(PublicAuthAPIView):
    serializer_class = OtpVerifyRequestSerializer

    def post(self, request):
        data = self.validated_data(request)
        user, is_new = verify_phone(data["phone"], data["otp"])
        return Response(
            AuthTokenResponseSerializer({"token": issue_token(user), "user": None if is_new else user}).data
        )


class UserRegisterAPIView(SerializerAPIView):
    """Authenticated with the token from OTP verify, which ties this call to whoever received the SMS."""

    permission_classes = [IsAuthenticated]
    serializer_class = UserRegisterRequestSerializer

    def post(self, request):
        data = self.validated_data(request)
        user = register_user(
            user=request.user,
            name=data["name"],
            password=data["password"],
            institution=data.get("institution"),
            educational_session=data.get("educational_session"),
            class_level=data.get("class_level"),
            group=data.get("group"),
        )
        return Response(
            AuthTokenResponseSerializer({"token": issue_token(user), "user": user}).data,
            status=status.HTTP_201_CREATED,
        )


class UserLoginAPIView(PublicAuthAPIView):
    serializer_class = UserLoginRequestSerializer

    def post(self, request):
        data = self.validated_data(request)
        user = authenticate_user(password=data["password"], phone=data["phone"])
        return Response(AuthTokenResponseSerializer({"token": issue_token(user), "user": user}).data)


class PasswordForgotAPIView(PublicAuthAPIView):
    serializer_class = PhoneRequestSerializer

    def post(self, request):
        phone = self.validated_data(request)["phone"]
        wait = start_password_reset(phone, request_meta(request))
        if wait:
            raise Throttled(wait=wait)
        return Response({"message": "OTP sent."})


class PasswordResetCheckAPIView(PublicAuthAPIView):
    serializer_class = OtpVerifyRequestSerializer

    def post(self, request):
        data = self.validated_data(request)
        check_reset_code(data["phone"], data["otp"])
        return Response({"message": "OTP is valid."})


class PasswordResetAPIView(PublicAuthAPIView):
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        data = self.validated_data(request)
        user = reset_password(phone=data["phone"], code=data["otp"], password=data["password"])
        return Response(
            PasswordResetResponseSerializer(
                {"token": issue_token(user, rotate=True), "message": "Password has been reset."}
            ).data
        )


class UserLogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        revoke_tokens(request.user)
        return Response({"ok": True})


class CurrentUserAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"data": UserSerializer(request.user).data})

    def post(self, request):
        serializer = ProfileUpdateRequestSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = serializer.save()
            token = None
            if serializer.validated_data.get("password"):
                # Signs every other session out; the caller carries on with the new token.
                token = issue_token(user, rotate=True)
        body = {"data": UserSerializer(user).data}
        if token:
            body["token"] = token
        return Response(body)
