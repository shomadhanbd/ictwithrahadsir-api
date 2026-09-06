"""Keeps a teacher's course assignments in step with the roster entry.

`CourseInstructor` copies `name`, `designation`, `description` and `image`
down from its `Teacher` so a teacher can be billed under a different title on
one course. `CourseInstructor.save()` fills those in when they are blank --
but only when the *assignment* is saved. Renaming the teacher did nothing, so
every course page kept showing the old name indefinitely.

This is a signal rather than a service call because a `Teacher` is saved from
places that share no chokepoint: `AdminTeamViewSet` (a `ModelViewSet`, so the
write is `serializer.save()`), the Django admin, the seed command, and the
shell. A service would only fix the callers that remembered to use it.

Contrast `apps/billing/services.py::confirm_payment`, which is deliberately
*not* a signal: granting course access on payment is a business operation
that must be explicit, ordered and inside one transaction.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.faculty.models import Teacher

#: The fields an assignment inherits from its teacher.
INHERITED_FIELDS = ('name', 'designation', 'description', 'image')

#: Where `pre_save` stashes the pre-change values for `post_save` to read.
_OLD_VALUES_ATTR = '_pre_save_inherited_values'


@receiver(pre_save, sender=Teacher, dispatch_uid='faculty.capture_teacher_fields')
def capture_teacher_fields(sender, instance, **kwargs):
    """Stash the row's current values before they are overwritten.

    `post_save` cannot tell an inherited value from a per-course override --
    both live in the same column -- so the only way to distinguish them is to
    know what the value used to be. An assignment still carrying the old
    value inherited it; one carrying anything else was overridden.
    """
    if not instance.pk:
        setattr(instance, _OLD_VALUES_ATTR, None)
        return

    previous = sender.objects.filter(pk=instance.pk).values(*INHERITED_FIELDS).first()
    setattr(instance, _OLD_VALUES_ATTR, previous)


@receiver(post_save, sender=Teacher, dispatch_uid='faculty.sync_teacher_to_assignments')
def sync_teacher_to_assignments(sender, instance, created, **kwargs):
    """Push changed fields onto the assignments that had not overridden them."""
    if created:
        return

    previous = getattr(instance, _OLD_VALUES_ATTR, None)
    if not previous:
        return

    for field in INHERITED_FIELDS:
        old, new = previous[field], getattr(instance, field)
        if old == new:
            continue
        # Only rows still holding the old value; anything else is a
        # deliberate per-course override and is left alone. `update()` rather
        # than `save()` so `CourseInstructor.save()`'s blank-filling does not
        # run again over values we are setting explicitly.
        instance.assignments.filter(**{field: old}).update(**{field: new})


@receiver(post_save, sender=Teacher, dispatch_uid='faculty.sync_teacher_login')
def sync_teacher_login(sender, instance, created, **kwargs):
    """Push a newly linked login down onto the teacher's existing assignments.

    `CourseInstructor.save()` inherits `user` from its teacher, but only when
    the *assignment* is saved. A teacher is usually put on their courses first
    and given a login later, so without this the assignments made before the
    link keep a null `user` -- and those are exactly the courses the teacher
    then cannot open.

    Only fills blanks. An assignment pointing at a different account was set
    that way deliberately.
    """
    if instance.user_id is None:
        return
    instance.assignments.filter(user__isnull=True).update(user_id=instance.user_id)
