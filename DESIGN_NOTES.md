# Design Notes

## Part 3 — Club Attribute Extraction

### Key logic

- **Authorization is club-scoped, not just role-scoped.** `require_club_extractor`
  (`app/routers/extraction.py`) requires both an elevated role and a match on the path
  club: `member.role not in {"admin", "service"} or member.club_id != club_id` raises
  403. A club-A admin cannot run extraction against club B.
- **Request validation rejects bad input before any DB/LLM work.** `ExtractAttributesIn`
  constrains `message_ids` to `Annotated[int, Field(strict=True, gt=0)]` with
  `Field(min_length=1, max_length=100)` — 1 to 100 strictly-positive integers, enforced
  by Pydantic at the API boundary.
- **Duplicate IDs in one request are deduplicated and processed once.**
  `for message_id in dict.fromkeys(message_ids):` in `extract_batch` preserves order
  while dropping repeats, so a client retry-with-duplicates in a single call can't
  double-process a message.
- **Row locking serializes concurrent extraction of the same message.** The message
  fetch uses `.with_for_update(of=ConversationMessage)`, taking a row lock for the
  duration of that message's transaction so two concurrent requests for the same
  `message_id` can't both pass the idempotency check and both write attributes.
- **Each message gets its own transaction; one failure doesn't affect the rest.**
  `extract_batch` calls `db.commit()`/`db.rollback()` per iteration of the loop, inside
  a `try`/`except Exception` per message — a failure on one `message_id` rolls back
  only that message's work and the loop continues to the next ID with `status: "failed"`.
- **Validation before persistence is independent of which LLM produced the data.**
  `extract_message_text` always runs the model's output through
  `validate_attributes(...)` (strict Pydantic validation plus same-kind/text
  deduplication) before any `MemberAttribute` row is built, regardless of whether the
  real `OpenAILLMClient` or `FakeLLMClient` supplied it.
- **Retry strategy only covers transient failures, not quota exhaustion.**
  `OpenAILLMClient` retries 429/5xx/transport errors with bounded backoff
  (`llm_max_attempts`, `llm_retry_base_seconds`/`llm_retry_max_seconds`), but
  `_is_quota_error` detects out-of-quota responses and routes straight to the
  OpenRouter fallback instead of burning retries on a condition retrying can't fix.

### Idempotency: what decides a message is already processed

`extract_batch` (`app/services/extraction_service.py`) treats a message as already
processed purely by the existence of rows pointing back to it, not by any separate
"processed" flag. The literal check, scoped to the calling club:

```python
existing_ids = db.scalars(
    select(MemberAttribute.id).where(
        MemberAttribute.source_message_id == message.id,
        MemberAttribute.club_id == club_id,
    )
).all()
if existing_ids:
    db.commit()
    results.append(
        {"message_id": message_id, "status": "skipped", "attribute_count": len(existing_ids)}
    )
    continue
```

So the idempotency key is `MemberAttribute.source_message_id == message.id` — any
pre-existing attribute row sourced from this message, within this club, short-circuits
re-extraction with `status: "skipped"`. This is what makes calling the endpoint twice
for the same message safe (idempotency), independent of the LLM call's own retry
strategy (bounded retries on transient rate-limit/5xx/transport failures inside
`OpenAILLMClient`), which only governs getting one successful response, not whether
that response gets persisted twice.

### Restricted attributes kept out of matching

The enforcement point is the introduction reason-generation query in
`app/routers/introductions.py`, not the extraction pipeline itself (extraction persists
whatever `restricted` value the model assigns; it doesn't filter anything out). The
actual check:

```python
MemberAttribute.restricted.is_(False),
```

applied as a `.filter()` clause alongside the member-ID and club-ID filters before the
attribute text is ever read into `a_text`/`b_text`. A restricted attribute is simply
never selected out of the database for that endpoint's response, rather than being
redacted after the fact. Note this filter is local to that one query — it is not a
blanket guarantee across every attribute consumer in the codebase.

### Eval threshold

`scripts/eval_extraction.py` exposes `--threshold` (default `1.0`) for interactive runs
right after a prompt change, so a developer sees 100% pass/fail at a glance. The
automated `tests/test_extraction_eval.py` instead asserts `passed / total >= 0.75`. The
gap between the two exists because the retry strategy inside `OpenAILLMClient` only
retries failed HTTP calls — it cannot make a successful call deterministic. Real model
output still varies run to run, so a committed regression test needs a tolerance below
100% to avoid flaking on acceptable variance while still catching a real regression in
extraction quality.

### Schema limitation

An unprocessed message and a successfully processed message that yielded zero
attributes (`status: "empty"`) are indistinguishable under this schema: both have no
`MemberAttribute` row with that `source_message_id`, so the idempotency check above
will re-run extraction on either one the next time it's requested.
