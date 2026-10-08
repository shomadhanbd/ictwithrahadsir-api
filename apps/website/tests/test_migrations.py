from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ContentMigrationTests(TransactionTestCase):
    """What the retired `content` app held arrives in the website app, and its tables go."""

    before = [("website", "0001_initial")]
    after = [("website", "0002_copy_content")]

    def test_pages_photo_and_advertisements_are_copied(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE content_page (id integer PRIMARY KEY, key varchar(100), value text, image varchar(200))"
            )
            cursor.execute(
                "INSERT INTO content_page VALUES (1, 'privacy-policy', '<p>Private</p>', NULL), "
                "(2, 'homeBannerImage', '', 'https://example.com/sir.jpg'), (3, 'homeStudentCounter', '42', NULL)"
            )
            cursor.execute(
                "CREATE TABLE content_advertisement "
                "(id integer PRIMARY KEY, title varchar(255), link varchar(200), image varchar(200))"
            )
            cursor.execute(
                "INSERT INTO content_advertisement VALUES "
                "(1, 'Admission', 'https://x.com', 'https://example.com/a.jpg'), "
                "(2, 'No image', '', NULL)"
            )

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.after)
        new = executor.loader.project_state(self.after).apps
        sections = {s.key: s.content for s in new.get_model("website", "Section").objects.all()}
        self.assertEqual(set(sections), {"legal.privacy-policy", "home.trust"})
        self.assertEqual(sections["legal.privacy-policy"]["body"], "<p>Private</p>")
        self.assertEqual(sections["home.trust"]["image"], "https://example.com/sir.jpg")
        self.assertEqual(
            list(new.get_model("website", "Banner").objects.values_list("title", flat=True)), ["Admission"]
        )
        tables = connection.introspection.table_names()
        self.assertNotIn("content_page", tables)
        self.assertNotIn("content_advertisement", tables)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
