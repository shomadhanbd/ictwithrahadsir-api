from apps.core.api.views.exports import local_stamp

RESULT_COLUMNS = [
    "Rank",
    "Name",
    "Phone",
    "Attempt",
    "Status",
    "Score",
    "Total marks",
    "Correct",
    "Wrong",
    "Skipped",
    "Time taken",
    "Submitted at",
]


def clock(seconds) -> str:
    return "" if seconds is None else f"{seconds // 60}:{seconds % 60:02d}"


def result_rows(exam, attempts, *, ranks):
    for attempt in attempts:
        yield [
            ranks.get(attempt.pk, ""),
            attempt.user.name,
            attempt.user.phone,
            "Official" if attempt.is_official else f"Practice #{attempt.number}",
            attempt.get_status_display(),
            "" if attempt.score is None else attempt.score,
            exam.total_marks,
            attempt.correct,
            attempt.wrong,
            attempt.skipped,
            clock(attempt.time_taken_seconds),
            local_stamp(attempt.submitted_at),
        ]
