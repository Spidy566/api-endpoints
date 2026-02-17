"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Added backup upload and retrieval        | 13-06-2025 | senthil
---------------------------------------------------------------------------
"""

from fastapi import APIRouter, UploadFile, File
from modules.backup import schemas, services

router = APIRouter()

@router.post(
    "/backup",
    summary="Upload Backup File",
    description="Uploads a file to the server's local backup directory.",
    response_model=schemas.BackupUploadResponse,
)
async def upload_backup_file(file: UploadFile = File(..., title="",  description="The binary file to upload.")):
    return services.save_backup_file(file)


@router.post(
    "/getbackup",
    summary="Retrieve Backup File",
    description="Downloads a file from the server given its path. Uses POST for legacy client compatibility.",
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "The requested file as a binary stream."
        },
        404: {"description": "File not found."}
    }
)
async def get_backup_file(req: schemas.BackupRetrieveRequest):
    return services.get_backup_file(req.file_path)