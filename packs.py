import random

from telegram import Bot, Sticker
from telegram.error import BadRequest, TelegramError

from catalogs import harvest_pack_names
from config import HARVEST_REQUESTS_PER_CATALOG, PACK_PICK_ATTEMPTS
from db import (
    add_pack,
    add_packs,
    count_alive_packs,
    mark_pack_dead,
    mark_pack_used,
    pick_random_pack_name,
)
from kinds import PackNamePattern, PostingKind

EnsurePoolRounds = 8


def parse_pack_name(kind: PostingKind, text: str) -> str | None:
    text = text.strip()
    link_match = kind.link_pattern.search(text)
    if link_match:
        return link_match.group(1)
    if PackNamePattern.match(text):
        return text
    return None


def remember_pack(kind: PostingKind, name: str | None, title: str | None = None) -> bool:
    if not name:
        return False
    return add_pack(kind, name, title)


async def harvest_pool(kind: PostingKind) -> int:
    names = await harvest_pack_names(kind.catalogs, HARVEST_REQUESTS_PER_CATALOG)
    return add_packs(kind, names)


async def ensure_pool(kind: PostingKind) -> int:
    added = 0
    for _ in range(EnsurePoolRounds):
        if count_alive_packs(kind) >= kind.min_pool_packs:
            break
        harvested = await harvest_pool(kind)
        if not harvested:
            break
        added += harvested
    return added


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
    mark_pack_used(kind, name, sticker_set.title, len(sticker_set.stickers))
    return random.choice(sticker_set.stickers)


async def pick_random_sticker(bot: Bot, kind: PostingKind) -> Sticker | None:
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


async def remember_custom_emoji_packs(
    bot: Bot, kind: PostingKind, custom_emoji_ids: list[str]
) -> list[str]:
    if not custom_emoji_ids:
        return []
    try:
        stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids)
    except TelegramError:
        return []
    return [
        sticker.set_name
        for sticker in stickers
        if sticker.set_name and remember_pack(kind, sticker.set_name)
    ]
