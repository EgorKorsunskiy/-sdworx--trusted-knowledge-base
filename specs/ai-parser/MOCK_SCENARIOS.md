# AI parser — Mock scenarios

*Demo and test sources for the [AI parser spec](FUNCTIONAL_SPEC.md) · draft · 2026-10-20*

Six mock sources, three Teams meeting transcripts and three group chats, for the demo and as test cases for both agents. Each scenario describes:

- the **problem** being discussed,
- the **conversation manner** the mock must reproduce,
- the **flow** of the conversation,
- the **expected memes** a correct agent returns,
- the **traps**: what it must not return.

> All people, cases and payroll rules here are fictional or simplified for the demo. Real institutions and tools (Limosa, A1, DmfA, KBO/BCE, VIES) are mentioned for realism, but cut-off dates, thresholds and internal procedures are invented. This is not real legal or payroll guidance.

## Cast

Speakers are the demo users from [`backend/mock_data/users.json`](../../backend/mock_data/users.json). Each keeps the same voice across all scenarios.

| Person | Role | Voice |
| --- | --- | --- |
| Employee A | Payroll consultant, experienced | Talks fast, corrects themselves mid-sentence, a bit defensive when challenged |
| Employee B | Payroll consultant, junior | Asks a lot, short replies ("ok", "mm-hmm", "thx"), lowercase and emojis in chat |
| Employee C | Payroll consultant | Bilingual, sometimes writes in Dutch, reads the newsletters and cites sources |
| Senior Expert | Senior payroll expert | Thorough, explains in numbered points, precise terminology, politely corrects others |
| Team Lead | Team lead | Chairs the weekly, pragmatic, turns discussions into action items |
| Manager | Payroll manager | Formal, decides and summarizes ("So, decision: …"), short acknowledgements ("noted", "ok, ok") |
| Admin | Platform admin | Appears only in the cross-team chat; GDPR and tooling |
| Lotte (guest) | Client HR contact, **not a Peerpoint user** | Polite, shares case-specific details freely |

### Participation and visibility

Who takes part in which source; nobody else may see its memes (BR-M1).

| | M1 | M2 | M3 | C1 | C2 | C3 |
| --- | --- | --- | --- | --- | --- | --- |
| Employee A | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Employee B | ✓ | | ✓ | ✓ | ✓ | ✓ |
| Employee C | ✓ | ✓ | | ✓ | ✓ | |
| Senior Expert | | ✓ | ✓ | ✓ | | ✓ |
| Team Lead | ✓ | | ✓ | ✓ | ✓ | |
| Manager | ✓ | | ✓ | | ✓ | ✓ |
| Admin | | | | | | ✓ |

---

## Meeting transcripts

### M1 · Payroll BE weekly

| | |
| --- | --- |
| Source | Teams meeting transcript · 2026-10-14 · 30 min |
| Participants | Team Lead (chair), Employee A, Employee B, Employee C, Manager (joins at 14:30) |

**Problem.** Every month contractor invoices arrive late, which forces off-cycle payments and a stressful last week. The team has agreed a later cut-off (the 25th) and needs a clear rule for urgent exceptions. A fake invoice that reached another team last month also raised the question of checking VAT numbers.

**Conversation manner**

- Informal and friendly, first names, fast turn-taking, people talk over each other.
- Three minutes of small talk at the start (weekend, the broken coffee machine).
- Round-robin structure: Team Lead asks everyone "anything from your side?".
- Fillers and backchannels: "so, uh", "yeah, yeah", "mm-hmm", "ok".
- Self-corrections mid-sentence.
- Speech-recognition artifacts: numbers spelled out ("twenty-fifth"), "VIES" transcribed as "vies".
- Ends with action items and "thanks all, see you next week".

Sample lines:

> **Employee A:** So anything that comes in after the twentieth — no, sorry, the twenty-fifth — goes into next month's run.
> **Employee B:** Mm-hmm, ok.
> **Employee C:** Yes, that's right, it was in the payroll newsletter in September.

**Flow**

1. 00:00 Small talk.
2. 03:10 Team Lead opens planning of the November run.
3. 12:31 Employee A explains the cut-off with a self-correction; B acknowledges, C confirms with a source.
4. 14:30 Manager joins ("sorry, I'm late").
5. 15:05 Team Lead: an urgent invoice after the cut-off can still be paid only with the Team Lead's approval by e-mail before the run is closed. Manager: "Yes, that's how we agreed it with Finance."
6. 19:40 Employee B: since the fake invoice, Finance asked everyone to check a new contractor's VAT number in VIES before the first payment.
7. 24:15 Employee B asks whether the cut-off also applies to Luxembourg contractors; Team Lead: "Good question, no idea, let's check." Nobody answers.
8. 27:00 Action items: "C, can you update the checklist by Friday?", "B, send the reminder to the contractors."

**Expected memes**

| # | Statement | Speaker | Confirmers | Kind | Basis hints | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Contractor invoices received after the 25th are processed in the next month's payroll run. | Employee A | Employee C | rule | A: responsible · C: relayed, "Payroll newsletter, September 2026" | Self-correction → 25th, both fragments quoted. Same as the example in the [agent contract](FUNCTIONAL_SPEC.md#6-agent-contract) |
| 2 | An urgent contractor invoice received after the cut-off can only be paid with the Team Lead's approval by e-mail before the run is closed. | Team Lead | Manager | rule | Team Lead: responsible | Both candidates are verifiers of this team; if both accept, only the Senior Expert can verify the entry (BR-M3) |
| 3 | Before the first payment to a new contractor, check their VAT number in VIES. | Employee B | — | how-to | B: relayed, "Finance team, September 2026" | "vies" normalized to "VIES" |

**Traps — must produce no meme or confirmer**

- Small talk and Manager's "sorry, I'm late".
- B's "mm-hmm, ok" after meme 1 is an acknowledgement, not a confirmation.
- The Luxembourg question stays unanswered.
- Both action items are tasks, not knowledge.

**Exercises:** FR-MT4, FR-MT5, FR-MA5, FR-MA11, FR-MO16, BR-M3.

### M2 · Dutch freelancer on-site in Belgium

| | |
| --- | --- |
| Source | Teams meeting transcript · 2026-10-08 · 45 min |
| Participants | Employee C (case owner), Senior Expert, Employee A, Lotte (client HR, guest — not a Peerpoint user) |

**Problem.** A client wants to bring in a self-employed consultant from the Netherlands to work on-site in Belgium for three months, starting in two weeks. Employee C is unsure which formalities apply and invited the Senior Expert. Three issues come up: the Limosa declaration, the A1 certificate, and the risk of bogus self-employment, because the client wants fixed working hours.

**Conversation manner**

- More formal and slower because a client is present; everyone introduces themselves.
- The Senior Expert explains at length and in structure ("there are three things to look at…"). They use local terms: *zelfstandige*, *schijnzelfstandigheid* / *faux indépendant*.
- The guest shares case details freely: the consultant's name, day rate, start date and the client's company name.
- Employee C repeats back as a question ("So if I understand correctly…?") instead of stating anything.
- Speech-recognition artifacts on jargon: "Limosa" → "Lima so", "A1" → "a one", *schijnzelfstandigheid* garbled.
- The guest appears in the transcript as "Lotte (Guest)", so there is no matching user (FR-MT3).

Sample lines:

> **Senior Expert:** There are three things to look at. First, the Lima so declaration — it has to be done before the first working day, and you, as the client, should ask for the L1 receipt.
> **Employee A:** Yes, exactly — we had the same with a German freelancer in spring, I checked it on the Limosa portal then.
> **Employee C:** So if I understand correctly, we need the L1 and the a one before day one?
> **Senior Expert:** Exactly.

**Flow**

1. 00:00 Introductions.
2. 03:00 Lotte describes the case with personal and commercial details.
3. 08:20 Senior Expert: Limosa declaration before the first working day; the client asks for the L1 receipt. Employee A confirms from their own experience.
4. 14:00 Senior Expert: an A1 certificate from the Dutch social security office shows that the consultant stays insured in the Netherlands; without it there is a risk of double contributions.
5. 19:30 Lotte: "We always handle the Limosa ourselves, it's never been a problem."
6. 24:00 Lotte: the client wants fixed hours from 9 to 5, with the consultant reporting to their team manager. Senior Expert: whenever a client sets fixed hours or gives instructions to a freelancer, the case must be flagged to a Senior Expert before the contract is signed.
7. 33:00 Employee C asks the repeat-back question; Senior Expert says "Exactly."
8. 38:00 Next steps with the client.

**Expected memes**

| # | Statement | Speaker | Confirmers | Kind | Basis hints | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | A foreign self-employed person working in Belgium needs a Limosa declaration before the first working day; the client should ask for the L1 receipt. | Senior Expert | Employee A | rule | Senior Expert: responsible · A: relayed, "Limosa portal" | Generic statement: no consultant name, rate or client name |
| 2 | An A1 certificate from the home country shows which country's social security applies; without it there is a risk of double contributions. | Senior Expert | — | fact | Senior Expert: responsible | "a one" normalized to "A1" |
| 3 | If a client sets fixed working hours or gives instructions to a freelancer, flag the case to a Senior Expert before the contract is signed. | Senior Expert | — | how-to | Senior Expert: responsible | Internal procedure, triggered by the bogus self-employment risk |

All three memes are `sensitive: false`: their statements and quotes contain no case details. A meme that quotes Lotte's case description must be flagged `sensitive: true`.

**Traps**

- Lotte's statements, even informative ones, are skipped: she has no Peerpoint user (FR-MA4).
- Case-specific facts (name, day rate, start date, client) are case data, not knowledge.
- C's repeat-back question and the Senior Expert's "Exactly." produce neither a new meme nor a confirmation.
- Speech-recognition misspellings must not leak into statements.

**Exercises:** FR-MA4, FR-MT3, FR-MA10, BR-M5, FR-MA11, FR-MO16.

### M3 · Q3 contractor payroll review

| | |
| --- | --- |
| Source | Teams meeting transcript · 2026-10-01 · 60 min |
| Participants | Manager (chair), Team Lead, Senior Expert, Employee A, Employee B |

**Problem.** In the quarterly retrospective, the team reviews two duplicate payments in Q3: the same contractor invoice was paid twice because it arrived both by e-mail and by post. They debate a four-eyes check and the Manager decides on a threshold. In passing, the Senior Expert points out that an existing knowledge-base entry about DmfA for freelancers is wrong.

**Conversation manner**

- Structured and agenda-driven; the Manager opens with the agenda, timeboxes topics and closes each one with an explicit decision.
- Formal register, longer turns, little small talk.
- A real debate: B proposes a lower threshold, the Team Lead argues about workload, the Manager decides.
- The incident review names a specific contractor and amounts.
- The Manager acknowledges while others speak ("ok, ok", "noted").
- The Senior Expert interrupts politely to correct a factual mistake; A reacts defensively first, then admits it.

Sample lines:

> **Employee B:** Why not every invoice above two and a half thousand?
> **Team Lead:** That would double the checks, we don't have the people for that.
> **Manager:** Ok, ok. So, decision: every contractor invoice above five thousand euros gets a four-eyes check, starting with the November run.
> **Team Lead:** Agreed, I'll make sure the team applies it.

**Flow**

1. 00:00 Manager: agenda and timeboxes.
2. 04:00 Incident review: contractor name, invoice number and the amount paid twice.
3. 15:00 Team Lead: before paying, search the payment log by invoice number and the contractor's VAT number.
4. 22:00 Threshold debate; the Manager decides on €5,000 from the November run; the Team Lead agrees explicitly.
5. 38:00 Employee A: "as in our DmfA entry, freelancers are declared quarterly…". Senior Expert: "Sorry, I have to correct that: freelancers are not declared in the DmfA, that's the employer declaration for employees. Self-employed people pay their contributions through their social insurance fund." A: "Hm. You're right, I mixed that up in the entry."
6. 52:00 "Tooling we'll discuss next quarter."

**Expected memes**

| # | Statement | Speaker | Confirmers | Kind | Basis hints | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | From the November 2026 run, every contractor invoice above €5,000 needs a four-eyes check before payment. | Manager | Team Lead | decision | Manager: responsible · Team Lead: responsible | Only the final decision, not B's proposal. Both candidates are verifiers of this team (BR-M3) |
| 2 | Freelancers are not declared in the DmfA; self-employed people pay social contributions through their social insurance fund. | Senior Expert | Employee A | fact | Senior Expert: responsible | Contradicts the seeded `PP-BE-FRE-00001` — the demo hook for "a meeting reveals an outdated entry". Found only by semantic similarity: the keyword score is 0.11 |
| 3 | Before paying a contractor invoice, search the payment log by invoice number and the contractor's VAT number to avoid paying it twice. | Team Lead | — | how-to | Team Lead: responsible | |

**Traps**

- Incident details (contractor name, amounts) never appear in a statement; a meme quoting them is `sensitive: true`.
- B's €2,500 proposal is an opinion that was not adopted.
- A's wrong DmfA statement was corrected, so it is not a meme (FR-MT5).
- "Next quarter" is a deferral, not knowledge.
- The Manager's "ok, ok" is not a confirmation.

**Exercises:** FR-MA5, FR-MT5, FR-MA9, FR-MA10, FR-MA11, BR-M3.

---

## Group chats

### C1 · Payroll BE — questions

| | |
| --- | --- |
| Source | Teams group chat · 2026-10-01 → 2026-10-14 · 31 messages |
| Members | Employee A, Employee B, Employee C, Senior Expert, Team Lead |

**Problem.** The team's everyday Q&A chat: the junior consultant and colleagues ask practical questions. Answers are spread over several messages and often come hours later.

**Conversation manner**

- Short, informal messages: lowercase, typos, abbreviations ("CN" for credit note, "pls", "thx", "afaik"), emojis.
- One thought split over several consecutive messages.
- Replies hours later, sometimes as threaded replies, sometimes as new messages quoting the question.
- Reactions (👍 ❤️ 😂) instead of answers.
- Lunch and coffee chatter in between.

Sample lines:

> **Employee B** (Oct 2, 09:14): how do we handle a CN from a contractor if the original invoice was already paid?
> **Senior Expert** (13:40): don't pay it out
> **Senior Expert** (13:40): register it and deduct it from the next invoice of the same contractor
> **Senior Expert** (13:41): if there's no next invoice within 2 months, ask Finance for a refund request
> **Employee C** (14:05, reply): confirmed, did exactly that last month 👍
> *Team Lead reacted 👍*

**Flow**

1. Oct 2: credit-note question; three-message answer from the Senior Expert; C's confirming reply; the Team Lead's reaction.
2. Oct 6: C: "where's the monthly contractor overview template again?" A: "team sharepoint > Templates > Contractors, TL moved it there in sept".
3. Oct 9: B: "are freelancer travel costs paid via payroll?" Team Lead: "no — freelancers invoice travel costs themselves, we only process the invoice." A, replying: "yep, correct." B: "ok thx".
4. Oct 10: B: "anyone knows if the Luxembourg rules are the same? 🤔". No answer.
5. Scattered: "lunch at 12?", a 😂 GIF, "thx!!".

**Expected memes**

| # | Statement | Speaker | Confirmers | Kind | Basis hints | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | A contractor's credit note for an already-paid invoice is not paid out: register it and deduct it from the contractor's next invoice; if there is none within two months, ask Finance for a refund. | Senior Expert | Employee C | how-to | Senior Expert: responsible | One meme from three messages (FR-MC3); the Team Lead's 👍 is not a confirmation (FR-MC6) |
| 2 | The monthly contractor overview template is in the team SharePoint under Templates > Contractors. | Employee A | — | how-to | — | Answerer is the speaker, not C who asked (FR-MC4) |
| 3 | Freelancers invoice their travel costs themselves; payroll only processes the invoice. | Team Lead | Employee A | fact | Team Lead: responsible | "yep, correct" replying to the statement is a confirmation; the asker's "ok thx" is not |

**Traps**

- The Luxembourg question is never answered.
- "lunch at 12?", GIFs, "thx!!", "ok thx".
- Reactions never count as confirmations or votes.

**Exercises:** FR-MC3, FR-MC4, FR-MC6, FR-MA5, FR-MA11.

### C2 · Contractor payroll — announcements

| | |
| --- | --- |
| Source | Teams group chat · 2026-09-22 → 2026-10-16 · 14 messages |
| Members | Team Lead, Manager, Employee A, Employee B, Employee C |

**Problem.** The chat where process changes are announced. The cut-off change from M1 is announced here first, then postponed by Finance; a holiday exception follows; questions are asked in threads under the announcements.

**Conversation manner**

- Semi-formal announcements: 📌 pin, bold first line, bullet lists, @mentions.
- Questions and answers in threads under each announcement.
- Edited messages ("edited"); the agent must use the final text.
- Bilingual: Employee C replies in Dutch.
- Acknowledgements instead of content: "noted", "👀", "thanks for the heads-up".

Sample lines:

> **Team Lead** (Sep 22): 📌 **Cut-off change** — from the October run, the cut-off for contractor invoices moves from the 20th to the 25th. @Employee A @Employee B @Employee C
> **Employee C** (Sep 23, thread): Klopt, dat stond ook in de payroll nieuwsbrief van september.
> **Team Lead** (Sep 29): Update: Finance postponed it — October stays on the 20th, the 25th applies from the November run. *(edited)*

**Flow**

1. Sep 22: the Team Lead announces the cut-off change from the October run.
2. Sep 22, thread: B: "does this also apply to invoices from umbrella companies?" Team Lead: "yes, same rule for umbrella companies."
3. Sep 23, thread: C confirms in Dutch, citing the September newsletter.
4. Sep 29: the Team Lead posts the update; the start moves to the November run. The message is edited once: the first version said "December run" by mistake.
5. Oct 15: the Manager: "Heads-up from Finance: for the December run the cut-off is exceptionally the 18th because of the holidays." A: "noted 👍".

**Expected memes**

| # | Statement | Speaker | Confirmers | Kind | Basis hints | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | From the November 2026 run, contractor invoices received after the 25th go into the next month's run (previously the 20th). | Team Lead | Employee C | rule | Team Lead: responsible · C: relayed, "Payroll newsletter, September 2026" | Latest statement wins and both messages are quoted (FR-MC5). C confirmed the 25th before the start date moved, and their request shows that quote. Same information as M1 #1 |
| 2 | The contractor invoice cut-off applies to invoices from umbrella companies too. | Team Lead | — | rule | Team Lead: responsible | Q&A in a thread: B asked, the Team Lead is the speaker |
| 3 | For the December 2026 run, the contractor invoice cut-off is exceptionally the 18th because of the holidays. | Manager | — | rule | Manager: relayed, "Finance" | A's "noted 👍" is not a confirmation |

**Traps**

- The original "from the October run" claim is superseded and must not be a separate meme.
- "noted", "👀", "thanks for the heads-up".
- Statements use the edited text ("November"), not the first version ("December").
- The Dutch reply must be understood as a confirmation with a source.

**Exercises:** FR-MC5, FR-MC3, FR-MC4, FR-MA11, FR-MO16.

### C3 · Freelance onboarding — cross-team

| | |
| --- | --- |
| Source | Teams group chat · 2026-10-05 → 2026-10-12 · 26 messages |
| Members | Senior Expert, Manager, Employee A, Employee B, Admin |

**Problem.** A cross-team effort to standardize onboarding of new freelancers: which checks to run, which documents to collect, where to store them. It includes a GDPR slip and a debate that ends without agreement.

**Conversation manner**

- Noisy: many people, parallel topics, off-topic jokes and GIFs. These are internet memes, not Peerpoint memes, and the agent must ignore them.
- Long structured messages from the Senior Expert next to one-liners from everyone else.
- A heated exchange between A and B that ends in "let's agree to disagree 😅".
- A GDPR incident: B pastes a fictional freelancer's full name, national register number and day rate, asking "is this ok?". The Admin asks to delete it and B deletes the message, but the export still contains it.
- Enthusiasm that is not agreement with content: "finally 🙌", "🔥".

Sample lines:

> **Senior Expert** (Oct 5): Proposal for the onboarding checklist for every new freelancer:
> 1. check the company number in the KBO/BCE public search
> 2. collect proof of affiliation with a social insurance fund
> 3. for foreign freelancers: Limosa L1 receipt and A1 certificate
> 4. signed contract without fixed working hours
>
> **Manager:** Approved — this is our checklist from now on. @Senior Expert can you add it to Peerpoint?
> **Employee A:** finally 🙌
> **Admin** (Oct 7): Please delete this — personal data never goes into chats. Onboarding documents are uploaded to the HR portal only.
> **Manager:** Correct, that's our GDPR policy.

**Flow**

1. Oct 5: the Senior Expert posts the checklist; the Manager approves it and asks for it to be added to Peerpoint; B reacts 👍; A writes "finally 🙌".
2. Oct 7: B pastes the personal data; the Admin states the rule; the Manager confirms; B deletes the message.
3. Oct 9: A and B debate whether a freelancer without their own website is a "real" freelancer; no consensus.
4. Throughout: GIFs, "happy Friday", a thread about the office parking.

**Expected memes**

| # | Statement | Speaker | Confirmers | Kind | Basis hints | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Onboarding checklist for a new freelancer: check the company number in the KBO/BCE public search; collect proof of affiliation with a social insurance fund; for foreign freelancers, get the Limosa L1 receipt and the A1 certificate; sign a contract without fixed working hours. | Senior Expert | Manager | how-to | Senior Expert: responsible | The Manager's "can you add it to Peerpoint?" is a task, not part of the meme; overlaps with M2 #1 and #3 |
| 2 | Onboarding documents are uploaded to the HR portal only and never shared in chats. | Admin | Manager | rule | Admin: relayed, "Internal GDPR policy" | Must quote only the Admin's and the Manager's messages, never B's pasted data |

**Traps**

- B's pasted personal data must never appear in a statement or quote, even though the message was deleted. Any meme touching it is `sensitive: true`.
- "finally 🙌", "🔥" and 👍 are enthusiasm or reactions, not confirmations.
- The website debate ends without a consensus.
- GIFs, jokes, parking talk.

**Exercises:** FR-MA10, BR-M5, FR-MA5, FR-MC6, FR-MA11.

---

## Coverage

| Behaviour under test | M1 | M2 | M3 | C1 | C2 | C3 |
| --- | --- | --- | --- | --- | --- | --- |
| Explicit confirmation → confirmer (FR-MA11) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Acknowledgement is not a confirmation | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Reaction is not a confirmation (FR-MC6) | | | | ✓ | ✓ | ✓ |
| Correction: latest statement wins (FR-MT5, FR-MC5) | ✓ | | ✓ | | ✓ | |
| One meme from several messages (FR-MC3) | | | | ✓ | | |
| Q&A: the answerer is the speaker (FR-MC4) | | | | ✓ | ✓ | |
| Speaker without a Peerpoint user is skipped (FR-MA4, FR-MT3) | | ✓ | | | | |
| Personal or customer data flagged (FR-MA10, BR-M5) | | ✓ | ✓ | | | ✓ |
| Opinions, debates, proposals skipped (FR-MA5) | | | ✓ | | | ✓ |
| Unanswered question skipped | ✓ | | | ✓ | | |
| Task assignments skipped | ✓ | ✓ | | | | ✓ |
| Relayed basis hint with source (FR-MO16) | ✓ | ✓ | | | ✓ | ✓ |
| Similar existing entry listed (FR-MA9) | | | ✓ | | | |
| Verifiers as speaker and confirmer (BR-M3) | ✓ | | ✓ | | | |
| Non-English message | | | | | ✓ | |
| Speech-recognition artifacts normalized | ✓ | ✓ | | | | |
| Same information in two sources | ✓ | ✓ | | | ✓ | ✓ |

## Files

```
backend/mock_data/sources/
├── index.json            # one row per source: type, title, date, files, participants
├── meetings/
│   ├── m1-payroll-be-weekly.vtt
│   ├── m2-dutch-freelancer-onsite.vtt
│   └── m3-q3-contractor-review.vtt
├── chats/
│   ├── c1-payroll-be-questions.json
│   ├── c2-contractor-announcements.json
│   └── c3-freelance-onboarding.json
└── expected/             # expected memes in the agent contract format, plus traps — test fixtures
    ├── m1-payroll-be-weekly.json
    ├── m2-dutch-freelancer-onsite.json
    ├── m3-q3-contractor-review.json
    ├── c1-payroll-be-questions.json
    ├── c2-contractor-announcements.json
    └── c3-freelance-onboarding.json
```

The file formats are described in the [mock data README](../../backend/mock_data/README.md#sources-for-the-ai-parser).

## Demo notes

- **M1 #2 and M3 #1:** if both the Team Lead and the Manager accept authorship, only the Senior Expert can verify the entry — a good moment to show BR-M3.
- **C3 #1 has no possible verifier with the current mock users.** If the Senior Expert publishes it, the entry has no team, and the only expert mapped to Payroll is its author. Either let the Manager publish it, so the Team Lead can verify, or add a second Payroll expert to `users.json`.
- **M3 #2 contradicts the seeded entry `PP-BE-FRE-00001`.** It is the natural lead-in to an outdated request on that entry. The current keyword similarity gives only 0.11 against the 60 % threshold, so the agent will not list that entry until similarity uses embeddings or a lower threshold for related entries.
