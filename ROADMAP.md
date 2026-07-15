# MCP OpenSCAD — Roadmap Completo

> **Objetivo:** Transformar o `mcp-openscad` na ferramenta de fabricação digital mais inteligente para agentes de IA — cobrindo corte a laser, impressão 3D e CNC com geração paramétrica, validação automática e exportação pronta para máquina.

---

## Estado atual — v0.3.0 ✅

| Ferramenta | Descrição |
|---|---|
| `render_to_png` | Preview PNG de qualquer código SCAD |
| `export_stl` | Exporta STL para impressão 3D |
| `export_3mf` | Exporta 3MF (formato moderno de impressão 3D) |
| `export_dxf` | Exporta DXF para laser / CNC |
| `export_svg` | Exporta SVG para laser / gravação |
| `check_syntax` | Valida sintaxe SCAD sem renderizar (rápido) |
| `generate_laser_part` | Gera 2D+3D inteligente para laser com finger joints, aberturas e layout automático |
| `validate_laser_config` | Detecta problemas geométricos antes de cortar |
| `generate_box` | Caixa retangular completa com tampa (snap/slide/none) e divisórias internas |
| `generate_kerf_test` | Placa de calibração de kerf (pinos macho + fendas fêmea) |
| `generate_finger_test` | Pente de teste de finger joints com múltiplos offsets |
| `estimate_material_use` | Calcula área e aproveitamento da chapa |
| `generate_3d_box` | Caixa sólida paramétrica com tampa snap-fit ou rosqueável |
| `generate_bracket` | Suporte/mancal paramétrico (L, U, flat) com furos de montagem |
| `generate_enclosure` | Gabinete eletrônico com catálogo de conectores e pilares PCB |
| `validate_printability` | Valida imprimibilidade FDM/resina (paredes, overhang, camadas) |

**Testes:** 84 testes · 90% cobertura · CI GitHub Actions

---

## v0.3.x — Laser Cutting Completo (Pendente)

### v0.3.1 — Tipos de junção adicionais
- [ ] **T-slot joint** — encaixe em T com porca de martelo
- [ ] **Lap joint** — meia-madeira (overlap de 50% da espessura)
- [ ] **Dado joint** — fenda rebaixada (para prateleiras dentro de caixas)
- [ ] Parâmetro `joint_type` no `generate_laser_part`

### v0.3.2 — Telhado e formas inclinadas
- [ ] **Painéis inclinados** com ângulo configurável (`roof_angle`, `pitch`)
- [ ] **Butt-joint no cumeeira** (painel longo/curto automático)
- [ ] Suporte a paredes com topo triangular (gável/frontão)

### v0.3.5 — Engravings e decorações 2D
- [ ] Suporte a **texto gravado** (engraving) com fonte configurável
- [ ] **Living hinge** — padrão de corte que deixa o MDF/acrílico flexível
- [ ] **Dogbone corners** — cantos com círculo para compensar fresa de CNC

---

## v0.4 — Impressão 3D Inteligente (Parcialmente implementado)

### v0.4.2 — Validação avançada para impressão 3D ✅ (parcial)
- [x] `validate_printability` — verifica paredes, overhang, layer height, proporções
- [ ] Verificação de peças não-manifold
- [ ] Verificação de detalhes menores que resolução mínima
- [ ] `suggest_orientation` — sugere a melhor orientação de impressão

### v0.4.3 — Configuração por perfil de impressora
- [ ] Perfis: FDM padrão, FDM fino, Resina (parâmetros automáticos)
- [ ] `tolerance` automático por perfil
- [ ] Geração de **textura de superfície** (grelha, honeycomb)

### v0.4.4 — Placas de teste 3D
- [ ] `generate_tolerance_test` — peças macho/fêmea com escala de tolerâncias
- [ ] `generate_bed_level_test` — padrão de nivelamento de cama
- [ ] `generate_retraction_test` — torre de teste de retração

### v0.4.5 — Multi-peças e assemblies
- [ ] `generate_assembly` — projetos com múltiplas peças encaixáveis
- [ ] Exportação individual por peça com nome descritivo
- [ ] **BOM (Bill of Materials)** automático em Markdown

---

## v0.5 — CNC e Fabricação Híbrida

### v0.5.1 — CNC Routing
- [ ] `generate_cnc_toolpath_hints` — sugestões de passadas e profundidades por material
- [ ] **Dogbone automático** em todos os cantos internos
- [ ] **Tabs de fixação** (pontes que mantêm a peça presa durante o corte)
- [ ] Geração de arquivo com marcações de zero-peça

### v0.5.2 — Projetos híbridos
- [ ] Projetos que combinam peças **laser (2D) + impressão 3D** em uma assembly
- [ ] Geração separada por processo

### v0.5.3 — Exportação profissional
- [ ] DXF com **camadas separadas** (corte vs. gravação vs. marcação)
- [ ] PDF de montagem com dimensões anotadas
- [ ] **STEP** para compatibilidade com CAD profissional (FreeCAD, Fusion360)

---

## v0.6 — Infraestrutura e Developer Experience

### v0.6.1 — Melhorias no servidor MCP
- [ ] Cache de geometrias compiladas para re-exports rápidos
- [ ] Suporte a **OPENSCADPATH** para bibliotecas externas (BOSL2)
- [ ] Opções avançadas de câmera: ângulo, zoom, perspectiva vs. ortográfica

### v0.6.2 — Biblioteca de componentes
- [ ] Biblioteca interna de módulos reutilizáveis (slots, tabs, hinges, threads)
- [ ] Compatibilidade com **BOSL2**
- [ ] Galeria de exemplos renderizados no README

### v0.6.3 — Observabilidade
- [x] `check_syntax` — validação rápida de sintaxe
- [ ] Parsing aprimorado dos warnings/erros do OpenSCAD
- [ ] Logs estruturados (JSON)

### v0.6.4 — Testes e CI
- [x] Testes unitários — 84 testes
- [x] Testes de integração com OpenSCAD real
- [x] Coverage > 80% (atual: 90%)
- [x] GitHub Actions: lint + test
- [ ] Testes de regressão visual (compara PNG com baseline)
- [ ] Render de todos os exemplos no CI

---

## v1.0 — Release Estável

- [ ] Documentação completa de todas as 16 ferramentas com exemplos
- [ ] Galeria de projetos feitos com o MCP (casa, caixa, gabinete, suporte...)
- [ ] Schema JSON validado para todos os configs
- [ ] Guia de contribuição claro
- [ ] Publicação no **PyPI** como pacote instalável
- [ ] Plugin Antigravity oficial — integração nativa com o AGY CLI

---

## Backlog / Ideias Futuras

| Ideia | Justificativa |
|---|---|
| Integração com Printables/MakerWorld | Upload automático de STL gerado |
| Slicer hints (PrusaSlicer, Cura) | Enviar STL + perfil de impressão direto para o slicer |
| AR preview via WebXR | Ver o objeto no espaço real antes de imprimir |
| STEP → SCAD reverso | Importar peça existente e parametrizá-la |
| Estimativa de custo | Calcular custo por material, tempo de corte/impressão |

---

## Versionamento

| Versão | Status | Foco principal |
|---|---|---|
| v0.1.0 | ✅ Released | Exportação básica (PNG, STL, DXF, SVG...) |
| v0.2.0 | ✅ Released | `generate_laser_part` + `validate_laser_config` |
| v0.3.0 | ✅ Released | `generate_box`, `generate_kerf_test`, `generate_finger_test`, `estimate_material_use`, `check_syntax`, `generate_3d_box`, `generate_bracket`, `generate_enclosure`, `validate_printability` |
| v0.4.x | 🔜 Próximo | Impressão 3D avançada: `suggest_orientation`, perfis, `generate_assembly` |
| v0.5.x | 📋 Planejado | CNC + fabricação híbrida |
| v0.6.x | 📋 Planejado | Infraestrutura, BOSL2, cache, logs |
| v1.0.0 | 🏁 Meta | Produto estável e publicado no PyPI |
