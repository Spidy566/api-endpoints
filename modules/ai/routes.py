"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Added /gemini_extract endpoint           | 11-05-2026 | vishal
Added /extract_document                  | 03-02-2026 | vishal
Added /extract_bl                        | 07-01-2026 | vishal
Added /scan_vc                           | 02-10-2025 | dhremagi
Added /openai_extract                    | 13-06-2025 | senthil
---------------------------------------------------------------------------
"""

import base64
import asyncio
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional

from core.config import logger
from core.dependencies import thread_pool_executor

from modules.ai import schemas, services, utils

router = APIRouter()


@router.post(
    "/openai_extract",
    summary="Openai Extract",
    description="Accepts Base64 (PDF/Img), sends to OpenAI, returns structured JSON.",
    response_model=schemas.AIGenericExtractResponse
)
async def openai_extract(request: schemas.AIGenericExtractRequest):
    """Extract data from PDF/JPEG/JPG/PNG files"""
    try:
        file_content = utils.extract_base64_content(request.p_input_content)
        if not file_content:
            raise HTTPException(status_code=400, detail="Invalid base64 content")

        if not request.p_template_prompt_header.strip() and not request.p_template_prompt_details.strip():
            raise HTTPException(status_code=400, detail="At least one prompt required")

        if request.p_api_name.lower() != "openai":
            raise HTTPException(status_code=400, detail="Only OpenAI supported")

        logger.info(f"Processing request for template: {request.p_template_name}")

        result = services.process_with_openai(
            request.p_api_key,
            request.p_api_model,
            request.p_template_prompt_header,
            request.p_template_prompt_details,
            file_content,
            request.p_api_token,
            request.p_temperature,
            request.p_top_p,
            request.p_timeout
        )

        logger.info(f"OpenAI processing result: success={result['success']}")

        if result["success"]:
            extracted_data = result["extracted_data"]

            if isinstance(extracted_data, dict):
                return {
                    "template_name": request.p_template_name,
                    **extracted_data
                }
            elif isinstance(extracted_data, list):
                return {
                    "template_name": request.p_template_name,
                    "data": extracted_data
                }
            else:
                return {
                    "template_name": request.p_template_name,
                    "extracted_data": extracted_data
                }
        else:
            logger.error(f"OpenAI processing failed: {result['error']}")
            raise HTTPException(status_code=502, detail=f"OpenAI Error: {result.get('error')}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@router.post(
    "/scan_vc",
    summary="Scan Visiting Card (Vision)",
    description="Uploads image/PDF, uses OpenAI Vision to transcribe and parse data.",
    response_model=schemas.AIVisitingCardResponse
)
async def scan_visiting_card(
        file: UploadFile = File(..., description="The visiting card file (JPG/PNG/PDF)."),
        api_key: Optional[str] = Form(None, description="OpenAI API Key."),
        model: Optional[str] = Form("gpt-4o", description="Model ID (e.g., gpt-4o, gpt-4o-mini)."),
):
    try:
        file_bytes = await file.read()
        if len(file_bytes) < 10:
            raise HTTPException(status_code=400, detail="File is empty or too small.")

        base64_file = base64.b64encode(file_bytes).decode('utf-8')

        if not api_key:
            raise HTTPException(status_code=401, detail="Missing OpenAI API Key.")

        result = services.scan_vc_with_vision(api_key, base64_file, model)

        if not result.get("success"):
            err_msg = str(result.get("error", "")).lower()
            if "authentication" in err_msg or "401" in err_msg:
                raise HTTPException(status_code=401, detail=result.get("error"))
            elif "rate limit" in err_msg:
                raise HTTPException(status_code=429, detail="OpenAI Rate Limit Exceeded.")
            else:
                raise HTTPException(status_code=500, detail=result.get("error"))

        ai_data = result.get("data", {})
        raw_text = ai_data.get("raw_text", "")
        parsed_data = ai_data.get("parsed_data", {})

        cleaned_text = utils.clean_card_text(raw_text)

        return {
            "success": True,
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "parsed_data": parsed_data,
            "model_used": model,
            "error": None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Processing Error: {str(e)}")


@router.post(
    "/extract_bl",
    summary="Extract Bill of Lading",
    description="Extracts specific fields from a BL Document using OpenAI Vision.",
    response_model=schemas.AIBillOfLadingResponse
)
async def extract_bl(request: schemas.AIBillOfLadingRequest):
    try:
        if not request.base64_file:
            raise HTTPException(status_code=400, detail="PDF content is required")

        loop = asyncio.get_running_loop()

        result = await loop.run_in_executor(
            thread_pool_executor,
            services.extract_bl_data,
            request.openai_api_key,
            request.base64_file,
            request.model
        )

        if not result["success"]:
            error_msg = result.get("error", "Unknown error")
            status_code = 502 if "OpenAI Error" in error_msg else 500
            raise HTTPException(status_code=status_code, detail=error_msg)

        return {
            "success": True,
            "extracted_bl": result["extracted_bl"]
        }

    except HTTPException:
        raise
    except Exception as route_err:
        logger.error(f"BL Route Error: {route_err}")
        raise HTTPException(status_code=500, detail=f"Server Error: {str(route_err)}")

@router.post(
    "/extract_document",
    summary="Process Any Document",
    description="Extracts data from any document (Invoice, Packing List, etc) using custom prompts.",
    response_model=schemas.AIExtractDocumentResponse
)
async def extract_document(request: schemas.AIExtractDocumentRequest):
    try:
        if not request.base64_file:
            raise HTTPException(status_code=400, detail="File content is required")

        loop = asyncio.get_running_loop()

        result = await loop.run_in_executor(
            thread_pool_executor,
            services.extract_document,
            request.openai_api_key,
            request.base64_file,
            request.model,
            request.system_prompt_b64,
            request.user_prompt_b64
        )

        if not result["success"]:
            error_msg = result.get("error", "Unknown error")
            status_code = 502 if "OpenAI Error" in error_msg else 500
            raise HTTPException(status_code=status_code, detail=error_msg)

        return {
            "success": True,
            "extracted_data": result["extracted_data"]
        }

    except HTTPException:
        raise
    except Exception as route_err:
        raise HTTPException(status_code=500, detail=f"Server Error: {str(route_err)}")

@router.post(
    "/gemini_extract",
    summary="Extract Document via Gemini",
    description="Extracts data from a base64 document (PDF/Img) into a strict structured JSON format using Google Gemini API. Prompts must be base64 encoded.",
    response_model=schemas.AIGeminiExtractResponse
)
async def gemini_extract(request: schemas.AIGeminiExtractRequest):
    try:
        if not request.base64_file:
            raise HTTPException(status_code=400, detail="File content is required")

        loop = asyncio.get_running_loop()

        # Run extraction in a thread pool to prevent blocking the async event loop
        result = await loop.run_in_executor(
            thread_pool_executor,
            services.extract_with_gemini,
            request.gemini_api_key,
            request.base64_file,
            request.model,
            request.system_prompt_b64,
            request.user_prompt_b64
        )

        if not result["success"]:
            error_msg = result.get("error", "Unknown error")
            status_code = 502 if "API Error" in error_msg else 500
            raise HTTPException(status_code=status_code, detail=error_msg)

        return {
            "success": True,
            "extracted_data": result["extracted_data"],
            "error": None
        }

    except HTTPException:
        raise
    except Exception as route_err:
        logger.error(f"Gemini Route Error: {route_err}")
        raise HTTPException(status_code=500, detail=f"Server Error: {str(route_err)}")