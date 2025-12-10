from pydantic import BaseModel, field_validator, Field
from typing import Union, Dict, List, Any, Optional


class ExtractionRequest(BaseModel):
    p_input_content: str = Field(..., title="", description="Base64 encoded file (PDF/JPG/PNG)")
    p_api_name: str = Field(..., title="", description="Must be 'openai'", examples=["openai"])
    p_api_model: str = Field(..., title="", description="GPT Model ID", examples=["gpt-4o"])
    p_api_key: str = Field(..., title="", description="OpenAI API Key")
    p_api_token: str = Field(..., title="", description="Max tokens for response (1-128000)", examples=["4000"])
    p_template_name: str = Field(..., title="", description="Identifier for the extraction template")
    p_template_prompt_header: str = Field(default="", title="", description="System/Header prompt context")
    p_template_prompt_details: str = Field(default="", title="", description="User/Detail prompt instructions")
    p_temperature: float = Field(default=0.9, ge=0.0, le=1.0, title="", description="Sampling temperature. Lower values are more deterministic.")
    p_top_p: float = Field(default=0.9, ge=0.0, le=1.0, title="", description="Nucleus sampling probability.")
    p_timeout: int = Field(default=180, title="", description="Request timeout in seconds")

    @field_validator('p_input_content', 'p_api_key', 'p_template_name')
    @classmethod
    def check_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v

    @field_validator('p_api_token')
    @classmethod
    def check_token_range(cls, v: str) -> str:
        if not v.isdigit() or not (1 <= int(v) <= 128000):
            raise ValueError("Token must be integer between 1 and 128000")
        return v

class ExtractionResponse(BaseModel):
    template_name: str
    data: Union[Dict[str, Any], List[Any]]

class VCScanResponse(BaseModel):
    success: bool
    raw_text: str
    cleaned_text: str
    parsed_data: Optional[Union[Dict, str]] = None
    model_used: str
    error: Optional[str] = None