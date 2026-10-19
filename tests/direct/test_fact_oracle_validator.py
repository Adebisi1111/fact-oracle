"""Validator-side tests for FactOracle.

Direct mode runs the leader and captures the validator, so the agreement rule
can be exercised directly through `direct_vm.run_validator(...)`. These are the
tests behind the security claim: the validator must accept a leader result only
when the digest it recorded matches what the validator reads itself.

What is deliberately NOT claimed here: the validator does not re-judge the
claim. It verifies the READ, not the wording. Re-running an LLM verdict over
live web content is non-deterministic, and requiring two independent judgments
to match makes an ambiguous page deadlock instead of committing UNVERIFIABLE.
The verdict is the leader's; the source and digest are recorded so the decision
can be re-run and audited afterwards.
"""

import hashlib
import json
import re

URL = "https://example.com/facts"
PAGE = "<html><body><p>Abuja is the capital city of Nigeria.</p></body></html>"
CLAIM = "Abuja is the capital of Nigeria."


def _source(vm, body=PAGE, status=200):
    vm.mock_web(r".*example\.com/facts.*", {"status": status, "body": body})


def _judge_for(vm, text, verdict, reasoning="Because the page says so."):
    vm.mock_llm(r"<<<CLAIM\n" + re.escape(text),
                json.dumps({"verdict": verdict, "reasoning": reasoning}))


def _submit(vm, c, alice):
    vm.sender = alice
    return c.submit_claim("c1", CLAIM, URL, "")


def test_validator_accepts_the_leaders_result(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, CLAIM, "TRUE")
    assert _submit(direct_vm, c, direct_alice) == "TRUE"
    assert direct_vm.run_validator() is True


def test_validator_rejects_a_tampered_digest(direct_vm, direct_deploy, direct_alice):
    """The core property: a verdict for a page the leader never read is refused."""
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, CLAIM, "TRUE")
    _submit(direct_vm, c, direct_alice)

    stored, _, _ = direct_vm._captured_validators[-1]
    tampered = dict(stored)
    tampered["digest"] = "0" * 64
    assert direct_vm.run_validator(leader_result=tampered) is False


def test_validator_rejects_a_result_with_no_digest(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, CLAIM, "TRUE")
    _submit(direct_vm, c, direct_alice)
    assert direct_vm.run_validator(leader_result={"verdict": "TRUE"}) is False


def test_validator_rejects_a_digest_from_a_different_page(
    direct_vm, direct_deploy, direct_alice
):
    """A digest of other bytes must not pass for this source."""
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, CLAIM, "TRUE")
    _submit(direct_vm, c, direct_alice)

    other = hashlib.sha256(b"a completely different page").hexdigest()
    assert direct_vm.run_validator(
        leader_result={"verdict": "TRUE", "reasoning": "", "digest": other}
    ) is False


def test_validator_rejects_an_off_script_verdict(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, CLAIM, "TRUE")
    _submit(direct_vm, c, direct_alice)

    stored, _, _ = direct_vm._captured_validators[-1]
    assert direct_vm.run_validator(
        leader_result={"verdict": "PROBABLY", "digest": stored["digest"]}
    ) is False


def test_validator_rejects_a_non_dict_result(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, CLAIM, "TRUE")
    _submit(direct_vm, c, direct_alice)
    assert direct_vm.run_validator(leader_result="TRUE") is False


def test_validator_agrees_when_the_leader_reports_unreachable(
    direct_vm, direct_deploy, direct_alice
):
    """A failed fetch is a legitimate outcome, not something to dispute."""
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _judge_for(direct_vm, CLAIM, "TRUE")   # no web mock: the leader cannot fetch

    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("unreachable"):
        c.submit_claim("c1", CLAIM, URL, "")
    assert direct_vm.run_validator() is True


def test_validator_disagrees_when_it_cannot_reach_the_source_itself(
    direct_vm, direct_deploy, direct_alice
):
    """A validator that cannot fetch has verified nothing, so it must not agree.

    Agreeing here would let a leader commit a verdict no other validator ever
    reached. Disagreement makes the round retry instead.
    """
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, CLAIM, "TRUE")
    _submit(direct_vm, c, direct_alice)

    direct_vm.clear_mocks()   # the validator's own fetch now fails
    _judge_for(direct_vm, CLAIM, "TRUE")
    assert direct_vm.run_validator() is False


def test_validator_disagrees_when_its_own_judgment_differs(
    direct_vm, direct_deploy, direct_alice
):
    """The substantive check: the validator must reach the leader's verdict itself.

    Same page, same digest — only the judgment differs. This is the test that
    distinguishes a validator that judges from one that merely checks formatting.
    """
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, CLAIM, "TRUE")
    _submit(direct_vm, c, direct_alice)

    # The validator re-reads the same page but judges it differently.
    direct_vm.clear_mocks()
    _source(direct_vm)
    _judge_for(direct_vm, CLAIM, "FALSE")
    assert direct_vm.run_validator() is False


def test_validator_agrees_when_it_hedges_to_unverifiable(
    direct_vm, direct_deploy, direct_alice
):
    """Hedging is not a contrary finding.

    The leader said TRUE; the validator, re-reading the same page, calls it
    UNVERIFIABLE. That is honest disagreement about thin evidence rather than
    fabrication, and blocking on it deadlocked the round — measured 3/6 commits
    against 6/6. A positive contrary verdict still blocks (test above).
    """
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, CLAIM, "TRUE")
    _submit(direct_vm, c, direct_alice)

    direct_vm.clear_mocks()
    _source(direct_vm)
    _judge_for(direct_vm, CLAIM, "UNVERIFIABLE")
    assert direct_vm.run_validator() is True
