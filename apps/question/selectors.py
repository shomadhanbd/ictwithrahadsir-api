from collections import defaultdict

from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q
from django.db.models.functions import Coalesce

from apps.academic.models import Chapter
from apps.core import providers
from apps.question.models import Question, QuestionBlock, QuestionOption, QuestionSet

PRACTICE_ROUND = 10
PRACTICE_MAX = 20
PUBLISHED_EXAM = "published"  # `exam.Exam.Status.PUBLISHED`; this app does not import exam


def admin_blocks():
    """Blocks in a fixed number of queries, questions correctly ordered."""
    questions = Question.objects.order_by("order_in_set", "id").prefetch_related("options")
    return (
        QuestionBlock.objects.select_related("subject", "chapter")
        .prefetch_related(
            "topics",
            "sources",
            Prefetch("question_set__questions", queryset=questions),
            Prefetch("standalone_question", queryset=questions),
        )
        .order_by(F("chapter__chapter_number").asc(nulls_last=True), "order_in_chapter", "id")
    )


def owning_block(*, block=None, question_set=None):
    """The block a question hangs off, whichever side of the xor it uses."""
    return block if block is not None else (question_set.block if question_set is not None else None)


def block_questions_by_id(block) -> dict:
    """The block's own questions, by id: its standalone question, or its stimulus set's parts."""
    if block.kind == QuestionBlock.Kind.GROUP:
        questions = Question.objects.filter(question_set__block=block)
    else:
        questions = Question.objects.filter(block=block)
    return {question.pk: question for question in questions.prefetch_related("options")}


def owning_block_id(block_id, question_set_id):
    if block_id:
        return block_id
    if question_set_id:
        return QuestionSet.objects.filter(pk=question_set_id).values_list("block_id", flat=True).first()
    return None


def exam_placement(block, *, published_only=False):
    """The first exam section this block is placed on, or None."""
    if block is None or block.pk is None:
        return None
    placements = block.exam_usages.select_related("section__exam")
    if published_only:
        placements = placements.filter(section__exam__status=PUBLISHED_EXAM)
    return placements.first()


def practice_blocks():
    """Active blocks in open chapters, minus any on a paper whose answers are not out yet."""
    blocks = QuestionBlock.objects.filter(
        is_active=True,
        chapter__is_active=True,
        chapter__practice_enabled=True,
        chapter__subject__is_active=True,
        chapter__subject__class_level__is_active=True,
    )
    unreleased = providers.get("question.unreleased_block_ids")
    if unreleased is not None:
        blocks = blocks.exclude(pk__in=unreleased())
    return blocks


def practice_questions():
    """MCQs with an answer key, standalone or inside a set, from practisable blocks."""
    blocks = practice_blocks()
    keyed = QuestionOption.objects.filter(question=OuterRef("pk"), is_correct=True)
    return (
        Question.objects.filter(question_type=Question.Type.MCQ)
        .filter(Q(block__in=blocks) | Q(question_set__block__in=blocks))
        .filter(Exists(keyed))
    )


def practice_tree() -> list[dict]:
    """Class levels, their subjects and chapters, each chapter with its practice question count."""
    counts = dict(
        practice_questions()
        .annotate(chapter_id=Coalesce("block__chapter_id", "question_set__block__chapter_id"))
        .values("chapter_id")
        .annotate(n=Count("pk"))
        .order_by()
        .values_list("chapter_id", "n")
    )
    chapters = Chapter.objects.filter(pk__in=counts).select_related("subject__class_level")
    levels: dict[int, dict] = {}
    for chapter in sorted(
        chapters,
        key=lambda c: (
            c.subject.class_level.order,
            c.subject.class_level.name,
            c.subject.order,
            c.subject.name,
            c.chapter_number,
            c.name,
        ),
    ):
        level = chapter.subject.class_level
        subjects = levels.setdefault(level.pk, {"level": level, "subjects": {}})["subjects"]
        subject = subjects.setdefault(chapter.subject.pk, {"subject": chapter.subject, "chapters": []})
        subject["chapters"].append({"chapter": chapter, "question_count": counts[chapter.pk]})
    return [{"level": entry["level"], "subjects": list(entry["subjects"].values())} for entry in levels.values()]


def practice_round(*, chapter_id, topic_id=None, count=PRACTICE_ROUND):
    """A random handful of practice MCQs from one chapter, optionally one topic."""
    in_chapter = Q(block__chapter_id=chapter_id) | Q(question_set__block__chapter_id=chapter_id)
    questions = practice_questions().filter(in_chapter)
    if topic_id:
        questions = questions.filter(Q(block__topics=topic_id) | Q(question_set__block__topics=topic_id))
    return list(
        questions.select_related("question_set")
        .prefetch_related("options")
        .order_by("?")[: max(1, min(count, PRACTICE_MAX))]
    )


def block_question_types(block_ids) -> dict:
    """`{block_id: {"mcq", "cq"}}` for every block that has any question."""
    rows = (
        Question.objects.filter(Q(block_id__in=block_ids) | Q(question_set__block_id__in=block_ids))
        .annotate(owner_block_id=Coalesce("block_id", "question_set__block_id"))
        .values_list("owner_block_id", "question_type")
        .distinct()
    )
    types = defaultdict(set)
    for block_id, question_type in rows:
        types[block_id].add(question_type)
    return types


def block_questions(block) -> list:
    """A block's questions in reading order: the standalone one, or the set's."""
    if block.kind == QuestionBlock.Kind.GROUP and getattr(block, "question_set", None) is not None:
        return list(block.question_set.questions.all())
    question = getattr(block, "standalone_question", None)
    return [question] if question is not None else []


def answer_keys(question_ids) -> dict[int, list[int]]:
    """`{question_id: [correct option ids]}`."""
    keys = defaultdict(list)
    rows = QuestionOption.objects.filter(question_id__in=question_ids, is_correct=True).values_list("id", "question_id")
    for option_id, question_id in rows:
        keys[question_id].append(option_id)
    return keys
