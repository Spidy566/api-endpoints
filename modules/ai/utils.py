"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Added Office format detection & conversion| 07-07-2026 | vishal
Added JSON newline cleaning utilities    | 03-02-2026 | vishal
Base64 and PDF-to-Image converters       | 13-06-2025 | senthil
---------------------------------------------------------------------------
"""
import io
import os
import uuid
import base64
import binascii
import zipfile
import tempfile
import subprocess
import signal
import fitz
from PIL import Image
from typing import List, Optional

from core.config import logger

def extract_base64_content(file_content: str) -> Optional[str]:
    try:
        if not file_content:
            return None

        if file_content.startswith('data:') and ',' in file_content:
            content = file_content.split(',', 1)[1]
        else:
            content = file_content

        content = content.strip().replace('\n', '').replace('\r', '').replace(' ', '')

        if len(content) < 10:
            return None
        base64.b64decode(content, validate=True)
        return content

    except (binascii.Error, ValueError):
        return None

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
    raise ValueError("Unsupported file format. Only PDF, JPEG, JPG, and PNG are allowed.")


def detect_office_format(file_bytes: bytes) -> Optional[str]:
    """
    Detects Word / Excel file formats from magic bytes in-memory.
    Returns: 'docx', 'xlsx', 'doc', 'xls', 'pdf', or None.
    """
    if len(file_bytes) < 4:
        return None

    # Check for Zip format (modern OpenXML: docx, xlsx)
    if file_bytes.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                namelist = z.namelist()
                if any("word/" in name for name in namelist):
                    return "docx"
                if any("xl/" in name for name in namelist):
                    return "xlsx"
        except Exception as e:
            logger.debug(f"Zip inspection failed: {e}")
        return "zip"

    # Check for OLECF format (legacy Binary: doc, xls)
    if file_bytes.startswith(b"\xD0\xCF\x11\xE0"):
        # Scan inside binary to locate typical structures
        if b"Workbook" in file_bytes or b"Book" in file_bytes:
            return "xls"
        return "doc"

    if file_bytes.startswith(b"%PDF"):
        return "pdf"

    return None


def convert_office_to_pdf_unoconv(office_data: bytes, extension: str) -> bytes:
    """
    Converts Word / Excel raw bytes to PDF bytes using local unoconv / LibreOffice.
    """
    suffix = f".{extension.lower().lstrip('.')}"

    with tempfile.TemporaryDirectory() as temp_dir:
        file_id = uuid.uuid4()
        temp_office_path = os.path.join(temp_dir, f"{file_id}{suffix}")
        expected_pdf_path = os.path.join(temp_dir, f"{file_id}.pdf")

        # Write original source file with correct extension
        with open(temp_office_path, "wb") as f:
            f.write(office_data)

        command = [
            "/usr/bin/python3",
            "/usr/bin/unoconv",
            "--format", "pdf",
            "-o", expected_pdf_path,
            temp_office_path
        ]

        logger.info(f"Calling unoconv to convert {extension.upper()} to PDF...")
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid if hasattr(os, 'setsid') else None
        )

        try:
            stdout, stderr = proc.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            logger.error("unoconv conversion execution timed out.")
            if hasattr(os, 'killpg') and hasattr(os, 'getpgid'):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
            proc.wait()
            raise RuntimeError("unoconv conversion timed out after 3 minutes.")

        if proc.returncode != 0:
            error_message = f"unoconv conversion failed (Code {proc.returncode}).\nStderr: {stderr.decode(errors='ignore')}"
            logger.error(error_message)
            raise RuntimeError(error_message)

        if not os.path.exists(expected_pdf_path):
            raise FileNotFoundError(f"PDF compilation target not found: {expected_pdf_path}")

        with open(expected_pdf_path, "rb") as f:
            return f.read()


def convert_pdf_to_jpeg(pdf_base64: str) -> List[str]:
    """Convert ALL PDF pages to JPEG images for Vision API"""
    try:
        pdf_bytes = base64.b64decode(pdf_base64)
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")

        if pdf_document.page_count == 0:
            raise Exception("PDF has no pages")

        images = []
        logger.info(f"Processing PDF with {pdf_document.page_count} pages")

        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]
            mat = fitz.Matrix(3.0, 3.0)  # 216 DPI
            pix = page.get_pixmap(matrix=mat, alpha=False)

            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data))

            # Convert to RGB
            if image.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "P":
                    image = image.convert("RGBA")
                if image.mode in ("RGBA", "LA"):
                    background.paste(image, mask=image.split()[-1])
                image = background
            elif image.mode not in ("RGB", "L"):
                image = image.convert("RGB")

            # Resize if too large
            width, height = image.size
            if max(width, height) > 2000:
                ratio = 2000 / max(width, height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            output_buffer = io.BytesIO()
            image.save(output_buffer, format="JPEG", quality=95, optimize=True)
            image_base64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')

            images.append(image_base64)
            output_buffer.close()

        pdf_document.close()
        return images
    except Exception as pdf_err:
        raise Exception(f"PDF conversion failed: {str(pdf_err)}")

def clean_card_text(text: str) -> str:
    """Basic cleanup for OCR-style text."""
    if not text:
        return ""
    replacements = {"•": " ", "—": "-"}
    for k, v in replacements.items():
        text = text.replace(k, v)
    return "\n".join([ln.strip() for ln in text.splitlines() if ln.strip()])

def extract_image(pdf_base64: str) -> List[str]:
    """PDF → JPEG conversion."""
    try:
        pdf_bytes = base64.b64decode(pdf_base64)
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")

        if pdf_document.page_count == 0:
            raise Exception("PDF has no pages")

        images: List[str] = []
        logger.info(f"Extracting: {pdf_document.page_count} page(s)")

        mat = fitz.Matrix(2.0, 2.0)

        for page_index in range(pdf_document.page_count):
            page = pdf_document[page_index]

            pix = page.get_pixmap(matrix=mat, alpha=False)

            image = Image.frombytes(
                "RGB",
                (pix.width, pix.height),
                pix.samples
            )

            max_dim = max(image.size)
            if max_dim > 1600:
                scale = 1600 / max_dim
                new_size = (
                    int(image.size[0] * scale),
                    int(image.size[1] * scale)
                )
                image = image.resize(new_size, Image.Resampling.BILINEAR)

            output_buffer = io.BytesIO()
            image.save(
                output_buffer,
                format="JPEG",
                quality=80,
                optimize=True,
                progressive=True
            )

            images.append(
                base64.b64encode(output_buffer.getvalue()).decode("utf-8")
            )

            output_buffer.close()

        pdf_document.close()
        return images

    except Exception as bl_err:
        raise Exception(f"PDF conversion failed: {str(bl_err)}")

def decode_base64_string(b64_string: str) -> str:
    """Decodes a Base64 string back to UTF-8 text."""
    try:
        if not b64_string:
            return ""

        decoded_bytes = base64.b64decode(b64_string)
        return decoded_bytes.decode("utf-8")
    except Exception as b64_err:
        logger.error(f"Prompt decoding failed: {b64_err}")
        return ""

def clean_json_newlines(data):
    """
    Recursively replaces literal '\\n' strings with actual newline characters '\n'.
    """
    if isinstance(data, dict):
        return {k: clean_json_newlines(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_json_newlines(i) for i in data]
    elif isinstance(data, str):
        return data.replace("\\n", "\n")
    else:
        return data