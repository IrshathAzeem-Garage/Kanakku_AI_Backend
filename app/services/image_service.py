import os
import uuid
import hashlib
from typing import Tuple
from fastapi import UploadFile, HTTPException, status
from PIL import Image
import io

from app.config import settings
from app.utils.logger import logger

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


class ImageProcessingResult:
    def __init__(
        self,
        request_id: str,
        image_id: str,
        saved_filename: str,
        file_path: str,
        relative_url: str,
        file_size_bytes: int,
        content_type: str,
        sha256_hash: str,
        original_filename: str
    ):
        self.request_id = request_id
        self.image_id = image_id
        self.saved_filename = saved_filename
        self.file_path = file_path
        self.relative_url = relative_url
        self.file_size_bytes = file_size_bytes
        self.content_type = content_type
        self.sha256_hash = sha256_hash
        self.original_filename = original_filename



def process_and_save_upload(
    upload_file: UploadFile,
    request_id: str
) -> ImageProcessingResult:
    """
    Validates, hashes, assigns unique UUID, and stores the image safely.
    Strictly avoids reusing old paths or cached files.
    """
    if not upload_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename."
        )

    _, ext = os.path.splitext(upload_file.filename)
    ext = ext.lower()
    
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image extension '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Read binary bytes
    file_bytes = upload_file.file.read()
    file_size = len(file_bytes)
    
    logger.info(
        f"Received image: filename='{upload_file.filename}' size={file_size} bytes request_id='{request_id}'"
    )

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded image file is empty."
        )

    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image size ({file_size / (1024*1024):.1f}MB) exceeds limit of {settings.MAX_FILE_SIZE_MB}MB."
        )

    # Compute SHA-256 hash for duplicate detection
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()

    # Validate image integrity with PIL
    try:
        with Image.open(io.BytesIO(file_bytes)) as img:
            img.verify()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or corrupted image file: {str(e)}"
        )

    # Generate unique UUID for this image (NEVER reuse ledger.jpg or old filenames)
    image_id = str(uuid.uuid4())
    unique_filename = f"{image_id}{ext}"
    content_type = upload_file.content_type or f"image/{ext.lstrip('.').replace('jpg', 'jpeg')}"

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    destination_path = os.path.join(settings.UPLOAD_DIR, unique_filename)

    logger.info(
        f"Processing image: image_id='{image_id}' unique_path='{destination_path}' request_id='{request_id}'"
    )

    with open(destination_path, "wb") as f:
        f.write(file_bytes)

    relative_url = f"/uploads/{unique_filename}"

    return ImageProcessingResult(
        request_id=request_id,
        image_id=image_id,
        saved_filename=unique_filename,
        file_path=destination_path,
        relative_url=relative_url,
        file_size_bytes=file_size,
        content_type=content_type,
        sha256_hash=sha256_hash,
        original_filename=upload_file.filename
    )

