import io
import os
import base64
import binascii
import tempfile
import fitz
from PIL import Image, UnidentifiedImageError
from typing import List, Optional

from core.config import logger, HAS_EASYOCR, HAS_TESSERACT

_EASY_OCR_READER = None
if HAS_EASYOCR:
    try:
        import easyocr
        _EASY_OCR_READER = easyocr.Reader(['en'], gpu=False)
    except Exception as e:
        logger.warning(f"Failed to init EasyOCR: {e}")

if HAS_TESSERACT:
    import pytesseract

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

def rasterize_first_page_to_jpeg(pdf_bytes: bytes) -> bytes:
    """Convert first page of a PDF to a high-quality JPEG (RGB)."""
    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    if pdf_document.page_count == 0:
        raise ValueError("PDF has no pages")
    page = pdf_document[0]
    mat = fitz.Matrix(3.0, 3.0)  # 216 DPI
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

def to_temp_image(file_bytes: bytes, content_type: str, original_name: str) -> str:
    """Write bytes to a temp file, converting PDF to JPG if necessary."""
    suffix = ".jpg"
    img_bytes = file_bytes

    if (content_type and "pdf" in content_type.lower()) or (original_name.lower().endswith(".pdf")):
        img_bytes = rasterize_first_page_to_jpeg(file_bytes)
    else:
        try:
            im = Image.open(io.BytesIO(file_bytes))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            b = io.BytesIO()
            im.save(b, format="JPEG", quality=95, optimize=True)
            img_bytes = b.getvalue()
            b.close()
        except (UnidentifiedImageError, OSError, ValueError):
            suffix = os.path.splitext(original_name)[1] or ".bin"

    fd, temp_path = tempfile.mkstemp(prefix="vc_", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(img_bytes)
    return temp_path

def _ocr_with_easyocr(img_path: str) -> str:
    if _EASY_OCR_READER is None:
        return ""
    try:
        result = _EASY_OCR_READER.readtext(img_path)
        return " ".join([line[1] for line in result]) if result else ""
    except Exception as easy_err:
        logger.warning(f"EasyOCR failed: {easy_err}")
        return ""

def _ocr_with_tesseract(img_path: str) -> str:
    if not HAS_TESSERACT:
        return ""
    try:
        from PIL import Image as _Image
        return pytesseract.image_to_string(_Image.open(img_path))
    except Exception as tess_err:
        logger.warning(f"Tesseract failed: {tess_err}")
        return ""

def ocr_extract_card(img_path: str) -> str:
    """Try EasyOCR first, then Tesseract. Return whichever is longer."""
    txt_easy = _ocr_with_easyocr(img_path)
    txt_tess = _ocr_with_tesseract(img_path)
    if len(txt_easy) >= len(txt_tess):
        return txt_easy.strip()
    return txt_tess.strip()

def clean_card_text(text: str) -> str:
    """Basic cleanup for OCR text."""
    if not text:
        return ""
    replacements = {
        "WWIN": "www", "VVWW": "www", "comcom": "com", "•": " ", "—": "-",
        "（": "(", "）": ")", "„": '"', "“": '"', "”": '"', "‘": "'", "’": "'",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return "\n".join([ln.strip() for ln in text.splitlines() if ln.strip()])