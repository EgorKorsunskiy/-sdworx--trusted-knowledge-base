"""AI parser data (specs/ai-parser/FUNCTIONAL_SPEC.md): sources, memes, per-candidate suggestions with an
append-only decision history, usefulness votes and co-authorship requests.

These are the tables the Information overview needs. Sources and memes are filled by an agent (for the demo, the stub
agent in ``app.services.parser_agent`` that reads ``mock_data/sources``)."""

from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MemeStatus(str, Enum):
    NEW = "new"
    PREPARING = "preparing"
    PUBLISHED = "published"
    DECLINED = "declined"


class SuggestionState(str, Enum):
    PENDING = "pending"
    POSTPONED = "postponed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CLOSED = "closed"


class RequestStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


meme_tags = Table(
    "meme_tags",
    Base.metadata,
    Column("meme_id", ForeignKey("memes.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)


class Source(Base):
    """One meeting transcript or group chat that the agents processed."""

    __tablename__ = "parser_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # meeting | chat
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    mock_id: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    uploader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # BR-M7: the raw transcript is kept only until extraction is confirmed (default 30 days), then purged
    raw_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    participants: Mapped[list["SourceParticipant"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    memes: Mapped[list["Meme"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class SourceParticipant(Base):
    """The participant list is fixed at import time (BR-M1)."""

    __tablename__ = "parser_participants"
    __table_args__ = (UniqueConstraint("source_id", "user_id", name="uq_source_participant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("parser_sources.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    source: Mapped["Source"] = relationship(back_populates="participants")
    user = relationship("User")


class Meme(Base):
    """One self-contained unit of information with exactly one speaker and at least one quote."""

    __tablename__ = "memes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("parser_sources.id"), nullable=False, index=True)
    speaker_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="fact")
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    category_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="country")
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    client_project_id: Mapped[int | None] = mapped_column(ForeignKey("client_projects.id"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=MemeStatus.NEW.value, index=True)
    entry_id: Mapped[int | None] = mapped_column(ForeignKey("entries.id"), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    nudged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    similar_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    source: Mapped["Source"] = relationship(back_populates="memes")
    speaker = relationship("User", foreign_keys=[speaker_id])
    entry = relationship("Entry")
    company = relationship("Company")
    client_project = relationship("ClientProject")
    tags = relationship("Tag", secondary=meme_tags)
    quotes: Mapped[list["Quote"]] = relationship(
        back_populates="meme", cascade="all, delete-orphan", order_by="Quote.id"
    )
    suggestions: Mapped[list["Suggestion"]] = relationship(
        back_populates="meme", cascade="all, delete-orphan", order_by="Suggestion.id"
    )
    votes: Mapped[list["UsefulnessVote"]] = relationship(back_populates="meme", cascade="all, delete-orphan")
    coauthor_requests: Mapped[list["CoauthorRequest"]] = relationship(
        back_populates="meme", cascade="all, delete-orphan", order_by="CoauthorRequest.id"
    )


class Quote(Base):
    """An exact source fragment: the statement, or a confirmation by one confirmer."""

    __tablename__ = "meme_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meme_id: Mapped[int] = mapped_column(ForeignKey("memes.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    at: Mapped[str] = mapped_column(String(32), nullable=False)  # timestamp (meeting) or message id (chat)
    is_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    # A few lines around the quote, cut from the source at import time (JSON list)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    meme: Mapped["Meme"] = relationship(back_populates="quotes")
    user = relationship("User")


class Suggestion(Base):
    """A meme as offered to one author candidate: their personal authorship request (BR-M9)."""

    __tablename__ = "meme_suggestions"
    __table_args__ = (UniqueConstraint("meme_id", "user_id", name="uq_meme_suggestion_owner"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meme_id: Mapped[int] = mapped_column(ForeignKey("memes.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # speaker | confirmer
    state: Mapped[str] = mapped_column(String(16), nullable=False, default=SuggestionState.PENDING.value)
    basis: Mapped[str | None] = mapped_column(String(16), nullable=True)
    basis_source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    basis_hint_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    meme: Mapped["Meme"] = relationship(back_populates="suggestions")
    user = relationship("User")
    events: Mapped[list["SuggestionEvent"]] = relationship(
        back_populates="suggestion", cascade="all, delete-orphan", order_by="SuggestionEvent.id"
    )


class SuggestionEvent(Base):
    """Decision history (FR-MO20): append-only; a later decision adds a row, nothing is changed or deleted."""

    __tablename__ = "meme_suggestion_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    suggestion_id: Mapped[int] = mapped_column(ForeignKey("meme_suggestions.id"), nullable=False, index=True)
    # created | approve | reject | postpone | reopen | withdraw | closed | joined
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    basis: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    suggestion: Mapped["Suggestion"] = relationship(back_populates="events")


@event.listens_for(SuggestionEvent, "before_update")
@event.listens_for(SuggestionEvent, "before_delete")
def _history_is_append_only(mapper, connection, target):
    raise RuntimeError("meme_suggestion_events is append-only")


class UsefulnessVote(Base):
    """A participant's judgement of a colleague's meme; separate from usage-record votes on entries."""

    __tablename__ = "meme_votes"
    __table_args__ = (UniqueConstraint("meme_id", "user_id", name="uq_meme_vote"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meme_id: Mapped[int] = mapped_column(ForeignKey("memes.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    useful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    meme: Mapped["Meme"] = relationship(back_populates="votes")
    user = relationship("User")


class CoauthorRequest(Base):
    """A participant asks the authors of a published meme for co-authorship (FR-MO10 to FR-MO15)."""

    __tablename__ = "meme_coauthor_requests"
    # One row per person and meme: one open request at a time, and a declined one cannot be repeated (FR-MO14)
    __table_args__ = (UniqueConstraint("meme_id", "requester_id", name="uq_coauthor_request"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meme_id: Mapped[int] = mapped_column(ForeignKey("memes.id"), nullable=False, index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    basis: Mapped[str] = mapped_column(String(16), nullable=False)
    basis_source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Where the requester said or confirmed it: a timestamp or message reference, or their detected quote
    evidence: Mapped[str | None] = mapped_column(String(500), nullable=True)
    evidence_quote_id: Mapped[int | None] = mapped_column(ForeignKey("meme_quotes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RequestStatus.PENDING.value)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    meme: Mapped["Meme"] = relationship(back_populates="coauthor_requests")
    requester = relationship("User", foreign_keys=[requester_id])
    decided_by = relationship("User", foreign_keys=[decided_by_id])
    evidence_quote = relationship("Quote")
