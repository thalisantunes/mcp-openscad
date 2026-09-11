# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] — 2026-09-10

### Added
- `mesh_section` — new tool (26 total): cross-section readback of an STL/SCAD part for
  fit checks between mating parts (press-fits, bores, pins). Reuses `_parse_stl` and
  the same `stl_path`/`scad_code` (+ `variables`, `timeout_s`) input contract as
  `analyze_mesh` (now factored into a shared `_resolve_stl_input()` helper). Cuts by
  one or more planes perpendicular to a configurable `axis` (`x`/`y`/`z`, default
  `z`) at `z` or `z_list` (max 50 heights), via standard triangle-edge/plane
  intersection (all degenerate cases — coplanar face, single-vertex touch, on-plane
  edge — handled explicitly and skipped/collapsed correctly, not just "skip
  degenerate").
  - Reports, per height: `n_points`, in-plane `bbox`/`extent`, `r_min`/`r_max` from a
    `center` (default: centroid of that height's points; can be pinned so multiple
    heights/parts are compared against the same axis), and `contours` — closed loops
    found by linking segments on shared endpoints rounded to 1e-6, sorted by `r_max`
    descending (so for a hollow tube `contours[0]` is the outer wall and
    `contours[1]` is the bore)
  - Automatically nudges the plane by `+1e-4` when it lands exactly on a vertex ring
    (the classic OpenSCAD `z=0` base-ring case) and reports that in the output
    instead of producing a degenerate/empty cut
  - Formatted output prints a `Ø externo | Ø interno | parede` line for hollow
    round sections (outer/inner diameter from each contour's `r_max`, wall thickness
    as the worst case `r_min(outer) - r_max(inner)`)
  - Same triangle cap (2,000,000) and STL parsing as `analyze_mesh`
  - Function signature: `mesh_section(path, zs, axis="z", center=None) -> dict`

### Added — Skill
- `skills/3d-print-gate/SKILL.md` — a pre-slicing quality gate procedure that drives
  `analyze_mesh` + `mesh_section`: export each part in print orientation, run
  `analyze_mesh` per part against pass criteria (watertight, 1 component, 0 floating,
  overhang ≤5%, bridge span ≤30mm), fit-check every mating pair with `mesh_section`
  against a ±0.05mm clearance tolerance, sanity-check orientation beyond the
  heuristic `suggest_orientation` score, and a blind read-only review of the `.scad`
  source — because a good-looking render doesn't prove a mesh is manifold or a wall
  has thickness. Installed for local use via a symlink at
  `~/.claude/skills/3d-print-gate`.

### Changed
- Extracted `_resolve_stl_input()`: the `stl_path`/`scad_code` input resolution shared
  by `analyze_mesh` and `mesh_section` (previously inlined only in `analyze_mesh`).

### Tests
- **288 tests** (up from 274), 94% coverage
- 14 new tests: cube cross-sections on all 3 axes, `z_list`, the vertex-ring nudge,
  an out-of-bbox empty section, the triangle cap, invalid `axis`, a real
  OpenSCAD-exported hollow cylinder ($fn-polygon, Ø40/Ø37.6 verified against the
  known `r_max=R` / `r_min=R·cos(π/$fn)` geometry), and the `mesh_section` MCP handler

## [0.7.0] — 2026-09-10

### Added
- `analyze_mesh` — new tool (25 total): pure-Python STL analysis for printability, no
  numpy/new dependencies. Accepts `stl_path` (existing file, validated the same way as
  other output paths) or `scad_code` (+ `variables`, `timeout_s`; exported to STL via
  `run_openscad` first). Parses both binary and ASCII STL (detected by file size:
  binary iff `size == 84 + 50*n`).
  - `non_manifold_edges` / `watertight` — via sorted vertex-index edge pairs (an edge
    is manifold iff exactly 2 faces reference it)
  - `components` (union-find over shared vertices, coordinates deduped at 1e-6) with
    per-component triangles/bbox/z_min, and `floating_components` — components whose
    `z_min` sits more than `bed_tol` above the mesh's global `z_min` (started in
    mid-air; need support or reorientation)
  - `volume_mm3` (signed tetrahedron sum, absolute value) and `surface_mm2`
  - Overhang analysis against a configurable `overhang_deg` (default 45°): faces with
    downward normal `nz < -sin(overhang_deg)` that aren't resting on the bed are
    flagged, reporting `overhang_area_mm2` / `overhang_pct` of the downward-facing
    area and the 5 lowest-z overhang face centroids with their angle. Convention used
    throughout: 0° = vertical wall, 90° = horizontal ceiling
    (`angle = degrees(asin(-nz))`)
  - Bridge detection: ceiling faces (angle > 85°) off the bed are clustered by shared
    edges; reports total bridge area and the largest cluster's bbox span, so a long
    unsupported span is visible before slicing
  - `printable` verdict (errors: not watertight, floating components; warnings:
    overhang > 5%, bridge span > 30mm, multiple components) with a `summary` string,
    matching the `validate_printability` convention
  - Hard cap of 2,000,000 triangles with a clear error; designed to analyze ~200k
    triangles in a few seconds using dict-keyed dedup and union-find instead of
    per-face object churn

### Changed
- `run_openscad()` timeout is now configurable via `timeout_s` (clamped to
  `[5, 900]` seconds, default 60 — was hard-coded at 60) and exposed as an optional
  `timeout_s` argument on `export_stl`, `export_3mf`, `export_dxf`, `export_svg`, and
  `render_to_png`. The timeout error message now includes the value actually used
  (e.g. `"timed out after 300 seconds"`).

### Tests
- **274 tests** (up from 254), **95% coverage** maintained
- 20 new tests: STL parsing (binary + ASCII), watertight/non-manifold detection,
  connected components + floating detection, overhang, bridge detection, the
  2,000,000-triangle cap, `timeout_s` clamping, and the `analyze_mesh` MCP handler

## [0.5.0] — 2026-07-16

### Security
- Converted `run_openscad` and `check_scad_syntax` to `async` using `asyncio.create_subprocess_exec` — eliminates event loop blocking
- Added safety check blocking OpenSCAD file-reading functions (`import()`, `surface()`) in custom SCAD code via regex
- Escaped double-quotes in `-D` variable string values to prevent argument injection
- Made allowed output path prefixes configurable via `MCP_OPENSCAD_ALLOWED_PATHS` environment variable
- Added `math.isfinite()` check to `assert_positive` and `assert_non_negative` — blocks `nan` and `inf` from config parameters

### Fixed
- Kerf clamped to `max(0.0, min(kerf, t - 0.1))` in `generate_laser_scad` and `generate_box_scad` — prevents negative kerf
- Output temp file path now uses `os.path.splitext()` instead of fragile `str.replace(".scad", …)`
- **Cylinder volume in BOM** corrected from `w×d×h` to `π×(d/2)²×h`
- 29 missing `await` calls added to `handle_call_tool` after async conversion

### Refactored (Sprint 3)
- Extracted `_generate_and_export()` async helper — eliminates 296 lines of duplicate export+preview code
- 11 handlers refactored to use the helper: `generate_laser_part`, `generate_box`, `generate_kerf_test`, `generate_finger_test`, `generate_3d_box`, `generate_bracket`, `generate_enclosure`, `generate_living_hinge`, `generate_dogbone`, `generate_tolerance_test`, `generate_bed_level_test`, `generate_retraction_test`, `generate_assembly`

### Tests (Sprint 4)
- **254 tests** (up from 197), **95% coverage** (up from 93%)
- Converted 21 sync integration tests to `@pytest.mark.asyncio`
- Updated timeout mocks from `subprocess.TimeoutExpired` → asyncio-based approach
- Strengthened 3 weak assertions (`test_validate_config_clean`, `test_validate_box_config_ok`, `test_check_syntax_invalid`)
- Added 52 new tests covering: `import()/surface()` blocking, env var path config, kerf guard, CNC division-by-zero, assembly edge cases, nan/inf validation, BOM cylinder volume, `_generate_and_export` helper

### Infrastructure
- CI matrix extended to Python 3.10, 3.11, 3.12 with `fail-fast: false`
- Added lint step with `ruff` to CI (`continue-on-error: true`)
- Added `xvfb-run` wrapper for OpenSCAD rendering in CI headless environments
- Comprehensive `.gitignore` for Python projects
- Updated `GEMINI.md` to reflect v0.5.0 (24 tools, 254 tests, 95% coverage)
- `README.md`: badges CI, Coverage 95%, Python 3.10+, MIT, Version 0.5.0
- `CHANGELOG.md` created (this file)

## [0.4.0] — 2026-07-15

### Added
- `generate_tolerance_test` — calibration plate with pin/hole pairs at varying tolerances
- `generate_bed_level_test` — disc grid for bed leveling verification
- `generate_retraction_test` — tower array for retraction tuning
- `generate_living_hinge` — flexible hinge patterns (straight/serpentine/cross-hatch)
- `generate_dogbone` — CNC pocket with dogbone/T-bone corner compensation
- `suggest_orientation` — 3-axis orientation advisor with scoring
- `generate_assembly` — multi-piece project with exploded view and auto BOM
- `generate_cnc_toolpath_hints` — CNC parameters for 8 materials

### Security
- Three-layer input validation: keyword safety, path traversal prevention, config parameter validation
- `validate_config_parameters` — comprehensive per-tool geometry validation

## [0.3.0] — 2026-07-10

### Added
- `generate_box` — laser box with snap/slide/none lid and X/Y dividers
- `generate_kerf_test` — kerf calibration plate
- `generate_finger_test` — finger joint fit test comb
- `estimate_material_use` — sheet material area calculator
- `check_syntax` — fast OpenSCAD syntax validation without rendering
- `validate_printability` — FDM/resin printability analysis
- `generate_3d_box` — 3D-printable box with snap-fit or threaded lid
- `generate_bracket` — parametric bracket (L, U, flat)
- `generate_enclosure` — electronics enclosure with connector catalog and PCB standoffs

## [0.2.0] — 2026-07-05

### Added
- `generate_laser_part` — smart laser box generator with finger joints and openings
- `validate_laser_config` — geometric validation for laser configs

## [0.1.0] — 2026-07-01

### Added
- `render_to_png` — OpenSCAD code to PNG preview
- `export_stl` — STL export for 3D printing
- `export_3mf` — 3MF export
- `export_dxf` — DXF export for laser/CNC
- `export_svg` — SVG export for laser/engraving
