from pydantic import BaseModel, Field
from typing import List, Dict, Any

class TextractStartRequest(BaseModel):
    bucket: str = Field(..., title="", description="The S3 Bucket name where the file is stored.", examples=["fresa-uploads"])
    file_name: str = Field(..., title="", description="The S3 Key (path) of the file.", examples=["uploads/20231201_invoice.pdf"])

class UploadResponse(BaseModel):
    success: bool = Field(..., title="", description="Indicates if the file was successfully uploaded to S3.")
    file_name: str = Field(..., title="", description="The full S3 Key (path) of the uploaded file.", examples=["uploads/20231201_invoice.pdf"])
    bucket: str = Field(..., title="", description="The S3 Bucket name where the file was uploaded.", examples=["fresa-uploads"])

class JobIdResponse(BaseModel):
    JobId: str = Field(..., title="", description="The AWS Textract Job ID.")

class StatusResponse(BaseModel):
    JobStatus: str = Field(..., title="", description="The current status of the Textract job.", examples=["IN_PROGRESS", "SUCCEEDED", "FAILED"])

class ExpenseResponse(BaseModel):
    summary_fields: List[Dict[str, str]] = Field(..., title="", description="Header-level fields extracted (Vendor Name, Total Amount, Invoice Date, etc).")
    line_items: List[Dict[str, str]] = Field(..., title="", description="Detailed line items extracted from the invoice body.")

class VendorInvoiceResponse(BaseModel):
    header_fields: Dict[str, str] = Field(..., title="", description="Top-level metadata (Invoice, Date, Consignee, etc).")
    charges_table: List[Dict[str, str]] = Field(..., title="", description="List of service charges, deduped.")
    container_table: List[Dict[str, str]] = Field(..., title="", description="Container details if present in the invoice.")

class RawTextractResponse(BaseModel):
    pages: List[Dict[str, Any]] = Field(..., title="", description="A list of raw JSON objects returned by AWS Textract, one per pagination page. Contains full 'Blocks', 'DocumentMetadata', etc.")

class ManifestResponse(BaseModel):
    key_value_pairs: Dict[str, str] = Field(..., title="", description="Flat dictionary of extracted fields (e.g., Agent Name, Date, Weights).")
    tables: List[Any] = Field(..., title="", description="List of extracted tables. Each table is a list of rows (objects or arrays).")
