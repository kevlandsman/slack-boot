from __future__ import annotations

import logging
from typing import Callable, Awaitable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger

from skills.loader import SkillLoader

logger = logging.getLogger(__name__)


class SkillScheduler:
    def __init__(self, db_path: str, skill_loader: SkillLoader):
        self.skill_loader = skill_loader
        jobstores = {
            "default": SQLAlchemyJobStore(url=f"sqlite:///{db_path}")
        }
        self.scheduler = AsyncIOScheduler(jobstores=jobstores)
        self._trigger_callback: Callable | None = None

    def set_trigger_callback(
        self, callback: Callable[[dict], Awaitable[None]]
    ):
        """Set the callback that fires when a scheduled skill triggers.

        The callback receives the skill config dict.
        """
        self._trigger_callback = callback

    def register_skills(self):
        """Register all scheduled skills as cron jobs."""
        # Remove existing jobs to avoid duplicates on restart
        self.scheduler.remove_all_jobs()

        for skill in self.skill_loader.get_scheduled_skills():
            schedule = skill.get("schedule")
            if not schedule:
                continue

            trigger = self._parse_cron(schedule)
            if not trigger:
                logger.error(
                    "Invalid cron expression for skill %s: %s",
                    skill["name"],
                    schedule,
                )
                continue

            self.scheduler.add_job(
                self._fire_skill,
                trigger=trigger,
                id=f"skill-{skill['name']}",
                replace_existing=True,
                kwargs={"skill_name": skill["name"]},
            )
            logger.info(
                "Scheduled skill '%s' with cron: %s", skill["name"], schedule
            )

    def _parse_cron(self, cron_expr: str) -> CronTrigger | None:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return None
        try:
            return CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
            )
        except Exception:
            logger.error("Failed to parse cron: %s", cron_expr, exc_info=True)
            return None

    async def _fire_skill(self, skill_name: str):
        skill = self.skill_loader.get_skill(skill_name)
        if not skill:
            logger.error("Scheduled skill not found: %s", skill_name)
            return
        if self._trigger_callback:
            await self._trigger_callback(skill)
        else:
            logger.warning("No trigger callback set for scheduler")

    def start(self):
        self.scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self):
        self.scheduler.shutdown()
        logger.info("Scheduler shut down")

    def add_skill_job(self, skill_config: dict):
        """Add or update a single skill's schedule."""
        schedule = skill_config.get("schedule")
        if not schedule or skill_config.get("trigger") != "scheduled":
            return

        trigger = self._parse_cron(schedule)
        if trigger:
            self.scheduler.add_job(
                self._fire_skill,
                trigger=trigger,
                id=f"skill-{skill_config['name']}",
                replace_existing=True,
                kwargs={"skill_name": skill_config["name"]},
            )
            logger.info("Added/updated scheduled job for '%s'", skill_config["name"])
