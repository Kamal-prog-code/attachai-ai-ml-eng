# Prioritized Code Review

Findings are ranked by business impact and limited to behavior confirmed in the inspected code. No request/response output is quoted or inferred; the payment before-trace is not available in the current workspace context, so payment findings below describe code paths, not claimed trace observations.

## 1. Cross-club member attributes are exposed

**File and line:** `app/routers/introductions.py:19-25`  
**Category:** Data isolation / sensitive data exposure  
**Severity:** Critical

The endpoint authenticates the caller but queries attributes using only the two URL-supplied member IDs, without verifying either target belongs to the caller's club. It returns every selected attribute, including rows marked restricted, so a caller can access other clubs' member profile data if the IDs are known.

**Recommended fix:** Load and authorize both target members against `member.club_id` before querying attributes, return a non-disclosing error for missing or out-of-club targets, and exclude restricted attributes from the response.

## 2. Knowledge search is not tenant-scoped

**File and line:** `app/routers/knowledge.py:28-36`  
**Category:** Data isolation / sensitive data exposure  
**Severity:** Critical

The endpoint checks that the path club matches the caller, but the similarity query has no `KnowledgeChunk.club_id` filter and returns chunk bodies from the global top five. A caller's search can therefore disclose another club's knowledge content when its chunks rank highly.

**Recommended fix:** Add a `KnowledgeChunk.club_id == member.club_id` predicate to the database query before ordering and limiting results, while retaining the existing path authorization check.

## 3. Booking payment amount is controlled by the request

**File and line:** `app/routers/bookings.py:28-40`  
**Category:** Payment integrity  
**Severity:** High

The endpoint charges `payload.amount_cents` and marks the booking confirmed after any successful charge, without checking that the amount equals the booking's stored `amount_cents`. This allows the payment amount and confirmed booking amount to diverge.

**Recommended fix:** Use the persisted booking amount as the charge amount, or reject any request whose amount differs; also validate the booking's allowed payment state before charging.

## 4. Payment retries can repeat a charge

**File and line:** `app/routers/bookings.py:28-41`; `app/services/session_flow.py:31-52`  
**Category:** Payment reliability / duplicate charge  
**Severity:** High

The booking route does not prevent charging an already-confirmed booking and persists no attempt when the provider raises an ambiguous timeout. In the session flow, the charge occurs before persistence and there is no prior-attempt check, so retrying after a crash between those operations can charge again; the existing `PaymentAttempt.idempotency_key` is unused.

**Recommended fix:** Make each booking/session payment operation idempotent with a stable key enforced by the provider and database, persist an attempt before or atomically around the external call, and make retries reconcile the existing attempt instead of issuing another charge.

## 5. Restricted attributes influence candidate ranking

**File and line:** `app/services/matching_service.py:9-12, 32-40`; `app/services/embedding_pipeline.py:8-10`  
**Category:** Data sensitivity / indirect disclosure  
**Severity:** High

Candidate selection is scoped to the caller's club, but the shared profile-text builder includes attributes regardless of `restricted`, and that text is used for both live query embeddings and stored candidate embeddings. Restricted information can therefore change the returned candidate identities and scores even though the endpoint does not return the raw attribute text.

**Recommended fix:** Exclude restricted attributes in the shared profile-text builder, regenerate stored embeddings under that policy, and verify both caller and candidate embeddings use only permitted attributes.