# -*- coding: utf-8 -*-
"""research-map: a small local server so the page can update itself.

`index.html` on its own is a static file — it cannot run Python, and the two
middle steps of an update (transcript -> card, cards -> map) need an agent's
judgement anyway. So the button talks to this, which runs the real commands.

Deliberately two steps:
  1. 새 세션 확인   extract only. Cheap, deterministic, spends nothing.
  2. 지도 갱신     hands the merge to the agent CLI. This costs tokens, so it
                   is never what the first click does.

Safety: binds 127.0.0.1 only, and every request must carry a token minted at
startup and injected into the page it serves. Nothing is exposed to the network.
"""
import http.server, json, os, secrets, subprocess, sys, threading, time, webbrowser
import urllib.parse

MAX_LOG = 4000


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


def agent_argv(map_name):
    """How to ask the installed agent CLI to do the judgement steps."""
    prompt = ("research-map 스킬로 '%s' 지도를 갱신해줘. "
              "추출(extract)은 방금 끝났으니, 바뀐 세션의 카드를 만들고 map.json 에 "
              "병합한 다음 render 까지 해줘. 렌더는 --open 없이." % map_name)
    exe = "claude"
    return [exe, "-p", prompt,
            "--allowedTools", "Bash", "Read", "Write", "Edit", "Glob", "Grep", "Agent"]


def serve(map_name, map_dir, scripts_dir, port=8787, open_browser=True):
    token = secrets.token_urlsafe(16)
    index = os.path.join(map_dir, "index.html")
    job = Job()
    py = sys.executable or "python"

    def inject(html):
        # Must land before the page's own script, which reads window.RM_SERVE on load.
        cfg = json.dumps({"token": token, "map": map_name}, ensure_ascii=False)
        tag = "<script>window.RM_SERVE=%s;</script>" % cfg
        i = html.find("<script>")
        return (html[:i] + tag + html[i:]) if i >= 0 else html.replace("</body>", tag + "</body>")

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
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
            except Exception:
                pass
            if u.path == "/api/scan":
                started = job.start("scan", [py, os.path.join(scripts_dir, "extract.py"),
                                             "--map", map_name], map_dir)
            elif u.path == "/api/update":
                started = job.start("update", agent_argv(map_name), map_dir)
            elif u.path == "/api/render":
                started = job.start("render", [py, os.path.join(scripts_dir, "render.py"),
                                               "--map", map_name], map_dir)
            else:
                return self._deny(404, "not found")
            return self._ok(json.dumps({"started": started}))

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    url = "http://127.0.0.1:%d/?t=%s" % (port, token)
    print("연구 지도 서버: %s" % url)
    print("  이 주소는 이 컴퓨터에서만 열리고, 토큰은 서버를 끄면 사라집니다.")
    print("  끄려면 Ctrl+C.")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 껐습니다.")
    finally:
        httpd.server_close()
