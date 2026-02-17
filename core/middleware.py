"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Global request/response body logging     | 07-01-2026 | vishal
---------------------------------------------------------------------------
"""
import uuid
from datetime import datetime
from fastapi import Request
from core.config import logger, LOGS_DIR
from modules.logs.services import request_counts, request_logs

async def log_and_count_requests(request: Request, call_next):
    """Global middleware to log requests and responses to disk and memory."""
    path = request.url.path

    if path.startswith("/static") or path == "/favicon.ico":
        return await call_next(request)

    request_counts[path] += 1
    req_file = None
    resp_file = None

    try:
        content_type = request.headers.get("content-type", "")
        is_binary = any(t in content_type for t in ["multipart/form-data", "application/pdf", "image/", "application/octet-stream"])
        req_body = await request.body()
        if req_body and not is_binary:
            try:
                req_json = req_body.decode("utf-8")
                req_filename = f"{uuid.uuid4()}_request.json"
                req_file_path = LOGS_DIR / req_filename
                with open(req_file_path, "w", encoding="utf-8") as f:
                    f.write(req_json)
                req_file = str(req_file_path)
            except UnicodeDecodeError:
                logger.warning(f"Middleware: Body content could not be decoded as UTF-8 for {path}")
        elif is_binary:
            req_file = "BINARY_FILE_UPLOAD_SKIPPED"
    except Exception as e:
        logger.warning(f"Middleware: Failed to log request body: {e}")

    response = await call_next(request)

    try:
        if hasattr(response, 'body_iterator'):
            resp_body = b''
            async for chunk in response.body_iterator:
                resp_body += chunk

            async def new_body_iterator():
                yield resp_body

            response.body_iterator = new_body_iterator()

            try:
                resp_json = resp_body.decode("utf-8")
                resp_filename = f"{uuid.uuid4()}_response.json"
                resp_file_path = LOGS_DIR / resp_filename
                with open(resp_file_path, "w", encoding="utf-8") as f:
                    f.write(resp_json)
                resp_file = str(resp_file_path)
            except UnicodeDecodeError:
                resp_file = "BINARY_RESPONSE_SKIPPED"
                pass
    except Exception as e:
        logger.warning(f"Middleware: Failed to log response body: {e}")

    log_entry = {
        "api_name": path,
        "requested_date": datetime.now().strftime("%d-%b-%Y %I:%M:%S %p"),
        "requested_url": str(request.url),
        "requested_ip": request.client.host if request.client else None,
        "request_file": req_file,
        "response_file": resp_file
    }

    if len(request_logs[path]) > 10000:
        request_logs[path].pop(0)

    request_logs[path].append(log_entry)
    logger.info(f"[MONITOR] {path} - {request.method} - {response.status_code}")

    return response