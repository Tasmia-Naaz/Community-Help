from pathlib import Path

from werkzeug.utils import secure_filename


ALLOWED_DOCUMENT_TYPES = {
    '.pdf': 'application/pdf',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png'
}


class InvalidDocumentError(ValueError):
    """Raised when an uploaded verification document is invalid."""


def read_validated_document(upload, required, max_bytes):
    if not upload or not upload.filename:
        if required:
            raise InvalidDocumentError('An ID document is required.')
        return None

    extension = Path(upload.filename).suffix.lower()
    if extension not in ALLOWED_DOCUMENT_TYPES:
        raise InvalidDocumentError('Choose a PDF, JPG, JPEG, or PNG file.')

    content = upload.stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise InvalidDocumentError(f'Files must be {max_bytes // (1024 * 1024)} MB or smaller.')
    if not content:
        raise InvalidDocumentError('The selected file is empty.')

    if extension == '.pdf':
        valid_content = content.startswith(b'%PDF-') and b'%%EOF' in content[-2048:]
    elif extension == '.png':
        valid_content = content.startswith(b'\x89PNG\r\n\x1a\n') and b'IEND' in content[-16:]
    else:
        valid_content = content.startswith(b'\xff\xd8\xff') and content.endswith(b'\xff\xd9')

    if not valid_content:
        raise InvalidDocumentError('The file contents do not match a valid supported document.')

    return {
        'content': content,
        'extension': extension,
        'content_type': ALLOWED_DOCUMENT_TYPES[extension],
        'filename': secure_filename(Path(upload.filename).name)[:255] or f'document{extension}',
        'size': len(content)
    }
