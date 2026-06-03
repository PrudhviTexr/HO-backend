"""Self-service account deletion: remove user data and the users row."""
from typing import Any, Dict, List, Tuple

from ..db.supabase_client import db

# (table, filter column) — best-effort cleanup before deleting the user
_USER_RELATED_DELETES: List[Tuple[str, str]] = [
    ("refresh_tokens", "user_id"),
    ("user_roles", "user_id"),
    ("email_verification_tokens", "user_id"),
    ("user_approvals", "user_id"),
    ("agent_bank_details", "agent_id"),
    ("agent_profiles", "user_id"),
    ("seller_profiles", "user_id"),
    ("saved_properties", "user_id"),
    ("property_views", "user_id"),
    ("notifications", "user_id"),
    ("agent_assignments", "agent_id"),
    ("agent_assignments", "user_id"),
    ("documents", "uploaded_by"),
    ("inquiries", "user_id"),
    ("inquiries", "agent_id"),
    ("inquiries", "assigned_agent_id"),
    ("bookings", "user_id"),
    ("bookings", "agent_id"),
]

_PROPERTY_OWNER_COLUMNS = ("owner_id", "seller_id", "added_by")


async def _safe_delete(table: str, column: str, value: str) -> None:
    try:
        await db.delete(table, {column: value})
    except Exception as exc:
        print(f"[ACCOUNT_DELETE] Skip {table}.{column}={value}: {exc}")


async def delete_user_account(user_id: str) -> Dict[str, Any]:
    """Delete all related rows for a user, then remove the users record."""
    for table, column in _USER_RELATED_DELETES:
        await _safe_delete(table, column, user_id)

    for column in _PROPERTY_OWNER_COLUMNS:
        try:
            props = await db.select("properties", filters={column: user_id})
            for prop in props or []:
                prop_id = prop.get("id")
                if prop_id:
                    await _safe_delete("properties", "id", prop_id)
        except Exception as exc:
            print(f"[ACCOUNT_DELETE] Properties by {column}: {exc}")

    try:
        props = await db.select(
            "properties",
            filters={"or": [{"assigned_agent_id": user_id}, {"agent_id": user_id}]},
        )
        for prop in props or []:
            prop_id = prop.get("id")
            if prop_id:
                try:
                    await db.update(
                        "properties",
                        {"assigned_agent_id": None, "agent_id": None},
                        {"id": prop_id},
                    )
                except Exception:
                    pass
    except Exception as exc:
        print(f"[ACCOUNT_DELETE] Unassign agent on properties: {exc}")

    await db.delete("users", {"id": user_id})
    return {"success": True, "message": "Account deleted successfully"}
