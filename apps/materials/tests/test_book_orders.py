from django.urls import reverse

from apps.billing.models import Payment
from apps.billing.tests.base import GATEWAY_PAGE, MY_PAYMENTS_URL, BillingTestBase, session_ok
from apps.core.testing import bearer, make_user
from apps.courses.models import Enrollment
from apps.identity.models import User
from apps.materials.models import BookOrder, DeliveryRate, MaterialCategory, MaterialItem, MaterialTopic

ORDER_URL = reverse("api:materials:book_order")
ADDRESS = {"name": "Rahim", "phone": "01810001111", "address": "Zindabazar, Sylhet", "zone": "sylhet"}


class BookOrderTests(BillingTestBase):
    def setUp(self):
        super().setUp()
        category = MaterialCategory.objects.create(name="বই")
        self.topic = MaterialTopic.objects.create(category=category, title="Books", is_published=True)
        self.book = MaterialItem.objects.create(topic=self.topic, kind="book", title="ICT Guide", price=350)

    def order(self, auth=None, **body):
        with session_ok() as create_session:
            response = self.client.post(
                ORDER_URL, {"item_id": self.book.pk, **ADDRESS, **body}, format="json", **(auth or self.auth)
            )
        return response, create_session

    def test_a_book_is_paid_for_with_its_delivery(self):
        response, create_session = self.order()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["gateway_page_url"], GATEWAY_PAGE)
        order = BookOrder.objects.get()
        self.assertEqual((order.book_price, order.delivery_charge, order.payment.amount), (350, 60, 410))
        self.assertIsNone(order.payment.product)
        self.assertTrue(order.payment.transaction_id.startswith("shc_bk_"))
        sent = create_session.call_args.args[0]
        self.assertEqual((sent["total_amount"], sent["product_profile"]), (410, "physical-goods"))
        self.assertEqual(sent["cus_add1"], ADDRESS["address"])

    def test_outside_sylhet_costs_the_outside_rate(self):
        DeliveryRate.objects.filter(zone="outside").update(charge=150)
        response, _ = self.order(zone="outside")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(BookOrder.objects.get().payment.amount, 500)

    def test_a_double_click_reuses_the_checkout(self):
        first, _ = self.order()
        second, create_session = self.order()
        self.assertEqual(first.json()["transaction_id"], second.json()["transaction_id"])
        create_session.assert_not_called()
        self.assertEqual(BookOrder.objects.count(), 1)

    def test_only_a_priced_book_on_a_published_topic_is_sold(self):
        for change in ({"price": None}, {"kind": "pdf"}):
            MaterialItem.objects.filter(pk=self.book.pk).update(**{"price": 350, "kind": "book", **change})
            response, _ = self.order()
            self.assertEqual(response.status_code, 422, change)
        MaterialItem.objects.filter(pk=self.book.pk).update(price=350, kind="book")
        MaterialTopic.objects.filter(pk=self.topic.pk).update(is_published=False)
        response, _ = self.order()
        self.assertEqual(response.status_code, 422)

    def test_a_students_only_book_is_sold_to_its_students(self):
        self.topic.access = MaterialTopic.Access.ENROLLED
        self.topic.save()
        self.topic.courses.set([self.course])
        response, _ = self.order()
        self.assertEqual(response.status_code, 422)

    def test_the_phone_must_be_a_bangladeshi_mobile(self):
        response, _ = self.order(phone="12345")
        self.assertEqual(response.status_code, 422)
        self.assertIn("phone", response.json()["errors"])

    def test_a_visitor_must_sign_in(self):
        response = self.client.post(ORDER_URL, {"item_id": self.book.pk, **ADDRESS}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_a_paid_order_reaches_the_admin_list_and_grants_no_course(self):
        self.order()
        payment = Payment.objects.get()
        self.capture(payment)
        payment.refresh_from_db()
        self.assertEqual((payment.status, payment.refund_due), (Payment.Status.VALID, False))
        self.assertFalse(Enrollment.objects.filter(user=self.student).exists())

        admin = bearer(make_user(role=User.Role.ADMIN))
        rows = self.client.get(reverse("api:materials:admin_book_order_list"), **admin).json()["data"]
        self.assertEqual(
            [(row["title"], row["phone"], row["amount"]) for row in rows], [("ICT Guide", "01810001111", 410)]
        )

        mine = self.client.get(MY_PAYMENTS_URL, **self.auth).json()["data"][0]
        self.assertEqual((mine["kind"], mine["title"], mine["courses"]), ("book", "ICT Guide", []))
        self.assertEqual(mine["book"]["address"], ADDRESS["address"])

    def test_a_second_paid_copy_is_not_a_duplicate(self):
        for _ in range(2):
            self.order()
            payment = Payment.objects.filter(status=Payment.Status.INITIATED).get()
            self.capture(payment)
        self.assertEqual(Payment.objects.filter(status=Payment.Status.VALID, refund_due=False).count(), 2)

    def test_unpaid_orders_stay_off_the_admin_list(self):
        self.order()
        admin = bearer(make_user(role=User.Role.ADMIN))
        rows = self.client.get(reverse("api:materials:admin_book_order_list"), **admin).json()["data"]
        self.assertEqual(rows, [])

    def test_admins_set_the_delivery_charges(self):
        admin = bearer(make_user(role=User.Role.ADMIN))
        url = reverse("api:materials:admin_delivery_rate_detail", args=["outside"])
        response = self.client.patch(url, {"charge": 130}, format="json", **admin)
        self.assertEqual(response.status_code, 200, response.content)
        public = self.client.get(reverse("api:materials:delivery_rate_list")).json()["data"]
        self.assertIn({"zone": "outside", "label": "Outside Sylhet", "charge": 130}, public)
        moderator = bearer(make_user(role=User.Role.MODERATOR))
        self.assertEqual(self.client.patch(url, {"charge": 1}, format="json", **moderator).status_code, 403)
