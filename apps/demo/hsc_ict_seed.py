import random

from apps.academic.models import Chapter, Subject, Topic
from apps.demo.builders import make_mcq
from apps.demo.hsc_ict import CHAPTERS, COMBINATIONS, SUBJECT_SLUG
from apps.question.models import QuestionBlock
from apps.question.services import refresh_curriculum_question_counts, save_block


def seed_hsc_ict(log=lambda message: None) -> bool:
    """Adds HSC ICT's six chapters, their topics and 20 MCQs each; chapters and questions already there are kept.

    False when the subject does not exist yet (`seed_curriculum` adds it)."""
    subject = Subject.objects.filter(slug=SUBJECT_SLUG).first()
    if subject is None:
        return False

    for number, data in enumerate(CHAPTERS, start=1):
        chapter, _ = Chapter.objects.get_or_create(
            subject=subject,
            chapter_number=number,
            defaults={"name": data["name"], "slug": f"{subject.slug}-ch{number}"},
        )
        if chapter.name != data["name"]:
            log(f"  chapter {number} is “{chapter.name}”; left as it is")
            continue

        topics = []
        for order, name in enumerate(data["topics"]):
            topic, _ = Topic.objects.get_or_create(
                chapter=chapter, name=name, defaults={"slug": f"{chapter.slug}-t{order + 1}", "order": order}
            )
            topics.append(topic)

        if chapter.question_blocks.exists():
            log(f"  chapter {number} already has questions")
            continue
        for index, (topic, prompt, choices, answer, explanation) in enumerate(data["questions"]):
            choices, answer = _shuffled(choices, answer, seed=f"{SUBJECT_SLUG}:{number}:{index}")
            block = save_block(
                None,
                {
                    "subject": subject,
                    "chapter": chapter,
                    "kind": QuestionBlock.Kind.STANDALONE,
                    "order_in_chapter": index,
                    "topics": [topics[topic]],
                },
            )
            make_mcq({"block": block}, prompt, choices, answer, explanation)
        log(f"  chapter {number}: {len(topics)} topics, {len(data['questions'])} questions")

    refresh_curriculum_question_counts()
    return True


def _shuffled(choices, answer, *, seed):
    """The choices in a fixed per-question order, so the key is not always ক; i/ii/iii choices keep theirs."""
    if choices == COMBINATIONS:
        return choices, answer
    order = list(range(len(choices)))
    random.Random(seed).shuffle(order)
    return [choices[i] for i in order], order.index(answer)
