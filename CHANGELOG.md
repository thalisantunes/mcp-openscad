# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
