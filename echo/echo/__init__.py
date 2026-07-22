from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from .cog import EchoCog, EchoAdminCommand

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.echo")

_NAME_FILE = "/code/admin_panel/config/echo_name.txt"
_DEFAULT_NAME = "echo"


def _get_command_name() -> str:
    try:
        with open(_NAME_FILE) as f:
            name = f.read().strip()
            return name if name else _DEFAULT_NAME
    except FileNotFoundError:
        return _DEFAULT_NAME


def save_command_name(name: str) -> None:
    with open(_NAME_FILE, "w") as f:
        f.write(name.strip())


async def setup(bot: "BallsDexBot") -> None:
    await bot.add_cog(EchoCog(bot))
    log.info("EchoCog loaded")

    command_name = _get_command_name()

    admin_cog = bot.cogs.get("Admin")
    if admin_cog is not None and hasattr(admin_cog, "admin"):
        try:
            
            for cmd in list(admin_cog.admin.app_command.commands):
                if isinstance(cmd, admin_cog.admin.app_command.__class__.__mro__[0]) or True:
                    if getattr(cmd, "_is_echo", False):
                        admin_cog.admin.app_command.remove_command(cmd.name)
                        log.debug("Removed stale echo command '%s'", cmd.name)

            cmd = EchoAdminCommand(bot, name=command_name)
            admin_cog.admin.app_command.add_command(cmd)
            log.info("Attached /admin %s to Admin cog", command_name)
        except Exception:
            log.warning("Failed to attach /admin %s", command_name, exc_info=True)
    else:
        log.warning(
            "Admin cog not found — /admin %s will not be registered.", command_name
        )


async def teardown(bot: "BallsDexBot") -> None:
    admin_cog = bot.cogs.get("Admin")
    if admin_cog is not None and hasattr(admin_cog, "admin"):
        try:
            for cmd in list(admin_cog.admin.app_command.commands):
                if getattr(cmd, "_is_echo", False):
                    admin_cog.admin.app_command.remove_command(cmd.name)
        except Exception:
            pass
