from __future__ import annotations

import asyncio
import logging
import logging.handlers
import sys
from pathlib import Path

import yaml

from agent.core import AgentCore
from agent.llm_router import LLMRouter
from agent.scheduler import SkillScheduler
from agent.state import ConversationStateManager
from providers.claude import ClaudeProvider
from providers.ollama import OllamaProvider
from skills.loader import SkillLoader
from slack.bot import create_app, start_socket_mode
from slack.handlers import register_handlers, setup_scheduled_skill_callback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            Path.home() / ".slack-booty" / "slack-booty.log",
            maxBytes=5_000_000,
            backupCount=3,
        ),
    ],
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        logger.error("config.yaml not found at %s", config_path)
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


async def main():
    # Ensure data directory exists
    data_dir = Path.home() / ".slack-booty"
    data_dir.mkdir(parents=True, exist_ok=True)

    config = load_config()

    # Database
    db_path = str(data_dir / "slack-booty.db")
    state_manager = ConversationStateManager(db_path)

    # LLM providers
    ollama_config = config.get("ollama", {})
    ollama = OllamaProvider(
        base_url=ollama_config.get("base_url", "http://localhost:11434"),
        model=ollama_config.get("model", "qwen3:8b"),
    )

    claude_config = config.get("claude", {})
    claude = ClaudeProvider(
        api_key=claude_config["api_key"],
        model=claude_config.get("model", "claude-haiku-4-20250414"),
    )

    llm_router = LLMRouter(
        ollama=ollama,
        claude=claude,
        global_override=config.get("llm_override"),
    )

    # Skills
    skills_dir = config.get("skills_dir", str(data_dir / "skills"))
    skill_loader = SkillLoader(skills_dir)
    skill_loader.load_all()
    logger.info("Loaded %d skills", len(skill_loader.get_all_skills()))

    # Slack app
    slack_config = config["slack"]
    app = create_app(slack_config["bot_token"])

    # Resolve bot user ID
    auth_response = await app.client.auth_test()
    bot_user_id = auth_response["user_id"]
    logger.info("Bot user ID: %s", bot_user_id)

    # Agent core
    agent = AgentCore(
        state_manager=state_manager,
        llm_router=llm_router,
        skill_loader=skill_loader,
        bot_user_id=bot_user_id,
    )

    # Scheduler
    scheduler = SkillScheduler(db_path, skill_loader)
    trigger_callback = setup_scheduled_skill_callback(agent, app)
    scheduler.set_trigger_callback(trigger_callback)
    scheduler.register_skills()
    scheduler.start()

    # Register Slack event handlers
    register_handlers(app, agent)

    # Startup notification
    owner = config.get("owner_user_id")
    if owner:
        try:
            dm = await app.client.conversations_open(users=[owner])
            skill_count = len(skill_loader.get_all_skills())
            scheduled = skill_loader.get_scheduled_skills()
            next_info = ""
            if scheduled:
                next_info = f", next scheduled skill: {scheduled[0]['name']}"
            await app.client.chat_postMessage(
                channel=dm["channel"]["id"],
                text=f"Back online. {skill_count} skill(s) active{next_info}.",
            )
        except Exception:
            logger.warning("Could not send startup DM", exc_info=True)

    logger.info("Slack-Booty is starting up...")
    try:
        await start_socket_mode(app, slack_config["app_token"])
    finally:
        scheduler.shutdown()
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
