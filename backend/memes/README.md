# Memes

**Agent output** of the AI parser (`app/ai_parser`, spec: [specs/ai-parser](../../specs/ai-parser/FUNCTIONAL_SPEC.md)) for the mock sources in `mock_data/sources/`. The Cursor CLI reads one meeting transcript or one group chat; the backend validates its answer and writes the memes here, to compare them with the expected memes (`python -m app.ai_parser.eval`). Only mocks belong here.

These files are not loaded into the database: the demo is filled from the expected memes by the stub agent (`seed_parser_demo`), and real uploads (`POST /parser/sources`) go straight to the database through the Information overview's import.

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

Requires the Cursor CLI (`agent`), signed in with `agent login` or `CURSOR_API_KEY`.
