"""Contract tests for the CMS endpoints.

The homepage aggregate is the important one: it reaches across courses,
team and cms, so it is the endpoint most likely to break when modules
move -- and it did during this restructure, without any test noticing.
"""

from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.cms.models import (
    Advertisement,
    ContactMessage,
    Notice,
    NoticeCategory,
    Page,
    Testimonial,
)
from apps.courses.models import Course, CourseCategory
from apps.team.models import Teacher

HOME_URL = reverse('api:cms:v1:home')
NOTICES_URL = reverse('api:cms:v1:notice_list')
NOTICE_CATEGORY_URL = reverse('api:cms:v1:notice_category_list')
CONTACT_URL = reverse('api:cms:v1:contact_messages')
ADMIN_PAGE_LIST_URL = reverse('api:cms:v1:admin_page_list')
ADMIN_CONTACT_LIST_URL = reverse('api:cms:v1:admin_contact_list')


class HomeTests(APITestCase):
    def setUp(self):
        self.category = CourseCategory.objects.create(title='HSC', slug='hsc')
        self.course = Course.objects.create(
            title='ICT Full', slug='ict-full', active=True, featured=True
        )
        self.course.categories.add(self.category)
        Course.objects.create(title='Hidden', slug='hidden', active=True, featured=False)
        Teacher.objects.create(name='Rahad Sir', designation='Founder')
        Testimonial.objects.create(name='Student', description='Great', ratings=5)
        Advertisement.objects.create(title='Admission open')

    def test_home_returns_every_section(self):
        response = self.client.get(HOME_URL)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        for key in [
            'courses', 'courseCategories', 'advertisement', 'testimonials',
            'counters', 'suceesstorycounter', 'instructors', 'bannerImage',
        ]:
            self.assertIn(key, body)

    def test_home_lists_only_featured_active_courses(self):
        titles = [c['title'] for c in self.client.get(HOME_URL).json()['courses']]
        self.assertEqual(titles, ['ICT Full'])

    def test_home_lists_only_top_level_categories(self):
        CourseCategory.objects.create(title='HSC 2026', slug='hsc-2026', category=self.category)
        titles = [c['title'] for c in self.client.get(HOME_URL).json()['courseCategories']]
        self.assertEqual(titles, ['HSC'])

    def test_success_story_counter_mirrors_the_instructor_counter(self):
        # There is no dedicated page key for it; the endpoint deliberately
        # echoes homeInstructorCounter.
        Page.objects.update_or_create(
            key='homeInstructorCounter',
            defaults={'slug': 'homeInstructorCounter', 'value_type': Page.ValueType.COUNTER,
                      'value': '18'},
        )
        self.assertEqual(self.client.get(HOME_URL).json()['suceesstorycounter'], '18')


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

    def test_notice_categories_are_top_level_only(self):
        NoticeCategory.objects.create(
            title='Child', slug='child', notice_category=self.category
        )
        body = self.client.get(NOTICE_CATEGORY_URL).json()
        self.assertEqual([c['title'] for c in body['data']], ['Exam'])


class PageTests(APITestCase):
    def setUp(self):
        self.page = Page.objects.create(key='about-us', slug='about-us', value='<h2>Hi</h2>')

    def test_page_is_fetched_by_key(self):
        url = reverse('api:cms:v1:page_detail', args=['about-us'])
        self.assertEqual(self.client.get(url).json()['data']['value'], '<h2>Hi</h2>')

    def test_unknown_page_is_404(self):
        url = reverse('api:cms:v1:page_detail', args=['nope'])
        self.assertEqual(self.client.get(url).status_code, 404)


class ContactTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone='01810200001', name='Student', password='Str0ngPass!23'
        )
        self.auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.user).key}'
        }

    def test_anonymous_submission_is_refused(self):
        # IsAuthenticatedOrReadOnly gates the POST, so a logged-out visitor
        # cannot use the contact form at all. Note the view still carries an
        # `if request.user.is_authenticated else None` branch for the owner
        # field, which is unreachable while that permission class stands --
        # one of the two is wrong, and the frontend decides which.
        response = self.client.post(
            CONTACT_URL, {'message': 'Hello', 'name': 'Guest'}, format='json'
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(ContactMessage.objects.exists())

    def test_a_signed_in_user_may_submit(self):
        response = self.client.post(
            CONTACT_URL, {'message': 'Hello'}, format='json', **self.auth
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ContactMessage.objects.get().user, self.user)

    def test_a_signed_in_user_sees_only_their_own_messages(self):
        ContactMessage.objects.create(user=self.user, message='Mine')
        ContactMessage.objects.create(message='Someone else')

        body = self.client.get(CONTACT_URL, **self.auth).json()
        self.assertEqual([m['message'] for m in body['data']], ['Mine'])

    def test_anonymous_listing_is_empty(self):
        ContactMessage.objects.create(user=self.user, message='Mine')
        self.assertEqual(self.client.get(CONTACT_URL).json()['data'], [])


class AdminCmsTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            phone='01710200001', name='Admin', password='Str0ngPass!23',
            role=User.Role.ADMIN, is_staff=True,
        )
        self.auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.admin).key}'
        }
        self.message = ContactMessage.objects.create(message='Help me')
        self.page = Page.objects.create(key='terms', slug='terms', value='old')

    def test_admin_endpoints_reject_anonymous(self):
        self.assertEqual(self.client.get(ADMIN_CONTACT_LIST_URL).status_code, 401)

    def test_contact_list_is_paginated(self):
        body = self.client.get(ADMIN_CONTACT_LIST_URL, **self.auth).json()
        self.assertEqual(body['meta']['total'], 1)

    def test_toggle_marks_a_message_read(self):
        url = reverse('api:cms:v1:admin_contact_toggle_read', args=[self.message.pk])
        self.assertEqual(self.client.get(url, **self.auth).status_code, 200)
        self.message.refresh_from_db()
        self.assertTrue(self.message.is_read)

    def test_replying_records_the_responder(self):
        url = reverse('api:cms:v1:admin_contact_detail', args=[self.message.pk])
        response = self.client.patch(url, {'reply_message': 'Sure'}, format='json', **self.auth)
        self.assertEqual(response.status_code, 200)

        self.message.refresh_from_db()
        self.assertEqual(self.message.reply_message, 'Sure')
        self.assertEqual(self.message.replied_by, self.admin)

    def test_reply_message_is_required(self):
        url = reverse('api:cms:v1:admin_contact_detail', args=[self.message.pk])
        self.assertEqual(self.client.patch(url, {}, format='json', **self.auth).status_code, 422)

    def test_a_message_can_be_deleted(self):
        url = reverse('api:cms:v1:admin_contact_detail', args=[self.message.pk])
        self.assertEqual(self.client.delete(url, **self.auth).status_code, 204)
        self.assertFalse(ContactMessage.objects.exists())

    def test_pages_are_listed_unpaginated(self):
        body = self.client.get(ADMIN_PAGE_LIST_URL, **self.auth).json()
        self.assertIn('data', body)
        self.assertNotIn('meta', body)

    def test_a_page_is_updated_by_slug(self):
        url = reverse('api:cms:v1:admin_page_update', args=['terms'])
        response = self.client.patch(url, {'value': 'new'}, format='json', **self.auth)
        self.assertEqual(response.status_code, 200)
        self.page.refresh_from_db()
        self.assertEqual(self.page.value, 'new')
