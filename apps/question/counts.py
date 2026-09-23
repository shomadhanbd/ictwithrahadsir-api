"""Recounts the curriculum's counters: questions, and subjects and chapters.

Run on demand -- `manage.py refresh_question_counts`, or the Question Bank's
"Refresh questions" button -- after questions or folders are added. Never on a
write, so adding one costs nothing extra; the counts are as fresh as the last run.

A question is counted once per block: a standalone question, or a stimulus
with all its parts.
"""

from django.db.models import Count

from apps.academic.models import Chapter, ClassLevel, Group, Subject, Topic

#: model -> {column: the path from a row to what it counts}
COUNTS = {
    ClassLevel: {"question_count": "subjects__question_blocks", "subject_count": "subjects"},
    Group: {"question_count": "subjects__question_blocks"},
    Subject: {"question_count": "question_blocks", "chapter_count": "chapters"},
    Chapter: {"question_count": "question_blocks"},
    Topic: {"question_count": "question_blocks"},
}


def refresh_question_counts() -> None:
    for model, columns in COUNTS.items():
        # One query per column: counting two to-many paths in one query would
        # multiply the joins together.
        fresh = {
            column: dict(model.objects.annotate(n=Count(path, distinct=True)).values_list("pk", "n"))
            for column, path in columns.items()
        }
        stale = []
        for row in model.objects.only("pk", *columns):
            changed = False
            for column in columns:
                if getattr(row, column) != fresh[column][row.pk]:
                    setattr(row, column, fresh[column][row.pk])
                    changed = True
            if changed:
                stale.append(row)
        model.objects.bulk_update(stale, list(columns), batch_size=500)
