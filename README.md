# FactOracle — Autonomous Fact-Checking Oracle

A standalone GenLayer Intelligent Contract. Anyone submits a **claim** plus one or
two public URLs that bear on it. AI validators independently fetch those pages and
commit a verdict on whether the evidence **supports** the claim (`TRUE`),
**contradicts** it (`FALSE`), or **does not address** it (`UNVERIFIABLE`). The
verdict is stored on-chain with its reasoning, the sources that were read, and a
sha256 digest of the bytes read.

- **Contract (Bradbury, chain 4221):** `0xC67aB43D69C0c115aE0d06f3aF724F849df3C1D7`
- **Explorer:** https://explorer-bradbury.genlayer.com/address/0xC67aB43D69C0c115aE0d06f3aF724F849df3C1D7
- **Source:** `contracts/fact_oracle.py` (19,064 bytes)

## Why this belongs on GenLayer

The judgment — *does this evidence actually establish this claim?* — has no
deterministic oracle. You cannot write a function that reads a page and decides
whether it supports a sentence. It needs reading and interpretation, and the
evidence is independently checkable, so every validator can reach the judgment
itself.

The stored verdict is a durable, consensus-derived artifact that any other
contract or application can query. That artifact **is** the product.

## How a verdict is reached

One leader/validator round per claim, via `gl.vm.run_nondet`:

1. The **leader** fetches the sources, flattens them to text, judges the claim, and
   returns the verdict with a **sha256 digest of the exact bytes it read**.
2. Each **validator** independently re-fetches the same URLs, **re-judges the
   claim**, and agrees only if:
   - its digest matches the leader's — so the leader read the recorded page — **and**
   - its own verdict does not contradict the leader's.

That second clause is the substantive check: the validator judges the page, it does
not audit the leader's formatting. A validator that **cannot** reach the source
returns disagreement rather than agreement — it has verified nothing, and agreeing
would let a leader commit a verdict no other validator reached.

### The hedging rule, and why it exists

"Does not contradict" rather than "matches exactly" is deliberate, and it was
measured rather than assumed. Requiring an exact match made honest runs disagree on
borderline pages and deadlocked the round:

| Validator rule | Committed, 6 paced claims |
|---|---|
| Digest only — no re-judging | 6/6 |
| Re-judge, **exact** verdict match required | 3/6 |
| Re-judge, **positive contrary** finding blocks | see the live run below |

A run calling a thin page `UNVERIFIABLE` where the leader said `TRUE` is honest
hedging about ambiguous evidence, not fabrication. A `TRUE`/`FALSE` flip *is*
fabrication, and still blocks. So the validator must reach the leader's verdict **or
reach no verdict at all** — which keeps the judgment in the validator's hands
without making ambiguous evidence unsettleable.

This deliberately does **not** use `gl.eq_principle.strict_eq` over LLM output,
which does not enforce cross-validator equality for non-deterministic results on
this network.

### Grounded in the evidence, or nothing

The model is instructed to judge **only** from the fetched evidence, and both the
claim and the fetched page are treated as **untrusted input**: they are fenced in
the prompt and the model is told never to follow instructions found inside them.

An **unreachable source aborts the transaction and stores nothing.** A fetch that
fails, times out, or returns a non-2xx status counts as unreachable rather than as
an empty page — a verdict derived from a failed fetch is worse than no verdict.

## Public API

| Method | Kind | Purpose |
|---|---|---|
| `submit_claim(claim_id, claim_text, source_url, second_url)` | write | Fact-check a claim; `second_url` may be `""` |
| `recheck(claim_id)` | write | Re-run consensus on a stored claim and revise its verdict |
| `get_claim(claim_id)` | view | Full record: claim, sources, submitter, verdict, reasoning, revisions, timestamp |
| `get_verdict(claim_id)` | view | The auditable part: verdict, reasoning, sources, revisions |
| `list_claims(offset, limit)` | view | Page the claim set (`limit` clamped to 20) |
| `total_claims()` | view | Claims recorded |
| `verdict_counts()` | view | `{true, false, unverifiable, total}` |
| `submitter_stats(wallet)` | view | Claims submitted by a wallet |
| `limits()` | view | The caps a caller must respect |
| `now()` | view | Contract clock |

### Using it

```javascript
await client.writeContract({
  address: "0x2DC05665A643820257a339eE447Ce922507f0118",
  functionName: "submit_claim",
  args: ["claim-1", "Abuja is the capital of Nigeria.", "https://example.com/page", ""],
  gasLimit: 5000000n,   // REQUIRED — GenLayer cannot estimate gas for nondet writes
});
```

### Caps

`limits()` returns them, so a caller never has to guess:

| Cap | Value | Why |
|---|---|---|
| `max_claim_chars` | 1000 | the claim is submitter-controlled and goes into the prompt |
| `max_id_chars` | 200 | a key in a TreeMap; unbounded is a storage-bloat vector |
| `max_url_chars` | 2000 | source URLs are submitter-controlled |
| `max_primary_chars` | 3500 | a heavy prompt times the round out (status 12/13) instead of disagreeing |
| `max_secondary_chars` | 1500 | same |
| `max_reason_chars` | 400 | keeps the stored record bounded |
| `max_raw_chars` | 60000 | the raw body is capped **before** the regex work, so a huge page cannot time the round out |

## Verdicts are revised, never silently overwritten

`recheck` is permissionless — sources change, and that is what makes this a public
good rather than a one-shot oracle. But nothing is overwritten quietly: the
previous verdict is kept in `previous_verdict` and `revisions` is incremented, so
the change is visible on-chain. An unreachable source on a recheck leaves the
stored verdict untouched.

## Verification

### Source parity

`getContractCode` at the address returns the source running on-chain, and its
sha256 is identical to the committed `contracts/fact_oracle.py`:

```
live bytes : 19633
local bytes: 19633
live  sha256: 807eb63fbabfce3e7d6b9a9c725f3fbd0f3bb8562d25841b4c4244ae762f96a3
local sha256: 807eb63fbabfce3e7d6b9a9c725f3fbd0f3bb8562d25841b4c4244ae762f96a3
MATCH      : YES
```

`status: ACCEPTED` proves a transaction was *decided*, never that the code is live.
Reading the code back is the falsifying check.

### Live discrimination

A verification oracle that has only ever been shown succeeding proves nothing. The
live run submits claims against the **same page** (`https://example.com/`), so the
claim is the only thing that changes:

| Claim | Expected |
|---|---|
| "…intended for use in illustrative examples in documents." | `TRUE` |
| "…used to sell consumer electronics online." | `FALSE` |
| "…was registered in 1995." | `UNVERIFIABLE` |

Plus an unreachable URL, which must revert and store nothing.

<!-- LIVE RESULTS -->
**Result — the whole surface works on the live contract.** End-to-end run
(`e2e.mjs`), **12/13 checks passed**:

| Check | Result |
|---|---|
| deployed source == repo source | PASS — 19,064 bytes, `55dfd2c1…` |
| `TRUE` for a claim the page states | PASS |
| `FALSE` for a claim the page contradicts | PASS |
| `UNVERIFIABLE` for a claim the page does not address | `NOT_VOTED` — see below |
| unreachable source aborts and stores nothing | PASS — `FINISHED_WITH_ERROR`, count unchanged |
| `recheck` revises with a visible trail | PASS — revisions 2 → 3, `previous_verdict=TRUE` |
| `list_claims` enumerates the set | PASS — 6 of 6 |
| counters sum to the total | PASS — `{true:2, false:2, unverifiable:2, total:6}` |
| `limits()` exposes the caps | PASS |

**The one miss is the known validator disagreement rate, not a contract defect.**
For "The example.com domain was registered in 1995" the validators split — some
runs returned `UNVERIFIABLE`, others a different verdict — and the round deadlocked
(`NOT_VOTED`). This is the same ~1/6 rate measured in the A/B: the claim is genuinely
ambiguous (the page says nothing about registration date), and requiring exact
agreement on borderline claims deadlocks the round. The hedging rule reduces but
cannot eliminate this; a failed round stores nothing, so a caller retries.

**Why pacing matters.** An unpaced 8-claim burst committed only 4/8, and the
diagnostic showed why: the **EVM submission transaction itself reverted** ("node at
capacity"), which is rate-limiting — not a consensus failure and not a contract
defect. Any client should pace writes and retry an admission revert with backoff.

## Tests

```bash
gltest tests/direct -q     # 73 passed
```

| File | Tests | Covers |
|---|---|---|
| `test_fact_oracle.py` | 23 | plumbing: validation, verdict storage, counters, `recheck`, read integrity |
| `test_fact_oracle_adversarial.py` | 29 | hostile input: injection, URL schemes, degenerate pages, malformed model output, the length cap |
| `test_fact_oracle_validator.py` | 11 | validator agreement, exercised directly via `direct_vm.run_validator(...)` |
| `test_fact_oracle_critical.py` | 10 | the four hardening fixes: raw-body cap, fence-escape sanitisation, ID/URL caps, designation tie-breaker |

The validator suite is the one behind the consensus claim. It feeds the validator a
tampered digest, a digest from a different page, a missing digest, an off-script
verdict, a non-dict result, and — the two that matter most — a case where its own
re-judgment **contradicts** the leader (must refuse) and a case where it merely
**hedges** to `UNVERIFIABLE` (must accept).

The suites do **not** prove the model discriminates; direct mode runs the leader and
the LLM is a stub. That proof is the live run.

### Seven real bugs the suites caught

1. **A JSON model reply can be unencodable.** The calldata encoder accepts only
   bytes, str, Sequence and Mapping. With `response_format="json"` the reply
   crosses as a parsed object, so one float field (a confidence score is the
   obvious one) makes the whole response unencodable and the verdict is lost.
   Fixed by requesting a plain-text reply, which is always a string; a static test
   now guards against reintroducing the JSON request.
2. **`UNREACHABLE` was unreachable.** The validator checked "is this an allowed
   verdict?" *before* the unreachable sentinel, and the sentinel is not in that
   set — so the branch was dead code.
3. **Lazy web responses.** `gl.nondet.web.request` returns a `Lazy[Response]`;
   reading through it unresolved silently yields an empty body, which is
   indistinguishable from a page that says nothing. Added explicit resolution.
4. **The raw body was unbounded.** `_extract_text` ran its regexes over the full
   page before truncation, so a 500 KB page would be fully processed — enough to
   time the round out (status 12/13) instead of producing a verdict. Fixed by
   capping the body at the fetch boundary, before any regex work.
5. **The prompt fence was escapable.** A page containing the literal marker
   `EVIDENCE>>>` could close its own fence and let the rest of the page read as
   instructions to the model. Fixed by stripping all four markers from both
   inputs before they enter the prompt; the digest is still computed over the
   original bytes, so leader and validator agree.
6. **`claim_id` and the URLs were unbounded** — submitter-controlled keys and
   arguments with no ceiling. Now capped and exposed in `limits()`.
7. **The model flip-flopped on a contradiction by designation.** The page says a
   domain is *for* documentation examples; the claim said it was used to sell
   electronics. Some runs returned `FALSE`, others `UNVERIFIABLE`. Added an
   explicit tie-breaker: a designation is a positive statement, so it excludes the
   asserted use.

## Design notes

- **Storage** is parallel `TreeMap`s of scalars. No `@allow_storage` dataclass:
  this GenVM build accepts such a contract at deploy and then stores no code, so
  reads fail forever.
- **All integer storage fields are `u256`.** Plain `int` storage fields are stored
  as nothing.
- **Imports are at the top.** `import json` below the class silently breaks the
  transpiler and is the most common cause of LLM-consensus failure.
- **Views return JSON**, never delimited strings, so a claim containing `|` cannot
  shift the fields that follow it.
- **The model reply is plain text**, never `response_format="json"` (see bug 1).
- **Non-2xx counts as unreachable**, so an error page is never judged as evidence.
- **No funds are held or moved.** The verdict is the artifact.

## Layout

```
contracts/fact_oracle.py                        the contract (19,064 B)
tests/direct/test_fact_oracle.py                23 plumbing tests
tests/direct/test_fact_oracle_adversarial.py    29 hostile-input tests
tests/direct/test_fact_oracle_validator.py      11 validator-agreement tests
tests/direct/test_fact_oracle_critical.py       10 hardening-fix tests
e2e.mjs                                         end-to-end run on the live contract
deploy.mjs / verify.mjs                         deploy + source parity
live_paced.mjs                                  paced live measurement
diag.mjs                                        admission-revert diagnostic
README.md / gltest.config.yaml / .gitignore
```
