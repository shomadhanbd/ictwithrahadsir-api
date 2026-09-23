from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.responses import MessageResponseSerializer, OkResponseSerializer
from apps.core.api.throttling import (
    AuthBurstThrottle,
    AuthSustainedThrottle,
    LoginBurstThrottle,
    LoginSustainedThrottle,
)
from apps.identity.api.base import (
    SerializerAPIView,
)
from apps.identity.api.serializers import (
    AuthTokenResponseSerializer,
    OtpRequestResponseSerializer,
    OtpVerifyRequestSerializer,
    PasswordResetRequestSerializer,
    PasswordResetResponseSerializer,
    PhoneCheckResponseSerializer,
    PhoneRequestSerializer,
    ProfileUpdateRequestSerializer,
    UserLoginRequestSerializer,
    UserRegisterRequestSerializer,
    UserSerializer,
)
from apps.identity.models import User
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


def request_meta(request) -> dict:
    """Client hints recorded against an issued code, for debugging only."""
    hints = {key: request.headers.get(header) for key, header in CLIENT_HINT_HEADERS.items()}
    return {key: value for key, value in hints.items() if value}


class PublicAuthAPIView(SerializerAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthBurstThrottle, AuthSustainedThrottle]


class PhoneCheckAPIView(PublicAuthAPIView):
    """GET /auth/phone-check?phone= -- does an account exist for this number?"""

    serializer_class = PhoneRequestSerializer

    @extend_schema(
        summary="Does an account exist for this number?",
        parameters=[PhoneRequestSerializer],
        responses={200: PhoneCheckResponseSerializer},
    )
    def get(self, request):
        data = self.validated_data(request, from_query=True)
        exists = User.objects.filter(phone=data["phone"]).exists()
        return Response(PhoneCheckResponseSerializer({"exists": exists}).data)


class OtpRequestAPIView(PublicAuthAPIView):
    """GET /auth/otp?phone= -- send a code; report if the number is known."""

    serializer_class = PhoneRequestSerializer

    @extend_schema(
        summary="Send a verification code",
        parameters=[PhoneRequestSerializer],
        responses={200: OtpRequestResponseSerializer},
    )
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
    """POST /auth/otp/verify -- consume a code and hand back a session token."""

    serializer_class = OtpVerifyRequestSerializer

    @extend_schema(
        summary="Consume a code and get a token",
        request=OtpVerifyRequestSerializer,
        responses={200: AuthTokenResponseSerializer},
    )
    def post(self, request):
        data = self.validated_data(request)
        user, is_new = verify_phone(data["phone"], data["otp"])
        return Response(
            AuthTokenResponseSerializer({"token": issue_token(user), "user": None if is_new else user}).data
        )


class UserRegisterAPIView(SerializerAPIView):
    """POST /auth/register -- fill in the profile for an OTP-verified number.

    Authenticated with the token `/auth/otp/verify/` hands back: that token is
    the only thing tying this call to whoever received the SMS.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = UserRegisterRequestSerializer

    @extend_schema(
        summary="Complete a profile after OTP verification",
        request=UserRegisterRequestSerializer,
        responses={201: AuthTokenResponseSerializer},
    )
    def post(self, request):
        data = self.validated_data(request)
        user = register_user(
            user=request.user,
            name=data["name"],
            password=data["password"],
            institution=data.get("institution"),
            educational_session=data.get("educational_session"),
        )
        return Response(
            AuthTokenResponseSerializer({"token": issue_token(user), "user": user}).data,
            status=status.HTTP_201_CREATED,
        )


class UserLoginAPIView(PublicAuthAPIView):
    """POST /auth/login -- phone plus password."""

    throttle_classes = [LoginBurstThrottle, LoginSustainedThrottle]
    serializer_class = UserLoginRequestSerializer

    @extend_schema(
        summary="Sign in",
        request=UserLoginRequestSerializer,
        responses={200: AuthTokenResponseSerializer},
    )
    def post(self, request):
        data = self.validated_data(request)
        user = authenticate_user(password=data["password"], phone=data["phone"])
        return Response(AuthTokenResponseSerializer({"token": issue_token(user), "user": user}).data)


class PasswordForgotAPIView(PublicAuthAPIView):
    """POST /auth/password/forgot -- send a reset code to a known number."""

    serializer_class = PhoneRequestSerializer

    @extend_schema(
        summary="Start a password reset",
        request=PhoneRequestSerializer,
        responses={200: MessageResponseSerializer},
    )
    def post(self, request):
        phone = self.validated_data(request)["phone"]
        start_password_reset(phone, request_meta(request))
        return Response(MessageResponseSerializer({"message": "OTP sent."}).data)


class PasswordResetAPIView(PublicAuthAPIView):
    """POST /auth/password/reset -- set a new password against a valid OTP."""

    serializer_class = PasswordResetRequestSerializer

    @extend_schema(
        summary="Finish a password reset",
        request=PasswordResetRequestSerializer,
        responses={200: PasswordResetResponseSerializer},
    )
    def post(self, request):
        data = self.validated_data(request)
        user = reset_password(phone=data["phone"], code=data["otp"], password=data["password"])
        return Response(
            PasswordResetResponseSerializer(
                {"token": issue_token(user, rotate=True), "message": "Password has been reset."}
            ).data
        )


class UserLogoutAPIView(APIView):
    """POST /auth/logout -- revoke the caller's token."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Sign out", request=None, responses={200: OkResponseSerializer})
    def post(self, request):
        revoke_tokens(request.user)
        return Response(OkResponseSerializer({"ok": True}).data)


class CurrentUserAPIView(APIView):
    """GET returns the current user; POST patches the profile."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="The signed-in user",
        responses={200: OpenApiResponse(UserSerializer, description="`{data: {...}}`")},
    )
    def get(self, request):
        return Response({"data": UserSerializer(request.user).data})

    @extend_schema(
        summary="Update the signed-in profile",
        request=ProfileUpdateRequestSerializer,
        responses={200: OpenApiResponse(UserSerializer, description="`{data: {...}}`")},
    )
    def post(self, request):
        serializer = ProfileUpdateRequestSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({"data": UserSerializer(user).data})
