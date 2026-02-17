from __future__ import annotations

import logging
from typing import Optional

from slack_bolt.async_app import AsyncApp

from agent.core import AgentCore

logger = logging.getLogger(__name__)


async def _enrich_channel_name(event: dict, client) -> dict:
    """Best-effort channel-name lookup so mention skills can match #channel configs."""
    channel_id = event.get("channel")
    if not channel_id or event.get("channel_name"):
        return event
    # DM channels don't need #channel skill matching.
    if str(channel_id).startswith("D"):
        return event
    try:
        info = await client.conversations_info(channel=channel_id)
        channel_name = info.get("channel", {}).get("name")
        if channel_name:
            enriched = dict(event)
            enriched["channel_name"] = channel_name
            return enriched
    except Exception:
        logger.debug("Unable to resolve channel name for %s", channel_id, exc_info=True)
    return event


def register_handlers(app: AsyncApp, agent: AgentCore):
    @app.event("message")
    async def handle_message(event, say, client):
        # Ignore bot's own messages
        if event.get("bot_id") or event.get("subtype"):
            return

        logger.debug("Incoming message event: %s", event)

        try:
            enriched_event = await _enrich_channel_name(event, client)
            response = await agent.handle_message(enriched_event)
        except Exception:
            logger.error("Error handling message", exc_info=True)
            response = "Something went wrong on my end. I'll look into it."

        if response:
            thread_ts = event.get("thread_ts") or event.get("ts")
            await say(text=response, thread_ts=thread_ts)

    @app.event("app_mention")
    async def handle_mention(event, say, client):
        logger.debug("Mention event: %s", event)

        try:
            enriched_event = await _enrich_channel_name(event, client)
            response = await agent.handle_message(enriched_event)
        except Exception:
            logger.error("Error handling mention", exc_info=True)
            response = "Something went wrong on my end. I'll look into it."

        if response:
            thread_ts = event.get("thread_ts") or event.get("ts")
            await say(text=response, thread_ts=thread_ts)


def setup_scheduled_skill_callback(agent: AgentCore, app: AsyncApp):
    """Returns a callback for the scheduler to trigger skills."""

    async def _find_user_id(target_user: str) -> Optional[str]:
        wanted = target_user.lower()
        cursor: Optional[str] = None
        while True:
            response = await app.client.users_list(cursor=cursor, limit=200)
            for member in response.get("members", []):
                name = member.get("name", "").lower()
                real_name = member.get("real_name", "").lower()
                display_name = member.get("profile", {}).get("display_name", "").lower()
                if wanted in {name, real_name, display_name}:
                    return member["id"]
            cursor = response.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break
        return None

    async def _find_channel_id(channel_name: str) -> Optional[str]:
        wanted = channel_name.lower().lstrip("#")
        cursor: Optional[str] = None
        while True:
            response = await app.client.conversations_list(
                types="public_channel,private_channel",
                exclude_archived=True,
                cursor=cursor,
                limit=200,
            )
            for channel in response.get("channels", []):
                if channel.get("name", "").lower() == wanted:
                    return channel["id"]
            cursor = response.get("response_metadata", {}).get("next_cursor") or None
            if not cursor:
                break
        return None

    async def on_skill_trigger(skill_config: dict):
        target_user = skill_config.get("target_user")
        channel = skill_config.get("channel", "dm")

        try:
            if channel == "dm":
                if not target_user:
                    logger.error("DM scheduled skill missing target_user: %s", skill_config.get("name"))
                    return
                user_id = await _find_user_id(target_user)
                if not user_id:
                    logger.error("Could not find user: %s", target_user)
                    return

                dm = await app.client.conversations_open(users=[user_id])
                channel_id = dm["channel"]["id"]
            else:
                channel_ref = str(channel).strip()
                if channel_ref and channel_ref[0] in {"C", "G"} and not channel_ref.startswith("#"):
                    channel_id = channel_ref
                else:
                    channel_id = await _find_channel_id(channel_ref)
                if not channel_id:
                    logger.error("Could not find channel: %s", channel)
                    return
                user_id = "system"

            response, conv_id = await agent.trigger_scheduled_skill(
                skill_config, channel_id, user_id
            )

            result = await app.client.chat_postMessage(
                channel=channel_id, text=response
            )

            # Update the conversation with the real thread timestamp
            thread_ts = result["ts"]
            agent.state.update_conversation(conv_id, slack_thread=thread_ts)

        except Exception:
            logger.error(
                "Failed to trigger scheduled skill: %s",
                skill_config.get("name"),
                exc_info=True,
            )

    return on_skill_trigger
