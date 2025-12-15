from pydantic import BaseModel, Field
from typing import List, Optional

class SignCreationRequest(BaseModel):
    invoice_pdf_base64: str = Field(..., title="",description="Base64 encoded string of the PDF file to be signed.")
    name: str = Field(..., title="", description="Name of the signer. Must match the filename of a .pfx certificate stored on the server.")
    password: str = Field(..., title="", description="Password to decrypt the .pfx certificate.")
    username: Optional[str] = Field(default=None, title="", description="Optional username to validate against the signer name. If provided, must match 'name'.")
    reason: Optional[str] = Field(default="Document Authentication", title="", description="The reason for signing this document.")
    location: Optional[str] = Field(default="India", title="", description="The physical location of the signer.")
    visible_signature: Optional[bool] = Field(default=True, title="", description="If True, adds a visual signature box to the PDF. If False, adds an invisible digital signature.")
    page_number: Optional[int] = Field(default=-1, title="", description="Page number to place the signature on. Use -1 for the last page.")
    x_coordinate: Optional[float] = Field(default=350, title="", description="X-coordinate (horizontal position) for the signature box.")
    y_coordinate: Optional[float] = Field(default=50, title="", description="Y-coordinate (vertical position) for the signature box.")
    box_width: Optional[float] = Field(default=200, title="", description="Width of the visual signature box.")
    box_height: Optional[float] = Field(default=70, title="", description="Height of the visual signature box.")

class SignValidationRequest(BaseModel):
    signed_pdf_base64: str = Field(..., title="", description="Base64 encoded string of the signed PDF file to be validated.")

class SignatureInfo(BaseModel):
    signer: str = Field(..., title="", description="Name of the signer.")
    organization: Optional[str] = Field(default=None, title="", description="Organization of the signer.")
    timestamp: str = Field(..., title="", description="Timestamp of the signature.")
    reason: Optional[str] = Field(default=None, title="", description="Reason for signing the document.")
    verification_status: str = Field(..., title="", description="Status of the signature verification.")

class SignCreationResponse(BaseModel):
    signed_pdf_base64: str = Field(..., title="", description="Base64 encoded string of the signed PDF file.")
    error: Optional[str] = Field(default=None, title="", description="Error message if the signature process failed.")
    auth_error: Optional[str] = Field(default=None, title="", description="Error message if the username/name mismatch occurs.")
    signature_info: Optional[dict] = Field(default=None, title="", description="Metadata about the successfully applied signature.")

class SignSignatureDetails(BaseModel):
    field_name: str = Field(..., title="", description="Name of the signature field.")
    signer: Optional[str] = Field(default="Unknown", title="", description="Name of the signer.")
    valid: Optional[bool] = Field(default=False, title="", description="Whether the signature is valid.")
    trusted: Optional[bool] = Field(default=False, title="", description="Whether the signer is trusted.")
    timestamp: Optional[str] = Field(default=None, title="", description="Timestamp of the signature.")
    intact: Optional[bool] = Field(default=False, title="", description="True if the document has not been modified since signing.")
    status: Optional[str] = Field(default="Unknown", title="", description="Status of the signature validation.")
    visual_indicator: str = Field(..., title="", description="Visual indicator of the signature status.")
    error: Optional[str] = Field(default=None, title="", description="Error message if the signature validation failed.")

class SignValidationResponse(BaseModel):
    has_signatures: bool = Field(..., title="", description="True if the PDF contains embedded signatures.")
    signature_count: Optional[int] = Field(default=0, title="", description="Number of embedded signatures in the PDF.")
    signatures: Optional[List[SignSignatureDetails]] = Field(default=[], title="", description="Detailed analysis of each signature found.")
    message: Optional[str] = Field(default=None, title="", description="Message indicating the result of the validation.")
    error: Optional[str] = Field(default=None, title="", description="Error message if the validation failed.")

class SignCertUploadResponse(BaseModel):
    success: bool = Field(..., title="", description="True if the certificate was successfully uploaded.")
    filename: str = Field(..., title="", description="Name of the uploaded certificate file.")
    overwritten: bool = Field(..., title="", description="True if the certificate was overwritten.")
