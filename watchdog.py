import os
import sys
import time
import json
import socket
import urllib.request
import urllib.error

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
HEALTH_URL = "https://api.bristleconelogic.com/api/v1/health"
CHECK_INTERVAL_SECONDS = 30

def send_discord_alert(title: str, description: str, color: int):
    if not DISCORD_WEBHOOK_URL:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Discord Webhook URL not set. Alert: {title} - {description}")
        return

    payload = {
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "footer": {"text": f"Node: {socket.gethostname()} | Bristlecone Sentinel"},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }]
    }

    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "BristleconeWatchdog/1.0"}
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Failed to transmit Discord alert: {e}", file=sys.stderr)

def check_gateway() -> bool:
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "BristleconeInternalWatchdog/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("status") == "healthy"
    except Exception:
        return False
    return False

def main():
    print(f"Bristlecone Sentinel Watchdog running. Polling {HEALTH_URL} every {CHECK_INTERVAL_SECONDS}s...")
    
    # Send startup confirmation to Discord
    send_discord_alert(
        title="🛡️ Bristlecone Sentinel Online",
        description=f"Host watchdog active on `{socket.gethostname()}`. Polling `{HEALTH_URL}` every 30 seconds.",
        color=3447003  # Blue
    )

    last_state_healthy = True

    while True:
        is_healthy = check_gateway()

        if not is_healthy and last_state_healthy:
            send_discord_alert(
                title="🚨 Bristlecone API Gateway DOWN",
                description=f"Healthcheck failed on `{HEALTH_URL}`.\nInvestigate via `docker compose ps` and `docker compose logs api`.",
                color=15158332  # Red
            )
            last_state_healthy = False
        elif is_healthy and not last_state_healthy:
            send_discord_alert(
                title="✅ Bristlecone API Gateway RECOVERED",
                description=f"Endpoint `{HEALTH_URL}` is returning `200 OK` (status: healthy).",
                color=3066993   # Green
            )
            last_state_healthy = True

        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
