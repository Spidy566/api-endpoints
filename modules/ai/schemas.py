"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Added Gemini extraction models           | 11-05-2026 | vishal
Models for Bill of Lading & Doc extract  | 07-01-2026 | vishal
Models for Visiting Card response        | 02-10-2025 | dhremagi
Models for OpenAI generic extraction     | 13-06-2025 | senthil
---------------------------------------------------------------------------
"""
from pydantic import BaseModel, field_validator, Field, ConfigDict
from typing import Union, Dict, Any, List, Optional


class AIGenericExtractRequest(BaseModel):
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

class AIGenericExtractResponse(BaseModel):
    template_name: str = Field(..., title="", description="The template name provided in the request.")
    model_config = ConfigDict(extra='allow')

class AIVisitingCardResponse(BaseModel):
    success: bool = Field(..., title="", description="True if the process completed without system errors else False.")
    raw_text: str = Field(..., title="", description="The raw, unformatted text extracted by the OCR engine.")
    cleaned_text: str = Field(..., title="", description="Post-processed text (common OCR typos fixed).")
    parsed_data: Union[Dict[str, Any], List[Any]] = Field(default=None, title="", description="The structured JSON data extracted by the AI.")
    model_used: str = Field(..., title="", description="The AI model used for the extraction.")
    error: Optional[str] = Field(default=None, title="", description="Error message if the AI or OCR failed.")

class AIBillOfLadingRequest(BaseModel):
    base64_file: str = Field(..., title="", description="Base64 encoded string of the file (PDF, JPG, PNG).")
    file_type: str = Field(..., title="", description="The file type extension.", examples=["pdf", "jpg", "png"])
    openai_api_key: str = Field(..., title="", description="Your OpenAI API Key.")
    model: str = Field(default="gpt-4o", title="", description="The OpenAI model to use (e.g., gpt-4o).")

class AIBillOfLadingResponse(BaseModel):
    success: bool = Field(..., title="", description="Indicates whether the Bill of Lading extraction was successful.")
    extracted_bl: Dict[str, Any]  = Field(..., title="", description="The structured JSON object containing extracted fields (Shipper, Consignee, Containers, etc.).")
    error: Optional[str] = Field(default=None, title="", description="Detailed error message if the extraction failed, otherwise null.")

class AIExtractDocumentRequest(BaseModel):
    base64_file: str = Field(..., description="Base64 encoded string of the file (PDF, JPG, PNG).")
    openai_api_key: str = Field(..., description="Your OpenAI API Key.")
    model: str = Field(default="gpt-4o", description="The OpenAI model to use.")
    system_prompt_b64: str = Field(..., description="The system instruction in base64.")
    user_prompt_b64: str = Field(..., description="The user instruction in base64.")

class AIExtractDocumentResponse(BaseModel):
    success: bool = Field(..., title="", description="Indicates whether the document extraction was successful.")
    extracted_data: Dict[str, Any] = Field(..., description="The structured JSON extracted based on your prompts.")
    error: Optional[str] = Field(default=None, title="", description="Detailed error message if the extraction failed, otherwise null.")

class AIGeminiExtractRequest(BaseModel):
    base64_file: str = Field(..., description="Base64 encoded string of the file (PDF, JPG, PNG).")
    gemini_api_key: str = Field(..., description="Your Google Gemini API Key.")
    model: str = Field(default="gemini-2.5-flash", description="The Gemini model to use (e.g., gemini-2.5-flash).")
    system_prompt_b64: str = Field(..., description="The system instruction defining the JSON structure, in base64.")
    user_prompt_b64: str = Field(..., description="The user instruction on what to extract, in base64.")

class AIGeminiExtractResponse(BaseModel):
    success: bool = Field(..., title="", description="Indicates whether the document extraction was successful.")
    extracted_data: Dict[str, Any] = Field(default_factory=dict, description="The structured JSON extracted based on your prompts.")
    error: Optional[str] = Field(default=None, title="", description="Detailed error message if the extraction failed, otherwise null.")