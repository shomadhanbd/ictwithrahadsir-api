from django.db import transaction

from rest_framework import status
from rest_framework.exceptions import Throttled
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.views.generics import SerializerAPIView
from apps.identity.api.public.serializers import (
    AccountStateResponseSerializer,
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
from apps.identity.selectors import account_state
from apps.identity.services import (
    authenticate_user,
    issue_token,
    register_user,
    request_login_otp,
    reset_password,
    revoke_tokens,
    start_password_reset,
    verify_phone,
)

CLIENT_HINT_HEADERS = {"platform": "X-Platform", "app_version": "X-App-Version"}


class PublicAuthAPIView(SerializerAPIView):
    permission_classes = [AllowAny]


class AccountLookupAPIView(PublicAuthAPIView):
    """Which sign-in step a phone needs, without sending a code: a password, or an OTP."""

    serializer_class = PhoneRequestSerializer

    def get(self, request):
        phone = self.validated_data(request, from_query=True)["phone"]
        return Response(AccountStateResponseSerializer(account_state(phone)).data)


# Sign up and sign in with OTP: request a code, verify it, then register if the account is new


class OtpRequestAPIView(PublicAuthAPIView):
    serializer_class = PhoneRequestSerializer

    def get(self, request):
        phone = self.validated_data(request, from_query=True)["phone"]
        state = request_login_otp(phone, _client_hints(request))

        if state["resend_in"]:
            message = "A code was sent recently. Please wait before requesting another."
        else:
            message = "OTP sent."
        return Response(OtpRequestResponseSerializer({**state, "message": message}).data)


class OtpVerifyAPIView(PublicAuthAPIView):
    serializer_class = OtpVerifyRequestSerializer

    def post(self, request):
        data = self.validated_data(request)
        user, is_new = verify_phone(data["phone"], data["otp"])

        token = issue_token(user)
        # A new account has nothing to show yet; the app sends it on to register.
        body = {"token": token, "user": None if is_new else user}
        return Response(AuthTokenResponseSerializer(body).data)


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

        body = {"token": issue_token(user), "user": user}
        return Response(AuthTokenResponseSerializer(body).data, status=status.HTTP_201_CREATED)


# Sign in with a password, and sign out


class UserLoginAPIView(PublicAuthAPIView):
    serializer_class = UserLoginRequestSerializer

    def post(self, request):
        data = self.validated_data(request)
        user = authenticate_user(phone=data["phone"], password=data["password"])

        body = {"token": issue_token(user), "user": user}
        return Response(AuthTokenResponseSerializer(body).data)


class UserLogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        revoke_tokens(request.user)
        return Response({"ok": True})


# Forgot password: request a reset code, then send it with the new password


class PasswordForgotAPIView(PublicAuthAPIView):
    serializer_class = PhoneRequestSerializer

    def post(self, request):
        phone = self.validated_data(request)["phone"]
        wait = start_password_reset(phone, _client_hints(request))
        if wait:
            raise Throttled(wait=wait)
        return Response({"message": "OTP sent."})


class PasswordResetAPIView(PublicAuthAPIView):
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        data = self.validated_data(request)
        user = reset_password(phone=data["phone"], code=data["otp"], password=data["password"])

        body = {"token": issue_token(user, rotate=True), "message": "Password has been reset."}
        return Response(PasswordResetResponseSerializer(body).data)


# The signed-in user's own profile


class CurrentUserAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"data": UserSerializer(request.user).data})

    def post(self, request):
        serializer = ProfileUpdateRequestSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        password_changed = bool(serializer.validated_data.get("password"))

        with transaction.atomic():
            user = serializer.save()
            if password_changed:
                # Signs every other session out; the caller carries on with the new token.
                token = issue_token(user, rotate=True)

        body = {"data": UserSerializer(user).data}
        if password_changed:
            body["token"] = token
        return Response(body)


def _client_hints(request) -> dict:
    """The app's platform and version headers, stored on the OTP for debugging only."""
    hints = {key: request.headers.get(header) for key, header in CLIENT_HINT_HEADERS.items()}
    return {key: value for key, value in hints.items() if value}
