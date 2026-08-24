from pathlib import Path

import pytest


@pytest.fixture
def geo_dir(tmp_path: Path) -> Path:
    (tmp_path / "geo.d").mkdir()
    return tmp_path


@pytest.fixture
def client(geo_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "apply.iter_apply",
        lambda **k: iter([("log", "ok"), ("done", {"exit": 0})]),
    )
    monkeypatch.setattr("lookup.iter_lookup", lambda domains: [])
    monkeypatch.setenv("GEO_UI_DIST", str(geo_dir / "missing-dist"))
    from app import create_app

    app = create_app(geo_dir=geo_dir)
    return app.test_client()


def _assert_sse(resp):
    assert resp.status_code == 200
    assert "event-stream" in (resp.mimetype or "")
    body = resp.get_data(as_text=True)
    assert "event: log" in body
    assert "event: done" in body


def test_get_groups_empty(client):
    r = client.get("/api/groups")
    assert r.status_code == 200
    data = r.get_json()
    assert data == {"groups": [], "collisions": []}


def test_get_missing_group_404(client):
    r = client.get("/api/groups/no-such")
    assert r.status_code == 404
    assert r.get_json() == {"error": r.get_json()["error"]}
    assert "error" in r.get_json()


def test_get_missing_entries_404(client):
    r = client.get("/api/groups/no-such/entries")
    assert r.status_code == 404
    assert "error" in r.get_json()


def test_post_group_writes_file_and_returns_sse(client, geo_dir: Path):
    r = client.post("/api/groups", json={"title": "PlayStation", "description": "PSN"})
    _assert_sse(r)
    path = geo_dir / "geo.d" / "playstation.conf"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# PlayStation")
    assert "PSN" in text


def test_get_group_and_entries_after_post(client):
    client.post("/api/groups", json={"title": "Sony"})
    r = client.post(
        "/api/groups/sony/entries",
        json={"set": "blocked-sites", "value": "playstation.com"},
    )
    _assert_sse(r)

    g = client.get("/api/groups/sony").get_json()
    assert g["slug"] == "sony"
    assert g["title"] == "Sony"
    assert g["entries"][0]["id"] == 0
    assert g["entries"][0]["set"] == "blocked-sites"
    assert g["entries"][0]["value"] == "playstation.com"
    assert g["entries"][0]["kind"] == "domain"

    e = client.get("/api/groups/sony/entries").get_json()
    assert e == {"entries": g["entries"]}


def test_post_invalid_domain_400_no_garbage(client, geo_dir: Path):
    client.post("/api/groups", json={"title": "Keep"})
    path = geo_dir / "geo.d" / "keep.conf"
    before = path.read_text(encoding="utf-8")
    r = client.post(
        "/api/groups/keep/entries",
        json={"set": "blocked-sites", "value": "not a domain!"},
    )
    assert r.status_code == 400
    assert "error" in r.get_json()
    assert path.read_text(encoding="utf-8") == before
    assert "not a domain" not in path.read_text(encoding="utf-8")


def test_post_unknown_geosite_tag_saves(client, geo_dir: Path):
    client.post("/api/groups", json={"title": "Tags"})
    r = client.post(
        "/api/groups/tags/entries",
        json={"set": "blocked-sites", "value": "geosite:not-a-real-tag"},
    )
    _assert_sse(r)
    text = (geo_dir / "geo.d" / "tags.conf").read_text(encoding="utf-8")
    assert "geosite:not-a-real-tag" in text


def test_post_geosite_mixed_case_saves_lower(client, geo_dir: Path):
    client.post("/api/groups", json={"title": "Case"})
    r = client.post(
        "/api/groups/case/entries",
        json={"set": "blocked-sites", "value": "GEOSITE:YouTube"},
    )
    _assert_sse(r)
    text = (geo_dir / "geo.d" / "case.conf").read_text(encoding="utf-8")
    assert "geosite:youtube" in text
    assert "YouTube" not in text


def test_post_entry_rejects_unknown_set(client, geo_dir: Path):
    client.post("/api/groups", json={"title": "Sets"})
    path = geo_dir / "geo.d" / "sets.conf"
    before = path.read_text(encoding="utf-8")
    r = client.post(
        "/api/groups/sets/entries",
        json={"set": "custom-set", "value": "example.com"},
    )
    assert r.status_code == 400
    assert "error" in r.get_json()
    assert path.read_text(encoding="utf-8") == before


def test_patch_and_delete_group(client, geo_dir: Path):
    client.post("/api/groups", json={"title": "Old"})
    r = client.patch("/api/groups/old", json={"title": "New Title", "description": "d"})
    _assert_sse(r)
    g = client.get("/api/groups/old").get_json()
    assert g["title"] == "New Title"
    assert g["description"] == "d"
    text = (geo_dir / "geo.d" / "old.conf").read_text(encoding="utf-8")
    assert text.startswith("# New Title")

    r = client.delete("/api/groups/old")
    _assert_sse(r)
    assert not (geo_dir / "geo.d" / "old.conf").exists()
    assert client.get("/api/groups/old").status_code == 404


def test_patch_entry_set_and_move_group(client):
    client.post("/api/groups", json={"title": "A"})
    client.post("/api/groups", json={"title": "B"})
    client.post(
        "/api/groups/a/entries",
        json={"set": "blocked-sites", "value": "example.com"},
    )
    r = client.patch(
        "/api/groups/a/entries/0",
        json={"group": "b", "set": "only-ru"},
    )
    _assert_sse(r)
    assert client.get("/api/groups/a/entries").get_json()["entries"] == []
    moved = client.get("/api/groups/b/entries").get_json()["entries"]
    assert len(moved) == 1
    assert moved[0]["value"] == "example.com"
    assert moved[0]["set"] == "only-ru"
    assert moved[0]["kind"] == "domain"


def test_delete_entry(client, geo_dir: Path):
    client.post("/api/groups", json={"title": "Del"})
    client.post(
        "/api/groups/del/entries",
        json={"set": "only-ru", "value": "myip.ru"},
    )
    r = client.delete("/api/groups/del/entries/0")
    _assert_sse(r)
    assert client.get("/api/groups/del/entries").get_json()["entries"] == []
    text = (geo_dir / "geo.d" / "del.conf").read_text(encoding="utf-8")
    assert "myip.ru" not in text


def test_status_last_exit_after_apply(client):
    before = client.get("/api/status").get_json()
    assert before["last_exit"] is None
    r = client.post("/api/groups", json={"title": "St"})
    _assert_sse(r)
    after = client.get("/api/status").get_json()
    assert after["last_exit"] == 0


def test_tags_type_query(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("tags.list_tags", lambda kind, dat, **k: ["youtube", "google"])
    r = client.get("/api/tags?type=geosite")
    assert r.status_code == 200
    assert r.get_json() == {"tags": ["youtube", "google"]}
    bad = client.get("/api/tags")
    assert bad.status_code == 400
    assert "error" in bad.get_json()


def test_index_503_without_dist(client):
    r = client.get("/")
    assert r.status_code == 503
    assert "error" in r.get_json()
    assert client.get("/api/groups").status_code == 200


def test_index_serves_dist(geo_dir: Path, monkeypatch: pytest.MonkeyPatch):
    dist = geo_dir / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html>geo</html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(
        "apply.iter_apply",
        lambda **k: iter([("log", "ok"), ("done", {"exit": 0})]),
    )
    monkeypatch.setenv("GEO_UI_DIST", str(dist))
    from app import create_app

    c = create_app(geo_dir=geo_dir).test_client()
    r = c.get("/")
    assert r.status_code == 200
    assert b"geo" in r.get_data()
    js = c.get("/assets/app.js")
    assert js.status_code == 200
    assert b"console.log" in js.get_data()


def test_create_app_does_not_bind(geo_dir: Path, monkeypatch: pytest.MonkeyPatch):
    def boom(*a, **k):
        raise AssertionError("detect_lan_ipv4 / run must not be called")

    monkeypatch.setattr("bindaddr.detect_lan_ipv4", boom)
    monkeypatch.setenv("GEO_UI_DIST", str(geo_dir / "missing-dist"))
    from flask import Flask
    from app import create_app

    monkeypatch.setattr(Flask, "run", boom)
    app = create_app(geo_dir=geo_dir, apply_cmd=["true"])
    assert app.config["GEO_DIR"] == geo_dir
    assert app.config["APPLY_LOCK"] == str(geo_dir / "geo-ui.lock")


def test_default_geo_paths():
    from app import DEFAULT_GEO_DIR, DEFAULT_GEO_VAR

    assert DEFAULT_GEO_DIR == "/opt/etc/geo"
    assert DEFAULT_GEO_VAR == "/opt/var/geo"


def test_collisions_in_groups_list(client):
    client.post("/api/groups", json={"title": "One"})
    client.post("/api/groups", json={"title": "Two"})
    client.post(
        "/api/groups/one/entries",
        json={"set": "blocked-sites", "value": "dup.com"},
    )
    client.post(
        "/api/groups/two/entries",
        json={"set": "only-ru", "value": "dup.com"},
    )
    data = client.get("/api/groups").get_json()
    assert any(c["value"] == "dup.com" for c in data["collisions"])
    hit = next(c for c in data["collisions"] if c["value"] == "dup.com")
    assert ["one", "blocked-sites"] in hit["hits"]
    assert ["two", "only-ru"] in hit["hits"]


def test_add_domain_lookup_in_sse(geo_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "apply.iter_apply",
        lambda **k: iter([("log", "ok"), ("done", {"exit": 0})]),
    )
    monkeypatch.setattr(
        "lookup.iter_lookup",
        lambda domains: ["lookup %s → 1.2.3.4" % domains[0]],
    )
    monkeypatch.setenv("GEO_UI_DIST", str(geo_dir / "missing-dist"))
    from app import create_app

    c = create_app(geo_dir=geo_dir).test_client()
    c.post("/api/groups", json={"title": "Sony"})
    r = c.post(
        "/api/groups/sony/entries",
        json={"set": "blocked-sites", "value": "playstation.com"},
    )
    body = r.get_data(as_text=True)
    assert "lookup playstation.com" in body
    assert "1.2.3.4" in body


def test_add_cidr_skips_lookup(geo_dir: Path, monkeypatch: pytest.MonkeyPatch):
    seen = []
    monkeypatch.setattr(
        "apply.iter_apply",
        lambda **k: iter([("log", "ok"), ("done", {"exit": 0})]),
    )
    monkeypatch.setattr("lookup.iter_lookup", lambda domains: seen.extend(domains) or [])
    monkeypatch.setenv("GEO_UI_DIST", str(geo_dir / "missing-dist"))
    from app import create_app

    c = create_app(geo_dir=geo_dir).test_client()
    c.post("/api/groups", json={"title": "Net"})
    c.post(
        "/api/groups/net/entries",
        json={"set": "blocked-sites", "value": "1.2.3.4"},
    )
    assert seen == []
