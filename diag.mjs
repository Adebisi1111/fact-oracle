// Diagnose the NOT_VOTED failures: is it a timeout, a disagreement, or an
// exception inside the nondet block? Dump the full transaction on failure.
import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { readFileSync } from "fs";
import { Wallet } from "ethers";

const ADDR = process.env.ADDR || "0xCD983F7AF2A997F49A26E64F7CF546d98E158083";
const KS = "/home/administrator/.genlayer/keystores/user_wallet.json";
const wallet = Wallet.fromEncryptedJsonSync(readFileSync(KS, "utf8"), process.env.GLPASS);
const client = createClient({ chain: testnetBradbury, account: createAccount(wallet.privateKey) });

const PAGE = "https://example.com/";
const clean = (o) => JSON.parse(JSON.stringify(o, (k, v) => (typeof v === "bigint" ? v.toString() : v)));

for (let i = 1; i <= 6; i++) {
  const id = `d${i}`;
  const text = "The example.com domain is intended for use in illustrative examples in documents.";
  const hash = await client.writeContract({
    address: ADDR, functionName: "submit_claim",
    args: [id, text, PAGE, ""], gasLimit: 5000000n,
  });
  const rc = await client.waitForTransactionReceipt({ hash, retries: 120, interval: 5000 });
  const status = rc?.statusName ?? rc?.status;
  const result = rc?.txExecutionResultName ?? "";
  console.log(`\n[${id}] tx=${hash} status=${status} result=${result}`);
  if (result !== "FINISHED_WITH_RETURN") {
    const tx = clean(await client.getTransaction({ hash }));
    console.log("  rounds :", tx?.numOfRounds ?? tx?.num_of_rounds);
    console.log("  votes  :", JSON.stringify(tx?.lastRound?.validatorVotesName ?? tx?.lastRound?.validator_votes ?? tx?.votes ?? null));
    console.log("  exec   :", JSON.stringify(tx?.txExecutionResultName ?? tx?.tx_execution_result_name));
    const keys = Object.keys(tx ?? {});
    console.log("  keys   :", keys.join(","));
    for (const k of keys) {
      if (/trace|error|stderr|log|message|round|vote/i.test(k)) {
        const v = tx[k];
        const s = typeof v === "string" ? v : JSON.stringify(v);
        if (s && s !== "[]" && s !== "null") console.log(`  ${k}: ${String(s).slice(0, 900)}`);
      }
    }
    break;
  }
  console.log("  OK");
}
