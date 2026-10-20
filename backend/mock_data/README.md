# Mock data

Demo data loaded by `app/seeds` on startup. Seeding runs only on an empty database, so after editing these files delete `backend/peerpoint.db` and restart the backend.

| File | Rows | References |
|---|---|---|
| `categories.json` | `name`, `description`, `is_default` | — |
| `teams.json` | `name`, `department`, `description`, `lead`, `members` (`user`, `role`, `primary`) | `lead` / `members[].user` → user `email` |
| `users.json` | `email`, `display_name`, `department`, `title`, `country`, `roles`, optional `expert_departments` | — |
| `projects.json` | Internal projects: `name`, `description`, `status` (`active` / `completed`), `lead`, `members` (`user`, `role`, `start_date`, optional `end_date`) | `lead` / `members[].user` → user `email` |
| `settings.json` | `key`, `value`, `value_type`, `description` | — |
| `entries.json` | `public_id`, `scope`, `department`, `country`, `category`, `author`, optional `team`, `tags`, `versions` | `category` → category `name`, `author` / `edited_by` / `verifier` → user `email`, `team` → team `name` |
| `history_demo.json` | Entries in the `entries.json` format, without `public_id` (generated), for the change log demo | as `entries.json` |

- User ids follow the order in `users.json`; tests log in by id (1 = Employee A … 7 = Admin), so append new users at the end.
- Verification scope of team leads and managers relies on **primary** team memberships; the `Payroll Experts` memberships are deliberately non-primary.
- An entry without `team` belongs to its author's primary team, so the author's team lead and manager can verify it.
- `versions` are numbered in list order; each takes `title`, `body`, optional `justification`, `status` (default `Unverified`), `change_note`, `edited_by` (default: the entry author), optional `created_days_ago` (default: now) and optional `verifications` (`verifier`, `role`, `days_ago`).
- Projects and settings are also added to an already-seeded database when they are missing; `history_demo.json` is seeded only when the `seed_history_demo` setting is on (default).
- A missing file is treated as an empty list.

## Sources for the AI parser

`sources/` holds mock Teams meeting transcripts and group chat exports for the AI parser, one per [mock scenario](../../specs/ai-parser/MOCK_SCENARIOS.md). The seeder does not load them.

| Path | Content |
|---|---|
| `index.json` | One row per source: `id`, `type` (`meeting` or `chat`), `title`, `date` or `date_from` / `date_to`, `file`, `expected`; meetings also list `participants` (user e-mails) and `guests` (speaker labels without a user) |
| `meetings/*.vtt` | Teams WebVTT transcripts: one cue per turn, speaker as `<v Display Name>`, e.g. `<v Employee A>` or `<v Lotte (Guest)>` |
| `chats/*.json` | Group chat exports: `chat`, `range`, `members` (`email`, `display_name`) and `messages` |
| `expected/*.json` | What a correct agent returns for that source: `memes` in the [agent contract](../../specs/ai-parser/FUNCTIONAL_SPEC.md#6-agent-contract) format, plus `traps` and `notes` |

- **Chat message** fields: `id`, `from` (e-mail), `created_at`, `text`, `reply_to_id`, `reactions` (`emoji`, `by`); optional `mentions`, `attachments` (`type`, `name`), `pinned`, `edited_at` with `edit_history` (`text`, `created_at`), and `deleted_at`. A deleted message stays in the export with its text.
- **Quote `at`** is the cue start `HH:MM:SS` for meetings or the message `id` for chats. The quote `text` is an exact fragment of that cue or message, by the same person.
- **Trap `expect`** is one of `no_meme`, `not_confirmer`, `not_quoted` (must never be quoted) or `use_final_text` (edited message).
- **`confidence` and `similar_entries[].score` are indicative.** When comparing agent output with the expected file, compare speakers, confirmers, kind, `sensitive` and the meaning of each statement.
