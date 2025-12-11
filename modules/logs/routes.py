from fastapi import APIRouter, Request, Path as PathParam
from modules.logs import schemas, services

router = APIRouter()

@router.get(
    "/logs/files/{filename}",
    summary="Download Raw Log File",
    description="Download a saved request or response JSON file by its filename.",
    responses={
        200: {
            "content": {"application/json": {}},
            "description": "The raw JSON log file."
        },
        404: {"description": "File not found."}
    }
)
async def download_log_file(filename: str = PathParam(..., title="", description="The filename of the log (e.g., uuid_request.json).")):
    return services.download_log_file(filename)

@router.get(
    "/{endpoint_path:path}/logs",
    summary="Get Endpoint Logs",
    description="Retrieve execution logs, timestamps, and file references for a specific API path.",
    response_model=schemas.LogResponse
)
async def get_endpoint_logs(request: Request, endpoint_path: str = PathParam(..., title="", description="The API path to inspect (e.g., 'ai/openai_extract').")):
    return services.get_endpoint_logs(endpoint_path, request)