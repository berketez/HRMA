"""v2.5.2 fizik düzeltmeleri doğrulama testleri.

Kapsanan düzeltmeler (D1 dalgası):

  1. TERMAL -3115 K BUGI (heat_transfer_analysis._analyze_wall_temperature)
     Cidar iletim düşümü, MUHAFAZAKÂR TASARIM akısıyla (boğazda ~35 MW/m²)
     hesaplanıp DENGE cidar sıcaklığından çıkarılıyordu. İki büyüklük farklı
     termal duruma ait olduğundan dış cidar mutlak sıfırın altına düşüyordu
     (Pc=60 bar, 8 mm çelik -> -3076 K). Artık düşüm, denge çözümünün fiilen
     taşıdığı akıdan hesaplanır: q_eq = (T_iç - T_ortam)/R_toplam.

  2. TERMAL GERİLME (heat_transfer_analysis._analyze_thermal_safety)
     Sabit çelik değerleri (alpha=12e-6, E=200e9, akma=250e6) ve tam-kısıtlı
     E·alpha·(T-293) formu yerine, SEÇİLEN malzemenin özellikleriyle klasik
     cidar-içi gradyan formu: sigma = E·alpha·dT/(2(1-nu)).

  3. YAPISAL TERMAL HOOP (structural_analysis._thermal_hoop_stress)
     "Konservatiflik" adına düşürülmeyen 2 faktörü geri kondu; cidar sıcaklığı
     bilinmediğinde iç yüz artık servis sınırının tamamında değil
     WALL_TEMP_SERVICE_FRACTION katında varsayılır.

  4. L* GEOMETRİYE YANSIYOR (hybrid_rocket_engine)
     Kamara boyu = L_grain + ön-yanma + art-yanma; art-yanma L* hacminden
     çözülür. Ayrıca gerçekleşen L* raporlanır (hibritte port hacmi büyük
     olduğundan düşük L* istekleri geometrik olarak sağlanamaz).

  5. OPTİMUM O/F SESSİZ VARSAYILANI (utils/optimum_of_ratio)
     Tabloda olmayan yakıt/oksitleyici çiftinde sessiz 7.0 yerine ValueError.

  6. PLOTLY bdata (regression_analysis, trajectory_analysis)
     Plotly 6.x numpy dizisini base64 'bdata' olarak yazıyor; uygulamadaki
     plotly.js 1.58.5 bunu çizemiyor (boş grafik). Diziler listeye çevrildi.

  7. ISA TEKİLLEŞTİRME (constants.isa_pressure / isa_temperature)

Koşum:
    cd <depo kökü>
    MPLBACKEND=Agg python3 -m pytest tests/test_v252_physics.py -q
"""

import json
import warnings

import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.regression_analysis import RegressionAnalyzer
from hrma.analysis.structural_analysis import (StructuralAnalyzer,
                                               WALL_TEMP_SERVICE_FRACTION)
from hrma.constants import ISA_LAYERS, isa_pressure, isa_temperature
from hrma.utils.optimum_of_ratio import OptimumOFRatioFinder

AMBIENT = 293.15


@pytest.fixture(scope='module')
def heat():
    return HeatTransferAnalyzer()


@pytest.fixture(scope='module')
def struct():
    return StructuralAnalyzer()


# ----------------------------------------------------------------------
# 1. Cidar sıcaklığı fiziksel bantta (negatif Kelvin YOK)
# ----------------------------------------------------------------------
# (Pc [bar], cidar kalınlığı [m], malzeme, soğutma)
WALL_CASES = [
    (60.0, 0.008, 'steel_4130', 'natural'),    # rapor edilen -3076 K vakası
    (20.0, 0.005, 'steel_4130', 'natural'),
    (20.0, 0.010, 'steel', 'forced'),
    (100.0, 0.003, 'copper', 'regenerative'),
    (206.0, 0.001, 'copper', 'regenerative'),
    (5.0, 0.002, 'aluminum_6061', 'natural'),
    (50.0, 0.015, 'inconel_718', 'forced'),
]


class TestWallTemperatureBounded:

    @pytest.mark.parametrize('pc,thickness,material,cooling', WALL_CASES)
    def test_outer_wall_between_ambient_and_inner(self, heat, pc, thickness,
                                                  material, cooling):
        md = {
            'chamber_pressure': pc, 'chamber_temperature': 3200,
            'chamber_diameter': 0.1, 'chamber_length': 0.5,
            'burn_time': 10, 'mdot_total': 1.0,
        }
        r = heat.analyze_heat_transfer(md, material=material,
                                       wall_thickness=thickness,
                                       ambient_temp=AMBIENT,
                                       cooling_type=cooling)
        w = r['wall_analysis']
        T_in, T_out = w['inner_temperature'], w['outer_temperature']
        assert np.isfinite(T_in) and np.isfinite(T_out)
        assert T_out > 0.0, f"Non-physical (<=0 K) outer wall: {T_out:.0f} K"
        assert AMBIENT - 1e-6 <= T_out <= T_in + 1e-6, (
            f"Outer wall {T_out:.0f} K outside [{AMBIENT:.0f}, {T_in:.0f}] K")

    def test_reported_bug_case_no_longer_negative(self, heat):
        """Bildirilen vaka: Pc=60 bar, 8 mm çelik -> eskiden -3076 K."""
        md = {
            'chamber_pressure': 60.0, 'chamber_temperature': 3200,
            'chamber_diameter': 0.1, 'chamber_length': 0.5,
            'burn_time': 10, 'mdot_total': 1.0,
        }
        r = heat.analyze_heat_transfer(md, material='steel_4130',
                                       wall_thickness=0.008,
                                       ambient_temp=AMBIENT,
                                       cooling_type='natural')
        w = r['wall_analysis']
        assert w['outer_temperature'] > AMBIENT
        # Eski hata: tasarım akısı * R_iletim = 3000+ K düşüş.
        assert w['temperature_drops']['conduction'] < (
            w['inner_temperature'] - AMBIENT + 1e-6)

    def test_conduction_drop_uses_equilibrium_flux_not_design_flux(self, heat):
        """Denge akısı tasarım akısından KÜÇÜK; tasarım akısı korunmalı."""
        md = {
            'chamber_pressure': 60.0, 'chamber_temperature': 3200,
            'chamber_diameter': 0.1, 'chamber_length': 0.5,
            'burn_time': 10, 'mdot_total': 1.0,
        }
        r = heat.analyze_heat_transfer(md, material='steel_4130',
                                       wall_thickness=0.008,
                                       cooling_type='natural')
        w = r['wall_analysis']
        assert w['equilibrium_heat_flux'] < w['design_heat_flux']
        # Tasarım (boğaz) akısı raporlarda AYNEN kalır — yanma-delinmesi
        # tehlikesi maskelenmemeli.
        assert r['gas_side_analysis']['throat_heat_flux'] == pytest.approx(
            w['design_heat_flux'], rel=1e-12)
        R = w['thermal_resistance']
        assert w['temperature_drops']['conduction'] == pytest.approx(
            w['equilibrium_heat_flux'] * R['conduction'], rel=1e-9)


# ----------------------------------------------------------------------
# 2. Termal gerilme malzemeden gelir ve makul bantta
# ----------------------------------------------------------------------
class TestThermalStressFromMaterial:

    def _run(self, heat, material):
        md = {
            'chamber_pressure': 20.0, 'chamber_temperature': 3200,
            'chamber_diameter': 0.1, 'chamber_length': 0.5,
            'burn_time': 10, 'mdot_total': 1.0,
        }
        return heat.analyze_heat_transfer(md, material=material,
                                          wall_thickness=0.005,
                                          cooling_type='regenerative')

    def test_material_properties_are_reported_and_material_specific(self, heat):
        steel = self._run(heat, 'steel_4130')['safety_analysis']
        copper = self._run(heat, 'copper')['safety_analysis']
        ps, pc_ = steel['thermal_stress_properties'], copper['thermal_stress_properties']
        assert ps['elastic_modulus_GPa'] != pytest.approx(pc_['elastic_modulus_GPa'])
        assert ps['thermal_expansion_per_K'] != pytest.approx(
            pc_['thermal_expansion_per_K'])
        # Eski sabitler (çelik) artık her malzemeye uygulanmıyor.
        assert pc_['elastic_modulus_GPa'] != pytest.approx(200.0, abs=1e-6)

    def test_stress_matches_gradient_formula(self, heat):
        """Yayımlanan ``thermal_stress`` gradyan formülünün ta kendisi.

        KAPSAM BEYANI — ÖH Faz B-4, defter P4B1-15 (orta). Bu bekçi
        ``thermal_stress`` alanının kendi ADIYLA tutarlı olduğunu
        gösterir ve o kadarıyla DOĞRUDUR; ama aynı sözlükte yayımlanan
        ``stress_safety_factor`` adı, yalnız bu gradyan terimini içerdiği
        hâlde "gerilme emniyet katsayısı" diye okunuyor: aynı cidarın
        taşıdığı çember (basınç) gerilmesi hesaba HİÇ girmiyor — üstelik
        ``_analyze_thermal_safety`` ``pressure`` argümanını ALIYOR. Ad
        eksenini iki yeni bekçi ölçüyor (ikisi de bugün xfail(strict)):
        :meth:`test_stress_safety_factor_carries_the_hoop_term` ve
        :meth:`test_thermal_safety_consumes_the_pressure_it_receives`."""
        r = self._run(heat, 'steel_4130')
        s = r['safety_analysis']
        p = s['thermal_stress_properties']
        w = r['wall_analysis']
        dT = w['inner_temperature'] - w['outer_temperature']
        expected = (p['elastic_modulus_GPa'] * 1e9
                    * p['thermal_expansion_per_K'] * dT
                    / (2.0 * (1.0 - p['poisson_ratio']))) / 1e6
        assert s['thermal_stress'] == pytest.approx(expected, rel=1e-9)
        assert s['thermal_stress_delta_T_K'] == pytest.approx(dT, rel=1e-9)

    def test_stress_no_longer_absurd(self, heat):
        """Eski tam-kısıtlı form GPa mertebesi veriyordu (SF ~ 0.04).

        KAPSAM BEYANI — ÖH Faz B-4, defter P4B1-15 (orta). ``SF > 0,1``
        bir BÜYÜKLÜK bandıdır; sayının İÇERİĞİNİ (hangi gerilme
        bileşenlerini topladığını) sormaz, dolayısıyla basınç terimi
        eksik bir SF'yi de geçirir. Ölçüldü (2026-08-27, bu vaka):
        ``thermal_stress`` 1784,95 MPa — bandın üst kenarı 2000'e %10,8
        pay kalmış; SF 0,2577. Aynı vakada çember gerilmesi 20,0 MPa,
        birleşik SF 0,2549 → yayımlanan SF birleşiğinden İYİMSER."""
        s = self._run(heat, 'steel_4130')['safety_analysis']
        assert s['thermal_stress'] < 2000.0, 'thermal stress still absurd (GPa)'
        assert s['stress_safety_factor'] > 0.1

    # -----------------------------------------------------------------
    # ÖH FAZ B-4 — "stress_safety_factor" ADI KADAR İDDİA TAŞIYOR MU?
    # (defter P4B1-15, orta — ad-fazla-iddia sınıfı)
    #
    # Depoda DOĞRU desen zaten yazılı: structural_analysis aynı cidar için
    # ``safety_factor_pressure`` + ``safety_factor_total`` ikilisini
    # yayımlıyor (kardeş bekçi tests/test_wall_chain.py:111). Burada
    # istenen o desenin bu modüle uygulanması ya da adın/künyenin
    # kapsamını AÇIKÇA söylemesidir — aynı sözlükteki
    # ``ambient_temperature_basis`` künyesi bunun emsalidir.
    #
    # ÖLÇÜM (2026-08-27, steel_4130, 5 mm cidar, D=100 mm, rejeneratif;
    # akma 460,0 MPa). σ_hoop = p·r/t (ince cidar):
    #   Pc [bar]   σ_th [MPa]   SF (yayımlanan)   σ_hoop   SF_birleşik
    #      20       1784,95         0,2577          20,0      0,2549
    #     100       2749,14         0,1673         100,0      0,1615
    #     500       3218,20         0,1429         500,0      0,1237
    #    2000       3351,45         0,1373        2000,0      0,0860
    # Yayımlanan SF her satırda birleşiğinden BÜYÜK (iyimser) ve makas
    # basınçla açılıyor: %1,1 → %3,6 → %15,5 → %59,7.
    # -----------------------------------------------------------------

    #: Künye adayları — alan hangisiyle gelirse gelsin kapsamını söylemeli.
    KAPSAM_KUNYE_ADAYLARI = ('stress_safety_factor_basis',
                             'stress_safety_factor_source',
                             'stress_safety_factor_scope')

    def _hoop_MPa(self, pc_bar, cap_m=0.1, cidar_m=0.005):
        """İnce cidar çember gerilmesi σ = p·r/t [MPa] (aynı girdilerden)."""
        return (pc_bar * 1e5) * (cap_m / 2.0) / cidar_m / 1e6

    # ÇEVİRİ (ÖH D15 fix-3 / taban geçişi) — BORÇ İMİ KALKTI.
    # Bu bekçi P4B1-15 borcunu ``xfail(strict=True)`` ile taşıyordu;
    # imin kendi metni "onarım dalgası bu imi kaldırır" diyordu. Kusur
    # ÖH Z5S / PK6 (hüküm damgası kulvarı, commit f8269a5) tarafından
    # ONARILDI, dolayısıyla im BAYATLADI: birleşik ağaçta test GEÇİYOR
    # ve strict im XPASS(strict) ile KIRMIZI veriyordu. İm kaldırıldı;
    # iddia artık CANLI bekçidir.
    #
    # ÜRÜNDEKİ KANIT: hrma/analysis/heat_transfer_analysis.py:2528
    # "ÖH P4B1-15: ÇEMBER (BASINÇ) TERİMİ"; :2551 ``stress_scope =
    # 'thermal_gradient_plus_pressure_hoop'``; :2644-2647 künye
    # ``stress_safety_factor_scope`` ve ``pressure_hoop_stress_MPa``
    # ADIYLA yayımlanıyor — testin İKİ kabul yolu da karşılanıyor.
    #
    # ÖH D16 / termo-ucus a1 (OH-D15-09) — BORÇ İMİ KALDIRILDI.
    # Bu bekçi ``xfail(strict=True)`` ile yazılmıştı ve ürün onarımı
    # (``_analyze_thermal_safety``e çember terimi) daha SONRA indi; im
    # kaldırılmadığı için XPASS(strict) = KIRMIZI kaldı ve üç test
    # imsiz kırmızı olarak sayıldı (ölçüldü: e88d096 ve 6fde52b).
    # Onarımın gerçekten indiği KODDAN doğrulandı (once.json K3):
    # dört basınçta da ``pressure_hoop_stress_MPa`` = p·r/t el hesabıyla
    # birebir ve ``stress_safety_factor`` = akma/(σ_th+σ_hoop):
    #   Pc  20 bar -> hoop  20,0 MPa, SF 0,2587396 (yalnız-termal 0,2616834)
    #   Pc 100 bar -> hoop 100,0 MPa, SF 0,1625110 (yalnız-termal 0,1684625)
    #   Pc 500 bar -> hoop 500,0 MPa, SF 0,1238879 (yalnız-termal 0,1431668)
    #   Pc 2000bar -> hoop 2000,0 MPa, SF 0,0859636 (yalnız-termal 0,1372684)
    # İm kalkınca bekçi ASIL işini yapar: onarım geri alınırsa kırmızıya
    # döner (ters-mutasyon kanıtı: tests/test_d16_termo_ucus_a1.py).
    @pytest.mark.parametrize('pc_bar', [20.0, 500.0])
    def test_stress_safety_factor_carries_the_hoop_term(self, heat, pc_bar):
        """SF ya çember terimini içerir ya kapsamını künyede söyler.

        ÖH Faz B-4 — defter P4B1-15 (orta). Kabul iki yönlüdür (ürün
        hangisini seçerse seçsin bekçi yeşile döner):
          * SF birleşik gerilmeden (σ_th + σ_hoop) türetilmiş olur, yani
            yalnız-termal SF'den daha İYİMSER olamaz; ya da
          * ``safety_analysis`` bir kapsam künyesi taşır ve o künye
            alanın YALNIZ termal gradyanı içerdiğini söyler (kardeşi
            ``ambient_temperature_basis`` bu deseni aynı modülde
            uyguluyor).
        """
        md = {'chamber_pressure': pc_bar, 'chamber_temperature': 3200,
              'chamber_diameter': 0.1, 'chamber_length': 0.5,
              'burn_time': 10, 'mdot_total': 1.0}
        s = heat.analyze_heat_transfer(md, material='steel_4130',
                                       wall_thickness=0.005,
                                       cooling_type='regenerative'
                                       )['safety_analysis']
        kunye = [k for k in self.KAPSAM_KUNYE_ADAYLARI if k in s]
        metin = ' '.join(str(s[k]) for k in kunye).lower() if kunye else ''
        # ÖH D21 bekci-cevirisi a1 (OH-D17-28) — KÜNYE DALI DARALTILDI.
        # Ölçüldü (once_statik.json K5): ürün
        # ``stress_safety_factor_scope='thermal_gradient_plus_pressure_hoop'``
        # yayımlıyor. ESKİ kabul yolu yalnız "metinde 'thermal' geçiyor mu"
        # diye sorup ``return`` ediyordu; o dize 'thermal' İÇERDİĞİ için
        # bekçi SAYISAL dala HİÇ inmiyordu → çember terimi üründen
        # sökülse bile 6/6 yeşil kalıyordu (Fable-D17 bağımsız
        # mutasyonuyla teyit; OH-D17-28). Beyan yolu ancak künye alanın
        # çember terimini İÇERMEDİĞİNİ söylüyorsa geçerlidir; künye
        # "hoop/pressure/çember dahil" diyorsa bu bir BEYAN değil bir
        # İDDİADIR ve sayıyla sınanır.
        HOOP_IZLERI = ('hoop', 'pressure', 'basinc', 'basınç',
                       'cember', 'çember')
        hoop_beyani = any(t in metin for t in HOOP_IZLERI)
        akma = s['thermal_stress_properties']['yield_strength_MPa']
        hoop = self._hoop_MPa(pc_bar)
        birlesik = akma / (s['thermal_stress'] + hoop)
        if kunye and not hoop_beyani:
            assert 'thermal' in metin or 'termal' in metin, (
                f'kapsam künyesi ({kunye}) alanın yalnız termal gradyanı '
                f'içerdiğini söylemiyor: {metin[:200]!r}')
            return
        if hoop_beyani:
            # Künye çember terimini İÇERDİĞİNİ söylüyor: sayı da öyle desin.
            assert s.get('pressure_hoop_stress_MPa') == pytest.approx(
                hoop, rel=1e-9), (
                f'künye {metin[:120]!r} çember terimini içerdiğini söylüyor '
                f'ama yayımlanan pressure_hoop_stress_MPa '
                f'{s.get("pressure_hoop_stress_MPa")!r}; aynı girdilerden '
                f'p·r/t = {hoop:.4f} MPa olmalıydı')
            assert s['stress_safety_factor'] == pytest.approx(
                birlesik, rel=1e-6), (
                f'künye {metin[:120]!r} SF\'nin çember terimini içerdiğini '
                f'söylüyor ama yayımlanan {s["stress_safety_factor"]:.6f} '
                f'birleşik değer {birlesik:.6f} DEĞİL — künye ile sayı ayrı '
                f'şey anlatıyor')
        assert s['stress_safety_factor'] <= birlesik * (1.0 + 1e-9), (
            f"stress_safety_factor {s['stress_safety_factor']:.4f} "
            f"yayımlanıyor; aynı cidarın çember gerilmesi "
            f"({hoop:.1f} MPa, Pc={pc_bar:g} bar) eklendiğinde katsayı "
            f"{birlesik:.4f} olurdu (%{100 * (s['stress_safety_factor'] / birlesik - 1):.1f} "
            f"iyimser). Alan ne birleşik SF'dir ne de kapsamını söyleyen "
            f"bir künyesi vardır (aranan: {self.KAPSAM_KUNYE_ADAYLARI})")

    # ÇEVİRİ (ÖH D15 fix-3 / taban geçişi) — BORÇ İMİ KALKTI.
    # Aynı kalemin (P4B1-15) yapısal ayağı; ÖH Z5S / PK6 (f8269a5)
    # tarafından ONARILDI ve im BAYATLADI (XPASS(strict) → kırmızı).
    #
    # ÜRÜNDEKİ KANIT: hrma/analysis/heat_transfer_analysis.py:2465
    # "ÖH ONARIMI (defter P4B1-15) — ``pressure`` ARTIK TÜKETİLİYOR.";
    # :1116 çağıran hazne yarıçapını da geçiriyor.
    #
    # ÖH D16 / termo-ucus a1 (OH-D15-09) — BORÇ İMİ KALDIRILDI (yukarıdaki
    # gerekçe). AST ölçümü (once.json K3): ``_analyze_thermal_safety``
    # gövdesi ``pressure`` adını artık OKUYOR (pressure_Pa = float(pressure)
    # -> hoop_stress = pressure_Pa * radius_m / thickness_m).
    def test_thermal_safety_consumes_the_pressure_it_receives(self):
        """Aldığı basınç argümanı gövdede OKUNMALI (yapısal ölçüm).

        ÖH Faz B-4 — defter P4B1-15 (orta). Kusurun bulunuş yöntemi
        buydu ve burada bekçileşiyor: çağıran (``:827``) basıncı dört
        konumlu argümanın dördüncüsü olarak geçiriyor, imza onu
        ``pressure`` adıyla alıyor, gövde ise adı bir kez bile OKUMUYOR.
        Ölçüldü (2026-08-27, ``ast``): imza
        ``(self, max_temp, mat_props, thickness, pressure, wall_delta_T)``,
        gövdede Load bağlamında geçmeyen tek argüman ``pressure``
        (``thickness`` geçiyor — yani kusur "argümanlar zaten
        kullanılmıyor" genellemesi değil, ADRESLİ).

        Ölü argüman ya tüketilir ya imzadan düşer: ikisi de bu bekçiyi
        yeşile çevirir; bugünkü hâl "basıncı aldım" görüntüsü verip
        yalnız termal SF yayımlamaktır.
        """
        import ast
        import pathlib

        kaynak = (pathlib.Path(__file__).resolve().parents[1] / 'hrma'
                  / 'analysis' / 'heat_transfer_analysis.py')
        agac = ast.parse(kaynak.read_text(encoding='utf-8'))
        dugum = next((n for n in ast.walk(agac)
                      if isinstance(n, ast.FunctionDef)
                      and n.name == '_analyze_thermal_safety'), None)
        assert dugum is not None, (
            '_analyze_thermal_safety bulunamadı — bekçi güncellenmeli')
        argumanlar = [a.arg for a in dugum.args.args if a.arg != 'self']
        assert 'pressure' in argumanlar, (
            f'imza değişmiş ({argumanlar}); basınç argümanı düştüyse bu '
            'bekçi kaldırılabilir')
        okunan = {n.id for n in ast.walk(dugum)
                  if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        assert 'pressure' in okunan, (
            f"_analyze_thermal_safety (satır {dugum.lineno}) 'pressure' "
            f"argümanını alıyor ama gövdesinde HİÇ okumuyor; yayımladığı "
            f"alanın adı ise 'stress_safety_factor'. Gövdede okunan diğer "
            f"argümanlar: {sorted(a for a in argumanlar if a in okunan)}")


class TestStructuralThermalHoop:

    def test_classic_surface_formula_restored(self, struct):
        mat = struct.materials['steel_4130']
        out = struct._thermal_hoop_stress(mat, 400.0)
        expected = (mat['elastic_modulus'] * mat['thermal_expansion'] * 400.0
                    / (2.0 * (1.0 - mat['poisson_ratio'])))
        assert out['thermal_hoop_stress'] == pytest.approx(expected, rel=1e-12)

    def test_wall_temperature_contract_is_honoured(self, struct):
        md = {'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
              'chamber_diameter': 0.1, 'chamber_length': 0.5,
              'throat_diameter': 0.03, 'nozzle_type': 'conical',
              'burn_time': 10.0,
              'wall_temperature_hot': 900.0, 'wall_temperature_cold': 400.0}
        res = struct.analyze_structure(md, material='steel_4130')
        ta = res['thermal_analysis']
        assert ta['wall_temperature_inner_K'] == pytest.approx(900.0)
        assert ta['wall_temperature_outer_K'] == pytest.approx(400.0)

    def test_fallback_wall_temperature_uses_service_fraction(self, struct):
        md = {'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
              'chamber_diameter': 0.1, 'chamber_length': 0.5,
              'throat_diameter': 0.03, 'nozzle_type': 'conical',
              'burn_time': 10.0}
        res = struct.analyze_structure(md, material='steel_4130')
        expected = (struct.materials['steel_4130']['max_service_temp']
                    * WALL_TEMP_SERVICE_FRACTION)
        assert res['thermal_analysis']['wall_temperature_inner_K'] == pytest.approx(
            expected, abs=1.0)

    def test_ordinary_hybrid_with_real_wall_temperatures_is_not_critical(
            self, heat, struct):
        """Isı modülünden gelen GERÇEK cidar sıcaklıklarıyla 20 bar sıradan
        hibrit çelik kamara makul SF bandına döner (eski: her sıcak motor
        SF<1 -> CRITICAL)."""
        md = {'chamber_pressure': 20.0, 'chamber_temperature': 3200.0,
              'chamber_diameter': 0.1, 'chamber_length': 0.5,
              'throat_diameter': 0.03, 'nozzle_type': 'conical',
              'burn_time': 10.0, 'mdot_total': 1.0}
        h = heat.analyze_heat_transfer(dict(md), material='steel_4130',
                                       wall_thickness=0.005,
                                       cooling_type='natural')
        w = h['wall_analysis']
        md['wall_temperature_hot'] = w['inner_temperature']
        md['wall_temperature_cold'] = w['outer_temperature']
        res = struct.analyze_structure(md, material='steel_4130')
        sf = res['chamber_analysis']['von_mises_safety_factor']
        assert sf > 1.0, f"von Mises SF {sf:.2f} still below 1"
        assert sf < 50.0, f"von Mises SF {sf:.2f} implausibly optimistic"


# ----------------------------------------------------------------------
# 3. L* geometriye yansıyor
# ----------------------------------------------------------------------
def _engine(**kwargs):
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    params = dict(thrust=1000, burn_time=10, of_ratio=6.0,
                  chamber_pressure=20.0, track_performance=False,
                  uq_mode=True)
    params.update(kwargs)
    return HybridRocketEngine(**params)


class TestLStarGeometry:

    def test_chamber_length_is_sum_of_sections(self):
        e = _engine(l_star=4.0)
        r = e.calculate()
        assert r['chamber_length'] == pytest.approx(
            r['grain_length'] + r['pre_chamber_length']
            + r['post_chamber_length'], rel=1e-9)

    def test_chamber_length_grows_with_l_star(self):
        """L* etkin bantta (geometrik tabanın üstünde) boyu ARTIRIR."""
        # v3.0.1 kulvar P: art-yanma odası [0,3; 3]·D_ch'ye kelepçeli ve
        # D_ch artık son port çapıdır (eski 1,5·D_son değil), bu yüzden
        # etkin bant aşağı kaydı. Ölçüldü (bu motor): L* <= 2,5 grain_limited,
        # 3,0 ve 3,5 l_star_derived (L 0,6984 -> 0,7820 m), >= 4,0
        # post_chamber_clamped_high (tavan L*_ach 3,862 m). Eski 4 -> 6 m
        # çifti artık İKİSİ DE tavanda; bekçinin iddiası etkin bantta sınanır.
        base = _engine(l_star=3.0).calculate()
        taller = _engine(l_star=3.5).calculate()
        assert taller['chamber_length'] > base['chamber_length'] * 1.02
        assert taller['post_chamber_length'] > base['post_chamber_length']

    def test_low_l_star_reports_achieved_value(self):
        """Hibritte port hacmi büyüktür: düşük L* isteği sağlanamaz ve
        SESSİZ kalınmaz — gerçekleşen L* ve not raporlanır."""
        r = _engine(l_star=1.0).calculate()
        assert r['l_star'] == pytest.approx(1.0)
        assert r['l_star_achieved'] > r['l_star']
        assert 'achieved' in r['l_star_note'].lower()

    def test_l_star_1_to_2_changes_chamber_volume_reporting(self):
        """1.0 -> 2.0 aralığı geometrik tabanın altında kalabilir; bu durumda
        boy sabit kalır ama istenen/gerçekleşen L* farkı raporlanır."""
        a = _engine(l_star=1.0).calculate()
        b = _engine(l_star=2.0).calculate()
        assert b['chamber_length'] >= a['chamber_length']
        assert b['l_star_achieved'] == pytest.approx(a['l_star_achieved'],
                                                     rel=1e-6)
        assert b['l_star_note'] and a['l_star_note']


class TestEngineInputWiring:

    def test_initial_port_diameter_is_used_directly(self):
        e = _engine(initial_port_diameter=0.04)
        e.calculate()
        assert e.D_port_initial == pytest.approx(0.04, rel=1e-12)

    def test_injector_type_reaches_injector_design(self):
        r = _engine(injector_type='pintle').calculate()
        assert r['injector_design']['injector_type'] == 'pintle'

    def test_tank_temperature_changes_injector_sizing(self):
        cold = _engine(tank_temperature=263.15).calculate()['injector_design']
        warm = _engine(tank_temperature=303.15).calculate()['injector_design']
        assert cold['total_injector_area_mm2'] != pytest.approx(
            warm['total_injector_area_mm2'], rel=1e-3)


# ----------------------------------------------------------------------
# 4. Optimum O/F: sessiz varsayılan yok
# ----------------------------------------------------------------------
class TestOptimumOFNoSilentDefault:

    def test_unknown_pair_raises(self):
        finder = OptimumOFRatioFinder()
        with pytest.raises(ValueError) as exc:
            finder.find_optimum_hybrid('n2o', 'abs')
        msg = str(exc.value)
        assert 'No optimum O/F data' in msg
        assert 'N2O' in msg and 'ABS' in msg

    def test_unknown_liquid_pair_raises(self):
        finder = OptimumOFRatioFinder()
        with pytest.raises(ValueError):
            finder.find_optimum_liquid('n2o4', 'ethanol')

    def test_known_pair_still_works(self):
        finder = OptimumOFRatioFinder()
        out = finder.find_optimum_hybrid('n2o', 'htpb')
        assert 6.0 < out['optimum_of_ratio'] < 9.0

    def test_combustion_analyzer_reports_english_error(self):
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        with pytest.raises(ValueError) as exc:
            CombustionAnalyzer().find_optimum_of_ratio(
                {'unobtainium': 100.0}, 'n2o', 20.0)
        assert 'Unsupported fuel key' in str(exc.value)


# ----------------------------------------------------------------------
# 5. Plotly JSON'unda bdata yok (numpy -> liste)
# ----------------------------------------------------------------------
class TestPlotlyNoBdata:

    @pytest.fixture(scope='class')
    def regression_data(self):
        ra = RegressionAnalyzer()
        return ra, ra.analyze_regression_vs_time({
            'burn_time': 10.0, 'mdot_ox': 0.5, 'chamber_length': 0.4,
            'port_diameter_initial': 0.03, 'fuel_type': 'htpb'})

    def test_regression_plot_has_no_bdata(self, regression_data):
        ra, data = regression_data
        payload = json.loads(ra.create_regression_plot(data))
        assert 'bdata' not in json.dumps(payload)
        for trace in payload['data']:
            assert isinstance(trace['x'], list)
            assert isinstance(trace['y'], list)

    def test_regression_plot_has_no_fixed_width(self, regression_data):
        ra, data = regression_data
        payload = json.loads(ra.create_regression_plot(data))
        assert 'width' not in payload['layout']

    def test_fuel_comparison_plot_has_no_bdata(self, regression_data):
        ra, _ = regression_data
        # ÇEVRİLEN BEKÇİ (ÖH D15 / P5B4-01): bu çağrı başlangıç port
        # çapını GÖNDERMİYORDU ve çözümleyicinin uydurduğu 30 mm'ye
        # yaslanıyordu. Değer açıkça yazıldı — o günkü örtük değerin ta
        # kendisi, yani grafiğe dair sayısal iddia değişmedi.
        payload = ra.compare_fuel_types({
            'burn_time': 10.0, 'mdot_ox': 0.5, 'chamber_length': 0.4,
            'port_diameter_initial': 0.03})
        assert 'bdata' not in payload

    def test_trajectory_plot_has_no_bdata(self):
        from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
        t = TrajectoryAnalyzer()
        motor = {'thrust': 2000, 'burn_time': 8, 'total_impulse': 16000,
                 'propellant_mass_total': 8.0}  # ÖH D23/P4B3-24: tutarsız 'isp' kaldırıldı
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            res = t.calculate_trajectory(motor, {'launch_angle': 85})
            payload = t.create_trajectory_plots(res)
        assert 'bdata' not in payload
        # Sabit figür genişliği kaldırıldı (template içindeki iz-seviyesi
        # 'width' anahtarları sayılmaz; yalnız üst seviye bakılır).
        assert 'width' not in json.loads(payload)['layout']

    def test_regression_plot_labels_are_english(self, regression_data):
        ra, data = regression_data
        payload = ra.create_regression_plot(data)
        for turkish in ('Regresyon', 'Port Çapı', 'Zaman', 'Yakıt Türleri'):
            assert turkish not in payload


# ----------------------------------------------------------------------
# 6. ISA yardımcıları
# ----------------------------------------------------------------------
class TestISAHelpers:

    def test_sea_level_reference(self):
        assert isa_pressure(0.0) == pytest.approx(101325.0, rel=1e-9)
        assert isa_temperature(0.0) == pytest.approx(288.15, rel=1e-9)

    def test_layer_base_values_reproduced(self):
        for h_base, T_base, _lapse, P_base in ISA_LAYERS:
            assert isa_temperature(h_base) == pytest.approx(T_base, rel=1e-9)
            assert isa_pressure(h_base) == pytest.approx(P_base, rel=1e-3)

    def test_pressure_monotonically_decreases(self):
        alts = [0, 1000, 5000, 11000, 20000, 32000, 50000, 71000, 84852, 90000]
        p = [isa_pressure(h) for h in alts]
        assert all(p[i] > p[i + 1] for i in range(len(p) - 1))
        assert all(v > 0 for v in p)

    def test_combustion_module_uses_helpers(self):
        """calculate_altitude_performance artık satır-içi ISA kopyası
        kullanmıyor: raporlanan basınç isa_pressure ile birebir."""
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        from hrma.constants import BAR_PER_PA
        analyzer = CombustionAnalyzer()
        motor = {
            'chamber_pressure': 20.0,
            'gas_constants': {'exit': 300.0},
            'conditions': {'exit': {'P': 1.0, 'T': 1500.0}},
            'performance': {'velocities': {'exit': 2000.0}, 'c_star': 1500.0},
            'gamma_avg': 1.2,
            'mdot_total': 1.0,
        }
        out = analyzer.calculate_altitude_performance(motor, [0, 5000, 15000])
        for row in out['altitude_performance']:
            assert row['pressure'] == pytest.approx(
                isa_pressure(row['altitude']) * BAR_PER_PA, rel=1e-12)
            assert row['temperature'] == pytest.approx(
                isa_temperature(row['altitude']), rel=1e-12)


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
