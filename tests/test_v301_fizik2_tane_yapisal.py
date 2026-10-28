"""V301/FİZİK-2 kalem 10 — katı Yapısal sekmesinin üç satırı: kaynak ve dayanak.

ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/fizik-2/k10_tane_yapisal_olcum.txt,
örnek KNDX): "Yapısal Verim %0 · Çatlak İlerlemesi Riski Yüksek · Isıl
Genleşme Uyumu Zayıf" sabit metin DEĞİL, modelin çıktısıdır
(``_calculate_grain_structural``): port gerinimi %2,21 ⟷ kapasite %2,0 →
gerinim SF 0,906. Dayanak ekranda yoktu, sınıf bantları kaynaksızdı ve
hiçbir uyarı üretilmiyordu. Sonra: künye alanları (bantlar "kaynaksız HRMA
seçimi"), adlı uyarı (SF < 1) ve ekranda dayanak satırı (EN+TR).
"""
import contextlib
import io
import pathlib

import pytest

from tests.support import kabul

KOK = pathlib.Path(__file__).resolve().parents[1]
KOD = 'warn.solid.grain_strain_exceeds_capability'


def _sessiz(fn, *a, **k):
    t = io.StringIO()
    with contextlib.redirect_stdout(t), contextlib.redirect_stderr(t):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def kati():
    # V301/S1-6 (28 Eki): dağıtılan örnek artık kartuş yüklü (gerinim SF
    # 5,32, uyarı yok — tests/test_v301_tane_yerlesimi.py). Bu bekçiler
    # kapasite aşımı MEKANİZMASINI sınar: aynı örnek gövdeye yapıştırılmış
    # yerleşimle (kürleme büzülmesi kısıtlı) koşulur → SF 0,906.
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        govde = dict(kabul.sayfa_yuku('solid'), grain_support='case_bonded')
        r = _sessiz(c.post, '/calculate_solid', json=govde)
        assert r.status_code == 200
        return r.get_json()


def test_uc_satir_dayanakli(kati):
    g = kati['structural_analysis']['grain_structural']
    assert g['strain_safety_factor'] < 1.0
    assert g['crack_propagation_risk'] == 'High'
    for alan in ('crack_propagation_risk_basis',
                 'thermal_expansion_compatibility_basis'):
        assert 'unsourced HRMA choice' in g[alan], alan
    assert 'not an efficiency of the structure' in \
        g['structural_efficiency_basis']
    assert g['thermal_bore_strain_ratio'] == pytest.approx(
        g['thermal_only_bore_strain_percent']
        / g['strain_capability_percent'], rel=1e-9)


def test_kapasite_asilinca_tek_adli_uyari(kati):
    kayit = [w for w in kati['warnings'] if w.get('code') == KOD]
    assert len(kayit) == 1
    assert kayit[0]['severity'] == 'warning'
    g = kati['structural_analysis']['grain_structural']
    assert kayit[0]['params']['safety_factor'] == pytest.approx(
        g['strain_safety_factor'], abs=5e-4)
    # KABUL: kritik değil (gerinim kapasitesi literatür bandı girdisi).
    assert not [k for k in kabul.kritikler(kati) if k['code'] == KOD]


def test_sf_bir_ustundeyse_uyari_yok():
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    motor = SolidRocketEngine.__new__(SolidRocketEngine)
    motor.design_warnings = []
    motor._tane_gerinim_uyarisi({'strain_safety_factor': 1.2,
                                 'bore_strain_percent': 1.0,
                                 'strain_capability_percent': 2.0})
    assert motor.design_warnings == []
    motor._tane_gerinim_uyarisi({'strain_safety_factor': 0.5,
                                 'bore_strain_percent': 4.0,
                                 'strain_capability_percent': 2.0})
    motor._tane_gerinim_uyarisi({'strain_safety_factor': 0.5,
                                 'bore_strain_percent': 4.0,
                                 'strain_capability_percent': 2.0})
    assert [w['code'] for w in motor.design_warnings] == [KOD]


def test_ekran_ve_sozluk_iki_dilde():
    sablon = (KOK / 'hrma' / 'templates' / 'solid.html').read_text(
        encoding='utf-8')
    assert "TF('solid.js.grain_strain_basis'" in sablon
    assert 'data-grain-strain-basis' in sablon
    sayfa = (KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
        encoding='utf-8')
    assert sayfa.count("'solid.js.grain_strain_basis':") == 2
    ortak = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    assert ortak.count("'%s':" % KOD) == 2
