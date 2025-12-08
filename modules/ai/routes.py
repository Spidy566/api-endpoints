import os
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional

from core.config import logger
from modules.ai import schemas, services, utils

router = APIRouter()


@router.post("/openai_extract")
async def openai_extract(request: schemas.ExtractionRequest):
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
            request.p_api_key, request.p_api_model,
            request.p_template_prompt_header, request.p_template_prompt_details,
            file_content, request.p_api_token, request.p_temperature,
            request.p_top_p, request.p_timeout
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
            raise HTTPException(status_code=500, detail=result["error"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@router.post("/scan_vc")
async def scan_visiting_card(
    file: UploadFile = File(...),
    api_key: Optional[str] = Form(None),
    model: Optional[str] = Form("gpt-5-mini"),
):
    """Scans a visiting card (JPG/PNG/PDF), performs OCR, and returns structured JSON."""
    temp_path = None
    try:
        file_bytes = await file.read()
        if not file_bytes or len(file_bytes) < 10:
            raise HTTPException(status_code=400, detail="Empty file or too small")

        temp_path = utils.to_temp_image(
            file_bytes,
            file.content_type or "",
            file.filename or "upload"
        )

        raw_text = utils.ocr_extract_card(temp_path)
        cleaned_text = utils.clean_card_text(raw_text)

        if not cleaned_text.strip():
            return {
                "success": False,
                "message": "No readable text found via OCR.",
                "raw_text": raw_text,
                "cleaned_text": cleaned_text,
            }

        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise HTTPException(
                status_code=400,
                detail="OpenAI API key not provided (form api_key or env OPENAI_API_KEY)"
            )

        result = services.extract_card_json_with_openai(key, model, raw_text, cleaned_text)

        if isinstance(result, dict) and "error" in result:
            return {
                "success": False,
                "raw_text": raw_text,
                "cleaned_text": cleaned_text,
                "error": result.get("error"),
                "raw": result.get("raw"),
                "model_used": model,
            }

        return {
            "success": True,
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "parsed_data": result,
            "model_used": model,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Visiting card scan error: {str(e)}")
    finally:
        try:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass