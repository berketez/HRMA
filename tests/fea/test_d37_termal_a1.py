# tests/fea — ÖH D37 A2-1 termal a1: çözücü + malzeme eşiği + köprü bekçileri
"""
Kalemler ve ters mutasyon kayıtları: docs/scofield/raw/OH/A2/termal/a1/
(rapor.md, mutasyon.md; kilit olcut_kulvar.json).

  F-02 / OH-DK-08  üç seviyeli uzamsal merdiven + Celik 2008 GCI (hrma/utils/
                   gci.py TEK tanım) + kilitli hüküm kuralı (K1); yayımlanan
                   seviye en ince; kaba seviyenin kalan hata kestirimi.
  OH-DK-11         zaman ölçütü alan L∞ (Dirichlet'e çivili tepeye kör değil).
  OH-DK-10         DEFAULT_MAX_DT_HALVINGS 8 → 10 (ölçüldü).
  keep_history     ince seviyeler geçmiş tutmaz; sonuç bit-aynı.
  F-01 / M2        materials_db.temperature_limits tek eşik + tüketiciler
                   (thermal_protection, heat_transfer_analysis, bridge) — AST.
  F-01             thermal_paths_reconciliation şeması (iki üretici tek şema).
  F-03             wall_profile_inputs_from_motor (üç motor sözlüğü, kanıt).
  B2-CP            consumed_paths (yapısal + termal çıkarıcılar).

Sayısal çapalar ÖLÇÜMDÜR (once/ ve D26 taban kaydı); kanıt dosyaları
tests/support/kanit.py kapısından okunur (yayın dalında gerekçeli atlama).
"""
from __future__ import annotations

import ast
import inspect
import json
import pathlib
import types

import numpy as np
import pytest

from hrma.data import materials_db as mdb
from hrma.fea import bridge
from hrma.fea import thermal_axisym as ta
from hrma.fea.mesh_axisym import build_wall_mesh
from hrma.fea.thermal_axisym import (
    AdiabaticBC, AmbientBC, ConvectionBC, FixedTemperatureBC,
    ThermalMaterial, solve_transient, solve_transient_auto,
)
from tests.support.kanit import kanit_gerekli

# Yol parçalarla kurulur ve YALNIZ kanit_gerekli kapısından okunur
# (tests/support/kanit_tarayici.py: kanit_yolu('docs/…') dize tohumu ve kapıyı
# yerel yardımcının İÇİNDE çağırmak ihlal sayılıyordu — test_kanit_atlama_
# kapisi::test_b; denetçi 3. tur süpürmesinde ölçüldü).
KANIT = (pathlib.Path(__file__).resolve().parents[2] / 'docs' / 'scofield'
         / 'raw' / 'OH' / 'A2' / 'termal' / 'a1')
ONCE = KANIT / 'once'


def _kanit_json(ad):
    return json.loads(kanit_gerekli(ONCE / ad).read_text(encoding='utf-8'))


# ---------------------------------------------------------------------------
# F-02 — üç seviyeli merdiven, gerçek çözücü (D26 taban vakası)
# ---------------------------------------------------------------------------
def _d26_vaka(refiner=True, na=16, nr=4):
    z = np.linspace(0.0, 0.30, 41)
    kontur = np.column_stack([z, np.full_like(z, 0.05)])
    mk = (lambda a, r: build_wall_mesh(kontur, 0.003, int(a), int(r)))
    mat = ThermalMaterial(rho=8000.0, cp=500.0, k=16.0, name='SS304')
    res = solve_transient_auto(
        mk(na, nr), mat, 3.0, ConvectionBC(h=5000.0, T_inf=3000.0),
        AmbientBC(h=10.0, T_ambient=293.15, emissivity=0.0), 293.15,
        mesh_refiner=(mk if refiner else None))
    return res


@pytest.fixture(scope='module')
def d26():
    return _d26_vaka()


class TestF02Merdiven:

    def test_uc_seviye_r2_ve_gci_tek_tanimdan(self, d26):
        u = d26.meta['uzamsal_yakinsama']
        assert u['denetlendi'] is True and u['seviye_sayisi'] == 3
        sv = u['seviyeler']
        assert [(s['n_axial'], s['n_radial']) for s in sv] == [
            (16, 4), (32, 8), (64, 16)]
        assert u['gci']['status'] == 'monotonic' and u['gci']['gci_valid']
        assert u['gci']['r21'] == pytest.approx(2.0) and \
            u['gci']['r32'] == pytest.approx(2.0)
        # Ölçüldü (D26 taban once_a3.json): 2191,8468 → 2190,7475 → 2190,4739
        assert u['kaba_peak_wall_T'] == pytest.approx(2191.8468, abs=5e-3)
        assert u['ince_peak_wall_T'] == pytest.approx(2190.7475, abs=5e-3)
        assert sv[2]['peak_wall_T'] == pytest.approx(2190.4739, abs=5e-3)

    def test_asimptotik_vakada_converged_p_iki(self, d26):
        u = d26.meta['uzamsal_yakinsama']
        assert u['hukum'] == 'converged' and u['converged'] is True
        assert u['neden_kodu'] is None and u['richardson_guvenilir'] is True
        assert 1.7 <= u['p'] <= 2.3
        assert u['GCI_fine21'] <= u['tol']
        assert 'SAĞLANDI' in u['beyan'] and 'GCI' in u['beyan']

    def test_yayimlanan_seviye_en_ince_ve_alan_o_meshin(self, d26):
        u = d26.meta['uzamsal_yakinsama']
        assert ta.SPATIAL_PUBLISH_LEVEL == 'finest'
        assert u['yayimlanan_seviye']['n_axial'] == 64
        assert u['seviyeler'][-1]['yayimlandi'] is True
        assert d26.published_mesh.n_axial == 64 and d26.published_mesh.n_radial == 16
        assert d26.T_final.shape == (d26.published_mesh.n_nodes,)
        assert d26.peak_wall_T == pytest.approx(u['seviyeler'][-1]['peak_wall_T'])
        assert d26.meta['yayimlanan_mesh']['istenen_mesh'] == {
            'n_axial': 16, 'n_radial': 4}

    def test_kalan_hata_kestirimi_kaba_icin_beyanli(self, d26):
        u = d26.meta['uzamsal_yakinsama']
        sv = u['seviyeler']
        # Richardson dışdeğerine göre kalan hata: kaba > orta > ince (mutlak)
        e = [abs(s['kalan_hata_kestirimi_K']) for s in sv]
        assert e[0] > e[1] > e[2]
        assert u['peak_wall_T_ext_K'] == pytest.approx(
            293.15 + u['gci']['f_ext'])

    def test_refiner_yoksa_not_evaluated_ve_kaba_yayimlanir(self):
        res = _d26_vaka(refiner=False)
        u = res.meta['uzamsal_yakinsama']
        assert u['denetlendi'] is False and u['hukum'] == 'not_evaluated'
        assert u['neden_kodu'] == 'refiner_yok'
        assert u['converged'] is None and u['rel_change'] is None
        assert 'DENETLENMEDİ' in u['beyan']
        assert res.published_mesh.n_axial == 16

    def test_ara_seviye_gecmis_tutmaz_yayimlanan_tutar(self, d26):
        sv = d26.meta['uzamsal_yakinsama']['seviyeler']
        assert sv[0]['gecmis_tutuldu'] is True      # kaba: zaman ölçütü için
        assert sv[1]['gecmis_tutuldu'] is False     # ara seviye
        assert sv[2]['gecmis_tutuldu'] is True      # yayımlanan (bütçeye sığdı)
        assert d26.T_history is not None


# ---------------------------------------------------------------------------
# F-02 — hüküm kuralı (K1) sentetik merdivenlerle (çözücü stub'lanır)
# ---------------------------------------------------------------------------
def _stub_merdiven(monkeypatch, tepeler, T0=293.15, dU=None, patlat=None,
                   n_levels=None):
    """``solve_transient``i her çağrıda sıradaki tepe değeriyle stub'lar."""
    dU = dU or [1.0e6 * (1 + 0.001 * i) for i in range(len(tepeler))]
    sira = {'i': 0}

    def sahte(mesh, material, times, ibc, obc, T_initial, keep_history=True):
        i = sira['i']
        sira['i'] += 1
        if patlat is not None and i == patlat:
            raise RuntimeError('sentetik inceltme hatası')
        return types.SimpleNamespace(
            peak_wall_T=float(tepeler[i]), energy={'dU_J': float(dU[i])},
            T_history=None if not keep_history else np.zeros((2, 1)))
    monkeypatch.setattr(ta, 'solve_transient', sahte)

    class M:
        def __init__(self, na, nr):
            self.n_axial, self.n_radial = na, nr
            self.n_elems, self.n_nodes = na * nr, (na + 1) * (nr + 1)
    kaba = M(16, 4)
    ilk = sahte(kaba, None, None, None, None, T0)
    ek = {} if n_levels is None else {'n_levels': n_levels}
    blok, res, mesh = ta._uzamsal_yakinsama(
        ilk, kaba, None, np.linspace(0.0, 1.0, 3), None, None, T0,
        lambda a, r: M(a, r), ta.DEFAULT_SPATIAL_TOL, **ek)
    return blok, res, mesh


class TestF02HukumKurali:

    def test_dk_t7_kaba_uclu_p_0_45_not_converged_p_dusuk(self, monkeypatch):
        """ÖLÇÜLDÜ (DK T7 / once/t7_ozet.json): 2582,5 → 2598,0 → 2609,3 K,
        p ≈ 0,45 < 1,0 → asimptotik aralık dışı; eski tek inceltme bunu
        'SAĞLANDI %0,68' diye yayımlıyordu (OH-DK-08)."""
        blok, res, mesh = _stub_merdiven(
            monkeypatch, [2582.5458, 2598.0102, 2609.3272])
        assert blok['hukum'] == 'not_converged'
        assert blok['neden_kodu'] == 'p_dusuk'
        # Ş4: insan metni iç kodu taşımaz (kod yalnız neden_kodu'nda)
        assert 'p_dusuk' not in blok['neden'] and 'p_dusuk' not in blok['beyan']
        assert blok['neden'].startswith('gözlenen mertebe 0.450')
        assert blok['gci']['p'] < ta.SPATIAL_P_MIN_ASYMPTOTIC
        assert blok['converged'] is False and 'SAĞLANMADI' in blok['beyan']
        # kaba seviyenin kalan hata kestirimi beyanlı ve emniyetsiz yönde (+)
        assert blok['seviyeler'][0]['kalan_hata_kestirimi_K'] > 0.0
        # Denetçi Ş7: p < p_min → dışdeğer/kalan hata sayısı DURUR (değişmez),
        # güvenilmez bayrağıyla ve beyanda adıyla.
        assert blok['richardson_guvenilir'] is False
        assert blok['peak_wall_T_ext_K'] == pytest.approx(
            293.15 + blok['gci']['f_ext'])
        assert 'GÜVENİLMEZ' in blok['beyan']
        # yayımlanan yine en ince
        assert mesh.n_axial == 64 and res.peak_wall_T == pytest.approx(2609.3272)

    def test_p_min_esigi_kilitle_ayni(self):
        kilit = json.loads(kanit_gerekli(KANIT / 'olcut_kulvar.json')
                           .read_text(encoding='utf-8'))
        assert ta.SPATIAL_P_MIN_ASYMPTOTIC == pytest.approx(
            kilit['K1_F02_urun_hukmu']['P_MIN_ASYMPTOTIC']['deger'])
        assert ta.DEFAULT_SPATIAL_TOL == pytest.approx(
            kilit['K1_F02_urun_hukmu']['spatial_tol'])
        assert ta.DEFAULT_SPATIAL_LEVELS == 3

    def test_gci_toleransi_asilinca_gci_buyuk(self, monkeypatch):
        # p = 2 ama farklar büyük: ΔT 1000 → 1120 → 1150 (ε32 = 120, ε21 = 30)
        blok, _, _ = _stub_merdiven(monkeypatch, [1293.15, 1413.15, 1443.15])
        assert blok['gci']['p'] == pytest.approx(2.0, abs=1e-9)
        assert blok['hukum'] == 'not_converged'
        assert blok['neden_kodu'] == 'gci_buyuk'
        assert 'gci_buyuk' not in blok['neden'] and 'gci_buyuk' not in blok['beyan']
        # p ≥ p_min: dışdeğer asimptotik aralıkta — güvenilir (Ş7)
        assert blok['richardson_guvenilir'] is True
        assert 'GÜVENİLMEZ' not in blok['beyan']

    def test_iraksayan_dizide_gci_yok(self, monkeypatch):
        blok, _, _ = _stub_merdiven(monkeypatch, [1300.0, 1320.0, 1360.0])
        assert blok['gci']['status'] == 'monotonic_divergent'
        assert blok['hukum'] == 'not_converged' and 'GCI_fine21' not in blok['gci']
        assert blok['p'] is None and blok['GCI_fine21'] is None
        assert blok['neden_kodu'] == 'sinif'
        assert not blok['neden'].startswith('sinif')
        assert blok['richardson_guvenilir'] is None     # dışdeğer yok

    def test_esit_tepe_dejenere_ve_ikincil_qoi(self, monkeypatch):
        blok, _, _ = _stub_merdiven(monkeypatch, [800.0, 800.0, 800.0],
                                    dU=[1.0e6, 1.04e6, 1.05e6])
        assert blok['neden_kodu'] == 'dejenere'
        assert blok['hukum'] == 'degenerate' and blok['converged'] is False
        assert blok['gci_dU'] is not None and blok['gci_dU']['status'] == 'monotonic'
        assert 'dU_J' in blok['beyan']

    def test_inceltme_hatasi_not_evaluated_iki_seviye(self, monkeypatch):
        blok, res, mesh = _stub_merdiven(
            monkeypatch, [2000.0, 2010.0, 2012.0], patlat=2)
        assert blok['hukum'] == 'not_evaluated' and blok['seviye_sayisi'] == 2
        assert blok['neden_kodu'] == 'az_seviye'
        assert blok['inceltme_hatasi']['tip'] == 'RuntimeError'
        assert blok['gci'] is None and blok['converged'] is None
        assert mesh.n_axial == 32          # çözülen en ince yayımlanır
        assert 'ÖLÇÜLEMEDİ' in blok['beyan']

    def test_yayim_politikasi_coarse_secilirse_kaba(self, monkeypatch):
        monkeypatch.setattr(ta, 'SPATIAL_PUBLISH_LEVEL', 'coarse')
        blok, res, mesh = _stub_merdiven(monkeypatch, [2000.0, 2004.0, 2005.0])
        assert mesh.n_axial == 16 and blok['seviyeler'][0]['yayimlandi'] is True
        assert res.peak_wall_T == pytest.approx(2000.0)


# ---------------------------------------------------------------------------
# Denetçi 3. tur Ş2 (X2) — 4 seviyede GCI EN İNCE üçlüden
# ---------------------------------------------------------------------------
class TestF02DortSeviye:
    """ÖLÇÜLDÜ (sart3/sonra.json merdiven.t7.dort_seviye; A+A = en ince
    yayım + motorun gazı): 16×4 2697,11 → 32×8 2705,25 → 64×16 2717,53 →
    128×32 2722,63 K. Kaba üçlü MONOTON IRAKSAR (GCI yok); ince üçlü p 1,27,
    GCI %0,186 → converged, Richardson 2726,25 K. Denetçi mutasyonu X2
    (``uclu = seviyeler[:3]``) hükmü 'not_converged'e çevirir — bu sınıf
    onu yakalar."""

    TEPELER = [2697.110164740994, 2705.2531260613296, 2717.5305724431587,
               2722.6293965733335]

    def test_dort_seviyede_gci_en_ince_ucluden(self, monkeypatch):
        blok, res, mesh = _stub_merdiven(monkeypatch, self.TEPELER, n_levels=4)
        assert blok['seviye_sayisi'] == 4
        g = blok['gci']
        # N sırası ince → kaba: 128×32, 64×16, 32×8 eleman
        assert g['N'] == [128 * 32, 64 * 16, 32 * 8]
        assert g['status'] == 'monotonic'
        assert g['p'] == pytest.approx(1.267774, abs=1e-5)
        assert blok['hukum'] == 'converged' and blok['neden_kodu'] is None
        assert blok['peak_wall_T_ext_K'] == pytest.approx(2726.2510, abs=1e-3)
        assert blok['richardson_guvenilir'] is True
        assert mesh.n_axial == 128 and res.peak_wall_T == pytest.approx(
            2722.6293965733335)

    def test_kaba_uclu_tek_basina_iraksar(self, monkeypatch):
        """Aynı dizinin ilk üç seviyesi (varsayılan 3 seviyeli istek) —
        monoton ıraksama, GCI yok: X2'nin vereceği yanlış hüküm budur."""
        blok, _, _ = _stub_merdiven(monkeypatch, self.TEPELER[:3])
        assert blok['gci']['status'] == 'monotonic_divergent'
        assert blok['hukum'] == 'not_converged' and blok['neden_kodu'] == 'sinif'


# ---------------------------------------------------------------------------
# OH-DK-11 — alan normu; OH-DK-10 — tavan; keep_history
# ---------------------------------------------------------------------------
def _t5a():
    mk = (lambda a, r: build_wall_mesh([(0.0, 0.02), (0.1, 0.02)], 0.02,
                                       int(a), int(r)))
    mat = ThermalMaterial(rho=7850.0, cp=477.0, k=42.7, name='steel_4130')
    return mk, mat


class TestDK11AlanNormu:

    def test_dirichlet_tepede_kor_degil(self):
        """ÖLÇÜLDÜ (DK T5a): eski ölçüt rel_change = 0,0 ile 1. yarılamada
        (32 adım) 'yakınsadı' diyordu; alan normu 0,025 → 128 adımda."""
        mk, mat = _t5a()
        res = solve_transient_auto(mk(4, 4), mat, 20.0, FixedTemperatureBC(T=800.0),
                                   AdiabaticBC(), 300.0, mesh_refiner=mk)
        za = res.meta['zaman_adimi']
        h = za['history']
        assert all(hh['rel_change_peak'] == pytest.approx(0.0) for hh in h[1:])
        assert all(hh['rel_change'] > 0.0 for hh in h[1:])
        assert za['halvings'] >= 2 and za['n_steps'] >= 64
        assert 'L∞' in za['beyan'] or 'alan' in za['yontem']

    def test_alan_normu_tepe_normunu_ustten_sinirlar(self):
        res = _d26_vaka()
        for hh in res.meta['zaman_adimi']['history'][1:]:
            assert hh['rel_change'] >= hh['rel_change_peak'] - 1e-15

    def test_dk10_tavan_on(self):
        assert ta.DEFAULT_MAX_DT_HALVINGS == 10
        assert ta.DEFAULT_N_STEPS0 * 2 ** ta.DEFAULT_MAX_DT_HALVINGS == 16384


class TestKeepHistory:

    def test_gecmissiz_kosu_bit_ayni(self):
        mk, mat = _t5a()
        mesh = mk(4, 4)
        times = np.linspace(0.0, 4.0, 65)
        a = solve_transient(mesh, mat, times, ConvectionBC(h=1500.0, T_inf=2000.0),
                            AdiabaticBC(), 300.0)
        b = solve_transient(mesh, mat, times, ConvectionBC(h=1500.0, T_inf=2000.0),
                            AdiabaticBC(), 300.0, keep_history=False)
        assert b.T_history is None and a.T_history is not None
        np.testing.assert_array_equal(a.T_final, b.T_final)
        np.testing.assert_array_equal(a.peak_wall_T_history, b.peak_wall_T_history)
        assert a.peak_node == b.peak_node and a.peak_time_s == b.peak_time_s
        assert a.energy['dU_J'] == b.energy['dU_J']
        assert a.meta['aralik_denetimi']['T_maks'] == b.meta['aralik_denetimi']['T_maks']
        assert a.meta['aralik_denetimi']['T_min'] == b.meta['aralik_denetimi']['T_min']
        # Koşu sırasında izlenen min/maks, tam geçmişin min/maksına EŞİT
        # (mutasyon M6: son adımın min'i alınırsa T_min 300 K'den kayar).
        assert a.meta['aralik_denetimi']['T_min'] == float(np.min(a.T_history))
        assert a.meta['aralik_denetimi']['T_maks'] == float(np.max(a.T_history))
        assert b.meta['aralik_denetimi']['T_min'] == pytest.approx(300.0)
        assert b.meta['alan_gecmisi_tutuldu'] is False and 'alan_gecmisi_beyani' in b.meta


# ---------------------------------------------------------------------------
# F-01 / M2 — tek eşik fonksiyonu ve tüketicileri
# ---------------------------------------------------------------------------
class TestM2TekEsik:

    @pytest.mark.parametrize('ad', mdb.list_materials())
    def test_merdiven_kayitla_tutarli(self, ad):
        rec = mdb.get_material(ad)
        tl = mdb.temperature_limits(rec)
        adaylar = [v for v in (rec.get('allowable_temperature'),
                               rec.get('max_service_temp')) if v]
        assert tl['allowable_K'] == pytest.approx(min(adaylar))
        assert tl['service_K'] == pytest.approx(rec['max_service_temp'])
        assert tl['melting_K'] == pytest.approx(rec['melting_point'])
        assert tl['ladder'] == ['allowable', 'service', 'melting']
        assert tl['allowable_K'] <= tl['melting_K']

    def test_olculen_degerler_ss304_4130_718(self):
        assert mdb.temperature_limits('ss_304')['allowable_K'] == 1073.0
        assert mdb.temperature_limits('ss_304')['service_K'] == 1143.0
        assert mdb.temperature_limits('ss_304')['melting_K'] == 1673.0
        assert mdb.temperature_limits('steel_4130')['allowable_K'] == 811.0
        assert mdb.temperature_limits('steel_4130')['source_fields']['allowable_K'] == 'max_service_temp'
        assert mdb.temperature_limits('inconel_718')['allowable_K'] == 977.0
        assert mdb.temperature_limits('copper')['allowable_K'] == 723.0

    def test_isi_yutucu_tek_esik_ss304_kisalir_4130_bit_ayni(self):
        """ÖNCE (once/isi_yutucu_t7_capasi.json, main 68c55a27): ss_304 sınır
        1143 K → sınıra süre 0,044212 s. SONRA: 1073 K → daha kısa."""
        from hrma.analysis.thermal_protection import ThermalProtectionAnalyzer
        once = _kanit_json('isi_yutucu_t7_capasi.json')
        tp = ThermalProtectionAnalyzer()
        for malz, beklenen in (('ss_304', 1073.0), ('steel_4130', 811.0),
                               ('inconel_718', 977.0), ('copper', 723.0)):
            o = tp.heat_sink_transient(h_gas_W_m2K=11631.0, T_recovery_K=3377.0,
                                       burn_time_s=10.0, wall_thickness_m=0.02308,
                                       wall_material=malz)
            assert o['max_service_temp_K'] == pytest.approx(beklenen)
            assert o['temperature_limits']['allowable_K'] == pytest.approx(beklenen)
            assert 'allowable_K' in o['limit_K_basis']
            if malz == 'ss_304':
                assert o['time_to_limit_s'] < once['ss_304']['time_to_limit_s']
            else:
                assert o['time_to_limit_s'] == pytest.approx(
                    once[malz]['time_to_limit_s'], rel=0, abs=0)
                assert o['max_service_temp_K'] == once[malz]['max_service_temp_K']

    def test_ast_isi_yutucu_ham_alan_okumaz(self):
        """AST: heat_sink_transient gövdesinde ``mat['max_service_temp']``
        abonelik ifadesi YOK (yorum/dizgi sayılmaz); tek eşik çağrısı VAR."""
        from hrma.analysis import thermal_protection as tp
        src = inspect.getsource(tp.ThermalProtectionAnalyzer.heat_sink_transient)
        agac = ast.parse('class _K:\n' + ''.join(
            '    ' + ln for ln in src.splitlines(keepends=True)))
        ham = [n for n in ast.walk(agac)
               if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
               and n.value.id == 'mat' and isinstance(n.slice, ast.Constant)
               and n.slice.value in ('max_service_temp', 'allowable_temperature',
                                     'melting_point')]
        assert ham == [], [ast.unparse(n) for n in ham]
        cagri = [n for n in ast.walk(agac) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == 'temperature_limits']
        assert cagri, 'temperature_limits çağrısı yok'

    def test_ast_kopru_min_yeniden_yazmaz(self):
        src = inspect.getsource(bridge._extract_thermal_material)
        assert 'temperature_limits(' in src
        assert 'min(adaylar' not in src

    def test_ast_denge_zinciri_esik_blogu_fonksiyondan(self):
        from hrma.analysis import heat_transfer_analysis as hta
        for fn in (hta.HeatTransferAnalyzer._analyze_gas_side_heat_transfer,
                   hta.HeatTransferAnalyzer._analyze_thermal_safety,
                   hta.HeatTransferAnalyzer._heat_sink_delta_T):
            assert 'temperature_limits(' in inspect.getsource(fn), fn.__name__
        src = inspect.getsource(hta.HeatTransferAnalyzer._analyze_thermal_safety)
        assert "mat_props['allowable_temperature']\n" not in src

    def test_kopru_malzeme_siniri_fonksiyondan(self):
        alanlar, _ = bridge._extract_thermal_material('ss_304')
        assert alanlar['allowable_temperature_K'] == 1073.0
        assert alanlar['allowable_temperature_alani'] == 'allowable_temperature'
        assert alanlar['allowable_temperature_adaylari_K'] == {
            'allowable_temperature': 1073.0, 'max_service_temp': 1143.0}
        assert alanlar['temperature_limits']['ladder'] == ['allowable', 'service', 'melting']
        alanlar, _ = bridge._extract_thermal_material('steel_4130')
        assert alanlar['allowable_temperature_K'] == 811.0
        assert alanlar['service_temperature_K'] == 811.0
        assert alanlar['melting_point_K'] == 1705.0

    def test_denge_zinciri_sf_merdiven_izin_basamagi(self):
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
        an = HeatTransferAnalyzer()
        mat = an.materials['steel_4130']
        s = an._analyze_thermal_safety(1500.0, mat, 0.005, 20e5, wall_delta_T=100.0,
                                       chamber_radius_m=0.05)
        assert s['threshold_ladder']['allowable_K'] == 811.0
        assert s['temperature_safety_factor'] == pytest.approx(811.0 / 1500.0)


# ---------------------------------------------------------------------------
# Denetçi 3. tur Ş2 (X6, X7) — eşiği DAVRANIŞTAN ölçen bekçiler
# (AST bekçisi yalnız temperature_limits çağrısının VARLIĞINA bakıyordu;
# çağrı durup sonuç ham alanla ezilince yeşil kalıyordu)
# ---------------------------------------------------------------------------
#: ÖLÇÜLDÜ (sart3/once.json ⟷ sonra.json gaz_tarafi): rejeneratif, Pc 10 bar,
#: Tc 1800 K, 0,5 kg/s — denge cidarı 811 ile 1000 K arasında (4130 933,2 K).
#: ÖNCE uyarı YOK (eşik ham allowable_temperature 1000 K), SONRA
#: warn.thermal.wall_exceeds_allowable allowable=811.
PENCERE_MOTOR = {'chamber_pressure': 10.0, 'chamber_temperature': 1800.0,
                 'chamber_diameter': 0.1, 'chamber_length': 0.5,
                 'burn_time': 10.0, 'mdot_total': 0.5}


class TestM2Davranis:

    @pytest.mark.parametrize('malz,izin', [('steel_4130', 811.0),
                                           ('steel', 811.0),
                                           ('steel_4340', 811.0)])
    def test_gaz_tarafi_uyari_esigi_izin_basamagi(self, malz, izin):
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
        r = HeatTransferAnalyzer().analyze_heat_transfer(
            dict(PENCERE_MOTOR), material=malz, wall_thickness=0.005,
            cooling_type='regenerative')
        g = r['gas_side_analysis']
        assert g['threshold_ladder']['allowable_K'] == izin
        assert izin < g['estimated_wall_temperature'] < 1000.0
        uy = [w for w in g['warnings']
              if w.get('code') == 'warn.thermal.wall_exceeds_allowable']
        assert uy and uy[0]['params']['allowable'] == round(izin), g['warnings']

    @pytest.mark.parametrize('malz,izin', [('steel_4130', 811.0),
                                           ('steel_4340', 811.0),
                                           ('steel', 811.0),
                                           ('copper', 723.0)])
    def test_radyasyon_dengesi_servis_siniri_izin_basamagi(self, malz, izin):
        """ÖLÇÜLDÜ (sart3 radyasyon, /api/thermal-protection): ÖNCE
        allowable_temperature (4130/4340/copper 1000, steel 1073)."""
        from hrma.analysis.thermal_protection import ThermalProtectionAnalyzer
        r = ThermalProtectionAnalyzer().radiation_equilibrium(
            h_gas_W_m2K=500.0, T_recovery_K=3000.0, material=malz)
        assert r['service_limit_K'] == izin
        assert r['margin_K'] == pytest.approx(izin - r['T_wall_eq_K'])


# ---------------------------------------------------------------------------
# F-01 — uzlaştırma bloğu şeması
# ---------------------------------------------------------------------------
UZLASTIRMA_SOZLESMESI = {'equilibrium_K', 'fea_peak_K', 'fea_time_s', 'gap_K',
            'question_equilibrium', 'question_fea', 'threshold_ladder'}


class TestF01Uzlastirma:

    def test_sema_sabit_ve_fail_closed(self):
        from hrma.analysis.heat_transfer_analysis import thermal_paths_reconciliation
        rec = mdb.get_material('ss_304')
        b = thermal_paths_reconciliation(equilibrium_K=3368.0, mat_props=rec,
                                         burn_time_s=10.0)
        assert UZLASTIRMA_SOZLESMESI <= set(b)
        assert b['fea_peak_K'] is None and b['gap_K'] is None
        assert b['fea_status'] == 'not_run_in_this_chain'
        assert b['threshold_ladder'] == {
            'allowable_K': 1073.0, 'service_K': 1143.0, 'melting_K': 1673.0,
            '_basis': b['threshold_ladder']['_basis']}
        b2 = thermal_paths_reconciliation(equilibrium_K=3368.0, fea_peak_K=2582.5,
                                          fea_time_s=10.0)
        assert b2['gap_K'] == pytest.approx(3368.0 - 2582.5)
        b3 = thermal_paths_reconciliation(equilibrium_K=float('nan'),
                                          fea_peak_K=2582.5)
        assert b3['equilibrium_K'] is None and b3['gap_K'] is None

    def test_gap_basis_sayi_tasimaz(self):
        """Denetçi Ş7: künyede F-02 öncesi '2582 K' bayat kalmıştı; künye
        artık sayı taşımaz (ölçüm kanıtı raporda)."""
        import re
        from hrma.analysis.heat_transfer_analysis import thermal_paths_reconciliation
        b = thermal_paths_reconciliation(equilibrium_K=3368.0, fea_peak_K=2717.5)
        assert not re.search(r'\d', b['gap_basis']), b['gap_basis']

    def test_ana_zincir_blogu_yayimlar(self):
        from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
        an = HeatTransferAnalyzer()
        r = an.analyze_heat_transfer({
            'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
            'chamber_diameter': 0.1, 'chamber_length': 0.5, 'burn_time': 10.0,
            'mdot_total': 1.0}, material='ss_304', wall_thickness=0.005)
        b = r['thermal_paths_reconciliation']
        assert UZLASTIRMA_SOZLESMESI <= set(b)
        assert b['equilibrium_K'] == pytest.approx(r['wall_analysis']['max_temperature'])
        assert b['fea_peak_K'] is None
        assert b['threshold_ladder']['allowable_K'] == 1073.0
        assert r['gas_side_analysis']['threshold_ladder']['allowable_K'] == 1073.0
        assert r['gas_side_analysis']['threshold_ladder']['critical_K'] == 1673.0


# ---------------------------------------------------------------------------
# F-03 — motor-agnostik profil girdisi kurucusu
# ---------------------------------------------------------------------------
class TestF03Kurucu:

    @pytest.mark.parametrize('ad,layout', [('hibrit', 'hybrid'), ('kati', 'solid'),
                                           ('sivi', 'liquid')])
    def test_uc_motorda_cekirdek_tam(self, ad, layout):
        from hrma.analysis.heat_transfer_analysis import wall_profile_inputs_from_motor
        m = _kanit_json(f'{ad}_motor.json')
        o = wall_profile_inputs_from_motor(m)
        assert o['layout'] == layout and o['missing'] == []
        for k in ('chamber_pressure', 'chamber_temperature', 'chamber_diameter',
                  'chamber_length', 'burn_time', 'throat_diameter', 'gamma',
                  'c_star', 'material', 'wall_thickness', 'nozzle_contour'):
            assert k in o['inputs'], k
            assert k in o['basis'], k
        assert 0.001 < o['inputs']['wall_thickness'] < 0.1     # metre
        assert 0.01 < o['inputs']['chamber_diameter'] < 1.0    # metre

    def test_kati_gaz_sabiti_c_star_ozdesliginden(self):
        from hrma.analysis.heat_transfer_analysis import wall_profile_inputs_from_motor
        from hrma.constants import R_UNIVERSAL
        m = _kanit_json('kati_motor.json')
        o = wall_profile_inputs_from_motor(m)
        assert 'molecular_weight' not in o['inputs']
        assert 'gas_constant' in o['derived']
        assert R_UNIVERSAL / o['inputs']['gas_constant'] == pytest.approx(28.0, abs=0.01)

    def test_sivi_malzeme_ve_cidar_kopruyle_ayni(self):
        from hrma.analysis.heat_transfer_analysis import wall_profile_inputs_from_motor
        m = _kanit_json('sivi_motor.json')
        o = wall_profile_inputs_from_motor(m)
        t_b, _ = bridge._extract_wall_thickness_m(m, 'liquid')
        assert o['inputs']['wall_thickness'] == pytest.approx(t_b)
        assert o['inputs']['material'] == 'inconel_718'
        assert o['inputs']['mdot_total'] == pytest.approx(m['total_mass_flow'])

    def test_hibrit_cekirdek_panel_duz_govdesiyle_ayni(self):
        from hrma.analysis.heat_transfer_analysis import wall_profile_inputs_from_motor
        m = _kanit_json('hibrit_motor.json')
        o = wall_profile_inputs_from_motor(m)['inputs']
        for k in ('chamber_pressure', 'chamber_temperature', 'burn_time',
                  'mdot_total', 'chamber_diameter', 'chamber_length',
                  'throat_diameter', 'expansion_ratio'):
            assert o[k] == pytest.approx(m[k])

    def test_imzasiz_sozluk_uydurmaz(self):
        from hrma.analysis.heat_transfer_analysis import wall_profile_inputs_from_motor
        o = wall_profile_inputs_from_motor({'chamber_pressure': 20.0})
        assert o['layout'] is None and o['missing']
        o = wall_profile_inputs_from_motor('yok')
        assert o['missing'] and o['inputs'] == {}


# ---------------------------------------------------------------------------
# B2-CP — consumed_paths + köprü uçtan uca (kanıt profiliyle)
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def hibrit_kosu():
    m = _kanit_json('hibrit_motor.json')
    wp = _kanit_json('wall_profile_panel.json')['wall_profile']
    return m, bridge.run_thermal_from_motor(m, axial_profile=wp,
                                            ambient_temperature_K=293.15)


class TestB2CPveKopru:

    def test_yapisal_consumed_paths(self):
        m = _kanit_json('hibrit_motor.json')
        inp = bridge.extract_structural_inputs(m)
        yollar = {c['path'] for c in inp['consumed_paths']}
        assert 'structural_analysis.chamber_analysis.wall_thickness_used_mm' in yollar
        assert 'structural_analysis.design_parameters.material' in yollar
        assert 'chamber_pressure' in yollar and 'nozzle_contour.points' in yollar
        assert all(c['path'] for c in inp['consumed_paths'])

    def test_termal_consumed_paths_burn_time_ekler(self, hibrit_kosu):
        _, o = hibrit_kosu
        yollar = [c['path'] for c in o['consumed_paths']]
        assert 'burn_time' in yollar
        assert 'heat_transfer_analysis.wall_analysis.max_temperature' in yollar
        assert None not in yollar

    def test_kopru_yayimlanan_mesh_ve_sozlesme(self, hibrit_kosu):
        _, o = hibrit_kosu
        assert o['status'] == 'ok'
        sc = o['spatial_convergence']
        assert sc['checked'] is True and sc['verdict'] == 'converged'
        assert sc['published_level']['n_axial'] == o['mesh']['n_axial'] == 64
        assert len(o['T_final_K']) == o['mesh']['n_nodes']
        assert o['mesh_object'].n_axial == 64 and o['requested_mesh_object'].n_axial == 16
        # Ölçüldü (once/merdiven_hibrit.json, 512 adım): 64×16 → 1787,7209 K
        assert o['peak_wall_T_K'] == pytest.approx(1787.7209, abs=5e-3)
        rc = o['thermal_paths_reconciliation']
        assert UZLASTIRMA_SOZLESMESI <= set(rc) and rc['gap_K'] == pytest.approx(
            rc['equilibrium_K'] - rc['fea_peak_K'])
        assert rc['threshold_ladder'] == {'allowable_K': 811.0, 'service_K': 811.0,
                                          'melting_K': 1705.0}
        assert o['material_limits']['temperature_limits']['allowable_K'] == 811.0
        assert 'ÖLÇÜLÜR' in o['meta']['mesh_politikasi']['beyan']
        assert not any('DENETLENMEZ' in s for s in o['meta']['not_modelled'])
        # Denetçi Ş4/Ş7: makine kanalı — converged'da neden kodu yok,
        # dışdeğer asimptotik (güvenilir).
        assert sc['reason_code'] is None and sc['richardson_reliable'] is True
        assert 'richardson_reliability_basis' in sc

    def test_kopru_not_converged_neden_kodu_ve_guvenilmez_disdeger(self):
        """Ş4 + Ş7 canlı köprü: DK T7 (jenerik gaz profili, once/) →
        observed_order_below_min; dışdeğer ve kalan hata SAYILARI aynen
        (ölçüldü sart3/sonra/t7_fea_jenerik_gaz.json: 2640,2080 K, +57,6622 K),
        yalnız richardson_reliable False."""
        m = _kanit_json('t7_motor.json')
        wp = _kanit_json('t7_wall_profile_panel.json')['wall_profile']
        o = bridge.run_thermal_from_motor(m, axial_profile=wp,
                                          ambient_temperature_K=293.15)
        sc = o['spatial_convergence']
        assert sc['verdict'] == 'not_converged'
        assert sc['reason_code'] == 'observed_order_below_min'
        assert sc['richardson_reliable'] is False
        assert sc['richardson_extrapolated_peak_K'] == pytest.approx(2640.2080, abs=5e-3)
        assert sc['levels'][0]['residual_error_estimate_K'] == pytest.approx(
            57.6622, abs=5e-3)
        assert o['peak_wall_T_K'] == pytest.approx(2609.3272, abs=5e-3)
        assert 'GÜVENİLMEZ' in sc['declaration']

    def test_neden_kodu_sozlesmesi_ingilizce_ve_tam(self):
        """Çözücünün her neden kodu köprüde İngilizce bir sözleşme koduna
        eşlenir (Ş4: ekran Türkçe metni/iç kodu basmaz, bu kodu çevirir)."""
        kodlar = {'sinif', 'p_dusuk', 'gci_buyuk', 'dejenere', 'az_seviye',
                  'refiner_yok'}
        assert set(bridge.SPATIAL_REASON_CODES) == kodlar
        for v in bridge.SPATIAL_REASON_CODES.values():
            assert v.isascii() and v == v.lower() and ' ' not in v
        assert len(set(bridge.SPATIAL_REASON_CODES.values())) == len(kodlar)
