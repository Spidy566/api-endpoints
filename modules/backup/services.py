import os
import shutil
from fastapi import UploadFile, HTTPException
from fastapi.responses import FileResponse

from core.config import logger, BACKUP_DIR

def save_backup_file(file: UploadFile) -> str:
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        file_path = os.path.join(BACKUP_DIR, file.filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logger.info(f"File saved to {file_path}")
        return {"success": True, "file_path": os.path.abspath(file_path)}

    except Exception as e:
        logger.error(f"File upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

def get_backup_file(file_path: str) -> FileResponse:
    try:
        if not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type="application/octet-stream"
        )
    except Exception as e:
        logger.error(f"Error while sending backup file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error returning file: {str(e)}")
