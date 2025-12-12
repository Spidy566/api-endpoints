import base64
import io
import mimetypes
import smtplib
import ssl
import html
import quopri
import binascii
from email import message_from_bytes, encoders
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import extract_msg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.config import logger, ALLOWED_EXTENSIONS, SHARED_SECRET_KEY
from modules.email.schemas import SmtpConfig, EmailMessage

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


class EmailAttachmentExtractor:
    """Class to handle multiple file format extraction from email files"""

    SUPPORTED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.zip', '.xlsx', '.xls', '.doc',
                            '.docx'}

    MIME_TYPE_MAP = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.tiff': 'image/tiff',
        '.tif': 'image/tiff',
        '.zip': 'application/zip',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    }

    FILE_SIGNATURES = {
        '.pdf': [b'%PDF'],
        '.jpg': [b'\xff\xd8\xff'],
        '.jpeg': [b'\xff\xd8\xff'],
        '.png': [b'\x89PNG\r\n\x1a\n'],
        '.tiff': [b'II*\x00', b'MM\x00*'],
        '.tif': [b'II*\x00', b'MM\x00*'],
        '.zip': [b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'],
        '.xlsx': [b'PK\x03\x04'],
        '.xls': [b'\xD0\xCF\x11\xE0'],
        '.doc': [b'\xD0\xCF\x11\xE0'],
        '.docx': [b'PK\x03\x04']
    }

    @staticmethod
    def is_supported_file(filename, content_type=None):
        if not filename: return False

        file_ext = '.' + filename.lower().split('.')[-1] if '.' in filename else ''

        if file_ext in EmailAttachmentExtractor.SUPPORTED_EXTENSIONS: return True
        if content_type:
            content_lower = content_type.lower()
            for ext, mime in EmailAttachmentExtractor.MIME_TYPE_MAP.items():
                if mime.lower() in content_lower: return True
        return False

    @staticmethod
    def get_file_extension(filename):
        if not filename or '.' not in filename:
            return '.unknown'
        return '.' + filename.lower().split('.')[-1]

    @staticmethod
    def validate_file_content(data, expected_extension):
        if not data or len(data) < 4: return False
        signatures = EmailAttachmentExtractor.FILE_SIGNATURES.get(expected_extension, [])
        for signature in signatures:
            if data.startswith(signature): return True
        return False

    @staticmethod
    def get_default_filename(index, extension, content_type=None):
        base_name = f"attachment_{index}"
        if extension and extension != '.unknown': return f"{base_name}{extension}"
        elif content_type:
            content_lower = content_type.lower()
            for ext, mime in EmailAttachmentExtractor.MIME_TYPE_MAP.items():
                if mime.lower() in content_lower: return f"{base_name}{ext}"
        return f"{base_name}.bin"

    @staticmethod
    def extract_from_eml(file_content):
        attachments = []

        try:
            msg = message_from_bytes(file_content)
            parts = list(msg.walk())
            logger.debug(f"EML parsing started - found {len(parts)} total parts")

            for i, part in enumerate(parts):
                logger.debug(f"--- Processing EML part {i} ---")
                logger.debug(f"Content-Type: {part.get_content_type()}")
                logger.debug(f"Content-Disposition: {part.get_content_disposition()}")
                logger.debug(f"Filename: {part.get_filename()}")

                content_disposition = part.get_content_disposition()
                content_type = part.get_content_type()
                filename = part.get_filename()

                is_attachment = False

                if content_disposition and 'attachment' in content_disposition.lower():
                    is_attachment = True
                    logger.debug(f"Part {i}: Identified as attachment by disposition")

                if filename and EmailAttachmentExtractor.is_supported_file(filename, content_type):
                    is_attachment = True
                    logger.debug(f"Part {i}: Identified as supported file by filename: {filename}")

                if content_type and any(
                        mime in content_type.lower() for mime in EmailAttachmentExtractor.MIME_TYPE_MAP.values()):
                    is_attachment = True
                    logger.debug(f"Part {i}: Identified as supported file by content-type: {content_type}")

                if is_attachment:
                    logger.debug(f"Part {i}: Processing as potential supported attachment")

                    file_ext = EmailAttachmentExtractor.get_file_extension(filename) if filename else '.unknown'

                    if not filename:
                        filename = EmailAttachmentExtractor.get_default_filename(i, file_ext, content_type)
                        logger.debug(f"Part {i}: Generated filename: {filename}")

                    if EmailAttachmentExtractor.is_supported_file(filename, content_type):
                        try:
                            logger.debug(f"Part {i}: Attempting to extract payload for {filename}")

                            payload = part.get_payload(decode=True)

                            if payload and len(payload) > 0:
                                logger.debug(f"Part {i}: Payload extracted - {len(payload)} bytes")

                                expected_ext = EmailAttachmentExtractor.get_file_extension(filename)
                                is_valid = EmailAttachmentExtractor.validate_file_content(payload, expected_ext)

                                if is_valid or expected_ext == '.unknown':
                                    logger.debug(f"Part {i}: Valid {expected_ext} file format detected")

                                    base64_content = base64.b64encode(payload).decode('utf-8')

                                    final_content_type = content_type or EmailAttachmentExtractor.MIME_TYPE_MAP.get(
                                        expected_ext, 'application/octet-stream')

                                    attachment_data = {
                                        'filename': filename,
                                        'content': base64_content,
                                        'content_type': final_content_type,
                                        'size_bytes': len(payload),
                                        'file_extension': expected_ext
                                    }

                                    attachments.append(attachment_data)
                                    logger.info(
                                        f"SUCCESS: Extracted {expected_ext} file {len(attachments)}: {filename} ({len(payload)} bytes, {len(base64_content)} base64 chars)")

                                else:
                                    logger.warning(
                                        f"Part {i}: File {filename} failed content validation for {expected_ext} - first 10 bytes: {payload[:10]}")
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
            logger.info(f"  File {i + 1}: {att['filename']} ({att['file_extension']}) - {att['size_bytes']} bytes")

        return attachments

    @staticmethod
    def extract_from_msg(file_content):
        attachments = []

        try:
            file_stream = io.BytesIO(file_content)
            msg = extract_msg.Message(file_stream)

            attachment_count = len(msg.attachments) if hasattr(msg, 'attachments') and msg.attachments else 0
            logger.debug(f"MSG parsing started - found {attachment_count} attachments")

            if hasattr(msg, 'attachments') and msg.attachments:
                for i, attachment in enumerate(msg.attachments):
                    logger.debug(f"--- Processing MSG attachment {i} ---")

                    try:
                        filename = (getattr(attachment, 'longFilename', None) or
                                    getattr(attachment, 'shortFilename', None) or
                                    getattr(attachment, 'displayName', None))

                        file_ext = EmailAttachmentExtractor.get_file_extension(filename) if filename else '.unknown'

                        if not filename:
                            filename = EmailAttachmentExtractor.get_default_filename(i, file_ext)

                        logger.debug(f"Attachment {i}: filename = {filename}")

                        logger.debug(f"Attachment {i}: type = {type(attachment)}")
                        logger.debug(
                            f"Attachment {i}: dir = {[attr for attr in dir(attachment) if not attr.startswith('_')]}")

                        if EmailAttachmentExtractor.is_supported_file(filename):
                            logger.debug(f"Attachment {i}: Processing as supported file: {filename}")

                            attachment_data = attachment.data

                            if attachment_data and len(attachment_data) > 0:
                                logger.debug(f"Attachment {i}: Data extracted - {len(attachment_data)} bytes")

                                expected_ext = EmailAttachmentExtractor.get_file_extension(filename)
                                is_valid = EmailAttachmentExtractor.validate_file_content(attachment_data, expected_ext)

                                if is_valid or expected_ext == '.unknown':
                                    logger.debug(f"Attachment {i}: Valid {expected_ext} file format detected")

                                    base64_content = base64.b64encode(attachment_data).decode('utf-8')

                                    content_type = EmailAttachmentExtractor.MIME_TYPE_MAP.get(expected_ext,
                                                                                              'application/octet-stream')

                                    attachment_info = {
                                        'filename': filename,
                                        'content': base64_content,
                                        'content_type': content_type,
                                        'size_bytes': len(attachment_data),
                                        'file_extension': expected_ext
                                    }

                                    attachments.append(attachment_info)
                                    logger.info(
                                        f"SUCCESS: Extracted {expected_ext} file {len(attachments)}: {filename} ({len(attachment_data)} bytes, {len(base64_content)} base64 chars)")

                                else:
                                    logger.warning(
                                        f"Attachment {i}: File {filename} failed content validation for {expected_ext} - first 10 bytes: {attachment_data[:10]}")
                            else:
                                logger.warning(f"Attachment {i}: Empty attachment data for {filename}")
                        else:
                            logger.debug(f"Attachment {i}: Skipping unsupported file: {filename}")

                    except Exception as e:
                        logger.error(f"Attachment {i}: Error processing: {str(e)}")
                        continue
            else:
                logger.info("No attachments found in MSG file")

            msg.close()

        except Exception as e:
            logger.error(f"Error parsing MSG file: {str(e)}")
            raise Exception(f"Failed to parse MSG file: {str(e)}")

        logger.info(f"MSG EXTRACTION COMPLETE: Found {len(attachments)} supported attachments")
        for i, att in enumerate(attachments):
            logger.info(f"  File {i + 1}: {att['filename']} ({att['file_extension']}) - {att['size_bytes']} bytes")

        return attachments


def send_email_logic(smtp_config: SmtpConfig, email_message: EmailMessage) -> tuple[bool, str]:
    msg = MIMEMultipart('mixed')
    msg['Subject'] = email_message.Subject
    msg['From'] = str(email_message.From)
    msg['To'] = ", ".join([str(e) for e in email_message.To])
    if email_message.Cc:
        msg['Cc'] = ", ".join([str(e) for e in email_message.Cc])
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

    try:
        encrypted_password_hex = smtp_config.Password.get_secret_value()
        key_bytes = SHARED_SECRET_KEY.encode('utf-8').ljust(32, b'0')

        data = bytes.fromhex(encrypted_password_hex)

        if len(data) < 28:
            return False, "Decryption Error: Payload too short (must be at least 28 bytes)."

        iv = data[:12]
        ciphertext_and_tag = data[12:]
        aesgcm = AESGCM(key_bytes)
        decrypted_bytes = aesgcm.decrypt(iv, ciphertext_and_tag, None)
        password = decrypted_bytes.decode('utf-8')

    except binascii.Error:
        return False, "Decryption Error: Password is not a valid Hex string."
    except Exception as e:
        return False, f"Decryption Error: {str(e)}"

    context = ssl.create_default_context()
    try:
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