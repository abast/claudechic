"""Workflow picker screen for selecting and activating workflows."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Input, Label, ListItem, ListView, Static


class WorkflowItem(ListItem):
    """A workflow entry in the picker list."""

    DEFAULT_CSS = """
    WorkflowItem {
        pointer: pointer;
    }
    """

    def __init__(
        self,
        workflow_id: str,
        main_role: str = "",
        phase_count: int = 0,
        is_active: bool = False,
    ) -> None:
        super().__init__()
        self.workflow_id = workflow_id
        self.main_role = main_role
        self.phase_count = phase_count
        self.is_active = is_active

    def compose(self) -> ComposeResult:
        yield Label(self.workflow_id, classes="workflow-name")
        parts = []
        if self.main_role:
            parts.append(f"role: {self.main_role}")
        parts.append(f"{self.phase_count} phase{'s' if self.phase_count != 1 else ''}")
        if self.is_active:
            parts.append("active")
        else:
            parts.append("available")
        yield Label(" . ".join(parts), classes="workflow-meta")


class WorkflowPickerScreen(Screen[str | None]):
    """Full-screen picker for selecting a workflow to activate.

    Returns the selected workflow_id string, or None if dismissed.
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = """
    WorkflowPickerScreen {
        background: $background;
        align: center top;
    }

    WorkflowPickerScreen #workflow-picker-container {
        width: 100%;
        max-width: 80;
        height: 100%;
        padding: 1 2;
    }

    WorkflowPickerScreen #workflow-picker-title {
        height: 1;
        margin-bottom: 1;
        text-style: bold;
    }

    WorkflowPickerScreen #workflow-search {
        height: 3;
        margin-bottom: 1;
    }

    WorkflowPickerScreen #workflow-list,
    WorkflowPickerScreen #workflow-list:focus {
        height: 1fr;
        background: transparent;
    }

    WorkflowPickerScreen #workflow-list > ListItem {
        padding: 0 0 0 1;
        height: auto;
        margin: 0 0 1 0;
        border-left: tall $panel;
    }

    WorkflowPickerScreen #workflow-list > ListItem:hover,
    WorkflowPickerScreen #workflow-list > ListItem.-highlight {
        background: $surface-darken-1;
        border-left: tall $primary;
    }

    WorkflowPickerScreen .workflow-meta {
        color: $text-muted;
    }
    """

    def __init__(self, workflows: dict) -> None:
        """Initialize with workflow data.

        Args:
            workflows: Dict mapping workflow_id -> dict with optional keys:
                main_role (str), phase_count (int), is_active (bool)
        """
        super().__init__()
        self._workflows = workflows

    def compose(self) -> ComposeResult:
        count = len(self._workflows)
        with Vertical(id="workflow-picker-container"):
            yield Static(
                f"Select Workflow ({count} available)",
                id="workflow-picker-title",
            )
            yield Input(placeholder="Search workflows...", id="workflow-search")
            yield ListView(id="workflow-list")

    def on_mount(self) -> None:
        self._update_list("")
        self.query_one("#workflow-search", Input).focus()

    def on_key(self, event) -> None:
        """Forward navigation keys to list."""
        list_view = self.query_one("#workflow-list", ListView)
        if event.key == "down":
            list_view.action_cursor_down()
            event.prevent_default()
        elif event.key == "up":
            list_view.action_cursor_up()
            event.prevent_default()

    def action_go_back(self) -> None:
        self.dismiss(None)

    def _update_list(self, search: str) -> None:
        search_lower = search.lower()
        list_view = self.query_one("#workflow-list", ListView)
        list_view.clear()

        title = self.query_one("#workflow-picker-title", Static)

        filtered = sorted(self._workflows.keys())
        if search_lower:
            filtered = [wf for wf in filtered if search_lower in wf.lower()]

        if not filtered:
            title.update("Select Workflow (0 matches)")
            return

        title.update(f"Select Workflow ({len(filtered)} available)")

        for wf_id in filtered:
            data = self._workflows[wf_id]
            if isinstance(data, dict):
                item = WorkflowItem(
                    workflow_id=wf_id,
                    main_role=data.get("main_role", ""),
                    phase_count=data.get("phase_count", 0),
                    is_active=data.get("is_active", False),
                )
            else:
                # Simple path-based entry
                item = WorkflowItem(workflow_id=wf_id)
            list_view.append(item)

        if list_view.children:
            list_view.index = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "workflow-search":
            self._update_list(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "workflow-search":
            list_view = self.query_one("#workflow-list", ListView)
            if list_view.index is not None and list_view.highlighted_child:
                item = list_view.highlighted_child
                list_view.post_message(
                    ListView.Selected(list_view, item, list_view.index)
                )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, WorkflowItem):
            self.dismiss(event.item.workflow_id)
