"""Grafik stil kuralları — cırtlak renk regresyonunu kalıcı engeller.

Berke şikayeti (2026-07-14): "grafikler aşırı renkli ve bazı yerlerde yazılar
iç içe geçmiş". Renkler hd paletine çekildi; bu testler eski paletin geri
sızmasını engeller. Kaynak: hrma/visualization/*.py + /calculate* yanıtları.
"""

import json
import re
import pytest

from hrma.app import app

# Yasak renkler: CSS adlarıyla cırtlaklar + eski açık temanın mor ailesi +
# gökkuşağı colorscale'leri. (Semantik renkler hd tonlarıyla serbest:
# #ff5d73 kırmızı, #2dd4a8 yeşil, #ff8c33 turuncu, #ffd166 amber.)
YASAK_DESENLER = [
    r"'red'", r'"red"', r"'blue'", r'"blue"', r"'green'", r'"green"',
    r"'purple'", r'"purple"', r"'orange'", r'"orange"', r"'yellow'", r'"yellow"',
    r"#667eea", r"#764ba2", r"#f093fb", r"#f5576c",
    r"colorscale='Jet'", r'colorscale="Jet"',
    r"colorscale='Rainbow'", r'colorscale="Rainbow"',
]

KAYNAK_DOSYALAR = [
    "hrma/visualization/visualization.py",
    "hrma/visualization/advanced_results.py",
]


@pytest.fixture(scope="module")
def client():
    return app.test_client()


@pytest.mark.parametrize("path", KAYNAK_DOSYALAR)
def test_kaynakta_yasak_renk_yok(path):
    src = open(path, encoding="utf-8").read()
    ihlaller = [d for d in YASAK_DESENLER if re.search(d, src)]
    assert not ihlaller, f"{path} içinde yasak renk kalıntısı: {ihlaller}"


# JSON yanıt taraması: adlandırılmış CSS renkleri JSON'da "red" gibi görünür
JSON_YASAK = re.compile(
    r'"(?:color|colorscale)"\s*:\s*"(red|blue|green|purple|orange|yellow|Jet|Rainbow)"'
)


def _plots_json(client, url, payload):
    r = client.post(url, json=payload)
    assert r.status_code == 200, (url, r.status_code)
    d = r.get_json()
    return json.dumps(d.get("plots", {}))


HYBRID = {
    "motor_name": "style-test", "thrust": 1000, "burn_time": 10,
    "chamber_pressure": 30, "of_ratio": 6, "fuel_type": "htpb",
    "oxidizer_type": "n2o", "expansion_ratio": 5,
}


def test_hybrid_plots_yasak_renk_yok(client):
    plots = _plots_json(client, "/calculate", HYBRID)
    m = JSON_YASAK.search(plots)
    assert not m, f"/calculate plots içinde yasak renk: {m.group(0)}"


def test_plotly_dark_merkezi_savunmalar():
    src = open("hrma/static/js/plotly_dark.js", encoding="utf-8").read()
    for gerekli in ("automargin", "maybeBottomLegend", "standoff",
                    "bgcolor = 'rgba(6, 13, 24", "colorway"):
        assert gerekli.split(" = ")[0] in src, f"plotly_dark.js'te eksik savunma: {gerekli}"
