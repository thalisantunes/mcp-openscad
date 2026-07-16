# MCP OpenSCAD — Roadmap Completo

> **Objetivo:** Transformar o `mcp-openscad` na ferramenta de fabricação digital mais inteligente para agentes de IA — cobrindo corte a laser, impressão 3D e CNC com geração paramétrica, validação automática e exportação pronta para máquina.

---

## Estado atual — v0.4.0 ✅

| Ferramenta | Categoria | Descrição |
|---|---|---|
| `render_to_png` | Export | Preview PNG de qualquer código SCAD |
| `export_stl` | Export | Exporta STL para impressão 3D |
| `export_3mf` | Export | Exporta 3MF (formato moderno de impressão 3D) |
| `export_dxf` | Export | Exporta DXF para laser / CNC |
| `export_svg` | Export | Exporta SVG para laser / gravação |
| `check_syntax` | Export | Valida sintaxe SCAD sem renderizar (rápido) |
| `generate_laser_part` | Laser | Gera 2D+3D inteligente para laser com finger joints |
| `validate_laser_config` | Laser | Detecta problemas geométricos antes de cortar |
| `generate_box` | Laser | Caixa retangular completa com tampa e divisórias |
| `generate_kerf_test` | Laser | Placa de calibração de kerf |
| `generate_finger_test` | Laser | Pente de teste de finger joints |
| `estimate_material_use` | Laser | Calcula área e aproveitamento da chapa |
| `generate_living_hinge` | Laser | Padrão de living hinge (3 tipos de corte) |
| `generate_dogbone` | CNC | Pocket com compensação dogbone/T-bone |
| `generate_3d_box` | 3D | Caixa sólida com tampa snap-fit ou rosqueável |
| `generate_bracket` | 3D | Suporte paramétrico (L, U, flat) |
| `generate_enclosure` | 3D | Gabinete eletrônico com conectores e pilares PCB |
| `validate_printability` | 3D | Valida imprimibilidade FDM/resina |
| `suggest_orientation` | 3D | Sugere melhor orientação de impressão |
| `generate_tolerance_test` | 3D | Placa de calibração de tolerância |
| `generate_bed_level_test` | 3D | Grid de discos para teste de nivelamento |
| `generate_retraction_test` | 3D | Torres para teste de retração |
| `generate_assembly` | Multi | Projeto multi-peça com vista explodida + BOM |
| `generate_cnc_toolpath_hints` | CNC | Sugestões de parâmetros CNC por material |

**Testes:** 197 testes · 93% cobertura · CI GitHub Actions

---

## v0.3.x — Laser Cutting Completo

### v0.3.0 ✅ — Ferramentas base
- [x] `generate_laser_part` + `validate_laser_config`
- [x] `generate_box` (snap/slide/none + divisórias)
- [x] `generate_kerf_test` + `generate_finger_test`
- [x] `estimate_material_use` + `check_syntax`

### v0.3.1 — Tipos de junção adicionais (Futuro)
- [ ] **T-slot joint** — encaixe em T com porca de martelo
- [ ] **Lap joint** — meia-madeira (overlap de 50% da espessura)
- [ ] **Dado joint** — fenda rebaixada (para prateleiras dentro de caixas)
- [ ] Parâmetro `joint_type` no `generate_laser_part`

### v0.3.2 — Telhado e formas inclinadas (Futuro)
- [ ] **Painéis inclinados** com ângulo configurável (`roof_angle`, `pitch`)
- [ ] **Butt-joint no cumeeira** (painel longo/curto automático)
- [ ] Suporte a paredes com topo triangular (gável/frontão)

### v0.3.5 ✅ — Decorações 2D e CNC
- [x] **Living hinge** — padrão de corte flexível (straight/serpentine/cross)
- [x] **Dogbone corners** — compensação CNC em cantos internos

---

## v0.4 — Impressão 3D Inteligente ✅

### v0.4.0 ✅ — Impressão 3D avançada
- [x] `validate_printability` — verifica paredes, overhang, layer height
- [x] `suggest_orientation` — recomenda orientação com score
- [x] `generate_3d_box` — caixa com tampa snap-fit/rosqueável
- [x] `generate_bracket` — suporte paramétrico
- [x] `generate_enclosure` — gabinete eletrônico

### v0.4.4 ✅ — Placas de teste 3D
- [x] `generate_tolerance_test` — pinos/furos com tolerância variada
- [x] `generate_bed_level_test` — grid de discos finos
- [x] `generate_retraction_test` — torres de retração

### v0.4.5 ✅ — Multi-peças e assemblies
- [x] `generate_assembly` — projetos multi-peça com BOM
- [x] Exportação individual por peça com nome descritivo
- [x] **BOM (Bill of Materials)** automático em Markdown
- [x] Vista explodida configurável

---

## v0.5 — CNC e Fabricação Híbrida

### v0.5.1 ✅ — CNC Routing
- [x] `generate_cnc_toolpath_hints` — sugestões de parâmetros por material
- [x] Database de 8 materiais com feed rate, RPM, DOC
- [x] Cálculo automático de chip load e número de passes
- [x] Sugestão de tabs para perfil
- [x] Passe de acabamento automático
- [x] **Dogbone automático** via `generate_dogbone`

### v0.5.2 — Projetos híbridos (Futuro)
- [ ] Projetos que combinam peças **laser (2D) + impressão 3D** em uma assembly
- [ ] Geração separada por processo

### v0.5.3 — Exportação profissional (Futuro)
- [ ] DXF com **camadas separadas** (corte vs. gravação vs. marcação)
- [ ] PDF de montagem com dimensões anotadas
- [ ] **STEP** para compatibilidade com CAD profissional (FreeCAD, Fusion360)

---

## v0.6 — Infraestrutura e Developer Experience

### v0.6.1 — Melhorias no servidor MCP (Futuro)
- [ ] Cache de geometrias compiladas para re-exports rápidos
- [ ] Suporte a **OPENSCADPATH** para bibliotecas externas (BOSL2)
- [ ] Opções avançadas de câmera: ângulo, zoom, perspectiva vs. ortográfica

### v0.6.2 — Biblioteca de componentes (Futuro)
- [ ] Biblioteca interna de módulos reutilizáveis (slots, tabs, hinges, threads)
- [ ] Compatibilidade com **BOSL2**
- [ ] Galeria de exemplos renderizados no README

### v0.6.3 — Observabilidade
- [x] `check_syntax` — validação rápida de sintaxe
- [ ] Parsing aprimorado dos warnings/erros do OpenSCAD
- [ ] Logs estruturados (JSON)

### v0.6.4 — Testes e CI
- [x] Testes unitários — 197 testes
- [x] Testes de integração com OpenSCAD real
- [x] Coverage > 90% (atual: 93%)
- [x] GitHub Actions: lint + test
- [ ] Testes de regressão visual (compara PNG com baseline)
- [ ] Render de todos os exemplos no CI

---

## v1.0 — Release Estável

- [x] Documentação completa de todas as 24 ferramentas com exemplos
- [ ] Galeria de projetos feitos com o MCP (casa, caixa, gabinete, suporte...)
- [x] Guia de contribuição claro
- [x] Publicação no **PyPI** como pacote instalável (`pyproject.toml` pronto)
- [ ] Plugin Antigravity oficial — integração nativa com o AGY CLI
- [x] Licença MIT

---

## Backlog / Ideias Futuras

| Ideia | Justificativa |
|---|---|
| Integração com Printables/MakerWorld | Upload automático de STL gerado |
| Slicer hints (PrusaSlicer, Cura) | Enviar STL + perfil de impressão direto para o slicer |
| AR preview via WebXR | Ver o objeto no espaço real antes de imprimir |
| STEP → SCAD reverso | Importar peça existente e parametrizá-la |
| Estimativa de custo | Calcular custo por material, tempo de corte/impressão |
| Schema JSON | Validação de configs com jsonschema |

---

## Versionamento

| Versão | Status | Foco principal |
|---|---|---|
| v0.1.0 | ✅ Released | Exportação básica (PNG, STL, DXF, SVG...) |
| v0.2.0 | ✅ Released | `generate_laser_part` + `validate_laser_config` |
| v0.3.0 | ✅ Released | Caixas, testes, enclosures, brackets, printability |
| v0.4.0 | ✅ Released | Impressão 3D avançada, assemblies, living hinge, dogbone, CNC |
| v0.5.x | 📋 Planejado | Projetos híbridos + exportação profissional |
| v0.6.x | 📋 Planejado | Infraestrutura, BOSL2, cache, logs |
| v1.0.0 | 🏁 Meta | Produto estável e publicado no PyPI |
