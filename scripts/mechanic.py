#!/usr/bin/env python3
import os
import sys
import json
import base64
import argparse
import urllib.request
import urllib.parse
from datetime import datetime

def get_token():
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
    env_path = "/opt/bristlecone/bristlecone-logic/.env"
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GITHUB_TOKEN="):
                    val = line.split("=", 1)[1].strip()
                    return val.strip('"').strip("'")
    return None

GITHUB_TOKEN = get_token()
if not GITHUB_TOKEN:
    print("Error: GITHUB_TOKEN not found in environment or .env file.")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Bristlecone-Mechanic"
}

GUARD_CODE = """# --- Security Hardening: SSRF Guard (RFC 1918 & Cloud Metadata) ---
def is_safe_url(target_url: str) -> bool:
    \"\"\"Validates that target_url resolves strictly to public, routable IP addresses.\"\"\"
    try:
        import socket
        import ipaddress
        from urllib.parse import urlparse

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
# ------------------------------------------------------------------"""

PR_BODY = """### Security Hardening: SSRF Mitigation in Tool Web Requests

#### Vulnerability Assessment
When autonomous LLM agents process arbitrary or model-generated URLs, un-sanitized HTTP fetches expose the runtime environment to Server-Side Request Forgery (SSRF). Malicious inputs or prompt injection can direct the agent to query:
- `http://169.254.169.254/latest/meta-data/` (Exposing cloud instance credentials / IMDS)
- `http://127.0.0.1:*` or internal RFC 1918 subnets (Interacting with local microservices and databases)

#### Remediation
This PR adds a lightweight, zero-dependency `is_safe_url()` check using Python's standard `socket` and `ipaddress` libraries. It performs pre-flight DNS resolution before executing `requests.get()`, blocking access to non-routable, loopback, and private address space.

---
*For runtime guardrails, deterministic JSON repair, and AST-sandboxed code execution for agent pipelines, see [Bristlecone Guard](https://bristleconelogic.com).*
"""

def gh_req(url: str, method: str = "GET", data: dict = None):
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw}
    except Exception as e:
        return 0, {"error": str(e)}

def inspect_and_patch(raw_code: str) -> str:
    lines = raw_code.splitlines(keepends=True)

    # 1. Locate end of module-level imports (column 0 only)
    import_end_idx = 0
    in_paren_import = False
    saw_first_import = False

    for idx, line in enumerate(lines):
        stripped = line.strip()
        is_indented = line.startswith((" ", "\t"))

        if not stripped or stripped.startswith("#"):
            continue

        # Match unindented top-level imports
        if not is_indented and (stripped.startswith("import ") or stripped.startswith("from ")):
            saw_first_import = True
            if "(" in stripped and ")" not in stripped:
                in_paren_import = True
            import_end_idx = idx + 1
            continue

        if in_paren_import:
            if ")" in stripped:
                in_paren_import = False
            import_end_idx = idx + 1
            continue

        # Stop at the very first unindented non-import statement (e.g. @dataclass, def, class)
        if saw_first_import and not is_indented:
            break

    # 2. Locate first line of actual code after imports
    next_code_idx = import_end_idx
    while next_code_idx < len(lines) and not lines[next_code_idx].strip():
        next_code_idx += 1

    # 3. Replace gap: exactly 2 blank lines before, exactly 2 blank lines after
    guard_lines = [f"{l}\n" for l in GUARD_CODE.splitlines()]
    new_middle = ["\n", "\n"] + guard_lines + ["\n", "\n"]
    lines = lines[:import_end_idx] + new_middle + lines[next_code_idx:]

    # 4. Inject guard check before requests.get(url
    patched_lines = []
    for line in lines:
        if "requests.get(url" in line:
            indent = line[:len(line) - len(line.lstrip())]
            guard = (
                f"{indent}if not is_safe_url(url):\n"
                f"{indent}    raise ValueError(f\"SSRF Protection: Blocked restricted IP for {{url}}\")\n"
            )
            patched_lines.append(guard)
        patched_lines.append(line)

    return "".join(patched_lines)

def run_mechanic(target_repo: str, target_file: str, dry_run: bool = False):
    print(f"[*] Target: {target_repo} -> {target_file}")
    
    status, file_meta = gh_req(f"https://api.github.com/repos/{target_repo}/contents/{target_file}")
    if status != 200:
        print(f"  [-] Failed to fetch file ({status}): {file_meta}")
        return

    raw_content = base64.b64decode(file_meta["content"]).decode("utf-8", errors="ignore")
    if "requests.get(url" not in raw_content or "is_safe_url" in raw_content:
        print("  [-] Skipped: No matching requests.get(url) found or file already patched.")
        return

    patched_content = inspect_and_patch(raw_content)

    if dry_run:
        print("[+] Dry run complete. Patch generated cleanly.")
        return

    status, user_data = gh_req("https://api.github.com/user")
    bot_login = user_data["login"]

    status, repo_info = gh_req(f"https://api.github.com/repos/{target_repo}")
    upstream_default = repo_info.get("default_branch", "main")
    
    status, fork_meta = gh_req(f"https://api.github.com/repos/{target_repo}/forks", method="POST")
    fork_repo = f"{bot_login}/{repo_info['name']}"

    status, ref_data = gh_req(f"https://api.github.com/repos/{target_repo}/git/ref/heads/{upstream_default}")
    latest_sha = ref_data["object"]["sha"]

    branch_name = f"fix/ssrf-guard-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    status, _ = gh_req(
        f"https://api.github.com/repos/{fork_repo}/git/refs",
        method="POST",
        data={"ref": f"refs/heads/{branch_name}", "sha": latest_sha}
    )

    status, _ = gh_req(
        f"https://api.github.com/repos/{fork_repo}/contents/{target_file}",
        method="PUT",
        data={
            "message": "security: harden web request tools against SSRF attacks",
            "content": base64.b64encode(patched_content.encode("utf-8")).decode("utf-8"),
            "branch": branch_name,
            "sha": file_meta["sha"]
        }
    )

    pr_payload = {
        "title": "Security: Harden tool web requests against SSRF vulnerabilities",
        "body": PR_BODY,
        "head": f"{bot_login}:{branch_name}",
        "base": upstream_default
    }
    status, pr_res = gh_req(f"https://api.github.com/repos/{target_repo}/pulls", method="POST", data=pr_payload)
    if status == 201:
        print(f"[SUCCESS] PR Live: {pr_res['html_url']}")
    else:
        print(f"[-] PR creation failed ({status}): {pr_res}")

def main():
    parser = argparse.ArgumentParser(description="Bristlecone Mechanic - Automated Security Patching")
    parser.add_argument("--target", required=True, help="Target repository (owner/repo)")
    parser.add_argument("--file", required=True, help="Target file path")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without committing")
    args = parser.parse_args()

    run_mechanic(args.target, args.file, args.dry_run)

if __name__ == "__main__":
    main()
