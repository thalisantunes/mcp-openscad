# Contexto do Projeto: MCP-OpenSCAD

## O que é este projeto
Servidor MCP (Model Context Protocol) que permite agentes de IA interagir com o OpenSCAD para gerar, renderizar e exportar designs CAD paramétricos para fabricação digital.

## Versão atual
**v0.3.0** — 16 ferramentas cobrindo exportação básica, laser cutting completo e impressão 3D.

## Ferramentas disponíveis (server.py)

### Exportação Básica
- `render_to_png` — preview PNG (suporta variáveis -D)
- `export_stl`, `export_3mf`, `export_dxf`, `export_svg` — exportações com variáveis
- `check_syntax` — valida sintaxe SCAD sem renderizar (rápido, 15s timeout)

### Laser Cutting
- `generate_laser_part` — geração inteligente 2D+3D com finger joints, aberturas (porta/janela), layout, exporta .scad+.svg+.dxf+PNG
- `validate_laser_config` — validação pré-corte geométrica
- `generate_box` — caixa retangular com tampa snap/slide/none + divisórias + estimativa material
- `generate_kerf_test` — placa de calibração de kerf (pinos macho + fendas fêmea com kerf variado)
- `generate_finger_test` — pente de teste de finger joints (offsets variados, pares macho/fêmea)
- `estimate_material_use` — área e aproveitamento da chapa

### Impressão 3D
- `generate_3d_box` — caixa sólida com tampa snap-fit ou rosqueável, cantos arredondados
- `generate_bracket` — suporte em L/U/flat com furos de montagem e gusset diagonal
- `generate_enclosure` — gabinete eletrônico com catálogo de conectores (USB-A/C, HDMI, Ethernet, barrel jack, OLED, switch) e pilares PCB
- `validate_printability` — valida paredes, overhang, layer height, proporções (perfis: fdm_standard, fdm_fine, resin)

## Roadmap completo
Ver [ROADMAP.md](./ROADMAP.md) para o plano v0.4 → v1.0.

### Próximas prioridades (v0.4 — ainda não implementadas)
1. `suggest_orientation` — sugere melhor orientação de impressão
2. Perfis de impressora configuráveis (FDM 0.4, FDM 0.2, Resina)
3. `generate_assembly` — projetos multi-peça com BOM automático

### Próximas prioridades (v0.5 — CNC)
1. Dogbone corners automático em cantos internos
2. Tabs de fixação (pontes para o corte CNC)
3. `generate_cnc_toolpath_hints` — sugestões de passadas

## Calibração de materiais conhecida
- **MDF 3mm**: kerf = 0.2mm (fit_allowance = 0.2mm → slot de 2.8mm encaixa perfeitamente)
- **Acrílico 3mm**: kerf ≈ 0.15mm

## Stack técnico
- Python 3.10+, MCP SDK (`mcp`), OpenSCAD CLI
- Ambiente virtual: `venv/`
- Testes: `tests/` — 84 testes, 90% cobertura
- CI: `.github/`

## Como rodar
```bash
source venv/bin/activate
python server.py
```

## Regras de desenvolvimento
- Sempre testar imports antes de commitar: `python -c "import server; print('OK')"`
- Manter consistência entre os geradores (server.py) e os arquivos SCAD gerados
- Novos módulos SCAD NUNCA devem duplicar código — usar `RENDER_MODE` para 2D/3D
- Finger joints SEMPRE devem pular dentes/slots que caem sob aberturas (porta, janela)
- `generate_box`: forçar N ímpar internamente se o usuário passar N par
- `validate_printability`: não depende de OpenSCAD — é análise estática do config Python
- `check_syntax`: usa timeout de 15s (menor que run_openscad de 60s)
- Catálogo de conectores em `generate_enclosure`: `CONN_CATALOG` com dimensões reais em mm
