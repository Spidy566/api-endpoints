import os
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
    summary="Scan Visiting Card",
    description="Upload image/PDF, performs OCR, then AI extraction and returns structured JSON.",
    response_model=schemas.AIVisitingCardResponse
)
async def scan_visiting_card(
    file: UploadFile = File(..., title="", description="The visiting card file. Supports JPG, PNG, and PDF."),
    api_key: Optional[str] = Form(None, title="", description="The OpenAI API Key.",),
    model: Optional[str] = Form(None, title="", description="The OpenAI model ID to use for extraction.", examples=['gpt-4o', 'gpt-4o-mini']),
):
    """Scans a visiting card (JPG/PNG/PDF), performs OCR, and returns structured JSON."""
    temp_path = None
    try:
        file_bytes = await file.read()
        if len(file_bytes) < 10:
            raise HTTPException(status_code=400, detail="File is empty or too small.")

        try:
            temp_path = utils.to_temp_image(
                file_bytes,
                file.content_type or "",
                file.filename or "upload"
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid image format: {str(e)}")

        raw_text = utils.ocr_extract_card(temp_path)
        clean_text = utils.clean_card_text(raw_text)

        if len(clean_text) < 5:
            raise HTTPException(status_code=422, detail="OCR failed to detect readable text.")

        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise HTTPException(status_code=401, detail="Missing OpenAI API Key.")

        result = services.extract_card_json_with_openai(key, model, raw_text, clean_text)

        if isinstance(result, dict) and "error" in result:
            error_msg = str(result["error"]).lower()
            if "invalid api key" in error_msg or "authentication" in error_msg:
                raise HTTPException(status_code=401, detail=f"OpenAI Auth Error: {result['error']}")
            elif "model" in error_msg and "not found" in error_msg:
                raise HTTPException(status_code=404, detail=f"OpenAI Model Error: {result['error']}")
            elif "rate limit" in error_msg:
                raise HTTPException(status_code=429, detail="OpenAI Rate Limit Exceeded.")
            else:
                raise HTTPException(status_code=502, detail=f"OpenAI Processing Failed: {result['error']}")

        return {
            "success": True,
            "raw_text": raw_text,
            "cleaned_text": clean_text,
            "parsed_data": result,
            "error": None,
            "model_used": model,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"VC Scan Error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Processing Error: {str(e)}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@router.post(
    "/extract-bl",
    summary="Extract Bill of Lading",
    description="Extracts specific fields from a BL PDF using OpenAI Vision (gpt-4o-mini).",
    response_model=schemas.AIBillOfLadingResponse
)
async def extract_bl(request: schemas.AIBillOfLadingRequest):
    try:
        if not request.pdf_base64:
            raise HTTPException(status_code=400, detail="PDF content is required")

        loop = asyncio.get_running_loop()

        result = await loop.run_in_executor(
            thread_pool_executor,
            services.extract_bl_data,
            request.openai_api_key,
            request.pdf_base64
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