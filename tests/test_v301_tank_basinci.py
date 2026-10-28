"""v3.0.1 (Ayberk tur 1 · kulvar T) — tank basıncı kullanıcıya açık.

Ayberk'in maddesi: "Tank pressure kullanıcıya bırakılma seçeneği de olsun.
Kullanıcı değiştirebilsin." Ölçülen kusur (rapor, ``once.json``): N₂O'da
devre P₁ = P_sat(T_tank), LOX/H₂O₂'de P₁ = P_c·(1 + ΔP/P_c) alıyordu ve
istekteki ``tank_pressure`` hiçbir kipte devreye girmiyordu (N₂O 60 ⟷ 80 bar,
LOX 30 ⟷ 40 bar enjektör çözümü bit-aynı).

Ana model kararı (Astra danışması) ve bu dosyanın bekçileri:
  * ``tank_pressure_source``: self_pressurised (N₂O varsayılanı) |
    design_pressure_drop (LOX/H₂O₂ varsayılanı) | user;
  * user kipinde P₁ = P_tank (hat kaybı modellenmiyor, beyanlı) devre
    çözücüsüne ``p_feed_bar`` olarak gider; ΔP = P₁ − P_c özdeşliği;
  * ΔP ≤ 0 → 422; N₂O'da P_tank < P_sat(T)·(1 − pay) → 422 (denge başlangıç
    hâli; yarı-kararlı sıvı modellenmez);
  * NHNE κ yalnız P₂ < P_v'de; P₂ ≥ P_v'de tek fazlı SPI ve etiket SPI;
  * takviyeli N₂O'da sıvı yoğunluğu (P₁, T) sıkıştırılmış sıvı;
  * user kipinde kendinden basınçlı blowdown bloğu yayımlanmaz;
  * varsayılan kipler BİT-AYNI (açık beyanlı kip = beyansız istek).

Kâhinler ürün kodundan bağımsızdır: CoolProp (N₂O EOS, Lemmon & Span 2006),
SPI orifis bağıntısı A = ṁ/(C_d·√(2ρΔP)) (Sutton & Biblarz Böl. 8), Dyer
κ tanımı (AIAA 2007-5702). Pay (0,02) Sunum 2 7. tur satırından LİTERAL.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import pathlib
import re
import shutil
import subprocess
import warnings

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
ADV_HTML = KOK / 'hrma' / 'templates' / 'advanced.html'
I18N_ADV = KOK / 'hrma' / 'static' / 'js' / 'i18n_advanced.js'

#: Sunum 2 7. tur YB-04: tank basıncı ⟷ P_sat payı (HRMA seçimi) — LİTERAL.
SUNUM_TANK_PSAT_PAYI = 0.02

#: Ornek-H1 (tests/test_d37_hibrit_f1.py::ORNEK_H1 ile aynı yük).
H1 = {
    'thrust': 1000.0, 'burn_time': 10.0, 'chamber_pressure': 20.0,
    'of_ratio': 7.5, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'tank_pressure': 50.0, 'injector_type': 'showerhead',
    'injector_material': 'stainless_steel', 'chamber_material': 'steel_304',
    'wall_thickness': 5.0, 'safety_factor': 4.0, 'pressure_drop': 4.0,
    'include_plots': False,
}
LOX = dict(H1, oxidizer_type='lox', of_ratio=2.5)
U = {'tank_pressure_source': 'user'}

_CACHE = {}


def _post(yol, govde):
    from hrma.app import app
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with app.test_client() as ist:
            r = ist.post(yol, json=govde)
    return r.status_code, r.get_json()


def _calc(anahtar, govde):
    """Aynı yükü bir kez koşar (her /calculate birkaç saniye)."""
    if anahtar not in _CACHE:
        _CACHE[anahtar] = _post('/calculate', govde)
    return _CACHE[anahtar]


def _ok(anahtar, govde):
    kod, j = _calc(anahtar, govde)
    assert kod == 200, j
    return j


def _md5(j):
    import hashlib
    return hashlib.md5(json.dumps(j, sort_keys=True, default=str)
                       .encode('utf-8')).hexdigest()


def _coolprop():
    cp = pytest.importorskip('CoolProp.CoolProp')
    return cp.PropsSI


# ===========================================================================
# 1. Kip çözümü ve değer kapıları (saf işlevler)
# ===========================================================================
def test_kip_adlari_tek_tanim_ve_pay_literal():
    from hrma.engines import hybrid_rocket_engine as h
    assert h.TANK_PRESSURE_SOURCES == ('self_pressurised',
                                       'design_pressure_drop', 'user')
    assert h.TANK_PRESSURE_SOURCE_REQUEST_VALUES == (
        'default', 'self_pressurised', 'design_pressure_drop', 'user')
    assert h.FEED_PRESSURE_SOURCE_N2O_SAT == 'n2o_saturation_at_tank_temperature'
    assert (h.FEED_PRESSURE_SOURCE_DESIGN_DP
            == 'chamber_pressure_plus_design_pressure_drop')
    assert h.FEED_PRESSURE_SOURCE_USER_TANK == 'user_tank_pressure'
    assert h.TANK_PRESSURE_PSAT_REL_TOL == SUNUM_TANK_PSAT_PAYI


@pytest.mark.parametrize('kaynak,ox,beklenen', [
    (None, 'n2o', 'self_pressurised'), ('', 'n2o', 'self_pressurised'),
    ('  ', 'lox', 'design_pressure_drop'), (None, 'lox', 'design_pressure_drop'),
    (None, 'h2o2', 'design_pressure_drop'), (None, None, 'self_pressurised'),
    ('user', 'n2o', 'user'), ('USER', 'lox', 'user'),
    ('self_pressurised', 'n2o', 'self_pressurised'),
    ('design_pressure_drop', 'h2o2', 'design_pressure_drop'),
    # Ön yüzün seçim kutusu değeri 'default' = oksitleyicinin varsayılanı.
    ('default', 'n2o', 'self_pressurised'),
    ('Default', 'lox', 'design_pressure_drop'),
])
def test_kip_cozumu(kaynak, ox, beklenen):
    from hrma.engines.hybrid_rocket_engine import resolve_tank_pressure_source
    kip, ret = resolve_tank_pressure_source(kaynak, ox)
    assert (kip, ret) == (beklenen, None)


@pytest.mark.parametrize('kaynak,ox,neden', [
    ('regulated', 'n2o', 'unknown_value'),
    (['user'], 'n2o', 'not_a_string'), ({'a': 1}, 'lox', 'not_a_string'),
    (True, 'n2o', 'not_a_string'), (1, 'n2o', 'not_a_string'),
    ('self_pressurised', 'lox', 'not_applicable_to_oxidizer'),
    ('self_pressurised', 'h2o2', 'not_applicable_to_oxidizer'),
    ('design_pressure_drop', 'n2o', 'not_applicable_to_oxidizer'),
])
def test_kip_reddi_sessiz_yedege_dusmez(kaynak, ox, neden):
    from hrma.engines.hybrid_rocket_engine import resolve_tank_pressure_source
    kip, ret = resolve_tank_pressure_source(kaynak, ox)
    assert kip is None
    assert ret['field'] == 'tank_pressure_source' and ret['reason'] == neden
    assert ret['accepted_values']


@pytest.mark.parametrize('deger,neden', [
    (None, 'required_for_user_tank_pressure_source'),
    ('', 'required_for_user_tank_pressure_source'),
    ('60', 'not_a_json_number'), (True, 'not_a_json_number'),
    ([60], 'not_a_json_number'), ({'p': 60}, 'not_a_json_number'),
    (float('nan'), 'not_a_positive_finite_number'),
    (float('inf'), 'not_a_positive_finite_number'),
    (-5.0, 'not_a_positive_finite_number'),
    (0, 'not_a_positive_finite_number'),
])
def test_kullanici_tank_basinci_deger_kapisi(deger, neden):
    from hrma.engines.hybrid_rocket_engine import user_tank_pressure_state
    durum, ret = user_tank_pressure_state(deger, 20.0, 'lox', None)
    assert durum is None
    assert [(k['field'], k['reason']) for k in ret] == [('tank_pressure', neden)]


def _psat_kahin_bar(T):
    """Bağımsız kâhin: CoolProp N₂O doyma basıncı (Lemmon & Span 2006)."""
    return _coolprop()('P', 'T', T, 'Q', 0, 'N2O') / 1e5


def test_doyma_kapisinin_psati_devrenin_pv_si_ve_kahinle_uyumlu():
    """Kapının P_sat'ı = devrenin NHNE'ye verdiği P_v (tek kaynak); CoolProp
    kâhiniyle tablo farkı ‰1'in altında (ürün tablo yolunu kullanır)."""
    from hrma.engines.injector_design import (design_injector,
                                              n2o_vapor_pressure_bar)
    for T in (270.0, 293.15, 300.0):
        p_kapi = n2o_vapor_pressure_bar(T)
        d = design_injector({'motor_type': 'hybrid', 'injector_type': 'showerhead',
                             'mdot_ox': 0.38, 'Pc_bar': 15.0, 'fluid_ox': 'n2o',
                             'T_ox_K': T})
        assert d['ox_circuit']['vapor_pressure_bar'] == pytest.approx(
            p_kapi, rel=1e-12)
        assert p_kapi == pytest.approx(_psat_kahin_bar(T), rel=1e-3)


def test_doyma_sarti_pay_disinda_reddeder_pay_icinde_kabul_eder():
    from hrma.engines.hybrid_rocket_engine import user_tank_pressure_state
    from hrma.engines.injector_design import n2o_vapor_pressure_bar
    p_sat = n2o_vapor_pressure_bar(293.15)
    p_min = p_sat * (1.0 - SUNUM_TANK_PSAT_PAYI)
    for p in (p_sat, p_min * 1.0001, 60.0):
        durum, ret = user_tank_pressure_state(p, 20.0, 'n2o', None)
        assert ret == [] and durum['injector_inlet_pressure_bar'] == p
        assert durum['saturation_pressure_bar'] == pytest.approx(p_sat)
        assert durum['feed_line_loss_included'] is False
    durum, ret = user_tank_pressure_state(p_min * 0.9999, 20.0, 'n2o', None)
    assert durum is None and len(ret) == 1
    k = ret[0]
    assert k['reason'] == 'below_n2o_saturation_pressure'
    assert k['saturation_pressure_bar'] == pytest.approx(p_sat)
    assert k['minimum_bar'] == pytest.approx(p_min)
    assert k['tank_temperature_K'] == 293.15
    assert k['relative_tolerance'] == SUNUM_TANK_PSAT_PAYI
    for parca in ('equilibrium', 'metastable', 'Raise the tank',
                  'lower the tank temperature'):
        assert parca in k['message'], parca
    # Kullanıcının sıcaklığı okunur: 270 K'de P_sat düşer, 40 bar geçer.
    durum, ret = user_tank_pressure_state(40.0, 20.0, 'n2o', 270.0)
    assert ret == [] and durum['tank_temperature_K'] == 270.0
    # LOX/H₂O₂'de doyma şartı yoktur (kendinden basınçlı değil).
    durum, ret = user_tank_pressure_state(25.0, 20.0, 'lox', None)
    assert ret == [] and 'saturation_pressure_bar' not in durum


def test_dp_sifir_ve_alti_sayilarla_reddedilir_iki_ret_birlikte():
    from hrma.engines.hybrid_rocket_engine import user_tank_pressure_state
    for p in (20.0, 19.9):
        durum, ret = user_tank_pressure_state(p, 20.0, 'lox', None)
        assert durum is None
        assert [k['reason'] for k in ret] == [
            'injector_pressure_drop_not_positive']
        k = ret[0]
        assert (k['submitted'], k['injector_inlet_pressure_bar'],
                k['chamber_pressure_bar'], k['feed_line_loss_bar'],
                k['feed_line_loss_included']) == (p, p, 20.0, None, False)
    # N₂O, P_c 60 bar, P_tank 45 bar: hem ΔP ≤ 0 hem doyma altı.
    _d, ret = user_tank_pressure_state(45.0, 60.0, 'n2o', None)
    assert [k['reason'] for k in ret] == [
        'injector_pressure_drop_not_positive', 'below_n2o_saturation_pressure']


def test_motor_kurucusu_ayni_kapiyla_reddeder_python_api():
    from hrma.engines.hybrid_rocket_engine import (HybridRocketEngine,
                                                   TankPressureSourceError)
    with pytest.raises(TankPressureSourceError) as e:
        HybridRocketEngine(thrust=1000, burn_time=10, of_ratio=7.5,
                           chamber_pressure=20, oxidizer_type='n2o',
                           tank_pressure_source='user', tank_pressure=45.0)
    assert e.value.field == 'tank_pressure'
    assert e.value.reason == 'below_n2o_saturation_pressure'
    assert isinstance(e.value, ValueError)
    with pytest.raises(TankPressureSourceError) as e:
        HybridRocketEngine(thrust=1000, burn_time=10, of_ratio=2.5,
                           chamber_pressure=20, oxidizer_type='lox',
                           tank_pressure_source='self_pressurised')
    assert e.value.reason == 'not_applicable_to_oxidizer'
    # Varsayılan kipte tank_pressure OKUNMAZ (bugünkü sözleşme).
    m = HybridRocketEngine(thrust=1000, burn_time=10, of_ratio=7.5,
                           chamber_pressure=20, oxidizer_type='n2o',
                           tank_pressure='çöp')
    assert m.tank_pressure_source == 'self_pressurised'
    assert m._user_tank_feed is None


# ===========================================================================
# 2. NHNE alan denetimi ve giriş yoğunluğu (devre modülü)
# ===========================================================================
def _devre(T, pc, p_feed, rho=None):
    from hrma.engines.injector_design import design_injector
    s = {'motor_type': 'hybrid', 'injector_type': 'showerhead',
         'mdot_ox': 0.38, 'Pc_bar': pc, 'fluid_ox': 'n2o', 'T_ox_K': T,
         'p_feed_bar': p_feed, 'cd': 0.7}
    if rho is not None:
        s['rho_ox'] = rho
    return design_injector(s)


def test_nhne_p2_pv_ustunde_spi_ve_kappa_yok():
    """T = 260 K: P_v ≈ 21,9 bar < P_c = 30 bar. κ tanımsız → SPI; alan
    SPI kâhinine eşit (bağımsız: A = ṁ/(C_d·√(2ρΔP)))."""
    rho = 980.0
    d = _devre(260.0, 30.0, 50.0, rho=rho)
    ox = d['ox_circuit']
    assert ox['vapor_pressure_bar'] < 30.0
    assert ox['flow_model'] == 'SPI'
    assert ox['nhne']['kappa'] is None
    assert 'undefined' in ox['nhne']['domain']
    a_kahin = 0.38 / (0.7 * math.sqrt(2.0 * rho * 20.0e5))
    # Delik planı kâhin alanı tam karşılar ya da üst kenara yuvarlar; devre
    # çözümünün GEREKLİ alanı birim akıdan okunur: ṁ/(ρ·v) yerine plan
    # yuvarlamasından bağımsız kıyas için birim alan debisi.
    from hrma.engines.injector_design import nhne_mass_flow
    g = nhne_mass_flow(0.7, 1.0, 50.0, 30.0, ox['vapor_pressure_bar'], 260.0,
                       rho)['mdot_kg_s']
    assert 0.38 / g == pytest.approx(a_kahin, rel=1e-12)


def test_nhne_p2_pv_altinda_kappa_dyer_tanimi():
    from hrma.engines.injector_design import n2o_vapor_pressure_bar
    d = _devre(293.15, 20.0, 60.0)
    ox = d['ox_circuit']
    pv = n2o_vapor_pressure_bar(293.15)
    assert ox['flow_model'] == 'NHNE'
    assert 'domain' not in ox['nhne']
    assert ox['nhne']['kappa'] == pytest.approx(
        math.sqrt((60.0 - 20.0) / (pv - 20.0)), rel=1e-12)


def test_giris_yogunlugu_sikistirilmis_sivi_kahinle():
    from hrma.engines.hybrid_rocket_engine import n2o_inlet_liquid_density
    PropsSI = _coolprop()
    T = 293.15
    for p in (55.0, 60.0, 80.0):
        rho, kunye = n2o_inlet_liquid_density(T, p)
        assert rho == pytest.approx(PropsSI('D', 'T', T, 'P', p * 1e5, 'N2O'),
                                    rel=1e-12)
        assert 'compressed' in kunye
    rho_sat = PropsSI('D', 'T', T, 'Q', 0, 'N2O')
    rho60, _ = n2o_inlet_liquid_density(T, 60.0)
    assert rho60 > rho_sat * 1.02          # ölçülen +%2,28
    rho50, kunye = n2o_inlet_liquid_density(T, 50.0)   # P_sat'ın altı (pay içi)
    assert rho50 == pytest.approx(rho_sat, rel=1e-12)
    assert 'saturated' in kunye


# ===========================================================================
# 3. /calculate — kullanıcı tank basıncı kipi
# ===========================================================================
def _n2o_u(p):
    return _ok('n2o_u%g' % p, dict(H1, tank_pressure=p, **U))


def test_n2o_kullanici_basinci_devreye_baglanir_ve_ozdeslik():
    """TERS MUTASYON BEKÇİSİ: p_feed_bar bağlaması koparsa P₁ = P_sat'a
    döner ve bu test KIRMIZI olur."""
    j = _n2o_u(60.0)
    idd = j['motor']['injector_design']
    ox = j['motor']['injector_design_detail']['ox_circuit']
    pc = float(j['motor']['chamber_pressure'])
    assert idd['feed_pressure_source'] == 'user_tank_pressure'
    assert idd['feed_pressure_bar'] == 60.0
    assert ox['delta_p_bar'] == pytest.approx(60.0 - pc, rel=1e-12)
    assert idd['injection_pressure_drop_bar'] == pytest.approx(60.0 - pc)
    assert idd['feed_pressure_bar'] == pytest.approx(pc + ox['delta_p_bar'],
                                                     rel=1e-12)
    assert idd['tank_pressure_source'] == 'user'
    assert idd['tank_pressure_bar'] == 60.0
    assert idd['feed_line_loss_included'] is False
    assert idd['feed_line_loss_bar'] is None
    assert 'NOT INCLUDED' in idd['feed_line_loss_basis']
    for parca in ('user-supplied tank pressure', 'NOT included',
                  'Zimmerman', 'NHNE', 'P_2 < P_v'):
        assert parca in idd['feed_pressure_basis'], parca
    # Plaka (utils) ΔP'yi çözücünün kanonundan alır.
    assert j['injector']['pressure_drop_bar'] == pytest.approx(60.0 - pc)
    # Takviyeli giriş beyanı ve aşırı soğutulmuş giriş hâli.
    kodlar = {a.get('code') for a in
              j['motor']['injector_design_detail'].get('assumptions') or []}
    assert 'warn.injector.n2o_supercharged_feed' in kodlar
    gs = idd['inlet_state']
    assert gs['subcooled'] is True
    assert gs['subcooling_pressure_margin_bar'] == pytest.approx(
        60.0 - ox['vapor_pressure_bar'])
    assert gs['liquid_density_kg_m3'] == pytest.approx(
        _coolprop()('D', 'T', 293.15, 'P', 60e5, 'N2O'), rel=1e-12)


def test_n2o_basinc_artinca_dp_artar_alan_azalir():
    sonuc = [_n2o_u(p) for p in (60.0, 70.0, 80.0)]
    dp = [s['motor']['injector_design_detail']['ox_circuit']['delta_p_bar']
          for s in sonuc]
    alan = [s['motor']['injector_design']['total_injector_area_mm2']
            for s in sonuc]
    assert dp[0] < dp[1] < dp[2]
    assert alan[0] > alan[1] > alan[2]


def test_n2o_kullanici_kipinde_kullanilmadi_uyarisi_ve_kunyesi_yok():
    j = _n2o_u(80.0)
    m = j['motor']
    assert not [w for w in m['warnings']
                if w.get('code') == 'warn.hybrid.tank_pressure_not_used']
    assert not [k for k in j.get('defaults_applied') or []
                if isinstance(k, dict) and k.get('field') == 'tank_pressure']
    assert m['tank_pressure'] == 80.0


def test_n2o_kullanici_kipinde_blowdown_yayimlanmaz_beyan_var():
    m = _n2o_u(60.0)['motor']
    bd = m['tank_blowdown']
    assert bd['status'] == 'NOT_MODELLED'
    assert bd['tank_pressure_source'] == 'user'
    assert 'time_s' not in bd and 'tank_pressure_bar' not in bd
    metin = ' '.join(bd['not_modelled']) + bd['not_modelled_basis']
    for parca in ('ullage', 'dissolution', 'Waxman', 'Zimmerman'):
        assert parca in metin, parca
    # Blowdown'a bağlı tüketiciler sayı uydurmaz. V301/H1 (beklenti
    # değişti, gerekçe docs/scofield/raw/OH/V301/bilinen/hibrit/RAPOR.md):
    # kap bloğu artık tankın kendi hâlinden (MEOP = P_tank) modellenir;
    # blowdown GEÇMİŞİNDEN türeyen hiçbir sayı yoktur.
    kap = m['oxidizer_tank_pressure_vessel']
    assert kap['meop_bar'] == 60.0 and kap['tank_pressure_source'] == 'user'
    assert 'tank_blowdown solution' not in kap['meop_source']
    assert m['of_shift']['blowdown']['status'] == 'NOT_MODELLED'


def test_psat_payi_icinde_50_bar_eski_yorumun_olcumu():
    """Eski motor yorumu: "p_feed_bar verilseydi Ornek-H1'de ΔP 30,543 →
    30,000 bar". Pay içi 50 bar (P_sat'ın %1,07 altı) kabul edilir ve ΔP tam
    olarak 30,000 olur."""
    j = _ok('n2o_u50', dict(H1, tank_pressure=50.0, **U))
    ox = j['motor']['injector_design_detail']['ox_circuit']
    assert ox['delta_p_bar'] == pytest.approx(30.0, rel=1e-12)
    assert ox['flow_model'] == 'NHNE'


def test_lox_kullanici_basinci_spi_kahini():
    from hrma.data.propellant_database import PropellantDatabase
    j = _ok('lox_u30', dict(LOX, tank_pressure=30.0, **U))
    m = j['motor']
    idd = m['injector_design']
    ox = m['injector_design_detail']['ox_circuit']
    assert idd['feed_pressure_source'] == 'user_tank_pressure'
    assert ox['delta_p_bar'] == pytest.approx(10.0, rel=1e-12)
    assert ox['flow_model'] == 'SPI'
    assert 'inlet_state' not in idd
    rho = float(PropellantDatabase().get_propellant_properties('lox')['density'])
    a_gerekli = m['mdot_ox'] / (ox['cd'] * math.sqrt(2.0 * rho * 10.0e5))
    # Plan alanı gerekli alanı karşılar (delik planı yukarı yuvarlar).
    assert idd['total_injector_area_mm2'] * 1e-6 >= a_gerekli * (1 - 1e-9)
    j40 = _ok('lox_u40', dict(LOX, tank_pressure=40.0, **U))
    assert (j40['motor']['injector_design_detail']['ox_circuit']['delta_p_bar']
            == pytest.approx(20.0))


def test_lox_dusuk_dp_chug_uyarisi_mevcut_kapidan():
    j = _ok('lox_u22', dict(LOX, tank_pressure=22.0, **U))
    m = j['motor']
    ox = m['injector_design_detail']['ox_circuit']
    assert ox['dp_pc_ratio'] == pytest.approx(0.1)
    kodlar = [w.get('code') for w in
              m['injector_design_detail'].get('warnings') or []]
    assert 'warn.injector.chug_risk' in kodlar
    from hrma.analysis.acoustic_modes import CHUG_DP_RATIO_MINIMUM
    assert ox['dp_pc_ratio'] < CHUG_DP_RATIO_MINIMUM
    assert m['combustion_stability']['chug_loop']['dp_ratio_j'] == \
        pytest.approx(0.1)


def test_soguk_takviyeli_n2o_p2_pv_ustu_200_ve_spi():
    j = _ok('n2o_soguk', dict(H1, tank_pressure=50.0, oxidizer_temp=260.0,
                              chamber_pressure=30.0, **U))
    ox = j['motor']['injector_design_detail']['ox_circuit']
    assert ox['flow_model'] == 'SPI' and ox['nhne']['kappa'] is None
    assert j['motor']['injector_design']['inlet_state']['flow_model'] == 'SPI'


# ===========================================================================
# 4. /calculate — 422 kapıları
# ===========================================================================
def test_422_psat_alti_sayilarla():
    from hrma.engines.injector_design import n2o_vapor_pressure_bar
    kod, j = _calc('n2o_u45', dict(H1, tank_pressure=45.0, **U))
    assert kod == 422, j
    assert j['error'] == 'tank_pressure_below_saturation'
    assert j['field'] == 'tank_pressure'
    k = j['invalid_fields'][0]
    assert k['reason'] == 'below_n2o_saturation_pressure'
    assert k['submitted'] == 45.0
    assert k['saturation_pressure_bar'] == pytest.approx(
        n2o_vapor_pressure_bar(293.15))
    assert 'Raise the tank pressure' in j['message']


@pytest.mark.parametrize('ad,govde,kod_beklenen,hata,neden', [
    ('lox_u20', dict(LOX, tank_pressure=20.0, **U), 422,
     'tank_pressure_not_above_chamber_pressure',
     'injector_pressure_drop_not_positive'),
    ('n2o_u_yok', {k: v for k, v in dict(H1, **U).items()
                   if k != 'tank_pressure'}, 422, 'tank_pressure_required',
     'required_for_user_tank_pressure_source'),
    ('kaynak_bilinmeyen', dict(H1, tank_pressure_source='regulated'), 422,
     'invalid_tank_pressure_source', 'unknown_value'),
    ('kaynak_liste', dict(H1, tank_pressure_source=['user']), 422,
     'invalid_tank_pressure_source', 'not_a_string'),
    ('lox_self', dict(LOX, tank_pressure_source='self_pressurised'), 422,
     'tank_pressure_source_not_applicable', 'not_applicable_to_oxidizer'),
    ('n2o_tasarim', dict(H1, tank_pressure_source='design_pressure_drop'), 422,
     'tank_pressure_source_not_applicable', 'not_applicable_to_oxidizer'),
])
def test_422_kapilari(ad, govde, kod_beklenen, hata, neden):
    kod, j = _calc(ad, govde)
    assert kod == kod_beklenen, j
    assert j['error'] == hata and j['status'] == 'invalid_input'
    assert j['invalid_fields'][0]['reason'] == neden


# ===========================================================================
# 5. Varsayılan kipler BİT-AYNI
# ===========================================================================
def test_n2o_acik_self_pressurised_beyansiz_istekle_bit_ayni():
    j0 = _ok('n2o_varsayilan', dict(H1))
    j1 = _ok('n2o_self', dict(H1, tank_pressure_source='self_pressurised'))
    j2 = _ok('n2o_default', dict(H1, tank_pressure_source='default'))
    assert _md5(j0) == _md5(j1) == _md5(j2)
    idd = j0['motor']['injector_design']
    assert idd['feed_pressure_source'] == 'n2o_saturation_at_tank_temperature'
    assert idd['feed_pressure_bar'] == pytest.approx(50.5433585, rel=1e-7)
    for alan in ('tank_pressure_source', 'inlet_state',
                 'feed_line_loss_included'):
        assert alan not in idd, alan
    assert j0['motor']['tank_blowdown']['status'] == 'modelled'


def test_lox_acik_design_pressure_drop_beyansiz_istekle_bit_ayni():
    j0 = _ok('lox_varsayilan', dict(LOX))
    j1 = _ok('lox_tasarim', dict(LOX, tank_pressure_source='design_pressure_drop'))
    assert _md5(j0) == _md5(j1)
    ox = j0['motor']['injector_design_detail']['ox_circuit']
    assert ox['dp_pc_ratio'] == pytest.approx(0.2)


def test_quick_geometry_ayni_kipi_cozer_ve_reddeder():
    kod, j = _post('/api/quick-geometry', dict(H1, tank_pressure=70.0, **U))
    assert kod == 200, j
    idd = j['motor']['injector_design']
    assert idd['feed_pressure_source'] == 'user_tank_pressure'
    assert idd['feed_pressure_bar'] == 70.0
    kod, j = _post('/api/quick-geometry', dict(H1, tank_pressure=45.0, **U))
    assert kod == 400
    assert j['invalid_fields'][0]['reason'] == 'below_n2o_saturation_pressure'


# ===========================================================================
# 6. Arayüz — şablon, sözlük, node DOM ikizi
# ===========================================================================
def _oku(yol):
    return yol.read_text(encoding='utf-8')


def test_secim_kutusu_tank_alanindan_once_ve_secenekler():
    metin = _oku(ADV_HTML)
    i_sec = metin.index('<select id="tank_pressure_source">')
    i_alan = metin.index('<input type="number" id="tank_pressure"')
    assert i_sec < i_alan, 'proje geri yüklemesi kipi önce kurmalı (DOM sırası)'
    blok = metin[i_sec:metin.index('</select>', i_sec)]
    assert re.findall(r'<option value="([^"]+)"', blok) == ['default', 'user']


YENI_ANAHTARLAR = (
    'adv.label.tankPressureSource', 'adv.tip.tankPressureSource',
    'adv.opt.tankPressureSourceSelf', 'adv.opt.tankPressureSourceDesignDp',
    'adv.opt.tankPressureSourceUser', 'adv.ph.tankPressureDesignDp',
    'adv.ph.tankPressureUserRequired', 'adv.js.tankPressureDesignDpNote',
    'adv.js.tankPressureUserNote', 'adv.js.tankPressureFeedUsedDesignDp',
    'adv.js.tankPressureFeedUsedUser')


def _sozluk_iki_dil(anahtar):
    bul = re.findall(r"^\s*'%s': '((?:[^'\\]|\\.)*)',\s*$" % re.escape(anahtar),
                     _oku(I18N_ADV), re.M)
    assert len(bul) == 2, (anahtar, len(bul))
    return [b.replace("\\'", "'") for b in bul]


@pytest.mark.parametrize('anahtar', YENI_ANAHTARLAR)
def test_yeni_anahtarlar_iki_dilde(anahtar):
    en, tr = _sozluk_iki_dil(anahtar)
    assert en and tr and en != tr
    assert sorted(re.findall(r'\{(\w+)\}', en)) == sorted(
        re.findall(r'\{(\w+)\}', tr))
    assert re.search(r'[çğıİöşüÇĞÖŞÜ]', tr), tr


_UI_ISLEVLERI = ('tankPressureMode', 'tankPressureIsSaturationDriven',
                 'updateTankPressureSourceOption', 'setTankPressureNote',
                 'applyTankPressureMode', 'clearTankPressureFeed',
                 'showTankPressureFeedFromResults', 'validateFormData')
_UI_SABITLERI = ('TANK_PRESSURE_N2O_FEED_SOURCE',
                 'TANK_PRESSURE_DESIGN_DP_FEED_SOURCE',
                 'TANK_PRESSURE_USER_FEED_SOURCE')

_UI_JS = r"""
'use strict';
const vm = require('vm');
const yedekler = {};
function el(id, value) {
    return { id: id, value: value, readOnly: false, required: false,
             dataset: {}, style: {}, attrs: {}, textContent: '',
             setAttribute(k, v) { this.attrs[k] = String(v); },
             getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
             removeAttribute(k) { delete this.attrs[k]; } };
}
const secenek = el('opt_default', 'default');
const els = { oxidizer_type: { value: 'n2o' },
              tank_pressure_source: Object.assign(el('tank_pressure_source', 'default'),
                  { querySelector: (q) => (q === 'option[value="default"]' ? secenek : null) }),
              tank_pressure: el('tank_pressure', '55'),
              tank_pressure_feed_note: el('tank_pressure_feed_note', ''),
              pressure_warning: { style: { display: 'none' } } };
const sb = { JSON, Math, String, Number, isFinite, Object,
    document: { getElementById: (id) => els[id] || null },
    validatePressures() {},
    i18nText(k, f) { yedekler[k] = f; return k; },
    i18nFmt(k, p, f) { yedekler[k] = f; return k + JSON.stringify(p || {}); } };
vm.createContext(sb);
vm.runInContext(JOB.kaynak, sb);
const tp = els.tank_pressure, not = els.tank_pressure_feed_note;
const kaynak = els.tank_pressure_source;
function durum() {
    return { readOnly: tp.readOnly, required: tp.required, value: tp.value,
             held: tp.dataset.heldValue === undefined ? null : tp.dataset.heldValue,
             ph: tp.getAttribute('data-i18n-placeholder'),
             aria: tp.getAttribute('aria-readonly'),
             not: not.getAttribute('data-i18n'),
             notParams: not.getAttribute('data-i18n-params'),
             secenek: secenek.getAttribute('data-i18n'), mod: sb.tankPressureMode() };
}
const sonuc = (s, k, dp) => ({ motor: { injector_design: {
    feed_pressure_bar: s, feed_pressure_source: k,
    injection_pressure_drop_bar: dp } } });
const out = {};
sb.applyTankPressureMode(); out.n2oVars = durum();
kaynak.value = 'user'; sb.clearTankPressureFeed(); out.n2oUser = durum();
sb.showTankPressureFeedFromResults(sonuc(55, 'user_tank_pressure', 35)); out.n2oUserSonuc = durum();
sb.showTankPressureFeedFromResults(sonuc(50.54, 'n2o_saturation_at_tank_temperature', 30.54));
out.n2oUserYanlisKaynak = durum();
kaynak.value = 'default'; sb.clearTankPressureFeed(); out.n2oGeri = durum();
els.oxidizer_type.value = 'lox'; sb.clearTankPressureFeed(); out.loxVars = durum();
sb.showTankPressureFeedFromResults(sonuc(24.0, 'chamber_pressure_plus_design_pressure_drop', 4.0));
out.loxVarsSonuc = durum();
sb.showTankPressureFeedFromResults(sonuc(24.0, 'n2o_saturation_at_tank_temperature', 4.0));
out.loxVarsYanlisKaynak = durum();
kaynak.value = 'user'; sb.clearTankPressureFeed(); out.loxUser = durum();
const tam = { motor_name: 'x', atmospheric_pressure: 1, of_ratio: 7.5,
              chamber_pressure: 20, thrust: 1000, burn_time: 10,
              fuel_type: 'htpb', injector_type: 'showerhead' };
out.formUserBos = sb.validateFormData(Object.assign(
    { oxidizer_type: 'n2o', tank_pressure_source: 'user' }, tam));
out.formUserDolu = sb.validateFormData(Object.assign(
    { oxidizer_type: 'n2o', tank_pressure_source: 'user', tank_pressure: 60 }, tam));
out.formLoxVars = sb.validateFormData(Object.assign({ oxidizer_type: 'lox' }, tam));
out.yedekler = yedekler;
process.stdout.write(JSON.stringify(out));
"""


def _sablon_islevi(metin, ad):
    i = metin.index('function %s(' % ad)
    j = metin.index('{', metin.index(')', i))
    derinlik = 0
    for k in range(j, len(metin)):
        if metin[k] == '{':
            derinlik += 1
        elif metin[k] == '}':
            derinlik -= 1
            if derinlik == 0:
                return metin[i:k + 1]
    raise AssertionError('işlev kapanmıyor: %s' % ad)


def _ui_kos():
    node = shutil.which('node')
    if node is None:
        pytest.skip('node kurulu değil')
    metin = _oku(ADV_HTML)
    kaynak = '\n'.join(_sablon_islevi(metin, ad) for ad in _UI_ISLEVLERI)
    for ad in _UI_SABITLERI:
        m = re.search(r"^\s*const %s = '([^']+)';" % ad, metin, re.M)
        assert m, ad
        kaynak = "const %s = '%s';\n" % (ad, m.group(1)) + kaynak
    girdi = 'const JOB = %s;\n' % json.dumps({'kaynak': kaynak}) + _UI_JS
    p = subprocess.run([node], input=girdi, capture_output=True, text=True,
                       timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


def test_arayuz_kipleri_dom_ikizi():
    o = _ui_kos()
    # N₂O varsayılan: salt-okur, sayı saklanır, P_sat notu, seçenek etiketi.
    a = o['n2oVars']
    assert (a['mod'], a['readOnly'], a['required'], a['value'], a['held'],
            a['ph'], a['not'], a['secenek']) == (
        'n2o_sat', True, False, '', '55', 'adv.ph.tankPressureN2oSat',
        'adv.js.tankPressureN2oNote', 'adv.opt.tankPressureSourceSelf')
    # Kullanıcı kipi: düzenlenebilir, ZORUNLU, saklanan sayı geri gelir.
    u = o['n2oUser']
    assert (u['mod'], u['readOnly'], u['required'], u['value'], u['held'],
            u['ph'], u['aria'], u['not']) == (
        'user', False, True, '55', None, 'adv.ph.tankPressureUserRequired',
        'false', 'adv.js.tankPressureUserNote')
    # Sonuç: kullanıcının sayısı alanda kalır, not P₁ ve ΔP'yi sunucudan basar.
    s = o['n2oUserSonuc']
    assert (s['value'], s['not'], s['readOnly']) == (
        '55', 'adv.js.tankPressureFeedUsedUser', False)
    assert json.loads(s['notParams']) == {'p': 55, 'dp': 35}
    # Sunucu başka kaynak yayımladıysa sayı UYDURULMAZ, kip notu kalır.
    y = o['n2oUserYanlisKaynak']
    assert (y['value'], y['not']) == ('55', 'adv.js.tankPressureUserNote')
    # Varsayılana dönüş: sayı yine saklanır.
    g = o['n2oGeri']
    assert (g['readOnly'], g['value'], g['held']) == (True, '', '55')
    # LOX varsayılan: tasarım ΔP kipi salt-okur; sunucunun P₁'i gösterilir.
    lv = o['loxVars']
    assert (lv['mod'], lv['readOnly'], lv['ph'], lv['not'], lv['secenek']) == (
        'design_dp', True, 'adv.ph.tankPressureDesignDp',
        'adv.js.tankPressureDesignDpNote', 'adv.opt.tankPressureSourceDesignDp')
    ls = o['loxVarsSonuc']
    assert (ls['value'], ls['not']) == ('24', 'adv.js.tankPressureFeedUsedDesignDp')
    assert json.loads(ls['notParams']) == {'p': 24}
    lx = o['loxVarsYanlisKaynak']
    assert (lx['value'], lx['not']) == ('', 'adv.js.tankPressureFeedNotPublished')
    lu = o['loxUser']
    assert (lu['readOnly'], lu['value'], lu['required']) == (False, '55', True)
    # Form doğrulaması: kullanıcı kipinde boş alan AÇIK hata; dolu ya da
    # varsayılan kipte tank basıncı hatası yok.
    assert [h for h in o['formUserBos'] if 'tank_pressure' in h], o['formUserBos']
    assert not [h for h in o['formUserDolu'] if 'tank_pressure' in h]
    assert not [h for h in o['formLoxVars'] if 'tank_pressure' in h]
    # JS yedek metinleri EN sözlüğüyle birebir.
    for anahtar in ('adv.js.tankPressureUserNote', 'adv.ph.tankPressureUserRequired',
                    'adv.js.tankPressureFeedUsedUser', 'adv.ph.tankPressureDesignDp',
                    'adv.js.tankPressureDesignDpNote',
                    'adv.js.tankPressureFeedUsedDesignDp',
                    'adv.opt.tankPressureSourceSelf',
                    'adv.opt.tankPressureSourceDesignDp'):
        en, _tr = _sozluk_iki_dil(anahtar)
        assert o['yedekler'][anahtar] == en, anahtar


def test_getformdata_kip_basina_govde():
    """Şablonun GERÇEK getFormData'sı (test_d36_hibrit_a1 düzeneği): N₂O
    varsayılan gövdesi bugünkü gibi (ne tank_pressure ne kaynak); kullanıcı
    kipinde ikisi birlikte gider. TERS MUTASYON BEKÇİSİ (form katmanı)."""
    from tests.test_d36_hibrit_a1 import NODE, _govde
    if NODE is None:
        pytest.skip('node kurulu değil')
    n2o = _govde(deger={'oxidizer_type': 'n2o', 'tank_pressure': 80})
    assert 'tank_pressure' not in n2o and 'tank_pressure_source' not in n2o
    n2o_u = _govde(deger={'oxidizer_type': 'n2o', 'tank_pressure': 62.5,
                          'tank_pressure_source': 'user'})
    assert n2o_u['tank_pressure'] == 62.5
    assert n2o_u['tank_pressure_source'] == 'user'
    h2o2 = _govde(deger={'oxidizer_type': 'h2o2', 'tank_pressure': 35})
    assert 'tank_pressure' not in h2o2
