import os
import sys
import time
import json
import socket
import urllib.request
import urllib.error

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
HEALTH_URL = "http://127.0.0.1:8000/api/v1/health"
CHECK_INTERVAL_SECONDS = 30
FAILURE_THRESHOLD = 2

def send_discord_alert(title: str, description: str, color: int):
    if not DISCORD_WEBHOOK_URL:
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
        headers={"Content-Type": "application/json", "User-Agent": "BristleconeWatchdog/1.2"}
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Failed to transmit Discord alert: {e}", file=sys.stderr)

def check_gateway() -> tuple[bool, str]:
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "BristleconeInternalWatchdog/1.2"})
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("status") == "healthy":
                    return True, "OK"
                return False, f"Unexpected body payload: {data}"
            return False, f"HTTP Status {response.status}"
    except Exception as e:
        return False, f"Exception: {type(e).__name__} - {e}"

def main():
    consecutive_failures = 0
    is_currently_down = False
    print(f"Bristlecone Sentinel Watchdog running against {HEALTH_URL}...")

    while True:
        healthy, reason = check_gateway()

        if healthy:
            if is_currently_down:
                send_discord_alert(
                    title="✅ Bristlecone API Gateway RECOVERED",
                    description=f"Endpoint `{HEALTH_URL}` returned `200 OK` (status: healthy).",
                    color=3066993  # Green
                )
                is_currently_down = False
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Healthcheck failed ({consecutive_failures}/{FAILURE_THRESHOLD}): {reason}")
            if consecutive_failures >= FAILURE_THRESHOLD and not is_currently_down:
                send_discord_alert(
                    title="🚨 Bristlecone API Gateway DOWN",
                    description=f"Healthcheck failed {consecutive_failures} consecutive times on `{HEALTH_URL}`.\n**Reason:** `{reason}`",
                    color=15158332  # Red
                )
                is_currently_down = True

        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
