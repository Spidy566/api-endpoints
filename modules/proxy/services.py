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


def handle_fasahpay_auth(auth_config) -> str:
    """Dynamically fetches the JWT token for FasahPay using provided credentials."""
    if not all([auth_config.auth_url, auth_config.client_id, auth_config.client_secret, auth_config.username,
                auth_config.password]):
        raise HTTPException(status_code=400,
                            detail="Missing required auth fields for FasahPay (auth_url, client_id, client_secret, username, password)")

    headers = {
        "X-Tabadul-Client-Id": auth_config.client_id,
        "X-Tabadul-Client-Secret": auth_config.client_secret,
        "Content-Type": "application/json"
    }
    payload = {
        "username": auth_config.username,
        "password": auth_config.password
    }

    try:
        response = requests.post(auth_config.auth_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json().get("token")
    except requests.exceptions.RequestException as e:
        logger.error(f"Generic Proxy - Failed to get token: {e}")
        raise HTTPException(status_code=502,
                            detail=f"Failed to authenticate with 3rd party: {response.text if response else str(e)}")


def forward_generic_request(req: GenericProxyRequest) -> dict:
    """Builds and forwards the request dynamically based on the payload."""

    headers = req.headers.copy() if req.headers else {}
    auth_tuple = None

    auth_type = req.auth.auth_type.lower()

    if auth_type == "basic":
        auth_tuple = (req.auth.username, req.auth.password)

    elif auth_type == "bearer":
        headers["Authorization"] = f"Bearer {req.auth.token}"

    elif auth_type == "fasahpay":
        token = handle_fasahpay_auth(req.auth)
        headers["Authorization"] = token
        headers["X-Tabadul-Client-Id"] = req.auth.client_id
        headers["X-Tabadul-Client-Secret"] = req.auth.client_secret

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
            response_json = response.json()
        except ValueError:
            response_json = response.text

        return {
            "proxy_status_code": response.status_code,
            "target_response": response_json
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Generic Proxy connection error: {e}")
        raise HTTPException(status_code=502, detail=f"Proxy failed to connect to target URL: {str(e)}")