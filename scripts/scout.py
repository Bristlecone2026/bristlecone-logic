#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

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
                    return val.strip('"\'')
    return None

GITHUB_TOKEN = get_token()
if not GITHUB_TOKEN:
    print("Error: GITHUB_TOKEN not found in environment or .env file.")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "Bristlecone-Scout"
}

SEARCH_QUERIES = [
    "requests.get agent filename:tools.py language:python",
    "requests.get crewai language:python",
    "requests.get langchain tools language:python",
    "requests.get autogen filename:tools.py language:python",
    "requests.get smolagents language:python"
]

def gh_get(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return 0, str(e)

def scout_candidates():
    candidates = []
    seen = set()

    for q in SEARCH_QUERIES:
        encoded = urllib.parse.quote(q)
        url = f"https://api.github.com/search/code?q={encoded}&per_page=10"
        status, data = gh_get(url)
        if status != 200 or not isinstance(data, dict):
            continue

        for item in data.get("items", []):
            repo_full = item["repository"]["full_name"]
            path = item["path"]
            key = f"{repo_full}:{path}"
            if key not in seen and not repo_full.startswith("Bristlecone"):
                seen.add(key)
                candidates.append((repo_full, path))

    results = []
    now = datetime.now(timezone.utc)

    for repo, path in candidates:
        status, meta = gh_get(f"https://api.github.com/repos/{repo}")
        if status != 200 or not isinstance(meta, dict):
            continue

        if meta.get("archived", False) or meta.get("fork", False):
            continue

        pushed_str = meta.get("pushed_at")
        if not pushed_str:
            continue
        pushed_dt = datetime.fromisoformat(pushed_str.replace("Z", "+00:00"))
        days_inactive = (now - pushed_dt).days

        stars = meta.get("stargazers_count", 0)
        open_issues = meta.get("open_issues_count", 0)

        # Require activity within 180 days and at least 5 stars
        if days_inactive > 180 or stars < 5:
            continue

        score = (stars * 2) - (days_inactive * 0.5)

        results.append({
            "repo": repo,
            "file": path,
            "stars": stars,
            "days_inactive": days_inactive,
            "open_issues": open_issues,
            "score": round(score, 1)
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results

def main():
    print("[Scout] Mining repositories for eligible agent tools...")
    targets = scout_candidates()

    if not targets:
        print("[-] No candidates passed the quality threshold.")
        return

    print(f"\nDiscovered {len(targets)} qualified targets (ranked by priority):\n")
    print(f"{'Score':<8} {'Stars':<8} {'Last Active':<14} {'Target Repository':<35} {'File'}")
    print("-" * 85)
    for t in targets[:10]:
        print(f"{t['score']:<8} {t['stars']:<8} {str(t['days_inactive']) + 'd ago':<14} {t['repo']:<35} {t['file']}")

if __name__ == "__main__":
    main()
