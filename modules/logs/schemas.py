from pydantic import BaseModel
from typing import List, Optional

class LogEntry(BaseModel):
    api_name: str
    requested_date: str
    requested_url: str
    requested_ip: Optional[str] = None
    request_file: Optional[str] = None
    response_file: Optional[str] = None
    request_file_url: Optional[str] = None
    response_file_url: Optional[str] = None

class LogResponse(BaseModel):
    endpoint: str
    request_count: int
    logs: List[LogEntry]