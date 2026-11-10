"""3.0.6 ana model (9 Kas) — TERMAL-KONTUR DEVİR 1: hibrit motorun KENDİ ısı
zinciri yayımlanan nozul konturuyla aynı ıslak alanı kullanır.

ÖLÇÜLEN KUSUR: TERMAL-KONTUR güverteyi (``/analyze_thermal_safety``) motorun
yayımladığı kontura bağladı; hibrit motorun ``ht_input``'u ise çıkış çapı,
nozul tipi, kontur açıları ve tasarımcının kontur bloğunu geçirmediği için ısı
modülü örnekleyicinin JENERİK nozuluna düşüyordu (``generic_defaults_used =
['exit_diameter', 'nozzle_type']``). PDF 'Cooling Requirement' güverteden
ayrışıyordu. Ölçüldü (örnek gövde, ıslak nozul alanı, m²):

    tip         güverte (kontur)   motor (önce)   motor (sonra)
    conical     0,026756           0,032434       0,026756
    bell        0,020722           0,032412       0,020722
    parabolic   0,020888           0,032412       0,020888
"""
import contextlib
import io

import pytest

H = {'Host': '127.0.0.1:8080'}


def _sessiz(fn, *a, **k):
    t = io.StringIO()
    with contextlib.redirect_stdout(t), contextlib.redirect_stderr(t):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _motor(client, tip):
    from tests.support.kabul_sayfa_yukleri import SAYFA_YUKLERI
    g = dict(SAYFA_YUKLERI['hybrid'])
    g['nozzle_type'] = tip
    r = _sessiz(client.post, '/calculate', json=g, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()['motor']


def _guverte_alani(client, m):
    import tests.test_v306_termal_kontur as T
    j = _sessiz(T._uc, client,
                T._govde(m, nozzle_contour=T._kontur(m))).get_json()
    gs = (j.get('heat_transfer_analysis') or j).get('gas_side_analysis') \
        if isinstance(j, dict) else None
    if gs is None:
        gs = ((j or {}).get('thermal_analysis') or {}).get('gas_side_analysis')
    return (gs or {}).get('nozzle_wetted_area')


@pytest.mark.parametrize('tip', ['conical', 'bell', 'parabolic'])
def test_motor_isi_zinciri_yayimlanan_konturla_ayni_alan(client, tip):
    m = _motor(client, tip)
    gsa = m['heat_transfer_analysis']['gas_side_analysis']
    kunye = gsa['wetted_integral_contour_basis']
    assert kunye['generic_defaults_used'] == [], kunye
    motor_alan = gsa['nozzle_wetted_area']
    guverte = _guverte_alani(client, m)
    assert guverte is not None
    assert motor_alan == pytest.approx(guverte, rel=1e-12), (tip, motor_alan,
                                                             guverte)


def test_aci_kurali_tek_yerde():
    """Yayımlanan açı bloğu ile ısı girdisinin açıları aynı yardımcıdan."""
    import inspect
    from hrma.engines import hybrid_rocket_engine as hre
    kaynak = inspect.getsource(hre)
    assert kaynak.count("30.0 if konik else 45.0") == 1
    assert "30.0 if nozzle_type == 'conical' else 45.0" not in kaynak
    assert hre._lule_aci_blogu('bell') == {
        'convergent_half_angle_deg': 45.0, 'divergent_half_angle_deg': 11.0,
        'nozzle_type': 'bell'}
