"""
Bristlecone Logic™ Blueprint: SSRF-Safe Web Extraction
Verifies target domains prior to network ingestion to prevent private intranet probing.
"""

from urllib.parse import urlparse
from bristlecone_logic.client import BristleconeClient

client = BristleconeClient()

target_urls = [
    "https://example.com/data.txt",
    "http://169.254.169.254/latest/meta-data/",
    "http://127.0.0.1:8000/internal-metrics",
]

for url in target_urls:
    parsed = urlparse(url)
    hostname = parsed.hostname or url

    audit = client.audit_dns(hostname)
    is_safe = audit.get("is_safe", audit.get("safe", False))
    
    if not is_safe:
        print(f"[BLOCKED] SSRF Guardrail: Unsafe hostname rejected -> {hostname}")
    else:
        print(f"[PASSED] Domain verified safe -> {hostname}. Safe for agent scraping.")
