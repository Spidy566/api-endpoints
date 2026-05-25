"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Resilient key parser & encryption utility| 25-05-2026 | vishal
---------------------------------------------------------------------------
"""
import base64
from core.config import logger

def _load_public_key_resilient(key_str: str):
    """
    Attempts to load public keys across various encodings and formats
    by self-healing whitespace, line-wraps, and tag omission.
    """
    from cryptography.hazmat.primitives.serialization import (
        load_pem_public_key,
        load_ssh_public_key,
        load_der_public_key
    )

    key_str = key_str.strip()
    if (key_str.startswith('"') and key_str.endswith('"')) or (key_str.startswith("'") and key_str.endswith("'")):
        key_str = key_str[1:-1].strip()

    key_bytes = key_str.encode('utf-8')

    if b"-----BEGIN" in key_bytes:
        try:
            return load_pem_public_key(key_bytes)
        except Exception as pem_err:
            logger.debug(f"ResilientLoader: Failed standard PEM load: {pem_err}")

    try:
        clean_lines = [line.strip() for line in key_str.splitlines() if line.strip()]
        single_line_ssh = " ".join(clean_lines)
        return load_ssh_public_key(single_line_ssh.encode('utf-8'))
    except Exception as ssh_err:
        logger.debug(f"ResilientLoader: Failed standard OpenSSH load: {ssh_err}")

    if key_str.startswith("AAAAB3NzaC1yc"):
        try:
            reconstructed_ssh = f"ssh-rsa {key_str}"
            return load_ssh_public_key(reconstructed_ssh.encode('utf-8'))
        except Exception:
            pass

    try:
        clean_base64 = "".join(key_str.split())
        der_bytes = base64.b64decode(clean_base64)
        return load_der_public_key(der_bytes)
    except Exception as der_err:
        logger.debug(f"ResilientLoader: Failed raw DER load: {der_err}")

    raise ValueError(
        "Invalid public key format. The public key must be a valid PEM key "
        "or an OpenSSH key format (e.g., starting with 'ssh-rsa')."
    )


def encrypt_ssh_credentials(payload: dict, public_key_str: str) -> dict:
    try:
        import os
        import base64
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sym_padding
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
        from cryptography.hazmat.primitives import hashes

        public_key = _load_public_key_resilient(public_key_str)

        symmetric_key = os.urandom(32)
        iv = os.urandom(16)

        cipher = Cipher(algorithms.AES(symmetric_key), modes.CBC(iv))

        def encrypt_field(field_value: str) -> str:
            padder = sym_padding.PKCS7(128).padder()
            padded = padder.update(field_value.encode('utf-8')) + padder.finalize()
            encryptor = cipher.encryptor()
            encrypted_bytes = encryptor.update(padded) + encryptor.finalize()
            return base64.b64encode(encrypted_bytes).decode('utf-8')

        enc_user = encrypt_field(payload["username"])
        enc_pass = encrypt_field(payload["password"])

        encrypted_symmetric_key = public_key.encrypt(
            symmetric_key,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA1()),
                algorithm=hashes.SHA1(),
                label=None
            )
        )

        return {
            "success": True,
            "encrypted_username": enc_user,
            "encrypted_password": enc_pass,
            "encrypted_symmetric_key": base64.b64encode(encrypted_symmetric_key).decode('utf-8'),
            "iv": base64.b64encode(iv).decode('utf-8'),
            "error": None
        }
    except Exception as e:
        return {
            "success": False,
            "encrypted_username": "",
            "encrypted_password": "",
            "encrypted_symmetric_key": "",
            "iv": "",
            "error": str(e)
        }