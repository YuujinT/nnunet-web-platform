"""应用配置"""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 基础配置
    APP_NAME: str = "nnU-Net Web Platform"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # 路径配置
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    PREDICTION_DIR: Path = DATA_DIR / "predictions"
    GROUND_TRUTH_DIR: Path = DATA_DIR / "ground_truth"
    MODEL_DIR: Path = BASE_DIR / "models"

    # nnU-Net 配置
    NNUNET_RAW: Path = DATA_DIR / "nnunet_raw"
    NNUNET_PREPROCESSED: Path = DATA_DIR / "nnunet_preprocessed"
    NNUNET_RESULTS: Path = DATA_DIR / "nnunet_results"

    # nnU-Net 推理配置（CLI 子进程模式）
    NNUNET_DEFAULT_FOLD: int = 0
    NNUNET_NPP: int = 1
    NNUNET_NPS: int = 1
    NNUNET_PERFORM_EVERYTHING_ON_DEVICE: bool = False

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8080

    # CORS 配置（生产环境应设置具体域名）
    CORS_ORIGINS: list = ["*"]

    # 文件限制
    MAX_FILE_SIZE: int = 500 * 1024 * 1024  # 500MB
    ALLOWED_EXTENSIONS: set = {".nii.gz", ".nii", ".dcm", ".zip"}

    # Uvicorn 日志配置（默认仅 warning/error）
    UVICORN_LOG_LEVEL: str = "warning"
    UVICORN_ACCESS_LOG: bool = False

    class Config:
        env_file = ".env"


settings = Settings()

# 确保目录存在
for path in [settings.UPLOAD_DIR, settings.PREDICTION_DIR,
             settings.GROUND_TRUTH_DIR, settings.NNUNET_RAW,
             settings.NNUNET_PREPROCESSED, settings.NNUNET_RESULTS]:
    path.mkdir(parents=True, exist_ok=True)