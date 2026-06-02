import discord
import logging
import os
import asyncio
from context_builder import build_context
from agent import run_agent

log = logging.getLogger("discord_client")

ALLOWED_ROLE_ID = int(os.getenv("ALLOWED_ROLE_ID", "1297669279461933116"))

EYES = "👀"
BRAIN = "🧠"


class QTIAgent(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)

    async def on_ready(self):
        log.info(f"QTI's Little Helper is online as {self.user}")

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return

        is_mention = self.user in message.mentions and not message.mention_everyone
        is_reply_to_us = (
            message.reference is not None
            and message.reference.resolved is not None
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author == self.user
        )

        if not is_mention and not is_reply_to_us:
            return

        if not isinstance(message.author, discord.Member):
            return

        has_role = any(role.id == ALLOWED_ROLE_ID for role in message.author.roles)
        if not has_role:
            return

        await message.add_reaction(EYES)

        try:
            chain = await self._walk_reply_chain(message)

            context = await build_context(
                trigger_message=message,
                reply_chain=chain,
                bot_id=self.user.id,
            )

            await message.remove_reaction(EYES, self.user)
            await message.add_reaction(BRAIN)

            response_text, files = await asyncio.to_thread(run_agent, context)

            await self._post_response(message, response_text, files)

        except Exception as e:
            log.error(f"Error handling message {message.id}: {e}")
            response_text = "Something went wrong on my end — check the logs."
            await self._post_response(message, response_text, [])

        finally:
            try:
                await message.remove_reaction(BRAIN, self.user)
            except Exception:
                pass

    async def _walk_reply_chain(self, message: discord.Message) -> list[dict]:
        chain = []
        current = message

        while True:
            entry = {
                "author": current.author.name,
                "content": current.content,
                "reply_to_index": None,
                "is_trigger": current.id == message.id,
            }
            chain.append((current.id, entry))

            if current.reference is None or current.reference.message_id is None:
                break

            if (
                current.reference.resolved is not None
                and isinstance(current.reference.resolved, discord.Message)
            ):
                parent = current.reference.resolved
            else:
                try:
                    parent = await current.channel.fetch_message(
                        current.reference.message_id
                    )
                except Exception:
                    break

            current = parent

        chain.reverse()

        id_to_index = {msg_id: i + 1 for i, (msg_id, _) in enumerate(chain)}

        result = []
        for i, (msg_id, entry) in enumerate(chain):
            if i > 0:
                parent_id = list(id_to_index.keys())[i - 1]
                entry["reply_to_index"] = id_to_index.get(parent_id)
            result.append(entry)

        return result

    async def _post_response(
        self,
        trigger: discord.Message,
        text: str,
        files: list[str],
    ):
        discord_files = []
        missing_files = []
        for path in files:
            if not path:
                continue
            if os.path.exists(path):
                discord_files.append(discord.File(path))
            else:
                log.warning("File attachment not found, skipping: %s", path)
                missing_files.append(path)

        if missing_files:
            text = text.rstrip()
            text += "\n\n_(Could not attach: " + ", ".join(f"`{p}`" for p in missing_files) + " — file not found on disk.)_"

        chunks = _chunk_text(text, limit=1900)

        for i, chunk in enumerate(chunks):
            if i == 0:
                await trigger.reply(
                    chunk,
                    files=discord_files if discord_files else discord.utils.MISSING,
                    mention_author=False,
                )
            else:
                await trigger.channel.send(chunk)


def _chunk_text(text: str, limit: int = 1900) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks


def run():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN not set in environment")

    client = QTIAgent()
    client.run(token)