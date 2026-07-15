# Contexto do Projeto: MCP-OpenSCAD

## O que é este projeto
Servidor MCP (Model Context Protocol) que permite agentes de IA interagir com o OpenSCAD para gerar, renderizar e exportar designs CAD paramétricos para fabricação digital.

## Versão atual
**v0.2.0** — inclui ferramentas de exportação básica + geração inteligente para laser cutting.

## Ferramentas disponíveis (server.py)
- `render_to_png` — preview PNG
- `export_stl`, `export_3mf`, `export_dxf`, `export_svg`, `export_csg`, `export_amf` — exportações
- `generate_laser_part` — geração inteligente 2D+3D a partir de JSON config com finger joints automáticos, respeito a aberturas (porta/janela), layout automático, exporta .scad + .svg + .dxf + PNG
- `validate_laser_config` — validação pré-corte que detecta peças soltas e erros geométricos

## Roadmap completo
Ver [ROADMAP.md](./ROADMAP.md) para o plano completo v0.3 → v1.0.

### Próximas prioridades (v0.3)
1. `generate_box` — caixa retangular com tampa
2. `generate_kerf_test` — placa de calibração de kerf
3. Suporte a painéis inclinados (telhado) em `generate_laser_part`
4. Tipos de junção: T-slot, lap joint

### Próximas prioridades (v0.4)
1. `generate_3d_box`, `generate_bracket`, `generate_enclosure` — objetos 3D paramétricos
2. `validate_printability` — validação para impressão 3D

## Calibração de materiais conhecida
- **MDF 3mm**: kerf = 0.2mm (fit_allowance = 0.2mm → slot de 2.8mm encaixa perfeitamente)

## Stack técnico
- Python 3.10+, MCP SDK (`mcp`), OpenSCAD CLI
- Ambiente virtual: `venv/`
- Testes: `tests/`
- CI: `.github/`

## Como rodar
```bash
source venv/bin/activate
python server.py
```

## Regras de desenvolvimento
- Sempre testar imports antes de commitar: `python -c "import server; print('OK')"`
- Manter consistência entre `generate_laser_part` (server.py) e os arquivos SCAD gerados
- Novos módulos SCAD gerados NUNCA devem duplicar código — usar arquivo único com `RENDER_MODE`
- Finger joints SEMPRE devem pular dentes/slots que caem sob aberturas (porta, janela)
