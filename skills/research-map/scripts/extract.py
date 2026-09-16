#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
research-map extractor — transcripts -> per-session digests + session index.

  python extract.py                       # 지도가 하나면 그것을, 여럿이면 --map 필요
  python extract.py --map mystudy             # 증분: 새로 생기거나 길어진 세션만
  python extract.py --map mystudy --all       # 전체 재생성
  python extract.py --init one --title "그 대화 하나" --session 9a34d5ca
  python extract.py --list-maps
  python extract.py --init rat --title "랫 실험 지도"
  python extract.py --init chat --title "ChatGPT 연구" \
                    --source markdown:~/research-exports

Reads whatever the map's config.json lists under "sources" (Claude Code,
Codex, or a folder of exported chats from any other LLM). Digests keep user
prompts, assistant prose, tool names + key arguments, and compaction
summaries; they drop tool output, thinking, images and subagent chatter.
"""
import json, os, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rmlib as R


def digest_session(s, cfg):
    lines, pending = [], []
    meta = {"sessionId": s.sid, "project": s.group, "source": s.source, "path": s.path,
            "cwd": s.cwd, "start": None, "end": None, "userPrompts": 0, "assistantMsgs": 0,
            "toolCalls": 0, "filesTouched": set(), "firstPrompt": "", "compactions": 0}

    def flush():
        if pending:
            lines.extend(pending)
            del pending[:]

    for kind, ts, payload in s.events:
        if ts:
            meta["start"] = meta["start"] or ts
            meta["end"] = ts
        if kind == "user":
            txt = R.clean_user_text(payload)
            if not txt:
                continue
            flush()
            meta["userPrompts"] += 1
            if not meta["firstPrompt"]:
                meta["firstPrompt"] = txt[:200].replace("\n", " ")
            lines.append("\n### [%s] USER\n%s\n" % (ts, txt[:R.MAX_USER_CHARS]))
        elif kind == "summary":
            flush()
            meta["compactions"] += 1
            lines.append("\n### [%s] 컨텍스트 압축 요약\n%s\n" % (ts, payload[:R.MAX_SUMMARY_CHARS]))
        elif kind == "assistant":
            txt = (payload or "").strip()
            if not txt:
                continue
            flush()
            meta["assistantMsgs"] += 1
            if len(txt) > R.MAX_ASSISTANT_CHARS:
                txt = txt[:R.MAX_ASSISTANT_CHARS] + " …(생략)"
            lines.append("\n**ASSISTANT [%s]**\n%s\n" % (ts, txt))
        elif kind == "tool":
            name, inp = payload
            meta["toolCalls"] += 1
            if isinstance(inp, dict):
                fp = inp.get("file_path") or inp.get("notebook_path")
                if fp and name in ("Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch"):
                    meta["filesTouched"].add(fp)
            pending.append(("  · %s %s" % (name, R._tool_key(inp))).rstrip())
            if len(pending) > 40:
                del pending[39:]
                pending.append("  · …(도구 호출 다수 생략)")
    flush()

    meta["filesTouched"] = sorted(meta["filesTouched"])
    return meta, "\n".join(lines)


BODY_MARK = "<!-- body -->"


def render_head(meta):
    head = [
        "# Session %s" % meta["sessionId"],
        "- source: %s" % meta.get("source"),
        "- project: %s" % meta.get("project"),
        "- cwd: %s" % meta.get("cwd"),
        "- period: %s → %s" % (meta.get("start"), meta.get("end")),
        "- user prompts: %d, assistant msgs: %d, tool calls: %d, compactions: %d"
        % (meta.get("userPrompts", 0), meta.get("assistantMsgs", 0),
           meta.get("toolCalls", 0), meta.get("compactions", 0)),
        "- files written: %d" % len(meta.get("filesTouched") or []),
    ]
    if meta.get("filesTouched"):
        head.append("  " + "\n  ".join(meta["filesTouched"][:60]))
    return "\n".join(head)


def old_body(path):
    """The body of an existing digest, without its header."""
    try:
        txt = open(path, encoding="utf-8").read()
    except OSError:
        return ""
    i = txt.find(BODY_MARK)
    return txt[i + len(BODY_MARK):].lstrip("\n") if i >= 0 else ""


def merge_meta(prev, cur):
    """Counts add up; identity fields come from whichever run saw them first."""
    if not prev:
        return cur
    m = dict(cur)
    for k in ("userPrompts", "assistantMsgs", "toolCalls", "compactions"):
        m[k] = (prev.get(k) or 0) + (cur.get(k) or 0)
    for k in ("cwd", "start", "firstPrompt"):
        m[k] = prev.get(k) or cur.get(k)
    m["end"] = cur.get("end") or prev.get("end")
    m["filesTouched"] = sorted(set(prev.get("filesTouched") or []) |
                               set(cur.get("filesTouched") or []))
    return m


def carded_sessions(map_dir):
    """Session ids already covered by a card — one card may cover several."""
    out = set()
    cdir = os.path.join(map_dir, "cards")
    if not os.path.isdir(cdir):
        return out
    for f in os.listdir(cdir):
        if not f.endswith(".json"):
            continue
        try:
            c = json.load(open(os.path.join(cdir, f), encoding="utf-8"))
        except Exception:
            continue
        for sid in c.get("sessionIds") or []:
            out.add(sid)
    return out


def included(meta, inc):
    hay_cwd = (meta.get("cwd") or "")
    hay_path = meta.get("path") or ""
    want = inc.get("cwdContains") or []
    if want and not any(w.lower() in hay_cwd.lower() for w in want):
        return False
    want = inc.get("pathContains") or []
    if want and not any(w.lower() in hay_path.lower() for w in want):
        return False
    start = meta.get("start") or ""
    if inc.get("since") and start and start[:10] < inc["since"]:
        return False
    if inc.get("until") and start and start[:10] > inc["until"]:
        return False
    if meta["userPrompts"] < (inc.get("minPrompts") or 1):
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list-maps", action="store_true")
    ap.add_argument("--doctor", action="store_true", help="이 컴퓨터에서 뭘 읽을 수 있는지 점검")
    ap.add_argument("--init", metavar="NAME")
    ap.add_argument("--title")
    ap.add_argument("--session", action="append", default=[],
                    help="이 대화만 담는 지도. id 일부만 줘도 된다. --init 과 함께")
    ap.add_argument("--source", action="append", default=[],
                    help="kind:root  (예: codex:~/.codex/sessions). --init 과 함께 사용")
    args = ap.parse_args()

    if args.doctor:
        print("python      %s" % sys.version.split()[0])
        print("maps dir    %s" % R.MAPS)
        found = R.detect_sources()
        if found:
            for f in found:
                print("source      %-12s %-34s 기록 %s개%s"
                      % (f["kind"], f["root"], f["files"], "+" if f["files"] >= 500 else ""))
        else:
            print("source      (없음) — 내보낸 대화 폴더를 markdown 소스로 쓰세요")
        for d in R.detect_memory_dirs()[:5]:
            print("memory      %s" % d)
        maps = R.list_maps()
        print("maps        %s" % (", ".join(maps) or "(없음)"))
        if not maps:
            names = " ".join("--source %s:%s" % (f["kind"], f["root"]) for f in found)
            print("")
            print("시작하기:")
            print('  extract.py --init mystudy --title "내 연구" %s' % names)
        return

    if args.list_maps:
        maps = R.list_maps()
        if not maps:
            print("지도 없음. extract.py --init <이름> --title \"...\"")
        for m in maps:
            cfg = R.load_config(m)
            mp = os.path.join(R.map_dir(m), "map.json")
            n = len(json.load(open(mp, encoding="utf-8")).get("nodes", [])) if os.path.exists(mp) else 0
            print("%-16s %-28s 노드 %3d  소스 %s" % (
                m, cfg["title"], n, ", ".join(s["kind"] for s in cfg["sources"])))
        return

    if args.init:
        srcs = []
        for spec in args.source:
            kind, _, root = spec.partition(":")
            if kind not in R.SOURCES:
                raise SystemExit("모르는 소스 종류: %s (가능: %s)" % (kind, ", ".join(R.SOURCES)))
            srcs.append({"kind": kind, "root": root or "~/.claude/projects"})
        if not srcs:
            srcs = [{"kind": f["kind"], "root": f["root"], "label": f["label"]}
                    for f in R.detect_sources()]
            if srcs:
                print("이 컴퓨터에서 찾은 기록: " + ", ".join(x["kind"] for x in srcs))
        d = R.init_map(args.init, args.title, srcs or None)
        print("만들었습니다: %s" % d)
        mem = R.detect_memory_dirs()
        cp = os.path.join(d, "config.json")
        cfg = json.load(open(cp, encoding="utf-8"))
        if mem:
            cfg["memoryDirs"] = [m.replace(os.path.expanduser("~"), "~") for m in mem[:4]]
            print("메모리 폴더 %d개를 config 에 넣었습니다" % len(cfg["memoryDirs"]))
        if args.session:
            # A transcript's filename carries its id, for every source we read.
            cfg["include"]["pathContains"] = list(args.session)
            cfg["include"]["minPrompts"] = 1
            print("대화 %d개만 담는 지도입니다: %s" % (len(args.session), ", ".join(args.session)))
        json.dump(cfg, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("config.json 의 sources·include 를 손본 뒤:  extract.py --map %s" % args.init)
        return

    name = R.resolve_map(args.map)
    d, cfg = R.map_dir(name), R.load_config(name)
    dig_dir = os.path.join(d, "digests")
    state_p, index_p = os.path.join(d, "state.json"), os.path.join(d, "sessions.json")
    os.makedirs(dig_dir, exist_ok=True)

    state = {}
    if os.path.exists(state_p) and not args.all:
        state = json.load(open(state_p, encoding="utf-8"))
    index = {}
    if os.path.exists(index_p):
        index = {s["sessionId"]: s for s in json.load(open(index_p, encoding="utf-8"))}

    changed, seen, skipped, dups, excl = [], set(), 0, 0, 0
    for src in cfg["sources"]:
        kind = src.get("kind")
        reader = R.SOURCES.get(kind)
        if not reader:
            print("WARN 모르는 소스 종류 건너뜀: %s" % kind)
            continue
        root = R.expand(src.get("root") or "")
        if not os.path.isdir(root):
            print("WARN 소스 경로 없음: %s (%s)" % (root, kind))
            continue
        resume = {p: v for p, v in state.items() if isinstance(v, dict)}
        for s in reader(root, resume):
            seen.add(s.sid)
            dup_of = getattr(s, "imported_from", None)
            if dup_of and (dup_of in index or dup_of in seen):
                state[s.path] = {"dup": dup_of}
                index.pop(s.sid, None)
                dups += 1
                continue
            st = os.stat(s.path)
            prev_state = state.get(s.path)
            prev_state = prev_state if isinstance(prev_state, dict) else {}
            sig = "%s:%d:%d" % (kind, st.st_size, int(st.st_mtime))
            if prev_state.get("sig") == sig and s.sid in index:
                continue
            # Only the new tail was parsed when the file had merely grown.
            grew = bool(getattr(s, "resumed_from", 0)) and s.sid in index
            meta, body = digest_session(s, cfg)
            if grew:
                meta = merge_meta(index.get(s.sid), meta)
            why = R.excluded_reason(meta, cfg.get("exclude"))
            if why:
                # Keep a stub so the page can say why, but never digest it.
                index[s.sid] = {k: meta[k] for k in ("sessionId", "project", "source",
                                                     "cwd", "start", "end", "userPrompts",
                                                     "firstPrompt")}
                index[s.sid]["excluded"] = why
                state[s.path] = {"sig": sig}
                excl += 1
                continue
            if not included(meta, cfg["include"]):
                state[s.path] = {"sig": sig}
                index.pop(s.sid, None)
                skipped += 1
                continue
            pdir = os.path.join(dig_dir, s.group.replace("/", "_"))
            os.makedirs(pdir, exist_ok=True)
            out = os.path.join(pdir, s.sid + ".md")

            keep = old_body(out) if grew else ""
            if grew and not body.strip():
                state[s.path] = {"sig": sig, "offset": s.end_offset,
                                 "head": R.head_hash(s.path, s.end_offset)}
                continue                      # grew, but nothing worth reading
            before = render_head(meta) + "\n" + BODY_MARK + "\n" + (keep + "\n" if keep else "")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(before + body)
            meta["digest"] = out
            meta["digestChars"] = len(before) + len(body)
            # Where this run's new material starts, so a card can read only the tail.
            meta["newFromLine"] = before.count("\n") + 1 if grew else 1
            meta["newChars"] = len(body) if grew else meta["digestChars"]
            index[s.sid] = meta
            state[s.path] = {"sig": sig, "offset": s.end_offset,
                             "head": R.head_hash(s.path, s.end_offset)}
            changed.append(s.sid)

    # Re-apply the exclude rules to everything already indexed, so editing
    # config.json takes effect on the next run without --all.
    for sid, meta in list(index.items()):
        why = R.excluded_reason(meta, cfg.get("exclude"))
        if why and not meta.get("excluded"):
            dg = meta.pop("digest", None)
            meta.pop("digestChars", None)
            meta["excluded"] = why
            excl += 1
            if dg and os.path.exists(dg):
                try:
                    os.remove(dg)
                except OSError:
                    pass
        elif meta.get("excluded") and not why:
            meta.pop("excluded")                 # rule withdrawn: pick it up again
            state.pop(meta.get("path", ""), None)

    rows = sorted(index.values(), key=lambda m: m.get("start") or "")
    for r in rows:
        r.setdefault("source", "claude-code")
    with open(index_p, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    with open(state_p, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)

    for r in rows:                       # backfill fields added after first build
        r.setdefault("source", "claude-code")
    live = [r for r in rows if not r.get("excluded")]
    print("[%s] 세션 %d개 · 이번에 갱신 %d개 · 필터로 제외 %d개 · 사본 %d개 · 연구 아님 %d개"
          % (name, len(live), len(changed), skipped, dups,
             sum(1 for r in rows if r.get("excluded"))))
    for m in rows:
        if m.get("excluded"):
            print("  (연구 아님) %s %s  %s" % (m["start"], m["sessionId"][:8], m["excluded"]))
            continue
        grew = (m["sessionId"] in changed and m.get("newFromLine", 1) > 1)
        tail = ("  ← %s자 추가 (전체 %s자, %d줄부터 새것)"
                % (format(m.get("newChars", 0), ","), format(m.get("digestChars", 0), ","),
                   m.get("newFromLine", 1))) if grew else ""
        print("%s %s → %s  %-10s %-24s %s  프롬프트%4d  %s%s" % (
            "*" if m["sessionId"] in changed else " ", m["start"], m["end"],
            m.get("source", "?"), m["project"][:24], m["sessionId"][:8],
            m["userPrompts"], m["firstPrompt"][:52], tail))
    if changed:
        by_id = {r["sessionId"]: r for r in rows}
        covered = carded_sessions(d)
        grown = [c for c in changed if by_id.get(c, {}).get("newFromLine", 1) > 1]
        fresh = [c for c in changed if c not in grown and c not in covered]
        redone = [c for c in changed if c not in grown and c in covered]
        print("\nSKILL.md 2단계 — 이번에 손댈 세션 %d개" % len(changed))
        if fresh:
            print("  새 세션 %d개 — 카드를 새로 쓴다: %s"
                  % (len(fresh), ", ".join(c[:8] for c in fresh)))
        if grown:
            print("  이어진 세션 %d개 — 기존 카드 + 아래 줄부터만 읽고 **갱신**한다:" % len(grown))
            for c in grown:
                r = by_id[c]
                print("    %s  %s  offset=%d줄 (%s자 추가 / 전체 %s자)"
                      % (c[:8], r.get("digest", ""), r["newFromLine"],
                         format(r.get("newChars", 0), ","),
                         format(r.get("digestChars", 0), ",")))
        if redone:
            print("  digest 만 다시 만든 세션 %d개 — **이미 카드가 있으니 그냥 두라**." % len(redone))
            print("    (기록이 통째로 바뀌었거나 --all 을 썼을 때 생긴다): %s"
                  % ", ".join(c[:8] for c in redone))


if __name__ == "__main__":
    main()
