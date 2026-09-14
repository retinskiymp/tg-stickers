import re

from config import MAX_INTERVAL_MINUTES, MIN_INTERVAL_MINUTES

PlainMinutesPattern = re.compile(r"\d{1,5}")
CompoundIntervalPattern = re.compile(
    r"\d{1,5}\s*[mhd](?:\s*\d{1,5}\s*[mhd])?", re.IGNORECASE
)
IntervalPartPattern = re.compile(r"(\d{1,5})\s*([mhd])", re.IGNORECASE)
UnitMinutes = {
    "m": 1,
    "h": 60,
    "d": 1440,
}


def parse_minutes(text: str) -> int | None:
    if PlainMinutesPattern.fullmatch(text):
        return int(text)
    if not CompoundIntervalPattern.fullmatch(text):
        return None
    parts = [(int(amount), unit.lower()) for amount, unit in IntervalPartPattern.findall(text)]
    units = {unit for _, unit in parts}
    if len(units) != len(parts):
        return None
    return sum(amount * UnitMinutes[unit] for amount, unit in parts)


def parse_interval(text: str) -> int | None:
    minutes = parse_minutes(text.strip())
    if minutes is None or minutes < MIN_INTERVAL_MINUTES or minutes > MAX_INTERVAL_MINUTES:
        return None
    return minutes


def format_interval(minutes: int) -> str:
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins or not parts:
        parts.append(f"{mins}m")
    return " ".join(parts)
