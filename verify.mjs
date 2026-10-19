// Verify the deployed FactOracle: source parity + live reads.
//
// `status: ACCEPTED` proves a transaction was decided, never that the code is
// live. The falsifying check is getContractCode at the address — if it returns
// "not found", the deploy stored nothing and every read will fail forever.
import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { readFileSync } from "fs";
import { createHash } from "crypto";
import { Wallet } from "ethers";

const ADDR = process.env.ADDR || "0xCD983F7AF2A997F49A26E64F7CF546d98E158083";
const KS = "/home/administrator/.genlayer/keystores/user_wallet.json";
const wallet = Wallet.fromEncryptedJsonSync(readFileSync(KS, "utf8"), process.env.GLPASS);
const client = createClient({ chain: testnetBradbury, account: createAccount(wallet.privateKey) });

const local = readFileSync(new URL("./contracts/fact_oracle.py", import.meta.url), "utf8");
const localHash = createHash("sha256").update(local, "utf8").digest("hex");

console.log("=== source parity ===");
const code = await client.getContractCode(ADDR);
const live = typeof code === "string" ? code : String(code);
console.log("live bytes :", Buffer.byteLength(live, "utf8"));
console.log("local bytes:", Buffer.byteLength(local, "utf8"));
const liveHash = createHash("sha256").update(live, "utf8").digest("hex");
console.log("live  sha256:", liveHash);
console.log("local sha256:", localHash);
console.log("MATCH      :", liveHash === localHash ? "YES" : "NO");
console.log("has _is_authorized?:", live.includes("_is_authorized"));
console.log("has UNREACHABLE    :", live.includes("UNREACHABLE"));

console.log("\n=== live reads ===");
const r = (fn, args = []) => client.readContract({ address: ADDR, functionName: fn, args });
console.log("total_claims()   :", await r("total_claims"));
console.log("verdict_counts() :", await r("verdict_counts"));
console.log("get_claim(nope)  :", await r("get_claim", ["nope"]));
console.log("get_verdict(nope):", await r("get_verdict", ["nope"]));
console.log("now()            :", await r("now"));
