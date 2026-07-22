"""
Echo Package Installer v3
"""

import io, os, re, traceback, discord
from discord.ui import View, Button, Modal, TextInput

REPO        = "GlitchedGlitch/BallsDex-Echo-Package"
BRANCH      = "1.0.0#main"
GIT_URL     = f"git+https://github.com/{REPO}.git@{BRANCH}"
APP_PATH    = "echo"
TOML_MARKER = f'path = "{APP_PATH}"'
TOML_ENTRY  = (
    "\n\n# Echo Package\n"
    "[[ballsdex.packages]]\n"
    f'location = "{GIT_URL}"\n'
    f'path = "{APP_PATH}"\n'
    "enabled = true"
)

EXTRA_TOML  = "/code/admin_panel/config/extra.toml"
NAME_FILE   = "/code/admin_panel/config/echo_name.txt"
DEFAULT_NAME = "echo"

FOOTER         = "Ultimate BallsDex Library Extensions • by Glitch (@glitchy.glitch)"
FOOTER_TIMEOUT = FOOTER + " • Timed out"
BAR_FILLED, BAR_EMPTY, BAR_LEN = "█", "░", 10


# ── Name helpers ──────────────────────────────────────────────────────────────

def _get_command_name() -> str:
    try:
        with open(NAME_FILE) as f:
            name = f.read().strip()
            return name if name else DEFAULT_NAME
    except FileNotFoundError:
        return DEFAULT_NAME


def _save_command_name(name: str) -> None:
    os.makedirs(os.path.dirname(NAME_FILE), exist_ok=True)
    with open(NAME_FILE, "w") as f:
        f.write(name.strip())


# ── extra.toml helpers ────────────────────────────────────────────────────────

def _toml_has_entry() -> bool:
    try:
        if not os.path.isfile(EXTRA_TOML):
            return False
        with open(EXTRA_TOML) as f:
            return TOML_MARKER in f.read()
    except OSError:
        return False


def _write_toml():
    os.makedirs(os.path.dirname(EXTRA_TOML), exist_ok=True)
    if os.path.isfile(EXTRA_TOML):
        with open(EXTRA_TOML) as f:
            contents = f.read()
        if TOML_MARKER in contents:
            return
        with open(EXTRA_TOML, "a") as f:
            f.write(TOML_ENTRY)
    else:
        with open(EXTRA_TOML, "w") as f:
            f.write(TOML_ENTRY.lstrip())


def _remove_toml():
    if not os.path.isfile(EXTRA_TOML):
        return
    with open(EXTRA_TOML) as f:
        contents = f.read()
    cleaned = re.sub(
        r"\n?# Echo Package\n\[\[ballsdex\.packages\]\][^\[]*path\s*=\s*\"echo\"[^\[]*",
        "", contents, flags=re.DOTALL,
    )
    with open(EXTRA_TOML, "w") as f:
        f.write(cleaned)


def is_installed() -> bool:
    return _toml_has_entry()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bar(current: int, total: int) -> str:
    filled = round(BAR_LEN * current / total)
    return f"`{BAR_FILLED * filled}{BAR_EMPTY * (BAR_LEN - filled)}` {round(100 * current / total)}%"


def _progress_embed(title: str, steps: list, color: discord.Color) -> discord.Embed:
    done  = sum(1 for _, s in steps if s is True)
    icons = {None: "⬜", True: "✅", False: "❌"}
    lines = [f"{icons[s]} {label}" for label, s in steps]
    e = discord.Embed(title=title, description="\n".join(lines) + f"\n\n{_bar(done, len(steps))}", color=color)
    e.set_footer(text=FOOTER)
    return e


# ── Embeds ────────────────────────────────────────────────────────────────────

def build_main_embed(installed: bool, color: discord.Color, cmd_name: str) -> discord.Embed:
    status = "✅ Registered in `extra.toml` — rebuild to activate" if installed else "❌ Not installed"
    e = discord.Embed(
        title="Echo Package",
        description=(
            "Adds an admin echo command to your BallsDex instance.\n\n"
            "**Commands**\n"
            f"• `/admin {cmd_name}` — send, edit, delete or reply to messages as the bot\n\n"
            "**Parameters**\n"
            "• `message` — text content to send or edit with\n"
            "• `file` — file attachment to include\n"
            "• `embed` — wrap message in an embed\n"
            "• `channel` — target channel (works cross-server)\n"
            "• `dm` — DM a specified user\n"
            "• `reply` — message link to reply to\n"
            "• `edit_message` — message link to edit instead of sending\n"
            "• `delete_message` — message link to delete\n\n"
            f"**Command name:** `/admin {cmd_name}`\n"
            f"**Status:** {status}"
        ),
        color=color,
    )
    e.set_footer(text=FOOTER)
    return e


def build_warning_embed() -> discord.Embed:
    e = discord.Embed(
        title="⚠️ Before Installing — Required Setup",
        description=(
            "The installer needs to write to `config/extra.toml`. "
            "By default Docker mounts this folder as **read-only**, "
            "so you must edit your `docker-compose.yml` first.\n\n"
            "**Find these two lines** in both the `bot` and `admin-panel` services "
            "and change `:ro` to `:rw`:\n"
            "```yaml\n"
            "- \"./config:/code/admin_panel/config:rw\"\n"
            "- \"./extra:/code/extra:rw\"\n"
            "```\n"
            "Then restart your containers:\n"
            "```\ndocker compose down\ndocker compose build\ndocker compose up -d\n```\n\n"
            "Once done, click **Confirm Install** below.\n"
            "If you have already done this, you can proceed immediately."
        ),
        color=discord.Color.orange(),
    )
    e.set_footer(text=FOOTER)
    return e


def build_confirm_remove_embed() -> discord.Embed:
    e = discord.Embed(
        title="Remove Echo Package",
        description=(
            "⚠️ **Are you sure?**\n\n"
            "This will remove the entry from `config/extra.toml`.\n"
            "The package will stop loading after the next rebuild.\n\n"
            "The command name setting will be preserved."
        ),
        color=discord.Color.orange(),
    )
    e.set_footer(text=FOOTER)
    return e


def build_error_embed(action: str, error: str) -> discord.Embed:
    short = error[:1000] + "..." if len(error) > 1000 else error
    e = discord.Embed(
        title="An error occurred",
        description=f"An error occurred when **{action}** the package!\n\n```\n{short}\n```\n\nFull error attached below.",
        color=discord.Color.red(),
    )
    e.set_footer(text=FOOTER)
    return e


def build_result_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    e.set_footer(text=FOOTER)
    return e


# ── Rename modal ──────────────────────────────────────────────────────────────

class CommandNameModal(Modal, title="Set Echo Command Name"):
    name_input = TextInput(
        label="Command name (group is always /admin)",
        placeholder="echo",
        min_length=1,
        max_length=32,
        required=True,
    )

    def __init__(self, parent: "EchoInstallerView"):
        super().__init__()
        self.parent = parent
        self.name_input.default = self.parent.cmd_name

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.name_input.value.strip().lower().replace(" ", "-")
        if not re.match(r"^[a-z0-9\-]{1,32}$", raw):
            await interaction.response.send_message(
                "Invalid name. Use only lowercase letters, numbers and hyphens.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        if not self.parent.installed:
            # Not installed yet — just update the preview name
            self.parent.cmd_name = raw
            _save_command_name(raw)
            await self.parent.message.edit(
                embed=build_main_embed(False, discord.Color.greyple(), raw),
                view=self.parent,
            )
            return

        # Installed — save the name so it takes effect on next rebuild
        old_name = self.parent.cmd_name
        _save_command_name(raw)
        self.parent.cmd_name = raw
        self.parent.done = True
        self.parent.stop()
        await self.parent.message.edit(
            embed=build_result_embed(
                "Command Name Updated",
                (
                    f"The command name has been changed from `{old_name}` to `{raw}`.\n\n"
                    "Rebuild and restart for the change to take effect:\n"
                    "```\ndocker compose build\ndocker compose up -d\n```\n"
                    "After the rebuild it will appear as `/admin {raw}`."
                ).replace("{raw}", raw),
                discord.Color.blurple(),
            ),
            view=None,
        )


# ── Warning gate ──────────────────────────────────────────────────────────────

class InstallWarningView(View):
    def __init__(self, parent: "EchoInstallerView"):
        super().__init__(timeout=120)
        self.parent = parent

    async def on_timeout(self):
        if not self.parent.done:
            color = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
            await self.parent.message.edit(
                embed=build_main_embed(self.parent.installed, color, self.parent.cmd_name),
                view=self.parent,
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm Install", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        steps = [("Writing to config/extra.toml", None)]

        async def update(i: int, success: bool = True):
            steps[i] = (steps[i][0], success)
            await self.parent.message.edit(
                embed=_progress_embed("Installing Echo Package…", steps, discord.Color.blurple()),
                view=None,
            )

        await self.parent.message.edit(
            embed=_progress_embed("Installing Echo Package…", steps, discord.Color.blurple()),
            view=None,
        )

        try:
            _write_toml()
            _save_command_name(self.parent.cmd_name)
            await update(0)
            self.parent.installed = True
            self.parent._update_buttons()
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Entry Added — Rebuild Required",
                    f"Added to `config/extra.toml` with command name `/admin {self.parent.cmd_name}`.\n\n"
                    "Now rebuild and restart your bot to finish the install:\n"
                    "```\ndocker compose build\ndocker compose up -d\n```\n"
                    "After the rebuild, and also after running `[p].admin syncslash`, `echo` will appear in the packages loaded log.\n\n"
                    "Use the **Rename** button before installing to change the command name.",
                    discord.Color.green(),
                ),
                view=None,
            )
        except OSError as e:
            self.parent.done = True
            self.stop()
            steps[0] = (steps[0][0], False)
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Permission Denied",
                    f"Could not write to `config/extra.toml` — the folder is still **read-only** (`{e.strerror}`).\n\n"
                    "Make sure you edited `docker-compose.yml` and restarted the containers first:\n"
                    "```yaml\n- \"./config:/code/admin_panel/config:rw\"\n- \"./extra:/code/extra:rw\"\n```\n"
                    "```\ndocker compose down\ndocker compose build\ndocker compose up -d\n```\n"
                    "Then run the installer eval again.",
                    discord.Color.red(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.parent.done = True
            self.stop()
            steps[0] = (steps[0][0], False)
            await self.parent.message.edit(embed=build_error_embed("installing", err), view=None)
            await interaction.followup.send(
                file=discord.File(io.BytesIO(err.encode()), filename="install_error.txt")
            )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        color = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
        await self.parent.message.edit(
            embed=build_main_embed(self.parent.installed, color, self.parent.cmd_name),
            view=self.parent,
        )


# ── Confirm remove ────────────────────────────────────────────────────────────

class ConfirmRemoveView(View):
    def __init__(self, parent: "EchoInstallerView"):
        super().__init__(timeout=60)
        self.parent = parent

    async def on_timeout(self):
        if not self.parent.done:
            color = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
            await self.parent.message.edit(
                embed=build_main_embed(self.parent.installed, color, self.parent.cmd_name),
                view=self.parent,
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, remove it", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        try:
            _remove_toml()
            self.parent.installed = False
            self.parent._update_buttons()
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(
                embed=build_result_embed(
                    "Entry Removed",
                    "Removed from `config/extra.toml`.\n\n"
                    "Rebuild to fully uninstall:\n"
                    "```\ndocker compose build\ndocker compose up -d\n```\n"
                    "The command name setting has been preserved.",
                    discord.Color.red(),
                ),
                view=None,
            )
        except Exception:
            err = traceback.format_exc()
            self.parent.done = True
            self.stop()
            await self.parent.message.edit(embed=build_error_embed("removing", err), view=None)
            await interaction.followup.send(
                file=discord.File(io.BytesIO(err.encode()), filename="remove_error.txt")
            )

    @discord.ui.button(label="No, go back", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        color = discord.Color.gold() if self.parent.installed else discord.Color.greyple()
        await self.parent.message.edit(
            embed=build_main_embed(self.parent.installed, color, self.parent.cmd_name),
            view=self.parent,
        )


# ── Main installer view ───────────────────────────────────────────────────────

class EchoInstallerView(View):
    def __init__(self, bot, ctx, installed: bool, cmd_name: str):
        super().__init__(timeout=180)
        self.bot = bot; self.ctx = ctx
        self.installed = installed
        self.cmd_name = cmd_name
        self.done = False; self.message = None
        self._update_buttons()

    def _update_buttons(self):
        for c in self.children:
            if c.label == "Install":
                c.disabled = self.installed
            elif c.label == "Remove":
                c.disabled = not self.installed

    async def on_timeout(self):
        if self.done: return
        for c in self.children: c.disabled = True
        if self.message:
            embed = build_main_embed(self.installed, discord.Color.dark_grey(), self.cmd_name)
            embed.set_footer(text=FOOTER_TIMEOUT)
            await self.message.edit(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Install", style=discord.ButtonStyle.success, emoji="📥")
    async def install_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.message.edit(embed=build_warning_embed(), view=InstallWarningView(self))

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def rename_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(CommandNameModal(self))

    @discord.ui.button(label="Remove", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def remove_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        await self.message.edit(embed=build_confirm_remove_embed(), view=ConfirmRemoveView(self))


# ── Entry point ───────────────────────────────────────────────────────────────

def _is_v2() -> bool:
    try:
        from django.apps import apps
        apps.check_apps_ready()
        return False
    except Exception:
        pass
    try:
        import tortoise  # noqa: F401
        return True
    except ImportError:
        pass
    return False

if _is_v2():
    await ctx.send(
        embed=discord.Embed(
            title="Incompatible Version",
            description=(
                "This installer is for **BallsDex v3** only.\n\n"
                "Your instance appears to be running **v2**.\n\n"
                "Please use the **v2 branch** of this package instead, or update "
                "to v3 before installing."
            ),
            color=discord.Color.red(),
        ).set_footer(text=FOOTER)
    )
else:
    installed = is_installed()
    cmd_name  = _get_command_name()
    view      = EchoInstallerView(bot, ctx, installed, cmd_name)
    color     = discord.Color.gold() if installed else discord.Color.greyple()
    message   = await ctx.send(embed=build_main_embed(installed, color, cmd_name), view=view)
    view.message = message 
