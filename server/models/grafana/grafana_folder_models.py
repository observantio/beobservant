"""Grafana folder model (split from grafana_models.py)."""
from typing import Optional
from pydantic import BaseModel, Field


class Folder(BaseModel):
    """Grafana folder."""
    id: Optional[int] = Field(None, description="Unique identifier for the folder")
    uid: Optional[str] = Field(None, description="Unique identifier string for the folder")
    title: str = Field(..., description="Title of the folder")
    
    class Config:
        populate_by_name = True
