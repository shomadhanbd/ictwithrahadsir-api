"""Keeps each role group's Django permissions in step with the models."""

from django.apps import apps as django_apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.db import DEFAULT_DB_ALIAS
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from apps.identity.roles import MODERATOR_APP_LABELS, Role


@receiver(post_migrate)
def sync_role_group_permissions(sender, **kwargs):
    """Grants the back-office groups their permissions, so the Django admin is not empty for them."""
    if sender.label != "identity":  # post_migrate fires once per app
        return

    # Other apps' permissions may not exist yet when identity's signal fires.
    using = kwargs.get("using", DEFAULT_DB_ALIAS)
    for app_config in django_apps.get_app_configs():
        create_permissions(app_config, verbosity=0, using=using)

    groups = {group.name: group for group in Group.objects.using(using).filter(name__in=Role.values)}
    permissions = Permission.objects.using(using)

    if admin_group := groups.get(Role.ADMIN):
        admin_group.permissions.set(permissions.all())

    if moderator := groups.get(Role.MODERATOR):
        moderator.permissions.set(permissions.filter(content_type__app_label__in=MODERATOR_APP_LABELS))
