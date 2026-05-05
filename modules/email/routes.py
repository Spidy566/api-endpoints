"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Added IMAP inbox processing endpoints    | 05-05-2026 | dhremagi
Added SMTP email sending                 | 03-12-2025 | vishal
Added attachment extraction endpoints    | 13-06-2025 | senthil
---------------------------------------------------------------------------
"""
import base64
import binascii
from typing import Dict, Any
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

        filename: str = file.filename or ""

        if not filename:
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

        file_type_counts: Dict[str, int] = {}
        for att in attachments:
            ext = att.get('file_extension', '.unknown')
            file_type_counts[ext] = file_type_counts.get(ext, 0) + 1

        response_data: Dict[str, Any]  = {
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

        logger.info("FINAL RESPONSE CHECK:")
        logger.info(f"  total_attachments: {response_data['total_attachments']}")
        logger.info(f"  file_type_counts: {response_data['file_type_counts']}")
        logger.info(f"  attachments array length: {len(response_data['attachments'])}")

        filenames = [att['filename'] for att in response_data['attachments']]
        logger.info(f"  attachment filenames: {filenames}")

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
async def extract_attachments_base64(request: schemas.EmailExtractionRequest):
    """Extract attachments from base64 EML/MSG input."""
    try:
        try:
            file_content = base64.b64decode(request.file_base64, validate=True)
        except (binascii.Error, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid Base64 string: {str(e)}"
            )
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Extraction crash: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@router.post(
    "/send_mail_using_customer_server",
    summary="Send Email (SMTP)",
    description="Sends an email (with optional attachments/HTML) using provided SMTP credentials.",
    response_model=schemas.EmailSendResponse,
)
async def send_email_endpoint(request: schemas.EmailSendRequest):
    success, message = services.send_email_logic(request.smtp_config, request.message)

    if success:
        return {"status": "success", "message": message}
    else:
        status_code = 500

        lower_msg = message.lower()
        if "decryption error" in lower_msg:
            status_code = 400
        elif "authentication failed" in lower_msg:
            status_code = 401
        elif "network" in lower_msg or "connection" in lower_msg:
            status_code = 502
        elif "configuration error" in lower_msg:
            status_code = 500

        raise HTTPException(
            status_code=status_code,
            detail=message
        )


@router.post(
    "/email_inbox_count",
    summary="Get Inbox Email Count",
    description="Connects via IMAP and returns the total number of emails in the INBOX.",
    response_model=schemas.EmailInboxCountResponse,
)
async def email_inbox_count(payload: schemas.EmailInboxPayload):
    try:
        count = services.get_inbox_count_logic(payload)
        return {"success": True, "email_count": count}

    except ValueError as e:
        logger.warning(f"IMAP Authentication Error: {str(e)}")
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"IMAP Inbox Count Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/email_inbox_get_first_email",
    summary="Get and Move First Email",
    description="Fetches the first email from INBOX, converts to Base64, moves to a backup folder, and deletes it from INBOX.",
    response_model=schemas.EmailInboxGetResponse,
)
async def email_inbox_get_first_email(payload: schemas.EmailInboxPayload):
    try:
        result = services.get_first_email_logic(payload)

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        logger.warning(f"IMAP Authentication Error: {str(e)}")
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"IMAP Get First Email Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))