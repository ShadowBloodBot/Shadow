import unittest
from datetime import datetime

from cogs.notice import (
    SQUAD_NAME_LIMIT,
    build_event_embed,
    build_game_embed,
    find_squad_field_index,
    parse_steam_release_date,
    parse_when,
    squad_field,
    steam_appid,
    toggle_enlisted,
)


class SteamAppidTests(unittest.TestCase):
    def test_store_url(self):
        self.assertEqual(
            steam_appid("https://store.steampowered.com/app/1867240/WARDOGS/"),
            "1867240",
        )

    def test_url_without_slug(self):
        self.assertEqual(
            steam_appid("https://store.steampowered.com/app/2646460"),
            "2646460",
        )

    def test_raw_digits(self):
        self.assertEqual(steam_appid("4253010"), "4253010")

    def test_garbage(self):
        self.assertIsNone(steam_appid("https://medal.tv/clip/abc"))
        self.assertIsNone(steam_appid(""))


class ReleaseDateTests(unittest.TestCase):
    def test_day_first(self):
        dt = parse_steam_release_date("21 Aug, 2026")
        self.assertEqual((dt.year, dt.month, dt.day), (2026, 8, 21))

    def test_month_first(self):
        dt = parse_steam_release_date("Aug 21, 2026")
        self.assertEqual((dt.year, dt.month, dt.day), (2026, 8, 21))

    def test_unparseable(self):
        self.assertIsNone(parse_steam_release_date("Coming soon"))
        self.assertIsNone(parse_steam_release_date("Q4 2026"))
        self.assertIsNone(parse_steam_release_date(""))


class ParseWhenTests(unittest.TestCase):
    def test_iso_style(self):
        dt = parse_when("2026-09-05 20:00")
        self.assertEqual((dt.year, dt.month, dt.day, dt.hour), (2026, 9, 5, 20))

    def test_au_style(self):
        dt = parse_when("05/09/2026 20:00")
        self.assertEqual((dt.year, dt.month, dt.day), (2026, 9, 5))

    def test_unix_timestamp(self):
        dt = parse_when("1741320000")
        self.assertIsInstance(dt, datetime)

    def test_garbage(self):
        self.assertIsNone(parse_when("next tuesday-ish"))


class SquadFieldTests(unittest.TestCase):
    def test_empty(self):
        field = squad_field({})
        self.assertIn("0 locked in", field["name"])
        self.assertIn("Be the first", field["value"])

    def test_some_names(self):
        field = squad_field({"1": "Joe", "2": "Gravy"})
        self.assertIn("2 locked in", field["name"])
        self.assertIn("Joe", field["value"])
        self.assertIn("Gravy", field["value"])

    def test_overflow(self):
        enlisted = {str(i): f"Member{i}" for i in range(SQUAD_NAME_LIMIT + 5)}
        field = squad_field(enlisted)
        self.assertIn(f"{SQUAD_NAME_LIMIT + 5} locked in", field["name"])
        self.assertIn("+5 more", field["value"])


class ToggleEnlistedTests(unittest.TestCase):
    def test_enlist_then_leave(self):
        notice = {"enlisted": {}}
        self.assertTrue(toggle_enlisted(notice, 42, "Joe"))
        self.assertEqual(notice["enlisted"], {"42": "Joe"})
        self.assertFalse(toggle_enlisted(notice, 42, "Joe"))
        self.assertEqual(notice["enlisted"], {})


class GameEmbedTests(unittest.TestCase):
    META = {
        "appid": "1867240",
        "name": "WARDOGS",
        "url": "https://store.steampowered.com/app/1867240/",
        "header_image": "https://cdn.example/header.jpg",
        "short_description": "Helicopter warfare.",
        "genres": ["Action", "Simulation"],
        "release_date": "21 Aug, 2026",
        "price": "A$59.95",
    }

    def test_payload_shape(self):
        embed = build_game_embed(self.META, "THIS IS WHERE WE BE AT", {})
        self.assertEqual(embed.title, "WARDOGS")
        self.assertEqual(embed.image.url, "https://cdn.example/header.jpg")
        self.assertIn("> THIS IS WHERE WE BE AT", embed.description)
        self.assertIn("Helicopter warfare.", embed.description)
        field_names = [f.name for f in embed.fields]
        self.assertIn("Release", field_names)
        self.assertIn("Price", field_names)
        self.assertIsNotNone(find_squad_field_index(embed))

    def test_squad_field_updates(self):
        embed = build_game_embed(self.META, "", {"1": "Joe"})
        idx = find_squad_field_index(embed)
        self.assertIn("1 locked in", embed.fields[idx].name)
        self.assertIn("Joe", embed.fields[idx].value)


class EventEmbedTests(unittest.TestCase):
    def test_with_parsed_time(self):
        dt = parse_when("2026-09-05 20:00")
        embed = build_event_embed("RUST FORCE WIPE", dt, "2026-09-05 20:00", None, None)
        self.assertIn("<t:", embed.description)
        self.assertEqual(embed.title, "📅 RUST FORCE WIPE")

    def test_with_raw_time(self):
        embed = build_event_embed("Beta night", None, "friday-ish", "Bring meds", None)
        self.assertIn("friday-ish", embed.description)
        self.assertIn("Bring meds", embed.description)


if __name__ == "__main__":
    unittest.main()
