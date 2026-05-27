# fraud_detection_api/app/core/config.py
import os
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Pydantic v2 uses pydantic_settings
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings

# ============================================================
# PROJECT PATHS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
EVIDENCE_DIR = BASE_DIR / "evidence_store"
MODELS_DIR = BASE_DIR / "models"

# Create directories if they don't exist
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# SETTINGS CLASS
# ============================================================
class Settings(BaseSettings):
    # API Settings
    api_title: str = "Fraud Detection API"
    api_version: str = "1.0.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8004
    api_reload: bool = False
    api_log_level: str = "info"
    
    # Database
    database_url: str = f"sqlite:///{BASE_DIR}/fraud_detection_finance.db"
    db_path: str = str(BASE_DIR / "fraud_detection_finance.db")
    
    # CORS
    cors_origins: list = ["*"]
    cors_credentials: bool = True
    cors_methods: list = ["*"]
    cors_headers_list: list = ["*"]
    
    # Fraud Detection
    fraud_threshold: float = 0.8
    high_risk_threshold: float = 0.7
    medium_risk_threshold: float = 0.3
    amount_base: float = 1200.0
    
    # Supabase
    use_supabase: bool = False
    supabase_url: str = ""
    supabase_key: str = ""
    
    # Blockchain
    polygon_rpc: str = "https://polygon-rpc.com"
    contract_address: str = ""
    private_key: str = ""
    
    # Evidence Storage
    evidence_store_path: str = str(EVIDENCE_DIR)
    
    # ML Model
    model_path: str = str(MODELS_DIR / "fraud_model.pkl")
    scaler_path: str = str(MODELS_DIR / "scaler.pkl")
    features_path: str = str(MODELS_DIR / "features.pkl")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def get_settings() -> dict:
    """Return all settings as dictionary"""
    return {
        "api_title": settings.api_title,
        "api_version": settings.api_version,
        "api_port": settings.api_port,
        "fraud_threshold": settings.fraud_threshold,
        "evidence_store": settings.evidence_store_path,
        "database_url": settings.database_url,
        "log_level": settings.api_log_level
    }


def validate_config() -> bool:
    """Validate critical configuration"""
    errors = []
    
    # Check if evidence directory is writable
    if not os.access(settings.evidence_store_path, os.W_OK):
        errors.append(f"Evidence directory not writable: {settings.evidence_store_path}")
    
    # Check model files if they should exist
    if os.path.exists(settings.model_path):
        if not os.access(settings.model_path, os.R_OK):
            errors.append(f"Model file not readable: {settings.model_path}")
    
    if errors:
        for error in errors:
            print(f"⚠️ Config Warning: {error}")
        return False
    
    return True


# ============================================================
# PRINT CONFIGURATION ON LOAD
# ============================================================
if __name__ != "__main__":
    print(f"[OK] Config loaded: {settings.api_title} v{settings.api_version}")
    print(f"   Evidence store: {settings.evidence_store_path}")
    print(f"   API will run on port: {settings.api_port}")