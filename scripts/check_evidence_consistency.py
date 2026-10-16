import os
import json
import re
import sys

def check_consistency():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    deployments_path = os.path.join(root, "scripts", "deploy", "deployments.json")
    live_evidence_path = os.path.join(root, "scripts", "deploy", "live_evidence.json")
    readme_path = os.path.join(root, "README.md")
    docs_dir = os.path.join(root, "docs")

    with open(deployments_path, "r", encoding="utf-8") as f:
        deployments = json.load(f)

    with open(live_evidence_path, "r", encoding="utf-8") as f:
        live_evidence = json.load(f)

    expected_arena = deployments["guardArena"]["address"].lower()
    expected_gate = deployments["guardGate"]["address"].lower()
    actual_arena = live_evidence["guardArenaAddress"].lower()
    actual_gate = live_evidence["guardGateAddress"].lower()

    assert actual_arena == expected_arena, f"GuardArena mismatch: {actual_arena} vs {expected_arena}"
    assert actual_gate == expected_gate, f"GuardGate mismatch: {actual_gate} vs {expected_gate}"

    # Collect all active hashes and addresses from deployments, evidence, and probe
    active_hashes = set()
    active_guard_ids = set()

    def extract_active(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("guardId", "guard_id") and isinstance(v, str):
                    active_guard_ids.add(v.lower())
                elif isinstance(v, str) and v.startswith("0x") and len(v) == 66:
                    active_hashes.add(v.lower())
                extract_active(v)
        elif isinstance(obj, list):
            for item in obj:
                extract_active(item)

    extract_active(deployments)
    extract_active(live_evidence)

    # Also add deploy tx hashes
    active_hashes.add(deployments["guardArena"]["deployTxHash"].lower())
    active_hashes.add(deployments["guardGate"]["deployTxHash"].lower())

    # Add Probe contract hashes if probe_results.json exists
    probe_path = os.path.join(root, "scripts", "deploy", "probe_results.json")
    if os.path.exists(probe_path):
        with open(probe_path, "r", encoding="utf-8") as f:
            probe_data = json.load(f)
            extract_active(probe_data)

    # Superseded deployments
    superseded_addrs = [item["address"].lower() for item in deployments.get("supersededDeployments", [])]
    superseded_txs = [item["deployTxHash"].lower() for item in deployments.get("supersededDeployments", [])]

    # 1. Audit README.md
    with open(readme_path, "r", encoding="utf-8") as f:
        readme_content = f.read()

    readme_parts = readme_content.split("## Superseded Deployments")
    main_readme = readme_parts[0]
    superseded_readme = readme_parts[1] if len(readme_parts) > 1 else ""

    # Verify no superseded address appears outside ## Superseded Deployments
    for s_addr in superseded_addrs:
        assert s_addr not in main_readme.lower(), (
            f"Superseded address {s_addr} found outside ## Superseded Deployments in README.md!"
        )

    # Verify all transaction hashes in main README are active
    hash_pattern = re.compile(r"0x[0-9a-fA-F]{64}")
    for h in hash_pattern.findall(main_readme):
        assert h.lower() in active_hashes or h.lower() in superseded_txs, (
            f"Unknown transaction hash {h} found in main README.md! Must be from active live_evidence."
        )

    # 2. Audit docs/*.md
    for fname in os.listdir(docs_dir):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(docs_dir, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            doc_content = f.read()

        # No superseded addresses in docs/ (they belong exclusively to README.md)
        for s_addr in superseded_addrs:
            assert s_addr not in doc_content.lower(), (
                f"Superseded address {s_addr} found in {fname}! It must only be in README.md."
            )

        # In EVIDENCE.md and INTEGRATION.md, verify all hashes are active
        if fname in ("EVIDENCE.md", "INTEGRATION.md"):
            for h in hash_pattern.findall(doc_content):
                assert h.lower() in active_hashes or h.lower() in superseded_txs, (
                    f"Unknown transaction hash {h} found in docs/{fname}!"
                )

    # 3. Check for truncated hashes like '0x1234...5678'
    files_to_check = [readme_path] + [os.path.join(docs_dir, f) for f in os.listdir(docs_dir) if f.endswith(".md")]
    truncated_pattern = re.compile(r"0x[a-fA-F0-9]{4,16}\.\.\.[a-fA-F0-9]{4,16}")
    for fpath in files_to_check:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
            matches = truncated_pattern.findall(content)
            assert not matches, f"Truncated tx/address hash found in {os.path.basename(fpath)}: {matches}"

    # 4. Check for 'undefined' or 'None' in markdown tables
    table_line_pattern = re.compile(r"^\|.*\|$", re.MULTILINE)
    for fpath in files_to_check:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
            for line in table_line_pattern.findall(content):
                # Allow 'None' only if explicitly talking about python return types in code/docs prose
                assert "undefined" not in line, f"'undefined' found in table row in {os.path.basename(fpath)}: {line}"
                assert " None " not in line and "| None |" not in line and "|None|" not in line, (
                    f"'None' found in table row in {os.path.basename(fpath)}: {line}"
                )

    print("PASSED: Evidence consistency check succeeded.")
    print(f"  Verified active GuardArena: {actual_arena}")
    print(f"  Verified active GuardGate: {actual_gate}")
    print(f"  Verified {len(active_hashes)} active transaction hashes.")
    print(f"  Verified {len(active_guard_ids)} active guard IDs.")
    print(f"  Verified 0 superseded addresses outside ## Superseded Deployments.")
    print(f"  Verified 0 truncated hashes, 'undefined', or 'None' in tables.")

if __name__ == "__main__":
    check_consistency()
