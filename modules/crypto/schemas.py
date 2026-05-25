"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Models for SSH credential hybrid enc     | 25-05-2026 | vishal
---------------------------------------------------------------------------
"""
from pydantic import BaseModel, Field
from typing import Optional

class SSHCredentialEncryptRequest(BaseModel):
    username: str = Field(..., description="The SSH username to encrypt.")
    password: str = Field(..., description="The SSH password to encrypt.")
    public_key: str = Field(..., description="The RSA public key (PEM or OpenSSH format) to encrypt the symmetric key with.")

class SSHCredentialEncryptResponse(BaseModel):
    success: bool
    encrypted_username: str = Field(..., description="Symmetric ciphertext of the username.")
    encrypted_password: str = Field(..., description="Symmetric ciphertext of the password.")
    encrypted_symmetric_key: str = Field(..., description="Base64 encoded wrapped AES key.")
    iv: str = Field(..., description="Base64 encoded initialization vector.")
    error: Optional[str] = None