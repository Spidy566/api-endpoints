"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Added /sftp_upload and /sftp_download    | 17-02-2026 | vishal
---------------------------------------------------------------------------
"""
from fastapi import APIRouter
from modules.sftp import schemas, services

router = APIRouter()

@router.post(
    "/sftp_upload",
    summary="SFTP Upload",
    description="Uploads a Base64 encoded file to a remote SFTP server.",
    response_model=schemas.SftpUploadResponse
)
async def sftp_upload(payload: schemas.SftpUploadRequest):
    return services.upload_to_sftp(payload)

@router.post(
    "/sftp_download",
    summary="SFTP Download Folder",
    description="Deletes specific files provided in the list, and downloads the remaining files from the remote directory as Base64.",
    response_model=schemas.SftpDownloadResponse
)
async def sftp_download(payload: schemas.SftpDownloadRequest):
    return services.download_folder_from_sftp(payload)