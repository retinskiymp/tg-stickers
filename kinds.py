import re
from dataclasses import dataclass

from telegram.constants import StickerType

from catalogs import EmojiCatalogs, StickerCatalogs
from config import (
    DEFAULT_INTERVAL_MINUTES,
    DISCOVER_EMOJI_PACKS,
    DISCOVER_PACKS,
    EMOJI_DEFAULT_INTERVAL_MINUTES,
    EMOJI_ENABLED_BY_DEFAULT,
    EMOJI_MIN_POOL_PACKS,
    ENABLED_BY_DEFAULT,
    MIN_INTERVAL_MINUTES,
    MIN_POOL_PACKS,
)
from models import ChatPostingState, ChatSettingsModel, EmojiPackModel, StickerPackModel

PackNamePattern = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def pack_link_pattern(link_path: str) -> re.Pattern:
    return re.compile(
        rf"(?:https?://)?(?:t|telegram)\.me/{link_path}/([A-Za-z0-9_]+)", re.IGNORECASE
    )


@dataclass(frozen=True)
class PostingKind:
    key: str
    noun: str
    plural_noun: str
    article: str
    pack_noun: str
    pack_model: type
    sticker_type: str
    catalogs: tuple
    link_path: str
    link_pattern: re.Pattern
    default_interval_minutes: int
    enabled_by_default: bool
    min_pool_packs: int
    discover: bool

    def state(self, settings: ChatSettingsModel) -> ChatPostingState:
        return ChatPostingState(settings, self.key)

    def starting_interval_minutes(self) -> int:
        return max(self.default_interval_minutes, MIN_INTERVAL_MINUTES)


StickerKind = PostingKind(
    key="sticker",
    noun="sticker",
    plural_noun="stickers",
    article="a",
    pack_noun="sticker pack",
    pack_model=StickerPackModel,
    sticker_type=StickerType.REGULAR,
    catalogs=StickerCatalogs,
    link_path="addstickers",
    link_pattern=pack_link_pattern("addstickers"),
    default_interval_minutes=DEFAULT_INTERVAL_MINUTES,
    enabled_by_default=ENABLED_BY_DEFAULT,
    min_pool_packs=MIN_POOL_PACKS,
    discover=DISCOVER_PACKS,
)

EmojiKind = PostingKind(
    key="emoji",
    noun="emoji",
    plural_noun="emoji",
    article="an",
    pack_noun="emoji pack",
    pack_model=EmojiPackModel,
    sticker_type=StickerType.CUSTOM_EMOJI,
    catalogs=EmojiCatalogs,
    link_path="addemoji",
    link_pattern=pack_link_pattern("addemoji"),
    default_interval_minutes=EMOJI_DEFAULT_INTERVAL_MINUTES,
    enabled_by_default=EMOJI_ENABLED_BY_DEFAULT,
    min_pool_packs=EMOJI_MIN_POOL_PACKS,
    discover=DISCOVER_EMOJI_PACKS,
)

Kinds = (StickerKind, EmojiKind)
