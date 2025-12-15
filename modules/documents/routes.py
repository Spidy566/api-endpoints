import asyncio
import base64
import binascii
import time
from fastapi import APIRouter, HTTPException, Query, Body, Response
from docxtpl import RichText

from core.config import logger
from core.dependencies import process_pool_executor, thread_pool_executor
from modules.documents import schemas, services

router = APIRouter()


@router.post(
    "/generate-report",
    summary="Generate Report",
    description="Populates a DOCX template with dynamic data. Returns a binary file download. Supports converting result to PDF.",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {},
                "application/pdf": {}
            },
            "description": "Returns the generated file as a binary stream."
        }
    }
)
async def generate_report(
        request: schemas.DocReportRequest,
        output_format: str = Query("docx", enum=["docx", "pdf"], title="", description="Output format: 'docx' (default) or 'pdf'.")
):
    try:
        base_template_bytes = base64.b64decode(request.template_file)
    except (binascii.Error, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 template string: {e}")

    if not request.records:
        raise HTTPException(status_code=400, detail="The 'records' field must be a non-empty list.")

    try:
        loop = asyncio.get_running_loop()

        start_docx_gen = time.perf_counter()

        page_break = RichText('\f')
        context_data = {
            "report_name": request.report_name,
            "records": request.records,
            "page_break": page_break
        }

        images_data = [img.model_dump() for img in request.images] if request.images else []

        final_docx_bytes = await loop.run_in_executor(
            process_pool_executor, services.generate_docx, base_template_bytes, context_data, images_data
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
        logger.error(f"Template Validation Error: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))

    except Exception as e:
        logger.error(f"Report Generation Error: {e}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@router.post(
    "/merge_pdf",
    summary="Merge Files to PDF",
    description="Accepts a list of Base64 files (PDFs or Images), merges them into a single PDF, and returns the result as Base64.",
    response_model=schemas.DocMergeResponse,
)
async def merge_base64_json(files: list[schemas.DocMergeItem] = Body(..., title="", description="List of files to merge.")):
    try:
        files_dict = [item.model_dump() for item in files]
        result = services.merge_files_logic(files_dict)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error merging files: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")