# mcp-openscad

<!-- mcp-name: io.github.thalisantunes/mcp-openscad -->

![CI](https://github.com/thalisantunes/mcp-openscad/actions/workflows/test.yml/badge.svg)
![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Version](https://img.shields.io/badge/version-0.8.0-blue)

> Servidor MCP (Model Context Protocol) que permite agentes de IA interagir com o OpenSCAD para gerar, renderizar e exportar designs CAD paramétricos para fabricação digital — laser cutting, impressão 3D e CNC.

## Versão atual: v0.8.0

### Ferramentas disponíveis (26)

#### Exportação Básica (6)
| Ferramenta | Descrição |
|---|---|
| `render_to_png` | Preview PNG de qualquer código SCAD |
| `export_stl` | Exporta STL para impressão 3D |
| `export_3mf` | Exporta 3MF (formato moderno de impressão 3D) |
| `export_dxf` | Exporta DXF para laser / CNC |
| `export_svg` | Exporta SVG para laser / gravação |
| `check_syntax` | Valida sintaxe SCAD sem renderizar (rápido) |

#### Corte a Laser (8)
| Ferramenta | Descrição |
|---|---|
| `generate_laser_part` | Gera 2D+3D com finger joints, aberturas, layout automático → SCAD+SVG+DXF+PNG |
| `validate_laser_config` | Detecta problemas geométricos antes de cortar |
| `generate_box` | Caixa retangular com tampa (snap/slide/none) e divisórias internas |
| `generate_kerf_test` | Placa de calibração de kerf — pinos macho + fendas fêmea |
| `generate_finger_test` | Pente de teste de finger joints com múltiplos offsets |
| `estimate_material_use` | Calcula área total e aproveitamento da chapa |
| `generate_living_hinge` | Padrão de living hinge (straight/serpentine/cross) para MDF flexível |
| `generate_dogbone` | Pocket com compensação dogbone/T-bone para cantos CNC |

#### Impressão 3D (8)
| Ferramenta | Descrição |
|---|---|
| `generate_3d_box` | Caixa sólida paramétrica com tampa snap-fit ou rosqueável |
| `generate_bracket` | Suporte/mancal paramétrico (tipo L, U ou flat) com furos de montagem |
| `generate_enclosure` | Gabinete eletrônico com catálogo de conectores e pilares para PCB |
| `validate_printability` | Valida imprimibilidade: paredes, overhang, layer height, proporções |
| `suggest_orientation` | Sugere a melhor orientação de impressão com análise de 3 eixos |
| `generate_tolerance_test` | Placa de calibração de tolerância — pinos + furos com tolerância variada |
| `generate_bed_level_test` | Grid de discos finos para teste de nivelamento da cama |
| `generate_retraction_test` | Torres para teste de retração/stringing |

#### Multi-peça e Assembly (1)
| Ferramenta | Descrição |
|---|---|
| `generate_assembly` | Projeto multi-peça com vista explodida e BOM automático em Markdown |

#### CNC (1)
| Ferramenta | Descrição |
|---|---|
| `generate_cnc_toolpath_hints` | Sugestões de parâmetros CNC (feed, RPM, DOC) por material e fresa |

#### Análise (2)
| Ferramenta | Descrição |
|---|---|
| `analyze_mesh` | Analisa STL (binário/ASCII) ou SCAD: watertight, componentes flutuantes, volume, overhang e bridges — 100% Python |
| `mesh_section` | Corte transversal de STL/SCAD por um ou mais planos — fit-check de encaixes/press-fits (Ø externo/interno, parede, clearance) |

## Skills

Além das ferramentas MCP, este repositório inclui skills do Claude Code em
[`skills/`](./skills):

| Skill | Uso |
|---|---|
| [`3d-print-gate`](./skills/3d-print-gate/SKILL.md) | Gate de qualidade pré-slicing: roda `analyze_mesh` + `mesh_section` em cada peça/encaixe de uma peça ou pasta de STLs, com tabela pass/fail, antes de liberar para o slicer |

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

### Living hinge para laser
```json
{
  "tool": "generate_living_hinge",
  "config": {
    "width": 200, "height": 100,
    "material_thickness": 3, "kerf": 0.2,
    "pattern": "serpentine", "cut_length": 15
  },
  "output_dir": "/tmp/hinge", "project_name": "flex_cover"
}
```

### Assembly multi-peça com BOM
```json
{
  "tool": "generate_assembly",
  "config": {
    "project_name": "caixa_simples",
    "pieces": [
      {"name": "base", "w": 100, "d": 60, "h": 3, "color": [0.9, 0.8, 0.6]},
      {"name": "front", "w": 100, "d": 3, "h": 40, "translate": [0,0,3], "color": [0.7, 0.5, 0.4]},
      {"name": "back", "w": 100, "d": 3, "h": 40, "translate": [0,57,3], "color": [0.7, 0.5, 0.4]},
      {"name": "left", "w": 3, "d": 54, "h": 40, "translate": [0,3,3], "color": [0.6, 0.5, 0.5]},
      {"name": "right", "w": 3, "d": 54, "h": 40, "translate": [97,3,3], "color": [0.6, 0.5, 0.5]}
    ]
  },
  "output_dir": "/tmp/assembly", "project_name": "caixa_asm"
}
```

### Sugestão de orientação para impressão 3D
```json
{
  "tool": "suggest_orientation",
  "config": {
    "width": 80, "depth": 60, "height": 200,
    "has_flat_bottom": true, "has_holes_yz": true,
    "profile": "fdm_standard"
  }
}
```

### Parâmetros CNC
```json
{
  "tool": "generate_cnc_toolpath_hints",
  "config": {
    "material": "acrylic",
    "material_thickness": 5,
    "tool_d": 3.175,
    "cut_type": "pocket",
    "finishing_pass": true
  }
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

### Análise de malha (imprimibilidade)
```json
{
  "tool": "analyze_mesh",
  "stl_path": "/tmp/minha_peca.stl",
  "overhang_deg": 45,
  "bed_tol": 0.3
}
```
Ou direto a partir de código SCAD (exporta STL internamente antes de analisar):
```json
{
  "tool": "analyze_mesh",
  "scad_code": "cube([30,30,10]);",
  "timeout_s": 120
}
```

### Corte transversal (fit-check de encaixe)
```json
{
  "tool": "mesh_section",
  "stl_path": "/tmp/tubo.stl",
  "z_list": [5, 10, 15],
  "axis": "z"
}
```
Útil para comparar Ø externo de um pino com o Ø interno (bore) da peça fêmea
correspondente na mesma altura de encaixe — ver a skill
[`3d-print-gate`](./skills/3d-print-gate/SKILL.md).

### Timeout configurável de render
`export_stl`, `export_3mf`, `export_dxf`, `export_svg` e `render_to_png` aceitam `timeout_s`
(padrão 60s, limitado a [5, 900]s) para peças complexas que demoram mais para renderizar:
```json
{
  "tool": "export_stl",
  "scad_code": "...",
  "output_path": "/tmp/peca_complexa.stl",
  "timeout_s": 300
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

Cobertura atual: **94%** — 288 testes.

## Roadmap

Ver [ROADMAP.md](./ROADMAP.md) para o plano completo.

## Calibração conhecida

| Material | Kerf | fit_allowance | Slot (t=3mm) |
|---|---|---|---|
| MDF 3mm | 0.2mm | 0.2mm | 2.8mm |
| Acrílico 3mm | 0.15mm | — | — |

## Materiais CNC suportados

| Material | Feed rate | Spindle RPM | DOC (% fresa) |
|---|---|---|---|
| MDF | 1500 mm/min | 18000 | 50% |
| Plywood | 1200 mm/min | 16000 | 40% |
| Acrílico | 800 mm/min | 14000 | 30% |
| Madeira dura | 1000 mm/min | 16000 | 35% |
| Madeira macia | 1800 mm/min | 18000 | 60% |
| Alumínio | 500 mm/min | 10000 | 15% |
| Espuma | 3000 mm/min | 12000 | 100% |
| HDPE | 1000 mm/min | 12000 | 40% |

## Stack técnico

- Python 3.10+ · `mcp` SDK · OpenSCAD CLI
- Testes: `pytest` + `pytest-asyncio` + `pytest-cov`
- CI: GitHub Actions
