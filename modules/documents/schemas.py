from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class ImageItem(BaseModel):
    source: str = Field(..., title="", description="Base64 encoded string of the image.")
    placeholder: str = Field(..., title="", description="The placeholder name in the DOCX template to replace.")

class ReportRequest(BaseModel):
    template_file: str = Field(..., title="", description="Base64 encoded string of the .docx template file.")
    report_name: str = Field(..., title="", description="The desired name for the output file (without extension).")
    records: list[Dict[str, Any]] = Field(..., title="", description="A list of data dictionaries to populate the template variables ({{var_name}}).")
    images: Optional[list[ImageItem]] = Field(default=[], title="", description="List of images to replace placeholders in the document.")

class MergeFileItem(BaseModel):
    filename: str = Field(default="file", title="", description="The original filename (used for logging/debugging).")
    mimetype: str = Field(..., title="", description="The MIME type of the file. Supports 'application/pdf', 'image/jpeg', 'image/png'.")
    base64content: str = Field(..., title="", description="Base64 encoded string of the file.")

class MergeResponse(BaseModel):
    outputfilename: str = Field(..., title="", description="Filename of the generated merged PDF.")
    outputmimetype: str = Field(..., title="", description="MIME type of the generated merged PDF.")
    outputbase64content: str = Field(..., title="", description="Base64 encoded string of the final merged PDF.")
