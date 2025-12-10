import subprocess
import uvicorn
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from core.config import logger, LOGS_DIR, CERT_DIR
from core.dependencies import process_pool_executor, thread_pool_executor

from modules.ai import routes as ai_routes
from modules.aws import routes as aws_routes
from modules.backup import routes as backup_routes
from modules.documents import routes as documents_routes
from modules.email import routes as email_routes
from modules.logs import routes as logs_routes
from modules.signature import routes as signature_routes

from modules.logs.services import request_counts, request_logs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle startup and shutdown logic.
    Checks for unoconv dependency and manages thread/process pools.
    """
    try:
        check_command = ["/usr/bin/python3", "/usr/bin/unoconv", "--version"]
        result = subprocess.run(check_command, check=True, capture_output=True, text=True)
        print(f"--- Found unoconv. Version: {result.stdout.strip()} ---")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.warning(
            f"WARNING: The 'unoconv' command could not be found or executed. PDF conversion may fail. Details: {e}")

    yield

    print("--- Shutting down executors ---")
    process_pool_executor.shutdown(wait=True)
    thread_pool_executor.shutdown(wait=True)
    print("--- [FastAPI] Cleanup complete ---")

tags_metadata = [
    {
        "name": "AI",
        "description": "Integration with **OpenAI** models for intelligent document extraction, visiting card scanning, and generic OCR tasks.",
    },
    {
        "name": "AWS",
        "description": "Integration with **AWS S3** for storage and **AWS Textract** for enterprise-grade OCR. Includes specific parsers for Vendor Invoices, Expenses, and Cargo Manifests.",
    },
    {
        "name": "Signature",
        "description": "Adobe-compatible **Digital Signature** services. Supports PFX certificates, visible/invisible signing, and validation.",
    },
    {
        "name": "Documents",
        "description": "Utilities for PDF merging, report generation (DOCX templating), and file conversion.",
    },
    {
        "name": "Email",
        "description": "Tools to parse email files (.eml/.msg), extract attachments, and send emails via SMTP.",
    },
    {
        "name": "Backup",
        "description": "Simple file backup and retrieval endpoints.",
    },
    {
        "name": "Logs",
        "description": "Access to API request/response logs for auditing and debugging.",
    },
]

app = FastAPI(
    title="Fresa Local testing",
    description="Full documentation of API for Documents, AI, and Integrations.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
    openapi_tags=tags_metadata,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_and_count_requests(request: Request, call_next):
    path = request.url.path

    if path != "/custom_logic":
        request_counts[path] += 1
        req_body = None
        req_file = None

        try:
            req_body = await request.body()
            if req_body:
                req_json = req_body.decode("utf-8")
                req_filename = f"{uuid.uuid4()}_request.json"
                req_file_path = LOGS_DIR / req_filename
                with open(req_file_path, "w", encoding="utf-8") as f:
                    f.write(req_json)
                req_file = str(req_file_path)
        except Exception:
            pass

        response = await call_next(request)

        resp_file = None
        try:
            if hasattr(response, 'body_iterator'):
                resp_body = b''
                async for chunk in response.body_iterator:
                    resp_body += chunk

                async def new_body_iterator():
                    yield resp_body

                response.body_iterator = new_body_iterator()

                resp_json = resp_body.decode("utf-8")
                resp_filename = f"{uuid.uuid4()}_response.json"
                resp_file_path = LOGS_DIR / resp_filename
                with open(resp_file_path, "w", encoding="utf-8") as f:
                    f.write(resp_json)
                resp_file = str(resp_file_path)
        except Exception:
            pass

        log_entry = {
            "api_name": path,
            "requested_date": datetime.now().strftime("%d-%b-%Y %I:%M:%S %p"),
            "requested_url": str(request.url),
            "requested_ip": request.client.host if request.client else None,
            "request_file": req_file,
            "response_file": resp_file
        }
        request_logs[path].append(log_entry)
        logger.info(f"[MONITOR] {log_entry}")
        return response
    else:
        response = await call_next(request)
        return response


app.include_router(ai_routes.router, tags=["AI"])
app.include_router(aws_routes.router, tags=["AWS"])
app.include_router(backup_routes.router, tags=["Backup"])
app.include_router(documents_routes.router, tags=["Documents"])
app.include_router(email_routes.router, tags=["Email"])
app.include_router(logs_routes.router, tags=["Logs"])
app.include_router(signature_routes.router, tags=["Signature"])


@app.get("/")
async def root():
    cert_count = len(list(CERT_DIR.glob("*.pfx")))
    return {
        "service": "Fresa API Gateway",
        "version": "2.0.0",
        "description": "Modularized API for Documents, AI, and Integrations",
        "features": [
            "AI Extraction (OpenAI)",
            "AWS Textract Integration",
            "Document Generation (Docx/PDF)",
            "Email Attachment Extraction",
            "Digital Signatures (Adobe Compatible)"
        ],
        "system_status": {
            "certificates_available": cert_count,
            "logs_active": True
        }
    }


# Custom ReDoc Endpoint
@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Fresa APIUAT Gateway - ReDoc</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
        <style>
        body { margin: 0; padding: 0; }
        </style>
    </head>
    <body>
        <redoc spec-url="/openapi.json"></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc@2.1.4/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    print(" Fresa API Gateway v2.0.0")
    print(" Server: http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)