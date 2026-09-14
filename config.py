import os
from dotenv import load_dotenv

load_dotenv()


def read_admin_ids(raw: str) -> frozenset[int]:
    return frozenset(
        int(part) for part in raw.replace(";", ",").split(",") if part.strip().lstrip("-").isdigit()
    )


TOKEN: str = os.getenv("BOT_TOKEN")
DB_URL: str = os.getenv("DB_URL", "sqlite:////app/db/stickers.db")

DEFAULT_INTERVAL_MINUTES: int = int(os.getenv("DEFAULT_INTERVAL_MINUTES", "240"))
MIN_INTERVAL_MINUTES: int = int(os.getenv("MIN_INTERVAL_MINUTES", "10"))
MAX_INTERVAL_MINUTES: int = int(os.getenv("MAX_INTERVAL_MINUTES", "10080"))
ENABLED_BY_DEFAULT: bool = os.getenv("ENABLED_BY_DEFAULT", "1") == "1"

# EMOJI_DEFAULT_INTERVAL_MINUTES: int = int(
#     os.getenv("EMOJI_DEFAULT_INTERVAL_MINUTES", str(DEFAULT_INTERVAL_MINUTES))
# )
# EMOJI_ENABLED_BY_DEFAULT: bool = os.getenv("EMOJI_ENABLED_BY_DEFAULT", "0") == "1"
# EMOJI_MIN_POOL_PACKS: int = int(os.getenv("EMOJI_MIN_POOL_PACKS", "150"))
# DISCOVER_EMOJI_PACKS: bool = os.getenv("DISCOVER_EMOJI_PACKS", "1") == "1"

PACK_PICK_ATTEMPTS: int = int(os.getenv("PACK_PICK_ATTEMPTS", "8"))
HARVEST_INTERVAL_MINUTES: int = int(os.getenv("HARVEST_INTERVAL_MINUTES", "60"))
HARVEST_REQUESTS_PER_CATALOG: int = int(os.getenv("HARVEST_REQUESTS_PER_CATALOG", "5"))
MIN_POOL_PACKS: int = int(os.getenv("MIN_POOL_PACKS", "300"))
HTTP_TIMEOUT_SECONDS: float = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
DISCOVER_PACKS: bool = os.getenv("DISCOVER_PACKS", "1") == "1"
ADMIN_ONLY_SETTINGS: bool = os.getenv("ADMIN_ONLY_SETTINGS", "1") == "1"
ADMIN_IDS: frozenset[int] = read_admin_ids(os.getenv("ADMIN_IDS", ""))
