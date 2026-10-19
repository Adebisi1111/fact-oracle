// Paced reliability run.
//
// The unpaced batch fired 8 submissions back to back and half failed — but the
// diagnostic showed the EVM submission tx itself REVERTING (node at capacity),
// not a consensus timeout. So the question is whether pacing fixes it. This run
// waits between claims and retries a reverted submission with backoff.
import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { readFileSync } from "fs";
import { Wallet } from "ethers";

const ADDR = process.env.ADDR || "0xCD983F7AF2A997F49A26E64F7CF546d98E158083";
const KS = "/home/administrator/.genlayer/keystores/user_wallet.json";
const wallet = Wallet.fromEncryptedJsonSync(readFileSync(KS, "utf8"), process.env.GLPASS);
const client = createClient({ chain: testnetBradbury, account: createAccount(wallet.privateKey) });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const read = (fn, args) => client.readContract({ address: ADDR, functionName: fn, args });

const PAGE = "https://example.com/";
const CLAIMS = [
  ["p1", "The example.com domain is intended for use in illustrative examples in documents.", "TRUE"],
  ["p2", "The example.com domain is used to sell consumer electronics online.", "FALSE"],
  ["p3", "The example.com domain was registered in 1995.", "UNVERIFIABLE"],
  ["p4", "The example.com domain is a domain reserved for documentation purposes.", "TRUE"],
  ["p5", "The example.com domain is a live online shop.", "FALSE"],
  ["p6", "The example.com domain was created by a company called Example Inc.", "UNVERIFIABLE"],
];

const PACE_MS = 45000;

console.log(`=== paced run: ${CLAIMS.length} claims, ${PACE_MS / 1000}s apart ===`);
const rows = [];
for (let i = 0; i < CLAIMS.length; i++) {
  const [id, text, expect] = CLAIMS[i];
  const t0 = Date.now();
  let note = "", verdict = null, submitted = false;

  // Submission retries: a reverted admission tx is the node refusing load.
  for (let a = 1; a <= 4 && !submitted; a++) {
    try {
      const hash = await client.writeContract({
        address: ADDR, functionName: "submit_claim",
        args: [id, text, PAGE, ""], gasLimit: 5000000n,
      });
      submitted = true;
      const rc = await client.waitForTransactionReceipt({ hash, retries: 120, interval: 5000 });
      note = `${rc?.statusName ?? rc?.status}/${rc?.txExecutionResultName ?? ""}`;
      if ((rc?.txExecutionResultName ?? "") === "FINISHED_WITH_RETURN") {
        await sleep(4000);
        for (let k = 0; k < 5 && !verdict; k++) {
          verdict = (await read("get_verdict", [id]))?.verdict ?? null;
          if (!verdict) await sleep(3000);
        }
      }
    } catch (e) {
      const msg = String(e);
      note = /reverted/i.test(msg) ? `admission reverted (attempt ${a})` : "ERR " + msg.slice(0, 80);
      await sleep(15000 * a);   // back off, then resubmit
    }
  }

  const secs = Math.round((Date.now() - t0) / 1000);
  const ok = verdict === expect;
  rows.push({ id, expect, verdict, ok, secs, note });
  console.log(`[${id}] expect=${expect.padEnd(12)} got=${String(verdict).padEnd(12)} ${note} (${secs}s) ${ok ? "OK" : "MISS"}`);

  if (i < CLAIMS.length - 1) await sleep(PACE_MS);
}

console.log("\n=== summary ===");
console.log(`verdicts matched: ${rows.filter(r => r.ok).length}/${CLAIMS.length}`);
console.log(`committed      : ${rows.filter(r => r.note.includes("FINISHED_WITH_RETURN")).length}/${CLAIMS.length}`);
console.log("timings(s):", rows.map(r => `${r.id}=${r.secs}`).join(" "));
console.log("verdict_counts():", JSON.stringify(await read("verdict_counts", [])));
