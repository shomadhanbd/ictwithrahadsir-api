from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.communication.gateways import SmsError, get_gateway
from apps.communication.models import NoticeSeen, SmsMessage


def send_sms(phone, message, *, purpose, recipient=None, sent_by=None) -> SmsMessage:
    """The only way to send an SMS; records it, and records then raises a failure as `SmsError`."""
    record = SmsMessage(
        purpose=purpose,
        phone=phone,
        body="" if purpose in SmsMessage.SECRET_PURPOSES else message,
        recipient=recipient,
        sent_by=sent_by,
    )
    try:
        get_gateway().send(phone, message)
    except SmsError as exc:
        record.status, record.error = SmsMessage.Status.FAILED, str(exc)[:255]
        record.save()
        raise
    record.status = SmsMessage.Status.SENT
    record.save()
    return record


def send_to_student(*, student, to, message, sent_by) -> SmsMessage:
    if to == "guardian":
        profile = getattr(student, "student", None)
        phone = profile.guardian_phone if profile else ""
        if not phone:
            raise ValidationError({"to": "This student has no guardian phone number."})
        return send_sms(phone, message, purpose=SmsMessage.Purpose.GUARDIAN, recipient=student, sent_by=sent_by)
    return send_sms(student.phone, message, purpose=SmsMessage.Purpose.CUSTOM, recipient=student, sent_by=sent_by)


def mark_notices_seen(user) -> NoticeSeen:
    seen, _ = NoticeSeen.objects.update_or_create(user=user, defaults={"seen_at": timezone.now()})
    return seen
