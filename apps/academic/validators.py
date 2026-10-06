from django.core.exceptions import ValidationError


# `question_blocks` is the question app's reverse relation, read by name so this app does not import it.
def validate_chapter_subject_change(chapter, subject):
    if chapter is not None and subject != chapter.subject and chapter.question_blocks.exists():
        raise ValidationError("This chapter has questions, so it cannot move to another subject.")


def validate_topic_chapter_change(topic, chapter):
    if topic is not None and chapter != topic.chapter and topic.question_blocks.exists():
        raise ValidationError("Questions are tagged with this topic, so it cannot move chapter.")
