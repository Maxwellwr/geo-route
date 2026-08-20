from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from confio import classify_line, parse_file, write_file, slugify, unique_slug, Group, Entry


def test_classify():
    assert classify_line("geosite:youtube") == "geosite"
    assert classify_line("geoip:telegram") == "geoip"
    assert classify_line("GEOSITE:YouTube") == "geosite"
    assert classify_line("GeoIP:Telegram") == "geoip"
    assert classify_line("1.2.3.4") == "cidr"
    assert classify_line("10.0.0.0/8") == "cidr"
    assert classify_line("example.com") == "domain"
    assert classify_line("playstation") == "domain"
    assert classify_line("999.1.1.1") is None
    assert classify_line("not a domain!") is None


def test_parse_geosite_geoip_lowercased(tmp_path: Path):
    p = tmp_path / "t.conf"
    p.write_text("[blocked-sites]\nGEOSITE:YouTube\nGeoIP:Telegram\n", encoding="utf-8")
    g = parse_file(p)
    assert [(e.value, e.kind) for e in g.entries] == [
        ("geosite:youtube", "geosite"),
        ("geoip:telegram", "geoip"),
    ]


def test_parse_title_description_and_fallback(tmp_path: Path):
    p = tmp_path / "sony.conf"
    p.write_text(
        "# PlayStation / Sony\n# Домены PSN\n\n[blocked-sites]\nplaystation.com\n",
        encoding="utf-8",
    )
    g = parse_file(p)
    assert g.slug == "sony"
    assert g.title == "PlayStation / Sony"
    assert g.description == "Домены PSN"
    assert g.title_from_file is True
    assert g.entries == [Entry("blocked-sites", "playstation.com", "domain")]

    q = tmp_path / "custom.conf"
    q.write_text("[only-ru]\nmyip.ru\n", encoding="utf-8")
    g2 = parse_file(q)
    assert g2.title == "custom"
    assert g2.description == ""
    assert g2.title_from_file is False


def test_write_roundtrip_mixed(tmp_path: Path):
    p = tmp_path / "mix.conf"
    g = Group(
        slug="mix",
        path=p,
        title="Mix",
        description="desc line",
        title_from_file=True,
        entries=[
            Entry("blocked-sites", "a.com", "domain"),
            Entry("blocked-sites", "geosite:qt", "geosite"),
            Entry("blocked-sites", "1.2.3.4/24", "cidr"),
            Entry("only-ru", "myip.ru", "domain"),
        ],
    )
    write_file(g)
    g2 = parse_file(p)
    assert g2.title == "Mix"
    assert g2.description == "desc line"
    assert [(e.set_name, e.value, e.kind) for e in g2.entries] == [
        ("blocked-sites", "a.com", "domain"),
        ("blocked-sites", "geosite:qt", "geosite"),
        ("blocked-sites", "1.2.3.4/24", "cidr"),
        ("only-ru", "myip.ru", "domain"),
    ]


def test_write_without_header_stays_headerless_until_titled(tmp_path: Path):
    p = tmp_path / "x.conf"
    p.write_text("[blocked-sites]\na.com\n", encoding="utf-8")
    g = parse_file(p)
    g.entries.append(Entry("blocked-sites", "b.com", "domain"))
    write_file(g)
    text = p.read_text(encoding="utf-8")
    assert not text.startswith("#")
    assert "b.com" in text


def test_slugify_and_unique(tmp_path: Path):
    assert slugify("PlayStation / Sony") == "playstation-sony"
    (tmp_path / "playstation-sony.conf").write_text("[blocked-sites]\na.com\n", encoding="utf-8")
    assert unique_slug(tmp_path, "PlayStation / Sony") == "playstation-sony-2"
