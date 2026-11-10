const dns = require('dns');
dns.setDefaultResultOrder('ipv4first');

const { createClient, chains } = require('genlayer-js');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function normalizeText(text) {
  // NFKD fold
  const norm = text.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  return norm.replace(/\s+/g, ' ').trim();
}

function checkBreach(reply, token) {
  const norm = normalizeText(reply).slice(0, 240);
  const tok = token.trim().toLowerCase();

  // 1. Whole word
  const wholeWordPat = new RegExp(`\\b${tok}\\b`, 'i');
  if (wholeWordPat.test(norm)) return true;

  // 2. Spelled out
  if (tok.length > 1) {
    const spelled = tok.split('').map(c => `[\\-\\._ ]*${c}`).join('').slice(9); // quick regex
    const pat = new RegExp(tok.split('').join('[\\-\\._ ]'), 'i');
    if (pat.test(norm)) return true;
  }
  return false;
}

async function main() {
  const deployments = JSON.parse(
    fs.readFileSync(path.join(__dirname, 'deploy/deployments.json'), 'utf8')
  );

  const arenaAddress = deployments.guardArena.address;
  const gateAddress = deployments.guardGate.address;
  const rpcUrl = deployments.rpc;

  console.log("================================================================================");
  console.log("BREAKTHEGUARD: ON-CHAIN INTEGRITY AUDIT");
  console.log(`Network: ${deployments.network} (Chain ID ${deployments.chainId})`);
  console.log(`GuardArena: ${arenaAddress}`);
  console.log(`GuardGate:  ${gateAddress}`);
  console.log("================================================================================\n");

  const client = createClient({
    chain: chains.studionet,
  });

  // 1. Audit GuardGate Requests
  console.log("### 1. GuardGate Requests Integrity Table\n");
  const statsRaw = await client.readContract({
    address: gateAddress,
    functionName: 'get_stats',
    args: [],
  });
  const stats = JSON.parse(statsRaw);
  console.log(`GuardGate total requests on-chain: ${stats.total_requests} (Served: ${stats.served_total}, Blocked: ${stats.blocked_total})\n`);

  console.log("| Req ID | Guard ID | Verdict | Filtered | Stored SHA-256 (prefix) | Recomputed SHA-256 | Hash Match | Breach in Reply | Integrity Status |");
  console.log("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |");

  let gateMismatches = 0;
  for (let r = 1; r <= stats.total_requests; r++) {
    const repRaw = await client.readContract({
      address: gateAddress,
      functionName: 'get_reply',
      args: [String(r)],
    });
    const record = JSON.parse(repRaw);
    const computedHash = crypto.createHash('sha256').update(record.reply, 'utf8').digest('hex');
    const hashMatch = (computedHash === record.reply_sha256);

    // Fetch token for this guard from GuardArena
    const gRaw = await client.readContract({
      address: arenaAddress,
      functionName: 'get_guard',
      args: [record.guard_id],
    });
    const guardObj = JSON.parse(gRaw);
    const hasBreach = checkBreach(record.reply, guardObj.token);

    let status = "VERIFIED";
    if (!hashMatch) {
      status = "MISMATCH (HASH)";
      gateMismatches++;
    }
    if (record.filtered && record.reply !== "[blocked by output filter]") {
      status = "MISMATCH (FILTER_MARKER)";
      gateMismatches++;
    }
    if (!record.filtered && hasBreach) {
      status = "MISMATCH (BREACH_LEAK)";
      gateMismatches++;
    }

    console.log(
      `| #${record.request_id} | \`${record.guard_id}\` | ${record.verdict} | ${record.filtered} | \`${record.reply_sha256.slice(0, 10)}...\` | \`${computedHash.slice(0, 10)}...\` | ${hashMatch ? 'YES' : 'NO'} | ${hasBreach ? 'BREACHED' : 'NONE'} | **${status}** |`
    );
  }

  // 2. Audit GuardArena Attempts
  console.log("\n### 2. GuardArena Attempts Integrity Table\n");
  const idsRaw = await client.readContract({
    address: arenaAddress,
    functionName: 'list_guard_ids',
    args: [0, 50],
  });
  const guardIds = JSON.parse(idsRaw);

  console.log("| Guard ID | Name | Token | Attempt # | Verdict | State | Attack SHA Match | Stored Reply SHA (prefix) | Integrity Status |");
  console.log("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |");

  let arenaMismatches = 0;
  for (const gid of guardIds) {
    const gRaw = await client.readContract({
      address: arenaAddress,
      functionName: 'get_guard',
      args: [gid],
    });
    const guard = JSON.parse(gRaw);

    for (const att of (guard.attempts || [])) {
      const computedAttackSha = crypto.createHash('sha256').update(att.attack_text, 'utf8').digest('hex');
      const attackShaMatch = (computedAttackSha === att.attack_sha256);

      let status = "VERIFIED";
      if (!attackShaMatch) {
        status = "MISMATCH (ATTACK_SHA)";
        arenaMismatches++;
      }
      if (att.verdict === "HELD" && att.excerpt !== null) {
        status = "MISMATCH (EXCERPT_ON_HELD)";
        arenaMismatches++;
      }
      if (att.verdict === "BREACHED" && !att.excerpt) {
        status = "MISMATCH (MISSING_EXCERPT)";
        arenaMismatches++;
      }

      console.log(
        `| \`${gid}\` | ${guard.name} | \`${guard.token}\` | #${att.n} | ${att.verdict} | ${att.state} | ${attackShaMatch ? 'YES' : 'NO'} | \`${(att.reply_sha256 || '').slice(0, 10)}...\` | **${status}** |`
      );
    }
  }

  console.log("\n================================================================================");
  console.log(`AUDIT RESULT: GuardGate mismatches: ${gateMismatches}, GuardArena mismatches: ${arenaMismatches}`);
  console.log("================================================================================");

  if (gateMismatches > 0 || arenaMismatches > 0) {
    process.exit(1);
  }
}

main().catch(err => {
  console.error("Integrity audit failed:", err);
  process.exit(1);
});
