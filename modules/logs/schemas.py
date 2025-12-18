from pydantic import BaseModel, Field
from typing import List, Optional

class LogEntry(BaseModel):
    api_name: str = Field(..., title="", description="The specific API route that was accessed.")
    requested_date: str = Field(..., title="", description="Timestamp of the request in 'DD-MMM-YYYY HH:MM:SS AM/PM' format.")
    requested_url: str = Field(..., title="", description="The full URL of the request")
    requested_ip: Optional[str] = Field(default=None, title="", description="The IP address of the client making the request")
    request_file: Optional[str] = Field(default=None, title="", description="Local file path where the raw request body was saved.")
    response_file: Optional[str] = Field(default=None, title="", description="Local file path where the raw response body was saved.")
    request_file_url: Optional[str] = Field(default=None, title="", description="Download URL to retrieve the saved request body.")
    response_file_url: Optional[str] = Field(default=None, title="", description="Download URL to retrieve the saved response body.")

class LogResponse(BaseModel):
    endpoint: str = Field(..., title="", description="The endpoint path being queried.")
    request_count: int = Field(..., title="", description="Total number of requests recorded for this endpoint since server start.")
    logs: List[LogEntry] = Field(..., title="", description="List of log entries for this endpoint.")