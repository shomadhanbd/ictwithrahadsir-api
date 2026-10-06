from django.urls import reverse

from rest_framework.test import APITestCase

from apps.academic.models import Batch, ClassLevel, Group
from apps.billing.models import Payment, Product
from apps.core.testing import bearer, make_user, next_slug
from apps.courses.models import (
    Content,
    Course,
    CourseTeacher,
    Enrollment,
    Section,
)
from apps.identity.models import User


class AdminCourseProfileTests(APITestCase):
    def setUp(self):
        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)
        self.url = reverse('api:courses:admin_course_list')

    def post(self, **data):
        return self.client.post(
            self.url, {'title': 'Physics', 'slug': next_slug('course'), **data}, format='json', **self.auth
        )

    def test_creates_a_full_course_profile(self):
        response = self.post(
            status='published',
            delivery='hybrid',
            learning_outcomes=[{'title': 'Solve board questions', 'icon': 'target'}],
            target_audience=[{'title': 'HSC 2027 candidates'}],
            requirements=[{'title': 'A smartphone'}],
            highlights=[{'title': 'Live classes', 'description': 'Twice a week.', 'icon': 'video'}],
            faqs=[{'question': 'Recorded?', 'answer': 'Yes.'}],
            starts_on='2026-11-01',
            ends_on='2027-04-30',
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIsNotNone(body['published_at'])
        self.assertEqual(body['enrolled_count'], 0)

    def test_rejects_malformed_list_items(self):
        bad = {
            'learning_outcomes': [{'title': 'X', 'icon': 'https://evil.example/x.svg'}],
            'faqs': [{'question': 'Q?'}],
            'target_audience': [{'title': f'T{i}'} for i in range(21)],
            'highlights': [{'title': 'X', 'description': 'Y', 'icon': 'video', 'colour': 'red'}],
        }
        for field, value in bad.items():
            response = self.post(**{field: value})
            self.assertEqual(response.status_code, 422, field)
            self.assertIn(field, response.json()['errors'], field)

    def test_a_highlight_needs_an_icon_but_not_a_description(self):
        self.assertEqual(self.post(highlights=[{'title': 'Support group', 'icon': 'users'}]).status_code, 201)
        response = self.post(highlights=[{'title': 'Support group', 'description': 'Ask anytime.'}])
        self.assertEqual(response.status_code, 422)
        self.assertIn('highlights', response.json()['errors'])

    def test_rejects_an_end_before_the_start(self):
        response = self.post(starts_on='2027-01-01', ends_on='2026-12-01')
        self.assertEqual(response.status_code, 422)
        self.assertIn('ends_on', response.json()['errors'])

    def test_the_model_rejects_the_same_input(self):
        from django.core.exceptions import ValidationError

        course = Course(title='X', faqs=[{'question': 'Q?'}])
        with self.assertRaises(ValidationError) as caught:
            course.full_clean()
        self.assertIn('faqs', caught.exception.message_dict)


class AdminCourseAudienceTests(APITestCase):
    def setUp(self):
        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)
        self.hsc = ClassLevel.objects.create(name='HSC', slug='hsc')
        self.ssc = ClassLevel.objects.create(name='SSC', slug='ssc')
        self.science = Group.objects.create(name='Science', slug='science')
        self.ssc_2027 = Batch.objects.create(slug=next_slug("batch"), name='SSC-2027', class_level=self.ssc)
        self.url = reverse('api:courses:admin_course_list')

    def test_creates_a_targeted_course(self):
        response = self.client.post(
            self.url,
            {'title': 'Physics', 'slug': 'physics', 'class_level_id': self.hsc.id, 'group_id': self.science.id},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['class_level_name'], 'HSC')
        self.assertEqual(response.json()['group_name'], 'Science')

    def test_rejects_group_without_level(self):
        response = self.client.post(
            self.url, {'title': 'X', 'slug': 'x', 'group_id': self.science.id}, format='json', **self.auth
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn('group_id', str(response.content))

    def test_rejects_batch_from_another_level(self):
        course = Course.objects.create(slug=next_slug("course"), title='Physics', class_level=self.hsc)
        response = self.client.patch(
            reverse('api:courses:admin_course_detail', args=[course.pk]),
            {'batch_id': self.ssc_2027.id},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn('batch_id', str(response.content))

    def test_admin_list_filters_by_level(self):
        Course.objects.create(slug=next_slug("course"), title='HSC', class_level=self.hsc)
        Course.objects.create(slug=next_slug("course"), title='Open')
        body = self.client.get(self.url, {'class_level_id': self.hsc.id}, **self.auth).json()
        self.assertEqual([c['title'] for c in body['data']], ['HSC'])


class AdminSlugTests(APITestCase):
    """The admin panel types slugs; a blank one is still generated."""

    def setUp(self):
        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)

    def create(self, **body):
        return self.client.post('/api/private/courses/', {'title': 'এইচএসসি আইসিটি', **body}, **self.auth)

    def test_a_typed_slug_is_stored(self):
        response = self.create(slug='hsc-ict')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Course.objects.get().slug, 'hsc-ict')

    def test_a_blank_slug_is_refused(self):
        response = self.create(slug='')

        self.assertEqual(response.status_code, 422)
        self.assertIn('slug', response.json()['errors'])

    def test_a_taken_slug_is_rejected(self):
        self.create(slug='hsc-ict')
        response = self.create(slug='hsc-ict')

        self.assertEqual(response.status_code, 422)
        self.assertIn('slug', response.json()['errors'])

    def test_a_bangla_slug_is_rejected(self):
        response = self.create(slug='আইসিটি')

        self.assertEqual(response.status_code, 422)
        self.assertIn('slug', response.json()['errors'])

    def test_the_slug_can_be_changed(self):
        self.create(slug='hsc-ict')
        response = self.client.patch(
            f'/api/private/courses/{Course.objects.get().pk}/', {'slug': 'hsc-ict-2026'}, format='json', **self.auth
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Course.objects.get().slug, 'hsc-ict-2026')


class AdminSectionOrderTests(APITestCase):
    def setUp(self):
        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)
        self.course = Course.objects.create(title='ICT', slug='ict-order')

    def create(self, title, **body):
        body = {'course_id': self.course.pk, 'title': title, 'slug': next_slug('section'), **body}
        return self.client.post('/api/private/sections/', body, format='json', **self.auth)

    def titles(self):
        return list(Section.objects.filter(course=self.course, section=None).values_list('title', flat=True))

    def move(self, title, direction):
        section = Section.objects.get(title=title)
        return self.client.post(
            f'/api/private/sections/{section.pk}/move/', {'direction': direction}, format='json', **self.auth
        )

    def test_a_section_cannot_be_moved_to_another_course(self):
        """Its lessons would stay behind: the new course's students locked out, the old one's let in."""
        self.create('Chapter')
        section = Section.objects.get(title='Chapter')
        lesson = Content.objects.create(course=self.course, section=section, title='L', slug='moving-l', type='video')
        other = Course.objects.create(title='Other', slug='other-course')

        response = self.client.patch(
            f'/api/private/sections/{section.pk}/', {'course_id': other.pk}, format='json', **self.auth
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn('course_id', response.json()['errors'])
        section.refresh_from_db()
        lesson.refresh_from_db()
        self.assertEqual((section.course_id, lesson.course_id), (self.course.pk, self.course.pk))

    def test_a_section_can_still_be_renamed_with_its_course_resent(self):
        self.create('Chapter')
        section = Section.objects.get(title='Chapter')
        response = self.client.patch(
            f'/api/private/sections/{section.pk}/',
            {'course_id': self.course.pk, 'title': 'Renamed'},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_a_new_section_goes_last(self):
        for title in ('অধ্যায় ১', 'অধ্যায় ২', 'অধ্যায় ৩'):
            self.assertEqual(self.create(title).status_code, 201)
        self.assertEqual(self.titles(), ['অধ্যায় ১', 'অধ্যায় ২', 'অধ্যায় ৩'])

    def test_moving_swaps_with_the_neighbour(self):
        for title in ('A', 'B', 'C'):
            self.create(title)
        self.assertEqual(self.move('C', 'up').status_code, 200)
        self.assertEqual(self.titles(), ['A', 'C', 'B'])
        self.move('A', 'up')
        self.assertEqual(self.titles(), ['A', 'C', 'B'])
        self.move('A', 'down')
        self.assertEqual(self.titles(), ['C', 'A', 'B'])

    def test_a_sub_section_moves_among_its_own_siblings(self):
        self.create('Chapter')
        parent = Section.objects.get(title='Chapter')
        for title in ('Part 1', 'Part 2'):
            self.create(title, section_id=parent.pk)
        self.move('Part 2', 'up')
        children = Section.objects.filter(section=parent).values_list('title', flat=True)
        self.assertEqual(list(children), ['Part 2', 'Part 1'])
        self.assertEqual(self.titles(), ['Chapter'])

    def test_a_routine_link_must_be_a_web_address(self):
        body = {'course_id': self.course.pk, 'title': 'Routine'}
        bad = self.client.post('/api/private/routines/', {**body, 'link': 'routine.pdf'}, format='json', **self.auth)
        self.assertEqual(bad.status_code, 422)
        good = self.client.post(
            '/api/private/routines/', {**body, 'link': 'https://drive.google.com/x'}, format='json', **self.auth
        )
        self.assertEqual(good.status_code, 201)


class AdminContentToggleTests(APITestCase):
    def setUp(self):
        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)
        course = Course.objects.create(title='ICT', slug='ict')
        section = Section.objects.create(course=course, title='Ch1', slug='ict-ch1')
        self.content = Content.objects.create(
            course=course,
            section=section,
            title='Lesson',
            slug='ict-lesson',
            type=Content.Type.VIDEO,
            active=True,
            paid=True,
        )

    def url(self):
        return reverse('api:courses:admin_content_toggle', args=[self.content.pk])

    def toggle(self, action):
        return self.client.post(self.url(), {'action': action}, format='json', **self.auth)

    def test_active_is_flipped(self):
        self.toggle('active')
        self.content.refresh_from_db()
        self.assertFalse(self.content.active)

    def test_paid_is_flipped(self):
        self.toggle('paid')
        self.content.refresh_from_db()
        self.assertFalse(self.content.paid)

    def test_a_toggle_bumps_updated_at(self):
        before = self.content.updated_at
        self.toggle('active')
        self.content.refresh_from_db()
        self.assertGreater(self.content.updated_at, before)

    def test_a_get_no_longer_changes_anything(self):
        response = self.client.get(self.url(), {'action': 'active'}, **self.auth)
        self.assertEqual(response.status_code, 405)
        self.content.refresh_from_db()
        self.assertTrue(self.content.active)

    def test_an_unknown_action_is_rejected(self):
        response = self.toggle('delete')
        self.assertEqual(response.status_code, 422)
        self.content.refresh_from_db()
        self.assertTrue(self.content.active)


class TeacherCourseScopeTests(APITestCase):
    def setUp(self):
        self.teacher = make_user(role=User.Role.TEACHER)
        self.auth = bearer(self.teacher)
        self.mine = Course.objects.create(title='Mine', slug='mine-scope')
        self.theirs = Course.objects.create(title='Theirs', slug='theirs-scope')
        CourseTeacher.objects.create(course=self.mine, user=self.teacher)
        self.my_section = Section.objects.create(course=self.mine, title='Ch 1', slug='mine-ch1')
        self.their_section = Section.objects.create(course=self.theirs, title='Ch 1', slug='theirs-ch1')

    def post(self, path, **body):
        return self.client.post(f'/api/private/{path}/', body, format='json', **self.auth)

    def test_a_teacher_writes_only_into_their_own_course(self):
        writes = {
            'sections': {'title': 'Ch 2', 'slug': None},
            'routines': {'title': 'Routine', 'link': 'https://example.com/r.pdf'},
            'course-materials': {'title': 'Sheet', 'type': 'pdf'},
        }
        for path, body in writes.items():
            with self.subTest(path=path):
                if 'slug' in body:
                    body['slug'] = next_slug(path)
                self.assertEqual(self.post(path, course_id=self.theirs.pk, **body).status_code, 403)
                self.assertEqual(self.post(path, course_id=self.mine.pk, **body).status_code, 201)

        lesson = {'title': 'Lesson', 'type': 'video'}
        theirs = self.post(
            'contents', course_id=self.theirs.pk, section_id=self.their_section.pk, slug=next_slug('lesson'), **lesson
        )
        self.assertEqual(theirs.status_code, 403)
        mine = self.post(
            'contents', course_id=self.mine.pk, section_id=self.my_section.pk, slug=next_slug('lesson'), **lesson
        )
        self.assertEqual(mine.status_code, 201)

    def test_a_lesson_cannot_be_moved_into_another_course(self):
        lesson = Content.objects.create(
            course=self.mine, section=self.my_section, title='L', slug='mine-l', type='video'
        )
        response = self.client.patch(
            f'/api/private/contents/{lesson.slug}/',
            {'course_id': self.theirs.pk, 'section_id': self.their_section.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        lesson.refresh_from_db()
        self.assertEqual(lesson.course_id, self.mine.pk)

    def test_a_section_must_belong_to_the_course(self):
        response = self.post(
            'contents', course_id=self.mine.pk, section_id=self.their_section.pk, title='L', slug='l', type='video'
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn('section_id', response.json()['errors'])

    def test_rich_text_is_stripped_of_script(self):
        response = self.post(
            'contents',
            course_id=self.mine.pk,
            section_id=self.my_section.pk,
            title='Note',
            slug='note',
            type='note',
            note_body='<p>নোট</p><img src="x" onerror="fetch(1)">',
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Content.objects.get(title='Note').note_body, '<p>নোট</p><img src="x">')

    def test_a_teacher_who_creates_a_course_teaches_it(self):
        response = self.client.post(
            '/api/private/courses/', {'title': 'New course', 'slug': 'new-course'}, format='json', **self.auth
        )
        self.assertEqual(response.status_code, 201, response.content)
        course_id = response.json()['id']
        self.assertTrue(CourseTeacher.objects.filter(course_id=course_id, user=self.teacher).exists())
        self.assertEqual(self.client.get(f'/api/private/courses/{course_id}/', **self.auth).status_code, 200)
        listed = self.client.get('/api/private/courses/', **self.auth).json()['data']
        self.assertIn(course_id, [c['id'] for c in listed])

    def test_an_admin_who_creates_a_course_is_not_made_its_teacher(self):
        admin = make_user(role=User.Role.ADMIN)
        response = self.client.post(
            '/api/private/courses/', {'title': 'Admin course', 'slug': 'admin-course'}, format='json', **bearer(admin)
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(CourseTeacher.objects.filter(course_id=response.json()['id']).exists())


class CourseDeleteTests(APITestCase):
    def setUp(self):
        self.auth = bearer(make_user(role=User.Role.ADMIN))
        self.course = Course.objects.create(title='ICT', slug='ict-delete')

    def delete(self):
        return self.client.delete(f'/api/private/courses/{self.course.pk}/', **self.auth)

    def test_an_empty_course_can_be_deleted(self):
        self.assertEqual(self.delete().status_code, 204)
        self.assertFalse(Course.objects.filter(pk=self.course.pk).exists())

    def test_a_course_with_students_is_kept(self):
        Enrollment.objects.create(course=self.course, user=make_user())
        response = self.delete()
        self.assertEqual(response.status_code, 409)
        self.assertIn('Archive it instead', response.json()['message'])
        self.assertTrue(Course.objects.filter(pk=self.course.pk).exists())

    def test_a_course_someone_paid_for_is_kept(self):
        product = Product.objects.create(title='ICT', product_id='ict-delete', price=500, base_price=500)
        product.courses.add(self.course)
        Payment.objects.create(user=make_user(), product=product, amount=500, status=Payment.Status.VALID)
        Enrollment.objects.filter(course=self.course).delete()
        self.assertEqual(self.delete().status_code, 409)


class LessonVariantTests(APITestCase):
    def test_draft_is_not_a_lesson_variant(self):
        auth = bearer(make_user(role=User.Role.ADMIN))
        course = Course.objects.create(title='ICT', slug='ict-variant')
        section = Section.objects.create(course=course, title='Ch 1', slug='ict-variant-ch1')
        body = {'course_id': course.pk, 'section_id': section.pk, 'title': 'L', 'type': 'video', 'variant': 'Draft'}
        response = self.client.post('/api/private/contents/', body, format='json', **auth)
        self.assertEqual(response.status_code, 422)
        self.assertIn('variant', response.json()['errors'])
