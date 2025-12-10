from pydantic import BaseModel, Field

class BackupRetrieveRequest(BaseModel):
    file_path: str = Field(..., title="", description="The full absolute path or relative path of the file to retrieve.")

class BackupUploadResponse(BaseModel):
    success: bool = Field(..., title="", description="Indicates if the file was saved successfully.")
    file_path: str = Field(..., title="", description="The absolute path where the file was saved on the server.")
    filename: str = Field(..., title="", description="The original filename.")