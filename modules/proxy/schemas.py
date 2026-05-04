"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Schemas for Generic API Proxy            | 29-04-2026 | vishal
---------------------------------------------------------------------------
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class ProxyAuthConfig(BaseModel):
    auth_type: str = Field(..., description="Type of auth: 'none', 'basic', 'bearer', or 'fasahpay'")

    username: Optional[str] = Field(None, description="Username for Basic or FasahPay auth")
    password: Optional[str] = Field(None, description="Password for Basic or FasahPay auth")
    token: Optional[str] = Field(None, description="Static token for Bearer auth")

    client_id: Optional[str] = Field(None, description="X-Tabadul-Client-Id")
    client_secret: Optional[str] = Field(None, description="X-Tabadul-Client-Secret")
    auth_url: Optional[str] = Field(None, description="URL to fetch the token (e.g., OAuth2 URL)")


class GenericProxyRequest(BaseModel):
    target_url: str = Field(..., description="The full URL of the third-party API endpoint")
    http_method: str = Field(default="POST", description="GET, POST, PUT, DELETE, etc.")
    auth: ProxyAuthConfig = Field(..., description="Authentication configuration")
    headers: Optional[Dict[str, str]] = Field(default_factory=dict, description="Custom headers to pass")
    query_params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="URL Query parameters")
    payload: Optional[Dict[str, Any]] = Field(default=None, description="The JSON body to send to the third party")