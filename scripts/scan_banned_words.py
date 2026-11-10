import os
import re
import sys

BANNED_PATTERNS = [
    (r'\bguarantee(s|d|ing)?\b', 'guarantee(s)'),
    (r'\bimmutable\b', 'immutable'),
    (r'\btrustless\b', 'trustless'),
    (r'\bofficial\b', 'official'),
    (r'\bverifiable\b', 'verifiable'),
    (r'\bprevents\b', 'prevents'),
    (r'\bWCAG\b', 'WCAG'),
    (r'\bunanimous(ly)?\b', 'unanimous'),
    (r'\btamper-?proof\b', 'tamper-proof'),
    (r'\bbytecode\b', 'bytecode'),
    (r'\bcryptographic\s+proof\b', 'cryptographic proof'),
    (r'\bnotary\b', 'notary'),
    (r'\btestnet\b', 'testnet'),
    (r'\brevolutionary\b', 'revolutionary'),
    (r'\bno\s+one\s+else\b', 'no one else'),
]

IGNORE_DIRS = {'.git', 'node_modules', 'dist', '__pycache__', '.pytest_cache'}
ALLOWED_FILES = {'scan_banned_words.py', 'scan_banned.mjs'}

def scan():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    violations = []
    
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            if f in ALLOWED_FILES:
                continue
            if not f.endswith(('.ts', '.tsx', '.js', '.jsx', '.json', '.md', '.html', '.py', '.css')):
                continue
            path = os.path.join(r, f)
            rel_path = os.path.relpath(path, root).replace('\\', '/')
            
            with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
                for line_idx, line in enumerate(fp, 1):
                    # Check finalized in docs/markdown (must only be used if referring to literal status_name FINALIZED or Raw receipt status)
                    if f.endswith('.md') and re.search(r'\bfinalized\b', line, re.IGNORECASE):
                        if not any(k in line for k in ['status_name', 'FINALIZED', 'Raw receipt status', 'latest-final', 'receipt.status']):
                            violations.append((rel_path, line_idx, 'finalized outside status_name', line.strip()))

                    # Check 'live' used for the network in docs/markdown
                    if f.endswith('.md') and re.search(r'\blive\s+(network|contract|mainnet|testnet|system|mode|environment|chain|state)\b', line, re.IGNORECASE):
                        violations.append((rel_path, line_idx, 'live used for network', line.strip()))

                    for pat, name in BANNED_PATTERNS:
                        m = re.search(pat, line, re.IGNORECASE)
                        if m:
                            violations.append((rel_path, line_idx, m.group(0), line.strip()))
    
    if violations:
        print(f"FAILED: Found {len(violations)} banned word violations:")
        for path, line_no, matched, text in violations:
            print(f"  {path}:{line_no} [{matched}] -> {text[:100]}")
        sys.exit(1)
    else:
        print("PASSED: Zero banned words detected across codebase and docs.")
        sys.exit(0)

if __name__ == '__main__':
    scan()
