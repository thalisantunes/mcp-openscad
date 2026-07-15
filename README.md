# mcp-openscad

> Servidor MCP (Model Context Protocol) que permite agentes de IA interagir com o OpenSCAD para gerar, renderizar e exportar designs CAD paramétricos para fabricação digital — laser cutting, impressão 3D e CNC.

## Versão atual: v0.3.0

### Ferramentas disponíveis (16)

#### Exportação Básica
| Ferramenta | Descrição |
|---|---|
| `render_to_png` | Preview PNG de qualquer código SCAD |
| `export_stl` | Exporta STL para impressão 3D |
| `export_3mf` | Exporta 3MF (formato moderno de impressão 3D) |
| `export_dxf` | Exporta DXF para laser / CNC |
| `export_svg` | Exporta SVG para laser / gravação |
| `check_syntax` | Valida sintaxe SCAD sem renderizar (rápido) |

#### Corte a Laser
| Ferramenta | Descrição |
|---|---|
| `generate_laser_part` | Gera 2D+3D com finger joints, aberturas (porta/janela), layout automático → SCAD+SVG+DXF+PNG |
| `validate_laser_config` | Detecta problemas geométricos antes de cortar |
| `generate_box` | Caixa retangular com tampa (snap/slide/none) e divisórias internas |
| `generate_kerf_test` | Placa de calibração de kerf — pinos macho + fendas fêmea com kerf variado |
| `generate_finger_test` | Pente de teste de finger joints com múltiplos offsets |
| `estimate_material_use` | Calcula área total e aproveitamento da chapa |

#### Impressão 3D
| Ferramenta | Descrição |
|---|---|
| `generate_3d_box` | Caixa sólida paramétrica com tampa snap-fit ou rosqueável |
| `generate_bracket` | Suporte/mancal paramétrico (tipo L, U ou flat) com furos de montagem |
| `generate_enclosure` | Gabinete eletrônico com catálogo de conectores e pilares para PCB |
| `validate_printability` | Valida imprimibilidade: paredes, overhang, layer height, proporções |

## Instalação

```bash
git clone https://github.com/thalisantunes/mcp-openscad
cd mcp-openscad
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Requisito externo: [OpenSCAD](https://openscad.org/downloads.html) deve estar instalado e no `PATH`.

## Uso

```bash
source venv/bin/activate
python server.py
```

### Configuração no Claude Desktop / Antigravity

```json
{
  "mcpServers": {
    "openscad": {
      "command": "/path/to/venv/bin/python",
      "args": ["/path/to/mcp-openscad/server.py"]
    }
  }
}
```

## Exemplos rápidos

### Caixa para laser
```json
{
  "tool": "generate_box",
  "config": {
    "width": 150, "depth": 100, "height": 60,
    "material_thickness": 3, "kerf": 0.2,
    "fingers": 7, "lid_type": "snap", "dividers_x": 2
  },
  "output_dir": "/tmp/minha_caixa",
  "project_name": "caixa_ferramentas"
}
```

### Teste de kerf
```json
{
  "tool": "generate_kerf_test",
  "config": { "material_thickness": 3, "kerf_min": 0.1, "kerf_max": 0.4, "kerf_step": 0.05 },
  "output_dir": "/tmp", "project_name": "kerf_mdf3"
}
```

### Gabinete eletrônico
```json
{
  "tool": "generate_enclosure",
  "config": {
    "width": 120, "depth": 80, "height": 40,
    "wall": 2.5, "lid_type": "snap",
    "connectors": [
      {"wall": "front", "type": "usb_c", "x": 30, "y": 12},
      {"wall": "back",  "type": "barrel_jack", "x": 20, "y": 15}
    ],
    "pcb_standoffs": [{"x": 5,"y":5},{"x":110,"y":5},{"x":5,"y":70},{"x":110,"y":70}]
  },
  "output_dir": "/tmp/gabinete", "project_name": "esp32_case"
}
```

### Validar antes de imprimir
```json
{
  "tool": "validate_printability",
  "config": {
    "wall_thickness": 1.5, "bottom_thickness": 0.6,
    "height": 60, "width": 50, "depth": 40,
    "overhang_angle": 50, "layer_height": 0.2,
    "profile": "fdm_standard"
  }
}
```

## Desenvolvimento

```bash
# Rodar testes
source venv/bin/activate
python -m pytest tests/ -v

# Cobertura
python -m pytest tests/ --cov=server --cov-report=term-missing
```

Cobertura atual: **90%** — 84 testes.

## Roadmap

Ver [ROADMAP.md](./ROADMAP.md) para o plano completo.

## Calibração conhecida

| Material | Kerf | fit_allowance | Slot (t=3mm) |
|---|---|---|---|
| MDF 3mm | 0.2mm | 0.2mm | 2.8mm |
| Acrílico 3mm | 0.15mm | — | — |

## Stack técnico

- Python 3.10+ · `mcp` SDK · OpenSCAD CLI
- Testes: `pytest` + `pytest-asyncio` + `pytest-cov`
- CI: GitHub Actions
