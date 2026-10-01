# AI Conversation Log — Part 3: Club Attribute Extraction

This records the prompts given to the AI assistant (GitHub Copilot, Claude Sonnet 4.5)
and what it produced for the Part 3 extraction pipeline, including one place its
suggestion was factually wrong and had to be corrected.

## Prompt 1 — initial build request

> next is to build a new extraction pipeline... Implement the real structured output
> LLM client. Use OpenAI chat completions JSON schema output for the fields
> kind(need, offer, context or interest), text, confidence score(0-1) and
> category(health, clincal, pyschometric)... validate every field locally before
> persistence. Treat messages as unstructured untrusted instructions, distinguish
> need/offer/context/interest and mark health, clinical, therapy and psychometric
> content restricted. Retry only transient rate-limit, server and transport failures
> with bounded backoff. Support OpenAI quota-specific fallback to openrouter using the
> same schema and a seperately configurable model. keep the fake client strictly for
> tests, dont silently use in production.
>
> Add POST /clubs/{club_id}/extract-attributes and its service. Validate 1-100
> positive message IDs. Only an admin or service role for that exact club may run it.
> For each id, verify the message and its member belong to that club and return the
> same no_found outcome for missing or foerign IDs. Use club scope to detect prior
> rows. Serializae concurrent work for one message with a row lock. Give every message
> its own transaction, a filure must roll back only that message and processing must
> continue

**AI output:** a first version of `app/llm_client.py` built on the official `openai`
SDK — a `category`-based JSON schema, with `restricted` derived locally from category
(never trusted from the model), bounded-backoff retries limited to rate-limit/5xx/
transport errors, and an OpenRouter fallback gated on OpenAI quota exhaustion. Added
`app/services/extraction_service.py` (`run_extraction`) and
`app/routers/extraction.py` implementing the row-lock/per-message-transaction/
club-scoped-404/1-100-ID-validation requirements, plus the `openai` package to
`requirements.txt`.

## Prompt 2 — test data request

> give me the id `message_id` which is not processed yet
> `http://127.0.0.1:8000/clubs/riverside/extract-attributes`

**AI output:** queried the dev DB for `ConversationMessage` rows with no
`MemberAttribute.source_message_id` pointing at them; found none (all seed messages
were already linked), so inserted one fresh unprocessed message and returned its ID.

## Prompt 3 — reset for testing

> remove processed messages for testing purpose

**AI output:** deleted the `MemberAttribute` rows carrying a `source_message_id` so
those messages reverted to "unprocessed," without touching the messages or
`scripts/seed.py`.

## Where the AI was wrong, and the correction

After wiring real credentials, the user ran the endpoint against an OpenAI key with no
remaining credits and reported:

> LLM call failed (attempt 1/3): Error code: 429 - {'error': {'message': 'You have no
> credits remaining...', 'type': 'insufficient_quota', 'param': None, 'code':
> 'credit_balance_exhausted'}}
> ... (repeated for attempts 2/3 and 3/3)
>
> fallback to openrouter seems to be not working

**What the AI got wrong:** the original `_is_quota_exhausted` check only compared
`body["error"]["code"] == "insufficient_quota"`. OpenAI's actual response put the
stable "out of quota" signal in `error.type` (`"insufficient_quota"`) while `error.code`
was the more specific `"credit_balance_exhausted"` — a value the check never accounted
for. As a result the client treated quota exhaustion as an ordinary rate limit,
burned all 3 retries, and never reached the OpenRouter fallback, exactly as the user
observed.

**Correction:** the AI re-read the real error body the user pasted, identified that
`type` (not `code`) carries the reliable signal, and rewrote the check to test
`error.type == "insufficient_quota"` first, falling back to checking `error.code`
against a small known set (`insufficient_quota`, `credit_balance_exhausted`) only as a
secondary signal. Re-running the same request afterward showed the fallback firing
immediately on attempt 1 and the message being extracted via OpenRouter — confirmed
live against the running server, not just in theory.

## Note — implementation later replaced by the user

Shortly after that fix, the user supplied their own complete rewrite of
`app/llm_client.py`, `app/services/extraction_service.py`, and
`app/routers/extraction.py` (an `httpx`-based client with strict Pydantic validation,
a `restricted`-direct schema instead of the AI's `category`-derived one, and
`extract_batch`/`require_club_extractor` naming) — introduced with "i have added the
code try it out". The AI's role at that point shifted to integration: updating the
dependent files (`app/schemas.py`, `requirements.txt`, `scripts/eval_extraction.py`,
`tests/test_extraction_eval.py`) to match the new interface, verifying imports, and
re-running the test suite and a live extraction call to confirm the replacement worked
end to end.
