"""Property management intake (public submit + admin list/update)."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List

from ..core.security import require_admin_or_api_key
from ..services.email import send_email
from ..services.property_management_store import (
    create_request,
    list_requests,
    update_status,
)

router = APIRouter()


class PropertyManagementRequestIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=200)
    phone: str = Field(..., min_length=8, max_length=20)
    property_type: str = Field(..., min_length=1, max_length=80)
    listing_type: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    bedrooms: Optional[str] = None
    bathrooms: Optional[str] = None
    area_sqft: Optional[str] = None
    furnishing: Optional[str] = None
    expected_rent: Optional[str] = None
    expected_price: Optional[str] = None
    services_needed: Optional[List[str]] = None
    preferred_contact_time: Optional[str] = None
    notes: Optional[str] = None


class PropertyManagementStatusUpdate(BaseModel):
    status: str


_FIELD_LABELS = {
    "name": "Name",
    "email": "Email",
    "phone": "Phone",
    "property_type": "Property type",
    "listing_type": "Listing type",
    "state": "State",
    "district": "District",
    "city": "City",
    "address": "Address",
    "pincode": "Pincode",
    "bedrooms": "BHK / bedrooms",
    "bathrooms": "Bathrooms",
    "balconies": "Balconies",
    "area_sqft": "Built-up area (sq ft)",
    "carpet_area_sqft": "Carpet area (sq ft)",
    "furnishing": "Furnishing",
    "floor": "Floor",
    "total_floors": "Total floors",
    "facing": "Facing",
    "bhk_config": "BHK config",
    "project_name": "Project / society",
    "building_name": "Building name",
    "flat_number": "Flat number",
    "tower_block": "Tower / block",
    "plot_area_sqft": "Plot area (sq ft)",
    "floor_count": "Floors in house",
    "private_garden": "Private garden",
    "commercial_subtype": "Commercial type",
    "parking_spaces": "Parking spaces",
    "washrooms": "Washrooms",
    "suitable_for": "Suitable for",
    "shell_type": "Shell type",
    "power_backup": "Power backup",
    "area_sqyd": "Area (sq yd)",
    "area_acres": "Area (acres)",
    "plot_dimensions": "Plot dimensions",
    "land_type": "Land type",
    "road_access": "Road access",
    "boundary_fencing": "Boundary fencing",
    "corner_plot": "Corner plot",
    "water_source": "Water source",
    "total_area_acres": "Total land (acres)",
    "expected_rent": "Expected rent",
    "expected_price": "Expected price",
    "preferred_contact_time": "Preferred contact time",
    "notes": "Notes",
}

_SKIP_EMAIL_KEYS = {"id", "status", "created_at", "updated_at", "services_needed"}


def _format_admin_html(payload: dict) -> str:
    services = payload.get("services_needed") or []
    if isinstance(services, list):
        services_str = ", ".join(services) if services else "—"
    else:
        services_str = str(services)

    rows = []
    for key, label in _FIELD_LABELS.items():
        val = payload.get(key)
        if val is not None and str(val).strip() != "":
            rows.append((label, val))
    for key, val in payload.items():
        if key in _FIELD_LABELS or key in _SKIP_EMAIL_KEYS:
            continue
        if val is not None and str(val).strip() != "":
            rows.append((key.replace("_", " ").title(), val))
    rows.append(("Services needed", services_str))
    trs = "".join(
        f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:600;width:35%">{k}</td>'
        f'<td style="padding:8px;border:1px solid #ddd">{v or "—"}</td></tr>'
        for k, v in rows
    )
    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#333">
      <h2 style="color:#162e5a">New Property Management Request</h2>
      <table style="border-collapse:collapse;width:100%;max-width:640px">{trs}</table>
    </body></html>
    """


@router.post("/property-management-request")
async def submit_property_management_request(body: PropertyManagementRequestIn):
    try:
        payload = body.model_dump()
        record = await create_request(payload)

        admin_html = _format_admin_html(payload)
        try:
            await send_email(
                to="info@homeandown.com",
                subject=f"Property Management Request — {body.name}",
                html=admin_html,
            )
        except Exception as mail_err:
            print(f"[PM] Admin email failed: {mail_err}")

        if body.email:
            user_html = f"""
            <html><body style="font-family:Arial,sans-serif;color:#333">
              <p>Hello {body.name},</p>
              <p>Thank you for your property management enquiry with <strong>Home & Own</strong>.</p>
              <p>Our team has received your details and will contact you shortly.</p>
              <p>Best regards,<br>Home & Own Team</p>
            </body></html>
            """
            try:
                await send_email(
                    to=body.email,
                    subject="We received your property management request — Home & Own",
                    html=user_html,
                )
            except Exception as mail_err:
                print(f"[PM] User confirmation email failed: {mail_err}")

        return {
            "success": True,
            "message": "Thank you! Our team will contact you soon.",
            "id": record.get("id"),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PM] Submit error: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit request")


@router.get("/property-management-requests")
async def admin_list_property_management_requests(
    _=Depends(require_admin_or_api_key),
):
    try:
        rows = await list_requests()
        return {"success": True, "requests": rows, "count": len(rows)}
    except Exception as e:
        print(f"[PM] List error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load requests")


@router.patch("/property-management-requests/{request_id}")
async def admin_update_property_management_request(
    request_id: str,
    body: PropertyManagementStatusUpdate,
    _=Depends(require_admin_or_api_key),
):
    allowed = {"new", "contacted", "in_progress", "closed"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(sorted(allowed))}")
    updated = await update_status(request_id, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"success": True, "request": updated}
