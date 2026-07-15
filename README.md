# MCP OpenSCAD Server

An MCP (Model Context Protocol) server for interacting with OpenSCAD. This server enables LLMs and Agents to autonomously generate, render, and export parametric CAD designs for 3D printing, laser cutting, and CNC machining.

## Features

- **render_to_png**: Render an OpenSCAD script into a PNG preview image.
- **export_stl**: Export 3D OpenSCAD designs to STL files (for 3D Printing).
- **export_dxf**: Export 2D OpenSCAD designs to DXF files (for Laser Cutting / CNC).
- **export_svg**: Export 2D OpenSCAD designs to SVG files (for Laser Engraving / Cutting).

## Requirements

- OpenSCAD installed and available in the system PATH (`openscad`).
- Python 3.10+
- The `mcp` Python SDK.

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running the Server

You can connect to this server via `stdio` using the MCP SDK or configure it in your Agent's `mcp_config.json`:

```json
{
  "mcpServers": {
    "openscad": {
      "command": "/path/to/mcp-openscad/venv/bin/python3",
      "args": ["/path/to/mcp-openscad/server.py"]
    }
  }
}
```
