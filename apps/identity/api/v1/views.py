from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import filters, status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.generics import (
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsFullAdmin, IsTeachingStaff
from apps.core.api.responses import MessageResponseSerializer, OkResponseSerializer
from apps.core.api.throttling import (
    AuthBurstThrottle,
    AuthSustainedThrottle,
    LoginBurstThrottle,
    LoginSustainedThrottle,
)
from apps.core.api.viewsets import UnpaginatedDataListMixin
from apps.core.spreadsheets import read_records
from apps.identity.api.v1.permissions import CanManageUsers
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
from apps.identity.services import consume_otp, import_users, issue_token, send_otp


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
    """GET /auth/phone-check?phone= -- does an account exist for this number?

    Throttled like the rest of the auth endpoints, which it was not: a public
    endpoint that answers "is this number registered?" and nothing else is a
    membership oracle, and an unlimited one can simply be walked across the
    whole 01XXXXXXXXX range to harvest which numbers hold accounts.

    The limits key on IP (`AnonRateThrottle`), so this raises the cost of
    that sweep rather than making it impossible. It is the same trade the
    login endpoint already makes.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AuthBurstThrottle, AuthSustainedThrottle]

    @extend_schema(
        summary='Does an account exist for this number?',
        parameters=[PhoneRequestSerializer],
        responses={200: PhoneCheckResponseSerializer},
    )
    def get(self, request):
        # Through the serializer, like its neighbours -- reading the raw
        # query param meant a missing `phone` was answered as "no account
        # exists for the empty string" rather than as a bad request.
        serializer = PhoneRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        return Response(
            PhoneCheckResponseSerializer(
                {
                    "exists": User.objects.filter(
                        phone=serializer.validated_data["phone"]
                    ).exists()
                }
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
        consume_otp(phone, serializer.validated_data["otp"])

        user = User.objects.filter(phone=phone).first()
        is_new = user is None
        if is_new:
            # A placeholder, not a student yet: the client stores the token
            # below as its session cookie, so the row has to exist now, but
            # nobody has told us a name. `/auth/register/` completes it.
            user = User.objects.create_unverified(phone)

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
            user.registered_at = timezone.now()
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

        # Account first, code second: burning a valid code because the phone
        # turned out to belong to nobody would cost the user a code and a
        # cooldown for a mistake the code had no part in.
        user = User.objects.filter(phone=data["phone"]).first()
        if not user:
            raise ValidationError({"phone": ["No account found with this phone number."]})
        consume_otp(data["phone"], data["otp"])

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


class AdminUserListCreateAPIView(ListCreateAPIView):
    """GET /admin/users/ -- the paginated roster. POST -- create an account."""

    permission_classes = [CanManageUsers]
    serializer_class = AdminUserSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "email", "institution"]
    ordering_fields = ["date_joined", "name"]

    #: What the panel's dropdowns send for their "no filter" option. Neither
    #: is a value the underlying field can hold, so each can only mean "any".
    ROLE_ANY = "all"
    STATUS_ANY = "all"

    def get_queryset(self):
        # `registered()`, not `all()`: a phone that passed OTP and then
        # abandoned the form is a pending verification, not a person on the
        # roster. See `User.registered_at`.
        qs = User.objects.registered()
        params = self.request.query_params

        # The role dropdown defaults to "all" and the page sends it on every
        # request, including the export. Matching it literally filtered the
        # list down to nothing, so the Users screen was empty on load and
        # only showed anyone once a specific role was picked.
        role = params.get("role")
        if role and role != self.ROLE_ANY:
            qs = qs.filter(role=role)

        # Deleting a user destroys their orders, payments and exam attempts
        # (all of them cascade off `user`), so `destroy` deactivates instead
        # -- see AdminUserDetailAPIView.destroy. Hiding deactivated accounts
        # by default is what keeps that looking like a delete to the panel,
        # which refetches this list afterwards. `?status=inactive` is how an
        # admin finds one again, and `?status=all` shows both.
        status_filter = params.get("status")
        if status_filter == "inactive":
            qs = qs.filter(is_active=False)
        elif status_filter != self.STATUS_ANY:
            qs = qs.filter(is_active=True)
        return qs


class AdminUserDetailAPIView(RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /admin/users/<pk>/.

    Unfiltered on purpose, where the list above hides deactivated accounts:
    an admin who has a specific id in hand is not browsing, and reactivating
    somebody means being able to reach them first.

    DELETE deactivates. See `destroy` for why.
    """

    permission_classes = [CanManageUsers]
    serializer_class = AdminUserSerializer
    queryset = User.objects.all()

    def destroy(self, request, *args, **kwargs):
        """Deactivate rather than delete, and revoke the account's tokens.

        `Order`, `Payment`, `Enrollment`, `ExamAttempt` and
        `ContentCompletion` all declare `on_delete=CASCADE` against the user,
        so a real delete takes the coaching centre's record of what this
        student paid and what they scored with it. There is no undo for that
        and no reason to want one: the thing an admin means by "delete this
        student" is "stop their access".

        Still answers 204, because that is what the admin panel handles, and
        the row leaves the default listing either way.
        """
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        Token.objects.filter(user=user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserSearchAPIView(UnpaginatedDataListMixin, ListAPIView):
    """Typeahead for the course-enrolment screens: students only, capped,
    unpaginated because the admin panel renders it straight into a dropdown."""

    # Teaching staff, because this is what the course enrolment screens
    # search against -- a teacher adding a student to their own course needs
    # to be able to find them.
    permission_classes = [IsTeachingStaff]
    serializer_class = UserSerializer
    RESULT_LIMIT = 25

    def get_queryset(self):
        qs = User.objects.students().filter(is_active=True)
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

    # Creating accounts in bulk, so it sits with the rest of account
    # management rather than with the enrolment screens.
    permission_classes = [IsFullAdmin]

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
