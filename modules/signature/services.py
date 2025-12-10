import asyncio
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any, List

from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from cryptography.hazmat.backends import default_backend

from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import signers, fields, validation
from pyhanko.sign.fields import SigSeedSubFilter

from core.config import logger, CERT_DIR
from core.dependencies import thread_pool_executor


# --- Certificate Management ---

def get_cert_path(name: str) -> Optional[Path]:
    """Finds a .pfx file in the certs directory matching the name."""
    # 1. Exact match
    cert_path = CERT_DIR / f"{name}.pfx"
    if cert_path.exists():
        return cert_path

    # 2. Lowercase match
    cert_path = CERT_DIR / f"{name.lower()}.pfx"
    if cert_path.exists():
        return cert_path

    # 3. Snake_case match
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


# --- Signing Logic ---

def sign_pdf_sync(pdf_data: bytes, cert_info: dict,
                  signer_name: str, reason: str, location: str,
                  visible: bool = True, page: int = -1,
                  x: float = 450, y: float = 50,
                  box_width: float = 200, box_height: float = 70) -> bytes:
    """Synchronous function to sign PDF (runs in thread pool)."""
    signed_pdf = None
    try:
        # Determine page count
        reader = PdfFileReader(BytesIO(pdf_data))
        try:
            page_tree = reader.page_tree
            total_pages = sum(1 for _ in page_tree)
        except:
            total_pages = reader.root['/Pages']['/Count']

        # Calculate target page
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

        # Prepare Writer
        w = IncrementalPdfFileWriter(BytesIO(pdf_data))

        if visible:
            sig_field_spec = fields.SigFieldSpec(
                sig_field_name='Signature1',
                on_page=page,
                box=(x, y, x + box_width, y + box_height)
            )
            fields.append_signature_field(w, sig_field_spec)

        # Buffer preparation
        prepared_buf = BytesIO()
        w.write(prepared_buf)
        prepared_buf.seek(0)

        # Execute Signing
        try:
            # Try PyHanko high-level API
            from pyhanko.sign.signers.pdf_signer import sign_pdf
            result = sign_pdf(
                pdf_in=prepared_buf if visible else BytesIO(pdf_data),
                signers=[signer],
                signature_meta=signature_meta,
                existing_fields_only=visible,  # If visible, we just created the field
            )
            if hasattr(result, 'read'):
                signed_pdf = result.read()
            else:
                signed_pdf = result
        except (ImportError, AttributeError):
            # Fallback for older versions or internal API changes
            w2 = IncrementalPdfFileWriter(prepared_buf if visible else BytesIO(pdf_data))
            out = signers.sign_pdf(
                w2,
                signature_meta,
                signer=signer,
                existing_fields_only=visible
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


# --- Validation Logic ---

def validate_pdf_content(pdf_bytes: bytes) -> Dict:
    """Validate digital signatures in a PDF."""
    try:
        pdf_reader = PdfFileReader(BytesIO(pdf_bytes))

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

                status_valid = val_result.valid and val_result.intact

                sig_info = {
                    "field_name": sig_field.field_name,
                    "signer": val_result.signer_cert.subject.rfc4514_string() if val_result.signer_cert else "Unknown",
                    "valid": val_result.valid,
                    "trusted": val_result.trusted,
                    "timestamp": str(val_result.timestamp) if val_result.timestamp else None,
                    "intact": val_result.intact,
                    "status": "Valid" if status_valid else "Invalid",
                    "visual_indicator": "✅ Verified" if status_valid else "❓ Needs Verification"
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