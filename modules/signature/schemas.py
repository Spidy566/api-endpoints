from pydantic import BaseModel
from typing import Optional, Dict, Any

class InvoiceSignRequest(BaseModel):
    invoice_pdf_base64: str
    name: str
    password: str
    username: Optional[str] = None
    reason: Optional[str] = "Document Authentication"
    location: Optional[str] = "India"
    visible_signature: Optional[bool] = True
    page_number: Optional[int] = -1
    x_coordinate: Optional[float] = 350
    y_coordinate: Optional[float] = 50
    box_width: Optional[float] = 200
    box_height: Optional[float] = 70

class InvoiceSignResponse(BaseModel):
    signed_pdf_base64: str
    error: Optional[str] = None
    auth_error: Optional[str] = None
    signature_info: Optional[dict] = None

class ValidationRequest(BaseModel):
    signed_pdf_base64: str