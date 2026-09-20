# -*- coding: utf-8 -*-
"""research-map: what changed in the map, recorded automatically.

The agent edits map.json freely; nobody has to remember to write a changelog.
On every render we diff the map against the last snapshot and, when something
actually moved, append a revision. Rendering an unchanged map records nothing,
so the history stays meaningful and `render.py` is safe to run repeatedly.

Files, inside the map directory:
  history/snapshot.json    the map as of the last recorded revision
  history/revisions.json   {"revisions": [ ... ]} newest last

A revision:
  {"rev": 3, "at": "2026-09-15 14:02", "nodes": 95,
   "added": ["id", ...], "removed": ["id", ...],
   "changed": [{"id": "...", "major": true, "fields": {...}}]}

The first recorded revision is a baseline: it fixes the starting point without
claiming that every existing node was just created.
"""
import json, os, datetime

# A change to these is a real turn in the research, not an edit.
MAJOR = ("status", "title", "parent", "type")
# Substance that accumulates on a node.
LISTS = ("evidence", "next", "sources", "links")   # tags are classification, not substance
TEXTS = ("summary", "detail")

KEEP_REVISIONS = 60


def _hist_dir(map_dir):
    return os.path.join(map_dir, "history")


def _load(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def diff_nodes(prev_nodes, cur_nodes):
    prev = {n["id"]: n for n in prev_nodes if n.get("id")}
    cur = {n["id"]: n for n in cur_nodes if n.get("id")}
    added = [i for i in cur if i not in prev]
    removed = [i for i in prev if i not in cur]
    changed = []
    for i, b in cur.items():
        a = prev.get(i)
        if a is None:
            continue
        fields = {}
        for k in MAJOR:
            if a.get(k) != b.get(k):
                fields[k] = [a.get(k), b.get(k)]
        for k in TEXTS:
            if (a.get(k) or "") != (b.get(k) or ""):
                fields[k] = "edited"
        for k in LISTS:
            la, lb = a.get(k) or [], b.get(k) or []
            if la == lb:
                continue
            new = [x for x in lb if x not in la]
            gone = [x for x in la if x not in lb]
            fields[k] = {"added": len(new), "removed": len(gone),
                         "sample": [(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False))[:160]
                                    for x in new[:3]]}
        pa = (a.get("period") or {}).get("end")
        pb = (b.get("period") or {}).get("end")
        if pa != pb:
            fields["period"] = [pa, pb]
        if fields:
            changed.append({"id": i, "major": any(k in fields for k in MAJOR), "fields": fields})
    changed.sort(key=lambda c: (not c["major"], c["id"]))
    return added, removed, changed


def record(map_dir, m, when=None):
    """Append a revision if the map moved.

    Returns (revisions, created) — `created` is the new revision or None when
    nothing moved, so callers do not announce a change that did not happen.
    """
    hd = _hist_dir(map_dir)
    os.makedirs(hd, exist_ok=True)
    snap_p = os.path.join(hd, "snapshot.json")
    revs_p = os.path.join(hd, "revisions.json")
    revs = _load(revs_p, {}).get("revisions") or []
    nodes = m.get("nodes") or []
    at = when or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    created = None
    if not os.path.exists(snap_p):
        created = {"rev": 1, "at": at, "nodes": len(nodes), "baseline": True,
                   "added": [], "removed": [], "changed": []}
        revs.append(created)
    else:
        prev = _load(snap_p, {"nodes": []}).get("nodes") or []
        added, removed, changed = diff_nodes(prev, nodes)
        if not (added or removed or changed):
            return revs, None                # nothing moved; do not invent a revision
        created = {"rev": (revs[-1]["rev"] + 1) if revs else 1, "at": at,
                   "nodes": len(nodes), "added": added, "removed": removed,
                   "changed": changed}
        revs.append(created)

    revs = revs[-KEEP_REVISIONS:]
    json.dump({"nodes": nodes}, open(snap_p, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"revisions": revs}, open(revs_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return revs, created


def node_marks(revs):
    """Per node: the revision it first appeared in, and the one it last moved in."""
    first, last, last_major = {}, {}, {}
    for r in revs:
        if r.get("baseline"):
            continue
        for i in r.get("added") or []:
            first.setdefault(i, r["rev"])
            last[i] = r["rev"]
        for c in r.get("changed") or []:
            last[c["id"]] = r["rev"]
            if c.get("major"):
                last_major[c["id"]] = r["rev"]
    return {"first": first, "last": last, "lastMajor": last_major}


def summarise(revs, since_rev=0):
    """Counts for everything after `since_rev` — what the header badge shows."""
    add = set()
    chg = set()
    major = []
    for r in revs:
        if r["rev"] <= since_rev or r.get("baseline"):
            continue
        add |= set(r.get("added") or [])
        for c in r.get("changed") or []:
            chg.add(c["id"])
            if c.get("major") and "status" in c["fields"]:
                major.append({"id": c["id"], "from": c["fields"]["status"][0],
                              "to": c["fields"]["status"][1], "rev": r["rev"]})
    return {"added": sorted(add), "changed": sorted(chg - add), "statusFlips": major}
