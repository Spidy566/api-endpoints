from pydantic import BaseModel, field_validator
from typing import Optional


class ExtractionRequest(BaseModel):
    p_input_content: str
    p_api_name: str
    p_api_model: str
    p_api_key: str
    p_api_token: str
    p_template_name: str
    p_template_prompt_header: str = ""
    p_template_prompt_details: str = ""
    p_temperature: float = 0.1
    p_top_p: float = 0.9
    p_timeout: int = 180

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