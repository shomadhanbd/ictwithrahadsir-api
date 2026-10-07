"""Small writers the demo seed commands share."""

from apps.question.models import Question
from apps.question.services import create_question

OPTION_LABELS = "কখগঘ"


def make_mcq(owner, prompt, options, answer, explanation) -> Question:
    """A single-answer MCQ under `owner` (`{"block": …}` or `{"question_set": …}`); `answer` indexes `options`."""
    return create_question(
        {
            **owner,
            "question_type": Question.Type.MCQ,
            "metadata": {"select_mode": "single"},
            "prompt_content": prompt,
            "explanation": explanation,
            "options": [
                {"label": label, "content": content, "is_correct": index == answer, "position": index}
                for index, (label, content) in enumerate(zip(OPTION_LABELS, options, strict=True))
            ],
        }
    )
