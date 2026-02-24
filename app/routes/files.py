from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
import os
from typing import Optional
from app.services import supabase_storage
from app.core.config import settings

router = APIRouter(prefix="/api/files", tags=["files"])

PY_API_KEY = os.environ.get('PYTHON_API_KEY') or os.environ.get('VITE_PYTHON_API_KEY')
DEV_ALLOW_INSECURE = os.environ.get('DEV_ALLOW_INSECURE_WRITES', 'false').lower() in ('1','true','yes')

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if PY_API_KEY and x_api_key == PY_API_KEY:
        return True
    if DEV_ALLOW_INSECURE:
        return True
    raise HTTPException(status_code=401, detail='Unauthorized')

@router.post('/upload')
async def upload_file(
    file: UploadFile = File(...),
    bucket: str = Form('property-images'),
    folder: Optional[str] = Form(None),
    property_id: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
    room_type: Optional[str] = Form(None),
    x_api_key=Depends(verify_api_key)
):
    # Basic validation
    filename = file.filename
    content = await file.read()
    content_type = file.content_type

    # sanitize bucket
    allowed_buckets = ['property-images','profile-images','documents','images','uploads']
    if bucket not in allowed_buckets:
        raise HTTPException(status_code=400, detail='Invalid bucket')

    # generate path
    import time, random
    timestamp = int(time.time()*1000)
    rand = random.randint(1000,9999)
    # keep folder structure if provided
    path_prefix = folder.strip('/') if folder else ''
    ext = filename.split('.')[-1] if '.' in filename else 'bin'
    path = f"{path_prefix}/{timestamp}-{rand}.{ext}" if path_prefix else f"{timestamp}-{rand}.{ext}"

    # upload bytes using service helper
    result = supabase_storage.upload_file(bucket, path, content, content_type)
    if result.get('error'):
        raise HTTPException(status_code=500, detail=f"Upload failed: {result.get('text')}")

    public_url = result.get('public_url')

    # Persist DB record depending on bucket
    db_record = None
    if bucket == 'property-images' and property_id:
        payload = {
            'property_id': property_id,
            'url': public_url,
            'path': result.get('path'),
            'uploaded_by': user_id
        }
        db_record = supabase_storage.insert_row('property_images', payload)
    elif bucket == 'documents' and property_id:
        payload = {
            'entity_type': 'property',
            'entity_id': property_id,
            'file_path': result.get('path'),
            'file_url': public_url,
            'uploaded_by': user_id
        }
        db_record = supabase_storage.insert_row('documents', payload)
    elif bucket == 'profile-images' and user_id:
        # Update user profile via PostgREST (upsert simplified via insert_row may not update; replace with PATCH if needed)
        payload = {'id': user_id, 'profile_image_url': public_url}
        db_record = supabase_storage.insert_row('users', payload)

    return JSONResponse({
        'success': True,
        'url': public_url,
        'path': result.get('path'),
        'db': db_record
    })

@router.delete('/delete')
async def delete_file(bucket: str, path: str, x_api_key=Depends(verify_api_key)):
    # Validate
    allowed_buckets = ['property-images','profile-images','documents','images','uploads']
    if bucket not in allowed_buckets:
        raise HTTPException(status_code=400, detail='Invalid bucket')

    res = supabase_storage.delete_file(bucket, path)
    if res.get('error'):
        raise HTTPException(status_code=500, detail='Delete failed')

    return {'success': True}

@router.get('/list')
async def list_files(bucket: str, prefix: Optional[str] = None, limit: int = 100, x_api_key=Depends(verify_api_key)):
    res = supabase_storage.list_files(bucket, prefix, limit)
    if res.get('error'):
        raise HTTPException(status_code=500, detail='List failed')
    return {'success': True, 'files': res.get('files')}