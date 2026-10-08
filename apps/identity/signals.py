from django.apps import apps as django_apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.db import DEFAULT_DB_ALIAS
from django.db.models import Q
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from apps.identity.roles import MODERATOR_APP_LABELS, MODERATOR_MODELS, Role


@receiver(post_migrate)
def sync_role_group_permissions(sender, using=DEFAULT_DB_ALIAS, **kwargs):
    """After every migrate, gives the admin group every permission and the moderator group those of the
    apps it manages, so the Django admin is not empty for them."""
    # post_migrate fires once per app; once is enough.
    if sender.label != "identity":
        return

    # Other apps' permissions may not exist yet when identity's signal fires.
    for app_config in django_apps.get_app_configs():
        create_permissions(app_config, verbosity=0, using=using)

    groups = Group.objects.using(using)
    permissions = Permission.objects.using(using)

    admin = groups.filter(name=Role.ADMIN).first()
    if admin is not None:
        admin.permissions.set(permissions.all())

    moderator = groups.filter(name=Role.MODERATOR).first()
    if moderator is not None:
        scope = Q(content_type__app_label__in=MODERATOR_APP_LABELS)
        for app_label, models in MODERATOR_MODELS.items():
            scope |= Q(content_type__app_label=app_label, content_type__model__in=models)
        moderator.permissions.set(permissions.filter(scope))
