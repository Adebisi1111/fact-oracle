// Lean live measurement: does the digest-match validator improve the commit rate?
//
// Logs each tx hash immediately (so a stall is diagnosable), polls the receipt
// with a shorter budget, and reports the first-attempt outcome per claim.
import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { readFileSync } from "fs";
import { createHash } from "crypto";
import { Wallet } from "ethers";

const ADDR = process.env.ADDR || "0xCD983F7AF2A997F49A26E64F7CF546d98E158083";
const KS = "/home/administrator/.genlayer/keystores/user_wallet.json";
const wallet = Wallet.fromEncryptedJsonSync(readFileSync(KS, "utf8"), process.env.GLPASS);
const client = createClient({ chain: testnetBradbury, account: createAccount(wallet.privateKey) });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const local = readFileSync(new URL("./contracts/fact_oracle.py", import.meta.url), "utf8");
const code = await client.getContractCode(ADDR);
const live = typeof code === "string" ? code : String(code);
const h = (s) => createHash("sha256").update(s, "utf8").digest("hex");
console.log("=== source parity ===");
console.log("live:", Buffer.byteLength(live, "utf8"), "local:", Buffer.byteLength(local, "utf8"),
            "MATCH:", h(live) === h(local) ? "YES" : "NO");
console.log("digest check present:", live.includes("digest"));

const PAGE = "https://example.com/";
const CASES = [
  ["m1", "The example.com domain is intended for use in illustrative examples in documents.", PAGE, "TRUE"],
  ["m2", "The example.com domain is used to sell consumer electronics online.", PAGE, "FALSE"],
  ["m3", "The example.com domain was registered in 1995.", PAGE, "UNVERIFIABLE"],
];

console.log("\n=== claims ===");
const rows = [];
for (const [id, text, url, expect] of CASES) {
  const t0 = Date.now();
  let verdict = null, note = "";
  try {
    const hash = await client.writeContract({
      address: ADDR, functionName: "submit_claim",
      args: [id, text, url, ""], gasLimit: 5000000n,
    });
    console.log(`[${id}] tx ${hash}`);
    const rc = await client.waitForTransactionReceipt({ hash, retries: 120, interval: 5000 });
    note = `${rc?.statusName ?? rc?.status} ${rc?.txExecutionResultName ?? ""}`;
    if ((rc?.txExecutionResultName ?? "") === "FINISHED_WITH_RETURN") {
      const row = await client.readContract({ address: ADDR, functionName: "get_verdict", args: [id] });
      verdict = row?.verdict ?? null;
    }
  } catch (e) {
    note = "ERROR " + String(e).slice(0, 120);
  }
  const secs = Math.round((Date.now() - t0) / 1000);
  const ok = verdict === expect;
  rows.push({ id, expect, verdict, note, ok, secs });
  console.log(`[${id}] expect=${expect.padEnd(12)} got=${String(verdict).padEnd(12)} ${note} (${secs}s) ${ok ? "OK" : "MISS"}`);
}

console.log("\n=== unreachable ===");
try {
  const hash = await client.writeContract({
    address: ADDR, functionName: "submit_claim",
    args: ["m4", "Nope.", "https://example.com/no-such-page-404", ""], gasLimit: 5000000n,
  });
  const rc = await client.waitForTransactionReceipt({ hash, retries: 120, interval: 5000 });
  console.log("result:", rc?.txExecutionResultName ?? rc?.statusName);
} catch (e) { console.log("ERROR", String(e).slice(0, 120)); }
console.log("stored:", JSON.stringify(await client.readContract({ address: ADDR, functionName: "get_claim", args: ["m4"] })));

console.log("\n=== summary ===");
console.log(`first-attempt verdicts landed: ${rows.filter(r => r.ok).length}/${CASES.length}`);
console.log("timings(s):", rows.map(r => `${r.id}=${r.secs}`).join(" "));
console.log("verdict_counts():", JSON.stringify(await client.readContract({ address: ADDR, functionName: "verdict_counts", args: [] })));
