import base64
import binascii
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional
from concurrent.futures import TimeoutError

from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from cryptography.hazmat.backends import default_backend

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import signers, fields, validation
from pyhanko.sign.fields import SigSeedSubFilter

from core.config import logger, CERT_DIR
from core.dependencies import thread_pool_executor

def get_cert_path(name: str) -> Optional[Path]:
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