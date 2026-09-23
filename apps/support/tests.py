"""Contract tests for the contact form and the staff inbox."""

from django.urls import reverse

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.identity.models import User
from apps.support.models import ContactMessage

CONTACT_URL = reverse('api:support:contact_messages')
ADMIN_CONTACT_LIST_URL = reverse('api:support:admin_contact_list')


class ContactTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone='01810200001', name='Student', password='Str0ngPass!23')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.user).key}'}

    def test_anonymous_submission_is_refused(self):
        # IsAuthenticatedOrReadOnly gates the POST, so a logged-out visitor
        # cannot use the contact form at all. Note the view still carries an
        # `if request.user.is_authenticated else None` branch for the owner
        # field, which is unreachable while that permission class stands --
        # one of the two is wrong, and the frontend decides which.
        response = self.client.post(CONTACT_URL, {'message': 'Hello', 'name': 'Guest'}, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertFalse(ContactMessage.objects.exists())

    def test_a_signed_in_user_may_submit(self):
        response = self.client.post(CONTACT_URL, {'message': 'Hello'}, format='json', **self.auth)
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


class AdminInboxTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            phone='01710200001',
            name='Admin',
            password='Str0ngPass!23',
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.admin).key}'}
        self.message = ContactMessage.objects.create(message='Help me')

    def test_admin_endpoints_reject_anonymous(self):
        self.assertEqual(self.client.get(ADMIN_CONTACT_LIST_URL).status_code, 401)

    def test_contact_list_is_paginated(self):
        body = self.client.get(ADMIN_CONTACT_LIST_URL, **self.auth).json()
        self.assertEqual(body['meta']['total'], 1)

    def test_toggle_marks_a_message_read(self):
        url = reverse('api:support:admin_contact_toggle_read', args=[self.message.pk])
        self.assertEqual(self.client.get(url, **self.auth).status_code, 200)
        self.message.refresh_from_db()
        self.assertTrue(self.message.is_read)

    def test_replying_records_the_responder(self):
        url = reverse('api:support:admin_contact_detail', args=[self.message.pk])
        response = self.client.patch(url, {'reply_message': 'Sure'}, format='json', **self.auth)
        self.assertEqual(response.status_code, 200)

        self.message.refresh_from_db()
        self.assertEqual(self.message.reply_message, 'Sure')
        self.assertEqual(self.message.replied_by, self.admin)

    def test_reply_message_is_required(self):
        url = reverse('api:support:admin_contact_detail', args=[self.message.pk])
        self.assertEqual(self.client.patch(url, {}, format='json', **self.auth).status_code, 422)

    def test_a_message_can_be_deleted(self):
        url = reverse('api:support:admin_contact_detail', args=[self.message.pk])
        self.assertEqual(self.client.delete(url, **self.auth).status_code, 204)
        self.assertFalse(ContactMessage.objects.exists())
