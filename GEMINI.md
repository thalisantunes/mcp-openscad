# MCP-OpenSCAD — Contexto para Agentes de IA

## Projeto
Servidor MCP para OpenSCAD — geração paramétrica de projetos para corte a laser, impressão 3D e CNC.

- **Versão atual:** v0.7.0
- **Arquivo principal:** `server.py`
- **Testes:** 274 testes · 95% cobertura
- **CI:** GitHub Actions (lint + test)

## Ferramentas disponíveis (25)

### Export
- `render_to_png` — Preview PNG de qualquer código SCAD
- `export_stl` — Exporta STL para impressão 3D
- `export_3mf` — Exporta 3MF (formato moderno de impressão 3D)
- `export_dxf` — Exporta DXF para laser / CNC
- `export_svg` — Exporta SVG para laser / gravação
- `check_syntax` — Valida sintaxe SCAD sem renderizar (rápido)

### Laser Cutting
- `generate_laser_part` — Gera 2D+3D com finger joints e aberturas
- `validate_laser_config` — Detecta problemas geométricos antes de cortar
- `generate_box` — Caixa com tampa (snap/slide/none) e divisórias
- `generate_kerf_test` — Placa de calibração de kerf
- `generate_finger_test` — Pente de teste de finger joints
- `estimate_material_use` — Calcula área e aproveitamento de chapa
- `generate_living_hinge` — Living hinge (straight/serpentine/cross)

### CNC
- `generate_dogbone` — Pocket com compensação dogbone/T-bone
- `generate_cnc_toolpath_hints` — Parâmetros CNC por material (8 materiais)

### Impressão 3D
- `generate_3d_box` — Caixa sólida com tampa snap-fit ou rosqueável
- `generate_bracket` — Suporte paramétrico (L, U, flat)
- `generate_enclosure` — Gabinete eletrônico com conectores e standoffs PCB
- `validate_printability` — Valida imprimibilidade FDM/resina
- `suggest_orientation` — Sugere melhor orientação de impressão
- `generate_tolerance_test` — Placa de calibração de tolerância
- `generate_bed_level_test` — Grade de discos para nivelamento
- `generate_retraction_test` — Torres de teste de retração

### Multi-peças
- `generate_assembly` — Projeto multi-peça com BOM e vista explodida

### Análise
- `analyze_mesh` — Analisa STL (binário/ASCII) ou SCAD para imprimibilidade: watertight, componentes flutuantes, volume, overhang e bridges (pura Python, sem numpy)

## Como executar
```bash
# Ativar ambiente
cd /home/thas/projetos/mcp-openscad
source .venv/bin/activate

# Rodar testes
python -m pytest tests/ -x -q

# Com cobertura
python -m pytest --cov=server --cov-report=term-missing tests/
```

## Referência do Roadmap
Ver `ROADMAP.md` para o plano completo de versões.

## Regras de Desenvolvimento
1. Cada nova ferramenta precisa de: função geradora + registro em `handle_list_tools` + handler em `handle_call_tool` + testes
2. Toda saída de arquivo deve passar por `validate_output_path` ou `safe_output_path`
3. Todo código SCAD deve passar por `verify_safety_guidelines`
4. Cobertura de testes deve se manter acima de 90%
5. Testes de integração devem rodar o OpenSCAD real
6. Novos geradores devem incluir valores padrão sensatos e guards contra inputs inválidos
7. Usar `async/await` corretamente — `run_openscad` e `check_scad_syntax` são async
8. Manter commits semânticos (feat:, fix:, test:, docs:, refactor:)
9. `run_openscad` aceita `timeout_s` (clamp [5, 900], default 60) — exposto como parâmetro opcional em `export_stl/3mf/dxf/svg` e `render_to_png`
10. `analyze_mesh`/`_parse_stl` não usam numpy — mantenha a análise de malha em Python puro

## Próximas Prioridades
- Sprint 3: Refatorar `handle_call_tool` (713 linhas → helper `_generate_and_export`)
- Sprint 4: Reforçar suite de testes (corrigir 3 testes fracos, 83+ cenários faltantes)
- Sprint 5: Modularizar `server.py` em pacote `mcp_openscad/`
- v0.5.2: Projetos híbridos laser + 3D
- v0.5.3: Export profissional (DXF layers, STEP, PDF assembly)
- v1.0.0: Release estável no PyPI
