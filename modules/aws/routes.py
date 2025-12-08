import base64
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse

from core.config import BUCKET, logger
from core.dependencies import s3_client, textract_client
from modules.aws import schemas
from modules.aws.services import (
    CargoManifestExtractor,
    parse_expense_response,
    parse_vendor_invoice_response
)

router = APIRouter()
manifest_extractor = CargoManifestExtractor()

@router.post("/aws_upload")
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

@router.post("/textract/aws_start_expense")
def start_expense_analysis(req: schemas.TextractStartRequest):
    try:
        response = textract_client.start_expense_analysis(
            DocumentLocation={"S3Object": {"Bucket": req.bucket, "Name": req.file_name}}
        )
        return {"JobId": response["JobId"]}
    except Exception as e:
        logger.error(f"ExpenseAnalysis start failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/textract/aws_get_expense/{job_id}")
def get_expense_invoice_data(job_id: str):
    return parse_expense_response(job_id)

@router.post("/textract/aws_start_document")
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

@router.get("/textract/aws_get_document_status/{job_id}")
def get_status(job_id: str):
    result = textract_client.get_document_analysis(JobId=job_id)
    return {"JobStatus": result["JobStatus"]}

@router.get("/textract/aws_get_document_result/{job_id}")
def get_result(job_id: str):
    pages = []
    response = textract_client.get_document_analysis(JobId=job_id)
    pages.append(response)
    token = response.get("NextToken", None)
    while token:
        response = textract_client.get_document_analysis(JobId=job_id, NextToken=token)
        pages.append(response)
        token = response.get("NextToken", None)
    return {"pages": pages}

@router.get("/textract/aws_get_document/{job_id}")
def get_vendor_invoice_data(job_id: str):
    return parse_vendor_invoice_response(job_id)

@router.post('/manifest_extract')
async def extract_manifest(file: UploadFile = File(...)):
    if file.content_type not in ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff']:
        raise HTTPException(status_code=400, detail='Unsupported file type')
    try:
        content = await file.read()
        data = manifest_extractor.extract_manifest_data(content, file.content_type)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error("Error extracting manifest: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")