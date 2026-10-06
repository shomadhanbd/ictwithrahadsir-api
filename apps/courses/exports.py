from apps.core.api.views.exports import local_stamp

STUDENT_EXPORT_HEADER = [
    "Name",
    "Phone",
    "Email",
    "Enrolled at",
    "Access until",
    "Status",
    "Payment type",
    "Progress %",
]


def student_export_rows(rows):
    for row in rows:
        enrollment = row["enrollment"]
        user = enrollment.user
        yield [
            user.name,
            user.phone or "",
            user.email or "",
            local_stamp(enrollment.created_at),
            local_stamp(enrollment.valid_till) or "Lifetime",
            enrollment.status.title(),
            enrollment.get_payment_type_display(),
            row["progress"],
        ]
