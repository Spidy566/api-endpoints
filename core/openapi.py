from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

def configure_openapi(app: FastAPI, title: str, version: str, desc: str, tags: list):
    """Generates the OpenAPI schema but removes the automatic '422 Validation Error' responses from the documentation."""
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

    app.openapi_schema = openapi_schema
    return app.openapi_schema