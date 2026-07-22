"""
Echo package for BallsDex v3
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.utils import checks

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.echo")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_message_link(link: str) -> tuple[int, int] | None:
    try:
        parts = link.strip().rstrip("/").split("/")
        return int(parts[-2]), int(parts[-1])
    except (ValueError, IndexError):
        return None


def _parse_channel(bot: "BallsDexBot", value: str) -> discord.TextChannel | None:
    raw = value.strip().lstrip("<#").rstrip(">")
    try:
        channel_id = int(raw)
    except ValueError:
        return None
    channel = bot.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel
    return None


async def _fetch_message(
    bot: "BallsDexBot", link: str
) -> tuple[discord.Message | None, str | None]:
    parsed = _parse_message_link(link)
    if not parsed:
        return None, "Invalid message link. Copy it via **Copy Message Link** in Discord."
    channel_id, message_id = parsed
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return None, (
            "Could not find the channel from the message link. "
            "Make sure the bot has access to it."
        )
    try:
        msg = await channel.fetch_message(message_id)
        return msg, None
    except discord.NotFound:
        return None, "Could not find the message. Make sure the link is correct."


# ── Cog ───────────────────────────────────────────────────────────────────────

class EchoCog(commands.Cog):
    """Echo package — admin message tools."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot


# ── Command factory ───────────────────────────────────────────────────────────

def EchoAdminCommand(bot: "BallsDexBot", name: str = "echo") -> app_commands.Command:
    """
    Returns the echo slash command with the given name.
    Called by __init__.py setup() so the name can be customised.
    """

    @app_commands.command(
        name=name,
        description="Send, edit, delete or reply to messages as the bot",
    )
    @checks.is_staff()
    @app_commands.describe(
        message="The text content to send or use when editing",
        file="A file to attach",
        embed="Wrap the message text in an embed",
        channel="Channel ID or <#mention> to send to — works cross-server (default: current channel)",
        dm="User to send the message to via DM (ignores channel parameter)",
        reply="Message link to reply to when sending",
        edit_message="Message link to edit instead of sending a new message",
        delete_message="Message link of the bot message to delete",
    )
    async def echo(
        interaction: discord.Interaction,
        message: str | None = None,
        file: discord.Attachment | None = None,
        embed: bool = False,
        channel: str | None = None,
        dm: discord.User | None = None,
        reply: str | None = None,
        edit_message: str | None = None,
        delete_message: str | None = None,
    ):
        if not message and not file and not edit_message and not delete_message:
            await interaction.response.send_message(
                "You must provide at least a `message`, a `file`, "
                "an `edit_message` link, or a `delete_message` link.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # ── Delete mode ───────────────────────────────────────────────────────
        if delete_message:
            del_msg, err = await _fetch_message(bot, delete_message)
            if err:
                await interaction.followup.send(err, ephemeral=True)
                return
            if del_msg.author.id != bot.user.id:  # type: ignore
                await interaction.followup.send(
                    "I can only delete my own messages.", ephemeral=True
                )
                return
            try:
                jump_url = del_msg.jump_url
                preview = (del_msg.content or "[no text content]")[:200]
                await del_msg.delete()
                await interaction.followup.send("Message deleted!", ephemeral=True)
                log.info(
                    f"{interaction.user} deleted a message in "
                    f"#{del_msg.channel} {jump_url} | Message: {preview!r}",
                    extra={"webhook": True},
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    "Missing permissions to delete that message.", ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(f"Error:\n```py\n{e}\n```", ephemeral=True)
            return

        # ── DM mode ───────────────────────────────────────────────────────────
        if dm:
            kwargs: dict = {}
            if embed:
                kwargs["embed"] = discord.Embed(description=message or "")
            elif message:
                kwargs["content"] = message
            if file:
                kwargs["files"] = [await file.to_file()]
            try:
                await dm.send(**kwargs)
                await interaction.followup.send(f"DM sent to **{dm}**!", ephemeral=True)
                parts = [
                    f"{interaction.user} sent a DM to {dm} ({dm.id}).",
                    f"Message: {message!r}" if message else "Message: [file only]",
                ]
                if file:
                    parts.append(f"File: {file.filename} {file.url}")
                if embed:
                    parts.append("Embed: True")
                log.info(" | ".join(parts), extra={"webhook": True})
            except discord.HTTPException as e:
                if e.code == 50007:
                    await interaction.followup.send(
                        f"Could not DM **{dm}** - they may have DMs disabled.",
                        ephemeral=True,
                    )
                elif e.code == 50278:
                    await interaction.followup.send(
                        f"Could not DM **{dm}** because the bot does not share any mutual servers.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"Error:\n```py\n{e}\n```", ephemeral=True
                    )
            except Exception as e:
                await interaction.followup.send(f"Error:\n```py\n{e}\n```", ephemeral=True)
            return

        # ── Resolve channel ───────────────────────────────────────────────────
        if channel is not None:
            target = _parse_channel(bot, channel)
            if target is None:
                await interaction.followup.send(
                    "Could not find that channel. Make sure you're using a valid channel ID "
                    "or `<#mention>` and that the bot has access to it.",
                    ephemeral=True,
                )
                return
        else:
            target = interaction.channel  # type: ignore

        # ── Edit mode ─────────────────────────────────────────────────────────
        if edit_message:
            if not message:
                await interaction.followup.send(
                    "You must provide `message` with the new content when editing.",
                    ephemeral=True,
                )
                return
            edit_msg, err = await _fetch_message(bot, edit_message)
            if err:
                await interaction.followup.send(err, ephemeral=True)
                return
            if edit_msg.author.id != bot.user.id:  # type: ignore
                await interaction.followup.send(
                    "I can only edit my own messages.", ephemeral=True
                )
                return
            try:
                prev_content = (edit_msg.content or "[no text content]")[:200]
                if embed:
                    await edit_msg.edit(content=None, embed=discord.Embed(description=message))
                else:
                    await edit_msg.edit(content=message, embed=None)
                await interaction.followup.send("Message edited!", ephemeral=True)
                parts = [
                    f"{interaction.user} edited a message in "
                    f"#{edit_msg.channel} {edit_msg.jump_url}",  # type: ignore
                    f"Message: {message!r}",
                ]
                if embed:
                    parts.append("Embed: True")
                parts.append(f"Previous message: {prev_content!r}")
                log.info(" | ".join(parts), extra={"webhook": True})
            except discord.Forbidden:
                await interaction.followup.send(
                    "Missing permissions to edit that message.", ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(f"Error:\n```py\n{e}\n```", ephemeral=True)
            return

        # ── Send mode ─────────────────────────────────────────────────────────
        reply_msg: discord.Message | None = None
        if reply:
            reply_msg, err = await _fetch_message(bot, reply)
            if err:
                await interaction.followup.send(err, ephemeral=True)
                return

        kwargs: dict = {}
        if embed:
            kwargs["embed"] = discord.Embed(description=message or "")
        elif message:
            kwargs["content"] = message
        if file:
            kwargs["files"] = [await file.to_file()]
        if reply_msg:
            kwargs["reference"] = reply_msg
            kwargs["mention_author"] = False

        try:
            sent_msg = await target.send(**kwargs)
            await interaction.followup.send("Message sent!", ephemeral=True)
            parts = [
                f"{interaction.user} sent a message in #{target} {sent_msg.jump_url}",
                f"Message: {message!r}" if message else "Message: [file only]",
            ]
            if file:
                parts.append(f"File: {file.filename} {file.url}")
            if embed:
                parts.append("Embed: True")
            if reply_msg:
                parts.append(f"Replied to: {reply_msg.jump_url}")
            log.info(" | ".join(parts), extra={"webhook": True})
        except discord.Forbidden:
            await interaction.followup.send(
                f"Missing permissions to send in {target.mention}.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"Error:\n```py\n{e}\n```", ephemeral=True)

    echo._is_echo = True  # type: ignore
    return echo 
