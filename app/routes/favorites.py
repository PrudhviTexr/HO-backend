from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional
import os
from app.services import supabase_storage

router = APIRouter(prefix="/api/property-favorites", tags=["property-favorites"])

PY_API_KEY = os.environ.get('PYTHON_API_KEY') or os.environ.get('VITE_PYTHON_API_KEY')
DEV_ALLOW_INSECURE = os.environ.get('DEV_ALLOW_INSECURE_WRITES', 'false').lower() in ('1','true','yes')

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if PY_API_KEY and x_api_key == PY_API_KEY:
        return True
    if DEV_ALLOW_INSECURE:
        return True
    raise HTTPException(status_code=401, detail='Unauthorized')

@router.get('')
asyn...