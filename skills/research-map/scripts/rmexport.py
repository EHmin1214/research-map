# -*- coding: utf-8 -*-
"""research-map: export a map (or a subtree) as Markdown for writing.

    python rmexport.py --map tis                      # whole map
    python rmexport.py --map tis --node rat           # one subtree
    python rmexport.py --map tis --checklist          # withdrawn/refuted numbers — do-not-cite list
    python rmexport.py --map tis --out draft.md       # write here instead of maps/<name>/exports/

Without --out the file lands in maps/<name>/exports/ and the path is printed.
The page has the same two exports as buttons (node panel → subtree, Changes → checklist),
built from the same fields, so what you download there matches what this prints.
"""
import argparse, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rmlib as R

STAT = {"ongoing": "진행 중", "done": "완료", "confirmed": "확인됨", "refuted": "반증", "withdrawn": "철회",
        "inconclusive": "미결", "abandoned": "중단", "open": "열림", "blocked": "막힘", "planned": "계획"}
STAT_EN = {k: k for k in STAT}
TYPE = {"topic": "주제", "direction": "방향", "process": "과정", "result": "결과", "open": "열린 질문", "artifact": "산출물"}
TYPE_EN = {"topic": "topic", "direction": "direction", "process": "process", "result": "result",
           "open": "open question", "artifact": "artifact"}
DEAD = ("withdrawn", "refuted", "abandoned")


def sort_key(n):
    return (1e9 if n.get("order") is None else n["order"], (n.get("period") or {}).get("start") or "9999", n.get("title") or "")


def period(n):
    p = n.get("period") or {}
    if not p.get("start"):
        return ""
    return p["start"] if not p.get("end") or p["end"] == p["start"] else "%s ~ %s" % (p["start"], p["end"])


def next_text(x, by=None):
    if isinstance(x, str):
        return x
    bits = [x.get("text") or ""]
    if x.get("due"):
        bits.append("(기한 %s)" % x["due"])
    if x.get("blockedBy"):
        by = by or {}
        bits.append("— 막힘: " + ", ".join((by.get(b) or {}).get("title") or b for b in x["blockedBy"]))
    return " ".join(b for b in bits if b)


def source_line(s):
    k, ref = s.get("kind"), s.get("ref") or ""
    if k == "session":
        return "세션 %s" % ref[:8]
    if k == "url":
        return "[%s](%s)" % (s.get("label") or ref, ref)
    return "%s `%s`" % (s.get("label") or k, ref) if s.get("label") else "`%s`" % ref


def node_md(n, depth, lang, kids, by=None, heading=True):
    st = (STAT_EN if lang == "en" else STAT).get(n.get("status"), n.get("status"))
    ty = (TYPE_EN if lang == "en" else TYPE).get(n.get("type"), n.get("type"))
    h = "#" * min(6, depth + 1)
    out = (["%s %s" % (h, n.get("title") or n["id"])] if heading else []) + [
           "*%s · %s%s*" % (ty, st, (" · " + period(n)) if period(n) else ""), ""]
    if n.get("summary"):
        out += [n["summary"], ""]
    if n.get("evidence"):
        out += ["**근거·수치**" if lang != "en" else "**Evidence**"]
        out += ["- " + e for e in n["evidence"]] + [""]
    if n.get("detail"):
        out += [n["detail"].strip(), ""]
    if n.get("next"):
        out += ["**더 파볼 것**" if lang != "en" else "**Next**"]
        out += ["- " + next_text(x, by) for x in n["next"]] + [""]
    if n.get("sources"):
        out += [("출처: " if lang != "en" else "Sources: ") + " · ".join(source_line(s) for s in n["sources"]), ""]
    for c in sorted(kids.get(n["id"], []), key=sort_key):
        out += node_md(c, depth + 1, lang, kids, by)
    return out


def export_tree(m, root_id, lang):
    nodes = m.get("nodes") or []
    kids = {}
    for n in nodes:
        kids.setdefault(n.get("parent"), []).append(n)
    by = {n["id"]: n for n in nodes}
    if root_id:
        if root_id not in by:
            raise SystemExit("노드 없음: %s" % root_id)
        roots = [by[root_id]]
        title = by[root_id].get("title") or root_id
    else:
        roots = sorted(kids.get(None, []), key=sort_key)
        title = m.get("title") or "연구 지도"
    out = ["# " + title, "", "_%s · %s_" % (m.get("updatedAt") or "", datetime.date.today().isoformat()), ""]
    if not root_id and m.get("summary"):
        out += [m["summary"], ""]
    for r in roots:
        out += node_md(r, 0 if root_id else 1, lang, kids, by, heading=not root_id)
    return "\n".join(out).rstrip() + "\n"


def path_of(n, by):
    p, cur = [], n
    while cur is not None:
        p.append(cur.get("title") or cur["id"])
        cur = by.get(cur.get("parent"))
    return " › ".join(reversed(p[1:])) if len(p) > 1 else ""


def export_checklist(m, lang):
    """Numbers that must not reach the paper: everything on withdrawn/refuted/abandoned nodes,
    plus 'inconclusive' nodes as conditional. Same rule as the page's checklist button."""
    nodes = m.get("nodes") or []
    by = {n["id"]: n for n in nodes}
    dead = sorted([n for n in nodes if n.get("status") in DEAD], key=lambda n: (n.get("status"), sort_key(n)))
    cond = sorted([n for n in nodes if n.get("status") == "inconclusive"], key=sort_key)
    en = lang == "en"
    out = ["# " + (m.get("title") or "연구 지도") + (" — do-not-cite checklist" if en else " — 철회 수치 체크리스트"), "",
           "_%s_" % datetime.date.today().isoformat(), "",
           ("Every number below sits on a withdrawn, refuted or abandoned node. Tick each one as you "
            "confirm it is absent from the manuscript." if en else
            "아래 수치는 전부 철회·반증·중단된 노드에 있는 값이다. 원고에 없음을 확인하면서 하나씩 체크한다."), ""]
    for n in dead:
        st = (STAT_EN if en else STAT).get(n["status"], n["status"])
        out += ["## ❌ %s  *(%s)*" % (n.get("title") or n["id"], st), "_%s_" % path_of(n, by), ""]
        if n.get("summary"):
            out += ["- [ ] " + n["summary"]]
        for e in n.get("evidence") or []:
            out += ["- [ ] " + e]
        out += [""]
    if cond:
        out += ["## ⚠ " + ("Conditional (inconclusive) — cite only with the caveat" if en else "조건부 (미결) — 단서 없이 인용 금지"), ""]
        for n in cond:
            out += ["- [ ] **%s** — %s" % (n.get("title") or n["id"], n.get("summary") or "")]
        out += [""]
    return "\n".join(out).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map")
    ap.add_argument("--node", help="이 노드 아래만")
    ap.add_argument("--checklist", action="store_true", help="철회·반증 수치 체크리스트")
    ap.add_argument("--out", help="출력 파일 (기본: maps/<name>/exports/…)")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args()
    name = R.resolve_map(a.map)
    d, cfg = R.map_dir(name), R.load_config(name)
    m = json.load(open(os.path.join(d, "map.json"), encoding="utf-8"))
    lang = cfg.get("lang") or "ko"
    text = export_checklist(m, lang) if a.checklist else export_tree(m, a.node, lang)
    if a.stdout:
        sys.stdout.write(text)
        return
    if a.out:
        out = a.out
    else:
        tag = "checklist" if a.checklist else (a.node or "all")
        out = os.path.join(d, "exports", "%s-%s-%s.md" % (name, tag, datetime.date.today().isoformat()))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("wrote %s (%d lines)" % (out, text.count("\n")))


if __name__ == "__main__":
    main()
