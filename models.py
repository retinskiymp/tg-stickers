from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class PackColumns:
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=True)
    alive = Column(Boolean, nullable=False, default=True, index=True)
    spicy = Column(Boolean, nullable=False, default=False, index=True)
    stickers_count = Column(Integer, nullable=False, default=0)
    added_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)


class StickerPackModel(PackColumns, Base):
    __tablename__ = "sticker_packs"


# class EmojiPackModel(PackColumns, Base):
#     __tablename__ = "emoji_packs"


class ChatSettingsModel(Base):
    __tablename__ = "chat_settings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_tg_id = Column(BigInteger, unique=True, nullable=False, index=True)
    title = Column(String, nullable=True)
    chat_type = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    present = Column(Boolean, nullable=False, default=True)
    sticker_interval_minutes = Column(Integer, nullable=False)
    sticker_enabled = Column(Boolean, nullable=False, default=True)
    sticker_last_sent_at = Column(DateTime, nullable=True)
    sticker_sent_count = Column(Integer, nullable=False, default=0)
    sticker_requests_count = Column(Integer, nullable=False, default=0)
    # emoji_interval_minutes = Column(Integer, nullable=False)
    # emoji_enabled = Column(Boolean, nullable=False, default=True)
    # emoji_last_sent_at = Column(DateTime, nullable=True)
    # emoji_sent_count = Column(Integer, nullable=False, default=0)
    # emoji_requests_count = Column(Integer, nullable=False, default=0)


def posting_field(name: str) -> property:
    def read(state: "ChatPostingState"):
        return getattr(state.settings, f"{state.prefix}_{name}")

    def write(state: "ChatPostingState", value) -> None:
        setattr(state.settings, f"{state.prefix}_{name}", value)

    return property(read, write)


class ChatPostingState:
    interval_minutes = posting_field("interval_minutes")
    enabled = posting_field("enabled")
    last_sent_at = posting_field("last_sent_at")
    sent_count = posting_field("sent_count")
    requests_count = posting_field("requests_count")

    def __init__(self, settings: ChatSettingsModel, prefix: str) -> None:
        self.settings = settings
        self.prefix = prefix
