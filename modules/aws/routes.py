"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Added Textract and S3 Upload endpoints   | 19-06-2025 | senthil
---------------------------------------------------------------------------
"""

import base64
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Path
from fastapi.responses import JSONResponse
from botocore.exceptions import ClientError

from core.config import BUCKET, logger
from core.dependencies import s3_client, textract_client
from modules.aws import schemas, services

router = APIRouter()


@router.post(
    "/aws_upload",
    summary="Upload PDF to S3",
    description="Expects base64-encoded PDF on body and 'x-file-name' on header.",
    response_model=schemas.AWSUploadResponse
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
    except ClientError as e:
        code = e.response['Error']['Code']
        msg = e.response['Error']['Message']
        logger.error(f"S3 Upload Error: {code} - {msg}")
        raise HTTPException(status_code=400, detail=f"S3 Error: {msg}")

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/textract/aws_start_expense",
    summary="Start Expense Analysis",
    description="Starts Textract Expense Analysis on an S3 object.",
    response_model=schemas.AWSJobIdResponse
)
def start_expense_analysis(req: schemas.AWSTextractStartRequest):
    try:
        response = textract_client.start_expense_analysis(
            DocumentLocation={"S3Object": {"Bucket": req.bucket, "Name": req.file_name}}
        )
        return {"JobId": response["JobId"]}

    except ClientError as e:
        code = e.response['Error']['Code']
        msg = e.response['Error']['Message']
        logger.error(f"AWS Expense Start Error: {code} - {msg}")

        if code == 'InvalidS3ObjectException':
            raise HTTPException(
                status_code=404,
                detail=f"File '{req.file_name}' not found in bucket '{req.bucket}'."
            )
        elif code == 'InvalidParameterException':
            raise HTTPException(status_code=400, detail=f"Invalid Parameters: {msg}")
        elif code == 'UnsupportedDocumentException':
            raise HTTPException(status_code=400, detail="File format not supported by Textract.")
        elif code == 'AccessDeniedException':
            raise HTTPException(status_code=403, detail="Access Denied to S3 Object.")

        raise HTTPException(status_code=400, detail=f"AWS Error: {msg}")

    except Exception as e:
        logger.error(f"Start Expense Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/textract/aws_get_expense/{job_id}",
    summary="Get Expense Results",
    description="Polls and parses expense analysis results into Summary and Line Items.",
    response_model=schemas.AWSExpenseResponse
)
def get_expense_invoice_data(job_id: str = Path(..., title="", description="The Job ID returned by the 'start_expense' endpoint.")):
    try:
        return services.parse_expense_response(job_id)
    except HTTPException:
        raise
    except ClientError as e:
        code = e.response['Error']['Code']
        if code == 'InvalidJobIdException':
            raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' not found.")
        raise HTTPException(status_code=400, detail=f"AWS Error: {e.response['Error']['Message']}")

@router.post(
    "/textract/aws_start_document",
    summary="Start Document Analysis",
    description="Starts generic Forms/Tables analysis on S3 object.",
    response_model=schemas.AWSJobIdResponse
)
def start_textract(req: schemas.AWSTextractStartRequest):
    try:
        response = textract_client.start_document_analysis(
            DocumentLocation={"S3Object": {"Bucket": req.bucket, "Name": req.file_name}},
            FeatureTypes=["FORMS", "TABLES"]
        )
        return {"JobId": response["JobId"]}

    except ClientError as e:
        code = e.response['Error']['Code']
        msg = e.response['Error']['Message']
        logger.error(f"AWS Document Start Error: {code} - {msg}")

        if code == 'InvalidS3ObjectException':
            raise HTTPException(
                status_code=404,
                detail=f"File '{req.file_name}' not found in bucket '{req.bucket}'."
            )
        elif code == 'InvalidParameterException':
            raise HTTPException(status_code=400, detail=f"Invalid Parameters: {msg}")
        elif code == 'UnsupportedDocumentException':
            raise HTTPException(status_code=400, detail="File format not supported by Textract.")
        elif code == 'AccessDeniedException':
            raise HTTPException(status_code=403, detail="Access Denied to S3 Object.")

        raise HTTPException(status_code=400, detail=f"AWS Error: {msg}")

    except Exception as e:
        logger.error(f"Start Document Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/textract/aws_get_document_status/{job_id}",
    summary="Get Job Status",
    description="Returns the current status of a Textract document analysis job.",
    response_model=schemas.AWSJobStatusResponse
)
def get_status(job_id: str = Path(..., title="", description="The Job ID returned by the 'start_document' endpoint.")):
    try:
        result = textract_client.get_document_analysis(JobId=job_id)
        return {"JobStatus": result["JobStatus"]}
    except ClientError as e:
        code = e.response['Error']['Code']
        message = e.response['Error']['Message']

        if code == 'InvalidJobIdException':
            raise HTTPException(status_code=404, detail=f"Job ID not found: {message}")
        raise HTTPException(status_code=400, detail=f"AWS Error: {message}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/textract/aws_get_document_result/{job_id}",
    summary="Get Raw Pages",
    description="Returns the raw, paginated JSON response from AWS Textract.",
    response_model=schemas.AWSRawTextractResponse
)
def get_result(job_id: str = Path(..., title="", description="The Job ID returned by the 'start_document' endpoint.")):
    try:
        pages = []
        response = textract_client.get_document_analysis(JobId=job_id)
        pages.append(response)
        token = response.get("NextToken", None)
        while token:
            response = textract_client.get_document_analysis(JobId=job_id, NextToken=token)
            pages.append(response)
            token = response.get("NextToken", None)
        return {"pages": pages}
    except ClientError as e:
        code = e.response['Error']['Code']
        message = e.response['Error']['Message']

        if code == 'InvalidJobIdException':
            raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' does not exist or has expired.")
        raise HTTPException(status_code=400, detail=f"AWS Error: {message}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/textract/aws_get_document/{job_id}",
    summary="Get Vendor Invoice Data",
    description="Parses document analysis into Header Fields, Charges Table, and Container Table.",
    response_model=schemas.AWSVendorInvoiceResponse
)
def get_vendor_invoice_data(job_id: str = Path(..., title="", description="The Job ID returned by the 'start_document' endpoint.")):
    try:
        return services.parse_vendor_invoice_response(job_id)
    except HTTPException:
        raise
    except ClientError as e:
        code = e.response['Error']['Code']
        if code == 'InvalidJobIdException':
            raise HTTPException(status_code=404, detail=f"Job ID '{job_id}' not found.")
        raise HTTPException(status_code=400, detail=f"AWS Error: {e.response['Error']['Message']}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    '/manifest_extract',
    summary="Extract Cargo Manifest",
    description="Upload PDF or Image. Uses Textract + Regex parsing.",
    response_model=schemas.AWSManifestResponse
)
async def extract_manifest(file: UploadFile = File(..., title="", description="The manifest file. Supports JPG, PNG, and PDF.")):
    if file.content_type not in ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff']:
        raise HTTPException(status_code=400, detail='Unsupported file type')
    try:
        content = await file.read()
        data = services.CargoManifestExtractor().extract_manifest_data(content, file.content_type)
        return JSONResponse(content=data)
    except ClientError as e:
        raise HTTPException(status_code=400, detail=f"AWS Error: {e.response['Error']['Message']}")
    except Exception as e:
        logger.error("Error extracting manifest: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")