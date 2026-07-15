import os
import subprocess
import tempfile
import asyncio
import math
import json
import shutil
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
# Gerador inteligente de SCAD para laser cutting
# ──────────────────────────────────────────────

def generate_laser_scad(config: dict) -> str:
    """
    Gera código OpenSCAD completo (2D layout + 3D assembly) a partir de um config dict.

    Config esperado:
    {
      "material_thickness": 3,        # espessura do MDF/acrílico em mm
      "kerf": 0.2,                    # compensação de kerf (slot = thickness - kerf)
      "width":  100,
      "depth":  100,
      "height": 80,
      "fingers": 5,                   # número de dentes por aresta horizontal/vertical
      "openings": [                   # lista de aberturas nas paredes
        {
          "wall": "front",            # front | back | left | right
          "shape": "rect",            # rect | circle
          "x": 35, "y": 0,           # posição (x a partir da esquerda, y a partir de baixo)
          "w": 30, "h": 45           # para rect: largura e altura
        },
        {
          "wall": "front",
          "shape": "circle",
          "cx": 50, "cy": 62,        # centro
          "d": 20                     # diâmetro
        },
        {
          "wall": "back",
          "shape": "circle",
          "cx": 50, "cy": 40,
          "d": 30
        }
      ]
    }
    """
    t   = config.get("material_thickness", 3)
    kerf = config.get("kerf", 0.2)
    W   = config.get("width",  100)
    D   = config.get("depth",  100)
    H   = config.get("height", 80)
    N   = config.get("fingers", 5)
    openings = config.get("openings", [])

    slot = t - kerf      # encaixe por pressão
    gap  = 15            # espaço entre peças no layout

    # Helpers Python para gerar lógica de dentes
    def finger_loop_with_exclusions(total_len, n_fingers, exclusions, axis='x',
                                    is_tab=True, depth=None):
        """
        Gera bloco SCAD de dentes ou fendas evitando regiões de abertura.
        exclusions: list of (start, end) intervals a evitar (no eixo `axis`)
        is_tab: True = dente (sai para fora), False = fenda (corta para dentro)
        """
        if depth is None:
            depth = t
        fw = total_len / n_fingers
        lines = []
        for i in range(0, n_fingers, 2):  # dentes em índices pares
            x0 = 0 if i == 0 else i * fw - kerf / 2
            x1 = total_len if i == n_fingers - 1 else (i + 1) * fw + kerf / 2
            center = (x0 + x1) / 2
            # verifica se o centro cai dentro de alguma abertura
            blocked = any(ex_s <= center <= ex_e for (ex_s, ex_e) in exclusions)
            if blocked:
                continue
            if axis == 'x':
                if is_tab:
                    lines.append(f"        translate([{x0:.4f}, {-depth:.4f}]) square([{x1-x0:.4f}, {depth:.4f}]);")
                else:
                    lines.append(f"        translate([{x0:.4f}, 0]) square([{x1-x0:.4f}, {slot:.4f}]);")
            else:  # y axis (lateral)
                if is_tab:
                    lines.append(f"        translate([{-depth:.4f}, {x0:.4f}]) square([{depth:.4f}, {x1-x0:.4f}]);")
                else:
                    lines.append(f"        translate([0, {x0:.4f}]) square([{slot:.4f}, {x1-x0:.4f}]);")
        return "\n".join(lines)

    def side_finger_loop(total_len, n_fingers, is_tab=True, depth=None, side='left'):
        """Dentes/fendas nas laterais (eixo Y das paredes front/back)."""
        if depth is None:
            depth = t
        fw = total_len / n_fingers
        lines = []
        for i in range(1, n_fingers, 2):  # dentes ímpares nas laterais
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
        """Gera o código SCAD do recorte de uma abertura."""
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
        """Retorna intervalos X bloqueados por aberturas que tocam y=0 (baixo da parede)."""
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

    # ── Coletar aberturas por parede ──
    def ops_for(wall):
        return [op for op in openings if op.get("wall") == wall]

    front_ops = ops_for("front")
    back_ops  = ops_for("back")

    front_excl = x_exclusions_for_wall("front", W)
    back_excl  = x_exclusions_for_wall("back",  W)

    side_w = D - 2 * t

    # ── Gerar módulos 2D ──
    front_tabs  = finger_loop_with_exclusions(W, N, front_excl, axis='x', is_tab=True)
    back_tabs   = finger_loop_with_exclusions(W, N, back_excl,  axis='x', is_tab=True)
    floor_f_slots = finger_loop_with_exclusions(W, N, front_excl, axis='x', is_tab=False)
    floor_b_slots = finger_loop_with_exclusions(W, N, back_excl,  axis='x', is_tab=False)

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
            // Dentes laterais para encaixe com paredes laterais
{side_finger_loop(H, N, is_tab=False, depth=slot, side='left').replace('square', 'square')}
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
        // (gerado com translate)
{chr(10).join("        translate([" + ln.strip().split("translate([")[1].split(", 0])")[0] + f", D-slot]) square([" + ln.strip().split("square([")[1].split("])")[0] + f"]);" if "translate" in ln else "" for ln in floor_b_slots.splitlines() if ln.strip())}
        // Fendas paredes laterais (x=0 e x=W-slot)
{finger_loop_with_exclusions(side_w, N, [], axis='y', is_tab=False)}
    }}
}}

// ── Layout 2D ───────────────────────────────────────────────
module layout_2d() {{
    // Linha 1
    translate([0, 0])         front_wall();
    translate([W+gap, 0])     back_wall();
    translate([2*(W+gap), 0]) floor_base();
    // Linha 2
    y2 = H + gap;
    translate([0, y2])            side_wall();
    translate([side_w+gap, y2])   side_wall();
    // Discos das janelas (peças soltas – abas/tampas)
    y3 = y2 + H + gap;
    x_disk = 0;
"""

    # adicionar os discos das janelas circulares
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
    // Piso
    color([0.9,0.8,0.6])
        translate([0, 0, -t])
            linear_extrude(t) floor_base();
    // Parede Frontal
    color([0.9,0.6,0.4])
        translate([0, t, 0])
            rotate([90,0,0])
                linear_extrude(t) front_wall();
    // Parede Traseira
    color([0.9,0.5,0.4])
        translate([0, D, 0])
            rotate([90,0,0])
                linear_extrude(t) back_wall();
    // Parede Lateral Esquerda
    color([0.8,0.5,0.4])
        translate([0, t, 0])
            rotate([90,0,90])
                linear_extrude(t) side_wall();
    // Parede Lateral Direita
    color([0.8,0.4,0.6])
        translate([W-t, t, 0])
            rotate([90,0,90])
                linear_extrude(t) side_wall();
}}

// Modo de renderização: "2d" ou "3d"
RENDER_MODE = "3d";

if (RENDER_MODE == "2d") {{
    layout_2d();
}} else {{
    assembly_3d();
}}
"""

    return scad


# ──────────────────────────────────────────────
# Validador: detecta peças soltas / slots órfãos
# ──────────────────────────────────────────────
def validate_config(config: dict) -> list[str]:
    """Retorna lista de avisos sobre problemas detectados."""
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
            # verifica dentes no eixo x da parede
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
# Registro das ferramentas MCP
# ──────────────────────────────────────────────
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="render_to_png",
            description="Render OpenSCAD code to a PNG image preview.",
            inputSchema={
                "type": "object",
                "properties": {
                    "variables": {"type": "object", "description": "Optional dictionary of variables to pass to OpenSCAD (-D name=value)"},
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
                    "output_path": {"type": "string", "description": "Absolute path to save the .stl file"}
                },
                "required": ["scad_code", "output_path"]
            }
        ),
        types.Tool(
            name="export_3mf",
            description="Export 3D OpenSCAD code to a 3MF file for modern 3D printing.",
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
                    "scad_code": {"type": "string", "description": "The OpenSCAD source code (must be 2D)"},
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
                    "scad_code": {"type": "string", "description": "The OpenSCAD source code (must be 2D)"},
                    "output_path": {"type": "string"}
                },
                "required": ["scad_code", "output_path"]
            }
        ),
        # ─── NOVA FERRAMENTA INTELIGENTE ───────────────────────
        types.Tool(
            name="generate_laser_part",
            description=(
                "Gera automaticamente um projeto completo para corte a laser a partir de um "
                "config JSON. Produz: código SCAD (2D layout + 3D assembly), valida se há "
                "peças soltas ou dentes sob aberturas, e exporta SVG + DXF prontos para "
                "a máquina laser. Ideal para caixas, casas, painéis com portas e janelas."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": (
                            "Configuração do projeto. Campos:\n"
                            "  material_thickness (mm, default 3)\n"
                            "  kerf (mm, default 0.2 — ajuste pelo seu teste de kerf)\n"
                            "  width, depth, height (mm)\n"
                            "  fingers (número de dentes por aresta, default 5)\n"
                            "  openings: lista de aberturas. Cada uma tem:\n"
                            "    wall: 'front'|'back'|'left'|'right'\n"
                            "    shape: 'rect'|'circle'\n"
                            "    Para rect: x, y, w, h\n"
                            "    Para circle: cx, cy, d\n"
                        ),
                        "properties": {
                            "material_thickness": {"type": "number"},
                            "kerf": {"type": "number"},
                            "width": {"type": "number"},
                            "depth": {"type": "number"},
                            "height": {"type": "number"},
                            "fingers": {"type": "integer"},
                            "openings": {
                                "type": "array",
                                "items": {"type": "object"}
                            }
                        },
                        "required": ["width", "depth", "height"]
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Diretório onde salvar os arquivos gerados (.scad, .svg, .dxf)"
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Nome base dos arquivos gerados (ex: 'house', 'caixa_ferramentas')"
                    }
                },
                "required": ["config", "output_dir", "project_name"]
            }
        ),
        types.Tool(
            name="validate_laser_config",
            description=(
                "Valida um config de laser cutting ANTES de gerar os arquivos. "
                "Detecta: dentes que cairiam sob aberturas (peças soltas), "
                "aberturas fora dos limites das paredes, e outros problemas geométricos. "
                "Use antes de generate_laser_part para antecipar erros."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": "Mesmo formato do generate_laser_part"
                    }
                },
                "required": ["config"]
            }
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:

    # ── Ferramentas originais ──────────────────────────────────
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
                out_path, stdout = run_openscad(scad_code, "png", ["--autocenter", "--viewall"] + extra_args)
                with open(out_path, "rb") as f:
                    import base64
                    img_data = base64.b64encode(f.read()).decode("utf-8")
                os.remove(out_path)
                return [
                    types.TextContent(type="text", text="Rendered successfully."),
                    types.ImageContent(type="image", data=img_data, mimeType="image/png")
                ]
            except Exception as e:
                return [types.TextContent(type="text", text=str(e))]

        else:  # export_*
            if "output_path" not in arguments:
                raise ValueError("Missing 'output_path' argument")
            output_path = arguments["output_path"]
            ext = name.split("_")[1]
            try:
                out_path, stdout = run_openscad(scad_code, ext, extra_args)
                shutil.move(out_path, output_path)
                return [types.TextContent(type="text", text=f"Exported successfully to {output_path}")]
            except Exception as e:
                return [types.TextContent(type="text", text=str(e))]

    # ── validate_laser_config ──────────────────────────────────
    elif name == "validate_laser_config":
        if not arguments or "config" not in arguments:
            raise ValueError("Missing 'config'")
        warnings = validate_config(arguments["config"])
        if warnings:
            msg = "Problemas detectados:\n" + "\n".join(warnings)
        else:
            msg = "✅ Configuração válida — nenhum problema detectado."
        return [types.TextContent(type="text", text=msg)]

    # ── generate_laser_part ────────────────────────────────────
    elif name == "generate_laser_part":
        if not arguments:
            raise ValueError("Missing arguments")
        config       = arguments.get("config", {})
        output_dir   = arguments.get("output_dir", "/tmp")
        project_name = arguments.get("project_name", "laser_part")

        os.makedirs(output_dir, exist_ok=True)

        # 1. Validar
        warnings = validate_config(config)

        # 2. Gerar SCAD
        scad_code = generate_laser_scad(config)
        scad_path = os.path.join(output_dir, f"{project_name}.scad")
        with open(scad_path, "w") as f:
            f.write(scad_code)

        results = [f"📄 SCAD gerado: {scad_path}"]
        if warnings:
            results.append("⚠ Avisos:\n" + "\n".join(warnings))

        # 3. Layout 2D → SVG
        scad_2d = scad_code.replace('RENDER_MODE = "3d"', 'RENDER_MODE = "2d"')
        try:
            svg_path = os.path.join(output_dir, f"{project_name}.svg")
            out_path, _ = run_openscad(scad_2d, "svg")
            shutil.move(out_path, svg_path)
            results.append(f"🖼 SVG gerado: {svg_path}")
        except Exception as e:
            results.append(f"❌ Erro SVG: {e}")

        # 4. Layout 2D → DXF
        try:
            dxf_path = os.path.join(output_dir, f"{project_name}.dxf")
            out_path, _ = run_openscad(scad_2d, "dxf")
            shutil.move(out_path, dxf_path)
            results.append(f"📐 DXF gerado: {dxf_path}")
        except Exception as e:
            results.append(f"❌ Erro DXF: {e}")

        # 5. Preview 3D PNG
        try:
            out_path, _ = run_openscad(scad_code, "png", ["--autocenter", "--viewall"])
            import base64
            with open(out_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            os.remove(out_path)
            return [
                types.TextContent(type="text", text="\n".join(results)),
                types.ImageContent(type="image", data=img_data, mimeType="image/png")
            ]
        except Exception as e:
            results.append(f"❌ Erro PNG: {e}")
            return [types.TextContent(type="text", text="\n".join(results))]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-openscad",
                server_version="0.2.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
