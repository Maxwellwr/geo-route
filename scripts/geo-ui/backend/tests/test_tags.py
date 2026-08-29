from pathlib import Path
from unittest.mock import patch

import pytest

from tags import LIST_ARGS, list_tags, parse_tag_list, search_tags

TAG_FIXTURE = """\
# geosite tags
CN

JP
google
  spaced  tag
# trailing comment only
"""


def test_parse_tag_list():
    assert parse_tag_list(TAG_FIXTURE) == ["cn", "jp", "google", "spaced"]


def test_parse_tag_list_lowercases():
    assert parse_tag_list("YouTube\nTelegram\n") == ["youtube", "telegram"]
    assert parse_tag_list("") == []
    assert parse_tag_list("\n\n# only comments\n") == []


AVAILABLE_CODES_FIXTURE = """\
Available codes:
youtube
telegram
"""


def test_parse_tag_list_skips_header_lines_with_colon():
    assert parse_tag_list(AVAILABLE_CODES_FIXTURE) == ["youtube", "telegram"]


def test_list_tags_uses_fixture_without_subprocess(tmp_path: Path):
    dat = tmp_path / "geosite.dat"
    dat.write_text("dummy", encoding="utf-8")
    with patch("tags.subprocess.run") as run:
        out = list_tags("geosite", dat, geoview_output=TAG_FIXTURE)
        run.assert_not_called()
    assert out == ["cn", "jp", "google", "spaced"]


def test_list_tags_geoview_failure_returns_empty(tmp_path: Path):
    dat = tmp_path / "geoip.dat"
    dat.write_text("dummy", encoding="utf-8")
    with patch("tags.subprocess.run", return_value=type("R", (), {"returncode": 1, "stdout": "x"})()):
        assert list_tags("geoip", dat) == []


def test_list_tags_geoview_success(tmp_path: Path):
    dat = tmp_path / "geosite.dat"
    dat.write_text("dummy", encoding="utf-8")
    proc = type("R", (), {"returncode": 0, "stdout": "CN\nJP\n"})()
    with patch("tags.subprocess.run", return_value=proc) as run:
        assert list_tags("geosite", dat) == ["cn", "jp"]
        run.assert_called_once()
        cmd = run.call_args[0][0]
        assert cmd == ["geoview", "-type", "geosite", *LIST_ARGS, "-input", str(dat)]


def test_list_args_is_extract():
    assert LIST_ARGS == ["-action", "extract"]


def test_search_tags_prioritizes_prefix_matches():
    items = ["my-youtube-helper", "youtube", "youtube-music", "z-youtube"]
    assert search_tags(items, "you", 3) == [
        "youtube",
        "youtube-music",
        "my-youtube-helper",
    ]


def test_search_tags_requires_two_characters_and_respects_limit():
    items = ["google", "google-cn", "google-play", "my-google"]
    assert search_tags(items, "g", 30) == []
    assert search_tags(items, "GO", 2) == ["google", "google-cn"]
