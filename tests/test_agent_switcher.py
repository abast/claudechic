"""Test 9: Agent Switcher hint, Ctrl+G modal, and AgentLabel footer widget."""

from __future__ import annotations

import pytest
from claudechic.app import ChatApp
from claudechic.hints.state import HintStateStore
from claudechic.widgets.layout.footer import AgentLabel

from tests.conftest import submit_command, wait_for_workers

HINT_KEY = "agent-switcher-tip"


@pytest.mark.asyncio
async def test_agent_switcher_hint_and_ctrl_g(mock_sdk, tmp_path, monkeypatch):
    """Full integration test for AgentSwitcher, AgentLabel, and discovery hint.

    6 steps covering hint firing, non-repetition, Ctrl+G modal interaction,
    agent switching, label visibility, and cross-session persistence.
    """
    # Force app._cwd to tmp_path so HintStateStore writes there
    monkeypatch.setattr("claudechic.app.Path.cwd", staticmethod(lambda: tmp_path))

    # ------------------------------------------------------------------
    # Step 1: Hint fires on 1 -> 2 agents
    # ------------------------------------------------------------------
    app = ChatApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # Starts with 1 agent
        assert len(app.agents) == 1

        # Create second agent
        await submit_command(app, pilot, "/agent second-agent")
        await wait_for_workers(app)
        await pilot.pause()

        assert len(app.agents) == 2

        # Assert: toast fired with "Ctrl+G" text
        # Textual stores toasts on the app._notifications list
        toast_texts = [str(n.message) for n in app._notifications]
        assert any("Ctrl+G" in t for t in toast_texts), (
            f"Expected toast with 'Ctrl+G', got: {toast_texts}"
        )

        # Assert: HintStateStore records times_shown == 1
        store = HintStateStore(tmp_path)
        assert store.get_times_shown(HINT_KEY) == 1

        # Assert: AgentLabel in footer is visible
        agent_label = app.query_one("#agent-label", AgentLabel)
        assert not agent_label.has_class("hidden"), (
            "AgentLabel should be visible with 2 agents"
        )
        # Label shows the active agent's name
        label_text = str(agent_label.renderable)
        assert len(label_text) > 0, "AgentLabel should show agent name"

        # ------------------------------------------------------------------
        # Step 2: Hint does NOT repeat on 2 -> 3 agents
        # ------------------------------------------------------------------
        toast_count_before = len(app._notifications)

        await submit_command(app, pilot, "/agent third-agent")
        await wait_for_workers(app)
        await pilot.pause()

        assert len(app.agents) == 3

        # Count new toasts containing "Ctrl+G"
        all_toasts = list(app._notifications)
        new_toasts = [str(n.message) for n in all_toasts[toast_count_before:]]
        assert not any("Ctrl+G" in t for t in new_toasts), (
            f"Hint should NOT repeat on 2->3, but got: {new_toasts}"
        )

        # HintStateStore unchanged
        store2 = HintStateStore(tmp_path)
        assert store2.get_times_shown(HINT_KEY) == 1

        # ------------------------------------------------------------------
        # Step 3: Ctrl+G opens AgentSwitcher modal
        # ------------------------------------------------------------------
        from claudechic.widgets.modals.agent_switcher import AgentSwitcher

        await pilot.press("ctrl+g")
        await pilot.pause()

        # Assert modal is on screen stack (ModalScreen is the active screen)
        assert isinstance(app.screen, AgentSwitcher)
        switcher = app.screen

        # Assert lists 3 agents
        from textual.widgets import ListView

        list_view = switcher.query_one("#agent-results", ListView)
        assert len(list_view.children) == 3

        # ------------------------------------------------------------------
        # Step 4: Navigate and switch agent
        # ------------------------------------------------------------------
        # Record current active agent
        active_before = app.active_agent_id

        # Down arrow + Enter to select second item (index 1)
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()

        # Modal should be dismissed (screen should no longer be AgentSwitcher)
        assert not isinstance(app.screen, AgentSwitcher), (
            "AgentSwitcher should be dismissed"
        )

        # Agent should have switched
        assert app.active_agent_id != active_before, "Active agent should have changed"

        # AgentLabel should be updated
        agent_label = app.query_one("#agent-label", AgentLabel)
        assert not agent_label.has_class("hidden")

        # ------------------------------------------------------------------
        # Step 5: AgentLabel hides at 1 agent
        # ------------------------------------------------------------------
        # Close 2 agents to get back to 1
        await submit_command(app, pilot, "/agent close")
        await wait_for_workers(app)
        await pilot.pause()

        await submit_command(app, pilot, "/agent close")
        await wait_for_workers(app)
        await pilot.pause()

        assert len(app.agents) == 1

        agent_label = app.query_one("#agent-label", AgentLabel)
        assert agent_label.has_class("hidden"), (
            "AgentLabel should be hidden with 1 agent"
        )

    # ------------------------------------------------------------------
    # Step 6: Cross-session persistence -- new app, same tmp_path
    # ------------------------------------------------------------------
    app2 = ChatApp()
    async with app2.run_test(size=(120, 40)) as pilot2:
        assert len(app2.agents) == 1

        toast_count_before = len(app2._notifications)

        # Create second agent to hit 1->2 threshold again
        await submit_command(app2, pilot2, "/agent cross-session")
        await wait_for_workers(app2)
        await pilot2.pause()

        assert len(app2.agents) == 2

        # Assert NO toast fires (cross-session persistence)
        all_toasts2 = list(app2._notifications)
        new_toasts = [str(n.message) for n in all_toasts2[toast_count_before:]]
        assert not any("Ctrl+G" in t for t in new_toasts), (
            f"Hint should NOT fire in second session, got: {new_toasts}"
        )

        # HintStateStore still == 1 from first session
        store3 = HintStateStore(tmp_path)
        assert store3.get_times_shown(HINT_KEY) == 1
