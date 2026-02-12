from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from pydantic import ValidationError

from fluent_agent.config import SimulationConfig
from fluent_agent.logger import AgentLogger


def _get_nested_attr(obj: Any, path: tuple[str, ...]) -> Any | None:
    current: Any = obj
    for field_name in path:
        if current is None or not hasattr(current, field_name):
            return None
        current = getattr(current, field_name)
    return current


def _format_value(value: Any) -> str:
    if value is None:
        return "N/A"
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _build_config_summary(config: SimulationConfig) -> dict[str, str]:
    geometry_file = _get_nested_attr(config, ("geometry", "file_path"))
    reynolds_number = _get_nested_attr(config, ("flow", "reynolds_number"))
    turbulence_model = _get_nested_attr(config, ("solver", "turbulence_model"))
    mesh_fineness = _get_nested_attr(config, ("mesh", "fineness"))

    return {
        "Geometry": _format_value(geometry_file),
        "Reynolds Number": _format_value(reynolds_number),
        "Turbulence Model": _format_value(turbulence_model),
        "Mesh Fineness": _format_value(mesh_fineness),
    }


def _load_config(config_path: Path, logger: AgentLogger) -> SimulationConfig:
    try:
        return SimulationConfig.from_yaml(str(config_path))
    except ValidationError as exc:
        logger.error("[bold red]Config validation failed[/bold red]")
        for error in exc.errors():
            location = ".".join(str(item) for item in error.get("loc", ())) or "config"
            logger.error("%s: %s", location, error.get("msg", "invalid value"))
        raise click.exceptions.Exit(1) from exc
    except FileNotFoundError as exc:
        logger.error("Config file not found: %s", config_path)
        raise click.exceptions.Exit(1) from exc
    except Exception as exc:
        logger.error("Failed to load config: %s", exc)
        raise click.exceptions.Exit(1) from exc


def _log_valid_config(config: SimulationConfig, logger: AgentLogger) -> None:
    logger.info("[bold green]Config valid[/bold green]")
    logger.summary(_build_config_summary(config))


@click.group(name="fluent-agent")
def main() -> None:
    """FluentAgent CLI."""


@main.command(name="validate")
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to configuration YAML file.",
)
def validate(config_path: Path) -> None:
    """Validate a simulation config file."""
    logger = AgentLogger()
    config = _load_config(config_path, logger)
    _log_valid_config(config, logger)


@main.command(name="run")
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to configuration YAML file.",
)
def run(config_path: Path) -> None:
    """Validate config and run orchestrator (stub in Phase 1)."""
    logger = AgentLogger()
    config = _load_config(config_path, logger)
    _log_valid_config(config, logger)
    logger.warning("Orchestrator not yet implemented (Phase 2)")


@main.command(name="prompt")
@click.argument("prompt_text", type=str)
@click.option("--dry-run", is_flag=True, default=False, help="Generate config only, do not execute.")
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    required=False,
    help="Optional output path for generated YAML.",
)
def prompt(prompt_text: str, dry_run: bool, output: Path | None) -> None:
    """Generate config from natural language prompt (stub in Phase 1)."""
    logger = AgentLogger()
    logger.debug("Received prompt text (%s characters)", len(prompt_text))
    if dry_run:
        logger.info("Dry-run mode enabled")
    if output is not None:
        logger.info("Requested output path: %s", output)
    logger.warning("NLP interface not yet implemented (Phase 3)")


if __name__ == "__main__":
    main()
