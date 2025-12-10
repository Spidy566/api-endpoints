import base64
from fastapi import APIRouter, HTTPException, UploadFile, File
from core.config import logger
from modules.email import schemas, services

router = APIRouter()


@router.post(
    '/extract_email_attachments',
    summary="Extract Attachments (File Upload)",
    description="Upload a raw .msg or .eml file. Parses the email structure and extracts all supported attachments as Base64.",
    response_model=schemas.EmailExtractionResponse,
)
async def extract_attachments(file: UploadFile = File(..., title="", description="The .msg or .eml file to process.")):
    """Main endpoint to extract supported attachments from email files"""
    try:
        logger.info("=== NEW EMAIL EXTRACTION REQUEST STARTED ===")

        if file.filename == '':
            raise HTTPException(status_code=400, detail="No file selected")

        if not services.allowed_file(file.filename):
            raise HTTPException(status_code=400, detail="Invalid file type. Only .msg and .eml files are allowed")

        file_content = await file.read()
        file_type = services.get_file_type(file.filename)

        logger.info(f"Processing {file_type.upper()} file: {file.filename} ({len(file_content)} bytes)")

        extractor = services.EmailAttachmentExtractor()

        if file_type == 'eml':
            attachments = extractor.extract_from_eml(file_content)
        elif file_type == 'msg':
            attachments = extractor.extract_from_msg(file_content)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        logger.info(f"EXTRACTION RESULT: Found {len(attachments)} supported attachments")

        file_type_counts = {}
        for att in attachments:
            ext = att.get('file_extension', '.unknown')
            file_type_counts[ext] = file_type_counts.get(ext, 0) + 1

        response_data = {
            'success': True,
            'message': f'Successfully processed {file.filename}',
            'file_type': file_type,
            'total_attachments': len(attachments),
            'file_type_counts': file_type_counts,
            'supported_formats': list(services.EmailAttachmentExtractor.SUPPORTED_EXTENSIONS),
            'attachments': []
        }

        for i, attachment in enumerate(attachments):
            attachment_info = {
                'index': i + 1,
                'filename': attachment['filename'],
                'content_type': attachment['content_type'],
                'file_extension': attachment['file_extension'],
                'size_bytes': attachment['size_bytes'],
                'base64_length': len(attachment['content']),
                'content': attachment['content']
            }
            response_data['attachments'].append(attachment_info)
            logger.info(
                f"RESPONSE: Added attachment {i + 1}: {attachment['filename']} ({attachment['file_extension']}) (base64 length: {len(attachment['content'])})")

        logger.info(f"FINAL RESPONSE CHECK:")
        logger.info(f"  total_attachments: {response_data['total_attachments']}")
        logger.info(f"  file_type_counts: {response_data['file_type_counts']}")
        logger.info(f"  attachments array length: {len(response_data['attachments'])}")
        logger.info(f"  attachment filenames: {[att['filename'] for att in response_data['attachments']]}")

        base64_contents = [att['content'] for att in response_data['attachments']]
        unique_contents = set(base64_contents)
        logger.info(f"  unique base64 contents: {len(unique_contents)} (should equal total_attachments)")

        if len(unique_contents) != len(base64_contents):
            logger.warning("WARNING: Some attachments have identical content!")
            for i, content in enumerate(base64_contents):
                logger.warning(f"  Attachment {i + 1} base64 hash: {hash(content)}")

        logger.info("=== EMAIL EXTRACTION RESPONSE BEING SENT ===")

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing email extraction request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post(
    "/extract_email_attachments_base64",
    summary="Extract Attachments (Base64)",
    description="Accepts a Base64 string of a .msg or .eml file and extracts attachments.",
    response_model=schemas.EmailExtractionResponse,
)
async def extract_attachments_base64(request: schemas.EmailBase64Request):
    """Extract attachments from base64 EML/MSG input."""
    try:
        file_content = base64.b64decode(request.file_base64)
        extractor = services.EmailAttachmentExtractor()
        if request.file_type.lower() == 'eml':
            attachments = extractor.extract_from_eml(file_content)
        elif request.file_type.lower() == 'msg':
            attachments = extractor.extract_from_msg(file_content)
        else:
            raise HTTPException(status_code=400, detail="Invalid file_type. Use 'eml' or 'msg'.")
        return {
            'success': True,
            'file_type': request.file_type,
            'file_name': request.file_name,
            'total_attachments': len(attachments),
            'attachments': attachments
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

@router.post(
    "/send_mail_using_customer_server",
    summary="Send Email (SMTP)",
    description="Sends an email (with optional attachments/HTML) using provided SMTP credentials.",
    response_model=schemas.SendEmailResponse,
)
async def send_email_endpoint(request: schemas.EmailRequest):
    success, message = services.send_email_logic(request.SmtpConfig, request.Message)

    if success:
        return {"status": "success", "message": message}
    else:
        return {"status": "error", "message": message}

