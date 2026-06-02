"""Persist property management intake requests (DB + JSON file fallback)."""

import json
import uuid
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..db.supabase_client import db

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_FILE = DATA_DIR / "property_management_requests.json"
TABLE = "property_management_requests"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _load_file() -> List[Dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_file(rows: List[Dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)


async def create_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    record = {
        "id": str(uuid.uuid4()),
        "status": "new",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        **payload,
    }

    try:
        inserted = await db.insert(TABLE, {k: v for k, v in record.items() if v is not None})
        if inserted:
            return inserted[0] if isinstance(inserted, list) else inserted
    except Exception as e:
        print(f"[PM_STORE] DB insert failed, using file fallback: {e}")

    rows = _load_file()
    rows.insert(0, record)
    _save_file(rows)
    return record


async def list_requests(limit: int = 500) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    try:
        db_rows = await db.admin_select(
            TABLE,
            limit=limit,
            order_by="created_at",
            ascending=False,
        )
        for row in db_rows or []:
            merged[str(row.get("id"))] = row
    except Exception as e:
        print(f"[PM_STORE] DB list failed: {e}")

    for row in _load_file():
        rid = str(row.get("id"))
        if rid not in merged:
            merged[rid] = row

    rows = list(merged.values())
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows[:limit]


async def update_status(request_id: str, status: str) -> Optional[Dict[str, Any]]:
    updated_at = _now_iso()

    try:
        result = await db.update(
            TABLE,
            {"status": status, "updated_at": updated_at},
            {"id": request_id},
        )
        if result:
            return result[0] if isinstance(result, list) else result
    except Exception as e:
        print(f"[PM_STORE] DB update failed: {e}")

    rows = _load_file()
    found = None
    for row in rows:
        if str(row.get("id")) == request_id:
            row["status"] = status
            row["updated_at"] = updated_at
            found = row
            break
    if found:
        _save_file(rows)
    return found
