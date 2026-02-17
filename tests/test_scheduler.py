from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from agent.scheduler import SkillScheduler
from skills.loader import SkillLoader


@pytest.fixture
def skill_loader(tmp_path):
    loader = SkillLoader(str(tmp_path / "skills"))
    loader.ensure_dir()
    return loader


@pytest.fixture
def scheduler(tmp_path, skill_loader):
    db_path = str(tmp_path / "test.db")
    s = SkillScheduler(db_path, skill_loader)
    return s


class TestSkillScheduler:
    def test_parse_cron_valid(self, scheduler):
        trigger = scheduler._parse_cron("0 16 * * *")
        assert trigger is not None

    def test_parse_cron_invalid_too_few_parts(self, scheduler):
        trigger = scheduler._parse_cron("0 16 *")
        assert trigger is None

    def test_parse_cron_invalid_too_many_parts(self, scheduler):
        trigger = scheduler._parse_cron("0 16 * * * *")
        assert trigger is None

    def test_parse_cron_complex(self, scheduler):
        trigger = scheduler._parse_cron("30 9 * * 1-5")
        assert trigger is not None

    def test_register_skills_with_scheduled(self, scheduler, skill_loader):
        skill_loader.save_skill({
            "name": "test-scheduled",
            "description": "Test",
            "trigger": "scheduled",
            "schedule": "0 16 * * *",
            "context": "Context",
        })
        skill_loader.load_all()
        scheduler.register_skills()
        jobs = scheduler.scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "skill-test-scheduled"

    def test_register_skills_no_scheduled(self, scheduler, skill_loader):
        skill_loader.save_skill({
            "name": "manual-only",
            "description": "Manual",
            "trigger": "command",
            "context": "Context",
        })
        skill_loader.load_all()
        scheduler.register_skills()
        jobs = scheduler.scheduler.get_jobs()
        assert len(jobs) == 0

    def test_register_skills_clears_old_jobs(self, scheduler, skill_loader):
        skill_loader.save_skill({
            "name": "s1",
            "description": "S1",
            "trigger": "scheduled",
            "schedule": "0 10 * * *",
            "context": "C",
        })
        skill_loader.load_all()
        scheduler.register_skills()
        assert len(scheduler.scheduler.get_jobs()) == 1

        # Re-register with no scheduled skills
        skill_loader._skills = {}
        scheduler.register_skills()
        assert len(scheduler.scheduler.get_jobs()) == 0

    def test_add_skill_job(self, scheduler, skill_loader):
        skill_loader.save_skill({
            "name": "dynamic",
            "description": "Dynamic",
            "trigger": "scheduled",
            "schedule": "30 9 * * 1-5",
            "context": "C",
        })
        skill_loader.load_all()
        scheduler.add_skill_job(skill_loader.get_skill("dynamic"))
        jobs = scheduler.scheduler.get_jobs()
        assert len(jobs) == 1

    def test_add_skill_job_non_scheduled(self, scheduler):
        scheduler.add_skill_job({
            "name": "manual",
            "trigger": "command",
        })
        jobs = scheduler.scheduler.get_jobs()
        assert len(jobs) == 0

    @pytest.mark.asyncio
    async def test_fire_skill_calls_callback(self, scheduler, skill_loader):
        skill_loader.save_skill({
            "name": "fire-test",
            "description": "Test",
            "trigger": "scheduled",
            "schedule": "0 16 * * *",
            "context": "Context",
        })
        skill_loader.load_all()

        callback = AsyncMock()
        scheduler.set_trigger_callback(callback)
        await scheduler._fire_skill("fire-test")
        callback.assert_called_once()
        assert callback.call_args[0][0]["name"] == "fire-test"

    @pytest.mark.asyncio
    async def test_fire_skill_not_found(self, scheduler):
        callback = AsyncMock()
        scheduler.set_trigger_callback(callback)
        await scheduler._fire_skill("nonexistent")
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_fire_skill_no_callback(self, scheduler, skill_loader):
        skill_loader.save_skill({
            "name": "no-cb",
            "description": "Test",
            "trigger": "scheduled",
            "schedule": "0 16 * * *",
            "context": "Context",
        })
        skill_loader.load_all()
        # No callback set — should not raise
        await scheduler._fire_skill("no-cb")

    @pytest.mark.asyncio
    async def test_start_and_shutdown(self, scheduler):
        import asyncio
        scheduler.start()
        assert scheduler.scheduler.running
        scheduler.scheduler.shutdown(wait=False)
        await asyncio.sleep(0.1)  # Let event loop process the shutdown
        assert not scheduler.scheduler.running
