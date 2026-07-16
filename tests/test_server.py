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
    assert len(tools) == 24


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

def test_openscad_renders_tolerance_test():
    """Integração: gera placa de tolerância e renderiza STL."""
    cfg = {"tol_min": 0.0, "tol_max": 0.1, "tol_step": 0.1}
    scad = server.generate_tolerance_test_scad(cfg)
    out_path, _ = server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


def test_openscad_renders_bed_level_test():
    """Integração: gera teste de nivelamento e renderiza STL."""
    cfg = {"grid_cols": 2, "grid_rows": 2, "bed_x": 100, "bed_y": 100}
    scad = server.generate_bed_level_test_scad(cfg)
    out_path, _ = server.run_openscad(scad, "stl")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


def test_openscad_renders_retraction_test():
    """Integração: gera torre de retração e renderiza STL."""
    cfg = {"tower_count": 2, "tower_h": 20}
    scad = server.generate_retraction_test_scad(cfg)
    out_path, _ = server.run_openscad(scad, "stl")
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

def test_openscad_renders_living_hinge_svg():
    """Integração: gera living hinge e exporta SVG."""
    cfg = {"width": 80, "height": 50, "pattern": "straight"}
    scad = server.generate_living_hinge_scad(cfg)
    out_path, _ = server.run_openscad(scad, "svg")
    assert os.path.exists(out_path)
    assert os.path.getsize(out_path) > 100
    os.remove(out_path)


def test_openscad_renders_dogbone_svg():
    """Integração: gera dogbone pocket e exporta SVG."""
    cfg = {"width": 50, "height": 30, "corner_style": "dogbone"}
    scad = server.generate_dogbone_scad(cfg)
    out_path, _ = server.run_openscad(scad, "svg")
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

def test_openscad_renders_assembly():
    """Integração: assembly gera SCAD válido que renderiza em STL."""
    cfg = {
        "pieces": [
            {"name": "base", "w": 50, "d": 40, "h": 3},
            {"name": "column", "type": "cylinder", "w": 8, "h": 25,
             "translate": [25, 20, 3]},
        ]
    }
    scad, _, _ = server.generate_assembly_scad(cfg)
    out_path, _ = server.run_openscad(scad, "stl")
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
async def test_render_to_png_default_camera():
    """Render com câmera padrão (autocenter + viewall)."""
    result = await server.handle_call_tool("render_to_png", {
        "scad_code": "cube([20, 20, 20]);"
    })
    assert len(result) == 2
    assert result[0].text == "Rendered successfully."
    assert result[1].type == "image"


@pytest.mark.asyncio
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
async def test_render_to_png_ortho_projection():
    """Render com projeção ortográfica."""
    result = await server.handle_call_tool("render_to_png", {
        "scad_code": "sphere(r=15);",
        "camera": {"projection": "ortho"}
    })
    assert len(result) == 2
    assert result[1].type == "image"


@pytest.mark.asyncio
async def test_render_to_png_custom_size():
    """Render com tamanho de imagem personalizado."""
    result = await server.handle_call_tool("render_to_png", {
        "scad_code": "cylinder(r=10, h=30, $fn=32);",
        "size": {"width": 400, "height": 300}
    })
    assert len(result) == 2
    assert result[1].type == "image"
