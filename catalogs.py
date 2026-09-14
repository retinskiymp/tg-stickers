import asyncio
import random
import re

import httpx

from config import HTTP_TIMEOUT_SECONDS

UserAgent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TlgrmPageUrl = "https://tlgrm.eu/stickers?page={page}"
TlgrmPackPattern = re.compile(r'href="https://tlgrm\.eu/stickers/([A-Za-z0-9_]{2,64})"')
TlgrmLastPagePattern = re.compile(r'data-last-page="(\d+)"')
TlgrmKnownLastPage = 186

CombotUrls = (
    "https://combot.org/stickers",
    "https://combot.org/stickers/trending",
    "https://combot.org/stickers/top30",
)
CombotPackPattern = re.compile(r'href="/stickers/([A-Za-z0-9_]{2,64})"')
CombotSectionNames = frozenset({"trending", "top30"})

ChannelFeedUrl = "https://t.me/s/{channel}"
ChannelFeedPageUrl = "https://t.me/s/{channel}?before={before}"
ChannelPostIdPattern = re.compile(r'data-post="[A-Za-z0-9_]+/(\d+)"')
EmojiPackPattern = re.compile(r"addemoji/([A-Za-z0-9_]{2,64})")
ChannelPageSize = 20

EmojiTgUrl = "https://emoji.tg/g/emoji"


class TlgrmCatalog:
    def __init__(self) -> None:
        self._last_page = TlgrmKnownLastPage

    async def harvest(self, client: httpx.AsyncClient, requests_count: int) -> list[str]:
        pages = random.sample(
            range(1, self._last_page + 1), k=min(requests_count, self._last_page)
        )
        return await gather_names(self._fetch_page(client, page) for page in pages)

    async def _fetch_page(self, client: httpx.AsyncClient, page: int) -> list[str]:
        response = await client.get(TlgrmPageUrl.format(page=page))
        response.raise_for_status()
        last_page = TlgrmLastPagePattern.search(response.text)
        if last_page:
            self._last_page = int(last_page.group(1))
        return TlgrmPackPattern.findall(response.text)


class CombotCatalog:
    async def harvest(self, client: httpx.AsyncClient, requests_count: int) -> list[str]:
        urls = random.sample(CombotUrls, k=min(requests_count, len(CombotUrls)))
        return await gather_names(self._fetch_url(client, url) for url in urls)

    async def _fetch_url(self, client: httpx.AsyncClient, url: str) -> list[str]:
        response = await client.get(url)
        response.raise_for_status()
        return [
            name
            for name in CombotPackPattern.findall(response.text)
            if name not in CombotSectionNames
        ]


class EmojiChannelCatalog:
    def __init__(self, channel: str, known_last_post_id: int) -> None:
        self._channel = channel
        self._last_post_id = known_last_post_id

    async def harvest(self, client: httpx.AsyncClient, requests_count: int) -> list[str]:
        names = await self._fetch_feed(client, None)
        offsets = self._random_offsets(requests_count - 1)
        names += await gather_names(self._fetch_feed(client, offset) for offset in offsets)
        return names

    def _random_offsets(self, count: int) -> list[int]:
        highest = self._last_post_id
        if count <= 0 or highest <= ChannelPageSize:
            return []
        return random.sample(range(ChannelPageSize, highest + 1), k=min(count, highest))

    async def _fetch_feed(self, client: httpx.AsyncClient, before: int | None) -> list[str]:
        url = (
            ChannelFeedUrl.format(channel=self._channel)
            if before is None
            else ChannelFeedPageUrl.format(channel=self._channel, before=before)
        )
        response = await client.get(url)
        response.raise_for_status()
        post_ids = [int(post_id) for post_id in ChannelPostIdPattern.findall(response.text)]
        if post_ids:
            self._last_post_id = max(self._last_post_id, max(post_ids))
        return EmojiPackPattern.findall(response.text)


class EmojiTgCatalog:
    async def harvest(self, client: httpx.AsyncClient, requests_count: int) -> list[str]:
        response = await client.get(EmojiTgUrl)
        response.raise_for_status()
        return EmojiPackPattern.findall(response.text)


StickerCatalogs = (TlgrmCatalog(), CombotCatalog())
EmojiCatalogs = (
    EmojiChannelCatalog("TgEmojis", 10160),
    EmojiChannelCatalog("CustomEmojiPack", 42570),
    EmojiTgCatalog(),
)


async def gather_names(tasks) -> list[str]:
    results = await asyncio.gather(*tasks, return_exceptions=True)
    names: list[str] = []
    for result in results:
        if isinstance(result, BaseException):
            continue
        names += result
    return names


async def harvest_pack_names(catalogs, requests_per_catalog: int) -> list[str]:
    headers = {"User-Agent": UserAgent, "Accept-Language": "en,ru;q=0.9"}
    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT_SECONDS, headers=headers, follow_redirects=True
    ) as client:
        return await gather_names(
            catalog.harvest(client, requests_per_catalog) for catalog in catalogs
        )
