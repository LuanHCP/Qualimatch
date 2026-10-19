from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_dynamic_precision_helpers_exist():
    js = (ROOT / "frontend/static/app.js").read_text(encoding="utf-8")
    assert "const decimalPlaces=" in js
    assert "const groupDecimals=" in js
    assert "const groupNum=" in js
    assert "const groupPct=" in js
    assert "const groupCm=" in js

def test_measurement_columns_share_precision():
    js = (ROOT / "frontend/static/app.js").read_text(encoding="utf-8")
    assert "width:groupDecimals(d.map(x=>x.width_m),0,3)" in js
    assert "groupNum(x.width_m,digits.width)" in js
    assert "groupNum(x.extension_m,digits.extension)" in js
    assert "groupNum(x.volume_mass_m3,digits.volume)" in js

def test_certificate_technical_groups_share_precision_but_vv_stays_fixed():
    js = (ROOT / "frontend/static/app.js").read_text(encoding="utf-8")
    assert "thicknessExec:groupDecimals" in js
    assert "ratio:groupDecimals" in js
    assert "gmb:groupDecimals" in js
    assert "groupCm(x.thickness_exec_cm,digits.thicknessExec)" in js
    assert "groupPct(x.ratio_ab_pct,digits.ratio)" in js
    assert "vvPct(x.voids_pct)" in js
    assert "fixedNum(v,1)+'%'" in js
