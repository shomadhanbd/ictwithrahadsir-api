"""Operations on a profile that reach past the model."""


def ensure_teacher_role(profile) -> None:
    """Give a teacher's account the `teacher` role, unless they outrank it.

    The permission tier reads the role, not whether a `TeacherProfile` exists,
    so a roster entry means nothing until its account is in the group. Admins
    and moderators are skipped: `set_role` makes its argument the *only* role,
    so calling it on an admin would demote them.

    Role names as strings, so `profiles` stays free of an import of `identity`.
    """
    user = profile.user
    if user is None or user.has_role("admin", "moderator"):
        return
    user.set_role("teacher")
