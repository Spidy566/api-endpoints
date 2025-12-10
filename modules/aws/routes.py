import base64
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Path
from fastapi.responses import JSONResponse

from core.config import BUCKET, logger
from core.dependencies import s3_client, textract_client
from modules.aws import schemas, services

router = APIRouter()


@router.post(
    "/aws_upload",
    summary="Upload PDF to S3",
    description="Expects base64-encoded PDF on body and 'x-file-name' on header.",
    response_model=schemas.UploadResponse
)
async def upload_pdf(request: Request):
    try:
        file_name = request.headers.get("x-file-name")
        if not file_name:
            raise HTTPException(status_code=400, detail="Missing x-file-name header")

        filename = f"uploads/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file_name}"

        base64_data = await request.body()
        pdf_bytes = base64.b64decode(base64_data)

        s3_client.put_object(
            Bucket=BUCKET,
            Key=filename,
            Body=pdf_bytes,
            ContentType="application/pdf"
        )

        logger.info(f"Uploaded file to S3: s3://{BUCKET}/{filename}")
        return {"success": True, "file_name": filename, "bucket": BUCKET}
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post(
    "/textract/aws_start_expense",
    summary="Start Expense Analysis",
    description="Starts Textract Expense Analysis on an S3 object.",
    response_model=schemas.JobIdResponse
)
def start_expense_analysis(req: schemas.TextractStartRequest):
    try:
        response = textract_client.start_expense_analysis(
            DocumentLocation={"S3Object": {"Bucket": req.bucket, "Name": req.file_name}}
        )
        return {"JobId": response["JobId"]}
    except Exception as e:
        logger.error(f"ExpenseAnalysis start failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/textract/aws_get_expense/{job_id}",
    summary="Get Expense Results",
    description="Polls and parses expense analysis results into Summary and Line Items.",
    response_model=schemas.ExpenseResponse
)
def get_expense_invoice_data(job_id: str = Path(..., title="", description="The Job ID returned by the 'start_expense' endpoint.")):
    return services.parse_expense_response(job_id)

@router.post(
    "/textract/aws_start_document",
    summary="Start Document Analysis",
    description="Starts generic Forms/Tables analysis on S3 object.",
    response_model=schemas.JobIdResponse
)
def start_textract(req: schemas.TextractStartRequest):
    try:
        response = textract_client.start_document_analysis(
            DocumentLocation={"S3Object": {"Bucket": req.bucket, "Name": req.file_name}},
            FeatureTypes=["FORMS", "TABLES"]
        )
        return {"JobId": response["JobId"]}
    except Exception as e:
        logger.error(f"Textract start failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/textract/aws_get_document_status/{job_id}",
    summary="Get Job Status",
    description="Returns the current status of a Textract document analysis job.",
    response_model=schemas.StatusResponse
)
def get_status(job_id: str = Path(..., title="", description="The Job ID returned by the 'start_document' endpoint.")):
    result = textract_client.get_document_analysis(JobId=job_id)
    return {"JobStatus": result["JobStatus"]}

@router.get(
    "/textract/aws_get_document_result/{job_id}",
    summary="Get Raw Pages",
    description="Returns the raw, paginated JSON response from AWS Textract.",
    response_model=schemas.RawTextractResponse
)
def get_result(job_id: str = Path(..., title="", description="The Job ID returned by the 'start_document' endpoint.")):
    pages = []
    response = textract_client.get_document_analysis(JobId=job_id)
    pages.append(response)
    token = response.get("NextToken", None)
    while token:
        response = textract_client.get_document_analysis(JobId=job_id, NextToken=token)
        pages.append(response)
        token = response.get("NextToken", None)
    return {"pages": pages}

@router.get(
    "/textract/aws_get_document/{job_id}",
    summary="Get Vendor Invoice Data",
    description="Parses document analysis into Header Fields, Charges Table, and Container Table.",
    response_model=schemas.VendorInvoiceResponse
)
def get_vendor_invoice_data(job_id: str = Path(..., title="", description="The Job ID returned by the 'start_document' endpoint.")):
    return services.parse_vendor_invoice_response(job_id)

@router.post(
    '/manifest_extract',
    summary="Extract Cargo Manifest",
    description="Upload PDF or Image. Uses Textract + Regex parsing.",
    response_model=schemas.ManifestResponse
)
async def extract_manifest(file: UploadFile = File(..., title="", description="The manifest file. Supports JPG, PNG, and PDF.")):
    if file.content_type not in ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff']:
        raise HTTPException(status_code=400, detail='Unsupported file type')
    try:
        content = await file.read()
        data = services.CargoManifestExtractor().extract_manifest_data(content, file.content_type)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error("Error extracting manifest: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")