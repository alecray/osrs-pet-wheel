"""Offline regression checks for drift classification (no Wiki requests)."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

import check_pets


# The 26 titles reported by issue #2, not a wildcard for all dog-like pets.
DOG_PAGES = [
    "Dog", "Puppy",
    "Bernese Mountain Dog", "Bernese Mountain Dog puppy",
    "Border Collie", "Border Collie puppy", "Chihuahua", "Chihuahua puppy",
    "Corgi", "Corgi puppy", "Greyhound", "Greyhound puppy",
    "Husky", "Husky puppy", "Labrador", "Labrador puppy", "Pug", "Pug puppy",
    "Samoyed", "Samoyed puppy", "Shiba", "Shiba puppy",
    "Spaniel", "Spaniel puppy", "Yorkie", "Yorkie puppy",
]


class DriftClassificationTests(unittest.TestCase):
    def run_checker(self, pages, pets=(), wikitext=""):
        output = io.StringIO()
        with (
            patch.object(check_pets.Path, "read_text", return_value=json.dumps(pets)),
            patch.object(check_pets, "wiki_pet_pages", return_value=pages),
            patch.object(check_pets, "page_wikitext", return_value=wikitext),
            patch.object(check_pets.time, "sleep"),
            contextlib.redirect_stdout(output),
        ):
            status = check_pets.main()
        return status, output.getvalue()

    def test_adoption_pages_do_not_report_drift(self):
        status, output = self.run_checker(DOG_PAGES)
        self.assertEqual(status, 0, output)
        self.assertNotIn("  NEW  ", output)

    def test_collection_log_reference_page_does_not_report_drift(self):
        status, output = self.run_checker(["Pet/Collection log"])
        self.assertEqual(status, 0, output)

    def test_unknown_pets_still_report_drift_including_dog_names(self):
        status, output = self.run_checker(DOG_PAGES + ["Future dog", "Future pet"])
        self.assertEqual(status, 1)
        self.assertIn("  NEW  Future dog  ", output)
        self.assertIn("  NEW  Future pet  ", output)
        self.assertIn("2 problem(s) found.", output)

    def test_huntable_canines_keep_item_id_validation(self):
        pets = [
            {"name": "Bloodhound", "itemId": 19730,
             "wikiUrl": "https://oldschool.runescape.wiki/w/Bloodhound"},
            {"name": "Hellpuppy", "itemId": 13247,
             "wikiUrl": "https://oldschool.runescape.wiki/w/Hellpuppy"},
        ]
        pages = DOG_PAGES + ["Bloodhound", "Hellpuppy"]
        status, output = self.run_checker(pages, pets, "|id = 19730\n|id2 = 13247")
        self.assertEqual(status, 0, output)
        status, output = self.run_checker(pages, pets, "|id = 99999")
        self.assertEqual(status, 1)
        self.assertIn("  BAD  Bloodhound:", output)
        self.assertIn("  BAD  Hellpuppy:", output)


if __name__ == "__main__":
    unittest.main()
