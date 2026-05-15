"""Local processor configuration."""

import os
from pathlib import Path

# ====================================
# Paths
# ====================================
DOWNLOAD_ROOT = Path(r"D:\搬运\01原素材带字幕")
INDEX_DIR     = Path(r"D:\搬运\_索引")
STATE_FILE    = Path(r"D:\搬运\_state.json")
LOG_FILE      = Path(r"D:\搬运\_log.txt")

# ====================================
# Bitable (Feishu) — pulled from monitor's GitHub secrets
# ====================================
FEISHU_APP_ID          = os.getenv("FEISHU_APP_ID",     "cli_aa89d73308745cc7")
FEISHU_APP_SECRET      = os.getenv("FEISHU_APP_SECRET", "NV8IPMNolrnrWrJKBpCFkhw8kfqxh2pT")
BITABLE_APP_TOKEN      = os.getenv("BITABLE_APP_TOKEN", "KJntbLfXIa0ZEGsxaHacuLSVnHb")
BITABLE_VIDEOS_TABLE   = os.getenv("BITABLE_VIDEOS_TABLE",   "tblrY6LqfrQsc1qv")
BITABLE_CREATORS_TABLE = os.getenv("BITABLE_CREATORS_TABLE", "tbl7L9IRcsfPAk1k")

# ====================================
# Gemini API
# ====================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyCHYrLlTDPGchbT72zJepKjpUv5gPd9kiI")
GEMINI_MODEL   = "gemini-2.5-flash"
GEMINI_MODEL_FALLBACK = "gemini-2.5-flash-lite"
GEMINI_MAX_RETRIES = 4
GEMINI_RETRY_BACKOFF_SEC = 8

# ====================================
# Whisper (faster-whisper, GPU-accelerated)
# ====================================
WHISPER_MODEL  = "large-v3"        # 3090Ti can handle large-v3 easily
WHISPER_DEVICE = "cuda"            # change to "cpu" if no GPU
WHISPER_COMPUTE_TYPE = "float16"   # float16 on GPU; int8 on CPU

# ====================================
# Processing limits
# ====================================
MAX_VIDEOS_PER_RUN = 80            # safety cap
SKIP_LONGER_THAN_SECONDS = 600     # skip 10+ min videos (rare on TikTok)
DOWNLOAD_TIMEOUT_SEC = 120
TRANSCRIBE_LANGUAGE = None         # auto-detect
