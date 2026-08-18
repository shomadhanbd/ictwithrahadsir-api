from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import filters, status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsAdminRole
from apps.core.api.responses import MessageResponseSerializer, OkResponseSerializer
from apps.core.api.throttling import (
    AuthBurstThrottle,
    AuthSustainedThrottle,
    LoginBurstThrottle,
    LoginSustainedThrottle,
)
from apps.core.api.viewsets import AdminModelViewSet, UnpaginatedDataListMixin
from apps.core.spreadsheets import read_records
from apps.identity.api.v1.serializers import (
    AdminUserSerializer,
    AuthTokenResponseSerializer,
    OtpRequestResponseSerializer,
    OtpVerifyRequestSerializer,
    PasswordResetRequestSerializer,
    PasswordResetResponseSerializer,
    PhoneCheckResponseSerializer,
    PhoneRequestSerializer,
    ProfileUpdateRequestSerializer,
    UserImportRequestSerializer,
    UserLoginRequestSerializer,
    UserRegisterRequestSerializer,
    UserSerializer,
)
from apps.identity.models import OTP, User
from apps.identity.services import import_users, issue_token, send_otp


class OtpIssueMixin:
    """Resend-cooldown guard for the endpoints that send an SMS.

    `OTP_RESEND_COOLDOWN_SECONDS` shipped in settings but was never read, so
    nothing stopped the public endpoints from being used to bombard a number
    with SMS at the platform's expense.
    """

    def issue_otp_or_throttle(self, phone: str) -> None:
        """For explicit "send me a code" actions: refuse while cooling down."""
        wait = OTP.seconds_until_resend(phone)
        if wait:
            raise Throttled(wait=wait)
        send_otp(phone)

    def issue_otp_if_due(self, phone: str) -> int:
        """For endpoints on a critical path: never fail, just skip the send.

        Returns the seconds remaining before another code may be sent.
        """
        wait = OTP.seconds_until_resend(phone)
        if not wait:
            send_otp(phone)
        return wait


# ---------------------------------------------------------------------------
# Public / client-facing auth
# ---------------------------------------------------------------------------


class PhoneCheckAPIView(APIView):
    """GET /check-phone?phone= -- does an account exist for this number?"""

    permission_classes = [AllowAny]

    @extend_schema(
        summary='Does an account exist for this number?',
        parameters=[PhoneRequestSerializer],
        responses={200: PhoneCheckResponseSerializer},
    )
    def get(self, request):
        phone = request.query_params.get("phone", "")
        return Response(
            PhoneCheckResponseSerializer(
                {"exists": User.objects.filter(phone=phone).exists()}
            ).data
        )


class OtpRequestAPIView(OtpIssueMixin, APIView):
    """GET /get-otp?phone= -- send a verification code and report whether the
    number already has an account and a usable password, which is what the
    client uses to branch between the login and registration flows.

    The client calls this on *every* login attempt (see the web app's
    `login(phone)`), so it must not start failing once a code has been sent:
    within the cooldown it still answers 200 with the account state and
    simply does not send a second SMS. `resend_in` tells the client how long
    until another code can be requested.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthBurstThrottle, AuthSustainedThrottle]

    @extend_schema(
        summary='Send a verification code',
        parameters=[PhoneRequestSerializer],
        responses={200: OtpRequestResponseSerializer},
    )
    def get(self, request):
        serializer = PhoneRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        user = User.objects.filter(phone=phone).first()
        wait = self.issue_otp_if_due(phone)

        return Response(
            OtpRequestResponseSerializer(
                {
                    "user_exist": bool(user),
                    "password_exist": bool(user and user.has_usable_password()),
                    "message": (
                        "OTP sent."
                        if not wait
                        else "A code was sent recently. Please wait before requesting another."
                    ),
                    "resend_in": wait,
                }
            ).data
        )


class OtpVerifyAPIView(APIView):
    """POST /verify-otp -- consume a code and hand back a session token.

    For an unknown number this creates a bare, unusable-password row so that
    /register can complete the profile against the same user.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthBurstThrottle, AuthSustainedThrottle]

    @extend_schema(
        summary='Consume a code and get a token',
        request=OtpVerifyRequestSerializer,
        responses={200: AuthTokenResponseSerializer},
    )
    def post(self, request):
        serializer = OtpVerifyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        user = User.objects.filter(phone=phone).first()
        is_new = user is None
        if is_new:
            user = User.objects.create_user(phone=phone, role=User.Role.STUDENT)

        user.phone_verified_at = timezone.now()
        user.save(update_fields=["phone_verified_at"])

        return Response(
            AuthTokenResponseSerializer(
                {"token": issue_token(user), "user": None if is_new else user}
            ).data
        )


class UserRegisterAPIView(APIView):
    """POST /register -- fill in the profile for an OTP-verified number."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthBurstThrottle, AuthSustainedThrottle]

    @extend_schema(
        summary='Complete a profile after OTP verification',
        request=UserRegisterRequestSerializer,
        responses={201: AuthTokenResponseSerializer},
    )
    def post(self, request):
        serializer = UserRegisterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            # Locked for the duration so two concurrent submissions cannot
            # both pass the "not yet registered" check.
            user = User.objects.select_for_update().filter(phone=data["phone"]).first()
            if not user or not user.phone_verified_at:
                raise ValidationError({"phone": ["Phone has not been verified via OTP."]})
            if user.has_usable_password():
                raise ValidationError({"phone": ["This phone number is already registered."]})

            user.name = data["name"]
            user.institution = data.get("institution", user.institution)
            user.educational_session = data.get(
                "educational_session", user.educational_session
            )
            user.set_password(data["password"])
            user.save()

        return Response(
            AuthTokenResponseSerializer({"token": issue_token(user), "user": user}).data,
            status=status.HTTP_201_CREATED,
        )


class UserLoginAPIView(APIView):
    """POST /login -- phone-or-email plus password."""

    permission_classes = [AllowAny]
    throttle_classes = [LoginBurstThrottle, LoginSustainedThrottle]

    @extend_schema(
        summary='Sign in',
        request=UserLoginRequestSerializer,
        responses={200: AuthTokenResponseSerializer},
    )
    def post(self, request):
        serializer = UserLoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        return Response(
            AuthTokenResponseSerializer({"token": issue_token(user), "user": user}).data
        )


class PasswordForgotAPIView(OtpIssueMixin, APIView):
    """POST /forget-password -- send a reset code to a known number."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthBurstThrottle, AuthSustainedThrottle]

    @extend_schema(
        summary='Start a password reset',
        request=PhoneRequestSerializer,
        responses={200: MessageResponseSerializer},
    )
    def post(self, request):
        serializer = PhoneRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        if not User.objects.filter(phone=phone).exists():
            raise ValidationError({"phone": ["No account found with this phone number."]})

        # An explicit "send me a reset code" button, so refusing while the
        # cooldown runs is honest and does not strand the user mid-flow.
        self.issue_otp_or_throttle(phone)
        return Response(MessageResponseSerializer({"message": "OTP sent."}).data)


class PasswordResetAPIView(APIView):
    """POST /password-reset -- set a new password against a valid OTP."""

    permission_classes = [AllowAny]
    throttle_classes = [AuthBurstThrottle, AuthSustainedThrottle]

    @extend_schema(
        summary='Finish a password reset',
        request=PasswordResetRequestSerializer,
        responses={200: PasswordResetResponseSerializer},
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User.objects.filter(phone=data["phone"]).first()
        if not user:
            raise ValidationError({"phone": ["No account found with this phone number."]})

        user.set_password(data["password"])
        user.save(update_fields=["password"])

        return Response(
            PasswordResetResponseSerializer(
                {
                    "token": issue_token(user, rotate=True),
                    "message": "Password has been reset.",
                }
            ).data
        )


class UserLogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Sign out', request=None, responses={200: OkResponseSerializer})
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(OkResponseSerializer({"ok": True}).data)


class CurrentUserAPIView(APIView):
    """GET returns the current user; POST patches the profile (the shape the
    existing client already sends -- not a PATCH)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='The signed-in user',
        responses={200: OpenApiResponse(UserSerializer, description='`{data: {...}}`')},
    )
    def get(self, request):
        return Response({"data": UserSerializer(request.user).data})

    @extend_schema(
        summary='Update the signed-in profile',
        request=ProfileUpdateRequestSerializer,
        responses={200: OpenApiResponse(UserSerializer, description='`{data: {...}}`')},
    )
    def post(self, request):
        serializer = ProfileUpdateRequestSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({"data": UserSerializer(user).data})


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


class AdminUserViewSet(AdminModelViewSet):
    queryset = User.objects.all()
    serializer_class = AdminUserSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "email", "institution"]
    ordering_fields = ["date_joined", "name"]

    #: What the admin panel's role dropdown sends for its "no filter" option.
    #: It is not a value `role` can hold, so it can only ever mean "any".
    ROLE_ANY = "all"

    def get_queryset(self):
        qs = super().get_queryset()
        role = self.request.query_params.get("role")

        # The dropdown defaults to "all" and the page sends it on every
        # request, including the export. Matching it literally filtered the
        # list down to nothing, so the Users screen was empty on load and
        # only showed anyone once a specific role was picked.
        if role and role != self.ROLE_ANY:
            qs = qs.filter(role=role)
        return qs


class AdminUserSearchAPIView(UnpaginatedDataListMixin, ListAPIView):
    """Typeahead for the course-enrolment screens: students only, capped,
    unpaginated because the admin panel renders it straight into a dropdown."""

    permission_classes = [IsAdminRole]
    serializer_class = UserSerializer
    RESULT_LIMIT = 25

    def get_queryset(self):
        qs = User.objects.students()
        search = self.request.query_params.get("search", "")
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )
        return qs[: self.RESULT_LIMIT]

    def get_list_payload(self, request, *args, **kwargs):
        # Deliberately not `filter_queryset`: the queryset is already sliced
        # to RESULT_LIMIT, and a filter backend that tried to order or filter
        # it would raise "Cannot filter a query once a slice has been taken".
        return self.get_serializer(self.get_queryset(), many=True).data


class AdminUserImportAPIView(APIView):
    """PUT /admin/user/import -- bulk-create students from a spreadsheet.

    Kept on PUT because that is what the admin panel sends.
    """

    permission_classes = [IsAdminRole]

    @extend_schema(
        summary='Bulk-create students from a spreadsheet',
        request=UserImportRequestSerializer,
        responses={200: OpenApiResponse(description='`{created, skipped}`')},
    )
    def put(self, request):
        serializer = UserImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        records = read_records(serializer.validated_data["file"])
        return Response(import_users(records))
