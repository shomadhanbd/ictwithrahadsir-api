"""Who may manage user accounts.

`IsAdminRole` -- the gate on every `/admin/*` endpoint -- admits instructors
as well as admins, because instructors need to manage teaching material. User
accounts are not teaching material, so `/admin/users/` needs a second layer:

    an instructor may create and edit students, and nothing else.

These rules used to live in `AdminUserSerializer.validate_role` and
`.validate`. That was the wrong layer. A serializer is only built for create
and update, so `destroy()` bypassed the guards entirely and an instructor
could:

    DELETE /api/v1/admin/users/<any-admin-pk>/   ->  204

Orders, payments, enrolments and exam attempts all cascade off `user`, so the
same call aimed at a student erased that student's whole payment and exam
history along with the row.

Written as a permission, the rules run on every method.
"""

from rest_framework.permissions import SAFE_METHODS

from apps.core.api.permissions import IsTeachingStaff, is_full_admin
from apps.identity.models import User

#: Roles an instructor may neither hand out nor edit. Handing one out is
#: self-promotion; editing an account that holds one is account takeover (an
#: instructor could reset an admin's password and sign in as them).
PRIVILEGED_ROLES = {User.Role.ADMIN, User.Role.INSTRUCTOR}


class CanManageUsers(IsTeachingStaff):
    """`/admin/users/` -- admins fully, teachers for students only.

    Built on `IsTeachingStaff` rather than the panel-wide gate so that
    moderators are excluded outright: the content desk has no business in
    student accounts, and inheriting the wider gate would have handed it to
    them the moment the role was added.
    """

    message = "Only an admin may manage this account."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        # Create and update carry the target role in the body, and there is
        # no object yet to check on create -- so the role being *assigned* is
        # checked here, and the role the target *already holds* below.
        if request.data.get("role") in PRIVILEGED_ROLES:
            return is_full_admin(request.user)
        # `is_active` is the block/unblock switch. Setting it from the body
        # would otherwise be a way around the DELETE rule below, which is the
        # same act by another route.
        if "is_active" in request.data:
            return is_full_admin(request.user)
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS or is_full_admin(request.user):
            return True
        if obj.role in PRIVILEGED_ROLES:
            return False
        # Deactivating an account cuts off a paying student's access, so it
        # stays an admin decision even when the student is an instructor's
        # own. (`destroy` deactivates rather than deletes -- see the viewset.)
        return request.method != "DELETE"
