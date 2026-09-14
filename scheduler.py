import logging
from datetime import datetime, timedelta

from telegram import Bot
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import Application, ContextTypes

from db import (
    disable_all_posting,
    load_enabled_chats,
    mark_post_sent,
    set_chat_presence,
    set_enabled,
)
from kinds import Kinds, PostingKind
from packs import pick_random_sticker

logger = logging.getLogger("stickerbot")

MinimumFirstDelaySeconds = 30
ChatGoneErrors = (
    "chat not found",
    "chat_id is empty",
    "group chat was upgraded",
    "peer_id_invalid",
    "bot was kicked",
    "bot was blocked",
)


def job_name(kind: PostingKind, chat_id: int) -> str:
    return f"{kind.key}:{chat_id}"


def cancel_chat_job(app: Application, kind: PostingKind, chat_id: int) -> None:
    for job in app.job_queue.get_jobs_by_name(job_name(kind, chat_id)):
        job.schedule_removal()


def cancel_all_chat_jobs(app: Application, chat_id: int) -> None:
    for kind in Kinds:
        cancel_chat_job(app, kind, chat_id)


def schedule_chat(
    app: Application,
    kind: PostingKind,
    chat_id: int,
    interval_minutes: int,
    first_seconds: float | None = None,
) -> None:
    cancel_chat_job(app, kind, chat_id)
    interval = timedelta(minutes=interval_minutes)
    first = interval if first_seconds is None else timedelta(seconds=first_seconds)
    app.job_queue.run_repeating(
        send_scheduled_post,
        interval=interval,
        first=first,
        chat_id=chat_id,
        name=job_name(kind, chat_id),
        data=kind,
    )


def next_run_at(app: Application, kind: PostingKind, chat_id: int) -> datetime | None:
    jobs = app.job_queue.get_jobs_by_name(job_name(kind, chat_id))
    return jobs[0].next_t if jobs else None


def first_delay_seconds(last_sent_at: datetime | None, interval_minutes: int) -> float:
    if last_sent_at is None:
        return interval_minutes * 60
    elapsed = (datetime.utcnow() - last_sent_at).total_seconds()
    remaining = interval_minutes * 60 - elapsed
    return max(remaining, MinimumFirstDelaySeconds)


def restore_kind_jobs(app: Application, kind: PostingKind) -> int:
    chats = load_enabled_chats(kind)
    for settings in chats:
        state = kind.state(settings)
        schedule_chat(
            app,
            kind,
            settings.chat_tg_id,
            state.interval_minutes,
            first_delay_seconds(state.last_sent_at, state.interval_minutes),
        )
    return len(chats)


def restore_jobs(app: Application) -> dict[str, int]:
    return {kind.key: restore_kind_jobs(app, kind) for kind in Kinds}


def is_chat_gone(error: BadRequest) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in ChatGoneErrors)


async def send_random_post(bot: Bot, kind: PostingKind, chat_id: int) -> bool:
    sticker = await pick_random_sticker(bot, kind)
    if not sticker:
        return False
    await bot.send_sticker(chat_id=chat_id, sticker=sticker.file_id)
    mark_post_sent(kind, chat_id)
    return True


async def send_scheduled_post(context: ContextTypes.DEFAULT_TYPE) -> None:
    kind = context.job.data
    chat_id = context.job.chat_id
    try:
        await send_random_post(context.bot, kind, chat_id)
    except Forbidden:
        disable_all_posting(chat_id)
        set_chat_presence(chat_id, False)
        cancel_all_chat_jobs(context.application, chat_id)
    except BadRequest as error:
        if not is_chat_gone(error):
            logger.warning("Sending %s to %s failed: %s", kind.noun, chat_id, error)
            return
        set_enabled(kind, chat_id, False)
        cancel_chat_job(context.application, kind, chat_id)
    except TelegramError:
        pass
