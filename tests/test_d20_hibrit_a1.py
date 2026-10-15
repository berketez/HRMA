# -*- coding: utf-8 -*-
"""ÖH Dalga-20 · kulvar **hibrit** · aşama 1/1 — onarım bekçileri.

Her sınıf TEK bir kalemi kilitler ve o kalemin ONARIMI GERİ ALINDIĞINDA
kırmızıya döner (ters-mutasyon kanıtı:
``docs/scofield/raw/OH/D20/hibrit/a1/mutasyon.json``).

Kapsanan kalemler:
  B1-06      (Fable-D17 ŞARTI) koşum-zamanı hükümleri ``calculate()``
             başında düşmüyordu; bir koşumda yazılan koşullu hüküm
             (``burn_integration_steps``) sonraki koşumda BAYAT kalıyordu
  OH-D19-01  ``/calculate`` 0 < ε < 1 gövdesini HTTP 200 ile kabul edip
             çıkışı boğazdan KÜÇÜK bir "lüle" çiziyordu
  OH-D17-05  ayrılma modülü ``separated=None`` (hüküm verilmedi) döndürünce
             hibrit bloğu ``bool()`` ile bunu "ayrılma yok" diye yayımlıyordu
  OH-D19-10  ``pla`` yoğunluğu iki dosyada iki değer (1250 ⟷ 1240), merkezi
             kayıtta anahtarı yoktu
  B3-13      ``sea_level_isp`` irtifa listesinin İLK satırıydı;
             ``mass_averaged_*`` kütle-ağırlıklı değildi
  B4-10      ``power_residual_rel`` basınç beslemeli çevrimde (mil YOK)
             uydurma ``0.0`` yayımlıyordu, künyesi yoktu
  B4-11      ``pintle_tip_geometry`` D_p'yi ince-anülüs yaklaşımından,
             t'yi tam ifadeden çözüyordu (t/D_p %4,555 sapma)
  B4-12      ``_plan_orifices`` band-altı çapı ``n_max`` yolunda sessiz
             geçiriyor, ``n_fixed`` yolunda uyarıyordu
"""
import contextlib
import io
import os
import warnings as _warnings

import numpy as np
import pytest

from hrma.data.propellant_database import HYBRID_FUEL_DENSITY_KG_M3
from hrma.engines.combustion_analysis import CombustionAnalyzer
from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.engines.injector_design import (
    DEFAULT_CONSTRAINTS,
    ORIFICE_D_PREF_MM,
    PINTLE_ANNULUS_T_OVER_DP,
    _plan_orifices,
    pintle_tip_geometry,
)

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOTOR_KAYNAK = os.path.join(_KOK, 'hrma', 'engines', 'hybrid_rocket_engine.py')

#: Ölçüm betiğiyle AYNI taban
#: (``docs/scofield/raw/OH/D20/hibrit/a1/olcum.py``).
TABAN = dict(thrust=1000.0, burn_time=10.0, of_ratio=6.0,
             chamber_pressure=20.0, fuel_type='htpb', oxidizer_type='n2o')


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        with _warnings.catch_warnings():
            _warnings.simplefilter('ignore')
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _kapilar(motor, ad):
    return [k for k in motor.design_gate_checks if k.get('gate') == ad]


# =========================================================================
# B1-06 · koşum hükümleri koşum başında düşer (Fable-D17 ŞARTI)
# =========================================================================
class TestB106KosumHukumleriDuser:
    """ŞARTIN birebir istediği bekçi: ``t_b`` kırpma tetikleyen koşumdan
    sonra kırpmayan koşumda ``burn_integration_steps`` kaydı KALMAZ.

    ÖLÇÜLDÜ (once.json ``B1_06``): kırpan koşumdan sonra defter
    [c_star_plausibility, burn_integration_steps]; kırpmayan koşumdan sonra
    da AYNI iki kayıt (bayat hüküm). sonra.json: ikinci koşumda tek kayıt.
    """

    def test_bayat_kirpma_hukmu_ikinci_kosumda_kalmaz(self):
        motor = _sessiz(HybridRocketEngine, **dict(TABAN, burn_time=3e5))
        _sessiz(motor.calculate)
        assert _kapilar(motor, 'burn_integration_steps'), (
            't_b = 3e5 kırpmayı tetiklemeliydi; ölçüm tabanı değişmiş')
        motor.burn_time = 10.0
        motor.t_b = 10.0
        _sessiz(motor.calculate)
        assert _kapilar(motor, 'burn_integration_steps') == [], (
            'kırpma OLMAYAN koşumdan sonra bayat clamped hükmü defterde '
            'kalıyor')

    def test_kurucu_zamani_hukmu_kosumdan_sonra_yasar(self):
        """Bant dışı η_c* KULLANICININ girdisidir; koşuma ait değildir."""
        motor = _sessiz(HybridRocketEngine, **dict(TABAN, eta_c_star=0.30))
        assert _kapilar(motor, 'c_star_efficiency_band')
        _sessiz(motor.calculate)
        assert _kapilar(motor, 'c_star_efficiency_band'), (
            'kurucu-zamanı hüküm koşum başında silinmiş — ŞART bunu '
            'AÇIKÇA yasaklıyor')
        _sessiz(motor.calculate)
        assert len(_kapilar(motor, 'c_star_efficiency_band')) == 1

    def test_kosum_kapisi_her_kosumda_yeniden_yazilir(self):
        motor = _sessiz(HybridRocketEngine, **TABAN)
        _sessiz(motor.calculate)
        _sessiz(motor.calculate)
        assert len(_kapilar(motor, 'c_star_plausibility')) == 1

    def test_evre_defteri_yanita_sizmaz(self):
        """Defterin ŞEKLİ değişmedi: kayıtlarda 'phase' anahtarı yok."""
        motor = _sessiz(HybridRocketEngine, **TABAN)
        _sessiz(motor.calculate)
        for kayit in motor.design_gate_checks:
            assert 'phase' not in kayit


# =========================================================================
# OH-D19-01 · /calculate ε < 1 adlı retle düşer
# =========================================================================
class TestOHD1901GenlesmeOraniBirdenKucukReddedilir:
    """ÖLÇÜLDÜ (once.json ``OH_D19_01``): ε = 0,5 -> HTTP 200,
    d_t = 26,658 mm, d_e = 18,850 mm (çıkış boğazdan KÜÇÜK)."""

    def test_eps_yarim_adli_retle_duser(self, istemci):
        r = _sessiz(istemci.post, '/calculate',
                    json=dict(TABAN, expansion_ratio=0.5))
        assert r.status_code == 422, r.get_data(as_text=True)[:300]
        govde = r.get_json() or {}
        alanlar = [k.get('field') for k in govde.get('invalid_fields', [])]
        assert 'expansion_ratio' in alanlar
        assert govde['invalid_fields'][0]['reason'] == 'must_be_at_least_one'
        assert 'motor' not in govde

    def test_eps_bir_dejenere_ama_tanimli_kabul_edilir(self, istemci):
        r = _sessiz(istemci.post, '/calculate',
                    json=dict(TABAN, expansion_ratio=1.0))
        assert r.status_code == 200
        motor = (r.get_json() or {}).get('motor') or {}
        assert motor['exit_diameter'] == pytest.approx(
            motor['throat_diameter'], rel=1e-12)

    def test_sifir_hala_cozucuye_birakir(self, istemci):
        """Sözleşme korunur: 0 = 'çözücü çözsün' (P16B1-08 deseni)."""
        r = _sessiz(istemci.post, '/calculate',
                    json=dict(TABAN, expansion_ratio=0))
        assert r.status_code == 200
        motor = (r.get_json() or {}).get('motor') or {}
        assert motor['expansion_ratio'] > 1.0

    def test_negatif_hala_400(self, istemci):
        r = _sessiz(istemci.post, '/calculate',
                    json=dict(TABAN, expansion_ratio=-2.0))
        assert r.status_code == 400


# =========================================================================
# OH-D17-05 · ayrılma hükmü ÜÇ DEĞERLİ taşınır
# =========================================================================
class TestOHD1705AyrilmaHukmuUcDegerli:
    def test_motor_kaynaginda_kosulsuz_bool_kalmadi(self):
        """``'separated': bool(sep.get('separated'))`` deseni yok olmalı."""
        with open(_MOTOR_KAYNAK, encoding='utf-8') as f:
            kaynak = f.read()
        assert "'separated': bool(sep.get('separated'))" not in kaynak, (
            'top-level separated hâlâ bool() ile None -> False çevriliyor')

    def test_hukum_verilmeyen_kosumda_none_yayimlanir(self):
        """Modül ``separated=None`` derse blok da None yayımlar."""
        from hrma.engines import hybrid_rocket_engine as motor_modulu
        yok_hukum = {
            'separated': None,
            'separated_criteria': [],
            'controlling_criterion': None,
            'x_sep_m': None,
            'area_ratio_sep': None,
            'criteria': {},
            'full_flow_exit': None,
            'not_applicable_reason': 'boğaz boğulmamış (ölçüm senaryosu)',
        }
        # Yayım bloğunun sözleşmesi: status not_applicable + separated None.
        durum = ('not_applicable'
                 if yok_hukum.get('not_applicable_reason') else 'modelled')
        yayim = (None if yok_hukum.get('separated') is None
                 else bool(yok_hukum.get('separated')))
        assert durum == 'not_applicable' and yayim is None
        # ve ürün kaynağı bu deseni GERÇEKTEN taşıyor:
        with open(_MOTOR_KAYNAK, encoding='utf-8') as f:
            kaynak = f.read()
        assert "'separated': (None if sep.get('separated') is None" in kaynak
        assert 'separated_verdict_basis' in kaynak
        assert motor_modulu is not None


# =========================================================================
# OH-D19-10 · pla yoğunluğu tek kaynaktan
# =========================================================================
class TestOHD1910PlaYogunluguTekKaynak:
    """ÖLÇÜLDÜ (once.json ``OH_D19_10``): motor rho_f 1250,
    combustion_specs 1240, merkezi tabloda anahtar YOK."""

    def test_merkezi_kayitta_pla_var(self):
        assert HYBRID_FUEL_DENSITY_KG_M3['pla'] == 1240

    def test_motor_merkezi_kayittan_okur(self):
        motor = _sessiz(HybridRocketEngine, **dict(TABAN, fuel_type='pla'))
        assert motor.rho_f == float(HYBRID_FUEL_DENSITY_KG_M3['pla'])

    def test_yanma_cozucusu_merkezi_kayittan_okur(self):
        ca = _sessiz(CombustionAnalyzer)
        assert (ca.propellant_specs['pla']['density']
                == HYBRID_FUEL_DENSITY_KG_M3['pla'])

    def test_motor_kaynaginda_ciplak_1250_kalmadi(self):
        with open(_MOTOR_KAYNAK, encoding='utf-8') as f:
            kaynak = f.read()
        assert "'density': 1250" not in kaynak


# =========================================================================
# B3-13 · ad ↔ davranış
# =========================================================================
class TestB313AdDavranisOrtusur:
    def test_sea_level_isp_deniz_seviyesi_satirindan(self):
        ca = _sessiz(CombustionAnalyzer)
        motor_data = {
            'performance': {'velocities': {'exit': 2400.0},
                            'c_star': 1600.0},
            'conditions': {'exit': {'P': 0.9, 'T': 1400.0}},
            'gas_constants': {'exit': 300.0},
            'mdot_total': 0.4,
        }
        sifirli = _sessiz(ca.calculate_altitude_performance,
                          motor_data, [0.0, 5000.0, 10000.0])
        sifirsiz = _sessiz(ca.calculate_altitude_performance,
                           motor_data, [5000.0, 10000.0])
        sifir_satiri = [s for s in sifirli['altitude_performance']
                        if s['altitude'] == 0.0][0]
        assert sifirli['sea_level_isp'] == pytest.approx(sifir_satiri['isp'])
        # deniz seviyesi İSTENMEDİĞİNDE sayı UYDURULMAZ
        assert sifirsiz['sea_level_isp'] is None
        assert 'sea_level_isp_basis' in sifirsiz
        # ve ilk satırın Isp'si sessizce "deniz seviyesi" diye geçmez
        ilk = sifirsiz['altitude_performance'][0]['isp']
        assert sifirsiz['sea_level_isp'] != ilk

    def test_mass_averaged_adi_kalmadi(self):
        import inspect

        from hrma.engines import combustion_analysis as modul
        kaynak = inspect.getsource(modul)
        # Yorumlarda kalemin ADI geçebilir; aranan şey YAYIMLANAN ANAHTAR.
        for eski in ("'mass_averaged_gamma'", "'mass_averaged_cp'",
                     "'mass_averaged_mw'"):
            assert eski not in kaynak, (
                f'kütle-ağırlıklı OLMAYAN büyüklük hâlâ {eski} anahtarıyla '
                'yayımlanıyor')
        assert "'station_mean_gamma'" in kaynak
        assert "'station_mean_basis'" in kaynak


# =========================================================================
# B4-10 · power_residual_rel kazanılmadığı yerde yayımlanmaz
# =========================================================================
class TestB410GucArtigiUydurulmaz:
    def test_basinc_beslemeli_cevrimde_mil_yok_artik_none(self):
        from hrma.engines import cycle_power_balance as cpb
        sol = _sessiz(cpb.solve_cycle, 'pressure_fed', 100.0, 20.0, 2.5,
                      'rp1', 'lox', tank_pressure_bar=200.0)
        assert sol.shafts == []
        assert sol.power_residual_rel is None, (
            'mil olmayan çevrimde "güç dengesi tam kapandı" diye okunan '
            'uydurma 0,0 yayımlanıyor')

    def test_kunye_ne_olmadigini_soyluyor(self):
        from hrma.engines import cycle_power_balance as cpb
        sol = _sessiz(cpb.solve_cycle, 'gas_generator', 100.0, 20.0, 2.5,
                      'rp1', 'lox')
        d = sol.to_dict()
        assert 'power_residual_basis' in d
        assert 'not an independent cross-check' in d['power_residual_basis']


# =========================================================================
# B4-11 · pintle ucu tek modelden çözülür
# =========================================================================
class TestB411PintleUcuTekModel:
    """ÖLÇÜLDÜ (once.json ``B4_11``): t/D_p her alanda 0,0477226 —
    künyenin söz verdiği 0,05'ten %4,555 sapma."""

    @pytest.mark.parametrize('a_ann', [2.0e-5, 8.0e-5, 3.2e-4])
    def test_t_over_dp_hedefi_tutar(self, a_ann):
        g = pintle_tip_geometry(1.5e-5, a_ann)
        t = g['annulus_gap_mm'] * 1e-3
        d_p = g['d_pintle_mm'] * 1e-3
        assert t / d_p == pytest.approx(PINTLE_ANNULUS_T_OVER_DP, rel=1e-9)

    @pytest.mark.parametrize('a_ann', [2.0e-5, 8.0e-5, 3.2e-4])
    def test_tam_anulus_alani_geri_verilir(self, a_ann):
        g = pintle_tip_geometry(1.5e-5, a_ann)
        t = g['annulus_gap_mm'] * 1e-3
        d_p = g['d_pintle_mm'] * 1e-3
        assert np.pi * (d_p + t) * t == pytest.approx(a_ann, rel=1e-12)

    def test_verilen_d_pintle_yolu_bozulmadi(self):
        g = pintle_tip_geometry(1.5e-5, 8.0e-5, d_pintle_m=0.030)
        assert g['d_pintle_mm'] == pytest.approx(30.0)


# =========================================================================
# B4-12 · orifis planı iki yolda AYNI hükmü verir
# =========================================================================
class TestB412OrifisPlaniSessizGecmez:
    """ÖLÇÜLDÜ (once.json ``B4_12``): aynı n ve aynı çap için ``n_fixed``
    yolu 1 uyarı, ``n_max`` yolu 0 uyarı."""

    KISIT = {'d_min_mm': 0.04, 'd_max_mm': 3.0, 'n_max': 120}

    def _alan(self, d1_mm):
        return np.pi / 4.0 * (d1_mm * 1e-3) ** 2

    def test_band_alti_cap_n_max_yolunda_da_uyarir(self):
        alan = self._alan(0.49)
        u1 = []
        n1, d1 = _plan_orifices(alan, self.KISIT, u1)
        u2 = []
        n2, d2 = _plan_orifices(alan, self.KISIT, u2, n_fixed=n1)
        assert (n1, d1) == (n2, d2)
        assert d1 * 1e3 < ORIFICE_D_PREF_MM[0]
        assert len(u1) == len(u2) == 1, (
            f'aynı geometri iki yolda farklı hüküm alıyor: '
            f'n_max {len(u1)} uyarı, n_fixed {len(u2)} uyarı')
        assert u1[0]['code'] == 'warn.injector.orifice_d_below_pref_band'

    def test_bant_ici_cozum_hala_sessiz(self):
        """Yanlış pozitif yok: tercih bandına oturan plan uyarı üretmez."""
        u = []
        n, d = _plan_orifices(self._alan(4.0), dict(DEFAULT_CONSTRAINTS), u)
        assert ORIFICE_D_PREF_MM[0] <= d * 1e3 <= ORIFICE_D_PREF_MM[1]
        assert u == []
