from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.communication.models import Notice, NoticeCategory, NoticeSeen, SmsMessage
from apps.courses.models import Enrollment
from apps.identity.roles import is_staff_member

# A first visit to the board counts this far back as unread.
FIRST_UNREAD_DAYS = 30

FOR_EVERYONE = Q(class_levels__isnull=True, batches__isnull=True)
NOTICE_RELATIONS = ("categories", "class_levels", "batches")


def notices_for(user):
    """Notices for everyone or for the user's class level or batch; staff read all."""
    notices = Notice.objects.all()
    if is_staff_member(user):
        return notices
    if user is None or not user.is_authenticated:
        return notices.filter(FOR_EVERYONE).distinct()

    courses = Enrollment.objects.current().filter(user=user).values_list("course__class_level_id", "course__batch_id")
    level_ids = {level for level, _ in courses if level}
    batch_ids = {batch for _, batch in courses if batch}
    profile = getattr(user, "student", None)
    if profile is not None and profile.class_level_id:
        level_ids.add(profile.class_level_id)
    return notices.filter(FOR_EVERYONE | Q(class_levels__in=level_ids) | Q(batches__in=batch_ids)).distinct()


def notice_board(user):
    return notices_for(user).prefetch_related(*NOTICE_RELATIONS)


def unread_notice_count(user) -> int:
    seen = NoticeSeen.objects.filter(user=user).values_list("seen_at", flat=True).first()
    since = seen or timezone.now() - timezone.timedelta(days=FIRST_UNREAD_DAYS)
    return notices_for(user).filter(created_at__gt=since).count()


def admin_notices():
    return Notice.objects.prefetch_related(*NOTICE_RELATIONS)


def admin_notice_categories():
    return NoticeCategory.objects.annotate(notice_count=Count("notices"))


def sms_to(user):
    """SMS sent to `user` or to their guardian about them."""
    return SmsMessage.objects.filter(recipient=user).select_related("sent_by")


def sms_recipient(pk):
    """The student to text, with the profile that holds their guardian's number; or 404."""
    return get_object_or_404(get_user_model().objects.select_related("student"), pk=pk)
