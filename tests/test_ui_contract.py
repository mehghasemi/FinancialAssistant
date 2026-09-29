"""Check navigation targets against the actual rendered page structure."""
from html.parser import HTMLParser
from pathlib import Path
import unittest


class PageStructure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pages = set()
        self.targets = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "page" in attrs.get("class", "").split():
            self.pages.add(attrs.get("id"))
        if "data-page" in attrs:
            self.targets.add(attrs["data-page"])


class NavigationTests(unittest.TestCase):
    def test_every_navigation_button_opens_an_existing_page(self):
        structure = PageStructure()
        structure.feed((Path(__file__).resolve().parents[1] / "static/index.html").read_text(encoding="utf-8"))
        self.assertTrue(structure.targets)
        self.assertEqual(structure.targets - structure.pages, set())
