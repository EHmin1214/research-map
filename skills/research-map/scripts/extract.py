#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
research-map extractor — transcripts -> per-session digests + session index.

  python extract.py                       # 지도가 하나면 그것을, 여럿이면 --map 필요
  python extract.py --map mystudy             # 증분: 새로 생기거나 길어진 세션만
  python extract.py --map mystudy --all       # 전체 재생성
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
    head = [
        "# Session %s" % s.sid,
        "- source: %s" % s.source,
        "- project: %s" % s.group,
        "- cwd: %s" % meta["cwd"],
        "- period: %s → %s" % (meta["start"], meta["end"]),
        "- user prompts: %d, assistant msgs: %d, tool calls: %d, compactions: %d"
        % (meta["userPrompts"], meta["assistantMsgs"], meta["toolCalls"], meta["compactions"]),
        "- files written: %d" % len(meta["filesTouched"]),
    ]
    if meta["filesTouched"]:
        head.append("  " + "\n  ".join(meta["filesTouched"][:60]))
    return meta, "\n".join(head) + "\n" + "\n".join(lines)


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
        if mem:
            cp = os.path.join(d, "config.json")
            cfg = json.load(open(cp, encoding="utf-8"))
            cfg["memoryDirs"] = [m.replace(os.path.expanduser("~"), "~") for m in mem[:4]]
            json.dump(cfg, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("메모리 폴더 %d개를 config 에 넣었습니다" % len(cfg["memoryDirs"]))
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

    changed, seen, skipped, dups = [], set(), 0, 0
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
        for s in reader(root):
            seen.add(s.sid)
            dup_of = getattr(s, "imported_from", None)
            if dup_of and (dup_of in index or dup_of in seen):
                state[s.path] = "dup:" + dup_of
                index.pop(s.sid, None)
                dups += 1
                continue
            st = os.stat(s.path)
            sig = "%s:%d:%d" % (kind, st.st_size, int(st.st_mtime))
            if state.get(s.path) == sig and s.sid in index:
                continue
            meta, body = digest_session(s, cfg)
            if not included(meta, cfg["include"]):
                state[s.path] = sig
                index.pop(s.sid, None)
                skipped += 1
                continue
            pdir = os.path.join(dig_dir, s.group.replace("/", "_"))
            os.makedirs(pdir, exist_ok=True)
            out = os.path.join(pdir, s.sid + ".md")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(body)
            meta["digest"] = out
            meta["digestChars"] = len(body)
            index[s.sid] = meta
            state[s.path] = sig
            changed.append(s.sid)

    rows = sorted(index.values(), key=lambda m: m.get("start") or "")
    for r in rows:
        r.setdefault("source", "claude-code")
    with open(index_p, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    with open(state_p, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)

    for r in rows:                       # backfill fields added after first build
        r.setdefault("source", "claude-code")
    print("[%s] 세션 %d개 · 이번에 갱신 %d개 · 필터로 제외 %d개 · 다른 도구가 가져간 사본 %d개"
          % (name, len(rows), len(changed), skipped, dups))
    for m in rows:
        print("%s %s → %s  %-10s %-24s %s  프롬프트%4d  %s" % (
            "*" if m["sessionId"] in changed else " ", m["start"], m["end"],
            m.get("source", "?"), m["project"][:24], m["sessionId"][:8],
            m["userPrompts"], m["firstPrompt"][:60]))
    if changed:
        print("\n카드를 만들 세션 %d개 — SKILL.md 2단계" % len(changed))


if __name__ == "__main__":
    main()
