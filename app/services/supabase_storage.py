from __future__ import annotations

import os
import requests
from typing import Optional, Dict, Any

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://ajymffxpunxoqcmunohx.supabase.co')
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    # In production these MUST be set; library will still import in dev but operations will fail gracefully
    pass

STORAGE_BASE = SUPABASE_URL.rstrip('/') + '/storage/v1'
REST_BASE = SUPABASE_URL.rstrip('/') + '/rest/v1'

HEADERS = {
    'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
    'apikey': SUPABASE_SERVICE_ROLE_KEY
}

def upload_file(bucket: str, path: str, file_bytes: bytes, content_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Upload raw bytes to Supabase Storage using the service role key.
    Returns a dict with keys: public_url, path
    """
    url = f"{STORAGE_BASE}/object/{bucket}/{path}"
    headers = HEADERS.copy()
    if content_type:
        headers['Content-Type'] = content_type

    resp = requests.put(url, data=file_bytes, headers=headers)
    if not resp.ok:
        return {'error': True, 'status_code': resp.status_code, 'text': resp.text}

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"
    return {'error': False, 'public_url': public_url, 'path': path}

def delete_file(bucket: str, path: str) -> Dict[str, Any]:
    url = f"{STORAGE_BASE}/object/{bucket}/{path}"
    resp = requests.delete(url, headers=HEADERS)
    if not resp.ok:
        return {'error': True, 'status_code': resp.status_code, 'text': resp.text}
    return {'error': False}

def list_files(bucket: str, prefix: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    """List files under a prefix in a bucket."""
    url = f"{STORAGE_BASE}/object/list/{bucket}"
    payload = { }
    if prefix:
        payload['prefix'] = prefix
    payload['limit'] = limit

    resp = requests.post(url, headers=HEADERS, json=payload)
    if not resp.ok:
        return {'error': True, 'status_code': resp.status_code, 'text': resp.text}
    return {'error': False, 'files': resp.json()}


# Helper functions to interact with PostgREST for simple inserts/queries when needed

def insert_row(table: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a row into Supabase via REST API and return representation."""
    url = f"{REST_BASE}/{table}"
    headers = HEADERS.copy()
    headers['Content-Type'] = 'application/json'
    headers['Prefer'] = 'return=representation'

    resp = requests.post(url, headers=headers, json=payload)
    if not resp.ok:
        return {'error': True, 'status_code': resp.status_code, 'text': resp.text}
    return {'error': False, 'rows': resp.json()}

def delete_row(table: str, where: str) -> Dict[str, Any]:
    """Delete rows using PostgREST filter. where should be like 'id=eq.<uuid>'"""
    url = f"{REST_BASE}/{table}?{where}"
    headers = HEADERS.copy()
    resp = requests.delete(url, headers=headers)
    if not resp.ok:
        return {'error': True, 'status_code': resp.status_code, 'text': resp.text}
    return {'error': False, 'rows_affected': resp.status_code}


# Example: get public URL helper
def get_public_url(bucket: str, path: str) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"