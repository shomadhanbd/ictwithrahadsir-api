"""Reads over the question bank.

The practice topic list is the reason this file exists. It used to walk the
folder tree once per folder:

    for bank in QuestionBank.objects.all():
        count = bank.all_questions().count()

`all_questions()` issues one query per level of nesting, so the listing cost
one tree walk plus one COUNT for every folder in the bank -- and it grew with
the bank, which is the one thing a topic list is guaranteed to do.

`practice_banks_with_counts` answers the same question in two queries flat,
whatever the shape of the tree.
"""

from collections import defaultdict

from django.db.models import Count

from apps.assessment.models import Question, QuestionBank


def practice_banks_with_counts():
    """Folders that offer at least one question, each with its total.

    The total is inclusive: a parent folder counts everything in its
    descendants, which is what makes a subject-level topic playable rather
    than an empty shell above the chapters that hold the questions.
    """
    banks = list(QuestionBank.objects.all())

    # One query for the direct count per folder...
    direct = dict(
        Question.objects.values_list('bank_id').annotate(n=Count('id')).values_list('bank_id', 'n')
    )

    # ...then roll the counts up the tree in Python.
    children = defaultdict(list)
    for bank in banks:
        children[bank.parent_id].append(bank.id)

    totals = {}

    def total_for(bank_id):
        if bank_id in totals:
            return totals[bank_id]
        # Seed before recursing so a cycle in the data cannot spin forever.
        totals[bank_id] = 0
        running = direct.get(bank_id, 0)
        for child_id in children.get(bank_id, ()):
            running += total_for(child_id)
        totals[bank_id] = running
        return running

    playable = []
    for bank in banks:
        count = total_for(bank.id)
        if count:
            bank.question_count = count
            playable.append(bank)
    return playable
