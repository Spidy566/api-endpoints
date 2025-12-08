from typing import List, Optional, Literal
from pydantic import BaseModel, EmailStr, SecretStr, ConfigDict, Field
from pydantic.alias_generators import to_pascal


class Attachment(BaseModel):
    Filename: str
    Content: str

class EmailMessage(BaseModel):
    From: EmailStr
    To: List[EmailStr]
    Cc: Optional[List[EmailStr]] = []
    Bcc: Optional[List[EmailStr]] = []
    Subject: str
    TextBody: str
    HtmlBody: Optional[str] = None
    HtmlBodyEncoding: Optional[Literal['plain', 'hex', 'quoted-printable', 'html-entities', 'base64']] = Field(
        default='plain',
        description="Encoding type for HtmlBody. Options are 'plain', 'hex', 'quoted-printable', 'html-entities', 'base64'."
    )
    ReplyTo: Optional[EmailStr] = None
    Attachments: Optional[List[Attachment]] = None

    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

class SmtpConfig(BaseModel):
    Server: str
    Port: int
    Username: EmailStr
    Password: SecretStr

    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

class EmailRequest(BaseModel):
    SmtpConfig: SmtpConfig
    Message: EmailMessage

    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

class EmailBase64Request(BaseModel):
    file_base64: str
    file_type: str
    file_name: str = None