"""What each kind of question *is*, in one place.

The bank ships MCQ and creative questions, and the source design lists six more
— fill-in-the-blank, ordering, short and long answer, flow chart,
transformation. Adding one must be an entry in this registry, not a new
`if question_type == ...` in every module that touches a question.

Two things the registry settles that a bare enum cannot:

* **Whether a machine can mark it.** `section_marking` used to read
  `!= MCQ` to mean "cannot be auto-marked", which would silently drop negative
  marking for fill-in-the-blank and ordering — both of which grade
  automatically. That is `auto_graded` here.
* **Where a type's own configuration lives.** `select_mode` was a column on the
  shared `Question` table, meaningful only to MCQ. Do that eight times and the
  table is mostly NULLs. Per-type settings go in `Question.metadata`, and the
  shape each type allows is declared below.

`metadata` is a payload, never a filter: `JSONField__contains` raises
`NotSupportedError` on SQLite, which is dev and the whole test suite. Anything
that has to be queried stays a column.
"""

from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class MetadataField:
    """One per-type setting: what it may be, and what it is when unset."""

    default: Any
    choices: tuple = ()


@dataclass(frozen=True)
class QuestionKind:
    value: str
    label: str
    #: Does it hang `QuestionOption` rows off itself?
    uses_options: bool
    #: Can a machine decide whether an answer is right? Drives negative
    #: marking, and later the grader.
    auto_graded: bool
    #: In a group block, is each part its own question on the paper? Each MCQ
    #: under a passage (উদ্দীপক) is answered and marked separately, so three of
    #: them are three questions. The ক/খ/গ/ঘ of one সৃজনশীল are one 10-mark
    #: question, not four. Drives what a block counts and costs on a section.
    counts_each_part: bool = False
    #: What `QuestionOption.position` and `.is_correct` mean for this type,
    #: because they do not mean the same thing for all of them.
    option_meaning: str = ""
    metadata: dict = field(default_factory=dict)


MCQ = QuestionKind(
    value="mcq",
    label="MCQ",
    uses_options=True,
    auto_graded=True,
    counts_each_part=True,
    option_meaning="One row per choice; `is_correct` marks the answer key.",
    metadata={
        "select_mode": MetadataField(default="single", choices=("single", "multiple")),
    },
)

CQ = QuestionKind(
    value="cq",
    label="Creative Question",
    uses_options=False,
    auto_graded=False,
    option_meaning="None — a creative answer is prose, marked by a teacher.",
)

#: Ordered as they should be offered. Adding a type is an entry here plus a
#: member on `Question.Type`; nothing else should need to change.
REGISTRY = {kind.value: kind for kind in (MCQ, CQ)}


def kind(question_type):
    """The registry entry, or a clear failure rather than a `KeyError`."""
    try:
        return REGISTRY[question_type]
    except KeyError:
        raise ValidationError({"question_type": f"Unknown question type “{question_type}”."})


def choices():
    """`TextChoices`-shaped, so the model and the registry cannot drift."""
    return [(entry.value, entry.label) for entry in REGISTRY.values()]


def clean_metadata(question_type, data):
    """Normalise one question's per-type settings.

    Unknown keys are refused rather than stored: a typo that silently persists
    is how a setting comes to exist in the database and nowhere in the code.
    """
    entry = kind(question_type)
    data = data or {}

    if not isinstance(data, dict):
        raise ValidationError({"metadata": "Settings must be an object."})

    unknown = sorted(set(data) - set(entry.metadata))
    if unknown:
        raise ValidationError({"metadata": f"{entry.label} has no setting called “{unknown[0]}”."})

    cleaned = {}
    for name, spec in entry.metadata.items():
        value = data.get(name, spec.default)
        if spec.choices and value not in spec.choices:
            raise ValidationError({"metadata": f"“{name}” must be one of {', '.join(spec.choices)}."})
        cleaned[name] = value
    return cleaned
