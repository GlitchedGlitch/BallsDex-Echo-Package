import re
from datetime import datetime, timezone

import discord
from bd_models.models import (
    Ball,
    BallGroup,
    BallInstance,
    Economy,
    GuildConfig,
    Player,
    Regime,
    Special,
)
from settings.models import settings

LINE_RE = re.compile(r"\{s:line\}", re.IGNORECASE)
EMOJI_RE = re.compile(r"\{e:([^{}]+)\}", re.IGNORECASE)
COUNT_RE = re.compile(r"\{c:([^{}]+)\}", re.IGNORECASE)
TIME_RE = re.compile(r"\{t:([^{}]+)\}", re.IGNORECASE)

class ExtraError(Exception):
    """Base exception for invalid extra placeholders."""


class UnknownBallError(ExtraError):
    def __init__(self, names: list[str]):
        self.names = names
        super().__init__()


class InvalidCountError(ExtraError):
    def __init__(self, value: str):
        self.value = value
        super().__init__()


class InvalidTimeError(ExtraError):
    def __init__(self, value: str):
        self.value = value
        super().__init__()


def unknown_balls_warning(names: list[str]) -> str:
    formatted = ", ".join(f"`{name}`" for name in names)

    return (
        f"The {settings.collectible_name if len(names) != 1 else settings.plural_collectible_name} {formatted} "
        f"don't exist. "
        "Are you sure you typed the full name correctly?\n"
        "Do you still want to proceed sending the message?"
    )


def invalid_count_warning(names: list[str]) -> str:
    formatted = ", ".join(f"`{name}`" for name in names)

    return (
        f"The count placeholder{'s' if len(names) != 1 else ''} "
        f"{formatted} could not be resolved. "
        "Check the model name and optional filter.\n"
        "Do you still want to proceed sending the message?"
    )


def invalid_time_warning(values: list[str]) -> str:
    formatted = ", ".join(f"`{value}`" for value in values)

    return (
        f"The time placeholder{'s' if len(values) != 1 else ''} "
        f"{formatted} could not be parsed. "
        "Use `D/M/Y H:M:S` or `D/M/Y`\n"
        "The allowed time formats are [t, d, D, f, F, R]\n"
        "Do you still want to proceed sending the message?"
    )


TIME_FORMATS = {
    "t": "t",
    "T": "T",
    "d": "d",
    "D": "D",
    "f": "f",
    "F": "F",
    "R": "R",
}


def parse_time(value: str) -> str | None:
    """
    Parse discord timestamps.
    """

    value = value.strip()

    timestamp_type = "f"

    match = re.fullmatch(
        r"(.+?)(?::([tTdDfFR]))?",
        value,
    )

    if not match:
        return None

    date_text = match.group(1).strip()
    requested_type = match.group(2)

    if requested_type:
        timestamp_type = requested_type

    formats = (
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    )

    parsed = None

    for fmt in formats:
        try:
            parsed = datetime.strptime(date_text, fmt)
            break
        except ValueError:
            continue

    if parsed is None:
        return None

    parsed = parsed.replace(tzinfo=timezone.utc)

    return f"<t:{int(parsed.timestamp())}:{timestamp_type}>"


async def resolve_times(text: str) -> tuple[str, list[str]]:
    invalid: list[str] = []

    def replace(match: re.Match[str]) -> str:
        value = match.group(1).strip()
        result = parse_time(value)

        if result is None:
            invalid.append(value)
            return match.group(0)

        return result

    result = TIME_RE.sub(replace, text)

    return result, invalid


COUNT_MODELS = {
    "economies": Economy,
    "regimes": Regime,
    "groups": BallGroup,
    "balls": Ball,
    "ballinstances": BallInstance,
    "guildconfigs": GuildConfig,
    "players": Player,
    "specials": Special,
}


async def count_model(
    value: str,
    bot: discord.Client,
) -> int | None:
    parts = [part.strip() for part in value.split(":", 1)]

    model_name = parts[0].lower()
    filter_name = parts[1] if len(parts) == 2 else None

    if model_name == "guilds":
        return len(bot.guilds)

    if model_name == "specialinstances":
        if filter_name:
            special_exists = await Special.objects.filter(
                name__iexact=filter_name,
            ).aexists()

            if not special_exists:
                return None

            return await BallInstance.objects.filter(
                special__name__iexact=filter_name,
            ).acount()

        return await BallInstance.objects.filter(
            special__isnull=False,
        ).acount()

    model = COUNT_MODELS.get(model_name)

    if model is None:
        return None

    queryset = model.objects.all()

    if model is BallInstance and filter_name:
        ball_exists = await Ball.objects.filter(
            country__iexact=filter_name,
        ).aexists()

        if not ball_exists:
            return None

        queryset = queryset.filter(
            ball__country__iexact=filter_name,
        )

    return await queryset.acount()


async def resolve_counts(
    text: str,
    bot: discord.Client,
) -> tuple[str, list[str]]:
    invalid: list[str] = []

    matches = list(COUNT_RE.finditer(text))

    for match in reversed(matches):
        value = match.group(1).strip()
        count = await count_model(value, bot)

        if count is None:
            invalid.append(value)
            continue

        text = text[:match.start()] + str(count) + text[match.end():]

    return text, invalid


async def resolve_emojis(
    text: str,
    bot: discord.Client,
) -> tuple[str, list[str]]:
    """
    Replace ball emoji placeholders.
    """

    names = list(dict.fromkeys(
        name.strip()
        for name in EMOJI_RE.findall(text)
    ))

    found: dict[str, str] = {}
    missing: list[str] = []

    for name in names:
        ball = await Ball.objects.filter(
            country__iexact=name,
        ).only("emoji_id").afirst()

        emoji = bot.get_emoji(ball.emoji_id) if ball else None

        if emoji:
            found[name.lower()] = str(emoji)
        else:
            missing.append(name)

    result = EMOJI_RE.sub(
        lambda match: found.get(
            match.group(1).strip().lower(),
            match.group(0),
        ),
        text,
    )

    return result, missing


async def resolve(
    text: str,
    bot: discord.Client,
) -> tuple[str, list[str]]:
    """
    Resolve all special characters in a message.
    """

    warnings: list[str] = []

    # Emojis
    text, missing_emojis = await resolve_emojis(text, bot)
    if missing_emojis:
        warnings.append(
            unknown_balls_warning(missing_emojis)
        )

    # Counts
    text, invalid_counts = await resolve_counts(text, bot)
    if invalid_counts:
        warnings.append(
            invalid_count_warning(invalid_counts)
        )

    # Times
    text, invalid_times = await resolve_times(text)
    if invalid_times:
        warnings.append(
            invalid_time_warning(invalid_times)
        )

    return text, warnings
