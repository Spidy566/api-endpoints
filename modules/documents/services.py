import io
import os
import uuid
import base64
import signal
import subprocess
import tempfile
from PIL import Image
from pypdf import PdfWriter, PdfReader
from docxtpl import DocxTemplate

from core.config import logger


def generate_docx(template_bytes: bytes, context: dict) -> bytes:
    try:
        tpl = DocxTemplate(io.BytesIO(template_bytes))
        tpl.render(context, autoescape=True)
        final_docx_buffer = io.BytesIO()
        tpl.save(final_docx_buffer)
        return final_docx_buffer.getvalue()
    except Exception as e:
        raise RuntimeError(
            f"Template Error: Unable to render document. Please check your template tags. Details: {str(e)}")


def convert_docx_to_pdf_unoconv(docx_data: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as temp_dir:
        file_id = uuid.uuid4()
        temp_docx_path = os.path.join(temp_dir, f"{file_id}.docx")
        expected_pdf_path = os.path.join(temp_dir, f"{file_id}.pdf")
        proc = None

        with open(temp_docx_path, "wb") as f:
            f.write(docx_data)

        command = [
            "/usr/bin/python3",
            "/usr/bin/unoconv",
            "--format", "pdf",
            "-o", expected_pdf_path,
            temp_docx_path
        ]

        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid
        )

        try:
            stdout, stderr = proc.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            print(f"  -> unoconv timed out for {temp_docx_path}. Killing process group {proc.pid}...")
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait()
            raise RuntimeError("unoconv conversion timed out after 5 minutes.")

        if proc.returncode != 0:
            error_message = f"unoconv failed with exit code {proc.returncode}.\nStderr: {stderr.decode()}\nStdout: {stdout.decode()}"
            raise RuntimeError(error_message)

        if not os.path.exists(expected_pdf_path):
            raise FileNotFoundError(f"PDF file was not created by unoconv at {expected_pdf_path}.")

        with open(expected_pdf_path, "rb") as f:
            return f.read()

def convert_image_to_pdf(image_bytes: bytes) -> io.BytesIO:
    """Convert image bytes to a single-page PDF."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    pdf_bytes = io.BytesIO()
    image.save(pdf_bytes, format="PDF")
    pdf_bytes.seek(0)
    return pdf_bytes

def merge_files_logic(files: list[dict]) -> dict:
    try:
        pdf_writer = PdfWriter()
        temp_pdfs = []
        os.makedirs("output", exist_ok=True)

        supported_image_types = ["image/jpeg", "image/jpg", "image/png"]
        supported_pdf_type = "application/pdf"

        for file_info in files:
            filename = file_info.get("filename", "file")
            mimetype = file_info.get("mimetype", "")
            base64content = file_info.get("base64content", "")

            if not base64content:
                raise ValueError(f"Missing base64content for {filename}")

            try:
                file_bytes = base64.b64decode(base64content.strip().split(",")[-1])
            except Exception:
                raise ValueError(f"Invalid base64 data in {filename}")

            fd, temp_pdf_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)

            if mimetype == supported_pdf_type or file_bytes[:4] == b"%PDF":
                with open(temp_pdf_path, "wb") as f:
                    f.write(file_bytes)

            elif mimetype.lower() in supported_image_types:
                try:
                    image_pdf = convert_image_to_pdf(file_bytes)
                    with open(temp_pdf_path, "wb") as f:
                        f.write(image_pdf.read())
                except Exception as e:
                    raise ValueError(f"Invalid image format in {filename}: {str(e)}")

            else:
                raise ValueError(f"Unsupported file type '{mimetype}' for file '{filename}'.")

            temp_pdfs.append(temp_pdf_path)

        for pdf_path in temp_pdfs:
            with open(pdf_path, "rb") as pdf_file:
                reader = PdfReader(pdf_file)
                for page in reader.pages:
                    pdf_writer.add_page(page)

        output_pdf = io.BytesIO()
        pdf_writer.write(output_pdf)
        output_pdf.seek(0)

        merged_base64 = base64.b64encode(output_pdf.getvalue()).decode("utf-8")

        return {
            "outputfilename": "merged_output.pdf",
            "outputmimetype": "application/pdf",
            "outputbase64content": merged_base64
        }

    finally:
        for temp_file in temp_pdfs:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                pass