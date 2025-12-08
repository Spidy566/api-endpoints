from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class ReportRequest(BaseModel):
    template_file: str
    report_name: str
    records: list[Dict[str, Any]]

class MergeFileItem(BaseModel):
    filename: str = "file"
    mimetype: str
    base64content: str

class MergeResponse(BaseModel):
    outputfilename: str
    outputmimetype: str
    outputbase64content: str
