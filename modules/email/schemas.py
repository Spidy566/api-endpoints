from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, EmailStr, SecretStr, ConfigDict, Field
from pydantic.alias_generators import to_pascal


class EmailSendAttachmentItem(BaseModel):
    Filename: str = Field(..., title="", description="Name of the file to attach (e.g., 'invoice.pdf').")
    Content: str = Field(..., title="", description="Base64 encoded content of the attachment.")

class EmailSendMessage(BaseModel):
    From: EmailStr = Field(..., title="", description="Sender's email address.")
    To: List[EmailStr] = Field(..., title="", description="List of recipient email addresses.")
    Cc: Optional[List[EmailStr]] = Field(default=[], title="", description="List of CC recipient email addresses.")
    Bcc: Optional[List[EmailStr]] = Field(default=[], title="", description="List of BCC recipient email addresses.")
    Subject: str = Field(..., title="", description="Email subject.")
    TextBody: str = Field(..., title="", description="Plain text body of the email.")
    HtmlBody: Optional[str] = Field(default=None, title="", description="HTML body of the email.")
    HtmlBodyEncoding: Optional[Literal['plain', 'hex', 'quoted-printable', 'html-entities', 'base64']] = Field(
        default='plain',
        description="Encoding type for HtmlBody. Options are 'plain', 'hex', 'quoted-printable', 'html-entities', 'base64'."
    )
    ReplyTo: Optional[EmailStr] = Field(default=None, title="", description="Email address to reply to.")
    Attachments: Optional[List[EmailSendAttachmentItem]] = Field(default=None, title="", description="List of attachments.")

    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

class EmailSmtpConfig(BaseModel):
    Server: str = Field(..., title="", description="SMTP server hostname.")
    Port: int = Field(..., title="", description="SMTP server port.")
    Username: EmailStr = Field(..., title="", description="SMTP username.")
    Password: SecretStr = Field(..., title="", description="SMTP password or App Password.")

    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

class EmailSendRequest(BaseModel):
    smtp_config: EmailSmtpConfig = Field(..., title="", description="SMTP configuration for sending the email.")
    message: EmailSendMessage = Field(..., title="", description="Email message details.")

    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

class EmailSendResponse(BaseModel):
    status: str = Field(..., title="", description="Status of the email sending operation.")
    message: str = Field(..., title="", description="Message associated with the status.")

class EmailExtractionRequest(BaseModel):
    file_base64: str = Field(..., title="", description="Base64 encoded email file content.")
    file_type: str = Field(..., title="", description="Type of the email file ('eml' or 'msg').")
    file_name: str = Field(default=None, title="", description="Optional: Name of the email file.")

class EmailExtractedAttachmentItem(BaseModel):
    index: Optional[int] = Field(default=None, title="", description="Index of the attachment in the email.")
    filename: str = Field(..., title="", description="Name of the extracted file.")
    content_type: str = Field(..., title="", description="Content type of the extracted file.")
    file_extension: str = Field(..., title="", description="File extension of the extracted file.")
    size_bytes: int = Field(..., title="", description="Size of the extracted file in bytes.")
    base64_length: Optional[int] = Field(default=None, title="", description="Length of the base64 encoded content.")
    content: str = Field(..., title="", description="Base64 encoded content of the extracted file.")

class EmailExtractionResponse(BaseModel):
    success: bool = Field(..., title="", description="Whether the extraction was successful.")
    message: Optional[str] = Field(default=None, title="", description="Message associated with the extraction status.")
    file_type: str = Field(..., title="", description="Detected file type (eml/msg).")
    file_name: Optional[str] = Field(default=None, title="", description="Name of the source file.")
    total_attachments: int = Field(..., title="", description="Count of attachments found.")
    file_type_counts: Optional[Dict[str, int]] = Field(default=None, title="", description="Summary of attachment types found.")
    supported_formats: Optional[List[str]] = Field(default=None, title="", description="List of supported formats.")
    attachments: List[EmailExtractedAttachmentItem] = Field(..., title="", description="List of extracted attachment objects.")