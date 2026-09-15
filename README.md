# Research Map

Turn your AI coding-agent transcripts into **one clickable map of your research**:
topic → direction → process → result → open questions.

Researchers who work with an LLM lose track of what they already tried. Which branch
was closed, and why? What was the number? Which conversation was that in? This tool
reads your transcripts and answers those questions on one page.

- **Nothing is deleted.** Refuted and withdrawn branches stay on the map with their
  status changed, so you do not walk down the same dead end twice.
- **Every result carries its evidence** — the numbers, the documents, and the command
  that resumes the original session.
- **One self-contained HTML file.** No server, no CDN, no internet. Send it to a
  colleague as a single file.

Reads **Claude Code** and **Codex CLI** transcripts directly, plus exported chats from
any other LLM (ChatGPT, Gemini, Claude.ai …) as markdown/JSON files.

한국어 설명은 [아래](#한국어)에 있습니다.

---

## Install

**As a Claude Code plugin** (recommended)

```
/plugin marketplace add EHmin1214/research-map
/plugin install research-map@research-map
```

**Or as a personal skill**

```bash
git clone https://github.com/EHmin1214/research-map
cd research-map
bash install.sh          # macOS / Linux / Git Bash
# powershell -ExecutionPolicy Bypass -File install.ps1     (Windows)
```

Requires Python 3.8+. Nothing else — no pip install.

Check what it can see on your machine:

```bash
python ~/.claude/skills/research-map/scripts/extract.py --doctor
```

## Use

Ask your agent, in plain words:

> build my research map

> update the research map

> start a new map for the rat experiments

The skill does the rest: it compresses each transcript into a digest, has sub-agents
read them into per-session cards, merges those into `map.json`, and renders the page.

Open the result at `~/.claude/research-map/maps/<name>/index.html`.

### The four views

| View | Answers |
|---|---|
| **Map** | What did I do, and how does it hang together? |
| **Timeline** | When did I run that experiment? |
| **Open questions** | What should I look at next? |
| **Sessions** | Which conversation was that, and how do I resume it? |

Search (`/`) matches titles, summaries, evidence numbers and tags. Colour chips filter
by node type and status.

## One map per research area

A map lives in `~/.claude/research-map/maps/<name>/`. Create another one for another
project:

```bash
python ~/.claude/skills/research-map/scripts/extract.py --init rat --title "Rat experiments"
```

Then narrow `config.json` to the sessions that belong to it — essential if you do
several projects on one machine:

```json
"include": {
  "cwdContains": ["projects/rat"],
  "since": "2026-08-01",
  "minPrompts": 3
}
```

## Sources

`config.json` lists what to read:

```json
"sources": [
  {"kind": "claude-code", "root": "~/.claude/projects"},
  {"kind": "codex",       "root": "~/.codex/sessions"},
  {"kind": "markdown",    "root": "~/chat-exports", "label": "ChatGPT"}
]
```

| kind | reads |
|---|---|
| `claude-code` | `~/.claude/projects/*/<sessionId>.jsonl` |
| `codex` | `~/.codex/sessions/**/rollout-*.jsonl` — copies Codex imported from another agent are skipped automatically |
| `markdown` | a folder of `.md` / `.txt` / `.json` — **the generic path for every other LLM** |

For tools without local transcripts, export the conversation and drop the file in a
folder. `## User` / `## Assistant` headings or `{"messages":[{"role","content"}]}` JSON
get split into turns; anything else is kept whole. See `examples/exports/`.

**Adding a tool:** write one `read_<kind>(root)` generator in `scripts/rmlib.py` and
register it in `SOURCES`. Yield `RawSession` objects and call
`add("user"|"assistant"|"tool"|"summary", timestamp, payload)`. Digesting, filtering,
incremental updates and rendering keep working unchanged. Add the tool's resume command
to `resumeCmd` in `render.py` to get a copy button in the panel.

## Language

`"lang": "en"` or `"ko"` in `config.json` switches the page chrome. Node content stays
in whatever language you and your agent wrote it in.

## What is in a map

`map.json` is the single source of truth and is meant to be hand-editable.
Each node has a type (`topic` · `direction` · `process` · `result` · `open` ·
`artifact`), a status, a summary, and optionally `detail` (markdown), `evidence`,
`next`, `sources` and `links`. `render.py --check` validates it: broken parents,
cycles, unknown link targets, document paths that no longer exist on disk, and
result nodes with no source.

See `skills/research-map/MAP_SCHEMA.md`.

## Privacy

Everything stays on your machine. The tool only reads transcripts you already have and
writes into `~/.claude/research-map/`. The rendered page loads no external resources.
A digest keeps your prompts and the agent's prose, so treat `index.html` like the
transcripts themselves before sharing it.

## License

MIT

---

<a name="한국어"></a>

# 한국어

LLM 과 연구를 하다 보면 자기가 어떤 갈래를 파고 어떤 결론을 냈는지 놓친다.
이 도구는 대화 기록을 읽어 **주제 → 방향 → 과정 → 결과 → 열린 질문** 트리 한 장으로 만든다.

- **지우지 않는다.** 반증·철회된 갈래도 상태만 바꿔 남긴다. 같은 길을 두 번 가지 않기 위해서다.
- **모든 결과에 근거가 붙는다** — 수치, 문서, 그리고 원본 대화를 이어가는 명령까지.
- **단일 HTML 파일.** 서버도 인터넷도 필요 없고 파일 하나로 보낼 수 있다.

**Claude Code** 와 **Codex CLI** 기록을 직접 읽고, 다른 LLM(ChatGPT·Gemini·Claude.ai)은
대화를 내보내 markdown 폴더에 넣으면 된다.

## 설치

플러그인으로 (권장):

```
/plugin marketplace add EHmin1214/research-map
/plugin install research-map@research-map
```

또는 개인 스킬로:

```bash
git clone https://github.com/EHmin1214/research-map
cd research-map
powershell -ExecutionPolicy Bypass -File install.ps1   # Windows
bash install.sh                                        # macOS / Linux
```

Python 3.8 이상만 있으면 되고 추가 설치는 없다.
`extract.py --doctor` 로 이 컴퓨터에서 무엇을 읽을 수 있는지 점검한다.

## 사용

에이전트에게 말로 시킨다.

> 연구 지도 만들어줘 · 연구 지도 업데이트해줘 · 랫 실험으로 새 지도 만들어줘

결과는 `~/.claude/research-map/maps/<이름>/index.html`.

| 탭 | 답하는 질문 |
|---|---|
| **지도** | 내가 뭘 했고 어떻게 이어지는가 |
| **타임라인** | 그 실험 언제 했지 |
| **열린 질문** | 다음에 뭘 파지 |
| **세션** | 그게 어느 대화였고 어떻게 이어가지 |

## 연구마다 지도 하나

```bash
python ~/.claude/skills/research-map/scripts/extract.py --init rat --title "랫 실험 지도"
```

그다음 `config.json` 의 `include`(`cwdContains` · `since` · `minPrompts`)로 그 연구
세션만 고른다. 한 컴퓨터에서 여러 연구를 한다면 이 필터가 핵심이다.

`"lang": "ko"` 가 기본이고 `"en"` 으로 바꾸면 화면이 영어가 된다.
