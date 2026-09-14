import logging
from datetime import timedelta

from telegram import BotCommand, Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
)

from config import (
    ADMIN_IDS,
    ADMIN_ONLY_SETTINGS,
    HARVEST_INTERVAL_MINUTES,
    MAX_INTERVAL_MINUTES,
    MIN_INTERVAL_MINUTES,
    TOKEN,
)
from db import (
    collect_admin_stats,
    count_packs,
    disable_all_posting,
    load_chat_settings,
    mark_post_requested,
    recent_packs,
    set_chat_presence,
    set_enabled,
    set_interval,
)
from handlers import (
    CommandsByKindKey,
    HandlerAdminHelp,
    HandlerAdminStats,
    HandlerHelp,
    HandlerStart,
    HandlerStatus,
    KindCommands,
)
from interval import format_countdown, format_interval, parse_interval
from kinds import Kinds, PostingKind
from packs import harvest_pool
from scheduler import (
    cancel_all_chat_jobs,
    cancel_chat_job,
    restore_jobs,
    schedule_chat,
    seconds_until_next_run,
    send_random_post,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO
)
logger = logging.getLogger("stickerbot")

# Unit letters (m/h/d) stay Latin: they are the interval syntax the user types back.
HelpText = (
    "Кидаю случайный стикер из случайного набора.\n\n"
    "<b>Команды</b>\n"
    "/sticker — стикер прямо сейчас\n"
    "/interval 1h 20m — как часто постить: 45, 30m, 2h, 1d, 1h 20m — "
    f"минимум {format_interval(MIN_INTERVAL_MINUTES)}\n"
    "/interval — показать текущий интервал\n"
    "/on, /off — включить или выключить постинг в этом чате\n"
    "/status — настройки этого чата"
)
RecentPacksLimit = 10
AdminOnlyText = "Менять эти настройки могут только администраторы чата."
HarvestJobName = "harvest"


def commands_for(kind: PostingKind) -> KindCommands:
    return CommandsByKindKey[kind.key]


def admin_help_text() -> str:
    lines = [
        "<b>Команды администратора</b>",
        f"/{HandlerAdminHelp.long} — этот список",
        f"/{HandlerAdminStats.long} — статистика бота по всем чатам",
    ]
    lines += [
        f"/{commands_for(kind).packs.long} — что лежит в пуле наборов" for kind in Kinds
    ]
    lines.append(
        "\nВсе начинаются на <b>a</b>, не показываются в меню команд и отвечают "
        "только на id из ADMIN_IDS."
    )
    return "\n".join(lines)


def plural(amount: int, one: str, few: str, many: str) -> str:
    """Russian count form: 1 чат, 2 чата, 5 чатов."""
    if 11 <= amount % 100 <= 14:
        return f"{amount} {many}"
    last = amount % 10
    if last == 1:
        return f"{amount} {one}"
    if 2 <= last <= 4:
        return f"{amount} {few}"
    return f"{amount} {many}"


def unreachable_text(kind: PostingKind) -> str:
    return f"Не получилось взять {kind.noun} прямо сейчас. Попробуй позже."


def send_failed_text(kind: PostingKind) -> str:
    return f"Telegram не дал отправить {kind.noun} в этот чат."


def interval_help_text(kind: PostingKind) -> str:
    command = commands_for(kind).interval.long
    return (
        f"Не понял интервал. Примеры: /{command} 45, /{command} 2h, "
        f"/{command} 1h 20m, /{command} 1d — не больше двух частей, у каждой своя "
        "единица. Допустимо: "
        f"{format_interval(MIN_INTERVAL_MINUTES)} — {format_interval(MAX_INTERVAL_MINUTES)}."
    )


async def can_change_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE or not ADMIN_ONLY_SETTINGS:
        return True
    if update.effective_message and update.effective_message.sender_chat:
        return True
    member = await context.bot.get_chat_member(chat.id, update.effective_user.id)
    return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


def is_bot_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user) and user.id in ADMIN_IDS


def chat_title(update: Update) -> str | None:
    chat = update.effective_chat
    return chat.title or chat.full_name


def chat_type_name(update: Update) -> str:
    return str(update.effective_chat.type)


def touch_chat(update: Update):
    return load_chat_settings(
        update.effective_chat.id, chat_title(update), chat_type_name(update)
    )


def apply_schedules(context: ContextTypes.DEFAULT_TYPE, chat_id: int, settings) -> None:
    for kind in Kinds:
        state = kind.state(settings)
        if state.enabled:
            schedule_chat(context.application, kind, chat_id, state.interval_minutes)
        else:
            cancel_chat_job(context.application, kind, chat_id)


def make_post_now_handler(kind: PostingKind):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        touch_chat(update)
        mark_post_requested(kind, chat_id)
        try:
            sent = await send_random_post(context.bot, kind, chat_id)
        except TelegramError as error:
            logger.warning("Sending %s to %s failed: %s", kind.key, chat_id, error)
            await update.effective_message.reply_text(send_failed_text(kind))
            return
        if not sent:
            await update.effective_message.reply_text(unreachable_text(kind))

    return handler


def make_interval_handler(kind: PostingKind):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        settings = touch_chat(update)
        state = kind.state(settings)
        if not context.args:
            posting = "включён" if state.enabled else "выключен"
            await update.effective_message.reply_text(
                f"Интервал: {format_interval(state.interval_minutes)}, "
                f"постинг {posting}."
            )
            return
        if not await can_change_settings(update, context):
            await update.effective_message.reply_text(AdminOnlyText)
            return
        minutes = parse_interval(" ".join(context.args))
        if minutes is None:
            await update.effective_message.reply_text(interval_help_text(kind))
            return
        set_interval(kind, chat_id, minutes)
        schedule_chat(context.application, kind, chat_id, minutes)
        await update.effective_message.reply_text(
            f"Буду кидать {kind.noun} каждые {format_interval(minutes)}."
        )

    return handler


def make_turn_on_handler(kind: PostingKind):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await can_change_settings(update, context):
            await update.effective_message.reply_text(AdminOnlyText)
            return
        chat_id = update.effective_chat.id
        settings = set_enabled(kind, chat_id, True)
        state = kind.state(settings)
        schedule_chat(context.application, kind, chat_id, state.interval_minutes)
        await update.effective_message.reply_text(
            f"Постинг включён, каждые {format_interval(state.interval_minutes)}."
        )

    return handler


def make_turn_off_handler(kind: PostingKind):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await can_change_settings(update, context):
            await update.effective_message.reply_text(AdminOnlyText)
            return
        chat_id = update.effective_chat.id
        set_enabled(kind, chat_id, False)
        cancel_chat_job(context.application, kind, chat_id)
        await update.effective_message.reply_text(
            f"Постинг выключен. /{commands_for(kind).turn_on.long} включит обратно."
        )

    return handler


def make_packs_handler(kind: PostingKind):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_bot_admin(update):
            return
        total, alive = count_packs(kind, spicy=False)
        spicy_total, spicy_alive = count_packs(kind, spicy=True)
        lines = [
            f"Наборов в пуле: {alive} живых из {total}, "
            f"спайси {spicy_alive} живых из {spicy_total}."
        ]
        latest = recent_packs(kind, RecentPacksLimit)
        if latest:
            lines.append("Добавлены последними:")
            lines += [f"• {pack.title or pack.name}" for pack in latest]
        await update.effective_message.reply_text("\n".join(lines))

    return handler


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    settings = touch_chat(update)
    set_chat_presence(chat_id, True)
    apply_schedules(context, chat_id, settings)
    await update.effective_message.reply_html(HelpText)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_html(HelpText)


async def admin_help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_bot_admin(update):
        return
    await update.effective_message.reply_html(admin_help_text())


def kind_status_line(
    context: ContextTypes.DEFAULT_TYPE, kind: PostingKind, settings
) -> str:
    state = kind.state(settings)
    parts = [
        "включено" if state.enabled else "выключено",
        f"каждые {format_interval(state.interval_minutes)}",
    ]
    remaining = seconds_until_next_run(context.application, kind, settings.chat_tg_id)
    if state.enabled and remaining is not None:
        parts.append(f"следующий через {format_countdown(remaining)}")
    parts.append(f"отправлено {state.sent_count}")
    return f"{kind.plural_noun.capitalize()}: {', '.join(parts)}"


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = touch_chat(update)
    lines = [kind_status_line(context, kind, settings) for kind in Kinds]
    if is_bot_admin(update):
        for kind in Kinds:
            total, alive = count_packs(kind, spicy=False)
            spicy_total, spicy_alive = count_packs(kind, spicy=True)
            lines.append(
                f"Наборов в пуле: {alive} живых из {total}, "
                f"спайси {spicy_alive} живых из {spicy_total}"
            )
    await update.effective_message.reply_text("\n".join(lines))


def admin_stats_text() -> str:
    stats = collect_admin_stats()
    lines = [
        "<b>Статистика бота</b>",
        f"Известно чатов: {plural(stats.chats_total, 'чат', 'чата', 'чатов')} "
        f"({stats.private_chats} личных, {stats.group_chats} групповых)",
        f"Сейчас со мной: {stats.chats_present}",
        f"Постинг включён: {stats.posting_chats}",
    ]
    for kind, kind_stats in zip(Kinds, stats.kinds):
        lines.append(
            f"<b>{kind.plural_noun.capitalize()}</b>: включены в "
            f"{plural(kind_stats.enabled_chats, 'чате', 'чатах', 'чатах')}, "
            f"отправлено {kind_stats.sent_count}, по команде {kind_stats.requests_count}, "
            f"пул {kind_stats.packs_alive} живых из {kind_stats.packs_total}"
        )
    if stats.busiest_chats:
        lines.append("<b>Самые активные чаты</b>")
        lines += [
            f"• {chat.title or chat.chat_tg_id} — "
            f"{plural(chat.sticker_sent_count, 'стикер', 'стикера', 'стикеров')}"
            for chat in stats.busiest_chats
        ]
    return "\n".join(lines)


async def admin_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_bot_admin(update):
        return
    await update.effective_message.reply_html(admin_stats_text())


# def custom_emoji_ids(message) -> list[str]:
#     entities = list(message.entities) + list(message.caption_entities)
#     return [
#         entity.custom_emoji_id
#         for entity in entities
#         if entity.type == MessageEntityType.CUSTOM_EMOJI and entity.custom_emoji_id
#     ]
#
#
# async def discover_emoji_packs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     ids = custom_emoji_ids(update.effective_message)
#     added = await remember_custom_emoji_packs(context.bot, EmojiKind, ids)
#     for name in added:
#         logger.info("New emoji pack in the pool: %s", name)


async def track_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    membership = update.my_chat_member
    chat = membership.chat
    status = membership.new_chat_member.status
    if status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        settings = load_chat_settings(chat.id, chat.title or chat.full_name, str(chat.type))
        set_chat_presence(chat.id, True)
        apply_schedules(context, chat.id, settings)
        greeting = greeting_text(settings)
        if greeting:
            await context.bot.send_message(chat.id, greeting)
    elif status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        disable_all_posting(chat.id)
        set_chat_presence(chat.id, False)
        cancel_all_chat_jobs(context.application, chat.id)


def greeting_text(settings) -> str | None:
    enabled = [kind for kind in Kinds if kind.state(settings).enabled]
    if not enabled:
        return None
    schedule = ", ".join(
        f"случайный {kind.noun} каждые {format_interval(kind.state(settings).interval_minutes)}"
        for kind in enabled
    )
    return f"Привет! Буду кидать {schedule}. /help — что я умею."


BotCommands = [
    BotCommand("sticker", "случайный стикер прямо сейчас"),
    BotCommand("interval", "как часто постить: 30m, 1h 20m, 1d"),
    BotCommand("on", "включить постинг"),
    BotCommand("off", "выключить постинг"),
    BotCommand("status", "настройки этого чата"),
    BotCommand("help", "что я умею"),
]


async def harvest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    for kind in Kinds:
        added, spicy_added = await harvest_pool(kind)
        total, alive = count_packs(kind, spicy=False)
        spicy_total, spicy_alive = count_packs(kind, spicy=True)
        logger.info(
            "Harvested %s %s packs and %s spicy, pool holds %s alive of %s and %s spicy of %s",
            added,
            kind.key,
            spicy_added,
            alive,
            total,
            spicy_alive,
            spicy_total,
        )


async def after_init(app) -> None:
    await app.bot.set_my_commands(BotCommands)
    restored = restore_jobs(app)
    app.job_queue.run_repeating(
        harvest_job,
        interval=timedelta(minutes=HARVEST_INTERVAL_MINUTES),
        first=timedelta(0),
        name=HarvestJobName,
    )
    for kind in Kinds:
        total, alive = count_packs(kind, spicy=False)
        spicy_total, spicy_alive = count_packs(kind, spicy=True)
        logger.info(
            "%s pool at start: %s alive of %s, spicy %s alive of %s, schedules restored: %s",
            kind.key,
            alive,
            total,
            spicy_alive,
            spicy_total,
            restored[kind.key],
        )
    logger.info("Bot admins: %s", len(ADMIN_IDS))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Handler failed", exc_info=context.error)


def add_kind_handlers(app, kind: PostingKind) -> None:
    commands = commands_for(kind)
    app.add_handler(CommandHandler(commands.post_now.as_list(), make_post_now_handler(kind)))
    app.add_handler(CommandHandler(commands.interval.as_list(), make_interval_handler(kind)))
    app.add_handler(CommandHandler(commands.turn_on.as_list(), make_turn_on_handler(kind)))
    app.add_handler(CommandHandler(commands.turn_off.as_list(), make_turn_off_handler(kind)))
    app.add_handler(CommandHandler(commands.packs.as_list(), make_packs_handler(kind)))


def main() -> None:
    app = ApplicationBuilder().token(TOKEN).post_init(after_init).build()
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler(HandlerStart.as_list(), start_cmd))
    app.add_handler(CommandHandler(HandlerHelp.as_list(), help_cmd))
    app.add_handler(CommandHandler(HandlerStatus.as_list(), status_cmd))
    app.add_handler(CommandHandler(HandlerAdminHelp.as_list(), admin_help_cmd))
    app.add_handler(CommandHandler(HandlerAdminStats.as_list(), admin_stats_cmd))
    for kind in Kinds:
        add_kind_handlers(app, kind)
    app.add_handler(ChatMemberHandler(track_membership, ChatMemberHandler.MY_CHAT_MEMBER))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
