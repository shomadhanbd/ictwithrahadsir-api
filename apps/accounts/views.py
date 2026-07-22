from django.utils import timezone
from rest_framework import filters
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminRole
from apps.core.viewsets import AdminModelViewSet

from .models import OTP, User
from .serializers import (
    AdminUserSerializer,
    LoginSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserSerializer,
)


def _issue_token(user: User) -> str:
    token, _ = Token.objects.get_or_create(user=user)
    return token.key


# ---------------------------------------------------------------------------
# Public / client-facing auth
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([AllowAny])
def check_phone(request):
    phone = request.query_params.get("phone", "")
    return Response({"exists": User.objects.filter(phone=phone).exists()})


@api_view(["GET"])
@permission_classes([AllowAny])
def get_otp(request):
    phone = request.query_params.get("phone")
    if not phone:
        raise ValidationError({"phone": ["Phone is required."]})
    user = User.objects.filter(phone=phone).first()
    OTP.issue(phone)
    return Response(
        {
            "user_exist": bool(user),
            "password_exist": bool(user and user.has_usable_password()),
            "message": "OTP sent.",
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def verify_otp(request):
    phone = request.data.get("phone")
    otp = request.data.get("otp")
    if not phone or not otp:
        raise ValidationError({"otp": ["Phone and OTP are required."]})
    if not OTP.verify(phone, otp):
        raise ValidationError({"otp": ["Invalid or expired OTP."]})

    user = User.objects.filter(phone=phone).first()
    if user:
        user.phone_verified_at = timezone.now()
        user.save(update_fields=["phone_verified_at"])
        return Response({"token": _issue_token(user), "user": UserSerializer(user).data})

    # New user: create a bare, unusable-password record so /register can
    # complete the profile against the same row.
    user = User.objects.create_user(phone=phone, role=User.Role.STUDENT)
    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at"])
    return Response({"token": _issue_token(user), "user": None})


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    phone = request.data.get("phone")
    user = User.objects.filter(phone=phone).first()
    if not user or not user.phone_verified_at:
        raise ValidationError({"phone": ["Phone has not been verified via OTP."]})
    if user.has_usable_password():
        raise ValidationError({"phone": ["This phone number is already registered."]})

    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    user.name = data["name"]
    user.institution = data.get("institution", user.institution)
    user.educational_session = data.get("educational_session", user.educational_session)
    user.set_password(data["password"])
    user.save()
    return Response({"token": _issue_token(user), "user": UserSerializer(user).data}, status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    user = None
    if data.get("phone"):
        user = User.objects.filter(phone=data["phone"]).first()
    elif data.get("email"):
        user = User.objects.filter(email=data["email"]).first()

    if not user or not user.check_password(data["password"]):
        raise ValidationError({"password": ["Invalid credentials."]})
    if not user.is_active:
        raise ValidationError({"password": ["This account has been deactivated."]})

    return Response({"token": _issue_token(user), "user": UserSerializer(user).data})


@api_view(["POST"])
@permission_classes([AllowAny])
def forget_password(request):
    phone = request.data.get("phone")
    if not phone:
        raise ValidationError({"phone": ["Phone is required."]})
    if not User.objects.filter(phone=phone).exists():
        raise ValidationError({"phone": ["No account found with this phone number."]})
    OTP.issue(phone)
    return Response({"message": "OTP sent."})


@api_view(["POST"])
@permission_classes([AllowAny])
def password_reset(request):
    phone = request.data.get("phone")
    otp = request.data.get("otp")
    password = request.data.get("password")
    password_confirmation = request.data.get("password_confirmation")

    if password != password_confirmation:
        raise ValidationError({"password_confirmation": ["Passwords do not match."]})
    if not OTP.verify(phone, otp):
        raise ValidationError({"otp": ["Invalid or expired OTP."]})

    user = User.objects.filter(phone=phone).first()
    if not user:
        raise ValidationError({"phone": ["No account found with this phone number."]})
    user.set_password(password)
    user.save()
    return Response({"token": _issue_token(user), "message": "Password has been reset."})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"ok": True})


class MeView(APIView):
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


@api_view(["GET"])
@permission_classes([IsAdminRole])
def user_search(request):
    search = request.query_params.get("search", "")
    qs = User.objects.filter(role=User.Role.STUDENT)
    if search:
        from django.db.models import Q

        qs = qs.filter(
            Q(name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search)
        )
    return Response({"data": UserSerializer(qs[:25], many=True).data})


@api_view(["PUT"])
@permission_classes([IsAdminRole])
def import_users(request):
    file = request.FILES.get("file")
    if not file:
        raise ValidationError({"file": ["An Excel file is required."]})

    import openpyxl

    workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValidationError({"file": ["The file is empty."]})

    header = [str(c).strip().lower() if c else "" for c in rows[0]]
    created, skipped = 0, 0
    for row in rows[1:]:
        record = dict(zip(header, row))
        phone = str(record.get("phone") or "").strip()
        if not phone or User.objects.filter(phone=phone).exists():
            skipped += 1
            continue
        User.objects.create_user(
            phone=phone,
            name=str(record.get("name") or "").strip(),
            email=(str(record.get("email")).strip() or None) if record.get("email") else None,
            institution=str(record.get("institution") or "").strip() or None,
            role=User.Role.STUDENT,
        )
        created += 1

    return Response({"created": created, "skipped": skipped})
