"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Added JSON newline cleaning utilities    | 03-02-2026 | vishal
Base64 and PDF-to-Image converters       | 13-06-2025 | senthil
---------------------------------------------------------------------------
"""
import io
import base64
import binascii
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