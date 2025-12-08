import json
import base64
import requests
import re
import io
import os
from email import message_from_bytes
from email.mime.multipart import MIMEMultipart
import mimetypes
import extract_msg
from typing import Optional, List, Union
from fastapi import FastAPI, HTTPException, status, File, UploadFile, Request, Form, Query, Body
import shutil
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator, Field
import logging
from PIL import Image
from pypdf import PdfWriter, PdfReader
import fitz  # PyMuPDF
from fastapi.responses import FileResponse, Response
import boto3
from datetime import datetime
from typing import Optional, List, Union, Dict, Any, Tuple, Literal
from fastapi.responses import JSONResponse
import binascii
from io import BytesIO
from pathlib import Path
import asyncio
import concurrent.futures
import time
import uuid
import openai
import signal
from docxtpl import DocxTemplate, RichText
from typing import Dict, Any
from pydantic import BaseModel
from contextlib import asynccontextmanager
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import sys
import subprocess
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
import quopri
import html
import binascii
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, SecretStr, ConfigDict
from pydantic.alias_generators import to_pascal



# --- NEW: imports for visiting card scan ---
import tempfile
from fastapi import Depends
try:
    import easyocr  # heavy dependency; installed via requirements
    _has_easyocr = True
except Exception:
    _has_easyocr = False

try:
    import pytesseract
    _has_tesseract = True
except Exception:
    _has_tesseract = False



# Core libraries for digtial signature
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import signers, fields
from pyhanko.sign.fields import SigSeedSubFilter
from pyhanko.stamp import TextStampStyle
from pyhanko.pdf_utils.text import TextBoxStyle
from pyhanko.pdf_utils.font import FontEngine
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from cryptography import x509
from cryptography.hazmat.backends import default_backend

process_pool_executor = ProcessPoolExecutor()
thread_pool_executor = ThreadPoolExecutor()


s3 = boto3.client("s3", aws_access_key_id=AWS_KEY, aws_secret_access_key=AWS_SECRET, region_name=REGION)
textract = boto3.client("textract", aws_access_key_id=AWS_KEY, aws_secret_access_key=AWS_SECRET, region_name=REGION)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fresa APIUAT Gateway",
    description="Full documentation for PDF parsing, Textract, email attachments, digital signature, and OpenAI extraction.",
    version="2.0.0",
    docs_url="/docs",          # Swagger UI
    redoc_url=None, # "/redoc",        # ReDoc UI
    openapi_url="/openapi.json"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


ALLOWED_EXTENSIONS = {'msg', 'eml'}

# ===== EMAIL ATTACHMENT EXTRACTION CLASSES =====

class EmailAttachmentExtractor:
    """Class to handle multiple file format extraction from email files"""
    
    # Supported file extensions
    SUPPORTED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.zip','.xlsx','.xls','.doc','.docx'} # 2025-06-13
    
    # MIME type mappings
    MIME_TYPE_MAP = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg', 
        '.png': 'image/png',
        '.tiff': 'image/tiff',
        '.tif': 'image/tiff',
        '.zip': 'application/zip',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # 2025-06-13: Added xlsx MIME type
        '.xls': 'application/vnd.ms-excel',  # 2025-06-13: Added xls MIME type
        '.doc': 'application/msword',  # 2025-06-13: Added doc MIME type
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'  # 2025-06-13: Added docx MIME type
    }
    
    # File format signatures for validation
    FILE_SIGNATURES = {
        '.pdf': [b'%PDF'],
        '.jpg': [b'\xff\xd8\xff'],
        '.jpeg': [b'\xff\xd8\xff'],
        '.png': [b'\x89PNG\r\n\x1a\n'],
        '.tiff': [b'II*\x00', b'MM\x00*'],
        '.tif': [b'II*\x00', b'MM\x00*'],
        '.zip': [b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'],
        '.xlsx': [b'PK\x03\x04'],  # 2025-06-13: Added xlsx signature
        '.xls': [b'\xD0\xCF\x11\xE0'],  # 2025-06-13: Added xls signature
        '.doc': [b'\xD0\xCF\x11\xE0'],  # 2025-06-13: Added doc signature
        '.docx': [b'PK\x03\x04']  # 2025-06-13: Added docx signature
    }
    
    @staticmethod
    def is_supported_file(filename, content_type=None):
        """Check if file is supported based on filename and content type"""
        if not filename:
            return False
        
        # Get file extension
        file_ext = '.' + filename.lower().split('.')[-1] if '.' in filename else ''
        
        # Check file extension
        if file_ext in EmailAttachmentExtractor.SUPPORTED_EXTENSIONS:
            return True
              # Check content type
        if content_type:
            content_lower = content_type.lower()
            for ext, mime in EmailAttachmentExtractor.MIME_TYPE_MAP.items():
                if mime.lower() in content_lower:
                    return True
                    
        return False
    
    @staticmethod
    def get_file_extension(filename):
        """Get standardized file extension"""
        if not filename or '.' not in filename:
            return '.unknown'
        return '.' + filename.lower().split('.')[-1]
    
    @staticmethod
    def validate_file_content(data, expected_extension):
        """Validate file content against expected format using file signatures"""
        if not data or len(data) < 4:
            return False
            
        signatures = EmailAttachmentExtractor.FILE_SIGNATURES.get(expected_extension, [])
        
        for signature in signatures:
            if data.startswith(signature):
                return True
                
        return False
    
    @staticmethod
    def get_default_filename(index, extension, content_type=None):
        """Generate default filename for attachments without names"""
        base_name = f"attachment_{index}"
        if extension and extension != '.unknown':
            return f"{base_name}{extension}"
        elif content_type:
            # Try to guess extension from content type
            content_lower = content_type.lower()
            for ext, mime in EmailAttachmentExtractor.MIME_TYPE_MAP.items():
                if mime.lower() in content_lower:
                    return f"{base_name}{ext}"
        return f"{base_name}.bin"
    
    @staticmethod
    def extract_from_eml(file_content):
        """Extract supported attachments from EML file with extensive debugging"""
        attachments = []
        
        try:
            # Parse EML content
            msg = message_from_bytes(file_content)
            parts = list(msg.walk())
            logger.debug(f"EML parsing started - found {len(parts)} total parts")
            
            # Walk through all parts of the message
            for i, part in enumerate(parts):
                logger.debug(f"--- Processing EML part {i} ---")
                logger.debug(f"Content-Type: {part.get_content_type()}")
                logger.debug(f"Content-Disposition: {part.get_content_disposition()}")
                logger.debug(f"Filename: {part.get_filename()}")
                
                content_disposition = part.get_content_disposition()
                content_type = part.get_content_type()
                filename = part.get_filename()
                
                # More comprehensive attachment detection
                is_attachment = False
                
                # Check various conditions for attachments
                if content_disposition and 'attachment' in content_disposition.lower():
                    is_attachment = True
                    logger.debug(f"Part {i}: Identified as attachment by disposition")
                
                if filename and EmailAttachmentExtractor.is_supported_file(filename, content_type):
                    is_attachment = True
                    logger.debug(f"Part {i}: Identified as supported file by filename: {filename}")
                
                if content_type and any(mime in content_type.lower() for mime in EmailAttachmentExtractor.MIME_TYPE_MAP.values()):
                    is_attachment = True
                    logger.debug(f"Part {i}: Identified as supported file by content-type: {content_type}")
                
                if is_attachment:
                    logger.debug(f"Part {i}: Processing as potential supported attachment")
                    
                    # Get file extension
                    file_ext = EmailAttachmentExtractor.get_file_extension(filename) if filename else '.unknown'
                    
                    # Generate filename if missing
                    if not filename:
                        filename = EmailAttachmentExtractor.get_default_filename(i, file_ext, content_type)
                        logger.debug(f"Part {i}: Generated filename: {filename}")
                    
                    # Only process supported files
                    if EmailAttachmentExtractor.is_supported_file(filename, content_type):
                        try:
                            logger.debug(f"Part {i}: Attempting to extract payload for {filename}")
                            
                            # Get the payload (attachment content)
                            payload = part.get_payload(decode=True)
                            
                            if payload and len(payload) > 0:
                                logger.debug(f"Part {i}: Payload extracted - {len(payload)} bytes")
                                
                                # Validate file content based on extension
                                expected_ext = EmailAttachmentExtractor.get_file_extension(filename)
                                is_valid = EmailAttachmentExtractor.validate_file_content(payload, expected_ext)
                                
                                if is_valid or expected_ext == '.unknown':
                                    logger.debug(f"Part {i}: Valid {expected_ext} file format detected")
                                    
                                    # Convert to base64
                                    base64_content = base64.b64encode(payload).decode('utf-8')
                                    
                                    # Determine content type
                                    final_content_type = content_type or EmailAttachmentExtractor.MIME_TYPE_MAP.get(expected_ext, 'application/octet-stream')
                                    
                                    attachment_data = {
                                        'filename': filename,
                                        'content': base64_content,
                                        'content_type': final_content_type,
                                        'size_bytes': len(payload),
                                        'file_extension': expected_ext
                                    }
                                    
                                    attachments.append(attachment_data)
                                    logger.info(f"SUCCESS: Extracted {expected_ext} file {len(attachments)}: {filename} ({len(payload)} bytes, {len(base64_content)} base64 chars)")
                                    
                                else:
                                    logger.warning(f"Part {i}: File {filename} failed content validation for {expected_ext} - first 10 bytes: {payload[:10]}")
                            else:
                                logger.warning(f"Part {i}: Empty or null payload for {filename}")
                                
                        except Exception as e:
                            logger.error(f"Part {i}: Error extracting {filename}: {str(e)}")
                            continue
                    else:
                        logger.debug(f"Part {i}: Skipping unsupported file: {filename}")
                else:
                    logger.debug(f"Part {i}: Not an attachment")
                    
        except Exception as e:
            logger.error(f"Error parsing EML file: {str(e)}")
            raise Exception(f"Failed to parse EML file: {str(e)}")
            
        logger.info(f"EML EXTRACTION COMPLETE: Found {len(attachments)} supported attachments")
        for i, att in enumerate(attachments):
            logger.info(f"  File {i+1}: {att['filename']} ({att['file_extension']}) - {att['size_bytes']} bytes")
            
        return attachments
    
    @staticmethod
    def extract_from_msg(file_content):
        """Extract supported attachments from MSG file with extensive debugging"""
        attachments = []
        
        try:
            # Create a BytesIO object from file content
            file_stream = io.BytesIO(file_content)
            
            # Parse MSG file
            msg = extract_msg.Message(file_stream)
            
            attachment_count = len(msg.attachments) if hasattr(msg, 'attachments') and msg.attachments else 0
            logger.debug(f"MSG parsing started - found {attachment_count} attachments")
            
            # Check if there are attachments
            if hasattr(msg, 'attachments') and msg.attachments:
                for i, attachment in enumerate(msg.attachments):
                    logger.debug(f"--- Processing MSG attachment {i} ---")
                    
                    try:
                        # Get filename (try different attributes)
                        filename = (getattr(attachment, 'longFilename', None) or 
                                  getattr(attachment, 'shortFilename', None) or 
                                  getattr(attachment, 'displayName', None))
                        
                        # Get file extension
                        file_ext = EmailAttachmentExtractor.get_file_extension(filename) if filename else '.unknown'
                        
                        if not filename:
                            filename = EmailAttachmentExtractor.get_default_filename(i, file_ext)
                            
                        logger.debug(f"Attachment {i}: filename = {filename}")
                        
                        # Check attachment type
                        logger.debug(f"Attachment {i}: type = {type(attachment)}")
                        logger.debug(f"Attachment {i}: dir = {[attr for attr in dir(attachment) if not attr.startswith('_')]}")
                        
                        # Only process supported files
                        if EmailAttachmentExtractor.is_supported_file(filename):
                            logger.debug(f"Attachment {i}: Processing as supported file: {filename}")
                            
                            # Get attachment data
                            attachment_data = attachment.data
                            
                            if attachment_data and len(attachment_data) > 0:
                                logger.debug(f"Attachment {i}: Data extracted - {len(attachment_data)} bytes")
                                
                                # Validate file content based on extension
                                expected_ext = EmailAttachmentExtractor.get_file_extension(filename)
                                is_valid = EmailAttachmentExtractor.validate_file_content(attachment_data, expected_ext)
                                
                                if is_valid or expected_ext == '.unknown':
                                    logger.debug(f"Attachment {i}: Valid {expected_ext} file format detected")
                                    
                                    # Convert binary data to base64
                                    base64_content = base64.b64encode(attachment_data).decode('utf-8')
                                    
                                    # Determine content type
                                    content_type = EmailAttachmentExtractor.MIME_TYPE_MAP.get(expected_ext, 'application/octet-stream')
                                    
                                    attachment_info = {
                                        'filename': filename,
                                        'content': base64_content,
                                        'content_type': content_type,
                                        'size_bytes': len(attachment_data),
                                        'file_extension': expected_ext
                                    }
                                    
                                    attachments.append(attachment_info)
                                    logger.info(f"SUCCESS: Extracted {expected_ext} file {len(attachments)}: {filename} ({len(attachment_data)} bytes, {len(base64_content)} base64 chars)")
                                    
                                else:
                                    logger.warning(f"Attachment {i}: File {filename} failed content validation for {expected_ext} - first 10 bytes: {attachment_data[:10]}")
                            else:
                                logger.warning(f"Attachment {i}: Empty attachment data for {filename}")
                        else:
                            logger.debug(f"Attachment {i}: Skipping unsupported file: {filename}")
                                
                    except Exception as e:
                        logger.error(f"Attachment {i}: Error processing: {str(e)}")
                        continue
            else:
                logger.info("No attachments found in MSG file")
            
            # Close the message
            msg.close()
            
        except Exception as e:
            logger.error(f"Error parsing MSG file: {str(e)}")
            raise Exception(f"Failed to parse MSG file: {str(e)}")
            
        logger.info(f"MSG EXTRACTION COMPLETE: Found {len(attachments)} supported attachments")
        for i, att in enumerate(attachments):
            logger.info(f"  File {i+1}: {att['filename']} ({att['file_extension']}) - {att['size_bytes']} bytes")
            
        return attachments


class ExtractionRequest(BaseModel):
    p_input_content: str
    p_api_name: str
    p_api_model: str
    p_api_key: str
    p_api_token: str
    p_template_name: str
    p_template_prompt_header: str = ""
    p_template_prompt_details: str = ""
    p_temperature: float = 0.1
    p_top_p: float = 0.9
    p_timeout: int = 180
    
    @field_validator('p_input_content', 'p_api_key', 'p_template_name')
    @classmethod
    def validate_required_fields(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field is required")
        return v
    
    @field_validator('p_api_token')
    @classmethod
    def validate_tokens(cls, v: str) -> str:
        token_int = int(v)
        if not 1 <= token_int <= 128000:
            raise ValueError("api_token must be between 1 and 128000")
        return v
    
    @field_validator('p_api_model')
    @classmethod
    def validate_api_model(cls, v: str) -> str:
        supported_models = [
            "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision-preview",
            "gpt-4", "gpt-4-32k", "gpt-3.5-turbo", "gpt-3.5-turbo-16k","gpt-4.1","gpt-4.1-mini",
        ]
        if v not in supported_models:
            raise ValueError(f"Unsupported model. Supported models: {', '.join(supported_models)}")
        return v

def convert_pdf_to_jpeg(pdf_base64: str) -> List[str]:
    """Convert ALL PDF pages to JPEG images for Vision API"""
    try:
        pdf_bytes = base64.b64decode(pdf_base64)
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        if pdf_document.page_count == 0:
            raise Exception("PDF has no pages")
        
        images = []
        logger.info(f"Processing PDF with {pdf_document.page_count} pages")
        
        # Process ALL pages
        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]
            mat = fitz.Matrix(3.0, 3.0)  # 216 DPI
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data))
            
            # Convert to RGB for JPEG
            if image.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "P":
                    image = image.convert("RGBA")
                if image.mode in ("RGBA", "LA"):
                    background.paste(image, mask=image.split()[-1])
                image = background
            elif image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            
            # Optimize size
            if max(image.size) > 2000:
                ratio = 2000 / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            output_buffer = io.BytesIO()
            image.save(output_buffer, format="JPEG", quality=95, optimize=True)
            image_base64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
            
            images.append(image_base64)
            output_buffer.close()
            
            logger.info(f"Processed page {page_num + 1}/{pdf_document.page_count}")
        
        pdf_document.close()
        return images
        
    except Exception as e:
        raise Exception(f"PDF conversion failed: {str(e)}")

def detect_and_validate_format(base64_content: str) -> str:
    """Detect and validate file format - only PDF, JPEG, JPG, PNG allowed"""
    format_signatures = {
        "JVBERi": "pdf",
        "/9j/": "jpeg",
        "iVBORw0KGgo": "png"
    }
    
    for signature, format_name in format_signatures.items():
        if base64_content.startswith(signature):
            return format_name
    
    # If not recognized, reject
    raise ValueError("Unsupported file format. Only PDF, JPEG, JPG, and PNG are allowed.")

def process_with_openai(api_key: str, model: str, prompt_header: str, prompt_details: str, 
                       base64_content: str, api_token: str, temperature: float, 
                       top_p: float, timeout: int) -> dict:
    """Process document with OpenAI Vision API"""
    try:
        # Combine prompts
        full_prompt = ""
        if prompt_header and prompt_details:
            full_prompt = f"{prompt_header}\n\n{prompt_details}"
        elif prompt_header:
            full_prompt = prompt_header
        elif prompt_details:
            full_prompt = prompt_details
        
        if not full_prompt.strip():
            return {"success": False, "error": "No prompt provided"}
        
        # Validate base64
        try:
            decoded_size = len(base64.b64decode(base64_content, validate=True))
            if decoded_size > 20 * 1024 * 1024:
                return {"success": False, "error": "File too large (>20MB)"}
        except Exception as e:
            return {"success": False, "error": f"Invalid base64: {str(e)}"}
        
        # Handle file format validation and PDF conversion
        try:
            file_format = detect_and_validate_format(base64_content)
            
            if file_format == "pdf":
                converted_images = convert_pdf_to_jpeg(base64_content)  # Now returns list
                file_format = "jpeg"
            else:
                converted_images = [base64_content]  # Single image as list
                
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"File processing failed: {str(e)}"}
        
        # Create content array with text and ALL images
        content = [{"type": "text", "text": full_prompt}]
        
        for i, image_base64 in enumerate(converted_images):
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{file_format};base64,{image_base64}",
                    "detail": "high"
                }
            })
            logger.info(f"Added image {i + 1}/{len(converted_images)} to request")
        
        # API request
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": content  # Now includes ALL page images
            }],
            "max_tokens": int(api_token),
            "temperature": temperature,
            "top_p": top_p
        }
        
        logger.info(f"Sending request to OpenAI with {len(converted_images)} images")
        response = requests.post("https://api.openai.com/v1/chat/completions", 
                               headers=headers, json=payload, timeout=timeout)
        
        if response.status_code == 200:
            result = response.json()
            
            if 'choices' not in result or len(result['choices']) == 0:
                return {"success": False, "error": "Invalid API response structure"}
            
            ai_response = result['choices'][0]['message']['content']
            logger.info(f"AI Response length: {len(ai_response) if ai_response else 0}")
            
            # Check if response is empty
            if not ai_response or not ai_response.strip():
                return {"success": False, "error": "AI returned empty response"}
            
            # Clean the response - remove potential markdown formatting
            cleaned_response = ai_response.strip()
            
            # Remove markdown code blocks if present
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            
            cleaned_response = cleaned_response.strip()
            
            # Parse JSON response
            try:
                parsed_json = json.loads(cleaned_response)
                
                return {
                    "success": True,
                    "extracted_data": parsed_json
                }
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON Parse Error: {str(e)}")
                logger.error(f"Raw AI Response: {ai_response[:500]}")
                return {
                    "success": False,
                    "error": f"JSON parsing failed: {str(e)}",
                    "raw_response": ai_response[:500]
                }
        
        # Handle API errors
        error_map = {
            429: "Rate limit exceeded",
            400: "Bad request - check parameters",
            401: "Invalid API key",
            403: "Insufficient permissions",
            500: "OpenAI server error"
        }
        
        return {"success": False, "error": error_map.get(response.status_code, f"API error: {response.status_code}")}
            
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Request timeout"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Connection error"}
    except Exception as e:
        return {"success": False, "error": f"Processing error: {str(e)}"}

def extract_base64_content(file_content: str) -> Optional[str]:
    """Extract and validate base64 content"""
    try:
        if not file_content:
            return None
        
        # Handle data URL format
        if file_content.startswith('data:') and ',' in file_content:
            content = file_content.split(',', 1)[1]
        else:
            content = file_content
        
        # Clean and validate
        content = content.strip().replace('\n', '').replace('\r', '').replace(' ', '')
        
        if len(content) < 10:
            return None
        
        # Test validity
        base64.b64decode(content, validate=True)
        return content
        
    except Exception:
        return None

# --- NEW: OCR helpers for visiting card scan ---
def _init_easyocr_reader():
    if not _has_easyocr:
        return None
    try:
        # English only; GPU off (safer for most servers)
        return easyocr.Reader(['en'], gpu=False)
    except Exception:
        return None

_EASY_OCR_READER = _init_easyocr_reader()

def _ocr_with_easyocr(img_path: str) -> str:
    if _EASY_OCR_READER is None:
        return ""
    try:
        result = _EASY_OCR_READER.readtext(img_path)
        return " ".join([line[1] for line in result]) if result else ""
    except Exception:
        return ""

def _ocr_with_tesseract(img_path: str) -> str:
    if not _has_tesseract:
        return ""
    try:
        # On Ubuntu, tesseract is usually at /usr/bin/tesseract after apt install
        # Do NOT hardcode Windows paths here.
        from PIL import Image as _Image
        return pytesseract.image_to_string(_Image.open(img_path))
    except Exception:
        return ""

def ocr_extract_card(img_path: str) -> str:
    """
    Try EasyOCR first (usually better on business cards), then Tesseract.
    Return whichever yields longer text.
    """
    txt_easy = _ocr_with_easyocr(img_path)
    txt_tess = _ocr_with_tesseract(img_path)
    if len(txt_easy) >= len(txt_tess):
        return txt_easy.strip()
    return txt_tess.strip()

def _clean_card_text(text: str) -> str:
    """
    Basic cleanup for common OCR artefacts on business cards
    """
    if not text:
        return ""
    replacements = {
        "WWIN": "www", "VVWW": "www", "comcom": "com", "•": " ", "—": "-",
        "（": "(", "）": ")", "„": '"', "“": '"', "”": '"', "‘": "'", "’": "'",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return "\n".join([ln.strip() for ln in text.splitlines() if ln.strip()])

def _rasterize_first_page_to_jpeg(pdf_bytes: bytes) -> bytes:
    """
    Convert first page of a PDF to a high-quality JPEG (RGB).
    Uses PyMuPDF which is already used elsewhere in main.py.
    """
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    if pdf_document.page_count == 0:
        raise ValueError("PDF has no pages")
    page = pdf_document[0]
    mat = fitz.Matrix(3.0, 3.0)  # 216 DPI approx
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img_png = pix.tobytes("png")

    image = Image.open(io.BytesIO(img_png))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=95, optimize=True)
    out = buf.getvalue()
    buf.close()
    pdf_document.close()
    return out

def _to_temp_image(file_bytes: bytes, content_type: str, original_name: str) -> str:
    """
    Accepts bytes from upload (jpg/png/pdf) and returns a temporary JPEG/PNG filepath.
    If PDF, rasterizes the first page to JPEG.
    """
    suffix = ".jpg"
    img_bytes = file_bytes

    if (content_type and "pdf" in content_type.lower()) or (original_name.lower().endswith(".pdf")):
        img_bytes = _rasterize_first_page_to_jpeg(file_bytes)
        suffix = ".jpg"
    else:
        # If it's image/* we keep original. For safety, we normalize to JPG
        try:
            im = Image.open(io.BytesIO(file_bytes))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            b = io.BytesIO()
            im.save(b, format="JPEG", quality=95, optimize=True)
            img_bytes = b.getvalue()
            b.close()
            suffix = ".jpg"
        except Exception:
            # If Pillow fails, just write as-is and hope OCR can read it
            suffix = os.path.splitext(original_name)[1] or ".bin"

    fd, temp_path = tempfile.mkstemp(prefix="vc_", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(img_bytes)
    return temp_path


@app.post("/openai_extract")
async def openai_extract(request: ExtractionRequest):
    """Extract data from PDF/JPEG/JPG/PNG files - returns only template_name + extracted data"""
    try:
        # Validate content
        file_content = extract_base64_content(request.p_input_content)
        if not file_content:
            raise HTTPException(status_code=400, detail="Invalid base64 content")
        
        # Validate prompts
        if not request.p_template_prompt_header.strip() and not request.p_template_prompt_details.strip():
            raise HTTPException(status_code=400, detail="At least one prompt required")
        
        # Process with OpenAI
        if request.p_api_name.lower() != "openai":
            raise HTTPException(status_code=400, detail="Only OpenAI supported")
        
        logger.info(f"Processing request for template: {request.p_template_name}")
        
        result = process_with_openai(
            request.p_api_key, request.p_api_model, 
            request.p_template_prompt_header, request.p_template_prompt_details, 
            file_content, request.p_api_token, request.p_temperature, 
            request.p_top_p, request.p_timeout
        )
        
        logger.info(f"OpenAI processing result: success={result['success']}")
        
        if result["success"]:
            # Handle both object and array responses
            extracted_data = result["extracted_data"]
            
            if isinstance(extracted_data, dict):
                # If it's an object, unpack it
                return {
                    "template_name": request.p_template_name,
                    **extracted_data
                }
            elif isinstance(extracted_data, list):
                # If it's an array, put it under 'data' key
                return {
                    "template_name": request.p_template_name,
                    "data": extracted_data
                }
            else:
                # Fallback for other types
                return {
                    "template_name": request.p_template_name,
                    "extracted_data": extracted_data
                }
        else:
            logger.error(f"OpenAI processing failed: {result['error']}")
            raise HTTPException(status_code=500, detail=result["error"])
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
@app.post("/backup")
async def upload_backup_file(file: UploadFile = File(...)):
    try:
        # Ensure backup folder exists
        backup_dir = "backup"
        os.makedirs(backup_dir, exist_ok=True)

        # Save using original filename
        file_path = os.path.join(backup_dir, file.filename)

        # Save the file to disk
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"File saved to {file_path}")
        return {"success": True, "file_path": os.path.abspath(file_path)}

    except Exception as e:
        logger.error(f"File upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

from pydantic import BaseModel

class BackupRequest(BaseModel):
    file_path: str

@app.post("/getbackup")
async def get_backup_file(req: BackupRequest):
    try:
        if not os.path.isfile(req.file_path):
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(
            path=req.file_path,
            filename=os.path.basename(req.file_path),
            media_type="application/octet-stream"
        )
    except Exception as e:
        logger.error(f"Error while sending backup file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error returning file: {str(e)}")


@app.post("/aws_upload")
async def upload_pdf(request: Request):
    try:
        # Get file name from header
        file_name = request.headers.get("x-file-name")
        if not file_name:
            raise HTTPException(status_code=400, detail="Missing x-file-name header")

        # Generate file path for S3
        filename = f"uploads/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_name}"

        # Read and decode base64
        base64_data = await request.body()
        pdf_bytes = base64.b64decode(base64_data)

        # Upload to S3 with proper MIME type
        s3.put_object(
            Bucket=BUCKET,
            Key=filename,
            Body=pdf_bytes,
            ContentType="application/pdf"
        )

        logger.info(f"Uploaded file to S3: s3://{BUCKET}/{filename}")
        return {"success": True, "file_name": filename, "bucket": BUCKET}
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.post("/textract/aws_start_expense")
def start_expense_analysis(req: dict):
    try:
        response = textract.start_expense_analysis(
            DocumentLocation={"S3Object": {"Bucket": req["bucket"], "Name": req["file_name"]}}
        )
        return {"JobId": response["JobId"]}
    except Exception as e:
        logger.error(f"ExpenseAnalysis start failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/textract/aws_get_expense/{job_id}")
def get_expense_invoice_data(job_id: str):
    try:
        pages = []
        response = textract.get_expense_analysis(JobId=job_id)
        pages.append(response)
        token = response.get("NextToken", None)
        while token:
            response = textract.get_expense_analysis(JobId=job_id, NextToken=token)
            pages.append(response)
            token = response.get("NextToken", None)
    except Exception as e:
        logger.error(f"ExpenseAnalysis retrieval failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Textract retrieval failed: {str(e)}")

    extracted_data = {
        "summary_fields": [],
        "line_items": []
    }

    for page in pages:
        for doc in page.get("ExpenseDocuments", []):
            # Summary fields (like Vendor Name, Invoice Date, etc.)
            for field in doc.get("SummaryFields", []):
                label = field.get("LabelDetection", {}).get("Text", "").strip()
                value = field.get("ValueDetection", {}).get("Text", "").strip()
                if label or value:
                    extracted_data["summary_fields"].append({
                        "label": label,
                        "value": value
                    })

            # Line items (like container & charges table)
            for group in doc.get("LineItemGroups", []):
                for item in group.get("LineItems", []):
                    row = {}
                    for field in item.get("LineItemExpenseFields", []):
                        label = field.get("LabelDetection", {}).get("Text", "").strip()
                        value = field.get("ValueDetection", {}).get("Text", "").strip()
                        if label or value:
                            row[label] = value
                    if row:
                        extracted_data["line_items"].append(row)

    return extracted_data

@app.post("/textract/aws_start_document")
def start_textract(req: dict):
    try:
        response = textract.start_document_analysis(
            DocumentLocation={"S3Object": {"Bucket": req["bucket"], "Name": req["file_name"]}},
            FeatureTypes=["FORMS", "TABLES"]
        )
        return {"JobId": response["JobId"]}
    except Exception as e:
        logger.error(f"Textract start failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/textract/aws_get_document_status/{job_id}")
def get_status(job_id: str):
    result = textract.get_document_analysis(JobId=job_id)
    return {"JobStatus": result["JobStatus"]}


@app.get("/textract/aws_get_document_result/{job_id}")
def get_result(job_id: str):
    pages = []
    response = textract.get_document_analysis(JobId=job_id)
    pages.append(response)
    token = response.get("NextToken", None)
    while token:
        response = textract.get_document_analysis(JobId=job_id, NextToken=token)
        pages.append(response)
        token = response.get("NextToken", None)
    return {"pages": pages}

@app.get("/textract/aws_get_document/{job_id}")
def extract_vendor_invoice_json(job_id: str) -> Dict:
    try:
        pages = []
        response = textract.get_document_analysis(JobId=job_id)
        pages.append(response)
        token = response.get("NextToken", None)
        while token:
            response = textract.get_document_analysis(JobId=job_id, NextToken=token)
            pages.append(response)
            token = response.get("NextToken", None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Textract retrieval failed: {str(e)}")

    block_map = {}
    key_map = {}
    value_map = {}
    table_blocks = []

    for page in pages:
        for block in page["Blocks"]:
            block_map[block["Id"]] = block
            if block["BlockType"] == "KEY_VALUE_SET":
                if "KEY" in block["EntityTypes"]:
                    key_map[block["Id"]] = block
                else:
                    value_map[block["Id"]] = block
            elif block["BlockType"] == "TABLE":
                table_blocks.append(block)

    def get_text(block):
        text = ""
        if "Relationships" in block:
            for rel in block["Relationships"]:
                if rel["Type"] == "CHILD":
                    for cid in rel["Ids"]:
                        word = block_map.get(cid, {})
                        if word.get("BlockType") == "WORD":
                            text += word.get("Text", "") + " "
                        elif word.get("BlockType") == "SELECTION_ELEMENT" and word.get("SelectionStatus") == "SELECTED":
                            text += "X "
        return text.strip()

    # Extract header fields
    header_fields = {}
    for key_id, key_block in key_map.items():
        key_text = get_text(key_block)
        val_text = ""
        if "Relationships" in key_block:
            for rel in key_block["Relationships"]:
                if rel["Type"] == "VALUE":
                    for val_id in rel["Ids"]:
                        val_block = value_map.get(val_id)
                        val_text = get_text(val_block)
        if key_text:
            header_fields[key_text] = val_text

    def extract_table(table_block):
        rows = {}
        for block in pages[0]["Blocks"]:
            if block["BlockType"] == "CELL" and block.get("Page") == table_block.get("Page"):
                row = block["RowIndex"]
                col = block["ColumnIndex"]
                text = get_text(block)
                rows.setdefault(row, {})[col] = text

        headers = rows.get(1, {})
        table_data = []
        for row_idx in sorted(rows.keys()):
            if row_idx == 1:
                continue
            row_data = {}
            for col_idx, col_val in rows[row_idx].items():
                col_name = headers.get(col_idx, f"Column{col_idx}")
                row_data[col_name] = col_val
            table_data.append(row_data)
        return table_data

    charges_table = []
    container_table = []
    for table in table_blocks:
        table_data = extract_table(table)
        table_str = " ".join([",".join(row.values()) for row in table_data]).lower()
        if "container" in table_str:
            container_table.extend(table_data)
        else:
            charges_table.extend(table_data)

    # Remove duplicates from charges table
    seen = set()
    deduped_charges = []
    for row in charges_table:
        key = tuple((k.lower().strip(), v.lower().strip()) for k, v in row.items())
        if key not in seen:
            deduped_charges.append(row)
            seen.add(key)

    return {
        "header_fields": header_fields,
        "charges_table": deduped_charges,
        "container_table": container_table
    }

class InvoiceSignRequest(BaseModel):
    invoice_pdf_base64: str
    name: str
    password: str
    username: Optional[str] = None
    reason: Optional[str] = "Document Authentication"
    location: Optional[str] = "India"
    visible_signature: Optional[bool] = True    
    page_number: Optional[int] = -1
    x_coordinate: Optional[float] = 350
    y_coordinate: Optional[float] = 50
    box_width: Optional[float] = 200
    box_height: Optional[float] = 70

class InvoiceSignResponse(BaseModel):
    signed_pdf_base64: str
    error: Optional[str] = None
    auth_error: Optional[str] = None
    signature_info: Optional[dict] = None

# 13-jun-25 senthil for extract_email_attachments
def allowed_file(filename):
    """Check if uploaded file has allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_type(filename):
    """Determine file type based on extension"""
    if filename.lower().endswith('.msg'):
        return 'msg'
    elif filename.lower().endswith('.eml'):
        return 'eml'
    return None


CERT_DIRECTORY = Path("certs")
os.makedirs(CERT_DIRECTORY, exist_ok=True)

def get_cert_path(name: str) -> Optional[Path]:
    cert_path = CERT_DIRECTORY / f"{name}.pfx"
    if cert_path.exists():
        return cert_path
    cert_path = CERT_DIRECTORY / f"{name.lower()}.pfx"
    if cert_path.exists():
        return cert_path
    name_safe = name.lower().replace(" ", "_")
    cert_path = CERT_DIRECTORY / f"{name_safe}.pfx"
    if cert_path.exists():
        return cert_path
    return None

def load_pkcs12_certificate(cert_path: Path, password: str):
    try:
        with open(cert_path, 'rb') as f:
            pfx_data = f.read()
        private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
            pfx_data, 
            password.encode('utf-8'),
            backend=default_backend()
        )
        subject = certificate.subject
        common_name = None
        organization = None
        for attribute in subject:
            if attribute.oid == NameOID.COMMON_NAME:
                common_name = attribute.value
            elif attribute.oid == NameOID.ORGANIZATION_NAME:
                organization = attribute.value
        return {
            'private_key': private_key,
            'certificate': certificate,
            'additional_certs': additional_certs or [],
            'common_name': common_name,
            'organization': organization
        }
    except Exception as e:
        logger.error(f"Failed to load certificate: {str(e)}")
        raise

def create_invisible_stamp():
    """Create an invisible stamp with no visual content"""
    try:
        # Create empty/invisible text stamp
        text_box_style = TextBoxStyle(
            font_size=1,  # Minimal font size
            text_sep=0
        )
        
        return TextStampStyle(
            stamp_text="",  # Empty text
            text_box_style=text_box_style,
            background_opacity=0.0  # Completely transparent
        )
    except Exception as e:
        logger.error(f"Error creating invisible stamp: {str(e)}")
        return None

def sign_pdf_with_pyhanko(pdf_data: bytes, cert_info: dict, 
                         signer_name: str, reason: str, location: str,
                         visible: bool = True, page: int = -1,
                         x: float = 450, y: float = 50,
                         box_width: float = 200, box_height: float = 70) -> bytes:
    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                sign_pdf_sync,
                pdf_data, cert_info, signer_name, reason, location,
                visible, page, x, y, box_width, box_height
            )
            return future.result(timeout=30)
    except concurrent.futures.TimeoutError:
        logger.error("PDF signing timed out")
        raise Exception("PDF signing operation timed out")
    except Exception as e:
        logger.error(f"Error signing PDF with pyHanko: {str(e)}")
        raise

def sign_pdf_sync(pdf_data: bytes, cert_info: dict, 
                  signer_name: str, reason: str, location: str,
                  visible: bool = True, page: int = -1,
                  x: float = 450, y: float = 50,
                  box_width: float = 200, box_height: float = 70) -> bytes:
    from io import BytesIO
    signed_pdf = None
    try:
        reader = PdfFileReader(BytesIO(pdf_data))
        try:
            page_tree = reader.page_tree
            total_pages = sum(1 for _ in page_tree)
        except:
            total_pages = reader.root['/Pages']['/Count']
        if page == -1:
            page = total_pages - 1
        elif page > 0:
            page = page - 1
        page = max(0, min(page, total_pages - 1))
        logger.info(f"Signing PDF: {total_pages} pages, placing signature on page {page + 1}")
        
        signer = signers.SimpleSigner.load_pkcs12(
            pfx_file=str(cert_info['cert_path']),
            passphrase=cert_info['password'].encode('utf-8')
        )
        
        # Create signature metadata without stamp_style
        signature_meta = signers.PdfSignatureMetadata(
            field_name='Signature1',
            name=signer_name,
            location=location,
            reason=reason,
            md_algorithm='sha256',
            subfilter=SigSeedSubFilter.ADOBE_PKCS7_DETACHED
        )
        
        if visible:
            w = IncrementalPdfFileWriter(BytesIO(pdf_data))
            sig_field_spec = fields.SigFieldSpec(
                sig_field_name='Signature1',
                on_page=page,
                box=(x, y, x + box_width, y + box_height)
            )
            fields.append_signature_field(w, sig_field_spec)
            prepared_buf = BytesIO()
            w.write(prepared_buf)
            prepared_buf.seek(0)
            
            # Try primary method first, silently fall back if needed
            try:
                from pyhanko.sign.signers.pdf_signer import sign_pdf
                result = sign_pdf(
                    pdf_in=prepared_buf,
                    signers=[signer],
                    signature_meta=signature_meta,
                    existing_fields_only=True,
                )
                if hasattr(result, 'read'):
                    signed_pdf = result.read()
                else:
                    signed_pdf = result
            except (ImportError, AttributeError):
                # Silent fallback - no error logging
                w2 = IncrementalPdfFileWriter(prepared_buf)
                out = signers.sign_pdf(
                    w2,
                    signature_meta,
                    signer=signer,
                    existing_fields_only=True
                )
                out_buf = BytesIO()
                if hasattr(out, 'write_to'):
                    out.write_to(out_buf)
                elif hasattr(out, 'getvalue'):
                    out_buf.write(out.getvalue())
                else:
                    out_buf.write(out)
                out_buf.seek(0)
                signed_pdf = out_buf.getvalue()
        else:
            # Invisible signature - no visual appearance at all
            try:
                from pyhanko.sign.signers.pdf_signer import sign_pdf
                result = sign_pdf(
                    pdf_in=BytesIO(pdf_data),
                    signers=[signer],
                    signature_meta=signature_meta
                )
                if hasattr(result, 'read'):
                    signed_pdf = result.read()
                else:
                    signed_pdf = result
            except (ImportError, AttributeError):
                # Silent fallback for invisible signatures
                w = IncrementalPdfFileWriter(BytesIO(pdf_data))
                out = signers.sign_pdf(
                    w,
                    signature_meta,
                    signer=signer
                )
                out_buf = BytesIO()
                if hasattr(out, 'write_to'):
                    out.write_to(out_buf)
                elif hasattr(out, 'getvalue'):
                    out_buf.write(out.getvalue())
                else:
                    out_buf.write(out)
                out_buf.seek(0)
                signed_pdf = out_buf.getvalue()
                
        if not isinstance(signed_pdf, bytes):
            raise ValueError("Failed to get bytes from signing operation")
        return signed_pdf
        
    except Exception as e:
        logger.error(f"Error in synchronous signing: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise

@app.post("/sign-invoice", response_model=InvoiceSignResponse)
async def sign_invoice(request: InvoiceSignRequest):
    auth_error = None
    error = None
    logger.info(f"Digital signature request for: {request.name}")
    
    try:
        # Decode base64 PDF
        try:
            pdf_data = base64.b64decode(request.invoice_pdf_base64, validate=True)
            logger.info(f"Decoded PDF: {len(pdf_data)} bytes")
        except binascii.Error as e:
            logger.error(f"Base64 decoding failed: {str(e)}")
            return JSONResponse(
                status_code=400,
                content={"error": f"Invalid base64 encoding: {str(e)}"}
            )
        
        # Validate PDF format
        if not pdf_data.startswith(b'%PDF'):
            logger.error("Invalid PDF format - missing PDF header")
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid PDF format"}
            )
        
        # Test PDF structure
        try:
            test_reader = PdfFileReader(BytesIO(pdf_data))
            _ = len(test_reader.root['/Pages']['/Kids'])
        except Exception as e:
            logger.error(f"PDF parsing failed: {str(e)}")
            return JSONResponse(
                status_code=400,
                content={"error": f"Invalid PDF structure: {str(e)}"}
            )
        
        # Find certificate
        cert_path = get_cert_path(request.name)
        if not cert_path:
            logger.warning(f"Certificate not found for name: {request.name}")
            return InvoiceSignResponse(
                signed_pdf_base64=request.invoice_pdf_base64,
                error="Invalid name",
                auth_error=None,
                signature_info=None
            )
        
        # Validate username if provided
        if request.username is not None and request.username != request.name:
            logger.warning(f"Username mismatch: {request.username} vs {request.name}")
            return InvoiceSignResponse(
                signed_pdf_base64=request.invoice_pdf_base64,
                error=None,
                auth_error="Invalid username",
                signature_info=None
            )
        
        # Load certificate
        try:
            cert_info = load_pkcs12_certificate(cert_path, request.password)
            cert_info['cert_path'] = cert_path
            cert_info['password'] = request.password
        except Exception as e:
            logger.warning(f"Invalid password for certificate: {request.name}")
            return InvoiceSignResponse(
                signed_pdf_base64=request.invoice_pdf_base64,
                error="Invalid password",
                auth_error=None,
                signature_info=None
            )
        
        # Sign PDF
        try:
            signed_pdf = sign_pdf_with_pyhanko(
                pdf_data,
                cert_info,
                request.name,
                request.reason,
                request.location,
                request.visible_signature,
                request.page_number,
                request.x_coordinate,
                request.y_coordinate,
                request.box_width,
                request.box_height
            )
            
            signed_pdf_base64 = base64.b64encode(signed_pdf).decode('utf-8')
            
            signature_info = {
                "signer": request.name,
                "organization": cert_info['organization'],
                "timestamp": datetime.now().isoformat(),
                "reason": request.reason,
                "location": request.location,
                "verification_status": "Signature created - Click signature field to verify",
                "verification_note": "❓ Red question mark will show initially, ✅ green checkmark after verification"
            }
            
            logger.info(f"✓ Digital signature completed successfully for {request.name}")
            return InvoiceSignResponse(
                signed_pdf_base64=signed_pdf_base64,
                error=None,
                auth_error=None,
                signature_info=signature_info
            )
            
        except Exception as e:
            logger.error(f"Internal error during signing: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Internal signing error: {str(e)}"}
            )
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Unexpected server error: {str(e)}"}
        )

@app.get("/")
async def root():
    cert_count = len(list(CERT_DIRECTORY.glob("*.pfx")))
    return {
        "service": "Adobe-Compatible Digital Signature API",
        "description": "Creates clean digital signatures without visual stamps",
        "version": "6.1.0",
        "signature_type": "PKCS#7 Digital Signature",
        "features": [
            "Clean signature field without purple stamp",
            "Click-to-verify system with visual indicators",
            "❓ Red question mark for unverified signatures",
            "✅ Green checkmark after verification",
            "Certificate chain validation",
            "Compliant with Adobe PDF standards",
            "Optional invisible signatures"
        ],
        "verification": [
            "Signature field appears as clickable area",
            "Click signature to verify and see certificate details",
            "Visual indicator changes from ❓ to ✅ upon verification",
            "Green checkmark indicates valid signature",
            "Yellow triangle indicates signature without trusted timestamp",
            "Red X indicates invalid or tampered signature"
        ],
        "certificates_available": cert_count,
        "requirements": [
            "Certificate must be from trusted CA for green checkmark",
            "Self-signed certificates will show yellow warning",
            "Install pip install pyhanko[pkcs11,image-support,opentype]"
        ]
    }

@app.post("/validate-signature")
async def validate_signature(request: dict):
    try:
        from pyhanko.sign import validation
        pdf_base64 = request.get('signed_pdf_base64')
        if not pdf_base64:
            return {"error": "signed_pdf_base64 field required"}
        
        pdf_data = base64.b64decode(pdf_base64, validate=True)
        pdf_reader = PdfFileReader(BytesIO(pdf_data))
        
        if not pdf_reader.embedded_signatures:
            return {
                "has_signatures": False,
                "message": "No digital signatures found in PDF"
            }
        
        signatures = []
        for sig_field in pdf_reader.embedded_signatures:
            try:
                val_result = validation.validate_pdf_signature(
                    pdf_reader,
                    sig_field,
                    validation.StandardVerificationContext()
                )
                sig_info = {
                    "field_name": sig_field.field_name,
                    "signer": val_result.signer_cert.subject.rfc4514_string() if val_result.signer_cert else "Unknown",
                    "valid": val_result.valid,
                    "trusted": val_result.trusted,
                    "timestamp": str(val_result.timestamp) if val_result.timestamp else None,
                    "intact": val_result.intact,
                    "status": "Valid" if val_result.valid and val_result.intact else "Invalid",
                    "visual_indicator": "✅ Verified" if val_result.valid and val_result.intact else "❓ Needs Verification"
                }
                signatures.append(sig_info)
            except Exception as e:
                signatures.append({
                    "field_name": sig_field.field_name,
                    "error": str(e),
                    "visual_indicator": "❓ Error"
                })
        
        return {
            "has_signatures": True,
            "signature_count": len(signatures),
            "signatures": signatures,
            "message": "Signatures found and validated"
        }
        
    except Exception as e:
        return {"error": str(e)}

# Email Attachment Extraction Endpoints
@app.post('/extract_email_attachments')
async def extract_attachments(file: UploadFile = File(...)):
    """Main endpoint to extract supported attachments from email files"""
    
    try:
        logger.info("=== NEW EMAIL EXTRACTION REQUEST STARTED ===")
        
        # Check if file is selected
        if file.filename == '':
            raise HTTPException(status_code=400, detail="No file selected")
        
        # Validate file type
        if not allowed_file(file.filename):
            raise HTTPException(status_code=400, detail="Invalid file type. Only .msg and .eml files are allowed")
        
        # Read file content
        file_content = await file.read()
        file_type = get_file_type(file.filename)
        
        logger.info(f"Processing {file_type.upper()} file: {file.filename} ({len(file_content)} bytes)")
        
        # Extract attachments based on file type
        extractor = EmailAttachmentExtractor()
        
        if file_type == 'eml':
            attachments = extractor.extract_from_eml(file_content)
        elif file_type == 'msg':
            attachments = extractor.extract_from_msg(file_content)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        
        logger.info(f"EXTRACTION RESULT: Found {len(attachments)} supported attachments")
        
        # Count attachments by type
        file_type_counts = {}
        for att in attachments:
            ext = att.get('file_extension', '.unknown')
            file_type_counts[ext] = file_type_counts.get(ext, 0) + 1
        
        # Prepare response with individual base64 for each attachment
        response_data = {
            'success': True,
            'message': f'Successfully processed {file.filename}',
            'file_type': file_type,
            'total_attachments': len(attachments),
            'file_type_counts': file_type_counts,
            'supported_formats': list(EmailAttachmentExtractor.SUPPORTED_EXTENSIONS),
            'attachments': []
        }
        
        # Add each attachment with individual base64 content
        for i, attachment in enumerate(attachments):
            attachment_info = {
                'index': i + 1,
                'filename': attachment['filename'],
                'content_type': attachment['content_type'],
                'file_extension': attachment['file_extension'],
                'size_bytes': attachment['size_bytes'],
                'base64_length': len(attachment['content']),
                'content': attachment['content']  # Individual base64 content for each file
            }
            response_data['attachments'].append(attachment_info)
            logger.info(f"RESPONSE: Added attachment {i+1}: {attachment['filename']} ({attachment['file_extension']}) (base64 length: {len(attachment['content'])})")
        
        # Final verification
        logger.info(f"FINAL RESPONSE CHECK:")
        logger.info(f"  total_attachments: {response_data['total_attachments']}")
        logger.info(f"  file_type_counts: {response_data['file_type_counts']}")
        logger.info(f"  attachments array length: {len(response_data['attachments'])}")
        logger.info(f"  attachment filenames: {[att['filename'] for att in response_data['attachments']]}")
        
        # Double-check that we have unique content for each attachment
        base64_contents = [att['content'] for att in response_data['attachments']]
        unique_contents = set(base64_contents)
        logger.info(f"  unique base64 contents: {len(unique_contents)} (should equal total_attachments)")
        
        if len(unique_contents) != len(base64_contents):
            logger.warning("WARNING: Some attachments have identical content!")
            for i, content in enumerate(base64_contents):
                logger.warning(f"  Attachment {i+1} base64 hash: {hash(content)}")
        
        logger.info("=== EMAIL EXTRACTION RESPONSE BEING SENT ===")
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing email extraction request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# 2025-06-13: New endpoint to upload .pfx certificate files (with overwrite option)
@app.post("/upload_certificate")  # 2025-06-13: New endpoint for uploading .pfx files
async def upload_certificate(
    file: UploadFile = File(".pfx"),  # 2025-06-13: Accept .pfx file
    overwrite: bool = Form(False)  # 2025-06-13: Overwrite option
):
    cert_dir = Path("certs")  # 2025-06-13: Cert directory
    cert_dir.mkdir(exist_ok=True)
    cert_path = cert_dir / file.filename
    if cert_path.exists() and not overwrite:
        raise HTTPException(status_code=409, detail="Certificate already exists. Set overwrite=True to replace.")  # 2025-06-13
    # 2025-06-13: Only accept .pfx files
    if not file.filename.lower().endswith('.pfx'):
        raise HTTPException(status_code=400, detail="Only .pfx files are allowed.")  # 2025-06-13: Reject non-pfx files
    try:
        with open(cert_path, "wb") as f:
            f.write(await file.read())  # 2025-06-13: Save uploaded file
        return {"success": True, "filename": file.filename, "overwritten": cert_path.exists()}  # 2025-06-13
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save certificate: {str(e)}")  # 2025-06-13

#19-June-2025 - Cargo Manifest Extraction
#---------------------------------------------------------------
# Define logs directory and create if it doesn't exist
LOGS_DIR = Path("logs")
os.makedirs(LOGS_DIR, exist_ok=True)

class CargoManifestExtractor:
    """
    Extracts key-value pairs, tables, and text from documents using AWS Textract.
    """
    def __init__(self):
        self.client = boto3.client(
            'textract',
            aws_access_key_id=AWS_KEY,
            aws_secret_access_key=AWS_SECRET,
            region_name=REGION
        )

    def extract_manifest_data(self, document_bytes: bytes, content_type: str) -> Dict[str, Any]:
        MIN_CONF = 85.0
        container_pattern = re.compile(r'^[A-Z]{4}\d{7}$')
        weight_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*(KG|KGS|KG\(S\))', re.IGNORECASE)
        date_pattern = re.compile(r'\d{1,2}-[A-Z]{3}-\d{2,4}')

        if content_type == 'application/pdf':
            s3 = boto3.client('s3', aws_access_key_id=AWS_KEY, aws_secret_access_key=AWS_SECRET, region_name=REGION)
            key = f"{uuid.uuid4()}.pdf"
            s3.put_object(Bucket=BUCKET, Key=key, Body=document_bytes)
            job = self.client.start_document_analysis(
                DocumentLocation={'S3Object': {'Bucket': BUCKET, 'Name': key}},
                FeatureTypes=['TABLES', 'FORMS']
            )
            job_id = job['JobId']
            while True:
                res = self.client.get_document_analysis(JobId=job_id)
                status = res.get('JobStatus')
                if status == 'SUCCEEDED':
                    response = res
                    break
                if status == 'FAILED':
                    raise Exception('Textract job failed')
                time.sleep(1)
        else:
            response = self.client.analyze_document(Document={'Bytes': document_bytes}, FeatureTypes=['TABLES', 'FORMS'])

        blocks = response.get('Blocks', [])
        block_map = {b['Id']: b for b in blocks}

        def get_text(b: Dict[str, Any]) -> str:
            text = ''
            for rel in b.get('Relationships', []):
                if rel['Type'] == 'CHILD':
                    for cid in rel['Ids']:
                        c = block_map.get(cid)
                        if c and c['BlockType'] == 'WORD':
                            text += c.get('Text', '') + ' '
                        elif c and c['BlockType'] == 'SELECTION_ELEMENT' and c.get('SelectionStatus') == 'SELECTED':
                            text += 'X '
            return text.strip()

        key_map, value_map = {}, {}
        for b in blocks:
            if b['BlockType'] == 'KEY_VALUE_SET':
                types = b.get('EntityTypes', [])
                if 'KEY' in types:
                    key_map[b['Id']] = b
                elif 'VALUE' in types:
                    value_map[b['Id']] = b

        kv_dict = {}
        for key_id, key_block in key_map.items():
            if key_block.get('Confidence', 0.0) < MIN_CONF:
                continue
            val_block = None
            for rel in key_block.get('Relationships', []):
                if rel['Type'] == 'VALUE':
                    val_block = value_map.get(rel['Ids'][0])
                    break
            if val_block and val_block.get('Confidence', 0.0) < MIN_CONF:
                continue
            raw_key = get_text(key_block)
            raw_val = get_text(val_block) if val_block else ''
            if 'agent' in raw_key.lower() and raw_val:
                raw_val = ' '.join(w.capitalize() for w in raw_val.split())
            if weight_pattern.search(raw_val):
                num = float(weight_pattern.search(raw_val).group(1)); raw_val = f"{num:.2f} KG"
            kv_dict[raw_key] = raw_val

        tables = []
        for b in blocks:
            if b['BlockType'] == 'TABLE':
                cells = [block_map[cid] for rel in b.get('Relationships', []) if rel['Type'] == 'CHILD' for cid in rel['Ids']]
                rows = {}
                for cell in cells:
                    if cell['BlockType'] != 'CELL': continue
                    r, cidx = cell.get('RowIndex', 0), cell.get('ColumnIndex', 0)
                    rows.setdefault(r, {})[cidx] = get_text(cell)
                table_data = [[rows[r][c] for c in sorted(rows[r].keys())] for r in sorted(rows.keys())]
                tables.append(table_data)

        parsed_tables = []
        for table_data in tables:
            if not table_data: continue
            if len(table_data[0]) == 2:
                parsed_tables.append({row[0]: row[1] for row in table_data})
            else:
                headers = table_data[0]
                parsed_tables.append([
                    {headers[i]: row[i] for i in range(len(headers))} for row in table_data[1:]
                ])

        return {'key_value_pairs': kv_dict, 'tables': parsed_tables}

# Initialize CargoManifestExtractor (use existing FastAPI app)
extractor = CargoManifestExtractor()

@app.post('/manifest_extract')
async def extract_manifest(file: UploadFile = File(...)):
    if file.content_type not in ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff']:
        raise HTTPException(status_code=400, detail='Unsupported file type')
    try:
        content = await file.read()
        data = extractor.extract_manifest_data(content, file.content_type)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error("Error extracting manifest: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")

from fastapi import Body

class EmailBase64Request(BaseModel):
    file_base64: str
    file_type: str  # 'eml' or 'msg'
    file_name: str = None

@app.post("/extract_email_attachments_base64")
async def extract_attachments_base64(request: EmailBase64Request):
    """Extract attachments from base64 EML/MSG input."""
    try:
        file_content = base64.b64decode(request.file_base64)
        extractor = EmailAttachmentExtractor()
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

from collections import defaultdict
request_counts = defaultdict(int)
request_logs = defaultdict(list)

@app.middleware("http")
async def log_and_count_requests(request: Request, call_next):
    path = request.url.path
    if path != "/custom_logic":
        request_counts[path] += 1
        req_body = None
        req_file = None
        try:
            req_body = await request.body()
            if req_body:
                req_json = req_body.decode("utf-8")
                req_filename = f"{uuid.uuid4()}_request.json"
                req_file_path = LOGS_DIR / req_filename
                with open(req_file_path, "w", encoding="utf-8") as f:
                    f.write(req_json)
                req_file = str(req_file_path)
        except Exception:
            pass
        response = await call_next(request)
        resp_file = None
        try:
            if hasattr(response, 'body_iterator'):
                resp_body = b''
                async for chunk in response.body_iterator:
                    resp_body += chunk
                async def new_body_iterator():
                    yield resp_body
                response.body_iterator = new_body_iterator()  
                resp_json = resp_body.decode("utf-8")
                resp_filename = f"{uuid.uuid4()}_response.json"
                resp_file_path = LOGS_DIR / resp_filename
                with open(resp_file_path, "w", encoding="utf-8") as f:
                    f.write(resp_json)
                resp_file = str(resp_file_path)
        except Exception:
            pass
        log_entry = {
            "api_name": path,
            "requested_date": datetime.now().strftime("%d-%b-%Y %I:%M:%S %p"),
            "requested_url": str(request.url),
            "requested_ip": request.client.host if request.client else None,
            "request_file": req_file,  
            "response_file": resp_file  
        }
        request_logs[path].append(log_entry)
        logger.info(f"[MONITOR] {log_entry}")
        return response
    else:
        response = await call_next(request)
        return response

@app.get("/{endpoint_path:path}/logs")
async def get_endpoint_logs(endpoint_path: str, request: Request):
    path = "/" + endpoint_path.strip("/")
    logs = []
    for entry in request_logs.get(path, []):
        log_copy = entry.copy()
        if log_copy.get("request_file"):
            log_copy["request_file_url"] = str(request.base_url) + f"logs/files/{Path(log_copy['request_file']).name}"
        if log_copy.get("response_file"):
            log_copy["response_file_url"] = str(request.base_url) + f"logs/files/{Path(log_copy['response_file']).name}"
        logs.append(log_copy)
    return {"endpoint": path, "logs": logs, "request_count": len(logs)}


@app.get("/logs/files/{filename}")
async def download_log_file(filename: str):
    file_path = LOGS_DIR / filename  
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path), filename=filename, media_type="application/json")
#--------------------------------------------------------------------------------------------

def _extract_card_json_with_openai(api_key: str, model: str, raw_text: str, cleaned_text: str, timeout: int = 120) -> dict:
    """
    Universal OpenAI extractor for GPT-4 and GPT-5 series.
    - Uses correct params (`max_tokens` or `max_completion_tokens`)
    - Enforces pure JSON output
    - Retries once if model returns empty/non-JSON
    """
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    # ======= Strong system + user prompt =======
    system_msg = {
        "role": "system",
        "content": (
            "You are an AI data extractor. "
            "Your only task is to output valid JSON. "
            "Do not include explanations, text, or markdown. "
            "Output must be a single JSON object following exactly the required keys."
        ),
    }

    user_prompt = f"""
Extract structured contact information from the OCR text below.

Rules:
1️⃣ Always detect multiple companies, phone numbers, and addresses if they exist.
2️⃣ Each key must contain an array of strings, even if one value.
3️⃣ Required keys:
   - name
   - designation
   - company_name
   - emails
   - phone_numbers
   - address
   - city
   - country
   - website
   - slogan
4️⃣ Merge multi-line addresses but keep different locations separate.
5️⃣ Fix OCR mistakes (e.g. '@ ' → '@', 'dot' → '.').

Example:
{{
  "name": ["John Smith"],
  "designation": ["Sales Director"],
  "company_name": ["ABC Logistics", "XYZ Shipping"],
  "emails": ["john@abclogistics.com"],
  "phone_numbers": ["+1 212-555-7890", "+971 50 123 4567"],
  "address": ["123 Main St, New York, USA", "Dubai Marina, UAE"],
  "city": ["New York", "Dubai"],
  "country": ["USA", "UAE"],
  "website": ["www.abclogistics.com"],
  "slogan": ["We move the world"]
}}

Now extract from:

Raw OCR:
\"\"\"{raw_text}\"\"\"

Cleaned OCR:
\"\"\"{cleaned_text}\"\"\"
"""

    # ======= Dynamic payload based on model family =======
    payload = {
        "model": model,
        "messages": [system_msg, {"role": "user", "content": user_prompt}],
    }

    # GPT-5 models need max_completion_tokens
    if model.startswith("gpt-5"):
        payload["max_completion_tokens"] = 800
    else:
        payload["max_tokens"] = 800
        payload["temperature"] = 0.1
        payload["top_p"] = 0.9

    def call_openai() -> dict:
        resp = requests.post("https://api.openai.com/v1/chat/completions",
                             headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            return {"error": f"OpenAI API error {resp.status_code}: {resp.text[:300]}"}
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"text": content.strip()}

    # ======= Attempt 1 =======
    result = call_openai()
    text = result.get("text", "").strip()

    # ======= Retry once if empty =======
    if not text:
        result = call_openai()
        text = result.get("text", "").strip()

    # ======= Clean and parse =======
    if not text:
        return {"error": "Empty response from model", "raw": ""}

    # Remove markdown fences if present
    for fence in ["```json", "```"]:
        if text.startswith(fence):
            text = text[len(fence):]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except Exception as e:
        return {"error": f"Failed to parse JSON: {e}", "raw": text[:1000]}

# ============================================================
# Visiting Card Scan Endpoint using GPT-5-Mini
# ============================================================

@app.post("/scan_vc")
async def scan_visiting_card(
    file: UploadFile = File(...),
    api_key: Optional[str] = Form(None),
    model: Optional[str] = Form("gpt-5-mini"),   # ✅ Default upgraded to GPT-5-Mini
):
    """
    Scans a visiting card (JPG/PNG/PDF), performs OCR, and returns structured JSON.

    - Accepts multipart/form-data:
        • file: the business card image or PDF
        • api_key (optional): OpenAI API key; falls back to env OPENAI_API_KEY
        • model (optional): OpenAI model (default: gpt-5-mini)
    """
    temp_path = None
    try:
        # 1 Read uploaded file
        file_bytes = await file.read()
        if not file_bytes or len(file_bytes) < 10:
            raise HTTPException(status_code=400, detail="Empty file or too small")

        # 2 Convert to temporary JPEG (handles PDF first-page rasterization)
        temp_path = _to_temp_image(
            file_bytes,
            file.content_type or "",
            file.filename or "upload"
        )

        # 3 Perform OCR → clean artefacts
        raw_text = ocr_extract_card(temp_path)
        cleaned_text = _clean_card_text(raw_text)

        if not cleaned_text.strip():
            return {
                "success": False,
                "message": "No readable text found via OCR.",
                "raw_text": raw_text,
                "cleaned_text": cleaned_text,
            }

        # 4 API key + model
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise HTTPException(
                status_code=400,
                detail="OpenAI API key not provided (form api_key or env OPENAI_API_KEY)"
            )

        # 5 Use the GPT-5-Mini model for JSON extraction
        result = _extract_card_json_with_openai(key, model, raw_text, cleaned_text)

        # 6 Handle helper errors
        if isinstance(result, dict) and "error" in result:
            return {
                "success": False,
                "raw_text": raw_text,
                "cleaned_text": cleaned_text,
                "error": result.get("error"),
                "raw": result.get("raw"),
                "model_used": model,
            }

        # 7 Success path
        return {
            "success": True,
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "parsed_data": result,
            "model_used": model,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visiting card scan error: {str(e)}")
    finally:
        # 8 Always remove temp file
        try:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass


# reporting tool for docx and pdf 
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        check_command = ["/usr/bin/python3", "/usr/bin/unoconv", "--version"]
        result = subprocess.run(check_command, check=True, capture_output=True, text=True)
        print(f"--- Found unoconv. Version: {result.stdout.strip()} ---")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"\nFATAL ERROR: The 'unoconv' command could not be found or executed. Details: {e}\n")
        sys.exit(1)
        
    yield
    print("--- Shutting down executors ---")
    process_pool_executor.shutdown(wait=True)
    thread_pool_executor.shutdown(wait=True)
    print("--- [FastAPI] Cleanup complete ---")

class ReportRequest(BaseModel):
    template_file: str
    report_name: str
    records: list[Dict[str, Any]]

def generate_docx(template_bytes: bytes, context: dict) -> bytes:
    try:
        tpl = DocxTemplate(io.BytesIO(template_bytes))
        tpl.render(context, autoescape=True)
        final_docx_buffer = io.BytesIO()
        tpl.save(final_docx_buffer)
        return final_docx_buffer.getvalue()
    except Exception as e:
        raise RuntimeError(f"Template Error: Unable to render document. Please check your template tags. Details: {str(e)}")

def convert_docx_to_pdf_unoconv(docx_data: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as temp_dir:
        file_id = uuid.uuid4()
        temp_docx_path = os.path.join(temp_dir, f"{file_id}.docx")
        expected_pdf_path = os.path.join(temp_dir, f"{file_id}.pdf")
        proc = None
    
        with open(temp_docx_path, "wb") as f:
            f.write(docx_data)

        command = [
            "/usr/bin/python3",
            "/usr/bin/unoconv",
            "--format", "pdf",
            "-o", expected_pdf_path,
            temp_docx_path
        ]
        
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid
        )

        try:
            stdout, stderr = proc.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            print(f"  -> unoconv timed out for {temp_docx_path}. Killing process group {proc.pid}...")
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait()
            raise RuntimeError("unoconv conversion timed out after 5 minutes.")

        if proc.returncode != 0:
            error_message = f"unoconv failed with exit code {proc.returncode}.\nStderr: {stderr.decode()}\nStdout: {stdout.decode()}"
            raise RuntimeError(error_message)

        if not os.path.exists(expected_pdf_path):
            raise FileNotFoundError(f"PDF file was not created by unoconv at {expected_pdf_path}.")
            
        with open(expected_pdf_path, "rb") as f:
            return f.read()

@app.post("/generate-report")
async def generate_report(
    request: ReportRequest,
    output_format: str = Query("docx", enum=["docx", "pdf"])
):
    try:
        base_template_bytes = base64.b64decode(request.template_file)
    except (base64.binascii.Error, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 template string: {e}")
    
    if not request.records:
        raise HTTPException(status_code=400, detail="The 'records' field must be a non-empty list.")

    try:
        loop = asyncio.get_running_loop()

        print("Starting DOCX generation...")
        start_docx_gen = time.perf_counter()
        
        page_break = RichText('\f')
        context_data = {
            "report_name": request.report_name,
            "records": request.records,
            "page_break": page_break
        }

        final_docx_bytes = await loop.run_in_executor(
            process_pool_executor, generate_docx, base_template_bytes, context_data
        )

        docx_creation_time = time.perf_counter() - start_docx_gen
        print(f"  -> DOCX generation completed in {docx_creation_time:.4f} seconds.")
        
        if output_format == "pdf":
            print("Starting DOCX to PDF conversion (isolated unoconv process)...")
            start_pdf_conv = time.perf_counter()

            pdf_bytes = await loop.run_in_executor(
                thread_pool_executor, convert_docx_to_pdf_unoconv, final_docx_bytes
            )

            pdf_conversion_time = time.perf_counter() - start_pdf_conv
            print(f"  -> PDF conversion completed in {pdf_conversion_time:.4f} seconds.")
            
            filename = f"{request.report_name}.pdf"
            headers = {"Content-Disposition": f'attachment; filename="{filename}"'}


            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers=headers
            )
        else:
            filename = f"{request.report_name}.docx"
            headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

            return Response(
                content=final_docx_bytes,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers=headers
            )

    except ValueError as ve:
        print(f"Template Validation Error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))

    except Exception as e:
        print(f"Error during report generation: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred: {str(e)}")

# reporting end 

# pdf merge begin
def convert_image_to_pdf(image_bytes: bytes) -> BytesIO:
    """Convert image bytes to a single-page PDF."""
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    pdf_bytes = BytesIO()
    image.save(pdf_bytes, format="PDF")
    pdf_bytes.seek(0)
    return pdf_bytes


@app.post("/merge_pdf")
async def merge_base64_json(files: list[dict] = Body(...)):
    """
    Accept multiple base64 files (PDF/JPG/PNG/JPEG) via JSON array,
    merge them into a single PDF, return as base64 JSON,
    and save JSON response to output folder with unique filename.
    """
    try:
        pdf_writer = PdfWriter()
        temp_pdfs = []
        os.makedirs("output", exist_ok=True)

        supported_image_types = ["image/jpeg", "image/jpg", "image/png"]
        supported_pdf_type = "application/pdf"

        for file_info in files:
            filename = file_info.get("filename", "file")
            mimetype = file_info.get("mimetype", "")
            base64content = file_info.get("base64content", "")

            if not base64content:
                raise HTTPException(status_code=400, detail=f"Missing base64content for {filename}")

            # Decode base64 data
            try:
                file_bytes = base64.b64decode(base64content.strip().split(",")[-1])
            except Exception:
                raise HTTPException(status_code=400, detail=f"Invalid base64 data in {filename}")

            temp_pdf_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name

            # --- File Type Validation ---
            if mimetype == supported_pdf_type or file_bytes[:4] == b"%PDF":
                # Handle PDF
                with open(temp_pdf_path, "wb") as f:
                    f.write(file_bytes)

            elif mimetype.lower() in supported_image_types:
                # Handle image formats (JPEG, JPG, PNG)
                try:
                    image_pdf = convert_image_to_pdf(file_bytes)
                    with open(temp_pdf_path, "wb") as f:
                        f.write(image_pdf.read())
                except Exception:
                    raise HTTPException(status_code=400, detail=f"Invalid image format in {filename}")

            else:
                # Unsupported file type
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type '{mimetype}' for file '{filename}'. "
                           f"Only PDF, JPG, JPEG, and PNG are allowed."
                )

            temp_pdfs.append(temp_pdf_path)

        # Merge all temporary PDFs
        for pdf_path in temp_pdfs:
            with open(pdf_path, "rb") as pdf_file:
                reader = PdfReader(pdf_file)
                for page in reader.pages:
                    pdf_writer.add_page(page)

        output_pdf = BytesIO()
        pdf_writer.write(output_pdf)
        output_pdf.seek(0)

        # Cleanup temp files
        for temp_file in temp_pdfs:
            try:
                os.remove(temp_file)
            except Exception:
                pass

        # Convert merged PDF to base64
        merged_base64 = base64.b64encode(output_pdf.getvalue()).decode("utf-8")

        # Prepare JSON response
        output_data = {
            "outputfilename": "merged_output.pdf",
            "outputmimetype": "application/pdf",
            "outputbase64content": merged_base64
        }

        # Save JSON response in output folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file_path = os.path.join("output", f"merged_output_{timestamp}.txt")
        with open(output_file_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)

        return output_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error merging files: {e}")

# pdf merge end
# send_mail_using_customer_server
class Attachment(BaseModel):
    Filename: str
    Content: str

class EmailMessage(BaseModel):
    From: EmailStr
    To: List[EmailStr]
    Cc: Optional[List[EmailStr]] = []
    Bcc: Optional[List[EmailStr]] = []
    Subject: str
    TextBody: str
    HtmlBody: Optional[str] = None
    HtmlBodyEncoding: Optional[Literal['plain', 'hex', 'quoted-printable', 'html-entities', 'base64']] = Field(
        default='plain',
        description="Encoding type for HtmlBody. Options are 'plain', 'hex', 'quoted-printable', 'html-entities', 'base64'."
    )
    ReplyTo: Optional[EmailStr] = None
    Attachments: Optional[List[Attachment]] = None

    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

class SmtpConfig(BaseModel):
    Server: str
    Port: int
    Username: EmailStr
    Password: SecretStr

    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

class EmailRequest(BaseModel):
    SmtpConfig: SmtpConfig
    Message: EmailMessage

    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

def send_email_logic(smtp_config: SmtpConfig, email_message: EmailMessage) -> tuple[bool, str]:
    msg = MIMEMultipart('mixed')
    msg['Subject'] = email_message.Subject
    msg['From'] = str(email_message.From)
    msg['To'] = ", ".join([str (e) for e in email_message.To])
    if email_message.Cc:
        msg['Cc'] = ", ".join([str (e) for e in email_message.Cc])
    if email_message.ReplyTo:
        msg['Reply-To'] = str(email_message.ReplyTo)

    msg_alternative = MIMEMultipart('alternative')
    msg_alternative.attach(MIMEText(email_message.TextBody, 'plain'))
    
    if email_message.HtmlBody:
        final_html = email_message.HtmlBody
        try:
            if email_message.HtmlBodyEncoding == 'hex':
                final_html = bytes.fromhex(email_message.HtmlBody).decode('utf-8')
            
            elif email_message.HtmlBodyEncoding == 'quoted-printable':
                final_html = quopri.decodestring(email_message.HtmlBody.encode('utf-8')).decode('utf-8')
            
            elif email_message.HtmlBodyEncoding == 'html-entities':
                final_html = html.unescape(email_message.HtmlBody)
            
            elif email_message.HtmlBodyEncoding == 'base64':
                final_html = base64.b64decode(email_message.HtmlBody).decode('utf-8')
        
        except (ValueError, binascii.Error, UnicodeDecodeError) as e:
            return False, f"Failed to decode HTML body using {email_message.HtmlBodyEncoding}: {str(e)}"

        msg_alternative.attach(MIMEText(final_html, 'html'))
    msg.attach(msg_alternative)

    if email_message.Attachments:
        for attachment_data in email_message.Attachments:
            content_type, _ = mimetypes.guess_type(attachment_data.Filename)
            if content_type is None: content_type = 'application/octet-stream'
            main_type, sub_type = content_type.split('/', 1)
            
            try:
                decoded_content = base64.b64decode(attachment_data.Content)
            except (ValueError, binascii.Error):
                return False, f"Invalid base64 content for attachment {attachment_data.Filename}"

            if main_type == 'image':
                part = MIMEImage(decoded_content, _subtype=sub_type)
            else:
                part = MIMEBase(main_type, sub_type)
                part.set_payload(decoded_content)
                encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{attachment_data.Filename}"')
            msg.attach(part)
    
    raw_recipients = email_message.To + (email_message.Cc or []) + (email_message.Bcc or [])
    all_recipients = [str(r) for r in raw_recipients]

    context = ssl.create_default_context()
    try:
        password = smtp_config.Password.get_secret_value()
        sender_email = str(email_message.From)
        username = str(smtp_config.Username)

        if smtp_config.Port == 465:
            with smtplib.SMTP_SSL(smtp_config.Server, smtp_config.Port, context=context) as server:
                server.login(username, password)
                server.sendmail(sender_email, all_recipients, msg.as_string())
        else:
            with smtplib.SMTP(smtp_config.Server, smtp_config.Port) as server:
                server.starttls(context=context)
                server.login(username, password)
                server.sendmail(sender_email, all_recipients, msg.as_string())
        return True, f"Email successfully sent to {', '.join(all_recipients)}."
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed. Check your email credentials"
    except smtplib.SMTPException as e:
        return False, f"SMTP Error: {str(e)}"
    except OSError as e:
        return False, f"Network/Connection Error: {str(e)}"
    except Exception as e:
        return False, f"An unexpected error occurred: {str(e)}"

@app.post("/send_mail_using_customer_server")
async def send_email_endpoint(request: EmailRequest):
    success, message = send_email_logic(request.SmtpConfig, request.Message)

    if success:
        return {"status": "success", "message": message}
    else:
        return {"status": "error", "message": message}

# end send_mail_using_customer_server

# begin of /redoc
@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Fresa APIUAT Gateway - ReDoc</title>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1">

        <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">

        <style>
        body {
            margin: 0;
            padding: 0;
        }
        </style>
    </head>
    <body>
        <redoc spec-url="/openapi.json"></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc@2.1.4/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# end of redoc


if __name__ == "__main__":
    import uvicorn
    print(" Invoice Extraction API v2.0.0")
    print(" Supported: PDF, JPEG, JPG, PNG only")
    print(" Output: template_name + extracted data only")
    print(" Server: http://0.0.0.0:8000")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
