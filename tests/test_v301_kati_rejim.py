"""V301/B6 — katı basınç çözücüsü: parçalı yanma hızı yasasının rejim sınırları.

KUSUR (ölçüm 20-21 Eki, docs/scofield/raw/OH/V301/makale1/B6/once.json):
deponun kendi katı örneği (KNDX, 3 × BATES, 75 mm, 40 bar) 228 adımın 9'unda
yakınsamıyordu (en büyük bağıl artık %1,73), ``warn.solid.pressure_solver_
not_converged`` yayımlanıyor ve durum NOT_CONVERGED oluyordu. Kök neden: KNDX
Nakka rejim tablosu sınırlarda süreksiz; 2,57 MPa'da hız basınçla AŞAĞI
sıçrıyor (−%1,80). Belirli bir Kn aralığında iki daldan hiçbirinde denge yok,
sönümlü yineleme sınır çevresinde salınıyor.

DÜZELTME (karar ana modelin): yakınsayan adımlar bit-aynı; yalnız tavana
takılan adımda kütle dengesi artığı parantezlenip ikiye bölünür. Sürekli kök
-> yakınsadı. Parantez bir rejim sınırına çökerse genelleştirilmiş (Filippov)
denge P = P_b, hız r_eq = P_b·A_t/(ρ_p·A_b·c*) ve r_eq sıçramanın içinde
olmak ZORUNDA. Sınırda tutulan adımlar başarısız sayılmaz, ayrı yayımlanır.

SONRA (sonra.json): KNDX 0/228 başarısız, 9 adım 25,7 bar sınırında tutuldu,
kütle dengesi artığı ≤ 7e-7; KNSB ve KNSU örnek eşdeğerleri bit-aynı.
"""

import contextlib
import io
import math

import numpy as np
import pytest

from hrma.data import burn_rate_db
from hrma.engines import solid_rocket_engine as sre
from hrma.engines.solid_rocket_engine import SolidRocketEngine
from tests.test_example_projects import (
    HEADERS, calculate_payload, load_example_doc)

TOL = 1e-6   # calculate_thrust_curve(convergence_tol=1e-6) varsayılanı

#: tests/test_faz4_motor_kapilari.py::KATI_TABAN_YAKINSAMA ile aynı tek üslü
#: taban (V301/T-ÇAPA-A: faz4'ün KATI_TABAN'ı 76 mm'ye taşındı; 30 mm'lik
#: yakınsama senaryosu orada KATI_TABAN_YAKINSAMA adıyla duruyor).
KATI_TABAN = dict(grain_type='bates', propellant_type='apcp',
                  chamber_diameter=100, grain_length=500, core_diameter=30,
                  chamber_pressure=40, burn_rate_a=0.005)


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


def _alanlar(yakit):
    """Örnek KNDX alanları; 'knsu' için aynı geometri + KNSU kataloğu
    (rejim yasası YOK -> tek üslü yol)."""
    alanlar = dict(load_example_doc('solid')['inputs']['fields'])
    if yakit == 'knsu':
        from hrma.data import propellants_db
        d = propellants_db.get_propellant('knsu')
        assert not burn_rate_db.has_law('knsu')
        alanlar.update({
            'propellant_name': d['name'], 'density': float(d['density']),
            'flame_temp': float(d['flame_temperature']),
            'molecular_weight': float(d['molecular_weight']),
            'gamma': float(d['gamma']), 'char_velocity': float(d['c_star']),
            'burn_rate_a': round(float(d['burn_rate_a']), 7),
            'burn_rate_n': round(float(d['burn_rate_n']), 4)})
        alanlar.pop('burn_rate_preset', None)
        # V301/T-ÇAPA-D: örnek katı (ÖRNEK 5fa435893) sayfanın gövdesini
        # taşıyor, içinde propellant_type = 'kndx'; seçim KNDX kalırsa
        # yakıt kimliği KNDX'in rejim tablosuna bağlanır (K-C2) ve vaka
        # tek üslü yol olmaz. Vaka baştan sona KNSU'dur: seçim de KNSU.
        alanlar['propellant_type'] = 'knsu'
    return alanlar


_KOSU = {}


def _kos(client, yakit, yedek=True):
    """HTTP (kullanıcı yolu) koşusu; ham eğri, motor ve yedek çağrıları
    yakalanır. ``yedek=False``: yedek hep None döner (B6 öncesi davranış)."""
    anahtar = (yakit, yedek)
    if anahtar in _KOSU:
        return _KOSU[anahtar]
    yakalanan = {'yedek': []}
    orj_egri = SolidRocketEngine.calculate_thrust_curve
    orj_yedek = SolidRocketEngine._equilibrium_pressure_fallback

    def egri(self, *a, **k):
        eg = orj_egri(self, *a, **k)
        yakalanan['egri'] = eg
        yakalanan['motor'] = self
        return eg

    def yedek_kayitli(self, *a, **k):
        sonuc = orj_yedek(self, *a, **k) if yedek else None
        yakalanan['yedek'].append((a, sonuc))
        return sonuc

    SolidRocketEngine.calculate_thrust_curve = egri
    SolidRocketEngine._equilibrium_pressure_fallback = yedek_kayitli
    try:
        yanit = client.post('/calculate_solid',
                            json=calculate_payload('solid', _alanlar(yakit)),
                            headers=HEADERS)
    finally:
        SolidRocketEngine.calculate_thrust_curve = orj_egri
        SolidRocketEngine._equilibrium_pressure_fallback = orj_yedek
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
    yakalanan['govde'] = yanit.get_json()
    _KOSU[anahtar] = yakalanan
    return yakalanan


def _kndx_sicramasi_yuzde(p_mpa):
    """Tablonun KENDİSİNDEN: r(P_b+)/r(P_b−) − 1 [%]."""
    rej = burn_rate_db.BURN_RATE_LAWS['kndx']['regimes']
    alt = next(r for r in rej if r['p_max_mpa'] == p_mpa)
    ust = next(r for r in rej if r['p_min_mpa'] == p_mpa)
    r_alt = alt['a'] * p_mpa ** alt['n']
    r_ust = ust['a'] * p_mpa ** ust['n']
    return (r_ust - r_alt) / r_alt * 100.0


# ---------------------------------------------------------------------------
# 1. KNDX örneği: yakınsamayan adım yok, sınırda tutulan adım var
# ---------------------------------------------------------------------------

def test_kndx_ornegi_yakinsamayan_adim_yok(client):
    k = _kos(client, 'kndx')
    eg = k['egri']
    assert eg['pressure_solver_failed_steps'] == 0
    assert eg['convergence_achieved'] is True
    assert eg['pressure_solver_max_residual'] <= TOL
    assert eg['pressure_solver_boundary_held_steps'] > 0
    assert (len(eg['pressure_solver_boundary_step_indices'])
            == eg['pressure_solver_boundary_held_steps'])
    govde = k['govde']
    kodlar = {w.get('code') for w in govde['warnings']}
    assert 'warn.solid.pressure_solver_not_converged' not in kodlar
    assert govde['design_summary']['status'] == sre.DESIGN_STATUS_CALCULATED


def test_kndx_yedeksiz_kusur_hala_uretilebilir(client):
    """Kusurun gerçek olduğunun kanıtı: yedek kapalıyken 228 adımın 9'u
    yakınsamıyor (once.json ile aynı sayı)."""
    eg = _kos(client, 'kndx', yedek=False)['egri']
    assert eg['pressure_solver_failed_steps'] == 9
    assert eg['pressure_solver_steps'] == 228
    assert eg['pressure_solver_max_residual'] > 1e-2


def test_sinirda_tutulan_adimlarda_r_eq_sicramanin_icinde_ve_denge_kapali(
        client):
    k = _kos(client, 'kndx')
    eg, motor = k['egri'], k['motor']
    sinir = [s for _, s in k['yedek'] if s is not None
             and s['kind'] == 'boundary']
    assert len(sinir) == eg['pressure_solver_boundary_held_steps'] > 0
    p = np.asarray(eg['pressure'], float)
    r = np.asarray(eg['burn_rate'], float)
    md = np.asarray(eg['mass_flow'], float)
    at = np.asarray(eg['throat_area_series'], float)
    law = burn_rate_db.BURN_RATE_LAWS['kndx']
    for i, s in zip(eg['pressure_solver_boundary_step_indices'], sinir):
        r_eq = s['burn_rate_mps']
        lo = min(s['rate_below_mps'], s['rate_above_mps'])
        hi = max(s['rate_below_mps'], s['rate_above_mps'])
        assert lo <= r_eq <= hi, (i, lo, r_eq, hi)
        # Aşağı sıçrama: altta hız büyük, üstte küçük (kararlı yön)
        assert s['rate_below_mps'] > s['rate_above_mps']
        # Eğriye giden hız r_eq'nun kendisi; basınç sınırın üst rejiminde,
        # bir alt kayan noktalı sayı alt rejimde
        assert r[i] == r_eq
        assert p[i] == s['pressure_bar']
        assert burn_rate_db._select_regime(law, p[i] / 10.0)['p_min_mpa'] \
            == pytest.approx(s['boundary_pressure_bar'] / 10.0, abs=0)
        assert burn_rate_db._select_regime(
            law, np.nextafter(p[i], 0.0) / 10.0)['p_max_mpa'] \
            == s['boundary_pressure_bar'] / 10.0
        # Kütle dengesi: üretim = boğaz akışı
        artik = abs(md[i] * motor.c_star / (at[i] * 1e5) - p[i]) / p[i]
        assert artik < TOL, (i, artik)
        assert s['residual'] < TOL
        assert s['law_jump_percent'] == pytest.approx(
            _kndx_sicramasi_yuzde(2.57), rel=1e-9)


def test_sinir_uclari_ayni_r_tanimiyla_yeniden_uretilir(client):
    """Yedeğin bildirdiği sıçrama uçları burn_rate()'in kendisinden gelir
    (erozif/sıcaklık çarpanları dahil) — bağımsız yeniden değerlendirme."""
    k = _kos(client, 'kndx')
    motor = k['motor']
    for (a, s) in k['yedek']:
        if s is None or s['kind'] != 'boundary':
            continue
        A_burn, A_port, A_t, port_ratio, sicaklik = a[:5]
        p_b = s['pressure_bar']
        p_alt = float(np.nextafter(p_b, 0.0))
        aki_once = motor.mass_flux
        try:
            motor.mass_flux = p_alt * 1e5 * A_t / (motor.c_star * A_port)
            r_alt = motor.burn_rate(p_alt, sicaklik, port_ratio)
            motor.mass_flux = p_b * 1e5 * A_t / (motor.c_star * A_port)
            r_ust = motor.burn_rate(p_b, sicaklik, port_ratio)
        finally:
            motor.mass_flux = aki_once
        assert r_alt == s['rate_below_mps']
        assert r_ust == s['rate_above_mps']
        r_eq = p_b * 1e5 * A_t / (motor.rho_p * A_burn * motor.c_star)
        assert r_eq == pytest.approx(s['burn_rate_mps'], rel=1e-14)


# ---------------------------------------------------------------------------
# 2. Bit-aynılık: yakınsayan adımlar ve tek üslü yol
# ---------------------------------------------------------------------------

_SERILER = ('time', 'pressure', 'thrust', 'mass_flow', 'burn_rate',
            'mass_flux', 'erosive_factor', 'throat_area_series')


def test_tek_uslu_yolda_egri_bit_ayni(client):
    acik = _kos(client, 'knsu')['egri']
    kapali = _kos(client, 'knsu', yedek=False)['egri']
    assert acik['pressure_solver_failed_steps'] == 0
    assert acik['pressure_solver_boundary_held_steps'] == 0
    assert acik['pressure_solver_fallback_root_steps'] == 0
    for ad in _SERILER:
        assert np.array_equal(np.asarray(acik[ad]), np.asarray(kapali[ad])), ad
    assert acik['pressure_solver_max_residual'] == \
        kapali['pressure_solver_max_residual']


def test_kndx_ilk_tutulan_adima_kadar_bit_ayni(client):
    acik = _kos(client, 'kndx')['egri']
    kapali = _kos(client, 'kndx', yedek=False)['egri']
    ilk = acik['pressure_solver_boundary_step_indices'][0]
    assert ilk > 0
    for ad in _SERILER:
        assert np.array_equal(np.asarray(acik[ad])[:ilk],
                              np.asarray(kapali[ad])[:ilk]), ad


def test_apcp_nominal_bit_ayni():
    def kos(yedek):
        m = SolidRocketEngine(burn_rate_n=0.35, **KATI_TABAN)
        if not yedek:
            m._equilibrium_pressure_fallback = lambda *a, **k: None
        return _sessiz(m.calculate_thrust_curve)
    a, b = kos(True), kos(False)
    for ad in _SERILER:
        assert np.array_equal(np.asarray(a[ad]), np.asarray(b[ad])), ad


def test_yavas_daralan_tek_uslu_cozum_surekli_kokle_kurtulur():
    """n = 0.88: gerçek kök var, yineleme yavaş. Yedek kapalıyken başarısız
    adım > 0; açıkken 0 ve kurtarılan adımlar sürekli kök (sınır değil)."""
    acik = _sessiz(SolidRocketEngine(burn_rate_n=0.88,
                                     **KATI_TABAN).calculate_thrust_curve)
    m = SolidRocketEngine(burn_rate_n=0.88, **KATI_TABAN)
    m._equilibrium_pressure_fallback = lambda *a, **k: None
    kapali = _sessiz(m.calculate_thrust_curve)
    assert kapali['pressure_solver_failed_steps'] > 0
    assert acik['pressure_solver_failed_steps'] == 0
    assert acik['pressure_solver_fallback_root_steps'] > 0
    assert acik['pressure_solver_boundary_held_steps'] == 0
    assert acik['pressure_solver_max_residual'] <= TOL


def test_kararsiz_denge_parantezlenmez_n_bir():
    """n >= 1: f artarak sıfırı keser (kararsız) -> yedek kök UYDURMAZ."""
    eg = _sessiz(SolidRocketEngine(burn_rate_n=1.0,
                                   **KATI_TABAN).calculate_thrust_curve)
    assert eg['pressure_solver_failed_steps'] > 0
    assert eg['convergence_achieved'] is False


# ---------------------------------------------------------------------------
# 3. Sentetik süreksiz yasa: genelleştirilmiş denge ve sürekli kök
# ---------------------------------------------------------------------------

B6_SENTETIK_YASA_ANAHTARI = 'v301_b6_sentetik'
P_SINIR_MPA = 3.0


@pytest.fixture()
def sentetik_motor(monkeypatch):
    """%10 AŞAĞI sıçramalı iki rejimli yasa (P_b = 3 MPa = 30 bar)."""
    monkeypatch.setitem(burn_rate_db.BURN_RATE_LAWS, B6_SENTETIK_YASA_ANAHTARI, {
        'name': 'synthetic', 'units': 'mmps_mpan', 'source': 'test',
        'regimes': [
            {'p_min_mpa': 0.1, 'p_max_mpa': P_SINIR_MPA, 'a': 5.0, 'n': 0.4},
            {'p_min_mpa': P_SINIR_MPA, 'p_max_mpa': 20.0, 'a': 4.5, 'n': 0.4},
        ]})
    m = _sessiz(SolidRocketEngine, burn_rate_n=0.4, **KATI_TABAN)
    m.burn_rate_law_key = B6_SENTETIK_YASA_ANAHTARI
    m.erosive_burning_coeff = 0.0
    m.mass_flux = 0.0
    return m


def _A_t_dengesi(m, A_burn, p_bar, r):
    """P = ρ·A_b·r·c*/(A_t·1e5) olacak boğaz alanı."""
    return m.rho_p * A_burn * m.c_star * r / (p_bar * 1e5)


def test_sentetik_sicramada_genellestirilmis_denge(sentetik_motor):
    m = sentetik_motor
    T = m.temp_ref
    A_burn, A_port, oran = 0.05, 1.0, 0.5
    p_b = P_SINIR_MPA * 10.0
    r_alt = m.burn_rate(float(np.nextafter(p_b, 0.0)), T, oran)
    r_ust = m.burn_rate(p_b, T, oran)
    assert r_ust / r_alt - 1 == pytest.approx(-0.10, rel=1e-9)
    # Ne alt ne üst dalda denge yok: r_eq sıçramanın ortasında
    A_t = _A_t_dengesi(m, A_burn, p_b, math.sqrt(r_alt * r_ust))
    s = m._equilibrium_pressure_fallback(A_burn, A_port, A_t, oran, T,
                                         27.0, 33.0, TOL)
    assert s is not None and s['kind'] == 'boundary'
    assert s['pressure_bar'] == p_b
    assert s['boundary_pressure_bar'] == p_b
    assert s['law_jump_percent'] == pytest.approx(-10.0, rel=1e-9)
    assert r_ust <= s['burn_rate_mps'] <= r_alt
    md = m.rho_p * A_burn * s['burn_rate_mps']
    assert abs(md * m.c_star / (A_t * 1e5) - p_b) / p_b < TOL
    # Akı dengeyle tutarlı bırakıldı
    assert m.mass_flux == pytest.approx(
        p_b * 1e5 * A_t / (m.c_star * A_port), rel=1e-15)


def test_sentetik_yasada_surekli_kok_genisletmeyle_bulunur(sentetik_motor):
    m = sentetik_motor
    T = m.temp_ref
    A_burn, A_port, oran = 0.05, 1.0, 0.5
    hedef = 20.0   # alt dalda, sınırdan uzak
    A_t = _A_t_dengesi(m, A_burn, hedef, m.burn_rate(hedef, T, oran))
    # Parantez 25-26 bar'dan (ikisinde de f < 0) aşağı genişlemek zorunda
    s = m._equilibrium_pressure_fallback(A_burn, A_port, A_t, oran, T,
                                         25.0, 26.0, TOL)
    assert s is not None and s['kind'] == 'root'
    assert s['pressure_bar'] == pytest.approx(hedef, rel=5 * TOL)
    assert s['residual'] <= TOL


def test_yukari_sicramada_kararli_dal_koku_bulunur(sentetik_motor,
                                                  monkeypatch):
    """YUKARI sıçrama (+%10): sınırda f(P_b−) < 0 < f(P_b+) — bu kararsız
    bir noktadır, genelleştirilmiş denge DEĞİLDİR. İki dalın kendi kararlı
    kökleri vardır; parantez kararsız yönde başlasa da (f(28,5) < 0 <
    f(31,5)) yedek kararlı yöne genişler ve üst dalın kökünü bulur."""
    monkeypatch.setitem(burn_rate_db.BURN_RATE_LAWS,
                        B6_SENTETIK_YASA_ANAHTARI, {
                            'name': 'synthetic', 'units': 'mmps_mpan',
                            'source': 'test',
                            'regimes': [
                                {'p_min_mpa': 0.1, 'p_max_mpa': P_SINIR_MPA,
                                 'a': 5.0, 'n': 0.4},
                                {'p_min_mpa': P_SINIR_MPA, 'p_max_mpa': 20.0,
                                 'a': 5.5, 'n': 0.4},
                            ]})
    m = sentetik_motor
    T = m.temp_ref
    A_burn, A_port, oran = 0.05, 1.0, 0.5
    p_b = P_SINIR_MPA * 10.0
    r_alt = m.burn_rate(float(np.nextafter(p_b, 0.0)), T, oran)
    r_ust = m.burn_rate(p_b, T, oran)
    r_orta = math.sqrt(r_alt * r_ust)
    A_t = _A_t_dengesi(m, A_burn, p_b, r_orta)
    # Üst dalın kökü: K'·r_ust(30)·(P/30)^0.4 = P
    p_ust = p_b * (r_ust / r_orta) ** (1.0 / 0.6)
    assert 31.5 < p_ust < 34.0
    s = m._equilibrium_pressure_fallback(A_burn, A_port, A_t, oran, T,
                                         28.5, 31.5, TOL)
    assert s is not None and s['kind'] == 'root'
    assert s['pressure_bar'] == pytest.approx(p_ust, rel=5 * TOL)


def test_tavanda_kirpilmis_kok_reddedilir_ve_iz_birakmaz(sentetik_motor,
                                                        monkeypatch):
    """n > 1 tek rejim: kararlı kök yalnız sayısal hız tavanında oluşur;
    bu bir denge değildir -> None, akı ve kırpma kaydı çağrı öncesi gibi."""
    monkeypatch.setitem(burn_rate_db.BURN_RATE_LAWS, B6_SENTETIK_YASA_ANAHTARI, {
        'name': 'synthetic', 'units': 'mmps_mpan', 'source': 'test',
        'regimes': [{'p_min_mpa': 0.1, 'p_max_mpa': 20.0, 'a': 5.0,
                     'n': 1.5}]})
    m = sentetik_motor
    m.mass_flux = 123.0
    m.__dict__.pop('_burn_rate_clipped_max', None)
    T = m.temp_ref
    A_burn, A_port, oran = 0.05, 1.0, 0.5
    A_t = _A_t_dengesi(m, A_burn, 30.0, m.burn_rate(30.0, T, oran))
    s = m._equilibrium_pressure_fallback(A_burn, A_port, A_t, oran, T,
                                         29.0, 31.0, TOL)
    assert s is None
    assert m.mass_flux == 123.0
    assert '_burn_rate_clipped_max' not in m.__dict__


# ---------------------------------------------------------------------------
# 4. Fail-closed: NaN / negatif / tip dışı girdi
# ---------------------------------------------------------------------------

_GECERLI = dict(A_burn=0.05, A_port=1.0, A_t=1e-4, port_ratio=0.5,
                temperature=None, p_start=27.0, p_image=33.0, tol=TOL)


@pytest.mark.parametrize('alan,deger', [
    ('A_burn', float('nan')), ('A_burn', -0.05), ('A_burn', 0.0),
    ('A_t', float('nan')), ('A_t', -1e-4), ('A_t', float('inf')),
    ('A_port', float('nan')), ('A_port', -1.0),
    ('port_ratio', float('nan')), ('temperature', float('nan')),
    ('p_start', float('nan')), ('p_start', -5.0), ('p_image', float('inf')),
    ('tol', float('nan')), ('tol', -1e-6), ('tol', 0.0),
    ('A_burn', 'x'), ('p_start', None),
])
def test_yedek_bozuk_girdide_fail_closed(sentetik_motor, alan, deger):
    m = sentetik_motor
    girdi = dict(_GECERLI, temperature=m.temp_ref)
    girdi[alan] = deger
    m.mass_flux = 7.0
    assert m._equilibrium_pressure_fallback(**girdi) is None
    assert m.mass_flux == 7.0


@pytest.mark.parametrize('bozuk', [
    dict(r_below=float('nan')), dict(r_above=float('nan')),
    dict(r_below=-1.0), dict(p_b=float('nan')), dict(p_b=-30.0),
    dict(A_burn=0.0), dict(c_star=float('inf')), dict(rho_p='x'),
])
def test_sinir_hizi_bozuk_girdide_fail_closed(bozuk):
    girdi = dict(p_b=30.0, r_below=0.011, r_above=0.009, A_t=1e-4,
                 A_burn=0.05, rho_p=1800.0, c_star=1500.0)
    girdi.update(bozuk)
    assert SolidRocketEngine._boundary_equilibrium_rate(**girdi) is None


def test_sinir_hizi_sicramanin_disinda_reddedilir():
    """r_eq sıçramanın dışında -> genelleştirilmiş denge YOK (None)."""
    A_t, A_burn, rho_p, c_star, p_b = 1e-4, 0.05, 1800.0, 1500.0, 30.0
    r_eq = p_b * 1e5 * A_t / (rho_p * A_burn * c_star)
    ic = SolidRocketEngine._boundary_equilibrium_rate(
        p_b, r_eq * 1.01, r_eq * 0.99, A_t, A_burn, rho_p, c_star)
    assert ic == pytest.approx(r_eq, rel=1e-15)
    for alt, ust in ((r_eq * 1.02, r_eq * 1.01), (r_eq * 0.99, r_eq * 0.98)):
        assert SolidRocketEngine._boundary_equilibrium_rate(
            p_b, alt, ust, A_t, A_burn, rho_p, c_star) is None


# ---------------------------------------------------------------------------
# 5. Yayın: tanı bloğu
# ---------------------------------------------------------------------------

def test_tani_blogu_sinir_ozetini_yayimliyor(client):
    k = _kos(client, 'kndx')
    tani = k['govde']['solver_diagnostics']
    eg = k['egri']
    assert tani['convergence_achieved'] is True
    assert tani['pressure_solver_failed_steps'] == 0
    assert (tani['pressure_solver_boundary_held_steps']
            == eg['pressure_solver_boundary_held_steps'] > 0)
    assert tani['pressure_solver_fallback_root_steps'] == 0
    sinirlar = tani['pressure_solver_regime_boundaries']
    assert len(sinirlar) == 1
    assert sinirlar[0]['boundary_pressure_bar'] == pytest.approx(25.7,
                                                                 rel=1e-12)
    assert sinirlar[0]['held_steps'] == \
        tani['pressure_solver_boundary_held_steps']
    assert sinirlar[0]['law_jump_percent'] == pytest.approx(
        _kndx_sicramasi_yuzde(2.57), rel=1e-9)
    assert 'Filippov' in tani['pressure_solver_boundary_basis']
    assert 'regime boundary' in tani['basis']
    not_ = k['govde']['design_summary']['numerical_validity']['note']
    assert 'regime boundary' in not_
    assert 'unconverged' not in not_.lower()


def test_yakinsama_kapisi_blogu_da_yeni_alanlari_tasiyor(monkeypatch):
    # V301/T-ÇAPA-A: n = 1,0 / a = 0,005 rejimi yalnız portu boğulan
    # geometride kurulabiliyor (100 mm tanede hiçbir çekirdek yetmiyor);
    # konu yakınsama kapısı bloğudur, port değil. Port kapısı (KT-23) K-A
    # ``test_solid_codex_fixes`` deseniyle BİLEREK devre dışı; gerekçe
    # tests/test_faz4_motor_kapilari.KATI_TABAN_YAKINSAMA künyesinde.
    monkeypatch.setattr(SolidRocketEngine, '_check_port_throat',
                        lambda self: None)
    sonuc = _sessiz(SolidRocketEngine(burn_rate_n=1.0,
                                      **KATI_TABAN).calculate_performance)
    assert sonuc.get('error')
    tani = sonuc['solver_diagnostics']
    assert tani['pressure_solver_boundary_held_steps'] == 0
    assert tani['pressure_solver_regime_boundaries'] == []
    assert 'Filippov' in tani['pressure_solver_boundary_basis']


def test_select_regime_belgesi_koda_uyuyor():
    """_select_regime: TAM sınırda ÜST rejim (belge eskiden tersini diyordu)."""
    law = burn_rate_db.BURN_RATE_LAWS['kndx']
    assert burn_rate_db._select_regime(law, 2.57)['p_min_mpa'] == 2.57
    assert burn_rate_db._select_regime(
        law, float(np.nextafter(2.57, 0.0)))['p_max_mpa'] == 2.57
    belge = burn_rate_db._select_regime.__doc__
    assert 'ÜST rejim' in belge
    # Eski (yanlış) cümle artık belgenin hükmü değil
    assert 'Rejim sınırında alt rejim geçerlidir' not in belge
