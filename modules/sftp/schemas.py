"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Added separate delete models             | 18-03-2026 | vishal
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
    status: str = Field(..., description="The status of the upload operation (e.g., success, error).")
    message: str = Field(..., description="A human-readable message describing the result.")
    size_bytes: int = Field(..., description="Size of the uploaded file in bytes.")

class SftpDownloadRequest(BaseModel):
    host: str = Field(..., description="SFTP server hostname or IP.")
    port: int = Field(..., description="SFTP port.")
    username: str = Field(..., description="SFTP username.")
    password: str = Field(..., description="SFTP password.")
    remote_dir: str = Field(..., description="The remote directory path to download files from.")

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

class SftpDeleteRequest(BaseModel):
    host: str = Field(..., description="SFTP server hostname or IP.")
    port: int = Field(..., description="SFTP port.")
    username: str = Field(..., description="SFTP username.")
    password: str = Field(..., description="SFTP password.")
    remote_dir: str = Field(..., description="The remote directory path where the file exists.")
    filename: str = Field(..., description="The exact filename of the file to delete.")

class SftpDeleteResponse(BaseModel):
    status: str = Field(..., description="The status of the delete operation (e.g., success, error).")
    message: str = Field(..., description="A human-readable message describing the result.")