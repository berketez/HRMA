"""cea_bridge doğrulama testleri — basınca bağlı yanma verisi köprüsü.

Kapsanan sözleşme (hrma/engines/cea_bridge.py):
  * Birim disiplini: RocketCEA Imperial (psia, ft/s, °R, cal/(g·K)) çıktısı
    doğru SI'ya çevriliyor mu? (ham CEA çağrısıyla birebir kıyas).
  * Fiziksel doğruluk: klasik literatür noktaları (kaynaklar aşağıda).
  * Pc bağımlılığı: statik tablonun göremediği basınç etkisi doğru YÖNDE.
  * Fallback zinciri: RocketCEA yoksa / çift eşlenemezse statik değerlere düşüş,
    kaynağın DÜRÜST etiketlenmesi (source), sahte sayı ÜRETMEME (not_modelled).

DOĞRULAMA REFERANSLARI ve KAYNAKLAR
-----------------------------------
RocketCEA'nın kendisi NASA CEA'dır (Gordon & McBride, NASA RP-1311); bu yüzden
"altın referans" ham RocketCEA çağrısıdır ve sarmalayıcının işi onu doğru birime
çevirmektir (sıkı, rel~1e-9 testler). Bunun ÜSTÜNE bağımsız literatür bantları
konur:

  * LOX/LH2, Pc≈68 bar (1000 psia), MR=6.0: bu MR SSME/RS-25 çalışma noktasıdır.
    RS-25 ölçülen c* verimi ~%99.5 ve teslim c*≈2300 m/s → IDEAL c*≈2300-2340 m/s
    (Sutton & Biblarz, Rocket Propulsion Elements 9. baskı, Tablo 5-5 ve Böl. 3;
    NASA RS-25 veri sayfaları). NOT: görev metnindeki "~2430 m/s" değeri c*'ın
    PIK yaptığı DÜŞÜK MR (~4.5-5) içindir; MR=6.0'da CEA ~2300 m/s verir ve bu
    fiziksel olarak doğrudur (bu dosya doğru fiziğe göre bantlanmıştır).
  * LOX/RP-1, Pc≈68 bar, MR=2.27: c*≈1780-1810 m/s (Huzel & Huang, "Modern
    Engineering for Design of Liquid-Propellant Rocket Engines", AIAA 1992,
    LOX/RP-1 performans tabloları).
  * LOX/CH4, Pc=100 bar, MR=3.6: CEA ideal c*≈1830 m/s. HRMA statik tablosundaki
    1958.7 m/s (liquid_rocket_engine.py:1115) bu noktada CEA'dan ~%7 YÜKSEKTİR
    (iyimser); bu test gerçek CEA'yı esas alır, tabloyu değil.

Birim sabitleri modülle AYNI kaynaktan (NIST SP 811) — kopya değil, import.
"""

import time
import pytest

from hrma.engines import cea_bridge
from hrma.engines.cea_bridge import (
    get_combustion_properties,
    map_propellants,
    FT_PER_S_TO_M_PER_S,
    DEG_R_TO_K,
    BAR_TO_PSIA,
)

# RocketCEA opsiyonel: kurulu değilse CEA-gerektiren testler atlanır,
# fallback/eşleme/yapı testleri yine koşar.
try:
    from rocketcea.cea_obj import CEA_Obj
    ROCKETCEA_AVAILABLE = True
except Exception:  # pragma: no cover
    ROCKETCEA_AVAILABLE = False

needs_cea = pytest.mark.skipif(
    not ROCKETCEA_AVAILABLE,
    reason="RocketCEA kurulu değil; CEA gerektiren testler atlanıyor.")


# --------------------------------------------------------------------------
# Bağımsız ham CEA yardımcıları (sarmalayıcıyı DIŞARIDAN doğrulamak için)
# --------------------------------------------------------------------------
def _raw_cstar_ms(ox, fu, pc_bar, mr):
    c = CEA_Obj(oxName=ox, fuelName=fu)
    return c.get_Cstar(Pc=pc_bar * BAR_TO_PSIA, MR=mr) * FT_PER_S_TO_M_PER_S


def _raw_tc_k(ox, fu, pc_bar, mr):
    c = CEA_Obj(oxName=ox, fuelName=fu)
    return c.get_Tcomb(Pc=pc_bar * BAR_TO_PSIA, MR=mr) * DEG_R_TO_K


# --------------------------------------------------------------------------
# 1) Ad eşlemesi — tablodaki TÜM çiftler + h2o2 kapsanmalı
# --------------------------------------------------------------------------
class TestNameMapping:
    """liquid_rocket_engine.py:1023-1153 tablosundaki tüm çiftler eşlenmeli."""

    @pytest.mark.parametrize("fuel,ox,exp_f,exp_o", [
        ('rp1', 'lox', 'RP1', 'LOX'),
        ('lh2', 'lox', 'LH2', 'LOX'),
        ('mmh', 'n2o4', 'MMH', 'N2O4'),
        ('udmh', 'n2o4', 'UDMH', 'N2O4'),
        ('methane', 'lox', 'CH4', 'LOX'),
        ('ethanol', 'lox', 'C2H5OH', 'LOX'),
        ('rp1', 'h2o2', 'RP1', 'H2O2'),   # görev kapsamı: h2o2 oksitleyici
    ])
    def test_table_pairs_map(self, fuel, ox, exp_f, exp_o):
        assert map_propellants(fuel, ox) == (exp_f, exp_o)

    def test_case_insensitive(self):
        assert map_propellants('Methane', 'LOX') == ('CH4', 'LOX')

    def test_unmapped_returns_none(self):
        f, o = map_propellants('unobtanium', 'phlogiston')
        assert f is None and o is None


# --------------------------------------------------------------------------
# 2) Birim disiplini — sarmalayıcı ham CEA'yı doğru SI'ya çevirmeli
# --------------------------------------------------------------------------
@needs_cea
class TestUnitConsistency:
    """Modül çıktısı (m/s, K) bağımsız ham RocketCEA çağrısıyla birebir olmalı."""

    def test_cstar_matches_raw_rocketcea(self):
        r = get_combustion_properties('methane', 'lox', 100.0, 3.6)
        raw = _raw_cstar_ms('LOX', 'CH4', 100.0, 3.6)
        assert r['c_star_m_s'] == pytest.approx(raw, rel=1e-9)
        # Sağlık: ft/s ham değeri m/s'den büyük olmalı (0.3048 çarpanı)
        raw_fts = raw / FT_PER_S_TO_M_PER_S
        assert raw_fts > r['c_star_m_s']

    def test_tc_matches_raw_rocketcea(self):
        r = get_combustion_properties('methane', 'lox', 100.0, 3.6)
        raw = _raw_tc_k('LOX', 'CH4', 100.0, 3.6)
        assert r['tc_k'] == pytest.approx(raw, rel=1e-9)

    def test_source_and_keys_present(self):
        r = get_combustion_properties('methane', 'lox', 100.0, 3.6,
                                      expansion_ratio=40.0)
        for key in ('c_star_m_s', 'tc_k', 'gamma_chamber', 'gamma_throat',
                    'mw_g_mol', 'isp_vac_s', 'isp_sl_s', 'cp_chamber',
                    'mole_fractions', 'source', 'validity'):
            assert key in r, f'çıktı anahtarı eksik: {key}'
        assert r['source'] == 'rocketcea'
        for vkey in ('pc_range_ok', 'real_gas_warning', 'extrapolated', 'note'):
            assert vkey in r['validity']


# --------------------------------------------------------------------------
# 3) Literatür doğrulama noktaları (kaynaklar dosya başında)
# --------------------------------------------------------------------------
@needs_cea
class TestLiteraturePoints:

    def test_lox_lh2_68bar_mr6(self):
        """LOX/LH2, 68 bar, MR=6.0 (RS-25 çalışma noktası).

        IDEAL c*≈2300-2340 m/s, Tc≈3400-3650 K. (Görev metnindeki 2430,
        c* pikinin olduğu düşük MR içindir; MR=6.0'da CEA doğru olarak
        ~2300 m/s verir.)
        """
        r = get_combustion_properties('lh2', 'lox', 68.0, 6.0, expansion_ratio=40.0)
        assert 2250.0 < r['c_star_m_s'] < 2400.0, \
            f"LOX/LH2 c*={r['c_star_m_s']:.1f} m/s beklenen ~2300 bandında değil"
        assert 3400.0 < r['tc_k'] < 3650.0, \
            f"LOX/LH2 Tc={r['tc_k']:.1f} K beklenen bantta değil"
        # RS-25 vakum Isp'i ~452 s (eps~69'da); eps=40'ta ~450 s civarı sağlık
        assert 430.0 < r['isp_vac_s'] < 465.0

    def test_lox_rp1_68bar_mr227(self):
        """LOX/RP-1, 68 bar, MR=2.27: c*≈1780-1810 m/s (Huzel & Huang)."""
        r = get_combustion_properties('rp1', 'lox', 68.0, 2.27)
        assert 1740.0 < r['c_star_m_s'] < 1850.0, \
            f"LOX/RP-1 c*={r['c_star_m_s']:.1f} m/s beklenen ~1780 bandında değil"

    def test_lox_ch4_100bar_mr36_vs_real_cea(self):
        """LOX/CH4, 100 bar, MR=3.6: gerçek CEA c*≈1830 m/s.

        HRMA statik tablosu bu noktada 1958.7 m/s (iyimser, ~%7 yüksek); bu
        test tabloyu DEĞİL gerçek CEA'yı esas alır. Sarmalayıcı ham CEA ile
        birebir olmalı.
        """
        r = get_combustion_properties('methane', 'lox', 100.0, 3.6)
        raw = _raw_cstar_ms('LOX', 'CH4', 100.0, 3.6)
        assert r['c_star_m_s'] == pytest.approx(raw, rel=1e-9)
        assert 1780.0 < r['c_star_m_s'] < 1900.0
        # Tablo değeri (1958.7) gerçek CEA'dan belirgin YÜKSEK olmalı (bilgi):
        assert r['c_star_m_s'] < 1958.7 * 0.98  # >%2 fark

    def test_cp_chamber_matches_static_table_order(self):
        """Donmuş oda cp'si statik tablo mertebesinde (2287 J/kgK) olmalı."""
        r = get_combustion_properties('methane', 'lox', 100.0, 3.6,
                                      expansion_ratio=40.0)
        # Statik tablo cp_chamber=2287.4; frozen CEA ~2292 → %2 içinde
        assert r['cp_chamber'] == pytest.approx(2287.4, rel=0.03)

    def test_gamma_throat_below_chamber(self):
        """Genişlerken gamma düşer: gamma_throat < gamma_chamber (sağlık)."""
        r = get_combustion_properties('methane', 'lox', 100.0, 3.6,
                                      expansion_ratio=40.0)
        assert 1.05 < r['gamma_throat'] <= r['gamma_chamber'] < 1.35
        assert 15.0 < r['mw_g_mol'] < 30.0  # LOX/CH4 egzoz MW bandı


# --------------------------------------------------------------------------
# 4) Pc bağımlılığı — statik tablonun göremediği etki, doğru YÖNDE
# --------------------------------------------------------------------------
@needs_cea
class TestPressureDependence:

    def test_cstar_increases_with_pc(self):
        """LOX/CH4 MR=3.6: Pc 100->300 bar c* ARTMALI (dissosiyasyon azalır),
        fark %0.5-%3 bandında olmalı (ölçülen ~%1.14)."""
        lo = get_combustion_properties('methane', 'lox', 100.0, 3.6)['c_star_m_s']
        hi = get_combustion_properties('methane', 'lox', 300.0, 3.6)['c_star_m_s']
        assert hi > lo, 'Pc artınca c* artmalı'
        delta_pct = 100.0 * (hi - lo) / lo
        assert 0.5 <= delta_pct <= 3.0, \
            f'c* Pc-farkı {delta_pct:.2f}% beklenen %0.5-3 bandında değil'

    def test_tc_increases_with_pc(self):
        """Tc de Pc ile artmalı (dissosiyasyon bastırılır)."""
        lo = get_combustion_properties('methane', 'lox', 100.0, 3.6)['tc_k']
        hi = get_combustion_properties('methane', 'lox', 300.0, 3.6)['tc_k']
        assert hi > lo

    def test_real_gas_warning_at_300bar(self):
        """Raptor sınıfı 300 bar: gerçek-gaz uyarısı + açıklama metni gelmeli."""
        r = get_combustion_properties('methane', 'lox', 300.0, 3.6)
        assert r['validity']['real_gas_warning'] is True
        assert r['validity']['extrapolated'] is False  # 300 <= 500 bandı içi
        assert 'real-gas' in r['validity']['note'].lower() or \
               'fugacity' in r['validity']['note'].lower()

    def test_no_real_gas_warning_at_100bar(self):
        r = get_combustion_properties('methane', 'lox', 100.0, 3.6)
        assert r['validity']['real_gas_warning'] is False


# --------------------------------------------------------------------------
# 5) Fallback zinciri — RocketCEA yok / çağrı hatası / eşleşmeme
# --------------------------------------------------------------------------
_STATIC_CH4 = {  # liquid_rocket_engine.py:1111-1131 değerleri (çağıran iletir)
    'c_star': 1958.7, 'T_c': 3556.2, 'gamma': 1.2287, 'mw': 20.49,
    'isp_vac': 382.4, 'isp_sl': 334.2, 'cp_chamber': 2287.4,
}


class TestFallbackChain:

    def test_rocketcea_unavailable_uses_static(self, monkeypatch):
        """RocketCEA yokmuş gibi davran -> statik fallback dönmeli, source doğru."""
        monkeypatch.setattr(cea_bridge, 'is_rocketcea_available', lambda: False)
        r = get_combustion_properties('methane', 'lox', 300.0, 3.6,
                                      fallback=_STATIC_CH4)
        assert r['source'] == 'static_table'
        assert r['c_star_m_s'] == 1958.7   # tablo değeri aynen
        assert r['tc_k'] == 3556.2
        assert r['gamma_chamber'] == 1.2287
        assert r['gamma_throat'] == 1.2287  # throat verilmedi -> chamber'a eşit
        assert r['mw_g_mol'] == 20.49
        # 300 bar fallback: gerçek-gaz uyarısı yine gelmeli
        assert r['validity']['real_gas_warning'] is True
        # 100 bar çapasından uzak -> extrapolated
        assert r['validity']['extrapolated'] is True

    def test_call_failure_falls_back(self, monkeypatch):
        """RocketCEA çağrısı patlarsa fallback kullanılmalı, not açıklamalı."""
        def _boom(*a, **k):
            raise RuntimeError('CEA exploded')
        monkeypatch.setattr(cea_bridge, '_compute_rocketcea', _boom)
        r = get_combustion_properties('methane', 'lox', 100.0, 3.6,
                                      fallback=_STATIC_CH4)
        assert r['source'] == 'static_table'
        assert r['c_star_m_s'] == 1958.7
        assert 'failed' in r['validity']['note'].lower()

    def test_unmapped_pair_with_fallback(self):
        """Eşlenemeyen çift + fallback -> statik değerler, source doğru."""
        r = get_combustion_properties('exotic', 'weird', 100.0, 3.0,
                                      fallback=_STATIC_CH4)
        assert r['source'] == 'static_table'
        assert r['c_star_m_s'] == 1958.7

    def test_unmapped_pair_no_fallback_not_modelled(self):
        """Ne eşleme ne fallback -> sahte sayı YOK, not_modelled + None."""
        r = get_combustion_properties('exotic', 'weird', 100.0, 3.0)
        assert r['source'] == 'not_modelled'
        assert r['c_star_m_s'] is None
        assert r['tc_k'] is None
        assert r['gamma_chamber'] is None
        assert 'not mapped' in r['validity']['note'].lower()

    def test_fallback_output_schema_aliases(self):
        """Çıktı şeması anahtarlarıyla (c_star_m_s...) iletilen fallback de çalışmalı."""
        fb = {'c_star_m_s': 2000.0, 'tc_k': 3600.0, 'gamma_chamber': 1.20,
              'gamma_throat': 1.15, 'mw_g_mol': 21.0}
        r = get_combustion_properties('exotic', 'weird', 100.0, 3.0, fallback=fb)
        assert r['c_star_m_s'] == 2000.0
        assert r['gamma_throat'] == 1.15  # ayrı verildi -> chamber'a eşitlenmez


# --------------------------------------------------------------------------
# 6) Önbellek / performans — ilk çağrı hariç <100 ms
# --------------------------------------------------------------------------
@needs_cea
class TestCachingPerformance:

    def test_repeat_call_is_cached_and_fast(self):
        # ilk çağrı (soğuk) — süre ölçülmez
        get_combustion_properties('rp1', 'lox', 70.0, 2.5, expansion_ratio=25.0)
        t = time.perf_counter()
        for _ in range(50):
            get_combustion_properties('rp1', 'lox', 70.0, 2.5, expansion_ratio=25.0)
        avg_ms = (time.perf_counter() - t) / 50.0 * 1000.0
        assert avg_ms < 100.0, f'önbellekli çağrı çok yavaş: {avg_ms:.3f} ms'

    def test_rounding_shares_cache(self):
        """Yuvarlama sınırındaki komşu girdiler aynı sonucu vermeli (deterministik)."""
        a = get_combustion_properties('methane', 'lox', 100.4, 3.601)['c_star_m_s']
        b = get_combustion_properties('methane', 'lox', 100.0, 3.60)['c_star_m_s']
        assert a == pytest.approx(b, rel=1e-12)


if __name__ == '__main__':  # elle hızlı çalıştırma
    import sys
    sys.exit(pytest.main([__file__, '-v']))
