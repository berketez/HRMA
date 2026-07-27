"""Codex (gpt-5.6-sol) katı motor bulgularının kalıcı bekçileri.

Kaynak defter: docs/codex_bulgular_2026-07-19.md
Kapsanan bulgular (hepsi ÖNCE kodla doğrulandı, sonra düzeltildi):

  1) solid_rocket_engine.py:1735 — c* verimi iptali. self.c_star yanma
     verimiyle çarpılı olduğu için verim raporu kaybı kendi kendine
     sıfırlıyordu (eta=1.0 -> %99.77, eta=0.8 -> yine %99.77).
  2) solid_rocket_engine.py:3621 — yanma süresi ve impuls son adımı
     atlıyordu; trapez integrali son örnek ile gerçek tükeniş arasını
     dışarıda bırakıyordu (end-burner'da tam itkideki bir dt).
  3) solid_rocket_engine.py:3609 — 'convergence_achieved' sabit True.
  4) solid_rocket_engine.py:2825 — UI'daki 'composite' kasa malzemesi
     materials_db'de yok; get_material patlıyor, istisna yutuluyor ve
     sessizce çelik yoğunluğu (7800 kg/m3) kullanılıyordu.
  5) solid_rocket_engine.py:3871 — tasarım özeti cidarı SABİT 250 MPa /
     SF=3 ile yeniden hesaplıyor, _case_design() sonucuyla çelişiyordu.
  6) solid_rocket_engine.py:3741 — nozul yarı açıları hep 30/15 derece;
     formdaki açı girdileri geometriye hiç girmiyordu.

Ek olarak aynı aileden bir bulgu daha yakalandı ve düzeltildi: Monte Carlo
örneklemesi teslim edilen c*'ı örneklediği ve alt motor yanma verimini bir
kez daha uyguladığı için eta İKİ KEZ çarpılıyordu.
"""

import numpy as np
import pytest

from hrma.engines.solid_rocket_engine import (
    SOLID_COST_PARAMS,
    SolidRocketEngine,
)


# ---------------------------------------------------------------------------
# D-track sözleşmesi (v2.6.2): uyarılar artık düz metin değil,
# {code, params, severity} sözlüğü. Testler METİN yerine KOD sınar — bu hem
# dilden bağımsızdır hem de metin düzenlemeleri testi kırmaz.
# ---------------------------------------------------------------------------
def _codes(warnings):
    """Uyarı listesinden kod kümesi çıkarır (eski düz metin biçimini de kabul eder)."""
    out = set()
    for w in warnings or []:
        if isinstance(w, dict) and w.get('code'):
            out.add(w['code'])
        elif isinstance(w, str):
            out.add(w)
    return out


def _params_of(warnings, code):
    """Belirli bir kodun parametre sözlüğünü döndürür (yoksa boş sözlük)."""
    for w in warnings or []:
        if isinstance(w, dict) and w.get('code') == code:
            return w.get('params') or {}
    return {}


def _engine(grain_type='bates', **overrides):
    return SolidRocketEngine(
        grain_type=grain_type,
        propellant_type='apcp',
        chamber_diameter=100,
        grain_length=500,
        core_diameter=30,
        chamber_pressure=40,
        overrides=(overrides or None),
    )


# ---------------------------------------------------------------------------
# (a) Bulgu 1 — yanma verimi kayıp dökümünde GÖRÜNÜR
# ---------------------------------------------------------------------------

def test_combustion_efficiency_shows_up_in_loss_breakdown():
    """eta_c* = 0.8 girildiğinde yanma kaybı ~%20 raporlanmalı."""
    res = _engine(combustion_efficiency=0.8).calculate_performance()
    metrics = res['detailed_analysis']['performance_metrics']
    losses = metrics['theoretical_vs_actual_isp']

    assert losses['combustion_losses'] == pytest.approx(20.0, abs=1.0), (
        "Yanma verimi kayıp dökümünde görünmüyor — c* verimi teslim edilen "
        "c*'a bölünüyor olabilir (Codex bulgusu, satır ~1735).")
    assert metrics['c_star_efficiency_percent'] == pytest.approx(80.0, abs=1.0)


def test_combustion_efficiency_is_monotonic():
    """Verim düştükçe raporlanan c* verimi de düşmeli (sabit kalmamalı)."""
    effs = (1.0, 0.9, 0.8, 0.7)
    reported = []
    for eta in effs:
        res = _engine(combustion_efficiency=eta).calculate_performance()
        reported.append(
            res['detailed_analysis']['performance_metrics'][
                'c_star_efficiency_percent'])
    assert all(a > b for a, b in zip(reported, reported[1:])), (
        f"c* verimi girdiye duyarsız: {reported}")
    # Girilen verimle raporlanan verim aynı büyüklükte olmalı
    for eta, got in zip(effs, reported):
        assert got == pytest.approx(100.0 * eta, abs=1.5)


def test_theoretical_isp_stays_lossless():
    """'Teorik Isp' kayıpsız referanstır; yanma verimi onu DÜŞÜRMEZ.

    Aksi hâlde kayıp iki kez sayılırdı: hem teorik referans düşer hem
    combustion_losses kalemi aynı kaybı raporlar.
    """
    ideal = _engine().calculate_performance()
    lossy = _engine(combustion_efficiency=0.8).calculate_performance()

    isp_ideal = ideal['detailed_analysis']['performance_metrics'][
        'theoretical_vs_actual_isp']['theoretical_isp']
    isp_lossy = lossy['detailed_analysis']['performance_metrics'][
        'theoretical_vs_actual_isp']['theoretical_isp']
    assert isp_lossy == pytest.approx(isp_ideal, rel=1e-9)

    # Gerçek Isp ise düşer ve oran girilen verimle tutarlıdır
    assert lossy['isp_sea_level'] < ideal['isp_sea_level']
    assert (lossy['isp_sea_level'] / isp_lossy) == pytest.approx(0.8, abs=0.05)


def test_monte_carlo_does_not_double_apply_efficiency():
    """MC ortalaması nominalin etrafında olmalı, eta kadar altında değil."""
    eng = _engine(combustion_efficiency=0.8)
    nominal = eng.calculate_performance()
    mc = eng.run_monte_carlo(n_samples=40, seed=1)
    assert mc['thrust']['mean'] == pytest.approx(
        nominal['average_thrust'], rel=0.05), (
        "MC ortalaması nominalden kopuk — teslim edilen c* örneklenip "
        "yanma verimi ikinci kez uygulanıyor olabilir.")
    assert mc['isp']['mean'] == pytest.approx(
        nominal['specific_impulse'], rel=0.05)


# ---------------------------------------------------------------------------
# (b) Bulgu 2 — son adım atlanmıyor; impuls/süre dt'den bağımsız
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('grain_type', ['bates', 'end_burner', 'finocyl'])
def test_impulse_and_burn_time_converge_in_dt(grain_type):
    """Kaba ve ince dt aynı impuls/süreyi vermeli (son aralık kapanmalı)."""
    eng = _engine(grain_type)
    coarse = eng.calculate_thrust_curve(dt=0.05)
    fine = eng.calculate_thrust_curve(dt=0.002)

    imp_coarse = float(np.trapz(coarse['thrust'], coarse['time']))
    imp_fine = float(np.trapz(fine['thrust'], fine['time']))
    t_coarse = float(coarse['time'][-1])
    t_fine = float(fine['time'][-1])

    assert imp_coarse == pytest.approx(imp_fine, rel=0.01), (
        f"{grain_type}: toplam impuls dt'ye bağımlı "
        f"({imp_coarse:.1f} vs {imp_fine:.1f}) — son integrasyon aralığı "
        "atlanıyor olabilir.")
    assert t_coarse == pytest.approx(t_fine, rel=0.01), (
        f"{grain_type}: yanma süresi dt'ye bağımlı "
        f"({t_coarse:.4f} vs {t_fine:.4f}).")


def test_end_burner_impulse_is_dt_independent():
    """Nötr (sabit alanlı) end-burner'da kapanış sonrası dt etkisi ~sıfır.

    Bu, bulgunun en keskin hâliydi: son örnek TAM itkideydi, yani atlanan
    aralık bir tam dt'lik itkiydi.
    """
    eng = _engine('end_burner')
    imps = []
    for dt in (0.05, 0.01, 0.002):
        c = eng.calculate_thrust_curve(dt=dt)
        imps.append(float(np.trapz(c['thrust'], c['time'])))
    assert max(imps) - min(imps) <= 1e-3 * max(imps)


@pytest.mark.parametrize('grain_type',
                         ['bates', 'end_burner', 'star', 'finocyl',
                          'slotted', 'wagon_wheel'])
def test_mass_conservation_after_burnout_closure(grain_type):
    """Kapanış kütle korunumunu bozmamalı: ∫mdot dt ≈ geometrik yakıt kütlesi."""
    eng = _engine(grain_type)
    curve = eng.calculate_thrust_curve(dt=0.002)
    m_integral = float(np.trapz(curve['mass_flow'], curve['time']))
    m_geometric = eng._propellant_volume() * eng.rho_p
    assert m_integral == pytest.approx(m_geometric, rel=0.02), (
        f"{grain_type}: kütle korunumu bozuldu "
        f"({m_integral:.4f} vs {m_geometric:.4f} kg).")


def test_burnout_closure_never_exceeds_one_step():
    """Kapanış en fazla bir zaman adımı ekleyebilir (uydurma kuyruk yok)."""
    for grain_type in ('bates', 'end_burner', 'finocyl'):
        eng = _engine(grain_type)
        dt = 0.01
        curve = eng.calculate_thrust_curve(dt=dt)
        t = np.asarray(curve['time'], dtype=float)
        assert np.all(np.diff(t) > 0), f"{grain_type}: zaman monoton değil"
        assert float(np.max(np.diff(t))) <= dt * (1.0 + 1e-9), (
            f"{grain_type}: kapanış bir adımdan uzun bir aralık üretti.")


# ---------------------------------------------------------------------------
# (c) Bulgu 3 — gerçek yakınsama bayrağı + kullanıcıya görünür uyarı
# ---------------------------------------------------------------------------

def test_convergence_flag_true_on_well_posed_case():
    """n = 0.35 gibi sağlam bir üste bayrak True kalmalı (uyarı gürültüsü yok)."""
    eng = _engine()
    curve = eng.calculate_thrust_curve(dt=0.01)
    assert curve['convergence_achieved'] is True
    assert curve['pressure_solver_failed_steps'] == 0
    codes = _codes(eng.calculate_performance()['warnings'])
    assert 'warn.solid.pressure_solver_not_converged' not in codes


def test_convergence_flag_false_when_solver_fails():
    """n = 0.9'da sabit-nokta zayıflar; bayrak artık dürüst olmalı."""
    eng = SolidRocketEngine(
        grain_type='bates', propellant_type='apcp', chamber_diameter=100,
        grain_length=500, core_diameter=30, chamber_pressure=40,
        burn_rate_a=0.005, burn_rate_n=0.9)
    curve = eng.calculate_thrust_curve(dt=0.01)
    assert curve['convergence_achieved'] is False, (
        "Yakınsamayan basınç çözümü hâlâ 'başarılı' diye dönüyor "
        "(Codex bulgusu, satır ~3609).")
    assert curve['pressure_solver_failed_steps'] > 0
    assert curve['pressure_solver_max_residual'] > curve[
        'pressure_solver_tolerance']

    warns = eng.calculate_performance()['warnings']
    assert 'warn.solid.pressure_solver_not_converged' in _codes(warns), (
        "Yakınsamama kullanıcıya görünen uyarıya dönüşmüyor.")
    # Tanı sayıları uyarının içinde taşınmalı; yoksa kullanıcı ne kadar
    # adımın kaçtığını göremez.
    p = _params_of(warns, 'warn.solid.pressure_solver_not_converged')
    assert p.get('failed_steps', 0) > 0
    assert p.get('max_residual', 0) > p.get('tolerance', 0)


def test_exponent_ge_one_is_flagged():
    """n >= 1 sabit-nokta daralması varsayımını bozar; açıkça söylenmeli."""
    eng = SolidRocketEngine(
        grain_type='bates', propellant_type='apcp', chamber_diameter=100,
        grain_length=500, core_diameter=30, chamber_pressure=40,
        burn_rate_a=0.005, burn_rate_n=1.0)
    warns = eng.calculate_performance()['warnings']
    assert 'warn.solid.burn_rate_exponent_ge_one' in _codes(warns)
    assert _params_of(warns, 'warn.solid.burn_rate_exponent_ge_one')['n'] == 1.0


def test_solver_diagnostics_reach_the_result_payload():
    """Çözücü sağlığı sonuç sözlüğünde raporlanır (sessiz başarı yok)."""
    res = _engine().calculate_performance()
    diag = res['solver_diagnostics']
    assert diag['convergence_achieved'] is True
    assert diag['pressure_solver_steps'] > 0
    assert diag['termination_reason'] in (
        'web_exhausted', 'burn_area_vanished', 'pressure_collapse',
        'burn_rate_zero', 'safety_limit')


# ---------------------------------------------------------------------------
# (d) Bulgu 4 — kompozit kasa sessizce çelik OLMAZ
# ---------------------------------------------------------------------------

def test_composite_case_is_not_silently_steel():
    """UI'daki 'composite' seçimi çelik yoğunluğu kullanamaz."""
    steel = _engine(case_material='steel')
    composite = _engine(case_material='composite')

    rho_composite = composite._case_density()
    rho_steel = steel._case_density()
    assert rho_composite < 0.5 * rho_steel, (
        f"Kompozit kasa çelik yoğunluğunda ({rho_composite:.0f} kg/m3) — "
        "get_material sessizce çeliğe düşüyor olabilir.")
    # Yoğunluk projenin TEK tanım noktasıyla (maliyet tablosu) tutarlı
    assert rho_composite == pytest.approx(
        SOLID_COST_PARAMS['case_materials']['composite'][0])
    assert composite._calculate_dry_mass() < steel._calculate_dry_mass()


def test_composite_case_warns_about_generic_allowable():
    """Jenerik kompozit izin verilen gerilmesi kullanıcıya beyan edilmeli."""
    res = _engine(case_material='composite').calculate_performance()
    assert 'warn.solid.case_generic_allowable' in _codes(res['warnings'])


def test_composite_with_explicit_yield_strength_has_no_warning():
    """Kullanıcı ölçülen dayanımı girdiyse jenerik uyarısı düşer."""
    res = _engine(case_material='composite',
                  yield_strength=650).calculate_performance()
    assert 'warn.solid.case_generic_allowable' not in _codes(res['warnings'])


def test_unknown_case_material_raises_instead_of_falling_back():
    """Bilinmeyen malzeme sessiz çeliğe düşmez, açık hata verir."""
    with pytest.raises(ValueError, match='Unsupported case material'):
        _engine(case_material='unobtanium')


@pytest.mark.parametrize('material', ['steel', 'aluminum', 'composite',
                                      'titanium'])
def test_every_ui_case_material_resolves(material):
    """solid.html'deki dört seçenek de gerçek bir malzeme kaydına çözülmeli."""
    eng = _engine(case_material=material)
    props = eng._case_material_properties(material)
    assert props['density'] > 0 and props['yield_strength'] > 0
    assert eng._case_density() == pytest.approx(props['density'])


# ---------------------------------------------------------------------------
# (e) Bulgu 6 — girilen nozul açıları geometriyi belirler ve rapora uyar
# ---------------------------------------------------------------------------

def test_entered_nozzle_angles_drive_geometry():
    """Açı değişince yakınsak/ıraksak uzunluklar değişmeli."""
    base = _engine().calculate_performance()['nozzle_angles']
    steep = _engine(convergent_angle=45.0,
                    divergent_angle=12.0).calculate_performance()[
                        'nozzle_angles']

    assert steep['convergent_length_mm'] != pytest.approx(
        base['convergent_length_mm'], rel=1e-6), (
        "Yakınsak uzunluk girilen açıya duyarsız (Codex bulgusu, ~3741).")
    assert steep['divergent_length_mm'] != pytest.approx(
        base['divergent_length_mm'], rel=1e-6)
    # 45 derece daha dik yakınsak -> daha KISA; 12 derece daha sığ ıraksak
    # -> daha UZUN
    assert steep['convergent_length_mm'] < base['convergent_length_mm']
    assert steep['divergent_length_mm'] > base['divergent_length_mm']


def test_reported_nozzle_angles_match_the_ones_used():
    """Raporlanan açı, uzunluğu üreten açıyla AYNI olmalı."""
    conv_deg, div_deg = 22.0, 18.0
    res = _engine(convergent_angle=conv_deg,
                  divergent_angle=div_deg).calculate_performance()
    na = res['nozzle_angles']
    assert na['convergent_half_angle_deg'] == pytest.approx(conv_deg)
    assert na['divergent_half_angle_deg'] == pytest.approx(div_deg)
    assert na['angles_source'] == 'user_input'

    d_t = na['throat_diameter_mm'] / 1000.0
    d_e = na['exit_diameter_mm'] / 1000.0
    expected_conv = ((res['chamber_diameter'] / 1000.0 - d_t)
                     / (2 * np.tan(np.radians(conv_deg))))
    expected_div = (d_e - d_t) / (2 * np.tan(np.radians(div_deg)))
    assert na['convergent_length_mm'] == pytest.approx(
        expected_conv * 1000.0, rel=1e-9)
    assert na['divergent_length_mm'] == pytest.approx(
        expected_div * 1000.0, rel=1e-9)


def test_default_nozzle_angles_are_declared():
    """Açı girilmediğinde varsayılan kullanıldığı açıkça etiketlenir."""
    na = _engine().calculate_performance()['nozzle_angles']
    assert na['angles_source'] == 'conical_default_30_15'
    assert na['convergent_half_angle_deg'] == pytest.approx(30.0)
    assert na['divergent_half_angle_deg'] == pytest.approx(15.0)


def test_nozzle_length_helper_uses_entered_angles():
    """CAD/3D yolunda kullanılan _calculate_nozzle_length de açıları okur."""
    base = _engine()._calculate_nozzle_length()
    shallow = _engine(divergent_angle=10.0)._calculate_nozzle_length()
    assert shallow > base


# ---------------------------------------------------------------------------
# (f) Bulgu 5 — tasarım özeti cidarı yapısal analizle AYNI
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('overrides', [
    {},
    {'case_thickness': 8.0},
    {'case_material': 'aluminum'},
    {'yield_strength': 500.0, 'safety_factor': 1.5},
    {'case_material': 'composite', 'yield_strength': 650.0},
])
def test_summary_thickness_matches_case_design(overrides):
    """Özet tablo cidarı _case_design() ile birebir aynı olmalı."""
    eng = _engine(**overrides)
    _material, _sigma_y, _sf, t_wall = eng._case_design()
    res = eng.calculate_performance()

    summary_t = res['design_summary']['key_dimensions']['wall_thickness_mm']
    assert summary_t == pytest.approx(t_wall * 1000.0, rel=1e-9), (
        f"{overrides}: özet {summary_t:.3f} mm, yapısal kaynak "
        f"{t_wall * 1000.0:.3f} mm — iki farklı cidar raporlanıyor "
        "(Codex bulgusu, ~3871).")


def test_entered_case_thickness_survives_into_the_summary():
    """Girilen 8 mm özet tabloda da 8 mm görünmeli."""
    res = _engine(case_thickness=8.0).calculate_performance()
    dims = res['design_summary']['key_dimensions']
    case = res['design_summary']['case_design']
    assert dims['wall_thickness_mm'] == pytest.approx(8.0, rel=1e-9)
    assert case['thickness_source'] == 'user_entered'
    # Dış çap da aynı cidardan türer
    assert dims['motor_outer_diameter_mm'] == pytest.approx(
        res['chamber_diameter'] + 2 * 8.0, rel=1e-9)


def test_summary_declares_material_and_strength():
    """Özet, cidarı hangi malzeme/dayanım/SF ile ürettiğini beyan eder."""
    res = _engine(case_material='aluminum',
                  safety_factor=2.0).calculate_performance()
    case = res['design_summary']['case_design']
    assert case['material'] == 'aluminum'
    assert case['design_safety_factor'] == pytest.approx(2.0)
    assert case['yield_strength_mpa'] > 0
