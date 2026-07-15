import os
import sys
import pytest
import subprocess
import asyncio
from unittest.mock import patch, MagicMock

# Add parent directory to path so we can import server
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import server

# --- Tests for run_openscad ---

def test_run_openscad_success(tmp_path):
    scad_code = "cube([10, 10, 10]);"
    out_path, stdout = server.run_openscad(scad_code, "stl")
    assert out_path.endswith(".stl")
    assert os.path.exists(out_path)
    os.remove(out_path)

def test_run_openscad_error():
    scad_code = "invalid_syntax();"
    with pytest.raises(RuntimeError) as exc:
        server.run_openscad(scad_code, "stl")
    assert "OpenSCAD Error" in str(exc.value)

@patch('subprocess.run')
def test_run_openscad_timeout(mock_run):
    # Simulate a timeout
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="openscad", timeout=60)
    scad_code = "cube();"
    with pytest.raises(RuntimeError) as exc:
        server.run_openscad(scad_code, "stl")
    assert "Execution timed out after 60 seconds" in str(exc.value)

# --- Tests for MCP Handlers ---

@pytest.mark.asyncio
async def test_handle_list_tools():
    tools = await server.handle_list_tools()
    assert len(tools) == 7
    tool_names = [t.name for t in tools]
    assert "render_to_png" in tool_names
    assert "export_stl" in tool_names
    assert "export_3mf" in tool_names
    assert "export_csg" in tool_names
    assert "export_amf" in tool_names
    assert "export_dxf" in tool_names
    assert "export_svg" in tool_names

@pytest.mark.asyncio
async def test_handle_call_tool_missing_args():
    with pytest.raises(ValueError, match="Missing 'scad_code' argument"):
        await server.handle_call_tool("export_stl", {})

@pytest.mark.asyncio
async def test_handle_call_tool_export_stl(tmp_path):
    out_path = str(tmp_path / "out.stl")
    scad_code = "cube([5, 5, 5]);"
    
    result = await server.handle_call_tool("export_stl", {
        "scad_code": scad_code,
        "output_path": out_path
    })
    
    assert len(result) == 1
    assert result[0].type == "text"
    assert "Exported successfully" in result[0].text
    assert os.path.exists(out_path)

@pytest.mark.asyncio
async def test_handle_call_tool_render_to_png():
    scad_code = "sphere(r=5);"
    result = await server.handle_call_tool("render_to_png", {
        "scad_code": scad_code
    })
    
    assert len(result) == 2
    assert result[0].type == "text"
    assert result[1].type == "image"
    assert result[1].mimeType == "image/png"
    assert len(result[1].data) > 100 # Should contain base64 data

@pytest.mark.asyncio
async def test_handle_call_tool_unknown():
    with pytest.raises(ValueError, match="Unknown tool: invalid_tool"):
        await server.handle_call_tool("invalid_tool", {"scad_code": "cube();"})

@pytest.mark.asyncio
async def test_handle_call_tool_variables(tmp_path):
    out_path = str(tmp_path / "out_var.stl")
    scad_code = "cube([w, w, w]);"
    
    # We pass a variable w=2
    result = await server.handle_call_tool("export_stl", {
        "scad_code": scad_code,
        "output_path": out_path,
        "variables": {
            "w": 2,
            "str_var": "test",
            "bool_var": True
        }
    })
    
    assert "Exported successfully" in result[0].text
    assert os.path.exists(out_path)
