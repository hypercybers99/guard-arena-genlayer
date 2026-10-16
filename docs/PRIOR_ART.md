# Prior Art & Differentiation Analysis

This document surveys existing research, centralized prompt robustness games, and the GenLayer smart contract ecosystem, outlining the key design differentiations of **BreakTheGuard**.

---

## 1. Existing Off-Chain Prompt Robustness Games & Benchmarks

Adversarial testing of language model guardrails has gained significant traction through several prominent benchmarks and interactive games:

### A. Lakera Gandalf
- **Model**: A centralized web application where players attempt to prompt an LLM to reveal a hidden password across escalating difficulty tiers.
- **Evaluation Mechanism**: Uses centralized proprietary classifiers and heuristic filters hosted on central cloud servers.
- **Differences from BreakTheGuard**:
  - Gandalf relies entirely on centralized servers and private evaluation algorithms; users cannot independently audit the evaluation logic.
  - No mechanism exists for public users to register, patch, and track the evolution lineage of their own defensive guard policies.
  - Gandalf does not run across distributed validator quorums.

### B. Tensor Trust (Toye et al., 2023)
- **Model**: A crowd-sourced two-player web game where defenders write system prompts (guardrails) and attackers write extraction prompts to obtain a secret access code.
- **Evaluation Mechanism**: Employs language models (LLM-as-a-judge) to evaluate whether the target code was leaked.
- **Differences from BreakTheGuard**:
  - In Tensor Trust, using an LLM as the evaluator opens recursive prompt injection vulnerabilities against the judge. BreakTheGuard eliminates this by using a deterministic Python predicate.
  - Tensor Trust operates off-chain without immutable consensus records or economic finality.

### C. JailbreakBench & PromptBench
- **Model**: Academic offline benchmark datasets (Chao et al., 2024; Zhu et al., 2023) evaluating LLM resilience against standardized adversarial prompts.
- **Differences from BreakTheGuard**:
  - These benchmarks run offline in batch mode and do not support dynamic, public multi-party adversarial interaction or on-chain lineage tracking.

---

## 2. On-Chain Contracts in the GenLayer Ecosystem

We searched the GenLayer developer ecosystem and public repository implementations for prompt defense and intelligent evaluation architectures:
- Existing intelligent contracts on GenLayer Studionet have explored element-based commitments (`CommitmentLedger`), drift monitoring (`SourceDriftLedger`), and arbitrated courts (`GuardrailCourt`).
- After examining the ecosystem, we found no contract that implements an adversarial language model guard arena combining:
  1. A deterministic Python predicate oracle (eliminating LLM-as-a-judge vulnerabilities);
  2. Majority-of-samples consensus ($K=3$) to absorb stochastic model sampling noise;
  3. A two-stage reproducibility requirement (`BREACHED_UNCONFIRMED` $\to$ `CONFIRMED` vs `FLAKY`) preventing non-repeatable anomalies from breaking guards;
  4. Mandatory baseline probe and utility probe verification at registration to disqualify refuse-all policies; and
  5. Cryptographically tracked defensive lineage across guard generations.

---

## 3. Summary of Differences

| Feature | Lakera Gandalf | Tensor Trust | JailbreakBench | BreakTheGuard (GenLayer) |
| :--- | :--- | :--- | :--- | :--- |
| **Execution Environment** | Centralized web server | Centralized web server | Offline Python script | Decentralized Intelligent Contract |
| **Breach Oracle** | Proprietary cloud classifier | LLM-as-a-judge | Keyword / LLM judge | **Deterministic Python predicate** |
| **Validator Consensus** | Single central server | Single central server | Local machine run | **5-validator BFT consensus** |
| **Sampling Resilience** | Single prompt call | Single prompt call | Batch statistics | **$K=3$ majority-of-samples** |
| **Flakiness Protection** | Not supported | Not supported | Statistical aggregate | **Independent re-verification round** |
| **Refuse-All Prevention** | Manual curation | Game rules | N/A | **On-chain utility & baseline probes** |
| **Lineage Tracking** | Not tracked | Leaderboard only | Not tracked | **On-chain parent guard pointers** |
| **Reusability** | Standalone app | Standalone app | Evaluation script | **GuardGate consumer contract** |
