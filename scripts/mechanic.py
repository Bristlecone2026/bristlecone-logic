#!/usr/bin/env python3
import os
import sys
import base64
import json
import time
import argparse
import difflib
import urllib.request
import urllib.parse
import urllib.error

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    print("Error: GITHUB_TOKEN environment variable not set.")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Bristlecone-Mechanic-Security-Scanner"
}

SSRF_GUARD_HEADER = """# --- Security Hardening: SSRF Guard (RFC 1918 & Cloud Metadata) ---
import socket
import ipaddress
from urllib.parse import urlparse

def is_safe_url(target_url: str) -> bool:
    \"\"\"Validates that target_url resolves strictly to public, routable IP addresses.\"\"\"
    try:
        parsed = urlparse(target_url)
        hostname = parsed.hostname
        if not hostname:
            return False
        addr_info = socket.getaddrinfo(hostname, None)
        for entry in addr_info:
            ip = ipaddress.ip_address(entry[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or not ip.is_global:
                return False
        return True
    except Exception:
        return False
# ------------------------------------------------------------------
"""

PR_TITLE = "fix(security): sanitize agent web requests against SSRF (RFC 1918 / Cloud Metadata)"
PR_BODY = """### Security Hardening: Server-Side Request Forgery (SSRF) Guard

#### Risk Overview
When autonomous LLM agents process arbitrary or model-generated URLs, un-sanitized HTTP fetches expose the runtime environment to Server-Side Request Forgery (SSRF). Malicious inputs or prompt injection can direct the agent to query:
- `http://169.254.169.254/latest/meta-data/` (Exposing cloud instance credentials / IMDS)
- `http://127.0.0.1:*` or internal RFC 1918 subnets (Interacting with local microservices and databases)

#### Remediation
This PR adds a lightweight, zero-dependency `is_safe_url()` check using Python's standard `socket` and `ipaddress` libraries. It performs pre-flight DNS resolution before executing `requests.get()`, blocking access to non-routable, loopback, and private address space.

---
*For runtime guardrails, deterministic JSON repair, and AST-sandboxed code execution for agent pipelines, see [Bristlecone Guard](https://bristleconelogic.com).*
"""

def gh_api(endpoint: str, method: str = "GET", payload: dict = None):
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body
    except Exception as e:
        return 0, str(e)

def inspect_and_patch(raw_code: str) -> str:
    if "is_safe_url" in raw_code:
        return raw_code

    lines = raw_code.splitlines(keepends=True)
    patched_lines = []

    for line in lines:
        if "requests.get(url" in line:
            indent = line[:len(line) - len(line.lstrip())]
            guard = (
                f"{indent}if not is_safe_url(url):\n"
                f"{indent}    raise ValueError(f\"SSRF Protection: Refusing to fetch restricted or private IP address for URL: {{url}}\")\n"
            )
            patched_lines.append(guard)
        patched_lines.append(line)

    return SSRF_GUARD_HEADER + "\n" + "".join(patched_lines)

def get_authenticated_user():
    status, data = gh_api("/user")
    if status == 200 and isinstance(data, dict):
        return data.get("login")
    return None

def remediate_repo(upstream_repo: str, target_file: str, dry_run: bool = True):
    user = get_authenticated_user()
    if not user:
        print("  [!] Failed to resolve authenticated user.")
        return

    print(f"\n[Mechanic] Target: {upstream_repo} -> {target_file}")

    # 1. Fetch file content from upstream
    status, file_meta = gh_api(f"/repos/{upstream_repo}/contents/{target_file}")
    if status != 200:
        print(f"  [-] Failed to fetch file ({status}): {file_meta}")
        return

    raw_content = base64.b64decode(file_meta["content"]).decode("utf-8", errors="ignore")
    if "requests.get(" not in raw_content or "is_safe_url" in raw_content:
        print("  [-] Skipped: No unvalidated requests.get found or already patched.")
        return

    patched_content = inspect_and_patch(raw_content)

    if dry_run:
        print("\n--- Unified Diff Preview ---")
        diff = difflib.unified_diff(
            raw_content.splitlines(),
            patched_content.splitlines(),
            fromfile=f"a/{target_file}",
            tofile=f"b/{target_file}",
            lineterm=""
        )
        for d in list(diff):
            print(d)
        print("\n[Dry-Run] Patch generated successfully. PR not submitted.")
        return

    # 2. Query upstream default branch
    status, upstream_info = gh_api(f"/repos/{upstream_repo}")
    if status != 200 or not isinstance(upstream_info, dict):
        print(f"  [-] Failed to query upstream repository details: {upstream_info}")
        return
    default_branch = upstream_info.get("default_branch", "main")

    # 3. Fork repository
    print(f"  [+] Requesting fork of {upstream_repo} to {user}...")
    gh_api(f"/repos/{upstream_repo}/forks", method="POST")
    repo_name = upstream_repo.split("/")[1]

    # 4. Poll fork until the default branch is provisioned and readable
    print(f"  [+] Waiting for fork provisioning to complete...")
    base_sha = None
    for attempt in range(12):
        time.sleep(3)
        status, branch_data = gh_api(f"/repos/{user}/{repo_name}/branches/{default_branch}")
        if status == 200 and isinstance(branch_data, dict) and "commit" in branch_data:
            base_sha = branch_data["commit"]["sha"]
            print(f"  [+] Fork confirmed ready at commit {base_sha[:7]}.")
            break
        print(f"  [*] Fork syncing (attempt {attempt + 1}/12)...")

    if not base_sha:
        print(f"  [-] Fork provisioning timed out. Branch '{default_branch}' not found.")
        return

    # 5. Create fix branch (or reuse if already present)
    new_branch = "fix/ssrf-guard"
    status, branch_check = gh_api(f"/repos/{user}/{repo_name}/branches/{new_branch}")
    if status != 200:
        print(f"  [+] Creating branch {new_branch}...")
        status, ref_res = gh_api(f"/repos/{user}/{repo_name}/git/refs", method="POST", payload={
            "ref": f"refs/heads/{new_branch}",
            "sha": base_sha
        })
        if status not in (200, 201):
            print(f"  [-] Failed to create branch ({status}): {ref_res}")
            return

    # 6. Retrieve accurate target file SHA on the fix branch
    status, fork_file = gh_api(f"/repos/{user}/{repo_name}/contents/{target_file}?ref={new_branch}")
    file_sha = fork_file.get("sha") if (status == 200 and isinstance(fork_file, dict)) else file_meta["sha"]

    # 7. Commit patched file
    print(f"  [+] Committing patch to {user}/{repo_name}:{new_branch}...")
    b64_new_content = base64.b64encode(patched_content.encode("utf-8")).decode("utf-8")
    status, commit_res = gh_api(f"/repos/{user}/{repo_name}/contents/{target_file}", method="PUT", payload={
        "message": "fix(security): sanitize agent web requests against SSRF",
        "content": b64_new_content,
        "sha": file_sha,
        "branch": new_branch
    })

    if status not in (200, 201):
        print(f"  [-] Commit failed ({status}): {commit_res}")
        return

    # 8. Open Pull Request upstream
    print(f"  [+] Submitting Pull Request to {upstream_repo}...")
    status, pr_res = gh_api(f"/repos/{upstream_repo}/pulls", method="POST", payload={
        "title": PR_TITLE,
        "head": f"{user}:{new_branch}",
        "base": default_branch,
        "body": PR_BODY
    })

    if status == 201 and isinstance(pr_res, dict):
        print(f"\n[SUCCESS] PR Live: {pr_res.get('html_url')}")
    else:
        print(f"\n[!] PR submission status ({status}): {pr_res}")

def main():
    parser = argparse.ArgumentParser(description="Bristlecone Mechanic - Automated Security Remediator")
    parser.add_argument("--dry-run", action="store_true", help="Preview unified diff without pushing changes.")
    parser.add_argument("--target", type=str, required=True, help="Target repo (e.g. 'kidzik/web-research-agent')")
    parser.add_argument("--file", type=str, default="tools.py", help="Target file (default: 'tools.py')")
    args = parser.parse_args()

    remediate_repo(args.target, args.file, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
