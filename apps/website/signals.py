from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.website.models import Banner, Section
from apps.website.services import refresh_website


@receiver([post_save, post_delete], sender=Section)
@receiver([post_save, post_delete], sender=Banner)
def website_changed(sender, **kwargs):
    """Any edit, from the admin panel or the Django admin, reaches the website once it is committed."""
    transaction.on_commit(refresh_website)
