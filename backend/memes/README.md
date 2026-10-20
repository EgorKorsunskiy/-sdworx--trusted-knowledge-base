# Memes

**Demo output** of the AI parser (`app/ai_parser`, spec: [specs/ai-parser](../../specs/ai-parser/FUNCTIONAL_SPEC.md)) for the mock sources in `mock_data/sources/`. The Cursor CLI reads one meeting transcript or one group chat; the backend validates its answer and writes the memes here. Only mocks belong here: these files are committed so the demo works without re-running the agent, and on startup they are loaded into the database (`seed_demo_memes`, once per source), where their authorship requests and notifications are created.

Real uploads (`POST /parser/sources`) never write files: their memes go straight to the database.

```
memes/
├── meetings/<source-id>.json        one file per meeting
├── chats/<chat-id>/<YYYY-MM-DD>.json one file per chat day
└── _uploads/                        real uploads while they are processed (gitignored, deleted after a successful run)
```

A chat is read as a whole, so corrections across days are seen; each meme goes into the file of the day of its **latest quote** (statement or confirmation). Re-running a chat replaces all its day files.

## File format

| Field | Meaning |
|---|---|
| `source` | `id`, `type`, `title`, and `date` (meeting) or `date_from` / `date_to` plus the file's `day` (chat) |
| `participants` | `email`, `display_name` of everyone who may see these memes |
| `guests` | Speaker labels without a Peerpoint user; they are never speakers or confirmers |
| `generated_at`, `generator` | When and how the file was made: `tool`, `model`, Cursor `session_id`, `prompt_version` |
| `memes` | Memes in the [agent contract](../../specs/ai-parser/FUNCTIONAL_SPEC.md#6-agent-contract) format, plus `id` (`<source-id>#n` or `<chat-id>@<day>#n`), `day` (chats) and `similar_entries` from the repository |
| `rejected` | Memes that failed validation even after one repair round, or fell below `meme_confidence_threshold`, with the reasons |

## Generating

```bash
cd backend
python -m app.ai_parser --all            # every mock source in mock_data/sources/index.json
python -m app.ai_parser m1 c2            # some of them
python -m app.ai_parser.eval             # compare the files here with mock_data/sources/expected/
```

Requires the Cursor CLI (`agent`), signed in with `agent login` or `CURSOR_API_KEY`. After regenerating, delete `backend/peerpoint.db` so the new files are loaded on the next start.
