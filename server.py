import os
import re
import subprocess
import tempfile
import asyncio
import math
import shutil
import base64
import struct
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

server = Server("mcp-openscad")

# ──────────────────────────────────────────────
# Diretivas de Segurança e Sanitização de Caminhos
# ──────────────────────────────────────────────
BANNED_KEYWORDS = [
    "firearm", "gun", "pistol", "rifle", "silencer", "receiver", "trigger",
    "bullet", "explosive", "grenade", "bomb", "missile", "rocket body", "rocket_body",
    "propellant", "combustion chamber", "combustion_chamber"
]

def verify_safety_guidelines(scad_code: str, project_name: str = ""):
    text = f"{scad_code} {project_name}".lower()
    if "nozzle" in text and ("rocket" in text or "propellant" in text or "thruster" in text):
        raise ValueError("Safety violation: Generation of rocket nozzles/propellants is prohibited.")
    for b in BANNED_KEYWORDS:
        if b in text:
            raise ValueError(f"Safety violation: Prohibited keyword '{b}' detected.")
    # Block OpenSCAD file-reading functions in custom code
    import re as _re
    if _re.search(r'(?<![_a-zA-Z0-9])import\s*\(|(?<![_a-zA-Z0-9])surface\s*\(', scad_code, _re.IGNORECASE):
        raise ValueError("Safety violation: OpenSCAD file-reading functions (import, surface) are prohibited.")

def validate_output_path(path: str) -> str:
    resolved = os.path.abspath(path)
    env_paths = os.environ.get("MCP_OPENSCAD_ALLOWED_PATHS", "")
    if env_paths:
        allowed_prefixes = [p.strip() for p in env_paths.split(":") if p.strip()]
    else:
        allowed_prefixes = [os.path.expanduser("~"), "/tmp", "/var/tmp"]
    if not any(resolved.startswith(p) for p in allowed_prefixes):
        raise ValueError(f"Access denied: Path '{resolved}' is outside allowed directories.")
    return resolved

def safe_output_path(output_dir: str, project_name: str) -> tuple[str, str]:
    # Sanitize project_name to avoid traversal
    safe_project_name = os.path.basename(project_name)
    safe_project_name = safe_project_name.replace("..", "").replace("/", "").replace("\\", "")
    if not safe_project_name or safe_project_name in (".", ".."):
        safe_project_name = "project"
    
    # Clean output_dir
    norm_dir = validate_output_path(output_dir)
    return norm_dir, safe_project_name

def validate_config_parameters(tool_name: str, config: dict) -> None:
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a dictionary.")

    # Helper to assert type and positivity
    def assert_positive(name, val):
        if val is None:
            raise ValueError(f"Parameter '{name}' is missing.")
        try:
            num = float(val)
        except (ValueError, TypeError):
            raise ValueError(f"Parameter '{name}' must be numeric.")
        if not math.isfinite(num):
            raise ValueError(f"Parameter '{name}' must be a finite number (got {val}).")
        if num <= 0:
            raise ValueError(f"Parameter '{name}' must be strictly positive.")
        return num

    def assert_non_negative(name, val):
        if val is None:
            raise ValueError(f"Parameter '{name}' is missing.")
        try:
            num = float(val)
        except (ValueError, TypeError):
            raise ValueError(f"Parameter '{name}' must be numeric.")
        if not math.isfinite(num):
            raise ValueError(f"Parameter '{name}' must be a finite number (got {val}).")
        if num < 0:
            raise ValueError(f"Parameter '{name}' must be non-negative.")
        return num

    def assert_integer(name, val, min_val=1):
        if val is None:
            raise ValueError(f"Parameter '{name}' is missing.")
        try:
            num = int(val)
        except (ValueError, TypeError):
            raise ValueError(f"Parameter '{name}' must be an integer.")
        if num < min_val:
            raise ValueError(f"Parameter '{name}' must be at least {min_val}.")
        return num

    if tool_name == "generate_laser_part":
        t = assert_positive("material_thickness", config.get("material_thickness", 3))
        assert_non_negative("kerf", config.get("kerf", 0.2))
        W = assert_positive("width", config.get("width", 100))
        D = assert_positive("depth", config.get("depth", 100))
        H = assert_positive("height", config.get("height", 80))
        assert_integer("fingers", config.get("fingers", 5), 1)
        if W <= 2 * t:
            raise ValueError(f"Width ({W}mm) must be greater than twice the material thickness ({2*t}mm).")
        if D <= 2 * t:
            raise ValueError(f"Depth ({D}mm) must be greater than twice the material thickness ({2*t}mm).")

        for op in config.get("openings", []):
            if not isinstance(op, dict):
                raise ValueError("Each opening must be a dictionary.")
            wall = op.get("wall")
            if wall not in ("front", "back", "left", "right"):
                raise ValueError(f"Opening wall '{wall}' is invalid. Must be 'front', 'back', 'left', or 'right'.")
            shape = op.get("shape", "rect")
            if shape not in ("rect", "circle"):
                raise ValueError(f"Opening shape '{shape}' is invalid. Must be 'rect' or 'circle'.")
            if shape == "rect":
                assert_non_negative("opening x", op.get("x", 0))
                assert_non_negative("opening y", op.get("y", 0))
                assert_positive("opening w", op.get("w", 30))
                assert_positive("opening h", op.get("h", 40))
            else:
                assert_non_negative("opening cx", op.get("cx", 50))
                assert_non_negative("opening cy", op.get("cy", 40))
                assert_positive("opening d", op.get("d", 20))

    elif tool_name == "generate_box":
        t = assert_positive("material_thickness", config.get("material_thickness", 3))
        assert_non_negative("kerf", config.get("kerf", 0.2))
        W = assert_positive("width", config.get("width", 100))
        D = assert_positive("depth", config.get("depth", 80))
        H = assert_positive("height", config.get("height", 50))
        assert_integer("fingers", config.get("fingers", 5), 1)
        assert_non_negative("dividers_x", config.get("dividers_x", 0))
        assert_non_negative("dividers_y", config.get("dividers_y", 0))
        lid_type = config.get("lid_type", "snap")
        if lid_type not in ("snap", "slide", "none"):
            raise ValueError(f"Lid type '{lid_type}' is invalid. Must be 'snap', 'slide', or 'none'.")
        assert_non_negative("lid_clearance", config.get("lid_clearance", 0.3))
        if W <= 2 * t:
            raise ValueError(f"Width ({W}mm) must be greater than twice the material thickness ({2*t}mm).")
        if D <= 2 * t:
            raise ValueError(f"Depth ({D}mm) must be greater than twice the material thickness ({2*t}mm).")

    elif tool_name == "generate_kerf_test":
        assert_positive("material_thickness", config.get("material_thickness", 3))
        k_min = assert_non_negative("kerf_min", config.get("kerf_min", 0.0))
        k_max = assert_non_negative("kerf_max", config.get("kerf_max", 0.5))
        assert_positive("kerf_step", config.get("kerf_step", 0.05))
        assert_positive("test_length", config.get("test_length", 30))
        if k_min > k_max:
            raise ValueError("kerf_min cannot be greater than kerf_max.")

    elif tool_name == "generate_finger_test":
        assert_positive("material_thickness", config.get("material_thickness", 3))
        fw = assert_positive("finger_width", config.get("finger_width", 5))
        assert_integer("finger_count", config.get("finger_count", 5), 1)
        assert_positive("height", config.get("height", 30))
        off_min = config.get("offset_min", -0.2)
        off_max = config.get("offset_max", 0.2)
        off_step = config.get("offset_step", 0.05)
        try:
            off_min = float(off_min)
            off_max = float(off_max)
            off_step = float(off_step)
        except (ValueError, TypeError):
            raise ValueError("Offsets must be numeric.")
        if off_min > off_max:
            raise ValueError("offset_min cannot be greater than offset_max.")
        if off_step <= 0:
            raise ValueError("offset_step must be greater than 0.")
        if fw + off_min <= 0:
            raise ValueError(f"offset_min ({off_min}) is too negative for finger_width ({fw}). Resulting tab width is non-positive.")
        if fw - off_max <= 0:
            raise ValueError(f"offset_max ({off_max}) is too large for finger_width ({fw}). Resulting slot width is non-positive.")

    elif tool_name == "generate_3d_box":
        W = assert_positive("width", config.get("width", 80))
        D = assert_positive("depth", config.get("depth", 60))
        H = assert_positive("height", config.get("height", 40))
        wt = assert_positive("wall_thickness", config.get("wall_thickness", 2.0))
        bt = assert_positive("bottom_thickness", config.get("bottom_thickness", 2.0))
        lid_type = config.get("lid_type", "snap")
        if lid_type not in ("snap", "thread", "none"):
            raise ValueError(f"Lid type '{lid_type}' is invalid. Must be 'snap', 'thread', or 'none'.")
        cr = assert_non_negative("corner_radius", config.get("corner_radius", 3.0))
        assert_non_negative("lid_height", config.get("lid_height", 10))
        assert_non_negative("tolerance", config.get("tolerance", 0.2))
        if W <= 2 * wt:
            raise ValueError("width must be greater than twice the wall_thickness.")
        if D <= 2 * wt:
            raise ValueError("depth must be greater than twice the wall_thickness.")
        if H <= bt:
            raise ValueError("height must be greater than bottom_thickness.")
        if cr > min(W, D) / 2:
            raise ValueError("corner_radius cannot be greater than half of width or depth.")

    elif tool_name == "generate_bracket":
        W = assert_positive("width", config.get("width", 40))
        H = assert_positive("height", config.get("height", 40))
        dep = assert_positive("depth", config.get("depth", 20))
        wall = assert_positive("wall", config.get("wall", 3.0))
        assert_non_negative("hole_d", config.get("hole_d", 0))
        mh = config.get("mount_holes", 4)
        if mh not in (0, 2, 4):
            raise ValueError("mount_holes must be 0, 2, or 4.")
        assert_non_negative("mount_hole_d", config.get("mount_hole_d", 3.2))
        btype = config.get("type", "L")
        if btype not in ("L", "U", "flat"):
            raise ValueError("Bracket type must be 'L', 'U', or 'flat'.")
        if btype == "U" and W <= 2 * wall:
            raise ValueError("width must be greater than twice the wall thickness for U brackets.")
        if btype == "L" and config.get("gusset", True):
            if dep <= wall or H <= wall:
                raise ValueError("Wall thickness exceeds depth/height limits for L bracket gusset.")

    elif tool_name == "generate_enclosure":
        W = assert_positive("width", config.get("width", 100))
        D = assert_positive("depth", config.get("depth", 60))
        H = assert_positive("height", config.get("height", 30))
        wall = assert_positive("wall", config.get("wall", 2.5))
        lid_type = config.get("lid_type", "snap")
        if lid_type not in ("snap", "screw"):
            raise ValueError("Lid type must be 'snap' or 'screw'.")
        cr = assert_non_negative("corner_radius", config.get("corner_radius", 3))
        if cr > min(W, D) / 2:
            raise ValueError("corner_radius cannot be greater than half of width or depth.")
        if lid_type == "screw" and cr < 1.6:
            raise ValueError("corner_radius must be at least 1.6 for screw lids to accommodate screw holes.")
        if W <= 2 * wall or D <= 2 * wall or H <= 2 * wall:
            raise ValueError("Dimensions must be greater than twice the wall thickness.")
        
        stod = assert_positive("standoff_d", config.get("standoff_d", 5))
        stoid = assert_positive("standoff_hole_d", config.get("standoff_hole_d", 2.5))
        if stod <= stoid:
            raise ValueError("standoff_d must be greater than standoff_hole_d.")
        assert_positive("standoff_h", config.get("standoff_h", 5))
        
        for s in config.get("pcb_standoffs", []):
            if not isinstance(s, dict):
                raise ValueError("Each pcb_standoff must be a dictionary.")
            sx = assert_non_negative("standoff x", s.get("x"))
            sy = assert_non_negative("standoff y", s.get("y"))
            if not (wall + stod/2 <= sx <= W - wall - stod/2):
                raise ValueError(f"Standoff x coordinate ({sx}mm) must be inside the walls.")
            if not (wall + stod/2 <= sy <= D - wall - stod/2):
                raise ValueError(f"Standoff y coordinate ({sy}mm) must be inside the walls.")

    elif tool_name == "generate_tolerance_test":
        assert_positive("base_width", config.get("base_width", 80))
        assert_positive("base_depth", config.get("base_depth", 60))
        assert_positive("base_height", config.get("base_height", 3))
        assert_positive("pin_height", config.get("pin_height", 15))
        assert_positive("pin_d", config.get("pin_d", 10))
        assert_positive("hole_d", config.get("hole_d", 10))
        tol_min = config.get("tol_min", -0.3)
        tol_max = config.get("tol_max", 0.3)
        tol_step = config.get("tol_step", 0.1)
        assert_non_negative("gap", config.get("gap", 5))
        try:
            tol_min = float(tol_min)
            tol_max = float(tol_max)
            tol_step = float(tol_step)
        except (ValueError, TypeError):
            raise ValueError("Tolerance bounds must be numeric.")
        if tol_min > tol_max:
            raise ValueError("tol_min cannot be greater than tol_max.")
        if tol_step <= 0:
            raise ValueError("tol_step must be greater than 0.")

    elif tool_name == "generate_bed_level_test":
        bx = assert_positive("bed_x", config.get("bed_x", 220))
        by = assert_positive("bed_y", config.get("bed_y", 220))
        dd = assert_positive("disc_d", config.get("disc_d", 30))
        assert_positive("disc_h", config.get("disc_h", 0.2))
        assert_integer("grid_cols", config.get("grid_cols", 5), 1)
        assert_integer("grid_rows", config.get("grid_rows", 5), 1)
        assert_non_negative("skirt_w", config.get("skirt_w", 1))
        if bx < dd + 10 or by < dd + 10:
            raise ValueError("Bed dimensions must be larger than disc diameter + margins.")

    elif tool_name == "generate_retraction_test":
        assert_positive("tower_d", config.get("tower_d", 10))
        assert_positive("tower_h", config.get("tower_h", 80))
        assert_integer("tower_count", config.get("tower_count", 5), 1)
        assert_positive("tower_gap", config.get("tower_gap", 20))
        assert_positive("base_h", config.get("base_h", 2))
        assert_non_negative("base_pad", config.get("base_pad", 5))

    elif tool_name == "generate_living_hinge":
        assert_positive("width", config.get("width", 100))
        assert_positive("height", config.get("height", 60))
        assert_positive("material_thickness", config.get("material_thickness", 3))
        assert_non_negative("kerf", config.get("kerf", 0.2))
        assert_positive("cut_length", config.get("cut_length", 15))
        assert_positive("cut_gap", config.get("cut_gap", 2))
        assert_positive("row_spacing", config.get("row_spacing", 3))
        assert_non_negative("margin", config.get("margin", 5))
        pattern = config.get("pattern", "straight")
        if pattern not in ("straight", "serpentine", "cross"):
            raise ValueError("Pattern must be 'straight', 'serpentine', or 'cross'.")

    elif tool_name == "generate_dogbone":
        W = assert_positive("width", config.get("width", 50))
        H = assert_positive("height", config.get("height", 30))
        assert_positive("depth", config.get("depth", 5))
        tool_d = assert_positive("tool_d", config.get("tool_d", 3.175))
        assert_positive("material_thickness", config.get("material_thickness", 6))
        style = config.get("corner_style", "dogbone")
        if style not in ("dogbone", "tbone_h", "tbone_v"):
            raise ValueError("Corner style must be 'dogbone', 'tbone_h', or 'tbone_v'.")
        if W < tool_d or H < tool_d:
            raise ValueError("Pocket dimensions must be at least the tool diameter.")

    elif tool_name == "suggest_orientation":
        assert_positive("width", config.get("width", 80))
        assert_positive("depth", config.get("depth", 60))
        assert_positive("height", config.get("height", 40))

    elif tool_name == "generate_assembly":
        for piece in config.get("pieces", []):
            if not isinstance(piece, dict):
                raise ValueError("Each piece must be a dictionary.")
            name = piece.get("name")
            if not name or not isinstance(name, str):
                raise ValueError("Piece name must be a non-empty string.")
            ptype = piece.get("type", "box")
            if ptype not in ("box", "cylinder", "custom"):
                raise ValueError("Piece type must be 'box', 'cylinder', or 'custom'.")
            assert_positive("piece width (w)", piece.get("w", 10))
            assert_positive("piece depth (d)", piece.get("d", 10))
            assert_positive("piece height (h)", piece.get("h", 10))
            assert_integer("piece qty", piece.get("qty", 1), 1)
            
            for prop in ("translate", "rotate", "color"):
                val = piece.get(prop)
                if val is not None:
                    if not isinstance(val, (list, tuple)) or len(val) != 3:
                        raise ValueError(f"Piece property '{prop}' must be a list/tuple of 3 elements.")
                    for item in val:
                        try:
                            float(item)
                        except (ValueError, TypeError):
                            raise ValueError(f"Elements of piece property '{prop}' must be numeric.")
                    if prop == "color":
                        for item in val:
                            if not (0 <= float(item) <= 1):
                                raise ValueError("Color channel values must be between 0 and 1.")

    elif tool_name == "generate_cnc_toolpath_hints":
        assert_positive("material_thickness", config.get("material_thickness", 6))
        assert_positive("tool_d", config.get("tool_d", 3.175))
        assert_integer("tool_flutes", config.get("tool_flutes", 2), 1)

# ──────────────────────────────────────────────
# TempFilePath class for automatic temp file deletion on GC
# ──────────────────────────────────────────────
class TempFilePath(str):
    def __del__(self):
        try:
            if os.path.exists(self):
                os.remove(self)
        except Exception:
            pass

# ──────────────────────────────────────────────
# Utilitário interno: roda openscad
# ──────────────────────────────────────────────
RENDER_TIMEOUT_MIN = 5.0
RENDER_TIMEOUT_MAX = 900.0
RENDER_TIMEOUT_DEFAULT = 60.0


def _clamp_timeout(timeout_s) -> float:
    """Normaliza e limita timeout_s ao intervalo [RENDER_TIMEOUT_MIN, RENDER_TIMEOUT_MAX]."""
    try:
        t = float(timeout_s)
    except (TypeError, ValueError):
        t = RENDER_TIMEOUT_DEFAULT
    if not math.isfinite(t):
        t = RENDER_TIMEOUT_DEFAULT
    return max(RENDER_TIMEOUT_MIN, min(RENDER_TIMEOUT_MAX, t))


async def run_openscad(
    scad_code: str,
    output_ext: str,
    export_args: list[str] | None = None,
    timeout_s: float = RENDER_TIMEOUT_DEFAULT,
) -> tuple:
    verify_safety_guidelines(scad_code)
    if export_args is None:
        export_args = []
    timeout_s = _clamp_timeout(timeout_s)

    with tempfile.NamedTemporaryFile(suffix=".scad", delete=False, mode='w') as f:
        f.write(scad_code)
        scad_path = f.name

    out_path = os.path.splitext(scad_path)[0] + f".{output_ext}"

    cmd = ["openscad", "-o", out_path] + export_args + [scad_path]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except Exception:
                    pass
            raise RuntimeError(f"OpenSCAD Error: Execution timed out after {timeout_s:g} seconds.")
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        if proc.returncode != 0 and not os.path.exists(out_path):
            raise RuntimeError(f"OpenSCAD Error:\n{stderr}")
        return TempFilePath(out_path), stdout + stderr
    except RuntimeError:
        raise
    except Exception as e:
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass
        raise
    finally:
        if os.path.exists(scad_path):
            try:
                os.remove(scad_path)
            except Exception:
                pass


# ──────────────────────────────────────────────
# check_syntax: valida sintaxe sem renderizar
# ──────────────────────────────────────────────
async def check_scad_syntax(scad_code: str) -> tuple:
    """
    Verifica sintaxe do código SCAD usando openscad.
    Retorna (is_valid, message).
    """
    verify_safety_guidelines(scad_code)
    with tempfile.NamedTemporaryFile(suffix=".scad", delete=False, mode='w') as f:
        f.write(scad_code)
        scad_path = f.name

    try:
        proc = await asyncio.create_subprocess_exec(
            "openscad", "--export-format", "svg", "-o", os.devnull, scad_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=15)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return False, "❌ Timeout ao verificar sintaxe."
        stderr = stderr_b.decode("utf-8", errors="replace").strip()
        errors = [ln for ln in stderr.splitlines() if "ERROR" in ln or "error" in ln.lower()]
        if errors:
            return False, "Erros encontrados:\n" + "\n".join(errors)
        warnings = [ln for ln in stderr.splitlines() if "WARNING" in ln or "ECHO" in ln]
        if warnings:
            return True, "✅ Sintaxe válida (com avisos):\n" + "\n".join(warnings)
        return True, "✅ Sintaxe válida — nenhum problema encontrado."
    finally:
        if os.path.exists(scad_path):
            try:
                os.remove(scad_path)
            except Exception:
                pass


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
    kerf = max(0.0, min(kerf, t - 0.1))
    slot = t - kerf
    gap  = 15

    def finger_loop_with_exclusions(total_len, n_fingers, exclusions, axis='x',
                                    is_tab=True, depth=None, y_override=None):
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
                    y_val = f"{-depth:.4f}" if y_override is None else y_override
                    lines.append(f"        translate([{x0:.4f}, {y_val}]) square([{x1-x0:.4f}, {depth:.4f}]);")
                else:
                    y_val = "0" if y_override is None else y_override
                    lines.append(f"        translate([{x0:.4f}, {y_val}]) square([{x1-x0:.4f}, {slot:.4f}]);")
            else:
                if is_tab:
                    x_val = f"{-depth:.4f}" if y_override is None else y_override
                    lines.append(f"        translate([{x_val}, {x0:.4f}]) square([{depth:.4f}, {x1-x0:.4f}]);")
                else:
                    x_val = "0" if y_override is None else y_override
                    lines.append(f"        translate([{x_val}, {x0:.4f}]) square([{slot:.4f}, {x1-x0:.4f}]);")
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
    floor_b_slots_translated = finger_loop_with_exclusions(W, N, back_excl, axis='x', is_tab=False, y_override="D-slot")

    front_openings_scad = "\n".join(opening_scad(op) for op in front_ops)
    back_openings_scad  = "\n".join(opening_scad(op) for op in back_ops)

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
    kerf = max(0.0, min(kerf, t - 0.1))
    slot = t - kerf
    gap  = 15

    # Ensure N is odd for symmetrical joints
    if N % 2 == 0:
        N += 1

    def tabs_bottom(length, n, is_tab=True, y_override=None):
        """Dentes/fendas na borda inferior (Y=0)."""
        fw = length / n
        lines = []
        for i in range(0, n, 2):
            x0 = i * fw + (0 if i == 0 else kerf / 2)
            x1 = (i + 1) * fw - (0 if i == n - 1 else kerf / 2)
            if is_tab:
                y_val = f"{-t:.3f}" if y_override is None else y_override
                lines.append(f"    translate([{x0:.3f}, {y_val}]) square([{x1-x0:.3f}, {t:.3f}]);")
            else:
                y_val = "0" if y_override is None else y_override
                lines.append(f"    translate([{x0:.3f}, {y_val}]) square([{x1-x0:.3f}, {slot:.3f}]);")
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
    back_slots_floor = tabs_bottom(W, N, is_tab=False, y_override=f"{D - slot:.3f}")

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
    N    = max(1, config.get("fingers", 5))
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
# generate_living_hinge
# ──────────────────────────────────────────────

def generate_living_hinge_scad(config: dict) -> str:
    """
    Gera padrão de living hinge para corte a laser.
    Suporta padrões: straight, serpentine, cross.
    Saída 2D para exportação SVG/DXF.
    """
    W       = max(10, config.get("width", 100))
    H       = max(10, config.get("height", 60))
    t       = config.get("material_thickness", 3)
    kerf    = config.get("kerf", 0.2)
    pattern = config.get("pattern", "straight")
    cut_len = max(1, config.get("cut_length", 15))
    cut_gap = max(0.5, config.get("cut_gap", 2))
    row_sp  = max(0.5, config.get("row_spacing", 3))
    margin  = max(0, config.get("margin", 5))

    # Clamp kerf
    kerf = max(0.05, min(kerf, t - 0.1 if t > 0.1 else 0.05))

    # Valid patterns
    if pattern not in ("straight", "serpentine", "cross"):
        pattern = "straight"

    inner_w = W - 2 * margin
    inner_h = H - 2 * margin

    # Guard: if inner area too small, just return base rectangle
    if inner_w < cut_len or inner_h < cut_len:
        return f"""// Living Hinge — área interna insuficiente
square([{W}, {H}]);
"""

    scad = f"""// ============================================================
// Living Hinge — Gerado pelo MCP-OpenSCAD
// {W}x{H}mm | Material: {t}mm | Kerf: {kerf}mm | Padrão: {pattern}
// cut_length: {cut_len}mm | cut_gap: {cut_gap}mm | row_spacing: {row_sp}mm
// ============================================================

"""

    if pattern == "straight":
        # Parallel rows of cuts, alternating offset by half cut_length + half cut_gap
        cut_lines = []
        y = margin
        row_idx = 0
        while y + kerf <= H - margin:
            # Offset for alternating rows
            x_offset = margin if row_idx % 2 == 0 else margin + (cut_len + cut_gap) / 2
            x = x_offset
            while x + cut_len <= W - margin:
                cut_lines.append(
                    f"        translate([{x:.4f}, {y:.4f}]) square([{cut_len:.4f}, {kerf:.4f}]);"
                )
                x += cut_len + cut_gap
            y += row_sp
            row_idx += 1

        scad += f"""difference() {{
    square([{W}, {H}]);
    // Cortes straight
{chr(10).join(cut_lines)}
}}
"""

    elif pattern == "serpentine":
        # Serpentine: long cuts alternating left/right with short bridges
        cut_lines = []
        y = margin
        row_idx = 0
        while y + kerf <= H - margin:
            if row_idx % 2 == 0:
                # Cut from left, leave bridge on right
                x0 = margin
                x1 = W - margin - cut_gap
                cut_lines.append(
                    f"        translate([{x0:.4f}, {y:.4f}]) square([{x1 - x0:.4f}, {kerf:.4f}]);"
                )
            else:
                # Cut from right, leave bridge on left
                x0 = margin + cut_gap
                x1 = W - margin
                cut_lines.append(
                    f"        translate([{x0:.4f}, {y:.4f}]) square([{x1 - x0:.4f}, {kerf:.4f}]);"
                )
            y += row_sp
            row_idx += 1

        scad += f"""difference() {{
    square([{W}, {H}]);
    // Cortes serpentine
{chr(10).join(cut_lines)}
}}
"""

    elif pattern == "cross":
        # Cross-hatch: cuts in both X and Y directions
        cut_lines = []
        # Horizontal cuts
        y = margin
        row_idx = 0
        while y + kerf <= H - margin:
            x_offset = margin if row_idx % 2 == 0 else margin + (cut_len + cut_gap) / 2
            x = x_offset
            while x + cut_len <= W - margin:
                cut_lines.append(
                    f"        translate([{x:.4f}, {y:.4f}]) square([{cut_len:.4f}, {kerf:.4f}]);"
                )
                x += cut_len + cut_gap
            y += row_sp
            row_idx += 1

        # Vertical cuts
        x = margin
        col_idx = 0
        while x + kerf <= W - margin:
            y_offset = margin if col_idx % 2 == 0 else margin + (cut_len + cut_gap) / 2
            y = y_offset
            while y + cut_len <= H - margin:
                cut_lines.append(
                    f"        translate([{x:.4f}, {y:.4f}]) square([{kerf:.4f}, {cut_len:.4f}]);"
                )
                y += cut_len + cut_gap
            x += row_sp
            col_idx += 1

        scad += f"""difference() {{
    square([{W}, {H}]);
    // Cortes cross-hatch
{chr(10).join(cut_lines)}
}}
"""

    return scad


# ──────────────────────────────────────────────
# generate_dogbone
# ──────────────────────────────────────────────

def generate_dogbone_scad(config: dict) -> str:
    """
    Gera pocket retangular com compensação dogbone/T-bone nos cantos
    para fresagem CNC. Saída 2D para exportação SVG/DXF.
    Inclui layout de teste com múltiplos tamanhos de pocket.
    """
    W      = max(5, config.get("width", 50))
    H      = max(5, config.get("height", 30))
    depth  = config.get("depth", 5)
    tool_d = max(0.1, config.get("tool_d", 3.175))
    style  = config.get("corner_style", "dogbone")
    mat_t  = config.get("material_thickness", 6)

    # Valid styles
    if style not in ("dogbone", "tbone_h", "tbone_v"):
        style = "dogbone"

    r = tool_d / 2
    # Diagonal offset for dogbone: circle center at 45° into the corner
    diag = r * math.sqrt(2) / 2

    def corner_circles(w, h, st):
        """Gera círculos de compensação nos 4 cantos do pocket."""
        lines = []
        corners = [
            (0, 0),       # bottom-left
            (w, 0),       # bottom-right
            (w, h),       # top-right
            (0, h),       # top-left
        ]
        # Direction vectors pointing diagonally into the rectangle
        diag_dirs = [
            (diag, diag),    # bottom-left -> into
            (-diag, diag),   # bottom-right -> into
            (-diag, -diag),  # top-right -> into
            (diag, -diag),   # top-left -> into
        ]
        # T-bone horizontal: offset along X axis
        tbone_h_dirs = [
            (r, 0),   (-r, 0),   (-r, 0),   (r, 0),
        ]
        # T-bone vertical: offset along Y axis
        tbone_v_dirs = [
            (0, r),   (0, r),   (0, -r),   (0, -r),
        ]

        if st == "dogbone":
            dirs = diag_dirs
        elif st == "tbone_h":
            dirs = tbone_h_dirs
        else:  # tbone_v
            dirs = tbone_v_dirs

        for (cx, cy), (dx, dy) in zip(corners, dirs):
            lines.append(
                f"        translate([{cx + dx:.4f}, {cy + dy:.4f}]) circle(r={r:.4f}, $fn=32);"
            )
        return "\n".join(lines)

    def pocket_module(name, w, h, st):
        """Gera um módulo de pocket com compensação."""
        circles = corner_circles(w, h, st)
        return f"""module {name}() {{
    union() {{
        square([{w:.4f}, {h:.4f}]);
        // Compensação {st} nos cantos (tool_d={tool_d}mm)
{circles}
    }}
}}
"""

    scad = f"""// ============================================================
// Dogbone/T-bone Pocket — Gerado pelo MCP-OpenSCAD
// Pocket: {W}x{H}mm | Profundidade: {depth}mm | Fresa: Ø{tool_d}mm
// Estilo: {style} | Material: {mat_t}mm
// ============================================================
$fn = 32;

"""

    # Main pocket module
    scad += pocket_module("main_pocket", W, H, style)

    # Test layout with multiple pocket sizes
    gap = 10
    test_sizes = [
        (W, H, "full_size"),
        (W * 0.75, H * 0.75, "size_75pct"),
        (W * 0.5, H * 0.5, "size_50pct"),
    ]

    for tw, th, tname in test_sizes:
        tw = max(tool_d * 2, tw)
        th = max(tool_d * 2, th)
        scad += pocket_module(f"pocket_{tname}", tw, th, style)

    # Layout
    scad += f"""// ── Layout de teste ──────────────────────────────────────────
module test_layout() {{
"""
    x_off = 0
    for tw, th, tname in test_sizes:
        tw = max(tool_d * 2, tw)
        th = max(tool_d * 2, th)
        scad += f"    translate([{x_off:.4f}, 0]) pocket_{tname}();\n"
        x_off += tw + gap

    scad += """}\n\n"""

    scad += f"""// Pocket principal
main_pocket();

// Layout de teste abaixo
translate([0, {H + gap:.4f}]) test_layout();
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
# generate_tolerance_test
# ──────────────────────────────────────────────

def generate_tolerance_test_scad(config: dict) -> str:
    """
    Gera placa de teste de tolerância para calibração de impressão 3D.
    Pares de pinos macho e furos fêmea com tolerâncias variadas.
    """
    base_w   = config.get("base_width", 80)
    base_d   = config.get("base_depth", 60)
    base_h   = config.get("base_height", 3)
    pin_h    = config.get("pin_height", 15)
    pin_d    = config.get("pin_d", 10)
    hole_d   = config.get("hole_d", 10)
    tol_min  = config.get("tol_min", -0.3)
    tol_max  = config.get("tol_max", 0.3)
    tol_step = config.get("tol_step", 0.1)
    gap      = config.get("gap", 5)

    # Guard against infinite loop
    if tol_step <= 0:
        tol_step = 0.1

    tols = []
    t = tol_min
    while t <= tol_max + 1e-9:
        tols.append(round(t, 4))
        t += tol_step

    n = len(tols)
    # Compute required base width: each pair needs pin_d + gap + hole_d + gap
    pair_w = pin_d + gap + hole_d + gap
    min_w  = gap + n * pair_w
    base_w = max(base_w, min_w)

    # Compute required base depth: pin_d + gap + label space
    min_d  = pin_d + gap * 2 + 10
    base_d = max(base_d, min_d)

    scad = f"""// ============================================================
// Placa de Teste de Tolerância — MCP-OpenSCAD
// Tolerância: {tol_min} a {tol_max}mm | Passo: {tol_step}mm
// ============================================================
// Como usar:
//   1. Imprima esta placa
//   2. Tente encaixar cada pino no furo correspondente
//   3. O par com encaixe justo = tolerância correta da sua impressora
// ============================================================
$fn = 64;

"""

    # Base plate
    scad += f"""// ── Base ─────────────────────────────────────────────────────
difference() {{
    cube([{base_w:.3f}, {base_d:.3f}, {base_h:.3f}]);
"""

    # Female holes (subtracted from base)
    for i, tol in enumerate(tols):
        hx = gap + i * pair_w + pin_d + gap + hole_d / 2
        hy = base_d / 2
        effective_hole_d = hole_d - tol
        scad += f"""    // Furo fêmea tol={tol:+.2f}mm (d={effective_hole_d:.3f}mm)
    translate([{hx:.3f}, {hy:.3f}, -0.1])
        cylinder(d={effective_hole_d:.3f}, h={base_h + 0.2:.3f});
"""

    scad += "}\n\n"

    # Male pins (on top of base)
    for i, tol in enumerate(tols):
        px = gap + i * pair_w + pin_d / 2
        py = base_d / 2
        effective_pin_d = pin_d + tol
        scad += f"""// Pino macho tol={tol:+.2f}mm (d={effective_pin_d:.3f}mm)
translate([{px:.3f}, {py:.3f}, {base_h:.3f}])
    cylinder(d={effective_pin_d:.3f}, h={pin_h:.3f});
"""

    # Labels
    for i, tol in enumerate(tols):
        lx = gap + i * pair_w + pair_w / 2
        ly = 2
        scad += f"""// Label tol={tol:+.2f}mm
translate([{lx:.3f}, {ly:.3f}, {base_h - 0.5:.3f}])
    linear_extrude(1)
        text("{tol:+.1f}", size=4, halign="center", font="Liberation Sans:style=Bold");
"""

    return scad


# ──────────────────────────────────────────────
# generate_bed_level_test
# ──────────────────────────────────────────────

def generate_bed_level_test_scad(config: dict) -> str:
    """
    Gera padrão de teste de nivelamento de mesa para impressão 3D.
    Grade de discos finos distribuídos pela área da mesa.
    """
    bed_x     = config.get("bed_x", 220)
    bed_y     = config.get("bed_y", 220)
    disc_d    = config.get("disc_d", 30)
    disc_h    = config.get("disc_h", 0.2)
    grid_cols = max(1, config.get("grid_cols", 5))
    grid_rows = max(1, config.get("grid_rows", 5))
    skirt_w   = config.get("skirt_w", 1)

    scad = f"""// ============================================================
// Teste de Nivelamento de Mesa — MCP-OpenSCAD
// Mesa: {bed_x}x{bed_y}mm | Discos: {grid_cols}x{grid_rows} | d={disc_d}mm h={disc_h}mm
// ============================================================
// Como usar:
//   1. Imprima este padrão na sua mesa
//   2. Observe a adesão e espessura de cada disco
//   3. Discos mal aderidos = mesa desnivelada naquela região
// ============================================================
$fn = 64;

"""

    # Calculate spacing
    margin_x = disc_d / 2 + 5
    margin_y = disc_d / 2 + 5
    if grid_cols > 1:
        step_x = (bed_x - 2 * margin_x) / (grid_cols - 1)
    else:
        step_x = 0
    if grid_rows > 1:
        step_y = (bed_y - 2 * margin_y) / (grid_rows - 1)
    else:
        step_y = 0

    for row in range(grid_rows):
        for col in range(grid_cols):
            cx = margin_x + col * step_x
            cy = margin_y + row * step_y

            # Skirt ring around disc
            if skirt_w > 0:
                outer_d = disc_d + 2 * skirt_w
                scad += f"""// Disco [{col},{row}] com saia
translate([{cx:.3f}, {cy:.3f}, 0]) {{
    cylinder(d={disc_d:.3f}, h={disc_h:.3f});
    difference() {{
        cylinder(d={outer_d:.3f}, h={disc_h:.3f});
        translate([0, 0, -0.1]) cylinder(d={disc_d:.3f}, h={disc_h + 0.2:.3f});
    }}
}}
"""
            else:
                scad += f"""// Disco [{col},{row}]
translate([{cx:.3f}, {cy:.3f}, 0])
    cylinder(d={disc_d:.3f}, h={disc_h:.3f});
"""

    return scad


# ──────────────────────────────────────────────
# generate_retraction_test
# ──────────────────────────────────────────────

def generate_retraction_test_scad(config: dict) -> str:
    """
    Gera torre de teste de retração/stringing para impressão 3D.
    Cilindros finos espaçados em base comum — stringing entre torres
    indica retração insuficiente.
    """
    tower_d     = config.get("tower_d", 10)
    tower_h     = config.get("tower_h", 80)
    tower_count = max(1, config.get("tower_count", 5))
    tower_gap   = config.get("tower_gap", 20)
    base_h      = config.get("base_h", 2)
    base_pad    = config.get("base_pad", 5)

    total_w = tower_count * tower_d + (tower_count - 1) * tower_gap + 2 * base_pad
    total_d = tower_d + 2 * base_pad

    scad = f"""// ============================================================
// Torre de Teste de Retração — MCP-OpenSCAD
// Torres: {tower_count} x d={tower_d}mm h={tower_h}mm | Gap: {tower_gap}mm
// ============================================================
// Como usar:
//   1. Imprima esta peça
//   2. Observe os fios (strings) entre as torres
//   3. Muita stringing = aumente retração ou diminua temperatura
// ============================================================
$fn = 64;

// ── Base ─────────────────────────────────────────────────────
cube([{total_w:.3f}, {total_d:.3f}, {base_h:.3f}]);

"""

    for i in range(tower_count):
        cx = base_pad + tower_d / 2 + i * (tower_d + tower_gap)
        cy = total_d / 2
        scad += f"""// Torre {i+1}
translate([{cx:.3f}, {cy:.3f}, {base_h:.3f}])
    cylinder(d={tower_d:.3f}, h={tower_h:.3f});
"""

    return scad


# ──────────────────────────────────────────────
# suggest_orientation (v0.4.2)
# ──────────────────────────────────────────────

def suggest_orientation(config: dict) -> dict:
    """
    Sugere a melhor orientação de impressão 3D baseado na geometria.
    Analisa proporções, overhangs potenciais e área de contato com a cama.
    """
    W = config.get("width", 80)
    D = config.get("depth", 60)
    H = config.get("height", 40)
    has_holes_xy = config.get("has_holes_xy", False)
    has_holes_xz = config.get("has_holes_xz", False)
    has_holes_yz = config.get("has_holes_yz", False)
    has_flat_bottom = config.get("has_flat_bottom", True)
    detail_on_top = config.get("detail_on_top", False)
    profile = config.get("profile", "fdm_standard")

    PROFILES = {
        "fdm_standard": {"max_overhang": 45, "support_cost": "alto"},
        "fdm_fine":     {"max_overhang": 50, "support_cost": "alto"},
        "resin":        {"max_overhang": 70, "support_cost": "baixo"},
    }
    prof = PROFILES.get(profile, PROFILES["fdm_standard"])

    orientations = []

    # Orientation 1: Original (Z up)
    base_area_z = W * D
    score_z = 100
    notes_z = []
    if has_flat_bottom:
        score_z += 20
        notes_z.append("✅ Base plana — boa aderência à cama")
    if H > max(W, D) * 3:
        score_z -= 30
        notes_z.append("⚠ Muito alto — risco de tombar, use brim/raft")
    if has_holes_xy:
        score_z += 10
        notes_z.append("✅ Furos no plano XY imprimem sem suporte")
    if has_holes_xz or has_holes_yz:
        score_z -= 15
        notes_z.append("⚠ Furos laterais podem precisar de suporte")
    if detail_on_top:
        score_z += 5
        notes_z.append("✅ Detalhes no topo — boa resolução nessa orientação")
    orientations.append({
        "name": "Original (Z ↑)",
        "rotation": [0, 0, 0],
        "base_area_mm2": round(base_area_z, 1),
        "height_mm": H,
        "score": score_z,
        "notes": notes_z,
    })

    # Orientation 2: Side (X up — rotate 90° around Y)
    base_area_x = D * H
    score_x = 100
    notes_x = []
    if base_area_x > base_area_z:
        score_x += 10
        notes_x.append("✅ Maior área de contato com a cama")
    elif base_area_x < base_area_z * 0.5:
        score_x -= 20
        notes_x.append("⚠ Área de base pequena — instável")
    if has_holes_yz:
        score_x += 10
        notes_x.append("✅ Furos YZ imprimem sem suporte nesta orientação")
    if W > max(D, H) * 3:
        score_x -= 25
        notes_x.append("⚠ Muito alto nesta orientação")
    orientations.append({
        "name": "Lado (X ↑, rotação 90° em Y)",
        "rotation": [0, 90, 0],
        "base_area_mm2": round(base_area_x, 1),
        "height_mm": W,
        "score": score_x,
        "notes": notes_x,
    })

    # Orientation 3: Front (Y up — rotate -90° around X)
    base_area_y = W * H
    score_y = 100
    notes_y = []
    if base_area_y > base_area_z:
        score_y += 10
        notes_y.append("✅ Maior área de contato com a cama")
    elif base_area_y < base_area_z * 0.5:
        score_y -= 20
        notes_y.append("⚠ Área de base pequena — instável")
    if has_holes_xz:
        score_y += 10
        notes_y.append("✅ Furos XZ imprimem sem suporte nesta orientação")
    if D > max(W, H) * 3:
        score_y -= 25
        notes_y.append("⚠ Muito alto nesta orientação")
    orientations.append({
        "name": "Frente (Y ↑, rotação -90° em X)",
        "rotation": [-90, 0, 0],
        "base_area_mm2": round(base_area_y, 1),
        "height_mm": D,
        "score": score_y,
        "notes": notes_y,
    })

    orientations.sort(key=lambda o: o["score"], reverse=True)
    best = orientations[0]

    return {
        "recommended": best,
        "all_orientations": orientations,
        "profile": profile,
        "summary": (
            f"🔄 Orientação recomendada: {best['name']} "
            f"(score: {best['score']}, base: {best['base_area_mm2']}mm², "
            f"altura: {best['height_mm']}mm)"
        )
    }


# ──────────────────────────────────────────────
# generate_assembly (v0.4.5)
# ──────────────────────────────────────────────

def generate_assembly_scad(config: dict) -> tuple:
    """
    Gera projeto multi-peça com posicionamento e BOM automático.
    Retorna (scad_assembly, piece_scads_dict, bom_markdown).
    """
    pieces = config.get("pieces", [])
    project_name = config.get("project_name", "assembly")
    explode_distance = max(0, config.get("explode_distance", 20))

    if not pieces:
        pieces = [
            {"name": "base", "type": "box", "w": 80, "d": 60, "h": 3,
             "color": [0.9, 0.8, 0.6]},
            {"name": "wall_front", "type": "box", "w": 80, "d": 3, "h": 30,
             "translate": [0, 0, 3], "color": [0.8, 0.6, 0.4]},
            {"name": "wall_back", "type": "box", "w": 80, "d": 3, "h": 30,
             "translate": [0, 57, 3], "color": [0.8, 0.5, 0.4]},
            {"name": "wall_left", "type": "box", "w": 3, "d": 54, "h": 30,
             "translate": [0, 3, 3], "color": [0.7, 0.5, 0.5]},
            {"name": "wall_right", "type": "box", "w": 3, "d": 54, "h": 30,
             "translate": [77, 3, 3], "color": [0.7, 0.4, 0.6]},
        ]

    piece_modules = []
    piece_positions = []
    bom_rows = []

    for i, p in enumerate(pieces):
        name = p.get("name", f"piece_{i}")
        ptype = p.get("type", "box")
        w = p.get("w", 10)
        d = p.get("d", 10)
        h = p.get("h", 10)
        translate = p.get("translate", [0, 0, 0])
        rotate_val = p.get("rotate", [0, 0, 0])
        color = p.get("color", [0.8, 0.8, 0.8])
        material = p.get("material", "PLA")
        qty = p.get("qty", 1)

        if ptype == "cylinder":
            shape = f"cylinder(d={w}, h={h}, $fn=64)"
        elif ptype == "custom":
            shape = p.get("scad", "cube([10,10,10])")
        else:
            shape = f"cube([{w}, {d}, {h}])"

        safe_name = name.replace(' ', '_').replace('-', '_')
        module_name = f"piece_{safe_name}"
        piece_modules.append(f"module {module_name}() {{\n    {shape};\n}}")

        piece_positions.append({
            "module": module_name,
            "translate": translate,
            "rotate": rotate_val,
            "color": color,
            "name": name,
        })

        if ptype == "cylinder":
            # Volume do cilindro: π × r² × h  (r = w/2 = diâmetro/2)
            vol_mm3 = math.pi * (w / 2) ** 2 * h
        elif ptype == "custom":
            # Volume desconhecido para SCAD customizado — estimativa como caixa
            vol_mm3 = w * d * h
        else:
            # Volume da caixa: w × d × h
            vol_mm3 = w * d * h
        bom_rows.append({
            "name": name, "type": ptype,
            "dimensions": f"{w}×{d}×{h}mm",
            "material": material, "qty": qty,
            "volume_cm3": round(vol_mm3 / 1000, 2),
        })

    # Assembly SCAD
    scad = f"""// ============================================================
// Assembly — {project_name}
// Gerado pelo MCP-OpenSCAD
// Peças: {len(pieces)}
// ============================================================
$fn = 64;

"""
    for mod in piece_modules:
        scad += mod + "\n\n"

    # Assembled module
    scad += "module assembled() {\n"
    for pp in piece_positions:
        tx, ty, tz = pp["translate"]
        rx, ry, rz = pp["rotate"]
        r, g, b = pp["color"][0], pp["color"][1], pp["color"][2]
        scad += f"    // {pp['name']}\n"
        scad += f"    color([{r}, {g}, {b}])\n"
        scad += f"        translate([{tx}, {ty}, {tz}])\n"
        scad += f"            rotate([{rx}, {ry}, {rz}])\n"
        scad += f"                {pp['module']}();\n"
    scad += "}\n\n"

    # Exploded module
    scad += "module exploded() {\n"
    for j, pp in enumerate(piece_positions):
        tx, ty, tz = pp["translate"]
        rx, ry, rz = pp["rotate"]
        r, g, b = pp["color"][0], pp["color"][1], pp["color"][2]
        ex = j * explode_distance
        scad += f"    // {pp['name']} (exploded)\n"
        scad += f"    color([{r}, {g}, {b}])\n"
        scad += f"        translate([{tx}, {ty}, {tz + ex}])\n"
        scad += f"            rotate([{rx}, {ry}, {rz}])\n"
        scad += f"                {pp['module']}();\n"
    scad += "}\n\n"

    scad += """SHOW_EXPLODED = false;
if (SHOW_EXPLODED) {
    exploded();
} else {
    assembled();
}
"""

    # Individual piece SCADs
    piece_scads = {}
    for pp, mod in zip(piece_positions, piece_modules):
        piece_scads[pp["name"]] = f"// Peça: {pp['name']}\n$fn = 64;\n\n{mod}\n\n{pp['module']}();\n"

    # BOM markdown
    bom_md = f"# BOM — {project_name}\n\n"
    bom_md += "| # | Peça | Tipo | Dimensões | Material | Qtd | Volume |\n"
    bom_md += "|---|------|------|-----------|----------|-----|--------|\n"
    total_vol = 0
    for i, row in enumerate(bom_rows):
        bom_md += (f"| {i+1} | {row['name']} | {row['type']} | "
                   f"{row['dimensions']} | {row['material']} | "
                   f"{row['qty']} | {row['volume_cm3']} cm³ |\n")
        total_vol += row["volume_cm3"] * row["qty"]
    bom_md += f"\n**Volume total:** {total_vol:.2f} cm³\n"
    bom_md += f"**Peças:** {sum(r['qty'] for r in bom_rows)}\n"

    return scad, piece_scads, bom_md


# ──────────────────────────────────────────────
# generate_cnc_toolpath_hints (v0.5.1)
# ──────────────────────────────────────────────

# Database de materiais com parâmetros CNC recomendados
CNC_MATERIALS = {
    "mdf": {
        "name": "MDF",
        "feed_rate_mm_min": 1500, "plunge_rate_mm_min": 500,
        "spindle_rpm": 18000, "doc_pct": 0.5,
        "notes": "Material uniforme, bom para iniciantes. Gera pó fino — use aspiração."
    },
    "plywood": {
        "name": "Compensado/Plywood",
        "feed_rate_mm_min": 1200, "plunge_rate_mm_min": 400,
        "spindle_rpm": 16000, "doc_pct": 0.4,
        "notes": "Camadas cruzadas podem causar tear-out. Use fresa upcut para corte, downcut para acabamento."
    },
    "acrylic": {
        "name": "Acrílico",
        "feed_rate_mm_min": 800, "plunge_rate_mm_min": 300,
        "spindle_rpm": 14000, "doc_pct": 0.3,
        "notes": "Não deixe o material derreter. Use fresa de 1 flauta (O-flute). Corte com refrigeração."
    },
    "hardwood": {
        "name": "Madeira dura (carvalho, nogueira)",
        "feed_rate_mm_min": 1000, "plunge_rate_mm_min": 350,
        "spindle_rpm": 16000, "doc_pct": 0.35,
        "notes": "Corte a favor do veio quando possível. Use fresas de 2 flautas."
    },
    "softwood": {
        "name": "Madeira macia (pinus, cedro)",
        "feed_rate_mm_min": 1800, "plunge_rate_mm_min": 600,
        "spindle_rpm": 18000, "doc_pct": 0.6,
        "notes": "Material suave — cuidado com bordas felpudas. Use fresa downcut para acabamento limpo."
    },
    "aluminum": {
        "name": "Alumínio",
        "feed_rate_mm_min": 500, "plunge_rate_mm_min": 150,
        "spindle_rpm": 10000, "doc_pct": 0.15,
        "notes": "Use lubrificação (WD-40 ou fluido de corte). Fresa de 1 flauta. Limpe cavacos frequentemente."
    },
    "foam": {
        "name": "Espuma (EVA, EPS, XPS)",
        "feed_rate_mm_min": 3000, "plunge_rate_mm_min": 1500,
        "spindle_rpm": 12000, "doc_pct": 1.0,
        "notes": "Pode cortar em passe único. Use fresa reta ou lâmina. Velocidade alta, RPM baixo."
    },
    "hdpe": {
        "name": "HDPE / Polietileno",
        "feed_rate_mm_min": 1000, "plunge_rate_mm_min": 400,
        "spindle_rpm": 12000, "doc_pct": 0.4,
        "notes": "Material flexível — fixe bem. Use fresa de 1 flauta (O-flute). Evite acúmulo de calor."
    },
}

def generate_cnc_toolpath_hints(config: dict) -> dict:
    """
    Gera sugestões de parâmetros CNC: feed rate, spindle, DOC, passes.
    """
    material = config.get("material", "mdf").lower()
    thickness = config.get("material_thickness", 6)
    tool_d = config.get("tool_d", 3.175)  # 1/8" endmill
    tool_flutes = config.get("tool_flutes", 2)
    cut_type = config.get("cut_type", "profile")  # profile, pocket, drill, engrave
    finishing_pass = config.get("finishing_pass", True)

    mat = CNC_MATERIALS.get(material, CNC_MATERIALS["mdf"])

    # Calcular DOC (depth of cut) por passe
    doc = tool_d * mat["doc_pct"]
    num_passes = max(1, math.ceil(thickness / doc))
    actual_doc = thickness / num_passes

    # Stepover para pockets (% do diâmetro)
    if cut_type == "pocket":
        stepover_pct = 0.40  # 40% para pocket
    elif cut_type == "engrave":
        stepover_pct = 0.10
    else:
        stepover_pct = 1.0  # profile = 100% (single pass)
    stepover_mm = tool_d * stepover_pct

    # Chip load
    chip_load = mat["feed_rate_mm_min"] / (mat["spindle_rpm"] * tool_flutes)

    # Tabs para perfil
    tabs = []
    if cut_type == "profile":
        tab_width = max(3, tool_d * 2)
        tab_height = min(thickness * 0.3, 2.0)
        tabs = [{
            "width_mm": round(tab_width, 1),
            "height_mm": round(tab_height, 1),
            "note": "Adicione tabs a cada ~50mm do perímetro para manter peça fixada"
        }]

    result = {
        "material": mat["name"],
        "tool_diameter_mm": tool_d,
        "tool_flutes": tool_flutes,
        "cut_type": cut_type,
        "parameters": {
            "feed_rate_mm_min": mat["feed_rate_mm_min"],
            "plunge_rate_mm_min": mat["plunge_rate_mm_min"],
            "spindle_rpm": mat["spindle_rpm"],
            "depth_per_pass_mm": round(actual_doc, 2),
            "num_passes": num_passes,
            "stepover_mm": round(stepover_mm, 2),
            "stepover_pct": round(stepover_pct * 100, 0),
            "chip_load_mm": round(chip_load, 4),
        },
        "tabs": tabs,
        "finishing": None,
        "notes": mat["notes"],
        "safety": [
            "🥽 Use óculos de proteção",
            "🔊 Use proteção auricular",
            "💨 Use aspiração/exaustão para pó",
            "🔒 Verifique fixação da peça antes de iniciar",
            "⚡ Não toque na fresa após o corte (quente)",
        ],
    }

    if finishing_pass and cut_type in ("profile", "pocket"):
        result["finishing"] = {
            "feed_rate_mm_min": int(mat["feed_rate_mm_min"] * 0.6),
            "depth_per_pass_mm": round(actual_doc * 0.3, 2),
            "offset_mm": 0.2,
            "note": "Passe de acabamento: velocidade reduzida, profundidade menor, offset 0.2mm"
        }

    # Summary
    time_est_min = (thickness / actual_doc) * 0.1  # rough estimate
    result["summary"] = (
        f"🔧 CNC — {mat['name']} ({thickness}mm) com fresa ⌀{tool_d}mm\n"
        f"   Feed: {mat['feed_rate_mm_min']}mm/min | RPM: {mat['spindle_rpm']} | "
        f"DOC: {actual_doc:.2f}mm × {num_passes} passes\n"
        f"   Chip load: {chip_load:.4f}mm | Stepover: {stepover_mm:.2f}mm ({stepover_pct*100:.0f}%)"
    )

    return result


# ──────────────────────────────────────────────
# analyze_mesh: análise pura-Python de STL para imprimibilidade
# ──────────────────────────────────────────────

STL_MAX_TRIANGLES = 2_000_000
_MESH_CEILING_ANGLE_DEG = 85.0


class _UnionFind:
    """Union-Find (disjoint set) com path compression + union by rank.

    Cresce dinamicamente via add() — usado tanto para os componentes conexos
    da malha (por vértice compartilhado) quanto para o agrupamento de faces
    de "teto" em clusters de bridge (por aresta compartilhada).
    """
    __slots__ = ("parent", "rank")

    def __init__(self, n: int = 0):
        self.parent = list(range(n))
        self.rank = [0] * n

    def add(self) -> int:
        idx = len(self.parent)
        self.parent.append(idx)
        self.rank.append(0)
        return idx

    def find(self, x: int) -> int:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


_STL_COORD_LIMIT = 1e9


def _detect_stl_binary(path: str, size: int) -> bool:
    """
    Decide se um STL é binário ou ASCII.

    Regra base: um STL binário tem tamanho exato de 84 + 50*n bytes
    (80 bytes de header + 4 bytes de contagem + 50 bytes por triângulo).
    Mas isso é ambíguo: ~1 em 50 arquivos ASCII válidos calha de ter um
    tamanho que também satisfaz 84 + 50*n por coincidência (ex.: OpenSCAD
    2021.01 exporta ASCII por padrão), e alguns exportadores *binários*
    escrevem literalmente "solid ..." nos primeiros bytes do header de 80
    bytes, imitando o cabeçalho ASCII.

    Por isso, o conteúdo tem prioridade sobre o tamanho: se o arquivo
    começa com "solid" (case-insensitive) E contém o token "facet" nos
    primeiros 1KB, ou "endsolid" nos últimos 200 bytes, é ASCII de
    verdade — mesmo que o tamanho bata com a fórmula binária. Caso
    contrário, cai de volta na checagem por tamanho.
    """
    with open(path, "rb") as f:
        head = f.read(5)
        if head.lower() == b"solid":
            f.seek(0)
            first_kb = f.read(1024)
            if b"facet" in first_kb.lower():
                return False
            f.seek(max(0, size - 200))
            tail = f.read(200)
            if b"endsolid" in tail.lower():
                return False
    return size >= 84 and (size - 84) % 50 == 0


def _parse_stl(path: str) -> list:
    """
    Lê um arquivo STL (binário ou ASCII) e retorna lista de triângulos,
    cada um como (v1, v2, v3) com vi = (x, y, z) float.

    Detecção binário vs. ASCII: ver `_detect_stl_binary`.
    """
    size = os.path.getsize(path)
    is_binary = _detect_stl_binary(path, size)

    if is_binary:
        n = (size - 84) // 50
        if n > STL_MAX_TRIANGLES:
            raise ValueError(f"STL tem {n:,} triângulos — acima do limite de {STL_MAX_TRIANGLES:,}.")
        with open(path, "rb") as f:
            f.seek(84)
            data = f.read()
        triangles = []
        for rec in struct.iter_unpack("<12fH", data):
            # rec = (nx,ny,nz, v1x,v1y,v1z, v2x,v2y,v2z, v3x,v3y,v3z, attr)
            # A normal gravada é ignorada — recalculamos a partir da geometria
            # (mais robusto: alguns exportadores gravam normais zeradas).
            v1 = (rec[3], rec[4], rec[5])
            v2 = (rec[6], rec[7], rec[8])
            v3 = (rec[9], rec[10], rec[11])
            for v in (v1, v2, v3):
                for c in v:
                    if not math.isfinite(c) or abs(c) > _STL_COORD_LIMIT:
                        raise ValueError(
                            "STL parse produced non-finite/huge coordinates — "
                            "file may be ASCII misdetected as binary."
                        )
            triangles.append((v1, v2, v3))
        return triangles

    # ASCII
    with open(path, "r", errors="replace") as f:
        text = f.read()
    n = text.count("endfacet")
    if n > STL_MAX_TRIANGLES:
        raise ValueError(f"STL tem {n:,} triângulos — acima do limite de {STL_MAX_TRIANGLES:,}.")
    tokens = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text)
    triangles = []
    usable = len(tokens) - (len(tokens) % 3)
    for i in range(0, usable, 3):
        v1 = tuple(float(x) for x in tokens[i])
        v2 = tuple(float(x) for x in tokens[i + 1])
        v3 = tuple(float(x) for x in tokens[i + 2])
        triangles.append((v1, v2, v3))
    return triangles


def analyze_mesh(path: str, overhang_deg: float = 45.0, bed_tol: float = 0.3, layer_h: float = 0.2) -> dict:
    """
    Analisa um arquivo STL (binário ou ASCII) para imprimibilidade 3D:
    manifoldness, componentes desconexos/flutuantes, volume, área de
    superfície, overhangs e bridges (vãos sem suporte).

    Convenção de ângulo de overhang usada em todo o retorno:
    0° = parede vertical, 90° = teto horizontal (ângulo medido a partir
    da vertical). Para uma face com normal unitária de componente z = nz
    (apontando para fora do sólido): overhang_angle = degrees(asin(-nz)).
    Uma face é candidata a overhang quando nz < -sin(overhang_deg).

    Performance: pura Python, sem numpy. Usa dicts com chaves de coordenada
    arredondada em 1e-6 para deduplicar vértices e union-find para
    componentes/clusters — pensado para lidar com ~200k triângulos em
    poucos segundos. Hard cap de STL_MAX_TRIANGLES triângulos.
    """
    triangles = _parse_stl(path)
    n_tri = len(triangles)
    if n_tri > STL_MAX_TRIANGLES:
        raise ValueError(f"STL tem {n_tri:,} triângulos — acima do limite de {STL_MAX_TRIANGLES:,}.")
    if n_tri == 0:
        raise ValueError("STL não contém triângulos.")

    vertex_map = {}
    vertex_coords = []
    uf = _UnionFind()
    edge_faces = {}  # (i,j) ordenado -> [face_idx, ...]

    tri_repr = [0] * n_tri
    tri_area = [0.0] * n_tri
    tri_nz = [0.0] * n_tri
    tri_max_z = [0.0] * n_tri
    tri_centroid = [None] * n_tri

    volume_acc = 0.0
    surface_acc = 0.0

    def _get_vidx(pt):
        key = (round(pt[0], 6), round(pt[1], 6), round(pt[2], 6))
        idx = vertex_map.get(key)
        if idx is None:
            idx = uf.add()
            vertex_map[key] = idx
            vertex_coords.append(pt)
        return idx

    for fi in range(n_tri):
        v1, v2, v3 = triangles[fi]
        i0 = _get_vidx(v1)
        i1 = _get_vidx(v2)
        i2 = _get_vidx(v3)
        uf.union(i0, i1)
        uf.union(i1, i2)
        tri_repr[fi] = i0

        for a, b in ((i0, i1), (i1, i2), (i2, i0)):
            key = (a, b) if a < b else (b, a)
            lst = edge_faces.get(key)
            if lst is None:
                edge_faces[key] = [fi]
            else:
                lst.append(fi)

        ux, uy, uz = v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2]
        wx, wy, wz = v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2]
        cx = uy * wz - uz * wy
        cy = uz * wx - ux * wz
        cz = ux * wy - uy * wx
        clen = math.sqrt(cx * cx + cy * cy + cz * cz)
        area = clen / 2.0
        tri_area[fi] = area
        tri_nz[fi] = (cz / clen) if clen > 1e-12 else 0.0
        surface_acc += area

        volume_acc += (
            v1[0] * (v2[1] * v3[2] - v2[2] * v3[1])
            + v1[1] * (v2[2] * v3[0] - v2[0] * v3[2])
            + v1[2] * (v2[0] * v3[1] - v2[1] * v3[0])
        )

        max_z = v1[2] if v1[2] >= v2[2] else v2[2]
        if v3[2] > max_z:
            max_z = v3[2]
        tri_max_z[fi] = max_z
        tri_centroid[fi] = (
            (v1[0] + v2[0] + v3[0]) / 3.0,
            (v1[1] + v2[1] + v3[1]) / 3.0,
            (v1[2] + v2[2] + v3[2]) / 3.0,
        )

    n_vert = len(vertex_coords)
    xs = [c[0] for c in vertex_coords]
    ys = [c[1] for c in vertex_coords]
    zs = [c[2] for c in vertex_coords]
    bbox_min = (min(xs), min(ys), min(zs))
    bbox_max = (max(xs), max(ys), max(zs))
    z_min_global = bbox_min[2]
    size_xyz = [bbox_max[i] - bbox_min[i] for i in range(3)]

    non_manifold_edges = sum(1 for lst in edge_faces.values() if len(lst) != 2)
    watertight = non_manifold_edges == 0
    volume_mm3 = abs(volume_acc) / 6.0
    surface_mm2 = surface_acc

    # ── componentes conexos (por vértice compartilhado) ──
    comp_stats = {}
    for vi in range(n_vert):
        root = uf.find(vi)
        x, y, z = vertex_coords[vi]
        st = comp_stats.get(root)
        if st is None:
            comp_stats[root] = {"triangles": 0, "min": [x, y, z], "max": [x, y, z]}
        else:
            m, M = st["min"], st["max"]
            if x < m[0]:
                m[0] = x
            if y < m[1]:
                m[1] = y
            if z < m[2]:
                m[2] = z
            if x > M[0]:
                M[0] = x
            if y > M[1]:
                M[1] = y
            if z > M[2]:
                M[2] = z

    for fi in range(n_tri):
        comp_stats[uf.find(tri_repr[fi])]["triangles"] += 1

    component_details = []
    floating = 0
    for st in comp_stats.values():
        z_min_c = st["min"][2]
        is_floating = z_min_c > z_min_global + bed_tol
        if is_floating:
            floating += 1
        component_details.append({
            "triangles": st["triangles"],
            "bbox": {"min": st["min"], "max": st["max"]},
            "z_min": z_min_c,
            "floating": is_floating,
        })
    component_details.sort(key=lambda c: c["z_min"])
    n_components = len(comp_stats)

    # ── overhang + bridges ──
    overhang_threshold = -math.sin(math.radians(overhang_deg))
    ceiling_threshold = -math.sin(math.radians(_MESH_CEILING_ANGLE_DEG))

    down_facing_area = 0.0
    overhang_area = 0.0
    worst = []  # mantém as 5 piores (menor z) faces de overhang: [(z, centroid, angle_deg), ...]
    is_ceiling = [False] * n_tri

    for fi in range(n_tri):
        nz = tri_nz[fi]
        if nz >= 0:
            continue
        on_bed = tri_max_z[fi] <= z_min_global + bed_tol
        if on_bed:
            continue
        down_facing_area += tri_area[fi]
        if nz < overhang_threshold:
            overhang_area += tri_area[fi]
            angle = math.degrees(math.asin(max(-1.0, min(1.0, -nz))))
            cz = tri_centroid[fi][2]
            worst.append((cz, tri_centroid[fi], angle))
            worst.sort(key=lambda w: w[0])
            if len(worst) > 5:
                worst.pop()
        if nz < ceiling_threshold:
            is_ceiling[fi] = True

    overhang_pct = (overhang_area / down_facing_area * 100.0) if down_facing_area > 0 else 0.0

    ceiling_uf = _UnionFind(n_tri)
    for lst in edge_faces.values():
        ceiling_faces = [f for f in lst if is_ceiling[f]]
        base = None
        for f in ceiling_faces:
            if base is None:
                base = f
            else:
                ceiling_uf.union(base, f)

    cluster_stats = {}
    for fi in range(n_tri):
        if not is_ceiling[fi]:
            continue
        root = ceiling_uf.find(fi)
        st = cluster_stats.get(root)
        if st is None:
            st = {"triangles": 0, "area": 0.0, "min": None, "max": None}
            cluster_stats[root] = st
        st["triangles"] += 1
        st["area"] += tri_area[fi]
        for vx, vy, vz in triangles[fi]:
            if st["min"] is None:
                st["min"] = [vx, vy, vz]
                st["max"] = [vx, vy, vz]
            else:
                m, M = st["min"], st["max"]
                if vx < m[0]:
                    m[0] = vx
                if vy < m[1]:
                    m[1] = vy
                if vz < m[2]:
                    m[2] = vz
                if vx > M[0]:
                    M[0] = vx
                if vy > M[1]:
                    M[1] = vy
                if vz > M[2]:
                    M[2] = vz

    bridge_area = sum(st["area"] for st in cluster_stats.values())
    largest_cluster = None
    if cluster_stats:
        best = max(cluster_stats.values(), key=lambda s: s["area"])
        dx = best["max"][0] - best["min"][0]
        dy = best["max"][1] - best["min"][1]
        dz = best["max"][2] - best["min"][2]
        largest_cluster = {
            "triangles": best["triangles"],
            "area_mm2": best["area"],
            "bbox_size": [dx, dy, dz],
            "span_mm": max(dx, dy),
        }

    # ── veredito ──
    errors = []
    warnings_ = []
    info = []

    if not watertight:
        errors.append(f"❌ Malha não é watertight: {non_manifold_edges} aresta(s) não-manifold (não conectam exatamente 2 faces).")
    else:
        info.append("✅ Malha é watertight (todas as arestas conectam exatamente 2 faces).")

    if floating > 0:
        errors.append(
            f"❌ {floating} componente(s) flutuante(s) no ar (z_min acima de {bed_tol}mm da base) "
            "— precisam de suporte ou reorientação."
        )

    if n_components > 1:
        warnings_.append(f"⚠ {n_components} componentes desconexos na malha.")
    else:
        info.append("✅ Malha é uma única peça conexa.")

    if overhang_pct > 5:
        warnings_.append(
            f"⚠ {overhang_pct:.1f}% da área voltada para baixo é overhang > {overhang_deg}° "
            f"({overhang_area:.1f}mm²) — considere suporte ou reorientação."
        )
    elif overhang_area > 0:
        info.append(f"✅ Overhang dentro do aceitável ({overhang_pct:.1f}% da área voltada para baixo).")

    if largest_cluster and largest_cluster["span_mm"] > 30:
        warnings_.append(
            f"⚠ Maior bridge (vão sem suporte) tem {largest_cluster['span_mm']:.1f}mm de extensão "
            "— considere suporte para vãos > 30mm."
        )
    elif bridge_area > 0:
        info.append("✅ Maior bridge dentro do limite recomendado (≤30mm).")

    printable = len(errors) == 0
    summary = (
        f"{'✅ Imprimível' if printable else '❌ Não imprimível'} "
        f"({len(errors)} erro(s), {len(warnings_)} aviso(s))"
    )

    return {
        "path": path,
        "triangles": n_tri,
        "vertices": n_vert,
        "bbox": {"min": list(bbox_min), "max": list(bbox_max)},
        "size": size_xyz,
        "z_min": z_min_global,
        "non_manifold_edges": non_manifold_edges,
        "watertight": watertight,
        "components": n_components,
        "component_details": component_details,
        "floating_components": floating,
        "volume_mm3": volume_mm3,
        "surface_mm2": surface_mm2,
        "overhang": {
            "convention": "0°=parede vertical, 90°=teto horizontal (ângulo a partir da vertical; angle=degrees(asin(-nz)))",
            "threshold_deg": overhang_deg,
            "down_facing_area_mm2": down_facing_area,
            "overhang_area_mm2": overhang_area,
            "overhang_pct": overhang_pct,
            "worst_faces": [{"centroid": list(c), "angle_deg": a} for (_, c, a) in worst],
        },
        "bridges": {
            "ceiling_threshold_deg": _MESH_CEILING_ANGLE_DEG,
            "bridge_area_mm2": bridge_area,
            "largest_cluster": largest_cluster,
        },
        "layer_h": layer_h,
        "layers_estimate": round(size_xyz[2] / layer_h) if layer_h > 0 else None,
        "errors": errors,
        "warnings": warnings_,
        "info": info,
        "printable": printable,
        "summary": summary,
    }


def _format_mesh_analysis(r: dict) -> str:
    """Formata o dict de analyze_mesh() como texto legível (mesmo padrão de validate_printability)."""
    watertight_line = "✅ sim" if r["watertight"] else f"❌ não ({r['non_manifold_edges']} arestas não-manifold)"
    size_r = [round(s, 2) for s in r["size"]]

    lines = [
        f"🔍 Análise de Malha STL — {r['triangles']} triângulos, {r['vertices']} vértices únicos",
        f"Resultado: {r['summary']}",
        "",
        f"📦 Bounding box: min={r['bbox']['min']} max={r['bbox']['max']} | tamanho={size_r}mm",
        f"🧩 Componentes: {r['components']} ({r['floating_components']} flutuante(s))",
        f"🔗 Watertight: {watertight_line}",
        f"📐 Volume: {r['volume_mm3']:.2f}mm³ | Área de superfície: {r['surface_mm2']:.2f}mm²",
        "",
        f"⛰ Overhang — convenção: {r['overhang']['convention']}",
        (
            f"  Área voltada p/ baixo: {r['overhang']['down_facing_area_mm2']:.2f}mm² | "
            f"Overhang > {r['overhang']['threshold_deg']}°: {r['overhang']['overhang_area_mm2']:.2f}mm² "
            f"({r['overhang']['overhang_pct']:.1f}%)"
        ),
    ]
    if r["overhang"]["worst_faces"]:
        lines.append("  Piores faces (menor z):")
        for wf in r["overhang"]["worst_faces"]:
            c = wf["centroid"]
            lines.append(f"    centroid=({c[0]:.1f}, {c[1]:.1f}, {c[2]:.1f}) ângulo={wf['angle_deg']:.1f}°")

    lc = r["bridges"]["largest_cluster"]
    lines.append("")
    lines.append(f"🌉 Bridges (faces de teto > {r['bridges']['ceiling_threshold_deg']}° fora da base): "
                 f"área total {r['bridges']['bridge_area_mm2']:.2f}mm²")
    if lc:
        lines.append(
            f"  Maior vão: {lc['span_mm']:.1f}mm (bbox {[round(s,1) for s in lc['bbox_size']]}mm, {lc['triangles']} face(s))"
        )

    lines.append("")
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

    return "\n".join(lines)


# ──────────────────────────────────────────────
# mesh_section: corte transversal (cross-section) de STL para fit-check
# ──────────────────────────────────────────────

_MESH_SECTION_AXES = {"x": 0, "y": 1, "z": 2}
_MESH_SECTION_MAX_Z = 50
_MESH_SECTION_NUDGE = 1e-4


def _triangle_plane_segment(tri, axis_idx: int, plane_idx: tuple, z: float, eps: float = 1e-9):
    """
    Interseção de um triângulo com o plano perpendicular a axis_idx em z.
    Retorna None (sem interseção/degenerado) ou um par de pontos 2D
    (nas coordenadas de plane_idx) que formam o segmento de corte.
    """
    d = [v[axis_idx] - z for v in tri]
    signs = [0 if abs(x) < eps else (1 if x > 0 else -1) for x in d]

    def proj(v):
        return (v[plane_idx[0]], v[plane_idx[1]])

    def interp(a, b, da, db):
        t = da / (da - db)
        return tuple(a[k] + t * (b[k] - a[k]) for k in plane_idx)

    pos = [i for i in range(3) if signs[i] > 0]
    neg = [i for i in range(3) if signs[i] < 0]
    zero = [i for i in range(3) if signs[i] == 0]

    if len(zero) == 3:
        return None  # triângulo coplanar ao corte — degenerado, ignorado
    if len(zero) == 2:
        if not pos and not neg:
            return None
        i, j = zero
        return (proj(tri[i]), proj(tri[j]))
    if len(zero) == 1:
        if len(pos) == 2 or len(neg) == 2:
            return None  # toque tangente num único vértice — sem segmento
        i0 = zero[0]
        others = [k for k in range(3) if k != i0]
        a, b = tri[others[0]], tri[others[1]]
        p = interp(a, b, d[others[0]], d[others[1]])
        return (proj(tri[i0]), p)
    if not pos or not neg:
        return None  # todos do mesmo lado — sem interseção
    lone_side, pair_side = (pos, neg) if len(pos) == 1 else (neg, pos)
    lone = lone_side[0]
    p1 = interp(tri[lone], tri[pair_side[0]], d[lone], d[pair_side[0]])
    p2 = interp(tri[lone], tri[pair_side[1]], d[lone], d[pair_side[1]])
    return (p1, p2)


def mesh_section(path: str, zs, axis: str = "z", center=None) -> dict:
    """
    Corta um STL (binário ou ASCII) por um ou mais planos perpendiculares a
    `axis` (default "z") e retorna, para cada altura solicitada: os pontos
    de interseção, bounding box no plano, extensão (extent), r_min/r_max
    (distância radial a partir de `center`) e os contornos (loops)
    encontrados ligando segmentos por vértices compartilhados (1e-6).

    Contornos são ordenados por r_max decrescente — para um tubo oco,
    contours[0] é a parede externa e contours[1] é o furo (bore).
    Diâmetros e espessura de parede usam r_max (raio nominal dos vértices);
    r_min é o apótema do polígono $fn.

    Se o plano solicitado coincidir exatamente com um anel de vértices da
    malha (comum em meshes do OpenSCAD, ex. z=0), a altura é deslocada
    automaticamente em +1e-4 e isso é reportado em `nudged`/`z_used`.

    `zs` aceita um número único ou uma lista (máx. 50 valores).
    `center`, se informado, é [c1, c2] nas coordenadas do plano (mesmo
    center usado para todas as alturas); por padrão é o centroide dos
    pontos de cada corte.
    """
    if axis not in _MESH_SECTION_AXES:
        raise ValueError(f"axis inválido: {axis!r}. Use 'x', 'y' ou 'z'.")
    axis_idx = _MESH_SECTION_AXES[axis]
    plane_idx = tuple(i for i in range(3) if i != axis_idx)
    plane_labels = tuple("xyz"[i] for i in plane_idx)

    if not isinstance(zs, (list, tuple)):
        zs = [zs]
    zs = list(zs)
    if len(zs) == 0:
        raise ValueError("Forneça ao menos uma altura de corte (z ou z_list).")
    if len(zs) > _MESH_SECTION_MAX_Z:
        raise ValueError(f"z_list aceita no máximo {_MESH_SECTION_MAX_Z} valores.")

    triangles = _parse_stl(path)
    n_tri = len(triangles)
    if n_tri > STL_MAX_TRIANGLES:
        raise ValueError(f"STL tem {n_tri:,} triângulos — acima do limite de {STL_MAX_TRIANGLES:,}.")
    if n_tri == 0:
        raise ValueError("STL não contém triângulos.")

    axis_coords = set()
    for tri in triangles:
        for v in tri:
            axis_coords.add(round(v[axis_idx], 6))

    sections = []
    for z_req in zs:
        z_req = float(z_req)
        z_used = z_req
        nudged = False
        if round(z_used, 6) in axis_coords:
            z_used = z_used + _MESH_SECTION_NUDGE
            nudged = True

        point_map = {}
        point_coords = []
        uf = _UnionFind()

        def _get_pidx(pt):
            key = (round(pt[0], 6), round(pt[1], 6))
            idx = point_map.get(key)
            if idx is None:
                idx = uf.add()
                point_map[key] = idx
                point_coords.append(pt)
            return idx

        for tri in triangles:
            seg = _triangle_plane_segment(tri, axis_idx, plane_idx, z_used)
            if seg is None:
                continue
            p1, p2 = seg
            i1 = _get_pidx(p1)
            i2 = _get_pidx(p2)
            if i1 != i2:
                uf.union(i1, i2)

        n_points = len(point_coords)
        if n_points == 0:
            sections.append({
                "z_requested": z_req,
                "z_used": z_used,
                "nudged": nudged,
                "n_points": 0,
                "bbox": None,
                "extent": None,
                "center": None,
                "r_min": None,
                "r_max": None,
                "contours": [],
            })
            continue

        c1s = [p[0] for p in point_coords]
        c2s = [p[1] for p in point_coords]
        bbox_min = (min(c1s), min(c2s))
        bbox_max = (max(c1s), max(c2s))
        extent = (bbox_max[0] - bbox_min[0], bbox_max[1] - bbox_min[1])

        if center is not None:
            cx, cy = float(center[0]), float(center[1])
        else:
            cx = sum(c1s) / n_points
            cy = sum(c2s) / n_points

        def _radius(p):
            return math.hypot(p[0] - cx, p[1] - cy)

        radii = [_radius(p) for p in point_coords]
        r_min_all = min(radii)
        r_max_all = max(radii)

        contour_stats = {}
        for idx, p in enumerate(point_coords):
            root = uf.find(idx)
            r = radii[idx]
            st = contour_stats.get(root)
            if st is None:
                contour_stats[root] = {"points": 1, "r_min": r, "r_max": r}
            else:
                st["points"] += 1
                if r < st["r_min"]:
                    st["r_min"] = r
                if r > st["r_max"]:
                    st["r_max"] = r

        contours = sorted(contour_stats.values(), key=lambda c: c["r_max"], reverse=True)

        sections.append({
            "z_requested": z_req,
            "z_used": z_used,
            "nudged": nudged,
            "n_points": n_points,
            "bbox": {plane_labels[0] + "_min": bbox_min[0], plane_labels[1] + "_min": bbox_min[1],
                     plane_labels[0] + "_max": bbox_max[0], plane_labels[1] + "_max": bbox_max[1]},
            "extent": list(extent),
            "center": [cx, cy],
            "r_min": r_min_all,
            "r_max": r_max_all,
            "contours": contours,
        })

    return {
        "path": path,
        "axis": axis,
        "plane_axes": list(plane_labels),
        "sections": sections,
    }


def _format_mesh_section(r: dict) -> str:
    """Formata o dict de mesh_section() como texto legível."""
    a1, a2 = r["plane_axes"]
    lines = [f"✂ Corte de Malha — eixo {r['axis']} (plano {a1}{a2})"]
    for s in r["sections"]:
        lines.append("")
        z_line = f"z_solicitado={s['z_requested']:.4f}"
        if s["nudged"]:
            z_line += f" → deslocado para {s['z_used']:.4f} (coincidia com anel de vértices)"
        lines.append(z_line)
        if s["n_points"] == 0:
            lines.append("  Sem interseção (plano fora do bounding box da malha).")
            continue
        lines.append(f"  Pontos: {s['n_points']} | Extensão ({a1},{a2}): {[round(x, 3) for x in s['extent']]}mm")
        lines.append(
            f"  Centro usado: ({s['center'][0]:.3f}, {s['center'][1]:.3f}) | "
            f"r_min={s['r_min']:.3f} r_max={s['r_max']:.3f}"
        )
        lines.append(f"  Contornos: {len(s['contours'])}")
        for i, c in enumerate(s["contours"]):
            lines.append(f"    [{i}] pontos={c['points']} r_min={c['r_min']:.3f} r_max={c['r_max']:.3f}")
        if len(s["contours"]) >= 2:
            outer, inner = s["contours"][0], s["contours"][1]
            d_ext = 2 * outer["r_max"]
            d_int = 2 * inner["r_max"]
            wall = outer["r_max"] - inner["r_max"]
            lines.append(f"  Ø externo {d_ext:.3f} | Ø interno {d_int:.3f} | parede {wall:.3f}")
            lines.append(
                "  (diâmetros e parede usam r_max — raio nominal dos vértices; "
                "r_min é o apótema do polígono $fn)"
            )
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Registro das ferramentas MCP
# ──────────────────────────────────────────────
@server.list_tools()
async def handle_list_tools() -> list:
    return [
        # Exportação básica
        types.Tool(
            name="render_to_png",
            description=(
                "Render OpenSCAD code to a PNG image preview. "
                "Supports camera control: angle, distance, position, projection (perspective/ortho), "
                "and image size."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "variables": {"type": "object", "description": "Optional dict of variables (-D name=value)"},
                    "scad_code": {"type": "string", "description": "The OpenSCAD source code"},
                    "camera": {
                        "type": "object",
                        "description": (
                            "Camera settings: translate (x,y,z center), rotate (rx,ry,rz angles), "
                            "distance (zoom), projection ('perspective' or 'ortho')"
                        )
                    },
                    "size": {
                        "type": "object",
                        "description": "Image size: width, height in pixels (default 800x600)"
                    },
                    "timeout_s": {
                        "type": "number",
                        "description": "Render timeout in seconds (default 60, max 900)"
                    },
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
                    "output_path": {"type": "string"},
                    "timeout_s": {
                        "type": "number",
                        "description": "Render timeout in seconds (default 60, max 900)"
                    },
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
                    "output_path": {"type": "string"},
                    "timeout_s": {
                        "type": "number",
                        "description": "Render timeout in seconds (default 60, max 900)"
                    },
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
                    "output_path": {"type": "string"},
                    "timeout_s": {
                        "type": "number",
                        "description": "Render timeout in seconds (default 60, max 900)"
                    },
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
                    "output_path": {"type": "string"},
                    "timeout_s": {
                        "type": "number",
                        "description": "Render timeout in seconds (default 60, max 900)"
                    },
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
        # 3D printing test plates (v0.4.0)
        types.Tool(
            name="generate_tolerance_test",
            description=(
                "Gera placa de teste de tolerância para calibração de impressão 3D. "
                "Pares de pinos macho e furos fêmea com tolerâncias variadas. "
                "Exporta SCAD + STL + preview PNG."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "base_width, base_depth, base_height, pin_height, pin_d, hole_d, "
                            "tol_min, tol_max, tol_step, gap"
                        )
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["output_dir", "project_name"]
            }
        ),
        types.Tool(
            name="generate_bed_level_test",
            description=(
                "Gera padrão de teste de nivelamento de mesa para impressão 3D. "
                "Grade de discos finos distribuídos pela área da mesa. "
                "Exporta SCAD + STL + preview PNG."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "bed_x, bed_y, disc_d, disc_h, grid_cols, grid_rows, skirt_w"
                        )
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["output_dir", "project_name"]
            }
        ),
        types.Tool(
            name="generate_retraction_test",
            description=(
                "Gera torre de teste de retração/stringing para impressão 3D. "
                "Cilindros finos espaçados em base comum. Stringing entre torres "
                "indica retração insuficiente. Exporta SCAD + STL + preview PNG."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "tower_d, tower_h, tower_count, tower_gap, base_h, base_pad"
                        )
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["output_dir", "project_name"]
            }
        ),
        types.Tool(
            name="generate_living_hinge",
            description=(
                "Gera padrão de living hinge para corte a laser. "
                "Padrões: straight (cortes paralelos alternados), serpentine (zigzag), cross (cross-hatch). "
                "Saída 2D para exportação SVG + DXF + preview PNG."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "width, height, material_thickness, kerf, "
                            "pattern (straight|serpentine|cross), "
                            "cut_length, cut_gap, row_spacing, margin"
                        )
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["output_dir", "project_name"]
            }
        ),
        types.Tool(
            name="generate_dogbone",
            description=(
                "Gera pocket retangular com compensação dogbone ou T-bone nos cantos para CNC. "
                "Compensa cantos internos para fresas cilíndricas. "
                "Inclui layout de teste com múltiplos tamanhos. Exporta SVG + DXF + preview PNG."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "width, height, depth, tool_d (diâmetro da fresa, default 3.175mm = 1/8\"), "
                            "corner_style (dogbone|tbone_h|tbone_v), material_thickness"
                        )
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["output_dir", "project_name"]
            }
        ),
        # Orientação + Assembly
        types.Tool(
            name="suggest_orientation",
            description=(
                "Sugere a melhor orientação de impressão 3D com base nas dimensões e furos. "
                "Analisa 3 orientações e retorna score, área de base e notas."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "width, depth, height, has_holes_xy, has_holes_xz, has_holes_yz, "
                            "has_flat_bottom, detail_on_top, profile (fdm_standard|fdm_fine|resin)"
                        )
                    }
                },
                "required": ["config"]
            }
        ),
        types.Tool(
            name="generate_assembly",
            description=(
                "Gera projeto multi-peça com posicionamento, vista explodida e BOM automático. "
                "Cada peça é definida com tipo (box/cylinder/custom), posição, rotação e cor. "
                "Exporta SCAD assembly + peças individuais + BOM em Markdown."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "pieces (array: name, type, w, d, h, translate, rotate, color, material, qty), "
                            "project_name, explode_distance"
                        )
                    },
                    "output_dir": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["output_dir", "project_name"]
            }
        ),
        # CNC
        types.Tool(
            name="generate_cnc_toolpath_hints",
            description=(
                "Gera sugestões de parâmetros CNC (feed rate, RPM, DOC, passes, chip load) "
                "para um material e fresa específicos. "
                "Materiais: mdf, plywood, acrylic, hardwood, softwood, aluminum, foam, hdpe."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "material (mdf|plywood|acrylic|hardwood|softwood|aluminum|foam|hdpe), "
                            "material_thickness, tool_d, tool_flutes, "
                            "cut_type (profile|pocket|drill|engrave), finishing_pass"
                        )
                    }
                },
                "required": ["config"]
            }
        ),
        # Análise de malha
        types.Tool(
            name="analyze_mesh",
            description=(
                "Analisa um arquivo STL (binário ou ASCII) ou código OpenSCAD para imprimibilidade 3D: "
                "manifoldness (watertight), componentes desconexos/flutuantes, volume, área de superfície, "
                "overhangs e bridges (vãos sem suporte). Análise 100% Python, sem dependências externas. "
                "Aceita 'stl_path' (arquivo já existente) OU 'scad_code' (exporta STL internamente antes de analisar)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "stl_path": {
                        "type": "string",
                        "description": "Caminho para um arquivo .stl existente (alternativa a scad_code)"
                    },
                    "scad_code": {
                        "type": "string",
                        "description": "Código OpenSCAD a exportar (STL) e analisar (alternativa a stl_path)"
                    },
                    "variables": {
                        "type": "object",
                        "description": "Variáveis -D quando usando scad_code"
                    },
                    "timeout_s": {
                        "type": "number",
                        "description": "Timeout do export quando usando scad_code, em segundos (default 60, max 900)"
                    },
                    "overhang_deg": {
                        "type": "number",
                        "description": "Ângulo (a partir da vertical) considerado overhang crítico (default 45°)"
                    },
                    "bed_tol": {
                        "type": "number",
                        "description": "Tolerância em mm para considerar uma face 'na base' (default 0.3mm)"
                    },
                    "layer_h": {
                        "type": "number",
                        "description": "Altura de camada em mm, usada só para estimar o nº de camadas (default 0.2mm)"
                    },
                },
            }
        ),
        types.Tool(
            name="mesh_section",
            description=(
                "Corta um STL (binário ou ASCII) ou código OpenSCAD por um ou mais planos perpendiculares "
                "a um eixo, para fit-check de encaixes/press-fits. Retorna pontos de interseção, bbox no "
                "plano, extensão, r_min/r_max a partir de um centro e os contornos (loops) encontrados — "
                "para um tubo oco, contours[0] é a parede externa e contours[1] é o furo. "
                "Aceita 'stl_path' (arquivo já existente) OU 'scad_code' (exporta STL internamente antes de cortar)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "stl_path": {
                        "type": "string",
                        "description": "Caminho para um arquivo .stl existente (alternativa a scad_code)"
                    },
                    "scad_code": {
                        "type": "string",
                        "description": "Código OpenSCAD a exportar (STL) e cortar (alternativa a stl_path)"
                    },
                    "variables": {
                        "type": "object",
                        "description": "Variáveis -D quando usando scad_code"
                    },
                    "timeout_s": {
                        "type": "number",
                        "description": "Timeout do export quando usando scad_code, em segundos (default 60, max 900)"
                    },
                    "z": {
                        "type": "number",
                        "description": "Altura única de corte (alternativa a z_list)"
                    },
                    "z_list": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Lista de alturas de corte (máx. 50) — alternativa a z"
                    },
                    "axis": {
                        "type": "string",
                        "enum": ["x", "y", "z"],
                        "description": "Eixo perpendicular ao plano de corte (default 'z')"
                    },
                    "center": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "[c1, c2] no plano de corte para medidas radiais (default: centroide dos pontos)"
                    },
                },
            }
        ),
    ]



# ──────────────────────────────────────────────
# Helper: gera SCAD, salva, exporta formatos e retorna resultado com preview PNG
# ──────────────────────────────────────────────
async def _generate_and_export(
    scad_code: str,
    output_dir: str,
    project_name: str,
    results: list[str],
    export_formats: list[tuple[str, str]] | None = None,
    png_args: list[str] | None = None,
    scad_2d: str | None = None,
) -> list:
    """
    Helper que encapsula o padrão repetido em todos os handlers:
    1. Salva o SCAD no disco
    2. Exporta os formatos vetoriais (SVG, DXF, STL…)
    3. Renderiza preview PNG
    4. Retorna lista de TextContent + ImageContent

    Args:
        scad_code: código SCAD principal (3D)
        output_dir: diretório de saída (já validado)
        project_name: nome base dos arquivos (já sanitizado)
        results: lista de mensagens de resultado acumuladas
        export_formats: lista de (ext, label) a exportar; default = [("svg","🖼 SVG"),("dxf","📐 DXF")]
        png_args: args extras para o render PNG; default = ["--autocenter","--viewall"]
        scad_2d: código SCAD 2D alternativo para exports vetoriais; usa scad_code se None
    """
    if export_formats is None:
        export_formats = [("svg", "🖼 SVG"), ("dxf", "📐 DXF")]
    if png_args is None:
        png_args = ["--autocenter", "--viewall"]
    scad_src = scad_2d if scad_2d is not None else scad_code

    # Salva SCAD
    os.makedirs(output_dir, exist_ok=True)
    scad_path = os.path.join(output_dir, f"{project_name}.scad")
    with open(scad_path, "w") as f:
        f.write(scad_code)

    # Exports vetoriais
    for fmt, label in export_formats:
        try:
            dst = os.path.join(output_dir, f"{project_name}.{fmt}")
            p, _ = await run_openscad(scad_src, fmt)
            shutil.move(p, dst)
            results.append(f"{label} gerado: {dst}")
        except Exception as e:
            results.append(f"❌ Erro {fmt.upper()}: {e}")

    # Preview PNG
    try:
        out_path, _ = await run_openscad(scad_code, "png", png_args)
        with open(out_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("utf-8")
        os.remove(out_path)
        return [
            types.TextContent(type="text", text="\n".join(results)),
            types.ImageContent(type="image", data=img_data, mimeType="image/png"),
        ]
    except Exception as e:
        results.append(f"❌ Erro PNG: {e}")
        return [types.TextContent(type="text", text="\n".join(results))]


async def _resolve_stl_input(arguments: dict) -> tuple:
    """
    Resolve a entrada compartilhada por analyze_mesh e mesh_section:
    'stl_path' (validado) ou 'scad_code' (exportado para STL via run_openscad).
    Assume que o chamador já validou que ao menos um dos dois está presente.

    Retorna (target_path, tmp_generated) — tmp_generated é o path a remover
    depois de usar (arquivo temporário gerado a partir de scad_code), ou
    None quando target_path veio de um stl_path já existente.
    """
    stl_path = arguments.get("stl_path")
    if stl_path:
        resolved_path = validate_output_path(stl_path)
        if not os.path.isfile(resolved_path):
            raise ValueError(f"Arquivo STL não encontrado: {resolved_path}")
        return resolved_path, None

    scad_code = arguments["scad_code"]
    variables = arguments.get("variables", {})
    timeout_s = arguments.get("timeout_s", RENDER_TIMEOUT_DEFAULT)
    extra_args = []
    for k, v in variables.items():
        if isinstance(v, str):
            escaped_v = str(v).replace('"', '\\"')
            extra_args.extend(["-D", f'{k}="{escaped_v}"'])
        elif isinstance(v, bool):
            extra_args.extend(["-D", f'{k}={"true" if v else "false"}'])
        else:
            extra_args.extend(["-D", f"{k}={v}"])
    target_path, _ = await run_openscad(scad_code, "stl", extra_args, timeout_s=timeout_s)
    return target_path, target_path


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list:

    # ── Security, Safety, and Validation Interceptor ──────────────────
    if not arguments:
        arguments = {}

    # Safety checks (keywords check)
    scad_code_for_safety = arguments.get("scad_code", "")
    project_name_for_safety = arguments.get("project_name", "")
    # Check custom SCAD in config if present
    cfg = arguments.get("config", {})
    if isinstance(cfg, dict):
        for piece in cfg.get("pieces", []):
            if isinstance(piece, dict) and "scad" in piece:
                scad_code_for_safety += " " + str(piece["scad"])
        if "project_name" in cfg:
            project_name_for_safety += " " + str(cfg["project_name"])
    verify_safety_guidelines(scad_code_for_safety, project_name_for_safety)

    # Path traversal validation/sanitization
    if "output_path" in arguments:
        arguments["output_path"] = validate_output_path(arguments["output_path"])
    
    if "output_dir" in arguments:
        output_dir = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "project")
        sanitized_dir, sanitized_proj = safe_output_path(output_dir, project_name)
        arguments["output_dir"] = sanitized_dir
        arguments["project_name"] = sanitized_proj

    # Config parameters validation (checking negative values, divisions, limits)
    if "config" in arguments:
        if name in [
            "generate_laser_part", "generate_box", "generate_kerf_test", "generate_finger_test",
            "generate_3d_box", "generate_bracket", "generate_enclosure", "validate_printability",
            "generate_tolerance_test", "generate_bed_level_test", "generate_retraction_test",
            "generate_living_hinge", "generate_dogbone", "suggest_orientation", "generate_assembly",
            "generate_cnc_toolpath_hints"
        ]:
            validate_config_parameters(name, arguments["config"])

    # ── Exportação básica ──────────────────────────────────────────
    if name in ["render_to_png", "export_stl", "export_3mf", "export_dxf", "export_svg"]:
        if "scad_code" not in arguments:
            raise ValueError("Missing 'scad_code' argument")

        scad_code = arguments["scad_code"]
        variables = arguments.get("variables", {})
        timeout_s = arguments.get("timeout_s", RENDER_TIMEOUT_DEFAULT)
        extra_args = []
        for k, v in variables.items():
            if isinstance(v, str):
                escaped_v = str(v).replace('"', '\\"')
                extra_args.extend(["-D", f'{k}="{escaped_v}"'])
            elif isinstance(v, bool):
                extra_args.extend(["-D", f'{k}={"true" if v else "false"}'])
            else:
                extra_args.extend(["-D", f"{k}={v}"])

        if name == "render_to_png":
            # Camera options
            camera = arguments.get("camera", {})
            img_size = arguments.get("size", {})
            render_args = extra_args[:]

            cam_translate = camera.get("translate")
            cam_rotate = camera.get("rotate")
            cam_distance = camera.get("distance")
            projection = camera.get("projection", "perspective")

            if cam_translate and cam_rotate and cam_distance:
                tx, ty, tz = cam_translate
                rx, ry, rz = cam_rotate
                d = cam_distance
                render_args.extend(["--camera", f"{tx},{ty},{tz},{rx},{ry},{rz},{d}"])
            else:
                render_args.extend(["--autocenter", "--viewall"])

            if projection == "ortho":
                render_args.append("--projection=ortho")

            width = img_size.get("width", 800)
            height = img_size.get("height", 600)
            render_args.extend(["--imgsize", f"{width},{height}"])

            out_path = None
            try:
                out_path, _ = await run_openscad(scad_code, "png", render_args, timeout_s=timeout_s)
                with open(out_path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
                return [
                    types.TextContent(type="text", text="Rendered successfully."),
                    types.ImageContent(type="image", data=img_data, mimeType="image/png")
                ]
            except Exception as e:
                return [types.TextContent(type="text", text=str(e))]
            finally:
                if out_path and os.path.exists(out_path):
                    try:
                        os.remove(out_path)
                    except Exception:
                        pass
        else:
            if "output_path" not in arguments:
                raise ValueError("Missing 'output_path' argument")
            output_path = arguments["output_path"]
            ext = name.split("_")[1]
            out_path = None
            try:
                out_path, _ = await run_openscad(scad_code, ext, extra_args, timeout_s=timeout_s)
                shutil.move(out_path, output_path)
                return [types.TextContent(type="text", text=f"Exported successfully to {output_path}")]
            except Exception as e:
                return [types.TextContent(type="text", text=str(e))]
            finally:
                if out_path and os.path.exists(out_path):
                    try:
                        os.remove(out_path)
                    except Exception:
                        pass

    elif name == "check_syntax":
        if not arguments or "scad_code" not in arguments:
            raise ValueError("Missing 'scad_code' argument")
        is_valid, msg = await check_scad_syntax(arguments["scad_code"])
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
        warns     = validate_config(config)
        scad_code = generate_laser_scad(config)
        scad_2d   = scad_code.replace('RENDER_MODE = "3d"', 'RENDER_MODE = "2d"')
        results   = [f"📄 SCAD gerado: {os.path.join(output_dir, project_name + '.scad')}"]
        if warns:
            results.append("⚠ Avisos:\n" + "\n".join(warns))
        return await _generate_and_export(scad_code, output_dir, project_name, results, scad_2d=scad_2d)

    elif name == "generate_box":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "box")
        warns     = validate_box_config(config)
        scad_code = generate_box_scad(config)
        sw, sh    = arguments.get("sheet_width", 600), arguments.get("sheet_height", 400)
        est       = estimate_material_use(config, sw, sh)
        scad_2d   = scad_code.replace('RENDER_MODE = "3d"', 'RENDER_MODE = "2d"')
        results   = [f"📦 Caixa gerada: {os.path.join(output_dir, project_name + '.scad')}"]
        if warns:
            results.append("⚠ Avisos:\n" + "\n".join(warns))
        results.append(
            f"\n📊 Material ({sw}x{sh}mm):\n"
            + "\n".join(f"  {p['name']} x{p['qty']}: {p['w']:.0f}×{p['h']:.0f}mm" for p in est["pieces"])
            + f"\n  Área: {est['total_area_cm2']} cm² | Uso: {est['usage_percent']}% | Chapas: {est['sheets_needed']}"
        )
        return await _generate_and_export(scad_code, output_dir, project_name, results, scad_2d=scad_2d)

    elif name == "generate_kerf_test":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "kerf_test")
        scad_code = generate_kerf_test_scad(config)
        results   = [f"🔬 Placa de kerf gerada: {os.path.join(output_dir, project_name + '.scad')}"]
        return await _generate_and_export(scad_code, output_dir, project_name, results,
                                          png_args=["--autocenter", "--viewall", "--projection=ortho"])

    elif name == "generate_finger_test":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "finger_test")
        scad_code = generate_finger_test_scad(config)
        results   = [f"🔧 Pente de finger joints gerado: {os.path.join(output_dir, project_name + '.scad')}"]
        return await _generate_and_export(scad_code, output_dir, project_name, results,
                                          png_args=["--autocenter", "--viewall", "--projection=ortho"])

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
        scad_code = generate_3d_box_scad(config)
        results   = [f"📦 Caixa 3D gerada: {os.path.join(output_dir, project_name + '.scad')}"]
        return await _generate_and_export(scad_code, output_dir, project_name, results,
                                          export_formats=[("stl", "📐 STL")])

    elif name == "generate_bracket":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "bracket")
        scad_code = generate_bracket_scad(config)
        results   = [f"🔩 Suporte gerado: {os.path.join(output_dir, project_name + '.scad')}"]
        return await _generate_and_export(scad_code, output_dir, project_name, results,
                                          export_formats=[("stl", "📐 STL")])

    elif name == "generate_enclosure":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "enclosure")
        scad_code = generate_enclosure_scad(config)
        results   = [
            f"🖥 Gabinete gerado: {os.path.join(output_dir, project_name + '.scad')}",
            f"  Conectores: {len(config.get('connectors', []))} | Standoffs: {len(config.get('pcb_standoffs', []))}",
        ]
        return await _generate_and_export(scad_code, output_dir, project_name, results,
                                          export_formats=[("stl", "📐 STL")])

    elif name == "generate_living_hinge":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "living_hinge")
        scad_code = generate_living_hinge_scad(config)
        results   = [f"🔗 Living hinge gerado: {os.path.join(output_dir, project_name + '.scad')}"]
        return await _generate_and_export(scad_code, output_dir, project_name, results,
                                          png_args=["--autocenter", "--viewall", "--projection=ortho"])

    elif name == "generate_dogbone":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "dogbone")
        scad_code = generate_dogbone_scad(config)
        results   = [f"🦴 Dogbone pocket gerado: {os.path.join(output_dir, project_name + '.scad')}"]
        return await _generate_and_export(scad_code, output_dir, project_name, results,
                                          png_args=["--autocenter", "--viewall", "--projection=ortho"])

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

    elif name == "generate_tolerance_test":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "tolerance_test")
        scad_code = generate_tolerance_test_scad(config)
        results   = [f"🔬 Placa de tolerância gerada: {os.path.join(output_dir, project_name + '.scad')}"]
        return await _generate_and_export(scad_code, output_dir, project_name, results,
                                          export_formats=[("stl", "📐 STL")])

    elif name == "generate_bed_level_test":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "bed_level_test")
        scad_code = generate_bed_level_test_scad(config)
        results   = [f"📏 Teste de nivelamento gerado: {os.path.join(output_dir, project_name + '.scad')}"]
        return await _generate_and_export(scad_code, output_dir, project_name, results,
                                          export_formats=[("stl", "📐 STL")])

    elif name == "generate_retraction_test":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "retraction_test")
        scad_code = generate_retraction_test_scad(config)
        results   = [f"🗼 Torre de retração gerada: {os.path.join(output_dir, project_name + '.scad')}"]
        return await _generate_and_export(scad_code, output_dir, project_name, results,
                                          export_formats=[("stl", "📐 STL")])

    elif name == "suggest_orientation":
        if not arguments or "config" not in arguments:
            raise ValueError("Missing 'config'")
        r = suggest_orientation(arguments["config"])
        lines = [r["summary"], ""]
        for o in r["all_orientations"]:
            marker = "👉 " if o == r["recommended"] else "   "
            lines.append(f"{marker}{o['name']} — score: {o['score']}")
            lines.append(f"      Base: {o['base_area_mm2']}mm² | Altura: {o['height_mm']}mm")
            for n in o["notes"]:
                lines.append(f"      {n}")
            lines.append("")
        return [types.TextContent(type="text", text="\n".join(lines))]

    elif name == "generate_assembly":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "assembly")
        os.makedirs(output_dir, exist_ok=True)

        scad_assembly, piece_scads, bom_md = generate_assembly_scad(config)

        # Save assembly SCAD
        scad_path = os.path.join(output_dir, f"{project_name}.scad")
        with open(scad_path, "w") as f:
            f.write(scad_assembly)

        results = [f"🏗 Assembly gerado: {scad_path}"]

        # Save individual pieces
        pieces_dir = os.path.join(output_dir, "pieces")
        os.makedirs(pieces_dir, exist_ok=True)
        for pname, pscad in piece_scads.items():
            ppath = os.path.join(pieces_dir, f"{pname}.scad")
            with open(ppath, "w") as f:
                f.write(pscad)
            results.append(f"  📦 Peça: {ppath}")

        # Save BOM
        bom_path = os.path.join(output_dir, f"{project_name}_bom.md")
        with open(bom_path, "w") as f:
            f.write(bom_md)
        results.append(f"📋 BOM: {bom_path}")

        return await _generate_and_export(scad_assembly, output_dir, project_name, results,
                                          export_formats=[("stl", "📐 STL assembly")])

    elif name == "generate_cnc_toolpath_hints":
        if not arguments or "config" not in arguments:
            raise ValueError("Missing 'config'")
        r = generate_cnc_toolpath_hints(arguments["config"])
        lines = [r["summary"], ""]
        p = r["parameters"]
        lines.append("📊 Parâmetros recomendados:")
        lines.append(f"  Feed rate:    {p['feed_rate_mm_min']} mm/min")
        lines.append(f"  Plunge rate:  {p['plunge_rate_mm_min']} mm/min")
        lines.append(f"  Spindle RPM:  {p['spindle_rpm']}")
        lines.append(f"  DOC/passe:    {p['depth_per_pass_mm']}mm × {p['num_passes']} passes")
        lines.append(f"  Stepover:     {p['stepover_mm']}mm ({p['stepover_pct']:.0f}%)")
        lines.append(f"  Chip load:    {p['chip_load_mm']}mm")
        lines.append("")

        if r["tabs"]:
            t = r["tabs"][0]
            lines.append(f"📌 Tabs: {t['width_mm']}mm × {t['height_mm']}mm")
            lines.append(f"   {t['note']}")
            lines.append("")

        if r["finishing"]:
            f_data = r["finishing"]
            lines.append(f"✨ Passe de acabamento:")
            lines.append(f"   Feed: {f_data['feed_rate_mm_min']} mm/min | DOC: {f_data['depth_per_pass_mm']}mm")
            lines.append(f"   {f_data['note']}")
            lines.append("")

        lines.append(f"📝 {r['notes']}")
        lines.append("")
        lines.append("⚠ Segurança:")
        for s in r["safety"]:
            lines.append(f"  {s}")

        return [types.TextContent(type="text", text="\n".join(lines))]

    elif name == "analyze_mesh":
        if not arguments.get("stl_path") and not arguments.get("scad_code"):
            raise ValueError("Forneça 'stl_path' ou 'scad_code'.")

        overhang_deg = arguments.get("overhang_deg", 45.0)
        bed_tol = arguments.get("bed_tol", 0.3)
        layer_h = arguments.get("layer_h", 0.2)

        tmp_generated = None
        try:
            target_path, tmp_generated = await _resolve_stl_input(arguments)
            result = analyze_mesh(target_path, overhang_deg=overhang_deg, bed_tol=bed_tol, layer_h=layer_h)
            return [types.TextContent(type="text", text=_format_mesh_analysis(result))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"❌ {e}")]
        finally:
            if tmp_generated and os.path.exists(tmp_generated):
                try:
                    os.remove(tmp_generated)
                except Exception:
                    pass

    elif name == "mesh_section":
        if not arguments.get("stl_path") and not arguments.get("scad_code"):
            raise ValueError("Forneça 'stl_path' ou 'scad_code'.")

        z = arguments.get("z")
        z_list = arguments.get("z_list")
        if z is None and not z_list:
            raise ValueError("Forneça 'z' ou 'z_list'.")
        zs = list(z_list) if z_list else [z]
        axis = arguments.get("axis", "z")
        center = arguments.get("center")

        tmp_generated = None
        try:
            target_path, tmp_generated = await _resolve_stl_input(arguments)
            result = mesh_section(target_path, zs, axis=axis, center=center)
            return [types.TextContent(type="text", text=_format_mesh_section(result))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"❌ {e}")]
        finally:
            if tmp_generated and os.path.exists(tmp_generated):
                try:
                    os.remove(tmp_generated)
                except Exception:
                    pass

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-openscad",
                server_version="0.8.1",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main_sync():
    """Synchronous entry point for PyPI script installation."""
    asyncio.run(main())

if __name__ == "__main__":
    main_sync()
