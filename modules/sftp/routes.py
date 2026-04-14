"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Separated download and delete endpoints  | 18-03-2026 | vishal
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
    description="Downloads all files from the remote directory as Base64.",
    response_model=schemas.SftpDownloadResponse
)
async def sftp_download(payload: schemas.SftpDownloadRequest):
    return services.download_folder_from_sftp(payload)

@router.post(
    "/sftp_delete",
    summary="SFTP Delete File",
    description="Deletes a specific file from the remote directory.",
    response_model=schemas.SftpDeleteResponse
)
async def sftp_delete(payload: schemas.SftpDeleteRequest):
    return services.delete_file_from_sftp(payload)