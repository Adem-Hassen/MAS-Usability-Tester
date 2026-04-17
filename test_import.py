import sys
import logging
from pathlib import Path

# Setup simple logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_import")

logger.info("Starting test_import.py")
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))
logger.info(f"sys.path: {sys.path}")

try:
    logger.info("Importing core.graph...")
    from core.graph import run_evaluation
    logger.info("Importing config.settings...")
    from config.settings import settings
    logger.info("MAS_AVAILABLE = True")
except Exception as e:
    logger.error(f"Failed to load MAS core: {e}")
    import traceback
    logger.error(traceback.format_exc())

logger.info("Done.")
