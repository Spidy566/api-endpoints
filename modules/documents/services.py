"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Expanded merging support for 12 formats  | 07-07-2026 | vishal
DOCX template rendering with images      | 07-01-2026 | vishal
Unoconv DOCX to PDF conversion logic     | 03-12-2025 | vishal
PyPDF based file merging logic           | 03-12-2025 | dhremagi
---------------------------------------------------------------------------
"""
import io
import os
import uuid
import base64
import signal
import zipfile
import subprocess
import tempfile
import binascii
import html
from email import message_from_bytes
from email.header import decode_header
from typing import List, Dict
from PIL import Image, UnidentifiedImageError
from pypdf import PdfWriter, PdfReader
from docxtpl import DocxTemplate
import extract_msg

from core.config import logger


def generate_docx(template_bytes: bytes, context: dict, images: List[Dict[str, str]] = None) -> bytes:
    temp_image_paths: List[str] = []
    try:
        tpl = DocxTemplate(io.BytesIO(template_bytes))
        if images:
            for image_item in images:
                source = image_item.get("source")
                placeholder = image_item.get("placeholder")

                if not source or not placeholder:
                    continue
                try:
                    try:
                        image_bytes = base64.b64decode(source)
                        image_stream = io.BytesIO(image_bytes)
                    except (binascii.Error, ValueError) as b64_err:
                        logger.warning(f"Invalid raw base64 for {placeholder}: {b64_err}")
                        continue

                    if image_stream:
                        fd, temp_path = tempfile.mkstemp(suffix=".png")
                        with os.fdopen(fd, "wb") as f:
                            f.write(image_stream.getvalue())

                        temp_image_paths.append(temp_path)

                        try:
                            tpl.replace_pic(placeholder, temp_path)
                            logger.info(f"Replaced image placeholder: {placeholder}")
                        except Exception as e:
                            logger.warning(f"Could not replace pic '{placeholder}': {e}")

                except Exception as e:
                    logger.error(f"Failed to process image for '{placeholder}': {e}")

        tpl.render(context, autoescape=True)
        final_docx_buffer = io.BytesIO()
        tpl.save(final_docx_buffer)
        return final_docx_buffer.getvalue()

    except zipfile.BadZipFile:
        raise ValueError("Invalid Template: The provided content is not a valid .docx file. Please check your Base64 string.")

    except Exception as e:
        raise ValueError(f"Template Rendering Failed: {str(e)}")

    finally:
        for path in temp_image_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass


def convert_office_to_pdf_unoconv(office_data: bytes, extension: str) -> bytes:
    """
    Utility to translate document formats to PDF using unoconv.
    Uses lowercase '-d' to specify spreadsheet doctype for CSV files.
    """
    suffix = f".{extension.lower().lstrip('.')}"
    with tempfile.TemporaryDirectory() as temp_dir:
        file_id = uuid.uuid4()
        temp_office_path = os.path.join(temp_dir, f"{file_id}{suffix}")
        expected_pdf_path = os.path.join(temp_dir, f"{file_id}.pdf")

        with open(temp_office_path, "wb") as f:
            f.write(office_data)

        command = [
            "/usr/bin/python3",
            "/usr/bin/unoconv",
            "--format", "pdf",
        ]

        if extension.lower() == "csv":
            command += ["-d", "spreadsheet"]

        command += [
            "-o", expected_pdf_path,
            temp_office_path
        ]

        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid if hasattr(os, 'setsid') else None
        )

        try:
            stdout, stderr = proc.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            if hasattr(os, 'killpg') and hasattr(os, 'getpgid'):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
            proc.wait()
            raise RuntimeError(f"unoconv conversion for {extension.upper()} timed out.")

        if proc.returncode != 0:
            error_message = f"unoconv failed with exit code {proc.returncode}.\nStderr: {stderr.decode(errors='ignore')}"
            raise RuntimeError(error_message)

        if not os.path.exists(expected_pdf_path):
            raise FileNotFoundError(f"PDF compiled output was not created by unoconv for {extension.upper()}.")

        with open(expected_pdf_path, "rb") as f:
            return f.read()


def convert_docx_to_pdf_unoconv(docx_data: bytes) -> bytes:
    """
    Backwards compatible wrapper for the generate-report routes.
    """
    return convert_office_to_pdf_unoconv(docx_data, "docx")


def convert_image_to_pdf(image_bytes: bytes) -> io.BytesIO:
    """Convert image bytes (including webp, png, jpeg, jpg) to a single-page PDF."""
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        pdf_bytes = io.BytesIO()
        image.save(pdf_bytes, format="PDF")
        pdf_bytes.seek(0)
        return pdf_bytes
    except (UnidentifiedImageError, OSError) as img_err:
        raise ValueError(f"Image conversion failed: {str(img_err)}")


def build_email_header_block(from_val: str, to_val: str, cc_val: str, bcc_val: str, date_val: str, subject: str) -> str:
    """
    Renders a unified header block for EML and MSG messages.
    """
    cc_row = ""
    if cc_val and cc_val.strip() != "N/A" and cc_val.strip() != "":
        cc_row = f'<div style="margin-bottom: 8px;"><span style="font-weight: bold; color: #555; display: inline-block; width: 80px;">Cc:</span> {cc_val}</div>'

    bcc_row = ""
    if bcc_val and bcc_val.strip() != "N/A" and bcc_val.strip() != "":
        bcc_row = f'<div style="margin-bottom: 8px;"><span style="font-weight: bold; color: #555; display: inline-block; width: 80px;">Bcc:</span> {bcc_val}</div>'

    return f"""
    <div style="font-family: '\''Segoe UI'\'', Arial, sans-serif; border-bottom: 2px solid #ddd; padding-bottom: 15px; margin-bottom: 25px; font-size: 14px; background: #fafafa; padding: 15px; border-radius: 4px;">
        <div style="margin-bottom: 8px;"><span style="font-weight: bold; color: #555; display: inline-block; width: 80px;">From:</span> {from_val}</div>
        <div style="margin-bottom: 8px;"><span style="font-weight: bold; color: #555; display: inline-block; width: 80px;">To:</span> {to_val}</div>
        {cc_row}
        {bcc_row}
        <div style="margin-bottom: 8px;"><span style="font-weight: bold; color: #555; display: inline-block; width: 80px;">Date:</span> {date_val}</div>
        <div style="margin-bottom: 8px;"><span style="font-weight: bold; color: #555; display: inline-block; width: 80px;">Subject:</span> <strong style="font-size: 16px; color: #111;">{subject}</strong></div>
    </div>
    """


def parse_eml_to_html(eml_bytes: bytes) -> str:
    """
    Parses EML headers and rich HTML/plaintext body content.
    If a rich HTML body is available, it splices the email headers directly
    inside the body element to preserve original styling.
    """
    msg = message_from_bytes(eml_bytes)

    def get_header(name: str) -> str:
        val = msg.get(name)
        if not val:
            return "N/A"
        decoded = decode_header(val)
        header_str = ""
        for part, encoding in decoded:
            if isinstance(part, bytes):
                header_str += part.decode(encoding or "utf-8", errors="ignore")
            else:
                header_str += str(part)
        return html.escape(header_str)

    subject = get_header("Subject")
    from_val = get_header("From")
    to_val = get_header("To")
    cc_val = get_header("Cc")
    bcc_val = get_header("Bcc")
    date_val = get_header("Date")

    header_block = build_email_header_block(from_val, to_val, cc_val, bcc_val, date_val, subject)

    # Extract body content
    html_body = None
    text_body = None

    for part in msg.walk():
        ctype = part.get_content_type()
        cdisp = str(part.get("Content-Disposition", ""))

        if "attachment" not in cdisp:
            if ctype == "text/html":
                html_body = part.get_payload(decode=True)
            elif ctype == "text/plain":
                text_body = part.get_payload(decode=True)

    # Render Strategy
    if html_body:
        try:
            body_content = html_body.decode("utf-8", errors="ignore")
        except Exception:
            body_content = html_body.decode("latin1", errors="ignore")

        # In-Place Splicing: Inject our header block right inside the EML's native HTML body
        body_idx = body_content.lower().find("<body")
        if body_idx != -1:
            end_body_tag_idx = body_content.find(">", body_idx)
            if end_body_tag_idx != -1:
                return body_content[:end_body_tag_idx + 1] + header_block + body_content[end_body_tag_idx + 1:]

        return header_block + body_content

    elif text_body:
        try:
            txt = text_body.decode("utf-8", errors="ignore")
        except Exception:
            txt = text_body.decode("latin1", errors="ignore")

        escaped_txt = html.escape(txt)
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; color: #333; line-height: 1.5; }}
                .email-body {{ font-size: 15px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            {header_block}
            <div class="email-body">
                <pre style="font-family: Arial, sans-serif; white-space: pre-wrap; word-wrap: break-word; margin: 0;">{escaped_txt}</pre>
            </div>
        </body>
        </html>
        """
    else:
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: sans-serif; margin: 40px;">
            {header_block}
            <p style="color: gray; font-style: italic; margin-top: 20px;">[No text content found in email body]</p>
        </body>
        </html>
        """


def get_safe_msg_field(msg: extract_msg.Message, field_name: str) -> str:
    """
    Safely retrieves metadata property from extract_msg.Message.
    Bypasses dynamic MAPI-unpacking ValueError and TypeError crashes cleanly.
    """
    try:
        val = getattr(msg, field_name, None)
        if val is None:
            return ""
        # If it is a list of objects or complex struct, cast it cleanly
        return str(val).strip()
    except Exception as e:
        logger.debug(f"Self-healing fallback active: bypassed corrupt MSG field '{field_name}' ({e})")
        return ""


def parse_msg_to_html(msg_bytes: bytes) -> str:
    """
    Parses Outlook MSG binary format, extracting metadata, headers and HTML/plain body.
    Protects all header lookups from python OLE binary unpacking crashes.
    """
    try:
        file_stream = io.BytesIO(msg_bytes)
        msg = extract_msg.Message(file_stream)

        # Defensive Header Extraction
        subject = html.escape(get_safe_msg_field(msg, "subject") or "N/A")
        from_val = html.escape(get_safe_msg_field(msg, "sender") or "N/A")
        to_val = html.escape(get_safe_msg_field(msg, "to") or "N/A")
        cc_val = html.escape(get_safe_msg_field(msg, "cc"))
        bcc_val = html.escape(get_safe_msg_field(msg, "bcc"))
        date_val = html.escape(get_safe_msg_field(msg, "date") or "N/A")

        header_block = build_email_header_block(from_val, to_val, cc_val, bcc_val, date_val, subject)

        html_body = None
        try:
            html_body = getattr(msg, "htmlBody", None)
        except Exception as body_err:
            logger.debug(f"Bypassed htmlBody retrieval error: {body_err}")

        text_body = None
        try:
            text_body = getattr(msg, "body", None)
        except Exception as body_err:
            logger.debug(f"Bypassed body text retrieval error: {body_err}")

        if html_body:
            try:
                body_content = html_body.decode("utf-8", errors="ignore")
            except Exception:
                body_content = html_body.decode("latin1", errors="ignore")

            # Splicing
            body_idx = body_content.lower().find("<body")
            if body_idx != -1:
                end_body_tag_idx = body_content.find(">", body_idx)
                if end_body_tag_idx != -1:
                    result = body_content[:end_body_tag_idx + 1] + header_block + body_content[end_body_tag_idx + 1:]
                    msg.close()
                    return result

            result = header_block + body_content
            msg.close()
            return result

        elif text_body:
            escaped_txt = html.escape(text_body)
            result = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; color: #333; line-height: 1.5; }}
                    .email-body {{ font-size: 15px; margin-top: 20px; }}
                </style>
            </head>
            <body>
                {header_block}
                <div class="email-body">
                    <pre style="font-family: Arial, sans-serif; white-space: pre-wrap; word-wrap: break-word; margin: 0;">{escaped_txt}</pre>
                </div>
            </body>
            </html>
            """
            msg.close()
            return result
        else:
            result = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8"></head>
            <body style="font-family: sans-serif; margin: 40px;">
                {header_block}
                <p style="color: gray; font-style: italic; margin-top: 20px;">[No text content found in email body]</p>
            </body>
            </html>
            """
            msg.close()
            return result

    except Exception as e:
        logger.error(f"Failed to parse OLE Outlook MSG format: {e}")
        raise ValueError(f"Outlook MSG structure corrupted: {str(e)}")


def convert_single_file_to_pdf(file_bytes: bytes, filename: str, mimetype: str) -> bytes:
    """
    Core routing helper to convert a single binary file payload into standard PDF bytes.
    Handles standard formats: pdf, webp, docx, xlsx, jpeg, png, jpg, txt, csv, doc, xls.
    For EML and MSG files, it compiles the main body PDF first, then recursively parses and appends attachments.
    """
    mime_to_ext = {
        "application/pdf": "pdf",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/msword": "doc",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/vnd.ms-excel": "xls",
        "text/plain": "txt",
        "text/csv": "csv",
        "message/rfc822": "eml",
        "application/vnd.ms-outlook": "msg"
    }

    ext = ""
    if "." in filename:
        ext = filename.lower().split(".")[-1].strip()

    if not ext and mimetype in mime_to_ext:
        ext = mime_to_ext[mimetype]

    if not ext:
        if file_bytes.startswith(b"%PDF"):
            ext = "pdf"
        elif file_bytes.startswith(b"PK\x03\x04"):
            ext = "docx"
        else:
            ext = "txt"

    if ext == "pdf" or file_bytes[:4] == b"%PDF":
        return file_bytes

    elif ext in ["jpg", "jpeg", "png", "webp"]:
        image_pdf = convert_image_to_pdf(file_bytes)
        return image_pdf.read()

    elif ext in ["docx", "doc", "xlsx", "xls", "txt", "csv"]:
        return convert_office_to_pdf_unoconv(file_bytes, ext)

    elif ext == "eml":
        # Process EML body (rich HTML or plaintext format)
        email_html = parse_eml_to_html(file_bytes)
        body_pdf_bytes = convert_office_to_pdf_unoconv(email_html.encode("utf-8"), "html")

        # Recursively parse and append EML attachments
        msg = message_from_bytes(file_bytes)
        attachment_pdfs: List[bytes] = [body_pdf_bytes]

        for part in msg.walk():
            part_filename = part.get_filename()
            cdisp = str(part.get("Content-Disposition", ""))

            if "attachment" in cdisp.lower() or part_filename:
                att_payload = part.get_payload(decode=True)
                if not att_payload:
                    continue

                part_mime = part.get_content_type()
                clean_filename = str(part_filename) if part_filename else "attachment"

                try:
                    logger.info(f"Found embedded EML attachment: {clean_filename} ({part_mime}). Processing...")
                    att_pdf = convert_single_file_to_pdf(att_payload, clean_filename, part_mime)
                    attachment_pdfs.append(att_pdf)
                except Exception as att_err:
                    logger.warning(f"Skipped corrupt or unsupported EML attachment '{clean_filename}': {att_err}")

        # Merge body page(s) and its attachment pages together
        if len(attachment_pdfs) > 1:
            eml_writer = PdfWriter()
            for pdf_bytes in attachment_pdfs:
                reader = PdfReader(io.BytesIO(pdf_bytes))
                for page in reader.pages:
                    eml_writer.add_page(page)

            output_stream = io.BytesIO()
            eml_writer.write(output_stream)
            return output_stream.getvalue()

        return body_pdf_bytes

    elif ext == "msg":
        # Process MSG body
        email_html = parse_msg_to_html(file_bytes)
        body_pdf_bytes = convert_office_to_pdf_unoconv(email_html.encode("utf-8"), "html")

        # Extract OLE attachments recursively
        attachment_pdfs: List[bytes] = [body_pdf_bytes]

        try:
            file_stream = io.BytesIO(file_bytes)
            msg_obj = extract_msg.Message(file_stream)

            if hasattr(msg_obj, "attachments") and msg_obj.attachments:
                for att in msg_obj.attachments:
                    long_name = getattr(att, "longFilename", None)
                    short_name = getattr(att, "shortFilename", None)
                    display_name = getattr(att, "displayName", None)
                    att_filename = long_name or short_name or display_name

                    att_data = getattr(att, "data", None)
                    if not isinstance(att_data, bytes) or len(att_data) == 0:
                        continue

                    clean_filename = str(att_filename) if att_filename else "attachment"

                    # Guess mime type safely
                    ext_suffix = "." + clean_filename.lower().split(".")[-1] if "." in clean_filename else ""
                    guessed_mime = "application/octet-stream"
                    for mime, mapping_ext in mime_to_ext.items():
                        if ext_suffix == f".{mapping_ext}":
                            guessed_mime = mime
                            break

                    try:
                        logger.info(f"Found embedded Outlook MSG attachment: {clean_filename}. Processing...")
                        att_pdf = convert_single_file_to_pdf(att_data, clean_filename, guessed_mime)
                        attachment_pdfs.append(att_pdf)
                    except Exception as att_err:
                        logger.warning(f"Skipped corrupt or unsupported MSG attachment '{clean_filename}': {att_err}")

            msg_obj.close()
        except Exception as msg_err:
            logger.warning(f"Bypassed OLE MSG attachment extraction process due to internal reader issue: {msg_err}")

        # Consolidate MSG pages
        if len(attachment_pdfs) > 1:
            msg_writer = PdfWriter()
            for pdf_bytes in attachment_pdfs:
                reader = PdfReader(io.BytesIO(pdf_bytes))
                for page in reader.pages:
                    msg_writer.add_page(page)

            output_stream = io.BytesIO()
            msg_writer.write(output_stream)
            return output_stream.getvalue()

        return body_pdf_bytes

    else:
        raise ValueError(f"Unsupported format standard '{ext}' for file '{filename}'.")


def merge_files_logic(files: List[Dict[str, str]]) -> Dict[str, str]:
    """
    Accepts a list of Base64 files. Supports:
    .pdf, .webp, .docx, .xlsx, .jpeg, .png, .jpg, .txt, .csv, .doc, .xls, .eml, .msg
    Converts and merges them into a single PDF document.
    """
    temp_pdfs: List[str] = []

    try:
        pdf_writer = PdfWriter()

        for file_info in files:
            filename = file_info.get("filename", "file")
            mimetype = file_info.get("mimetype", "").lower().strip()
            base64content = file_info.get("base64content", "")

            if not base64content:
                raise ValueError(f"Missing base64content for {filename}")

            try:
                file_bytes = base64.b64decode(base64content.strip())
            except (binascii.Error, ValueError):
                raise ValueError(f"Invalid base64 data inside {filename}")

            # Create an intermediate workspace path for this consolidated file
            fd, temp_pdf_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            temp_pdfs.append(temp_pdf_path)

            try:
                # Route file conversion dynamically
                pdf_bytes = convert_single_file_to_pdf(file_bytes, filename, mimetype)
                with open(temp_pdf_path, "wb") as f:
                    f.write(pdf_bytes)
            except Exception as e:
                raise ValueError(f"Office conversion failed for '{filename}': {str(e)}")

        # Consolidate pages
        for pdf_path in temp_pdfs:
            with open(pdf_path, "rb") as pdf_file:
                reader = PdfReader(pdf_file)
                for page in reader.pages:
                    pdf_writer.add_page(page)

        output_pdf = io.BytesIO()
        pdf_writer.write(output_pdf)
        output_pdf.seek(0)

        merged_base64 = base64.b64encode(output_pdf.getvalue()).decode("utf-8")

        return {
            "outputfilename": "merged_output.pdf",
            "outputmimetype": "application/pdf",
            "outputbase64content": merged_base64
        }

    finally:
        for temp_file in temp_pdfs:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except OSError:
                pass