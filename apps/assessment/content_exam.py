"""Flat `exam_*` compatibility for the admin content endpoint.

The admin panel reads and writes ten flat `exam_*` keys on
`/api/admin/contents/`. Those names are contract, but the fields now
live on `assessment.Exam` rather than on `courses.Content`.

The knowledge sits here rather than in `courses` so the courses serializer
does not have to know how an exam is stored -- it just delegates.
"""

from decimal import Decimal

from apps.assessment.models import Exam

#: flat API key -> Exam field
FIELD_MAP = {
    'exam_store_id': 'question_bank_id',
    'exam_mode': 'mode',
    'exam_total_marks': 'total_marks',
    'exam_pass_marks': 'pass_marks',
    'exam_positive_marks': 'positive_marks',
    'exam_negative_marks': 'negative_marks',
    'exam_duration_minutes': 'duration_minutes',
    'exam_start_time': 'start_time',
    'exam_end_time': 'end_time',
    'exam_result_publish_time': 'result_publish_time',
}

#: What a Content with no Exam row must still report.
#:
#: These used to be Django field defaults on Content, so *every* content --
#: a video included -- reported exam_mode="exam" and 1.00/0.00. Emitting
#: nulls instead would be a visible change to the admin payload, so the
#: defaults are reproduced verbatim.
DEFAULTS = {
    'exam_store_id': None,
    'exam_mode': Exam.Mode.EXAM,
    'exam_total_marks': None,
    'exam_pass_marks': None,
    'exam_positive_marks': Decimal('1'),
    'exam_negative_marks': Decimal('0'),
    'exam_duration_minutes': None,
    'exam_start_time': None,
    'exam_end_time': None,
    'exam_result_publish_time': None,
}


def read_exam_fields(content):
    """The flat `exam_*` values for `content`, defaults if it has no Exam."""
    exam = getattr(content, 'exam', None)
    if exam is None:
        return dict(DEFAULTS)
    return {key: getattr(exam, attr) for key, attr in FIELD_MAP.items()}


def write_exam_fields(content, values):
    """Persist the flat `exam_*` values against `content`'s Exam row.

    The row is created for any content marked as an exam, even when every
    field is still empty, so the admin panel can fill them in over several
    saves. It is never deleted when the type changes away -- an orphan is
    harmless and keeps the configuration if the type is flipped back.
    """
    from apps.courses.models import Content

    if not values and content.type != Content.Type.EXAM:
        return

    defaults = {FIELD_MAP[key]: value for key, value in values.items() if key in FIELD_MAP}
    exam, _ = Exam.objects.update_or_create(content=content, defaults=defaults)

    # Point `content.exam` at what was just written. `read_exam_fields` runs
    # immediately afterwards to build the response, and if `content` was
    # loaded with `select_related('exam')` it is carrying a cached relation
    # from before this write -- so the caller would be answered with the
    # values it just replaced.
    content.exam = exam
