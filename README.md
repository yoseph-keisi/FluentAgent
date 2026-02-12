# FluentAgent

Autonomous CFD simulation orchestrator for ANSYS Fluent with adaptive retry logic and optional natural language config generation.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Demo

Demo GIF/screenshot placeholder (to be added after first working run).

## What It Does

FluentAgent automates an end-to-end CFD workflow: geometry intake, meshing, solving, and post-processing. It encodes practical CFD decision logic so the pipeline can recover from common mesh-quality and solver-convergence failures automatically. You can run from a structured YAML configuration or generate one from natural language with Claude API integration. The goal is to reduce manual trial-and-error and make runs reproducible.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m fluent_agent.cli validate --config configs/example_naca2412.yaml
```

## Installation

```bash
pip install -e ".[dev]"
```

- A valid ANSYS Fluent license is required for simulation execution.
- Create a `.env` file from `.env.example` and set at minimum:
  - `ANTHROPIC_API_KEY` (for NLP mode)
  - `FLUENT_PATH` (path to Fluent installation)

## Usage

Config mode:

```bash
fluent-agent run --config configs/example_naca2412.yaml
```

NLP mode:

```bash
fluent-agent prompt "Simulate NACA 2412 at Re 3e6 and 2 deg AoA"
```

Dry run (generate config only):

```bash
fluent-agent prompt "NACA 0012 at Re 6e6" --dry-run --output configs/generated.yaml
```

Validate only:

```bash
fluent-agent validate --config configs/example_naca2412.yaml
```

## Config Reference

See `configs/schema_reference.yaml`.

## Architecture

See `docs/ARCHITECTURE.md`.

## Validation

NACA 2412 validation case and quantitative results will be documented here after the first full Fluent run.

## Limitations

- Requires an ANSYS Fluent license.
- Current scope is 2D simulations.
- Current modeling scope is RANS.

## Roadmap

- OpenFOAM backend support
- 3D simulation support
- Multi-objective optimization workflows

## License

MIT. See `LICENSE`.
