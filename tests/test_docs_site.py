import unittest

from docs_site.server import DOCS_ROOT, document_path, documents


class DocsSiteTests(unittest.TestCase):
    def test_wiki_index_is_in_navigation(self):
        self.assertIn(
            {"path": "docs/wiki/INDEX.md", "title": "Wiki", "section": "wiki"},
            documents(),
        )

    def test_document_path_stays_inside_docs(self):
        self.assertEqual(document_path("docs/wiki/INDEX.md"), DOCS_ROOT / "wiki/INDEX.md")
        self.assertIsNone(document_path("../README.md"))
