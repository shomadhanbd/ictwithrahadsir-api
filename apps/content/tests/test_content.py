from django.urls import reverse

from rest_framework.test import APITestCase

from apps.content.models import (
    Advertisement,
    EBook,
    Notice,
    NoticeCategory,
    Page,
    Testimonial,
)
from apps.core.testing import bearer, make_user
from apps.courses.models import Course
from apps.identity.models import User
from apps.profiles.models import TeacherProfile

HOME_URL = reverse('api:content:home')
NOTICES_URL = reverse('api:content:notice_list')
NOTICE_CATEGORY_URL = reverse('api:content:notice_category_list')
ADMIN_PAGE_LIST_URL = reverse('api:content:admin_page_list')


class HomeTests(APITestCase):
    def setUp(self):
        self.course = Course.objects.create(title='ICT Full', slug='ict-full', status='published', is_featured=True)
        Course.objects.create(title='Hidden', slug='hidden', status='published', is_featured=False)
        TeacherProfile.objects.create(
            user=make_user(role=User.Role.TEACHER, name='Rahad Sir'),
            designation='Founder',
        )
        Testimonial.objects.create(name='Student', description='Great', ratings=5)
        Advertisement.objects.create(title='Admission open')

    def test_home_returns_every_section(self):
        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        for key in [
            'courses',
            'advertisement',
            'testimonials',
            'counters',
            'suceesstorycounter',
            'instructors',
            'bannerImage',
        ]:
            self.assertIn(key, body)

    def test_home_lists_only_featured_active_courses(self):
        titles = [c['title'] for c in self.client.get(HOME_URL).json()['courses']]
        self.assertEqual(titles, ['ICT Full'])

    def test_success_story_counter_mirrors_the_instructor_counter(self):
        # The endpoint deliberately echoes homeInstructorCounter.
        Page.objects.update_or_create(
            key='homeInstructorCounter',
            defaults={'slug': 'homeInstructorCounter', 'value_type': Page.ValueType.COUNTER, 'value': '18'},
        )
        self.assertEqual(self.client.get(HOME_URL).json()['suceesstorycounter'], '18')


class HomeInstructorTests(APITestCase):
    def test_disabled_teachers_are_left_off_the_home_and_about_pages(self):
        active = make_user(role=User.Role.TEACHER, name='Teaching')
        gone = make_user(role=User.Role.TEACHER, name='Left the centre', is_active=False)
        for user in (active, gone):
            TeacherProfile.objects.create(user=user)
        names = [i['name'] for i in self.client.get(HOME_URL).json()['instructors']]
        self.assertIn('Teaching', names)
        self.assertNotIn('Left the centre', names)


class NoticeTests(APITestCase):
    def setUp(self):
        self.category = NoticeCategory.objects.create(title='Exam', slug='exam')
        self.notice = Notice.objects.create(title='Exam schedule', slug='exam-schedule')
        self.notice.categories.add(self.category)
        Notice.objects.create(title='Holiday', slug='holiday')

    def test_notices_are_paginated(self):
        body = self.client.get(NOTICES_URL).json()
        self.assertEqual(body['meta']['total'], 2)

    def test_notices_filter_by_category(self):
        body = self.client.get(NOTICES_URL, {'category_id': self.category.pk}).json()
        self.assertEqual([n['title'] for n in body['data']], ['Exam schedule'])

    def test_a_category_that_is_not_an_id_is_a_422_not_a_500(self):
        response = self.client.get(NOTICES_URL, {'category_id': 'abc'})
        self.assertEqual(response.status_code, 422)
        self.assertIn('category_id', response.json()['errors'])

    def test_notice_categories_are_top_level_only(self):
        NoticeCategory.objects.create(title='Child', slug='child', notice_category=self.category)
        body = self.client.get(NOTICE_CATEGORY_URL).json()
        self.assertEqual([c['title'] for c in body['data']], ['Exam'])


class PageTests(APITestCase):
    def setUp(self):
        self.page = Page.objects.create(key='about-us', slug='about-us', value='<h2>Hi</h2>')

    def test_page_is_fetched_by_key(self):
        url = reverse('api:content:page_detail', args=['about-us'])
        self.assertEqual(self.client.get(url).json()['data']['value'], '<h2>Hi</h2>')

    def test_unknown_page_is_404(self):
        url = reverse('api:content:page_detail', args=['nope'])
        self.assertEqual(self.client.get(url).status_code, 404)


class AdminCmsTests(APITestCase):
    def setUp(self):
        self.admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(self.admin)
        self.page = Page.objects.create(key='terms', slug='terms', value='old')

    def test_pages_are_listed_unpaginated(self):
        body = self.client.get(ADMIN_PAGE_LIST_URL, **self.auth).json()
        self.assertIn('data', body)
        self.assertNotIn('meta', body)

    def test_a_page_is_updated_by_slug(self):
        url = reverse('api:content:admin_page_update', args=['terms'])
        response = self.client.patch(url, {'value': 'new'}, format='json', **self.auth)
        self.assertEqual(response.status_code, 200)
        self.page.refresh_from_db()
        self.assertEqual(self.page.value, 'new')

    def test_page_html_is_stripped_of_script(self):
        url = reverse('api:content:admin_page_update', args=['terms'])
        html = '<p class="ql-align-center" onclick="x">শর্ত<img src="x" onerror="alert(1)"><script>alert(1)</script></p>'
        self.client.patch(url, {'value': html}, format='json', **self.auth)
        self.page.refresh_from_db()
        self.assertEqual(self.page.value, '<p class="ql-align-center">শর্ত<img src="x"></p>')

    def test_raw_markup_cannot_be_smuggled_in_by_changing_the_page_type(self):
        """Store it as an "image", flip it back to HTML: the public site would serve the raw markup."""
        url = reverse('api:content:admin_page_update', args=['terms'])
        raw = '<img src=x onerror=alert(1)><script>steal()</script>'
        self.client.patch(url, {'value_type': 'image', 'value': raw}, format='json', **self.auth)
        self.client.patch(url, {'value_type': 'html'}, format='json', **self.auth)

        self.page.refresh_from_db()
        self.assertEqual(self.page.value_type, Page.ValueType.HTML)
        self.assertNotIn('onerror', self.page.value)
        self.assertNotIn('<script', self.page.value)

    def test_a_counter_page_stays_a_counter(self):
        Page.objects.update_or_create(
            key='homeStudentCounter', defaults={'slug': 'homeStudentCounter', 'value_type': Page.ValueType.COUNTER}
        )
        url = reverse('api:content:admin_page_update', args=['homeStudentCounter'])
        self.client.patch(url, {'value_type': 'html', 'value': '5000'}, format='json', **self.auth)
        self.assertEqual(Page.objects.get(key='homeStudentCounter').value_type, Page.ValueType.COUNTER)

    def test_a_notice_body_is_stripped_of_script(self):
        body = {'title': 'Notice', 'body': '<p>খবর</p><a href="javascript:steal()">x</a>'}
        response = self.client.post(reverse('api:content:admin-notice-list'), body, format='json', **self.auth)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotIn('javascript', Notice.objects.get().body)


class PublicEBookListTests(APITestCase):
    def setUp(self):
        EBook.objects.create(
            title='ICT Handnote',
            description='Syntax and loops, explained.',
            booking_link='https://example.test/order',
            preview='https://example.test/preview.pdf',
        )

    def test_the_shelf_is_public(self):
        response = self.client.get(reverse('api:content:ebook_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['title'], 'ICT Handnote')

    def test_it_is_read_only(self):
        response = self.client.post(reverse('api:content:ebook_list'), {'title': 'Nope'}, format='json')
        self.assertEqual(response.status_code, 405)
