"""Deterministic checks of the agent's reply against the source (BR-M6: no quote, no meme)."""
from pydantic import ValidationError

from app.ai_parser.schema import AgentMeme
from app.ai_parser.sources import Source, normalize


def _check_quote(source: Source, at: str, text: str, email: str, label: str) -> tuple[int | None, list[str]]:
    """Order of the quoted unit, or the reasons the quote does not hold."""
    units = source.units_at(at)
    if not units:
        return None, [f"{label}: there is no line with at={at!r}"]
    name = source.participants.get(email)
    wanted = normalize(text)
    for unit in units:
        if not unit.deleted and unit.speaker == name and wanted and wanted in normalize(unit.text):
            return unit.order, []
    unit = units[0]
    if unit.deleted:
        return None, [f"{label}: line {at} is a deleted message and must not be quoted"]
    if unit.speaker != name:
        return None, [f"{label}: line {at} is by {unit.speaker}, not by {name or email}"]
    return None, [f"{label}: text is not an exact fragment of line {at}"]


def check_meme(meme: AgentMeme, source: Source) -> list[str]:
    errors: list[str] = []
    if meme.speaker not in source.participants:
        errors.append(f"speaker {meme.speaker} is not a participant (guests cannot be speakers)")
    if not meme.quotes:
        errors.append("a meme needs at least one quote by its speaker")
    if not meme.tags:
        errors.append("a meme needs at least one tag")

    orders = []
    for n, quote in enumerate(meme.quotes, 1):
        if quote.speaker != meme.speaker:
            errors.append(f"quote {n}: statement quotes must be by the speaker {meme.speaker}")
            continue
        order, errs = _check_quote(source, quote.at, quote.text, quote.speaker, f"quote {n}")
        errors += errs
        if order is not None:
            orders.append(order)

    for c in meme.confirmed_by:
        label = f"confirmation by {c.user}"
        if c.user == meme.speaker:
            errors.append(f"{label}: the speaker cannot confirm their own meme")
            continue
        if c.user not in source.participants:
            errors.append(f"{label}: not a participant (guests cannot confirm)")
            continue
        order, errs = _check_quote(source, c.quote.at, c.quote.text, c.user, label)
        errors += errs
        if order is not None and orders and order <= min(orders):
            errors.append(f"{label}: the confirmation must come after the statement")

    hints = [("speaker basis hint", meme.speaker_basis_hint)] + [
        (f"basis hint of {c.user}", c.basis_hint) for c in meme.confirmed_by
    ]
    for label, hint in hints:
        if hint and hint.basis == "relayed" and not hint.source:
            errors.append(f"{label}: a relayed basis needs a source")

    scope = meme.suggested
    if scope.scope == "company" and not scope.company:
        errors.append("suggested.scope company needs suggested.company")
    if scope.scope == "client_project" and not scope.client_project:
        errors.append("suggested.scope client_project needs suggested.client_project")
    return errors


def validate_reply(data: object, source: Source) -> tuple[list[AgentMeme], list[dict]]:
    """Valid memes, and one problem per invalid meme: {index, meme, errors}."""
    if not isinstance(data, dict) or not isinstance(data.get("memes"), list):
        return [], [{"index": None, "meme": data, "errors": ["the reply must be an object with a 'memes' list"]}]
    memes, problems = [], []
    for index, raw in enumerate(data["memes"], 1):
        try:
            meme = AgentMeme.model_validate(raw)
        except ValidationError as exc:
            errors = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
            problems.append({"index": index, "meme": raw, "errors": errors})
            continue
        errors = check_meme(meme, source)
        if errors:
            problems.append({"index": index, "meme": raw, "errors": errors})
        else:
            memes.append(meme)
    return memes, problems
