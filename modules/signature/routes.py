import base64
import binascii
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from core.config import logger, CERT_DIR
from modules.signature import schemas, services

router = APIRouter()


@router.get("/")
async def signature_info():
    """Information endpoint about the signature service."""
    # Count certs safely
    try:
        cert_count = len(list(CERT_DIR.glob("*.pfx")))
    except Exception:
        cert_count = 0

    return {
        "service": "Adobe-Compatible Digital Signature API",
        "description": "Creates clean digital signatures without visual stamps",
        "version": "6.1.0",
        "signature_type": "PKCS#7 Digital Signature",
        "features": [
            "Clean signature field",
            "Click-to-verify system",
            "Certificate chain validation",
            "Compliant with Adobe PDF standards"
        ],
        "certificates_available": cert_count
    }


@router.post("/sign-invoice", response_model=schemas.InvoiceSignResponse)
async def sign_invoice(request: schemas.InvoiceSignRequest):
    logger.info(f"Digital signature request for: {request.name}")

    try:
        # 1. Decode Base64
        try:
            pdf_data = base64.b64decode(request.invoice_pdf_base64, validate=True)
            if not pdf_data.startswith(b'%PDF'):
                raise ValueError("Missing PDF header")
        except (binascii.Error, ValueError) as e:
            logger.error(f"Invalid PDF/Base64: {str(e)}")
            return JSONResponse(status_code=400, content={"error": f"Invalid PDF data: {str(e)}"})

        # 2. Check Certificate
        cert_path = services.get_cert_path(request.name)
        if not cert_path:
            logger.warning(f"Certificate not found for name: {request.name}")
            return schemas.InvoiceSignResponse(
                signed_pdf_base64=request.invoice_pdf_base64,
                error="Invalid name (Certificate not found)"
            )

        # 3. Validate Username Match
        if request.username is not None and request.username != request.name:
            return schemas.InvoiceSignResponse(
                signed_pdf_base64=request.invoice_pdf_base64,
                auth_error="Invalid username"
            )

        # 4. Load Certificate (Verify Password)
        try:
            cert_info = services.load_pkcs12_certificate(cert_path, request.password)
            # Add metadata needed for service
            cert_info['cert_path'] = cert_path
            cert_info['password'] = request.password
        except Exception:
            logger.warning(f"Invalid password for certificate: {request.name}")
            return schemas.InvoiceSignResponse(
                signed_pdf_base64=request.invoice_pdf_base64,
                error="Invalid password"
            )

        # 5. Sign PDF (Async execution)
        try:
            signed_pdf = await services.sign_pdf_async(pdf_data, cert_info, request)

            signed_pdf_base64 = base64.b64encode(signed_pdf).decode('utf-8')

            signature_info = {
                "signer": request.name,
                "organization": cert_info['organization'],
                "timestamp": datetime.now().isoformat(),
                "reason": request.reason,
                "verification_status": "Signature created - Click signature field to verify"
            }

            logger.info(f"✓ Digital signature completed successfully for {request.name}")
            return schemas.InvoiceSignResponse(
                signed_pdf_base64=signed_pdf_base64,
                signature_info=signature_info
            )

        except Exception as e:
            logger.error(f"Internal signing error: {str(e)}")
            return JSONResponse(status_code=500, content={"error": f"Internal signing error: {str(e)}"})

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Unexpected server error: {str(e)}"})


@router.post("/validate-signature")
async def validate_signature(request: schemas.ValidationRequest):
    """Validate an existing signed PDF."""
    try:
        pdf_data = base64.b64decode(request.signed_pdf_base64, validate=True)
        result = services.validate_pdf_content(pdf_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upload_certificate")
async def upload_certificate(
        file: UploadFile = File(...),
        overwrite: bool = Form(False)
):
    """Upload a .pfx certificate file."""
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