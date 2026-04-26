"""Guardrails modal — shows all rules/injections with active/skipped status.

Checkboxes let the user toggle individual rules on or off at runtime.
Toggling updates an in-memory ``disabled_rules`` set on the app;
the hook evaluator consults this set on every tool call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Static

if TYPE_CHECKING:
    from claudechic.guardrails.digest import GuardrailEntry

# Enforcement level display badges
_ENFORCEMENT_BADGE = {
    "deny": "[bold red]deny[/]",
    "warn": "[bold yellow]warn[/]",
    "log": "[dim]log[/]",
    "inject": "[bold cyan]inject[/]",
}


@dataclass(frozen=True)
class GuardrailToggled(Message):
    """Posted when a guardrail checkbox is toggled."""

    rule_id: str
    enabled: bool


class _GuardrailRow(Horizontal):
    """A single row: checkbox + enforcement badge + id + skip reason."""

    DEFAULT_CSS = """
    _GuardrailRow {
        height: 1;
        padding: 0 1;
    }

    _GuardrailRow .gr-badge {
        width: 8;
        text-align: center;
    }

    _GuardrailRow .gr-id {
        width: 1fr;
    }

    _GuardrailRow .gr-reason {
        width: auto;
        max-width: 40;
        color: $text-muted;
    }
    """

    def __init__(self, entry: GuardrailEntry, **kwargs) -> None:
        super().__init__(**kwargs)
        self._entry = entry

    def compose(self) -> ComposeResult:
        e = self._entry
        cb = Checkbox("", value=e.active, id=f"gr-cb-{e.id}")
        cb.BUTTON_INNER = " "  # tighter rendering
        yield cb
        badge = _ENFORCEMENT_BADGE.get(e.enforcement, e.enforcement)
        yield Static(badge, classes="gr-badge", markup=True)
        yield Static(e.id, classes="gr-id")
        if e.skip_reason:
            yield Static(f"({e.skip_reason})", classes="gr-reason")


class GuardrailsModal(ModalScreen):
    """Modal listing all guardrails with toggleable checkboxes."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    GuardrailsModal {
        align: center middle;
    }

    GuardrailsModal #gr-container {
        width: auto;
        min-width: 60;
        max-width: 100;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: solid $panel;
        padding: 1 2;
    }

    GuardrailsModal #gr-header {
        height: 1;
        margin-bottom: 1;
    }

    GuardrailsModal #gr-title {
        width: 1fr;
    }

    GuardrailsModal #gr-scroll {
        max-height: 20;
        height: auto;
    }

    GuardrailsModal .gr-section-title {
        height: 1;
        margin-top: 1;
        color: $text-muted;
    }

    GuardrailsModal #gr-empty {
        color: $text-muted;
        padding: 1;
    }

    GuardrailsModal #gr-footer {
        height: 1;
        margin-top: 1;
        align: center middle;
    }

    GuardrailsModal #gr-close-btn {
        min-width: 10;
    }
    """

    def __init__(self, entries: list[GuardrailEntry], **kwargs) -> None:
        super().__init__(**kwargs)
        self._entries = entries

    def compose(self) -> ComposeResult:
        with Vertical(id="gr-container"):
            with Horizontal(id="gr-header"):
                yield Static("[bold]Guardrails[/]", id="gr-title", markup=True)

            if not self._entries:
                yield Static("No rules or injections loaded.", id="gr-empty")
            else:
                rules = [e for e in self._entries if e.kind == "rule"]
                injections = [e for e in self._entries if e.kind == "injection"]

                with VerticalScroll(id="gr-scroll"):
                    if rules:
                        yield Static(
                            f"[bold]Rules[/] ({len(rules)})",
                            classes="gr-section-title",
                            markup=True,
                        )
                        for entry in rules:
                            yield _GuardrailRow(entry)

                    if injections:
                        yield Static(
                            f"[bold]Injections[/] ({len(injections)})",
                            classes="gr-section-title",
                            markup=True,
                        )
                        for entry in injections:
                            yield _GuardrailRow(entry)

            with Horizontal(id="gr-footer"):
                yield Button("Close", id="gr-close-btn")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Forward checkbox toggle as a GuardrailToggled message."""
        cb_id = event.checkbox.id or ""
        if cb_id.startswith("gr-cb-"):
            rule_id = cb_id[len("gr-cb-"):]
            self.post_message(GuardrailToggled(rule_id=rule_id, enabled=event.value))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "gr-close-btn":
            self.dismiss()
