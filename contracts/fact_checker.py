# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

import json
from dataclasses import dataclass
from genlayer import *


# Consensus-Verified Fact Checker
#
# Users submit claims with evidence URLs. Validators independently fetch
# and verify against web evidence, reach comparative consensus on
# TRUE / FALSE / MISLEADING.


@dataclass
class Claim:
    submitter: str
    claim: str
    evidence_url: str
    verdict: str        # "TRUE" | "FALSE" | "MISLEADING" | "PENDING"
    yes_votes: u256     # TRUE
    no_votes: u256      # FALSE
    misleading_votes: u256


class FactChecker(gl.Contract):
    claims: TreeMap[str, Claim]
    claim_count: u256

    def __init__(self):
        pass

    @gl.public.write
    def submit_claim(self, claim_text: str, evidence_url: str) -> str:
        claim_id = f"claim-{self.claim_count + u256(1)}"
        self.claims[claim_id] = Claim(
            submitter=gl.message.sender_address.as_hex,
            claim=claim_text,
            evidence_url=evidence_url,
            verdict="PENDING",
            yes_votes=u256(0),
            no_votes=u256(0),
            misleading_votes=u256(0),
        )
        self.claim_count += u256(1)
        return claim_id

    def _verify_claim(self, claim: str, evidence_url: str) -> str:
        ALLOWED = ("TRUE", "FALSE", "MISLEADING")

        try:
            evidence = gl.nondet.web.render(evidence_url, mode="text")
        except Exception:
            evidence = "(source unavailable)"

        def leader() -> dict:
            prompt = (
                f"Claim: {claim}\n"
                f"Evidence from {evidence_url}:\n\n{evidence[:2000]}\n\n"
                f"Is the claim TRUE, FALSE, or MISLEADING based ONLY on the evidence? "
                f'Respond as JSON: {{"verdict": "TRUE"|"FALSE"|"MISLEADING", "reason": "..."}}'
            )
            res = gl.nondet.exec_prompt(prompt, response_format="json")
            verdict = (res.get("verdict") or "").strip().upper()
            return {"verdict": verdict if verdict in ALLOWED else "FALSE"}

        def validator(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            v = leader()["verdict"]
            return v == leader_result.calldata["verdict"]

        result = gl.vm.run_nondet_unsafe(leader, validator)
        return result["verdict"]

    @gl.public.write
    def verify(self, claim_id: str) -> None:
        c = self.claims.get(claim_id, None)
        if c is None:
            raise Exception("Claim not found")
        if c.verdict != "PENDING":
            raise Exception("Already verified")

        verdict = self._verify_claim(c.claim, c.evidence_url)
        if verdict == "TRUE":
            c.yes_votes += u256(1)
        elif verdict == "FALSE":
            c.no_votes += u256(1)
        else:
            c.misleading_votes += u256(1)
        c.verdict = verdict
        self.claims[claim_id] = c

    @gl.public.view
    def get_claim(self, claim_id: str) -> str:
        c = self.claims.get(claim_id, None)
        if c is None:
            return json.dumps({"exists": False})
        return json.dumps({
            "exists": True,
            "claim": c.claim,
            "evidence_url": c.evidence_url,
            "verdict": c.verdict,
            "yes_votes": int(c.yes_votes),
            "no_votes": int(c.no_votes),
            "misleading_votes": int(c.misleading_votes),
        })

    @gl.public.view
    def get_claim_count(self) -> str:
        return json.dumps({"count": int(self.claim_count)})
