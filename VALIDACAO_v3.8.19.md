# Validação v3.8.19

## Objetivo
Colocar o botão **Remover duplicados** diretamente em **BV > Certificados** e garantir limpeza segura.

## Regras validadas
- Apenas `certificate_files.status = DUPLICADO` entra na limpeza.
- O registro canônico em `certificates` é preservado.
- Número BI330 repetido, sozinho, não é critério de exclusão.
- A cópia passa para `DUPLICADO_REMOVIDO`, com `certificate_id = NULL`.
- A sincronização ignora a cópia removida enquanto `mtime/size` não mudar, inclusive com `force=True`.
- Arquivo físico não é apagado.
- O botão saiu de Arquivos por medição e foi para a aba Certificados.

## Banco do pacote
Nenhuma migração nem alteração prévia no `data/qualimatch.db`. A rotina só atua quando o usuário clicar no botão em execução.
