from tkinter.scrolledtext import example

from pydantic import BaseModel, field_validator, Field
from typing import Optional, Any, Union


class ExtractionRequest(BaseModel):
    p_input_content: str = Field(..., title="", description="Base64 encoded file (PDF/JPG/PNG)")
    p_api_name: str = Field(..., title="", description="Must be 'openai'", examples=["openai"])
    p_api_model: str = Field(..., title="", description="GPT Model ID", examples=["gpt-4-turbo"])
    p_api_key: str = Field(..., description="OpenAI API Key")
    p_api_token: str = Field(..., title="", description="Max tokens for API response", examples=["4000"])
    p_template_name: str = Field(..., title="", description="Name of the extraction template")
    p_template_prompt_header: str = Field(default="", title="", description="Prompt for header extraction")
    p_template_prompt_details: str = Field(default="", title="", description="Prompt for detailed extraction")
    p_temperature: float = Field(default=0.9, ge=0.0, le=1.0, title="")
    p_top_p: float = Field(default=0.9, ge=0.0, le=1.0, title="")
    p_timeout: int = Field(default=180, title="", description="Request timeout in seconds")

    @field_validator('p_input_content', 'p_api_key', 'p_template_name')
    @classmethod
    def validate_required_fields(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field is required")
        return v

    @field_validator('p_api_token')
    @classmethod
    def validate_tokens(cls, v: str) -> str:
        token_int = int(v)
        if not 1 <= token_int <= 128000:
            raise ValueError("api_token must be between 1 and 128000")
        return v

    @field_validator('p_api_model')
    @classmethod
    def validate_api_model(cls, v: str) -> str:
        supported_models = [
            "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision-preview",
            "gpt-4", "gpt-4-32k", "gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4.1", "gpt-4.1-mini",
        ]
        if v not in supported_models:
            raise ValueError(f"Unsupported model. Supported models: {', '.join(supported_models)}")
        return v