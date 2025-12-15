import json
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

def configure_openapi(app: FastAPI, title: str, version: str, desc: str, tags: list):
    """Generates OpenAPI schema and cleans up ugly schema names."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=title,
        version=version,
        description=desc,
        routes=app.routes,
        tags=tags,
    )

    openapi_schema["info"]["x-logo"] = {
        "url": "/static/Fresa-Tech-logo.png",
        "backgroundColor": "#FFFFFF",
        "altText": "Fresa Logo",
        "href": "https://fresatechnologies.com/"
    }

    for _, methods in openapi_schema["paths"].items():
        for _, content in methods.items():
            if "responses" in content and "422" in content["responses"]:
                del content["responses"]["422"]

    body_renames = {
        "Body_scan_visiting_card_scan_vc_post": "AIVisitingCardUploadRequest",
        "Body_extract_manifest_manifest_extract_post": "AWSManifestUploadRequest",
        "Body_extract_attachments_extract_email_attachments_post": "EmailFileUploadRequest",
        "Body_upload_backup_file_backup_post": "BackupUploadRequest",
        "Body_upload_certificate_upload_certificate_post": "SignCertUploadRequest"
    }

    schema_str = json.dumps(openapi_schema)

    for ugly_name, clean_name in body_renames.items():
        schema_str = schema_str.replace(f'"{ugly_name}"', f'"{clean_name}"')
        schema_str = schema_str.replace(f"#/components/schemas/{ugly_name}", f"#/components/schemas/{clean_name}")

    openapi_schema = json.loads(schema_str)

    if "components" in openapi_schema and "schemas" in openapi_schema["components"]:
        current_schemas = openapi_schema["components"]["schemas"]
        sorted_schemas = dict(sorted(current_schemas.items()))
        openapi_schema["components"]["schemas"] = sorted_schemas

    app.openapi_schema = openapi_schema
    return app.openapi_schema