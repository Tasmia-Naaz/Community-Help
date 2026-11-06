import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)
STORAGE_REQUEST_TIMEOUT_SECONDS = 10


class DocumentStorageError(Exception):
    """Raised when a private verification document cannot be stored or retrieved."""


def _storage_request(method, path, body=None, content_type='application/json'):
    base_url = os.getenv('SUPABASE_URL', '').rstrip('/')
    service_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
    if not base_url or not service_key:
        raise DocumentStorageError(
            'Private document storage is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.'
        )

    data = json.dumps(body).encode('utf-8') if isinstance(body, dict) else body
    request = Request(
        f'{base_url}/storage/v1{path}',
        data=data,
        method=method,
        headers={
            'apikey': service_key,
            'Authorization': f'Bearer {service_key}',
            'Content-Type': content_type
        }
    )
    try:
        with urlopen(request, timeout=STORAGE_REQUEST_TIMEOUT_SECONDS) as response:
            response_body = response.read()
    except HTTPError as exc:
        response_body = exc.read(2048).decode('utf-8', errors='replace').strip()
        if service_key:
            response_body = response_body.replace(service_key, '[REDACTED]')
        logger.error(
            'Supabase Storage returned HTTP %s for %s: %s',
            exc.code,
            method,
            response_body or 'No error details returned.'
        )
        raise DocumentStorageError(
            f'Private document storage rejected the request (HTTP {exc.code}). '
            'Check the Flask terminal for Supabase details.'
        ) from exc
    except (URLError, TimeoutError) as exc:
        logger.error('Supabase Storage is unreachable during %s.', method)
        raise DocumentStorageError('Private document storage is unavailable.') from exc

    if not response_body:
        return {}
    try:
        return json.loads(response_body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DocumentStorageError('Private document storage returned an invalid response.') from exc


def upload_verification_document(path, content, content_type):
    bucket = quote(os.getenv('SUPABASE_STORAGE_BUCKET', 'volunteer-verification-documents'), safe='')
    object_path = quote(path, safe='/')
    _storage_request(
        'POST',
        f'/object/{bucket}/{object_path}',
        body=content,
        content_type=content_type
    )
    return path


def create_document_signed_url(path, expires_in=60):
    bucket = quote(os.getenv('SUPABASE_STORAGE_BUCKET', 'volunteer-verification-documents'), safe='')
    object_path = quote(path, safe='/')
    result = _storage_request(
        'POST',
        f'/object/sign/{bucket}/{object_path}',
        body={'expiresIn': expires_in}
    )
    signed_url = result.get('signedURL')
    if not isinstance(signed_url, str) or not signed_url:
        raise DocumentStorageError('Private document storage did not provide a preview URL.')
    if signed_url.startswith('http://') or signed_url.startswith('https://'):
        return signed_url
    base_url = os.getenv('SUPABASE_URL', '').rstrip('/')
    return f'{base_url}/storage/v1{signed_url if signed_url.startswith("/") else "/" + signed_url}'


def delete_verification_document(path):
    bucket = quote(os.getenv('SUPABASE_STORAGE_BUCKET', 'volunteer-verification-documents'), safe='')
    object_path = quote(path, safe='/')
    _storage_request('DELETE', f'/object/{bucket}/{object_path}')
