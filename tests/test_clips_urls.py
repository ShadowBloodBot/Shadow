import unittest

from cogs.clip_urls import (
    clip_source,
    extract_urls,
    html_looks_like_video,
    is_allowlisted_clip_url,
    is_https_url,
    is_valid_clip_url,
    is_valid_medal_url,
    is_valid_tiktok_url,
    is_valid_twitch_url,
    is_valid_youtube_url,
    normalize_clip_url,
)


class ClipUrlTests(unittest.TestCase):
    def test_medal_game_clip(self):
        url = "https://medal.tv/games/sand-raiders-of-sophie-1/clips/mZOG8kaxAQvXk512X"
        self.assertTrue(is_valid_medal_url(url))
        self.assertTrue(is_valid_clip_url(url))
        self.assertEqual(clip_source(url), "medal")

    def test_medal_strips_query(self):
        raw = "https://medal.tv/games/sand/clips/abc123?invite=foo"
        self.assertEqual(
            normalize_clip_url(raw),
            "https://medal.tv/games/sand/clips/abc123",
        )

    def test_youtube_shorts(self):
        url = "https://youtube.com/shorts/1McMCio_ANQ?si=abc"
        self.assertTrue(is_valid_youtube_url(url))
        self.assertTrue(is_allowlisted_clip_url(url))
        self.assertEqual(clip_source(url), "youtube")

    def test_youtube_watch_and_be(self):
        self.assertTrue(is_valid_youtube_url("https://www.youtube.com/watch?v=dQw4w9wgGcQ"))
        self.assertTrue(is_valid_youtube_url("https://youtu.be/abHKtvTKC2Q"))
        self.assertTrue(is_valid_youtube_url("https://www.youtube.com/clip/UgkxSomething"))

    def test_twitch_clips(self):
        self.assertTrue(is_valid_twitch_url("https://clips.twitch.tv/CleverClipName"))
        self.assertTrue(is_valid_twitch_url("https://www.twitch.tv/shroud/clip/SomeClip-abc"))
        self.assertTrue(is_allowlisted_clip_url("https://clips.twitch.tv/CleverClipName"))

    def test_tiktok(self):
        self.assertTrue(
            is_valid_tiktok_url("https://www.tiktok.com/@user/video/1234567890123456789")
        )
        self.assertTrue(is_valid_tiktok_url("https://vm.tiktok.com/ZMabcdef/"))
        self.assertTrue(is_allowlisted_clip_url("https://vm.tiktok.com/ZMabcdef/"))

    def test_streamable(self):
        self.assertTrue(is_allowlisted_clip_url("https://streamable.com/abc12"))
        self.assertEqual(clip_source("https://streamable.com/abc12"), "streamable")

    def test_direct_video_https(self):
        self.assertTrue(
            is_allowlisted_clip_url("https://cdn.example.com/clips/play.mp4")
        )
        self.assertEqual(clip_source("https://cdn.example.com/clips/play.mp4"), "file")

    def test_rejects_non_https_and_empty(self):
        self.assertFalse(is_https_url(""))
        self.assertFalse(is_https_url("http://medal.tv/clips/abc"))
        self.assertFalse(is_valid_clip_url(""))
        self.assertFalse(is_valid_clip_url("http://youtu.be/abHKtvTKC2Q"))

    def test_rejects_unrelated_https(self):
        self.assertFalse(is_allowlisted_clip_url("https://evil.example/phish"))
        self.assertFalse(is_allowlisted_clip_url("https://google.com"))
        self.assertFalse(is_valid_twitch_url("https://twitch.tv/shroud"))

    def test_rejects_relative(self):
        self.assertFalse(is_valid_clip_url("/clips/abc"))
        self.assertFalse(is_https_url("medal.tv/clips/abc"))

    def test_extract_urls_from_message(self):
        text = "check this https://youtu.be/abHKtvTKC2Q dude"
        self.assertEqual(extract_urls(text), ["https://youtu.be/abHKtvTKC2Q"])

    def test_html_video_og(self):
        html = '<meta property="og:type" content="video.other" />'
        self.assertTrue(html_looks_like_video(html))
        self.assertFalse(html_looks_like_video('<meta property="og:type" content="website" />'))


if __name__ == "__main__":
    unittest.main()
