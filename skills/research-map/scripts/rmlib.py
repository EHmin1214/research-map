# -*- coding: utf-8 -*-
"""research-map: shared paths, map config, and transcript source adapters.

A "map" is one research area. Each map lives in its own directory:

  ~/.claude/research-map/maps/<name>/
      config.json     what to read, what to call it
      map.json        the map itself (single source of truth)
      sessions.json   session index
      state.json      incremental-extract bookkeeping
      cards/          per-session cards (intermediate)
      digests/        compressed transcripts
      index.html      rendered map

config.json:
{
  "title": "...",
  "summary": "...",
  "sources": [
    {"kind": "claude-code", "root": "~/.claude/projects", "label": "Claude Code"},
    {"kind": "codex",       "root": "~/.codex/sessions"},
    {"kind": "markdown",    "root": "~/research-exports", "label": "ChatGPT 내보내기"}
  ],
  "include": {"cwdContains": [], "pathContains": [], "since": null, "until": null, "minPrompts": 1},
  "memoryDirs": ["~/.claude/projects/<slug>/memory"]
}

Adding a new LLM: write a `read_<kind>()` generator below and register it in
SOURCES. It must yield RawSession objects. Nothing else in the tool changes.
"""
import json, os, re, glob

HOME = os.path.expanduser("~")
# Maps live outside any one agent's folder so Claude Code and Codex share them.
# Override with RESEARCH_MAP_HOME; the legacy ~/.claude/research-map is still honoured.
ROOT = os.environ.get("RESEARCH_MAP_HOME") or ""
if ROOT:
    ROOT = os.path.abspath(os.path.expanduser(ROOT))
else:
    legacy = os.path.join(HOME, ".claude", "research-map")
    ROOT = legacy if os.path.isdir(os.path.join(legacy, "maps")) else os.path.join(HOME, ".research-map")
MAPS = os.path.join(ROOT, "maps")

# Stamped into the prompt when the update button drives an agent, so the next
# scan can tell the tool's own runs apart from real research.
UPDATER_MARK = "[research-map:updater]"

MAX_ASSISTANT_CHARS = 3500
MAX_USER_CHARS = 4000
MAX_SUMMARY_CHARS = 6000

# Wrapper blocks that the harness injects into user turns; not written by the user.
TAG_RE = re.compile(
    r"<(system-reminder|command-name|command-message|command-args|local-command-stdout|"
    r"local-command-stderr|ide_selection|ide_opened_file|task-notification|task-reminder|"
    r"environment_context|user_instructions|recommended_plugins|plugin_instructions|"
    r"available_skills|world_state)>.*?</\1>",
    re.S)
SKIP_PREFIXES = ("[Request interrupted", "<local-command", "<command-name")


def expand(p):
    """Absolute path, tolerating Git Bash / MSYS drive paths like /c/Users/... ."""
    p = os.path.expanduser(os.path.expandvars(p or ""))
    if os.name == "nt":
        m = re.match(r"^/([A-Za-z])(/.*)?$", p.replace("\\", "/"))
        if m:
            p = m.group(1).upper() + ":" + (m.group(2) or "/")
    return os.path.abspath(p)


class RawSession(object):
    """One conversation, normalised across tools."""

    def __init__(self, sid, path, group, source):
        self.sid = sid            # stable id (used for `resume` and filenames)
        self.path = path          # transcript file on disk
        self.group = group        # project/folder label
        self.source = source      # "claude-code" | "codex" | "markdown" | ...
        self.cwd = None
        self.imported_from = None  # this chat is a copy of another tool's session
        self.events = []          # (kind, ts, payload) in order

    def add(self, kind, ts, payload):
        self.events.append((kind, ts or "", payload))


def clean_user_text(t):
    t = TAG_RE.sub("", t or "").strip()
    if not t or t.startswith(SKIP_PREFIXES):
        return ""
    # A turn that was nothing but harness preamble
    if t.startswith("<") and t.endswith(">") and "\n" not in t[:200]:
        return ""
    if t.startswith("[Image:") and len(t) < 200:
        return "[이미지 첨부]"
    return t


def _tool_key(inp):
    if isinstance(inp, str):
        return inp.replace("\n", " ")[:160]
    if isinstance(inp, dict):
        for k in ("file_path", "path", "notebook_path", "command", "cmd", "pattern",
                  "query", "url", "prompt", "description", "skill"):
            v = inp.get(k)
            if isinstance(v, str):
                return "%s=%s" % (k, v.replace("\n", " ")[:160])
    return ""


# --------------------------------------------------------------------------
# adapters
# --------------------------------------------------------------------------

def read_claude_code(root):
    """Claude Code: ~/.claude/projects/<project-slug>/<sessionId>.jsonl"""
    for path in sorted(glob.glob(os.path.join(root, "*", "*.jsonl"))):
        group = os.path.basename(os.path.dirname(path))
        sid = os.path.splitext(os.path.basename(path))[0]
        s = RawSession(sid, path, group, "claude-code")
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                try:
                    d = json.loads(raw)
                except Exception:
                    continue
                if d.get("type") not in ("user", "assistant") or d.get("isSidechain"):
                    continue
                ts = (d.get("timestamp") or "")[:16].replace("T", " ")
                s.cwd = s.cwd or d.get("cwd")
                content = (d.get("message") or {}).get("content")
                blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])
                for b in blocks:
                    bt, role = b.get("type"), d["type"]
                    if role == "user" and bt == "text":
                        txt = b.get("text", "")
                        if txt.startswith("This session is being continued"):
                            s.add("summary", ts, txt[:MAX_SUMMARY_CHARS])
                        else:
                            s.add("user", ts, txt)
                    elif role == "user" and bt == "image":
                        s.add("user", ts, "[이미지 첨부]")
                    elif role == "assistant" and bt == "text":
                        s.add("assistant", ts, b.get("text", ""))
                    elif role == "assistant" and bt == "tool_use":
                        s.add("tool", ts, (b.get("name", "?"), b.get("input") or {}))
        yield s


def _codex_imports(root):
    """Codex can import other agents' transcripts; those chats are duplicates.

    external_agent_session_imports.json maps the imported thread id back to the
    original transcript file, so we can tag the copy instead of counting it twice.
    """
    man = os.path.join(os.path.dirname(root.rstrip("/\\")), "external_agent_session_imports.json")
    out = {}
    try:
        for rec in (json.load(open(man, encoding="utf-8")) or {}).get("records") or []:
            tid = rec.get("imported_thread_id")
            src = (rec.get("source_path") or "").replace("\\?\\", "")
            if tid and src:
                out[tid] = os.path.splitext(os.path.basename(src))[0]
    except Exception:
        pass
    return out


def read_codex(root):
    """Codex CLI: ~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl"""
    imports = _codex_imports(root)
    for path in sorted(glob.glob(os.path.join(root, "*", "*", "*", "*.jsonl"))):
        base = os.path.splitext(os.path.basename(path))[0]
        m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", base)
        sid = m.group(1) if m else base
        s = RawSession(sid, path, "codex", "codex")
        s.imported_from = imports.get(sid)
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                try:
                    d = json.loads(raw)
                except Exception:
                    continue
                ts = (d.get("timestamp") or "")[:16].replace("T", " ")
                p = d.get("payload") or {}
                if not isinstance(p, dict):
                    continue
                if d.get("type") == "turn_context" and p.get("cwd"):
                    s.cwd = s.cwd or p.get("cwd")
                    continue
                if d.get("type") != "response_item":
                    continue
                pt = p.get("type")
                if pt == "message":
                    role = p.get("role")
                    if role not in ("user", "assistant"):
                        continue          # developer/system turns are harness text
                    for b in p.get("content") or []:
                        txt = b.get("text") or ""
                        if txt:
                            s.add("user" if role == "user" else "assistant", ts, txt)
                elif pt in ("custom_tool_call", "function_call", "local_shell_call"):
                    name = p.get("name") or pt
                    s.add("tool", ts, (name, p.get("input") or p.get("arguments") or {}))
        yield s


def read_markdown(root):
    """Any other LLM: a folder of exported conversations, one file per chat.

    Accepts .md / .txt / .json (ChatGPT-style {"messages":[{role,content}]}).
    Plain text files are kept whole; if the file uses `## User` / `## Assistant`
    headings (or `**User:**`), the turns are split so the digest stays readable.
    """
    pats = ("*.md", "*.markdown", "*.txt", "*.json")
    files = []
    for p in pats:
        files += glob.glob(os.path.join(root, "**", p), recursive=True)
    for path in sorted(set(files)):
        sid = os.path.splitext(os.path.basename(path))[0]
        if sid.lower() in ("readme", "index", "notes-template", ".gitkeep"):
            continue          # folder documentation, not a conversation
        group = os.path.relpath(os.path.dirname(path), root).replace("\\", "/")
        if group == ".":
            group = os.path.basename(root.rstrip("/\\")) or "markdown"
        s = RawSession(sid, path, group, "markdown")
        ts = ""
        try:
            import datetime
            ts = datetime.datetime.fromtimestamp(os.stat(path).st_mtime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
        text = open(path, encoding="utf-8", errors="replace").read()
        if path.lower().endswith(".json"):
            try:
                d = json.loads(text)
                msgs = d.get("messages") or d.get("conversation") or []
                for msg in msgs:
                    role = (msg.get("role") or "").lower()
                    c = msg.get("content")
                    if isinstance(c, list):
                        c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
                    if not c:
                        continue
                    s.add("user" if role in ("user", "human") else "assistant", ts, c)
                yield s
                continue
            except Exception:
                pass
        parts = re.split(r"(?im)^\s*(?:#{1,3}\s*|\*\*)(user|assistant|you|chatgpt|gemini|claude|사용자|나)\b[:\*\s]*$",
                         text)
        if len(parts) > 2:
            if parts[0].strip():
                s.add("assistant", ts, parts[0].strip())
            for i in range(1, len(parts) - 1, 2):
                role = parts[i].lower()
                body = parts[i + 1].strip()
                if not body:
                    continue
                is_user = role in ("user", "you", "사용자", "나")
                s.add("user" if is_user else "assistant", ts, body)
        else:
            s.add("user", ts, text.strip())
        yield s


SOURCES = {
    "claude-code": read_claude_code,
    "codex": read_codex,
    "markdown": read_markdown,
}


# --------------------------------------------------------------------------
# maps
# --------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "title": "연구 지도",
    "lang": "ko",                       # "ko" | "en" — HTML 화면 언어
    "summary": "",
    "sources": [{"kind": "claude-code", "root": "~/.claude/projects"}],
    "include": {"cwdContains": [], "pathContains": [], "since": None, "until": None, "minPrompts": 1},
    # Sessions that are deliberately not research. Kept with a reason so the map
    # can say "left out on purpose" instead of looking like a hole.
    "exclude": {"sessions": {}, "firstPromptContains": [UPDATER_MARK]},
    "memoryDirs": [],
}


def excluded_reason(meta, exc):
    """Why this session is not research, or None."""
    by_id = (exc or {}).get("sessions") or {}
    sid = meta.get("sessionId") or ""
    for k, why in by_id.items():
        if sid == k or (len(k) >= 6 and sid.startswith(k)):
            return why or "제외됨"
    first = meta.get("firstPrompt") or ""
    for frag in (exc or {}).get("firstPromptContains") or []:
        if frag and frag in first:
            return ("이 도구의 갱신 실행" if frag == UPDATER_MARK
                    else "첫 프롬프트에 %r 포함" % frag)
    return None


def list_maps():
    if not os.path.isdir(MAPS):
        return []
    return sorted(d for d in os.listdir(MAPS) if os.path.isfile(os.path.join(MAPS, d, "config.json")))


def map_dir(name):
    return os.path.join(MAPS, name)


def resolve_map(name):
    """Pick the map to act on. With one map, --map is optional."""
    maps = list_maps()
    if name:
        if name not in maps:
            raise SystemExit("map '%s' not found. 있는 지도: %s\n새로 만들기: extract.py --init %s"
                             % (name, ", ".join(maps) or "(없음)", name))
        return name
    if len(maps) == 1:
        return maps[0]
    if not maps:
        raise SystemExit("지도가 없습니다. 먼저: extract.py --init <이름> --title \"...\"")
    raise SystemExit("지도가 여럿입니다(%s). --map <이름> 을 주세요." % ", ".join(maps))


def load_config(name):
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(json.load(open(os.path.join(map_dir(name), "config.json"), encoding="utf-8")))
    inc = dict(DEFAULT_CONFIG["include"])
    inc.update(cfg.get("include") or {})
    cfg["include"] = inc
    exc = json.loads(json.dumps(DEFAULT_CONFIG["exclude"]))
    user_exc = cfg.get("exclude") or {}
    exc["sessions"].update(user_exc.get("sessions") or {})
    for f in user_exc.get("firstPromptContains") or []:
        if f not in exc["firstPromptContains"]:
            exc["firstPromptContains"].append(f)
    cfg["exclude"] = exc
    return cfg


def init_map(name, title=None, sources=None):
    d = map_dir(name)
    if os.path.exists(os.path.join(d, "config.json")):
        raise SystemExit("이미 있는 지도입니다: %s" % d)
    os.makedirs(os.path.join(d, "cards"), exist_ok=True)
    os.makedirs(os.path.join(d, "digests"), exist_ok=True)
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg["title"] = title or (name + " 연구 지도")
    if sources:
        cfg["sources"] = sources
    with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(d, "map.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "title": cfg["title"], "summary": "", "updatedAt": "", "nodes": []},
                  fh, ensure_ascii=False, indent=1)
    return d


# --------------------------------------------------------------------------
# environment detection — so a fresh install can configure itself
# --------------------------------------------------------------------------

CANDIDATE_ROOTS = [
    ("claude-code", "~/.claude/projects", "Claude Code"),
    ("codex", "~/.codex/sessions", "Codex CLI"),
]


def detect_sources():
    """Transcript stores that actually exist on this machine."""
    found = []
    for kind, root, label in CANDIDATE_ROOTS:
        d = expand(root)
        if not os.path.isdir(d):
            continue
        n = 0
        for _ in glob.iglob(os.path.join(d, "**", "*.jsonl"), recursive=True):
            n += 1
            if n >= 500:
                break
        if n:
            found.append({"kind": kind, "root": root, "label": label, "files": n})
    return found


def detect_memory_dirs():
    """Claude Code per-project memory folders, newest first."""
    base = expand("~/.claude/projects")
    out = []
    if os.path.isdir(base):
        for d in glob.glob(os.path.join(base, "*", "memory")):
            if glob.glob(os.path.join(d, "*.md")):
                out.append(d)
    out.sort(key=lambda d: -os.stat(d).st_mtime)
    return out
