from apps.academic.models import Batch, Chapter, ClassLevel, Group, Subject, Topic


def active_class_levels():
    return ClassLevel.objects.active()


def active_groups():
    return Group.objects.active()


def active_batches():
    return Batch.objects.active().select_related("class_level")


def admin_class_levels():
    return ClassLevel.objects.with_counts()


def admin_groups():
    return Group.objects.with_counts()


def admin_subjects():
    return Subject.objects.with_counts().select_related("class_level", "group")


def admin_chapters():
    return Chapter.objects.select_related("subject")


def admin_topics():
    return Topic.objects.select_related("chapter")


def admin_batches():
    return Batch.objects.select_related("class_level")
