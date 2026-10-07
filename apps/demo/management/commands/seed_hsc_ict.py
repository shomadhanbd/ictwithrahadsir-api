import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academic.models import Chapter, Subject, Topic
from apps.demo.builders import make_mcq
from apps.demo.hsc_ict import CHAPTERS, COMBINATIONS, SUBJECT_SLUG
from apps.question.models import QuestionBlock
from apps.question.services import refresh_curriculum_question_counts, save_block


class Command(BaseCommand):
    help = "Add HSC ICT's six chapters, their topics and 20 MCQs each; safe to run again."

    @transaction.atomic
    def handle(self, *args, **options):
        subject = Subject.objects.filter(slug=SUBJECT_SLUG).first()
        if subject is None:
            raise CommandError(f"No subject “{SUBJECT_SLUG}”; run `manage.py seed_curriculum` first.")

        for number, data in enumerate(CHAPTERS, start=1):
            chapter, _ = Chapter.objects.get_or_create(
                subject=subject,
                chapter_number=number,
                defaults={"name": data["name"], "slug": f"{subject.slug}-ch{number}"},
            )
            if chapter.name != data["name"]:
                self.stdout.write(self.style.WARNING(f"  chapter {number} is “{chapter.name}”; left as it is"))
                continue

            topics = []
            for order, name in enumerate(data["topics"]):
                topic, _ = Topic.objects.get_or_create(
                    chapter=chapter, name=name, defaults={"slug": f"{chapter.slug}-t{order + 1}", "order": order}
                )
                topics.append(topic)

            if chapter.question_blocks.exists():
                self.stdout.write(f"  chapter {number} already has questions")
                continue
            for index, (topic, prompt, choices, answer, explanation) in enumerate(data["questions"]):
                choices, answer = self._shuffled(choices, answer, seed=f"{SUBJECT_SLUG}:{number}:{index}")
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
            self.stdout.write(f"  chapter {number}: {len(topics)} topics, {len(data['questions'])} questions")

        refresh_curriculum_question_counts()
        self.stdout.write(self.style.SUCCESS("HSC ICT ready."))

    @staticmethod
    def _shuffled(choices, answer, *, seed):
        """The choices in a fixed per-question order, so the key is not always ক; i/ii/iii choices keep theirs."""
        if choices == COMBINATIONS:
            return choices, answer
        order = list(range(len(choices)))
        random.Random(seed).shuffle(order)
        return [choices[i] for i in order], order.index(answer)
