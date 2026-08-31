import unittest

from cogs.clips import ClipsCog


def _cog_with_clips(clips: dict) -> ClipsCog:
    cog = ClipsCog.__new__(ClipsCog)
    cog.data = {"panels": {}, "clips": clips}
    return cog


class ClipsDedupeTests(unittest.TestCase):
    def test_exact_url_is_duplicate(self):
        cog = _cog_with_clips(
            {"1": {"url": "https://medal.tv/games/rust/clips/abc123", "author_name": "Joe"}}
        )
        dup = cog._find_duplicate_clip("https://medal.tv/games/rust/clips/abc123")
        self.assertIsNotNone(dup)
        self.assertEqual(dup["author_name"], "Joe")

    def test_tracking_params_still_duplicate(self):
        cog = _cog_with_clips(
            {"1": {"url": "https://medal.tv/games/rust/clips/abc123", "author_name": "Joe"}}
        )
        dup = cog._find_duplicate_clip(
            "https://medal.tv/games/rust/clips/abc123?invite=cr-XYZ&theater=true"
        )
        self.assertIsNotNone(dup)

    def test_different_url_is_not_duplicate(self):
        cog = _cog_with_clips(
            {"1": {"url": "https://medal.tv/games/rust/clips/abc123", "author_name": "Joe"}}
        )
        self.assertIsNone(cog._find_duplicate_clip("https://medal.tv/games/rust/clips/zzz999"))

    def test_upload_clips_without_url_are_skipped(self):
        cog = _cog_with_clips({"1": {"url": None, "author_name": "Joe", "source": "upload"}})
        self.assertIsNone(cog._find_duplicate_clip("https://medal.tv/games/rust/clips/abc123"))


if __name__ == "__main__":
    unittest.main()
