const dns = require('dns');
dns.setDefaultResultOrder('ipv4first');

const { createClient, chains, createAccount } = require('genlayer-js');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

async function main() {
  console.log("=================================================");
  console.log("BREAKTHEGUARD: DEPLOYING GUARDARENA & GUARDGATE");
  console.log("=================================================");

  const account = createAccount();
  console.log("Using throwaway test account:", account.address);

  const client = createClient({
    chain: chains.studionet,
    account: account,
  });

  // 1. Deploy GuardArena
  console.log("\n1. Deploying GuardArena...");
  const arenaPath = path.join(__dirname, '../../contracts/GuardArena.py');
  const arenaCode = fs.readFileSync(arenaPath, 'utf8');
  const arenaSha256 = crypto.createHash('sha256').update(arenaCode, 'utf8').digest('hex');
  console.log("GuardArena source sha256:", arenaSha256);

  async function deployWithRetry(deployFn, label, maxAttempts = 3) {
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        return await deployFn();
      } catch (err) {
        console.warn(`[WARN] ${label} attempt ${attempt} failed: ${err.message}`);
        if (attempt === maxAttempts) throw err;
        await new Promise((r) => setTimeout(r, 3000));
      }
    }
  }

  const t0Arena = Date.now();
  const arenaDeployTx = await deployWithRetry(
    () => client.deployContract({ code: arenaCode, args: [] }),
    "GuardArena deployContract"
  );
  console.log("GuardArena deploy tx:", arenaDeployTx);

  const arenaReceipt = await client.waitForTransactionReceipt({
    hash: arenaDeployTx,
    retries: 120,
    interval: 3000,
  });
  const arenaElapsed = ((Date.now() - t0Arena) / 1000).toFixed(2);
  console.log(`GuardArena deployed in ${arenaElapsed}s:`);
  console.log("  status_name:", arenaReceipt.status_name);
  console.log("  result_name:", arenaReceipt.result_name);
  const arenaAddress = arenaReceipt.recipient;
  console.log("GuardArena address:", arenaAddress);

  if (!arenaAddress || arenaReceipt.consensus_data?.leader_receipt?.[0]?.execution_result !== 'SUCCESS') {
    throw new Error("GuardArena deployment failed: " + JSON.stringify(arenaReceipt));
  }

  // 2. Deploy GuardGate with arenaAddress
  console.log("\n2. Deploying GuardGate...");
  const gatePath = path.join(__dirname, '../../contracts/GuardGate.py');
  const gateCode = fs.readFileSync(gatePath, 'utf8');
  const gateSha256 = crypto.createHash('sha256').update(gateCode, 'utf8').digest('hex');
  console.log("GuardGate source sha256:", gateSha256);

  const t0Gate = Date.now();
  const gateDeployTx = await deployWithRetry(
    () => client.deployContract({ code: gateCode, args: [arenaAddress, 1] }),
    "GuardGate deployContract"
  );
  console.log("GuardGate deploy tx:", gateDeployTx);

  const gateReceipt = await client.waitForTransactionReceipt({
    hash: gateDeployTx,
    retries: 120,
    interval: 3000,
  });
  const gateElapsed = ((Date.now() - t0Gate) / 1000).toFixed(2);
  console.log(`GuardGate deployed in ${gateElapsed}s:`);
  console.log("  status_name:", gateReceipt.status_name);
  console.log("  result_name:", gateReceipt.result_name);
  const gateAddress = gateReceipt.recipient;
  console.log("GuardGate address:", gateAddress);

  if (!gateAddress || gateReceipt.consensus_data?.leader_receipt?.[0]?.execution_result !== 'SUCCESS') {
    throw new Error("GuardGate deployment failed: " + JSON.stringify(gateReceipt));
  }

  const deployments = {
    network: "GenLayer Studionet (Preview)",
    chainId: 61999,
    rpc: "https://studio.genlayer.com/api",
    explorerBase: "https://explorer-studio.genlayer.com",
    deployerAddress: account.address,
    guardArena: {
      address: arenaAddress,
      deployTxHash: arenaDeployTx,
      sourceFile: "contracts/GuardArena.py",
      sourceSha256: arenaSha256,
      sourceBytes: arenaCode.length,
      elapsed: arenaElapsed,
      statusName: arenaReceipt.status_name,
      resultName: arenaReceipt.result_name,
      votes: arenaReceipt.consensus_data?.votes,
      explorerUrl: `https://explorer-studio.genlayer.com/address/${arenaAddress}`,
    },
    guardGate: {
      address: gateAddress,
      deployTxHash: gateDeployTx,
      sourceFile: "contracts/GuardGate.py",
      sourceSha256: gateSha256,
      sourceBytes: gateCode.length,
      elapsed: gateElapsed,
      statusName: gateReceipt.status_name,
      resultName: gateReceipt.result_name,
      votes: gateReceipt.consensus_data?.votes,
      explorerUrl: `https://explorer-studio.genlayer.com/address/${gateAddress}`,
    },
    supersededDeployments: [
      {
        contract: "GuardArena",
        address: "0x05628E36D65281bfa7EA64DBcCd9Ac9c2e1a6474",
        deployTxHash: "0x8c7cf7754804996df19d8e355df3f01b28ac5f64a22655f96a9857afdf25fba0",
        reason: "Superseded by v1.1.0 deployment with independent validator binding on persisted reply, samples, and integrity hashes"
      },
      {
        contract: "GuardGate",
        address: "0xE699C8828F4F054fEe73B251837CE8B373Ba3D02",
        deployTxHash: "0xbabc4708a844890d1b25ddc9c263ed956c6e08753772682dcec38c110c206f21",
        reason: "Superseded by v1.1.0 deployment with independent validator binding on persisted reply, filter flag, and semantic consistency"
      },
      {
        contract: "GuardArena",
        address: "0x6ebabD1360f65C4F08DaDfe57ae9af2f7C49dEdD",
        deployTxHash: "0xee2fcce3cb68115d0774f785ef1a33d808d10cb781d82fe0420c3b4793086c10",
        reason: "Superseded initial deployment prior to GuardGate storage schema update"
      }
    ],
    deployedAt: new Date().toISOString(),
  };

  fs.writeFileSync(
    path.join(__dirname, 'deployments.json'),
    JSON.stringify(deployments, null, 2)
  );
  console.log("\nSaved scripts/deploy/deployments.json successfully.");

  // Save raw deploy receipts
  const evidenceDir = path.join(__dirname, '../../docs/evidence');
  if (!fs.existsSync(evidenceDir)) fs.mkdirSync(evidenceDir, { recursive: true });
  fs.writeFileSync(
    path.join(evidenceDir, 'guard_arena_deploy_receipt.json'),
    JSON.stringify(arenaReceipt, null, 2)
  );
  fs.writeFileSync(
    path.join(evidenceDir, 'guard_gate_deploy_receipt.json'),
    JSON.stringify(gateReceipt, null, 2)
  );
  console.log("Saved raw deployment receipts to docs/evidence/");
}

main().catch(err => {
  console.error("Deployment failed:", err);
  process.exit(1);
});
