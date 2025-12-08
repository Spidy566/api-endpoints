from fastapi import APIRouter, UploadFile, File
from modules.backup import schemas, services

router = APIRouter()

@router.post("/backup")
async def upload_backup_file(file: UploadFile = File(...)):
    saved_path = services.save_backup_file(file)
    return {"success": True, "file_path": saved_path}


@router.post("/getbackup")
async def get_backup_file(req: schemas.BackupRequest):
    return services.get_backup_file(req.file_path)