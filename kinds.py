from dataclasses import dataclass

from telegram.constants import StickerType

from catalogs import AnimeStickerCatalogs, SpicyStickerCatalogs, StickerCatalogs
from config import DEFAULT_INTERVAL_MINUTES, ENABLED_BY_DEFAULT, MIN_INTERVAL_MINUTES
from models import ChatPostingState, ChatSettingsModel, StickerPackModel


@dataclass(frozen=True)
class PostingKind:
    key: str
    noun: str
    plural_noun: str
    pack_noun: str
    pack_model: type
    sticker_type: str
    catalogs: tuple
    spicy_catalogs: tuple
    anime_catalogs: tuple
    default_interval_minutes: int
    enabled_by_default: bool
    send_as_upload: bool

    def state(self, settings: ChatSettingsModel) -> ChatPostingState:
        return ChatPostingState(settings, self.key)

    def starting_interval_minutes(self) -> int:
        return max(self.default_interval_minutes, MIN_INTERVAL_MINUTES)


StickerKind = PostingKind(
    key="sticker",
    noun="стикер",
    plural_noun="стикеры",
    pack_noun="набор",
    pack_model=StickerPackModel,
    sticker_type=StickerType.REGULAR,
    catalogs=StickerCatalogs,
    spicy_catalogs=SpicyStickerCatalogs,
    anime_catalogs=AnimeStickerCatalogs,
    default_interval_minutes=DEFAULT_INTERVAL_MINUTES,
    enabled_by_default=ENABLED_BY_DEFAULT,
    send_as_upload=False,
)

# EmojiKind = PostingKind(
#     key="emoji",
#     noun="emoji",
#     plural_noun="emoji",
#     article="an",
#     pack_noun="emoji pack",
#     pack_model=EmojiPackModel,
#     sticker_type=StickerType.CUSTOM_EMOJI,
#     catalogs=EmojiCatalogs,
#     link_path="addemoji",
#     link_pattern=pack_link_pattern("addemoji"),
#     default_interval_minutes=EMOJI_DEFAULT_INTERVAL_MINUTES,
#     enabled_by_default=EMOJI_ENABLED_BY_DEFAULT,
#     min_pool_packs=EMOJI_MIN_POOL_PACKS,
#     discover=DISCOVER_EMOJI_PACKS,
#     send_as_upload=True,
# )

Kinds = (StickerKind,)
