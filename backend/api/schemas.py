from enum import Enum
from pydantic import BaseModel
from typing import Optional


class ArtifactType(str, Enum):
    BRD = "BRD"
    FSD = "FSD"
    TSD = "TSD"


class GenerateRequest(BaseModel):
    artifact_type: ArtifactType
    job_id: Optional[str] = None   # Optional: client-supplied idempotency key


class GenerateResponse(BaseModel):
    job_id: str
    status: str                     # "queued" | "running" | "done" | "error"
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    artifact_type: str
    sections_complete: int
    total_sections: int
    events: list[str]
    final_document: Optional[str] = None
    error: Optional[str] = None


class IngestionResponse(BaseModel):
    filename: str
    chunks_created: int
    parent_chunks: int
    child_chunks: int
    inferred_target: str


class StatsResponse(BaseModel):
    child_chunks: int
    parent_chunks: int
