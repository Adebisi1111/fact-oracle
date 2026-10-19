// Live discrimination check on Bradbury.
//
// One page, three claims. A verification oracle that has only ever been shown
// succeeding proves nothing: the committee must commit TRUE for a claim the
// page supports, FALSE for one it contradicts, and UNVERIFIABLE for one it does
// not address — all read from the SAME URL, so the question is the only thing
// that changes. An unreachable URL must revert and store nothing.
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
  ["t1", "The example.com domain is intended for use in illustrative examples in documents.", PAGE, ""],
  ["t2", "The example.com domain is used to sell consumer electronics online.", PAGE, ""],
  ["t3", "The example.com domain was registered in 1995.", PAGE, ""],
];

for (const [id, text, url, second] of CASES) {
  process.stdout.write(`\n[${id}] ${text}\n`);
  try {
    const hash = await client.writeContract({
      address: ADDR, functionName: "submit_claim",
      args: [id, text, url, second], gasLimit: 5000000n,
    });
    console.log("  tx      :", hash);
    const rc = await client.waitForTransactionReceipt({ hash, retries: 240, interval: 5000 });
    console.log("  status  :", rc?.statusName ?? rc?.status, rc?.txExecutionResultName ?? "");
    const row = await client.readContract({ address: ADDR, functionName: "get_verdict", args: [id] });
    console.log("  verdict :", JSON.stringify(row));
  } catch (e) {
    console.log("  ERROR   :", String(e).slice(0, 300));
  }
}

console.log("\n=== unreachable source (must store nothing) ===");
try {
  const hash = await client.writeContract({
    address: ADDR, functionName: "submit_claim",
    args: ["t4", "This source does not exist.", "https://example.com/definitely-not-here-404", ""],
    gasLimit: 5000000n,
  });
  const rc = await client.waitForTransactionReceipt({ hash, retries: 240, interval: 5000 });
  console.log("  status  :", rc?.statusName ?? rc?.status, rc?.txExecutionResultName ?? "");
} catch (e) {
  console.log("  ERROR   :", String(e).slice(0, 300));
}
const t4 = await client.readContract({ address: ADDR, functionName: "get_claim", args: ["t4"] });
console.log("  stored  :", JSON.stringify(t4));

console.log("\n=== final state ===");
console.log("total_claims()  :", await client.readContract({ address: ADDR, functionName: "total_claims", args: [] }));
console.log("verdict_counts():", JSON.stringify(await client.readContract({ address: ADDR, functionName: "verdict_counts", args: [] })));
