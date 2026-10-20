"""Extract memes with the Cursor CLI into backend/memes/.

    python -m app.ai_parser m1 c2          # sources from mock_data/sources/index.json
    python -m app.ai_parser --all
    python -m app.ai_parser path/to/chat-export.json
"""
import argparse
import json
import sys
from pathlib import Path

from app.ai_parser import pipeline
from app.ai_parser.cursor_cli import CursorCliError
from app.ai_parser.sources import load_chat
from app.database import SessionLocal, init_db
from app.seeds import seed_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ai_parser", description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs="*", help="ids from mock_data/sources/index.json, or paths to chat exports")
    parser.add_argument("--all", action="store_true", help="every source in mock_data/sources/index.json")
    args = parser.parse_args(argv)

    index = {row["id"]: row for row in json.loads((pipeline.SOURCES_DIR / "index.json").read_text(encoding="utf-8"))}
    names = list(index) if args.all else args.sources
    if not names:
        parser.error("name at least one source, or use --all")

    init_db()
    seed_all()  # the agent maps speakers to users, so the demo users must exist
    failed = 0
    with SessionLocal() as db:
        for name in names:
            try:
                source = pipeline.source_from_index(db, index[name]) if name in index else load_chat(Path(name))
                for path in pipeline.run_source(db, source):
                    print(f"{name}: wrote {path}")
            except (CursorCliError, OSError, ValueError, KeyError) as exc:
                failed += 1
                print(f"{name}: failed — {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
