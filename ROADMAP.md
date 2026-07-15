# MCP OpenSCAD — Roadmap Completo

> **Objetivo:** Transformar o `mcp-openscad` na ferramenta de fabricação digital mais inteligente para agentes de IA — cobrindo corte a laser, impressão 3D e CNC com geração paramétrica, validação automática e exportação pronta para máquina.

---

## Estado atual — v0.2.0 ✅

| Ferramenta | Descrição |
|---|---|
| `render_to_png` | Preview PNG de qualquer código SCAD |
| `export_stl` | Exporta STL para impressão 3D |
| `export_3mf` | Exporta 3MF (formato moderno de impressão 3D) |
| `export_dxf` | Exporta DXF para laser / CNC |
| `export_svg` | Exporta SVG para laser / gravação |
| `export_csg` | Exporta CSG (geometria sólida) |
| `export_amf` | Exporta AMF (fabricação aditiva) |
| `generate_laser_part` | Gera 2D+3D inteligente para laser com finger joints, aberturas e layout automático |
| `validate_laser_config` | Detecta problemas geométricos antes de cortar |

---

## v0.3 — Laser Cutting Completo
> _Foco: tornar o gerador de peças a laser robusto e profissional_

### v0.3.1 — Tipos de junção adicionais
- [ ] **T-slot joint** — encaixe em T com porca de martelo (muito usado em estruturas)
- [ ] **Lap joint** — meia-madeira (overlap de 50% da espessura)
- [ ] **Puzzle joint** — encaixe curvilíneo (bom para painéis curvos)
- [ ] **Dado joint** — fenda rebaixada (para prateleiras dentro de caixas)
- [ ] Parâmetro `joint_type` no `generate_laser_part`

### v0.3.2 — Telhado e formas inclinadas
- [ ] **Painéis inclinados** com ângulo configurável (`roof_angle`, `pitch`)
- [ ] **Butt-joint no cumeeira** (painel longo/curto automático)
- [ ] Suporte a paredes com topo triangular (gável/frontão)
- [ ] Geração de slots nos painéis de telhado alinhados com a rampa

### v0.3.3 — Gerador de caixas avançado
- [ ] `generate_box` — caixa retangular completa com tampa encaixável
- [ ] Opções de tampa: **dobradiça laser** (living hinge), **parafuso**, **encaixe por pressão**
- [ ] Caixas com divisórias internas configuráveis
- [ ] Suporte a pés/niveladores (pequenos dentes de apoio na base)

### v0.3.4 — Ferramentas de qualidade de corte
- [ ] `generate_kerf_test` — gera placa de teste para calibrar o kerf da sua máquina
- [ ] `generate_finger_test` — gera pente de teste de encaixes (vários offsets de 0.1 em 0.1mm)
- [ ] `estimate_material_use` — calcula área total usada e retorna % de aproveitamento da chapa
- [ ] Detecção de peças muito pequenas que podem cair durante o corte

### v0.3.5 — Engravings e decorações 2D
- [ ] Suporte a **texto gravado** (engraving) com fonte configurável
- [ ] **Living hinge** — padrão de corte que deixa o MDF/acrílico flexível
- [ ] **Dogbone corners** — cantos com círculo para compensar fresa de CNC
- [ ] Suporte a importar SVG externo como decoração

---

## v0.4 — Impressão 3D Inteligente
> _Foco: geração paramétrica para impressão 3D com consciência de fabricação_

### v0.4.1 — Gerador de objetos 3D paramétricos
- [ ] `generate_3d_box` — caixa sólida com tampa rosqueável ou por encaixe
- [ ] `generate_bracket` — suportes/mancais com furos de montagem configuráveis
- [ ] `generate_enclosure` — gabinete eletrônico com furações para conectores, display e botões
- [ ] `generate_thread` — rosca ISO métrica (M3–M20) paramétrica para porcas e parafusos impressos

### v0.4.2 — Validação para impressão 3D
- [ ] `validate_printability` — verifica:
  - [ ] Paredes muito finas (< 1.2mm para FDM padrão)
  - [ ] Overhangs > 45° sem suporte
  - [ ] Peças isoladas (não-manifold)
  - [ ] Dimensões mínimas de detalhes
  - [ ] Espessura de fundo/topo em múltiplos de altura de camada
- [ ] `suggest_orientation` — sugere a melhor orientação de impressão para minimizar suportes

### v0.4.3 — Configuração por perfil de impressora
- [ ] Perfis pré-definidos: **FDM padrão** (0.4mm nozzle, 0.2mm layer), **Resina**, **FDM fino** (0.2mm nozzle)
- [ ] `tolerance` automático por perfil (folga para peças encaixáveis)
- [ ] Geração de **textura de superfície** (grelha, honeycomb) para economia de material

### v0.4.4 — Placas de teste e calibração
- [ ] `generate_tolerance_test` — peças macho/fêmea com escala de tolerâncias (0.1mm a 0.5mm)
- [ ] `generate_bed_level_test` — padrão de nivelamento de cama
- [ ] `generate_retraction_test` — torre de teste de retração

### v0.4.5 — Multi-peças e assemblies
- [ ] `generate_assembly` — projetos com múltiplas peças encaixáveis (impressas + laser)
- [ ] Exportação individual de cada peça com nome descritivo
- [ ] **BOM (Bill of Materials)** automático em Markdown

---

## v0.5 — CNC e Fabricação Híbrida
> _Foco: suporte a fresamento CNC e projetos que combinam múltiplos processos_

### v0.5.1 — CNC Routing
- [ ] `generate_cnc_toolpath_hints` — sugere passadas e profundidades de corte por material
- [ ] **Dogbone automático** em todos os cantos internos
- [ ] **Tabs de fixação** (pontes que mantêm a peça presa durante o corte)
- [ ] Geração de arquivo com marcações de zero-peça

### v0.5.2 — Projetos híbridos
- [ ] Projetos que combinam peças **laser (2D) + impressão 3D** em uma única assembly
- [ ] Geração separada por processo: "peças para laser", "peças para impressão"
- [ ] Conectores paramétricos laser/impressão (encaixe padrão)

### v0.5.3 — Exportação profissional
- [ ] DXF com **camadas separadas** (corte vs. gravação vs. marcação)
- [ ] PDF de montagem com dimensões anotadas
- [ ] **STEP** para compatibilidade com CAD profissional (FreeCAD, Fusion360)
- [ ] G-Code básico para pequenas fresadoras

---

## v0.6 — Infraestrutura e Developer Experience
> _Foco: tornar o servidor robusto, extensível e fácil de usar_

### v0.6.1 — Melhorias no servidor MCP
- [ ] Cache de geometrias compiladas (CSG tree) para re-exports rápidos
- [ ] Suporte a **OPENSCADPATH** para usar bibliotecas externas (BOSL2, OpenSCAD std)
- [ ] Opções avançadas de câmera: ângulo, zoom, perspectiva vs. ortográfica
- [ ] Streaming de preview PNG durante renderizações longas

### v0.6.2 — Biblioteca de componentes
- [ ] Biblioteca interna de módulos reutilizáveis (slots, tabs, hinges, threads)
- [ ] Módulos acessíveis via include automático nos arquivos gerados
- [ ] Compatibilidade com **BOSL2** (biblioteca OpenSCAD mais popular)
- [ ] Galeria de exemplos renderizados no README

### v0.6.3 — Observabilidade e diagnóstico
- [ ] Parsing aprimorado dos warnings/erros do OpenSCAD (mensagens amigáveis para LLMs)
- [ ] `check_syntax` — validação de sintaxe sem renderizar (rápido)
- [ ] Logs estruturados (JSON) para integração com ferramentas de monitoramento

### v0.6.4 — Testes e CI
- [x] Testes unitários básicos
- [ ] Testes de integração com OpenSCAD real (render e valida output)
- [ ] Testes de regressão visual (compara PNG com baseline)
- [ ] Coverage > 80%
- [ ] GitHub Actions: lint + test + render de todos os exemplos

---

## v1.0 — Release Estável

- [ ] Documentação completa de todas as ferramentas com exemplos
- [ ] Galeria de projetos feitos com o MCP (casa, caixa, gabinete, suporte...)
- [ ] Schema JSON validado para todos os configs
- [ ] Guia de contribuição claro
- [ ] Publicação no **PyPI** como pacote instalável
- [ ] Suporte a múltiplas instâncias do OpenSCAD em paralelo (fila de renderização)
- [ ] Plugin Antigravity oficial — integração nativa com o AGY CLI

---

## Backlog / Ideias Futuras

| Ideia | Justificativa |
|---|---|
| Integração com Printables/MakerWorld | Upload automático de STL gerado |
| Slicer hints (PrusaSlicer, Cura) | Enviar STL + perfil de impressão direto para o slicer |
| AR preview via WebXR | Ver o objeto no espaço real antes de imprimir |
| Suporte a STEP → SCAD reverso | Importar peça existente e parametrizá-la |
| Simulação de montagem | Verificar se as peças encaixam antes de cortar/imprimir |
| Estimativa de custo | Calcular custo por material, tempo de corte/impressão |

---

## Prioridade de Implementação

```
Alta prioridade (próximas sprints):
  v0.3.2  Telhado/painéis inclinados      → completa a casinha atual
  v0.3.3  generate_box                    → caso de uso mais comum em laser
  v0.3.4  generate_kerf_test              → necessidade imediata do usuário
  v0.4.1  Geradores 3D paramétricos       → expande para impressão 3D
  v0.4.2  validate_printability           → evita impressões falhas

Média prioridade:
  v0.3.1  Tipos de junção extras          → qualidade profissional
  v0.4.3  Perfis de impressora            → personalização real
  v0.5.1  CNC routing                     → novo processo de fabricação
  v0.6.1  Melhorias servidor              → performance e UX

Baixa prioridade (futuro):
  v0.5.x  Exportação profissional
  v0.6.x  Infraestrutura avançada
  v1.0    Release estável
```

---

## Versionamento

| Versão | Status | Foco principal |
|---|---|---|
| v0.1.0 | ✅ Released | Exportação básica (PNG, STL, DXF, SVG...) |
| v0.2.0 | ✅ Released | `generate_laser_part` + `validate_laser_config` |
| v0.3.x | 🔜 Próximo | Laser cutting profissional |
| v0.4.x | 📋 Planejado | Impressão 3D inteligente |
| v0.5.x | 📋 Planejado | CNC + fabricação híbrida |
| v0.6.x | 📋 Planejado | Infraestrutura e DX |
| v1.0.0 | 🏁 Meta | Produto estável e publicado |
