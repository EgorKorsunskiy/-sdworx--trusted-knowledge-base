"""Compare the agent's memes in backend/memes/ with the expected memes of the mock scenarios.

    python -m app.ai_parser.eval          # score what is in backend/memes/
    python -m app.ai_parser.eval --run    # extract every mock source first (uses Cursor quota)

A produced meme overlaps an expected one when both have the same speaker and share a statement
quote. An expected meme is covered when some produced meme overlaps it; the agent may cut the
same information into more or fewer memes than the scenario (split / merged), which is reported
separately from unrelated extra memes. Kind is compared with the produced meme that overlaps the expected one most; its confirmers
should be those of every expected meme it overlaps.
"""
import argparse
import json

from app import config
from app.ai_parser import pipeline


def produced_memes(row: dict) -> list[dict]:
    stem = row["file"].split("/")[-1].rsplit(".", 1)[0]
    if row["type"] == "meeting":
        path = config.MEMES_DIR / "meetings" / f"{stem}.json"
        files = [path] if path.exists() else []
    else:
        files = sorted((config.MEMES_DIR / "chats" / stem).glob("*.json"))
    return [m for f in files for m in json.loads(f.read_text(encoding="utf-8"))["memes"]]


def _statement_ats(meme: dict) -> set[str]:
    return {q["at"] for q in meme["quotes"]}


def _overlap(a: dict, b: dict) -> int:
    return len(_statement_ats(a) & _statement_ats(b)) if a["speaker"] == b["speaker"] else 0


def _expected_confirmers(expected: list[dict], produced: dict) -> set[str]:
    """When a produced meme merges several expected ones, it should carry all their confirmers."""
    return {c["user"] for e in expected if _overlap(e, produced) for c in e["confirmed_by"]}


def score(produced: list[dict], expected: dict) -> dict:
    exp = expected["memes"]
    best = [max(produced, key=lambda p: _overlap(e, p), default=None) for e in exp]
    best = [p if p is not None and _overlap(e, p) else None for e, p in zip(exp, best)]
    pairs = [(e, p) for e, p in zip(exp, best) if p is not None]
    unrelated = [p for p in produced if not any(_overlap(e, p) for e in exp)]
    reshaped = sum(
        sum(1 for p in produced if _overlap(e, p)) > 1  # split into several memes
        or any(_overlap(o, p) for o in exp if o is not e)  # merged with another expected meme
        for e, p in pairs
    )
    traps = _traps_by_expect(expected["traps"])
    violations = []
    for m in produced:
        quoted = _statement_ats(m) | {c["quote"]["at"] for c in m["confirmed_by"]}
        violations += [f"quotes {at}" for at in sorted(quoted & traps["not_quoted"])]
        violations += [f"confirmer at {c['quote']['at']}" for c in m["confirmed_by"] if c["quote"]["at"] in traps["not_confirmer"]]
    for m in unrelated:
        violations += [f"meme from {at}" for at in sorted(_statement_ats(m) & traps["no_meme"])]
    return {
        "expected": len(exp),
        "covered": len(pairs),
        "unrelated": len(unrelated),
        "reshaped": reshaped,
        "confirmers": sum(_expected_confirmers(exp, p) == {c["user"] for c in p["confirmed_by"]} for _, p in pairs),
        "kind": sum(e["kind"] == p["kind"] for e, p in pairs),
        "kind_diffs": [f"{e['kind']} → {p['kind']}: {p['statement']}" for e, p in pairs if e["kind"] != p["kind"]],
        "violations": violations,
        "extras": [p["statement"] for p in unrelated],
    }


def _traps_by_expect(traps: list[dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {"no_meme": set(), "not_confirmer": set(), "not_quoted": set(), "use_final_text": set()}
    for t in traps:
        out.setdefault(t["expect"], set()).add(t["at"])
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ai_parser.eval")
    parser.add_argument("--run", action="store_true", help="extract every mock source with the Cursor CLI first")
    args = parser.parse_args(argv)
    if args.run:
        from app.ai_parser.__main__ import main as extract

        extract(["--all"])

    rows = json.loads((pipeline.SOURCES_DIR / "index.json").read_text(encoding="utf-8"))
    print(f"{'source':<8}{'covered':>9}{'unrelated':>11}{'split/merged':>14}{'confirmers':>12}{'kind':>8}  trap violations")
    keys = ("expected", "covered", "unrelated", "reshaped", "confirmers", "kind")
    totals = dict.fromkeys(keys, 0) | {"violations": 0}
    extras = []
    for row in rows:
        expected = json.loads((pipeline.SOURCES_DIR / row["expected"]).read_text(encoding="utf-8"))
        s = score(produced_memes(row), expected)
        print(f"{row['id']:<8}{s['covered']:>6}/{s['expected']:<2}{s['unrelated']:>11}{s['reshaped']:>14}"
              f"{s['confirmers']:>9}/{s['covered']:<2}{s['kind']:>5}/{s['covered']:<2} {', '.join(s['violations']) or '—'}")
        for key in keys:
            totals[key] += s[key]
        totals["violations"] += len(s["violations"])
        extras += [f"{row['id']}: {text}" for text in s["extras"]]
    print(f"{'total':<8}{totals['covered']:>6}/{totals['expected']:<2}{totals['unrelated']:>11}{totals['reshaped']:>14}"
          f"{totals['confirmers']:>9}/{totals['covered']:<2}{totals['kind']:>5}/{totals['covered']:<2} {totals['violations']} violations")
    if extras:
        print("\nUnrelated extra memes:")
        print("\n".join(f"  - {e}" for e in extras))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
