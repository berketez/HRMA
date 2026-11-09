"""V306/HİBRİT-ÇAPRAZ-2 — kulvar bekçileri (9 Kasım 2026).

Kanıt: ``docs/scofield/raw/OH/V306/hibrit-capraz-2/`` (RAPOR.md, olcum/).
Kalem 1'in bekçileri ``tests/test_hibrit_egri_ornekleme.py`` sonundadır;
burada kalem 2/5'in ürün onarımları kilitlenir:

* N₂O kendinden basınçlı tankta TESLİM süresi (boşalma çözümü) gönderilen
  ``burn_time``ı "kullanılmadı, model çözdü" diye beyan ettirmez — ne
  ``inputs_not_used``da ne de ekrana basılan ``input_warnings``te. Taban
  78dbb287e her varsayılan N₂O hibrit koşusunda (örnek dahil) bu uyarıyı
  basıyordu (``olcum/k5_once.json``).
* Regresyon künyesi KULLANILAN çiftin kaynağıdır (katalog künyesi yalnız
  çift katalogla eşitken ``citation``).
* UQ hibrit fabrikası ``mass_flux_chamber``ı okuyor; "okunmadı" denmez.
"""

import warnings
from types import SimpleNamespace

import pytest

from hrma.app import app

HAFIF = {'include_plots': False, 'generate_cad': False,
         'calculate_trajectory': False, 'include_combustion_analysis': False,
         'include_realtime_dashboard': False,
         'include_3d_visualization': False}
GOVDE = dict(HAFIF, motor_type='hybrid', thrust=1000.0, burn_time=10.0,
             chamber_pressure=20.0, of_ratio=6.0, fuel_type='htpb',
             oxidizer_type='n2o')


@pytest.fixture(scope='module')
def istemci():
    with app.test_client() as c:
        yield c


def _calc(istemci, **ek):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        r = istemci.post('/calculate', json=dict(GOVDE, **ek),
                         headers={'Host': '127.0.0.1:8080'})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def test_teslim_suresi_girdiyi_kullanilmadi_diye_beyan_ettirmez(istemci):
    j = _calc(istemci)
    m = j['motor']
    # Dayanak: teslim süresi gerçekten istenenden farklı (boşalma fiziği).
    assert m['delivered_source'] == 'tank_blowdown'
    assert m['burn_time_requested_s'] == 10.0
    assert m['burn_time'] > 10.0
    alanlar = {b['field'] for b in (j.get('inputs_not_used') or [])}
    assert 'burn_time' not in alanlar
    ekran = [(w.get('params') or {}).get('field')
             for w in (j.get('input_warnings') or []) if isinstance(w, dict)]
    assert 'burn_time' not in ekran


def test_model_tasarim_suresini_cozdugunde_beyan_aynen(istemci):
    """I + F önceliği: t = I/F = 15 s; beyan tasarım süresini söyler."""
    j = _calc(istemci, thrust=500.0, burn_time=20.0, total_impulse=7500.0)
    beyan = {b['field']: b for b in j['inputs_not_used']}['burn_time']
    assert beyan['submitted'] == 20.0
    assert beyan['used_by_model'] == pytest.approx(15.0, rel=1e-12)
    assert beyan['used_by_model'] == j['motor']['burn_time_requested_s']
    assert 'burn_time_requested_s' in beyan['message']
    ekran = [(w.get('params') or {}).get('field')
             for w in (j.get('input_warnings') or []) if isinstance(w, dict)]
    assert 'burn_time' in ekran


def test_tasarim_alani_yoksa_eski_karsilastirma():
    """Alanı yayımlamayan motor yolunda davranış değişmez (saf işlev)."""
    from hrma.app import _declare_overridden_inputs
    b = _declare_overridden_inputs({'burn_time': 10.0},
                                   {'burn_time': 12.5}, ('burn_time',))
    assert [(x['field'], x['used_by_model']) for x in b] == [
        ('burn_time', 12.5)]
    assert 'the analysis and the delivered performance use 12.5' in \
        b[0]['message']
    assert _declare_overridden_inputs(
        {'burn_time': 10.0},
        {'burn_time': 12.5, 'burn_time_requested_s': 10.0},
        ('burn_time',)) == []


def test_kunye_kullanilan_ciftin_kaynagi():
    from hrma.analysis import cea_karsilastirma as ck
    motor = {'fuel_type': 'htpb'}
    farkli = SimpleNamespace(fuel_type='htpb', rho_f=920.0, a=6.399e-05,
                             n=0.554, oxidizer_type='n2o',
                             combustion_analyzer=None)
    g = ck.build_hybrid_data_sources(
        {'regression_a': 6.399e-05, 'regression_n': 0.554}, farkli, motor,
        {})['fuel']['regression']
    assert g['equals_catalogue'] is False and g['origin'] == 'request'
    assert g['citation'] is None
    assert g['independent_fit'] is None and g['basis'] is None
    assert g['catalogue_citation'].startswith('Doran')
    katalog = SimpleNamespace(fuel_type='htpb', rho_f=920.0, a=3.68e-05,
                              n=0.555, oxidizer_type='n2o',
                              combustion_analyzer=None)
    k = ck.build_hybrid_data_sources({}, katalog, motor,
                                     {})['fuel']['regression']
    assert k['equals_catalogue'] is True
    assert k['citation'] == k['catalogue_citation']
    assert k['independent_fit'] is True and k['basis']


def test_uq_aki_okunuyor_okunmadi_denmez(istemci):
    r = istemci.post('/api/uncertainty-analysis', json={
        'motor_type': 'hybrid', 'level': 'fast', 'seed': 7, 'n_samples': 12,
        'inputs': {'thrust': 1000.0, 'chamber_pressure': 20.0,
                   'burn_time': 10.0, 'of_ratio': 6.0,
                   'mass_flux_chamber': 250.0}})
    assert r.status_code == 200
    assert 'inputs_not_read' not in r.get_json()


def test_regresyon_katsayisi_ipucu_cozucunun_akisini_soyler():
    """K-P2 (KILAVUZ, 9 Kas): ipucu çözücünün KULLANDIĞI akıyı söyler.

    Ölçüldü (``olcum/kp2_aki_tabani.json``): örnek koşunun
    ``regression_flux_mode`` = 'ox'; Carmicino 2013 uyarlaması (G_ox, ṙ)
    çiftlerine (``hibrit-nozul/olcum/k5_carmicino_fit.py``). İki taban aynı
    → regresyon hızı doğru, yalnız ipucu yanlıştı ("varsayılan G_total",
    "%10-18 fazla regresyon"). Varsayılan değişirse bu bekçi kırmızı düşer
    ve ipucu da değişmelidir.
    """
    import pathlib
    import re
    from hrma.analysis.regression_analysis import DEFAULT_FLUX_MODE
    assert DEFAULT_FLUX_MODE == 'ox'
    kok = pathlib.Path(__file__).resolve().parents[1]
    js = (kok / 'hrma' / 'static' / 'js' / 'i18n_advanced.js').read_text(
        encoding='utf-8')
    metinler = re.findall(
        r"'adv\.tip\.regressionRateCoefficient': '((?:[^'\\]|\\.)*)'", js)
    html = (kok / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')
    metinler += re.findall(
        r'data-i18n="adv\.tip\.regressionRateCoefficient">([^<]*)<', html)
    assert len(metinler) == 3, metinler
    for m in metinler:
        assert 'G_total' not in m and '10-18' not in m, m
        assert 'G_ox' in m, m


def test_itki_paneli_aciklamasi_iki_beslemeyi_ayri_soyler():
    """Panel açıklaması N₂O teslim eğrisini 'oksitleyici debisi sabit' diye
    anlatmaz (HİBRİT-ÇAPRAZ'tan beri eğri boşalma çözümüdür; ölçüldü:
    ekran ``ekran/hibrit_tr_hybridThrustCurvePanel_1280.png`` öncesi)."""
    import pathlib
    import re
    kok = pathlib.Path(__file__).resolve().parents[1]
    js = (kok / 'hrma' / 'static' / 'js' / 'i18n_advanced.js').read_text(
        encoding='utf-8')
    en, tr = re.findall(
        r"'adv\.txt\.thrustCurveExplain': '((?:[^'\\]|\\.)*)'", js)
    assert 'self-pressurised N2O tank' in en and 'regulated feed' in en
    assert 'boşalma çözümü' in tr and 'Regüleli beslemede' in tr
    html = (kok / 'hrma' / 'templates' / 'advanced.html').read_text(
        encoding='utf-8')
    yedek = re.search(r'data-i18n="adv\.txt\.thrustCurveExplain">([^<]*)<',
                      html).group(1)
    assert ' '.join(yedek.split()) == en.replace("\\'", "'")


# ---------------------------------------------------------------------------
# Ek tur (9 Kas öğleden sonra) — DEVİR 1: ısıl maruziyet = gerçek yanma süresi
# ---------------------------------------------------------------------------
def _motor(**ek):
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    ayar = dict(thrust=1000.0, burn_time=10.0, of_ratio=6.0,
                chamber_pressure=20.0, fuel_type='htpb', oxidizer_type='n2o')
    ayar.update(ek)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        e = HybridRocketEngine(**ayar)
        return e, e.calculate()


def test_isil_zincir_bosalmada_teslim_suresini_kullanir():
    """Ölçüldü (``olcum/ek_isil_*.json``): örnek astar 7,404 → 7,582 mm;
    Isıl panel (``motor.burn_time``) aynı süreyle aynı astarı bulur."""
    e, r = _motor()
    assert r['delivered_source'] == 'tank_blowdown'
    t = r['burn_time']
    assert t == r['tank_blowdown']['burn_duration_s'] > 10.0
    tp = r['thermal_protection']
    assert tp['burn_time_s'] == t
    assert tp['chamber_liner']['burn_time_s'] == t
    assert 'blowdown' in tp['burn_time_source']
    assert ('Burn time (%.2f s) is the delivered burn' % t) in \
        tp['chamber_liner']['basis']
    er = r['nozzle_material_analysis']['erosion']
    assert er['total_radial_recession_mm'] == pytest.approx(
        er['radial_recession_rate_mm_s'] * t, rel=1e-12)
    # Yayımlanan boşalma bloğu ısıl zincirin kullandığı çözümün kendisi.
    assert r['tank_blowdown'] is e._tank_blowdown_erken


def test_isil_zincir_regule_kipte_istenen_sure():
    """Kullanıcı tank basıncı (regüle): maruziyet istenen süre (bit-aynı yol)."""
    _, r = _motor(tank_pressure_source='user', tank_pressure=60.0)
    assert r['delivered_source'] == 'regulated_design_curve'
    assert r['thermal_protection']['burn_time_s'] == 10.0
    assert 'blowdown' not in r['thermal_protection']['burn_time_source']


# ---------------------------------------------------------------------------
# Ek tur — UÇUŞ-KÜTLE DEVİR 1: regüle kipte harcanan itici TEK SAYI
# ---------------------------------------------------------------------------
def test_regule_harcanan_itici_tek_sayi():
    """Ölçüldü (``olcum/ek_kutle_*.json``): taban L3 118,10409 (∫ṁ) ⟷
    118,17560 kg (bütçe); fark açık Euler ayrıklaştırması
    Σ ρ_f·N·π·L·ṙ²·Δt². Tek sayı: korunan kütle; eğri integrali tanılama."""
    import numpy as np
    e, r = _motor(tank_pressure_source='user', tank_pressure=60.0)
    assert r['delivered_source'] == 'regulated_design_curve'
    reg = r['of_shift']['regulated']
    assert r['propellant_mass_consumed_kg'] == r['propellant_mass_total']
    assert reg['propellant_consumed_kg'] == r['propellant_mass_total']
    assert reg['isp_mass_avg_s'] == r['isp_delivered_avg_s']
    # Eğri integrali adıyla durur; farkı tam ayrıklaştırma terimidir.
    D = np.asarray(e._port_diameter_history, float)
    tp = np.asarray(e._port_time_history, float)
    rdot = np.diff(D) / (2.0 * np.diff(tp))
    terim = float(np.sum(e.rho_f * e.port_count * np.pi * e.L_grain
                         * rdot ** 2 * np.diff(tp) ** 2))
    assert terim > 0.0
    fark = r['propellant_mass_total'] - reg['mass_flow_curve_integral_kg']
    assert fark > 0.0
    assert 'diagnostic' in reg['mass_flow_curve_integral_basis']


def test_bosalma_kipinde_regule_butce_kimligi_kapanir():
    """Sabit debili bütçe kendi içinde I = Isp·m·g0 ile kapanır."""
    e, r = _motor()
    b = r['constant_oxidizer_flow_budget']
    assert b['total_impulse_Ns'] == pytest.approx(
        b['isp_delivered_avg_s'] * b['propellant_consumed_kg'] * e.g0,
        rel=1e-12)
