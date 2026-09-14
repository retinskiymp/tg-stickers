import os
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import scoped_session, sessionmaker

from config import DB_URL
from kinds import EmojiKind, Kinds, PostingKind, StickerKind
from models import Base, ChatSettingsModel

NameChunkSize = 400
BusiestChatsLimit = 5
PrivateChatType = "private"


def ensure_database_directory(url: str) -> None:
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite") or not parsed.database:
        return
    directory = os.path.dirname(os.path.abspath(parsed.database))
    if directory:
        os.makedirs(directory, exist_ok=True)


ensure_database_directory(DB_URL)

engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))
Base.metadata.create_all(bind=engine)


def chat_column(kind: PostingKind, name: str):
    return getattr(ChatSettingsModel, f"{kind.key}_{name}")


def get_chat_settings(
    session, chat_id: int, title: str | None = None, chat_type: str | None = None
) -> ChatSettingsModel:
    settings = session.query(ChatSettingsModel).filter_by(chat_tg_id=chat_id).first()
    if not settings:
        settings = ChatSettingsModel(
            chat_tg_id=chat_id,
            title=title,
            chat_type=chat_type,
            sticker_interval_minutes=StickerKind.starting_interval_minutes(),
            sticker_enabled=StickerKind.enabled_by_default,
            emoji_interval_minutes=EmojiKind.starting_interval_minutes(),
            emoji_enabled=EmojiKind.enabled_by_default,
        )
        session.add(settings)
        session.commit()
        return settings
    changed = False
    if title and settings.title != title:
        settings.title = title
        changed = True
    if chat_type and settings.chat_type != chat_type:
        settings.chat_type = chat_type
        changed = True
    if changed:
        session.commit()
    return settings


def load_chat_settings(
    chat_id: int, title: str | None = None, chat_type: str | None = None
) -> ChatSettingsModel:
    with SessionLocal() as session:
        return get_chat_settings(session, chat_id, title, chat_type)


def set_interval(kind: PostingKind, chat_id: int, minutes: int) -> ChatSettingsModel:
    with SessionLocal() as session:
        settings = get_chat_settings(session, chat_id)
        state = kind.state(settings)
        state.interval_minutes = minutes
        state.enabled = True
        session.commit()
        return settings


def set_enabled(kind: PostingKind, chat_id: int, enabled: bool) -> ChatSettingsModel:
    with SessionLocal() as session:
        settings = get_chat_settings(session, chat_id)
        kind.state(settings).enabled = enabled
        session.commit()
        return settings


def disable_all_posting(chat_id: int) -> None:
    with SessionLocal() as session:
        settings = get_chat_settings(session, chat_id)
        for kind in Kinds:
            kind.state(settings).enabled = False
        session.commit()


def set_chat_presence(chat_id: int, present: bool) -> None:
    with SessionLocal() as session:
        settings = get_chat_settings(session, chat_id)
        settings.present = present
        session.commit()


def load_enabled_chats(kind: PostingKind) -> list[ChatSettingsModel]:
    with SessionLocal() as session:
        return (
            session.query(ChatSettingsModel)
            .filter(chat_column(kind, "enabled") == True)
            .all()
        )


def mark_post_sent(kind: PostingKind, chat_id: int) -> None:
    with SessionLocal() as session:
        settings = get_chat_settings(session, chat_id)
        state = kind.state(settings)
        state.last_sent_at = datetime.utcnow()
        state.sent_count += 1
        session.commit()


def mark_post_requested(kind: PostingKind, chat_id: int) -> None:
    with SessionLocal() as session:
        settings = get_chat_settings(session, chat_id)
        state = kind.state(settings)
        state.requests_count += 1
        session.commit()


def add_pack(kind: PostingKind, name: str, title: str | None = None) -> bool:
    with SessionLocal() as session:
        pack = session.query(kind.pack_model).filter_by(name=name).first()
        if pack:
            if not pack.alive:
                pack.alive = True
                session.commit()
            return False
        session.add(kind.pack_model(name=name, title=title))
        session.commit()
        return True


def add_packs(kind: PostingKind, names: list[str]) -> int:
    unique = list(dict.fromkeys(names))
    added = 0
    for start in range(0, len(unique), NameChunkSize):
        chunk = unique[start : start + NameChunkSize]
        with SessionLocal() as session:
            known = {
                row[0]
                for row in session.execute(
                    select(kind.pack_model.name).where(kind.pack_model.name.in_(chunk))
                )
            }
            fresh = [name for name in chunk if name not in known]
            session.add_all([kind.pack_model(name=name) for name in fresh])
            session.commit()
            added += len(fresh)
    return added


def pick_random_pack_name(kind: PostingKind) -> str | None:
    with SessionLocal() as session:
        row = session.execute(
            select(kind.pack_model.name)
            .where(kind.pack_model.alive == True)
            .order_by(func.random())
            .limit(1)
        ).first()
        return row[0] if row else None


def mark_pack_dead(kind: PostingKind, name: str) -> None:
    with SessionLocal() as session:
        pack = session.query(kind.pack_model).filter_by(name=name).first()
        if pack:
            pack.alive = False
            session.commit()


def mark_pack_used(
    kind: PostingKind, name: str, title: str | None, stickers_count: int
) -> None:
    with SessionLocal() as session:
        pack = session.query(kind.pack_model).filter_by(name=name).first()
        if not pack:
            return
        pack.title = title
        pack.stickers_count = stickers_count
        pack.last_used_at = datetime.utcnow()
        session.commit()


def count_alive_packs(kind: PostingKind) -> int:
    with SessionLocal() as session:
        return (
            session.query(func.count(kind.pack_model.id))
            .filter(kind.pack_model.alive == True)
            .scalar()
        )


def count_packs(kind: PostingKind) -> tuple[int, int]:
    with SessionLocal() as session:
        total = session.query(func.count(kind.pack_model.id)).scalar()
        alive = (
            session.query(func.count(kind.pack_model.id))
            .filter(kind.pack_model.alive == True)
            .scalar()
        )
        return total, alive


def recent_packs(kind: PostingKind, limit: int) -> list:
    with SessionLocal() as session:
        return (
            session.query(kind.pack_model)
            .filter_by(alive=True)
            .order_by(kind.pack_model.added_at.desc())
            .limit(limit)
            .all()
        )


@dataclass(frozen=True)
class KindStats:
    key: str
    enabled_chats: int
    sent_count: int
    requests_count: int
    packs_total: int
    packs_alive: int


@dataclass(frozen=True)
class ChatActivity:
    chat_tg_id: int
    title: str | None
    chat_type: str | None
    sticker_sent_count: int
    emoji_sent_count: int


@dataclass(frozen=True)
class AdminStats:
    chats_total: int
    chats_present: int
    private_chats: int
    group_chats: int
    posting_chats: int
    kinds: list[KindStats]
    busiest_chats: list[ChatActivity]


def collect_kind_stats(session, kind: PostingKind) -> KindStats:
    enabled_chats = (
        session.query(func.count(ChatSettingsModel.id))
        .filter(chat_column(kind, "enabled") == True, ChatSettingsModel.present == True)
        .scalar()
    )
    sent_count = session.query(func.sum(chat_column(kind, "sent_count"))).scalar() or 0
    requests_count = (
        session.query(func.sum(chat_column(kind, "requests_count"))).scalar() or 0
    )
    packs_total = session.query(func.count(kind.pack_model.id)).scalar()
    packs_alive = (
        session.query(func.count(kind.pack_model.id))
        .filter(kind.pack_model.alive == True)
        .scalar()
    )
    return KindStats(
        key=kind.key,
        enabled_chats=enabled_chats,
        sent_count=int(sent_count),
        requests_count=int(requests_count),
        packs_total=packs_total,
        packs_alive=packs_alive,
    )


def collect_admin_stats() -> AdminStats:
    with SessionLocal() as session:
        chats_total = session.query(func.count(ChatSettingsModel.id)).scalar()
        chats_present = (
            session.query(func.count(ChatSettingsModel.id))
            .filter(ChatSettingsModel.present == True)
            .scalar()
        )
        private_chats = (
            session.query(func.count(ChatSettingsModel.id))
            .filter(ChatSettingsModel.chat_type == PrivateChatType)
            .scalar()
        )
        posting_chats = (
            session.query(func.count(ChatSettingsModel.id))
            .filter(
                ChatSettingsModel.present == True,
                (ChatSettingsModel.sticker_enabled == True)
                | (ChatSettingsModel.emoji_enabled == True),
            )
            .scalar()
        )
        busiest = (
            session.query(ChatSettingsModel)
            .order_by(
                (
                    ChatSettingsModel.sticker_sent_count
                    + ChatSettingsModel.emoji_sent_count
                ).desc()
            )
            .limit(BusiestChatsLimit)
            .all()
        )
        return AdminStats(
            chats_total=chats_total,
            chats_present=chats_present,
            private_chats=private_chats,
            group_chats=chats_total - private_chats,
            posting_chats=posting_chats,
            kinds=[collect_kind_stats(session, kind) for kind in Kinds],
            busiest_chats=[
                ChatActivity(
                    chat_tg_id=settings.chat_tg_id,
                    title=settings.title,
                    chat_type=settings.chat_type,
                    sticker_sent_count=settings.sticker_sent_count,
                    emoji_sent_count=settings.emoji_sent_count,
                )
                for settings in busiest
            ],
        )
