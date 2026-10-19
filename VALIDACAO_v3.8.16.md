# Validação — QualiMatch v3.8.16

## Falha corrigida
No Windows com o novo Python Launcher/Install Manager instalado, mas sem o runtime Python 3.13, o comando `py -3.13` pode exibir:

`No runtime installed that matches 3.13. Try running "py install <version>".`

A v3.8.15 podia aceitar esse launcher como se o runtime existisse e tentar criar o `.venv`, gerando `pyvenv.cfg` ausente.

## Correção
- `iniciar.bat` e `iniciar_preparar.bat` não confiam mais apenas no código de saída do launcher.
- Cada candidato deve imprimir exatamente `QUALIMATCH_BASE_OK` executando Python 3.11+ com `sys.prefix == sys.base_prefix`.
- Erros/mensagens do launcher são capturados e não são tratados como runtime válido.
- Python 3.12 é preferido por estabilidade de dependências.
- Se nenhum runtime estiver presente, tenta-se `py install 3.12` automaticamente e o runtime é validado novamente.
- Instalações base em caminhos conhecidos e PATH continuam como fallback.

## Escopo
Somente bootstrap/instalação. Parser BI330 permanece 3.8.13. Nenhuma migração ou alteração de banco foi adicionada.
