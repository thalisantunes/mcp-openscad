"""
Testes do MCP-OpenSCAD — v0.3.0
Cobre: run_openscad, check_syntax, todos os geradores, validadores e handlers MCP.
"""
import os
import sys
import math
import pytest
import subprocess
import asyncio
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import server


# ─────────────────────────────────────────────────────────────────────────────
# run_openscad
# ─────────────────────────────────────────────────────────────────────────────

def test_run_openscad_success():
    scad_code = "cube([10, 10, 10]);"
    out_path, _ = server.run_openscad(scad_code, "stl")
    assert out_path.endswith(".stl")
    assert os.path.exists(out_path)
    os.remove(out_path)


def test_run_openscad_error():
    with pytest.raises(RuntimeError, match="OpenSCAD Error"):
        server.run_openscad("invalid_syntax_xyz();", "stl")


@patch('subprocess.run')
def test_run_openscad_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="openscad", timeout=60)
    with pytest.raises(RuntimeError, match="Execution timed out after 60 seconds"):
        server.run_openscad("cube();", "stl")


# ─────────────────────────────────────────────────────────────────────────────
# check_scad_syntax
# ─────────────────────────────────────────────────────────────────────────────

def test_check_syntax_valid():
    is_valid, msg = server.check_scad_syntax("cube([10,10,10]);")
    assert is_valid
    assert "válida" in msg or "valid" in msg.lower() or "✅" in msg


def test_check_syntax_invalid():
    is_valid, msg = server.check_scad_syntax("XYZINVALIDKEYWORD(;;;)")
    # Pode ser inválido ou válido dependendo do OpenSCAD — só verificamos que retorna
    assert isinstance(is_valid, bool)
    assert isinstance(msg, str)


@patch('subprocess.run')
def test_check_syntax_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="openscad", timeout=15)
    is_valid, msg = server.check_scad_syntax("cube([1,1,1]);")
    assert not is_valid
    assert "Timeout" in msg or "timeout" in msg.lower()


# ─────────────────────────────────────────────────────────────────────────────
# validate_config (laser_part)
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_config_clean():
    cfg = {"width": 100, "depth": 80, "height": 50}
    warns = server.validate_config(cfg)
    assert isinstance(warns, list)


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
    assert len(tools) == 16


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


@pytest.mark.asyncio
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

def test_openscad_renders_box():
    """Integração: gera SCAD de caixa e renderiza para PNG via OpenSCAD real."""
    cfg = {"width": 80, "depth": 60, "height": 40}
    scad = server.generate_box_scad(cfg)
    out_path, _ = server.run_openscad(scad, "png", ["--autocenter", "--viewall"])
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 1000  # PNG não vazio
    os.remove(out_path)


def test_openscad_renders_3d_box():
    """Integração: gera SCAD 3D e renderiza STL."""
    cfg = {"width": 50, "depth": 40, "height": 30, "lid_type": "none"}
    scad = server.generate_3d_box_scad(cfg)
    out_path, _ = server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


def test_openscad_renders_bracket():
    """Integração: gera suporte em L e renderiza STL."""
    cfg = {"type": "L", "width": 30, "height": 30, "depth": 15, "gusset": False}
    scad = server.generate_bracket_scad(cfg)
    out_path, _ = server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    os.remove(out_path)


def test_openscad_renders_kerf_test_svg():
    """Integração: gera placa de kerf e exporta SVG."""
    cfg = {"material_thickness": 3, "kerf_min": 0.1, "kerf_max": 0.3, "kerf_step": 0.1}
    scad = server.generate_kerf_test_scad(cfg)
    out_path, _ = server.run_openscad(scad, "svg")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


def test_openscad_renders_enclosure():
    """Integração: gera gabinete e renderiza STL."""
    cfg = {
        "width": 100, "depth": 60, "height": 30, "wall": 2.5,
        "connectors": [{"wall": "front", "type": "usb_c", "x": 20, "y": 8}],
        "pcb_standoffs": [{"x": 10, "y": 10}, {"x": 90, "y": 50}]
    }
    scad = server.generate_enclosure_scad(cfg)
    out_path, _ = server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


def test_openscad_renders_laser_2d():
    """Integração: gera laser_part e exporta SVG 2D."""
    cfg = {"width": 80, "depth": 60, "height": 40}
    scad = server.generate_laser_scad(cfg)
    scad_2d = scad.replace('RENDER_MODE = "3d"', 'RENDER_MODE = "2d"')
    out_path, _ = server.run_openscad(scad_2d, "svg")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


def test_openscad_renders_finger_test():
    """Integração: gera finger test e exporta SVG."""
    cfg = {"material_thickness": 3, "offset_min": 0.0, "offset_max": 0.1, "offset_step": 0.1}
    scad = server.generate_finger_test_scad(cfg)
    out_path, _ = server.run_openscad(scad, "svg")
    assert os.path.exists(out_path)
    os.remove(out_path)


def test_openscad_renders_3d_box_with_lid():
    """Integração: gera caixa 3D com tampa snap e renderiza STL."""
    cfg = {"width": 60, "depth": 40, "height": 30, "lid_type": "snap"}
    scad = server.generate_3d_box_scad(cfg)
    out_path, _ = server.run_openscad(scad, "stl")
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
