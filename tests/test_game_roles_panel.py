import unittest

from cogs.game_roles import _sorted_catalog, public_panel_fields


class GameRolesPanelTests(unittest.TestCase):
    def test_public_panel_lists_every_game_including_wardogs(self):
        catalog = [{"id": str(i), "label": chr(65 + (i % 26)) + str(i)} for i in range(37)]
        catalog.append({"id": "1536979035861553264", "label": "Wardogs"})
        catalog = _sorted_catalog(catalog)
        fields = public_panel_fields(catalog)
        blob = "\n".join(str(f.get("value") or "") for f in fields)
        self.assertIn("Wardogs", blob)
        self.assertIn("**38**", blob)
        self.assertNotIn("Page ", blob)


if __name__ == "__main__":
    unittest.main()
