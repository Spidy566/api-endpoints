"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Added list-based targeted deletion logic | 27-02-2026 | vishal
Implemented Paramiko SFTP client logic   | 17-02-2026 | vishal
Implemented folder download and delete   | 17-02-2026 | vishal
---------------------------------------------------------------------------
"""
import io
import base64
import paramiko
import stat
from typing import Dict, Any
from fastapi import HTTPException
from modules.sftp import schemas
from core.config import logger


def upload_to_sftp(payload: schemas.SftpUploadRequest) -> Dict[str, Any]:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sftp = None
    file_obj = None

    try:
        try:
            file_data = base64.b64decode(payload.content)
            file_obj = io.BytesIO(file_data)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Base64 string in 'content' field.")

        try:
            ssh.connect(
                hostname=payload.host,
                port=payload.port,
                username=payload.username,
                password=payload.password,
                timeout=60
            )
            sftp = ssh.open_sftp()
        except paramiko.AuthenticationException:
            raise HTTPException(status_code=401, detail="SFTP Authentication Failed.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"SFTP Connection Error: {str(e)}")

        try:
            sftp.chdir(payload.remote_dir)
        except IOError:
            raise HTTPException(status_code=404, detail=f"Remote directory '{payload.remote_dir}' not found.")

        sftp.putfo(file_obj, payload.filename)

        return {
            "status": "success",
            "message": f"File uploaded to {payload.remote_dir}/{payload.filename}",
            "size_bytes": len(file_data)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SFTP Upload Failure: {e}")
        raise HTTPException(status_code=500, detail=f"SFTP Upload Error: {str(e)}")
    finally:
        if sftp: sftp.close()
        if ssh: ssh.close()
        if file_obj: file_obj.close()


def download_folder_from_sftp(payload: schemas.SftpDownloadRequest) -> Dict[str, Any]:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sftp = None

    try:
        try:
            ssh.connect(
                hostname=payload.host,
                port=payload.port,
                username=payload.username,
                password=payload.password,
                timeout=60
            )
            sftp = ssh.open_sftp()
        except paramiko.AuthenticationException:
            raise HTTPException(status_code=401, detail="SFTP Authentication Failed.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"SFTP Connection Error: {str(e)}")

        remote_dir = payload.remote_dir.rstrip("/")
        try:
            sftp.chdir(remote_dir)
        except Exception:
            raise HTTPException(status_code=404, detail=f"Remote directory not found: {payload.remote_dir}")

        entries = sftp.listdir_attr(remote_dir)

        files_to_delete = set(payload.filenames)
        files_out = []
        deleted_out = []

        for ent in entries:
            name = ent.filename
            remote_path = f"{remote_dir}/{name}"

            if stat.S_ISDIR(ent.st_mode):
                continue

            if name in files_to_delete:
                try:
                    sftp.remove(remote_path)
                    deleted_out.append({"filename": name, "status": "deleted"})
                except Exception as e:
                    logger.error(f"Failed to delete {name} from SFTP: {e}")
                    deleted_out.append({"filename": name, "status": "error"})
                files_to_delete.remove(name)
            else:
                file_obj = io.BytesIO()
                try:
                    sftp.getfo(remote_path, file_obj)
                    file_bytes = file_obj.getvalue()
                    encoded = base64.b64encode(file_bytes).decode("utf-8")

                    files_out.append({
                        "filename": name,
                        "status": "success",
                        "size_bytes": len(file_bytes),
                        "content_base64": encoded,
                    })
                except Exception as e:
                    files_out.append({"filename": name, "status": "error", "error": str(e)})

        for missing_file in files_to_delete:
            deleted_out.append({"filename": missing_file, "status": "not found"})

        return {
            "status": "success",
            "remote_dir": remote_dir,
            "deleted_summary": deleted_out,
            "downloaded_count": len([f for f in files_out if f.get("status") == "success"]),
            "files": files_out
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SFTP Download Failure: {e}")
        raise HTTPException(status_code=500, detail=f"SFTP Error: {str(e)}")
    finally:
        if sftp: sftp.close()
        if ssh: ssh.close()