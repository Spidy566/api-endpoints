from pydantic import BaseModel

class TextractStartRequest(BaseModel):
    bucket: str
    file_name: str