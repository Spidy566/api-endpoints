"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Backup storage and retrieval             | 13-06-2025 | senthil
---------------------------------------------------------------------------
"""
from pathlib import Path
from fastapi import UploadFile, HTTPException
from fastapi.responses import FileResponse

from core.config import logger, BACKUP_DIR


def save_backup_file(file: UploadFile) -> dict:
    """
    Saves an uploaded file to the configured BACKUP_DIR.
    Returns a dict matching the BackupUploadResponse schema.
    """
    if not file.filename or not file.filename.strip():
        raise HTTPException(status_code=400, detail="No filename provided in upload.")
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        filename = Path(file.filename).name
        if not filename:
            raise HTTPException(status_code=400, detail="Invalid filename.")

        file_path = BACKUP_DIR / filename

        if file_path.is_dir():
            raise HTTPException(status_code=400,detail=f"Cannot save file: A directory named '{filename}' already exists.")

        with open(file_path, "wb") as buffer:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                buffer.write(chunk)

        logger.info(f"Backup file saved: {file_path}")

        return {
            "success": True,
            "file_path": str(file_path.absolute()),
            "filename": filename
        }

    except PermissionError:
        logger.error(f"Permission denied writing to {BACKUP_DIR}")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: Write permission denied for backup directory."
        )
    except OSError as e:
        logger.error(f"OS Error: {e}")
        raise HTTPException(status_code=500, detail=f"File system error: {e.strerror}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backup upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected upload failure: {str(e)}")


def get_backup_file(file_path_str: str) -> FileResponse:
    """
    Retrieves a file from the disk.
    """
    try:
        path_obj = Path(file_path_str)

        if not path_obj.is_file():
            possible_path = BACKUP_DIR / file_path_str
            if possible_path.is_file():
                path_obj = possible_path
            else:
                raise HTTPException(status_code=404, detail=f"File not found: {file_path_str}")

        return FileResponse(
            path=path_obj,
            filename=path_obj.name,
            media_type="application/octet-stream"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving backup file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error returning file: {str(e)}")
