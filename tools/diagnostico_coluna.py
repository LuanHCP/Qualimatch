import sys
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qualimatch.xlsx_xml import sheet_path
from qualimatch.normalizers import norm_header
from qualimatch.quality_excel_writer import (
    _resolve_table_path,
    _table_info,
    _cell_numeric_text,
    _find_row,
    _col_to_num,
    _num_to_col,
)


def main() -> None:
    if len(sys.argv) < 2:
        print('Uso: python diagnostico_coluna.py "CAMINHO_DO_ARQUIVO.xlsx" [ABA] [LINHA]')
        return
    path = Path(sys.argv[1])
    aba = sys.argv[2] if len(sys.argv) > 2 else "BD_QUALI"
    row_num = int(sys.argv[3]) if len(sys.argv) > 3 else 2370

    if not path.exists():
        print(f"Arquivo não encontrado: {path}")
        return

    with ZipFile(path, "r") as zin:
        ws_path = sheet_path(zin, aba)
        table_path = _resolve_table_path(zin, ws_path)
        table_xml = zin.read(table_path)
        sheet_xml = zin.read(ws_path)
        ref, header_row, table_end, header_map, _ = _table_info(table_xml)

    print(f"Arquivo: {path}")
    print(f"Aba usada: {aba!r} -> {ws_path}")
    print(f"Intervalo da Tabela (ref): {ref}")
    print(f"Linha de cabeçalho: {header_row} | última linha da tabela: {table_end}")

    import re as _re
    m_start, m_end = ref.split(":")
    sc = _re.match(r"[A-Z]+", m_start).group(0)
    ec = _re.match(r"[A-Z]+", m_end).group(0)
    width_by_ref = _col_to_num(ec) - _col_to_num(sc) + 1
    width_by_cols = len(header_map)
    print(f"Largura pelo intervalo (ref): {width_by_ref} colunas | Largura pela lista de colunas da Tabela: {width_by_cols} colunas")
    if width_by_ref != width_by_cols:
        print(">>> DIVERGÊNCIA ENCONTRADA: o intervalo da Tabela tem largura diferente da lista de colunas.")
        print(">>> Isso desalinha TODAS as colunas a partir do ponto da divergência (é a causa mais provável do erro).")
    print()

    print("Mapeamento que o QualiMatch está usando hoje (nome normalizado -> coluna):")
    for name, letter in sorted(header_map.items(), key=lambda kv: _col_to_num(kv[1])):
        marker = "   <-- LINHA MEDIÇÃO" if name == norm_header("LINHA MEDIÇÃO") else ""
        print(f"  {letter}: {name}{marker}")
    print()

    linha_col = header_map.get(norm_header("LINHA MEDIÇÃO"))
    print(f"Coluna que o QualiMatch está usando para 'LINHA MEDIÇÃO': {linha_col!r}")

    found = _find_row(sheet_xml, row_num, 0)
    if not found:
        print(f"Linha {row_num} não encontrada na planilha (aba errada ou linha inexistente).")
        return
    _, _, row_xml = found

    if linha_col:
        val = _cell_numeric_text(row_xml, linha_col, row_num)
        print(f"Valor que o QualiMatch está lendo em {linha_col}{row_num}: {val!r}")
    val_d = _cell_numeric_text(row_xml, "D", row_num)
    print(f"Valor real na coluna D{row_num} (a que você conferiu manualmente): {val_d!r}")

    if linha_col and linha_col != "D":
        print()
        print(f">>> CONFIRMADO: o QualiMatch está lendo a coluna {linha_col} em vez da coluna D para 'LINHA MEDIÇÃO'.")


if __name__ == "__main__":
    main()