from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import filters, status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsAdminRole
from apps.core.api.viewsets import AdminModelViewSet

from .models import OTP, User
from .serializers import (
    AdminUserSerializer,
    LoginSerializer,
    PasswordResetSerializer,
    PhoneSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserImportSerializer,
    UserSerializer,
    VerifyOtpSerializer,
)


def issue_token(user: User, *, rotate: bool = False) -> str:
    """Return the user's API token, optionally replacing any existing one.

    Rotation matters after a credential change: DRF tokens never expire, so
    without it a token stolen before a password reset stays valid forever
    afterwards -- the reset would not actually lock the attacker out.
    """
    if rotate:
        Token.objects.filter(user=user).delete()
        return Token.objects.create(user=user).key
    token, _ = Token.objects.get_or_create(user=user)
    return token.key


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
        OTP.issue(phone)

    def issue_otp_if_due(self, phone: str) -> int:
        """For endpoints on a critical path: never fail, just skip the send.

        Returns the seconds remaining before another code may be sent.
        """
        wait = OTP.seconds_until_resend(phone)
        if not wait:
            OTP.issue(phone)
        return wait


# ---------------------------------------------------------------------------
# Public / client-facing auth
# ---------------------------------------------------------------------------


class CheckPhoneView(APIView):
    """GET /check-phone?phone= -- does an account exist for this number?"""

    permission_classes = [AllowAny]

    def get(self, request):
        phone = request.query_params.get("phone", "")
        return Response({"exists": User.objects.filter(phone=phone).exists()})


class RequestOtpView(OtpIssueMixin, APIView):
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

    def get(self, request):
        serializer = PhoneSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        user = User.objects.filter(phone=phone).first()
        wait = self.issue_otp_if_due(phone)

        return Response(
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
        )


class VerifyOtpView(APIView):
    """POST /verify-otp -- consume a code and hand back a session token.

    For an unknown number this creates a bare, unusable-password row so that
    /register can complete the profile against the same user.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        user = User.objects.filter(phone=phone).first()
        is_new = user is None
        if is_new:
            user = User.objects.create_user(phone=phone, role=User.Role.STUDENT)

        user.phone_verified_at = timezone.now()
        user.save(update_fields=["phone_verified_at"])

        return Response(
            {
                "token": issue_token(user),
                "user": None if is_new else UserSerializer(user).data,
            }
        )


class RegisterView(APIView):
    """POST /register -- fill in the profile for an OTP-verified number."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
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
            {"token": issue_token(user), "user": UserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """POST /login -- phone-or-email plus password."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        return Response({"token": issue_token(user), "user": UserSerializer(user).data})


class ForgetPasswordView(OtpIssueMixin, APIView):
    """POST /forget-password -- send a reset code to a known number."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        if not User.objects.filter(phone=phone).exists():
            raise ValidationError({"phone": ["No account found with this phone number."]})

        # An explicit "send me a reset code" button, so refusing while the
        # cooldown runs is honest and does not strand the user mid-flow.
        self.issue_otp_or_throttle(phone)
        return Response({"message": "OTP sent."})


class PasswordResetView(APIView):
    """POST /password-reset -- set a new password against a valid OTP."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User.objects.filter(phone=data["phone"]).first()
        if not user:
            raise ValidationError({"phone": ["No account found with this phone number."]})

        user.set_password(data["password"])
        user.save(update_fields=["password"])

        return Response(
            {
                "token": issue_token(user, rotate=True),
                "message": "Password has been reset.",
            }
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"ok": True})


class MeView(APIView):
    """GET returns the current user; POST patches the profile (the shape the
    existing client already sends -- not a PATCH)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"data": UserSerializer(request.user).data})

    def post(self, request):
        serializer = ProfileUpdateSerializer(
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

    def get_queryset(self):
        qs = super().get_queryset()
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        return qs


class AdminUserSearchView(ListAPIView):
    """Typeahead for the course-enrolment screens: students only, capped,
    unpaginated because the admin panel renders it straight into a dropdown."""

    permission_classes = [IsAdminRole]
    serializer_class = UserSerializer
    pagination_class = None
    RESULT_LIMIT = 25

    def get_queryset(self):
        qs = User.objects.filter(role=User.Role.STUDENT)
        search = self.request.query_params.get("search", "")
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )
        return qs[: self.RESULT_LIMIT]

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response({"data": serializer.data})


class AdminUserImportView(APIView):
    """PUT /admin/user/import -- bulk-create students from a spreadsheet.

    Kept on PUT because that is what the admin panel sends.
    """

    permission_classes = [IsAdminRole]

    def put(self, request):
        serializer = UserImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        import openpyxl

        workbook = openpyxl.load_workbook(
            serializer.validated_data["file"], read_only=True, data_only=True
        )
        rows = list(workbook.active.iter_rows(values_only=True))
        if not rows:
            raise ValidationError({"file": ["The file is empty."]})

        header = [str(c).strip().lower() if c else "" for c in rows[0]]

        # Pull the existing keys up front: the previous implementation ran a
        # uniqueness query per row, and let a duplicate email reach the
        # database as an unhandled IntegrityError (a 500 mid-import).
        taken_phones = set(User.objects.exclude(phone=None).values_list("phone", flat=True))
        taken_emails = set(User.objects.exclude(email=None).values_list("email", flat=True))

        created, skipped = 0, 0
        with transaction.atomic():
            for row in rows[1:]:
                record = dict(zip(header, row))
                phone = str(record.get("phone") or "").strip()
                email = str(record.get("email") or "").strip() or None

                if not phone or phone in taken_phones or (email and email in taken_emails):
                    skipped += 1
                    continue

                User.objects.create_user(
                    phone=phone,
                    name=str(record.get("name") or "").strip(),
                    email=email,
                    institution=str(record.get("institution") or "").strip() or None,
                    role=User.Role.STUDENT,
                )
                taken_phones.add(phone)
                if email:
                    taken_emails.add(email)
                created += 1

        return Response({"created": created, "skipped": skipped})
