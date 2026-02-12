# FluentAgent Architecture

> Autonomous CFD Simulation Orchestrator with Adaptive Retry Logic

---

## 1. System Overview

FluentAgent is a Python orchestrator that drives ANSYS Fluent CFD simulations end-to-end. It replaces a multi-day manual engineering workflow with a single command by encoding expert CFD heuristics into an autonomous retry loop.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER ENTRY POINTS                            │
│                                                                     │
│   fluent-agent run --config <yaml>        (Config Mode / Pipeline 2)│
│   fluent-agent prompt "simulate ..."      (NLP Mode   / Pipeline 1) │
│   fluent-agent validate --config <yaml>   (Validation only)         │
│   fluent-agent prompt "..." --dry-run     (Generate config only)    │
│                                                                     │
└────────────────┬──────────────────────────┬─────────────────────────┘
                 │                          │
                 │  Config Mode             │  NLP Mode
                 │                          │
                 ▼                          ▼
         ┌──────────────┐         ┌──────────────────┐
         │  YAML Config │         │ NLPConfigGenerator│
         │  (on disk)   │         │  (Claude API)     │
         └──────┬───────┘         └────────┬─────────┘
                │                          │
                │   SimulationConfig        │  SimulationConfig
                │   (Pydantic-validated)   │  (Pydantic-validated)
                └──────────┬───────────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ SimulationOrchestrator│
                │   (master loop)      │
                └──────────┬──────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────────┐
        │ Geometry │ │  Mesh    │ │   Solver     │
        │ Handler  │ │Generator │ │  Manager     │
        └────┬─────┘ └────┬─────┘ └──────┬───────┘
             │            │               │
             │            │               │
             │            ▼               ▼
             │      ┌──────────┐   ┌──────────────┐
             │      │ Quality  │   │ Convergence  │
             │      │  Gates   │   │  Monitor     │
             │      └──────────┘   └──────────────┘
             │                            │
             │                            ▼
             │                     ┌──────────────┐
             │                     │PostProcessor  │
             │                     │ (plots,       │
             │                     │  reports,     │
             │                     │  data export) │
             │                     └──────────────┘
             │
             ▼
       ┌───────────────┐
       │ PyFluent API   │
       │ (ANSYS Fluent) │
       └───────────────┘
```

---

## 2. Operational Modes

### 2.1 Config Mode (Pipeline 2 — Primary)

The user provides a geometry file and a structured YAML config. The orchestrator validates the config via Pydantic, then executes geometry intake, meshing, solving, and post-processing autonomously with intelligent retry logic.

**Data flow:** `YAML file → SimulationConfig → Orchestrator → [Geometry → Mesh → Solve → Post] → Outputs`

### 2.2 Natural Language Mode (Pipeline 1 — Secondary)

The user provides a plain-English prompt. The `NLPConfigGenerator` calls the Claude API with a physics-aware system prompt, receives YAML, validates it through the same Pydantic schema, and hands the resulting `SimulationConfig` to the orchestrator. From that point forward, both pipelines are identical.

**Data flow:** `English prompt → Claude API → YAML → SimulationConfig → Orchestrator → [Geometry → Mesh → Solve → Post] → Outputs`

This design means the NLP layer is a pure *translator*. It has zero coupling to the simulation engine. Testing and debugging each layer is independent.

---

## 3. The Config Contract

The YAML config schema (`SimulationConfig`) is the single most important design artifact. It is the **contract** between:

- The NLP layer (producer) and the engine (consumer)
- The user (author) and the orchestrator (executor)
- The current Fluent backend and any future backend (OpenFOAM, etc.)

### 3.1 Schema Sections

| Section    | Pydantic Model         | Purpose                                                  |
|------------|------------------------|----------------------------------------------------------|
| `geometry` | `GeometryConfig`       | Source file, format, chord length, reference area        |
| `domain`   | `DomainConfig`         | Domain type and sizing relative to chord                 |
| `mesh`     | `MeshConfig`           | Strategy, sizing, inflation, quality gates, retry limits |
| `flow`     | `FlowConfig`           | Re, velocity, AoA, Mach, fluid properties                |
| `solver`   | `SolverConfig`         | Turbulence model, schemes, convergence, adaptive retry   |
| `output`   | `OutputConfig`         | Directory, exports, plot toggles, report generation      |

### 3.2 Derived Quantity Computation

A `@model_validator` on `SimulationConfig` computes quantities that depend on cross-section values:

- **First-layer height** from `target_y_plus`, `reynolds_number`, `chord_length`, and `freestream_velocity` using the flat-plate boundary layer correlation.
- **Freestream velocity** from Reynolds number if not explicitly provided.
- **Mach number** from velocity and standard atmosphere if not provided.

This ensures the config is always internally consistent regardless of which entry point produced it.

---

## 4. Module Architecture

### 4.1 Module Dependency Graph

```
cli.py
  ├── orchestrator.py
  │     ├── config.py          (loads/validates YAML)
  │     ├── geometry.py        (geometry intake)
  │     ├── meshing.py         (mesh generation + quality retry)
  │     │     ├── physics_rules.py
  │     │     └── constants.py
  │     ├── solver.py          (solver execution + convergence retry)
  │     │     ├── physics_rules.py
  │     │     └── constants.py
  │     ├── postprocessor.py   (results + plots + reports)
  │     └── logger.py          (structured logging)
  │
  └── nlp_interface.py         (Claude API → SimulationConfig)
        ├── config.py
        └── physics_rules.py
```

Key observation: `physics_rules.py` is consumed by both the engine modules (for adaptive decisions during retry) and the NLP module (for encoding engineering heuristics into the system prompt). It is the shared "brain" of the system.

### 4.2 Module Responsibilities

#### `constants.py` — Physical Constants & Enums

Stateless module. Defines:
- Sea-level air properties (`RHO_AIR_SL`, `MU_AIR_SL`, `GAMMA_AIR`, `R_AIR`, `T_SL`, `P_SL`)
- `TurbulenceModel(str, Enum)` — `spalart-allmaras`, `k-epsilon-realizable`, `k-omega-sst`, `transition-sst`
- `DomainType(str, Enum)` — `c-type`, `h-type`, `rectangular`
- `MeshFineness(str, Enum)` — `coarse`, `medium`, `fine`, `ultra-fine`
- Fineness preset dictionaries mapping each level to sizing parameters
- Default quality gate thresholds
- Default solver scheme tables per turbulence model

#### `config.py` — Configuration Schema & Validation

Pydantic v2 `BaseModel` hierarchy:
- `GeometryConfig`, `DomainConfig`, `InflationConfig`, `SurfaceSizingConfig`, `QualityGatesConfig`, `MeshConfig`, `FluidConfig`, `FlowConfig`, `DiscretizationConfig`, `ConvergenceConfig`, `AdaptiveRetryConfig`, `SolverConfig`, `OutputConfig`
- Top-level `SimulationConfig` with `@model_validator` for derived quantities
- `from_yaml(path) → SimulationConfig` class method
- `to_yaml(path)` instance method
- Field validators: `reynolds_number > 0`, `angle_of_attack ∈ [-90, 90]`, enum membership, etc.

#### `geometry.py` — Geometry Intake

`GeometryHandler` class:
- Loads CSV (x, y columns), validates ordering around airfoil contour
- Closes open trailing edges by averaging first/last points
- Computes chord length and cross-checks against config
- Exports geometry in PyFluent-compatible format
- Future: STEP/STL/IGES loaders behind the same interface

#### `meshing.py` — Mesh Generation with Quality Retry

`MeshGenerator` class. **This is the first intelligence module.**

Inner loop:
```
for attempt in range(max_retries):
    generate_mesh(current_params)
    report = check_quality(session)
    if report.passed:
        return MeshResult(success)
    current_params = adjust_parameters(report, attempt)
raise MeshQualityError(diagnostics)
```

Adjustment rules:
| Failure            | Action                                              |
|--------------------|-----------------------------------------------------|
| High skewness      | Reduce max element size by 20%, increase smoothing  |
| Low ortho quality  | Reduce growth rate by 0.05, add smoothing passes    |
| High aspect ratio  | Adjust first-layer height or growth rate             |

Produces `MeshResult` (mesh path, final quality metrics, attempt log).

#### `solver.py` — Solver Execution with Convergence Retry

`SolverManager` class. **This is the second intelligence module.**

Runs iterations in **batches** (e.g., 500 at a time). After each batch:

```
status = check_convergence(history)
match status:
    CONVERGED   → return success
    DIVERGED    → apply_retry_strategy(n)
    STAGNATED   → apply_retry_strategy(n, conservative=True)
    MAX_ITERS   → return partial results
```

Retry strategy ladder (applied in order):

| Retry # | Strategy                                                      |
|---------|---------------------------------------------------------------|
| 1       | Drop to first-order for 500 iters, then ramp to second-order |
| 2       | Reduce URFs (pressure→0.2, momentum→0.5, turbulence→0.6)     |
| 3       | Switch to FMG initialization and restart                      |
| 4       | Return `NEEDS_REMESH` to orchestrator for mesh refinement     |

Divergence detection: any residual > 1e6 or NaN.
Convergence detection: all residuals below targets AND Cl/Cd stable over configured window.
Stagnation detection: residuals plateaued above targets for 2+ consecutive batches.

Produces `SolverResult` (status, final residuals, Cl, Cd, histories, retry log).

#### `postprocessor.py` — Results & Reporting

`PostProcessor` class:
- Extracts Cl, Cd, Cm from Fluent session
- Extracts Cp distribution (pressure coefficient vs x/c)
- Extracts wall y+ distribution
- Generates matplotlib plots: residual history, Cl/Cd convergence, Cp distribution, y+ distribution
- Exports raw data as CSV
- Generates a Markdown summary report with run metadata, mesh stats, solver performance, final results, embedded plot references, and warnings
- Saves Fluent .cas and .dat files

#### `orchestrator.py` — Master Control Loop

`SimulationOrchestrator` class. Outer loop with mesh-solver cycling:

```
for cycle in range(max_mesh_solver_cycles):     # default: 2
    mesh_result = MeshGenerator.generate()
    if mesh_failed: abort(diagnostics)

    solver_result = SolverManager.run()
    match solver_result.status:
        CONVERGED | MAX_ITERATIONS:
            PostProcessor.run()
            return RunResult(success)
        NEEDS_REMESH:
            refine_mesh_params()  # reduce sizing 30%, add layers
            continue
        DIVERGED:
            abort(diagnostics)
```

Produces `RunResult` (success flag, status, output dir, Cl, Cd, wall time, error message).

#### `physics_rules.py` — Engineering Heuristics

`PhysicsAdvisor` — stateless decision functions:

| Function                          | Input                    | Output                          |
|-----------------------------------|--------------------------|---------------------------------|
| `recommend_turbulence_model`      | Re, Mach, application   | Turbulence model string         |
| `recommend_domain_sizing`         | geometry type            | Upstream/downstream/lateral     |
| `recommend_y_plus_target`         | turbulence model         | Target y+ value                 |
| `validate_y_plus_results`         | measured y+[], model     | Pass/fail + diagnostics         |
| `recommend_discretization_strategy` | is_first_run           | Discretization scheme dict      |
| `recommend_urf`                   | turbulence model, retry? | Under-relaxation factor dict    |

#### `nlp_interface.py` — Natural Language → Config Translation

`NLPConfigGenerator` class:
1. Load system prompt from `prompts/config_generation.md`
2. Send user prompt + system prompt to Claude API (`claude-sonnet-4-20250514`)
3. Parse returned YAML
4. Validate with Pydantic (`SimulationConfig`)
5. On validation failure: send error + failed YAML back to Claude for one correction attempt
6. Return validated `SimulationConfig`

The NLP layer is a pure translator with zero coupling to the engine. It could be replaced by any other LLM or even a rule-based parser.

#### `logger.py` — Structured Logging

`AgentLogger` class:
- Wraps Python `logging` with `rich` for terminal output
- Stage transition headers: `[GEOMETRY] → [MESHING] → [SOLVER] → [POST]`
- Quality gate pass/fail with specific metric values
- Retry attempts with strategy descriptions
- Convergence monitor values at each batch
- Final summary with wall time, status, result paths
- Simultaneous file logging to `{output_dir}/run.log`

#### `cli.py` — Command-Line Interface

Click-based CLI with four commands:
- `run --config <path>` — Config mode execution
- `prompt "<text>"` — NLP mode execution
- `prompt "<text>" --dry-run --output <path>` — Generate config only
- `validate --config <path>` — Validate config without execution

---

## 5. Data Flow & Lifecycle

### 5.1 Object Lifecycle

```
YAML file (or Claude API response)
    │
    ▼
SimulationConfig  ─────────────────────────────────────────────┐
    │                                                           │
    ├─► GeometryHandler.load() → np.ndarray (Nx2 coords)       │
    │                                                           │
    ├─► MeshGenerator.generate() → MeshResult                   │
    │       ├── mesh_path: str                                  │
    │       ├── final_quality: QualityReport                    │
    │       ├── attempts: int                                   │
    │       └── iteration_log: list[dict]                       │
    │                                                           │
    ├─► SolverManager.run() → SolverResult                      │
    │       ├── status: ConvergenceStatus                       │
    │       ├── iterations_run: int                             │
    │       ├── final_residuals: dict[str, float]               │
    │       ├── cl, cd: float                                   │
    │       ├── residual_history: pd.DataFrame                  │
    │       ├── coefficient_history: pd.DataFrame               │
    │       └── retry_log: list[dict]                           │
    │                                                           │
    └─► PostProcessor → SimulationResults                       │
            ├── plots: list[str] (file paths)                   │
            ├── csv_exports: list[str]                          │
            ├── report_path: str                                │
            └── case_data_paths: tuple[str, str]                │
                                                                │
    RunResult  ◄────────────────────────────────────────────────┘
        ├── success: bool
        ├── status: str
        ├── output_directory: str
        ├── cl, cd: float
        ├── total_mesh_attempts: int
        ├── total_solver_attempts: int
        └── total_wall_time: float
```

### 5.2 Error Propagation

Errors are classified into two categories:

| Type        | Examples                                    | Handling                           |
|-------------|---------------------------------------------|------------------------------------|
| Recoverable | Mesh quality below gates, solver divergence | Retry with adjusted parameters     |
| Fatal       | License unavailable, file not found, schema invalid | Abort with diagnostic message |

Recoverable errors are handled within each module's retry loop. If a module exhausts its retries, it raises a typed exception (`MeshQualityError`, `SolverDivergenceError`) that the orchestrator catches and decides whether to escalate (e.g., trigger remeshing) or abort.

Fatal errors propagate immediately to the CLI layer, which displays them with `rich` formatting and writes them to the run log.

---

## 6. PyFluent Integration Layer

### 6.1 Session Management

```
┌─────────────────────────────────────────────┐
│           PyFluent Session Lifecycle          │
│                                               │
│  Option A: Separate sessions                  │
│  meshing_session = launch_fluent("meshing")   │
│  ... mesh ...                                 │
│  meshing_session.exit()                       │
│  solver_session = launch_fluent("solver")     │
│  solver_session.file.read_mesh(path)          │
│                                               │
│  Option B: Session transition                 │
│  meshing_session = launch_fluent("meshing")   │
│  ... mesh ...                                 │
│  solver_session = meshing_session.switch_to_solver() │
│                                               │
└─────────────────────────────────────────────┘
```

The orchestrator manages session lifecycle. Modules receive an active session, they do not create sessions themselves. This enables future flexibility (e.g., reusing sessions across parameter sweeps).

### 6.2 API Wrapping

All PyFluent calls are wrapped in `try/except` blocks with typed exceptions. The PyFluent API surface changes between versions, so wrappers provide a stable internal interface that insulates business logic from API churn.

### 6.3 Concurrency

PyFluent sessions are **not thread-safe**. The orchestrator is single-threaded. Future parallelism (e.g., AoA sweeps) must use separate processes, each with its own Fluent instance and license checkout.

---

## 7. Adaptive Intelligence System

The "intelligence" of FluentAgent lives in two feedback loops:

### 7.1 Mesh Quality Loop (inner)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Generate     │────►│ Check        │────►│ Adjust       │
│ Mesh         │     │ Quality      │     │ Parameters   │
└──────────────┘     └──────┬───────┘     └──────┬───────┘
       ▲                    │                     │
       │              PASS? │              FAIL   │
       │                    ▼                     │
       │             Return MeshResult            │
       │                                          │
       └──────────────────────────────────────────┘
                    (up to max_retry_attempts)
```

### 7.2 Solver Convergence Loop (inner)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Run Batch    │────►│ Check        │────►│ Apply Retry  │
│ (500 iters)  │     │ Convergence  │     │ Strategy     │
└──────────────┘     └──────┬───────┘     └──────┬───────┘
       ▲                    │                     │
       │           CONVERGED│         DIVERGED/   │
       │                    ▼         STAGNATED   │
       │             Return SolverResult          │
       │                                          │
       └──────────────────────────────────────────┘
                    (up to max_retries)
```

### 7.3 Mesh-Solver Outer Loop (orchestrator)

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Mesh Stage   │────►│ Solver Stage │────►│ Post Stage   │
│              │     │              │     │              │
└──────────────┘     └──────┬───────┘     └──────────────┘
       ▲                    │
       │         NEEDS_REMESH│
       │                    │
       └────────────────────┘
          (refine mesh params, max 2 cycles)
```

This three-tier retry architecture means FluentAgent can recover from a wide range of failures autonomously — poor initial mesh, solver instability, inappropriate discretization — before giving up and reporting diagnostics.

---

## 8. Output Structure

Each run produces a self-contained output directory:

```
outputs/run_001/
├── run.log                          # Full structured log
├── mesh.msh                         # Final Fluent mesh
├── case.cas                         # Fluent case file
├── data.dat                         # Fluent data file
├── residuals.csv                    # Residual history
├── force_coefficients.csv           # Cl, Cd, Cm history
├── plots/
│   ├── residuals.png                # Residual convergence plot
│   ├── cl_cd_history.png            # Force coefficient convergence
│   ├── pressure_coefficient.png     # Cp vs x/c
│   └── wall_y_plus.png             # y+ distribution
└── report.md                        # Markdown summary report
```

Output directories are auto-incremented (`run_001`, `run_002`, ...) if the target directory already exists.

---

## 9. Extension Points

The architecture is designed for these future additions without refactoring:

### 9.1 Alternative Backends (OpenFOAM)

`MeshGenerator` and `SolverManager` are designed as concrete classes today but should be promoted to abstract base classes when a second backend is added:

```
MeshGeneratorBase (ABC)
  ├── FluentMeshGenerator
  └── OpenFOAMMeshGenerator

SolverManagerBase (ABC)
  ├── FluentSolverManager
  └── OpenFOAMSolverManager
```

The orchestrator works with the base interface. Backend selection is a config-level or CLI-level choice.

### 9.2 3D Support

`GeometryHandler` already accepts a `source_type` field. 3D support adds `stp`, `stl`, `igs` loaders. The mesh and solver modules gain 3D-specific parameters but the flow is unchanged.

### 9.3 Parameter Sweeps

The orchestrator's `run()` method returns a `RunResult`. A sweep runner calls `run()` in a loop (or across processes) with varying configs (e.g., AoA from -5 to 15 degrees), collecting results into a sweep-level report.

### 9.4 Optimization Loop

A genetic algorithm or surrogate model generates geometry variations, calls the orchestrator for each, and optimizes toward an objective (e.g., max L/D). The orchestrator is the "fitness function."

### 9.5 Web UI

A FastAPI layer wraps the CLI commands. The orchestrator runs in a background task. WebSocket streams the logger output to a React frontend in real time.

---

## 10. Security & Licensing

- FluentAgent is an **orchestrator only**. It does not distribute, bundle, or modify any ANSYS software.
- Users must have their own valid ANSYS Fluent license.
- API keys (Claude, ANSYS license server) are stored in `.env` (gitignored), never in code.
- The NLP interface sends only the user's simulation description to Claude — no proprietary data is included in prompts.

---

## 11. Technology Stack

| Component              | Technology                 | Purpose                               |
|------------------------|----------------------------|---------------------------------------|
| Language               | Python 3.10+               | Core implementation                   |
| CFD Backend            | ANSYS Fluent via PyFluent  | Meshing & solving                     |
| Config Validation      | Pydantic v2                | Schema enforcement & derived values   |
| Config Format          | YAML                       | Human-readable simulation configs     |
| NLP                    | Claude API (Anthropic)     | Natural language → config translation |
| CLI                    | Click                      | Command-line interface                |
| Logging                | Python logging + Rich      | Structured terminal & file logging    |
| Visualization          | Matplotlib                 | Convergence plots, Cp, y+            |
| Data Handling          | NumPy, Pandas              | Arrays, DataFrames                    |
| Build System           | Hatch (via pyproject.toml) | Packaging & dependency management     |
| Testing                | Pytest                     | Unit & integration tests              |

## Proposed Additions
