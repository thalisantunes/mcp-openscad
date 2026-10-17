# mcp-openscad

<!-- mcp-name: io.github.thalisantunes/mcp-openscad -->

![CI](https://github.com/thalisantunes/mcp-openscad/actions/workflows/test.yml/badge.svg)
![Coverage](https://img.shields.io/badge/coverage-94%25-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Version](https://img.shields.io/badge/version-0.9.0-blue)

> Servidor MCP (Model Context Protocol) que permite agentes de IA interagir com o OpenSCAD para gerar, renderizar e exportar designs CAD paramétricos para fabricação digital — laser cutting, impressão 3D e CNC.

## Versão atual: v0.9.0

### Ferramentas disponíveis (27)

A coluna **Obrigatórios** lista o que o schema da ferramenta exige; o resto tem valor padrão.
`config{...}` quer dizer que o objeto `config` precisa ter essas chaves.

#### Exportação Básica (7)
| Ferramenta | Obrigatórios | Descrição |
|---|---|---|
| `render_to_png` | `scad_code` | Preview PNG de qualquer código SCAD (aceita `camera`, `size`, `variables`) |
| `export_stl` | `scad_code`, `output_path` | Exporta STL para impressão 3D |
| `export_3mf` | `scad_code`, `output_path` | Exporta 3MF (formato moderno de impressão 3D) |
| `export_dxf` | `scad_code`, `output_path` | Exporta DXF para laser / CNC (o SCAD precisa ser 2D) |
| `export_svg` | `scad_code`, `output_path` | Exporta SVG para laser / gravação (o SCAD precisa ser 2D) |
| `export_obj` | `scad_code`, `output_path` | Exporta OBJ para Blender / Godot — **só no OpenSCAD nightly** |
| `check_syntax` | `scad_code` | Valida sintaxe SCAD sem gerar geometria (rápido) |

#### Corte a Laser (8)
| Ferramenta | Obrigatórios | Descrição |
|---|---|---|
| `generate_laser_part` | `config{width, depth, height}`, `output_dir`, `project_name` | Gera 2D+3D com finger joints, aberturas, layout automático → SCAD+SVG+DXF+PNG |
| `validate_laser_config` | `config` | Detecta problemas geométricos antes de cortar |
| `generate_box` | `config{width, depth, height}`, `output_dir`, `project_name` | Caixa retangular com tampa (snap/slide/none) e divisórias internas |
| `generate_kerf_test` | `output_dir`, `project_name` | Placa de calibração de kerf — pinos macho + fendas fêmea |
| `generate_finger_test` | `output_dir`, `project_name` | Pente de teste de finger joints com múltiplos offsets |
| `estimate_material_use` | `config` | Calcula área total e aproveitamento da chapa |
| `generate_living_hinge` | `output_dir`, `project_name` | Padrão de living hinge (straight/serpentine/cross) para MDF flexível |
| `generate_dogbone` | `output_dir`, `project_name` | Pocket com compensação dogbone/T-bone para cantos CNC |

#### Impressão 3D (8)
| Ferramenta | Obrigatórios | Descrição |
|---|---|---|
| `generate_3d_box` | `config{width, depth, height}`, `output_dir`, `project_name` | Caixa sólida paramétrica com tampa snap-fit ou anel `thread` (sem rosca real) |
| `generate_bracket` | `config{width, height, depth}`, `output_dir`, `project_name` | Suporte/mancal paramétrico (tipo L, U ou flat) com furos de montagem |
| `generate_enclosure` | `config{width, depth, height}`, `output_dir`, `project_name` | Gabinete eletrônico com catálogo de conectores e pilares para PCB |
| `validate_printability` | `config` | Valida imprimibilidade: paredes, overhang, layer height, proporções |
| `suggest_orientation` | `config` | Sugere a melhor orientação de impressão com análise de 3 eixos |
| `generate_tolerance_test` | `output_dir`, `project_name` | Placa de calibração de tolerância — pinos + furos com tolerância variada |
| `generate_bed_level_test` | `output_dir`, `project_name` | Grid de discos finos para teste de nivelamento da cama |
| `generate_retraction_test` | `output_dir`, `project_name` | Torres para teste de retração/stringing |

#### Multi-peça e Assembly (1)
| Ferramenta | Obrigatórios | Descrição |
|---|---|---|
| `generate_assembly` | `output_dir`, `project_name` | Projeto multi-peça com vista explodida e BOM automático em Markdown |

#### CNC (1)
| Ferramenta | Obrigatórios | Descrição |
|---|---|---|
| `generate_cnc_toolpath_hints` | `config` | Sugestões de parâmetros CNC (feed, RPM, DOC) por material e fresa |

#### Análise (2)
| Ferramenta | Obrigatórios | Descrição |
|---|---|---|
| `analyze_mesh` | `stl_path` **ou** `scad_code` | Analisa STL (binário/ASCII) ou SCAD: watertight, componentes flutuantes, volume, overhang e bridges — 100% Python |
| `mesh_section` | (`stl_path` **ou** `scad_code`) e (`z` **ou** `z_list`) | Corte transversal de STL/SCAD por um ou mais planos — fit-check de encaixes/press-fits (Ø externo/interno, parede, clearance) |

`output_dir` é obrigatório nas ferramentas que geram arquivos e deve ser um **caminho absoluto**
dentro das pastas permitidas (ver [Variáveis de ambiente](#variáveis-de-ambiente)).

## Skills

Além das ferramentas MCP, este repositório inclui skills do Claude Code em
[`skills/`](./skills):

| Skill | Uso |
|---|---|
| [`3d-print-gate`](./skills/3d-print-gate/SKILL.md) | Gate de qualidade pré-slicing: roda `analyze_mesh` + `mesh_section` em cada peça/encaixe de uma peça ou pasta de STLs, com tabela pass/fail, antes de liberar para o slicer |

A skill vive no repositório, então precisa do clone (a instalação por `uvx` não a traz). Dentro do clone:

```bash
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/3d-print-gate" ~/.claude/skills/3d-print-gate
```

## Instalação

### Requisitos

- **Python 3.10 ou mais novo.** O Python que vem com o macOS é o 3.9 e não instala o `mcp`
  (erro opaco do pip). Use o `uv` (`brew install uv`, ele baixa o Python certo sozinho) ou
  `brew install python@3.12`.
- **OpenSCAD.** O 2021.01 funciona, mas o **nightly (com Manifold) é o recomendado**: é bem mais
  rápido em booleanas pesadas, exporta OBJ (`export_obj`) e renderiza PNG sem display.
  No 2021.01 o PNG precisa de uma sessão gráfica; em Linux sem tela rode o servidor com `xvfb-run -a`.

### Instalar o OpenSCAD

| Sistema | Como |
|---|---|
| macOS | `brew install --cask openscad@snapshot` (nightly, universal, instala `/Applications/OpenSCAD.app` e o comando `openscad`). O cask `openscad` (2021.01) está **desabilitado desde 09/2026** por falhar no Gatekeeper. Alternativa: baixar o DMG em [openscad.org/downloads](https://openscad.org/downloads.html#snapshots), arrastar para `/Applications` e liberar: `xattr -dr com.apple.quarantine /Applications/OpenSCAD.app` |
| Linux | `sudo apt install openscad` (traz o 2021.01) ou o AppImage nightly de [openscad.org/downloads](https://openscad.org/downloads.html#snapshots) (`chmod +x` e aponte `OPENSCAD_PATH` para ele) |
| Windows | Não testado |

O servidor acha o binário sozinho (`OPENSCAD_PATH`, depois o `PATH`, depois `/opt/homebrew/bin`,
`/usr/local/bin`, `/Applications/OpenSCAD.app`, `/snap/bin` e `/usr/bin`). Confira com `openscad --version`
(no macOS a versão sai no stderr).

### Instalar o servidor

O pacote ainda **não está no PyPI**. Enquanto isso, o `uvx` instala direto do GitHub, sem clonar nada:

```bash
uvx --from git+https://github.com/thalisantunes/mcp-openscad mcp-openscad
```

Alternativa com clone (necessária para a skill e para desenvolver):

```bash
git clone https://github.com/thalisantunes/mcp-openscad
cd mcp-openscad
uv sync                    # cria o .venv com Python >= 3.10 e instala o mcp
uv run mcp-openscad        # ou: .venv/bin/python server.py
```

Sem `uv`: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

### Registrar no Claude Code

```bash
claude mcp add openscad -e MCP_OPENSCAD_ALLOWED_PATHS="$HOME:/tmp" -- uvx --from git+https://github.com/thalisantunes/mcp-openscad mcp-openscad
```

Com o clone, troque o trecho depois do `--` por `/caminho/do/mcp-openscad/.venv/bin/python /caminho/do/mcp-openscad/server.py`.

### Registrar no Claude Desktop

No macOS o arquivo é `~/Library/Application Support/Claude/claude_desktop_config.json`.
Apps com interface gráfica **não herdam o `PATH` do shell**, então use o caminho **absoluto**
do `uvx` (`which uvx`) e passe o resto pelo bloco `env`. O JSON não expande `~` nem `$HOME`:

```json
{
  "mcpServers": {
    "openscad": {
      "command": "/opt/homebrew/bin/uvx",
      "args": ["--from", "git+https://github.com/thalisantunes/mcp-openscad", "mcp-openscad"],
      "env": {
        "OPENSCAD_PATH": "/opt/homebrew/bin/openscad",
        "OPENSCADPATH": "/Users/SEU_USUARIO/Documents/OpenSCAD/libraries",
        "MCP_OPENSCAD_ALLOWED_PATHS": "/Users/SEU_USUARIO:/tmp"
      }
    }
  }
}
```

Reinicie o Claude Desktop depois de salvar. O mesmo bloco serve para outros clientes MCP
(ex.: Antigravity); só muda o arquivo de configuração.

### Variáveis de ambiente

| Variável | Para que serve | Padrão |
|---|---|---|
| `OPENSCAD_PATH` | Caminho absoluto do binário do OpenSCAD (use quando ele não está no `PATH`, como em apps gráficos) | `openscad` no `PATH`, depois os locais conhecidos |
| `OPENSCADPATH` | Pastas de bibliotecas `.scad` (`include <...>` / `use <...>`), separadas por `:`. É lida pelo próprio OpenSCAD, que herda o ambiente do servidor. No macOS a pasta do usuário é `~/Documents/OpenSCAD/libraries` | — |
| `MCP_OPENSCAD_ALLOWED_PATHS` | Pastas onde o servidor pode gravar saídas e ler `stl_path`, separadas por `:`. **Substitui** a lista padrão (não acrescenta) | `~`, a pasta temporária do sistema, `/tmp`, `/var/tmp` |

Os caminhos são resolvidos (symlinks incluídos) antes de comparar: no macOS `/tmp` vale `/private/tmp`.
Escrever fora das pastas permitidas dá `Access denied`. Use sempre caminhos absolutos em `output_dir`;
um caminho relativo é resolvido a partir do diretório de trabalho do servidor, que em apps gráficos costuma ser `/`.

## Exemplos rápidos

Os blocos JSON abaixo são um **pseudo-formato** para leitura: `tool` ao lado dos argumentos. Na chamada
real do protocolo (JSON-RPC `tools/call`) o nome vai em `name` e os argumentos em `arguments`:
`{"name": "generate_box", "arguments": {"config": {...}, "output_dir": "...", "project_name": "..."}}`.

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

### Peça de laser com aberturas
```json
{
  "tool": "generate_laser_part",
  "config": {
    "width": 120, "depth": 80, "height": 60,
    "material_thickness": 3, "kerf": 0.2, "fingers": 5,
    "openings": [
      {"wall": "front", "shape": "rect", "x": 40, "y": 10, "w": 40, "h": 25},
      {"wall": "back", "shape": "circle", "cx": 60, "cy": 30, "d": 20}
    ]
  },
  "output_dir": "/tmp/peca_laser", "project_name": "caixa_com_janelas"
}
```
`wall` é `front` ou `back`: aberturas em `left` e `right` ainda não são desenhadas e por isso são recusadas.
`shape` é `rect` (`x`, `y`, `w`, `h`) ou `circle` (`cx`, `cy`, `d`).
Gera 4 paredes e o piso (sem tampa), mais o layout 2D em SVG/DXF.

### Caixa 3D para impressão
```json
{
  "tool": "generate_3d_box",
  "config": {
    "width": 80, "depth": 60, "height": 40,
    "wall_thickness": 2, "bottom_thickness": 2,
    "lid_type": "snap", "corner_radius": 3, "lid_height": 10, "tolerance": 0.2
  },
  "output_dir": "/tmp/caixa3d", "project_name": "caixa_snap"
}
```
`lid_type`: `snap`, `thread` (anel liso, sem rosca) ou `none`.

### Suporte em L
```json
{
  "tool": "generate_bracket",
  "config": {
    "type": "L", "width": 40, "height": 40, "depth": 20, "wall": 3,
    "mount_holes": 4, "mount_hole_d": 3.2, "hole_d": 8, "gusset": true
  },
  "output_dir": "/tmp/suporte", "project_name": "suporte_l"
}
```
`type`: `L`, `U` ou `flat`; `mount_holes`: 0, 2 ou 4.

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
Tipos de conector: `usb_a`, `usb_c`, `usb_mini`, `micro_usb`, `barrel_jack`, `hdmi`, `ethernet`, `audio_35`,
`switch`, `button_12`, `oled_128x64` e `custom` (informe `w` e `h`). Paredes: `front`, `back`, `left`, `right`
e `top`. `x` corre ao longo da parede (em `left`/`right`, ao longo da profundidade) e `y` é a altura acima do
piso interno; em `top`, `x` e `y` são a posição no plano da tampa.

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

### Preview com câmera
```json
{
  "tool": "render_to_png",
  "scad_code": "cube([20, 20, 20]); translate([25, 0, 0]) sphere(10);",
  "camera": {"translate": [10, 10, 5], "rotate": [60, 0, 30], "distance": 120, "projection": "ortho"},
  "size": {"width": 1024, "height": 768}
}
```
`translate`, `rotate` e `distance` valem juntos: se faltar um, a câmera é ignorada e o OpenSCAD centraliza
o modelo sozinho. `projection` é `perspective` (padrão) ou `ortho`.

### Exportar OBJ (Blender, Godot)
```json
{
  "tool": "export_obj",
  "scad_code": "sphere(10, $fn=24);",
  "output_path": "/tmp/esfera.obj"
}
```
Só funciona no OpenSCAD nightly. No 2021.01 a resposta é `OBJ requer OpenSCAD 2022+ (nightly)`.
glTF/GLB não existe em nenhuma versão do OpenSCAD: converta o OBJ no Blender.

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

## Limitações e segurança

- **`import()` e `surface()` são bloqueados** (também `import_stl`, `import_off` e `import_dxf`), mesmo escondidos
  em comentários como `import/**/(...)`. Dá para analisar um STL existente com `analyze_mesh` / `mesh_section` via
  `stl_path`, mas não importá-lo dentro do SCAD. `include <...>` e `use <...>` não são bloqueados.
- **Filtro de palavras.** Código SCAD e `project_name` com `firearm`, `gun`, `pistol`, `rifle`, `silencer`, `receiver`,
  `trigger`, `bullet`, `explosive`, `grenade`, `bomb`, `missile`, `rocket body`, `propellant` ou `combustion chamber`
  (e bocais de foguete) são recusados. A busca é por palavra inteira, com ou sem `s` no fim, e `_` separa palavras:
  `begun`, `gunmetal` e `gun2` passam; `gun`, `guns`, `water_gun_prop` e `pistol_grip` não. Ainda pode dar falso
  positivo em props de jogo ou RC (`receiver`, `trigger`).
- **`variables`** (`-D`): o nome precisa ser um identificador (`largura`, `$fn`) e o valor um bool, número, string
  ou lista de números. Qualquer outra coisa é recusada, porque o OpenSCAD avalia `-D` como código.
- **Escrita.** `output_path` precisa terminar com a extensão da ferramenta (`.stl`, `.3mf`, `.dxf`, `.svg`, `.obj`) e
  tudo fica dentro das pastas permitidas. Nos nomes de peça do `generate_assembly`, acentos perdem o sinal e o que
  não for letra, dígito, `_` ou `-` vira `_` (`peça 1.b` vira o arquivo `peca_1_b.scad`); `/` e `\` são recusados.
- **`check_syntax`** só interpreta e avalia o modelo, sem gerar geometria (limite de 15 s). Erros que só aparecem na
  hora de renderizar, como geometria vazia, ficam para o `export_*` / `render_to_png`.
- **Tampa `thread`** do `generate_3d_box` é um anel liso, não uma rosca. Para rosca de verdade use uma biblioteca
  como a BOSL2, apontando `OPENSCADPATH` para ela.
- **STL de `generate_3d_box` e `generate_enclosure`** traz corpo e tampa juntos (a tampa flutua acima do corpo),
  então o `analyze_mesh` vai acusar componente flutuante. Separe as peças antes de fatiar.
- **Layout de laser** (`generate_box`, `generate_laser_part`) é uma fileira única: confira o comprimento total contra
  o tamanho da chapa. `estimate_material_use` só soma áreas, não faz nesting.

## Solução de problemas

| Mensagem | Causa | O que fazer |
|---|---|---|
| `OpenSCAD não encontrado. Instale (...) ou defina OPENSCAD_PATH=...` | O servidor não achou o binário. Em apps gráficos (Claude Desktop) o `PATH` do shell não existe | Instale o OpenSCAD e ponha `OPENSCAD_PATH` com o caminho absoluto (`which openscad`) no bloco `env`. Se a mensagem disser `OPENSCAD_PATH='...' foi ignorado`, esse caminho não existe ou não é executável |
| `Access denied: Path '...' is outside allowed directories.` | `output_dir`, `output_path` ou `stl_path` fora das pastas permitidas (no macOS, p. ex., `/Volumes/...`) | Use um caminho absoluto dentro de `~` ou `/tmp`, ou liste a pasta em `MCP_OPENSCAD_ALLOWED_PATHS` (isso substitui o padrão: inclua `~` de novo se ainda precisar dele) |
| `OpenSCAD Error: exit code -11` ao gerar PNG (versões anteriores à 0.9.0 respondiam `Rendered successfully.` com imagem vazia) | `-11` é o OpenSCAD 2021.01 morrendo com segfault por não conseguir abrir um contexto OpenGL, geralmente sem sessão gráfica (SSH, serviço, Linux sem tela) | Use o nightly, ou em Linux rode o servidor com `xvfb-run -a`; no macOS use uma sessão gráfica logada |
| `❌ Timeout ao verificar sintaxe.` | O `check_syntax` passou de 15 s | Modelo muito pesado ou OpenSCAD travado. Rode `export_stl` com `timeout_s` maior (até 900) ou use o nightly |

## Desenvolvimento

```bash
uv sync --extra dev        # .venv com pytest, pytest-asyncio e pytest-cov

# Rodar testes
uv run pytest tests/ -v

# Cobertura
uv run pytest tests/ --cov=server --cov-report=term-missing
```

Cobertura atual: **94%** — 424 testes (rodados com OpenSCAD nightly). No 2021.01 os testes que
dependem de PNG precisam de display: sem ele são pulados com o motivo "OpenSCAD sem contexto GL (2021.01 sem
display)", e o CI roda sob `xvfb-run`.

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

- Python 3.10+ · `mcp` SDK (1.10 a 1.x) · OpenSCAD CLI (2021.01 ou nightly)
- Testes: `pytest` + `pytest-asyncio` + `pytest-cov`
- CI: GitHub Actions
