import os
import subprocess
import tempfile
import asyncio
import math
import shutil
import base64
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

server = Server("mcp-openscad")

# ──────────────────────────────────────────────
# Utilitário interno: roda openscad
# ──────────────────────────────────────────────
def run_openscad(scad_code: str, output_ext: str, export_args=None):
    if export_args is None:
        export_args = []

    with tempfile.NamedTemporaryFile(suffix=".scad", delete=False, mode='w') as f:
        f.write(scad_code)
        scad_path = f.name

    out_path = scad_path.replace(".scad", f".{output_ext}")

    cmd = ["openscad", "-o", out_path] + export_args + [scad_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0 and not os.path.exists(out_path):
            raise RuntimeError(f"OpenSCAD Error:\n{result.stderr}")
        return out_path, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        raise RuntimeError("OpenSCAD Error: Execution timed out after 60 seconds.")
    finally:
        if os.path.exists(scad_path):
            os.remove(scad_path)


# ──────────────────────────────────────────────
# check_syntax: valida sintaxe sem renderizar
# ──────────────────────────────────────────────
def check_scad_syntax(scad_code: str) -> tuple:
    """
    Verifica sintaxe do código SCAD usando openscad.
    Retorna (is_valid, message).
    """
    with tempfile.NamedTemporaryFile(suffix=".scad", delete=False, mode='w') as f:
        f.write(scad_code)
        scad_path = f.name

    try:
        result = subprocess.run(
            ["openscad", "--export-format", "svg", "-o", os.devnull, scad_path],
            capture_output=True, text=True, timeout=15
        )
        stderr = result.stderr.strip()
        errors = [ln for ln in stderr.splitlines() if "ERROR" in ln or "error" in ln.lower()]
        if errors:
            return False, "Erros encontrados:\n" + "\n".join(errors)
        warnings = [ln for ln in stderr.splitlines() if "WARNING" in ln or "ECHO" in ln]
        if warnings:
            return True, "✅ Sintaxe válida (com avisos):\n" + "\n".join(warnings)
        return True, "✅ Sintaxe válida — nenhum problema encontrado."
    except subprocess.TimeoutExpired:
        return False, "❌ Timeout ao verificar sintaxe."
    finally:
        if os.path.exists(scad_path):
            os.remove(scad_path)


# ──────────────────────────────────────────────
# Gerador inteligente de SCAD para laser cutting
# ──────────────────────────────────────────────

def generate_laser_scad(config: dict) -> str:
    t   = config.get("material_thickness", 3)
    kerf = config.get("kerf", 0.2)
    W   = config.get("width",  100)
    D   = config.get("depth",  100)
    H   = config.get("height", 80)
    N   = max(1, config.get("fingers", 5))
    openings = config.get("openings", [])

    # Clamp kerf to material thickness
    kerf = min(kerf, t - 0.1)
    slot = t - kerf
    gap  = 15

    def finger_loop_with_exclusions(total_len, n_fingers, exclusions, axis='x',
                                    is_tab=True, depth=None):
        if depth is None:
            depth = t
        fw = total_len / n_fingers
        lines = []
        for i in range(0, n_fingers, 2):
            x0 = 0 if i == 0 else i * fw - kerf / 2
            x1 = total_len if i == n_fingers - 1 else (i + 1) * fw + kerf / 2
            center = (x0 + x1) / 2
            blocked = any(ex_s <= center <= ex_e for (ex_s, ex_e) in exclusions)
            if blocked:
                continue
            if axis == 'x':
                if is_tab:
                    lines.append(f"        translate([{x0:.4f}, {-depth:.4f}]) square([{x1-x0:.4f}, {depth:.4f}]);")
                else:
                    lines.append(f"        translate([{x0:.4f}, 0]) square([{x1-x0:.4f}, {slot:.4f}]);")
            else:
                if is_tab:
                    lines.append(f"        translate([{-depth:.4f}, {x0:.4f}]) square([{depth:.4f}, {x1-x0:.4f}]);")
                else:
                    lines.append(f"        translate([0, {x0:.4f}]) square([{slot:.4f}, {x1-x0:.4f}]);")
        return "\n".join(lines)

    def side_finger_loop(total_len, n_fingers, is_tab=True, depth=None, side='left'):
        if depth is None:
            depth = t
        fw = total_len / n_fingers
        lines = []
        for i in range(1, n_fingers, 2):
            y0 = i * fw + (kerf / 2 if not is_tab else -kerf / 2)
            y1 = (i + 1) * fw + (-kerf / 2 if not is_tab else kerf / 2)
            if is_tab:
                offset = -depth if side == 'left' else total_len
                lines.append(f"        translate([{offset:.4f}, {y0:.4f}]) square([{depth:.4f}, {y1-y0:.4f}]);")
            else:
                offset = 0 if side == 'left' else total_len - slot
                lines.append(f"        translate([{offset:.4f}, {y0:.4f}]) square([{slot:.4f}, {y1-y0:.4f}]);")
        return "\n".join(lines)

    def opening_scad(op):
        shape = op.get("shape", "rect")
        if shape == "rect":
            x, y = op.get("x", 0), op.get("y", 0)
            w, h = op.get("w", 30), op.get("h", 40)
            return f"        translate([{x:.4f}, {y:.4f}]) square([{w:.4f}, {h:.4f}]);"
        elif shape == "circle":
            cx, cy = op.get("cx", 50), op.get("cy", 40)
            d = op.get("d", 20)
            return f"        translate([{cx:.4f}, {cy:.4f}]) circle(d={d:.4f}, $fn=64);"
        return ""

    def x_exclusions_for_wall(wall_name, wall_width):
        excl = []
        for op in openings:
            if op.get("wall") != wall_name:
                continue
            shape = op.get("shape", "rect")
            if shape == "rect" and op.get("y", 999) == 0:
                x0 = op.get("x", 0)
                x1 = x0 + op.get("w", 0)
                excl.append((x0, x1))
        return excl

    def ops_for(wall):
        return [op for op in openings if op.get("wall") == wall]

    front_ops = ops_for("front")
    back_ops  = ops_for("back")

    front_excl = x_exclusions_for_wall("front", W)
    back_excl  = x_exclusions_for_wall("back",  W)

    side_w = D - 2 * t

    front_tabs  = finger_loop_with_exclusions(W, N, front_excl, axis='x', is_tab=True)
    back_tabs   = finger_loop_with_exclusions(W, N, back_excl,  axis='x', is_tab=True)
    floor_f_slots = finger_loop_with_exclusions(W, N, front_excl, axis='x', is_tab=False)
    floor_b_slots = finger_loop_with_exclusions(W, N, back_excl,  axis='x', is_tab=False)

    front_openings_scad = "\n".join(opening_scad(op) for op in front_ops)
    back_openings_scad  = "\n".join(opening_scad(op) for op in back_ops)

    # Build translated back slots for floor
    back_slot_lines = []
    for ln in floor_b_slots.splitlines():
        ln = ln.strip()
        if ln and "translate" in ln:
            coords_part = ln.split("translate([")[1].split(", 0])")[0]
            dim_part = ln.split("square([")[1].split("])")[0]
            back_slot_lines.append(f"        translate([{coords_part}, D-slot]) square([{dim_part}]);")
    floor_b_slots_translated = "\n".join(back_slot_lines)

    scad = f"""// ============================================================
// Gerado automaticamente pelo MCP-OpenSCAD Laser Tool
// ============================================================
t   = {t};
kerf = {kerf};
W   = {W};
D   = {D};
H   = {H};
slot = t - kerf;
side_w = D - 2 * t;
gap  = {gap};

// ── Parede Frontal ──────────────────────────────────────────
module front_wall() {{
    difference() {{
        union() {{
            square([W, H]);
            // Dentes inferiores (evitam aberturas que tocam y=0)
{front_tabs}
        }}
        // Aberturas (porta, janela...)
{front_openings_scad}
        // Fendas laterais (recebem dentes da side_wall)
{side_finger_loop(H, N, is_tab=False, depth=slot, side='left')}
{side_finger_loop(H, N, is_tab=False, depth=slot, side='right')}
    }}
}}

// ── Parede Traseira ─────────────────────────────────────────
module back_wall() {{
    difference() {{
        union() {{
            square([W, H]);
            // Dentes inferiores
{back_tabs}
        }}
        // Aberturas
{back_openings_scad}
        // Fendas laterais
{side_finger_loop(H, N, is_tab=False, depth=slot, side='left')}
{side_finger_loop(H, N, is_tab=False, depth=slot, side='right')}
    }}
}}

// ── Parede Lateral ──────────────────────────────────────────
module side_wall() {{
    union() {{
        square([side_w, H]);
        // Dentes para front/back (eixo Y)
{side_finger_loop(H, N, is_tab=True, depth=t, side='left')}
{side_finger_loop(H, N, is_tab=True, depth=t, side='right')}
        // Dentes inferiores
{finger_loop_with_exclusions(side_w, N, [], axis='x', is_tab=True)}
    }}
}}

// ── Piso (Base) ─────────────────────────────────────────────
module floor_base() {{
    difference() {{
        square([W, D]);
        // Fendas parede frontal (y=0)
{floor_f_slots}
        // Fendas parede traseira (y=D-slot)
{floor_b_slots_translated}
        // Fendas paredes laterais
{finger_loop_with_exclusions(side_w, N, [], axis='y', is_tab=False)}
    }}
}}

// ── Layout 2D ───────────────────────────────────────────────
module layout_2d() {{
    translate([0, 0])         front_wall();
    translate([W+gap, 0])     back_wall();
    translate([2*(W+gap), 0]) floor_base();
    y2 = H + gap;
    translate([0, y2])            side_wall();
    translate([side_w+gap, y2])   side_wall();
    y3 = y2 + H + gap;
"""

    disk_x = 0
    disk_lines = []
    for op in openings:
        if op.get("shape") == "circle":
            d = op.get("d", 20)
            r = d / 2
            disk_lines.append(f"    translate([{disk_x + r:.1f}, y3+{r:.1f}]) circle(d={d}, $fn=64);")
            disk_x += d + gap

    scad += "\n".join(disk_lines) + "\n}\n\n"

    scad += f"""// ── Assembly 3D ─────────────────────────────────────────────
module assembly_3d() {{
    color([0.9,0.8,0.6])
        translate([0, 0, -t])
            linear_extrude(t) floor_base();
    color([0.9,0.6,0.4])
        translate([0, t, 0])
            rotate([90,0,0])
                linear_extrude(t) front_wall();
    color([0.9,0.5,0.4])
        translate([0, D, 0])
            rotate([90,0,0])
                linear_extrude(t) back_wall();
    color([0.8,0.5,0.4])
        translate([0, t, 0])
            rotate([90,0,90])
                linear_extrude(t) side_wall();
    color([0.8,0.4,0.6])
        translate([W-t, t, 0])
            rotate([90,0,90])
                linear_extrude(t) side_wall();
}}

RENDER_MODE = "3d";
if (RENDER_MODE == "2d") {{
    layout_2d();
}} else {{
    assembly_3d();
}}
"""
    return scad


# ──────────────────────────────────────────────
# generate_box: caixa retangular com tampa laser
# ──────────────────────────────────────────────

def generate_box_scad(config: dict) -> str:
    """
    Gera caixa retangular completa com tampa encaixável para laser cutting.
    Suporta: snap, slide, none. Divisórias internas X e Y.
    """
    t    = config.get("material_thickness", 3)
    kerf = config.get("kerf", 0.2)
    W    = config.get("width", 100)
    D    = config.get("depth", 80)
    H    = config.get("height", 50)
    N    = max(1, config.get("fingers", 5))
    lid  = config.get("lid_type", "snap")
    lc   = config.get("lid_clearance", 0.3)
    div_x = max(0, config.get("dividers_x", 0))
    div_y = max(0, config.get("dividers_y", 0))

    # Clamp kerf to material thickness
    kerf = min(kerf, t - 0.1)
    slot = t - kerf
    gap  = 15

    # Ensure N is odd for symmetrical joints
    if N % 2 == 0:
        N += 1

    def tabs_bottom(length, n, is_tab=True):
        """Dentes/fendas na borda inferior (Y=0)."""
        fw = length / n
        lines = []
        for i in range(0, n, 2):
            x0 = i * fw + (0 if i == 0 else kerf / 2)
            x1 = (i + 1) * fw - (0 if i == n - 1 else kerf / 2)
            if is_tab:
                lines.append(f"    translate([{x0:.3f}, {-t:.3f}]) square([{x1-x0:.3f}, {t:.3f}]);")
            else:
                lines.append(f"    translate([{x0:.3f}, 0]) square([{x1-x0:.3f}, {slot:.3f}]);")
        return "\n".join(lines)

    def tabs_side(length, n, is_tab=True, side='left'):
        """Dentes/fendas nas bordas laterais (X=0 ou X=length)."""
        fw = length / n
        lines = []
        for i in range(1, n, 2):
            y0 = i * fw + kerf / 2
            y1 = (i + 1) * fw - kerf / 2
            if is_tab:
                ox = -t if side == 'left' else length
                lines.append(f"    translate([{ox:.3f}, {y0:.3f}]) square([{t:.3f}, {y1-y0:.3f}]);")
            else:
                ox = 0 if side == 'left' else length - slot
                lines.append(f"    translate([{ox:.3f}, {y0:.3f}]) square([{slot:.3f}, {y1-y0:.3f}]);")
        return "\n".join(lines)

    inner_w = W - 2 * t
    inner_d = D - 2 * t

    # Build back-translated floor slots
    front_slot_lines = tabs_bottom(W, N, is_tab=False)
    back_slot_lines_raw = []
    for ln in front_slot_lines.splitlines():
        ln = ln.strip()
        if ln and "translate" in ln:
            coords_part = ln.split("translate([")[1].split(", 0])")[0]
            dim_part = ln.split("square([")[1].split("])")[0]
            back_slot_lines_raw.append(f"    translate([{coords_part}, {D - slot:.3f}]) square([{dim_part}]);")
    back_slots_floor = "\n".join(back_slot_lines_raw)

    # Divisórias X (paralelas ao eixo depth, cortam ao longo de D)
    divider_floor_slots = ""
    divider_layout_pieces = ""
    if div_x > 0:
        step = inner_w / (div_x + 1)
        slot_lines = []
        for i in range(div_x):
            xpos = t + step * (i + 1) - t / 2
            slot_lines.append(f"    // Divisória X{i+1}: fenda no piso\n    translate([{xpos:.3f}, {t:.3f}]) square([{slot:.3f}, {inner_d:.3f}]);")
            lx = (i + 1) * (inner_d + gap) + W + gap
            divider_layout_pieces += f"    translate([{lx:.3f}, 0]) square([{inner_d:.3f}, {H:.3f}]);\n"
        divider_floor_slots = "\n".join(slot_lines)

    divider_y_floor_slots = ""
    if div_y > 0:
        step = inner_d / (div_y + 1)
        slot_lines_y = []
        for i in range(div_y):
            ypos = t + step * (i + 1) - t / 2
            slot_lines_y.append(f"    // Divisória Y{i+1}: fenda no piso\n    translate([{t:.3f}, {ypos:.3f}]) square([{inner_w:.3f}, {slot:.3f}]);")
        divider_y_floor_slots = "\n".join(slot_lines_y)

    # Tampa
    lid_module = ""
    lid_in_layout = ""
    lid_lip = t
    if lid == "snap":
        lid_module = f"""
// ── Tampa Snap-fit ───────────────────────────────────────────
module box_lid() {{
    // Plano principal
    square([{W:.3f}, {D:.3f}]);
    // Reborda de encaixe
    translate([{lid_lip:.3f}, {lid_lip:.3f}])
        difference() {{
            square([{W - 2*lid_lip:.3f}, {D - 2*lid_lip:.3f}]);
            translate([{t:.3f}, {t:.3f}]) square([{W - 2*lid_lip - 2*t:.3f}, {D - 2*lid_lip - 2*t:.3f}]);
        }}
}}
"""
        lid_in_layout = f"    translate([0, {H + gap:.3f}]) box_lid();\n"
    elif lid == "slide":
        lid_module = f"""
// ── Tampa Deslizante ─────────────────────────────────────────
module box_lid() {{
    square([{W - lc*2:.3f}, {D - lc*2:.3f}]);
}}
"""
        lid_in_layout = f"    translate([0, {H + gap:.3f}]) box_lid();\n"

    scad = f"""// ============================================================
// Caixa Laser — Gerada pelo MCP-OpenSCAD
// {W}x{D}x{H}mm | Espessura: {t}mm | Kerf: {kerf}mm | Tampa: {lid}
// ============================================================
t    = {t};
kerf = {kerf};
W    = {W};
D    = {D};
H    = {H};
slot = t - kerf;
gap  = {gap};

// ── Piso ─────────────────────────────────────────────────────
module box_floor() {{
    difference() {{
        square([W, D]);
        // Fendas parede frontal
{front_slot_lines}
        // Fendas parede traseira
{back_slots_floor}
        // Fendas paredes laterais esq/dir
{tabs_side(D, N, is_tab=False, side='left')}
{tabs_side(D, N, is_tab=False, side='right')}
{divider_floor_slots}
{divider_y_floor_slots}
    }}
}}

// ── Parede Frontal/Traseira ───────────────────────────────────
module box_front_wall() {{
    difference() {{
        union() {{
            square([W, H]);
            // Dentes para encaixe com piso
{tabs_bottom(W, N, is_tab=True)}
        }}
        // Fendas para paredes laterais
{tabs_side(H, N, is_tab=False, side='left')}
{tabs_side(H, N, is_tab=False, side='right')}
    }}
}}

// ── Parede Lateral ───────────────────────────────────────────
module box_side_wall() {{
    union() {{
        square([D, H]);
        // Dentes para encaixe com piso
{tabs_bottom(D, N, is_tab=True)}
        // Dentes para front/back
{tabs_side(H, N, is_tab=True, side='left')}
{tabs_side(H, N, is_tab=True, side='right')}
    }}
}}

{lid_module}

// ── Layout 2D (para corte) ────────────────────────────────────
module layout_2d() {{
    translate([0, 0])                    box_floor();
    translate([{W + gap:.3f}, 0])        box_front_wall();
    translate([{2*(W + gap):.3f}, 0])    box_front_wall();
    translate([{3*(W + gap):.3f}, 0])    box_side_wall();
    translate([{3*(W + gap) + D + gap:.3f}, 0]) box_side_wall();
{divider_layout_pieces}{lid_in_layout}}}

// ── Assembly 3D ───────────────────────────────────────────────
module assembly_3d() {{
    // Piso
    color([0.9, 0.8, 0.6]) linear_extrude(t) box_floor();
    // Frontal
    color([0.9, 0.6, 0.4])
        translate([0, 0, 0]) rotate([90,0,0])
            translate([0, 0, {-t:.3f}]) linear_extrude(t) box_front_wall();
    // Traseira
    color([0.9, 0.5, 0.4])
        translate([0, D, 0]) rotate([90,0,0])
            translate([0, 0, {-t:.3f}]) linear_extrude(t) box_front_wall();
    // Lateral esquerda
    color([0.8, 0.5, 0.4])
        translate([0, 0, 0]) rotate([90,0,90])
            linear_extrude(t) box_side_wall();
    // Lateral direita
    color([0.8, 0.4, 0.6])
        translate([W, 0, 0]) rotate([90,0,90])
            translate([0, 0, {-t:.3f}]) linear_extrude(t) box_side_wall();
}}

RENDER_MODE = "3d";
if (RENDER_MODE == "2d") {{
    layout_2d();
}} else {{
    assembly_3d();
}}
"""
    return scad


def validate_box_config(config: dict) -> list:
    warnings = []
    t = config.get("material_thickness", 3)
    W = config.get("width", 100)
    D = config.get("depth", 80)
    H = config.get("height", 50)
    N = config.get("fingers", 5)

    if N % 2 == 0:
        warnings.append("⚠ 'fingers' deve ser ímpar para finger joints simétricos. Recomendado: 5, 7, 9.")
    if t >= min(W, D, H) / 4:
        warnings.append(f"⚠ Espessura ({t}mm) grande em relação às dimensões. Verifique.")
    if W / N < t * 2:
        warnings.append(f"⚠ Dentes muito finos ({W/N:.1f}mm). Aumente 'width' ou diminua 'fingers'.")
    if config.get("dividers_x", 0) < 0 or config.get("dividers_y", 0) < 0:
        warnings.append("⚠ Número de divisórias não pode ser negativo.")
    if config.get("lid_type", "snap") not in ("snap", "slide", "none"):
        warnings.append("⚠ 'lid_type' deve ser 'snap', 'slide' ou 'none'.")
    return warnings


# ──────────────────────────────────────────────
# estimate_material_use
# ──────────────────────────────────────────────

def estimate_material_use(config: dict, sheet_w: float = 600, sheet_h: float = 400) -> dict:
    t = config.get("material_thickness", 3)
    W = config.get("width", 100)
    D = config.get("depth", 80)
    H = config.get("height", 50)

    pieces = [
        {"name": "Piso",             "qty": 1, "w": W, "h": D},
        {"name": "Frontal/Traseira", "qty": 2, "w": W, "h": H},
        {"name": "Lateral",          "qty": 2, "w": D, "h": H},
    ]

    lid = config.get("lid_type", "snap")
    if lid in ("snap", "slide"):
        pieces.append({"name": "Tampa", "qty": 1, "w": W, "h": D})

    div_x = config.get("dividers_x", 0)
    div_y = config.get("dividers_y", 0)
    if div_x > 0:
        pieces.append({"name": "Divisória X", "qty": div_x, "w": D - 2*t, "h": H})
    if div_y > 0:
        pieces.append({"name": "Divisória Y", "qty": div_y, "w": W - 2*t, "h": H})

    total_area = sum(p["qty"] * p["w"] * p["h"] for p in pieces)
    sheet_area = sheet_w * sheet_h
    usage_pct  = (total_area / sheet_area) * 100

    return {
        "pieces": pieces,
        "total_area_mm2": round(total_area, 1),
        "total_area_cm2": round(total_area / 100, 1),
        "sheet_w_mm": sheet_w,
        "sheet_h_mm": sheet_h,
        "sheet_area_mm2": round(sheet_area, 1),
        "usage_percent": round(usage_pct, 1),
        "sheets_needed": math.ceil(usage_pct / 100),
    }


# ──────────────────────────────────────────────
# generate_kerf_test
# ──────────────────────────────────────────────

def generate_kerf_test_scad(config: dict) -> str:
    t         = config.get("material_thickness", 3)
    kerf_min  = config.get("kerf_min", 0.0)
    kerf_max  = config.get("kerf_max", 0.5)
    kerf_step = config.get("kerf_step", 0.05)
    test_len  = config.get("test_length", 30)

    # Guard against infinite loop
    if kerf_step <= 0:
        kerf_step = 0.05

    kerfs = []
    k = kerf_min
    while k <= kerf_max + 1e-9:
        kerfs.append(round(k, 4))
        k += kerf_step

    gap   = 5
    pin_w = t
    col_w = pin_w + gap + t + gap + t  # pino + espaço + placa-com-fenda + margem

    scad = f"""// ============================================================
// Placa de Teste de Kerf — MCP-OpenSCAD
// Material: {t}mm | Kerf: {kerf_min}–{kerf_max}mm | Passo: {kerf_step}mm
// ============================================================
// Como usar:
//   1. Corte esta placa no laser
//   2. Tente encaixar cada pino na sua fenda correspondente
//   3. O slot que encaixar por pressão = seu kerf correto
// ============================================================

t = {t};

"""

    x_off = 0
    for kv in kerfs:
        slot_val = round(t - kv, 4)
        pin_x    = x_off
        plate_x  = x_off + pin_w + gap

        scad += f"""// ─── Kerf = {kv}mm  (slot = {slot_val}mm) ────────────────────
// Pino macho
translate([{pin_x:.3f}, 0]) square([{pin_w:.3f}, {test_len:.3f}]);
// Placa fêmea com fenda
translate([{plate_x:.3f}, 0])
    difference() {{
        square([{gap + slot_val + gap:.3f}, {test_len:.3f}]);
        translate([{gap:.3f}, 0]) square([{slot_val:.3f}, {test_len:.3f}]);
    }}

"""
        x_off += col_w

    return scad


# ──────────────────────────────────────────────
# generate_finger_test
# ──────────────────────────────────────────────

def generate_finger_test_scad(config: dict) -> str:
    t          = config.get("material_thickness", 3)
    off_min    = config.get("offset_min", -0.2)
    off_max    = config.get("offset_max", 0.2)
    off_step   = config.get("offset_step", 0.05)
    fw         = config.get("finger_width", 5)
    fn         = max(1, config.get("finger_count", 5))
    piece_h    = config.get("height", 30)

    # Guard against infinite loop
    if off_step <= 0:
        off_step = 0.05

    offsets = []
    o = off_min
    while o <= off_max + 1e-9:
        offsets.append(round(o, 4))
        o += off_step

    piece_w = fn * fw
    gap     = 8

    scad = f"""// ============================================================
// Pente de Teste de Finger Joints — MCP-OpenSCAD
// Material: {t}mm | Offset: {off_min}–{off_max}mm | Passo: {off_step}mm
// ============================================================
// Como usar:
//   Corte todos os pentes e tente encaixar o macho na fêmea.
//   O par com encaixe suave = offset correto para seu material.
// ============================================================

t  = {t};
fw = {fw};

"""

    x_off = 0
    for off in offsets:
        tab_w  = fw + off
        slot_w = fw - off

        macho_tabs = ""
        for j in range(0, fn, 2):
            tx = j * fw
            macho_tabs += f"        translate([{tx:.3f}, {-t:.3f}]) square([{tab_w:.3f}, {t:.3f}]);\n"

        femea_fendas = ""
        for j in range(0, fn, 2):
            fx = j * fw
            femea_fendas += f"        translate([{fx:.3f}, 0]) square([{slot_w:.3f}, {t:.3f}]);\n"

        scad += f"""// ─── Offset = {off:+.3f}mm (tab={tab_w:.3f}mm, slot={slot_w:.3f}mm) ───
translate([{x_off:.3f}, 0]) {{
    union() {{
        square([{piece_w:.3f}, {piece_h:.3f}]);
{macho_tabs}    }}
}}
translate([{x_off:.3f}, {piece_h + gap:.3f}]) {{
    difference() {{
        square([{piece_w:.3f}, {piece_h:.3f}]);
{femea_fendas}    }}
}}

"""
        x_off += piece_w + gap + 5

    return scad


# ──────────────────────────────────────────────
# Validador original: laser_part
# ──────────────────────────────────────────────
def validate_config(config: dict) -> list:
    warnings = []
    t    = config.get("material_thickness", 3)
    W    = config.get("width", 100)
    N    = config.get("fingers", 5)
    fw   = W / N
    openings = config.get("openings", [])

    for op in openings:
        wall = op.get("wall")
        shape = op.get("shape", "rect")

        if shape == "rect" and op.get("y", 999) == 0:
            ox1 = op.get("x", 0)
            ox2 = ox1 + op.get("w", 0)
            for i in range(0, N, 2):
                x0 = 0 if i == 0 else i * fw
                x1 = W if i == N-1 else (i+1) * fw
                center = (x0 + x1) / 2
                if ox1 <= center <= ox2:
                    warnings.append(
                        f"⚠ [{wall}] Dente i={i} (x={x0:.1f}–{x1:.1f}) cai "
                        f"dentro da abertura '{shape}' (x={ox1}–{ox2}). "
                        f"Será omitido automaticamente."
                    )
        if shape == "rect":
            x, y = op.get("x", 0), op.get("y", 0)
            w_op, h_op = op.get("w", 0), op.get("h", 0)
            H = config.get("height", 80)
            if y + h_op > H:
                warnings.append(
                    f"⚠ [{wall}] Abertura '{shape}' (y={y}, h={h_op}) ultrapassa "
                    f"a altura da parede ({H}mm)."
                )
            if x < 0 or x + w_op > W:
                warnings.append(
                    f"⚠ [{wall}] Abertura '{shape}' (x={x}, w={w_op}) sai "
                    f"dos limites da parede ({W}mm)."
                )
    return warnings


# ──────────────────────────────────────────────
# generate_3d_box
# ──────────────────────────────────────────────

def generate_3d_box_scad(config: dict) -> str:
    W    = config.get("width", 80)
    D    = config.get("depth", 60)
    H    = config.get("height", 40)
    wt   = config.get("wall_thickness", 2.0)
    bt   = config.get("bottom_thickness", 2.0)
    lid  = config.get("lid_type", "snap")
    cr   = config.get("corner_radius", 3.0)
    lh   = config.get("lid_height", 10)
    tol  = config.get("tolerance", 0.2)

    scad = f"""// ============================================================
// Caixa 3D Paramétrica — Gerada pelo MCP-OpenSCAD
// {W}x{D}x{H}mm | Parede: {wt}mm | Tampa: {lid}
// ============================================================
$fn = 64;

W   = {W};
D   = {D};
H   = {H};
wt  = {wt};
bt  = {bt};
cr  = {cr};
tol = {tol};

module rounded_box(w, d, h, r) {{
    if (r <= 0) {{
        cube([w, d, h]);
    }} else {{
        hull() {{
            for (x = [r, w-r]) for (y = [r, d-r])
                translate([x, y, 0]) cylinder(r=r, h=h);
        }}
    }}
}}

module box_body() {{
    difference() {{
        rounded_box(W, D, H, cr);
        translate([wt, wt, bt])
            rounded_box(W - 2*wt, D - 2*wt, H, max(0.1, cr - wt));
    }}
}}

"""
    if lid == "snap":
        scad += f"""module box_lid() {{
    // Topo
    rounded_box(W, D, bt, cr);
    // Reborda interna
    translate([wt + tol, wt + tol, bt])
        difference() {{
            rounded_box(W - 2*(wt+tol), D - 2*(wt+tol), {lh:.2f}, max(0.1, cr-wt-tol));
            translate([wt, wt, -0.1])
                rounded_box(W - 4*wt - 2*tol, D - 4*wt - 2*tol, {lh+0.2:.2f}, max(0.1, cr-2*wt));
        }}
}}

SHOW_LID = true;
if (SHOW_LID) {{
    box_body();
    color([0.5, 0.7, 1.0, 0.7])
        translate([0, 0, H + 5]) box_lid();
}} else {{
    box_body();
}}
"""
    elif lid == "thread":
        scad += f"""module box_lid() {{
    rounded_box(W, D, bt, cr);
    // Anel de rosca (aprox.) – use BOSL2 para rosca ISO real
    translate([W/2, D/2, bt])
        difference() {{
            cylinder(d=min(W,D) - 2*wt - 2*tol, h={lh:.2f}, $fn=64);
            translate([0,0,-0.1]) cylinder(d=min(W,D) - 4*wt - 2*tol, h={lh+0.2:.2f}, $fn=64);
        }}
}}
box_body();
color([0.5, 0.7, 1.0, 0.7]) translate([0, 0, H + 5]) box_lid();
"""
    else:
        scad += "box_body();\n"

    return scad


# ──────────────────────────────────────────────
# generate_bracket
# ──────────────────────────────────────────────

def generate_bracket_scad(config: dict) -> str:
    W      = config.get("width", 40)
    H      = config.get("height", 40)
    dep    = config.get("depth", 20)
    wall   = config.get("wall", 3.0)
    hole_d = config.get("hole_d", 0)
    mh     = config.get("mount_holes", 4)
    mhd    = config.get("mount_hole_d", 3.2)
    gusset = config.get("gusset", True)
    btype  = config.get("type", "L")

    scad = f"""// ============================================================
// Suporte/Mancal 3D — Gerado pelo MCP-OpenSCAD
// Tipo: {btype} | {W}x{H}x{dep}mm | Parede: {wall}mm
// ============================================================
$fn = 64;
W    = {W};
H    = {H};
dep  = {dep};
wall = {wall};

"""

    if btype == "L":
        gusset_code = ""
        if gusset:
            gusset_code = f"""            // Reforço diagonal
            translate([{W/2 - wall/2:.3f}, 0, 0])
                linear_extrude(wall)
                    polygon([[0, wall], [{dep - wall:.3f}, wall], [wall, {H - wall:.3f}], [0, {H - wall:.3f}]]);
"""
        mount_code = ""
        if mh >= 2:
            m = dep / 4
            mount_code += f"""        translate([{W/4:.3f}, {m:.3f}, -0.1]) cylinder(d={mhd}, h=wall+0.2);
        translate([{3*W/4:.3f}, {m:.3f}, -0.1]) cylinder(d={mhd}, h=wall+0.2);
"""
        if mh == 4:
            m2 = dep * 3 / 4
            mount_code += f"""        translate([{W/4:.3f}, {m2:.3f}, -0.1]) cylinder(d={mhd}, h=wall+0.2);
        translate([{3*W/4:.3f}, {m2:.3f}, -0.1]) cylinder(d={mhd}, h=wall+0.2);
"""
        hole_code = ""
        if hole_d > 0:
            hole_code = f"        translate([{W/2:.3f}, -0.1, {H/2:.3f}]) rotate([-90,0,0]) cylinder(d={hole_d}, h=wall+0.2);\n"

        scad += f"""module bracket_L() {{
    difference() {{
        union() {{
            cube([W, dep, wall]);
            cube([W, wall, H]);
{gusset_code}        }}
{mount_code}{hole_code}    }}
}}
bracket_L();
"""

    elif btype == "U":
        mount_code = ""
        if mh >= 2:
            m = dep / 2
            mount_code = f"""        translate([{W/4:.3f}, {m:.3f}, -0.1]) cylinder(d={mhd}, h=wall+0.2);
        translate([{3*W/4:.3f}, {m:.3f}, -0.1]) cylinder(d={mhd}, h=wall+0.2);
"""
        scad += f"""module bracket_U() {{
    difference() {{
        union() {{
            cube([wall, dep, H]);
            translate([W - wall, 0, 0]) cube([wall, dep, H]);
            cube([W, dep, wall]);
        }}
{mount_code}    }}
}}
bracket_U();
"""
    else:  # flat
        mount_code = ""
        if mh >= 2:
            mount_code += f"        translate([{W/4:.3f}, {dep/4:.3f}, -0.1]) cylinder(d={mhd}, h=wall+0.2);\n"
            mount_code += f"        translate([{3*W/4:.3f}, {dep/4:.3f}, -0.1]) cylinder(d={mhd}, h=wall+0.2);\n"
        if mh == 4:
            mount_code += f"        translate([{W/4:.3f}, {3*dep/4:.3f}, -0.1]) cylinder(d={mhd}, h=wall+0.2);\n"
            mount_code += f"        translate([{3*W/4:.3f}, {3*dep/4:.3f}, -0.1]) cylinder(d={mhd}, h=wall+0.2);\n"
        hole_code = ""
        if hole_d > 0:
            hole_code = f"        translate([{W/2:.3f}, {dep/2:.3f}, -0.1]) cylinder(d={hole_d}, h=wall+0.2);\n"

        scad += f"""module bracket_flat() {{
    difference() {{
        cube([W, dep, wall]);
{mount_code}{hole_code}    }}
}}
bracket_flat();
"""

    return scad


# ──────────────────────────────────────────────
# generate_enclosure
# ──────────────────────────────────────────────

def generate_enclosure_scad(config: dict) -> str:
    W      = config.get("width", 100)
    D      = config.get("depth", 60)
    H      = config.get("height", 30)
    wall   = config.get("wall", 2.5)
    lid    = config.get("lid_type", "snap")
    cr     = config.get("corner_radius", 3)
    conns  = config.get("connectors", [])
    soffs  = config.get("pcb_standoffs", [])
    stoh   = config.get("standoff_h", 5)
    stod   = config.get("standoff_d", 5)
    stoid  = config.get("standoff_hole_d", 2.5)
    tol    = 0.3

    CONN_CATALOG = {
        "usb_a":       (12.5, 6.0),
        "usb_c":       (9.5,  3.5),
        "usb_mini":    (8.5,  4.0),
        "micro_usb":   (8.0,  3.5),
        "barrel_jack": (9.5,  9.5),
        "hdmi":        (16.0, 7.0),
        "ethernet":    (16.0, 14.0),
        "audio_35":    (7.0,  7.0),
        "switch":      (12.0, 12.0),
        "button_12":   (12.0, 12.0),
        "oled_128x64": (28.0, 12.0),
    }

    def conn_cut_front(c):
        """Cutout na parede frontal (plano XZ em Y=0)."""
        ctype = c.get("type", "custom")
        cx, cy = c.get("x", 10), c.get("y", 10)
        cw, ch = CONN_CATALOG.get(ctype, (c.get("w", 10), c.get("h", 10)))
        return f"        translate([{cx:.2f}, -0.1, {wall + cy:.2f}]) cube([{cw:.2f}, {wall + 0.2:.2f}, {ch:.2f}]);"

    def conn_cut_back(c):
        """Cutout na parede traseira (plano XZ em Y=D)."""
        ctype = c.get("type", "custom")
        cx, cy = c.get("x", 10), c.get("y", 10)
        cw, ch = CONN_CATALOG.get(ctype, (c.get("w", 10), c.get("h", 10)))
        return f"        translate([{cx:.2f}, {D - wall - 0.1:.2f}, {wall + cy:.2f}]) cube([{cw:.2f}, {wall + 0.2:.2f}, {ch:.2f}]);"

    def conn_cut_left(c):
        """Cutout na parede esquerda (plano YZ em X=0)."""
        ctype = c.get("type", "custom")
        cx, cy = c.get("x", 10), c.get("y", 10)
        cw, ch = CONN_CATALOG.get(ctype, (c.get("w", 10), c.get("h", 10)))
        return f"        translate([-0.1, {cx:.2f}, {wall + cy:.2f}]) cube([{wall + 0.2:.2f}, {cw:.2f}, {ch:.2f}]);"

    def conn_cut_right(c):
        """Cutout na parede direita (plano YZ em X=W)."""
        ctype = c.get("type", "custom")
        cx, cy = c.get("x", 10), c.get("y", 10)
        cw, ch = CONN_CATALOG.get(ctype, (c.get("w", 10), c.get("h", 10)))
        return f"        translate([{W - wall - 0.1:.2f}, {cx:.2f}, {wall + cy:.2f}]) cube([{wall + 0.2:.2f}, {cw:.2f}, {ch:.2f}]);"

    def conn_cut_top(c):
        """Cutout no topo (plano XY em Z=H)."""
        ctype = c.get("type", "custom")
        cx, cy = c.get("x", 10), c.get("y", 10)
        cw, ch = CONN_CATALOG.get(ctype, (c.get("w", 10), c.get("h", 10)))
        return f"        translate([{cx:.2f}, {cy:.2f}, {H - wall - 0.1:.2f}]) cube([{cw:.2f}, {ch:.2f}, {wall + 0.2:.2f}]);"

    front_cuts = "\n".join(conn_cut_front(c) for c in conns if c.get("wall") == "front")
    back_cuts  = "\n".join(conn_cut_back(c) for c in conns if c.get("wall") == "back")
    left_cuts  = "\n".join(conn_cut_left(c) for c in conns if c.get("wall") == "left")
    right_cuts = "\n".join(conn_cut_right(c) for c in conns if c.get("wall") == "right")
    top_cuts   = "\n".join(conn_cut_top(c) for c in conns if c.get("wall") == "top")

    standoff_code = ""
    for s in soffs:
        sx, sy = s.get("x", 5), s.get("y", 5)
        standoff_code += f"""    translate([{sx:.2f}, {sy:.2f}, {wall:.2f}])
        difference() {{
            cylinder(d={stod:.2f}, h={stoh:.2f});
            translate([0,0,-0.1]) cylinder(d={stoid:.2f}, h={stoh+0.2:.2f});
        }}
"""

    lid_body = ""
    if lid == "snap":
        lid_body = f"""    // Reborda interna snap-fit
    translate([wall + tol, wall + tol, bt])
        difference() {{
            rounded_box(W - 2*(wall+tol), D - 2*(wall+tol), {wall:.2f}, max(0.1, cr-wall-tol));
            translate([wall, wall, -0.1])
                rounded_box(W - 4*wall - 2*tol, D - 4*wall - 2*tol, {wall+0.1:.2f}, max(0.1, cr-2*wall));
        }}"""
    elif lid == "screw":
        lid_body = f"""    // Furos de parafuso M3 nos cantos
    for (x = [cr, W-cr]) for (y = [cr, D-cr])
        translate([x, y, -0.1]) cylinder(d=3.2, h=bt+0.2);"""

    scad = f"""// ============================================================
// Gabinete Eletrônico 3D — Gerado pelo MCP-OpenSCAD
// {W}x{D}x{H}mm | Parede: {wall}mm | Tampa: {lid}
// Conectores: {len(conns)} | Standoffs: {len(soffs)}
// ============================================================
$fn = 64;
W    = {W};
D    = {D};
H    = {H};
wall = {wall};
cr   = {cr};
tol  = {tol};
bt   = {wall};  // espessura da tampa = espessura da parede

module rounded_box(w, d, h, r) {{
    if (r <= 0) {{
        cube([w, d, h]);
    }} else {{
        hull() {{
            for (x = [r, w-r]) for (y = [r, d-r])
                translate([x, y, 0]) cylinder(r=r, h=h);
        }}
    }}
}}

module enclosure_body() {{
    difference() {{
        rounded_box(W, D, H, cr);
        // Vazado interno
        translate([wall, wall, wall])
            rounded_box(W - 2*wall, D - 2*wall, H, max(0.1, cr-wall));
        // Abertura do topo para tampa
        translate([-0.1, -0.1, H - wall - 0.1])
            cube([W+0.2, D+0.2, wall+0.2]);

        // ── Recortes de conectores ────────────────────────────
        // Parede Frontal (Y=0, cortando ao longo de Y)
{front_cuts}
        // Parede Traseira (Y=D)
{back_cuts}
        // Parede Esquerda (X=0)
{left_cuts}
        // Parede Direita (X=W)
{right_cuts}
        // Topo
{top_cuts}
    }}
    // ── Pilares para PCB ──────────────────────────────────────
{standoff_code}}}

module enclosure_lid() {{
    difference() {{
        rounded_box(W, D, bt, cr);
{lid_body}
    }}
}}

SHOW_LID = true;
if (SHOW_LID) {{
    enclosure_body();
    color([0.6, 0.8, 1.0, 0.5])
        translate([0, 0, H + 3]) enclosure_lid();
}} else {{
    enclosure_body();
}}
"""
    return scad


# ──────────────────────────────────────────────
# validate_printability
# ──────────────────────────────────────────────

def validate_printability(config: dict) -> dict:
    """
    Analisa configuração 3D e retorna diagnóstico de printabilidade FDM/resina.
    """
    profile = config.get("profile", "fdm_standard")

    PROFILES = {
        "fdm_standard": {"min_wall": 0.8, "min_detail": 0.4,  "max_overhang": 45, "layer": 0.2, "nozzle": 0.4},
        "fdm_fine":     {"min_wall": 0.4, "min_detail": 0.2,  "max_overhang": 50, "layer": 0.1, "nozzle": 0.2},
        "resin":        {"min_wall": 0.2, "min_detail": 0.05, "max_overhang": 70, "layer": 0.05, "nozzle": None},
    }
    prof = PROFILES.get(profile, PROFILES["fdm_standard"])

    warnings = []
    info     = []
    errors   = []

    wt       = config.get("wall_thickness", 2.0)
    bt       = config.get("bottom_thickness", 2.0)
    H        = config.get("height", 40)
    W        = config.get("width", 80)
    D_dim    = config.get("depth", 60)
    overhang = config.get("overhang_angle", 0)
    lh       = config.get("layer_height", prof["layer"])
    nd       = config.get("nozzle_d", prof.get("nozzle") or 0.4)

    # Parede
    if wt < prof["min_wall"]:
        errors.append(f"❌ Parede muito fina ({wt}mm < mínimo {prof['min_wall']}mm para {profile}).")
    elif wt < prof["min_wall"] * 2:
        warnings.append(f"⚠ Parede fina ({wt}mm). Recomendado >= {prof['min_wall']*2:.1f}mm.")
    else:
        info.append(f"✅ Espessura de parede OK ({wt}mm).")

    # Fundo em múltiplos de layer height
    if lh > 0:
        bt_layers = bt / lh
        if abs(bt_layers - round(bt_layers)) > 0.05:
            warnings.append(f"⚠ Fundo ({bt}mm) não é múltiplo da camada ({lh}mm). Sugerido: {round(bt_layers)*lh:.2f}mm.")
        else:
            info.append(f"✅ Fundo = {int(round(bt_layers))} camadas ({bt}mm / {lh}mm).")

    # Overhang
    if overhang > prof["max_overhang"]:
        errors.append(f"❌ Overhang {overhang}° > máximo sem suporte ({prof['max_overhang']}° para {profile}).")
    elif overhang > prof["max_overhang"] * 0.8:
        warnings.append(f"⚠ Overhang {overhang}° próximo do limite ({prof['max_overhang']}°). Considere suporte.")
    elif overhang > 0:
        info.append(f"✅ Overhang {overhang}° dentro do limite ({prof['max_overhang']}°).")

    # Nozzle vs. parede
    if profile != "resin" and wt < nd * 2:
        warnings.append(f"⚠ Parede ({wt}mm) < 2× bico ({nd}mm). Aumente a parede ou use bico menor.")

    # Proporções
    base_min = min(W, D_dim)
    ratio = H / base_min if base_min > 0 else 0
    if ratio > 5:
        warnings.append(f"⚠ Objeto muito alto ({H}mm) vs. base ({base_min:.0f}mm). Use brim/raft.")
    else:
        info.append(f"✅ Proporção altura/base OK ({ratio:.1f}:1).")

    # Dimensão mínima
    if min(W, D_dim, H) < 5:
        warnings.append(f"⚠ Dimensão mínima ({min(W,D_dim,H):.1f}mm) muito pequena.")

    return {
        "profile":  profile,
        "errors":   errors,
        "warnings": warnings,
        "info":     info,
        "printable": len(errors) == 0,
        "summary": (
            f"{'✅ Imprimível' if not errors else '❌ Não imprimível'} "
            f"({len(errors)} erro(s), {len(warnings)} aviso(s))"
        )
    }


# ──────────────────────────────────────────────
# Registro das ferramentas MCP
# ──────────────────────────────────────────────
@server.list_tools()
async def handle_list_tools() -> list:
    return [
        # Exportação básica
        types.Tool(
            name="render_to_png",
            description="Render OpenSCAD code to a PNG image preview.",
            inputSchema={
                "type": "object",
                "properties": {
                    "variables": {"type": "object", "description": "Optional dict of variables (-D name=value)"},
                    "scad_code": {"type": "string", "description": "The OpenSCAD source code"},
                },
                "required": ["scad_code"]
            }
        ),
        types.Tool(
            name="export_stl",
            description="Export OpenSCAD code to an STL file for 3D printing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "variables": {"type": "object"},
                    "scad_code": {"type": "string"},
                    "output_path": {"type": "string"}
                },
                "required": ["scad_code", "output_path"]
            }
        ),
        types.Tool(
            name="export_3mf",
            description="Export 3D OpenSCAD code to a 3MF file for 3D printing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "variables": {"type": "object"},
                    "scad_code": {"type": "string"},
                    "output_path": {"type": "string"}
                },
                "required": ["scad_code", "output_path"]
            }
        ),
        types.Tool(
            name="export_dxf",
            description="Export 2D OpenSCAD code to a DXF file for laser cutting/CNC.",
            inputSchema={
                "type": "object",
                "properties": {
                    "variables": {"type": "object"},
                    "scad_code": {"type": "string"},
                    "output_path": {"type": "string"}
                },
                "required": ["scad_code", "output_path"]
            }
        ),
        types.Tool(
            name="export_svg",
            description="Export 2D OpenSCAD code to an SVG file for laser cutting/engraving.",
            inputSchema={
                "type": "object",
                "properties": {
                    "variables": {"type": "object"},
                    "scad_code": {"type": "string"},
                    "output_path": {"type": "string"}
                },
                "required": ["scad_code", "output_path"]
            }
        ),
        # check_syntax
        types.Tool(
            name="check_syntax",
            description=(
                "Verifica a sintaxe de código OpenSCAD sem renderizar (rápido). "
                "Retorna erros e warnings do compilador OpenSCAD."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scad_code": {"type": "string", "description": "Código OpenSCAD a validar"}
                },
                "required": ["scad_code"]
            }
        ),
        # Laser tools
        types.Tool(
            name="generate_laser_part",
            description=(
                "Gera projeto completo para corte a laser (caixa/casa/painel com finger joints). "
                "Exporta SCAD + SVG + DXF + preview PNG. Suporta aberturas (porta/janela)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": "material_thickness, kerf, width, depth, height, fingers, openings[]",
                        "required": ["width", "depth", "height"]
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["config", "output_dir", "project_name"]
            }
        ),
        types.Tool(
            name="validate_laser_config",
            description=(
                "Valida config de laser cutting: detecta dentes sob aberturas, "
                "aberturas fora dos limites, e outros problemas geométricos."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {"type": "object", "description": "Mesmo formato do generate_laser_part"}
                },
                "required": ["config"]
            }
        ),
        types.Tool(
            name="generate_box",
            description=(
                "Gera caixa retangular para laser cutting com tampa (snap/slide/none). "
                "Suporta divisórias internas X e Y, kerf compensation. "
                "Exporta SCAD + SVG + DXF + preview PNG + estimativa de material."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "material_thickness, kerf, width, depth, height, fingers, "
                            "lid_type (snap|slide|none), lid_clearance, dividers_x, dividers_y"
                        ),
                        "required": ["width", "depth", "height"]
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["config", "output_dir", "project_name"]
            }
        ),
        types.Tool(
            name="generate_kerf_test",
            description=(
                "Gera placa de calibração de kerf para laser. "
                "Produz pinos macho + fendas fêmea com kerf variado. "
                "Exporta SVG + DXF + preview PNG."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": "material_thickness, kerf_min, kerf_max, kerf_step, test_length"
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["output_dir", "project_name"]
            }
        ),
        types.Tool(
            name="generate_finger_test",
            description=(
                "Gera pente de teste de finger joints com múltiplos offsets. "
                "Pares macho/fêmea para calibrar encaixe por material e máquina."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": "material_thickness, offset_min, offset_max, offset_step, finger_width, finger_count, height"
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["output_dir", "project_name"]
            }
        ),
        types.Tool(
            name="estimate_material_use",
            description=(
                "Calcula área total de material e aproveitamento da chapa para um projeto laser. "
                "Retorna lista de peças, área cm², percentual de uso e chapas necessárias."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {"type": "object", "description": "Config do generate_box ou generate_laser_part"},
                    "sheet_width":  {"type": "number", "description": "Largura da chapa mm (default: 600)"},
                    "sheet_height": {"type": "number", "description": "Altura da chapa mm (default: 400)"}
                },
                "required": ["config"]
            }
        ),
        # 3D printing tools
        types.Tool(
            name="generate_3d_box",
            description=(
                "Gera caixa sólida paramétrica para impressão 3D com tampa snap-fit ou rosqueável. "
                "Cantos arredondados, tolerâncias configuráveis. Exporta SCAD + STL + preview PNG."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "width, depth, height, wall_thickness, bottom_thickness, "
                            "lid_type (snap|thread|none), corner_radius, lid_height, tolerance"
                        ),
                        "required": ["width", "depth", "height"]
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["config", "output_dir", "project_name"]
            }
        ),
        types.Tool(
            name="generate_bracket",
            description=(
                "Gera suporte/mancal paramétrico para impressão 3D. "
                "Tipos: L (ângulo), U (canal), flat (plano). "
                "Furos de montagem configuráveis e reforço diagonal (gusset)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "type (L|U|flat), width, height, depth, wall, "
                            "hole_d, mount_holes (0/2/4), mount_hole_d, gusset"
                        ),
                        "required": ["width", "height", "depth"]
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["config", "output_dir", "project_name"]
            }
        ),
        types.Tool(
            name="generate_enclosure",
            description=(
                "Gera gabinete eletrônico paramétrico para impressão 3D. "
                "Catálogo de conectores: USB-A/C, HDMI, Ethernet, barrel jack, OLED, switch. "
                "Suporta pilares para PCB (standoffs), tampa snap ou parafuso."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "width, depth, height, wall, lid_type (snap|screw), "
                            "corner_radius, connectors [{wall, type, x, y}], "
                            "pcb_standoffs [{x,y}], standoff_h, standoff_d, standoff_hole_d"
                        ),
                        "required": ["width", "depth", "height"]
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["config", "output_dir", "project_name"]
            }
        ),
        types.Tool(
            name="validate_printability",
            description=(
                "Valida imprimibilidade de objeto 3D em FDM ou resina. "
                "Verifica paredes, overhang, múltiplos de layer height, proporções. "
                "Perfis: fdm_standard, fdm_fine, resin."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "wall_thickness, bottom_thickness, height, width, depth, "
                            "overhang_angle, layer_height, nozzle_d, "
                            "profile (fdm_standard|fdm_fine|resin)"
                        )
                    }
                },
                "required": ["config"]
            }
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list:

    # ── Exportação básica ──────────────────────────────────────────
    if name in ["render_to_png", "export_stl", "export_3mf", "export_dxf", "export_svg"]:
        if not arguments or "scad_code" not in arguments:
            raise ValueError("Missing 'scad_code' argument")

        scad_code = arguments["scad_code"]
        variables = arguments.get("variables", {})
        extra_args = []
        for k, v in variables.items():
            if isinstance(v, str):
                extra_args.extend(["-D", f'{k}="{v}"'])
            elif isinstance(v, bool):
                extra_args.extend(["-D", f'{k}={"true" if v else "false"}'])
            else:
                extra_args.extend(["-D", f"{k}={v}"])

        if name == "render_to_png":
            try:
                out_path, _ = run_openscad(scad_code, "png", ["--autocenter", "--viewall"] + extra_args)
                with open(out_path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
                os.remove(out_path)
                return [
                    types.TextContent(type="text", text="Rendered successfully."),
                    types.ImageContent(type="image", data=img_data, mimeType="image/png")
                ]
            except Exception as e:
                return [types.TextContent(type="text", text=str(e))]
        else:
            if "output_path" not in arguments:
                raise ValueError("Missing 'output_path' argument")
            output_path = arguments["output_path"]
            ext = name.split("_")[1]
            try:
                out_path, _ = run_openscad(scad_code, ext, extra_args)
                shutil.move(out_path, output_path)
                return [types.TextContent(type="text", text=f"Exported successfully to {output_path}")]
            except Exception as e:
                return [types.TextContent(type="text", text=str(e))]

    elif name == "check_syntax":
        if not arguments or "scad_code" not in arguments:
            raise ValueError("Missing 'scad_code' argument")
        is_valid, msg = check_scad_syntax(arguments["scad_code"])
        return [types.TextContent(type="text", text=msg)]

    elif name == "validate_laser_config":
        if not arguments or "config" not in arguments:
            raise ValueError("Missing 'config'")
        warns = validate_config(arguments["config"])
        msg = "Problemas detectados:\n" + "\n".join(warns) if warns else "✅ Configuração válida — nenhum problema detectado."
        return [types.TextContent(type="text", text=msg)]

    elif name == "generate_laser_part":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "laser_part")
        os.makedirs(output_dir, exist_ok=True)

        warns     = validate_config(config)
        scad_code = generate_laser_scad(config)
        scad_path = os.path.join(output_dir, f"{project_name}.scad")
        with open(scad_path, "w") as f:
            f.write(scad_code)

        results = [f"📄 SCAD gerado: {scad_path}"]
        if warns:
            results.append("⚠ Avisos:\n" + "\n".join(warns))

        scad_2d = scad_code.replace('RENDER_MODE = "3d"', 'RENDER_MODE = "2d"')

        for fmt, label in [("svg", "🖼 SVG"), ("dxf", "📐 DXF")]:
            try:
                dst = os.path.join(output_dir, f"{project_name}.{fmt}")
                p, _ = run_openscad(scad_2d, fmt)
                shutil.move(p, dst)
                results.append(f"{label} gerado: {dst}")
            except Exception as e:
                results.append(f"❌ Erro {fmt.upper()}: {e}")

        try:
            out_path, _ = run_openscad(scad_code, "png", ["--autocenter", "--viewall"])
            with open(out_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            os.remove(out_path)
            return [types.TextContent(type="text", text="\n".join(results)),
                    types.ImageContent(type="image", data=img_data, mimeType="image/png")]
        except Exception as e:
            results.append(f"❌ Erro PNG: {e}")
            return [types.TextContent(type="text", text="\n".join(results))]

    elif name == "generate_box":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "box")
        os.makedirs(output_dir, exist_ok=True)

        warns     = validate_box_config(config)
        scad_code = generate_box_scad(config)
        scad_path = os.path.join(output_dir, f"{project_name}.scad")
        with open(scad_path, "w") as f:
            f.write(scad_code)

        results = [f"📦 Caixa gerada: {scad_path}"]
        if warns:
            results.append("⚠ Avisos:\n" + "\n".join(warns))

        sw  = arguments.get("sheet_width", 600)
        sh  = arguments.get("sheet_height", 400)
        est = estimate_material_use(config, sw, sh)
        results.append(
            f"\n📊 Material ({sw}x{sh}mm):\n"
            + "\n".join(f"  {p['name']} x{p['qty']}: {p['w']:.0f}×{p['h']:.0f}mm" for p in est["pieces"])
            + f"\n  Área: {est['total_area_cm2']} cm² | Uso: {est['usage_percent']}% | Chapas: {est['sheets_needed']}"
        )

        scad_2d = scad_code.replace('RENDER_MODE = "3d"', 'RENDER_MODE = "2d"')
        for fmt, label in [("svg", "🖼 SVG"), ("dxf", "📐 DXF")]:
            try:
                dst = os.path.join(output_dir, f"{project_name}.{fmt}")
                p, _ = run_openscad(scad_2d, fmt)
                shutil.move(p, dst)
                results.append(f"{label} gerado: {dst}")
            except Exception as e:
                results.append(f"❌ Erro {fmt.upper()}: {e}")

        try:
            out_path, _ = run_openscad(scad_code, "png", ["--autocenter", "--viewall"])
            with open(out_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            os.remove(out_path)
            return [types.TextContent(type="text", text="\n".join(results)),
                    types.ImageContent(type="image", data=img_data, mimeType="image/png")]
        except Exception as e:
            results.append(f"❌ Erro PNG: {e}")
            return [types.TextContent(type="text", text="\n".join(results))]

    elif name == "generate_kerf_test":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "kerf_test")
        os.makedirs(output_dir, exist_ok=True)

        scad_code = generate_kerf_test_scad(config)
        scad_path = os.path.join(output_dir, f"{project_name}.scad")
        with open(scad_path, "w") as f:
            f.write(scad_code)

        results = [f"🔬 Placa de kerf gerada: {scad_path}"]
        for fmt, label in [("svg", "🖼 SVG"), ("dxf", "📐 DXF")]:
            try:
                dst = os.path.join(output_dir, f"{project_name}.{fmt}")
                p, _ = run_openscad(scad_code, fmt)
                shutil.move(p, dst)
                results.append(f"{label} gerado: {dst}")
            except Exception as e:
                results.append(f"❌ Erro {fmt.upper()}: {e}")

        try:
            out_path, _ = run_openscad(scad_code, "png", ["--autocenter", "--viewall", "--projection=ortho"])
            with open(out_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            os.remove(out_path)
            results.append("📷 Preview gerado.")
            return [types.TextContent(type="text", text="\n".join(results)),
                    types.ImageContent(type="image", data=img_data, mimeType="image/png")]
        except Exception as e:
            results.append(f"❌ Erro PNG: {e}")
            return [types.TextContent(type="text", text="\n".join(results))]

    elif name == "generate_finger_test":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "finger_test")
        os.makedirs(output_dir, exist_ok=True)

        scad_code = generate_finger_test_scad(config)
        scad_path = os.path.join(output_dir, f"{project_name}.scad")
        with open(scad_path, "w") as f:
            f.write(scad_code)

        results = [f"🔧 Pente de finger joints gerado: {scad_path}"]
        for fmt, label in [("svg", "🖼 SVG"), ("dxf", "📐 DXF")]:
            try:
                dst = os.path.join(output_dir, f"{project_name}.{fmt}")
                p, _ = run_openscad(scad_code, fmt)
                shutil.move(p, dst)
                results.append(f"{label} gerado: {dst}")
            except Exception as e:
                results.append(f"❌ Erro {fmt.upper()}: {e}")

        try:
            out_path, _ = run_openscad(scad_code, "png", ["--autocenter", "--viewall", "--projection=ortho"])
            with open(out_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            os.remove(out_path)
            results.append("📷 Preview gerado.")
            return [types.TextContent(type="text", text="\n".join(results)),
                    types.ImageContent(type="image", data=img_data, mimeType="image/png")]
        except Exception as e:
            results.append(f"❌ Erro PNG: {e}")
            return [types.TextContent(type="text", text="\n".join(results))]

    elif name == "estimate_material_use":
        if not arguments or "config" not in arguments:
            raise ValueError("Missing 'config'")
        config = arguments["config"]
        sw = arguments.get("sheet_width", 600)
        sh = arguments.get("sheet_height", 400)
        r  = estimate_material_use(config, sw, sh)
        lines = [
            f"📊 Estimativa — Chapa {r['sheet_w_mm']}×{r['sheet_h_mm']}mm",
            "Peças:",
        ]
        for p in r["pieces"]:
            area = p["qty"] * p["w"] * p["h"] / 100
            lines.append(f"  • {p['name']} ×{p['qty']}: {p['w']:.0f}×{p['h']:.0f}mm = {area:.1f} cm²")
        lines += [
            f"\nÁrea total:         {r['total_area_cm2']} cm²",
            f"Área da chapa:      {r['sheet_area_mm2']/100:.1f} cm²",
            f"Aproveitamento:     {r['usage_percent']}%",
            f"Chapas necessárias: {r['sheets_needed']}",
        ]
        return [types.TextContent(type="text", text="\n".join(lines))]

    elif name == "generate_3d_box":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "box_3d")
        os.makedirs(output_dir, exist_ok=True)

        scad_code = generate_3d_box_scad(config)
        scad_path = os.path.join(output_dir, f"{project_name}.scad")
        with open(scad_path, "w") as f:
            f.write(scad_code)

        results = [f"📦 Caixa 3D gerada: {scad_path}"]
        try:
            stl_path = os.path.join(output_dir, f"{project_name}.stl")
            p, _ = run_openscad(scad_code, "stl")
            shutil.move(p, stl_path)
            results.append(f"📐 STL gerado: {stl_path}")
        except Exception as e:
            results.append(f"❌ Erro STL: {e}")

        try:
            out_path, _ = run_openscad(scad_code, "png", ["--autocenter", "--viewall"])
            with open(out_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            os.remove(out_path)
            return [types.TextContent(type="text", text="\n".join(results)),
                    types.ImageContent(type="image", data=img_data, mimeType="image/png")]
        except Exception as e:
            results.append(f"❌ Erro PNG: {e}")
            return [types.TextContent(type="text", text="\n".join(results))]

    elif name == "generate_bracket":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "bracket")
        os.makedirs(output_dir, exist_ok=True)

        scad_code = generate_bracket_scad(config)
        scad_path = os.path.join(output_dir, f"{project_name}.scad")
        with open(scad_path, "w") as f:
            f.write(scad_code)

        results = [f"🔩 Suporte gerado: {scad_path}"]
        try:
            stl_path = os.path.join(output_dir, f"{project_name}.stl")
            p, _ = run_openscad(scad_code, "stl")
            shutil.move(p, stl_path)
            results.append(f"📐 STL gerado: {stl_path}")
        except Exception as e:
            results.append(f"❌ Erro STL: {e}")

        try:
            out_path, _ = run_openscad(scad_code, "png", ["--autocenter", "--viewall"])
            with open(out_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            os.remove(out_path)
            return [types.TextContent(type="text", text="\n".join(results)),
                    types.ImageContent(type="image", data=img_data, mimeType="image/png")]
        except Exception as e:
            results.append(f"❌ Erro PNG: {e}")
            return [types.TextContent(type="text", text="\n".join(results))]

    elif name == "generate_enclosure":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "enclosure")
        os.makedirs(output_dir, exist_ok=True)

        scad_code = generate_enclosure_scad(config)
        scad_path = os.path.join(output_dir, f"{project_name}.scad")
        with open(scad_path, "w") as f:
            f.write(scad_code)

        results = [
            f"🖥 Gabinete gerado: {scad_path}",
            f"  Conectores: {len(config.get('connectors', []))} | Standoffs: {len(config.get('pcb_standoffs', []))}",
        ]
        try:
            stl_path = os.path.join(output_dir, f"{project_name}.stl")
            p, _ = run_openscad(scad_code, "stl")
            shutil.move(p, stl_path)
            results.append(f"📐 STL gerado: {stl_path}")
        except Exception as e:
            results.append(f"❌ Erro STL: {e}")

        try:
            out_path, _ = run_openscad(scad_code, "png", ["--autocenter", "--viewall"])
            with open(out_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            os.remove(out_path)
            return [types.TextContent(type="text", text="\n".join(results)),
                    types.ImageContent(type="image", data=img_data, mimeType="image/png")]
        except Exception as e:
            results.append(f"❌ Erro PNG: {e}")
            return [types.TextContent(type="text", text="\n".join(results))]

    elif name == "validate_printability":
        if not arguments or "config" not in arguments:
            raise ValueError("Missing 'config'")
        r = validate_printability(arguments["config"])
        lines = [
            f"🖨 Validação de Imprimibilidade — Perfil: {r['profile']}",
            f"Resultado: {r['summary']}",
            "",
        ]
        if r["errors"]:
            lines.append("❌ Erros:")
            lines.extend(f"  {e}" for e in r["errors"])
            lines.append("")
        if r["warnings"]:
            lines.append("⚠ Avisos:")
            lines.extend(f"  {w}" for w in r["warnings"])
            lines.append("")
        if r["info"]:
            lines.append("ℹ Info:")
            lines.extend(f"  {i}" for i in r["info"])
        return [types.TextContent(type="text", text="\n".join(lines))]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-openscad",
                server_version="0.3.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
