from apps.profiles.models import TeacherProfile


def admin_teachers():
    return TeacherProfile.objects.roster()


def teacher_options():
    """Every teacher, for the course teacher picker."""
    return TeacherProfile.objects.select_related("user")
