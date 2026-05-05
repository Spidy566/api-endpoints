"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Generic Request Forwarding Logic         | 29-04-2026 | vishal
---------------------------------------------------------------------------
"""
import requests
from fastapi import HTTPException
from core.config import logger
from modules.proxy.schemas import GenericProxyRequest


def forward_generic_request(req: GenericProxyRequest) -> dict:
    headers = req.headers.copy() if req.headers else {}
    auth_tuple = None
    auth_type = req.auth.auth_type.lower()

    if auth_type == "basic":
        if not req.auth.username or not req.auth.password:
            raise HTTPException(status_code=400, detail="Username and password required for basic auth.")
        auth_tuple = (req.auth.username, req.auth.password)

    elif auth_type == "bearer":
        if not req.auth.token:
            raise HTTPException(status_code=400, detail="Token required for bearer auth.")
        headers["Authorization"] = f"Bearer {req.auth.token}"

    # Default JSON headers
    if req.payload and "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"
    if "Accept" not in headers:
        headers["Accept"] = "application/json"

    try:
        logger.info(f"Generic Proxy forwarding {req.http_method.upper()} to {req.target_url}")

        response = requests.request(
            method=req.http_method.upper(),
            url=req.target_url,
            headers=headers,
            params=req.query_params,
            json=req.payload,
            auth=auth_tuple,
            timeout=60
        )

        try:
            target_response = response.json()
        except ValueError:
            target_response = response.text

        return {
            "proxy_status_code": response.status_code,
            "target_response": target_response
        }

    except requests.exceptions.Timeout:
        logger.error(f"Proxy connection timed out to {req.target_url}")
        raise HTTPException(status_code=504, detail="Proxy timed out waiting for the target server.")
    except requests.exceptions.ConnectionError:
        logger.error(f"Proxy connection error to {req.target_url}")
        raise HTTPException(status_code=502, detail="Proxy failed to connect to the target server.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Proxy unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected proxy error: {str(e)}")