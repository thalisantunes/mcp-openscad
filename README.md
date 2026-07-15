# MCP OpenSCAD Server

An MCP (Model Context Protocol) server for interacting with OpenSCAD. This server enables LLMs and Agents to autonomously generate, render, and export parametric CAD designs for **3D printing**, **laser cutting**, and **CNC machining**.

> See [ROADMAP.md](./ROADMAP.md) for the full development plan.

---

## Features

### Export Tools
| Tool | Description |
|---|---|
| `render_to_png` | Render any OpenSCAD script to a PNG preview image |
| `export_stl` | Export 3D designs to STL (for 3D printing) |
| `export_3mf` | Export 3D designs to 3MF (modern 3D printing format) |
| `export_dxf` | Export 2D designs to DXF (for laser cutting / CNC) |
| `export_svg` | Export 2D designs to SVG (for laser engraving / cutting) |
| `export_csg` | Export designs to CSG (Constructive Solid Geometry) |
| `export_amf` | Export designs to AMF (Additive Manufacturing Format) |

### Intelligent Generation Tools (v0.2+)

#### `generate_laser_part`
Generates a complete laser cutting project from a simple JSON config — no OpenSCAD knowledge needed.

- **Smart finger joints** that automatically skip teeth under openings (door/windows), preventing floating pieces
- **Automatic 2D layout** of all panels with proper spacing — no manual positioning
- **Single source of truth** — one `.scad` file with `RENDER_MODE = "2d"` or `"3d"` toggle
- Exports `.scad` + `.svg` + `.dxf` + preview PNG in one call

```json
{
  "material_thickness": 3,
  "kerf": 0.2,
  "width": 100,
  "depth": 100,
  "height": 80,
  "fingers": 5,
  "openings": [
    { "wall": "front", "shape": "rect",   "x": 35, "y": 0,  "w": 30, "h": 45 },
    { "wall": "front", "shape": "circle", "cx": 50, "cy": 62, "d": 20 },
    { "wall": "back",  "shape": "circle", "cx": 50, "cy": 40, "d": 30 }
  ]
}
```

#### `validate_laser_config`
Pre-flight geometry validation **before** generating any files. Detects:
- Teeth that would fall under openings (causing floating pieces on the laser cutter)
- Openings exceeding panel dimensions
- Other geometric problems with exact location reporting

---

## Requirements

- OpenSCAD installed and available in the system PATH (`openscad`)
- Python 3.10+
- The `mcp` Python SDK

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running the Server

Configure in your Agent's `mcp_config.json`:

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

---

## Roadmap

See [ROADMAP.md](./ROADMAP.md) for the full plan. Highlights:

- **v0.3** — Laser: roof panels, box generator, kerf test, living hinges
- **v0.4** — 3D Printing: parametric generators, printability validation, printer profiles
- **v0.5** — CNC routing, hybrid laser+3D projects, professional exports (STEP, G-Code)
- **v1.0** — Stable release, PyPI package, full documentation
