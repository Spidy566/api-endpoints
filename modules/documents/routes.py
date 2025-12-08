import asyncio
import base64
import time
from fastapi import APIRouter, HTTPException, Query, Body, Response
from docxtpl import RichText

from core.config import logger
from core.dependencies import process_pool_executor, thread_pool_executor
from modules.documents import schemas, services

router = APIRouter()


@router.post("/generate-report")
async def generate_report(
        request: schemas.ReportRequest,
        output_format: str = Query("docx", enum=["docx", "pdf"])
):
    try:
        base_template_bytes = base64.b64decode(request.template_file)
    except (base64.binascii.Error, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 template string: {e}")

    if not request.records:
        raise HTTPException(status_code=400, detail="The 'records' field must be a non-empty list.")

    try:
        loop = asyncio.get_running_loop()

        print("Starting DOCX generation...")
        start_docx_gen = time.perf_counter()

        page_break = RichText('\f')
        context_data = {
            "report_name": request.report_name,
            "records": request.records,
            "page_break": page_break
        }

        final_docx_bytes = await loop.run_in_executor(
            process_pool_executor, services.generate_docx, base_template_bytes, context_data
        )

        docx_creation_time = time.perf_counter() - start_docx_gen
        print(f"  -> DOCX generation completed in {docx_creation_time:.4f} seconds.")

        if output_format == "pdf":
            print("Starting DOCX to PDF conversion (isolated unoconv process)...")
            start_pdf_conv = time.perf_counter()

            pdf_bytes = await loop.run_in_executor(
                thread_pool_executor, services.convert_docx_to_pdf_unoconv, final_docx_bytes
            )

            pdf_conversion_time = time.perf_counter() - start_pdf_conv
            print(f"  -> PDF conversion completed in {pdf_conversion_time:.4f} seconds.")

            filename = f"{request.report_name}.pdf"
            headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers=headers
            )
        else:
            filename = f"{request.report_name}.docx"
            headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

            return Response(
                content=final_docx_bytes,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers=headers
            )

    except ValueError as ve:
        print(f"Template Validation Error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))

    except Exception as e:
        print(f"Error during report generation: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred: {str(e)}")

@router.post("/merge_pdf", response_model=schemas.MergeResponse)
async def merge_base64_json(files: list[schemas.MergeFileItem] = Body(...)):
    try:
        files_dict = [item.model_dump() for item in files]
        result = services.merge_files_logic(files_dict)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error merging files: {e}")
        raise HTTPException(status_code=500, detail=f"Error merging files: {e}")