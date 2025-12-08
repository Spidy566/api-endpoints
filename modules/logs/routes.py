from fastapi import APIRouter, Request
from modules.logs import schemas, services

router = APIRouter()

@router.get("/logs/files/{filename}")
async def download_log_file(filename: str):
    return services.download_log_file(filename)

@router.get("/{endpoint_path:path}/logs", response_model=schemas.LogResponse)
async def get_endpoint_logs(endpoint_path: str, request: Request):
    return services.get_endpoint_logs(endpoint_path, request)