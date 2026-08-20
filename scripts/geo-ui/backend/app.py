from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

import apply
import tags
from collisions import find_collisions
from confio import (
    SETS,
    Entry,
    Group,
    canonicalize_value,
    classify_line,
    list_groups,
    parse_file,
    unique_slug,
    write_file,
)

DEFAULT_GEO_DIR = "/opt/etc/geo"
DEFAULT_GEO_VAR = "/opt/var/geo"


def create_app(geo_dir=None, apply_cmd=None):
    geo_dir = Path(geo_dir or os.environ.get("GEO_DIR", DEFAULT_GEO_DIR))
    if os.environ.get("GEO_VAR"):
        geo_var = Path(os.environ["GEO_VAR"])
    elif str(geo_dir).replace("\\", "/") == DEFAULT_GEO_DIR:
        geo_var = Path(DEFAULT_GEO_VAR)
    else:
        geo_var = geo_dir
    dist = Path(
        os.environ.get(
            "GEO_UI_DIST",
            Path(__file__).resolve().parent.parent / "frontend" / "dist",
        )
    )
    if apply_cmd is None:
        env_cmd = os.environ.get("GEO_UPDATE")
        apply_cmd = env_cmd.split() if env_cmd else None

    geo_d = geo_dir / "geo.d"
    geo_d.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__)
    app.config["GEO_DIR"] = geo_dir
    app.config["GEO_VAR"] = geo_var
    app.config["GEO_UI_DIST"] = dist
    app.config["APPLY_CMD"] = apply_cmd
    app.config["APPLY_LOCK"] = str(geo_var / "geo-ui.lock")
    app.config["LAST_EXIT"] = None
    app.config["TAG_CACHE"] = {}

    def err(msg: str, code: int):
        return jsonify(error=msg), code

    def group_file(slug: str) -> Path:
        return geo_d / (slug + ".conf")

    def load_group(slug: str) -> Group | None:
        path = group_file(slug)
        if not path.is_file():
            return None
        return parse_file(path)

    def entry_json(i: int, e: Entry) -> dict:
        return {"id": i, "set": e.set_name, "value": e.value, "kind": e.kind}

    def entries_json(g: Group) -> list[dict]:
        return [entry_json(i, e) for i, e in enumerate(g.entries)]

    def sse_apply():
        def gen():
            kwargs = {"lock_path": app.config["APPLY_LOCK"]}
            cmd = app.config.get("APPLY_CMD")
            if cmd is not None:
                kwargs["cmd"] = cmd
            for kind, data in apply.iter_apply(**kwargs):
                if kind == "done" and isinstance(data, dict) and "exit" in data:
                    app.config["LAST_EXIT"] = data["exit"]
                if kind == "log":
                    yield "event: log\ndata: %s\n\n" % json.dumps(
                        data, ensure_ascii=False
                    )
                else:
                    yield "event: done\ndata: %s\n\n" % json.dumps(data)

        return Response(gen(), mimetype="text/event-stream")

    def parse_value(set_name, value):
        if set_name not in SETS:
            return None, err("unknown set", 400)
        value = (value or "").strip()
        if not value:
            return None, err("value required", 400)
        kind = classify_line(value)
        if not kind:
            return None, err("invalid value", 400)
        return Entry(set_name, canonicalize_value(value, kind), kind), None

    @app.get("/api/groups")
    def api_groups():
        groups = list_groups(geo_d)
        return jsonify(
            groups=[
                {"slug": g.slug, "title": g.title, "description": g.description}
                for g in groups
            ],
            collisions=[
                {"value": c.value, "hits": [list(h) for h in c.hits]}
                for c in find_collisions(groups)
            ],
        )

    @app.post("/api/groups")
    def api_create_group():
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title:
            return err("title required", 400)
        slug = unique_slug(geo_d, title)
        group = Group(
            slug=slug,
            path=group_file(slug),
            title=title,
            description=data.get("description") or "",
            title_from_file=True,
        )
        write_file(group)
        return sse_apply()

    @app.get("/api/groups/<slug>")
    def api_get_group(slug):
        g = load_group(slug)
        if g is None:
            return err("group not found", 404)
        return jsonify(
            slug=g.slug,
            title=g.title,
            description=g.description,
            entries=entries_json(g),
        )

    @app.patch("/api/groups/<slug>")
    def api_patch_group(slug):
        g = load_group(slug)
        if g is None:
            return err("group not found", 404)
        data = request.get_json(silent=True) or {}
        if "title" in data:
            title = (data.get("title") or "").strip()
            if not title:
                return err("title required", 400)
            g.title = title
            g.title_from_file = True
        if "description" in data:
            g.description = data.get("description") or ""
        write_file(g)
        return sse_apply()

    @app.delete("/api/groups/<slug>")
    def api_delete_group(slug):
        path = group_file(slug)
        if not path.is_file():
            return err("group not found", 404)
        path.unlink()
        return sse_apply()

    @app.get("/api/groups/<slug>/entries")
    def api_entries(slug):
        g = load_group(slug)
        if g is None:
            return err("group not found", 404)
        return jsonify(entries=entries_json(g))

    @app.post("/api/groups/<slug>/entries")
    def api_add_entry(slug):
        g = load_group(slug)
        if g is None:
            return err("group not found", 404)
        data = request.get_json(silent=True) or {}
        entry, error = parse_value(data.get("set"), data.get("value"))
        if error:
            return error
        g.entries.append(entry)
        write_file(g)
        return sse_apply()

    @app.patch("/api/groups/<slug>/entries/<int:eid>")
    def api_patch_entry(slug, eid):
        g = load_group(slug)
        if g is None:
            return err("group not found", 404)
        if eid < 0 or eid >= len(g.entries):
            return err("entry not found", 404)
        data = request.get_json(silent=True) or {}
        entry = g.entries[eid]
        if "set" in data:
            if data["set"] not in SETS:
                return err("unknown set", 400)
            entry.set_name = data["set"]
        target = data.get("group")
        if target and target != slug:
            dest = load_group(target)
            if dest is None:
                return err("group not found", 404)
            g.entries.pop(eid)
            dest.entries.append(entry)
            write_file(g)
            write_file(dest)
        else:
            write_file(g)
        return sse_apply()

    @app.delete("/api/groups/<slug>/entries/<int:eid>")
    def api_delete_entry(slug, eid):
        g = load_group(slug)
        if g is None:
            return err("group not found", 404)
        if eid < 0 or eid >= len(g.entries):
            return err("entry not found", 404)
        g.entries.pop(eid)
        write_file(g)
        return sse_apply()

    @app.get("/api/tags")
    def api_tags():
        kind = request.args.get("type")
        if kind not in ("geosite", "geoip"):
            return err("type must be geosite or geoip", 400)
        cache = app.config["TAG_CACHE"]
        if kind not in cache:
            dat = geo_var / ("%s.dat" % kind)
            cache[kind] = tags.list_tags(kind, dat)
        return jsonify(tags=cache[kind])

    @app.get("/api/status")
    def api_status():
        counts = {}
        for name in ("blocked-sites", "only-ru", "blocked-sites-ip", "only-ru-ip"):
            path = geo_dir / name
            if not path.is_file():
                continue
            n = 0
            for line in path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s and not s.startswith("#"):
                    n += 1
            counts[name] = n
        return jsonify(last_exit=app.config["LAST_EXIT"], counts=counts)

    @app.get("/")
    def index():
        index_html = dist / "index.html"
        if not dist.is_dir() or not index_html.is_file():
            return err("frontend dist not found", 503)
        return send_from_directory(dist, "index.html")

    @app.get("/assets/<path:filename>")
    def static_assets(filename):
        return send_from_directory(dist / "assets", filename)

    return app
