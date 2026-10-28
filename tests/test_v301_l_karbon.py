"""V301 / L-KARBON bekçileri — LOX/RP-1 gaz tarafı karbon birikimi direnci.

Berke (26 Eki 2026): "Bu gece ekle." Kanıt, kaynak satırları ve önce/sonra
tabloları: ``docs/scofield/raw/OH/V301/kati-sivi/L-KARBON/RAPOR.md``.

(a) Direnç TEK kaynaktan: toplu Bartz zinciri ve istasyon marşı aynı işlevi
    (``carbon_deposit_resistance``) ve aynı sayıyı kullanır; kaynak sayıları
    (SP-125 Örnek 4-3: 1670 / 1125 / 1645 in²·s·°F/Btu) yalnız
    ``regen_cooling.py``de durur.
(b) Zarf dışında uygulanmaz ve beyan edilir (LOX/RP-1, O/F 1,77-3,32,
    P_c 4,1-13,8 MPa — NASA TP-2862); metan/LH2 yolunda direnç işlevi HİÇ
    çağrılmaz (sayılar birikimsiz modelle bit-aynı).
(c) SP-125 A-1 kıyas noktası: kitabın kendi h_g'siyle h_gc ve akı yeniden
    üretilir; ürün örneğinde boğaz akısı ölçüme dayalı bantta.
(d) Bartz denetiminin kilidi: HRMA Bartz'ı SP-125 A-1 köşeli parantezini
    %1,5 içinde yeniden üretir (düzeltme yapılmadı); birikimde sigma
    T_wg/T_c = 0,8'de.
(e) SP-8087 §3.4.1 dökülme denetimi: birikimsiz yerel cidar erimeyi aşarsa
    kök uyarılarda KRİTİK.
"""

import ast
import contextlib
import io
import json
import pathlib
import warnings

import pytest

KOK = pathlib.Path(__file__).resolve().parent.parent

# Birim dönüşümü (kaynak sayılarının kendisi değil, birim tanımları).
IN = 0.0254
BTU = 1055.05585262
R2K = 5.0 / 9.0
H_US = BTU / (IN ** 2 * R2K)        # 1 Btu/(in² s °F) -> W/(m² K)


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*a, **k)


def _rp1(**over):
    """Doğrudan RP-1 marşı (örnek sıvı motor ölçeği, CuCrZr)."""
    from hrma.analysis.regen_cooling import RegenCooling
    kw = dict(chamber_pressure=70e5, chamber_temperature=3500.0, gamma=1.2,
              molecular_weight=22.0, throat_diameter=0.055,
              expansion_ratio=12.0, coolant='rp1', coolant_mdot=2.8,
              coolant_inlet_temp=300.0, coolant_inlet_pressure=80e5,
              n_channels=38, channel_width=3.0e-3, channel_height=2.0e-3,
              wall_thickness=1.0e-3, wall_material='cucrzr', n_stations=40)
    kw.update(over)
    return RegenCooling(**kw)


LOX_RP1_BAGLAMI = {'oxidizer': 'lox', 'fuel': 'rp1', 'mixture_ratio': 2.3}


def _ornek_yuk(**ek):
    alan = json.loads((KOK / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma')
                      .read_text(encoding='utf-8'))['inputs']['fields']
    yuk = dict(alan)
    yuk.update(ek)
    return yuk


L_KARBON_VAKALARI = {
    'cucrzr_pc70': dict(chamber_material='cucrzr', chamber_wall_thickness=1.0,
                        chamber_pressure=70, mixture_ratio=2.3),
    'cucrzr_pc30': dict(chamber_material='cucrzr', chamber_wall_thickness=1.0,
                        chamber_pressure=30, mixture_ratio=2.3),
}


@pytest.fixture(scope='module')
def yanit():
    from hrma.app import app
    out = {}
    with app.test_client() as c:
        for ad, ek in L_KARBON_VAKALARI.items():
            r = _sessiz(c.post, '/calculate_liquid', json=_ornek_yuk(**ek),
                        headers={'Host': '127.0.0.1:8080'})
            assert r.status_code == 200, (ad, r.get_data(as_text=True)[:300])
            out[ad] = r.get_json()
    return out


# ---------------------------------------------------------------------------
# (a) tek kaynak
# ---------------------------------------------------------------------------
def test_a_kaynak_sayilari_ve_birim():
    from hrma.analysis import regen_cooling as R
    us = 1.0 / R.CARBON_DEPOSIT_RD_US_TO_SI
    assert R.carbon_deposit_resistance(1.0, True) * us == pytest.approx(1125.0)
    assert R.carbon_deposit_resistance(1.0, False) * us == pytest.approx(1125.0)
    assert R.carbon_deposit_resistance(5.0, True) * us == pytest.approx(1645.0)
    # Yanma odası (A/A_t > şeklin üst ucu) = Örnek 4-3 'combustion chamber'.
    assert R.carbon_deposit_resistance(4.0, False) * us == pytest.approx(1670.0)
    # Şeklin genişleme ucunun ötesi uygulanmaz.
    assert R.carbon_deposit_resistance(25.0, True) is None
    # Birim: 1 / (Btu/(in² s °F) -> W/(m² K)).
    assert R.CARBON_DEPOSIT_RD_US_TO_SI == pytest.approx(1.0 / H_US, rel=1e-12)


def test_a_toplu_zincir_ve_mars_ayni_direnci_kullanir(yanit):
    from hrma.analysis.regen_cooling import carbon_deposit_resistance
    y = yanit['cucrzr_pc70']
    cs = y['cooling_system']
    sm = y['thermal_protection']['station_march']
    bogaz = carbon_deposit_resistance(1.0, False)
    assert cs['carbon_deposit']['applied'] is True
    assert sm['carbon_deposit']['applied'] is True
    assert cs['carbon_deposit']['resistance_throat_m2K_W'] == bogaz
    assert sm['carbon_deposit']['resistance_throat_m2K_W'] == bogaz
    # Toplu zincir direnci GERÇEKTEN kullanır: boğaz akısı
    # h_gc (T_c - T_w), h_gc = 1/(1/h_g + R_d) (SP-125 Eş. 4-18).
    h_gc = 1.0 / (1.0 / cs['bartz_coefficient'] + bogaz)
    assert cs['gas_side_conductance_throat'] == pytest.approx(h_gc, rel=1e-12)
    assert cs['peak_heat_flux'] * 1000.0 == pytest.approx(
        h_gc * (y['chamber_temperature'] - cs['wall_temperature_hot']),
        rel=1e-9)


def test_a_kaynak_sayilari_yalniz_regen_modulunde():
    """1125/1645/1670 ve 0,8 sigma oranı sıvı motorda literal olarak yok."""
    kaynak = (KOK / 'hrma' / 'engines' / 'liquid_rocket_engine.py').read_text(
        encoding='utf-8')
    agac = ast.parse(kaynak)
    sayilar = {n.value for n in ast.walk(agac)
               if isinstance(n, ast.Constant) and isinstance(n.value, float)}
    for s in (1125.0, 1645.0, 1670.0, 2070.0):
        assert s not in sayilar, s
    # Direnç işlevi motorda TEK yardımcıdan (_rd) çağrılır.
    cagri = [n for n in ast.walk(agac) if isinstance(n, ast.Call)
             and getattr(n.func, 'id', None) == 'carbon_deposit_resistance']
    assert len(cagri) == 1


# ---------------------------------------------------------------------------
# (b) zarf, beyan, metan/LH2
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('ox,fu,mr,pc,durum', [
    ('lox', 'rp1', 2.3, 70e5, 'applied'),
    ('lox', 'rp1', 1.77, 4.1e6, 'applied'),
    ('lox', 'rp1', 3.32, 13.8e6, 'applied'),
    ('lox', 'rp1', 3.5, 70e5, 'out_of_envelope'),
    ('lox', 'rp1', 2.3, 30e5, 'out_of_envelope'),
    ('lox', 'rp1', 2.3, 150e5, 'out_of_envelope'),
    ('lox', 'methane', 3.2, 70e5, 'not_applicable'),
    ('lox', 'lh2', 6.0, 70e5, 'not_applicable'),
    ('n2o4', 'rp1', 2.3, 70e5, 'not_applicable'),
])
def test_b_zarf(ox, fu, mr, pc, durum):
    from hrma.analysis.regen_cooling import carbon_deposit_envelope
    z = carbon_deposit_envelope(ox, fu, mr, pc)
    assert z['status'] == durum
    assert z['applied'] is (durum == 'applied')
    assert z['reason']


def test_b_zarf_disi_uygulanmaz_sayilar_birikimsizle_bit_ayni():
    baglamsiz = _rp1(chamber_pressure=30e5).solve()
    disarda = _rp1(chamber_pressure=30e5,
                   motor_data={'carbon_deposit_context': LOX_RP1_BAGLAMI}).solve()
    for k in ('T_wall_hot_K', 'T_wall_cold_K', 'T_coolant_K', 'q_MW_m2',
              'h_gas_W_m2K'):
        assert disarda[k] == baglamsiz[k], k
    assert baglamsiz['carbon_deposit']['status'] == 'not_evaluated'
    assert disarda['carbon_deposit']['status'] == 'out_of_envelope'
    notlar = [w for w in disarda['summary']['warnings']
              if w.startswith('CARBON DEPOSIT: carbon deposit not modelled '
                              '(out of envelope)')]
    assert len(notlar) == 1
    assert not any(w.startswith('CARBON DEPOSIT')
                   for w in baglamsiz['summary']['warnings'])


def test_b_urun_zarf_disi_beyan(yanit):
    y = yanit['cucrzr_pc30']
    sm = y['thermal_protection']['station_march']
    assert sm['carbon_deposit']['status'] == 'out_of_envelope'
    assert y['cooling_system']['carbon_deposit']['status'] == 'out_of_envelope'
    assert any(w.startswith('CARBON DEPOSIT: carbon deposit not modelled')
               for w in sm['warnings'])


@pytest.mark.parametrize('ek', [
    dict(fuel_type='methane', fuel_density=422, mixture_ratio=3.2,
         stoichiometric_of=4.0, of_min=2.5, of_max=4.0,
         chamber_material='cucrzr'),
    dict(fuel_type='lh2', fuel_density=71, mixture_ratio=6.0,
         stoichiometric_of=8.0, of_min=4.0, of_max=8.0,
         chamber_material='cucrzr'),
])
def test_b_metan_lh2_direnc_islevine_ugramaz(ek, monkeypatch):
    from hrma.app import app
    from hrma.analysis import regen_cooling as R
    with app.test_client() as c:
        once = _sessiz(c.post, '/calculate_liquid', json=_ornek_yuk(**ek),
                       headers={'Host': '127.0.0.1:8080'}).get_json()

        def _patla(*a, **k):
            raise AssertionError('carbon_deposit_resistance çağrıldı')
        monkeypatch.setattr(R, 'carbon_deposit_resistance', _patla)
        r = _sessiz(c.post, '/calculate_liquid', json=_ornek_yuk(**ek),
                    headers={'Host': '127.0.0.1:8080'})
    assert r.status_code == 200
    sonra = r.get_json()
    cs0, cs1 = once['cooling_system'], sonra['cooling_system']
    assert cs1['carbon_deposit']['status'] == 'not_applicable'
    for k in ('total_heat_load', 'peak_heat_flux', 'bartz_coefficient',
              'coolant_exit_temperature', 'wall_temperature_hot'):
        assert cs1[k] == cs0[k], k
    assert cs1['gas_side_conductance_throat'] == cs1['bartz_coefficient']


# ---------------------------------------------------------------------------
# (c) SP-125 A-1 kıyası
# ---------------------------------------------------------------------------
def test_c_sp125_a1_hgc_ve_aki_yeniden_uretilir():
    """SP-125 Örnek 4-3/4-4 (s. 102-110): h_g 0,0027 -> h_gc 0,00067
    Btu/in²s°F; q = (5667 - 1188) x 0,00067 = 3,00 Btu/in²s (4,90 MW/m²)."""
    from hrma.analysis.regen_cooling import carbon_deposit_resistance
    h_g = 0.0027 * H_US
    h_gc = 1.0 / (1.0 / h_g + carbon_deposit_resistance(1.0, False))
    assert h_gc / H_US == pytest.approx(0.00067, rel=0.01)
    q = h_gc * (5667.0 - 1188.0) * R2K
    assert q / 1e6 == pytest.approx(4.90, rel=0.01)


def test_c_urun_ornegi_bogaz_akisi_olcume_dayali_bantta(yanit):
    """Ürün (25 kN, Pc 70, O/F 2,3, CuCrZr 1 mm) nominal tepe akı SP-125
    A-1'in 4,90 MW/m²'sinin [1,0; 1,5] katı. Ölçüldü: 6,62 MW/m² (1,35x);
    fark Bartz özellik teriminden (+%23,9, gamma_eff 1,170 ⟷ SP-125 1,222)
    ve kütle akısı/eğrilik terimlerinden (bartz_denetim.json). Birikimsiz
    model 35,3 MW/m² (7,2x) veriyordu."""
    sm = yanit['cucrzr_pc70']['thermal_protection']['station_march']
    oran = sm['peak_heat_flux_MW_m2'] / 4.90
    assert 1.0 <= oran <= 1.5, oran


# ---------------------------------------------------------------------------
# (d) Bartz denetiminin kilidi + sigma
# ---------------------------------------------------------------------------
def test_d_bartz_sp125_a1_koseli_parantezi_yeniden_uretir():
    from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
    lb = 0.45359237
    hta = HeatTransferAnalyzer.__new__(HeatTransferAnalyzer)
    gaz = {'gas_viscosity': 4.18e-6 * lb / IN,
           'gas_cp': 0.485 * BTU / lb / R2K, 'prandtl': 0.816,
           'gamma': 1.222}
    tc = 6140.0 * R2K
    h = hta._bartz_coefficient(24.9 * IN, 1000.0 * 6894.757293168,
                               5660.0 * 0.3048, gaz, tc, 0.8 * tc,
                               11.71 / 24.9)
    m2 = 1.0 + 0.222 / 2.0
    sigma = 1.0 / ((0.5 * 0.8 * m2 + 0.5) ** 0.68 * m2 ** 0.12)
    # SP-125 Şekil 4-24 okuması sigma = 1,0 (T_wg/T_c 0,8); formül 1,027.
    assert sigma == pytest.approx(1.0, rel=0.03)
    assert (h / sigma) / (0.0027 * H_US) == pytest.approx(1.0, rel=0.015)


def test_d_birikimde_sigma_08():
    from hrma.analysis.regen_cooling import CARBON_DEPOSIT_SIGMA_TWG_OVER_TC
    rc = _rp1(motor_data={'carbon_deposit_context': LOX_RP1_BAGLAMI})
    r = rc.solve()
    assert r['carbon_deposit']['applied'] is True
    ti = r['throat_index']
    gaz = rc._hta._get_gas_properties(rc._md_gas, rc.chamber_temperature)
    th = rc._hta._resolve_throat_conditions(
        rc._md_gas, rc.chamber_pressure, rc.chamber_temperature, gaz,
        rc.motor_data.get('mdot_total', 1.0))
    h = rc._hta._bartz_coefficient(
        th['throat_diameter'], rc.chamber_pressure, th['c_star'], gaz,
        rc.chamber_temperature,
        CARBON_DEPOSIT_SIGMA_TWG_OVER_TC * rc.chamber_temperature,
        th['rc_over_dt'], area_ratio_local=1.0 / r['area_ratio'][ti],
        mach_local=r['mach'][ti])
    assert r['h_gas_W_m2K'][ti] == pytest.approx(h, rel=1e-12)


def test_d_seri_devre_birikimle_kapanir():
    r = _rp1(motor_data={'carbon_deposit_context': LOX_RP1_BAGLAMI}).solve()
    rd = r['carbon_deposit_resistance_m2K_W']
    for i in range(r['n_stations']):
        q = r['q_MW_m2'][i] * 1e6
        # Metal sıcak cidar = T_aw - q (1/h_g + R_d)
        assert r['T_wall_hot_K'][i] == pytest.approx(
            r['T_recovery_K'][i] - q * (1.0 / r['h_gas_W_m2K'][i] + rd[i]),
            rel=1e-9)


def test_d_sekil_disi_istasyonlar_sayilir():
    r = _rp1(expansion_ratio=25.0,
             motor_data={'carbon_deposit_context': LOX_RP1_BAGLAMI}).solve()
    cd = r['carbon_deposit']
    assert cd['stations_beyond_figure_not_applied'] > 0
    disari = [i for i, a in enumerate(r['area_ratio'])
              if i > r['throat_index'] and a > 14.8]
    assert len(disari) == cd['stations_beyond_figure_not_applied']
    assert all(r['carbon_deposit_resistance_m2K_W'][i] == 0.0 for i in disari)


# ---------------------------------------------------------------------------
# (e) SP-8087 §3.4.1 dökülme
# ---------------------------------------------------------------------------
def test_e_dokulmus_cidar_daha_sicak_ve_bant_yayimlanir():
    r = _rp1(motor_data={'carbon_deposit_context': LOX_RP1_BAGLAMI}).solve()
    nominal = r['T_wall_hot_K']
    dokulmus = r['T_wall_hot_no_deposit_K']
    for i, (a, b) in enumerate(zip(nominal, dokulmus)):
        if r['carbon_deposit_resistance_m2K_W'][i] > 0.0:
            assert b > a, i
    band = r['carbon_deposit']['band']
    assert band['nominal']['peak_wall_hot_K'] == r['summary']['max_wall_hot_K']
    assert band['conservative']['peak_wall_hot_K'] == pytest.approx(
        max(v for v in dokulmus if v is not None), rel=0, abs=0)
    assert band['optimistic'] is None and band['optimistic_note']


def test_e_urunde_dokulme_erimeyi_asarsa_kok_uyari_kritik(yanit):
    y = yanit['cucrzr_pc70']
    sm = y['thermal_protection']['station_march']
    cd = sm['carbon_deposit']
    assert cd['spalled_above_melting'] is True
    assert cd['band']['conservative']['peak_wall_hot_K'] > \
        sm['material_melting_K']
    satir = [w for w in sm['warnings']
             if w.startswith('CRITICAL: where the carbon deposit spalls')]
    assert len(satir) == 1
    # V301/DİL (L-KARBON DEVİR 1): kök uyarı kendi koduyla iner; sayılar
    # marşın KENDİ cümlesindekilerle aynıdır (hüküm ve sayı değişmedi).
    kok = [w for w in y['input_warnings']
           if w.get('code') == 'warn.liquid.deposit_spall_above_melting'
           and w.get('severity') == 'critical']
    assert len(kok) == 1
    p = kok[0]['params']
    assert ('reaches %s K, above the %s melting point %s K'
            % (p['spall_K'], p['material'], p['melting_K'])) in satir[0]
    assert not [w for w in y['input_warnings']
                if w.get('code') == 'warn.liquid.regen_march_note'
                and str((w.get('params') or {}).get('detail', '')).startswith(
                    'CRITICAL: where the carbon deposit spalls')]


def test_e_tr_karsiliklari_var():
    js = (KOK / 'hrma' / 'static' / 'js' / 'i18n_charts.js').read_text(
        encoding='utf-8')
    for desen in (r'/^CARBON DEPOSIT: LOX\/RP-1 gas-side carbon deposit',
                  r'/^CRITICAL: where the carbon deposit spalls',
                  r'/^CARBON DEPOSIT: carbon deposit not modelled'):
        assert desen in js, desen
    assert 'KARBON BİRİKİMİ' in js
