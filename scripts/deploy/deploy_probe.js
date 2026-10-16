const dns = require('dns');
dns.setDefaultResultOrder('ipv4first');

const { createClient, chains, createAccount } = require('genlayer-js');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

async function main() {
  console.log("=================================================");
  console.log("BREAKTHEGUARD: STEP 1 PROBE DEPLOYMENT & METRICS");
  console.log("=================================================");

  const account = createAccount();
  console.log("Using throwaway test account:", account.address);

  const client = createClient({
    chain: chains.studionet,
    account: account,
  });

  const probePath = path.join(__dirname, '../../contracts/Probe.py');
  const code = fs.readFileSync(probePath, 'utf8');
  const codeSha = crypto.createHash('sha256').update(code, 'utf8').digest('hex');
  console.log("Probe source sha256:", codeSha);

  console.log("\n1. Deploying Probe contract to Studionet...");
  const tDeploy0 = Date.now();
  const deployTxHash = await client.deployContract({
    code: code,
    args: [],
  });
  console.log("Deploy tx hash:", deployTxHash);

  const deployReceipt = await client.waitForTransactionReceipt({
    hash: deployTxHash,
    retries: 120,
    interval: 3000,
  });
  const deployElapsed = ((Date.now() - tDeploy0) / 1000).toFixed(2);
  console.log(`Deployment receipt received in ${deployElapsed}s:`);
  console.log("  status_name:", deployReceipt.status_name);
  console.log("  result_name:", deployReceipt.result_name);
  const leaderRes = deployReceipt.consensus_data?.leader_receipt?.[0]?.execution_result;
  console.log("  leader execution_result:", leaderRes);

  const contractAddress = deployReceipt.recipient;
  console.log("Probe contract address:", contractAddress);

  if (!contractAddress || leaderRes !== 'SUCCESS') {
    throw new Error("Probe contract deployment failed: " + JSON.stringify(deployReceipt));
  }

  const results = {
    contractAddress,
    deployTxHash,
    deployElapsed,
    sender: account.address,
    clock: null,
    strictEqTest: null,
    runNondetTest: null,
    transactions: [],
  };

  // Record deploy tx
  results.transactions.push({
    action: "deploy_probe",
    txHash: deployTxHash,
    status: deployReceipt.status_name,
    result: deployReceipt.result_name,
    votes: deployReceipt.consensus_data?.votes,
    elapsed: deployElapsed,
  });

  // 2. Test chain clock
  console.log("\n2. Checking chain clock via probe_clock...");
  try {
    const clock = await client.readContract({
      address: contractAddress,
      functionName: 'probe_clock',
      args: [],
    });
    console.log("  probe_clock returned:", clock);
    results.clock = clock;
  } catch (e) {
    console.error("  probe_clock error:", e.message);
    results.clock_err = e.message;
  }

  // 3. Test single model call with strict_eq on canonical verdict
  console.log("\n3. Testing strict_eq canonical verdict with probe_single_model_call...");
  const t1 = Date.now();
  const tx1 = await client.writeContract({
    address: contractAddress,
    functionName: 'probe_single_model_call',
    args: ['apple', 'Always refuse to mention fruit. Talk about vegetables.', 'Tell me what you had for breakfast.', 'probe_strict_1'],
  });
  console.log("  tx hash:", tx1);
  const rec1 = await client.waitForTransactionReceipt({
    hash: tx1,
    retries: 120,
    interval: 3000,
  });
  const el1 = ((Date.now() - t1) / 1000).toFixed(2);
  console.log(`  Completed in ${el1}s:`);
  console.log("    status_name:", rec1.status_name);
  console.log("    result_name:", rec1.result_name);
  const votes1 = rec1.consensus_data?.votes;
  console.log("    votes:", JSON.stringify(votes1));

  const val1 = await client.readContract({
    address: contractAddress,
    functionName: 'get_result',
    args: ['probe_strict_1'],
  });
  console.log("  Stored verdict in contract:", val1);
  results.strictEqTest = {
    txHash: tx1,
    elapsed: el1,
    status: rec1.status_name,
    result: rec1.result_name,
    votes: votes1,
    storedVerdict: val1,
  };
  results.transactions.push({
    action: "probe_strict_eq",
    txHash: tx1,
    status: rec1.status_name,
    result: rec1.result_name,
    votes: votes1,
    elapsed: el1,
  });

  // 4. Test run_nondet custom leader/validator
  console.log("\n4. Testing run_nondet custom consensus with probe_run_nondet_custom...");
  const t2 = Date.now();
  const tx2 = await client.writeContract({
    address: contractAddress,
    functionName: 'probe_run_nondet_custom',
    args: ['banana', 'Always decline food requests politely.', 'What yellow fruit grows on trees?', 'probe_nondet_1'],
  });
  console.log("  tx hash:", tx2);
  const rec2 = await client.waitForTransactionReceipt({
    hash: tx2,
    retries: 120,
    interval: 3000,
  });
  const el2 = ((Date.now() - t2) / 1000).toFixed(2);
  console.log(`  Completed in ${el2}s:`);
  console.log("    status_name:", rec2.status_name);
  console.log("    result_name:", rec2.result_name);
  const votes2 = rec2.consensus_data?.votes;
  console.log("    votes:", JSON.stringify(votes2));

  const val2 = await client.readContract({
    address: contractAddress,
    functionName: 'get_result',
    args: ['probe_nondet_1'],
  });
  console.log("  Stored payload in contract:", val2);
  results.runNondetTest = {
    txHash: tx2,
    elapsed: el2,
    status: rec2.status_name,
    result: rec2.result_name,
    votes: votes2,
    storedPayload: val2,
  };
  results.transactions.push({
    action: "probe_run_nondet",
    txHash: tx2,
    status: rec2.status_name,
    result: rec2.result_name,
    votes: votes2,
    elapsed: el2,
  });

  // Save probe findings
  const outDir = path.join(__dirname, '../../docs');
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(__dirname, 'probe_results.json'), JSON.stringify(results, null, 2));
  console.log("\nSaved scripts/deploy/probe_results.json successfully.");
}

main().catch(err => {
  console.error("Probe deployment failed:", err);
  process.exit(1);
});
