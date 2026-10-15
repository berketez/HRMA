"""ÖH Dalga-23 / hibrit a1 — bekçiler.

Kapsanan kalemler:

* **P15B1-04** (D22 DEVİR, kalan yarı) — ``nozzle_design`` diverjans
  çarpanı λ'yı **yalnız momentum itkisine** uygular (Sutton & Biblarz
  9. baskı Eş. 3-34); basınç-itki terimi ölçeklenmez. Manşet ile lüle
  panelinin C_F'i artık kayan nokta tabanında aynıdır.
* **OH-D21-08** — ``mdot_f = N·rho_f·π·D·L·r_dot`` TEK TANIM NOKTASINDAN;
  geçici balistik port sayısını taşır.
* **OH-D22-01** — hibrit ``/calculate`` L* üst kapısı sıvı literatür
  bandını değil modelin KENDİ kelepçesini okur; üst tarafta da dürüst not.
* **P9B2-24** (D22 DEVİR, kısmen) — yayımlanan boy ⟷ ihraç boyu: yakınsak
  koni ayağı kapalı kalır (kapanan yarıyı KİLİTLER).
"""
import ast
import contextlib
import io
import os

import numpy as np
import pytest


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AT, PC, GAMMA, R_S, T_C = 0.001, 30.0, 1.20, 350.0, 3400.0


@pytest.fixture(scope='module')
def designer():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.engines.nozzle_design import NozzleDesigner
    return NozzleDesigner()


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


HIBRIT = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
          'chamber_pressure': 20.0, 'fuel_type': 'htpb',
          'oxidizer_type': 'n2o'}


# --------------------------------------------------------------- P15B1-04
class TestP15B1_04LambdaUygulamaYeri:
    """λ basınç-itki terimini de kırpıyordu (ölçülen −%0,0458 … +%0,5793)."""

    @pytest.mark.parametrize('eps', (4.0, 6.5, 12.0, 40.0, 100.0))
    def test_lambda_yalniz_momentum_terimine(self, designer, eps):
        p = _sessiz(designer.design_nozzle, AT, eps, PC, 1.01325, 'conical',
                    gamma=GAMMA, R_specific=R_S, T_chamber=T_C)['performance']
        lam = p['divergence_efficiency']
        # Momentum tabanı: ayrılmış bantta ayrılma istasyonununki. Yayımlanan
        # özdeşlik v_e = CF_mom_basis · c* iki bantta da bunu verir.
        cf_mom_basis = p['exit_velocity'] / p['characteristic_velocity']
        cf_bas = p['thrust_coefficient_ideal'] - cf_mom_basis
        eta_hiz = (p['friction_efficiency'] * p['two_phase_efficiency']
                   * p['kinetic_efficiency'])
        beklenen = (lam * cf_mom_basis + cf_bas) * eta_hiz
        assert p['thrust_coefficient_actual'] == pytest.approx(
            beklenen, rel=1e-12), (
            'λ Sutton Eş. 3-34 dışında uygulanıyor')
        # Basınç-itki terimi ayrıca YAYIMLANIR (beyan okunabilir olmalı).
        assert p['thrust_coefficient_pressure_thrust'] == pytest.approx(
            cf_bas, rel=1e-12)

    @pytest.mark.parametrize('eps', (4.0, 12.0, 100.0))
    def test_eski_tam_katsayi_carpimi_artik_gecerli_degil(self, designer, eps):
        """Ters yön: cf_actual = cf_ideal · eta_nozzle ARTIK DOĞRU DEĞİL.

        Basınç-itki terimi sıfır olmadığı sürece iki sayı ayrışır; bu, λ'nın
        yerinin gerçekten değiştiğini gösteren farktır.
        """
        p = _sessiz(designer.design_nozzle, AT, eps, PC, 1.01325, 'conical',
                    gamma=GAMMA, R_specific=R_S, T_chamber=T_C)['performance']
        eski = p['thrust_coefficient_ideal'] * p['nozzle_efficiency']
        assert abs(p['thrust_coefficient_pressure_thrust']) > 1e-6
        assert abs(p['thrust_coefficient_actual'] / eski - 1.0) > 1e-6

    def test_nozzle_efficiency_hala_dort_carpanin_carpimi(self, designer):
        """Yayımlanan verim alanının SÖZLEŞMESİ değişmedi (D20 bekçisi)."""
        p = _sessiz(designer.design_nozzle, AT, 12.0, PC, 1.01325, 'conical',
                    gamma=GAMMA, R_specific=R_S, T_chamber=T_C)['performance']
        assert p['nozzle_efficiency'] == pytest.approx(
            p['divergence_efficiency'] * p['friction_efficiency']
            * p['two_phase_efficiency'] * p['kinetic_efficiency'], rel=1e-12)
        # Ama C_F'e FİİLEN inen oran artık ayrı bir alandır ve farklıdır.
        assert p['thrust_coefficient_efficiency_effective'] == pytest.approx(
            p['thrust_coefficient_actual'] / p['thrust_coefficient_ideal'],
            rel=1e-12)
        assert 'Eq. 3-34' in p['nozzle_efficiency_application']

    def test_legacy_tek_faktor_yeri_degismedi(self, designer):
        """efficiency=<sayı> geçilince eski uygulama noktası korunur."""
        p = _sessiz(designer.design_nozzle, AT, 12.0, PC, 1.01325, 'conical',
                    efficiency=0.95, gamma=GAMMA, R_specific=R_S,
                    T_chamber=T_C)['performance']
        assert p['thrust_coefficient_actual'] == pytest.approx(
            p['thrust_coefficient_ideal'] * 0.95, rel=1e-12)
        assert 'legacy single-factor' in p['nozzle_efficiency_application']

    def test_adapte_genlesmede_iki_yol_ayni(self, designer):
        """Basınç-itki terimi sıfırken uygulama yerinin etkisi de sıfırdır."""
        from hrma.engines.nozzle_design import NozzleDesigner
        eps = 12.0
        p_e = NozzleDesigner.exit_pressure_from_expansion(eps, GAMMA, PC)
        p = _sessiz(designer.design_nozzle, AT, eps, PC, p_e, 'conical',
                    gamma=GAMMA, R_specific=R_S, T_chamber=T_C)['performance']
        assert p['thrust_coefficient_pressure_thrust'] == pytest.approx(
            0.0, abs=1e-12)
        assert p['thrust_coefficient_actual'] == pytest.approx(
            p['thrust_coefficient_ideal'] * p['nozzle_efficiency'], rel=1e-12)

    @pytest.mark.parametrize('eps', (6.5, 12.0, 40.0))
    def test_manset_ile_panel_kayan_nokta_tabaninda_ayni(self, eps):
        """Kalemin ÖZÜ: aynı lülenin iki C_F'i artık tek sayıdır."""
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        m = HybridRocketEngine(thrust=3000, chamber_pressure=30,
                               of_ratio=6.0, expansion_ratio=eps)
        _sessiz(m.calculate)
        cc = m.thrust_coefficient_cross_check
        assert abs(cc['relative_gap_percent']) < 1e-10, cc
        assert cc['status'] == 'pass'
        assert cc['remaining_causes'] == []
        # Kapanan kök künyede KAYITLI kalır ama "kalan" diye yayımlanmaz.
        assert any('Eq. 3-34' in c for c in cc['closed_causes'])
        assert not any('Eq. 3-34' in c for c in cc['remaining_causes'])


# --------------------------------------------------------------- OH-D21-08
class TestOHD2108TekMdotF:
    """mdot_f yedi kopyanın son üçü; geçici seri port sayısını taşımıyordu."""

    DOSYALAR = ('hrma/engines/hybrid_rocket_engine.py',
                'hrma/analysis/transient_ballistics.py',
                'hrma/analysis/regression_analysis.py')

    @pytest.mark.parametrize('yol', DOSYALAR)
    def test_elle_yazilmis_yanma_yuzeyi_carpimi_kalmadi(self, yol):
        src = open(os.path.join(KOK, yol), encoding='utf-8').read()
        agac = ast.parse(src)
        kalan = []
        for d in ast.walk(agac):
            if not isinstance(d, ast.BinOp):
                continue
            duz = ' '.join((ast.get_source_segment(src, d) or '').split())
            if ('np.pi' in duz and 'rho_f' in duz and 'L_grain' in duz
                    and ('r_dot' in duz or 'r_dot_final' in duz)):
                kalan.append(duz[:120])
        assert kalan == [], f'{yol}: elle yazılmış mdot_f kopyası: {kalan}'

    def test_tek_tanim_noktasi_cagriliyor(self):
        for yol in ('hrma/engines/hybrid_rocket_engine.py',
                    'hrma/analysis/transient_ballistics.py'):
            src = open(os.path.join(KOK, yol), encoding='utf-8').read()
            assert 'fuel_mass_flow_kg_s(' in src, yol

    def test_gecici_seri_port_sayisini_tasir(self):
        """7 portlu motorda geçici seri t=0 debisi tasarım noktasıyla aynı.

        ÖLÇÜLDÜ (once.json): 0,0772868 ⟷ 0,1837274 kg/s = 2,3772×.
        """
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
            from hrma.analysis.transient_ballistics import TransientBallistics
        m = HybridRocketEngine(thrust=3000, chamber_pressure=30, of_ratio=6.0,
                               expansion_ratio=6.5, port_count=7)
        _sessiz(m.calculate)
        sol = _sessiz(TransientBallistics(m, feed_mode='regulated',
                                          n_steps=60).solve)
        assert float(sol['mdot_fuel'][0]) == pytest.approx(
            float(m.mdot_f), rel=1e-9)

    def test_ters_form_fail_closed(self):
        from hrma.analysis.regression_analysis import (
            fuel_mass_flow_kg_s, grain_length_for_fuel_mass_flow_m)
        # ileri/geri özdeşlik
        L = grain_length_for_fuel_mass_flow_m(0.2, 950.0, 0.05, 1e-3,
                                              port_count=7)
        assert fuel_mass_flow_kg_s(950.0, 0.05, L, 1e-3,
                                   port_count=7) == pytest.approx(0.2,
                                                                  rel=1e-12)
        with pytest.raises(ValueError, match='burning-surface'):
            grain_length_for_fuel_mass_flow_m(0.2, 950.0, 0.05, 0.0)


# --------------------------------------------------------------- OH-D22-01
class TestOHD2201LStarTavani:
    """Üst kapı SIVI literatür bandını hibrit uca uyguluyordu."""

    def test_cift_bandi_genel_bandi_ASLA_genisletmez(self):
        """Kalemin İDDİA ETTİĞİ mekanizma ölçümle çürük: çift bandına
        bağlamak kapıyı yalnız DARALTIR."""
        from hrma.constants import L_STAR_GENERIC_BAND_M
        from hrma.engines.liquid_rocket_engine import (
            L_STAR_BY_PAIR_M, l_star_band_for_pair)
        assert max(b[1] for b in L_STAR_BY_PAIR_M.values()) < \
            L_STAR_GENERIC_BAND_M[1]
        # Hibrit çifti tabloda YOK: bağlantı hibrit uçta zaten no-op olurdu.
        assert l_star_band_for_pair('htpb', 'n2o')[2] == \
            'sp125_table_4_1_generic'

    @pytest.mark.parametrize('deger', (4.0, 6.0))
    def test_modelin_kurabildigi_l_star_kesilmez(self, client, deger):
        """ÖLÇÜLDÜ: 3,05 m üstü 422 iken aynı koşu 3,5438 m L* kuruyordu."""
        r = client.post('/calculate', json=dict(HIBRIT, l_star=deger))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        m = r.get_json()['motor']
        assert m['l_star_achieved'] == pytest.approx(deger, rel=0.15)
        assert m['l_star_clamped_high'] is False

    @pytest.mark.parametrize('deger', (1e3, 1e9))
    def test_kurulamayan_l_star_hala_reddedilir(self, client, deger):
        r = client.post('/calculate', json=dict(HIBRIT, l_star=deger))
        assert r.status_code == 422
        k = r.get_json()['invalid_fields'][0]
        assert k['field'] == 'l_star'
        assert k['reason'] == 'above_model_ceiling'
        assert k['achieved'] and float(k['achieved']) > 0.0
        # Ret gerekçesi bu koşunun KENDİ geometrisidir, literatür bandı değil.
        assert 'literature band' in k['message']
        assert '3.05' not in k['message']

    def test_ust_tarafta_da_not_yazilir(self):
        """P16B1-19'un özü: kırpma iki yönde de olur, not iki yönde de yazılır."""
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        m = HybridRocketEngine(thrust=1000, chamber_pressure=20, of_ratio=6.0,
                               l_star=1e3)
        _sessiz(m.calculate)
        assert m.l_star_clamped_high is True
        assert 'NOT applied' in m.l_star_note

    def test_bos_not_ile_200_yayimlanmiyor(self, client):
        """D22 bekçisinin amacı korunur: 200 dönen hiçbir gövdede 'yankı var,
        not yok' hâli kalmaz."""
        for deger in (1e-6, 1.0, 3.05, 4.0, 6.0):
            r = client.post('/calculate', json=dict(HIBRIT, l_star=deger))
            assert r.status_code == 200
            m = r.get_json()['motor']
            if abs(float(m['l_star']) - float(m['l_star_achieved'])) > 1e-9:
                assert m['l_star_note'].strip() != '', deger


# --------------------------------------------------------------- P9B2-24
class TestP9B224YayimlananBoy:
    """Kalemin KAPANAN yarısı kilitlenir: yakınsak koni yayımlanan boyda."""

    def test_yayimlanan_boy_yakinsak_koniyi_sayar(self, client):
        r = client.post('/calculate_liquid', json={
            'motor_name': 'D23P9', 'thrust': 10000.0, 'burn_time': 30.0,
            'chamber_pressure': 30.0, 'mixture_ratio': 2.2,
            'fuel_type': 'rp1', 'oxidizer_type': 'lox',
            'expansion_ratio': 12.0})
        assert r.status_code == 200
        kd = r.get_json()['design_summary']['key_dimensions']
        assert kd['convergent_length_mm'] > 0.0
        assert kd['overall_length_mm'] == pytest.approx(
            kd['chamber_length_mm'] + kd['convergent_length_mm']
            + kd['nozzle_length_mm'], rel=1e-12)
        # Tanım ADIYLA yayımlanır (kapağın DIŞARIDA olduğu okunabilir olmalı).
        assert 'convergent' in kd['overall_length_basis']

    def test_hibrit_kapakli_ve_kapaksiz_boyu_AYRI_yayimlar(self, client):
        """Kalan yarının ÇÖZÜM DESENİ hibritte zaten var; kilitlenir."""
        r = client.post('/calculate', json=HIBRIT)
        assert r.status_code == 200
        kd = r.get_json()['motor']['design_summary']['key_dimensions']
        assert kd['total_motor_length_with_caps_mm'] > \
            kd['total_motor_length_chamber_nozzle_mm']
        assert kd['forward_closure_length_mm'] > 0.0
