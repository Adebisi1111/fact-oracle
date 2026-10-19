// Retry the TRUE / FALSE cases until consensus commits.
//
// Status 12/13 (VALIDATORS_TIMEOUT / LEADER_TIMEOUT) are time-outs, not
// disagreements: any single round can miss before one reaches AGREE. The claim
// is not stored on a timeout, so re-submitting is safe and is the correct
// response rather than a contract change.
import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { readFileSync } from "fs";
import { Wallet } from "ethers";

const ADDR = process.env.ADDR || "0x35937a7f85fd1ff89E73b2D7D0130905d2E2d7DE";
const KS = "/home/administrator/.genlayer/keystores/user_wallet.json";
const wallet = Wallet.fromEncryptedJsonSync(readFileSync(KS, "utf8"), process.env.GLPASS);
const client = createClient({ chain: testnetBradbury, account: createAccount(wallet.privateKey) });

const PAGE = "https://example.com/";
const CASES = [
  ["t1", "The example.com domain is intended for use in illustrative examples in documents."],
  ["t2", "The example.com domain is used to sell consumer electronics online."],
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

for (const [id, text] of CASES) {
  console.log(`\n[${id}] ${text}`);
  for (let attempt = 1; attempt <= 6; attempt++) {
    try {
      const hash = await client.writeContract({
        address: ADDR, functionName: "submit_claim",
        args: [id, text, PAGE, ""], gasLimit: 5000000n,
      });
      const rc = await client.waitForTransactionReceipt({ hash, retries: 240, interval: 5000 });
      const status = rc?.statusName ?? rc?.status;
      const result = rc?.txExecutionResultName ?? "";
      console.log(`  attempt ${attempt}: status=${status} result=${result} tx=${hash}`);
      if (result === "FINISHED_WITH_RETURN") {
        const row = await client.readContract({ address: ADDR, functionName: "get_verdict", args: [id] });
        console.log("  VERDICT:", JSON.stringify(row));
        break;
      }
    } catch (e) {
      console.log(`  attempt ${attempt}: ERROR ${String(e).slice(0, 200)}`);
    }
    await sleep(5000);
  }
}

console.log("\n=== final state ===");
console.log("total_claims()  :", await client.readContract({ address: ADDR, functionName: "total_claims", args: [] }));
console.log("verdict_counts():", JSON.stringify(await client.readContract({ address: ADDR, functionName: "verdict_counts", args: [] })));
for (const id of ["t1", "t2", "t3"]) {
  console.log(`get_verdict(${id}):`, JSON.stringify(await client.readContract({ address: ADDR, functionName: "get_verdict", args: [id] })));
}
