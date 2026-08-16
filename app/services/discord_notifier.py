import httpx
import os
import logging
from datetime import datetime

logger = logging.getLogger("uvicorn.error")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

async def send_discord_alert(title: str, description: str, color: int = 3447003, fields: list = None):
    if not DISCORD_WEBHOOK_URL:
        return
    
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields or [],
        "timestamp": datetime.utcnow().isoformat()
    }
    
    payload = {"embeds": [embed]}
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        logger.error(f"[Discord] Failed to send webhook alert: {e}")
