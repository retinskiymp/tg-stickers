import os
from pathlib import Path

from dotenv import load_dotenv

BaseDir = Path(__file__).resolve().parent
# Identity lives apart from the tunables, so rewriting .env never touches the
# token or the admin list. Loaded first: load_dotenv never overrides what is
# already set, so .env.main wins if a key appears in both.
MainEnvFile = BaseDir / ".env.main"
SettingsEnvFile = BaseDir / ".env"

load_dotenv(MainEnvFile)
load_dotenv(SettingsEnvFile)


def read_admin_ids(raw: str) -> frozenset[int]:
    return frozenset(
        int(part) for part in raw.replace(";", ",").split(",") if part.strip().lstrip("-").isdigit()
    )


# From .env.main
TOKEN: str = os.getenv("BOT_TOKEN")
ADMIN_IDS: frozenset[int] = read_admin_ids(os.getenv("ADMIN_IDS", ""))

# From .env
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
HARVEST_INTERVAL_MINUTES: int = int(os.getenv("HARVEST_INTERVAL_MINUTES", "1440"))
POPULAR_PACKS_LIMIT: int = int(os.getenv("POPULAR_PACKS_LIMIT", "300"))
SPICY_PACKS_LIMIT: int = int(os.getenv("SPICY_PACKS_LIMIT", "1000"))
def read_list(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


# "entertainment" is the site's "Юмор и Развлечения" category — the widest meme
# source there is, since its search only matches pack names.
SPICY_CATEGORIES: tuple[str, ...] = read_list(
    os.getenv("SPICY_CATEGORIES", "adult,entertainment")
)
SPICY_SEARCH_TERMS: tuple[str, ...] = read_list(
    os.getenv("SPICY_SEARCH_TERMS", "мат,meme,funny,жиза,пошлые")
)
# Anime has no category of its own, so it is searched instead.
ANIME_SEARCH_TERMS: tuple[str, ...] = read_list(
    os.getenv("ANIME_SEARCH_TERMS", "anime,neko,chibi,kawaii,waifu")
)
TLGRM_HOST: str = os.getenv("TLGRM_HOST", "tlgrm.ru")
TGLIST_HOST: str = os.getenv("TGLIST_HOST", "tglist.info")
HTTP_TIMEOUT_SECONDS: float = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
ADMIN_ONLY_SETTINGS: bool = os.getenv("ADMIN_ONLY_SETTINGS", "1") == "1"
