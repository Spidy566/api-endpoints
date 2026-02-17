"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
PyHanko PFX digital signing logic        | 13-06-2025 | senthil
Added PDF signature validation service   | 13-06-2025 | senthil
---------------------------------------------------------------------------
"""
import logging
import asyncio
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any

from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from cryptography.hazmat.backends import default_backend

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import signers, fields, validation
from pyhanko.sign.fields import SigSeedSubFilter
from pyhanko_certvalidator import errors, ValidationContext

from core.config import logger, CERT_DIR
from core.dependencies import thread_pool_executor



def get_cert_path(name: str) -> Optional[Path]:
    """Finds a .pfx file in the certs directory matching the name."""
    cert_path = CERT_DIR / f"{name}.pfx"
    if cert_path.exists():
        return cert_path

    cert_path = CERT_DIR / f"{name.lower()}.pfx"
    if cert_path.exists():
        return cert_path

    name_safe = name.lower().replace(" ", "_")
    cert_path = CERT_DIR / f"{name_safe}.pfx"
    if cert_path.exists():
        return cert_path

    return None


def load_pkcs12_certificate(cert_path: Path, password: str):
    """Loads and decrypts the PKCS#12 certificate."""
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
            'organization': organization,
            'cert_path': cert_path,
            'password': password
        }
    except Exception as e:
        logger.error(f"Failed to load certificate: {str(e)}")
        raise

def sign_pdf_sync(pdf_data: bytes, cert_info: dict,
                  signer_name: str, reason: str, location: str,
                  visible: bool = True, page: int = -1,
                  x: float = 450, y: float = 50,
                  box_width: float = 200, box_height: float = 70) -> bytes:
    """Synchronous function to sign PDF (runs in thread pool)."""
    try:
        reader = PdfFileReader(BytesIO(pdf_data))
        total_pages = int(reader.root['/Pages']['/Count'])

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

        signature_meta = signers.PdfSignatureMetadata(
            field_name='Signature1',
            name=signer_name,
            location=location,
            reason=reason,
            md_algorithm='sha256',
            subfilter=SigSeedSubFilter.ADOBE_PKCS7_DETACHED
        )

        w = IncrementalPdfFileWriter(BytesIO(pdf_data))

        if visible:
            sig_field_spec = fields.SigFieldSpec(
                sig_field_name='Signature1',
                on_page=page,
                box=(int(x), int(y), int(x + box_width), int(y + box_height))
            )
            fields.append_signature_field(w, sig_field_spec)

        out_buf = BytesIO()

        signers.sign_pdf(
            w,
            signature_meta,
            signer=signer,
            existing_fields_only=visible,
            output=out_buf
        )
        signed_pdf = out_buf.getvalue()
        return signed_pdf

    except Exception as e:
        logger.error(f"Error in synchronous signing: {str(e)}")
        raise

async def sign_pdf_async(pdf_data: bytes, cert_info: dict, request_data: Any):
    """Async wrapper around the sync signing function."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        thread_pool_executor,
        sign_pdf_sync,
        pdf_data, cert_info, request_data.name, request_data.reason,
        request_data.location, request_data.visible_signature,
        request_data.page_number, request_data.x_coordinate,
        request_data.y_coordinate, request_data.box_width,
        request_data.box_height
    )


def validate_pdf_content(pdf_bytes: bytes) -> Dict:
    """Validate digital signatures in a PDF."""
    logging.getLogger("pyhanko_certvalidator").setLevel(logging.ERROR)
    logging.getLogger("pyhanko.sign.validation").setLevel(logging.ERROR)

    try:
        pdf_reader = PdfFileReader(BytesIO(pdf_bytes))

        if not pdf_reader.embedded_signatures:
            return {
                "has_signatures": False,
                "signature_count": 0,
                "signatures": [],
                "message": "No digital signatures found in PDF"
            }

        signatures = []

        for sig_field in pdf_reader.embedded_signatures:
            val_result = None

            signer_name = "Unknown"
            is_valid = False
            is_intact = False
            is_trusted = False
            status_label = "Invalid"
            visual_indicator = "❓ Error"
            timestamp_str = None
            cert = None
            error_msg = None

            try:
                vc = ValidationContext(revocation_mode='soft-fail')

                val_result = validation.validate_pdf_signature(
                    sig_field,
                    signer_validation_context=vc
                )

                is_valid = getattr(val_result, 'valid', False)
                is_intact = getattr(val_result, 'intact', False)
                is_trusted = getattr(val_result, 'trusted', False)
                cert = getattr(val_result, 'signing_cert', None) or getattr(val_result, 'signer_cert', None)

            except (errors.PathBuildingError, errors.InvalidCertificateError):
                try:
                    cert = sig_field.signer_cert
                    if cert:
                        vc_self_signed = ValidationContext(trust_roots=[cert], revocation_mode='soft-fail')

                        val_result = validation.validate_pdf_signature(
                            sig_field,
                            signer_validation_context=vc_self_signed
                        )

                        is_intact = getattr(val_result, 'intact', False)
                        is_valid = getattr(val_result, 'valid', False)

                        if is_intact:
                            is_trusted = False
                            status_label = "Valid (Untrusted)"
                            visual_indicator = "⚠️ Untrusted"
                        else:
                            status_label = "Invalid (Tampered)"
                            visual_indicator = "❌ Invalid"
                except Exception as retry_err:
                    error_msg = str(retry_err)
                    status_label = "Untrusted"
                    visual_indicator = "❌ Untrusted"

            if cert:
                try:
                    subject_data = cert.subject.native
                    if isinstance(subject_data, dict):
                        signer_name = subject_data.get('common_name') or subject_data.get(
                            'organization_name') or "Unknown"
                    else:
                        signer_name = str(subject_data)
                except (AttributeError, KeyError, TypeError):
                    signer_name = "Unknown"

            if 'val_result' in locals():
                ts_obj = getattr(val_result, 'timestamp', None)
                if not ts_obj:
                    ts_obj = getattr(val_result, 'signer_reported_dt', None)
                timestamp_str = str(ts_obj) if ts_obj else None

                if is_valid and is_intact and is_trusted:
                    status_label = "Valid"
                    visual_indicator = "✅ Verified"
                elif is_valid and is_intact and not is_trusted and status_label == "Invalid":
                    status_label = "Valid (Untrusted)"
                    visual_indicator = "⚠️ Untrusted"

            sig_info = {
                "field_name": sig_field.field_name,
                "signer": signer_name,
                "valid": is_valid,
                "trusted": is_trusted,
                "timestamp": timestamp_str,
                "intact": is_intact,
                "status": status_label,
                "visual_indicator": visual_indicator,
                "error": error_msg
            }
            signatures.append(sig_info)

        return {
            "has_signatures": True,
            "signature_count": len(signatures),
            "signatures": signatures,
            "message": "Signatures found and validated",
            "error": None
        }
    except Exception as e:
        logger.error(f"Global validation error: {e}")
        return {
            "has_signatures": False,
            "signature_count": 0,
            "signatures": [],
            "error": str(e),
            "message": "Error reading PDF"
        }