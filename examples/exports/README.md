# Example: chats exported from another LLM

Point a `markdown` source at a folder like this one:

```json
{"kind": "markdown", "root": "~/chat-exports", "label": "ChatGPT"}
```

Three shapes are understood.

| file | shape |
|---|---|
| `01-headings.md` | `## User` / `## Assistant` headings — turns are split |
| `02-messages.json` | `{"messages":[{"role","content"}]}` — turns are split |
| `03-plain-note.txt` | anything else — kept whole as one entry |

The file name becomes the session id, so name files after the conversation.
Also accepted as headings: `# You`, `**Assistant:**`, `## 사용자`, `## 나`.
