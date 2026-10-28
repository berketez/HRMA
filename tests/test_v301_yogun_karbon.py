"""V301/B7 — hibrit termokimyasal dengeye yoğun faz katı karbon C(gr).

Kusur (ölçüldü 20 Eki, HRMA'nın kendi CEA karşılaştırması, 20 bar
N2O/HTPB): gri30 yalnız gaz fazı taşıdığı için yakıtça zengin uçta karbon
gaz türlerinde kalıyordu; O/F 2,0'da Δc* −%6,73, ΔT_c −%11,49; 2,5'te
−%4,64 / −%9,97. Düzeltme: gaz dengesi karbonca aşırı doymuşsa (ln a_C > 0,
NASA RP-1311 Part I eş. 3.7) denge gaz + C(gr) olarak çözülür; aksi hâlde
bugünkü yol BİT-AYNI kalır.

Kanıt paketi: docs/scofield/raw/OH/V301/makale1/B7/ (RAPOR.md, once.json,
sonra.json, mutasyon.json, saglamlik.json, ölçüm betikleri).

Bekçiler:
  * yakıtça zengin noktalarda NASA CEA'ya (RocketCEA, HRMA'nın kendi itici
    kartlarıyla) yakınlık — eşikler ölçülen en büyük sapmanın ~2 katı,
  * doymamış noktalarda (O/F ≥ 3,5 N2O/HTPB ε=4, LOX, PMMA, parafin, H2O2)
    yoğun yol kapatılmış çözümle BİREBİR eşitlik,
  * beyan alanları, kütle/element korunumu (gaz + katı), 0 ≤ ε < 1,
    karışım bağıntıları (R_mix = (1−ε)R_g, ρ = ρ_g/(1−ε)), kökte a_C = 1,
  * sağlamlık ızgarası (O/F 1,0–3,3; Pc 5–100 bar),
  * beyanlı düşüşler (çözülemezse 'condensed_carbon_unsolved', C(gr) verisi
    yoksa 'unavailable').
"""
import math
import warnings

import numpy as np
import pytest

warnings.filterwarnings('ignore', message=r'.*outside valid range.*')

ce = pytest.importorskip('cantera')

from hrma.engines import combustion_analysis as ca_mod  # noqa: E402
from hrma.engines.combustion_analysis import CombustionAnalyzer  # noqa: E402

HTPB = {'htpb': 100.0}

# Ölçülen en büyük |Δ%| (sonra.json, N2O/HTPB O/F 1,5–3,25, Pc 10/20/40,
# ε 4/15 + parafin/PE O/F 3): T_c 0,047; c* 0,022; Isp_vak 0,016; M 0,062;
# γ 0,125. Eşikler bunların ~2 katı (kaynaksız sabit değil, ölçüm bandı).
CEA_ESIK_PCT = {
    'chamber_temperature': 0.10,
    'c_star': 0.05,
    'isp_vacuum': 0.05,
    'chamber_molecular_weight': 0.15,
    'chamber_gamma': 0.25,
}
# Düzeltmeden ÖNCE aynı noktalarda (once.json, Pc 20 bar ε 4): O/F 2,0
# ΔT_c −11,49 / Δc* −6,73; O/F 2,5 −9,97 / −4,64; O/F 3,0 −2,42 / −1,92.
YAKITCA_ZENGIN = [(2.0, 20.0), (2.5, 20.0), (3.0, 20.0), (1.5, 10.0),
                  (2.5, 40.0)]
DOYMAMIS = [
    ('htpb', 'n2o', 3.5, 20.0), ('htpb', 'n2o', 6.0, 20.0),
    ('htpb', 'n2o', 8.0, 40.0), ('htpb', 'lox', 2.0, 20.0),
    ('pmma', 'n2o', 3.0, 20.0), ('paraffin', 'n2o', 5.0, 20.0),
    ('htpb', 'h2o2', 7.0, 20.0),
]
# Düzeltmeden ÖNCE ölçülen sayılar (once.json, taban a367de3d2, macOS;
# T_c [K], c* [m/s], Isp [s]). Platformlar arası Cantera farkına pay
# bırakmak için bağıl 1e-9; makine üstündeki birebir eşitlik
# ``test_doymamis_noktalar_yogun_yol_kapaliyla_birebir`` ile kilitli.
ONCE_CAPALARI = {
    ('htpb', 'n2o', 3.5, 20.0): (2447.267700260911, 1464.0440896601492,
                                 214.59338222956117),
    ('htpb', 'n2o', 6.0, 20.0): (3245.6920966427515, 1595.8688364555653,
                                 233.5066953419211),
    ('htpb', 'n2o', 8.0, 40.0): (3358.6191271901453, 1585.0656891019446,
                                 231.5102832943165),
    ('htpb', 'lox', 2.0, 20.0): (3457.9162592028233, 1789.905848870086,
                                 261.6380927329512),
    ('pmma', 'n2o', 3.0, 20.0): (2834.520222918904, 1483.7861441265404,
                                 216.98682990124507),
    ('paraffin', 'n2o', 5.0, 20.0): (2823.1859530544575, 1544.7401192887628,
                                     226.04076160936765),
    ('htpb', 'h2o2', 7.0, 20.0): (2925.4561678096193, 1642.874098101366,
                                  239.4670274047258),
}
EPS = 4.0


def _analiz(an, fu, ox, of, pc, eps=EPS):
    return an.analyze_combustion({fu: 100.0}, ox, of, pc, expansion_ratio=eps)


def _yapraklar(r):
    """Karşılaştırılan sayısal yapraklar (oda, boğaz, çıkış, performans)."""
    p = r['performance']
    out = [r['compositions'][k][a] for k in ('chamber', 'throat', 'exit')
           for a in ('temperature', 'density', 'molecular_weight', 'gamma',
                     'enthalpy', 'entropy', 'cp', 'cv')]
    out += [r['conditions'][k][a] for k in ('throat', 'exit')
            for a in ('P', 'T')]
    out += [p[k] for k in ('c_star', 'isp', 'cf', 'isp_frozen',
                           'isp_shifting', 'c_star_single_gamma',
                           'throat_sonic_residual')]
    return out


@pytest.fixture(scope='module')
def an():
    a = CombustionAnalyzer()
    if not a.cantera_available or a._yk is None:
        pytest.skip('Cantera gri30 + C(gr) termo verisi gerekli')
    return a


@pytest.fixture(scope='module')
def zengin(an):
    return _analiz(an, 'htpb', 'n2o', 2.5, 20.0)


# ---------------------------------------------------------------------------
# 1) CEA'ya yakınlık (yakıtça zengin uç)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('of,pc', YAKITCA_ZENGIN)
def test_yakitca_zengin_cea_ya_yakin(an, of, pc):
    pytest.importorskip('rocketcea')
    from hrma.analysis import cea_karsilastirma as ck
    r = _analiz(an, 'htpb', 'n2o', of, pc)
    assert r['condensed_phases']['status'] == 'present'
    mr = {'combustion_analysis': r, 'expansion_ratio': EPS,
          'oxidizer_inlet_state': an.oxidizer_inlet_state('n2o')}
    cmp = ck.build_hybrid_cea_comparison(mr, an)
    assert cmp['status'] == 'available', cmp.get('reason')
    satir = {s['quantity']: s for s in cmp['rows']}
    for ad, esik in CEA_ESIK_PCT.items():
        assert abs(satir[ad]['delta_pct']) < esik, (ad, satir[ad])


def test_cea_mw_satiri_yogun_fazda_tanim_esler(an, zengin):
    """CEA 1/totn = MW (eş. 2.4a) ⟷ HRMA M·(1 − x_c); künye bunu söyler."""
    pytest.importorskip('rocketcea')
    from hrma.analysis import cea_karsilastirma as ck
    mr = {'combustion_analysis': zengin, 'expansion_ratio': EPS,
          'oxidizer_inlet_state': an.oxidizer_inlet_state('n2o')}
    satir = {s['quantity']: s for s in
             ck.build_hybrid_cea_comparison(mr, an)['rows']}
    oda = zengin['compositions']['chamber']
    x_c = oda['condensed_species']['C(gr)']['mole_fraction']
    mw = satir['chamber_molecular_weight']
    assert mw['hrma'] == pytest.approx(oda['molecular_weight'] * (1 - x_c),
                                       rel=1e-14)
    assert 'eq. 2.4a' in mw['hrma_basis'] and 'eq. 2.4a' in mw['cea_basis']


# ---------------------------------------------------------------------------
# 2) Doymamış noktalarda bit-aynılık
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('fu,ox,of,pc', DOYMAMIS)
def test_doymamis_noktalar_yogun_yol_kapaliyla_birebir(an, monkeypatch,
                                                       fu, ox, of, pc):
    """Hiçbir durumda gaz aşırı doymamışsa yoğun kod HİÇ iz bırakmaz."""
    r = _analiz(CombustionAnalyzer(), fu, ox, of, pc)
    assert r['condensed_phases']['status'] == 'absent'
    kapali = CombustionAnalyzer()
    monkeypatch.setattr(kapali, '_gaz_karbon_asiri_doymus', lambda: False)
    r0 = _analiz(kapali, fu, ox, of, pc)
    assert _yapraklar(r) == _yapraklar(r0)


@pytest.mark.parametrize('anahtar', sorted(ONCE_CAPALARI))
def test_doymamis_noktalar_once_capasiyla_ayni(anahtar):
    fu, ox, of, pc = anahtar
    r = _analiz(CombustionAnalyzer(), fu, ox, of, pc)
    Tc, cs, isp = ONCE_CAPALARI[anahtar]
    assert r['compositions']['chamber']['temperature'] == pytest.approx(
        Tc, rel=1e-9)
    assert r['performance']['c_star'] == pytest.approx(cs, rel=1e-9)
    assert r['performance']['isp'] == pytest.approx(isp, rel=1e-9)


def test_doymamis_beyan_sayi_tasimaz(an):
    """'absent' beyanı yalnız metindir (sabit sayısal yaprak üretmez)."""
    b = _analiz(an, 'htpb', 'n2o', 6.0, 20.0)['condensed_phases']
    assert b['status'] == 'absent'
    assert all(isinstance(v, str) for v in b.values())


# ---------------------------------------------------------------------------
# 3) Beyan alanları + karışım bağıntıları
# ---------------------------------------------------------------------------
def test_beyan_alanlari(zengin):
    b = zengin['condensed_phases']
    assert b['status'] == 'present'
    assert b['species_admitted'] == 'C(gr)'
    assert b['stations_with_condensed_phase'] == ['chamber', 'throat', 'exit']
    for ist in ('chamber', 'throat', 'exit'):
        comp = zengin['compositions'][ist]
        eps = comp['condensed_mass_fraction']
        assert b['condensed_mass_fraction'][ist] == eps
        assert 0.0 < eps < 1.0
        assert comp['condensed_species']['C(gr)']['mass_fraction'] == eps
        assert 0.0 < comp['condensed_species']['C(gr)']['mole_fraction'] < 1.0
        assert 'RP-1311' in comp['phase_basis']
    assert zengin['conditions']['chamber']['temperature_source'] == \
        'equilibrium'
    assert zengin['conditions']['exit']['basis'] == \
        'expansion_ratio_equilibrium'
    assert zengin['performance']['c_star_basis'] == \
        'shifting_equilibrium_throat'


def test_karisim_bagintilari_R_ve_yogunluk(zengin):
    """R_mix = (1−ε)R_g (Sutton eş. 3-38), ρ = ρ_g/(1−ε) (RP-1311 §2.2)."""
    R_u = CombustionAnalyzer().R_universal
    for ist in ('chamber', 'throat', 'exit'):
        c = zengin['compositions'][ist]
        eps = c['condensed_mass_fraction']
        assert c['molecular_weight'] * (1.0 - eps) == pytest.approx(
            c['gas_molecular_weight'], rel=1e-13)
        assert c['density'] * (1.0 - eps) == pytest.approx(
            c['gas_density'], rel=1e-13)
        # Gaz yasası karışım tanımıyla: P = ρ (R_u/M) T  (ρ ve M karışım)
        P = c['pressure'] * 1e5
        assert P == pytest.approx(
            c['density'] * ce.gas_constant / c['molecular_weight']
            * c['temperature'], rel=1e-10)
    R_c = zengin['performance']['gas_constants']['chamber']
    assert R_c == pytest.approx(
        R_u / zengin['compositions']['chamber']['molecular_weight'], rel=1e-14)


def test_kokte_karbon_aktivitesi_bir(an, zengin):
    c = zengin['compositions']['chamber']
    el = zengin['elemental_composition']
    an.gas.TPY = c['temperature'], c['pressure'] * 1e5, \
        an._elements_to_cantera_composition(el)
    an.gas.equilibrate('TP')
    y_el = an._yk_element_kutle()
    d = an._yk_tp(c['temperature'], c['pressure'] * 1e5, y_el)
    assert abs(an._karbon_ln_aktivite()) < 1e-9
    assert d['eps'] == pytest.approx(c['condensed_mass_fraction'], rel=1e-9)


# ---------------------------------------------------------------------------
# 4) Kütle ve element korunumu (gaz + katı)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('of', [1.5, 2.5, 3.0])
def test_kutle_ve_element_korunumu(an, of):
    r = _analiz(an, 'htpb', 'n2o', of, 20.0)
    gaz = an.gas
    el_adlari = gaz.element_names
    toplam = np.array([r['elemental_composition'].get(e.upper(), 0.0)
                       for e in el_adlari], dtype=float)
    toplam /= toplam.sum()
    for ist in ('chamber', 'throat', 'exit'):
        c = r['compositions'][ist]
        eps = c['condensed_mass_fraction']
        y_el = np.zeros(len(el_adlari))
        y_top = 0.0
        for ad, v in c['species'].items():
            sp = gaz.species(ad)
            M = gaz.molecular_weights[gaz.species_index(ad)]
            y_top += v['mass_fraction']
            for j, e in enumerate(el_adlari):
                y_el[j] += (v['mass_fraction'] * sp.composition.get(e, 0.0)
                            * gaz.atomic_weight(e) / M)
        # gaz fazı kesirleri kendi içinde 1'e kapanır (1e-10 tabanı kadar)
        assert y_top == pytest.approx(1.0, abs=1e-8)
        karisim = (1.0 - eps) * y_el
        karisim[gaz.element_index('C')] += eps
        np.testing.assert_allclose(karisim, toplam, atol=2e-6)


# ---------------------------------------------------------------------------
# 5) Sağlamlık ızgarası
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('pc', [5.0, 20.0, 100.0])
def test_saglamlik_izgarasi(an, pc):
    for of in (1.0, 1.5, 2.0, 2.5, 3.0, 3.3):
        r = _analiz(an, 'htpb', 'n2o', of, pc)
        assert r['conditions']['chamber']['temperature_source'] == \
            'equilibrium', (of, pc)
        assert r['conditions']['throat']['basis'] == 'shifting_equilibrium'
        assert r['conditions']['exit']['basis'] == \
            'expansion_ratio_equilibrium', (of, pc)
        b = r['condensed_phases']
        assert b['status'] == 'present', (of, pc)
        for eps in b['condensed_mass_fraction'].values():
            assert 0.0 <= eps < 1.0
        p = r['performance']
        for k in ('c_star', 'isp', 'cf', 'chamber_gamma'):
            assert math.isfinite(p[k]) and p[k] > 0.0, (k, of, pc)
        assert p['isp_frozen_chamber'] <= p['isp_frozen'] <= p['isp'], (of, pc)


def test_tc_ve_cstar_o_f_ile_monoton_ve_surekli(an):
    """Yoğun sınırı (O/F ≈ 3,1–3,3) boyunca sıçrama yok."""
    ofs = [2.8, 2.9, 3.0, 3.1, 3.2, 3.25, 3.3, 3.4, 3.5]
    sonuc = [_analiz(an, 'htpb', 'n2o', of, 20.0) for of in ofs]
    Tc = [r['compositions']['chamber']['temperature'] for r in sonuc]
    cs = [r['performance']['c_star'] for r in sonuc]
    assert all(b > a for a, b in zip(Tc, Tc[1:]))
    assert all(b > a for a, b in zip(cs, cs[1:]))
    adim = [b / a - 1.0 for a, b in zip(cs, cs[1:])]
    assert max(adim) < 0.02


# ---------------------------------------------------------------------------
# 6) Beyanlı düşüşler (fail-closed)
# ---------------------------------------------------------------------------
def test_cozulemezse_ampirik_yol_adiyla(monkeypatch):
    a = CombustionAnalyzer()

    def patla(*_a, **_k):
        raise RuntimeError('zorlanmış başarısızlık')
    monkeypatch.setattr(a, '_yk_alev_sicakligi', patla)
    r = _analiz(a, 'htpb', 'n2o', 2.5, 20.0)
    ch = r['conditions']['chamber']
    assert ch['temperature_source'] == 'empirical_envelope'
    assert ch['warning']['params']['reason'] == 'condensed_carbon_unsolved'


def test_cgr_verisi_yoksa_unavailable_beyani():
    a = CombustionAnalyzer()
    a._yk, a._yk_neden = None, 'condensed_thermo_unavailable'
    r = _analiz(a, 'htpb', 'n2o', 2.5, 20.0)
    assert r['condensed_phases'] == {
        'status': 'unavailable', 'reason': 'condensed_thermo_unavailable',
        'species_admitted': 'C(gr)'}


def test_aktivite_esigi_tanim_geregi_sifir():
    assert ca_mod.CONDENSED_CARBON_LN_ACTIVITY_THRESHOLD == 0.0
    assert ca_mod.CONDENSED_CARBON_SPECIES == 'C(gr)'
