---
name: 3d-print-gate
description: Pre-slicing quality gate for OpenSCAD/STL parts — use before sending any part to a slicer, and especially for multi-part assemblies that include press-fits or other mating features. Drives the mcp-openscad tools `analyze_mesh` (watertight/manifold/overhang/bridge checks) and `mesh_section` (cross-section fit checks between mating parts). Takes an optional argument: a path to a `.scad` file (with named parts, e.g. a `part=` variable) or a folder of already-exported `.stl` files.
license: MIT
---

# 3D Print Gate

A procedural checklist that catches printability and fit problems in software,
before a part hits the slicer or the printer. It exists because a good-looking
render is not evidence of printability — it hides disconnected solids,
zero-thickness walls, and non-manifold geometry just as easily as it hides a
sound design.

## When to use

- Before slicing any OpenSCAD-generated or hand-authored STL part.
- Always for multi-part assemblies with press-fits, bores, pins, or any other
  mating geometry — that's where silent fit failures live.
- When the user asks to "check before printing", "validate this part/assembly",
  or invokes this skill explicitly with a `.scad` path or a folder of STLs.

## Procedure

### (a) Export every part in its print orientation

Export each part exactly as it will sit on the bed — not the assembly's design
orientation. Use the OpenSCAD CLI with `-D part=<name>` (or whatever variable
selects a part in the source `.scad`) per part, or `mcp-openscad`'s
`export_stl` tool with the same `variables`. Complex parts may need more than
the default 60s render — pass `timeout_s` (up to 900) rather than letting the
export time out silently.

### (b) `analyze_mesh` per part — pass criteria

Run `analyze_mesh` (via `stl_path` on the exported file, or directly with
`scad_code` + `variables`) for every part. A part **passes** when:

- `watertight` is `true`
- `components == 1` (a single connected shell — unless multiple shells are an
  intentional design, e.g. two half-clam parts printed as one plate)
- `floating_components == 0`
- `overhang_pct <= 5` — or higher, explicitly justified (e.g. a chamfer the
  design accepts printing with visible artifacts on)
- the largest bridge span `<= 30mm` — or explicitly justified with a known
  bridging-capable printer/filament

Anything outside these is a **fail**: fix the geometry (or the print
orientation) before moving on. Don't average scores across parts — every part
must individually pass.

### (c) Fit check between mating parts

For each male/female (pin/hole, boss/bore, press-fit) pair:

1. Identify the mating height(s) — the z (or x/y) range where the two parts
   actually interface.
2. Run `mesh_section` on both parts at those heights (same `axis`, matching
   z/z_list, ideally the same `center` so radii are directly comparable).
3. Read the male part's OD from its outer contour and the female part's bore
   diameter from its inner contour — both as `2 * r_max` (the nominal vertex
   radius on a faceted/`$fn` mesh), never `r_min` (the facet apothem, which
   is smaller and not what the design dimension refers to). This is exactly
   `mesh_section`'s own "Ø externo/Ø interno/parede" line for a hollow
   section.
4. Compute `clearance_mm = (female_bore_diameter - male_od) / 2` (radial
   clearance per side).
5. Compare against the design's intended clearance, tolerance **±0.05mm**.
   Outside that band is a fail — even if both parts individually passed (b).

Table every pair: `part_a | part_b | height | male_od | female_bore |
clearance | design_clearance | pass/fail`.

### (d) Orientation sanity

`suggest_orientation` exists and is a useful first pass, but it's a heuristic
score — don't accept its output uncritically. Reason explicitly about:

- **First-layer contact area**: is the bed-touching face large and flat
  enough for adhesion, or is the part balanced on a small/pointed footprint?
- **Overhangs introduced by this specific orientation**: re-check with
  `analyze_mesh` at the orientation actually chosen, not the design
  orientation — overhang and bridge numbers change with orientation.

If the heuristic and the explicit reasoning disagree, explicit reasoning
wins; say why in the output.

### (e) Blind review of the source

Have a second model read the `.scad` source **read-only** (no edits) against
this checklist:

- Wall thicknesses are `>= 2 * nozzle_diameter` everywhere load-bearing.
- Bores/holes that must go all the way through are extended past the surface
  by a small `eps` (e.g. `0.01–0.1mm`) on both ends — a bore ending exactly
  flush with a face is a classic zero-thickness/coincident-face bug.
- No sliver geometry (near-zero-thickness walls, near-coplanar coincident
  faces) introduced by boolean operations.
- Parameters actually drive the geometry end-to-end — no hardcoded numbers
  that silently ignore a parameter change.
- The assembly view and the per-part plate/export are consistent (same
  version of each part, not a stale cached one).

**The governing lesson: never approve a part from its PNG preview.** A render
can look flawless while the underlying mesh is two disconnected shells, has a
zero-thickness wall that CSG happened to render as a visible surface, or has
a bore that doesn't actually pierce the far wall. Only `analyze_mesh` /
`mesh_section` (or this read-only source review) catch that — the render
can't.

### (f) Output

Produce a short, scannable pass/fail table:

- One row per part: watertight / components / floating / overhang% / bridge
  span → pass/fail.
- One row per mating pair: clearance vs. design → pass/fail.

Only release the parts for slicing once every row passes (or every failure
is explicitly justified in the output, not silently waived). If anything
fails, report it and stop — don't slice on a "probably fine."
