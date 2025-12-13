import base64
import binascii
import asyncio
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from core.config import logger, CERT_DIR
from core.dependencies import thread_pool_executor
from modules.signature import schemas, services

router = APIRouter()


@router.post(
    "/sign-invoice",
    summary="Sign Invoice",
    description="Digitally signs a PDF using a server-stored PFX certificate. Supports visual stamps and Adobe-compatible signatures.",
    response_model=schemas.InvoiceSignResponse
)
async def sign_invoice(request: schemas.InvoiceSignRequest):
    logger.info(f"Digital signature request for: {request.name}")

    try:
        try:
            pdf_data = base64.b64decode(request.invoice_pdf_base64, validate=True)
            if not pdf_data.startswith(b'%PDF'):
                raise ValueError("Missing PDF header")
        except (binascii.Error, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid PDF Data: {str(e)}"
            )

        cert_path = services.get_cert_path(request.name)
        if not cert_path:
            raise HTTPException(
                status_code=404,
                detail=f"Certificate for '{request.name}' not found on server."
            )

        if request.username is not None and request.username != request.name:
            raise HTTPException(
                status_code=401,
                detail=f"Username mismatch: '{request.username}' does not match certificate name '{request.name}'."
            )

        try:
            cert_info = services.load_pkcs12_certificate(cert_path, request.password)
            cert_info['cert_path'] = cert_path
            cert_info['password'] = request.password
        except Exception:
            logger.warning(f"Invalid password for certificate: {request.name}")
            raise HTTPException(
                status_code=401,
                detail="Invalid password or corrupted certificate file."
            )

        try:
            signed_pdf = await services.sign_pdf_async(pdf_data, cert_info, request)
            signed_pdf_base64 = base64.b64encode(signed_pdf).decode('utf-8')

            signature_info = {
                "signer": request.name,
                "organization": cert_info['organization'],
                "timestamp": datetime.now().isoformat(),
                "reason": request.reason,
                "verification_status": "Signature created successfully"
            }

            return {
                "signed_pdf_base64": signed_pdf_base64,
                "signature_info": signature_info,
                "error": None,
                "auth_error": None
            }

        except Exception as e:
            logger.error(f"Internal signing error: {str(e)}")
            raise HTTPException(status_code=500,detail=f"Signing process failed: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500,detail=f"Unexpected server error: {str(e)}")


@router.post(
    "/validate-signature",
    summary="Validate Signed PDF",
    description="Analyzes a PDF for digital signatures and verifies their integrity and trust status.",
    response_model=schemas.ValidationResponse
)
async def validate_signature(request: schemas.ValidationRequest):
    try:
        try:
            pdf_data = base64.b64decode(request.signed_pdf_base64, validate=True)
        except (binascii.Error, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid Base64 string: {str(e)}"
            )
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            thread_pool_executor,
            services.validate_pdf_content,
            pdf_data
        )
        if result.get("error") and "No digital signatures" not in str(result.get("message", "")):
            if "EOF marker" in str(result.get("error")) or "not a PDF" in str(result.get("error")):
                raise HTTPException(status_code=400, detail=f"Corrupted PDF: {result['error']}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected server error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected server error: {str(e)}"
        )

@router.post(
    "/upload_certificate",
    summary="Upload PFX Certificate",
    description="Upload a .pfx file to the server for use in signing. Requires 'overwrite=True' to replace existing certs.",
    response_model=schemas.UploadCertResponse
)
async def upload_certificate(
        file: UploadFile = File(..., title="", description="The .pfx certificate file."),
        overwrite: bool = Form(default=False, title="", description="Whether to overwrite an existing certificate.")
):
    if not file.filename.lower().endswith('.pfx'):
        raise HTTPException(status_code=400, detail="Only .pfx files are allowed.")

    cert_path = CERT_DIR / file.filename

    if cert_path.exists() and not overwrite:
        raise HTTPException(status_code=409, detail="Certificate already exists. Set overwrite=True to replace.")

    try:
        content = await file.read()
        with open(cert_path, "wb") as f:
            f.write(content)
        return {"success": True, "filename": file.filename, "overwritten": cert_path.exists()}
    except Exception as e:
        logger.error(f"Failed to save certificate: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save certificate: {str(e)}")