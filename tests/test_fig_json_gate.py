"""_fig_json kapısı bekçi testi (v2.5.5).

Kök neden (2026-07-19 "Regression Rate & Port Growth boş" bugı): plotly 6.x,
``fig.to_json()`` çıktısında numpy dizilerini base64 'bdata' blokları olarak
yazar; uygulamanın paketlediği vendor plotly.js 1.58.5 bu biçimi çözemez ve
grafik BOŞ çizilir. Çözüm tek kapı: her figür JSON'u
``hrma.visualization.visualization._fig_json`` üzerinden üretilir (bdata
blokları listeye açılır, numpy skalerleri Python tiplerine iner, NaN/Inf
null olur).

Bu test, hrma/ altında ÇIPLAK ``fig.to_json()`` çağrısı kalmadığını
AST ile doğrular (yorum ve docstring içindeki bahisler sayılmaz).

Bilinçli istisna: hrma/export/cad_visualization.py — bu dosya v2.5.5
dalgasının dokunulmayanlar listesindedir ve bdata koruması orada farklı bir
yolla sağlanır: tüm diziler trace'e eklenirken ``.tolist()`` ile düz listeye
çevrilir (dosyadaki v2.5.2 "BDATA DUZELTMESI" notu). İstisnanın BÜYÜMESİ de
yakalanır: çağrı sayısı mevcut tavanı aşarsa test düşer.
"""

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HRMA_DIR = REPO_ROOT / 'hrma'

#: Çıplak to_json çağrısına izin verilen dosyalar -> izinli azami çağrı
#: sayısı. Yeni dosya eklemek YASAK; buradaki sayı ancak AZALABİLİR.
ALLOWED_BARE_TO_JSON = {
    'hrma/export/cad_visualization.py': 5,
}


def _bare_to_json_lines(path: pathlib.Path):
    """Dosyadaki gerçek ``<nesne>.to_json(...)`` çağrılarının satırları.

    AST üzerinden bakıldığı için yorumlar, docstring'ler ve
    ``export_to_json`` gibi farklı adlı metotlar eşleşmez.
    """
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'to_json'):
            lines.append(node.lineno)
    return lines


def _scan():
    violations = {}
    allowed_hits = {}
    for path in sorted(HRMA_DIR.rglob('*.py')):
        rel = path.relative_to(REPO_ROOT).as_posix()
        lines = _bare_to_json_lines(path)
        if not lines:
            continue
        if rel in ALLOWED_BARE_TO_JSON:
            allowed_hits[rel] = lines
        else:
            violations[rel] = lines
    return violations, allowed_hits


def test_ciplak_fig_to_json_kalmadi():
    """hrma/ altında istisna listesi dışında fig.to_json() çağrısı yok."""
    violations, _allowed = _scan()
    assert not violations, (
        'Çıplak fig.to_json() çağrısı bulundu — _fig_json kapısından '
        'geçirilmeli (bdata / vendor plotly.js 1.58.5 uyumsuzluğu, boş '
        'grafik bugunun kökü): %r' % violations)


def test_istisna_listesi_buyumedi():
    """İzinli dosyadaki çağrı sayısı tavanı aşamaz (istisna şişmesin)."""
    _violations, allowed = _scan()
    for rel, lines in allowed.items():
        cap = ALLOWED_BARE_TO_JSON[rel]
        assert len(lines) <= cap, (
            '%s içindeki to_json çağrısı %d oldu (tavan %d) — yeni çağrı '
            'ekleme, _fig_json kullan. Satırlar: %r'
            % (rel, len(lines), cap, lines))


def test_fig_json_kapisi_yerinde():
    """Kapının kendisi silinmediğinden emin ol (import + davranış)."""
    import numpy as np
    import plotly.graph_objects as go
    from hrma.visualization.visualization import _fig_json
    import json

    fig = go.Figure(data=[go.Scatter(x=np.array([0.0, 1.0]),
                                     y=np.array([1.0, np.nan]))])
    out = _fig_json(fig)
    assert isinstance(out, str)
    assert 'bdata' not in out
    parsed = json.loads(out)
    # NaN, plotly.js'in boşluk olarak yorumladığı null'a iner
    assert parsed['data'][0]['y'][1] is None
