"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Models for SFTP auth and file transfers  | 17-02-2026 | vishal
---------------------------------------------------------------------------
"""
from pydantic import BaseModel, Field
from typing import List, Optional

class SftpUploadRequest(BaseModel):
    host: str = Field(..., description="SFTP server hostname or IP.")
    port: int = Field(..., description="SFTP port.")
    username: str = Field(..., description="SFTP username.")
    password: str = Field(..., description="SFTP password.")
    remote_dir: str = Field(..., description="The remote directory path to upload to.")
    filename: str = Field(..., description="The name to save the file as.")
    content: str = Field(..., description="Base64 encoded content of the file.")

class SftpUploadResponse(BaseModel):
    status: str = Field(..., description="The status of the upload operation (e.g., success, error).", example="success")
    message: str = Field(..., description="A human-readable message describing the result.", example="File uploaded")
    size_bytes: int = Field(..., description="Size of the uploaded file in bytes.")

class SftpDownloadRequest(BaseModel):
    host: str = Field(..., description="SFTP server hostname or IP.")
    port: int = Field(..., description="SFTP port.")
    username: str = Field(..., description="SFTP username.")
    password: str = Field(..., description="SFTP password.")
    remote_dir: str = Field(..., description="The remote directory path to download files from.")
    delete_after_download: bool = Field(default=False, description="If true, deletes files from the server after successful download.")

class SftpFileItem(BaseModel):
    filename: str = Field(..., description="The name of the file retrieved from the server.")
    status: str = Field(..., description="Individual file processing status (e.g., downloaded, failed).")
    size_bytes: Optional[int] = Field(None, description="Size of the file in bytes. Null if processing failed.")
    content_base64: Optional[str] = Field(None, description="The Base64 encoded content of the downloaded file.")
    error: Optional[str] = Field(None, description="Specific error message if the individual file failed.")

class SftpDownloadResponse(BaseModel):
    status: str = Field(..., description="Overall status of the bulk download operation.")
    remote_dir: str = Field(..., description="The remote directory path where the download was initiated.")
    downloaded_count: int = Field(..., description="Total number of files successfully downloaded.")
    files: List[SftpFileItem] = Field(..., description="A list containing the details and content of each file processed.")