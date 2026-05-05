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
    auth_type: str = Field(default="none", description="'none', 'basic', or 'bearer'")
    username: Optional[str] = Field(None, description="Used for Basic Auth")
    password: Optional[str] = Field(None, description="Used for Basic Auth")
    token: Optional[str] = Field(None, description="Used for Bearer Auth")

class GenericProxyRequest(BaseModel):
    target_url: str = Field(..., description="The full URL of the third-party API endpoint")
    http_method: str = Field(default="POST", description="GET, POST, PUT, DELETE, etc.")
    auth: ProxyAuthConfig = Field(default_factory=ProxyAuthConfig, description="Optional auth helpers")
    headers: Optional[Dict[str, str]] = Field(default_factory=dict, description="Custom headers to pass")
    query_params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="URL Query parameters")
    payload: Optional[Dict[str, Any]] = Field(default=None, description="The JSON body to send")