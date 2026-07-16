# Contribuindo com o mcp-openscad

Obrigado pelo interesse em contribuir! 🎉

## Setup do ambiente

```bash
git clone https://github.com/thalisantunes/mcp-openscad
cd mcp-openscad
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

**Requisito:** [OpenSCAD](https://openscad.org/downloads.html) instalado e no `PATH`.

```bash
# Verificar instalação
openscad --version
```

## Rodando testes

```bash
# Todos os testes
python -m pytest tests/ -v

# Com cobertura
python -m pytest tests/ --cov=server --cov-report=term-missing

# Um teste específico
python -m pytest tests/test_server.py::test_generate_box_basic -v
```

## Estrutura do código

```
server.py              # Servidor MCP + todos os geradores
tests/test_server.py   # Todos os testes (unit + integration)
pyproject.toml         # Configuração do pacote PyPI
ROADMAP.md             # Plano de desenvolvimento
```

### Padrão de implementação

Cada ferramenta segue este padrão:

1. **Função geradora** — `generate_X_scad(config: dict) -> str`
   - Recebe config como dict
   - Retorna código OpenSCAD como string
   - Validação de inputs com `max()`, `min()`, guards

2. **Registro no `handle_list_tools()`** — `types.Tool(...)`
   - Nome, descrição, inputSchema com JSON Schema

3. **Handler no `handle_call_tool()`** — `elif name == "..."`
   - Valida argumentos
   - Gera SCAD + exporta (STL/SVG/DXF) + preview PNG
   - Retorna `TextContent` + `ImageContent`

4. **Testes** — pelo menos 3 por ferramenta
   - Teste básico com defaults
   - Teste de edge case (valores extremos, configs vazios)
   - Teste do handler MCP (async)
   - Teste de integração com OpenSCAD (renderização real)

## Convenções

- **Commits:** Semantic commits (`feat:`, `fix:`, `docs:`, `test:`)
- **Linguagem:** Código em inglês, comentários e docs em português
- **Testes:** Meta > 90% de cobertura
- **OpenSCAD:** Usar `$fn` para controle de resolução, `difference()` para subtração

## Dicas para novos geradores

- Sempre escape `{{` e `}}` ao usar f-strings com código OpenSCAD
- Use `os.devnull` ao invés de `/dev/null` para cross-platform
- Proteja contra loops infinitos (step <= 0)
- Proteja contra divisão por zero (clamp com `max(1, ...)`)
- Teste com renderização real do OpenSCAD (testes de integração)

## Issues e Pull Requests

1. Abra uma issue descrevendo a feature ou bug
2. Fork o repositório
3. Crie um branch (`feat/nome-da-feature` ou `fix/descricao-do-bug`)
4. Implemente com testes
5. Verifique que todos os testes passam: `python -m pytest tests/ -v`
6. Abra o PR
