// Deploy FactOracle to Bradbury using genlayer-js.
//
// The keystore is decrypted in-process; the private key never touches disk.
// Pass the password via the GLPASS environment variable.
import { createClient, createAccount } from "genlayer-js";
import { testnetBradbury } from "genlayer-js/chains";
import { readFileSync } from "fs";
import { Wallet } from "ethers";

const KS = "/home/administrator/.genlayer/keystores/user_wallet.json";
const wallet = Wallet.fromEncryptedJsonSync(readFileSync(KS, "utf8"), process.env.GLPASS);
const account = createAccount(wallet.privateKey);
const client = createClient({ chain: testnetBradbury, account });

console.log("deployer:", account.address);

const code = readFileSync(new URL("./contracts/fact_oracle.py", import.meta.url), "utf8");
console.log("bytes   :", Buffer.byteLength(code, "utf8"));

const hash = await client.deployContract({ code, args: [], value: 0n, gasLimit: 5000000n });
console.log("deploy tx:", hash);

const receipt = await client.waitForTransactionReceipt({ hash, retries: 120, interval: 5000 });
console.log("status   :", receipt?.status ?? receipt?.txExecutionResultName, receipt?.statusName ?? "");

const tx = await client.getTransaction({ hash });
console.log("ADDRESS  :", tx?.recipient);
