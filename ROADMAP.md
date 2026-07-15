# MCP OpenSCAD Roadmap

## Fase 1: Suporte estendido a formatos de arquivo (Atual)
- [x] Suporte a STL
- [x] Suporte a DXF e SVG (2D)
- [x] Suporte a 3MF (Implementado)
- [x] Suporte a exportação CSG (`export_csg`)
- [x] Suporte a exportação AMF (`export_amf`)

## Fase 2: Parametrização e Configurações
- [ ] Suporte a passagem de variáveis (`-D var=value`) para personalizar os modelos.
- [ ] Permitir uso de bibliotecas de terceiros ou definição de `OPENSCADPATH`.
- [ ] Mais opções de renderização (cores, ângulos de câmera, resolução).

## Fase 3: Confiabilidade e Segurança
- [ ] Timeout nas chamadas de execução do OpenSCAD (para prevenir scripts que travam a execução).
- [ ] Tratamento de erros e parsing aprimorado das mensagens do OpenSCAD para fácil correção pelo modelo.
- [ ] Criação de testes automatizados unitários/integração.

## Fase 4: Qualidade de Vida (QoL)
- [ ] Checagem de sintaxe antes de iniciar a renderização completa.
- [ ] Pipeline CI/CD básico no repositório.
