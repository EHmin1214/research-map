# -*- coding: utf-8 -*-
"""research-map: a small local server so the page can update and correct itself.

`index.html` on its own is a static file — it cannot run Python, and the two
middle steps of an update (transcript -> card, cards -> map) need an agent's
judgement anyway. So the buttons talk to this, which runs the real commands.

Deliberately two steps for an update:
  1. 새 세션 확인   extract only. Cheap, deterministic, spends nothing.
  2. 지도 갱신     hands the merge to the agent CLI. This costs tokens, so it
                   is never what the first click does.

Corrections from the node panel come in two flavours for the same reason:
  /api/edit      status / title / summary changed directly in map.json, then a
                 re-render. No agent, no tokens. A '### 변경 이력' line records it.
  /api/correct   free-text instruction handed to the agent, scoped to one node.

Which agent: config "agent" ("claude" | "codex"), else whichever is on PATH,
claude first. Codex runs as `codex exec` with a workspace-write sandbox.

Safety: binds 127.0.0.1 only, and every request must carry a token minted at
startup and injected into the page it serves. Nothing is exposed to the network.
"""
import datetime, http.server, json, os, secrets, shutil, subprocess, sys, threading, webbrowser
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rmlib

MAX_LOG = 4000
EDITABLE = ("status", "title", "summary")
STATUSES = ("ongoing", "done", "confirmed", "refuted", "withdrawn", "inconclusive",
            "abandoned", "open", "blocked", "planned")


class Job(object):
    """One command at a time, with its output readable while it runs."""

    def __init__(self):
        self.lock = threading.Lock()
        self.name = None
        self.lines = []
        self.done = True
        self.rc = None

    def start(self, name, argv, cwd, env=None):
        with self.lock:
            if not self.done:
                return False
            self.name, self.lines, self.done, self.rc = name, [], False, None
        threading.Thread(target=self._run, args=(argv, cwd, env), daemon=True).start()
        return True

    def _run(self, argv, cwd, env):
        e = dict(os.environ)
        e["PYTHONIOENCODING"] = "utf-8"
        e["PYTHONUNBUFFERED"] = "1"
        if env:
            e.update(env)
        try:
            p = subprocess.Popen(argv, cwd=cwd, env=e, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace", bufsize=1)
            for line in p.stdout:
                with self.lock:
                    self.lines.append(line.rstrip("\n"))
                    if len(self.lines) > MAX_LOG:
                        del self.lines[:MAX_LOG // 2]
            p.wait()
            rc = p.returncode
        except FileNotFoundError:
            rc = -1
            with self.lock:
                self.lines.append("실행 파일을 찾지 못했습니다: %s" % argv[0])
        except Exception as ex:                                   # noqa: BLE001
            rc = -1
            with self.lock:
                self.lines.append("실행 실패: %s" % ex)
        with self.lock:
            self.rc, self.done = rc, True

    def snapshot(self, since):
        with self.lock:
            return {"name": self.name, "done": self.done, "rc": self.rc,
                    "total": len(self.lines), "lines": self.lines[since:]}


# ---------------------------------------------------------------- agent CLI

def pick_agent(cfg):
    """('claude'|'codex', path) — config wins, else first found on PATH. None if neither."""
    want = (cfg or {}).get("agent")
    order = [want] if want in ("claude", "codex") else ["claude", "codex"]
    for name in order:
        exe = shutil.which(name) or shutil.which(name + ".cmd")
        if exe:
            return name, exe
    return None, None


def agent_argv(map_name, map_dir, cfg, prompt):
    """How to ask the installed agent CLI to do a judgement step, non-interactively."""
    name, exe = pick_agent(cfg)
    prompt = rmlib.UPDATER_MARK + " " + prompt
    if name == "codex":
        # exec = non-interactive; workspace-write keeps writes inside the map folder,
        # which is all the skill needs (digests, cards, map.json, index.html live there).
        return [exe, "exec", "--skip-git-repo-check", "--sandbox", "workspace-write",
                "-C", map_dir, prompt]
    if name == "claude":
        return [exe, "-p", prompt,
                "--allowedTools", "Bash", "Read", "Write", "Edit", "Glob", "Grep", "Agent"]
    return ["claude", "-p", prompt,
            "--allowedTools", "Bash", "Read", "Write", "Edit", "Glob", "Grep", "Agent"]


def update_prompt(map_name):
    return ("research-map 스킬로 '%s' 지도를 갱신해줘. 추출(extract)은 방금 끝났으니, "
            "바뀐 세션의 카드를 만들고 map.json 에 병합한 다음 render 까지 해줘. "
            "렌더는 --open 없이." % map_name)


def correct_prompt(map_name, node, text):
    return ("research-map 스킬의 '%s' 지도에서 노드 '%s'(%s) 를 사용자 지시대로 정정해줘. "
            "지시: %s\n세션 기록을 다시 읽지 말고 map.json 의 그 노드(필요하면 직접 관련된 노드)만 고쳐. "
            "status 나 결론이 바뀌면 detail 에 '### 변경 이력' 으로 날짜와 이유를 남기고, "
            "끝나면 render 해줘 (--open 없이). 지도 전체를 다시 설명하지 말고 고친 것만 짧게 보고해."
            % (map_name, node.get("id"), node.get("title") or "", text.strip()))


# ---------------------------------------------------------------- direct edit

def apply_edit(map_dir, body):
    """Change status/title/summary of one node in map.json. Returns (ok, message)."""
    nid = (body.get("id") or "").strip()
    if not nid:
        return False, "id 없음"
    p = os.path.join(map_dir, "map.json")
    m = json.load(open(p, encoding="utf-8"))
    node = next((n for n in m.get("nodes") or [] if n.get("id") == nid), None)
    if node is None:
        return False, "노드 없음: %s" % nid
    changes = []
    for k in EDITABLE:
        if k not in body:
            continue
        v = (body.get(k) or "").strip()
        if k == "status" and v not in STATUSES:
            return False, "status 값이 이상합니다: %r" % v
        if k == "title" and not v:
            return False, "제목은 비울 수 없습니다"
        if v == (node.get(k) or ""):
            continue
        changes.append((k, node.get(k) or "", v))
        node[k] = v
    if not changes:
        return False, "바뀐 것이 없습니다"
    today = datetime.date.today().isoformat()
    why = (body.get("why") or "").strip()
    lines = []
    for k, a, b in changes:
        if k == "status":
            lines.append("- %s: 페이지에서 정정 — status %s → %s%s" % (today, a, b, (" (%s)" % why) if why else ""))
        else:
            lines.append("- %s: 페이지에서 %s 정정%s" % (today, "제목" if k == "title" else "요약", (" — %s" % why) if why else ""))
    detail = (node.get("detail") or "").rstrip()
    if "### 변경 이력" in detail:
        detail += "\n" + "\n".join(lines)
    else:
        detail = (detail + "\n\n" if detail else "") + "### 변경 이력\n" + "\n".join(lines)
    node["detail"] = detail
    m["updatedAt"] = today
    json.dump(m, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return True, "저장: " + ", ".join("%s %s→%s" % (k, a[:20], b[:20]) if k == "status" else k for k, a, b in changes)


# ---------------------------------------------------------------- server

def serve(map_name, map_dir, scripts_dir, cfg=None, port=8787, open_browser=True):
    token = secrets.token_urlsafe(16)
    index = os.path.join(map_dir, "index.html")
    job = Job()
    py = sys.executable or "python"
    cfg = cfg or {}
    agent_name, _ = pick_agent(cfg)

    def inject(html):
        # Must land before the page's own script, which reads window.RM_SERVE on load.
        conf = json.dumps({"token": token, "map": map_name, "agent": agent_name}, ensure_ascii=False)
        tag = "<script>window.RM_SERVE=%s;</script>" % conf
        i = html.find("<script>")
        return (html[:i] + tag + html[i:]) if i >= 0 else html.replace("</body>", tag + "</body>")

    def render_argv():
        return [py, os.path.join(scripts_dir, "render.py"), "--map", map_name]

    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):                       # keep the console for job output
            pass

        def _ok(self, body, ctype="application/json; charset=utf-8"):
            b = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def _deny(self, code=403, msg="forbidden"):
            b = msg.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _auth(self, q):
            if q.get("t", [None])[0] == token:
                return True
            return self.headers.get("X-RM-Token") == token

        def _body(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                return json.loads(raw.decode("utf-8")) if raw else {}
            except Exception:
                return {}

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if not self._auth(q):
                return self._deny()
            if u.path in ("/", "/index.html"):
                try:
                    html = open(index, encoding="utf-8").read()
                except OSError:
                    return self._deny(404, "index.html 이 아직 없습니다")
                return self._ok(inject(html), "text/html; charset=utf-8")
            if u.path == "/api/job":
                since = int((q.get("since", ["0"])[0]) or 0)
                return self._ok(json.dumps(job.snapshot(since), ensure_ascii=False))
            return self._deny(404, "not found")

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if not self._auth(q):
                return self._deny()
            body = self._body()
            if u.path == "/api/scan":
                started = job.start("scan", [py, os.path.join(scripts_dir, "extract.py"),
                                             "--map", map_name], map_dir)
            elif u.path == "/api/update":
                started = job.start("update", agent_argv(map_name, map_dir, cfg, update_prompt(map_name)), map_dir)
            elif u.path == "/api/render":
                started = job.start("render", render_argv(), map_dir)
            elif u.path == "/api/edit":
                ok, msg = apply_edit(map_dir, body)
                if not ok:
                    return self._ok(json.dumps({"started": False, "error": msg}, ensure_ascii=False))
                started = job.start("render", render_argv(), map_dir)
                return self._ok(json.dumps({"started": started, "applied": msg}, ensure_ascii=False))
            elif u.path == "/api/correct":
                nid, text = (body.get("id") or "").strip(), (body.get("text") or "").strip()
                if not nid or not text:
                    return self._ok(json.dumps({"started": False, "error": "노드와 지시가 필요합니다"}, ensure_ascii=False))
                try:
                    m = json.load(open(os.path.join(map_dir, "map.json"), encoding="utf-8"))
                    node = next((n for n in m.get("nodes") or [] if n.get("id") == nid), None)
                except OSError:
                    node = None
                if node is None:
                    return self._ok(json.dumps({"started": False, "error": "노드 없음: %s" % nid}, ensure_ascii=False))
                started = job.start("correct", agent_argv(map_name, map_dir, cfg, correct_prompt(map_name, node, text)), map_dir)
            else:
                return self._deny(404, "not found")
            return self._ok(json.dumps({"started": started}))

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    url = "http://127.0.0.1:%d/?t=%s" % (port, token)
    print("연구 지도 서버: %s" % url)
    print("  이 주소는 이 컴퓨터에서만 열리고, 토큰은 서버를 끄면 사라집니다.")
    print("  갱신·정정에 쓰는 에이전트: %s" % (agent_name or "없음 — claude 나 codex 가 PATH 에 없습니다"))
    print("  끄려면 Ctrl+C.")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 껐습니다.")
    finally:
        httpd.server_close()


def main():
    """CLI: run the agent step in the foreground (used by the VS Code extension and open-map.bat)."""
    import argparse
    ap = argparse.ArgumentParser(description="research-map: 에이전트 갱신을 서버 없이 바로 실행")
    ap.add_argument("--map")
    ap.add_argument("--update", action="store_true", help="extract 후 에이전트에게 카드·병합·렌더를 맡긴다 (토큰)")
    ap.add_argument("--correct", metavar="NODE", help="이 노드를 --text 지시대로 에이전트가 정정")
    ap.add_argument("--text", default="")
    a = ap.parse_args()
    name = rmlib.resolve_map(a.map)
    d, cfg = rmlib.map_dir(name), rmlib.load_config(name)
    agent, exe = pick_agent(cfg)
    if not agent:
        raise SystemExit("claude 나 codex CLI 가 PATH 에 없습니다.")
    here = os.path.dirname(os.path.abspath(__file__))
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if a.update:
        print("[1/2] extract — 새 세션 확인")
        subprocess.call([sys.executable, os.path.join(here, "extract.py"), "--map", name], env=env)
        print("[2/2] %s — 카드·병합·렌더 (토큰을 씁니다)" % agent)
        rc = subprocess.call(agent_argv(name, d, cfg, update_prompt(name)), cwd=d, env=env)
        raise SystemExit(rc)
    if a.correct:
        m = json.load(open(os.path.join(d, "map.json"), encoding="utf-8"))
        node = next((n for n in m.get("nodes") or [] if n.get("id") == a.correct), None)
        if node is None or not a.text.strip():
            raise SystemExit("노드 id 와 --text 지시가 필요합니다.")
        rc = subprocess.call(agent_argv(name, d, cfg, correct_prompt(name, node, a.text)), cwd=d, env=env)
        raise SystemExit(rc)
    ap.print_help()


if __name__ == "__main__":
    main()
