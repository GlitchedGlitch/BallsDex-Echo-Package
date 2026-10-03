import asyncio
import io
import logging
import re
from typing import TYPE_CHECKING, Literal

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.discord import LayoutView, View
from ballsdex.core.utils import checks
from bd_models.models import Ball
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

type Interaction = discord.Interaction["BallsDexBot"]

log = logging.getLogger("ballsdex.packages.echo")

LINE_RE = re.compile(r"\{s:line\}", re.IGNORECASE)
EMOJI_RE = re.compile(r"\{e:([^{}]+)\}", re.IGNORECASE)
PREVIEW_TIMEOUT = 120


def webhook_log(message: str):
    """Log to the webhook channel without pinging anyone mentioned in the message."""

    extra = {"webhook": {"params": {"allowed_mentions": discord.AllowedMentions.none()}}}
    log.info(message, extra=extra)

def unknown_balls_warning(names: list[str]) -> str:
    formatted = ", ".join(f"`{name}`" for name in names)
    noun = f"{settings.collectible_name}" if len(names) == 1 else f"{settings.plural_collectible_name}"
    verb = "doesn't" if len(names) == 1 else "don't"

    return (
        f"The {noun} {formatted} {verb} exist. "
        "Are you sure you typed the full name correctly? "
        "Do you still want to proceed sending the message?"
    )

class Draft:
    """
    A message ready to be sent, edited or previewed.
    Views and files can only be used once, so everything is rebuilt on every call.
    """

    def __init__(self, text: str | None, style: str | None, attachment: discord.Attachment | None, data: bytes | None):
        self.text = text
        self.style = style
        self.attachment = attachment
        self.data = data
        self.filename = re.sub(r"[^\w.\-]", "_", attachment.filename) if attachment else None

    def files(self) -> list[discord.File]:
        if not self.attachment or self.data is None or not self.filename:
            return []
        return [discord.File(io.BytesIO(self.data), filename=self.filename)]

    def attachment_item(self) -> discord.ui.Item | None:
        if not self.attachment or not self.filename:
            return None
        url = f"attachment://{self.filename}"
        if (self.attachment.content_type or "").startswith("image/"):
            return discord.ui.MediaGallery(discord.MediaGalleryItem(url))
        return discord.ui.File(url)

    def container(self, with_file: bool = True) -> discord.ui.Container:
        container = discord.ui.Container()
        segments = [s.strip() for s in LINE_RE.split(self.text or "") if s.strip()]
        for i, segment in enumerate(segments):
            if i:
                container.add_item(discord.ui.Separator(visible=True))
            container.add_item(discord.ui.TextDisplay(segment))
        if with_file and (item := self.attachment_item()):
            container.add_item(item)
        return container

    def payload(self, with_file: bool = True) -> dict:
        """Keyword arguments for `send()` / `edit()`."""
        if self.style == "Container":
            view = LayoutView(timeout=None)
            view.add_item(self.container(with_file))
            return {"view": view, "files": self.files() if with_file else []}
        if self.style == "Embed":
            return {"embed": discord.Embed(description=self.text), "files": self.files() if with_file else []}
        return {"content": self.text, "files": self.files() if with_file else []}


class Echo(commands.Cog):
    """Admin message tools."""

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.command: app_commands.Command | None = None

    async def cog_load(self):
        self.attach()

    def attach(self):
        """Register the echo command."""
        admin = self.bot.get_cog("Admin")
        group = getattr(admin, "admin", None)
        if group is None:
            log.warning("Admin cog not found, /admin echo will not be registered.")
            return

        self.command = self.make_command()
        group.app_command.add_command(self.command)
        log.info("Attached /admin echo")

    async def cog_unload(self):
        group = getattr(self.bot.get_cog("Admin"), "admin", None)
        if group is not None and self.command is not None:
            group.app_command.remove_command(self.command.name)

    async def fetch_message(self, link: str) -> tuple[discord.Message | None, str | None]:
        try:
            parts = link.strip().rstrip("/").split("/")
            channel_id, message_id = int(parts[-2]), int(parts[-1])
        except (ValueError, IndexError):
            return None, "Invalid message link. Copy it via **Copy Message Link** in Discord."
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return None, "Could not find the channel from the message link. Make sure the bot has access to it."
        try:
            return await channel.fetch_message(message_id), None
        except discord.NotFound:
            return None, "Could not find the message. Make sure the link is correct."

    def parse_channel(self, value: str) -> discord.TextChannel | None:
        value = value.strip()

        if "/channels/" in value:
            parts = value.rstrip("/").split("/")
            value = parts[-1]

        value = value.removeprefix("<#").removesuffix(">")

        try:
            channel = self.bot.get_channel(int(value))
        except ValueError:
            return None

        return channel if isinstance(channel, discord.TextChannel) else None

    async def resolve_emojis(self, text: str) -> tuple[str, list[str]]:
        """Replace known ball placeholders and return names that could not be resolved."""
        names = list(dict.fromkeys(
            name.strip()
            for name in EMOJI_RE.findall(text)
        ))

        found: dict[str, str] = {}
        missing: list[str] = []

        for name in names:
            ball = await Ball.objects.filter(
                country__iexact=name
            ).only("emoji_id").afirst()

            emoji = self.bot.get_emoji(ball.emoji_id) if ball else None

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

    async def build_draft(
        self,
        text: str | None,
        style: str | None,
        file: discord.Attachment | None,
    ) -> tuple[Draft | None, str | None, list[str]]:
        missing: list[str] = []
    
        if text:
            text, missing = await self.resolve_emojis(text)
    
        if style == "Embed" and not text:
            return None, "The Embed style needs a `message`.", missing
    
        if style == "Container":
            if not text and not file:
                return None, "The Container style needs a `message` or a `file`.", missing
            if text and not [s for s in LINE_RE.split(text) if s.strip()]:
                return None, "Your message only contains lines, add some text.", missing
    
        limit = {"Embed": 4096, "Container": 4000}.get(style or "", 2000)
        if text and len(text) > limit:
            return None, f"Your message is too long for this style ({len(text)}/{limit} characters).", missing
    
        data = await file.read() if file else None
        return Draft(text, style, file, data), None, missing


    async def confirm(
        self,
        interaction: Interaction,
        confirmation: str,
        draft: Draft,
        with_file: bool,
        warning: str | None = None,
    ) -> tuple[bool, discord.WebhookMessage]:
        """Confirm an optional warning, then optionally confirm the preview."""
        warning_message: discord.WebhookMessage | None = None

        if warning:
            warning_view = LayoutView(timeout=PREVIEW_TIMEOUT)
            warning_view.add_item(
                discord.ui.TextDisplay(warning)
            )

            warning_decision: asyncio.Future[bool] = (
                asyncio.get_running_loop().create_future()
            )

            async def warning_accept(i: Interaction):
                if not warning_decision.done():
                    warning_decision.set_result(True)
                await i.response.defer()

            async def warning_deny(i: Interaction):
                if not warning_decision.done():
                    warning_decision.set_result(False)
                await i.response.defer()

            yes = discord.ui.Button(
                emoji="✔️",
                style=discord.ButtonStyle.success,
            )
            no = discord.ui.Button(
                emoji="✖️",
                style=discord.ButtonStyle.danger,
            )

            yes.callback = warning_accept
            no.callback = warning_deny

            warning_view.add_item(
                discord.ui.ActionRow(yes, no)
            )

            warning_message = await interaction.followup.send(
                view=warning_view,
                ephemeral=True,
                wait=True,
            )

            try:
                warning_accepted = await asyncio.wait_for(
                    warning_decision,
                    timeout=PREVIEW_TIMEOUT,
                )
            except asyncio.TimeoutError:
                warning_accepted = False
            finally:
                warning_view.stop()

            if not warning_accepted:
                return False, warning_message

            if not confirmation:
                return True, warning_message

        if draft.style == "Embed":
            preview_view = View(timeout=PREVIEW_TIMEOUT)

            preview_decision: asyncio.Future[bool] = (
                asyncio.get_running_loop().create_future()
            )

            async def preview_accept(i: Interaction):
                if not preview_decision.done():
                    preview_decision.set_result(True)
                await i.response.defer()

            async def preview_deny(i: Interaction):
                if not preview_decision.done():
                    preview_decision.set_result(False)
                await i.response.defer()

            yes = discord.ui.Button(
                emoji="✔️",
                style=discord.ButtonStyle.success,
            )
            no = discord.ui.Button(
                emoji="✖️",
                style=discord.ButtonStyle.danger,
            )

            yes.callback = preview_accept
            no.callback = preview_deny

            preview_view.add_item(yes)
            preview_view.add_item(no)

            preview_message = await interaction.followup.send(
                confirmation,
                embed=discord.Embed(description=draft.text),
                view=preview_view,
                files=draft.files() if with_file else [],
                ephemeral=True,
                wait=True,
            )

            try:
                confirmed = await asyncio.wait_for(
                    preview_decision,
                    timeout=PREVIEW_TIMEOUT,
                )
            except asyncio.TimeoutError:
                confirmed = False
            finally:
                preview_view.stop()

            return confirmed, preview_message

        preview_view = LayoutView(timeout=PREVIEW_TIMEOUT)

        preview_view.add_item(
            discord.ui.TextDisplay(confirmation)
        )

        if draft.style == "Container":
            preview_view.add_item(
                draft.container(with_file)
            )
        else:
            preview_view.add_item(
                discord.ui.Separator(visible=True)
            )

            preview_view.add_item(
                discord.ui.TextDisplay(
                    draft.text or "*[file only]*"
                )
            )

            if with_file and (item := draft.attachment_item()):
                preview_view.add_item(item)

        preview_decision: asyncio.Future[bool] = (
            asyncio.get_running_loop().create_future()
        )

        async def preview_accept(i: Interaction):
            if not preview_decision.done():
                preview_decision.set_result(True)
            await i.response.defer()

        async def preview_deny(i: Interaction):
            if not preview_decision.done():
                preview_decision.set_result(False)
            await i.response.defer()

        yes = discord.ui.Button(
            emoji="✔️",
            style=discord.ButtonStyle.success,
        )
        no = discord.ui.Button(
            emoji="✖️",
            style=discord.ButtonStyle.danger,
        )

        yes.callback = preview_accept
        no.callback = preview_deny

        preview_view.add_item(
            discord.ui.ActionRow(yes, no)
        )

        if warning_message is not None:
            await warning_message.edit(
                view=preview_view,
            )
            preview_message = warning_message

        else:

            preview_message = await interaction.followup.send(
                view=preview_view,
                files=draft.files() if with_file else [],
                ephemeral=True,
                wait=True,
            )

        try:
            confirmed = await asyncio.wait_for(
                preview_decision,
                timeout=PREVIEW_TIMEOUT,
            )
        except asyncio.TimeoutError:
            confirmed = False
        finally:
            preview_view.stop()

        return confirmed, preview_message
        
    async def edit_preview_status(
        self,
        preview_message: discord.WebhookMessage,
        status: str,
        style: str | None,
        components_v2: bool = False,
    ):
        """Replace the preview contents with a final status."""

        if components_v2:
            view = LayoutView(timeout=None)
            view.add_item(discord.ui.TextDisplay(status))
            await preview_message.edit(view=view)
            return

        if style == "Embed":
            await preview_message.edit(
                content=status,
                embed=None,
                view=None,
            )
            return

        view = LayoutView(timeout=None)
        view.add_item(discord.ui.TextDisplay(status))

        await preview_message.edit(view=view)

    @staticmethod
    def describe(
        action: str,
        style: str | None,
        mention: bool,
        target: str | None = None,
        reply: discord.Message | None = None,
        edit: discord.Message | None = None,
        file: discord.Attachment | None = None,
    ) -> str:
        parts = [f"Style: {style or 'Text'}", f"Mentions: {mention}"]
        if edit:
            parts.append(f"Editing: {edit.jump_url}")
        if reply:
            parts.append(f"Replying: {reply.jump_url}")
        if target:
            parts.append(f"Channel: {target}")
        if file:
            parts.append(f"File: {file.filename}")
        return f"Are you sure you want to {action} this message? " + " | ".join(parts)

    def make_command(self) -> app_commands.Command:
        """Build the echo slash command."""
        cog = self

        @app_commands.command()
        @checks.is_staff()
        async def echo(
            interaction: Interaction,
            message: str | None = None,
            file: discord.Attachment | None = None,
            style: Literal["Embed", "Container"] | None = None,
            channel: str | None = None,
            dm: discord.User | None = None,
            reply: str | None = None,
            edit_message: str | None = None,
            delete_message: str | None = None,
            mention: bool = True,
            preview: bool = False,
        ):
            """
            Send, edit, delete or reply to messages as the bot.

            Parameters
            ----------
            message: str | None
                The message text.
            file: discord.Attachment | None
                A file to attach.
            style: Literal["Embed", "Container"] | None
                How the message is displayed. Leave empty for plain text.
            channel: str | None
                Channel to send to.
            dm: discord.User | None
                User to send the message to via DM (ignores channel parameter).
            reply: str | None
                Message link to reply to when sending.
            edit_message: str | None
                Message link to edit instead of sending a new message.
            delete_message: str | None
                Message link of the bot message to delete.
            mention: bool
                Whether pings and replies actually notify users and roles.
            preview: bool
                Preview the message privately and confirm before it is sent.
            """
                
            bot = cog.bot
            if not message and not file and not edit_message and not delete_message:
                await interaction.response.send_message(
                    "You must provide at least a message, a file, "
                    "an edit_message link, or a delete_message link.",
                    ephemeral=True,
                )
                return
            

            await interaction.response.defer(ephemeral=True)
            allowed = discord.AllowedMentions.all() if mention else discord.AllowedMentions.none()


            if delete_message:
                del_msg, err = await cog.fetch_message(delete_message)
                if err or del_msg is None:
                    await interaction.followup.send(err or "Message not found.", ephemeral=True)
                    return
                if del_msg.author.id != bot.user.id:  # type: ignore
                    await interaction.followup.send("I can only delete my own messages.", ephemeral=True)
                    return
                try:
                    jump_url = del_msg.jump_url
                    preview_text = (del_msg.content or "[no text content]")[:200]
                    await del_msg.delete()
                    await interaction.followup.send("Message deleted!", ephemeral=True)
                    webhook_log(
                        f"{interaction.user} deleted a message in #{del_msg.channel} {jump_url} "
                        f"| Message: {preview_text!r}"
                    )
                except discord.Forbidden:
                    await interaction.followup.send("Missing permissions to delete that message.", ephemeral=True)
                except Exception as error:
                    await interaction.followup.send(f"Error:\n```py\n{error}\n```", ephemeral=True)
                return

            target = None
            if not dm:
                if channel is not None:
                    target = cog.parse_channel(channel)
                    if target is None:
                        await interaction.followup.send(
                            "Could not find that channel. Make sure you're using a valid channel ID "
                            "or #channel and that the bot has access to it.",
                            ephemeral=True,
                        )
                        return
                else:
                    target = interaction.channel  # type: ignore

            edit_msg: discord.Message | None = None
            if edit_message:
                if not message:
                    await interaction.followup.send(
                        "You must provide `message` with the new content when editing.", ephemeral=True
                    )
                    return
                edit_msg, err = await cog.fetch_message(edit_message)
                if err or edit_msg is None:
                    await interaction.followup.send(err or "Message not found.", ephemeral=True)
                    return
                if edit_msg.author.id != bot.user.id:  # type: ignore
                    await interaction.followup.send("I can only edit my own messages.", ephemeral=True)
                    return
                if edit_msg.flags.components_v2 and style != "Container":
                    await interaction.followup.send(
                        "That message is a container message, it can only be edited with the Container style.",
                        ephemeral=True,
                    )
                    return

            reply_msg: discord.Message | None = None
            if reply and not edit_msg:
                reply_msg, err = await cog.fetch_message(reply)
                if err:
                    await interaction.followup.send(err, ephemeral=True)
                    return

            draft, err, missing_balls = await cog.build_draft(
                message,
                style,
                None if edit_msg else file,
            )
            if err or draft is None:
                await interaction.followup.send(err or "Could not build the message.", ephemeral=True)
                return

            preview_message = None

            action = "edit" if edit_msg else "send"
            where = f"DM to {dm.mention}" if dm else getattr(target, "mention", None)

            confirmation = cog.describe(
                action,
                style,
                mention,
                where,
                reply_msg,
                edit_msg,
                None if edit_msg else file,
            )

            if missing_balls or preview:
                warning = (
                    unknown_balls_warning(missing_balls)
                    if missing_balls
                    else None
                )

                confirmed, preview_message = await cog.confirm(
                    interaction,
                    confirmation if preview else "",
                    draft,
                    with_file=not edit_msg,
                    warning=warning,
                )

                if not confirmed:
                    await cog.edit_preview_status(
                        preview_message,
                        "Cancelled, nothing was sent.",
                        style,
                    )
                    return

            if edit_msg:
                try:
                    previous = (edit_msg.content or "[no text content]")[:200]
                    kwargs = draft.payload(with_file=False)
                    kwargs.pop("files")

                    if style == "Container":
                        await edit_msg.edit(
                            content=None,
                            embed=None,
                            allowed_mentions=allowed,
                            **kwargs,
                        )
                    elif style == "Embed":
                        await edit_msg.edit(
                            content=None,
                            allowed_mentions=allowed,
                            **kwargs,
                        )
                    else:
                        await edit_msg.edit(
                            embed=None,
                            allowed_mentions=allowed,
                            **kwargs,
                        )

                    if preview_message:
                        await cog.edit_preview_status(
                            preview_message,
                            "Message edited!",
                            style,
                        )
                    else:
                        await interaction.followup.send(
                            "Message edited!",
                            ephemeral=True,
                        )
                    parts = [
                        f"{interaction.user} edited a message in #{edit_msg.channel} {edit_msg.jump_url}",
                        f"Message: {draft.text!r}",
                        f"Style: {style or 'Text'}",
                        f"Mentions: {mention}",
                        f"Previous message: {previous!r}",
                    ]
                    webhook_log(" | ".join(parts))
                except discord.Forbidden:
                    await interaction.followup.send("Missing permissions to edit that message.", ephemeral=True)
                except Exception as error:
                    await interaction.followup.send(f"Error:\n```py\n{error}\n```", ephemeral=True)
                return

            if dm:
                try:
                    await dm.send(allowed_mentions=allowed, **draft.payload())
                    
                    if preview_message:
                        await cog.edit_preview_status(
                            preview_message,
                            f"DM sent to **{dm}**!",
                            style,
                        )
                    else:
                        await interaction.followup.send(
                            f"DM sent to **{dm}**!",
                            ephemeral=True,
                        )
                    parts = [
                        f"{interaction.user} sent a DM to {dm} ({dm.id}).",
                        f"Message: {draft.text!r}" if draft.text else "Message: [file only]",
                        f"Style: {style or 'Text'}",
                        f"Mentions: {mention}",
                    ]
                    if file:
                        parts.append(f"File: {file.filename} {file.url}")
                    webhook_log(" | ".join(parts))
                except discord.HTTPException as error:
                    if error.code == 50007:
                        await interaction.followup.send(
                            f"Could not DM **{dm}** - they may have DMs disabled.", ephemeral=True
                        )
                    elif error.code == 50278:
                        await interaction.followup.send(
                            f"Could not DM **{dm}** because the bot does not share any mutual servers.",
                            ephemeral=True,
                        )
                    else:
                        await interaction.followup.send(f"Error:\n```py\n{error}\n```", ephemeral=True)
                except Exception as error:
                    await interaction.followup.send(f"Error:\n```py\n{error}\n```", ephemeral=True)
                return

            try:
                sent = await target.send(
                    allowed_mentions=allowed,
                    reference=reply_msg,
                    **draft.payload(),
                )
                
                if preview_message:
                    await cog.edit_preview_status(
                        preview_message,
                        "Message sent!",
                        style,
                    )
                else:
                    await interaction.followup.send(
                        "Message sent!",
                        ephemeral=True,
                    )
                parts = [
                    f"{interaction.user} sent a message in #{target} {sent.jump_url}",
                    f"Message: {draft.text!r}" if draft.text else "Message: [file only]",
                    f"Style: {style or 'Text'}",
                    f"Mentions: {mention}",
                ]
                if file:
                    parts.append(f"File: {file.filename} {file.url}")
                if reply_msg:
                    parts.append(f"Replied to: {reply_msg.jump_url}")
                webhook_log(" | ".join(parts))
            except discord.Forbidden:
                await interaction.followup.send(
                    f"Missing permissions to send in {getattr(target, 'mention', target)}.", ephemeral=True
                )
            except Exception as error:
                await interaction.followup.send(f"Error:\n```py\n{error}\n```", ephemeral=True)
            
        @echo.autocomplete("channel")
        async def channel_autocomplete(
            interaction: Interaction,
            current: str,
        ) -> list[app_commands.Choice[str]]:
            guild = interaction.guild
            if guild is None:
                return []

            current = current.lower().strip()

            channels = [
                ch
                for ch in guild.channels
                if isinstance(ch, discord.TextChannel)
                and (
                    not current
                    or current in ch.name.lower()
                    or current in str(ch.id)
                )
            ]

            return [
                app_commands.Choice(
                    name=f"#{ch.name}",
                    value=str(ch.id),
                )
                for ch in channels[:25]
            ]

        return echo
