import subprocess
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import ResponseValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import logger, CERT_DIR, APP_TITLE, APP_VERSION, APP_DESC
from core.dependencies import process_pool_executor, thread_pool_executor
from core.middleware import log_and_count_requests
from core.handlers import validation_exception_handler
from core.openapi import configure_openapi

from modules.ai import routes as ai_routes
from modules.aws import routes as aws_routes
from modules.backup import routes as backup_routes
from modules.documents import routes as documents_routes
from modules.email import routes as email_routes
from modules.logs import routes as logs_routes
from modules.signature import routes as signature_routes
from modules.logs.services import request_counts


templates = Jinja2Templates(directory="templates")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        check_command = ["/usr/bin/python3", "/usr/bin/unoconv", "--version"]
        result = subprocess.run(check_command, check=True, capture_output=True, text=True)
        print(f"--- Found unoconv. Version: {result.stdout.strip()} ---")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("WARNING: 'unoconv' not found. PDF conversion may fail.")

    yield

    print("--- Shutting down executors ---")
    process_pool_executor.shutdown(wait=True)
    thread_pool_executor.shutdown(wait=True)


TAGS_METADATA = [
    {"name": "AI", "description": "OpenAI, OCR, and Extraction services."},
    {"name": "AWS", "description": "S3 Storage and Textract analysis."},
    {"name": "Signature", "description": "Digital PFX Signatures."},
    {"name": "Documents", "description": "PDF Merging and DOCX Generation."},
    {"name": "Email", "description": "Email parsing and sending."},
    {"name": "Backup", "description": "File backup utilities."},
    {"name": "Logs", "description": "System audit logs."},
]

app = FastAPI(
    title=APP_TITLE,
    description=APP_DESC,
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url=None,
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])
app.middleware("http")(log_and_count_requests)
app.exception_handler(ResponseValidationError)(validation_exception_handler)

app.include_router(ai_routes.router, tags=["AI"])
app.include_router(aws_routes.router, tags=["AWS"])
app.include_router(backup_routes.router, tags=["Backup"])
app.include_router(documents_routes.router, tags=["Documents"])
app.include_router(email_routes.router, tags=["Email"])
app.include_router(logs_routes.router, tags=["Logs"])
app.include_router(signature_routes.router, tags=["Signature"])


@app.get("/", include_in_schema=False)
async def root(request: Request):
    cert_count = len(list(CERT_DIR.glob("*.pfx")))
    total_requests = sum(request_counts.values())

    context = {
        "request": request,
        "title": APP_TITLE,
        "version": APP_VERSION,
        "cert_count": cert_count,
        "total_requests": total_requests,
        "features": [tag['name'] for tag in TAGS_METADATA]
    }
    return templates.TemplateResponse("home.html", context)


@app.get("/redoc", include_in_schema=False)
async def custom_redoc(request: Request):
    return templates.TemplateResponse("redoc.html", {"request": request, "title": APP_TITLE})


def custom_openapi_wrapper():
    return configure_openapi(app, APP_TITLE, APP_VERSION, APP_DESC, TAGS_METADATA)


app.openapi = custom_openapi_wrapper

if __name__ == "__main__":
    print(f" {APP_TITLE} v{APP_VERSION}")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)