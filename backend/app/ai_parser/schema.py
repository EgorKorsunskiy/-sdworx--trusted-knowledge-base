"""The meme format the agent returns (agent contract, section 6 of the AI parser spec)."""
from typing import Literal

from pydantic import BaseModel

Kind = Literal["fact", "rule", "decision", "how-to"]
Scope = Literal["universal", "eu", "country", "company", "client_project"]


class BasisHint(BaseModel):
    basis: Literal["responsible", "relayed"]
    source: str | None = None


class Quote(BaseModel):
    speaker: str
    text: str
    at: str  # cue start "HH:MM:SS" (meetings) or message id (chats)


class ConfirmationQuote(BaseModel):
    text: str
    at: str


class Confirmation(BaseModel):
    user: str
    quote: ConfirmationQuote
    basis_hint: BasisHint | None = None


class Suggested(BaseModel):
    title: str
    category: str
    country: str | None = None
    scope: Scope = "country"
    company: str | None = None
    client_project: str | None = None


class AgentMeme(BaseModel):
    """One meme as the agent returns it; the backend adds id, source and similar entries."""

    speaker: str
    speaker_basis_hint: BasisHint | None = None
    kind: Kind
    statement: str
    suggested: Suggested
    tags: list[str]
    quotes: list[Quote]
    confirmed_by: list[Confirmation] = []
    confidence: float
    sensitive: bool = False
