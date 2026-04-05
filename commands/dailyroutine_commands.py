import asyncio
import logging
from typing import Any

import discord
import requests
from discord import app_commands

from config import (
    DAILY_ROUTINE_API_TOKEN,
    DAILY_ROUTINE_BASE_URL,
    DAILY_ROUTINE_EXECUTE_BY_DEFAULT,
    DAILY_ROUTINE_REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


class DailyRoutineApiError(RuntimeError):
    """Raised when the DailyRoutine API request cannot be completed."""


class DailyRoutineClient:
    def __init__(self):
        self.base_url = DAILY_ROUTINE_BASE_URL.rstrip("/")
        self.api_token = DAILY_ROUTINE_API_TOKEN.strip()
        self.timeout = DAILY_ROUTINE_REQUEST_TIMEOUT

    @property
    def agent_plan_url(self) -> str:
        return f"{self.base_url}/api/discord/agent-plan"

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_token)

    async def ask(
        self,
        *,
        prompt: str,
        execute: bool,
        interaction: discord.Interaction,
        request_suffix: str = "main",
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise DailyRoutineApiError(
                "DailyRoutine is not configured on this bot yet. "
                "Set DAILY_ROUTINE_BASE_URL and DAILY_ROUTINE_API_TOKEN in the bot environment."
            )

        return await asyncio.to_thread(
            self._ask_sync,
            prompt=prompt,
            execute=execute,
            interaction=interaction,
            request_suffix=request_suffix,
        )

    def _ask_sync(
        self,
        *,
        prompt: str,
        execute: bool,
        interaction: discord.Interaction,
        request_suffix: str,
    ) -> dict[str, Any]:
        request_id = f"{interaction.id}:{request_suffix}"
        payload = {
            "prompt": prompt,
            "execute": execute,
            "source": "discord",
            "discord_user_id": str(interaction.user.id),
            "discord_channel_id": str(interaction.channel_id),
            "discord_guild_id": str(interaction.guild_id or ""),
        }
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "X-Discord-Request-Id": request_id,
        }

        try:
            response = requests.post(
                self.agent_plan_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise DailyRoutineApiError(
                "I could not reach DailyRoutine right now."
            ) from error

        try:
            data = response.json()
        except ValueError:
            data = {"error": response.text[:400] or "Unknown API error"}

        if response.status_code >= 400:
            raise DailyRoutineApiError(
                str(data.get("error") or data.get("message") or "DailyRoutine returned an error.")
            )

        return data


def _trim(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _summarize_commands(commands: list[dict[str, Any]]) -> str:
    if not commands:
        return "No command steps were planned."

    lines = []
    for index, command in enumerate(commands[:5], start=1):
        command_type = _trim(command.get("type") or "unknown", 48)
        details = []
        for key in ("title", "description", "event_title", "when", "status"):
            value = command.get(key)
            if isinstance(value, str) and value.strip():
                details.append(_trim(value.strip(), 48))
                break
        line = f"{index}. `{command_type}`"
        if details:
            line += f" - {details[0]}"
        lines.append(line)

    if len(commands) > 5:
        lines.append(f"…and {len(commands) - 5} more.")

    return "\n".join(lines)


def _build_result_embed(
    *,
    prompt: str,
    result: dict[str, Any],
    executed: bool,
) -> discord.Embed:
    speech = _trim(result.get("speech") or result.get("reply") or "Done.", 3500)
    title = "DailyRoutine executed" if executed else "DailyRoutine preview"
    color = 0x3AA675 if executed else 0x4F7FF7
    embed = discord.Embed(title=title, description=speech, color=color)
    embed.add_field(name="Prompt", value=_trim(prompt, 1024), inline=False)

    commands = result.get("commands")
    if isinstance(commands, list):
        embed.add_field(
            name="Planned actions",
            value=_trim(_summarize_commands(commands), 1024),
            inline=False,
        )

    executions = result.get("executions")
    if executed and isinstance(executions, list) and executions:
        execution_lines = []
        for item in executions[:4]:
            execution_lines.append(
                f"`{_trim(item.get('command_type') or 'unknown', 40)}` - "
                f"{_trim(item.get('speech') or 'Done.', 120)}"
            )
        embed.add_field(
            name="Completed",
            value=_trim("\n".join(execution_lines), 1024),
            inline=False,
        )

    provider = _trim(result.get("provider") or "unknown", 64)
    footer = f"Provider: {provider}"
    if not executed:
        footer += " • Use Run plan to apply changes."
    embed.set_footer(text=footer)
    return embed


class ExecutePlanView(discord.ui.View):
    def __init__(
        self,
        *,
        api_client: DailyRoutineClient,
        prompt: str,
        author_id: int,
    ):
        super().__init__(timeout=15 * 60)
        self.api_client = api_client
        self.prompt = prompt
        self.author_id = author_id

    async def _deny_other_user(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return False

        await interaction.response.send_message(
            "This preview belongs to someone else. Run your own /routine command instead.",
            ephemeral=True,
        )
        return True

    @discord.ui.button(label="Run plan", style=discord.ButtonStyle.green)
    async def run_plan(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if await self._deny_other_user(interaction):
            return

        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("Running that plan now…", ephemeral=True)

        try:
            result = await self.api_client.ask(
                prompt=self.prompt,
                execute=True,
                interaction=interaction,
                request_suffix="execute",
            )
        except DailyRoutineApiError as error:
            await interaction.followup.send(f"❌ {error}", ephemeral=True)
            return

        await interaction.followup.send(
            embed=_build_result_embed(prompt=self.prompt, result=result, executed=True)
        )

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.secondary)
    async def dismiss(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if await self._deny_other_user(interaction):
            return

        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)


def setup_dailyroutine_commands(client):
    api_client = DailyRoutineClient()

    async def _run_prompt(
        interaction: discord.Interaction,
        *,
        prompt: str,
        execute: bool,
        request_suffix: str,
    ):
        await interaction.response.defer(thinking=True)

        try:
            result = await api_client.ask(
                prompt=prompt,
                execute=execute,
                interaction=interaction,
                request_suffix=request_suffix,
            )
        except DailyRoutineApiError as error:
            await interaction.followup.send(f"❌ {error}")
            return

        embed = _build_result_embed(prompt=prompt, result=result, executed=execute)
        if execute or not result.get("commands"):
            await interaction.followup.send(embed=embed)
            return

        await interaction.followup.send(
            embed=embed,
            view=ExecutePlanView(
                api_client=api_client,
                prompt=prompt,
                author_id=interaction.user.id,
            ),
        )

    @client.tree.command(name="routine", description="Ask DailyRoutine something")
    @app_commands.describe(
        prompt="What you want DailyRoutine to help with",
        execute="Run the plan now instead of previewing it first",
    )
    async def routine_command(
        interaction: discord.Interaction,
        prompt: str,
        execute: bool = DAILY_ROUTINE_EXECUTE_BY_DEFAULT,
    ):
        await _run_prompt(
            interaction,
            prompt=prompt,
            execute=execute,
            request_suffix="routine",
        )

    @client.tree.command(name="briefing", description="Get your DailyRoutine briefing")
    async def briefing_command(interaction: discord.Interaction):
        await _run_prompt(
            interaction,
            prompt="Give me my daily briefing.",
            execute=True,
            request_suffix="briefing",
        )

    @client.tree.command(name="schedule", description="Read your DailyRoutine schedule")
    @app_commands.describe(timeframe="For example: today, tomorrow, this week")
    async def schedule_command(
        interaction: discord.Interaction, timeframe: str = "today"
    ):
        await _run_prompt(
            interaction,
            prompt=f"What is on my schedule {timeframe}?",
            execute=True,
            request_suffix="schedule",
        )

    @client.tree.command(name="pantry", description="Check your pantry and spice status")
    async def pantry_command(interaction: discord.Interaction):
        await _run_prompt(
            interaction,
            prompt="Give me my pantry and spice cabinet status. Call out anything low or out.",
            execute=True,
            request_suffix="pantry",
        )

    @client.tree.command(name="chef", description="Ask DailyRoutine what to cook")
    async def chef_command(interaction: discord.Interaction):
        await _run_prompt(
            interaction,
            prompt="What should I cook tonight with what I already have?",
            execute=True,
            request_suffix="chef",
        )
