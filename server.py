import os
import subprocess
import tempfile
import asyncio
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

server = Server("mcp-openscad")

def run_openscad(scad_code: str, output_ext: str, export_args=None):
    if export_args is None:
        export_args = []
    
    with tempfile.NamedTemporaryFile(suffix=".scad", delete=False, mode='w') as f:
        f.write(scad_code)
        scad_path = f.name
    
    out_path = scad_path.replace(".scad", f".{output_ext}")
    
    cmd = ["openscad", "-o", out_path] + export_args + [scad_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return out_path, result.stdout
    except subprocess.CalledProcessError as e:
        if os.path.exists(out_path):
            os.remove(out_path)
        if os.path.exists(scad_path):
            os.remove(scad_path)
        raise RuntimeError(f"OpenSCAD Error:\n{e.stderr}")
    finally:
        # We leave the out_path for the user to read, but we should clean up the scad_path
        if os.path.exists(scad_path):
            os.remove(scad_path)

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="render_to_png",
            description="Render OpenSCAD code to a PNG image preview.",
            inputSchema={
                "type": "object",
                "properties": {
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
                    "scad_code": {"type": "string", "description": "The OpenSCAD source code"},
                    "output_path": {"type": "string", "description": "Absolute path to save the .stl file"}
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
                    "scad_code": {"type": "string", "description": "The OpenSCAD source code (must be 2D)"},
                    "output_path": {"type": "string", "description": "Absolute path to save the .dxf file"}
                },
                "required": ["scad_code", "output_path"]
            }
        ),
        types.Tool(
            name="export_svg",
            description="Export 2D OpenSCAD code to an SVG file for laser engraving/cutting.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scad_code": {"type": "string", "description": "The OpenSCAD source code (must be 2D)"},
                    "output_path": {"type": "string", "description": "Absolute path to save the .svg file"}
                },
                "required": ["scad_code", "output_path"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if not arguments or "scad_code" not in arguments:
        raise ValueError("Missing 'scad_code' argument")
    
    scad_code = arguments["scad_code"]
    
    if name == "render_to_png":
        try:
            out_path, stdout = run_openscad(scad_code, "png", ["--autocenter", "--viewall"])
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

    elif name in ["export_stl", "export_dxf", "export_svg"]:
        if "output_path" not in arguments:
            raise ValueError("Missing 'output_path' argument")
        
        output_path = arguments["output_path"]
        ext = name.split("_")[1] # stl, dxf, or svg
        
        try:
            out_path, stdout = run_openscad(scad_code, ext)
            # move from tmp to output_path
            import shutil
            shutil.move(out_path, output_path)
            return [types.TextContent(type="text", text=f"Exported successfully to {output_path}")]
        except Exception as e:
            return [types.TextContent(type="text", text=str(e))]
            
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-openscad",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
