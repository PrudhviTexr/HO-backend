from fastapi import APIRouter, HTTPException, Depends
from ..models.schemas import EmailRequest
from ..services.email import send_email
from ..core.security import require_api_key

router = APIRouter()

@router.post("/send")
async def send(email: EmailRequest, _: None = Depends(require_api_key)):
    try:
        print(f"[PY-API] Sending email -> to={email.to} subject={email.subject}")
        await send_email(email.to, email.subject, email.html)
        print("[PY-API] Email send completed ok")
        return {"ok": True}
    except Exception as e:
        print(f"[PY-API] Email send failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
