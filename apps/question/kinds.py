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
    uses_options: bool
    auto_graded: bool
    counts_each_part: bool = False
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

REGISTRY = {kind.value: kind for kind in (MCQ, CQ)}


def kind(question_type):
    """The registry entry, or a validation error rather than a `KeyError`."""
    try:
        return REGISTRY[question_type]
    except KeyError:
        raise ValidationError({"question_type": f"Unknown question type “{question_type}”."})
