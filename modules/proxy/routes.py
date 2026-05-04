"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Generic Forwarding Endpoint              | 29-04-2026 | vishal
---------------------------------------------------------------------------
"""
from fastapi import APIRouter
from modules.proxy import schemas, services

router = APIRouter()

@router.post(
    "/forward",
    summary="Generic API Proxy Forwarder",
    description="Send a target URL, method, credentials, and payload. This API will authenticate and forward it automatically."
)
async def generic_forward(request: schemas.GenericProxyRequest):
    return services.forward_generic_request(request)