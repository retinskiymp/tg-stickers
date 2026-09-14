from dataclasses import dataclass
from typing import Iterable, List, Tuple, Union

ShortType = Union[str, Tuple[str, ...], None]


@dataclass(frozen=True)
class CommandAliases:
    long: str
    short: ShortType = None

    def __iter__(self) -> Iterable[str]:
        yield self.long
        if self.short:
            if isinstance(self.short, tuple):
                for alias in self.short:
                    yield alias
            else:
                yield self.short

    def as_list(self) -> List[str]:
        return list(self)


@dataclass(frozen=True)
class KindCommands:
    post_now: CommandAliases
    interval: CommandAliases
    turn_on: CommandAliases
    turn_off: CommandAliases
    packs: CommandAliases


HandlerStart = CommandAliases(long="start")
HandlerHelp = CommandAliases(long="help", short="h")
HandlerStatus = CommandAliases(long="status")

# Admin-only commands are all prefixed with "a" and kept out of the command menu.
HandlerAdminHelp = CommandAliases(long="ahelp")
HandlerAdminStats = CommandAliases(long="astats", short="adminstats")

StickerCommands = KindCommands(
    post_now=CommandAliases(long="sticker", short=("s", "st")),
    interval=CommandAliases(long="interval", short=("setinterval", "i", "stickerinterval")),
    turn_on=CommandAliases(long="on", short="stickeron"),
    turn_off=CommandAliases(long="off", short="stickeroff"),
    packs=CommandAliases(long="apacks", short="astickerpacks"),
)

# EmojiCommands = KindCommands(
#     post_now=CommandAliases(long="emoji", short=("e", "em")),
#     interval=CommandAliases(long="emojiinterval", short=("setemojiinterval", "ei")),
#     turn_on=CommandAliases(long="emojion"),
#     turn_off=CommandAliases(long="emojioff"),
#     add_pack=CommandAliases(long="addemoji", short="addemojipack"),
#     packs=CommandAliases(long="aemojipacks"),
# )

CommandsByKindKey = {"sticker": StickerCommands}
