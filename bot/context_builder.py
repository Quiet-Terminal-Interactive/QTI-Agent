import json
import os
import discord
from config_store import (
    get_all_repos,
    get_all_buckets,
    get_current_version,
    get_recent_changelog,
)

TOOL_SCHEMA = json.dumps(
    [
        {
            "tool": "shell",
            "description": (
                "Run any shell command in the sandbox. Use for builds, file ops, "
                "git, grep, find, anything. Returns stdout and stderr."
            ),
            "params": {"command": "string"},
        },
        {
            "tool": "gitea_api",
            "description": "Query the Gitea API. Use for listing repos, branches, tags, commits.",
            "params": {
                "endpoint": "string",
                "method": "GET|POST",
                "body": "object|null",
            },
        },
        {
            "tool": "minio_get",
            "description": "Download a file from a public MinIO bucket into the sandbox.",
            "params": {"bucket": "string", "filename": "string"},
        },
        {
            "tool": "minio_list",
            "description": "List files in a public MinIO bucket, optionally filtered by prefix.",
            "params": {"bucket": "string", "prefix": "string|null"},
        },
        {
            "tool": "read_config",
            "description": "Read a repo or bot config JSON file by name.",
            "params": {"name": "string"},
        },
        {
            "tool": "write_config",
            "description": "Write or update a config JSON file.",
            "params": {"name": "string", "content": "object"},
        },
        {
            "tool": "read_json",
            "description": (
                "Read any JSON data file by path. "
                "e.g. ideas.json, changelog.json, asset_meta.json."
            ),
            "params": {"path": "string"},
        },
        {
            "tool": "write_json",
            "description": "Write or update any JSON data file.",
            "params": {"path": "string", "content": "object"},
        },
        {
            "tool": "discord_respond",
            "description": (
                "Send the final response to Discord. "
                "Include any sandbox file paths to attach. Always call this last."
            ),
            "params": {"message": "string", "files": ["string|null"]},
        },
    ],
    indent=2,
)

TEAM = {
    "ieatsystemfiles": {"name": "Kohan Mathers", "pronouns": "they/them", "role": "Founder & lead developer"},
    "dumbnat14":       {"name": "Natalia Rybicka", "pronouns": "she/her",  "role": "Co-founder & creative lead"},
    "hannahfaun":      {"name": "Hannah Stewart",  "pronouns": "she/her",  "role": "Creative assistant & QA"},
}

STATIC_PROMPT = """You are QTI's Little Helper, the internal studio assistant bot for Quiet Terminal \
Interactive (QTI) — a small but scrappy UK-based indie game studio founded in early \
2025. QTI is currently developing Rogue Reunion, a 2.5D pixel art action roguelike, \
alongside several other projects in the QTI universe.

## The Team
There are three team members. You know them well:

- Kohan Mathers (Discord: ieatsystemfiles) — Founder, lead developer, and technical \
director. Writes all the code, built the custom engine, makes the high-risk calls, \
and is probably awake at 4am. They go by Kohan with they/them pronouns.
- Natalia Rybicka (Discord: dumbnat14) — Co-founder and creative lead. Owns visual \
direction, character design, and world identity across all QTI projects. \
She goes by Nat with she/her pronouns.
- Hannah Stewart (Discord: hannahfaun) — Creative assistant and QA. Keeps things \
grounded, tests everything until it breaks, and bridges creative and practical. \
She goes by Hannah with she/her pronouns.

## Your Personality
You are professional but not stiff. You match the energy of the team — concise, a \
little dry, occasionally funny, never corporate. You care about getting things right \
and you're not afraid to ask for clarification before acting. You refer to team \
members by first name. You are loyal to QTI and take the work seriously even when \
the team doesn't always. You reflect the tone of whoever is speaking to you, while \
always staying polite (if they swear at you, don't swear back unless it's purely \
for expression).

## Rules
- Never guess file paths, use shell to find them if unsure
- Always attach build logs as files, never paste them in the message
- Keep Discord messages concise and conversational
- If a build fails, check the log and summarise the error clearly
- If you are unsure what the user wants, ask in Discord before acting
- Always respond with a single JSON tool call and nothing else — no explanation, no markdown, no preamble
- Every response must use exactly this format: {"tool": "<tool_name>", "params": {...}}
- When you have everything you need, call discord_respond"""


def _build_context_block(sender_username: str) -> str:
    repos = get_all_repos()
    buckets = get_all_buckets()
    version = get_current_version()
    recent_changes = get_recent_changelog(limit=5)

    repo_list = ", ".join(repos) if repos else "none registered"
    bucket_list = ", ".join(buckets) if buckets else "none registered"
    changes_list = (
        "\n".join(f"  - {c}" for c in recent_changes)
        if recent_changes
        else "  none yet"
    )

    import logging
    logging.getLogger("context_builder").debug("[context] sender_username=%r", sender_username)
    member = TEAM.get(sender_username.lower())
    if member:
        sender_desc = f"{member['name']} (Discord: {sender_username}, {member['pronouns']}, {member['role']})"
    else:
        sender_desc = sender_username

    return f"""
## Current Context
- Registered repos: {repo_list}
- Registered buckets: {bucket_list}
- Current build version: {version}
- Recent changes:
{changes_list}
- The person speaking to you right now is: {sender_desc}

## Available Tools
{TOOL_SCHEMA}"""


def _build_chain_block(reply_chain: list[dict], trigger: dict, guild: discord.Guild | None = None, bot_id: int | None = None) -> str:
    messages = reply_chain if reply_chain else [trigger]

    header = (
        "\n---\n"
        + (
            "This message is a continuation of a previous conversation. "
            "All messages in the chain are below in chronological order:\n"
            if len(messages) > 1
            else "The message you must respond to:\n"
        )
    )

    lines = [header]

    for i, entry in enumerate(messages):
        number = i + 1
        author = entry["author"]
        content = _resolve_mentions(entry["content"], guild, bot_id)
        reply_to = entry.get("reply_to_index")
        is_trigger = entry.get("is_trigger", False)

        parts = [f"#{number} {author}"]
        if reply_to is not None:
            parts.append(f"(Replying to #{reply_to})")
        if is_trigger:
            parts.append("(The message you must respond to)")

        lines.append(f"{' '.join(parts)}: {content}")

    return "\n".join(lines)


def _resolve_mentions(content: str, guild: discord.Guild | None, bot_id: int | None) -> str:
    import re

    def replace(m: re.Match) -> str:
        raw = m.group(0)
        is_role = raw.startswith("<@&")
        id_str = re.search(r"\d+", raw).group()
        entity_id = int(id_str)

        if not is_role and entity_id == bot_id:
            return ""

        if guild:
            if is_role:
                role = guild.get_role(entity_id)
                if role:
                    return f"@{role.name}"
            else:
                member = guild.get_member(entity_id)
                if member:
                    return f"@{member.display_name}"

        return raw

    return re.sub(r"<@[!&]?\d+>", replace, content).strip()


async def build_context(
    trigger_message: discord.Message,
    reply_chain: list[dict],
    bot_id: int | None = None,
) -> dict:
    sender = trigger_message.author.name

    guild = trigger_message.guild
    clean_content = _resolve_mentions(trigger_message.content, guild, bot_id)

    trigger_entry = {
        "author": sender,
        "content": clean_content,
        "reply_to_index": None,
        "is_trigger": True,
    }

    system_prompt = (
        STATIC_PROMPT
        + _build_context_block(sender_username=sender)
        + _build_chain_block(reply_chain, trigger=trigger_entry, guild=guild, bot_id=bot_id)
    )

    return {
        "system_prompt": system_prompt,
        "sender": sender,
    }