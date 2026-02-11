# FluentAgent — Autonomous CFD Simulation Orchestrator

## Project Specification & Implementation Instructions for Claude Code / Codex

---

## 1. PROJECT OVERVIEW

**FluentAgent** is a Python-based autonomous orchestrator that drives ANSYS Fluent CFD simulations end-to-end — from geometry intake through meshing, solver execution, adaptive error recovery, and post-processing — with an optional natural language interface powered by Claude's API.

### Core Value Proposition

Engineers spend days to weeks manually iterating on mesh quality, solver settings, and convergence issues. FluentAgent encodes expert CFD engineering logic into an autonomous retry loop, reducing a multi-day manual workflow to a single command.

### Two Operational Modes

1. **Config Mode (Pipeline 2 — build this first):** User provides geometry file + structured YAML config specifying flow conditions, mesh parameters, and solver settings. The agent executes autonomously with intelligent retry logic.

2. **Natural Language Mode (Pipeline 1 — build this second):** User provides a plain-English prompt like *"Simulate flow over a NACA 0012 at Re=3M, Mach 0.3"*. An LLM (Claude API) translates the prompt into a structured YAML config, making physics-informed decisions (turbulence model selection, domain sizing, boundary conditions). That config is then passed to the same engine as Mode 1.

NOTE: First iterations will not call the natural language model. For preliminary testing we will use config mode.

### Key Dependencies

- **Python 3.10+**
- **ansys-fluent-core (PyFluent)** — Python API for ANSYS Fluent
- **ansys-fluent-meshing** — Meshing automation (if using Fluent Meshing; alternatively Ansys Meshing)
- **anthropic** — Claude API SDK (for Pipeline 1 / natural language mode)
- **pyyaml** — Config parsing
- **numpy, pandas** — Data handling
- **matplotlib** — Convergence plotting and contour visualization
- **pydantic** — Config schema validation
- **rich** — Terminal logging and progress display
- **click** — CLI framework

### License Note

FluentAgent is an *orchestrator*. It requires the user to have their own valid ANSYS Fluent license. FluentAgent does not distribute, bundle, or modify any ANSYS software. This must be stated clearly in the README and LICENSE.

---

## 2. DIRECTORY STRUCTURE

Create this exact structure. Every file listed below must be created.

```
fluent-agent/
├── README.md
├── LICENSE                          # MIT License
├── pyproject.toml                   # Project metadata, dependencies, entry points
├── .env.example                     # Template for API keys and Fluent path
├── .gitignore
│
├── configs/
│   ├── example_naca2412.yaml        # Example config: NACA 2412 validation case
│   ├── example_naca0012.yaml        # Example config: NACA 0012 standard case
│   └── schema_reference.yaml        # Annotated reference of all config fields
│
├── geometries/
│   ├── naca2412.csv                 # Sample geometry: NACA 2412 coordinates (x, y)
│   └── naca0012.csv                 # Sample geometry: NACA 0012 coordinates (x, y)
│
├── src/
│   └── fluent_agent/
│       ├── __init__.py
│       ├── cli.py                   # CLI entry point (click-based)
│       ├── config.py                # Pydantic models for config schema + YAML loader
│       ├── geometry.py              # Geometry intake, CSV parsing, format conversion
│       ├── meshing.py               # Mesh generation, quality assessment, adaptive retry
│       ├── solver.py                # Solver setup, execution, monitoring, adaptive retry
│       ├── postprocessor.py         # Result extraction, report generation, plotting
│       ├── orchestrator.py          # Master loop: ties all stages together
│       ├── nlp_interface.py         # Claude API integration for natural language mode
│       ├── physics_rules.py         # Engineering heuristics and decision tables
│       ├── logger.py                # Structured logging with rich
│       └── constants.py             # Physical constants, default thresholds, enums
│
├── prompts/
│   └── config_generation.md         # System prompt for Claude API config generation
│
├── tests/
│   ├── test_config.py               # Config parsing and validation tests
│   ├── test_geometry.py             # Geometry loading and conversion tests
│   ├── test_physics_rules.py        # Heuristic / decision table unit tests
│   ├── test_nlp_interface.py        # Prompt-to-config translation tests (mocked API)
│   └── conftest.py                  # Shared fixtures
│
├── outputs/                         # Default output directory (gitignored except .gitkeep)
│   └── .gitkeep
│
└── docs/
    ├── ARCHITECTURE.md              # High-level architecture documentation
    └── CONTRIBUTING.md              # Contribution guidelines
```

---

## 3. CONFIG SCHEMA — THE CONTRACT

This is the single most important design decision. The YAML config is the contract between the NLP layer and the engine. Every field must be precisely defined.

### File: `src/fluent_agent/config.py`

Use Pydantic v2 `BaseModel` classes. The config has four top-level sections:

```yaml
# Full annotated config schema

geometry:
  source_type: "csv"               # One of: csv, stp, stl, igs
  file_path: "geometries/naca2412.csv"
  # For CSV: assumes two columns (x, y) representing airfoil surface coordinates
  # The agent will handle closing the trailing edge if needed
  chord_length: 1.0                # meters — used for non-dimensionalization
  reference_area: 1.0              # m² — for force coefficient computation

domain:
  type: "c-type"                   # One of: c-type, h-type, rectangular
  # Domain sizing relative to chord length:
  upstream_distance: 15            # chord lengths upstream of leading edge
  downstream_distance: 25          # chord lengths downstream of trailing edge
  lateral_distance: 15             # chord lengths above/below
  # These defaults follow best practices for external aero

mesh:
  strategy: "auto"                 # One of: auto, manual
  # If auto, agent selects parameters based on Re and turbulence model
  # If manual, user specifies below:
  fineness: "medium"               # One of: coarse, medium, fine, ultra-fine
  inflation_layers:
    first_layer_height: null       # meters — if null, computed from target y+
    growth_rate: 1.2
    num_layers: 20
    target_y_plus: 1.0             # Drives first layer height calculation
  surface_sizing:
    min_size: 0.001                # meters
    max_size: 0.05                 # meters
    curvature_normal_angle: 12     # degrees — controls curvature refinement
  quality_gates:
    min_orthogonal_quality: 0.15   # Fluent recommendation: > 0.1
    max_skewness: 0.90             # Fluent recommendation: < 0.95
    max_aspect_ratio: 100          # For boundary layer cells, can be higher
  max_retry_attempts: 3            # How many times to remesh on quality failure

flow:
  reynolds_number: 3.0e6
  freestream_velocity: 43.822      # m/s
  angle_of_attack: 0.0             # degrees
  mach_number: 0.13                # Used to determine compressibility treatment
  fluid:
    density: 1.225                 # kg/m³
    viscosity: 1.7894e-5           # Pa·s
    # Defaults to sea-level air

solver:
  turbulence_model: "k-omega-sst"  # One of: spalart-allmaras, k-epsilon-realizable,
                                    #         k-omega-sst, transition-sst
  pressure_velocity_coupling: "coupled"  # One of: coupled, simple, simplec
  discretization:
    pressure: "second-order"
    momentum: "second-order-upwind"
    turbulent_kinetic_energy: "second-order-upwind"
    specific_dissipation_rate: "second-order-upwind"
  initialization: "hybrid"          # One of: hybrid, standard, fmg
  convergence:
    residual_targets:
      continuity: 1.0e-6
      x_velocity: 1.0e-6
      y_velocity: 1.0e-6
      k: 1.0e-6
      omega: 1.0e-6
    max_iterations: 5000
    monitor_cl: true                # Monitor lift coefficient for convergence
    monitor_cd: true                # Monitor drag coefficient for convergence
    cl_convergence_window: 100      # Iterations over which Cl must be stable
    cl_convergence_tolerance: 0.001 # Cl change threshold for "converged"
  adaptive_retry:
    enabled: true
    max_retries: 3
    # Retry strategies (applied in order):
    # 1. Drop to first-order discretization for 500 iterations, then ramp to second-order
    # 2. Reduce under-relaxation factors (pressure: 0.2, momentum: 0.5)
    # 3. Switch initialization method and restart
    # 4. Flag for mesh refinement and loop back to meshing stage

output:
  directory: "outputs/run_001"      # Auto-incremented if exists
  save_case_file: true
  save_data_file: true
  export_residuals_csv: true
  export_force_coefficients_csv: true
  generate_plots:
    residuals: true
    cl_cd_history: true
    pressure_coefficient: true      # Cp vs x/c distribution
    wall_y_plus: true               # y+ distribution along surface
  generate_report: true             # Markdown summary report
```

### Pydantic Implementation Notes

- Every field must have a sensible default or be explicitly `Optional` with `None`.
- Add validators: `reynolds_number` must be positive, `angle_of_attack` must be in [-90, 90], `fineness` must be one of the allowed enum values, etc.
- Add a `@model_validator` that computes derived quantities: if `first_layer_height` is null, compute it from `target_y_plus`, `reynolds_number`, `chord_length`, and `freestream_velocity` using the flat-plate boundary layer estimation formula.
- Add a class method `from_yaml(path: str) -> SimulationConfig` that loads and validates.
- Add a method `to_yaml(path: str)` that serializes (used by the NLP layer to save generated configs).

---

## 4. MODULE SPECIFICATIONS

### 4.1 `constants.py`

Define:
- Physical constants: `RHO_AIR_SL`, `MU_AIR_SL`, `GAMMA_AIR`, `R_AIR`, `T_SL`, `P_SL`
- Turbulence model enum: `TurbulenceModel(str, Enum)`
- Domain type enum: `DomainType(str, Enum)`
- Mesh fineness presets: a dictionary mapping `fineness` levels to sizing parameters
- Quality gate defaults
- Solver scheme defaults per turbulence model (e.g., k-omega-sst uses specific discretization)

### 4.2 `geometry.py`

**Class: `GeometryHandler`**

Responsibilities:
- Load CSV coordinates (x, y columns), validate ordering (should go around the airfoil)
- If trailing edge is open, close it by averaging the first and last points
- Compute chord length from the loaded coordinates and validate against config
- For future: load STEP/STL/IGES files directly
- Provide a method that returns the geometry in whatever format PyFluent meshing expects
- For MVP: export the CSV as a Fluent-compatible point file or use PyFluent's geometry import

**Key method signatures:**
```python
class GeometryHandler:
    def __init__(self, config: GeometryConfig):
        ...

    def load(self) -> np.ndarray:
        """Load and validate geometry coordinates. Returns Nx2 array."""
        ...

    def compute_chord(self) -> float:
        """Compute chord length from loaded coordinates."""
        ...

    def close_trailing_edge(self, coords: np.ndarray) -> np.ndarray:
        """Close open trailing edge if gap detected."""
        ...

    def export_for_meshing(self, output_path: str) -> str:
        """Export geometry in format suitable for PyFluent meshing intake."""
        ...
```

### 4.3 `meshing.py`

**Class: `MeshGenerator`**

This is the first major intelligence module. It generates a mesh and evaluates it against quality gates, retrying with adjusted parameters if quality is insufficient.

**Core logic flow:**

```
1. Receive config (domain type, sizing, inflation, quality gates)
2. Compute first-layer height from y+ target if not provided
3. Launch PyFluent Meshing session
4. Import geometry
5. Create domain boundaries (far-field, inlet, outlet, airfoil wall)
6. Apply sizing functions (surface sizing, curvature refinement, BOI if needed)
7. Apply inflation layers on the airfoil wall
8. Generate mesh
9. QUALITY CHECK:
   a. Query mesh statistics from PyFluent (orthogonal quality, skewness, aspect ratio)
   b. Compare against quality gates
   c. If PASS → export mesh, close meshing session, return mesh path
   d. If FAIL → log which metrics failed, adjust parameters:
      - If skewness too high: reduce max element size by 20%, increase smoothing
      - If orthogonal quality too low: adjust growth rate (reduce by 0.05), add smoothing passes
      - If aspect ratio too high near wall: adjust first layer height or growth rate
      - Increment retry counter
      - If retries < max_retry_attempts: go to step 6
      - If retries exhausted: raise MeshQualityError with diagnostics
```

**Key method signatures:**
```python
class MeshGenerator:
    def __init__(self, config: SimulationConfig, logger: AgentLogger):
        ...

    def compute_first_layer_height(self) -> float:
        """
        Estimate first cell height from target y+ using flat-plate BL correlation:
        y = (y+ * mu) / (u_tau * rho)
        where u_tau = sqrt(tau_w / rho)
        and tau_w = 0.5 * Cf * rho * U^2
        and Cf = 0.058 * Re_L^(-0.2) (turbulent flat plate)
        """
        ...

    def generate(self) -> MeshResult:
        """
        Full mesh generation loop with quality-based retry.
        Returns MeshResult containing mesh path, final quality metrics, and iteration log.
        """
        ...

    def _check_quality(self, session) -> QualityReport:
        """Query mesh quality metrics from active PyFluent meshing session."""
        ...

    def _adjust_parameters(self, quality_report: QualityReport, attempt: int) -> MeshConfig:
        """Determine parameter adjustments based on which quality gates failed."""
        ...
```

**Data classes to define:**
```python
@dataclass
class QualityReport:
    min_orthogonal_quality: float
    max_skewness: float
    max_aspect_ratio: float
    total_cells: int
    passed: bool
    failures: list[str]  # Human-readable failure descriptions

@dataclass
class MeshResult:
    mesh_path: str
    final_quality: QualityReport
    attempts: int
    iteration_log: list[dict]  # Log of each attempt's parameters and results
```

### 4.4 `solver.py`

**Class: `SolverManager`**

The second major intelligence module. Configures and runs the Fluent solver, monitors convergence in real-time, and implements adaptive retry strategies for divergence or stagnation.

**Core logic flow:**

```
1. Launch PyFluent solver session (or transition from meshing session)
2. Read the mesh
3. Configure physics:
   a. Set turbulence model
   b. Set fluid properties
   c. Set boundary conditions (velocity inlet, pressure outlet, wall, symmetry/far-field)
   d. Set reference values for coefficient computation
4. Configure solver:
   a. Pressure-velocity coupling scheme
   b. Spatial discretization schemes
   c. Under-relaxation factors (start with defaults)
   d. Convergence monitors (residuals + Cl/Cd if enabled)
5. Initialize (hybrid/standard/FMG per config)
6. Run iterations in BATCHES (e.g., 500 at a time) — not all at once
   After each batch:
   a. Read residual history
   b. Read force coefficient history
   c. DIVERGENCE CHECK: if any residual > 1e6 or NaN detected → DIVERGED
   d. CONVERGENCE CHECK: if all residuals < targets AND Cl/Cd stable → CONVERGED
   e. STAGNATION CHECK: if residuals plateaued above targets for 2+ batches → STAGNATED
7. Handle outcomes:
   - CONVERGED → proceed to post-processing
   - DIVERGED → apply retry strategy:
     * Retry 1: Drop all discretization to first-order, run 500 iterations,
                then ramp back to second-order (pseudo-transient if available)
     * Retry 2: Reduce URFs (pressure → 0.2, momentum → 0.5, turbulence → 0.6)
     * Retry 3: Switch to FMG initialization and restart
     * Retry 4: Return control to orchestrator with flag "needs_mesh_refinement"
   - STAGNATED → similar retry logic but less aggressive
   - MAX ITERATIONS REACHED → report partial convergence with current state
```

**Key method signatures:**
```python
class SolverManager:
    def __init__(self, config: SimulationConfig, logger: AgentLogger):
        ...

    def setup(self, session) -> None:
        """Configure all physics, solver settings, and monitors on a PyFluent session."""
        ...

    def run(self, session) -> SolverResult:
        """
        Execute solver with batch monitoring and adaptive retry.
        Returns SolverResult with convergence status, history, and diagnostics.
        """
        ...

    def _run_batch(self, session, n_iterations: int) -> BatchResult:
        """Run a batch of iterations and return residual/monitor snapshots."""
        ...

    def _check_convergence(self, history: ConvergenceHistory) -> ConvergenceStatus:
        """Evaluate residual + monitor history against convergence criteria."""
        ...

    def _apply_retry_strategy(self, session, strategy_index: int) -> None:
        """Apply the nth retry strategy to the active session."""
        ...

    def _setup_boundary_conditions(self, session) -> None:
        """
        Configure BCs based on domain type and flow config.
        For C-type domain: velocity inlet on the C-shaped boundary,
        pressure outlet downstream, wall on airfoil surface.
        Must correctly decompose velocity into components based on AoA.
        """
        ...
```

**Data classes:**
```python
class ConvergenceStatus(str, Enum):
    CONVERGED = "converged"
    DIVERGED = "diverged"
    STAGNATED = "stagnated"
    MAX_ITERATIONS = "max_iterations_reached"
    NEEDS_REMESH = "needs_mesh_refinement"

@dataclass
class SolverResult:
    status: ConvergenceStatus
    iterations_run: int
    final_residuals: dict[str, float]
    cl: float | None
    cd: float | None
    residual_history: pd.DataFrame
    coefficient_history: pd.DataFrame
    retry_log: list[dict]
```

### 4.5 `postprocessor.py`

**Class: `PostProcessor`**

Extracts results and generates a comprehensive output package.

**Responsibilities:**
- Extract final Cl, Cd, Cm from Fluent
- Extract Cp distribution along the airfoil surface (pressure coefficient vs x/c)
- Extract wall y+ distribution (critical for validating mesh adequacy)
- Generate matplotlib plots: residual history, Cl/Cd convergence, Cp distribution, y+ distribution
- Export raw data as CSV files
- Generate a Markdown summary report containing:
  - Run metadata (date, config hash, geometry)
  - Mesh statistics (cells, quality metrics, attempts)
  - Solver performance (iterations, convergence status, retries)
  - Final results (Cl, Cd, Cm)
  - Embedded plot references
  - Any warnings or flags (e.g., y+ > 5 for SST model, partial convergence)
- Save Fluent case and data files if configured

**Key method signatures:**
```python
class PostProcessor:
    def __init__(self, config: SimulationConfig, solver_result: SolverResult,
                 mesh_result: MeshResult, logger: AgentLogger):
        ...

    def extract_results(self, session) -> SimulationResults:
        """Extract all results from the active Fluent session."""
        ...

    def generate_plots(self, results: SimulationResults) -> list[str]:
        """Generate all configured plots. Returns list of file paths."""
        ...

    def generate_report(self, results: SimulationResults) -> str:
        """Generate Markdown summary report. Returns path to report file."""
        ...

    def export_data(self, results: SimulationResults) -> list[str]:
        """Export raw data as CSV files. Returns list of file paths."""
        ...

    def save_case_data(self, session) -> tuple[str, str]:
        """Save Fluent .cas and .dat files."""
        ...
```

### 4.6 `orchestrator.py`

**Class: `SimulationOrchestrator`**

The master controller. Ties all stages together and handles the outer retry loop (mesh→solve→remesh if needed).

**Core flow:**
```
1. Load and validate config
2. Set up output directory (auto-increment run number)
3. Initialize logger
4. OUTER LOOP (max 2 mesh-solver cycles):
   a. Run MeshGenerator → MeshResult
   b. If mesh failed after all retries → abort with diagnostics
   c. Run SolverManager → SolverResult
   d. If solver says NEEDS_REMESH:
      - Refine mesh parameters (reduce sizing by 30%, add inflation layers)
      - Loop back to (a)
   e. If solver CONVERGED or MAX_ITERATIONS:
      - Run PostProcessor
      - Break
   f. If solver DIVERGED after all retries → abort with diagnostics
5. Output final report and paths to all generated files
6. Return overall RunResult
```

**Key method signatures:**
```python
class SimulationOrchestrator:
    def __init__(self, config_path: str):
        ...

    def run(self) -> RunResult:
        """Execute the full simulation pipeline. Returns RunResult."""
        ...

@dataclass
class RunResult:
    success: bool
    status: str
    output_directory: str
    report_path: str | None
    cl: float | None
    cd: float | None
    total_mesh_attempts: int
    total_solver_attempts: int
    total_wall_time: float  # seconds
    error_message: str | None
```

### 4.7 `physics_rules.py`

**Class: `PhysicsAdvisor`**

Encodes expert CFD engineering heuristics. Used by both the NLP layer (to make decisions from prompts) and the engine (to make adaptive decisions during retry).

**Decision tables to implement:**

```python
def recommend_turbulence_model(re: float, mach: float, application: str) -> str:
    """
    Rules:
    - Re < 5e5 and transition expected → transition-sst
    - Re 5e5 to 1e7, external aero → k-omega-sst
    - Re > 1e7, attached flow → spalart-allmaras
    - Internal flow / separated → k-epsilon-realizable
    - Default: k-omega-sst
    """

def recommend_domain_sizing(geometry_type: str) -> dict:
    """
    Rules:
    - Airfoil, C-type: upstream 15c, downstream 25c, lateral 15c
    - Bluff body: upstream 10D, downstream 30D, lateral 10D
    - Internal: based on geometry bounds
    """

def recommend_y_plus_target(turbulence_model: str) -> float:
    """
    - k-omega-sst: y+ ≈ 1
    - spalart-allmaras: y+ ≈ 1
    - k-epsilon-realizable: y+ ≈ 30-50 (wall functions)
    - transition-sst: y+ ≈ 1
    """

def validate_y_plus_results(measured_y_plus: np.ndarray, model: str) -> dict:
    """Check if actual y+ distribution is appropriate for the turbulence model."""

def recommend_discretization_strategy(is_first_run: bool) -> dict:
    """
    First run or retry: start first-order for stability, ramp to second-order.
    Normal run: second-order upwind for all transport equations.
    """

def recommend_urf(turbulence_model: str, is_retry: bool) -> dict:
    """Return under-relaxation factors. More conservative for retries."""
```

### 4.8 `nlp_interface.py`

**Class: `NLPConfigGenerator`**

Takes a natural language prompt and produces a valid SimulationConfig.

**Implementation approach:**

1. Load the system prompt from `prompts/config_generation.md`
2. The system prompt must contain:
   - The full config schema with descriptions of every field
   - The physics rules from `physics_rules.py` expressed as natural language
   - Explicit instruction to output ONLY valid YAML matching the schema
   - Examples of prompt → config translations
3. Send user prompt + system prompt to Claude API (claude-sonnet-4-20250514 for speed/cost)
4. Parse the returned YAML
5. Validate with Pydantic (SimulationConfig)
6. If validation fails, send the error back to Claude with the failed YAML for correction (one retry)
7. Return the validated config

**Key method signatures:**
```python
class NLPConfigGenerator:
    def __init__(self, api_key: str | None = None):
        ...

    def generate_config(self, user_prompt: str) -> SimulationConfig:
        """
        Translate natural language to validated SimulationConfig.
        Raises NLPConfigError if generation fails after retry.
        """
        ...

    def _build_messages(self, user_prompt: str) -> list[dict]:
        """Construct the message array for the Claude API call."""
        ...

    def _parse_and_validate(self, response_text: str) -> SimulationConfig:
        """Extract YAML from response, parse, and validate."""
        ...

    def _retry_with_error(self, original_yaml: str, error: str) -> SimulationConfig:
        """Send validation error back to Claude for correction."""
        ...
```

### 4.9 `cli.py`

**Click-based CLI with two commands:**

```bash
# Config mode
fluent-agent run --config configs/example_naca2412.yaml

# NLP mode
fluent-agent prompt "Simulate flow over a NACA 0012 at Re 3 million, Mach 0.3, find Cl and Cd"

# Dry run — generates config from prompt but doesn't execute
fluent-agent prompt "..." --dry-run --output generated_config.yaml

# Validate a config without running
fluent-agent validate --config configs/example_naca2412.yaml
```

### 4.10 `logger.py`

**Class: `AgentLogger`**

Wraps Python's `logging` module with `rich` for beautiful terminal output and simultaneous file logging.

- Every stage transition logged with a header: `[GEOMETRY] → [MESHING] → [SOLVER] → [POST]`
- Quality gate checks logged with pass/fail and specific metrics
- Retry attempts logged with the strategy being applied
- Convergence monitor values logged at each batch
- Final summary logged with wall time, status, and result paths
- All logs also written to `{output_dir}/run.log` as plain text

---

## 5. SYSTEM PROMPT FOR NLP CONFIG GENERATION

### File: `prompts/config_generation.md`

This file is loaded by `nlp_interface.py` and sent as the system prompt to Claude.

**Contents should include:**

```markdown
You are a CFD simulation configuration assistant. Your job is to translate natural language descriptions of CFD simulations into precise YAML configuration files.

You have deep knowledge of:
- Turbulence modeling (RANS models, their applicability regimes, y+ requirements)
- Mesh design for external and internal aerodynamics
- Boundary condition specification
- Solver numerics and convergence strategies
- Fluid properties at standard conditions

## Your Task

Given a user's description of a simulation they want to run, generate a complete YAML configuration file that matches the schema below. Make intelligent engineering decisions for any parameters the user does not specify.

## Decision-Making Rules

### Turbulence Model Selection
- External aerodynamics at Re > 5e5: default to k-omega-sst
- Low Reynolds number with transition: use transition-sst
- Very high Re attached flow: spalart-allmaras is acceptable
- Internal flow or expected separation: k-epsilon-realizable

### Domain Sizing (relative to characteristic length)
- C-type for airfoils: 15c upstream, 25c downstream, 15c lateral
- Rectangular for bluff bodies: 10D upstream, 30D downstream, 10D lateral

### Mesh Strategy
- Always compute first-layer height from y+ target for the chosen turbulence model
- k-omega-sst, SA, transition-sst require y+ ≈ 1
- k-epsilon with wall functions requires y+ ≈ 30-50

### Flow Conditions
- If user specifies Re but not velocity: compute velocity from Re = ρUL/μ at sea level
- If user specifies Mach but not velocity: compute from Mach = U / sqrt(γRT) at sea level
- If Mach < 0.3: incompressible treatment is fine
- If Mach > 0.3: enable energy equation, use ideal gas

## Config Schema
[INSERT FULL ANNOTATED YAML SCHEMA HERE]

## Output Rules
- Output ONLY the YAML configuration. No explanation, no markdown fences, no preamble.
- Every field in the schema must be present.
- All values must be physically reasonable.
- If the user's description is ambiguous, make the most common/safe engineering choice.
```

---

## 6. SAMPLE GEOMETRY FILES

### `geometries/naca2412.csv`

Generate NACA 2412 airfoil coordinates using the standard NACA 4-digit formula:
- 200 points around the airfoil (100 upper, 100 lower)
- Cosine spacing for clustering at leading and trailing edges
- Format: `x,y` with header row
- Normalized to chord = 1.0

### `geometries/naca0012.csv`

Same approach for NACA 0012 (symmetric airfoil). This is the standard validation case.

---

## 7. EXAMPLE CONFIG FILES

### `configs/example_naca2412.yaml`

A complete, ready-to-run config for the NACA 2412 at:
- Re = 3.0e6
- AoA = 0°
- k-omega-SST
- C-type domain
- Medium mesh fineness
- Target y+ = 1.0
- Full output suite enabled

This should reproduce the validation case from the developer's published research.

### `configs/example_naca0012.yaml`

Standard NACA 0012 at Re = 6.0e6, AoA = 0°. Classic validation case with abundant reference data available (Abbott & Von Doenhoff, NASA experimental data).

### `configs/schema_reference.yaml`

The full schema with extensive comments on every field. Serves as documentation.

---

## 8. TESTS

### Testing Strategy

- **Unit tests** for config parsing, geometry loading, physics rules — these require no ANSYS license
- **Integration tests** (marked with `@pytest.mark.integration`) for PyFluent interactions — only run when Fluent is available
- **Mock tests** for NLP interface — mock the Claude API to test prompt construction and response parsing

### `tests/test_config.py`
- Test loading a valid YAML config
- Test validation catches invalid values (negative Re, AoA out of range, etc.)
- Test first-layer height auto-computation
- Test default value population
- Test serialization round-trip (load → save → load produces identical config)

### `tests/test_geometry.py`
- Test CSV loading with valid data
- Test trailing edge closure
- Test chord length computation
- Test rejection of malformed CSV (missing columns, NaN values)

### `tests/test_physics_rules.py`
- Test turbulence model recommendation for various Re/Mach combinations
- Test domain sizing recommendations
- Test y+ target recommendations per model
- Test URF recommendations for normal vs retry modes

### `tests/test_nlp_interface.py`
- Mock Claude API responses
- Test that a well-formed prompt produces a valid config
- Test the retry logic when initial generation has validation errors
- Test edge cases: ambiguous prompts, missing information

---

## 9. README.md STRUCTURE

The README must include:

1. **Header** — Project name, one-line description, badges (Python version, license)
2. **Demo GIF/screenshot** — placeholder for now, add after first working run
3. **What it does** — 3-4 sentences explaining the value proposition
4. **Quickstart** — minimal steps to run the example config
5. **Installation** — pip install, ANSYS license requirements, .env setup
6. **Usage** — config mode, NLP mode, dry run, validate
7. **Config reference** — link to schema_reference.yaml
8. **Architecture** — link to docs/ARCHITECTURE.md
9. **Validation** — description of NACA 2412 validation case and results (to be filled after first run)
10. **Limitations** — requires ANSYS license, currently 2D only, RANS only
11. **Roadmap** — OpenFOAM backend, 3D support, multi-objective optimization
12. **License** — MIT

---

## 10. pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "fluent-agent"
version = "0.1.0"
description = "Autonomous CFD simulation orchestrator with adaptive retry logic and natural language interface"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
dependencies = [
    "ansys-fluent-core>=0.20",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "numpy>=1.24",
    "pandas>=2.0",
    "matplotlib>=3.7",
    "click>=8.0",
    "rich>=13.0",
    "anthropic>=0.40",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "ruff>=0.1",
]

[project.scripts]
fluent-agent = "fluent_agent.cli:main"

[tool.ruff]
line-length = 100
```

---

## 11. IMPLEMENTATION ORDER — INSTRUCTIONS FOR CODEX / CLAUDE CODE

**Follow this order precisely. Do not skip ahead. Each phase must be complete and testable before the next begins.**

### Phase 1: Foundation (Do this first)

1. Create the entire directory structure as specified in Section 2
2. Implement `constants.py` with all physical constants, enums, and default dictionaries
3. Implement `config.py` with full Pydantic models and YAML loading/saving
4. Implement `physics_rules.py` with all decision functions
5. Write `tests/test_config.py` and `tests/test_physics_rules.py`
6. Run tests — everything must pass before proceeding
7. Generate NACA geometry CSV files using the standard 4-digit formulas
8. Write `tests/test_geometry.py` and implement `geometry.py`
9. Create all three config YAML files
10. Create `pyproject.toml` and `.gitignore`

### Phase 2: Engine Core

11. Implement `logger.py` with rich terminal output + file logging
12. Implement `meshing.py` — start with the quality checking logic (testable without Fluent) then add PyFluent calls
13. Implement `solver.py` — start with convergence checking logic (testable with mock data) then add PyFluent calls
14. Implement `postprocessor.py` — plotting and report generation (testable with mock data)
15. Implement `orchestrator.py` — wire everything together

### Phase 3: Intelligence Layer

16. Write the system prompt in `prompts/config_generation.md`
17. Implement `nlp_interface.py`
18. Write `tests/test_nlp_interface.py` with mocked API calls
19. Implement `cli.py` with all four commands (run, prompt, dry-run, validate)

### Phase 4: Polish

20. Write `README.md`
21. Write `docs/ARCHITECTURE.md`
22. Write `docs/CONTRIBUTING.md`
23. Create `.env.example`
24. Write `LICENSE` (MIT)
25. Final pass: ensure all imports resolve, all tests pass, CLI works end-to-end

---

## 12. CRITICAL IMPLEMENTATION NOTES

### PyFluent API Patterns

PyFluent uses a TUI-like command structure. Example patterns the implementer must know:

```python
import ansys.fluent.core as pyfluent

# Launch Fluent in meshing mode
meshing_session = pyfluent.launch_fluent(mode="meshing")

# Launch Fluent in solver mode
solver_session = pyfluent.launch_fluent(mode="solver")

# Or transition from meshing to solver:
solver_session = meshing_session.switch_to_solver()

# Reading mesh in solver mode:
solver_session.file.read_mesh(file_name="mesh.msh")

# Setting up turbulence model (example for k-omega SST):
solver_session.setup.models.viscous.model = "k-omega"
solver_session.setup.models.viscous.k_omega_model = "sst"

# Boundary conditions:
solver_session.setup.boundary_conditions.velocity_inlet["inlet"].velocity_magnitude = 43.8

# Running iterations:
solver_session.solution.run_calculation.iterate(iter_count=500)

# Reading residuals:
# (Implementation varies by PyFluent version — check docs)
```

**IMPORTANT:** PyFluent's API surface changes between versions. The implementer MUST consult the PyFluent documentation at https://fluent.docs.pyansys.com/ for the exact syntax of the installed version. The patterns above are illustrative, not guaranteed exact. Wrap all PyFluent interactions in try/except blocks with meaningful error messages.

### Error Handling Philosophy

- Every PyFluent call should be wrapped in try/except
- Errors should be classified: recoverable (retry) vs fatal (abort with diagnostics)
- The agent should NEVER silently fail. Every error gets logged with context.
- If the ANSYS license server is unreachable, detect this early and provide a clear message

### Concurrency Note

- PyFluent sessions are NOT thread-safe
- The orchestrator should be single-threaded
- If future parallelism is desired (multiple AoA sweeps), use separate processes

---

## 13. FUTURE EXTENSIONS (Do NOT implement now, but design for)

The architecture should make these additions straightforward:

- **OpenFOAM backend**: A second meshing/solver module pair that implements the same interfaces but targets OpenFOAM instead of Fluent
- **3D support**: Geometry handler accepts 3D files, meshing module generates volume meshes
- **Parameter sweeps**: Orchestrator runs multiple configs (e.g., AoA sweep from -5° to 15°)
- **Optimization loop**: Genetic algorithm that modifies geometry and calls the orchestrator (essentially recreating the developer's research workflow as a general tool)
- **Web UI**: FastAPI + React frontend for non-CLI users

Design for these by using clean interfaces between modules. The `MeshGenerator` and `SolverManager` should be abstract base classes with `FluentMeshGenerator` and `FluentSolverManager` as concrete implementations.

---

*End of specification. Begin implementation at Phase 1.*