import json
import re
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/tools", tags=["Developer Tools"])

class JsonRepairRequest(BaseModel):
    malformed_json: str

@router.post("/json-repair")
async def repair_json(payload: JsonRepairRequest):
    raw = payload.malformed_json.strip()
    
    # 1. Normalize unquoted object keys
    fixed = re.sub(r'(?<={|,)\s*([a-zA-Z0-9_]+)\s*:', r'"\1":', raw)
    
    # 2. Fix trailing commas before closing braces
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)

    try:
        parsed = json.loads(fixed)
        valid = True
    except Exception:
        # Fallback sanitize
        fixed = fixed.replace("'", '"')
        try:
            parsed = json.loads(fixed)
            valid = True
        except Exception as e:
            parsed = None
            valid = False

    return {
        "status": "success" if valid else "partial_recovery",
        "original_length": len(raw),
        "repaired_json": parsed if valid else fixed,
        "valid": valid
    }
