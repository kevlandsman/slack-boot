from __future__ import annotations

import logging

from slack_bolt.async_app import AsyncApp

from agent.core import AgentCore

logger = logging.getLogger(__name__)


def register_handlers(app: AsyncApp, agent: AgentCore):
    @app.event("message")
    async def handle_message(event, say, client):
        # Ignore bot's own messages
        if event.get("bot_id") or event.get("subtype"):
            return

        logger.debug("Incoming message event: %s", event)

        try:
            response = await agent.handle_message(event)
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
            response = await agent.handle_message(event)
        except Exception:
            logger.error("Error handling mention", exc_info=True)
            response = "Something went wrong on my end. I'll look into it."

        if response:
            thread_ts = event.get("thread_ts") or event.get("ts")
            await say(text=response, thread_ts=thread_ts)


def setup_scheduled_skill_callback(agent: AgentCore, app: AsyncApp):
    """Returns a callback for the scheduler to trigger skills."""

    async def on_skill_trigger(skill_config: dict):
        target_user = skill_config.get("target_user")
        channel = skill_config.get("channel", "dm")

        try:
            if channel == "dm" and target_user:
                # Look up user ID by display name
                users = await app.client.users_list()
                user_id = None
                for member in users["members"]:
                    if member.get("name") == target_user or member.get("real_name", "").lower() == target_user.lower():
                        user_id = member["id"]
                        break

                if not user_id:
                    logger.error("Could not find user: %s", target_user)
                    return

                dm = await app.client.conversations_open(users=[user_id])
                channel_id = dm["channel"]["id"]
            else:
                # Channel skill — strip the # prefix
                channel_name = channel.lstrip("#")
                channels = await app.client.conversations_list(types="public_channel,private_channel")
                channel_id = None
                for ch in channels["channels"]:
                    if ch["name"] == channel_name:
                        channel_id = ch["id"]
                        break
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
