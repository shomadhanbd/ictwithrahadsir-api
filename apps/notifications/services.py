from apps.notifications.gateways import SmsError, get_gateway
from apps.notifications.models import SmsMessage


def send_sms(phone, message, *, purpose, recipient=None, sent_by=None) -> SmsMessage:
    """The only way to send an SMS: sends it and records it. A failure is recorded, then raised as `SmsError`."""
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
