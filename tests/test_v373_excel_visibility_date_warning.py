import qualimatch.quality_excel_writer as q


def test_active_table_filter_is_cleared_without_removing_autofilter():
    xml=(
        b'<table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ref="B11:GM20">'
        b'<autoFilter ref="B11:GM20"><filterColumn colId="3"><filters><filter val="M01"/></filters></filterColumn></autoFilter>'
        b'<tableColumns count="1"><tableColumn id="1" name="ID"/></tableColumns></table>'
    )
    assert q._table_has_active_filter(xml) is True
    out=q._clear_table_filters(xml)
    assert b'<autoFilter' in out
    assert b'filterColumn' not in out


def test_unhide_table_rows_only_inside_requested_range():
    sheet=(b'<worksheet><sheetData>'
           b'<row r="5" hidden="1"><c r="A5"/></row>'
           b'<row r="12" hidden="1"><c r="A12"/></row>'
           b'<row r="20" hidden="1"><c r="A20"/></row>'
           b'</sheetData></worksheet>')
    out=q._unhide_table_rows(sheet,12,20)
    assert b'<row r="5" hidden="1"' in out
    assert b'<row r="12" hidden="1"' not in out
    assert b'<row r="20" hidden="1"' not in out


def test_cloned_row_does_not_keep_filter_hidden_flag():
    row=b'<row r="10" hidden="1" spans="1:3"><c r="A10"><v>1</v></c></row>'
    cloned=q._clone_row(row,10,30,{})
    visible=q._make_row_visible(cloned)
    assert b'r="30"' in visible
    assert b'hidden="1"' not in visible


def test_frontend_marks_business_date_warning_yellow():
    js=open('frontend/static/app.js',encoding='utf-8').read()
    css=open('frontend/static/app.css',encoding='utf-8').read()
    assert 'cert-row-date-warning' in js
    assert 'Data de recebimento em laboratório anterior à Data Ext. dos CPs' in js
    assert '.cert-row-date-warning' in css
    assert 'cert-date-warning' in css
