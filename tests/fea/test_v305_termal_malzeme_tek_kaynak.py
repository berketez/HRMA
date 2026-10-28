# tests/fea — V305/B: termal FEA zincirinde profil malzemesi == köprünün ağ malzemesi
"""
v3.0.5 (28 Eki 2026, V305/B ek tur) — ZİNCİRİN İKİ UCU AYNI MALZEME, TEK KAYNAK.

Gerileme (ölçüldü, docs/scofield/raw/OH/V305/ci/B/RAPOR.md "Ek tur"):
fe72e04b5 (FİZİK-2 / NK-12) ile köprü termal ağı motorun LÜLE malzemesiyle
çözer (``hrma.fea.bridge.NOZZLE_MATERIAL_PATHS``). ``/api/analysis/
wall-profile`` ucunun ``motor_results`` kurucusu
(``heat_transfer_analysis.wall_profile_inputs_from_motor``) malzemeyi hâlâ
yalnız kamara/kasa alanından okuyordu. Sonuç: arayüzün katı termal FEA
paneli (gövde = ``{motor_results}``) graphite ve tungsten lülede 422
``axial_profile_material_mismatch`` aldı (fe72e04b5^'da 200); hibritin
yalnız ``motor_results`` gönderen API yolu da 422 aldı. Onarım: kurucunun
malzeme adayları köprünün yol listesiyle başlar, liste köprüden OKUNUR
(``_wall_profile_material_paths``).

Bu bekçi kanıt dosyasına BAĞLI DEĞİLDİR (taze motorlar, docs'suz ağaçta
koşar). Panel gövdesi düğümleri ``node`` ister; CI iş akışı node kurar ve
"sıfır atlama" adımı node düğümlerinin atlanmasını yakalar.

Ters mutasyon (eski aday listesi: yalnız kamara/kasa yolu): tek kaynak
düğümü, katı iki lüle × iki yol ve hibritin API yolu KIRMIZI (ölçüldü,
RAPOR.md).
"""
from __future__ import annotations

import shutil

import pytest

from tests.fea.test_d37_termal_a2 import (H, HIBRIT_A2_GOVDE, KAPI_YANMA_S,
                                          KATI_GOVDE, SIVI_ABLATIF_STEEL_304,
                                          _q, _sivi_kos)

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: Taze motorlar: (ad, motor tipi, uç, gövde). Katıda arayüzün iki analiz
#: edilen lüle seçeneği (graphite varsayılan, tungsten); hibritte varsayılan
#: malzemeler (kamara steel_304, lüle graphite) ve kapı vakasının yanma
#: süresi; sıvıda a2 ablatif steel_304 gövdesi (SV-03 önerili besleme).
TEK_KAYNAK_MOTORLARI = (
    ('kati_graphite', 'solid', '/calculate_solid', KATI_GOVDE),
    ('kati_tungsten', 'solid', '/calculate_solid',
     dict(KATI_GOVDE, nozzle_material='tungsten')),
    ('hibrit_varsayilan', 'hybrid', '/calculate',
     dict(HIBRIT_A2_GOVDE, burn_time=KAPI_YANMA_S)),
    ('sivi_ablatif_steel_304', 'liquid', '/calculate_liquid',
     SIVI_ABLATIF_STEEL_304),
)
TEK_KAYNAK_MOTOR_ADLARI = [m[0] for m in TEK_KAYNAK_MOTORLARI]


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def motorlar(client):
    out = {}
    for ad, tip, uc, govde in TEK_KAYNAK_MOTORLARI:
        r = (_sivi_kos(client, govde) if uc == '/calculate_liquid'
             else _q(client.post, uc, json=govde, headers=H))
        assert r.status_code == 200, (ad, r.get_data(as_text=True)[:300])
        g = r.get_json()
        out[ad] = (tip, g['motor'] if tip == 'hybrid' else g)
    return out


def _beklenen_ag_malzemesi(motor):
    """Köprünün ağ malzemesi (lüle bloğu varsa lüle, yoksa yapısal)."""
    from hrma.fea import bridge
    lule = bridge._lule_malzemesi(motor)
    if lule is not None:
        return lule[0]
    return bridge.extract_structural_inputs(
        motor, include_chamber=False)['material_key']


def _zincir(client, motor, govde):
    r1 = _q(client.post, '/api/analysis/wall-profile', json=govde, headers=H)
    assert r1.status_code == 200, r1.get_data(as_text=True)[:300]
    wp = r1.get_json()['wall_profile']
    r2 = _q(client.post, '/api/fea/thermal',
            json={'motor_results': motor, 'axial_profile': wp,
                  'ambient_temperature_K': 293.15}, headers=H)
    assert r2.status_code == 200, r2.get_data(as_text=True)[:300]
    return wp, r2.get_json()['fea']


def test_malzeme_yollari_kopruden_tek_kaynak():
    """Kurucunun malzeme adayları = köprünün lüle yolları (aynı sıra) +
    köprünün yapısal yedeği; yol listesi kopyalanmaz, köprüden okunur."""
    from hrma.analysis.heat_transfer_analysis import (
        WALL_PROFILE_MOTOR_PATHS, _wall_profile_material_paths)
    from hrma.fea.bridge import NOZZLE_MATERIAL_PATHS
    lule = [(tuple(y.split('.')), None) for y in NOZZLE_MATERIAL_PATHS]
    for layout in ('hybrid', 'liquid', 'solid'):
        yollar = _wall_profile_material_paths(layout)
        assert yollar[:len(lule)] == lule, layout
        assert yollar[len(lule):] == list(
            WALL_PROFILE_MOTOR_PATHS[layout]['material']), layout


@pytest.mark.parametrize('ad', TEK_KAYNAK_MOTOR_ADLARI)
def test_kurucu_malzemesi_kopru_ag_malzemesi(motorlar, ad):
    """Saf işlev katmanı: kurucunun seçtiği malzeme == köprünün ağ
    malzemesi; katı ve hibritte lüle bloğundan okunur ve beyan edilir."""
    from hrma.analysis.heat_transfer_analysis import (
        wall_profile_inputs_from_motor)
    tip, motor = motorlar[ad]
    k = wall_profile_inputs_from_motor(motor)
    assert k['layout'] == tip
    assert k['inputs']['material'] == _beklenen_ag_malzemesi(motor)
    if tip in ('solid', 'hybrid'):
        assert k['basis']['material'] == 'nozzle_material_analysis.material'


@pytest.mark.parametrize('ad', TEK_KAYNAK_MOTOR_ADLARI)
def test_api_motor_results_zinciri_200(client, motorlar, ad):
    """Yalnız ``motor_results`` gönderen API yolu: wall-profile → termal FEA
    200; profilin malzemesi ağın malzemesi."""
    _, motor = motorlar[ad]
    wp, f = _zincir(client, motor, {'motor_results': motor})
    assert f['status'] == 'ok'
    assert wp['material'] == f['scalars']['material_key'] == \
        _beklenen_ag_malzemesi(motor)


@needs_node
@pytest.mark.parametrize('ad', TEK_KAYNAK_MOTOR_ADLARI)
def test_panel_govdesiyle_zincir_200(client, motorlar, ad, tmp_path):
    """Arayüz panelinin GERÇEK gövdesi (thermal_fea_panel.js
    buildWallProfileBody, node) ile zincir 200 ve tek malzeme. Katı ve
    sıvıda panel gövdesi ``{motor_results}``tır (onarılan yol), hibritte
    düz gövde + lüle malzemesi."""
    from tests.test_thermal_fea_panel import _run_panel
    tip, motor = motorlar[ad]
    b = _run_panel(tmp_path, build_body=[motor])['bodies'][0]
    assert b['missing'] == []
    if tip in ('solid', 'liquid'):
        assert b['body'] == {'motor_results': motor}
    wp, f = _zincir(client, motor, b['body'])
    assert f['status'] == 'ok'
    assert wp['material'] == f['scalars']['material_key'] == \
        _beklenen_ag_malzemesi(motor)
