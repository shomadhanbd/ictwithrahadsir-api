from apps.core import providers


def register():
    """Hands courses and question the exam reads they need without importing this app."""
    from apps.exam.selectors import assert_may_edit_placed_block, unreleased_block_ids
    from apps.exam.services.attempts import lesson_exam

    providers.register("courses.lesson_exam", lesson_exam)
    providers.register("question.unreleased_block_ids", unreleased_block_ids)
    providers.register("question.assert_may_edit_placed_block", assert_may_edit_placed_block)
