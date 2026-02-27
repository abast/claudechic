"""Tests for --yolo flag (bypass permissions mode) implementation.

This file tests the behavior specified in the YOLO flag implementation:
1. Fresh install → default mode
2. --yolo flag → bypass mode
3. Spawned agents inherit correct mode
4. Mode cycling works correctly
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudechic.app import ChatApp
from claudechic.widgets import StatusFooter
from tests.conftest import wait_for_workers, submit_command


class TestFreshInstallDefault:
    """Test that fresh installs start in 'default' mode (safe mode)."""

    @pytest.mark.asyncio
    async def test_fresh_install_uses_default_mode(self, mock_sdk):
        """Fresh install starts in 'default' mode (safe for new users)."""
        app = ChatApp()
        async with app.run_test():
            assert app._agent is not None
            assert app._agent.permission_mode == "default"

    @pytest.mark.asyncio
    async def test_fresh_install_footer_shows_default(self, mock_sdk):
        """Footer shows 'Default' mode on fresh install."""
        app = ChatApp()
        async with app.run_test():
            footer = app.query_one(StatusFooter)
            assert footer.permission_mode == "default"

    @pytest.mark.asyncio
    async def test_agent_manager_global_mode_is_default(self, mock_sdk):
        """AgentManager.global_permission_mode is 'default' on fresh install."""
        app = ChatApp()
        async with app.run_test():
            assert app.agent_mgr is not None
            assert app.agent_mgr.global_permission_mode == "default"


class TestYoloFlag:
    """Test that --yolo flag enables bypass permissions mode."""

    @pytest.mark.asyncio
    async def test_yolo_flag_sets_bypass_mode(self, mock_sdk):
        """--yolo flag sets permission mode to bypassPermissions."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test():
            assert app._agent is not None
            assert app._agent.permission_mode == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_yolo_flag_updates_global_mode(self, mock_sdk):
        """--yolo flag updates AgentManager.global_permission_mode."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test():
            assert app.agent_mgr is not None
            assert app.agent_mgr.global_permission_mode == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_yolo_flag_footer_shows_bypass(self, mock_sdk):
        """Footer shows 'Bypass' mode when --yolo flag is used."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test():
            footer = app.query_one(StatusFooter)
            assert footer.permission_mode == "bypassPermissions"


class TestSpawnedAgentInheritance:
    """Test that spawned agents inherit the correct permission mode."""

    @pytest.mark.asyncio
    async def test_spawned_agent_inherits_default_mode(self, mock_sdk):
        """Spawned agents inherit 'default' mode in fresh install."""
        app = ChatApp()
        async with app.run_test() as pilot:
            # Create second agent
            await submit_command(app, pilot, "/agent second")
            await wait_for_workers(app)

            # Both agents should have default mode
            for agent in app.agents.values():
                assert agent.permission_mode == "default"

    @pytest.mark.asyncio
    async def test_spawned_agent_inherits_bypass_mode(self, mock_sdk):
        """Spawned agents inherit 'bypassPermissions' mode when --yolo is used."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test() as pilot:
            # Create second agent
            await submit_command(app, pilot, "/agent second")
            await wait_for_workers(app)

            # Both agents should have bypass mode
            for agent in app.agents.values():
                assert agent.permission_mode == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_spawned_agent_inherits_current_global_mode(self, mock_sdk):
        """Spawned agents inherit the current global mode (after cycling)."""
        app = ChatApp()
        async with app.run_test() as pilot:
            # Start in default mode, cycle to bypassPermissions
            await pilot.press("shift+tab")
            assert app.agent_mgr.global_permission_mode == "bypassPermissions"

            # Create second agent
            await submit_command(app, pilot, "/agent second")
            await wait_for_workers(app)

            # Find the new agent (not the first one)
            agents = list(app.agents.values())
            second_agent = [a for a in agents if a.name == "second"][0]

            # Should inherit the cycled mode
            assert second_agent.permission_mode == "bypassPermissions"


class TestModeCyclingWithYolo:
    """Test that mode cycling works correctly after --yolo."""

    @pytest.mark.asyncio
    async def test_cycle_from_yolo_bypass_mode(self, mock_sdk):
        """Mode cycling works correctly starting from --yolo bypass mode."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test() as pilot:
            # Start in bypass mode (from --yolo)
            assert app._agent.permission_mode == "bypassPermissions"

            # Cycle: bypassPermissions -> acceptEdits
            await pilot.press("shift+tab")
            assert app._agent.permission_mode == "acceptEdits"

            # Cycle: acceptEdits -> plan
            await pilot.press("shift+tab")
            assert app._agent.permission_mode == "plan"

            # Cycle: plan -> default
            await pilot.press("shift+tab")
            assert app._agent.permission_mode == "default"

            # Cycle: default -> bypassPermissions
            await pilot.press("shift+tab")
            assert app._agent.permission_mode == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_cycle_updates_all_agents_with_yolo(self, mock_sdk):
        """Mode cycling updates all agents including those spawned with --yolo."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test() as pilot:
            # Create second agent
            await submit_command(app, pilot, "/agent second")
            await wait_for_workers(app)

            # Both should be in bypass mode
            for agent in app.agents.values():
                assert agent.permission_mode == "bypassPermissions"

            # Cycle to acceptEdits
            await pilot.press("shift+tab")

            # All agents should be in acceptEdits mode
            for agent in app.agents.values():
                assert agent.permission_mode == "acceptEdits"


class TestConfigPersistence:
    """Test that config persistence interacts correctly with --yolo."""

    @pytest.mark.asyncio
    async def test_yolo_overrides_persisted_default(self, mock_sdk):
        """--yolo overrides a persisted 'default' setting."""
        # Even if config says 'default', --yolo should force bypass
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "default"},
        ):
            app = ChatApp(skip_permissions=True)
            async with app.run_test():
                assert app._agent.permission_mode == "bypassPermissions"
                assert app.agent_mgr.global_permission_mode == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_no_yolo_respects_persisted_bypass(self, mock_sdk):
        """Without --yolo, respects persisted 'bypassPermissions' setting."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "bypassPermissions"},
        ):
            app = ChatApp(skip_permissions=False)
            async with app.run_test():
                # Should use persisted bypass mode
                assert app._agent.permission_mode == "bypassPermissions"
                assert app.agent_mgr.global_permission_mode == "bypassPermissions"
