import logging
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

import requests as http_requests
from rest_framework.exceptions import Throttled, ValidationError
from sslcommerz_lib import SSLCOMMERZ

from apps.billing.models import Payment, Product
from apps.billing.selectors import access_until, open_checkout
from apps.billing.services.settlement import flag_if_duplicate, lock_buyer, refuse_running_purchase
from apps.courses.models import Course

logger = logging.getLogger("payments")

_DHAKA_TZ = ZoneInfo("Asia/Dhaka")
_TRAN_DATE_FMT = "%Y-%m-%d %H:%M:%S"
MIN_AMOUNT = 10
GATEWAY_TIMEOUT_SECONDS = 15


class _Gateway(SSLCOMMERZ):
    """The SDK, with a timeout on the session call it would otherwise make without one."""

    def hash_validate_ipn(self, post_body):
        """The SDK's signature check, refusing rather than raising on a body whose `verify_key` names a missing
        field: SSLCommerz retries a callback that does not get a 200."""
        try:
            return super().hash_validate_ipn(post_body)
        except (KeyError, AttributeError, TypeError):
            return False

    def call_api(self, method, url, payload):
        if method != "POST":
            return super().call_api(method, url, payload)
        try:
            return http_requests.post(url, data=payload, timeout=GATEWAY_TIMEOUT_SECONDS).json()
        except (http_requests.RequestException, ValueError) as exc:
            logger.error("SSLCommerz createSession call failed: %s", type(exc).__name__)
            return {}


def _get_sslcz() -> SSLCOMMERZ:
    return _Gateway(
        {
            "store_id": settings.SSLCOMMERZ_STORE_ID,
            "store_pass": settings.SSLCOMMERZ_STORE_PASSWORD,
            "issandbox": settings.SSLCOMMERZ_IS_SANDBOX,
        }
    )


def _throttle_initiate(user) -> None:
    cutoff = timezone.now() - timezone.timedelta(hours=1)
    count = Payment.objects.filter(user=user, status=Payment.Status.INITIATED, created_at__gte=cutoff).count()
    if count >= settings.PAYMENT_INITIATE_RATE_LIMIT_PER_USER_PER_HOUR:
        raise Throttled(detail="Too many payment initiation requests. Please try again later.")


def _validate_with_validator_api(
    val_id: str,
    expected_amount: int,
    expected_tran_id: str,
    expected_user_pk: int | None = None,
) -> bool | None:
    """None when SSLCommerz could not be reached."""
    base = "https://sandbox.sslcommerz.com" if settings.SSLCOMMERZ_IS_SANDBOX else "https://securepay.sslcommerz.com"
    url = f"{base}/validator/api/validationserverAPI.php"
    params = {
        "val_id": val_id,
        "store_id": settings.SSLCOMMERZ_STORE_ID,
        "store_passwd": settings.SSLCOMMERZ_STORE_PASSWORD,
        "v": 1,
        "format": "json",
    }
    try:
        resp = http_requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        # Only the type: request errors quote the URL, which carries store_passwd.
        logger.warning("SSLCommerz validator API call failed: %s", type(exc).__name__)
        return None

    # VALIDATED is the same answer for a val_id that was already checked once.
    if data.get("status") not in ("VALID", "VALIDATED"):
        return False
    if data.get("tran_id") != expected_tran_id:
        return False
    try:
        if abs(float(data.get("amount", 0)) - expected_amount) > 0.5:
            return False
    except (TypeError, ValueError):
        return False
    if expected_user_pk is not None and data.get("value_a") != str(expected_user_pk):
        logger.warning(
            "SSLCommerz: value_a mismatch for tran_id %s (got %r, expected %r)",
            expected_tran_id,
            data.get("value_a"),
            str(expected_user_pk),
        )
        return False
    return True


def _apply_status(payment: Payment, data: dict, *, validated: bool | None = None) -> None:
    """Idempotent."""
    incoming_status = data.get("status", "")
    if incoming_status not in Payment.Status.values:
        incoming_status = Payment.Status.FAILED  # e.g. UNATTEMPTED

    if payment.status == incoming_status:
        logger.info(
            "SSLCommerz: payment %s already at status %s — no-op",
            payment.transaction_id,
            incoming_status,
        )
        return
    if payment.status == Payment.Status.VALID:
        logger.warning(
            "SSLCommerz: payment %s is VALID; ignoring a late %s",
            payment.transaction_id,
            incoming_status,
        )
        return

    if incoming_status == Payment.Status.VALID:
        if validated is None:
            logger.warning(
                "SSLCommerz: could not validate payment %s — left for the IPN",
                payment.transaction_id,
            )
            return
        if not validated:
            logger.warning(
                "SSLCommerz: val_id validation failed for payment %s — marking FAILED",
                payment.transaction_id,
            )
            payment.status = Payment.Status.FAILED
            payment.gateway_response = data
            payment.save(update_fields=["status", "gateway_response", "updated_at"])
            return

    tran_date_str = data.get("tran_date")
    if tran_date_str:
        try:
            naive = datetime.strptime(tran_date_str, _TRAN_DATE_FMT)
            transaction_date = timezone.make_aware(naive, _DHAKA_TZ)
        except (ValueError, TypeError) as exc:
            logger.warning("SSLCommerz: could not parse tran_date %r: %s", tran_date_str, exc)
            transaction_date = timezone.now()
    else:
        transaction_date = None

    if incoming_status == Payment.Status.VALID:
        flag_if_duplicate(payment)

    payment.status = incoming_status
    payment.card_type = data.get("card_type", "")
    payment.card_issuer_country = data.get("card_issuer_country", "")
    payment.gateway_response = data
    if transaction_date is not None:
        payment.transaction_date = transaction_date
    payment.save(
        update_fields=[
            "status",
            "card_type",
            "card_issuer_country",
            "gateway_response",
            "transaction_date",
            "note",
            "refund_due",
            "updated_at",
        ]
    )


def _settle(payment: Payment, data: dict) -> Payment:
    validated = None
    if data.get("status") == Payment.Status.VALID and payment.status != Payment.Status.VALID:
        validated = _validate_with_validator_api(
            data.get("val_id", ""),
            payment.amount,
            payment.transaction_id,
            expected_user_pk=payment.user_id,
        )
    with transaction.atomic():
        lock_buyer(payment.user_id)
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        _apply_status(payment, data, validated=validated)
    return payment


def _callback_url(name: str) -> str:
    return settings.API_BASE_URL.rstrip("/") + reverse(f"api:billing:{name}")


def _product_for_sale(product_id: str) -> Product:
    """The package on sale, or why it is not."""
    product = Product.objects.on_sale().filter(product_id=product_id).first()
    if product is not None:
        return product
    unpublished = Course.objects.filter(products__product_id=product_id).exclude(status=Course.Status.PUBLISHED).first()
    if unpublished is not None:
        raise ValidationError({"product_id": f"{unpublished.title} is not open for purchase."})
    closed = Course.objects.filter(products__product_id=product_id, enrollment_deadline__lt=timezone.now()).first()
    if closed is not None:
        when = timezone.localtime(closed.enrollment_deadline)
        raise ValidationError({"product_id": f"Enrolment for {closed.title} closed on {when:%d %b %Y}."})
    raise ValidationError({"product_id": "Product not found."})


def initiate_payment(*, user, product_id: str) -> dict:
    """A free product is VALID at once and has no gateway_page_url."""
    product = _product_for_sale(product_id)
    amount = product.current_price
    if 0 < amount < MIN_AMOUNT:
        raise ValidationError({"product_id": f"The amount to pay must be at least {MIN_AMOUNT} BDT."})

    with transaction.atomic():
        # One buyer at a time: a double click sees the first click's checkout, and a free package is claimed once.
        lock_buyer(user.pk)
        refuse_running_purchase(user, product)
        pending = open_checkout(user, product, amount) if amount else None
        if pending is not None and not pending.gateway_page_url:
            raise ValidationError({"product_id": "This checkout is already opening. Please wait a moment."})
        if pending is not None:
            return {"transaction_id": pending.transaction_id, "gateway_page_url": pending.gateway_page_url}

        _throttle_initiate(user)
        fields = {"user": user, "product": product, "amount": amount, "access_until": access_until(product, user=user)}
        if amount == 0:
            payment = Payment.objects.create(status=Payment.Status.VALID, transaction_date=timezone.now(), **fields)
            return {"transaction_id": payment.transaction_id, "gateway_page_url": None}
        payment = Payment.objects.create(**fields)

    # Committed first, so no transaction is held open while SSLCommerz answers.
    return _open_gateway_session(payment)


def _open_gateway_session(payment: Payment) -> dict:
    user = payment.user
    capture_url = _callback_url("payment_capture")
    post_body = {
        "total_amount": payment.amount,
        "currency": "BDT",
        "tran_id": payment.transaction_id,
        "success_url": capture_url,
        "fail_url": capture_url,
        "cancel_url": capture_url,
        "ipn_url": _callback_url("payment_ipn"),
        "multi_card_name": "",
        "emi_option": 0,
        "value_a": str(user.pk),  # echoed by the Validator API; see `_validate_with_validator_api`
        "cus_name": user.name or "Customer",
        "cus_email": user.email or f"{user.phone}@students.invalid",
        "cus_add1": "",
        "cus_city": "",
        "cus_country": "Bangladesh",
        "cus_phone": (user.phone or "01").lstrip("+"),
        "shipping_method": "NO",
        "num_of_item": 1,
        "product_name": payment.title[:255],
        "product_category": "education",
        "product_profile": "non-physical-goods",
    }

    session = _get_sslcz().createSession(post_body) or {}

    if session.get("status") != "SUCCESS":
        logger.error("SSLCommerz createSession failed: %s", session)
        payment.delete()
        raise ValidationError({"non_field_errors": "Payment gateway error. Please try again."})

    payment.gateway_page_url = session["GatewayPageURL"]
    payment.save(update_fields=["gateway_page_url", "updated_at"])
    return {"transaction_id": payment.transaction_id, "gateway_page_url": payment.gateway_page_url}


def _redirect(url: str, tran_id: str) -> dict:
    return {"redirect_url": f"{url}?{urlencode({'tran_id': tran_id})}"}


def process_capture(data: dict) -> dict:
    sslcz = _get_sslcz()
    if not sslcz.hash_validate_ipn(data):
        logger.warning("SSLCommerz capture: hash validation failed")
        return {"redirect_url": settings.SSLCOMMERZ_FAIL_REDIRECT}

    tran_id = data.get("tran_id", "")
    payment = Payment.objects.filter(transaction_id=tran_id).first()
    if payment is None:
        logger.error("SSLCommerz capture: payment %s not found", tran_id)
        return {"redirect_url": settings.SSLCOMMERZ_FAIL_REDIRECT}

    payment = _settle(payment, data)

    incoming_status = data.get("status", "")
    if payment.status == Payment.Status.VALID:
        return _redirect(settings.SSLCOMMERZ_SUCCESS_REDIRECT, tran_id)
    if incoming_status == Payment.Status.VALID and payment.status == Payment.Status.INITIATED:
        return _redirect(settings.SSLCOMMERZ_SUCCESS_REDIRECT, tran_id)
    if payment.status == Payment.Status.CANCELLED:
        return _redirect(settings.SSLCOMMERZ_CANCEL_REDIRECT, tran_id)
    return _redirect(settings.SSLCOMMERZ_FAIL_REDIRECT, tran_id)


def process_ipn(data: dict) -> None:
    """Never raises: SSLCommerz retries an IPN that does not get a 200."""
    sslcz = _get_sslcz()
    if not sslcz.hash_validate_ipn(data):
        logger.warning("SSLCommerz IPN: hash validation failed")
        return

    tran_id = data.get("tran_id", "")
    payment = Payment.objects.filter(transaction_id=tran_id).first()
    if payment is None:
        logger.error("SSLCommerz IPN: payment %s not found", tran_id)
        return

    try:
        _settle(payment, data)
    except Exception:
        logger.exception("SSLCommerz IPN: error applying status for %s", tran_id)
