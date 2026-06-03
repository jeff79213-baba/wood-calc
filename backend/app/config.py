from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    app_name: str = "Interior Material Swap API"
    debug: bool = True

    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/interior_mat"
    redis_url: str = "redis://localhost:6379/0"

    upload_dir_materials: str = "uploads/materials"
    upload_dir_rooms: str = "uploads/rooms"
    upload_dir_results: str = "uploads/results"

    sam_model_type: Literal["vit_h", "vit_l", "vit_b"] = "vit_b"
    sam_checkpoint: str = "models/sam_vit_b_01ec64.pth"
    device: str = "cpu"

    max_image_size: int = 2048
    segmentation_confidence: float = 0.5

    class Config:
        env_file = ".env"


settings = Settings()
