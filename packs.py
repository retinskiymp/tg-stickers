import random

from telegram import Bot, Sticker
from telegram.error import BadRequest, TelegramError

from catalogs import harvest_pack_names
from config import (
    EXCLUDED_TITLE_WORDS,
    PACK_PICK_ATTEMPTS,
    POPULAR_PACKS_LIMIT,
    SPICY_PACKS_LIMIT,
)
from db import (
    add_packs,
    count_alive_packs,
    mark_pack_dead,
    mark_pack_used,
    pick_random_pack_name,
)
from kinds import PostingKind


async def harvest_pool(kind: PostingKind) -> tuple[int, int]:
    """Re-read the top packs of every catalogue and store the new ones.

    The spicy listings are read first so their names can be withheld from the safe
    pool: plenty of meme and 18+ packs also rank high in the general listing. The
    two pools only label where a pack came from — picking ignores the label.
    """
    spicy_names = await harvest_pack_names(kind.spicy_catalogs, SPICY_PACKS_LIMIT)
    spicy_names += await harvest_pack_names(kind.anime_catalogs, SPICY_PACKS_LIMIT)
    spicy_added = add_packs(kind, spicy_names, spicy=True)
    spicy = set(spicy_names)
    safe_names = await harvest_pack_names(kind.catalogs, POPULAR_PACKS_LIMIT)
    safe_added = add_packs(kind, [name for name in safe_names if name not in spicy])
    return safe_added, spicy_added


ExcludedTitleWords = tuple(word.lower() for word in EXCLUDED_TITLE_WORDS)


def is_wanted_title(title: str | None) -> bool:
    """Titles are free text, so an excluded word counts anywhere inside one."""
    lowered = (title or "").lower()
    return not any(word in lowered for word in ExcludedTitleWords)


async def fetch_pack_sticker(bot: Bot, kind: PostingKind, name: str) -> Sticker | None:
    try:
        sticker_set = await bot.get_sticker_set(name)
    except BadRequest:
        mark_pack_dead(kind, name)
        return None
    except TelegramError:
        return None
    if not sticker_set.stickers or sticker_set.sticker_type != kind.sticker_type:
        mark_pack_dead(kind, name)
        return None
    # The live title is the only place a promo rename shows up; catalogues keep
    # whatever the title was when they last parsed the pack.
    if not is_wanted_title(sticker_set.title):
        mark_pack_dead(kind, name)
        return None
    mark_pack_used(kind, name, sticker_set.title, len(sticker_set.stickers))
    return random.choice(sticker_set.stickers)


async def pick_random_sticker(bot: Bot, kind: PostingKind) -> Sticker | None:
    """Any live pack, uniformly — popular and spicy share one pool here."""
    if not count_alive_packs(kind):
        await harvest_pool(kind)
    for _ in range(PACK_PICK_ATTEMPTS):
        name = pick_random_pack_name(kind)
        if not name:
            return None
        sticker = await fetch_pack_sticker(bot, kind, name)
        if sticker:
            return sticker
    return None


# async def remember_custom_emoji_packs(
#     bot: Bot, kind: PostingKind, custom_emoji_ids: list[str]
# ) -> list[str]:
#     if not custom_emoji_ids:
#         return []
#     try:
#         stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids)
#     except TelegramError:
#         return []
#     return [
#         sticker.set_name
#         for sticker in stickers
#         if sticker.set_name and remember_pack(kind, sticker.set_name)
#     ]
