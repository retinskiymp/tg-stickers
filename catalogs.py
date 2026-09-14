import asyncio
import re

import httpx

from config import HTTP_TIMEOUT_SECONDS, TGLIST_HOST, TLGRM_HOST

UserAgent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

TlgrmPageUrl = f"https://{TLGRM_HOST}/stickers?page={{page}}"
TlgrmPackPattern = re.compile(
    rf'href="https://{re.escape(TLGRM_HOST)}/stickers/([A-Za-z0-9_]{{2,64}})"'
)

TglistPageUrl = f"https://{TGLIST_HOST}/stickers?sort=rating_score&page={{page}}"
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
            harvested = 0
            for result in results:
                if isinstance(result, BaseException):
                    continue
                for name in result:
                    names.setdefault(name)
                harvested += len(result)
            if not harvested:
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


async def gather_names(tasks) -> list[str]:
    results = await asyncio.gather(*tasks, return_exceptions=True)
    names: list[str] = []
    for result in results:
        if isinstance(result, BaseException):
            continue
        names += result
    return names


async def harvest_pack_names(catalogs, limit: int) -> list[str]:
    headers = {"User-Agent": UserAgent, "Accept-Language": "ru,en;q=0.9"}
    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT_SECONDS, headers=headers, follow_redirects=True
    ) as client:
        return await gather_names(catalog.harvest(client, limit) for catalog in catalogs)
