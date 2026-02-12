from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table


class AgentLogger:
    """Thin logging wrapper with rich terminal output and optional file logs."""

    def __init__(self, name: str = "fluent-agent", output_dir: str | None = None) -> None:
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        if not any(isinstance(handler, RichHandler) for handler in self._logger.handlers):
            rich_handler = RichHandler(show_time=True, show_path=False, rich_tracebacks=True, markup=True)
            rich_handler.setLevel(logging.INFO)
            rich_handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(rich_handler)

        if output_dir is not None:
            self._add_file_handler(output_dir)

    def _add_file_handler(self, output_dir: str) -> None:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        log_file = output_path / "run.log"

        for handler in self._logger.handlers:
            if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_file:
                return

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        self._logger.addHandler(file_handler)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.error(message, *args, **kwargs)

    def stage(self, name: str) -> None:
        stage_name = name.strip().upper() or "STAGE"
        line = "\u2501" * 3
        self._logger.info(f"[bold cyan]{line} [{stage_name}] {line}[/bold cyan]")

    def summary(self, data: dict[str, Any]) -> None:
        table = Table(title="Simulation Summary")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        for key, value in data.items():
            rendered_value = value.value if hasattr(value, "value") else value
            table.add_row(str(key), str(rendered_value))

        console = Console(width=120, record=True)
        console.print(table)
        self._logger.info("\n%s", console.export_text(clear=False).rstrip())
