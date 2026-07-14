from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # LLM
    anthropic_api_key: str
    llama_cloud_api_key: str = ""

    # ChromaDB
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_name: str = "docuforge_chunks"

    # Job store
    job_db_path: str = "./jobs.db"

    # Chunking
    child_chunk_size: int = 250
    parent_chunk_size: int = 1500
    retrieval_top_k: int = 6

    # Generation
    max_retries_per_section: int = 3
    model_name: str = "claude-sonnet-4-6"

    # Rate limiting (per client IP, in-memory — single-instance only)
    ingest_rate_limit_per_minute: int = 20
    generate_rate_limit_per_minute: int = 5

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
