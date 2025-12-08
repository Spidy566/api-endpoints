from pydantic import BaseModel

class BackupRequest(BaseModel):
    file_path: str