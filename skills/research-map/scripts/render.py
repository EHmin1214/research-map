#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
research-map renderer: map.json + sessions.json -> index.html (single file, no CDN).

  python render.py                  # 지도가 하나면 그것을 렌더
  python render.py --map tis --open
  python render.py --map tis --check    # 검증만 (경로·출처·순환·고아 노드)
  python render.py --map tis --out D:\\share\\map.html
"""
import json, os, sys, argparse, datetime, webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rmlib as R

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")
TYPES = {"topic", "direction", "process", "result", "open", "artifact"}
STATUS = {"ongoing", "done", "confirmed", "refuted", "withdrawn", "inconclusive",
          "abandoned", "open", "blocked", "planned"}


def validate(m, cfg, sessions):
    errs, warns = [], []
    nodes = m.get("nodes") or []
    mem_dirs = [R.expand(p) for p in (cfg.get("memoryDirs") or [])]
    known_sessions = {s["sessionId"] for s in sessions}
    ids = {}
    for n in nodes:
        i = n.get("id")
        if not i:
            errs.append("node without id: %r" % (n.get("title"),))
            continue
        if i in ids:
            errs.append("duplicate id: %s" % i)
        ids[i] = n
    for n in nodes:
        i = n.get("id")
        if n.get("type") not in TYPES:
            errs.append("%s: bad type %r" % (i, n.get("type")))
        if n.get("status") not in STATUS:
            errs.append("%s: bad status %r" % (i, n.get("status")))
        p = n.get("parent")
        if p is not None and p not in ids:
            errs.append("%s: parent %r not found" % (i, p))
        if not n.get("title"):
            errs.append("%s: missing title" % i)
        if not n.get("summary"):
            warns.append("%s: missing summary" % i)
        if n.get("type") in ("result", "process") and not n.get("sources"):
            warns.append("%s: %s node without sources" % (i, n["type"]))
        for s in n.get("sources") or []:
            kind = s.get("kind")
            if kind not in ("session", "file", "doc", "memory", "url"):
                errs.append("%s: bad source kind %r" % (i, kind))
            elif kind in ("file", "doc"):
                if not os.path.exists(s.get("ref", "")):
                    warns.append("%s: source path missing on disk: %s" % (i, s.get("ref")))
            elif kind == "memory":
                hit = None
                for d in mem_dirs:
                    cand = os.path.join(d, s.get("ref", ""))
                    if os.path.exists(cand):
                        hit = cand
                        break
                if hit:
                    s["path"] = hit
                else:
                    warns.append("%s: memory file missing: %s" % (i, s.get("ref")))
            elif kind == "session":
                if known_sessions and s.get("ref") not in known_sessions:
                    warns.append("%s: session not in index: %s" % (i, (s.get("ref") or "")[:8]))
        for l in n.get("links") or []:
            if l not in ids:
                warns.append("%s: link to unknown node %s" % (i, l))
        seen, cur = set(), n
        while cur is not None:
            if cur["id"] in seen:
                errs.append("cycle through %s" % cur["id"])
                break
            seen.add(cur["id"])
            cur = ids.get(cur.get("parent"))
    tops = [n for n in nodes if n.get("parent") is None]
    if len(tops) > 9:
        warns.append("%d top-level topics (스키마 권고 9개 이하)" % len(tops))
    return errs, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()

    name = R.resolve_map(args.map)
    d, cfg = R.map_dir(name), R.load_config(name)
    map_p, sess_p = os.path.join(d, "map.json"), os.path.join(d, "sessions.json")
    out = args.out or os.path.join(d, "index.html")

    if not os.path.exists(map_p):
        raise SystemExit("map.json 없음: %s" % map_p)
    m = json.load(open(map_p, encoding="utf-8"))
    sessions = json.load(open(sess_p, encoding="utf-8")) if os.path.exists(sess_p) else []

    errs, warns = validate(m, cfg, sessions)
    for w in warns:
        print("WARN  " + w)
    for e in errs:
        print("ERROR " + e)

    nodes = m.get("nodes") or []
    from collections import Counter
    print("[%s] nodes: %d  by type: %s" % (name, len(nodes), dict(Counter(n.get("type") for n in nodes))))
    print("        by status: %s" % dict(Counter(n.get("status") for n in nodes)))
    if errs:
        raise SystemExit("%d error(s) — map.json 을 먼저 고치세요" % len(errs))
    if args.check:
        return

    slim = [{k: s.get(k) for k in ("sessionId", "project", "source", "cwd", "start", "end",
                                   "userPrompts", "firstPrompt", "digest", "compactions")}
            for s in sessions]
    data = {"map": m, "sessions": slim, "mapName": name, "lang": cfg.get("lang") or "ko",
            "resumeCmd": {"claude-code": "claude --resume ", "codex": "codex resume ", "markdown": ""},
            "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    payload = "window.RM_DATA = " + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + ";"
    html = open(TEMPLATE, encoding="utf-8").read()
    html = html.replace("/*__DATA__*/", payload).replace("__TITLE__", m.get("title") or "연구 지도")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("wrote %s (%d KB)" % (out, len(html.encode("utf-8")) // 1024))
    if args.open:
        webbrowser.open("file:///" + os.path.abspath(out).replace("\\", "/"))


if __name__ == "__main__":
    main()
