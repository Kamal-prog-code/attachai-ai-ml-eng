# Terminal Log

Captured in order: setup, baseline test run, a real bug episode (before/after),
the extraction pipeline demo, the eval run, the confidence-threshold ("4a") demo,
and a final full test run with the opt-in eval tests actually executing.

## 1. Setup output

```
$ ./.venv/bin/python --version
Python 3.11.9

$ ./.venv/bin/python -m pip install -r requirements.txt
...
Requirement already satisfied: httptools>=0.5.0 in ./.venv/lib/python3.11/site-packages (0.8.0)
Requirement already satisfied: pyyaml>=5.1 in ./.venv/lib/python3.11/site-packages (6.0.3)
Requirement already satisfied: uvloop!=0.15.0,!=0.15.1,>=0.14.0 in ./.venv/lib/python3.11/site-packages (0.23.0)
Requirement already satisfied: watchfiles>=0.13 in ./.venv/lib/python3.11/site-packages (1.3.0)
Requirement already satisfied: websockets>=10.4 in ./.venv/lib/python3.11/site-packages (17.1)
Requirement already satisfied: annotated-types>=0.6.0 in ./.venv/lib/python3.11/site-packages (0.8.0)
Requirement already satisfied: pydantic-core==2.46.5 in ./.venv/lib/python3.11/site-packages (2.46.5)
Requirement already satisfied: typing-inspection>=0.4.2 in ./.venv/lib/python3.11/site-packages (0.4.4)

$ ./.venv/bin/python -m pip check
No broken requirements found.
```

## 2. Initial test run

```
$ DATABASE_URL="postgresql+psycopg://kindred:kindred@localhost:5432/kindred_test" ./.venv/bin/python -m pytest -q
.ss................                                                      [100%]
17 passed, 2 skipped, 1 warning in 0.41s
```

The 2 skips are `tests/test_extraction_eval.py`, gated behind `RUN_EXTRACTION_EVAL=1`
(see section 8 for them actually running).

## 3. Bug trace (before)

Reused verbatim from this session's transcript — the bug no longer exists in the
current, rewritten `app/llm_client.py`, so it cannot be safely reproduced without
reverting already-shipped code. This is the real failure observed when OpenAI
returned quota exhaustion and the quota-detection check only matched
`error.code == "insufficient_quota"`, missing the actual `credit_balance_exhausted`
code OpenAI sent:

```
LLM call failed (attempt 1/3): Error code: 429 - {'error': {'message': 'You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organization/billing/.', 'type': 'insufficient_quota', 'param': None, 'code': 'credit_balance_exhausted'}}
LLM call failed (attempt 2/3): Error code: 429 - {'error': {'message': 'You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organization/billing/.', 'type': 'insufficient_quota', 'param': None, 'code': 'credit_balance_exhausted'}}
LLM call failed (attempt 3/3): Error code: 429 - {'error': {'message': 'You have no credits remaining. Add credits to continue using the API at https://platform.openai.com/settings/organization/billing/.', 'type': 'insufficient_quota', 'param': None, 'code': 'credit_balance_exhausted'}}
```

Direct reproduction via the client, same session, showing it exhausted all retries
and never reached the OpenRouter fallback:

```
openai.RateLimitError: Error code: 429 - {'error': {'message': 'You have no credits remaining...', 'type': 'insufficient_quota', 'param': None, 'code': 'credit_balance_exhausted'}}
...
app.llm_client.TransientLLMError: LLM request failed after 3 retries
```

## 4. Fix trace (after)

Also reused verbatim: once quota detection checked `error.type == "insufficient_quota"`
(with `code` as a secondary signal), the same exhausted-quota condition fell over to
OpenRouter on the first attempt instead of retrying 3 times:

```
$ curl -s -X POST http://127.0.0.1:8000/clubs/riverside/extract-attributes \
  -H "X-Member-Token: riverside-admin" -H "Content-Type: application/json" \
  -d '{"message_ids": [10]}' | python3 -m json.tool
{
    "results": [
        {
            "message_id": 10,
            "status": "extracted",
            "attribute_count": 1
        }
    ]
}
```

## 5. Extraction demo (first call + idempotent second call)

Fresh message (id 15) created directly against the dev DB, then extracted twice:

```
$ curl -s -X POST http://127.0.0.1:8000/clubs/riverside/extract-attributes \
  -H "X-Member-Token: riverside-admin" -H "Content-Type: application/json" \
  -d '{"message_ids": [15]}' | python3 -m json.tool
--- first call ---
{
    "results": [
        {
            "message_id": 15,
            "status": "extracted",
            "attribute_count": 2
        }
    ]
}
--- second call (idempotent) ---
{
    "results": [
        {
            "message_id": 15,
            "status": "skipped",
            "attribute_count": 2
        }
    ]
}
```

The second call finds existing `MemberAttribute` rows via `source_message_id` and
skips re-extraction instead of duplicating attributes (see `DESIGN_NOTES.md`).

## 6. Eval output

```
$ ./.venv/bin/python -m scripts.eval_extraction --threshold 1.0
[PASS] "I'm trying to raise a Series A in the next few months, would" kind_ok=True keywords_ok=True restricted_ok=True
[PASS] "I've led fundraising for three Series A rounds as an operato" kind_ok=True keywords_ok=True restricted_ok=True
[PASS] "I've been in therapy for the last year and it's helped a lot" kind_ok=True keywords_ok=True restricted_ok=True
[PASS] 'Does anyone want to join a weekly running club on Tuesday mo' kind_ok=True keywords_ok=True restricted_ok=True

4/4 passed (100%)
```

## 7. 4a demo — confidence-threshold filtering on introductions

Two demo members (ids 16, 17) in `riverside`: member 16 has a `need` attribute at
confidence 0.9; member 17 has an `offer` attribute at confidence 0.4, below the
`introduction_min_confidence` default of 0.7.

```
$ curl -s "http://127.0.0.1:8000/introductions/16/17?reason=business" \
  -H "X-Member-Token: demo-tok-a" | python3 -m json.tool
{
    "reason_text": "Because needs a CFO and  \u2014 a good business match."
}
```

The 0.9-confidence text ("needs a CFO") appears; the 0.4-confidence text ("maybe
offers CFO services") is filtered out by `MemberAttribute.confidence >=
settings.introduction_min_confidence` in `app/routers/introductions.py`, leaving
member B's side of the sentence empty.

## 8. Final test run (pytest actually executing the eval tests)

```
$ RUN_EXTRACTION_EVAL=1 DATABASE_URL="postgresql+psycopg://kindred:kindred@localhost:5432/kindred_test" ./.venv/bin/python -m pytest -v
tests/test_bookings.py::test_confirm_payment_succeeds PASSED             [  5%]
tests/test_extraction_eval.py::test_golden_set_meets_accuracy_threshold PASSED [ 10%]
tests/test_extraction_eval.py::test_golden_set_never_misses_restricted_content PASSED [ 15%]
tests/test_introductions.py::test_generate_reason_includes_attributes PASSED [ 21%]
tests/test_introductions.py::test_generate_reason_excludes_low_confidence_attributes PASSED [ 26%]
tests/test_introductions.py::test_generate_reason_rejects_foreign_target_as_member_a PASSED [ 31%]
tests/test_introductions.py::test_generate_reason_rejects_foreign_target_as_member_b PASSED [ 36%]
tests/test_introductions.py::test_generate_reason_rejects_missing_target PASSED [ 42%]
tests/test_introductions.py::test_generate_reason_admin_caller_same_club PASSED [ 47%]
tests/test_introductions.py::test_generate_reason_admin_caller_rejects_foreign_target PASSED [ 52%]
tests/test_introductions.py::test_generate_reason_excludes_restricted_attributes PASSED [ 57%]
tests/test_introductions.py::test_generate_reason_excludes_attribute_with_misassigned_club PASSED [ 63%]
tests/test_knowledge.py::test_query_own_club_returns_results PASSED      [ 68%]
tests/test_knowledge.py::test_query_rejects_non_member PASSED            [ 73%]
tests/test_knowledge.py::test_query_excludes_other_clubs_chunks_even_when_closer_match PASSED [ 78%]
tests/test_knowledge.py::test_query_returns_multiple_same_club_results_only PASSED [ 84%]
tests/test_matching.py::test_rank_candidates_returns_sorted_list PASSED  [ 89%]
tests/test_sessions.py::test_session_books_end_to_end PASSED             [ 94%]
tests/test_sessions.py::test_refund_dispute_escalates PASSED             [100%]

19 passed, 1 warning in 7.47s
```
