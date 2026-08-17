"""Contract tests for the exam-taking and ranking endpoints.

These cover the behaviour the client depends on: access gating, the exam
window, single submission, negative marking, and the leaderboard shape.
"""

from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.identity.models import User
from apps.courses.models import Content, Course, Enrollment, Section
from apps.assessment.models import Exam, ExamAttempt, Question, QuestionBank


def exam_url(pk):
    return reverse('api:assessment:v1:exam_detail', args=[pk])


def submission_url(pk):
    return reverse('api:assessment:v1:exam_submission', args=[pk])


def ranking_url(pk):
    return reverse('api:assessment:v1:exam_ranking', args=[pk])


class ExamTestBase(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            phone='01810100001', name='Student', password='Str0ngPass!23'
        )
        self.auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'
        }

        self.course = Course.objects.create(title='ICT', slug='ict')
        self.section = Section.objects.create(course=self.course, title='Ch1', slug='ict-ch1')
        self.store = QuestionBank.objects.create(title='Numbers')
        self.question = Question.objects.create(
            bank=self.store, question='2 + 2?', a='3', b='4', c='5', d='6', answer='b'
        )
        self.exam = Content.objects.create(
            course=self.course,
            section=self.section,
            title='Ch1 Exam',
            slug='ict-ch1-exam',
            type=Content.Type.EXAM,
            paid=True,
        )
        # Exam.pk is the Content pk, so `self.exam.pk` still addresses the
        # exam everywhere the URLs and payloads use it.
        self.exam_config = Exam.objects.create(
            content=self.exam,
            question_bank=self.store,
            total_marks=10,
            positive_marks=Decimal('1.00'),
            negative_marks=Decimal('0.25'),
        )

    def enrol(self, user=None):
        Enrollment.objects.create(
            course=self.course,
            user=user or self.student,
            valid_till=timezone.now() + timezone.timedelta(days=30),
        )


class ExamAccessTests(ExamTestBase):
    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get(exam_url(self.exam.pk)).status_code, 401)

    def test_unenrolled_student_cannot_open_a_paid_exam(self):
        response = self.client.get(exam_url(self.exam.pk), **self.auth)
        self.assertEqual(response.status_code, 403)

    def test_enrolled_student_gets_the_paper(self):
        self.enrol()
        response = self.client.get(exam_url(self.exam.pk), **self.auth)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body['id'], self.exam.pk)
        self.assertEqual(body['title'], 'Ch1 Exam')
        self.assertIsNone(body['result'])
        questions = body['question']['body']['sections'][0]['questions']
        self.assertEqual(len(questions), 1)

    def test_free_exam_needs_no_enrolment(self):
        self.exam.paid = False
        self.exam.save(update_fields=['paid'])
        self.assertEqual(self.client.get(exam_url(self.exam.pk), **self.auth).status_code, 200)

    def test_expired_enrolment_loses_access(self):
        Enrollment.objects.create(
            course=self.course,
            user=self.student,
            valid_till=timezone.now() - timezone.timedelta(days=1),
        )
        self.assertEqual(self.client.get(exam_url(self.exam.pk), **self.auth).status_code, 403)

    def test_unknown_exam_is_404(self):
        self.assertEqual(self.client.get(exam_url(999999), **self.auth).status_code, 404)

    def test_non_exam_content_is_not_reachable(self):
        video = Content.objects.create(
            course=self.course, section=self.section, title='Video',
            slug='ict-ch1-video', type=Content.Type.VIDEO, paid=False,
        )
        self.assertEqual(self.client.get(exam_url(video.pk), **self.auth).status_code, 404)


class AnswerKeyExposureTests(ExamTestBase):
    """The paper used to ship the correct option and explanation for every
    question, so any student could read the answers out of the network tab
    before submitting -- which also made the rankings meaningless."""

    def setUp(self):
        super().setUp()
        self.enrol()

    def questions(self):
        response = self.client.get(exam_url(self.exam.pk), **self.auth)
        self.assertEqual(response.status_code, 200)
        return response.json()['question']['body']['sections'][0]['questions']

    def test_the_answer_key_is_absent_before_submitting(self):
        question = self.questions()[0]
        for field in ('answer', 'answer_image', 'explanation'):
            self.assertNotIn(field, question, f'{field} leaked to an unsubmitted student')

    def test_the_question_itself_is_still_served(self):
        question = self.questions()[0]
        for field in ('id', 'question', 'a', 'b', 'c', 'd'):
            self.assertIn(field, question)
        self.assertEqual(question['b'], '4')

    def test_the_answer_key_is_returned_after_submitting(self):
        ExamAttempt.objects.create(exam=self.exam_config, user=self.student, marks=Decimal('1'))

        question = self.questions()[0]
        self.assertEqual(question['answer'], 'b')
        self.assertIn('explanation', question)

    def test_one_students_attempt_does_not_reveal_answers_to_another(self):
        ExamAttempt.objects.create(exam=self.exam_config, user=self.student, marks=Decimal('1'))

        classmate = User.objects.create_user(
            phone='01810100099', name='Classmate', password='Str0ngPass!23'
        )
        self.enrol(classmate)
        auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=classmate).key}'}

        response = self.client.get(exam_url(self.exam.pk), **auth)
        question = response.json()['question']['body']['sections'][0]['questions'][0]
        self.assertNotIn('answer', question)

    def test_the_serializer_fails_closed_without_context(self):
        # A new call site that forgets to opt in must not leak by default.
        from apps.assessment.api.v1.serializers import ExamMcqSerializer

        data = ExamMcqSerializer(self.question).data
        self.assertNotIn('answer', data)

    def test_admins_still_see_answers_in_the_question_bank(self):
        admin = User.objects.create_user(
            phone='01710100099', name='Admin', password='Str0ngPass!23',
            role=User.Role.ADMIN, is_staff=True,
        )
        auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}

        url = reverse('api:assessment:v1:admin-mcq-list')
        row = self.client.get(url, **auth).json()['data'][0]
        self.assertEqual(row['answer'], 'b')


class ResultPublishTimeTests(ExamTestBase):
    """`exam_result_publish_time` was stored and echoed back but never
    checked, so the answer key and the leaderboard were readable the moment
    an attempt was submitted regardless of the configured embargo."""

    def setUp(self):
        super().setUp()
        self.enrol()
        ExamAttempt.objects.create(exam=self.exam_config, user=self.student, marks=Decimal('1'))

    def embargo(self):
        self.exam_config.result_publish_time = timezone.now() + timezone.timedelta(days=1)
        self.exam_config.save(update_fields=['result_publish_time'])

    def publish(self):
        self.exam_config.result_publish_time = timezone.now() - timezone.timedelta(minutes=1)
        self.exam_config.save(update_fields=['result_publish_time'])

    def test_an_unset_publish_time_means_no_embargo(self):
        self.assertIsNone(self.exam_config.result_publish_time)
        body = self.client.get(exam_url(self.exam.pk), **self.auth).json()
        self.assertTrue(body['result_published'])
        self.assertIn('answer', body['question']['body']['sections'][0]['questions'][0])

    def test_the_answer_key_stays_hidden_before_the_publish_time(self):
        self.embargo()
        body = self.client.get(exam_url(self.exam.pk), **self.auth).json()
        self.assertFalse(body['result_published'])
        self.assertNotIn('answer', body['question']['body']['sections'][0]['questions'][0])

    def test_the_answer_key_appears_once_published(self):
        self.publish()
        body = self.client.get(exam_url(self.exam.pk), **self.auth).json()
        self.assertTrue(body['result_published'])
        self.assertIn('answer', body['question']['body']['sections'][0]['questions'][0])

    def test_the_caller_still_sees_their_own_result_under_embargo(self):
        self.embargo()
        body = self.client.get(exam_url(self.exam.pk), **self.auth).json()
        self.assertIsNotNone(body['result'])

    def test_the_leaderboard_is_withheld_before_the_publish_time(self):
        self.embargo()
        body = self.client.get(ranking_url(self.exam.pk), **self.auth).json()
        self.assertEqual(body['rankings'], [])
        self.assertIsNone(body['user_rank'])
        self.assertFalse(body['result_published'])
        # Shape is preserved so the client degrades to an empty board.
        self.assertEqual(body['exam_title'], 'Ch1 Exam')

    def test_the_leaderboard_appears_once_published(self):
        self.publish()
        body = self.client.get(ranking_url(self.exam.pk), **self.auth).json()
        self.assertEqual(len(body['rankings']), 1)
        self.assertEqual(body['user_rank'], 1)
        self.assertTrue(body['result_published'])


class ExamWindowTests(ExamTestBase):
    def setUp(self):
        super().setUp()
        self.enrol()

    def test_exam_before_its_start_time_is_refused(self):
        self.exam_config.start_time = timezone.now() + timezone.timedelta(hours=1)
        self.exam_config.save(update_fields=['start_time'])
        self.assertEqual(self.client.get(exam_url(self.exam.pk), **self.auth).status_code, 403)

    def test_exam_after_its_end_time_is_refused(self):
        self.exam_config.end_time = timezone.now() - timezone.timedelta(hours=1)
        self.exam_config.save(update_fields=['end_time'])
        self.assertEqual(self.client.get(exam_url(self.exam.pk), **self.auth).status_code, 403)

    def test_practice_mode_ignores_the_window(self):
        self.exam_config.mode = Exam.Mode.PRACTICE
        self.exam_config.end_time = timezone.now() - timezone.timedelta(hours=1)
        self.exam_config.save(update_fields=['mode', 'end_time'])
        self.assertEqual(self.client.get(exam_url(self.exam.pk), **self.auth).status_code, 200)


class ExamSubmissionTests(ExamTestBase):
    def setUp(self):
        super().setUp()
        self.enrol()

    def submit(self, user_answer, duration=60):
        return self.client.post(
            submission_url(self.exam.pk),
            {
                'duration': duration,
                'sections': [
                    {'answers': [{'mcq_id': self.question.pk, 'user_answer': user_answer}]}
                ],
            },
            format='json',
            **self.auth,
        )

    def test_correct_answer_scores_the_positive_mark(self):
        response = self.submit('b')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Decimal(response.json()['marks']), Decimal('1.00'))

    def test_wrong_answer_applies_negative_marking(self):
        response = self.submit('a')
        self.assertEqual(Decimal(response.json()['marks']), Decimal('-0.25'))

    def test_answer_matching_is_case_insensitive(self):
        self.assertEqual(Decimal(self.submit('B').json()['marks']), Decimal('1.00'))

    def test_blank_answer_neither_scores_nor_penalises(self):
        self.assertEqual(Decimal(self.submit('').json()['marks']), Decimal('0'))

    def test_an_exam_can_only_be_submitted_once(self):
        self.assertEqual(self.submit('b').status_code, 201)
        self.assertEqual(self.submit('b').status_code, 422)
        self.assertEqual(ExamAttempt.objects.filter(exam=self.exam_config).count(), 1)

    def test_sections_must_be_a_list(self):
        response = self.client.post(
            submission_url(self.exam.pk), {'sections': 'nope'}, format='json', **self.auth
        )
        self.assertEqual(response.status_code, 422)

    def test_submitting_returns_the_stored_result(self):
        self.submit('b', duration=125)
        result = ExamAttempt.objects.get(exam=self.exam_config, user=self.student)
        self.assertEqual(result.duration, 125)
        self.assertTrue(result.submitted)


class ExamRankingTests(ExamTestBase):
    def setUp(self):
        super().setUp()
        self.enrol()
        self.rival = User.objects.create_user(
            phone='01810100002', name='Rival', password='Str0ngPass!23'
        )
        ExamAttempt.objects.create(
            exam=self.exam_config, user=self.rival, marks=Decimal('9'), duration=100
        )
        ExamAttempt.objects.create(
            exam=self.exam_config, user=self.student, marks=Decimal('5'), duration=100
        )

    def test_ranking_is_ordered_by_marks(self):
        response = self.client.get(ranking_url(self.exam.pk), **self.auth)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body['exam_title'], 'Ch1 Exam')
        self.assertEqual(body['user_rank'], 2)
        self.assertEqual(len(body['rankings']), 2)

    def test_caller_without_a_result_has_no_rank(self):
        outsider = User.objects.create_user(
            phone='01810100003', name='Outsider', password='Str0ngPass!23'
        )
        auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=outsider).key}'}
        body = self.client.get(ranking_url(self.exam.pk), **auth).json()
        self.assertIsNone(body['user_rank'])
        self.assertIsNone(body['user_result'])


class AdminExamAttemptTests(ExamTestBase):
    def setUp(self):
        super().setUp()
        admin = User.objects.create_user(
            phone='01710100001', name='Admin', password='Str0ngPass!23',
            role=User.Role.ADMIN, is_staff=True,
        )
        self.admin_auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'
        }
        ExamAttempt.objects.create(exam=self.exam_config, user=self.student, marks=Decimal('7'))

    def test_students_are_refused(self):
        url = reverse('api:assessment:v1:admin_exam_results')
        self.assertEqual(self.client.get(url, **self.auth).status_code, 403)

    def test_results_are_paginated(self):
        url = reverse('api:assessment:v1:admin_exam_results')
        body = self.client.get(url, **self.admin_auth).json()
        self.assertEqual(body['meta']['total'], 1)

    def test_results_filter_by_exam(self):
        url = reverse('api:assessment:v1:admin_exam_results')
        body = self.client.get(url, {'exam_id': 999999}, **self.admin_auth).json()
        self.assertEqual(body['meta']['total'], 0)


class AdminQuestionBankTests(ExamTestBase):
    def setUp(self):
        super().setUp()
        admin = User.objects.create_user(
            phone='01710100002', name='Admin', password='Str0ngPass!23',
            role=User.Role.ADMIN, is_staff=True,
        )
        self.admin_auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'
        }
        self.child = QuestionBank.objects.create(title='Binary', parent=self.store)

    def test_list_returns_only_top_level_folders(self):
        url = reverse('api:assessment:v1:admin-mcq-store-list')
        body = self.client.get(url, **self.admin_auth).json()
        titles = [row['title'] for row in body['data']]
        self.assertIn('Numbers', titles)
        self.assertNotIn('Binary', titles)

    def test_children_are_listed_by_parent_id(self):
        url = reverse('api:assessment:v1:admin-mcq-store-list')
        body = self.client.get(url, {'mcq_store_id': self.store.pk}, **self.admin_auth).json()
        self.assertEqual([row['title'] for row in body['data']], ['Binary'])

    def test_questions_filter_by_folder(self):
        url = reverse('api:assessment:v1:admin-mcq-list')
        body = self.client.get(url, {'mcq_store_id': self.store.pk}, **self.admin_auth).json()
        self.assertEqual(body['meta']['total'], 1)


class PracticeQuizTests(APITestCase):
    """The MCQ bank was reachable only inside a scheduled exam, so the one
    piece of content that would persuade a visitor to pay was invisible to
    anyone who had not already paid."""

    TOPICS_URL = reverse('api:assessment:v1:practice_topics')
    QUESTIONS_URL = reverse('api:assessment:v1:practice_questions')

    def setUp(self):
        self.root = QuestionBank.objects.create(title='ICT bank')
        self.chapter = QuestionBank.objects.create(title='Number systems', parent=self.root)
        self.empty = QuestionBank.objects.create(title='Empty chapter')
        for i in range(6):
            Question.objects.create(
                bank=self.chapter, question=f'Q{i}', a='1', b='2', c='3', d='4',
                answer='b', explanation='Because.',
            )

    def test_topics_are_public(self):
        response = self.client.get(self.TOPICS_URL)
        self.assertEqual(response.status_code, 200)
        titles = [b['title'] for b in response.data['data']]
        self.assertIn('Number systems', titles)

    def test_a_parent_topic_counts_its_descendants(self):
        response = self.client.get(self.TOPICS_URL)
        root = next(b for b in response.data['data'] if b['title'] == 'ICT bank')
        self.assertEqual(root['question_count'], 6)

    def test_an_empty_topic_is_not_offered(self):
        response = self.client.get(self.TOPICS_URL)
        self.assertNotIn('Empty chapter', [b['title'] for b in response.data['data']])

    def test_questions_are_public_and_carry_the_answer(self):
        response = self.client.get(self.QUESTIONS_URL)
        self.assertEqual(response.status_code, 200)
        question = response.data['data'][0]
        self.assertIn('answer', question)
        self.assertIn('explanation', question)

    def test_the_sample_is_capped(self):
        """The answers are included, so the cap is what stops the whole bank
        being lifted in one request."""
        response = self.client.get(self.QUESTIONS_URL, {'limit': 500})
        self.assertLessEqual(len(response.data['data']), 20)

    def test_a_topic_filters_the_sample(self):
        other = QuestionBank.objects.create(title='Other')
        Question.objects.create(
            bank=other, question='Stranger', a='1', b='2', answer='a',
        )
        response = self.client.get(self.QUESTIONS_URL, {'bank_id': self.chapter.pk, 'limit': 20})
        self.assertNotIn('Stranger', [q['question'] for q in response.data['data']])

    def test_an_unknown_topic_is_a_404(self):
        response = self.client.get(self.QUESTIONS_URL, {'bank_id': 999999})
        self.assertEqual(response.status_code, 404)

    def test_a_junk_limit_falls_back_to_the_default(self):
        response = self.client.get(self.QUESTIONS_URL, {'limit': 'lots'})
        self.assertLessEqual(len(response.data['data']), 10)
