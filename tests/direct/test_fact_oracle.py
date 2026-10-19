"""Direct-mode tests for FactOracle.

No network and no chain: web fetches and the LLM are mocked, so these tests
exercise the contract's plumbing — input validation, the unreachable-source
abort, verdict and counter bookkeeping, and read integrity.

They do NOT prove the model discriminates. In direct mode gltest runs only the
leader function and the LLM is a stub, so "TRUE here, FALSE there" shows the
contract stores what it is told, not that a real committee reads the page. That
proof is the live on-chain run, where the same URL is judged twice and the claim
is the only thing that changes.
"""

import json
import re

from tests.direct.conftest import to_hex

URL = "https://example.com/facts"
URL2 = "https://example.com/archive"

PAGE = (
    "<html><body><h1>Nigeria</h1>"
    "<p>Abuja is the capital city of Nigeria. Lagos is the largest city.</p>"
    "</body></html>"
)
PAGE2 = (
    "<html><body><p>Lagos had a population of about nine million in 2006.</p>"
    "</body></html>"
)

SUPPORTS = "Abuja is the capital of Nigeria."
CONTRADICTS = "Lagos is the capital of Nigeria."
SILENT = "The naira is Nigeria's currency."


def _source(vm, body=PAGE, pattern=r".*example\.com/facts.*", status=200):
    vm.mock_web(pattern, {"status": status, "body": body})


def _judge_for(vm, claim_text, verdict, reasoning="The page states it directly."):
    """Bind one verdict to one exact claim.

    The pattern anchors on the CLAIM section rather than the page text: the page
    itself contains the words of both the supported and the contradicted claim,
    so an unanchored pattern would satisfy the first registered mock and every
    test would silently receive that verdict.
    """
    vm.mock_llm(
        r"<<<CLAIM\n" + re.escape(claim_text),
        json.dumps({"verdict": verdict, "reasoning": reasoning}),
    )


# ------------------------------------------------------------------ verdicts


def test_evidence_supporting_the_claim_commits_true(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, SUPPORTS, "TRUE", "The page names Abuja as the capital.")

    direct_vm.sender = direct_alice
    assert c.submit_claim("c1", SUPPORTS, URL, "") == "TRUE"

    row = c.get_claim("c1")
    assert row["exists"] is True
    assert row["verdict"] == "TRUE"
    assert row["claim_text"] == SUPPORTS
    assert row["source_url"] == URL
    assert "Abuja" in row["reasoning"]
    assert row["submitter"] == to_hex(direct_alice)


def test_evidence_contradicting_the_claim_commits_false(direct_vm, direct_deploy, direct_alice):
    """Same URL as the TRUE case, different claim — only the question changed."""
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, CONTRADICTS, "FALSE", "The page names Abuja, not Lagos.")

    direct_vm.sender = direct_alice
    assert c.submit_claim("c1", CONTRADICTS, URL, "") == "FALSE"
    assert c.get_claim("c1")["verdict"] == "FALSE"


def test_evidence_silent_on_the_claim_commits_unverifiable(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, SILENT, "UNVERIFIABLE", "The page says nothing about currency.")

    direct_vm.sender = direct_alice
    assert c.submit_claim("c1", SILENT, URL, "") == "UNVERIFIABLE"
    assert c.get_claim("c1")["verdict"] == "UNVERIFIABLE"


def test_an_unrecognized_verdict_token_is_stored_as_unverifiable(
    direct_vm, direct_deploy, direct_alice
):
    """A model that answers off-script must not mint a TRUE or FALSE badge."""
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, SUPPORTS, "MAYBE")

    direct_vm.sender = direct_alice
    assert c.submit_claim("c1", SUPPORTS, URL, "") == "UNVERIFIABLE"


# ------------------------------------------------------- unreachable evidence


def test_unreachable_source_stores_nothing(direct_vm, direct_deploy, direct_alice):
    """No mock registered for the URL, so the fetch raises.

    A verdict derived from a failed fetch is worse than no verdict: the
    transaction must revert and leave no claim behind.
    """
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _judge_for(direct_vm, SUPPORTS, "TRUE")  # an LLM mock exists, the web one does not

    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("unreachable"):
        c.submit_claim("c1", SUPPORTS, URL, "")

    assert c.get_claim("c1")["exists"] is False
    assert c.total_claims() == 0
    assert c.verdict_counts()["total"] == 0


def test_error_status_counts_as_unreachable(direct_vm, direct_deploy, direct_alice):
    """A 500 is not evidence — judging its body would be judging an error page."""
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm, body="<html><body>Internal Server Error</body></html>", status=500)
    _judge_for(direct_vm, SUPPORTS, "TRUE")

    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("unreachable"):
        c.submit_claim("c1", SUPPORTS, URL, "")

    assert c.get_claim("c1")["exists"] is False


# ------------------------------------------------------------------ validation


def test_claim_id_is_required(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("claim_id required"):
        c.submit_claim("  ", SUPPORTS, URL, "")


def test_claim_text_is_required(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("claim_text required"):
        c.submit_claim("c1", "   ", URL, "")


def test_duplicate_claim_id_is_rejected(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, SUPPORTS, "TRUE")

    direct_vm.sender = direct_alice
    c.submit_claim("c1", SUPPORTS, URL, "")
    with direct_vm.expect_revert("already exists"):
        c.submit_claim("c1", SUPPORTS, URL, "")


def test_non_http_source_is_rejected(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("must be http"):
        c.submit_claim("c1", SUPPORTS, "ftp://example.com/facts", "")


def test_malformed_second_url_is_rejected(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("must be http"):
        c.submit_claim("c1", SUPPORTS, URL, "example.com/archive")


# ---------------------------------------------------------------- second source


def test_second_source_is_actually_fetched(direct_vm, direct_deploy, direct_alice):
    """Both URLs must be read, and both must be recorded with the verdict."""
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm, body=PAGE, pattern=r".*example\.com/facts.*")
    _source(direct_vm, body=PAGE2, pattern=r".*example\.com/archive.*")
    _judge_for(direct_vm, SUPPORTS, "TRUE")

    direct_vm.sender = direct_alice
    c.submit_claim("c1", SUPPORTS, URL, URL2)

    verdict_row = c.get_verdict("c1")
    assert verdict_row["source_url"] == URL
    assert verdict_row["second_url"] == URL2

    # If the second fetch had been skipped the archive mock would be unused.
    assert len(direct_vm._web_mocks_hit) == 2


def test_an_unreachable_second_source_also_aborts(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm, body=PAGE, pattern=r".*example\.com/facts.*")
    _judge_for(direct_vm, SUPPORTS, "TRUE")

    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("unreachable"):
        c.submit_claim("c1", SUPPORTS, URL, URL2)

    assert c.get_claim("c1")["exists"] is False


def test_second_url_equal_to_the_first_is_dropped(direct_vm, direct_deploy, direct_alice):
    """Fetching the same page twice wastes a round without adding evidence."""
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, SUPPORTS, "TRUE")

    direct_vm.sender = direct_alice
    c.submit_claim("c1", SUPPORTS, URL, URL)
    assert c.get_verdict("c1")["second_url"] == ""


# ------------------------------------------------------------------- bookkeeping


def test_verdict_counts_track_every_branch(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, SUPPORTS, "TRUE")
    _judge_for(direct_vm, CONTRADICTS, "FALSE")
    _judge_for(direct_vm, SILENT, "UNVERIFIABLE")

    direct_vm.sender = direct_alice
    c.submit_claim("c1", SUPPORTS, URL, "")
    c.submit_claim("c2", CONTRADICTS, URL, "")
    c.submit_claim("c3", SILENT, URL, "")

    counts = c.verdict_counts()
    assert counts == {"true": 1, "false": 1, "unverifiable": 1, "total": 3}
    assert c.total_claims() == 3


def test_submitter_stats_count_per_wallet(direct_vm, direct_deploy, direct_alice, direct_bob):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, SUPPORTS, "TRUE")

    direct_vm.sender = direct_alice
    c.submit_claim("c1", SUPPORTS, URL, "")
    c.submit_claim("c2", SUPPORTS, URL, "")
    direct_vm.sender = direct_bob
    c.submit_claim("c3", SUPPORTS, URL, "")

    assert c.submitter_stats(to_hex(direct_alice))["submitted"] == 2
    assert c.submitter_stats(to_hex(direct_bob))["submitted"] == 1
    assert c.submitter_stats("0x0000000000000000000000000000000000000000")["submitted"] == 0


# --------------------------------------------------------------------- recheck


def test_recheck_replaces_the_verdict_and_moves_the_counters(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, SUPPORTS, "TRUE", "The page names Abuja as the capital.")
    _judge_for(direct_vm, SUPPORTS, "FALSE", "On re-reading, the page contradicts it.")

    direct_vm.sender = direct_alice
    c.submit_claim("c1", SUPPORTS, URL, "")
    assert c.verdict_counts()["true"] == 1

    # Clear the verdict mocks so the recheck lands on the FALSE binding.
    direct_vm.clear_mocks()
    _source(direct_vm)
    _judge_for(direct_vm, SUPPORTS, "FALSE", "On re-reading, the page contradicts it.")

    direct_vm.sender = direct_bob
    assert c.recheck("c1") == "FALSE"

    counts = c.verdict_counts()
    assert counts["true"] == 0
    assert counts["false"] == 1
    assert counts["total"] == 1
    assert "re-reading" in c.get_verdict("c1")["reasoning"]
    # The original submitter is preserved through a recheck by a third party.
    assert c.get_claim("c1")["submitter"] == to_hex(direct_alice)


def test_recheck_of_an_unknown_claim_reverts(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("not found"):
        c.recheck("nope")


def test_recheck_leaves_the_verdict_alone_when_the_source_is_unreachable(
    direct_vm, direct_deploy, direct_alice
):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, SUPPORTS, "TRUE")

    direct_vm.sender = direct_alice
    c.submit_claim("c1", SUPPORTS, URL, "")

    direct_vm.clear_mocks()  # the source goes away
    with direct_vm.expect_revert("unreachable"):
        c.recheck("c1")

    assert c.get_claim("c1")["verdict"] == "TRUE"
    assert c.verdict_counts()["true"] == 1


def test_recheck_to_the_same_verdict_does_not_double_count(
    direct_vm, direct_deploy, direct_alice
):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, SUPPORTS, "TRUE")

    direct_vm.sender = direct_alice
    c.submit_claim("c1", SUPPORTS, URL, "")
    assert c.recheck("c1") == "TRUE"

    counts = c.verdict_counts()
    assert counts["true"] == 1
    assert counts["total"] == 1


# --------------------------------------------------------------- read integrity


def test_claim_text_containing_a_separator_does_not_corrupt_reads(
    direct_vm, direct_deploy, direct_alice
):
    """A `|` in the claim must not shift the other fields.

    Views return JSON, so a claim that itself contains the separator still reads
    back with the right verdict, source and submitter.
    """
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)

    nasty = "Abuja | Lagos | Kano are all | cities in Nigeria."
    _judge_for(direct_vm, nasty, "TRUE")

    direct_vm.sender = direct_alice
    assert c.submit_claim("c1", nasty, URL, "") == "TRUE"

    row = c.get_claim("c1")
    assert row["claim_text"] == nasty      # stored verbatim
    assert row["verdict"] == "TRUE"        # NOT shifted into the claim text
    assert row["source_url"] == URL
    assert row["submitter"] == to_hex(direct_alice)


def test_unknown_claim_reads_back_as_absent(direct_vm, direct_deploy):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    assert c.get_claim("nope")["exists"] is False
    assert c.get_verdict("nope")["exists"] is False


def test_created_at_is_recorded(direct_vm, direct_deploy, direct_alice):
    direct_vm.warp("2026-01-01T00:00:00Z")
    c = direct_deploy("contracts/fact_oracle.py")
    _source(direct_vm)
    _judge_for(direct_vm, SUPPORTS, "TRUE")

    direct_vm.sender = direct_alice
    c.submit_claim("c1", SUPPORTS, URL, "")
    assert c.get_claim("c1")["created_at"] > 0
