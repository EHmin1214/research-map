#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
research-map renderer: map.json + sessions.json -> index.html (single file, no CDN).

  python render.py                  # 지도가 하나면 그것을 렌더
  python render.py --map mystudy --open
  python render.py --map mystudy --check    # 검증만 (경로·출처·순환·고아 노드)
  python render.py --map mystudy --serve    # 페이지에서 갱신 버튼을 쓰는 로컬 서버
  python render.py --map mystudy --out D:\\share\\map.html
"""
import json, os, sys, argparse, datetime, webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rmlib as R
import rmhistory as H

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")
TYPES = {"topic", "direction", "process", "result", "open", "artifact"}

# What makes a node not yet pull its weight. The page filters on the same list.
GAP_LABEL = {
    "noSummary":  "요약 없음",
    "noEvidence": "결과인데 근거 수치 없음",
    "noSources":  "출처 없음",
    "noNext":     "열린 질문인데 다음 단계 없음",
}


EFFORT = ("quick", "day", "long")        # under an hour / a day / longer


def norm_next(n, ids, errs, warns):
    """`next` items may be a plain string or {text, due, effort, blockedBy, why}."""
    out = []
    for it in n.get("next") or []:
        if isinstance(it, str):
            out.append({"text": it})
            continue
        if not isinstance(it, dict) or not it.get("text"):
            errs.append("%s: next item needs text" % n["id"])
            continue
        d = {"text": it["text"]}
        if it.get("due"):
            try:
                datetime.date(*[int(x) for x in str(it["due"]).split("-")])
                d["due"] = it["due"]
            except Exception:
                errs.append("%s: bad due %r (use YYYY-MM-DD)" % (n["id"], it["due"]))
        if it.get("effort"):
            if it["effort"] in EFFORT:
                d["effort"] = it["effort"]
            else:
                errs.append("%s: bad effort %r (%s)" % (n["id"], it["effort"], "|".join(EFFORT)))
        bb = it.get("blockedBy") or []
        if isinstance(bb, str):
            bb = [bb]
        if bb:
            d["blockedBy"] = bb
            for b in bb:
                if b not in ids and b.replace("-", "").isalnum() and "-" in b:
                    warns.append("%s: blockedBy %r looks like a node id but no such node" % (n["id"], b))
        if it.get("why"):
            d["why"] = it["why"]
        out.append(d)
    return out


def gaps_of(n):
    g = []
    if not n.get("summary"):
        g.append("noSummary")
    if n.get("type") == "result" and not n.get("evidence"):
        g.append("noEvidence")
    if n.get("type") in ("result", "process") and not n.get("sources"):
        g.append("noSources")
    if n.get("type") == "open" and not n.get("next"):
        g.append("noNext")
    return g
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
    nxt = {}
    for n in nodes:
        if n.get("id") and n.get("next"):
            nxt[n["id"]] = norm_next(n, ids, errs, warns)
    return errs, warns, {n['id']: gaps_of(n) for n in nodes if n.get('id')}, nxt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--serve", action="store_true",
                    help="렌더한 뒤 localhost 서버를 띄워 페이지에서 갱신 버튼을 쓴다")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()

    name = R.resolve_map(args.map)
    d, cfg = R.map_dir(name), R.load_config(name)
    map_p, sess_p = os.path.join(d, "map.json"), os.path.join(d, "sessions.json")
    out = args.out or os.path.join(d, "index.html")

    if not os.path.exists(map_p):
        raise SystemExit("map.json 없음: %s" % map_p)
    m = json.load(open(map_p, encoding="utf-8"))
    sessions = json.load(open(sess_p, encoding="utf-8")) if os.path.exists(sess_p) else []

    errs, warns, gaps, nxt = validate(m, cfg, sessions)
    for w in warns:
        print("WARN  " + w)
    for e in errs:
        print("ERROR " + e)

    nodes = m.get("nodes") or []
    from collections import Counter
    print("[%s] nodes: %d  by type: %s" % (name, len(nodes), dict(Counter(n.get("type") for n in nodes))))
    print("        by status: %s" % dict(Counter(n.get("status") for n in nodes)))
    allnext = [i for v in nxt.values() for i in v]
    if allnext:
        blocked = sum(1 for i in allnext if i.get("blockedBy"))
        dated = sum(1 for i in allnext if i.get("due"))
        print("        열린 항목 %d개 — 기한 있는 것 %d · 막힌 것 %d"
              % (len(allnext), dated, blocked))
    flat = [k for v in gaps.values() for k in v]
    if flat:
        cnt = Counter(flat)
        print("        채울 곳: " + " · ".join("%s %d개" % (GAP_LABEL[k], c)
                                              for k, c in cnt.most_common()))
        worst = [i for i, v in gaps.items() if "noEvidence" in v][:6]
        if worst:
            ttl = {n["id"]: n.get("title") for n in nodes}
            print("        근거 없는 결과 예: " + ", ".join(ttl.get(i, i) for i in worst))
    if errs:
        raise SystemExit("%d error(s) — map.json 을 먼저 고치세요" % len(errs))
    if args.check:
        return

    # Record what moved since the last render. No movement -> no revision.
    revs, created = H.record(d, m)
    marks = H.node_marks(revs)
    if created and created.get("baseline"):
        print("변경 이력 기준선을 잡았습니다 (rev1). 다음 갱신부터 바뀐 것만 보입니다.")
    elif created:
        latest = H.summarise(revs, created["rev"] - 1)
        print("이번 판 rev%d — 새 노드 %d개 · 바뀐 노드 %d개"
              % (created["rev"], len(latest["added"]), len(latest["changed"])))
        for f in latest["statusFlips"][:8]:
            t = next((n.get("title") for n in nodes if n.get("id") == f["id"]), f["id"])
            print("   상태 %s → %s   %s" % (f["from"], f["to"], t))
    elif revs:
        print("지도 내용은 직전 판(rev%d)과 같습니다." % revs[-1]["rev"])

    slim = [{k: s.get(k) for k in ("sessionId", "project", "source", "cwd", "start", "end",
                                   "userPrompts", "firstPrompt", "digest", "compactions")}
            for s in sessions]
    data = {"map": m, "sessions": slim, "mapName": name, "lang": cfg.get("lang") or "ko",
            "revisions": revs, "marks": marks, "gaps": {k: v for k, v in gaps.items() if v}, "next": nxt,
            "resumeCmd": {"claude-code": "claude --resume ", "codex": "codex resume ", "markdown": ""},
            "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    payload = "window.RM_DATA = " + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + ";"
    html = open(TEMPLATE, encoding="utf-8").read()
    html = html.replace("/*__DATA__*/", payload).replace("__TITLE__", m.get("title") or "연구 지도")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("wrote %s (%d KB)" % (out, len(html.encode("utf-8")) // 1024))
    if args.serve:
        import rmserve
        rmserve.serve(name, d, os.path.dirname(os.path.abspath(__file__)),
                      port=args.port, open_browser=True)
        return
    if args.open:
        webbrowser.open("file:///" + os.path.abspath(out).replace("\\", "/"))


if __name__ == "__main__":
    main()
