# On-Chain Verification Guide

This guide provides step-by-step instructions for independently verifying the deployed contracts, source code hashes, and execution receipts on **GenLayer Studionet (Preview)**.

---

## 1. Network Information

- **Network Name**: GenLayer Studionet (Preview)
- **Chain ID**: `61999`
- **RPC URL**: `https://studio.genlayer.com/api`
- **Block Explorer**: `https://explorer-studio.genlayer.com`
- **GuardArena Address**: `0x05628E36D65281bfa7EA64DBcCd9Ac9c2e1a6474`
- **GuardGate Address**: `0xE699C8828F4F054fEe73B251837CE8B373Ba3D02`

---

## 2. Verifying Source Code Matching

GenLayer transactions that deploy intelligent contracts embed the source code in base64 format inside the deployment transaction payload.

### Method:
1. Query the JSON-RPC endpoint using `eth_getTransactionByHash` with the deployment transaction hash:
   - GuardArena Deploy Tx: `0x8c7cf7754804996df19d8e355df3f01b28ac5f64a22655f96a9857afdf25fba0`
   - GuardGate Deploy Tx: `0xbabc4708a844890d1b25ddc9c263ed956c6e08753772682dcec38c110c206f21`
2. Extract the field:
   `result.data.contract_code`
3. Decode the base64 string to UTF-8 text.
4. Calculate the SHA-256 hash of the decoded text.
5. Compare the hash against the local file:
   - `contracts/GuardArena.py`: `fd163692452d869e1422c63efc09b388269e68175f22bcff3b0783e9ed55f1c4`
   - `contracts/GuardGate.py`: `4f4ef9bd903f24b145faecfef50a2d78227fa68e2693cc7eb07889cf76c92233`

### Automated Script:
Run:
```bash
npm run verify:source
```
Output:
```
Verifying GuardArena...
Local SHA-256: fd163692452d869e1422c63efc09b388269e68175f22bcff3b0783e9ed55f1c4
On-chain decoded SHA-256: fd163692452d869e1422c63efc09b388269e68175f22bcff3b0783e9ed55f1c4
SHA-256 Match: EXACT MATCH (VERIFIED)

Verifying GuardGate...
Local SHA-256: 4f4ef9bd903f24b145faecfef50a2d78227fa68e2693cc7eb07889cf76c92233
On-chain decoded SHA-256: 4f4ef9bd903f24b145faecfef50a2d78227fa68e2693cc7eb07889cf76c92233
SHA-256 Match: EXACT MATCH (VERIFIED)
```

---

## 3. Auditing Consensus Data & Transaction Receipts

To inspect the raw validator votes and consensus outcomes for any transaction:
```bash
curl -X POST https://studio.genlayer.com/api \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "eth_getTransactionReceipt",
    "params": ["0x002a8024d2ec759337eb8bbf8e10af39fddeedcde0447d4f3f0e6990b19cd1cd"]
  }'
```
Inspect:
- `result.status_name`: `ACCEPTED`
- `result.result_name`: `MAJORITY_AGREE`
- `result.consensus_data.votes`: Mapping of validator addresses to their respective votes (`agree`, `idle`, or `disagree`).
- `result.consensus_data.leader_receipt[0].execution_result`: `SUCCESS` (or error payload on revert).

---

## 4. End-to-End Test Suite & Policy Scanners

To run the complete offline and online verification suite:
```bash
npm run check
```
This single command executes:
- `npm run test`: 22 unit tests across Layer 1 (pure predicate logic), Layer 2 (storage atomicity, counter invariants, mock state machine), and Layer 3 (validator disagreement and sampling noise resilience).
- `npm run scan:ascii`: Enforces 100% pure ASCII across all smart contract files.
- `npm run scan:banned`: Scans codebase and documentation for prohibited or misleading claims.
- `npm run scan:secrets`: Ensures no private keys, mnemonics, or OAuth tokens are present.
- `npm run verify:source`: Verifies local SHA-256 against on-chain transaction code.
- `npm run check:evidence`: Verifies cross-document consistency between live receipts and markdown tables.
