# AGENTS.md — FluentAgent Multi-Agent Build Plan

---

## A. Project Mission

FluentAgent is a Python orchestrator that drives ANSYS Fluent CFD simulations end-to-end — geometry intake, meshing, solver execution, adaptive error recovery, and post-processing — via a single command. It encodes expert CFD engineering logic into autonomous retry loops, replacing days of manual iteration. An optional NLP mode (Claude API) translates plain-English prompts into structured simulation configs.

---

## B. Absolute Constraints

All agents must follow these. Violations block merge.

1. **Phase order.** Phase 1 (foundation) must be fully green before any Phase 2 work begins. No PyFluent runtime calls until Phase 2.
2. **Directory structure is frozen.** Do not add, rename, or move files beyond what the spec defines. If you need a new file, stop and note it in `docs/ARCHITECTURE.md § Future` instead.
3. **Type annotations on everything.** Every function signature, every class attribute, every return type. Use `from __future__ import annotations` at the top of every module.
4. **Unit tests for every module.** Tests must run without an ANSYS license. Mock or stub all Fluent/PyFluent calls. Use `pytest`.
5. **Pydantic v2 only.** Use `model_validator`, `field_validator`, `model_dump()` — never v1 equivalents.
6. **No silent stubs.** If PyFluent syntax is uncertain, implement the logic behind an interface and raise `NotImplementedError("TODO: verify PyFluent >= 0.20 API — see docs at https://fluent.docs.pyansys.com/")`. Add a corresponding mocked test.
7. **Import chain must be acyclic.** `constants` ← `config` ← `physics_rules` ← `geometry`. No circular imports.

---

## C. Definition of Done (per PR / merge)

A branch is merge-ready when **all four** pass:

- [ ] `pytest tests/ -v` — all tests pass
- [ ] `ruff check src/ tests/` — zero lint errors (line-length 100)
- [ ] All imports resolve (`python -c "from fluent_agent import config, constants, physics_rules, geometry"` exits 0)
- [ ] Config YAML files load without error (`python -c "from fluent_agent.config import SimulationConfig; SimulationConfig.from_yaml('configs/example_naca2412.yaml')"`)

---

## D. Git Workflow

```
main                (protected — only Integrator merges here)
 ├── agent-a/config-schema
 ├── agent-b/physics-rules
 ├── agent-c/geometry
 ├── agent-d/cli-logger
 └── agent-e/docs-packaging
```

Rules:
1. One branch per agent. Branch names above are mandatory.
2. An agent may **only** edit files listed in its scope table (Section F). Editing another agent's files blocks merge.
3. The Integrator (you, the human) reviews diffs, resolves conflicts, and merges to `main` only after CI checks pass.
4. If two agents share a dependency (e.g., Agent A's `config.py` is imported by Agent C's `geometry.py`), Agent A must merge first. The dependency order is: **A → B → C → D → E** (A merges first, E merges last).

---

## E. Stop Conditions

If any of these occur, the agent must **stop coding** and leave a note:

1. **Scope creep.** The task starts requiring a file outside the agent's scope → add a `# TODO(agent-X): ...` comment and stop.
2. **Spec ambiguity.** The CLAUDE.md spec is unclear on a detail → add a `# QUESTION: ...` comment and stop.
3. **Untestable without Fluent.** Logic requires a live Fluent session to validate → stub with `NotImplementedError`, write a mocked test, and stop.
4. **New file needed.** The implementation wants a file not in the spec → add a note to `docs/ARCHITECTURE.md` under a new `## Proposed Additions` section and stop.

---

## F. Agent Definitions

### Agent 0: Integrator (You — the human)

**Role:** Repo owner. Creates branches, dispatches Codex sessions, merges PRs, resolves conflicts.

**Owns:** `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `.env.example`, `outputs/.gitkeep`, repo-level git operations.

**Workflow:**
1. Bootstrap repo (scaffold + `git init` + push to GitHub)
2. Create all five agent branches
3. Open one Codex session per agent, paste the prompt
4. Merge in order: A → B → C → D → E (after each passes DoD checks)

---

### Agent A: Config & Schema

**Branch:** `agent-a/config-schema`

**Scope (may only edit these files):**
```
src/fluent_agent/constants.py
src/fluent_agent/config.py
src/fluent_agent/__init__.py
configs/example_naca2412.yaml
configs/example_naca0012.yaml
configs/schema_reference.yaml
tests/test_config.py
tests/conftest.py
```

**Depends on:** nothing (first to merge)

**Expected outputs:**
- `constants.py` — all enums, physical constants, preset dicts
- `config.py` — full Pydantic v2 model hierarchy (16 models), `from_yaml`, `to_yaml`, `@model_validator` for first-layer-height
- `__init__.py` — version string
- 3 YAML config files — valid, loadable
- `conftest.py` — shared fixtures
- `test_config.py` — 7+ tests

---

### Agent B: Physics Rules

**Branch:** `agent-b/physics-rules`

**Scope (may only edit these files):**
```
src/fluent_agent/physics_rules.py
tests/test_physics_rules.py
```

**Depends on:** Agent A (imports `constants.py`)

**Expected outputs:**
- `physics_rules.py` — 6 stateless decision functions
- `test_physics_rules.py` — 11+ tests

---

### Agent C: Geometry

**Branch:** `agent-c/geometry`

**Scope (may only edit these files):**
```
src/fluent_agent/geometry.py
geometries/naca2412.csv
geometries/naca0012.csv
tests/test_geometry.py
```

**Depends on:** Agent A (imports `config.py` for `GeometryConfig`)

**Expected outputs:**
- `geometry.py` — `GeometryHandler` class (load, chord, TE closure, export)
- 2 CSV files — real NACA coordinates (200 points each, cosine-spaced)
- `test_geometry.py` — 6+ tests

---

### Agent D: CLI & Logger

**Branch:** `agent-d/cli-logger`

**Scope (may only edit these files):**
```
src/fluent_agent/cli.py
src/fluent_agent/logger.py
```

**Depends on:** Agent A (imports `config.py`)

**Expected outputs:**
- `logger.py` — `AgentLogger` class with rich terminal + file logging
- `cli.py` — Click CLI with 4 commands: `run` (stub body), `prompt` (stub body), `validate` (fully working — loads config, prints validation result), `--dry-run` flag
- No test file in Phase 1 (CLI tested manually; logger is thin wrapper)

---

### Agent E: Docs & Packaging

**Branch:** `agent-e/docs-packaging`

**Scope (may only edit these files):**
```
README.md
LICENSE
pyproject.toml
.env.example
.gitignore
docs/ARCHITECTURE.md
docs/CONTRIBUTING.md
prompts/config_generation.md
```

**Depends on:** Agent A (needs to reference schema in README and prompts)

**Expected outputs:**
- `README.md` — per spec Section 9
- `LICENSE` — MIT, 2025, "Yoseph Keisi"
- `pyproject.toml` — per spec Section 10
- `.env.example` — template with `ANTHROPIC_API_KEY` and `FLUENT_PATH`
- `docs/ARCHITECTURE.md` — already written, Agent E polishes/finalizes
- `docs/CONTRIBUTING.md` — contribution guidelines
- `prompts/config_generation.md` — system prompt per spec Section 5

---

## G. Agent Prompts (Copy-Paste into Codex)

### Prompt for Agent A

```
You are implementing Phase 1 of FluentAgent — the config schema layer.

CONTEXT FILES (read these first):
- CLAUDE.md (full spec — Sections 3, 4.1, 11 are most relevant)
- docs/ARCHITECTURE.md (system design)
- AGENTS.md Section F "Agent A" (your exact scope)

YOUR TASK — implement these files and nothing else:

1. src/fluent_agent/__init__.py
   - Single line: __version__ = "0.1.0"

2. src/fluent_agent/constants.py
   - Sea-level ISA air properties: RHO_AIR_SL=1.225, MU_AIR_SL=1.7894e-5, GAMMA_AIR=1.4, R_AIR=287.058, T_SL=288.15, P_SL=101325.0
   - Enums (str, Enum): TurbulenceModel (spalart-allmaras, k-epsilon-realizable, k-omega-sst, transition-sst), DomainType (c-type, h-type, rectangular), MeshFineness (coarse, medium, fine, ultra-fine), ConvergenceStatus (converged, diverged, stagnated, max_iterations_reached, needs_mesh_refinement)
   - MESH_FINENESS_PRESETS: dict mapping MeshFineness → {min_size, max_size, curvature_normal_angle}
   - DEFAULT_QUALITY_GATES: {min_orthogonal_quality: 0.15, max_skewness: 0.90, max_aspect_ratio: 100}
   - DEFAULT_URF and CONSERVATIVE_URF dicts

3. src/fluent_agent/config.py
   - Pydantic v2 BaseModel hierarchy: GeometryConfig, DomainConfig, InflationConfig, SurfaceSizingConfig, QualityGatesConfig, MeshConfig, FluidConfig, FlowConfig, DiscretizationConfig, ResidualTargetsConfig, ConvergenceConfig, AdaptiveRetryConfig, SolverConfig, PlotsConfig, OutputConfig, SimulationConfig
   - Field defaults exactly as specified in CLAUDE.md Section 3
   - Validators: reynolds_number > 0, angle_of_attack in [-90,90], enum membership
   - @model_validator(mode="after") on SimulationConfig: compute first_layer_height from y+ target using flat-plate BL correlation:
     Cf = 0.058 * Re_L^(-0.2), tau_w = 0.5*Cf*rho*U^2, u_tau = sqrt(tau_w/rho), y = (y_plus * mu) / (u_tau * rho)
   - from_yaml(path) classmethod, to_yaml(path) instance method
   - Use "from __future__ import annotations" at the top

4. configs/example_naca2412.yaml — complete valid config: Re=3e6, AoA=0, k-omega-sst, C-type, medium mesh, y+=1.0, geometry file_path "geometries/naca2412.csv"
5. configs/example_naca0012.yaml — Re=6e6, AoA=0, similar structure, geometry file_path "geometries/naca0012.csv"
6. configs/schema_reference.yaml — full schema with inline # comments on every field

7. tests/conftest.py — fixtures: sample_config_path, sample_geometry_path, naca0012_geometry_path pointing to the real files

8. tests/test_config.py — at minimum these tests:
   - test_load_valid_config (load example_naca2412.yaml, assert no error, check Re=3e6)
   - test_invalid_reynolds_number (negative Re raises ValidationError)
   - test_invalid_angle_of_attack (AoA=100 raises ValidationError)
   - test_first_layer_height_auto_computation (None → computed positive float)
   - test_default_values (minimal config → all defaults populated)
   - test_serialization_roundtrip (load → save to tmp → load → assert equal)
   - test_invalid_turbulence_model (bad string raises ValidationError)

RULES:
- Pydantic v2 only (model_validator, field_validator, model_dump)
- All functions type-annotated
- from __future__ import annotations at top of every .py file
- Do NOT touch any file outside your scope list
- Run: pytest tests/test_config.py -v (must pass)
- Run: ruff check src/fluent_agent/constants.py src/fluent_agent/config.py tests/test_config.py (must pass, line-length 100)
```

### Prompt for Agent B

```
You are implementing Phase 1 of FluentAgent — the physics rules module.

CONTEXT FILES (read these first):
- CLAUDE.md Section 4.7 (physics_rules.py spec)
- src/fluent_agent/constants.py (already implemented — read it for enums and constants)
- AGENTS.md Section F "Agent B" (your exact scope)

YOUR TASK — implement these files and nothing else:

1. src/fluent_agent/physics_rules.py
   Implement 6 stateless functions:

   a) recommend_turbulence_model(re: float, mach: float, application: str = "external") -> str
      Rules: Re < 5e5 + transition → "transition-sst"; Re 5e5–1e7 + external → "k-omega-sst";
      Re > 1e7 + attached → "spalart-allmaras"; internal → "k-epsilon-realizable"; default "k-omega-sst"

   b) recommend_domain_sizing(geometry_type: str = "airfoil") -> dict
      Airfoil C-type: {"upstream": 15, "downstream": 25, "lateral": 15}
      Bluff body: {"upstream": 10, "downstream": 30, "lateral": 10}

   c) recommend_y_plus_target(turbulence_model: str) -> float
      k-omega-sst, spalart-allmaras, transition-sst → 1.0; k-epsilon-realizable → 30.0

   d) validate_y_plus_results(measured_y_plus: np.ndarray, model: str) -> dict
      Returns {"valid": bool, "mean_y_plus": float, "max_y_plus": float, "warnings": list[str]}
      For wall-resolved models (SST, SA, transition): warn if max > 5. For k-epsilon: warn if < 20 or > 100.

   e) recommend_discretization_strategy(is_first_run: bool = True) -> dict
      First run: {"pressure": "second-order", "momentum": "second-order-upwind", ...}
      Retry: {"pressure": "standard", "momentum": "first-order-upwind", ...}

   f) recommend_urf(turbulence_model: str, is_retry: bool = False) -> dict
      Normal: DEFAULT_URF from constants. Retry: CONSERVATIVE_URF from constants.

2. tests/test_physics_rules.py — at minimum these tests:
   - test_recommend_turbulence_model_external_high_re (Re=3e6 → k-omega-sst)
   - test_recommend_turbulence_model_low_re (Re=1e5 → transition-sst)
   - test_recommend_turbulence_model_very_high_re (Re=2e7 → spalart-allmaras)
   - test_recommend_turbulence_model_internal (Re=1e6, "internal" → k-epsilon-realizable)
   - test_recommend_y_plus_target_sst (→ 1.0)
   - test_recommend_y_plus_target_ke (→ 30.0)
   - test_recommend_domain_sizing_airfoil (upstream=15, downstream=25, lateral=15)
   - test_recommend_urf_normal (returns DEFAULT_URF values)
   - test_recommend_urf_retry (returns CONSERVATIVE_URF values)
   - test_validate_y_plus_good (all ~1 for SST → valid=True)
   - test_validate_y_plus_bad (all ~10 for SST → valid=False, has warnings)

RULES:
- Import enums/constants from fluent_agent.constants
- from __future__ import annotations at top
- All functions type-annotated
- numpy is allowed for validate_y_plus_results
- Do NOT touch any file outside your scope list
- Run: pytest tests/test_physics_rules.py -v (must pass)
```

### Prompt for Agent C

```
You are implementing Phase 1 of FluentAgent — the geometry module and NACA airfoil data files.

CONTEXT FILES (read these first):
- CLAUDE.md Sections 4.2 and 6 (geometry.py spec + NACA formulas)
- src/fluent_agent/config.py (already implemented — read GeometryConfig model)
- AGENTS.md Section F "Agent C" (your exact scope)

YOUR TASK — implement these files and nothing else:

1. geometries/naca2412.csv
   Generate NACA 2412 coordinates using the standard NACA 4-digit formula:
   - m=0.02, p=0.4, t=0.12
   - 200 points total: 100 upper + 100 lower surface
   - Cosine spacing: x_raw = 0.5*(1 - cos(theta)) for theta from 0 to pi
   - Thickness: yt = 5*t*(0.2969*sqrt(x) - 0.1260*x - 0.3516*x^2 + 0.2843*x^3 - 0.1015*x^4)
   - Camber and camber gradient per standard NACA formulas
   - Upper: xu = x - yt*sin(theta_c), yu = yc + yt*cos(theta_c)
   - Lower: xl = x + yt*sin(theta_c), yl = yc - yt*cos(theta_c)
   - Header row: x,y
   - Order: trailing edge upper → leading edge → trailing edge lower
   - Chord normalized to 1.0

2. geometries/naca0012.csv
   Same approach, symmetric (m=0, p=0): upper = (x, yt), lower = (x, -yt). 200 points.

3. src/fluent_agent/geometry.py
   Class GeometryHandler:
   - __init__(self, config: GeometryConfig)
   - load(self) -> np.ndarray: Read CSV (x,y columns), validate 2 columns, check for NaN, return Nx2 array
   - compute_chord(self) -> float: max(x) - min(x) from loaded coords
   - close_trailing_edge(self, coords: np.ndarray) -> np.ndarray: if gap between first/last point > 1e-6*chord, insert average point
   - export_for_meshing(self, output_path: str) -> str: write clean CSV to output_path, return path
   Store loaded coords in self._coords (set by load()). Raise ValueError for bad data.

4. tests/test_geometry.py — at minimum:
   - test_load_naca2412 (load CSV, check shape ~ (200, 2))
   - test_load_naca0012 (same)
   - test_chord_length (computed chord within 0.02 of 1.0)
   - test_trailing_edge_closure (create open-TE coords, verify closure adds a point)
   - test_reject_malformed_csv (single column → raises error)
   - test_reject_nan_values (NaN in data → raises error)

RULES:
- Import GeometryConfig from fluent_agent.config
- from __future__ import annotations at top
- numpy and pandas are allowed
- The CSV files must contain ACTUAL COMPUTED coordinate data, not placeholders
- Do NOT touch any file outside your scope list
- Run: pytest tests/test_geometry.py -v (must pass)
```

### Prompt for Agent D

```
You are implementing Phase 1 of FluentAgent — the CLI and logger modules.

CONTEXT FILES (read these first):
- CLAUDE.md Sections 4.9 and 4.10 (cli.py and logger.py specs)
- src/fluent_agent/config.py (already implemented — SimulationConfig.from_yaml used by CLI)
- AGENTS.md Section F "Agent D" (your exact scope)

YOUR TASK — implement these files and nothing else:

1. src/fluent_agent/logger.py
   Class AgentLogger:
   - __init__(self, name: str = "fluent-agent", output_dir: str | None = None)
   - Creates a Python logging.Logger
   - Adds a rich.logging.RichHandler for terminal output (colorized, with timestamps)
   - If output_dir is provided, adds a FileHandler writing to {output_dir}/run.log
   - Methods: info, warning, error, debug (delegates to underlying logger)
   - stage(self, name: str) → logs a prominent header like "━━━ [MESHING] ━━━" using rich markup
   - summary(self, data: dict) → logs a formatted summary table using rich.table.Table

2. src/fluent_agent/cli.py
   Click-based CLI group "fluent-agent" with entry point main():

   a) validate command: --config PATH (required)
      - Loads config with SimulationConfig.from_yaml(path)
      - On success: prints "Config valid" + summary (geometry file, Re, turb model, mesh fineness) via rich
      - On ValidationError: prints error details, exits code 1

   b) run command: --config PATH (required)
      - Loads and validates config (same as validate)
      - Prints "Orchestrator not yet implemented (Phase 2)" and exits
      - This is a stub — do NOT import orchestrator.py

   c) prompt command: PROMPT (argument), --dry-run flag, --output PATH (optional)
      - Prints "NLP interface not yet implemented (Phase 3)" and exits
      - This is a stub — do NOT import nlp_interface.py

   All commands should use AgentLogger for output.

RULES:
- Import SimulationConfig from fluent_agent.config
- Import AgentLogger from fluent_agent.logger
- Use click for CLI, rich for display
- from __future__ import annotations at top
- All functions type-annotated
- Do NOT touch any file outside your scope list
- Manual test: python -m fluent_agent.cli validate --config configs/example_naca2412.yaml (should print valid)
```

### Prompt for Agent E

```
You are implementing Phase 1 of FluentAgent — documentation, packaging, and project files.

CONTEXT FILES (read these first):
- CLAUDE.md Sections 5, 9, 10 (system prompt, README structure, pyproject.toml)
- docs/ARCHITECTURE.md (already written — review and polish it)
- AGENTS.md Section F "Agent E" (your exact scope)

YOUR TASK — implement these files and nothing else:

1. pyproject.toml — exact content from CLAUDE.md Section 10. Use hatchling build backend.

2. README.md — per CLAUDE.md Section 9:
   - Header: "FluentAgent" + one-line description
   - What it does (3–4 sentences)
   - Quickstart (run example config)
   - Installation (pip install -e ., ANSYS license note, .env setup)
   - Usage (config mode, NLP mode, dry run, validate)
   - Config reference (link to schema_reference.yaml)
   - Architecture (link to docs/ARCHITECTURE.md)
   - Limitations (requires ANSYS license, 2D only, RANS only)
   - Roadmap (OpenFOAM, 3D, optimization)
   - License (MIT)

3. LICENSE — MIT license, year 2025, copyright "Yoseph Keisi"

4. .env.example:
   ANTHROPIC_API_KEY=your-api-key-here
   FLUENT_PATH=/path/to/ansys/fluent

5. .gitignore — Python standard: __pycache__, *.pyc, .env, *.egg-info, dist, build, .venv, venv, outputs/ (except .gitkeep), .pytest_cache, *.msh, *.cas, *.dat, .ruff_cache

6. docs/ARCHITECTURE.md — already exists. Review it. Fix any inconsistencies with CLAUDE.md. Add a "## Proposed Additions" section at the bottom (empty, for future stop-condition notes).

7. docs/CONTRIBUTING.md — short contribution guidelines: fork, branch, test, PR, code style (ruff, type hints).

8. prompts/config_generation.md — system prompt per CLAUDE.md Section 5. Include: role definition, CFD knowledge areas, decision rules for turbulence model / domain / mesh / flow conditions, the full config YAML schema with field descriptions, output rules (YAML only, all fields present, physically reasonable).

RULES:
- Do NOT touch any Python source files
- Do NOT touch any file outside your scope list
- All docs should be concise but complete
```

---

## H. Merge Order & Dependency Chain

```
Step 1:  merge agent-a/config-schema → main       (no deps)
Step 2:  merge agent-b/physics-rules → main        (needs constants.py from A)
Step 3:  merge agent-c/geometry → main              (needs config.py from A)
Step 4:  merge agent-d/cli-logger → main            (needs config.py from A)
Step 5:  merge agent-e/docs-packaging → main        (needs schema from A for docs)
```

Steps 2–4 can run in parallel as Codex sessions since they all depend only on A. But they merge sequentially to avoid conflicts. Step 5 can start in parallel too (docs don't import Python) but merges last.

---

## I. VS Code + Windows Workflow

### Prerequisites

- Python 3.10+ installed
- Git installed
- VS Code with Codex extension
- GitHub CLI (`gh`) installed and authenticated

### Step-by-step

#### 1. Bootstrap the repo (one-time, PowerShell)

```powershell
cd C:\Users\keisi\Documents
cd FluentAgent

# Init git
git init
git add .
git commit -m "scaffold: directory structure + AGENTS.md + ARCHITECTURE.md"

# Create GitHub repo and push
gh repo create yoseph-keisi/FluentAgent --public --source=. --remote=origin --push
```

#### 2. Create agent branches

```powershell
git checkout -b agent-a/config-schema
git push -u origin agent-a/config-schema
git checkout main

git checkout -b agent-b/physics-rules
git push -u origin agent-b/physics-rules
git checkout main

git checkout -b agent-c/geometry
git push -u origin agent-c/geometry
git checkout main

git checkout -b agent-d/cli-logger
git push -u origin agent-d/cli-logger
git checkout main

git checkout -b agent-e/docs-packaging
git push -u origin agent-e/docs-packaging
git checkout main
```

#### 3. Set up Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

(Run this after Agent E writes `pyproject.toml`, or write a minimal one first — see bootstrap section.)

#### 4. Open Codex sessions

For each agent:
1. In VS Code, open a new Codex chat (Ctrl+Shift+P → "Codex: New Chat" or equivalent)
2. Switch to the agent's branch first: `git checkout agent-a/config-schema`
3. Paste the agent's prompt from Section G above
4. Let Codex implement. Review the diff.
5. Run the DoD checks:

```powershell
pytest tests/ -v
ruff check src/ tests/
python -c "from fluent_agent.config import SimulationConfig; SimulationConfig.from_yaml('configs/example_naca2412.yaml')"
```

6. Commit and push:

```powershell
git add -A
git commit -m "agent-a: implement config schema + constants + YAML configs + tests"
git push
```

#### 5. Merge sequence

```powershell
# Merge A first
git checkout main
git merge agent-a/config-schema
git push

# Then B (rebase onto updated main first)
git checkout agent-b/physics-rules
git rebase main
# resolve any conflicts if needed
git checkout main
git merge agent-b/physics-rules
git push

# Then C
git checkout agent-c/geometry
git rebase main
git checkout main
git merge agent-c/geometry
git push

# Then D
git checkout agent-d/cli-logger
git rebase main
git checkout main
git merge agent-d/cli-logger
git push

# Then E
git checkout agent-e/docs-packaging
git rebase main
git checkout main
git merge agent-e/docs-packaging
git push
```

#### 6. Final validation on main

```powershell
git checkout main
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
python -m fluent_agent.cli validate --config configs/example_naca2412.yaml
```

---

## J. Repo Bootstrap (Scaffold Only)

The directory tree and empty placeholder files should already exist (see bootstrap script below). The only files with actual content at bootstrap time are:

| File | Content |
|------|---------|
| `AGENTS.md` | This file |
| `CLAUDE.md` | Full spec (already exists) |
| `docs/ARCHITECTURE.md` | Architecture doc (already exists) |
| `src/fluent_agent/__init__.py` | Empty (Agent A fills it) |
| `outputs/.gitkeep` | Empty |
| `pyproject.toml` | Minimal version (enough for `pip install -e .`) |
| `.gitignore` | Python standard ignores |

Everything else is an empty file waiting for an agent to fill it.

---

## K. GitHub Repository

**Target:** `github.com/yoseph-keisi/FluentAgent`

Commands to create and push (after bootstrap):

```powershell
# If not already initialized:
cd C:\Users\keisi\Documents\FluentAgent
git init
git add .
git commit -m "scaffold: directory structure + AGENTS.md + ARCHITECTURE.md"

# Create repo on GitHub (public, MIT license already in repo)
gh repo create yoseph-keisi/FluentAgent --public --source=. --remote=origin --push

# Verify
gh repo view yoseph-keisi/FluentAgent --web
```

If you prefer the web UI:
1. Go to https://github.com/new
2. Name: `FluentAgent`, Public, do NOT initialize with README (we already have one)
3. Then locally:
```powershell
git remote add origin https://github.com/yoseph-keisi/FluentAgent.git
git branch -M main
git push -u origin main
```

---

## M. Repository Hygiene and Environment Isolation

### Critical Lessons Learned

During parallel agent development, the repository entered a broken state due to virtual environment tracking. This section documents the recovery process and establishes practices to prevent recurrence.

### Root Cause

**Virtual environment directories (`Lib/`, `Scripts/`, `share/`, `.venv/`) were accidentally tracked in git**, causing:
- 9,152 files tracked that should have been ignored
- 4.3M lines of dependency code in version control
- Merge conflicts during branch rebases (binary .exe files, package metadata)
- Broken merge state requiring manual intervention

### Why This Happened

1. **Dependencies installed before .gitignore was complete** — `pip install -e ".[dev]"` was run before .gitignore properly excluded virtual environment directories
2. **Worktrees created from contaminated branches** — branches with tracked virtual environments were used as worktree bases
3. **Cross-branch environment pollution** — different agents installed dependencies in their worktrees, each creating unique virtual environment states that git attempted to merge

### Recovery Steps Executed

```powershell
# 1. Abort any in-progress merge/rebase
git merge --abort  # or git rebase --abort

# 2. Remove all virtual environment tracking from main branch
git rm -r --cached Lib Scripts share .venv 2>/dev/null
git add .gitignore  # Ensure .gitignore is complete
git commit -m "repository hygiene: remove virtual environment tracking permanently"
git push origin main

# 3. Clean each agent branch
# For each branch, either:
#   a) Soft reset to main and recommit only implementation files, OR
#   b) git rm --cached to remove venv tracking, then rebase

# 4. Force-push cleaned branches
git push --force-with-lease

# 5. Rebase all agent branches onto cleaned main
# This must be done AFTER main is clean
```

### Mandatory .gitignore Entries

**ALWAYS include these in .gitignore from the start:**

```gitignore
# Virtual environments (Python)
.venv/
venv/
env/
Lib/
Scripts/
share/
pyvenv.cfg

# Python compiled
__pycache__/
*.py[cod]
*.pyo
*.pyd
*.so
*.egg-info/
dist/
build/

# IDE
.vscode/
.idea/
*.swp
*.swo
.claude/settings.local.json

# Environment variables
.env
.env.local
```

### Correct Workflow for Virtual Environments

#### Initial Setup (Once per Repository)

```powershell
# 1. Clone repository
git clone <repo-url>
cd <repo>

# 2. Verify .gitignore is present and complete
cat .gitignore  # Check for .venv/, Lib/, Scripts/, share/

# 3. Create virtual environment
python -m venv .venv

# 4. Activate virtual environment
.\.venv\Scripts\Activate.ps1  # Windows PowerShell
# source .venv/bin/activate    # Linux/macOS

# 5. Install dependencies ONLY after activation
pip install -e ".[dev]"

# 6. Verify virtual environment is NOT tracked
git status  # Should NOT show Lib/, Scripts/, .venv/
```

#### Worktree Setup (For Parallel Development)

```powershell
# 1. Create worktree
git worktree add C:\path\to\worktree\agent-b agent-b/branch-name

# 2. Navigate to worktree
cd C:\path\to\worktree\agent-b

# 3. Create virtual environment IN THE WORKTREE
python -m venv .venv

# 4. Activate and install
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 5. Verify .gitignore excludes virtual environment
git status  # Should be clean or show only your implementation files
```

#### Before EVERY Commit

```powershell
# Always check git status before committing
git status

# If you see Lib/, Scripts/, .venv/, or share/:
# DO NOT COMMIT. Something is wrong with .gitignore.

# Verify only implementation files are staged
git diff --cached --stat

# Commit only if status is clean
git commit -m "..."
```

### Tool Invocation on Windows

**Always use `py -m` for tool invocation**, not bare tool names:

```powershell
# Correct
py -m pytest
py -m ruff check src/
py -m fluent_agent.cli --help

# Incorrect (may use wrong Python interpreter)
pytest
ruff check src/
fluent-agent --help
```

### Merge Discipline

1. **Never merge while conflicts exist** — resolve or abort, never leave repository in conflicted state
2. **Always rebase feature branches onto main before merging** — ensures linear history and catches conflicts early
3. **Never force-push to main** — use force-push only on feature branches after rebases
4. **Verify clean working tree before branch creation** — `git status` should show clean state

### Pre-Merge Checklist

Before requesting a merge to main:

```powershell
# 1. Verify no virtual environment tracking
git status  # Should NOT show Lib/, Scripts/, .venv/, share/

# 2. Verify only scope files are changed
git diff --name-only origin/main  # Should match your agent's scope

# 3. Verify tests pass (in virtual environment)
.\.venv\Scripts\Activate.ps1
py -m pytest tests/

# 4. Verify linter passes
py -m ruff check src/ tests/

# 5. Verify imports work
py -c "from fluent_agent import config, constants, physics_rules, geometry, cli, logger; print('OK')"
```

### Recovery Commands Reference

If you accidentally track virtual environments:

```powershell
# Stop tracking (but keep local files)
git rm -r --cached Lib Scripts share .venv

# Stage .gitignore update
git add .gitignore

# Commit removal
git commit -m "fix: remove virtual environment from tracking"

# Push to remote
git push origin <branch-name>
```

### Architecture-Level Principle

**Virtual environments are runtime artifacts, not source code.**

- Source code: committed to git
- Dependencies: declared in `pyproject.toml`, installed at runtime
- Virtual environments: ephemeral, created locally, never committed

This separation ensures:
- Repository stays small (~MB, not GB)
- Merges are conflict-free
- Different developers can use different Python versions
- CI/CD systems can recreate environments reliably

---
