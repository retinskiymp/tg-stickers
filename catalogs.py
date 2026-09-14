import asyncio
import re
from itertools import zip_longest
from urllib.parse import quote

import httpx

from config import (
    ANIME_SEARCH_TERMS,
    HTTP_TIMEOUT_SECONDS,
    SPICY_CATEGORIES,
    SPICY_SEARCH_TERMS,
    TGLIST_HOST,
    TLGRM_HOST,
)

UserAgent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

TlgrmPageUrl = f"https://{TLGRM_HOST}/stickers?page={{page}}"
TlgrmPackPattern = re.compile(
    rf'href="https://{re.escape(TLGRM_HOST)}/stickers/([A-Za-z0-9_]{{2,64}})"'
)

TglistPageUrl = f"https://{TGLIST_HOST}/stickers?sort=rating_score&page={{page}}"
TglistCategoryPageUrl = (
    f"https://{TGLIST_HOST}/stickers?category={{category}}&sort=rating_score&page={{{{page}}}}"
)
TglistSearchPageUrl = (
    f"https://{TGLIST_HOST}/stickers?search={{term}}&sort=rating_score&page={{{{page}}}}"
)
TglistPackPattern = re.compile(r'href="/view/([A-Za-z0-9_]{2,64})"')

PageBatchSize = 6
MaxCatalogPages = 300

# CombotUrls = (
#     "https://combot.org/stickers",
#     "https://combot.org/stickers/trending",
#     "https://combot.org/stickers/top30",
# )
# CombotPackPattern = re.compile(r'href="/stickers/([A-Za-z0-9_]{2,64})"')
# CombotSectionNames = frozenset({"trending", "top30"})


class PopularCatalog:
    """Reads a popularity-ordered listing from page 1 until `limit` packs are collected.

    Pages are walked in order and never sampled, so every harvest returns the same
    top slice of the catalogue — plus whatever has climbed into it since last time.
    """

    def __init__(self, page_url: str, pack_pattern: re.Pattern) -> None:
        self._page_url = page_url
        self._pack_pattern = pack_pattern

    async def harvest(self, client: httpx.AsyncClient, limit: int) -> list[str]:
        names: dict[str, None] = {}
        page = 1
        while len(names) < limit and page <= MaxCatalogPages:
            batch = range(page, min(page + PageBatchSize, MaxCatalogPages + 1))
            results = await asyncio.gather(
                *(self._fetch_page(client, number) for number in batch),
                return_exceptions=True,
            )
            known = len(names)
            for result in results:
                if isinstance(result, BaseException):
                    continue
                for name in result:
                    names.setdefault(name)
            # Stop on an exhausted listing and on one that ignores ?page= and keeps
            # serving the same rows, as the adult category does.
            if len(names) == known:
                break
            page += PageBatchSize
        return list(names)[:limit]

    async def _fetch_page(self, client: httpx.AsyncClient, page: int) -> list[str]:
        response = await client.get(self._page_url.format(page=page))
        response.raise_for_status()
        return self._pack_pattern.findall(response.text)


# class CombotCatalog:
#     async def harvest(self, client: httpx.AsyncClient, limit: int) -> list[str]:
#         return await gather_names(self._fetch_url(client, url) for url in CombotUrls)
#
#     async def _fetch_url(self, client: httpx.AsyncClient, url: str) -> list[str]:
#         response = await client.get(url)
#         response.raise_for_status()
#         return [
#             name
#             for name in CombotPackPattern.findall(response.text)
#             if name not in CombotSectionNames
#         ]


StickerCatalogs = (
    PopularCatalog(TlgrmPageUrl, TlgrmPackPattern),
    PopularCatalog(TglistPageUrl, TglistPackPattern),
)
# The spicy pool is memes, swearing and 18+ together. tlgrm.ru offers neither an
# adult section nor a server-side search, so it all comes from tglist: whole
# categories, which carry the bulk, plus a keyword search per term on top.
SpicyStickerCatalogs = tuple(
    PopularCatalog(TglistCategoryPageUrl.format(category=quote(category)), TglistPackPattern)
    for category in SPICY_CATEGORIES
) + tuple(
    PopularCatalog(TglistSearchPageUrl.format(term=quote(term)), TglistPackPattern)
    for term in SPICY_SEARCH_TERMS
)

AnimeStickerCatalogs = tuple(
    PopularCatalog(TglistSearchPageUrl.format(term=quote(term)), TglistPackPattern)
    for term in ANIME_SEARCH_TERMS
)


def merge_by_rank(groups: list[list[str]], limit: int) -> list[str]:
    """Take rank 1 from every catalogue, then rank 2, and so on, up to `limit`.

    Concatenating instead would let the first catalogue alone fill a limit smaller
    than the combined yield, and the rest would never be reached.
    """
    merged: dict[str, None] = {}
    for row in zip_longest(*groups):
        for name in row:
            if name is not None:
                merged.setdefault(name)
        if len(merged) >= limit:
            break
    return list(merged)[:limit]


async def harvest_pack_names(catalogs, limit: int) -> list[str]:
    headers = {"User-Agent": UserAgent, "Accept-Language": "ru,en;q=0.9"}
    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT_SECONDS, headers=headers, follow_redirects=True
    ) as client:
        results = await asyncio.gather(
            *(catalog.harvest(client, limit) for catalog in catalogs),
            return_exceptions=True,
        )
    return merge_by_rank(
        [result for result in results if not isinstance(result, BaseException)], limit
    )
