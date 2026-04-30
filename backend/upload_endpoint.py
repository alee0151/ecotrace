"""
upload_endpoint.py
==================

Standalone FastAPI router for the POST /api/upload endpoint.

Import and include this router in main.py:

    from upload_endpoint import router as upload_router
    app.include_router(upload_router)

The endpoint accepts a single PDF file, saves it to a configurable UPLOAD_DIR,
and returns a JSON receipt. The saved file can later be picked up by the
report / LLM extraction layer using the returned filename.

Required .env:
    UPLOAD_DIR   (optional, defaults to ./uploads)
    MAX_UPLOAD_MB (optional, defaults to 10)
"""

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

router = APIRouter()

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024  # default 10 MB

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/api/upload")
async def upload_document(file: UploadFile = File(...)) -> JSONResponse:
    """
    Accept a PDF document uploaded by the frontend (ConsumerSearch page).

    Validation:
    - Content-type must be application/pdf.
    - File size must not exceed MAX_UPLOAD_MB (default 10 MB).

    Returns:
    {
        "message": "Upload successful",
        "filename": "<saved filename on disk>",
        "original_name": "<original client filename>"
    }
    """
    # Validate content-type
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Only PDFs are accepted.",
        )

    # Read with size guard
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {os.getenv('MAX_UPLOAD_MB', '10')} MB limit.",
        )

    # Generate a unique filename to avoid collisions
    unique_id = uuid.uuid4().hex
    safe_name = Path(file.filename or "upload").name  # strip any path components
    saved_name = f"{unique_id}_{safe_name}"
    dest = UPLOAD_DIR / saved_name

    dest.write_bytes(content)

    return JSONResponse(
        status_code=200,
        content={
            "message": "Upload successful",
            "filename": saved_name,
            "original_name": file.filename,
        },
    )
