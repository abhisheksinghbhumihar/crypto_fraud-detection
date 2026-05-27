# fraud_detection_api/app/utils/logger.py
import logging

logger = logging.getLogger("fraud_detection")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)