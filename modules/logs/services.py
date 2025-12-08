import os
from collections import defaultdict
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from core.config import LOGS_DIR, logger

request_counts = defaultdict(int)
request_logs = defaultdict(list)

def get_endpoint_logs(endpoint_path: str, request: Request) -> dict:
    path = "/" + endpoint_path.strip("/")
    logs = []
    for entry in request_logs.get(path, []):
        log_copy = entry.copy()
        if log_copy.get("request_file"):
            log_copy["request_file_url"] = str(request.base_url) + f"logs/files/{Path(log_copy['request_file']).name}"
        if log_copy.get("response_file"):
            log_copy["response_file_url"] = str(request.base_url) + f"logs/files/{Path(log_copy['response_file']).name}"
        logs.append(log_copy)
    return {"endpoint": path, "logs": logs, "request_count": len(logs)}

def download_log_file(filename: str):
    file_path = LOGS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path), filename=filename, media_type="application/json")