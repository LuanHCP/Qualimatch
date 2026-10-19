# Validação v3.8.7

- 139 testes automatizados aprovados.
- Python compilado sem erros.
- JavaScript validado com `node --check`.
- Teste unitário confirmou escrita automática apenas para certificado pronto e bloqueio de caso REVISAR.
- Teste real de parser/análise com BI330-0388 (Arena, 9 linhas) e BI330-0468 (Pavidez, 11 linhas): 20/20 CPs vinculados, ambos prontos para atualização da BD_QUALI.
- Configuração `auto_bdquali_enabled=1` criada automaticamente em bancos existentes/novos.
- O monitor registra a assinatura pós-gravação para não reescrever o mesmo BI apenas porque a própria BD_QUALI mudou.
