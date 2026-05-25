"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Encryption route registration            | 25-05-2026 | vishal
---------------------------------------------------------------------------
"""
import asyncio
from fastapi import APIRouter, HTTPException
from core.config import logger
from core.dependencies import thread_pool_executor
from modules.crypto import schemas, services

router = APIRouter()


@router.post(
    "/ssh_encrypt",
    summary="Encrypt SSH Credentials",
    description="Accepts username, password, and public key. Encrypts the credentials using hybrid AES-CBC + RSA-OAEP encryption.",
    response_model=schemas.SSHCredentialEncryptResponse
)
async def encrypt_ssh_credentials_endpoint(request: schemas.SSHCredentialEncryptRequest):
    try:
        loop = asyncio.get_running_loop()

        credential_payload = {
            "username": request.username,
            "password": request.password
        }

        result = await loop.run_in_executor(
            thread_pool_executor,
            services.encrypt_ssh_credentials,
            credential_payload,
            request.public_key
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in SSH credentials encryption route: {e}")
        raise HTTPException(status_code=500, detail=f"Encryption failed: {str(e)}")