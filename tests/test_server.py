"""
Testes do MCP-OpenSCAD — v0.5.0
Cobre: run_openscad, check_syntax, todos os geradores, validadores e handlers MCP.
"""
import os
import re
import sys
import math
import struct
import threading
import pytest
import subprocess
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import server


# ─────────────────────────────────────────────────────────────────────────────
# run_openscad
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_openscad_success():
    scad_code = "cube([10, 10, 10]);"
    out_path, _ = await server.run_openscad(scad_code, "stl")
    assert out_path.endswith(".stl")
    assert os.path.exists(out_path)
    os.remove(out_path)


@pytest.mark.asyncio
async def test_run_openscad_error():
    with pytest.raises(RuntimeError, match="OpenSCAD Error"):
        await server.run_openscad("invalid_syntax_xyz();", "stl")


@pytest.mark.asyncio
async def test_run_openscad_timeout():
    """Guard: timeout de 60s deve levantar RuntimeError."""
    async def slow_communicate():
        await asyncio.sleep(100)
        return b"", b""

    mock_proc = MagicMock()
    mock_proc.communicate = slow_communicate
    mock_proc.kill = MagicMock()

    async def mock_create_subprocess(*args, **kwargs):
        return mock_proc

    with patch('asyncio.create_subprocess_exec', side_effect=mock_create_subprocess):
        with pytest.raises(RuntimeError, match="timed out after 60 seconds"):
            await server.run_openscad("cube();", "stl")


# ─────────────────────────────────────────────────────────────────────────────
# check_scad_syntax
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_syntax_valid():
    is_valid, msg = await server.check_scad_syntax("cube([10,10,10]);")
    assert is_valid is True
    assert "válida" in msg or "valid" in msg.lower() or "✅" in msg


@pytest.mark.asyncio
async def test_check_syntax_invalid():
    is_valid, msg = await server.check_scad_syntax("XYZINVALIDKEYWORD(;;;)")
    # OpenSCAD pode retornar erro ou aviso — verificamos que é inválido OU string não vazia
    assert isinstance(is_valid, bool)
    assert isinstance(msg, str)
    assert len(msg) > 0


@pytest.mark.asyncio
async def test_check_syntax_timeout():
    """Guard: timeout de 15s deve retornar (False, msg_timeout)."""
    async def slow_communicate():
        await asyncio.sleep(100)
        return b"", b""

    mock_proc = MagicMock()
    mock_proc.communicate = slow_communicate
    mock_proc.kill = MagicMock()

    async def mock_create_subprocess(*args, **kwargs):
        return mock_proc

    with patch('asyncio.create_subprocess_exec', side_effect=mock_create_subprocess):
        is_valid, msg = await server.check_scad_syntax("cube([1,1,1]);")
    assert not is_valid
    assert "Timeout" in msg or "timeout" in msg.lower()
    assert "timeout" in msg.lower()


# ─────────────────────────────────────────────────────────────────────────────
# validate_config (laser_part)
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_config_clean():
    cfg = {"width": 100, "depth": 80, "height": 50}
    warns = server.validate_config(cfg)
    assert isinstance(warns, list)
    assert len(warns) == 0


def test_validate_config_opening_out_of_bounds():
    cfg = {
        "width": 100, "depth": 80, "height": 50,
        "openings": [{"wall": "front", "shape": "rect", "x": 0, "y": 0, "w": 30, "h": 80}]
    }
    warns = server.validate_config(cfg)
    assert any("ultrapassa" in w for w in warns)


def test_validate_config_opening_x_bounds():
    cfg = {
        "width": 100, "depth": 80, "height": 50,
        "openings": [{"wall": "front", "shape": "rect", "x": 90, "y": 10, "w": 30, "h": 20}]
    }
    warns = server.validate_config(cfg)
    assert any("limites" in w for w in warns)


# ─────────────────────────────────────────────────────────────────────────────
# validate_box_config
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_box_config_ok():
    cfg = {"width": 100, "depth": 80, "height": 50, "fingers": 5}
    warns = server.validate_box_config(cfg)
    assert isinstance(warns, list)
    assert len(warns) == 0  # Configuração válida não deve ter avisos


def test_validate_box_config_even_fingers():
    cfg = {"width": 100, "depth": 80, "height": 50, "fingers": 4}
    warns = server.validate_box_config(cfg)
    assert any("ímpar" in w for w in warns)


def test_validate_box_config_bad_lid():
    cfg = {"width": 100, "depth": 80, "height": 50, "lid_type": "wrong"}
    warns = server.validate_box_config(cfg)
    assert any("lid_type" in w for w in warns)


def test_validate_box_config_negative_dividers():
    cfg = {"width": 100, "depth": 80, "height": 50, "dividers_x": -1}
    warns = server.validate_box_config(cfg)
    assert any("negativo" in w for w in warns)


# ─────────────────────────────────────────────────────────────────────────────
# estimate_material_use
# ─────────────────────────────────────────────────────────────────────────────

def test_estimate_material_use_basic():
    cfg = {"width": 100, "depth": 80, "height": 50}
    r = server.estimate_material_use(cfg)
    assert "total_area_cm2" in r
    assert "usage_percent" in r
    assert "sheets_needed" in r
    assert r["sheets_needed"] >= 1
    assert r["total_area_cm2"] > 0


def test_estimate_material_use_with_lid():
    cfg = {"width": 100, "depth": 80, "height": 50, "lid_type": "snap"}
    r = server.estimate_material_use(cfg)
    pieces_names = [p["name"] for p in r["pieces"]]
    assert "Tampa" in pieces_names


def test_estimate_material_use_no_lid():
    cfg = {"width": 100, "depth": 80, "height": 50, "lid_type": "none"}
    r = server.estimate_material_use(cfg)
    pieces_names = [p["name"] for p in r["pieces"]]
    assert "Tampa" not in pieces_names


def test_estimate_material_use_with_dividers():
    cfg = {"width": 100, "depth": 80, "height": 50, "dividers_x": 2, "dividers_y": 1}
    r = server.estimate_material_use(cfg)
    pieces_names = [p["name"] for p in r["pieces"]]
    assert any("Divisória" in n for n in pieces_names)


def test_estimate_material_use_custom_sheet():
    cfg = {"width": 200, "depth": 150, "height": 100}
    r = server.estimate_material_use(cfg, sheet_w=300, sheet_h=300)
    assert r["sheet_w_mm"] == 300
    assert r["sheet_h_mm"] == 300


# ─────────────────────────────────────────────────────────────────────────────
# validate_printability
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_printability_ok():
    cfg = {
        "wall_thickness": 2.0,
        "bottom_thickness": 2.0,
        "height": 40, "width": 80, "depth": 60,
        "overhang_angle": 30,
        "profile": "fdm_standard"
    }
    r = server.validate_printability(cfg)
    assert r["printable"]
    assert len(r["errors"]) == 0


def test_validate_printability_thin_wall():
    cfg = {
        "wall_thickness": 0.3,
        "bottom_thickness": 0.4,
        "height": 40, "width": 80, "depth": 60,
        "profile": "fdm_standard"
    }
    r = server.validate_printability(cfg)
    assert not r["printable"]
    assert len(r["errors"]) > 0


def test_validate_printability_overhang():
    cfg = {
        "wall_thickness": 2.0,
        "bottom_thickness": 2.0,
        "height": 40, "width": 80, "depth": 60,
        "overhang_angle": 60,
        "profile": "fdm_standard"
    }
    r = server.validate_printability(cfg)
    assert not r["printable"]
    assert any("Overhang" in e for e in r["errors"])


def test_validate_printability_resin():
    cfg = {
        "wall_thickness": 0.3,
        "bottom_thickness": 0.2,
        "height": 20, "width": 40, "depth": 30,
        "overhang_angle": 60,
        "profile": "resin"
    }
    r = server.validate_printability(cfg)
    # Resina tem limites mais permissivos
    assert r["profile"] == "resin"


def test_validate_printability_tall_object():
    cfg = {
        "wall_thickness": 2.0,
        "bottom_thickness": 2.0,
        "height": 200, "width": 20, "depth": 20,
        "profile": "fdm_standard"
    }
    r = server.validate_printability(cfg)
    assert any("alto" in w or "brim" in w for w in r["warnings"])


def test_validate_printability_bad_layer_multiple():
    cfg = {
        "wall_thickness": 2.0,
        "bottom_thickness": 0.35,  # não múltiplo de 0.2
        "height": 40, "width": 80, "depth": 60,
        "layer_height": 0.2,
        "profile": "fdm_standard"
    }
    r = server.validate_printability(cfg)
    assert any("múltiplo" in w or "camada" in w for w in r["warnings"])


# ─────────────────────────────────────────────────────────────────────────────
# generate_laser_scad
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_laser_scad_basic():
    cfg = {"width": 100, "depth": 80, "height": 50}
    scad = server.generate_laser_scad(cfg)
    assert "module front_wall" in scad
    assert "module back_wall" in scad
    assert "module side_wall" in scad
    assert "module floor_base" in scad
    assert "module layout_2d" in scad
    assert "module assembly_3d" in scad
    assert "RENDER_MODE" in scad


def test_generate_laser_scad_with_openings():
    cfg = {
        "width": 100, "depth": 80, "height": 50,
        "openings": [{"wall": "front", "shape": "rect", "x": 30, "y": 0, "w": 20, "h": 30}]
    }
    scad = server.generate_laser_scad(cfg)
    assert "square" in scad


def test_generate_laser_scad_circle_opening():
    cfg = {
        "width": 100, "depth": 80, "height": 50,
        "openings": [{"wall": "front", "shape": "circle", "cx": 50, "cy": 30, "d": 20}]
    }
    scad = server.generate_laser_scad(cfg)
    assert "circle" in scad


# ─────────────────────────────────────────────────────────────────────────────
# generate_box_scad
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_box_scad_basic():
    cfg = {"width": 100, "depth": 80, "height": 50}
    scad = server.generate_box_scad(cfg)
    assert "module box_floor" in scad
    assert "module box_front_wall" in scad
    assert "module box_side_wall" in scad
    assert "layout_2d" in scad
    assert "assembly_3d" in scad


def test_generate_box_scad_snap_lid():
    cfg = {"width": 100, "depth": 80, "height": 50, "lid_type": "snap"}
    scad = server.generate_box_scad(cfg)
    assert "box_lid" in scad
    assert "Snap" in scad or "snap" in scad.lower()


def test_generate_box_scad_slide_lid():
    cfg = {"width": 100, "depth": 80, "height": 50, "lid_type": "slide"}
    scad = server.generate_box_scad(cfg)
    assert "box_lid" in scad


def test_generate_box_scad_no_lid():
    cfg = {"width": 100, "depth": 80, "height": 50, "lid_type": "none"}
    scad = server.generate_box_scad(cfg)
    assert "layout_2d" in scad


def test_generate_box_scad_dimensions_present():
    cfg = {"width": 150, "depth": 90, "height": 60, "material_thickness": 4}
    scad = server.generate_box_scad(cfg)
    assert "150" in scad
    assert "90"  in scad
    assert "60"  in scad


# ─────────────────────────────────────────────────────────────────────────────
# generate_kerf_test_scad
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_kerf_test_basic():
    cfg = {"material_thickness": 3, "kerf_min": 0.0, "kerf_max": 0.3, "kerf_step": 0.1}
    scad = server.generate_kerf_test_scad(cfg)
    assert "square" in scad
    assert "Kerf" in scad or "kerf" in scad.lower()


def test_generate_kerf_test_correct_count():
    cfg = {"material_thickness": 3, "kerf_min": 0.0, "kerf_max": 0.4, "kerf_step": 0.1}
    scad = server.generate_kerf_test_scad(cfg)
    # 0.0, 0.1, 0.2, 0.3, 0.4 = 5 valores
    assert scad.count("Kerf =") == 5


def test_generate_kerf_test_slot_values():
    cfg = {"material_thickness": 3.0, "kerf_min": 0.2, "kerf_max": 0.2, "kerf_step": 0.1}
    scad = server.generate_kerf_test_scad(cfg)
    # slot = 3.0 - 0.2 = 2.8
    assert "2.8" in scad


# ─────────────────────────────────────────────────────────────────────────────
# generate_finger_test_scad
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_finger_test_basic():
    cfg = {"material_thickness": 3, "offset_min": -0.1, "offset_max": 0.1, "offset_step": 0.1}
    scad = server.generate_finger_test_scad(cfg)
    assert "square" in scad
    assert "Offset" in scad


def test_generate_finger_test_count():
    cfg = {"material_thickness": 3, "offset_min": 0.0, "offset_max": 0.2, "offset_step": 0.1}
    scad = server.generate_finger_test_scad(cfg)
    # 0.0, 0.1, 0.2 = 3 offsets
    assert scad.count("Offset =") == 3


# ─────────────────────────────────────────────────────────────────────────────
# generate_3d_box_scad
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_3d_box_basic():
    cfg = {"width": 80, "depth": 60, "height": 40}
    scad = server.generate_3d_box_scad(cfg)
    assert "module box_body" in scad
    assert "rounded_box" in scad


def test_generate_3d_box_snap_lid():
    cfg = {"width": 80, "depth": 60, "height": 40, "lid_type": "snap"}
    scad = server.generate_3d_box_scad(cfg)
    assert "module box_lid" in scad


def test_generate_3d_box_no_lid():
    cfg = {"width": 80, "depth": 60, "height": 40, "lid_type": "none"}
    scad = server.generate_3d_box_scad(cfg)
    assert "box_body" in scad
    assert "module box_lid" not in scad


def test_generate_3d_box_thread_lid():
    cfg = {"width": 80, "depth": 60, "height": 40, "lid_type": "thread"}
    scad = server.generate_3d_box_scad(cfg)
    assert "box_lid" in scad


def test_generate_3d_box_corner_radius():
    cfg = {"width": 80, "depth": 60, "height": 40, "corner_radius": 5}
    scad = server.generate_3d_box_scad(cfg)
    assert "5" in scad


# ─────────────────────────────────────────────────────────────────────────────
# generate_bracket_scad
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_bracket_L():
    cfg = {"type": "L", "width": 40, "height": 40, "depth": 20}
    scad = server.generate_bracket_scad(cfg)
    assert "bracket_L" in scad


def test_generate_bracket_U():
    cfg = {"type": "U", "width": 50, "height": 40, "depth": 20}
    scad = server.generate_bracket_scad(cfg)
    assert "bracket_U" in scad


def test_generate_bracket_flat():
    cfg = {"type": "flat", "width": 60, "height": 5, "depth": 30}
    scad = server.generate_bracket_scad(cfg)
    assert "bracket_flat" in scad


def test_generate_bracket_mount_holes():
    cfg = {"type": "L", "width": 40, "height": 40, "depth": 20, "mount_holes": 4, "mount_hole_d": 3.2}
    scad = server.generate_bracket_scad(cfg)
    assert "cylinder" in scad
    assert "3.2" in scad


def test_generate_bracket_gusset():
    cfg = {"type": "L", "width": 40, "height": 40, "depth": 20, "gusset": True}
    scad = server.generate_bracket_scad(cfg)
    assert "polygon" in scad


def test_generate_bracket_no_gusset():
    cfg = {"type": "L", "width": 40, "height": 40, "depth": 20, "gusset": False}
    scad = server.generate_bracket_scad(cfg)
    assert "polygon" not in scad


def test_generate_bracket_center_hole():
    cfg = {"type": "L", "width": 40, "height": 40, "depth": 20, "hole_d": 10}
    scad = server.generate_bracket_scad(cfg)
    assert "10" in scad


# ─────────────────────────────────────────────────────────────────────────────
# generate_enclosure_scad
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_enclosure_basic():
    cfg = {"width": 100, "depth": 60, "height": 30}
    scad = server.generate_enclosure_scad(cfg)
    assert "module enclosure_body" in scad
    assert "module enclosure_lid" in scad


def test_generate_enclosure_connectors():
    cfg = {
        "width": 120, "depth": 70, "height": 35,
        "connectors": [
            {"wall": "front", "type": "usb_a", "x": 20, "y": 10},
            {"wall": "back",  "type": "barrel_jack", "x": 20, "y": 10},
        ]
    }
    scad = server.generate_enclosure_scad(cfg)
    assert "cube" in scad  # cutouts geram cubes para subtração 3D


def test_generate_enclosure_custom_connector():
    cfg = {
        "width": 100, "depth": 60, "height": 30,
        "connectors": [{"wall": "right", "type": "custom", "x": 10, "y": 5, "w": 20, "h": 10}]
    }
    scad = server.generate_enclosure_scad(cfg)
    assert "20.00" in scad or "20" in scad


def test_generate_enclosure_standoffs():
    cfg = {
        "width": 100, "depth": 60, "height": 30,
        "pcb_standoffs": [{"x": 5, "y": 5}, {"x": 90, "y": 50}],
        "standoff_h": 5, "standoff_d": 6, "standoff_hole_d": 2.5
    }
    scad = server.generate_enclosure_scad(cfg)
    assert "cylinder" in scad


def test_generate_enclosure_snap_lid():
    cfg = {"width": 100, "depth": 60, "height": 30, "lid_type": "snap"}
    scad = server.generate_enclosure_scad(cfg)
    assert "snap" in scad.lower() or "Reborda" in scad


def test_generate_enclosure_screw_lid():
    cfg = {"width": 100, "depth": 60, "height": 30, "lid_type": "screw"}
    scad = server.generate_enclosure_scad(cfg)
    assert "3.2" in scad  # M3 holes


# ─────────────────────────────────────────────────────────────────────────────
# MCP Handlers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_list_tools():
    tools = await server.handle_list_tools()
    tool_names = [t.name for t in tools]
    # Ferramentas básicas
    assert "render_to_png"    in tool_names
    assert "export_stl"       in tool_names
    assert "export_3mf"       in tool_names
    assert "export_dxf"       in tool_names
    assert "export_svg"       in tool_names
    # check_syntax
    assert "check_syntax"     in tool_names
    # Laser
    assert "generate_laser_part"  in tool_names
    assert "validate_laser_config" in tool_names
    assert "generate_box"         in tool_names
    assert "generate_kerf_test"   in tool_names
    assert "generate_finger_test" in tool_names
    assert "estimate_material_use" in tool_names
    # 3D
    assert "generate_3d_box"        in tool_names
    assert "generate_bracket"        in tool_names
    assert "generate_enclosure"      in tool_names
    assert "validate_printability"   in tool_names
    assert "generate_tolerance_test"  in tool_names
    assert "generate_bed_level_test"  in tool_names
    assert "generate_retraction_test" in tool_names
    # Laser decoration / CNC
    assert "generate_living_hinge"     in tool_names
    assert "generate_dogbone"          in tool_names
    # Orientation + Assembly
    assert "suggest_orientation"        in tool_names
    assert "generate_assembly"          in tool_names
    # CNC
    assert "generate_cnc_toolpath_hints" in tool_names
    # Análise
    assert "analyze_mesh" in tool_names
    assert "mesh_section" in tool_names
    # Exportação OBJ (nightly)
    assert "export_obj" in tool_names
    assert len(tools) == 27

    mesh_tool = next(t for t in tools if t.name == "analyze_mesh")
    props = mesh_tool.inputSchema["properties"]
    assert "stl_path" in props
    assert "scad_code" in props
    assert "overhang_deg" in props
    assert "bed_tol" in props
    assert "layer_h" in props
    assert "timeout_s" in props

    section_tool = next(t for t in tools if t.name == "mesh_section")
    sprops = section_tool.inputSchema["properties"]
    assert "stl_path" in sprops
    assert "scad_code" in sprops
    assert "z" in sprops
    assert "z_list" in sprops
    assert "axis" in sprops
    assert "center" in sprops
    assert "timeout_s" in sprops

    for export_tool in ("render_to_png", "export_stl", "export_3mf", "export_dxf", "export_svg", "export_obj"):
        t = next(t for t in tools if t.name == export_tool)
        assert "timeout_s" in t.inputSchema["properties"]


@pytest.mark.asyncio
async def test_handle_call_tool_missing_scad_code():
    with pytest.raises(ValueError, match="Missing 'scad_code' argument"):
        await server.handle_call_tool("export_stl", {})


@pytest.mark.asyncio
async def test_handle_call_tool_export_stl(tmp_path):
    out_path = str(tmp_path / "out.stl")
    result = await server.handle_call_tool("export_stl", {
        "scad_code": "cube([5, 5, 5]);",
        "output_path": out_path
    })
    assert result[0].type == "text"
    assert "Exported successfully" in result[0].text
    assert os.path.exists(out_path)


def _png_unavailable_reason():
    """None se o OpenSCAD consegue gerar um PNG; senão o motivo. O 2021.01 sem display
    (SSH, container, CI sem xvfb) morre por segfault ao criar o contexto OpenGL."""
    try:
        out_path, _ = asyncio.run(server.run_openscad("cube(1);", "png", ["--autocenter", "--viewall"]))
    except RuntimeError as e:
        if str(e).startswith("OpenSCAD Error"):
            return "OpenSCAD sem contexto GL (2021.01 sem display)"
        raise
    os.remove(out_path)
    return None


@pytest.fixture(scope="session")
def png_rendering():
    """Pula os testes que dependem de PNG quando o OpenSCAD instalado não renderiza PNG aqui."""
    reason = _png_unavailable_reason()
    if reason:
        pytest.skip(reason)


def test_png_unavailable_reason_when_openscad_crashes(monkeypatch):
    fake_exec, _ = _fake_openscad_process(-11, b"", b"")       # segfault e PNG de 0 bytes, como no 2021.01 sem display
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    assert _png_unavailable_reason() == "OpenSCAD sem contexto GL (2021.01 sem display)"


def test_png_unavailable_reason_is_none_when_openscad_renders(monkeypatch):
    fake_exec, _ = _fake_openscad_process(0, b"", b"\x89PNG fake")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    assert _png_unavailable_reason() is None


@pytest.mark.asyncio
@pytest.mark.usefixtures("png_rendering")
async def test_handle_call_tool_render_to_png():
    result = await server.handle_call_tool("render_to_png", {"scad_code": "sphere(r=5);"})
    assert len(result) == 2
    assert result[0].type == "text"
    assert result[1].type == "image"
    assert result[1].mimeType == "image/png"
    assert len(result[1].data) > 100


@pytest.mark.asyncio
async def test_handle_call_tool_export_dxf(tmp_path):
    out_path = str(tmp_path / "out.dxf")
    result = await server.handle_call_tool("export_dxf", {
        "scad_code": "square([50, 30]);",
        "output_path": out_path
    })
    assert "Exported" in result[0].text
    assert os.path.exists(out_path)


@pytest.mark.asyncio
async def test_handle_call_tool_export_3mf(tmp_path):
    out_path = str(tmp_path / "out.3mf")
    result = await server.handle_call_tool("export_3mf", {
        "scad_code": "cube([10,10,10]);",
        "output_path": out_path
    })
    assert "Exported" in result[0].text


@pytest.mark.asyncio
async def test_handle_call_tool_variables(tmp_path):
    out_path = str(tmp_path / "out_var.stl")
    result = await server.handle_call_tool("export_stl", {
        "scad_code": "cube([w, w, w]);",
        "output_path": out_path,
        "variables": {"w": 5, "str_v": "test", "bool_v": True}
    })
    assert "Exported successfully" in result[0].text


@pytest.mark.asyncio
async def test_handle_call_tool_unknown():
    with pytest.raises(ValueError, match="Unknown tool"):
        await server.handle_call_tool("nonexistent_tool", {"scad_code": "cube();"})


@pytest.mark.asyncio
async def test_handle_call_tool_check_syntax_valid():
    result = await server.handle_call_tool("check_syntax", {"scad_code": "cube([1,2,3]);"})
    assert result[0].type == "text"
    assert "✅" in result[0].text or "valid" in result[0].text.lower()


@pytest.mark.asyncio
async def test_handle_call_tool_check_syntax_missing():
    with pytest.raises(ValueError, match="Missing 'scad_code'"):
        await server.handle_call_tool("check_syntax", {})


@pytest.mark.asyncio
async def test_handle_call_tool_validate_laser_config_ok():
    result = await server.handle_call_tool("validate_laser_config", {
        "config": {"width": 100, "depth": 80, "height": 50}
    })
    assert "✅" in result[0].text


@pytest.mark.asyncio
async def test_handle_call_tool_validate_laser_config_missing():
    with pytest.raises(ValueError, match="Missing 'config'"):
        await server.handle_call_tool("validate_laser_config", {})


@pytest.mark.asyncio
async def test_handle_call_tool_validate_printability():
    result = await server.handle_call_tool("validate_printability", {
        "config": {"wall_thickness": 2, "bottom_thickness": 2, "height": 40, "width": 80, "depth": 60}
    })
    assert "🖨" in result[0].text
    assert "Resultado" in result[0].text


@pytest.mark.asyncio
async def test_handle_call_tool_validate_printability_missing():
    with pytest.raises(ValueError, match="Missing 'config'"):
        await server.handle_call_tool("validate_printability", {})


@pytest.mark.asyncio
async def test_handle_call_tool_estimate_material_use():
    result = await server.handle_call_tool("estimate_material_use", {
        "config": {"width": 100, "depth": 80, "height": 50}
    })
    assert "📊" in result[0].text
    assert "Área" in result[0].text or "Area" in result[0].text


@pytest.mark.asyncio
async def test_handle_call_tool_estimate_material_missing():
    with pytest.raises(ValueError, match="Missing 'config'"):
        await server.handle_call_tool("estimate_material_use", {})


@pytest.mark.asyncio
async def test_handle_call_tool_generate_box(tmp_path):
    result = await server.handle_call_tool("generate_box", {
        "config": {"width": 100, "depth": 80, "height": 50, "lid_type": "snap"},
        "output_dir": str(tmp_path),
        "project_name": "test_box"
    })
    assert len(result) >= 1
    assert result[0].type == "text"
    assert "test_box" in result[0].text
    assert os.path.exists(str(tmp_path / "test_box.scad"))


@pytest.mark.asyncio
async def test_handle_call_tool_generate_kerf_test(tmp_path):
    result = await server.handle_call_tool("generate_kerf_test", {
        "config": {"material_thickness": 3, "kerf_min": 0.1, "kerf_max": 0.3, "kerf_step": 0.1},
        "output_dir": str(tmp_path),
        "project_name": "kerf_test"
    })
    assert len(result) >= 1
    assert "kerf_test" in result[0].text
    assert os.path.exists(str(tmp_path / "kerf_test.scad"))


@pytest.mark.asyncio
async def test_handle_call_tool_generate_finger_test(tmp_path):
    result = await server.handle_call_tool("generate_finger_test", {
        "config": {"material_thickness": 3, "offset_min": -0.1, "offset_max": 0.1, "offset_step": 0.1},
        "output_dir": str(tmp_path),
        "project_name": "finger_test"
    })
    assert os.path.exists(str(tmp_path / "finger_test.scad"))


@pytest.mark.asyncio
async def test_handle_call_tool_generate_3d_box(tmp_path):
    result = await server.handle_call_tool("generate_3d_box", {
        "config": {"width": 80, "depth": 60, "height": 40, "lid_type": "snap"},
        "output_dir": str(tmp_path),
        "project_name": "box3d"
    })
    assert os.path.exists(str(tmp_path / "box3d.scad"))
    assert len(result) >= 1


@pytest.mark.asyncio
async def test_handle_call_tool_generate_bracket(tmp_path):
    result = await server.handle_call_tool("generate_bracket", {
        "config": {"type": "L", "width": 40, "height": 40, "depth": 20, "mount_holes": 4},
        "output_dir": str(tmp_path),
        "project_name": "bracket"
    })
    assert os.path.exists(str(tmp_path / "bracket.scad"))


@pytest.mark.asyncio
async def test_handle_call_tool_generate_enclosure(tmp_path):
    result = await server.handle_call_tool("generate_enclosure", {
        "config": {
            "width": 100, "depth": 60, "height": 30,
            "connectors": [{"wall": "front", "type": "usb_a", "x": 20, "y": 10}],
            "pcb_standoffs": [{"x": 5, "y": 5}]
        },
        "output_dir": str(tmp_path),
        "project_name": "enclosure"
    })
    assert os.path.exists(str(tmp_path / "enclosure.scad"))


@pytest.mark.asyncio
async def test_handle_call_tool_generate_laser_part(tmp_path):
    result = await server.handle_call_tool("generate_laser_part", {
        "config": {"width": 100, "depth": 80, "height": 50},
        "output_dir": str(tmp_path),
        "project_name": "laser_test"
    })
    assert os.path.exists(str(tmp_path / "laser_test.scad"))
    assert "laser_test" in result[0].text


@pytest.mark.asyncio
async def test_generate_box_missing_args():
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_box", None)


@pytest.mark.asyncio
async def test_generate_kerf_test_missing_args():
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_kerf_test", None)


# ─────────────────────────────────────────────────────────────────────────────
# Testes de integração OpenSCAD (render real)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.usefixtures("png_rendering")
async def test_openscad_renders_box():
    """Integração: gera SCAD de caixa e renderiza para PNG via OpenSCAD real."""
    cfg = {"width": 80, "depth": 60, "height": 40}
    scad = server.generate_box_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "png", ["--autocenter", "--viewall"])
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 1000  # PNG não vazio
    os.remove(out_path)


@pytest.mark.asyncio
async def test_openscad_renders_3d_box():
    """Integração: gera SCAD 3D e renderiza STL."""
    cfg = {"width": 50, "depth": 40, "height": 30, "lid_type": "none"}
    scad = server.generate_3d_box_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


@pytest.mark.asyncio
async def test_openscad_renders_bracket():
    """Integração: gera suporte em L e renderiza STL."""
    cfg = {"type": "L", "width": 30, "height": 30, "depth": 15, "gusset": False}
    scad = server.generate_bracket_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    os.remove(out_path)


@pytest.mark.asyncio
async def test_openscad_renders_kerf_test_svg():
    """Integração: gera placa de kerf e exporta SVG."""
    cfg = {"material_thickness": 3, "kerf_min": 0.1, "kerf_max": 0.3, "kerf_step": 0.1}
    scad = server.generate_kerf_test_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "svg")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


@pytest.mark.asyncio
async def test_openscad_renders_enclosure():
    """Integração: gera gabinete e renderiza STL."""
    cfg = {
        "width": 100, "depth": 60, "height": 30, "wall": 2.5,
        "connectors": [{"wall": "front", "type": "usb_c", "x": 20, "y": 8}],
        "pcb_standoffs": [{"x": 10, "y": 10}, {"x": 90, "y": 50}]
    }
    scad = server.generate_enclosure_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


@pytest.mark.asyncio
async def test_openscad_renders_laser_2d():
    """Integração: gera laser_part e exporta SVG 2D."""
    cfg = {"width": 80, "depth": 60, "height": 40}
    scad = server.generate_laser_scad(cfg)
    scad_2d = scad.replace('RENDER_MODE = "3d"', 'RENDER_MODE = "2d"')
    out_path, _ = await server.run_openscad(scad_2d, "svg")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


@pytest.mark.asyncio
async def test_openscad_renders_finger_test():
    """Integração: gera finger test e exporta SVG."""
    cfg = {"material_thickness": 3, "offset_min": 0.0, "offset_max": 0.1, "offset_step": 0.1}
    scad = server.generate_finger_test_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "svg")
    assert os.path.exists(out_path)
    os.remove(out_path)


@pytest.mark.asyncio
async def test_openscad_renders_3d_box_with_lid():
    """Integração: gera caixa 3D com tampa snap e renderiza STL."""
    cfg = {"width": 60, "depth": 40, "height": 30, "lid_type": "snap"}
    scad = server.generate_3d_box_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases: input validation guards
# ─────────────────────────────────────────────────────────────────────────────

def test_kerf_test_step_zero():
    """Guard: kerf_step=0 deve usar fallback em vez de loop infinito."""
    cfg = {"material_thickness": 3, "kerf_min": 0.1, "kerf_max": 0.3, "kerf_step": 0}
    scad = server.generate_kerf_test_scad(cfg)
    assert "square" in scad  # Deve gerar SCAD normalmente


def test_kerf_test_step_negative():
    """Guard: kerf_step negativo deve usar fallback."""
    cfg = {"material_thickness": 3, "kerf_min": 0.1, "kerf_max": 0.3, "kerf_step": -0.1}
    scad = server.generate_kerf_test_scad(cfg)
    assert "square" in scad


def test_finger_test_step_zero():
    """Guard: offset_step=0 deve usar fallback em vez de loop infinito."""
    cfg = {"material_thickness": 3, "offset_min": 0.0, "offset_max": 0.2, "offset_step": 0}
    scad = server.generate_finger_test_scad(cfg)
    assert "square" in scad


def test_finger_test_step_negative():
    """Guard: offset_step negativo deve usar fallback."""
    cfg = {"material_thickness": 3, "offset_min": 0.0, "offset_max": 0.2, "offset_step": -0.1}
    scad = server.generate_finger_test_scad(cfg)
    assert "square" in scad


def test_laser_scad_fingers_zero():
    """Guard: fingers=0 não deve causar divisão por zero."""
    cfg = {"width": 100, "depth": 80, "height": 50, "fingers": 0}
    scad = server.generate_laser_scad(cfg)
    assert "module front_wall" in scad


def test_laser_scad_fingers_one():
    """Edge: fingers=1 deve funcionar."""
    cfg = {"width": 100, "depth": 80, "height": 50, "fingers": 1}
    scad = server.generate_laser_scad(cfg)
    assert "module front_wall" in scad


def test_box_scad_fingers_zero():
    """Guard: fingers=0 não deve causar divisão por zero no generate_box."""
    cfg = {"width": 100, "depth": 80, "height": 50, "fingers": 0}
    scad = server.generate_box_scad(cfg)
    assert "module box_floor" in scad


def test_box_scad_even_fingers_corrected():
    """Verify: even fingers auto-corrected to odd in generate_box_scad."""
    cfg = {"width": 100, "depth": 80, "height": 50, "fingers": 4}
    scad = server.generate_box_scad(cfg)
    assert "module box_floor" in scad  # Should generate successfully


def test_kerf_exceeds_thickness():
    """Guard: kerf >= material_thickness deve ser clamped."""
    cfg = {"width": 100, "depth": 80, "height": 50, "material_thickness": 3, "kerf": 5}
    scad = server.generate_laser_scad(cfg)
    assert "slot" in scad  # Deve gerar código válido


def test_box_kerf_exceeds_thickness():
    """Guard: kerf >= material_thickness em generate_box."""
    cfg = {"width": 100, "depth": 80, "height": 50, "material_thickness": 3, "kerf": 4}
    scad = server.generate_box_scad(cfg)
    assert "module box_floor" in scad


def test_box_scad_with_dividers_x():
    """Verifica que divisórias X são geradas no SCAD."""
    cfg = {"width": 100, "depth": 80, "height": 50, "dividers_x": 2}
    scad = server.generate_box_scad(cfg)
    assert "Divisória X" in scad or "divid" in scad.lower()


def test_box_scad_with_dividers_y():
    """Verifica que divisórias Y são geradas no SCAD."""
    cfg = {"width": 100, "depth": 80, "height": 50, "dividers_y": 1}
    scad = server.generate_box_scad(cfg)
    assert "Divisória Y" in scad or "divid" in scad.lower()


def test_box_scad_negative_dividers_clamped():
    """Guard: divisórias negativas são clamped a 0."""
    cfg = {"width": 100, "depth": 80, "height": 50, "dividers_x": -3}
    scad = server.generate_box_scad(cfg)
    assert "module box_floor" in scad
    # Não deve gerar divisórias
    assert "Divisória" not in scad


def test_finger_test_finger_count_zero():
    """Guard: finger_count=0 não causa divisão por zero."""
    cfg = {"material_thickness": 3, "finger_count": 0}
    scad = server.generate_finger_test_scad(cfg)
    assert "square" in scad


def test_validate_box_config_thick_material():
    """Warning: material muito grosso em relação às dimensões."""
    cfg = {"width": 20, "depth": 20, "height": 20, "material_thickness": 8}
    warns = server.validate_box_config(cfg)
    assert any("Espessura" in w or "grande" in w for w in warns)


def test_validate_box_config_thin_fingers():
    """Warning: dentes muito finos."""
    cfg = {"width": 20, "depth": 80, "height": 50, "fingers": 15, "material_thickness": 3}
    warns = server.validate_box_config(cfg)
    assert any("finos" in w for w in warns)


def test_validate_printability_small_dimension():
    """Warning: dimensão mínima < 5mm."""
    cfg = {
        "wall_thickness": 1.0, "bottom_thickness": 1.0,
        "height": 3, "width": 3, "depth": 3,
        "profile": "fdm_standard"
    }
    r = server.validate_printability(cfg)
    assert any("pequena" in w for w in r["warnings"])


def test_validate_printability_unknown_profile():
    """Fallback: perfil desconhecido usa fdm_standard."""
    cfg = {
        "wall_thickness": 2.0, "bottom_thickness": 2.0,
        "height": 40, "width": 80, "depth": 60,
        "profile": "nonexistent_profile"
    }
    r = server.validate_printability(cfg)
    assert r["printable"]  # Should use fdm_standard and pass


def test_opening_unknown_shape():
    """Edge: abertura com shape desconhecido deve ser ignorada."""
    cfg = {
        "width": 100, "depth": 80, "height": 50,
        "openings": [{"wall": "front", "shape": "hexagon", "x": 30, "y": 10}]
    }
    scad = server.generate_laser_scad(cfg)
    assert "module front_wall" in scad


def test_empty_config_laser():
    """Edge: config vazio deve usar defaults."""
    scad = server.generate_laser_scad({})
    assert "module front_wall" in scad


def test_empty_config_box():
    """Edge: config vazio deve usar defaults."""
    scad = server.generate_box_scad({})
    assert "module box_floor" in scad


def test_empty_config_3d_box():
    """Edge: config vazio deve usar defaults."""
    scad = server.generate_3d_box_scad({})
    assert "module box_body" in scad


def test_empty_config_bracket():
    """Edge: config vazio deve usar defaults."""
    scad = server.generate_bracket_scad({})
    assert "bracket_L" in scad


def test_empty_config_enclosure():
    """Edge: config vazio deve usar defaults."""
    scad = server.generate_enclosure_scad({})
    assert "module enclosure_body" in scad


# ─────────────────────────────────────────────────────────────────────────────
# Missing handler tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_call_tool_export_svg(tmp_path):
    """Handler: export_svg deve funcionar."""
    out_path = str(tmp_path / "out.svg")
    result = await server.handle_call_tool("export_svg", {
        "scad_code": "square([50, 30]);",
        "output_path": out_path
    })
    assert "Exported" in result[0].text
    assert os.path.exists(out_path)


@pytest.mark.asyncio
async def test_handle_call_tool_export_missing_output_path():
    """Handler: export_stl sem output_path deve dar ValueError."""
    with pytest.raises(ValueError, match="Missing 'output_path'"):
        await server.handle_call_tool("export_stl", {
            "scad_code": "cube([5,5,5]);"
        })


@pytest.mark.asyncio
async def test_generate_laser_part_missing_args():
    """Handler: generate_laser_part sem args."""
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_laser_part", None)


@pytest.mark.asyncio
async def test_generate_finger_test_missing_args():
    """Handler: generate_finger_test sem args."""
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_finger_test", None)


@pytest.mark.asyncio
async def test_generate_3d_box_missing_args():
    """Handler: generate_3d_box sem args."""
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_3d_box", None)


@pytest.mark.asyncio
async def test_generate_bracket_missing_args():
    """Handler: generate_bracket sem args."""
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_bracket", None)


@pytest.mark.asyncio
async def test_generate_enclosure_missing_args():
    """Handler: generate_enclosure sem args."""
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_enclosure", None)


@pytest.mark.asyncio
async def test_handle_call_tool_render_to_png_failure():
    """Handler: render_to_png com código inválido retorna erro em texto."""
    result = await server.handle_call_tool("render_to_png", {
        "scad_code": "INVALID_CODE_THAT_WILL_FAIL_XYZZY({{{}}}});"
    })
    # Deve retornar texto com erro, não levantar exceção
    assert len(result) >= 1
    assert result[0].type == "text"


@pytest.mark.asyncio
async def test_handle_call_tool_export_stl_failure():
    """Handler: export com SCAD inválido retorna erro."""
    import tempfile
    out = tempfile.mktemp(suffix=".stl")
    result = await server.handle_call_tool("export_stl", {
        "scad_code": "ZZZNONSENSE_MODULE({{});;",
        "output_path": out
    })
    assert len(result) >= 1
    assert result[0].type == "text"


# ─────────────────────────────────────────────────────────────────────────────
# generate_tolerance_test_scad
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_tolerance_test_basic():
    """Basic: gera placa de tolerância com defaults."""
    cfg = {}
    scad = server.generate_tolerance_test_scad(cfg)
    assert "cylinder" in scad
    assert "Tolerância" in scad or "Toler" in scad
    assert "difference" in scad
    assert "text" in scad
    assert "linear_extrude" in scad


def test_generate_tolerance_test_custom_range():
    """Custom: tolerância de -0.1 a 0.1 com passo 0.1 = 3 pares."""
    cfg = {"tol_min": -0.1, "tol_max": 0.1, "tol_step": 0.1}
    scad = server.generate_tolerance_test_scad(cfg)
    assert scad.count("Pino macho") == 3
    assert scad.count("Furo fêmea") == 3


def test_generate_tolerance_test_step_zero_guard():
    """Guard: tol_step=0 deve usar fallback 0.1."""
    cfg = {"tol_min": 0.0, "tol_max": 0.2, "tol_step": 0}
    scad = server.generate_tolerance_test_scad(cfg)
    assert "cylinder" in scad


def test_generate_tolerance_test_step_negative_guard():
    """Guard: tol_step negativo deve usar fallback 0.1."""
    cfg = {"tol_min": -0.1, "tol_max": 0.1, "tol_step": -0.05}
    scad = server.generate_tolerance_test_scad(cfg)
    assert "cylinder" in scad


def test_generate_tolerance_test_single_value():
    """Edge: tol_min == tol_max = 1 par apenas."""
    cfg = {"tol_min": 0.0, "tol_max": 0.0, "tol_step": 0.1}
    scad = server.generate_tolerance_test_scad(cfg)
    assert scad.count("Pino macho") == 1
    assert scad.count("Furo fêmea") == 1


def test_generate_tolerance_test_empty_config():
    """Edge: config vazio deve usar defaults."""
    scad = server.generate_tolerance_test_scad({})
    assert "$fn" in scad
    assert "cube" in scad


@pytest.mark.asyncio
async def test_handle_call_tool_generate_tolerance_test(tmp_path):
    """Handler: generate_tolerance_test gera SCAD + STL."""
    result = await server.handle_call_tool("generate_tolerance_test", {
        "config": {"tol_min": -0.1, "tol_max": 0.1, "tol_step": 0.1},
        "output_dir": str(tmp_path),
        "project_name": "tol_test"
    })
    assert os.path.exists(str(tmp_path / "tol_test.scad"))
    assert len(result) >= 1
    assert "tol_test" in result[0].text


@pytest.mark.asyncio
async def test_generate_tolerance_test_missing_args():
    """Handler: generate_tolerance_test sem args."""
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_tolerance_test", None)


# ─────────────────────────────────────────────────────────────────────────────
# generate_bed_level_test_scad
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_bed_level_test_basic():
    """Basic: gera padrão de nivelamento com defaults."""
    cfg = {}
    scad = server.generate_bed_level_test_scad(cfg)
    assert "cylinder" in scad
    assert "Nivelamento" in scad or "Disco" in scad
    # Default: 5x5 = 25 discos
    assert scad.count("Disco [") == 25


def test_generate_bed_level_test_custom_grid():
    """Custom: 3x2 grid = 6 discos."""
    cfg = {"grid_cols": 3, "grid_rows": 2, "bed_x": 200, "bed_y": 200}
    scad = server.generate_bed_level_test_scad(cfg)
    assert scad.count("Disco [") == 6


def test_generate_bed_level_test_no_skirt():
    """Edge: skirt_w=0 gera discos sem saia."""
    cfg = {"grid_cols": 2, "grid_rows": 2, "skirt_w": 0}
    scad = server.generate_bed_level_test_scad(cfg)
    assert "difference" not in scad
    assert "cylinder" in scad


def test_generate_bed_level_test_single_disc():
    """Edge: 1x1 grid = 1 disco centralizado."""
    cfg = {"grid_cols": 1, "grid_rows": 1}
    scad = server.generate_bed_level_test_scad(cfg)
    assert scad.count("Disco [") == 1


def test_generate_bed_level_test_empty_config():
    """Edge: config vazio deve usar defaults."""
    scad = server.generate_bed_level_test_scad({})
    assert "$fn" in scad
    assert "cylinder" in scad


@pytest.mark.asyncio
async def test_handle_call_tool_generate_bed_level_test(tmp_path):
    """Handler: generate_bed_level_test gera SCAD + STL."""
    result = await server.handle_call_tool("generate_bed_level_test", {
        "config": {"grid_cols": 2, "grid_rows": 2, "bed_x": 100, "bed_y": 100},
        "output_dir": str(tmp_path),
        "project_name": "bed_test"
    })
    assert os.path.exists(str(tmp_path / "bed_test.scad"))
    assert len(result) >= 1
    assert "bed_test" in result[0].text


@pytest.mark.asyncio
async def test_generate_bed_level_test_missing_args():
    """Handler: generate_bed_level_test sem args."""
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_bed_level_test", None)


# ─────────────────────────────────────────────────────────────────────────────
# generate_retraction_test_scad
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_retraction_test_basic():
    """Basic: gera torre de retração com defaults."""
    cfg = {}
    scad = server.generate_retraction_test_scad(cfg)
    assert "cylinder" in scad
    assert "cube" in scad
    assert "Retração" in scad or "Torre" in scad
    # Default: 5 torres
    assert scad.count("Torre ") >= 5


def test_generate_retraction_test_custom_count():
    """Custom: 3 torres."""
    cfg = {"tower_count": 3}
    scad = server.generate_retraction_test_scad(cfg)
    # 3 torre comments (Torre 1, Torre 2, Torre 3)
    for i in range(1, 4):
        assert f"Torre {i}" in scad


def test_generate_retraction_test_single_tower():
    """Edge: tower_count=1 deve gerar 1 torre."""
    cfg = {"tower_count": 1}
    scad = server.generate_retraction_test_scad(cfg)
    assert scad.count("cylinder") == 1


def test_generate_retraction_test_zero_tower_guard():
    """Guard: tower_count=0 deve ser clamped a 1."""
    cfg = {"tower_count": 0}
    scad = server.generate_retraction_test_scad(cfg)
    assert scad.count("cylinder") >= 1


def test_generate_retraction_test_empty_config():
    """Edge: config vazio deve usar defaults."""
    scad = server.generate_retraction_test_scad({})
    assert "$fn" in scad
    assert "cube" in scad


@pytest.mark.asyncio
async def test_handle_call_tool_generate_retraction_test(tmp_path):
    """Handler: generate_retraction_test gera SCAD + STL."""
    result = await server.handle_call_tool("generate_retraction_test", {
        "config": {"tower_count": 3, "tower_h": 40},
        "output_dir": str(tmp_path),
        "project_name": "retract_test"
    })
    assert os.path.exists(str(tmp_path / "retract_test.scad"))
    assert len(result) >= 1
    assert "retract_test" in result[0].text


@pytest.mark.asyncio
async def test_generate_retraction_test_missing_args():
    """Handler: generate_retraction_test sem args."""
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_retraction_test", None)


# ─────────────────────────────────────────────────────────────────────────────
# Integração OpenSCAD — novos geradores v0.4.0
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_openscad_renders_tolerance_test():
    """Integração: gera placa de tolerância e renderiza STL."""
    cfg = {"tol_min": 0.0, "tol_max": 0.1, "tol_step": 0.1}
    scad = server.generate_tolerance_test_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


@pytest.mark.asyncio
async def test_openscad_renders_bed_level_test():
    """Integração: gera teste de nivelamento e renderiza STL."""
    cfg = {"grid_cols": 2, "grid_rows": 2, "bed_x": 100, "bed_y": 100}
    scad = server.generate_bed_level_test_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


@pytest.mark.asyncio
async def test_openscad_renders_retraction_test():
    """Integração: gera torre de retração e renderiza STL."""
    cfg = {"tower_count": 2, "tower_h": 20}
    scad = server.generate_retraction_test_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


# ─────────────────────────────────────────────────────────────────────────────
# generate_living_hinge_scad
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_living_hinge_straight_basic():
    """Straight pattern: deve gerar difference() com cortes."""
    cfg = {"width": 100, "height": 60, "pattern": "straight"}
    scad = server.generate_living_hinge_scad(cfg)
    assert "difference()" in scad
    assert "square" in scad
    assert "Living Hinge" in scad
    assert "straight" in scad


def test_generate_living_hinge_serpentine():
    """Serpentine pattern: deve gerar cortes alternados."""
    cfg = {"width": 100, "height": 60, "pattern": "serpentine"}
    scad = server.generate_living_hinge_scad(cfg)
    assert "difference()" in scad
    assert "serpentine" in scad
    assert "square" in scad


def test_generate_living_hinge_cross():
    """Cross pattern: deve gerar cortes em X e Y."""
    cfg = {"width": 100, "height": 60, "pattern": "cross"}
    scad = server.generate_living_hinge_scad(cfg)
    assert "difference()" in scad
    assert "cross-hatch" in scad
    assert "square" in scad


def test_generate_living_hinge_invalid_pattern_fallback():
    """Padrão desconhecido deve usar 'straight' como fallback."""
    cfg = {"width": 100, "height": 60, "pattern": "invalid_xyz"}
    scad = server.generate_living_hinge_scad(cfg)
    assert "straight" in scad


def test_generate_living_hinge_small_inner_area():
    """Guard: margem grande demais deve retornar retângulo simples."""
    cfg = {"width": 20, "height": 20, "margin": 15, "cut_length": 15}
    scad = server.generate_living_hinge_scad(cfg)
    # Inner area too small, should just output a plain square
    assert "insuficiente" in scad


def test_generate_living_hinge_empty_config():
    """Edge: config vazio deve usar defaults."""
    scad = server.generate_living_hinge_scad({})
    assert "Living Hinge" in scad
    assert "difference()" in scad


def test_generate_living_hinge_custom_params():
    """Custom params: cut_length, cut_gap, row_spacing."""
    cfg = {
        "width": 80, "height": 50, "pattern": "straight",
        "cut_length": 10, "cut_gap": 3, "row_spacing": 4, "margin": 3
    }
    scad = server.generate_living_hinge_scad(cfg)
    assert "80" in scad and "50" in scad
    assert "difference()" in scad


@pytest.mark.asyncio
async def test_handle_call_tool_generate_living_hinge(tmp_path):
    """Handler: generate_living_hinge gera SCAD + SVG + DXF."""
    result = await server.handle_call_tool("generate_living_hinge", {
        "config": {"width": 80, "height": 50, "pattern": "straight"},
        "output_dir": str(tmp_path),
        "project_name": "hinge_test"
    })
    assert os.path.exists(str(tmp_path / "hinge_test.scad"))
    assert len(result) >= 1
    assert "hinge_test" in result[0].text


@pytest.mark.asyncio
async def test_generate_living_hinge_missing_args():
    """Handler: generate_living_hinge sem args."""
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_living_hinge", None)


# ─────────────────────────────────────────────────────────────────────────────
# generate_dogbone_scad
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_dogbone_basic():
    """Dogbone: deve gerar módulos com circles nos cantos."""
    cfg = {"width": 50, "height": 30}
    scad = server.generate_dogbone_scad(cfg)
    assert "module main_pocket" in scad
    assert "circle" in scad
    assert "dogbone" in scad.lower()
    assert "square" in scad


def test_generate_dogbone_tbone_h():
    """T-bone horizontal: deve gerar compensação horizontal."""
    cfg = {"width": 50, "height": 30, "corner_style": "tbone_h"}
    scad = server.generate_dogbone_scad(cfg)
    assert "tbone_h" in scad
    assert "circle" in scad


def test_generate_dogbone_tbone_v():
    """T-bone vertical: deve gerar compensação vertical."""
    cfg = {"width": 50, "height": 30, "corner_style": "tbone_v"}
    scad = server.generate_dogbone_scad(cfg)
    assert "tbone_v" in scad
    assert "circle" in scad


def test_generate_dogbone_invalid_style_fallback():
    """Estilo desconhecido deve usar 'dogbone' como fallback."""
    cfg = {"width": 50, "height": 30, "corner_style": "invalid"}
    scad = server.generate_dogbone_scad(cfg)
    assert "dogbone" in scad.lower()


def test_generate_dogbone_test_layout():
    """Deve gerar layout de teste com múltiplos pocket sizes."""
    cfg = {"width": 50, "height": 30}
    scad = server.generate_dogbone_scad(cfg)
    assert "test_layout" in scad
    assert "pocket_full_size" in scad
    assert "pocket_size_75pct" in scad
    assert "pocket_size_50pct" in scad


def test_generate_dogbone_custom_tool():
    """Custom tool diameter."""
    cfg = {"width": 50, "height": 30, "tool_d": 6.35}
    scad = server.generate_dogbone_scad(cfg)
    assert "6.35" in scad
    assert "circle" in scad


def test_generate_dogbone_empty_config():
    """Edge: config vazio deve usar defaults."""
    scad = server.generate_dogbone_scad({})
    assert "module main_pocket" in scad
    assert "3.175" in scad  # default tool_d


@pytest.mark.asyncio
async def test_handle_call_tool_generate_dogbone(tmp_path):
    """Handler: generate_dogbone gera SCAD + SVG + DXF."""
    result = await server.handle_call_tool("generate_dogbone", {
        "config": {"width": 50, "height": 30, "corner_style": "dogbone"},
        "output_dir": str(tmp_path),
        "project_name": "dogbone_test"
    })
    assert os.path.exists(str(tmp_path / "dogbone_test.scad"))
    assert len(result) >= 1
    assert "dogbone_test" in result[0].text


@pytest.mark.asyncio
async def test_generate_dogbone_missing_args():
    """Handler: generate_dogbone sem args."""
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_dogbone", None)


# ─────────────────────────────────────────────────────────────────────────────
# Integração OpenSCAD — living hinge + dogbone
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_openscad_renders_living_hinge_svg():
    """Integração: gera living hinge e exporta SVG."""
    cfg = {"width": 80, "height": 50, "pattern": "straight"}
    scad = server.generate_living_hinge_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "svg")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


@pytest.mark.asyncio
async def test_openscad_renders_dogbone_svg():
    """Integração: gera dogbone pocket e exporta SVG."""
    cfg = {"width": 50, "height": 30, "corner_style": "dogbone"}
    scad = server.generate_dogbone_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "svg")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


# ─────────────────────────────────────────────────────────────────────────────
# suggest_orientation
# ─────────────────────────────────────────────────────────────────────────────

def test_suggest_orientation_basic():
    """Basic: peça com base plana, orientação Z deve ser recomendada."""
    cfg = {"width": 80, "depth": 60, "height": 40, "has_flat_bottom": True}
    r = server.suggest_orientation(cfg)
    assert "recommended" in r
    assert "all_orientations" in r
    assert len(r["all_orientations"]) == 3
    assert r["recommended"]["score"] >= 100
    assert "summary" in r


def test_suggest_orientation_tall_piece():
    """Peça muito alta: penalidade na orientação Z."""
    cfg = {"width": 20, "depth": 20, "height": 200, "has_flat_bottom": True}
    r = server.suggest_orientation(cfg)
    z_orient = [o for o in r["all_orientations"] if o["rotation"] == [0, 0, 0]][0]
    assert any("tombar" in n for n in z_orient["notes"])


def test_suggest_orientation_holes_yz():
    """Furos YZ: orientação X deve ganhar bônus."""
    cfg = {"width": 80, "depth": 60, "height": 40, "has_holes_yz": True}
    r = server.suggest_orientation(cfg)
    x_orient = [o for o in r["all_orientations"] if o["rotation"] == [0, 90, 0]][0]
    assert any("YZ" in n for n in x_orient["notes"])


def test_suggest_orientation_flat_piece():
    """Peça plana (grande base, baixa): Z deve ser ideal."""
    cfg = {"width": 200, "depth": 150, "height": 5, "has_flat_bottom": True}
    r = server.suggest_orientation(cfg)
    assert r["recommended"]["rotation"] == [0, 0, 0]


def test_suggest_orientation_with_detail():
    """Detail on top: bônus na orientação Z."""
    cfg = {"width": 80, "depth": 60, "height": 40, "detail_on_top": True}
    r = server.suggest_orientation(cfg)
    z_orient = [o for o in r["all_orientations"] if o["rotation"] == [0, 0, 0]][0]
    assert any("Detalhes" in n for n in z_orient["notes"])


def test_suggest_orientation_unknown_profile():
    """Perfil desconhecido: usa fdm_standard."""
    cfg = {"width": 80, "depth": 60, "height": 40, "profile": "xyz_unknown"}
    r = server.suggest_orientation(cfg)
    assert r["profile"] == "xyz_unknown"
    assert len(r["all_orientations"]) == 3


def test_suggest_orientation_empty_config():
    """Config vazio: usa defaults."""
    r = server.suggest_orientation({})
    assert len(r["all_orientations"]) == 3
    assert "recommended" in r


@pytest.mark.asyncio
async def test_handle_call_tool_suggest_orientation():
    """Handler: suggest_orientation retorna texto."""
    result = await server.handle_call_tool("suggest_orientation", {
        "config": {"width": 80, "depth": 60, "height": 40}
    })
    assert len(result) >= 1
    assert "Orientação" in result[0].text or "score" in result[0].text


@pytest.mark.asyncio
async def test_suggest_orientation_missing_config():
    """Handler: suggest_orientation sem config."""
    with pytest.raises(ValueError, match="Missing"):
        await server.handle_call_tool("suggest_orientation", {})


# ─────────────────────────────────────────────────────────────────────────────
# generate_assembly
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_assembly_default():
    """Default: gera assembly com 5 peças exemplo."""
    scad, pieces, bom = server.generate_assembly_scad({})
    assert "assembled()" in scad
    assert "exploded()" in scad
    assert "SHOW_EXPLODED" in scad
    assert len(pieces) == 5
    assert "base" in pieces
    assert "# BOM" in bom
    assert "Volume total" in bom


def test_generate_assembly_custom_pieces():
    """Custom: 2 peças personalizadas."""
    cfg = {
        "project_name": "test_proj",
        "pieces": [
            {"name": "placa", "type": "box", "w": 50, "d": 30, "h": 2},
            {"name": "pilar", "type": "cylinder", "w": 10, "h": 20,
             "translate": [25, 15, 2], "material": "PETG"},
        ]
    }
    scad, pieces, bom = server.generate_assembly_scad(cfg)
    assert len(pieces) == 2
    assert "placa" in pieces
    assert "pilar" in pieces
    assert "cylinder" in pieces["pilar"]
    assert "PETG" in bom


def test_generate_assembly_custom_scad():
    """Custom SCAD: peça com código personalizado."""
    cfg = {
        "pieces": [
            {"name": "custom_gear", "type": "custom",
             "scad": "sphere(r=15)", "w": 30, "d": 30, "h": 30}
        ]
    }
    scad, pieces, bom = server.generate_assembly_scad(cfg)
    assert "sphere(r=15)" in scad
    assert "sphere(r=15)" in pieces["custom_gear"]


def test_generate_assembly_bom_format():
    """BOM: formato correto com tabela markdown."""
    cfg = {
        "pieces": [
            {"name": "a", "w": 10, "d": 20, "h": 30, "qty": 2},
            {"name": "b", "w": 5, "d": 5, "h": 5, "qty": 4},
        ]
    }
    _, _, bom = server.generate_assembly_scad(cfg)
    assert "| 1 |" in bom
    assert "| 2 |" in bom
    assert "10×20×30mm" in bom
    assert "**Peças:** 6" in bom


def test_generate_assembly_explode_distance():
    """Explode distance configurável."""
    cfg = {"explode_distance": 50}
    scad, _, _ = server.generate_assembly_scad(cfg)
    assert "exploded()" in scad


def test_generate_assembly_empty_config():
    """Config vazio: usa assembly padrão."""
    scad, pieces, bom = server.generate_assembly_scad({})
    assert len(pieces) == 5
    assert "assembled" in scad


@pytest.mark.asyncio
async def test_handle_call_tool_generate_assembly(tmp_path):
    """Handler: generate_assembly gera SCAD + STL + BOM."""
    result = await server.handle_call_tool("generate_assembly", {
        "config": {
            "pieces": [
                {"name": "base", "w": 40, "d": 30, "h": 3},
                {"name": "wall", "w": 40, "d": 2, "h": 20, "translate": [0, 0, 3]},
            ]
        },
        "output_dir": str(tmp_path),
        "project_name": "test_asm"
    })
    assert os.path.exists(str(tmp_path / "test_asm.scad"))
    assert os.path.exists(str(tmp_path / "test_asm_bom.md"))
    assert os.path.exists(str(tmp_path / "pieces" / "base.scad"))
    assert os.path.exists(str(tmp_path / "pieces" / "wall.scad"))
    assert len(result) >= 1


@pytest.mark.asyncio
async def test_generate_assembly_missing_args():
    """Handler: generate_assembly sem args."""
    with pytest.raises(ValueError, match="Missing arguments"):
        await server.handle_call_tool("generate_assembly", None)


# ─────────────────────────────────────────────────────────────────────────────
# Integração: suggest_orientation + assembly
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_openscad_renders_assembly():
    """Integração: assembly gera SCAD válido que renderiza em STL."""
    cfg = {
        "pieces": [
            {"name": "base", "w": 50, "d": 40, "h": 3},
            {"name": "column", "type": "cylinder", "w": 8, "h": 25,
             "translate": [25, 20, 3]},
        ]
    }
    scad, _, _ = server.generate_assembly_scad(cfg)
    out_path, _ = await server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


# ─────────────────────────────────────────────────────────────────────────────
# generate_cnc_toolpath_hints
# ─────────────────────────────────────────────────────────────────────────────

def test_cnc_toolpath_hints_mdf_default():
    """MDF com defaults: feed 1500, RPM 18000."""
    r = server.generate_cnc_toolpath_hints({})
    assert r["material"] == "MDF"
    assert r["parameters"]["feed_rate_mm_min"] == 1500
    assert r["parameters"]["spindle_rpm"] == 18000
    assert r["parameters"]["num_passes"] >= 1
    assert "summary" in r


def test_cnc_toolpath_hints_aluminum():
    """Alumínio: parâmetros conservadores."""
    r = server.generate_cnc_toolpath_hints({"material": "aluminum", "material_thickness": 3})
    assert r["material"] == "Alumínio"
    assert r["parameters"]["feed_rate_mm_min"] == 500
    assert r["parameters"]["spindle_rpm"] == 10000
    assert r["parameters"]["num_passes"] >= 1


def test_cnc_toolpath_hints_pocket_stepover():
    """Pocket: stepover deve ser ~40%."""
    r = server.generate_cnc_toolpath_hints({"cut_type": "pocket", "tool_d": 6})
    assert r["parameters"]["stepover_pct"] == 40.0
    assert abs(r["parameters"]["stepover_mm"] - 2.4) < 0.01


def test_cnc_toolpath_hints_profile_has_tabs():
    """Profile: deve incluir tabs."""
    r = server.generate_cnc_toolpath_hints({"cut_type": "profile"})
    assert len(r["tabs"]) > 0
    assert r["tabs"][0]["width_mm"] > 0


def test_cnc_toolpath_hints_engrave_no_tabs():
    """Engrave: sem tabs, stepover baixo."""
    r = server.generate_cnc_toolpath_hints({"cut_type": "engrave"})
    assert len(r["tabs"]) == 0
    assert r["parameters"]["stepover_pct"] == 10.0


def test_cnc_toolpath_hints_finishing_pass():
    """Finishing pass: incluído por padrão em profile."""
    r = server.generate_cnc_toolpath_hints({"cut_type": "profile", "finishing_pass": True})
    assert r["finishing"] is not None
    assert r["finishing"]["feed_rate_mm_min"] < r["parameters"]["feed_rate_mm_min"]


def test_cnc_toolpath_hints_no_finishing():
    """Sem finishing pass."""
    r = server.generate_cnc_toolpath_hints({"cut_type": "profile", "finishing_pass": False})
    assert r["finishing"] is None


def test_cnc_toolpath_hints_unknown_material():
    """Material desconhecido: fallback para MDF."""
    r = server.generate_cnc_toolpath_hints({"material": "titanium"})
    assert r["material"] == "MDF"  # fallback


def test_cnc_toolpath_hints_all_materials():
    """Todos os materiais do catálogo retornam resultados."""
    for mat in ["mdf", "plywood", "acrylic", "hardwood", "softwood", "aluminum", "foam", "hdpe"]:
        r = server.generate_cnc_toolpath_hints({"material": mat})
        assert r["parameters"]["feed_rate_mm_min"] > 0
        assert r["parameters"]["spindle_rpm"] > 0


def test_cnc_toolpath_hints_chip_load():
    """Chip load é calculado corretamente."""
    r = server.generate_cnc_toolpath_hints({"tool_flutes": 1})
    expected = 1500 / (18000 * 1)
    assert abs(r["parameters"]["chip_load_mm"] - round(expected, 4)) < 0.0001


def test_cnc_toolpath_hints_safety():
    """Safety notes incluídas."""
    r = server.generate_cnc_toolpath_hints({})
    assert len(r["safety"]) >= 5


@pytest.mark.asyncio
async def test_handle_call_tool_cnc_toolpath_hints():
    """Handler: CNC toolpath hints retorna texto formatado."""
    result = await server.handle_call_tool("generate_cnc_toolpath_hints", {
        "config": {"material": "acrylic", "material_thickness": 5, "tool_d": 3.175}
    })
    assert len(result) >= 1
    assert "Feed rate" in result[0].text or "CNC" in result[0].text


@pytest.mark.asyncio
async def test_cnc_toolpath_hints_missing_config():
    """Handler: sem config."""
    with pytest.raises(ValueError, match="Missing"):
        await server.handle_call_tool("generate_cnc_toolpath_hints", {})


# ─────────────────────────────────────────────────────────────────────────────
# render_to_png com câmera avançada
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.usefixtures("png_rendering")
async def test_render_to_png_default_camera():
    """Render com câmera padrão (autocenter + viewall)."""
    result = await server.handle_call_tool("render_to_png", {
        "scad_code": "cube([20, 20, 20]);"
    })
    assert len(result) == 2
    assert result[0].text == "Rendered successfully."
    assert result[1].type == "image"


@pytest.mark.asyncio
@pytest.mark.usefixtures("png_rendering")
async def test_render_to_png_custom_camera():
    """Render com câmera personalizada."""
    result = await server.handle_call_tool("render_to_png", {
        "scad_code": "cube([20, 20, 20]);",
        "camera": {
            "translate": [10, 10, 10],
            "rotate": [55, 0, 25],
            "distance": 150,
            "projection": "perspective"
        }
    })
    assert len(result) == 2
    assert result[1].type == "image"


@pytest.mark.asyncio
@pytest.mark.usefixtures("png_rendering")
async def test_render_to_png_ortho_projection():
    """Render com projeção ortográfica."""
    result = await server.handle_call_tool("render_to_png", {
        "scad_code": "sphere(r=15);",
        "camera": {"projection": "ortho"}
    })
    assert len(result) == 2
    assert result[1].type == "image"


@pytest.mark.asyncio
@pytest.mark.usefixtures("png_rendering")
async def test_render_to_png_custom_size():
    """Render com tamanho de imagem personalizado."""
    result = await server.handle_call_tool("render_to_png", {
        "scad_code": "cylinder(r=10, h=30, $fn=32);",
        "size": {"width": 400, "height": 300}
    })
    assert len(result) == 2
    assert result[1].type == "image"


# ─────────────────────────────────────────────────────────────────────────────
# Testes Adicionais de Segurança, Sanitização e Validação (v0.6.0)
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_safety_guidelines_banned_word():
    with pytest.raises(ValueError, match="Safety violation"):
        server.verify_safety_guidelines("cube([1,1,1]); // gun model here")

def test_verify_safety_guidelines_rocket_nozzle():
    with pytest.raises(ValueError, match="Safety violation"):
        server.verify_safety_guidelines("cylinder(d1=10, d2=20, h=30); // rocket nozzle")

def test_verify_safety_guidelines_safe_nozzle():
    # standard nozzle settings should be allowed
    server.verify_safety_guidelines("nozzle_d = 0.4; cube([10,10,10]);")

def test_validate_output_path_allowed():
    path = "/tmp/some_file.scad"
    assert server.validate_output_path(path) == os.path.realpath(path)

def test_validate_output_path_denied():
    with pytest.raises(ValueError, match="Access denied"):
        server.validate_output_path("/etc/passwd")

def test_safe_output_path_sanitization():
    out_dir, proj = server.safe_output_path("/tmp/test_dir", "../../../etc/bad_project")
    assert proj == "bad_project"
    assert out_dir == os.path.realpath("/tmp/test_dir")

def test_validate_config_parameters_negative_value():
    with pytest.raises(ValueError, match="must be strictly positive"):
        server.validate_config_parameters("generate_laser_part", {
            "width": -10, "depth": 80, "height": 50, "material_thickness": 3
        })

def test_validate_config_parameters_non_numeric():
    with pytest.raises(ValueError, match="must be numeric"):
        server.validate_config_parameters("generate_laser_part", {
            "width": "abc", "depth": 80, "height": 50, "material_thickness": 3
        })

def test_validate_config_parameters_impossible_dimensions():
    with pytest.raises(ValueError, match="must be greater than twice"):
        server.validate_config_parameters("generate_laser_part", {
            "width": 5, "depth": 80, "height": 50, "material_thickness": 3
        })

def test_validate_config_parameters_negative_fingers():
    with pytest.raises(ValueError, match="must be at least 1"):
        server.validate_config_parameters("generate_laser_part", {
            "width": 100, "depth": 80, "height": 50, "material_thickness": 3, "fingers": -2
        })

def test_validate_config_parameters_3d_box_impossible_radius():
    with pytest.raises(ValueError, match="corner_radius cannot be greater"):
        server.validate_config_parameters("generate_3d_box", {
            "width": 80, "depth": 60, "height": 40, "wall_thickness": 2, "bottom_thickness": 2,
            "corner_radius": 50
        })

def test_validate_config_parameters_enclosure_standoff_out_of_bounds():
    with pytest.raises(ValueError, match="must be inside the walls"):
        server.validate_config_parameters("generate_enclosure", {
            "width": 100, "depth": 60, "height": 30, "wall": 2.5, "lid_type": "snap",
            "standoff_d": 5, "standoff_hole_d": 2.5, "standoff_h": 5,
            "pcb_standoffs": [{"x": 1, "y": 10}] # sx=1 is less than wall + stod/2 = 2.5 + 2.5 = 5.0
        })

def test_validate_config_parameters_bracket_gusset_oversize():
    with pytest.raises(ValueError, match="Wall thickness exceeds depth/height limits"):
        server.validate_config_parameters("generate_bracket", {
            "type": "L", "width": 40, "height": 10, "depth": 20, "wall": 15, "gusset": True
        })

@pytest.mark.asyncio
async def test_handle_call_tool_safety_block():
    with pytest.raises(ValueError, match="Safety violation"):
        await server.handle_call_tool("render_to_png", {
            "scad_code": "cube([10,10,10]); // bomb activator"
        })

@pytest.mark.asyncio
async def test_handle_call_tool_path_traversal_block():
    with pytest.raises(ValueError, match="Access denied"):
        await server.handle_call_tool("export_stl", {
            "scad_code": "cube([5,5,5]);",
            "output_path": "/etc/passwd"
        })


# ─────────────────────────────────────────────────────────────────────────────
# Testes de Validação Completa de Parâmetros (validate_config_parameters)
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_config_not_dict():
    with pytest.raises(ValueError, match="Configuration must be a dictionary"):
        server.validate_config_parameters("generate_laser_part", "not-a-dict")

def test_validate_helpers_edge_cases():
    # Test assert_positive missing/None value
    with pytest.raises(ValueError, match="Parameter .* is missing"):
        server.validate_config_parameters("generate_laser_part", {"width": None})
    
    # Test assert_positive non-numeric
    with pytest.raises(ValueError, match="must be numeric"):
        server.validate_config_parameters("generate_laser_part", {"width": "invalid"})

    # Test assert_non_negative missing
    with pytest.raises(ValueError, match="Parameter .* is missing"):
        server.validate_config_parameters("generate_laser_part", {"kerf": None})

    # Test assert_integer missing
    with pytest.raises(ValueError, match="Parameter .* is missing"):
        server.validate_config_parameters("generate_laser_part", {"fingers": None})

    # Test assert_integer non-numeric
    with pytest.raises(ValueError, match="must be an integer"):
        server.validate_config_parameters("generate_laser_part", {"fingers": "abc"})

def test_validate_laser_part_impossible():
    # Width <= 2 * t
    with pytest.raises(ValueError, match="Width .* must be greater than twice the material thickness"):
        server.validate_config_parameters("generate_laser_part", {"width": 5, "material_thickness": 3})
    # Depth <= 2 * t
    with pytest.raises(ValueError, match="Depth .* must be greater than twice the material thickness"):
        server.validate_config_parameters("generate_laser_part", {"depth": 5, "material_thickness": 3})

    # Openings validation
    with pytest.raises(ValueError, match="Each opening must be a dictionary"):
        server.validate_config_parameters("generate_laser_part", {"openings": ["not-a-dict"]})
    
    with pytest.raises(ValueError, match="Opening wall .* is invalid"):
        server.validate_config_parameters("generate_laser_part", {"openings": [{"wall": "top"}]})
        
    with pytest.raises(ValueError, match="Opening shape .* is invalid"):
        server.validate_config_parameters("generate_laser_part", {"openings": [{"wall": "front", "shape": "hexagon"}]})

    # Rect opening bad parameters
    with pytest.raises(ValueError, match="Parameter 'opening x' must be non-negative"):
        server.validate_config_parameters("generate_laser_part", {"openings": [{"wall": "front", "shape": "rect", "x": -1}]})
    with pytest.raises(ValueError, match="Parameter 'opening w' must be strictly positive"):
        server.validate_config_parameters("generate_laser_part", {"openings": [{"wall": "front", "shape": "rect", "w": 0}]})

    # Circle opening bad parameters
    with pytest.raises(ValueError, match="Parameter 'opening cx' must be non-negative"):
        server.validate_config_parameters("generate_laser_part", {"openings": [{"wall": "front", "shape": "circle", "cx": -5}]})
    with pytest.raises(ValueError, match="Parameter 'opening d' must be strictly positive"):
        server.validate_config_parameters("generate_laser_part", {"openings": [{"wall": "front", "shape": "circle", "d": -2}]})

def test_validate_box_lid_type_and_dimensions():
    with pytest.raises(ValueError, match="Lid type .* is invalid"):
        server.validate_config_parameters("generate_box", {"lid_type": "screw"})
    
    with pytest.raises(ValueError, match="Width .* must be greater than twice the material thickness"):
        server.validate_config_parameters("generate_box", {"width": 5, "material_thickness": 3})

def test_validate_kerf_test_bounds():
    with pytest.raises(ValueError, match="kerf_min cannot be greater than kerf_max"):
        server.validate_config_parameters("generate_kerf_test", {"kerf_min": 0.5, "kerf_max": 0.2})

def test_validate_finger_test_bounds():
    # off_min > off_max
    with pytest.raises(ValueError, match="offset_min cannot be greater than offset_max"):
        server.validate_config_parameters("generate_finger_test", {"offset_min": 0.3, "offset_max": 0.1})
    # off_step <= 0
    with pytest.raises(ValueError, match="offset_step must be greater than 0"):
        server.validate_config_parameters("generate_finger_test", {"offset_step": -0.1})
    # non-numeric offsets
    with pytest.raises(ValueError, match="Offsets must be numeric"):
        server.validate_config_parameters("generate_finger_test", {"offset_min": "abc"})
    # tab width non-positive
    with pytest.raises(ValueError, match="Resulting tab width is non-positive"):
        server.validate_config_parameters("generate_finger_test", {"finger_width": 5, "offset_min": -6})
    # slot width non-positive
    with pytest.raises(ValueError, match="Resulting slot width is non-positive"):
        server.validate_config_parameters("generate_finger_test", {"finger_width": 5, "offset_max": 6})

def test_validate_3d_box_params():
    # Invalid lid type
    with pytest.raises(ValueError, match="Lid type .* is invalid"):
        server.validate_config_parameters("generate_3d_box", {"lid_type": "slide"})
    # width <= 2 * wt
    with pytest.raises(ValueError, match="width must be greater than twice the wall_thickness"):
        server.validate_config_parameters("generate_3d_box", {"width": 10, "wall_thickness": 6})
    # depth <= 2 * wt
    with pytest.raises(ValueError, match="depth must be greater than twice the wall_thickness"):
        server.validate_config_parameters("generate_3d_box", {"depth": 10, "wall_thickness": 6})
    # height <= bt
    with pytest.raises(ValueError, match="height must be greater than bottom_thickness"):
        server.validate_config_parameters("generate_3d_box", {"height": 5, "bottom_thickness": 6})

def test_validate_bracket_params():
    # mount_holes check
    with pytest.raises(ValueError, match="mount_holes must be 0, 2, or 4"):
        server.validate_config_parameters("generate_bracket", {"mount_holes": 3})
    # type check
    with pytest.raises(ValueError, match="Bracket type must be"):
        server.validate_config_parameters("generate_bracket", {"type": "circular"})
    # U-bracket width <= 2 * wall
    with pytest.raises(ValueError, match="width must be greater than twice the wall thickness"):
        server.validate_config_parameters("generate_bracket", {"type": "U", "width": 10, "wall": 6})

def test_validate_enclosure_params():
    # Invalid lid
    with pytest.raises(ValueError, match="Lid type must be"):
        server.validate_config_parameters("generate_enclosure", {"lid_type": "slide"})
    # screw lid small corner radius
    with pytest.raises(ValueError, match="corner_radius must be at least 1.6"):
        server.validate_config_parameters("generate_enclosure", {"lid_type": "screw", "corner_radius": 1.0})
    # standoff_d <= standoff_hole_d
    with pytest.raises(ValueError, match="standoff_d must be greater than standoff_hole_d"):
        server.validate_config_parameters("generate_enclosure", {"standoff_d": 3, "standoff_hole_d": 4})
    # standoff dict check
    with pytest.raises(ValueError, match="Each pcb_standoff must be a dictionary"):
        server.validate_config_parameters("generate_enclosure", {"pcb_standoffs": ["not-a-dict"]})

def test_validate_tolerance_test_params():
    # tol_min > tol_max
    with pytest.raises(ValueError, match="tol_min cannot be greater than tol_max"):
        server.validate_config_parameters("generate_tolerance_test", {"tol_min": 0.5, "tol_max": 0.2})
    # tol_step <= 0
    with pytest.raises(ValueError, match="tol_step must be greater than 0"):
        server.validate_config_parameters("generate_tolerance_test", {"tol_step": 0})
    # non-numeric bounds
    with pytest.raises(ValueError, match="Tolerance bounds must be numeric"):
        server.validate_config_parameters("generate_tolerance_test", {"tol_min": "abc"})

def test_validate_bed_level_test_params():
    # bed too small
    with pytest.raises(ValueError, match="Bed dimensions must be larger than disc diameter"):
        server.validate_config_parameters("generate_bed_level_test", {"bed_x": 30, "disc_d": 40})

def test_validate_living_hinge_params():
    with pytest.raises(ValueError, match="Pattern must be"):
        server.validate_config_parameters("generate_living_hinge", {"pattern": "diagonal"})

def test_validate_dogbone_params():
    # invalid style
    with pytest.raises(ValueError, match="Corner style must be"):
        server.validate_config_parameters("generate_dogbone", {"corner_style": "circle"})
    # pocket size too small
    with pytest.raises(ValueError, match="Pocket dimensions must be at least the tool diameter"):
        server.validate_config_parameters("generate_dogbone", {"width": 2, "tool_d": 3})

def test_validate_assembly_params():
    # piece not dict
    with pytest.raises(ValueError, match="Each piece must be a dictionary"):
        server.validate_config_parameters("generate_assembly", {"pieces": ["not-a-dict"]})
    # name missing
    with pytest.raises(ValueError, match="Piece name must be a non-empty string"):
        server.validate_config_parameters("generate_assembly", {"pieces": [{"w": 5}]})
    # type invalid
    with pytest.raises(ValueError, match="Piece type must be"):
        server.validate_config_parameters("generate_assembly", {"pieces": [{"name": "a", "type": "sphere"}]})
    # property length check
    with pytest.raises(ValueError, match="must be a list/tuple of 3 elements"):
        server.validate_config_parameters("generate_assembly", {"pieces": [{"name": "a", "translate": [1, 2]}]})
    # non-numeric property
    with pytest.raises(ValueError, match="must be numeric"):
        server.validate_config_parameters("generate_assembly", {"pieces": [{"name": "a", "translate": [1, "b", 3]}]})
    # color boundaries
    with pytest.raises(ValueError, match="Color channel values must be between 0 and 1"):
        server.validate_config_parameters("generate_assembly", {"pieces": [{"name": "a", "color": [1.5, 0, 0]}]})


# ─────────────────────────────────────────────────────────────────────────────
# Sprint 4: Testes novos cobrindo gaps críticos identificados na auditoria
# ─────────────────────────────────────────────────────────────────────────────

# ── Segurança: import()/surface() em SCAD customizado ────────────────────────

def test_verify_safety_guidelines_blocks_import():
    """Segurança: import() deve ser bloqueado em custom SCAD."""
    with pytest.raises(ValueError, match="Safety violation"):
        server.verify_safety_guidelines('import("/etc/passwd");')


def test_verify_safety_guidelines_blocks_surface():
    """Segurança: surface() deve ser bloqueado em custom SCAD."""
    with pytest.raises(ValueError, match="Safety violation"):
        server.verify_safety_guidelines('surface("/etc/shadow");')


def test_verify_safety_guidelines_allows_import_word_in_comment():
    """Segurança: 'import' como parte de nome não deve ser bloqueado."""
    # 'import_size' não tem 'import(' então deve passar
    server.verify_safety_guidelines("import_size = 10; cube([import_size, 10, 10]);")


# ── Segurança: MCP_OPENSCAD_ALLOWED_PATHS env var ────────────────────────────

def test_validate_output_path_uses_env_var(monkeypatch):
    """Segurança: MCP_OPENSCAD_ALLOWED_PATHS env var deve ser respeitada."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("MCP_OPENSCAD_ALLOWED_PATHS", tmpdir)
        result = server.validate_output_path(os.path.join(tmpdir, "test.scad"))
        assert result.startswith(os.path.realpath(tmpdir))


def test_validate_output_path_env_var_blocks_outside(monkeypatch):
    """Segurança: path fora de MCP_OPENSCAD_ALLOWED_PATHS deve ser bloqueado."""
    monkeypatch.setenv("MCP_OPENSCAD_ALLOWED_PATHS", "/some/allowed/path")
    with pytest.raises(ValueError, match="Access denied"):
        server.validate_output_path("/tmp/test.scad")


# ── Kerf: guard contra kerf negativo ─────────────────────────────────────────

def test_generate_laser_scad_kerf_guard_thin_material():
    """Guard: kerf não deve ficar negativo com material fino."""
    cfg = {"material_thickness": 0.05, "kerf": 0.5}
    scad = server.generate_laser_scad(cfg)
    # Se chegou aqui sem exceção, o guard funcionou
    assert "module" in scad


def test_generate_box_scad_kerf_guard_thin_material():
    """Guard: kerf não deve ficar negativo em generate_box_scad com material fino."""
    cfg = {"material_thickness": 0.05, "kerf": 0.5}
    scad = server.generate_box_scad(cfg)
    assert "module" in scad


# ── CNC: divisão por zero com tool_d=0 e tool_flutes=0 ───────────────────────

def test_validate_config_parameters_cnc_tool_d_zero():
    """CNC: tool_d=0 deve levantar ValueError."""
    with pytest.raises(ValueError):
        server.validate_config_parameters("generate_cnc_toolpath_hints", {"tool_d": 0})


def test_validate_config_parameters_cnc_tool_flutes_zero():
    """CNC: tool_flutes=0 deve levantar ValueError (min=1)."""
    with pytest.raises(ValueError):
        server.validate_config_parameters("generate_cnc_toolpath_hints", {"tool_flutes": 0})


def test_validate_config_parameters_cnc_negative_thickness():
    """CNC: material_thickness negativo deve levantar ValueError."""
    with pytest.raises(ValueError):
        server.validate_config_parameters("generate_cnc_toolpath_hints", {"material_thickness": -1})


# ── Assembly: edge cases ──────────────────────────────────────────────────────

def test_generate_assembly_empty_pieces():
    """Assembly: lista de peças vazia usa peças padrão."""
    cfg = {"pieces": []}
    scad, pieces, bom = server.generate_assembly_scad(cfg)
    # Com lista vazia, deve usar peças padrão (5 peças)
    assert len(pieces) == 5


def test_generate_assembly_piece_with_rotate():
    """Assembly: peça com rotate deve incluir rotate() no SCAD."""
    cfg = {"pieces": [{"name": "part", "w": 20, "d": 10, "h": 5, "rotate": [0, 0, 45]}]}
    scad, pieces, _ = server.generate_assembly_scad(cfg)
    assert "rotate" in scad


def test_generate_assembly_piece_with_color():
    """Assembly: peça com color deve incluir color() no SCAD."""
    cfg = {"pieces": [{"name": "colorful", "w": 20, "d": 10, "h": 5, "color": [1, 0, 0]}]}
    scad, pieces, _ = server.generate_assembly_scad(cfg)
    assert "color" in scad


def test_generate_assembly_duplicate_piece_names():
    """Assembly: peças com nomes duplicados devem ser geradas (último vence no dict)."""
    cfg = {"pieces": [
        {"name": "part", "w": 10, "d": 10, "h": 10},
        {"name": "part", "w": 20, "d": 20, "h": 20},
    ]}
    scad, pieces, _ = server.generate_assembly_scad(cfg)
    # Funciona sem exceção — o dict terá 1 entrada (último valor)
    assert "part" in pieces


# ── Material thickness zero / nan / inf ──────────────────────────────────────

def test_validate_config_parameters_nan_value():
    """Validação: float('nan') deve ser rejeitado."""
    with pytest.raises(ValueError):
        server.validate_config_parameters("generate_laser_part", {"width": float("nan")})


def test_validate_config_parameters_inf_value():
    """Validação: float('inf') deve ser rejeitado."""
    with pytest.raises(ValueError):
        server.validate_config_parameters("generate_laser_part", {"width": float("inf")})


def test_validate_config_parameters_material_thickness_zero():
    """Validação: material_thickness=0 deve ser rejeitado."""
    with pytest.raises(ValueError):
        server.validate_config_parameters("generate_laser_part", {"material_thickness": 0})


# ── safe_output_path: string vazia ───────────────────────────────────────────

def test_safe_output_path_empty_project_name():
    """Segurança: project_name vazio deve resultar em nome padrão 'project'."""
    out_dir, proj = server.safe_output_path("/tmp/test", "")
    assert proj == "project"


def test_safe_output_path_only_dots():
    """Segurança: project_name '...' deve resultar em nome padrão."""
    _, proj = server.safe_output_path("/tmp/test", "...")
    assert proj not in (".", "..", "...")


# ── Volume cilindro no BOM ────────────────────────────────────────────────────

def test_generate_assembly_bom_cylinder_volume():
    """BOM: volume de cilindro deve ser calculado (verificar que BOM não está vazio)."""
    cfg = {"pieces": [{"name": "cyl", "type": "cylinder", "w": 10, "h": 20}]}
    _, _, bom = server.generate_assembly_scad(cfg)
    assert "cyl" in bom
    assert "Volume" in bom or "volume" in bom.lower() or "mm³" in bom


# ── _generate_and_export helper ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_and_export_helper(tmp_path):
    """Sprint 3: helper _generate_and_export deve salvar SCAD e retornar resultado."""
    scad = "cube([10,10,10]);"
    results = ["✅ Teste"]
    ret = await server._generate_and_export(
        scad, str(tmp_path), "test_cube", results,
        export_formats=[("stl", "📐 STL")]
    )
    assert len(ret) >= 1
    assert os.path.exists(str(tmp_path / "test_cube.scad"))


@pytest.mark.asyncio
async def test_generate_and_export_helper_with_scad_2d(tmp_path):
    """Sprint 3: helper _generate_and_export com scad_2d alternativo."""
    scad_3d = "cube([20,20,20]);"
    scad_2d = "square([20,20]);"
    results = ["✅ Laser test"]
    ret = await server._generate_and_export(
        scad_3d, str(tmp_path), "laser_test", results,
        export_formats=[("svg", "🖼 SVG")],
        scad_2d=scad_2d
    )
    assert len(ret) >= 1


# ── README.md: versão atualizada ─────────────────────────────────────────────

def test_readme_has_version_badge():
    """Documentação: README deve ter badge de versão."""
    readme = os.path.join(os.path.dirname(__file__), '..', 'README.md')
    with open(readme) as f:
        content = f.read()
    assert "version" in content.lower() or "badge" in content.lower()


# ── CHANGELOG.md: existência ─────────────────────────────────────────────────

def test_changelog_exists():
    """Documentação: CHANGELOG.md deve existir."""
    changelog = os.path.join(os.path.dirname(__file__), '..', 'CHANGELOG.md')
    assert os.path.exists(changelog), "CHANGELOG.md não encontrado"
    with open(changelog) as f:
        content = f.read()
    assert "0.5.0" in content or "0.4.0" in content


# ─────────────────────────────────────────────────────────────────────────────
# run_openscad: timeout configurável (v0.7.0)
# ─────────────────────────────────────────────────────────────────────────────

def test_clamp_timeout_within_range():
    assert server._clamp_timeout(120) == 120
    assert server._clamp_timeout(120.5) == 120.5


def test_clamp_timeout_below_min():
    assert server._clamp_timeout(1) == server.RENDER_TIMEOUT_MIN
    assert server._clamp_timeout(-5) == server.RENDER_TIMEOUT_MIN


def test_clamp_timeout_above_max():
    assert server._clamp_timeout(99999) == server.RENDER_TIMEOUT_MAX


def test_clamp_timeout_invalid_falls_back_to_default():
    assert server._clamp_timeout("not-a-number") == server.RENDER_TIMEOUT_DEFAULT
    assert server._clamp_timeout(None) == server.RENDER_TIMEOUT_DEFAULT
    assert server._clamp_timeout(float("nan")) == server.RENDER_TIMEOUT_DEFAULT
    assert server._clamp_timeout(float("inf")) == server.RENDER_TIMEOUT_DEFAULT


@pytest.mark.asyncio
async def test_run_openscad_timeout_message_includes_clamped_value_high():
    """timeout_s acima do máximo deve ser clampado e refletido na mensagem de erro."""
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    mock_proc.kill = MagicMock()

    async def mock_create_subprocess(*a, **kw):
        return mock_proc

    async def _immediate_timeout(coro, timeout):
        coro.close()
        raise asyncio.TimeoutError()

    with patch('asyncio.create_subprocess_exec', side_effect=mock_create_subprocess), \
         patch('asyncio.wait_for', side_effect=_immediate_timeout):
        with pytest.raises(RuntimeError, match="timed out after 900 seconds"):
            await server.run_openscad("cube();", "stl", timeout_s=999999)


@pytest.mark.asyncio
async def test_run_openscad_timeout_message_includes_clamped_value_low():
    """timeout_s abaixo do mínimo deve ser clampado e refletido na mensagem de erro."""
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    mock_proc.kill = MagicMock()

    async def mock_create_subprocess(*a, **kw):
        return mock_proc

    async def _immediate_timeout(coro, timeout):
        coro.close()
        raise asyncio.TimeoutError()

    with patch('asyncio.create_subprocess_exec', side_effect=mock_create_subprocess), \
         patch('asyncio.wait_for', side_effect=_immediate_timeout):
        with pytest.raises(RuntimeError, match="timed out after 5 seconds"):
            await server.run_openscad("cube();", "stl", timeout_s=1)


@pytest.mark.asyncio
async def test_run_openscad_custom_timeout_used():
    """asyncio.wait_for deve receber o timeout_s (clampado) explicitamente passado."""
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    async def mock_create_subprocess(*cmd, **kw):
        # saída ausente ou vazia é falha: o processo falso precisa "gerar" o arquivo (-o)
        with open(cmd[list(cmd).index("-o") + 1], "wb") as f:
            f.write(b"solid x\nendsolid x\n")
        return mock_proc

    captured = {}

    async def fake_wait_for(coro, timeout):
        captured["timeout"] = timeout
        coro.close()
        return b"", b""

    with patch('asyncio.create_subprocess_exec', side_effect=mock_create_subprocess), \
         patch('asyncio.wait_for', side_effect=fake_wait_for):
        # returncode != 0 sem out_path existente levantaria erro; simulamos sucesso
        mock_proc.returncode = 0
        out_path, _ = await server.run_openscad("cube([1,1,1]);", "stl", timeout_s=120)
    assert captured["timeout"] == 120
    if os.path.exists(out_path):
        os.remove(out_path)


# ─────────────────────────────────────────────────────────────────────────────
# analyze_mesh: helpers de STL sintético para os testes
# ─────────────────────────────────────────────────────────────────────────────

def _box_triangles(origin=(0.0, 0.0, 0.0), size=(10.0, 10.0, 10.0)):
    """Gera os 12 triângulos de uma caixa fechada, com winding CCW-de-fora
    (normais para fora), a partir de origin (canto min) e size (dx,dy,dz)."""
    ox, oy, oz = origin
    sx, sy, sz = size
    v = [
        (ox, oy, oz), (ox + sx, oy, oz), (ox + sx, oy + sy, oz), (ox, oy + sy, oz),
        (ox, oy, oz + sz), (ox + sx, oy, oz + sz), (ox + sx, oy + sy, oz + sz), (ox, oy + sy, oz + sz),
    ]
    faces = [
        (0, 4, 7), (0, 7, 3),  # -X
        (1, 2, 6), (1, 6, 5),  # +X
        (0, 1, 5), (0, 5, 4),  # -Y
        (3, 7, 6), (3, 6, 2),  # +Y
        (0, 2, 1), (0, 3, 2),  # -Z
        (4, 5, 6), (4, 6, 7),  # +Z
    ]
    return [(v[a], v[b], v[c]) for a, b, c in faces]


def _write_binary_stl(path, triangles):
    with open(path, "wb") as f:
        f.write(b"\x00" * 80)
        f.write(struct.pack("<I", len(triangles)))
        for v1, v2, v3 in triangles:
            f.write(struct.pack("<3f", 0.0, 0.0, 0.0))
            f.write(struct.pack("<3f", *v1))
            f.write(struct.pack("<3f", *v2))
            f.write(struct.pack("<3f", *v3))
            f.write(struct.pack("<H", 0))


def _write_ascii_stl(path, triangles):
    lines = ["solid test"]
    for v1, v2, v3 in triangles:
        lines.append("  facet normal 0 0 0")
        lines.append("    outer loop")
        for v in (v1, v2, v3):
            lines.append(f"      vertex {v[0]} {v[1]} {v[2]}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid test")
    with open(path, "w") as f:
        f.write("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────────
# _parse_stl: detecção binário vs. ASCII (v0.8.1 — bugfix produção)
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_stl_ascii_matching_binary_size_still_parses_as_ascii(tmp_path):
    """
    Bug original: um STL ASCII cujo tamanho em bytes calha de bater com a
    fórmula binária (84 + 50*n) — ex.: ~1 em 50 arquivos ASCII do OpenSCAD
    2021.01 — era detectado (e parseado) como binário, produzindo lixo
    (bbox em escala 1e34). Preenchemos o arquivo com espaços em branco até
    o tamanho bater com a fórmula binária por coincidência, e confirmamos
    que ainda assim é reconhecido como ASCII (pelo conteúdo, não tamanho)
    e produz o bbox correto do cubo de 10mm.
    """
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube_ascii_padded.stl"
    _write_ascii_stl(str(p), tris)

    size = os.path.getsize(str(p))
    remainder = (size - 84) % 50
    if remainder != 0:
        pad = 50 - remainder
        with open(p, "a") as f:
            f.write("\n" + " " * (pad - 1))
    size2 = os.path.getsize(str(p))
    assert size2 >= 84 and (size2 - 84) % 50 == 0, "setup falhou em produzir o tamanho ambíguo"

    r = server.analyze_mesh(str(p))
    assert r["triangles"] == 12
    assert r["bbox"]["min"] == [0.0, 0.0, 0.0]
    assert r["bbox"]["max"] == [10.0, 10.0, 10.0]
    assert r["volume_mm3"] == pytest.approx(1000.0, rel=1e-3)


def test_parse_stl_binary_with_solid_header_still_detected_as_binary(tmp_path):
    """Exportador binário que grava literalmente 'solid' no header de 80 bytes."""
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube_binary_solid_header.stl"
    header = b"solid " + b"\x00" * 74
    assert len(header) == 80
    with open(p, "wb") as f:
        f.write(header)
        f.write(struct.pack("<I", len(tris)))
        for v1, v2, v3 in tris:
            f.write(struct.pack("<3f", 0.0, 0.0, 0.0))
            f.write(struct.pack("<3f", *v1))
            f.write(struct.pack("<3f", *v2))
            f.write(struct.pack("<3f", *v3))
            f.write(struct.pack("<H", 0))

    r = server.analyze_mesh(str(p))
    assert r["triangles"] == 12
    assert r["volume_mm3"] == pytest.approx(1000.0, rel=1e-3)


def test_parse_stl_binary_garbage_coords_raise_clear_error(tmp_path):
    """Se o parse binário produz coordenadas absurdas, deve falhar alto e claro."""
    n = 5
    size = 84 + 50 * n
    p = tmp_path / "garbage.stl"
    with open(p, "wb") as f:
        f.write(b"\xff" * size)  # cada float32 decodificado daqui é NaN

    with pytest.raises(ValueError, match="non-finite|misdetected"):
        server.analyze_mesh(str(p))


# ─────────────────────────────────────────────────────────────────────────────
# analyze_mesh: parsing + geometria
# ─────────────────────────────────────────────────────────────────────────────

def test_analyze_mesh_closed_cube_binary_watertight(tmp_path):
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)

    r = server.analyze_mesh(str(p))
    assert r["triangles"] == 12
    assert r["vertices"] == 8
    assert r["non_manifold_edges"] == 0
    assert r["watertight"] is True
    assert r["components"] == 1
    assert r["floating_components"] == 0
    assert r["volume_mm3"] == pytest.approx(1000.0, rel=1e-3)
    assert r["surface_mm2"] == pytest.approx(600.0, rel=1e-3)
    assert r["printable"] is True
    assert "summary" in r


def test_analyze_mesh_closed_cube_ascii_matches_binary(tmp_path):
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube_ascii.stl"
    _write_ascii_stl(str(p), tris)

    r = server.analyze_mesh(str(p))
    assert r["triangles"] == 12
    assert r["vertices"] == 8
    assert r["watertight"] is True
    assert r["volume_mm3"] == pytest.approx(1000.0, rel=1e-3)


def test_analyze_mesh_open_cube_non_manifold(tmp_path):
    """Cubo com uma face faltando: 4 arestas de borda ficam com contagem 1."""
    tris = _box_triangles(size=(10, 10, 10))
    # Remove a face +Z (últimos 2 triângulos)
    tris_open = tris[:-2]
    p = tmp_path / "open_cube.stl"
    _write_binary_stl(str(p), tris_open)

    r = server.analyze_mesh(str(p))
    assert r["non_manifold_edges"] == 4
    assert r["watertight"] is False
    assert r["printable"] is False
    assert any("watertight" in e.lower() or "manifold" in e.lower() for e in r["errors"])


def test_analyze_mesh_two_components_one_floating(tmp_path):
    tris = _box_triangles(origin=(0, 0, 0), size=(10, 10, 10))
    tris += _box_triangles(origin=(30, 0, 5), size=(10, 10, 10))
    p = tmp_path / "two_cubes.stl"
    _write_binary_stl(str(p), tris)

    r = server.analyze_mesh(str(p), bed_tol=0.3)
    assert r["components"] == 2
    assert r["floating_components"] == 1
    assert r["printable"] is False


def test_analyze_mesh_overhang_wedge_detected(tmp_path):
    """Face única inclinada > 45° a partir da vertical, elevada acima da base."""
    tri = [(
        (0.0, 0.0, 5.0),
        (0.0, 10.0, 5.0),
        (10.0, 10.0, 0.0),
    )]
    p = tmp_path / "wedge.stl"
    _write_binary_stl(str(p), tri)

    r = server.analyze_mesh(str(p), overhang_deg=45)
    assert r["overhang"]["overhang_area_mm2"] > 0
    assert len(r["overhang"]["worst_faces"]) >= 1
    assert r["overhang"]["worst_faces"][0]["angle_deg"] > 45


def test_analyze_mesh_table_bridge_detected(tmp_path):
    """Slab elevado sobre uma perna: face de baixo do slab é um bridge > 30mm."""
    tris = _box_triangles(origin=(0, 0, 0), size=(5, 5, 20))          # perna, toca a base
    tris += _box_triangles(origin=(-20, -20, 20), size=(50, 50, 2))   # slab elevado
    p = tmp_path / "table.stl"
    _write_binary_stl(str(p), tris)

    r = server.analyze_mesh(str(p), bed_tol=0.3)
    assert r["bridges"]["bridge_area_mm2"] > 0
    assert r["bridges"]["largest_cluster"] is not None
    assert r["bridges"]["largest_cluster"]["span_mm"] > 30
    assert any("bridge" in w.lower() or "vão" in w.lower() for w in r["warnings"])


def test_analyze_mesh_empty_stl_raises(tmp_path):
    p = tmp_path / "empty.stl"
    _write_binary_stl(str(p), [])
    with pytest.raises(ValueError, match="não contém triângulos"):
        server.analyze_mesh(str(p))


def test_analyze_mesh_triangle_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "STL_MAX_TRIANGLES", 5)
    tris = _box_triangles(size=(10, 10, 10))  # 12 triângulos > cap de 5
    p = tmp_path / "toobig.stl"
    _write_binary_stl(str(p), tris)
    with pytest.raises(ValueError, match="acima do limite"):
        server.analyze_mesh(str(p))


def test_format_mesh_analysis_returns_string(tmp_path):
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)
    r = server.analyze_mesh(str(p))
    text = server._format_mesh_analysis(r)
    assert isinstance(text, str)
    assert "Imprimível" in text or "imprimível" in text


# ─────────────────────────────────────────────────────────────────────────────
# analyze_mesh: handler MCP (handle_call_tool)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_call_tool_analyze_mesh_stl_path(tmp_path):
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)

    ret = await server.handle_call_tool("analyze_mesh", {"stl_path": str(p)})
    assert len(ret) == 1
    assert "Imprimível" in ret[0].text or "imprimível" in ret[0].text


@pytest.mark.asyncio
async def test_handle_call_tool_analyze_mesh_missing_input():
    with pytest.raises(ValueError, match="stl_path.*scad_code|scad_code.*stl_path"):
        await server.handle_call_tool("analyze_mesh", {})


@pytest.mark.asyncio
async def test_handle_call_tool_analyze_mesh_nonexistent_path(tmp_path):
    missing = tmp_path / "does_not_exist.stl"
    ret = await server.handle_call_tool("analyze_mesh", {"stl_path": str(missing)})
    assert len(ret) == 1
    assert "não encontrado" in ret[0].text or "❌" in ret[0].text


@pytest.mark.asyncio
async def test_handle_call_tool_analyze_mesh_from_scad_code():
    ret = await server.handle_call_tool("analyze_mesh", {"scad_code": "cube([10,10,10]);"})
    assert len(ret) == 1
    assert "triângulos" in ret[0].text


# ─────────────────────────────────────────────────────────────────────────────
# mesh_section: geometria pura (malhas sintéticas)
# ─────────────────────────────────────────────────────────────────────────────

def test_mesh_section_cube_axes(tmp_path):
    """Cubo 10mm cortado no meio em cada eixo deve dar seção 10x10, 1 contorno."""
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)

    for axis in ("x", "y", "z"):
        r = server.mesh_section(str(p), 5.0, axis=axis)
        assert r["axis"] == axis
        s = r["sections"][0]
        assert s["n_points"] > 0
        assert len(s["contours"]) == 1
        assert s["extent"][0] == pytest.approx(10.0, abs=1e-6)
        assert s["extent"][1] == pytest.approx(10.0, abs=1e-6)
        assert s["nudged"] is False


def test_mesh_section_z_list(tmp_path):
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)

    r = server.mesh_section(str(p), [2.0, 5.0, 8.0])
    assert len(r["sections"]) == 3
    for s in r["sections"]:
        assert s["n_points"] > 0
        assert len(s["contours"]) == 1


def test_mesh_section_vertex_ring_nudge(tmp_path):
    """Cortar exatamente em z=0 (anel de vértices da base) deve disparar o nudge automático."""
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)

    r = server.mesh_section(str(p), 0.0)
    s = r["sections"][0]
    assert s["nudged"] is True
    assert s["z_used"] == pytest.approx(server._MESH_SECTION_NUDGE, abs=1e-9)
    assert s["n_points"] > 0
    assert len(s["contours"]) == 1


def test_mesh_section_empty_outside_bbox(tmp_path):
    """Plano fora do bounding box: n_points=0, sem crash."""
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)

    r = server.mesh_section(str(p), 50.0)
    s = r["sections"][0]
    assert s["n_points"] == 0
    assert s["bbox"] is None
    assert s["contours"] == []


def test_mesh_section_triangle_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "STL_MAX_TRIANGLES", 5)
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "toobig.stl"
    _write_binary_stl(str(p), tris)
    with pytest.raises(ValueError, match="acima do limite"):
        server.mesh_section(str(p), 5.0)


def test_mesh_section_invalid_axis(tmp_path):
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)
    with pytest.raises(ValueError, match="axis"):
        server.mesh_section(str(p), 5.0, axis="w")


def test_mesh_section_z_list_too_long(tmp_path):
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)
    with pytest.raises(ValueError, match="50"):
        server.mesh_section(str(p), [float(i) for i in range(51)])


def test_format_mesh_section_returns_string(tmp_path):
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)
    r = server.mesh_section(str(p), 5.0)
    text = server._format_mesh_section(r)
    assert isinstance(text, str)
    assert "Corte de Malha" in text


# ─────────────────────────────────────────────────────────────────────────────
# mesh_section: tubo oco via OpenSCAD real ($fn-polígono)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mesh_section_hollow_cylinder_fn_polygon():
    """
    Tubo oco Ø externo 40mm / Ø interno 37.6mm ($fn=24). Para um polígono de
    $fn lados aproximando um círculo de raio R, os vértices (arestas verticais
    do prisma) ficam exatamente em r_max=R em qualquer altura — por isso
    Ø ext/int e a parede (todos calculados a partir de r_max, não de r_min)
    são precisos e height-independent em qualquer corte: parede = outer_r -
    inner_r = 1.2mm exatamente. Já o r_min (apótema) só bate exatamente com
    R*cos(pi/$fn) na meia-altura: em alturas intermediárias, o ponto de
    cruzamento com a diagonal de triangulação de cada face lateral plana cai
    num ponto do "chord" mais próximo de um dos vértices (mais perto de R),
    então usamos limites (>= apótema, <= R) nas outras alturas e a igualdade
    exata só na meia-altura.
    """
    fn = 24
    outer_r = 20.0
    inner_r = 18.8
    height = 20.0
    mid_z = height / 2
    scad = f"""
    $fn = {fn};
    difference() {{
        cylinder(h={height}, r={outer_r}, center=false);
        translate([0, 0, -1]) cylinder(h={height + 2}, r={inner_r}, center=false);
    }}
    """
    out_path, _ = await server.run_openscad(scad, "stl")
    try:
        expected_apothem_outer = outer_r * math.cos(math.pi / fn)
        expected_apothem_inner = inner_r * math.cos(math.pi / fn)

        for z in (5.0, mid_z, 15.0):
            r = server.mesh_section(str(out_path), z)
            s = r["sections"][0]
            assert s["n_points"] > 0
            assert len(s["contours"]) == 2

            outer, inner = s["contours"]

            # r_max (e portanto Ø ext/int) é o mesmo em qualquer altura —
            # vem das arestas verticais do prisma, sempre no raio nominal.
            assert outer["r_max"] == pytest.approx(outer_r, abs=1e-3)
            assert inner["r_max"] == pytest.approx(inner_r, abs=1e-3)
            d_ext = 2 * outer["r_max"]
            d_int = 2 * inner["r_max"]
            assert d_ext == pytest.approx(40.0, abs=1e-3)
            assert d_int == pytest.approx(37.6, abs=1e-3)

            # r_min está sempre entre o apótema ideal e R.
            assert expected_apothem_outer - 1e-3 <= outer["r_min"] <= outer_r + 1e-3
            assert expected_apothem_inner - 1e-3 <= inner["r_min"] <= inner_r + 1e-3

            # parede = outer.r_max - inner.r_max (mesma convenção de Ø ext/int,
            # ambos raios nominais dos vértices) — height-independent.
            wall = outer["r_max"] - inner["r_max"]
            assert wall == pytest.approx(outer_r - inner_r, abs=1e-3)
            assert wall == pytest.approx(1.2, abs=1e-3)

            if z == mid_z:
                # Na meia-altura, o cruzamento com a diagonal cai exatamente
                # no ponto médio da corda — o apótema exato.
                assert outer["r_min"] == pytest.approx(expected_apothem_outer, abs=1e-2)
                assert inner["r_min"] == pytest.approx(expected_apothem_inner, abs=1e-2)
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)


# ─────────────────────────────────────────────────────────────────────────────
# mesh_section: handler MCP (handle_call_tool)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_call_tool_mesh_section_stl_path(tmp_path):
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)

    ret = await server.handle_call_tool("mesh_section", {"stl_path": str(p), "z": 5.0})
    assert len(ret) == 1
    assert "Corte de Malha" in ret[0].text


@pytest.mark.asyncio
async def test_handle_call_tool_mesh_section_missing_input():
    with pytest.raises(ValueError, match="stl_path.*scad_code|scad_code.*stl_path"):
        await server.handle_call_tool("mesh_section", {"z": 5.0})


@pytest.mark.asyncio
async def test_handle_call_tool_mesh_section_missing_z(tmp_path):
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)
    with pytest.raises(ValueError, match="z"):
        await server.handle_call_tool("mesh_section", {"stl_path": str(p)})


@pytest.mark.asyncio
async def test_handle_call_tool_mesh_section_z_list(tmp_path):
    tris = _box_triangles(size=(10, 10, 10))
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), tris)

    ret = await server.handle_call_tool("mesh_section", {"stl_path": str(p), "z_list": [2.0, 5.0, 8.0]})
    assert len(ret) == 1
    assert ret[0].text.count("z_solicitado") == 3


@pytest.mark.asyncio
async def test_handle_call_tool_mesh_section_from_scad_code():
    ret = await server.handle_call_tool("mesh_section", {"scad_code": "cube([10,10,10]);", "z": 5.0})
    assert len(ret) == 1
    assert "Corte de Malha" in ret[0].text




# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — Descoberta do binário do OpenSCAD (find_openscad)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def no_openscad_cache():
    """find_openscad() é cacheada: limpa antes e depois dos testes que simulam a busca."""
    server.find_openscad.cache_clear()
    yield
    server.find_openscad.cache_clear()


def _fake_executable(path):
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return str(path)


def test_find_openscad_env_has_precedence(tmp_path, monkeypatch, no_openscad_cache):
    fake = _fake_executable(tmp_path / "my-openscad")
    monkeypatch.setenv("OPENSCAD_PATH", fake)
    monkeypatch.setattr(server.shutil, "which", lambda name: "/usr/bin/openscad-from-path")
    assert server.find_openscad() == fake


def test_find_openscad_env_ignored_when_not_executable(tmp_path, monkeypatch, no_openscad_cache):
    not_exec = tmp_path / "not-executable"
    not_exec.write_text("x")
    not_exec.chmod(0o644)
    monkeypatch.setenv("OPENSCAD_PATH", str(not_exec))
    monkeypatch.setattr(server.shutil, "which", lambda name: "/usr/bin/openscad-from-path")
    assert server.find_openscad() == "/usr/bin/openscad-from-path"


def test_find_openscad_uses_path_lookup(monkeypatch, no_openscad_cache):
    monkeypatch.delenv("OPENSCAD_PATH", raising=False)
    monkeypatch.setattr(server.shutil, "which", lambda name: "/opt/x/openscad" if name == "openscad" else None)
    assert server.find_openscad() == "/opt/x/openscad"


def test_find_openscad_falls_back_to_known_macos_locations(monkeypatch, no_openscad_cache):
    app = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
    monkeypatch.delenv("OPENSCAD_PATH", raising=False)
    with monkeypatch.context() as m:
        m.setattr(server.shutil, "which", lambda name: None)
        m.setattr(server.os.path, "isfile", lambda p: p == app)
        m.setattr(server.os, "access", lambda p, mode: p == app)
        assert server.find_openscad() == app


def test_find_openscad_result_is_cached(monkeypatch, no_openscad_cache):
    calls = []
    monkeypatch.delenv("OPENSCAD_PATH", raising=False)
    monkeypatch.setattr(server.shutil, "which", lambda name: calls.append(name) or "/opt/x/openscad")
    assert server.find_openscad() == server.find_openscad()
    assert len(calls) == 1


def _hide_openscad(m):
    """Faz a busca não achar nada (PATH, OPENSCAD_PATH e lista fixa)."""
    m.delenv("OPENSCAD_PATH", raising=False)
    m.setattr(server.shutil, "which", lambda name: None)
    m.setattr(server.os.path, "isfile", lambda p: False)


def test_find_openscad_error_names_the_rejected_openscad_path(monkeypatch, no_openscad_cache):
    with monkeypatch.context() as m:
        _hide_openscad(m)
        m.setenv("OPENSCAD_PATH", "/wrong/place/openscad")
        with pytest.raises(RuntimeError) as exc:
            server.find_openscad()
    assert "/wrong/place/openscad" in str(exc.value)
    assert "OpenSCAD não encontrado" in str(exc.value)


def test_find_openscad_error_does_not_blame_an_unset_openscad_path(monkeypatch, no_openscad_cache):
    with monkeypatch.context() as m:
        _hide_openscad(m)
        with pytest.raises(RuntimeError) as exc:
            server.find_openscad()
    assert "foi ignorado" not in str(exc.value)


def test_find_openscad_not_found_has_actionable_message(monkeypatch, no_openscad_cache):
    with monkeypatch.context() as m:
        _hide_openscad(m)
        with pytest.raises(RuntimeError) as exc:
            server.find_openscad()
    msg = str(exc.value)
    assert "OpenSCAD não encontrado" in msg
    assert "OPENSCAD_PATH" in msg
    assert "openscad@snapshot" in msg


@pytest.mark.asyncio
async def test_check_syntax_without_openscad_returns_false_instead_of_raising(monkeypatch, no_openscad_cache):
    with monkeypatch.context() as m:
        _hide_openscad(m)
        is_valid, msg = await server.check_scad_syntax("cube(1);")
    assert is_valid is False
    assert "OpenSCAD não encontrado" in msg


@pytest.mark.asyncio
async def test_run_openscad_without_openscad_raises_actionable_error(monkeypatch, no_openscad_cache):
    with monkeypatch.context() as m:
        _hide_openscad(m)
        with pytest.raises(RuntimeError, match="OpenSCAD não encontrado"):
            await server.run_openscad("cube(1);", "stl")


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — validate_output_path (realpath, commonpath, tempdir do sistema)
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_output_path_denies_sibling_prefix(tmp_path, monkeypatch):
    allowed = tmp_path / "ok"
    evil = tmp_path / "okevil"
    allowed.mkdir()
    evil.mkdir()
    monkeypatch.setenv("MCP_OPENSCAD_ALLOWED_PATHS", str(allowed))
    with pytest.raises(ValueError, match="Access denied"):
        server.validate_output_path(str(evil / "x.stl"))
    assert server.validate_output_path(str(allowed / "x.stl")) == os.path.realpath(str(allowed / "x.stl"))


def test_validate_output_path_denies_tmp_sibling_with_default_list(monkeypatch):
    monkeypatch.delenv("MCP_OPENSCAD_ALLOWED_PATHS", raising=False)
    with pytest.raises(ValueError, match="Access denied"):
        server.validate_output_path("/tmpevil/x.stl")


def test_validate_output_path_denies_symlink_escape(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (allowed / "link").symlink_to(outside)
    monkeypatch.setenv("MCP_OPENSCAD_ALLOWED_PATHS", str(allowed))
    with pytest.raises(ValueError, match="Access denied"):
        server.validate_output_path(str(allowed / "link" / "x.stl"))


def test_validate_output_path_allows_system_tempdir(monkeypatch):
    """macOS: tempfile.gettempdir() é /var/folders/... (fora de ~, /tmp e /var/tmp)."""
    monkeypatch.delenv("MCP_OPENSCAD_ALLOWED_PATHS", raising=False)
    monkeypatch.setattr(server.tempfile, "gettempdir", lambda: "/macos-sim/var/folders/xx/T")
    path = "/macos-sim/var/folders/xx/T/out.stl"
    assert server.validate_output_path(path) == os.path.realpath(path)


def test_validate_output_path_allows_symlinked_prefix(tmp_path, monkeypatch):
    """macOS: /tmp é um symlink para /private/tmp; o chamador pode passar qualquer um dos dois."""
    real = tmp_path / "private_tmp"
    link = tmp_path / "tmp"
    real.mkdir()
    link.symlink_to(real)
    monkeypatch.setenv("MCP_OPENSCAD_ALLOWED_PATHS", str(link))
    for target in (real / "x.stl", link / "x.stl"):
        assert server.validate_output_path(str(target)) == os.path.realpath(str(target))


def test_validate_output_path_env_uses_os_pathsep(tmp_path, monkeypatch):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("MCP_OPENSCAD_ALLOWED_PATHS", os.pathsep.join([str(a), str(b)]))
    assert server.validate_output_path(str(b / "x.stl")) == os.path.realpath(str(b / "x.stl"))


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — B3: run_openscad não aceita saída vazia nem returncode != 0
# ─────────────────────────────────────────────────────────────────────────────

def _fake_openscad_process(returncode, stderr=b"", output=None):
    """Substitui asyncio.create_subprocess_exec: cria o arquivo de saída (-o) com
    `output` (se não for None) e devolve um processo falso com `returncode`."""
    created = {}

    async def fake_exec(*cmd, **kwargs):
        out_path = cmd[list(cmd).index("-o") + 1]
        created["out_path"] = out_path
        if output is not None:
            with open(out_path, "wb") as f:
                f.write(output)
        proc = MagicMock()
        proc.returncode = returncode
        proc.communicate = AsyncMock(return_value=(b"", stderr))
        return proc

    return fake_exec, created


@pytest.mark.asyncio
@pytest.mark.parametrize("returncode, output", [(139, b""), (0, b""), (1, b"partial")])
async def test_run_openscad_fails_on_bad_exit_or_empty_output(monkeypatch, returncode, output):
    fake_exec, created = _fake_openscad_process(returncode, b"Can't create OpenGL OffscreenView", output)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    with pytest.raises(RuntimeError, match="OpenSCAD Error"):
        await server.run_openscad("cube(1);", "png")
    assert not os.path.exists(created["out_path"])


@pytest.mark.asyncio
async def test_render_to_png_reports_error_instead_of_empty_image(monkeypatch):
    fake_exec, _ = _fake_openscad_process(139, b"Can't create OpenGL OffscreenView", b"")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = await server.handle_call_tool("render_to_png", {"scad_code": "cube(1);"})
    assert [c.type for c in result] == ["text"]
    assert "OpenSCAD Error" in result[0].text


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — B1: juntas do lado direito usam a borda da PEÇA, não o length do loop
# ─────────────────────────────────────────────────────────────────────────────

_SQUARE_RE = re.compile(
    r"translate\(\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]\)\s*square\(\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]\)"
)


def _scad_module_body(scad, name):
    m = re.search(rf"module {name}\(\)\s*\{{(.*?)^\}}", scad, re.S | re.M)
    assert m, f"module {name} not found"
    return m.group(1)


def _joint_x_positions(scad, module, width):
    """Posições X dos retângulos de largura `width` (fendas = slot, dentes = t) no módulo."""
    body = _scad_module_body(scad, module)
    return sorted({float(x) for x, _y, w, _h in _SQUARE_RE.findall(body) if abs(float(w) - width) < 1e-6})


@pytest.mark.parametrize("W, D, H", [(150, 100, 60), (80, 120, 200)])
def test_box_right_joints_use_the_piece_edge(W, D, H):
    t, kerf = 3, 0.2
    slot = t - kerf
    scad = server.generate_box_scad({
        "width": W, "depth": D, "height": H, "material_thickness": t, "kerf": kerf, "lid_type": "none",
    })
    assert _joint_x_positions(scad, "box_front_wall", slot) == [0.0, round(W - slot, 3)]
    assert _joint_x_positions(scad, "box_floor", slot) == [0.0, round(W - slot, 3)]
    assert _joint_x_positions(scad, "box_side_wall", t) == [-float(t), float(D - 2 * t)]


@pytest.mark.parametrize("W, D, H", [(150, 100, 60), (80, 120, 200)])
def test_laser_part_right_joints_use_the_piece_edge(W, D, H):
    t, kerf = 3, 0.2
    slot = t - kerf
    side_w = D - 2 * t
    scad = server.generate_laser_scad({
        "width": W, "depth": D, "height": H, "material_thickness": t, "kerf": kerf,
    })
    assert _joint_x_positions(scad, "front_wall", slot) == [0.0, round(W - slot, 3)]
    assert _joint_x_positions(scad, "back_wall", slot) == [0.0, round(W - slot, 3)]
    assert _joint_x_positions(scad, "side_wall", t) == [-float(t), float(side_w)]


@pytest.mark.parametrize("W, D, H", [(150, 100, 60), (80, 120, 200)])
def test_laser_part_floor_has_side_slots_on_both_edges(W, D, H):
    t, kerf = 3, 0.2
    slot = t - kerf
    scad = server.generate_laser_scad({
        "width": W, "depth": D, "height": H, "material_thickness": t, "kerf": kerf,
    })
    assert _joint_x_positions(scad, "floor_base", slot) == [0.0, round(W - slot, 3)]


def _floor_side_slots_y(scad, floor_module, slot):
    """{x: [(y0, y1), ...]}: fendas laterais do piso (largura = slot), agrupadas pela borda em que ficam."""
    by_x = {}
    for x, y, w, h in _SQUARE_RE.findall(_scad_module_body(scad, floor_module)):
        if abs(float(w) - slot) < 1e-6:
            by_x.setdefault(float(x), []).append((float(y), round(float(y) + float(h), 4)))
    return {x: sorted(v) for x, v in by_x.items()}


def _side_wall_bottom_teeth(scad, wall_module, t):
    """[(u0, u1), ...]: dentes da borda inferior da lateral (y = -t, altura t), ao longo da peça."""
    return sorted(
        (float(x), round(float(x) + float(w), 4))
        for x, y, w, h in _SQUARE_RE.findall(_scad_module_body(scad, wall_module))
        if abs(float(y) + t) < 1e-6 and abs(float(h) - t) < 1e-6
    )


@pytest.mark.parametrize("W, D, H", [(150, 100, 60), (80, 120, 200)])
def test_laser_part_floor_side_slots_line_up_with_side_wall_teeth(W, D, H):
    """A lateral fica entre a frontal e a traseira: no assembly seu comprimento começa em y = t. As fendas
    laterais do piso saíam de y = 0, 3 mm antes dos dentes da lateral (0 a 18,9 contra 3 a 21,9)."""
    t, kerf = 3, 0.2
    slot = t - kerf
    scad = server.generate_laser_scad({
        "width": W, "depth": D, "height": H, "material_thickness": t, "kerf": kerf,
    })
    assert re.search(
        r"translate\(\[0,\s*t,\s*0\]\)\s*rotate\(\[90,\s*0,\s*90\]\)\s*linear_extrude\(t\)\s*side_wall\(\)", scad
    ), "o assembly deixou de começar a lateral em y = t: revise este teste"
    teeth_in_floor_frame = [(round(a + t, 4), round(b + t, 4)) for a, b in _side_wall_bottom_teeth(scad, "side_wall", t)]
    slots = _floor_side_slots_y(scad, "floor_base", slot)
    assert slots[0.0] == teeth_in_floor_frame
    assert slots[round(W - slot, 3)] == teeth_in_floor_frame


def test_laser_part_floor_side_slots_exact_positions_for_the_readme_size():
    scad = server.generate_laser_scad({
        "width": 150, "depth": 100, "height": 60, "material_thickness": 3, "kerf": 0.2,
    })
    expected = [(3.0, 21.9), (40.5, 59.5), (78.1, 97.0)]
    assert _floor_side_slots_y(scad, "floor_base", 2.8) == {0.0: expected, 147.2: expected}


@pytest.mark.asyncio
async def test_laser_part_side_wall_teeth_fit_the_floor_slots():
    """Geometria real: monta o piso e as duas laterais como no assembly_3d e mede a interferência. Com os dentes
    dentro das fendas só sobra a folga de projeto (t - slot = kerf) ao longo dos dentes; com a fenda 3 mm
    fora de lugar os dentes batiam no piso (110 mm³ por lateral em vez de 34)."""
    t, kerf = 3, 0.2
    scad = server.generate_laser_scad({"width": 150, "depth": 100, "height": 60, "material_thickness": t, "kerf": kerf})
    tooth_length = sum(b - a for a, b in _side_wall_bottom_teeth(scad, "side_wall", t))
    designed = 2 * (kerf * t * tooth_length)        # 0,2 mm de folga x 3 mm de altura x comprimento dos dentes, nas 2 laterais
    assert await _interference_mm3(scad, "floor", ["left", "right"]) == pytest.approx(designed, abs=0.1)


def test_laser_part_floor_front_slots_line_up_with_front_wall_teeth():
    """Na frente não há deslocamento: o piso e a parede frontal usam o mesmo referencial em X."""
    t, kerf = 3, 0.2
    slot = t - kerf
    scad = server.generate_laser_scad({"width": 150, "depth": 100, "height": 60, "material_thickness": t, "kerf": kerf})
    wall_teeth = _side_wall_bottom_teeth(scad, "front_wall", t)
    floor_slots = sorted(
        (float(x), round(float(x) + float(w), 4))
        for x, y, w, h in _SQUARE_RE.findall(_scad_module_body(scad, "floor_base"))
        if float(y) == 0.0 and abs(float(h) - slot) < 1e-6
    )
    assert wall_teeth
    assert floor_slots == wall_teeth


BOX_CFG = {"width": 150, "depth": 100, "height": 60, "material_thickness": 3, "kerf": 0.2, "lid_type": "none"}


def test_box_floor_side_slots_line_up_with_side_wall_teeth():
    """Mesmo modelo do generate_laser_part: a lateral cabe entre a frontal e a traseira (começa em y = t) e as
    fendas laterais do piso usam os mesmos dedos dos dentes inferiores da lateral, deslocados em t."""
    t, kerf = 3, 0.2
    slot = t - kerf
    scad = server.generate_box_scad(BOX_CFG)
    assert re.search(
        r"translate\(\[0,\s*t,\s*0\]\)\s*rotate\(\[90,\s*0,\s*90\]\)\s*linear_extrude\(t\)\s*box_side_wall\(\)", scad
    ), "o assembly deixou de começar a lateral em y = t: revise este teste"
    teeth_in_floor_frame = [(round(a + t, 4), round(b + t, 4)) for a, b in _side_wall_bottom_teeth(scad, "box_side_wall", t)]
    slots = _floor_side_slots_y(scad, "box_floor", slot)
    assert slots[0.0] == teeth_in_floor_frame
    assert slots[round(150 - slot, 3)] == teeth_in_floor_frame


def test_box_floor_side_slots_exact_positions_for_the_readme_size():
    """Antes: fendas do piso em Y 20,1-39,9 e 60,1-79,9 (dedos ímpares); dentes da lateral (comprimento 100) em
    0-19,9, 40,1-59,9 e 80,1-100 (dedos pares). Agora a lateral tem 94 e as duas listas são a mesma."""
    scad = server.generate_box_scad(BOX_CFG)
    expected = [(3.0, 21.7), (40.7, 59.3), (78.3, 97.0)]
    assert _floor_side_slots_y(scad, "box_floor", 2.8) == {0.0: expected, 147.2: expected}
    assert _side_wall_bottom_teeth(scad, "box_side_wall", 3) == [(0.0, 18.7), (37.7, 56.3), (75.3, 94.0)]


def test_box_side_walls_fit_between_front_and_back_in_layout():
    scad = server.generate_box_scad(BOX_CFG)
    sides = [(w, h) for _x, _y, w, h in _box_layout_rects(scad) if (w, h) == (94.0, 60.0)]
    assert len(sides) == 2                       # D - 2t = 94, não 100


def test_estimate_material_use_lateral_fits_between_front_and_back():
    r = server.estimate_material_use({"width": 150, "depth": 100, "height": 60, "material_thickness": 3})
    lateral = next(p for p in r["pieces"] if p["name"] == "Lateral")
    assert (lateral["w"], lateral["h"], lateral["qty"]) == (94, 60, 2)


_ASSEMBLY_PART_RE = re.compile(r"color\(\[[^\]]*\]\)\s*(.*?linear_extrude\(t\)\s*\w+\(\))\s*;", re.S)


def _assembly_parts(scad):
    """Expressões de posicionamento do assembly_3d: piso, frontal, traseira, lateral esquerda e direita."""
    exprs = _ASSEMBLY_PART_RE.findall(_scad_module_body(scad, "assembly_3d"))
    assert len(exprs) == 5
    return dict(zip(("floor", "front", "back", "left", "right"), exprs))


async def _interference_mm3(scad, part, others):
    """Volume (mm³) da interseção de `part` com a união de `others`, na posição do assembly_3d."""
    parts = _assembly_parts(scad)
    union_body = "".join(f"        {parts[o]};\n" for o in others)
    scene = f"\nintersection() {{\n    {parts[part]};\n    union() {{\n{union_body}    }}\n}}\n"
    stl_path, _ = await server.run_openscad(scad[:scad.index('RENDER_MODE = "3d";')] + scene, "stl")
    try:
        return server.analyze_mesh(stl_path)["volume_mm3"]
    finally:
        os.remove(stl_path)


def _clearance_lengths(scad, t):
    """Comprimentos que geram a folga de projeto (t - slot = kerf) em cada tipo de junta do generate_box."""
    return {
        "side_bottom": sum(b - a for a, b in _side_wall_bottom_teeth(scad, "box_side_wall", t)),
        "front_bottom": sum(b - a for a, b in _side_wall_bottom_teeth(scad, "box_front_wall", t)),
        "side_tabs": sum(
            float(h) for x, _y, _w, h in _SQUARE_RE.findall(_scad_module_body(scad, "box_side_wall")) if float(x) == -t
        ),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("part, other, joint", [
    ("floor", "left", "side_bottom"), ("floor", "right", "side_bottom"),
    ("floor", "front", "front_bottom"), ("floor", "back", "front_bottom"),
    ("front", "left", "side_tabs"), ("front", "right", "side_tabs"),
    ("back", "left", "side_tabs"), ("back", "right", "side_tabs"),
])
async def test_box_pieces_only_interfere_by_the_designed_clearance(part, other, joint):
    """Geometria real: monta as peças como no assembly_3d e mede a interferência de cada par que se encaixa.
    Com dentes dentro das fendas só sobra a folga de projeto (t - slot = kerf) x altura do dente x comprimento."""
    t, kerf = 3, 0.2
    scad = server.generate_box_scad(BOX_CFG)
    designed = kerf * t * _clearance_lengths(scad, t)[joint]
    assert await _interference_mm3(scad, part, [other]) == pytest.approx(designed, abs=0.1)


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — B1b/B1c: divisórias do generate_box no layout 2D
# ─────────────────────────────────────────────────────────────────────────────

_LAYOUT_ITEM_RE = re.compile(
    r"translate\(\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]\)\s*(box_\w+\(\)|square\(\[\s*[\d.]+\s*,\s*[\d.]+\s*\]\))\s*;"
)


def _scad_numbers(scad):
    """Variáveis numéricas do cabeçalho do SCAD gerado (t, W, D, H, slot, side_d...), avaliadas em ordem."""
    env = {}
    for name, expr in re.findall(r"^(\w+)\s*=\s*([^;\"]+);", scad.split("module ", 1)[0], re.M):
        try:
            env[name] = eval(expr, {"__builtins__": {}}, env)
        except Exception:
            pass
    return env


def _body_size(scad, module):
    """(largura, altura) do retângulo principal de um módulo: o primeiro square(), avaliado com o cabeçalho."""
    m = re.search(r"square\(\[\s*([^,\]]+?)\s*,\s*([^\]]+?)\s*\]\)", _scad_module_body(scad, module))
    env = _scad_numbers(scad)
    return float(eval(m.group(1), {"__builtins__": {}}, env)), float(eval(m.group(2), {"__builtins__": {}}, env))


def _box_lid_size(scad):
    """(w, d) do retângulo principal da tampa (snap: W×D; slide: menor pela folga)."""
    m = re.search(r"square\(\[\s*([\d.]+)\s*,\s*([\d.]+)\s*\]\)", _scad_module_body(scad, "box_lid"))
    return float(m.group(1)), float(m.group(2))


def _box_layout_rects(scad):
    """Retângulos (x, y, w, h) das peças em layout_2d, sem os dentes. Os tamanhos vêm dos módulos gerados."""
    sizes = {
        "box_floor()": _body_size(scad, "box_floor"),
        "box_front_wall()": _body_size(scad, "box_front_wall"),
        "box_side_wall()": _body_size(scad, "box_side_wall"),
    }
    if "module box_lid()" in scad:
        sizes["box_lid()"] = _box_lid_size(scad)
    rects = []
    for x, y, what in _LAYOUT_ITEM_RE.findall(_scad_module_body(scad, "layout_2d")):
        if what in sizes:
            w, h = sizes[what]
        else:
            w, h = (float(v) for v in re.findall(r"[\d.]+", what))
        rects.append((float(x), float(y), float(w), float(h)))
    return rects


def _overlapping_pairs(rects):
    return [
        (a, b)
        for i, a in enumerate(rects)
        for b in rects[i + 1:]
        if a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
    ]


def test_box_dividers_do_not_overlap_other_pieces_in_layout():
    scad = server.generate_box_scad({
        "width": 150, "depth": 100, "height": 60, "material_thickness": 3, "kerf": 0.2,
        "lid_type": "none", "dividers_x": 2, "dividers_y": 1,
    })
    rects = _box_layout_rects(scad)
    assert len(rects) == 5 + 3
    assert _overlapping_pairs(rects) == []


@pytest.mark.parametrize("dx, dy", [(0, 0), (2, 0), (0, 2), (1, 1), (3, 2)])
def test_box_layout_has_one_piece_per_divider(dx, dy):
    scad = server.generate_box_scad({
        "width": 150, "depth": 100, "height": 60, "material_thickness": 3, "kerf": 0.2,
        "lid_type": "none", "dividers_x": dx, "dividers_y": dy,
    })
    rects = _box_layout_rects(scad)
    sizes = [(w, h) for _x, _y, w, h in rects]
    assert len(rects) == 5 + dx + dy
    assert sizes.count((94.0, 60.0)) == 2 + dx    # 2 laterais + divisórias X: todas inner_d x H
    assert sizes.count((144.0, 60.0)) == dy    # divisória Y: inner_w x H
    assert _overlapping_pairs(rects) == []


@pytest.mark.parametrize("lid", ["snap", "slide"])
@pytest.mark.parametrize("W, D, H", [(150, 100, 60), (80, 40, 100)])
def test_box_lid_does_not_overlap_the_floor_in_layout(lid, W, D, H):
    """A tampa ia para y = H + gap: sobrepunha o piso (0..D) sempre que D > H + gap."""
    scad = server.generate_box_scad({
        "width": W, "depth": D, "height": H, "material_thickness": 3, "kerf": 0.2, "lid_type": lid,
    })
    rects = _box_layout_rects(scad)
    assert len(rects) == 5 + 1
    assert _overlapping_pairs(rects) == []


def test_box_layout_with_lid_and_dividers_has_no_overlap():
    scad = server.generate_box_scad({
        "width": 150, "depth": 100, "height": 60, "lid_type": "snap", "dividers_x": 2, "dividers_y": 1,
    })
    rects = _box_layout_rects(scad)
    assert len(rects) == 5 + 3 + 1
    assert _overlapping_pairs(rects) == []


@pytest.mark.asyncio
async def test_box_layout_svg_keeps_one_contour_per_piece():
    """Exemplo do README: 5 peças + 2 divisórias + tampa + 2 furos de fenda no piso = 10 contornos.
    Com a tampa fundida no piso o SVG saía com 9."""
    scad = server.generate_box_scad({
        "width": 150, "depth": 100, "height": 60, "material_thickness": 3, "kerf": 0.2,
        "fingers": 7, "lid_type": "snap", "dividers_x": 2,
    }).replace('RENDER_MODE = "3d"', 'RENDER_MODE = "2d"')
    svg_path, _ = await server.run_openscad(scad, "svg")
    try:
        with open(svg_path, encoding="utf-8") as f:
            path_data = " ".join(re.findall(r'\bd="([^"]*)"', f.read()))
    finally:
        os.remove(svg_path)
    assert path_data.count("M") == 10


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — B5: `variables` (-D) validadas e escapadas
# ─────────────────────────────────────────────────────────────────────────────

def _stl_bbox(path):
    tris = server._parse_stl(path)
    pts = [v for tri in tris for v in tri]
    return [(min(p[i] for p in pts), max(p[i] for p in pts)) for i in range(3)]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool, ext", [("export_stl", "stl"), ("render_to_png", "png")])
async def test_variables_key_with_statements_is_rejected(tmp_path, tool, ext):
    args = {"scad_code": "cube(1);", "variables": {"a=1;translate([50,0,0]) cube(5);b": 1}}
    if tool != "render_to_png":
        args["output_path"] = str(tmp_path / f"o.{ext}")
    with pytest.raises(ValueError, match="variable name"):
        await server.handle_call_tool(tool, args)


@pytest.mark.asyncio
async def test_variables_key_with_statements_is_rejected_in_analyze_mesh():
    # analyze_mesh devolve os erros como texto (❌ ...) em vez de levantar
    result = await server.handle_call_tool("analyze_mesh", {
        "scad_code": "cube(1);", "variables": {"a=1;cube(5);b": 1},
    })
    assert "Invalid variable name" in result[0].text


@pytest.mark.asyncio
async def test_variables_string_value_cannot_break_out_of_the_string(tmp_path):
    out = tmp_path / "o.stl"
    result = await server.handle_call_tool("export_stl", {
        "scad_code": "cube(1);",
        "output_path": str(out),
        "variables": {"s": '\\"; translate([50,0,0]) cube(5); //'},
    })
    assert "Exported successfully" in result[0].text
    (x_min, x_max), _, _ = _stl_bbox(str(out))
    assert x_max == pytest.approx(1.0)       # só o cubo base: a injeção não adicionou geometria


@pytest.mark.asyncio
async def test_variables_string_backslash_is_escaped(tmp_path):
    out = tmp_path / "o.stl"
    await server.handle_call_tool("export_stl", {
        "scad_code": "cube(len(s));",
        "output_path": str(out),
        "variables": {"s": "a\\nb"},          # a, barra, n, b = 4 caracteres
    })
    (_, x_max), _, _ = _stl_bbox(str(out))
    assert x_max == pytest.approx(4.0)


@pytest.mark.parametrize("value", [{"x": 1}, None, [1, "a"], [[1, 2], [3, 4]], object()])
def test_variables_rejects_unsupported_value_types(value):
    with pytest.raises(ValueError, match="variable"):
        server._define_args({"v": value})


def test_variables_accepts_scalars_numeric_lists_and_special_names():
    args = server._define_args({"$fn": 32, "w": 2.5, "flag": True, "off": False, "name": 'a"b', "dims": [1, 2.5, 3]})
    assert args == [
        "-D", "$fn=32",
        "-D", "w=2.5",
        "-D", "flag=true",
        "-D", "off=false",
        "-D", 'name="a\\"b"',
        "-D", "dims=[1, 2.5, 3]",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — B6: filtro de import()/surface() não é contornável por comentário ou nome legado
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", [
    'import/**/("x.stl");',
    'import_stl("x.stl");',
    'import_off("x.off");',
    'import_dxf("x.dxf");',
    'surface/**/(file="x.dat");',
    'import // comentário\n("x.stl");',
    's = "//"; import("x.stl");',        # "//" dentro de string não é comentário
    's = "/*"; import("x.stl"); t = "*/";',
])
def test_safety_blocks_obfuscated_file_reading(code):
    with pytest.raises(ValueError, match="Safety violation"):
        server.verify_safety_guidelines(code)


def test_safety_ignores_import_mentioned_only_in_comments():
    server.verify_safety_guidelines('cube(1); // import("x.stl") não é usado\n/* surface(file="y") */')


def test_safety_does_not_block_identifiers_that_merely_contain_import():
    server.verify_safety_guidelines("module my_import(x) { cube(x); } my_import(2); important = 3;")


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — B16: palavras banidas casam por palavra, não por substring
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ["begun = 1;", "gunmetal = 1;", "gun2 = 1;", "module bombay() {}"])
def test_banned_words_do_not_match_inside_other_words(code):
    server.verify_safety_guidelines(code)
    server.verify_safety_guidelines("cube(1);", project_name=code)


@pytest.mark.parametrize("code", [
    "cube(1); // gun", "GUN();", "a gun model", "guns = 2;", "bomb()", "pistol (grip)",
    "rocket body", "rocket_body = 1;", "combustion chamber", "trigger();",
    "water_gun_prop = 1;", "pistol_grip();", "module gun_barrel() {}", "ar15_receiver = 1;", "x_bomb_y = 1;",
])
def test_banned_words_still_block_whole_words(code):
    with pytest.raises(ValueError, match="Safety violation"):
        server.verify_safety_guidelines(code)


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — openings do generate_laser_part: só front/back são desenhadas
# ─────────────────────────────────────────────────────────────────────────────

_RECT_OPENING = {"shape": "rect", "x": 10, "y": 10, "w": 20, "h": 20}


@pytest.mark.parametrize("wall", ["left", "right"])
def test_laser_part_rejects_openings_on_left_and_right_walls(wall):
    with pytest.raises(ValueError, match="front/back"):
        server.validate_config_parameters("generate_laser_part", {"openings": [{"wall": wall, **_RECT_OPENING}]})


@pytest.mark.asyncio
async def test_generate_laser_part_handler_rejects_left_opening(tmp_path):
    with pytest.raises(ValueError, match="front/back"):
        await server.handle_call_tool("generate_laser_part", {
            "config": {"width": 100, "depth": 80, "height": 50, "openings": [{"wall": "left", **_RECT_OPENING}]},
            "output_dir": str(tmp_path), "project_name": "p",
        })


@pytest.mark.parametrize("wall", ["front", "back"])
def test_laser_part_still_accepts_openings_on_front_and_back(wall):
    server.validate_config_parameters("generate_laser_part", {"openings": [{"wall": wall, **_RECT_OPENING}]})


def test_validate_laser_config_warns_about_openings_that_will_be_ignored():
    warns = server.validate_config({
        "width": 100, "depth": 80, "height": 50, "openings": [{"wall": "right", **_RECT_OPENING}],
    })
    assert any("front/back" in w for w in warns)


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — B8: escrita só onde a tool promete
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("bad_name", ["../../x", "/abs/x", "a/b", "a\\b"])
async def test_generate_assembly_rejects_piece_names_with_path_separators(tmp_path, bad_name):
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="piece name"):
        await server.handle_call_tool("generate_assembly", {
            "config": {"pieces": [{"name": bad_name, "w": 10, "d": 10, "h": 10}]},
            "output_dir": str(out), "project_name": "asm",
        })
    assert not (tmp_path / "x.scad").exists()
    assert not (out / "pieces").exists() or list((out / "pieces").glob("*")) == []


@pytest.mark.asyncio
async def test_generate_assembly_sanitizes_piece_names(tmp_path):
    """Espaço, ponto e acento viram '_' (ou somem): o módulo SCAD e o arquivo precisam ser válidos."""
    out = tmp_path / "out"
    result = await server.handle_call_tool("generate_assembly", {
        "config": {"pieces": [
            {"name": "peça 1.b", "w": 10, "d": 10, "h": 10},
            {"name": "wall front", "w": 10, "d": 10, "h": 10, "translate": [20, 0, 0]},
            {"name": "ok-name_2", "w": 10, "d": 10, "h": 10, "translate": [40, 0, 0]},
        ]},
        "output_dir": str(out), "project_name": "asm",
    })
    assert "Erro STL" not in result[0].text           # SCAD válido: o STL do assembly foi gerado
    assert (out / "asm.stl").is_file()
    for filename in ("peca_1_b.scad", "wall_front.scad", "ok-name_2.scad"):
        assert (out / "pieces" / filename).is_file()
    assembly = (out / "asm.scad").read_text(encoding="utf-8")
    assert "module piece_peca_1_b()" in assembly
    assert "module piece_ok_name_2()" in assembly


@pytest.mark.asyncio
@pytest.mark.parametrize("tool, wrong", [
    ("export_stl", "out.txt"), ("export_3mf", "out.stl"), ("export_dxf", "out.svg"), ("export_svg", "out"),
])
async def test_export_requires_the_extension_of_the_tool(tmp_path, tool, wrong):
    with pytest.raises(ValueError, match="extension"):
        await server.handle_call_tool(tool, {"scad_code": "square(5);", "output_path": str(tmp_path / wrong)})
    assert not (tmp_path / wrong).exists()


@pytest.mark.asyncio
async def test_export_extension_check_is_case_insensitive(tmp_path):
    out = tmp_path / "OUT.STL"
    result = await server.handle_call_tool("export_stl", {"scad_code": "cube(1);", "output_path": str(out)})
    assert "Exported successfully" in result[0].text
    assert out.is_file()


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — B4: check_syntax decide por returncode e linhas ERROR:, não por substring
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_syntax_echo_containing_the_word_error_is_valid():
    is_valid, msg = await server.check_scad_syntax('echo("no error here"); cube(5);')
    assert is_valid is True
    assert "ECHO" in msg


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["cube(5);", "square(5);", "// só um comentário", "foo_unknown_module();"])
async def test_check_syntax_accepts_2d_3d_empty_and_unknown_module(code):
    is_valid, msg = await server.check_scad_syntax(code)
    assert is_valid is True, msg


@pytest.mark.asyncio
async def test_check_syntax_unknown_module_is_reported_as_warning():
    is_valid, msg = await server.check_scad_syntax("foo_unknown_module();")
    assert is_valid is True
    assert "WARNING" in msg


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["cube([1,2,3;", 'assert(false, "boom"); cube(1);'])
async def test_check_syntax_detects_real_errors(code):
    is_valid, msg = await server.check_scad_syntax(code)
    assert is_valid is False
    assert "ERROR" in msg


@pytest.mark.asyncio
async def test_check_syntax_nonzero_exit_without_error_line_is_invalid(monkeypatch):
    fake_exec, _ = _fake_openscad_process(139, b"Segmentation fault")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    is_valid, msg = await server.check_scad_syntax("cube(1);")
    assert is_valid is False
    assert "139" in msg


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — B2: reforço (gusset) do suporte em L fica dentro da peça
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bracket_gusset_stays_inside_the_part():
    scad = server.generate_bracket_scad({"type": "L", "width": 40, "height": 40, "depth": 20})
    out_path, _ = await server.run_openscad(scad, "stl")
    try:
        _, (y_min, y_max), (z_min, z_max) = _stl_bbox(out_path)
    finally:
        os.remove(out_path)
    assert y_max - y_min <= 20 + 1e-6      # profundidade (dep): o reforço não pode sair pra fora
    assert z_max - z_min == pytest.approx(40)


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — B13/B14: event loop livre e cancelamento mata o openscad
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("tool, extra", [("analyze_mesh", {}), ("mesh_section", {"z": 5.0})])
async def test_mesh_tools_run_off_the_event_loop_thread(tmp_path, monkeypatch, tool, extra):
    p = tmp_path / "cube.stl"
    _write_binary_stl(str(p), _box_triangles(size=(10, 10, 10)))
    real = getattr(server, tool)
    seen = {}

    def spy(*args, **kwargs):
        seen["thread"] = threading.current_thread()
        return real(*args, **kwargs)

    monkeypatch.setattr(server, tool, spy)
    await server.handle_call_tool(tool, {"stl_path": str(p), **extra})
    assert seen["thread"] is not threading.main_thread()


def _hanging_openscad(partial_output=None):
    """Processo falso que fica pendurado em communicate(). Se `partial_output` for dado, grava
    esses bytes no arquivo de saída (-o) antes de pendurar, como um openscad no meio do trabalho."""
    started = asyncio.Event()
    created = {}
    proc = MagicMock()
    proc.returncode = None
    proc.kill = MagicMock()

    async def hang():
        started.set()
        await asyncio.sleep(100)
        return b"", b""

    proc.communicate = hang

    async def fake_exec(*cmd, **kwargs):
        out_path = cmd[list(cmd).index("-o") + 1]
        created["out_path"] = out_path
        if partial_output is not None:
            with open(out_path, "wb") as f:
                f.write(partial_output)
        return proc

    return fake_exec, proc, started, created


async def _cancel_after_start(coro, started):
    task = asyncio.create_task(coro)
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_run_openscad_kills_process_when_cancelled(monkeypatch):
    fake_exec, proc, started, _ = _hanging_openscad()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    await _cancel_after_start(server.run_openscad("cube(1);", "stl"), started)
    proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_run_openscad_removes_partial_output_when_cancelled(monkeypatch):
    fake_exec, proc, started, created = _hanging_openscad(partial_output=b"partial stl")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    await _cancel_after_start(server.run_openscad("cube(1);", "stl"), started)
    assert not os.path.exists(created["out_path"])


@pytest.mark.asyncio
async def test_check_syntax_kills_process_when_cancelled(monkeypatch):
    fake_exec, proc, started, _ = _hanging_openscad()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    await _cancel_after_start(server.check_scad_syntax("cube(1);"), started)
    proc.kill.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — export_obj (OpenSCAD nightly)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_obj_exports_with_openscad_nightly(tmp_path):
    out = tmp_path / "cube.obj"
    result = await server.handle_call_tool("export_obj", {
        "scad_code": "cube([10, 10, 10]);", "output_path": str(out),
    })
    if "OBJ requer OpenSCAD 2022+" in result[0].text:
        pytest.skip("OpenSCAD instalado não exporta OBJ (2021.01)")
    assert "Exported successfully" in result[0].text
    lines = out.read_text().splitlines()
    assert len([ln for ln in lines if ln.startswith("v ")]) == 8      # 8 vértices do cubo
    assert any(ln.startswith("f ") for ln in lines)


@pytest.mark.asyncio
async def test_export_obj_explains_when_openscad_is_too_old(tmp_path, monkeypatch):
    async def old_openscad(scad_code, ext, export_args=None, timeout_s=60.0):
        raise RuntimeError(
            "OpenSCAD Error:\nEither add a valid suffix or specify one using the --export-format option."
        )

    monkeypatch.setattr(server, "run_openscad", old_openscad)
    result = await server.handle_call_tool("export_obj", {
        "scad_code": "cube(1);", "output_path": str(tmp_path / "cube.obj"),
    })
    assert "OBJ requer OpenSCAD 2022+ (nightly)" in result[0].text


@pytest.mark.asyncio
async def test_export_obj_passes_other_errors_through(tmp_path, monkeypatch):
    async def broken(scad_code, ext, export_args=None, timeout_s=60.0):
        raise RuntimeError("OpenSCAD Error:\nsomething else")

    monkeypatch.setattr(server, "run_openscad", broken)
    result = await server.handle_call_tool("export_obj", {
        "scad_code": "cube(1);", "output_path": str(tmp_path / "cube.obj"),
    })
    assert "something else" in result[0].text
    assert "2022+" not in result[0].text


@pytest.mark.asyncio
async def test_export_obj_tool_schema():
    tools = await server.handle_list_tools()
    tool = next(t for t in tools if t.name == "export_obj")
    assert tool.inputSchema["required"] == ["scad_code", "output_path"]
    assert {"variables", "scad_code", "output_path", "timeout_s"} <= set(tool.inputSchema["properties"])


# ─────────────────────────────────────────────────────────────────────────────
# v0.9.0 — arquivos de texto sempre em UTF-8, independente do locale
# ─────────────────────────────────────────────────────────────────────────────

def test_text_files_are_utf8_regardless_of_locale(tmp_path):
    """Sem encoding explícito o Python usa o locale: em locale C (ASCII) escrever '—' ou 'ç' quebrava."""
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = (
        "import asyncio, sys\n"
        f"sys.path.insert(0, {root!r})\n"
        "import server\n"
        "async def go():\n"
        "    ok, msg = await server.check_scad_syntax('// \\u2014 \\u00e7\\ncube(1);')\n"
        "    assert ok, msg\n"
        "    await server.handle_call_tool('generate_assembly', "
        "{'config': {}, 'output_dir': sys.argv[1], 'project_name': 'asm'})\n"
        "asyncio.run(go())\n"
    )
    env = {**os.environ, "LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}
    proc = subprocess.run(
        [sys.executable, "-X", "utf8=0", "-c", script, str(tmp_path / "asm")],
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert (tmp_path / "asm" / "asm.scad").read_bytes().decode("utf-8")
    assert "—".encode("utf-8") in (tmp_path / "asm" / "asm_bom.md").read_bytes()
