# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] — 2026-10-16

macOS portability, laser finger joints, and input validation. No tool was removed or
renamed; one tool was added (27 total).

### Added
- `export_obj` — new tool: exports a Wavefront OBJ (Blender, Godot). Requires OpenSCAD
  2022+ (nightly). On 2021.01, which has no OBJ exporter, it answers "OBJ requer OpenSCAD
  2022+ (nightly)" instead of the raw CLI message.
- `find_openscad()` — the OpenSCAD binary is now looked up (and cached) in this order:
  `OPENSCAD_PATH` (if it exists and is executable), `openscad` on `PATH`, then the usual
  install locations (`/opt/homebrew/bin`, `/usr/local/bin`, `/Applications/OpenSCAD.app`,
  `/Applications/OpenSCAD-2021.01.app`, `/snap/bin`, `/usr/bin`). GUI hosts such as Claude
  Desktop do not inherit the shell `PATH`, so the literal `openscad` used to fail on macOS.
  When nothing is found the error says how to install it or set `OPENSCAD_PATH`, and it
  names the `OPENSCAD_PATH` value that was rejected, if one was set. `check_syntax` now
  returns `(False, message)` instead of raising `FileNotFoundError`.
- CI: a `macos-latest` job (`brew install --cask openscad@snapshot`), `continue-on-error`
  until it has been verified on a real runner.
- `server.json`: documents the `OPENSCAD_PATH` environment variable.

### Fixed
- **Right-hand finger joints in the wrong place** (`generate_box`, `generate_laser_part`).
  The right edge of a joint was placed at the loop length instead of the piece width, so
  slots and tabs only landed correctly when width = depth = height. For a 150×100×60 box
  the front wall slot was at x=57.2 instead of 147.2 and the side wall tabs at x=60
  instead of at the end of the wall. The parts did not fit together.
- `generate_laser_part` floor: the side-wall slots were only on the left edge, and on both
  edges they started at `y = 0`. The side walls sit between the front and back walls, so
  they start at `y = t`, and their bottom teeth landed 3 mm off the slots (slots at 0 to 18.9,
  teeth at 3 to 21.9 for 150×100×60). The slots are now on both edges, at `W - slot` on the
  right, and start at `y = t`: the teeth fit with only the designed `kerf` clearance left
  (the floor and side wall interference went from 110 to 34 mm³ per wall).
- `generate_box` did not assemble. The side walls were `D` long, but the space between the
  front and back walls is `D - 2t` (the dividers and the lid ring already used it), so their
  vertical teeth fell outside the front and back walls. The floor's side slots used the odd
  fingers while the side walls' bottom teeth use the even ones, and the 3D assembly put the
  floor beside the walls instead of under them, the back wall outside the floor and the side
  walls at `y = 0`. It now
  follows the model of `generate_laser_part`: the side wall is `D - 2t` long, the floor slots
  reuse the teeth's fingers shifted by `t`, and the layout, the dividers' position, the
  material estimate and `assembly_3d` agree with it. For 150×100×60 with 5 fingers the floor
  slots moved from Y 20.1-39.9 and 60.1-79.9 to 3.0-21.7, 40.7-59.3 and 78.3-97.0, which is
  where the side wall's teeth are. The side wall went from 100 to 94 mm.
- `generate_laser_part`: `openings` on the `left` and `right` walls were accepted by the
  validation and then silently not drawn. They are now rejected with "openings só em
  front/back nesta versão", and `validate_laser_config` reports them as a warning.
- `generate_box` dividers: X dividers were laid out on top of the walls in the 2D layout
  (the SVG/DXF merged them), and `dividers_y` cut the floor slots but produced no pieces.
  Divider pieces now follow the last wall in the layout, X dividers first and then Y.
- `generate_box` lid: the snap/slide lid was laid out at `y = H + gap`, on top of the floor
  (which spans `0..D`) whenever the depth exceeded the height plus the gap, as in the
  README example. The SVG/DXF fused them: 9 contours instead of 10. The lid now sits at
  `D + gap`.
- `run_openscad` accepted any output file that existed, even with a non-zero exit code.
  On OpenSCAD 2021.01 without a display, PNG rendering segfaults and leaves a
  0-byte file, which `render_to_png` reported as "Rendered successfully" with an empty
  image. It now fails with `OpenSCAD Error: exit code N` (`-11` for the segfault) when the
  exit code is non-zero or the output is missing or empty, and deletes the leftover file.
- `validate_output_path`: now resolves symlinks (`realpath`) on the path and on every
  allowed prefix and compares with `commonpath`. Before, `/tmpevil/x` matched `/tmp`, a
  symlink inside `/tmp` could point anywhere, and on macOS `/private/tmp` and
  `/var/folders/...` (what `tempfile.gettempdir()` returns) were rejected, which made 22 of
  the tests fail there. The system temp dir is in the default allow-list; the
  `MCP_OPENSCAD_ALLOWED_PATHS` separator is `os.pathsep`.
- `variables` (`-D`) injection: the name is validated (`^\$?[A-Za-z_][A-Za-z0-9_]*$`), the
  value must be bool, number, string or a list of numbers, and strings escape `\` before
  `"`. OpenSCAD evaluates `-D a=1;stmt` as code, so a crafted name or value could add
  geometry or import files. Shared by `render_to_png`, `export_*`, `analyze_mesh` and
  `mesh_section`.
- `import()`/`surface()` filter: comments are stripped (string-aware, so `"//"` inside a
  string does not hide code) before checking, and `import_stl`, `import_off`, `import_dxf`
  are blocked too. `import/**/("x.stl")` and `import_stl("x.stl")` used to pass. The
  policy is unchanged: file-reading functions stay prohibited.
- Banned keywords match whole words (plus a plural `s`) instead of substrings, so
  `begun`, `gunmetal`, `gun2` and `bombay` pass while `gun`, `guns` and `bomb` are still
  blocked. Only letters and digits glue to a word: `_` separates, so `water_gun_prop`,
  `pistol_grip`, `gun_barrel` and `ar15_receiver` stay blocked.
- `generate_assembly`: a piece name was used as a file name unchecked, so `../../x` wrote
  outside `output_dir`. `/` and `\` in a name are now rejected before anything is written.
  The rest is sanitized for both the file and the SCAD module name: accents lose their mark
  and anything that is not a letter, digit, `_` or `-` becomes `_` (`peça 1.b` becomes
  `peca_1_b`). A dot used to produce an invalid `module piece_a.b()`.
- `export_stl`/`export_3mf`/`export_dxf`/`export_svg`: `output_path` must now end with the
  tool's extension (case-insensitive), so a tool can no longer overwrite an arbitrary
  existing file with a different format. Overwriting a file with the right extension is
  unchanged.
- `check_syntax`: flagged `echo("no error here")` as invalid because it looked for the
  substring "error". It now fails on a non-zero exit code or on lines starting with
  `ERROR:`, and reports `WARNING:` and `ECHO:` lines as warnings. It also switched the
  probe from an SVG render to a CSG export: that only parses and evaluates the model, so a
  valid 3D model no longer exits with code 1 ("not a 2D object") and a heavy model no longer
  times out after 15 s on 2021.01 (the limit is kept).
- `generate_bracket`: the L bracket gusset was drawn in the XY plane and extruded along Z,
  so a 40×40×20 part came out 37 mm deep. It is now a triangle in the YZ plane with the
  thickness along X, inside the part.
- `analyze_mesh` and `mesh_section` ran their pure-Python geometry on the event loop and
  blocked the server (1.8 s on a 130k-triangle mesh). They now run in a worker thread.
- Cancelling a call left the `openscad` process running until it finished (up to
  `timeout_s`, 900 s at most). `run_openscad` and `check_syntax` now kill it on
  cancellation, and `run_openscad` also deletes the partial output file.
- Text files (temporary `.scad`, generated `.scad`, assembly pieces and BOM) are written
  as UTF-8. Without an explicit encoding Python used the locale, and `generate_kerf_test`
  crashed with `UnicodeEncodeError` on `—` where UTF-8 mode was off.

### Changed
- `mcp>=1.10,<2` (was `>=1.0.0`): the SDK only validates `inputSchema` (`required`,
  including `output_dir`) from 1.10.0 on; older versions skipped the path sanitation.
- Packaging: dropped `packages = ["."]` from the wheel target. The wheel used to ship
  `README.md`, `LICENSE`, `Dockerfile`, `skills/` and the CI files into `site-packages`;
  it now contains only `server.py` and the dist-info.
- Version is 0.9.0 in `pyproject.toml`, `server.json` (both places) and the MCP handshake.
- Removed the unused `import subprocess`. Cleared 11 of the 14 pre-existing `ruff`
  findings (`E,F,W`): whitespace on blank lines, `f` prefix on strings without
  placeholders, an unused exception variable. The other three are unused assignments
  (`F841`) that were left alone and stay visible in the lint output.
- The inner helpers `side_finger_loop` and `tabs_side` now take `edge` as a required
  keyword argument.

### Known issues
- `suggest_orientation` reads `profile` (`fdm_standard`, `fdm_fine`, `resin`) but never
  uses it, so the option has no effect. `ruff` reports it as `F841`, along with two other
  unused assignments in `validate_config` and `generate_cnc_toolpath_hints`.

### Docs
- README: macOS install (`brew install --cask openscad@snapshot`; the `openscad` cask is
  disabled), Python >= 3.10, `uvx --from git+...`, `claude mcp add`, Claude Desktop config
  with absolute paths and an `env` block, environment variables, skill install, required
  parameters of every tool, new examples, limitations and troubleshooting.
- ROADMAP and GEMINI brought up to date.
- CONTRIBUTING: setup with `uv sync --extra dev` (or a venv) and `OPENSCAD_PATH` instead
  of requiring `openscad` on the `PATH`.

### Tests
- **424 tests** (up from 291). New: binary lookup (precedence, fallbacks, cache,
  message), path validation (sibling prefix, symlinks, symlinked prefix, system temp dir),
  failed and empty output, right-hand joints and floor slots of both generators, layout
  without overlap (dividers and lid, also checked on the SVG contour count), `variables`
  injection and escaping, filter bypasses, whole-word keywords, openings on side walls,
  floor slot and side wall tooth alignment of both generators (positions, and the interference
  measured on the assembled pieces: only the designed `kerf` clearance is left in each joint),
  piece names, export extensions, `check_syntax` classification, gusset bounding box,
  worker-thread execution, cancellation (process and partial output), `export_obj` (real on
  the nightly, simulated for 2021.01) and UTF-8 under a C locale.
- Existing tests adjusted: tool count 26 → 27; three path assertions compare against
  `realpath` so they hold on macOS (`/tmp` → `/private/tmp`); the mocked process in
  `test_run_openscad_custom_timeout_used` now creates its output file, since a missing
  output is a failure.
- The six tests that need a real PNG (the plain `render_to_png` handler call, its default
  camera, custom camera, ortho and custom size variants, and the box PNG render) use a
  session fixture that renders a cube
  to PNG once and skips them with "OpenSCAD sem contexto GL (2021.01 sem display)" when
  OpenSCAD cannot. On 2021.01 without a display they used to pass only because an empty PNG
  was accepted as success; they now would fail with `OpenSCAD Error: exit code -11`.
  The CI runs 2021.01 under `xvfb-run` and the nightly renders PNG headless, so they run there.

## [0.8.1] — 2026-09-10

### Fixed
- `_parse_stl` (used by `analyze_mesh` and `mesh_section`) detected binary vs. ASCII
  STL purely by file size (`size == 84 + 50*n`). OpenSCAD 2021.01 exports ASCII by
  default, so roughly 1 in 50 valid ASCII files happened to have a byte length that
  also satisfied the binary formula, got misparsed as binary, and produced garbage
  (observed in production: a bbox at 1e34 scale on a valid file — the same file
  parsed fine after a trivial geometry edit changed its byte length). Detection is
  now content-first: if the file starts with `solid` (case-insensitive) and contains
  `facet` in the first 1KB, or `endsolid` in the last 200 bytes, it's treated as
  ASCII regardless of size; only files that don't look like ASCII fall back to the
  size-based binary check (some binary exporters do write a literal `solid` header,
  hence the extra content check rather than trusting the first 5 bytes alone).
- The binary parser now validates its own output: a non-finite or `|coordinate| >
  1e9` value raises a clear `ValueError` ("STL parse produced non-finite/huge
  coordinates — file may be ASCII misdetected as binary") instead of silently
  returning garbage geometry.

### Tests
- **291 tests** (up from 288): an ASCII STL padded to accidentally match the binary
  size formula still parses correctly (bbox/volume of the 10mm cube), a binary STL
  with a `solid`-prefixed header still parses as binary, and a garbage-coordinate
  guard test.

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
