# Validação v3.7.3

- Correção específica para BD_QUALI filtrada: validada com o modelo PAVIDEZ que estava com filtro M01 ativo e 3.524 linhas ocultas.
- Cópia de teste adicionou nova linha ao fim da tabela, removeu `hidden=1`, atualizou o `ref` da tabela e gravou o Nº CERTIFICADO Vv esperado.
- Validação pós-gravação lê novamente o XLSX gerado e aborta se o certificado não estiver nas linhas projetadas.
- Destaque amarelo de data inconsistente validado no frontend.
