"""Bebek-Scofield (17 Ağustos 2026) katı motor + yapısal bulgularının bekçisi.

Kapatılan üç kalem:

* **F2-1** — tek kapta İKİ (aslında üç) malzeme kimliği. Kasa etiketi
  ``steel_4130`` iken cidar 250 MPa ile boyutlandırılıyor, kopma basıncı
  4130'un 460/730 MPa'sıyla hesaplanıyor, yoğunluk ise hiçbir kayıtta
  bulunmayan 7800 kg/m³ oluyordu.
* **F2-2** — ``isp_vacuum`` ampirik log-fitten (``vacuum_isp_ratio``)
  geliyordu; o çarpan hazne basıncını görmediği için yanıtın KENDİ CF
  zinciriyle çelişiyordu.
* **F4-2** — yapısal hüküm (``status`` / ``risk_level``), modülün kendisinin
  "totolojik" diye işaretlediği emniyet katsayılarından türüyordu.

Bekçi ölçütü defterin kuralıdır: kusuru geri getiren bir değişiklik yapılırsa
bu dosyadaki testler KIRILMAK zorundadır.
"""

import re
from pathlib import Path

import numpy as np
import pytest

from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
from hrma.analysis.structural_analysis import (
    STRUCTURAL_APPROVAL_VERDICTS,
    STRUCTURAL_VERDICT_NOT_EVALUATED,
    StructuralAnalyzer,
)
import math


def _EMEKLI_AMPIRIK_FIT(epsilon: float, gamma: float = 1.22) -> float:
    """``hrma.constants.vacuum_isp_ratio``in EMEKLİ ampirik gövdesi.

    ÖH D22 · P10B3-16 — bu bekçi eskiden ``hrma.constants.vacuum_isp_ratio``i
    çağırıyordu ve "yayımlanan oran ona YAKINSAMASIN" diyordu. O fonksiyon bu
    dalgada ONARILDI: artık oda basıncını ZORUNLU alıyor ve tam izentropik Cf
    oranını veriyor (raporun beş ölçüm noktasını %0,002 içinde üretir). Yani
    bekçi, artık DOĞRU olan bir fonksiyondan uzak durulmasını istiyordu — yani
    KUSURU KORUYAN bir bekçiye dönüşmüştü.

    Bekçinin korumak istediği şey ise hâlâ geçerli: katı motorun oda
    basıncını GÖRMEYEN eski ampirik çarpanı geri gelmemeli. O yüzden referans
    artık emekli formülün BURADAKİ kopyasıdır — ürün koduna değil, kaldırılan
    yola bağlıdır ve onarılan fonksiyonla birlikte kaymaz.

    Emekli gövde (v2.6.27 öncesi ``constants.py``):
        ratio = 0.953 + 0.0405*ln(eps) + 0.005*(gamma - 1.2)
    """
    return 0.953 + 0.0405 * math.log(max(float(epsilon), 1.0)) \
        + 0.005 * (float(gamma) - 1.2)
from hrma.data.materials_db import get_material
from hrma.engines.solid_rocket_engine import (
    SOLID_CASE_DEFAULT_MATERIAL,
    SOLID_CASE_DESIGN,
    SolidRocketEngine,
)
from hrma.utils.numeric_compat import trapezoid

SOLID_ENGINE_SOURCE = (Path(__file__).resolve().parents[1]
                       / 'hrma' / 'engines' / 'solid_rocket_engine.py')

#: solid.html ``#case_material`` <select> seçenekleri (backend sözleşmesi).
UI_CASE_MATERIALS = ('steel', 'aluminum', 'composite', 'titanium')


@pytest.fixture(scope='module')
def varsayilan_sonuc():
    """Varsayılan katı motorun tam çözümü (APCP, 100/30 mm, 500 mm, 40 bar)."""
    return SolidRocketEngine().calculate_performance()


# ===========================================================================
# F2-1 — tek kapta TEK malzeme kimliği
# ===========================================================================
class TestF2_1MalzemeKimligi:
    """Kasa cidarını boyutlandıran dayanım ile kopma basıncını üreten
    dayanım AYNI malzeme kaydından gelmek zorundadır."""

    def test_varsayilan_malzeme_arayuzun_varsayilaniyla_ayni(self):
        """solid.html'in <select> ilk seçeneği ile motor varsayılanı aynı.

        ÖLÇÜLDÜ (HEAD f9d95eb): alan gönderilmeden burst = 341,13 bar,
        ``case_material='steel'`` ile 186,09 bar — aynı motor, 1,833 kat fark.
        Sebep varsayılanın 'steel_4130' etiketi taşımasıydı.
        """
        assert SOLID_CASE_DEFAULT_MATERIAL == 'steel'
        assert SOLID_CASE_DESIGN['material'] == SOLID_CASE_DEFAULT_MATERIAL
        assert SOLID_CASE_DEFAULT_MATERIAL in UI_CASE_MATERIALS

    def test_tasarim_sabitleri_malzeme_kaydindan_turer(self):
        """SOLID_CASE_DESIGN dayanım/yoğunluğu İKİNCİ KEZ tanımlamaz."""
        kayit = get_material(SOLID_CASE_DESIGN['material'])
        assert SOLID_CASE_DESIGN['yield_strength_pa'] == pytest.approx(
            float(kayit['yield_strength']), rel=0, abs=0)
        assert SOLID_CASE_DESIGN['case_density_kg_m3'] == pytest.approx(
            float(kayit['density']), rel=0, abs=0)

    def test_alan_gonderilmeyen_yol_ile_arayuz_yolu_ozdes(self):
        """Kimlik ayrışması tam olarak burada görünüyordu."""
        sessiz = SolidRocketEngine().calculate_performance()
        formdan = SolidRocketEngine(
            overrides={'case_material': 'steel'}).calculate_performance()
        for blok, alanlar in (
                ('safety_analysis', ('burst_pressure_bar', 'yield_pressure_bar',
                                     'case_material', 'case_wall_thickness_mm')),
                ('structural_analysis', ()),
        ):
            if blok == 'safety_analysis':
                a = sessiz[blok]['pressure_safety']
                b = formdan[blok]['pressure_safety']
                for alan in alanlar:
                    assert a[alan] == b[alan], (
                        f"'{alan}' alanı gönderilmeyen yolda farklı: "
                        f'{a[alan]} vs {b[alan]}')
        assert (sessiz['structural_analysis']['case_analysis']
                ['yield_strength_mpa']
                == formdan['structural_analysis']['case_analysis']
                ['yield_strength_mpa'])

    @pytest.mark.parametrize('malzeme', (None,) + UI_CASE_MATERIALS)
    def test_boyutlandirma_ve_kopma_ayni_dayanimi_kullanir(self, malzeme):
        """Yanıtın KENDİSİ iki dayanımı yan yana yayımlar ve eşit olmalı."""
        ov = None if malzeme is None else {'case_material': malzeme}
        r = SolidRocketEngine(overrides=ov).calculate_performance()
        ps = r['safety_analysis']['pressure_safety']
        ca = r['structural_analysis']['case_analysis']
        assert ps['case_yield_strength_mpa'] == pytest.approx(
            ca['yield_strength_mpa'], rel=1e-12)
        assert ps['burst_yield_strength_mpa'] == pytest.approx(
            ps['case_yield_strength_mpa'], rel=1e-12), (
            'Kopma basıncı, cidarı boyutlandıran dayanımdan BAŞKA bir '
            'dayanımla hesaplanmış — tek kapta iki malzeme kimliği geri geldi')
        assert ps['material_identity_consistent'] is True

    def test_yogunluk_da_ayni_kayittan_gelir(self):
        """7800 kg/m³ hiçbir malzeme kaydında yoktu (üçüncü kimlik)."""
        for malzeme in (None,) + UI_CASE_MATERIALS:
            ov = None if malzeme is None else {'case_material': malzeme}
            e = SolidRocketEngine(overrides=ov)
            beklenen = e._case_material_properties(e.case_material)['density']
            assert e._case_density() == pytest.approx(beklenen, rel=0, abs=0)

    def test_kopma_basinci_kap_cozucusuyle_bit_uyumlu(self, varsayilan_sonuc):
        """Motorun yayımladığı burst, aynı malzemeyle kap çözücüsünün değeri."""
        ps = varsayilan_sonuc['safety_analysis']['pressure_safety']
        pv = PressureVesselAnalyzer().analyze(
            meop_bar=max(ps['max_operating_pressure_bar'], 1e-6),
            inner_diameter_mm=100.0,
            material=ps['case_material'],
            wall_thickness_mm=ps['case_wall_thickness_mm'],
        )
        assert ps['burst_pressure_bar'] == pytest.approx(
            float(pv['actual_burst_pressure_bar']), rel=1e-12)
        assert ps['burst_yield_strength_mpa'] == pytest.approx(
            float(pv['derating']['room_temp_yield_strength_Pa']) / 1e6,
            rel=1e-12)

    def test_kimlik_ayrismasi_sessiz_kalamaz(self):
        """Kimlik ayrışırsa yanıt bunu bayrakla VE uyarıyla söyler.

        Ayrışma doğrudan üretilemediği için (düzeltme tam da onu engelliyor)
        motorun yayımladığı sözleşme sınanır: bayrak yanlışsa uyarı listesi
        boş kalamaz.
        """
        r = SolidRocketEngine().calculate_performance()
        ps = r['safety_analysis']['pressure_safety']
        assert 'material_identity_consistent' in ps
        assert 'material_identity_basis' in ps
        if not ps['material_identity_consistent']:
            assert any('identity' in str(u).lower()
                       for u in ps['vessel_warnings'])


# ===========================================================================
# F2-2 — vakum Isp'si yanıtın KENDİ CF zincirinden
# ===========================================================================
class TestF2_2VakumIsp:

    def test_ampirik_log_fit_ithal_edilmiyor(self):
        """``vacuum_isp_ratio`` katı motordan çıkarıldı — ithal geri gelemez.

        Docstring/yorum içindeki anma serbesttir; ithal ya da çağrı yasaktır.
        """
        kaynak = SOLID_ENGINE_SOURCE.read_text(encoding='utf-8')
        kod = re.sub(r'#.*', '', kaynak)
        # Üçlü tırnaklı blokları (docstring) çıkar
        kod = re.sub(r'"""(?:.|\n)*?"""', '', kod)
        kod = re.sub(r"'''(?:.|\n)*?'''", '', kod)
        assert 'vacuum_isp_ratio' not in kod, (
            'Ampirik vakum Isp çarpanı katı motora geri döndü; vakum Isp\'si '
            'motorun kendi CF zincirinden türemek zorunda')

    def test_vakum_cf_analitik_ozdeslige_uyuyor(self):
        """CF_vac_ideal - CF_SL_ekli_ideal = eps * (P_a/P_c) (Sutton 3-30/31).

        ÖLÇÜLDÜ: fark 2,8e-17 (çift duyarlıkta tam).
        """
        for pc in (20.0, 40.0, 80.0, 150.0):
            e = SolidRocketEngine(chamber_pressure=pc)
            durum = e._thrust_coefficient_state(pc)
            if durum['status'] != 'attached':
                continue
            eps = e._estimate_expansion_ratio()
            p_amb = float(getattr(e, 'ambient_pressure_bar', 1.01325))
            cf_vac_ideal = (e._thrust_coefficient_vacuum()
                            / e._total_nozzle_efficiency())
            assert cf_vac_ideal - durum['cf_attached_ideal'] == pytest.approx(
                eps * (p_amb / pc), rel=1e-10, abs=1e-12)

    def test_yayimlanan_isp_kendi_impuls_integralinden(self, varsayilan_sonuc):
        """isp_vacuum = I_vac / (m_p * g0), I_vac yanıtta yayımlı."""
        r = varsayilan_sonuc
        beklenen = (r['total_impulse_vacuum']
                    / (r['propellant_mass'] * 9.80665))
        assert r['isp_vacuum'] == pytest.approx(beklenen, rel=1e-12)
        # Oran, iki impuls integralinin oranıyla ÖZDEŞ olmalı: aynı kütle,
        # aynı örnekler, yalnız CF farkı.
        assert (r['isp_vacuum'] / r['isp_sea_level']) == pytest.approx(
            r['total_impulse_vacuum'] / r['total_impulse'], rel=1e-12)

    def test_vakum_impulsu_bagimsiz_yeniden_hesapla_ortusur(self):
        """Bekçi kendi integralini kurar: CF_vac x Pc x A_t."""
        e = SolidRocketEngine()
        r = e.calculate_performance()
        egri = e.calculate_thrust_curve()
        cf_vac = e._thrust_coefficient_vacuum()
        i_vac = float(trapezoid(
            cf_vac * np.asarray(egri['pressure'], dtype=float) * 1e5
            * np.asarray(egri['throat_area_series'], dtype=float),
            egri['time']))
        assert r['total_impulse_vacuum'] == pytest.approx(i_vac, rel=1e-9)
        assert r['thrust_coefficient_vacuum'] == pytest.approx(
            cf_vac, rel=1e-12)

    @pytest.mark.parametrize('pc,en_az_sapma_yuzde', [(20.0, 12.0),
                                                      (40.0, 8.0),
                                                      (80.0, 3.0)])
    def test_ampirik_fit_celiskisi_geri_gelirse_kirmizi(self, pc,
                                                        en_az_sapma_yuzde):
        """Eski ampirik yol geri gelirse yayımlanan oran ona EŞİTLENİR.

        ÖLÇÜLDÜ (yayımlanan oran vs ampirik fit): Pc = 20 bar'da %14,0,
        40 bar'da %10,2, 80 bar'da %4,8 sapma. Test sapmanın ALTINDA
        kalmamasını ister; ampirik yol geri dönerse sapma 0 olur ve kırılır.
        """
        e = SolidRocketEngine(chamber_pressure=pc)
        r = e.calculate_performance()
        oran = r['isp_vacuum'] / r['isp_sea_level']
        ampirik = _EMEKLI_AMPIRIK_FIT(r['expansion_ratio'], e.gamma)
        sapma = 100.0 * abs(oran - ampirik) / oran
        assert sapma >= en_az_sapma_yuzde, (
            f'Pc={pc} bar: yayımlanan vakum oranı ampirik log-fite '
            f'yakınsadı (sapma %{sapma:.2f}) — hazne basıncını görmeyen '
            'çarpan geri gelmiş olabilir')

    def test_vakum_isp_daima_deniz_seviyesinden_buyuk(self):
        """Ortam basıncını kaldırmak itkiyi ARTIRIR (basınç-itki terimi)."""
        for pc in (20.0, 40.0, 80.0, 150.0):
            r = SolidRocketEngine(chamber_pressure=pc).calculate_performance()
            assert r['isp_vacuum'] > r['isp_sea_level']

    def test_onerilen_vakum_lulesi_ayrimi_beyanli(self, varsayilan_sonuc):
        """expansion_ratio_vacuum BAŞKA bir lüledir; ayrım adıyla yazılır."""
        r = varsayilan_sonuc
        assert r['expansion_ratio_vacuum'] != pytest.approx(
            r['expansion_ratio'])
        beyan = r['expansion_ratio_vacuum_basis'].lower()
        assert 'suggested' in beyan
        assert r['isp_vacuum_basis']


# ===========================================================================
# F4-2 — yapısal hüküm totolojik SF'ye dayanamaz
# ===========================================================================
REF_MOTOR = {
    'chamber_pressure': 40.0, 'chamber_diameter': 0.1, 'chamber_length': 0.5,
    'throat_diameter': 0.02, 'thrust': 3000.0, 'burn_time': 3.0,
}


@pytest.fixture
def analyzer():
    return StructuralAnalyzer()


class TestF4_2YapisalHukum:

    @pytest.mark.parametrize('sf_hedef', (3.0, 4.0, 5.0))
    def test_boyutlandirma_modunda_onay_verilmiyor(self, analyzer, sf_hedef):
        """ÖLÇÜLDÜ: SF hedefi 3,0 -> min 3,000000 + 'ACCEPTABLE/LOW'.

        Yani kullanıcı hangi hedefi yazarsa yazsın kabul kararı çıkıyordu.
        """
        r = analyzer.analyze_structure(REF_MOTOR, design_safety_factor=sf_hedef)
        sa = r['safety_analysis']
        # Sayı hâlâ hedefin geri okunmasıdır — bunu bekçi de ölçer.
        assert sa['minimum_safety_factor'] == pytest.approx(sf_hedef, rel=1e-9)
        assert sa['binding_safety_factor_is_tautological'] is True
        assert sa['status'] not in STRUCTURAL_APPROVAL_VERDICTS, (
            'Totolojik emniyet katsayısından kabul kararı çıktı: '
            + str(sa['status']))
        assert sa['status'] == STRUCTURAL_VERDICT_NOT_EVALUATED
        assert sa['risk_level'] == STRUCTURAL_VERDICT_NOT_EVALUATED
        assert sa['verdict_withheld'] is True
        # Gerekçe modülün KENDİ adıyla durur (uç katmanı 'verdict_basis'
        # anahtarını kendi metniyle doldurduğu için çakışma yasak).
        assert 'No acceptance is issued' in (
            sa['minimum_safety_factor_verdict_basis'])

    def test_uyari_asla_bastirilmiyor(self, analyzer):
        """SF hedefi düşükse tehlike bildirimi GÖRÜNÜR kalır, geri çekilmez.

        Z4 onarımı (2026-08-27): eski biçim hedefin EKOSUNU ana hükme
        basıyordu (kusurun kendisi — P5B1-01). Yeni sözleşme: ana hüküm
        kazanılmamışsa NOT_EVALUATED + withheld; hedef-türevi tehlike
        ``design_target_assessment`` kanalında ADIYLA yayımlanır ve
        SUSTURULMAZ. Ölçülen: dta.status UNSAFE / HIGH, hedef 2,0.
        """
        r = analyzer.analyze_structure(REF_MOTOR, design_safety_factor=2.0)
        sa = r['safety_analysis']
        assert sa['binding_safety_factor_is_tautological'] is True
        assert sa['binding_safety_factor_reads_back_target'] is True
        assert sa['status'] == STRUCTURAL_VERDICT_NOT_EVALUATED
        assert sa['verdict_withheld'] is True
        dta = sa['design_target_assessment']
        assert dta['status'] == 'UNSAFE'
        assert dta['risk_level'] == 'HIGH'
        assert dta['design_safety_factor_target'] == pytest.approx(2.0)
        assert dta['target_derived_minimum_safety_factor'] == pytest.approx(2.0)

    def test_yalniz_hazne_cidari_yetmez_ve_bu_beyan_ediliyor(self, analyzer):
        """Eski kör nokta: lüle/kapak HEP 'size' modunda kalıyordu.

        ÖLÇÜLDÜ (SF hedefi 3,0): kullanıcı 2 / 5 / 10 mm gerçek cidar
        verdiğinde hazne SF'si 3,057 / 7,643 / 13,783'e çıkıyor ama
        yayımlanan minimum üçünde de 3,000 kalıyordu — kazanılan doğrulama
        totolojik iki aday tarafından maskeleniyordu.
        """
        oncekiler = []
        for t in (0.002, 0.005, 0.010):
            sa = analyzer.analyze_structure(
                REF_MOTOR, design_safety_factor=3.0,
                actual_wall_thickness=t)['safety_analysis']
            assert sa['binding_safety_factors'] and all(
                ad in ('nozzle', 'end_cap')
                for ad in sa['binding_safety_factors'])
            assert sa['binding_safety_factor_is_tautological'] is True
            assert sa['status'] == STRUCTURAL_VERDICT_NOT_EVALUATED
            # Kazanılmış minimum GÖRÜNÜR ve gerçek cidarla birlikte büyür.
            oncekiler.append(sa['minimum_earned_safety_factor'])
        assert oncekiler == sorted(oncekiler)
        assert oncekiler[-1] > oncekiler[0] * 2.0

    def test_gercek_kalinliklar_verilince_hukum_kazanilir(self, analyzer):
        """Üç kalınlık da verilirse hüküm bağımsız doğrulamadan gelir."""
        sonuc = {}
        for t in (0.002, 0.005, 0.010):
            sa = analyzer.analyze_structure(
                REF_MOTOR, design_safety_factor=3.0,
                actual_wall_thickness=t, actual_throat_thickness=t,
                actual_end_cap_thickness=3.0 * t)['safety_analysis']
            assert sa['binding_safety_factor_is_tautological'] is False
            assert sa['verdict_withheld'] is False
            sonuc[t] = sa['minimum_safety_factor']
        # Hüküm artık GERÇEK cidara tepki verir (eski davranışta hep 3,000).
        assert sonuc[0.002] < sonuc[0.005] < sonuc[0.010]
        assert sonuc[0.010] > 4.0

    def test_bogaz_kalinligi_argumani_gercekten_iletiliyor(self, analyzer):
        """v2.6.26'daki 'argüman destekleniyor ama geçirilmiyor' sınıfı."""
        ince = analyzer.analyze_structure(
            REF_MOTOR, design_safety_factor=3.0,
            actual_throat_thickness=0.001)['nozzle_analysis']
        kalin = analyzer.analyze_structure(
            REF_MOTOR, design_safety_factor=3.0,
            actual_throat_thickness=0.008)['nozzle_analysis']
        assert ince['design_mode'] == 'verify'
        assert kalin['design_mode'] == 'verify'
        assert ince['throat_thickness_used_mm'] == pytest.approx(1.0)
        assert kalin['safety_factor'] > ince['safety_factor'] * 4.0

    def test_kapak_kalinligi_argumani_gercekten_iletiliyor(self, analyzer):
        ince = analyzer.analyze_structure(
            REF_MOTOR, design_safety_factor=3.0,
            actual_end_cap_thickness=0.002)['end_cap_analysis']
        kalin = analyzer.analyze_structure(
            REF_MOTOR, design_safety_factor=3.0,
            actual_end_cap_thickness=0.020)['end_cap_analysis']
        assert ince['design_mode'] == 'verify'
        assert ince['head_thickness_used_mm'] == pytest.approx(2.0)
        assert kalin['head_thickness_used_mm'] == pytest.approx(20.0)
        # ANALİTİK ÖZDEŞLİK: önerilen tip 'dished' iken ASME UG-32(d) tersi
        #     sigma = P*(D/t + 0.2)/(2E)   ->   SF ~ 1/(D/t + 0.2)
        # D = 100 mm için oran (100/2 + 0,2)/(100/20 + 0,2) = 50,2/5,2.
        assert ince['recommended_type'] == kalin['recommended_type'] == 'dished'
        beklenen_oran = (100.0 / 2.0 + 0.2) / (100.0 / 20.0 + 0.2)
        assert (kalin['head_safety_factor'] / ince['head_safety_factor']
                == pytest.approx(beklenen_oran, rel=1e-9))

    def test_aday_bazli_totoloji_haritasi_yayimlaniyor(self, analyzer):
        """Hangi adayın kazanılmış olduğu adıyla okunabilmeli."""
        sa = analyzer.analyze_structure(
            REF_MOTOR, design_safety_factor=3.0,
            actual_wall_thickness=0.005)['safety_analysis']
        harita = sa['safety_factor_is_tautological']
        assert set(harita) == set(sa['safety_factors'])
        assert harita['chamber_hoop'] is False
        assert harita['chamber_von_mises'] is False
        assert harita['nozzle'] is True
        assert harita['end_cap'] is True

    def test_termal_tehlike_geri_cekilmis_hukmu_deler(self, analyzer):
        """Termal marj cidardan bağımsızdır: NOT_EVALUATED bir TAVANDIR."""
        sicak = dict(REF_MOTOR, chamber_temperature=3200.0)
        sa = analyzer.analyze_structure(
            sicak, design_safety_factor=4.0)['safety_analysis']
        assert sa['binding_safety_factor_is_tautological'] is True
        assert sa['status'] in ('MARGINAL', 'UNSAFE'), sa['status']
        assert sa['risk_level'] not in ('LOW', 'VERY LOW')

    def test_minimum_sf_hala_tum_adaylarin_minimumu(self, analyzer):
        """Sayı SİLİNMEZ: panel sözleşmesi ve uyarılar onu okuyor."""
        for kwargs in ({}, {'actual_wall_thickness': 0.005},
                       {'actual_wall_thickness': 0.005,
                        'actual_throat_thickness': 0.005,
                        'actual_end_cap_thickness': 0.015}):
            sa = analyzer.analyze_structure(
                REF_MOTOR, design_safety_factor=3.0,
                **kwargs)['safety_analysis']
            adaylar = [v for v in sa['safety_factors'].values()
                       if np.isfinite(v)]
            assert sa['minimum_safety_factor'] == pytest.approx(
                min(adaylar), rel=1e-9)


# ===========================================================================
# ÖH FAZ B (27 Ağustos 2026) — F4-2 ailesinin KÖR kaldığı iki eksen
# ===========================================================================
class TestF4_2TasinanBekciler:
    """TAŞINAN BEKÇİLER — ``TestF4_2YapisalHukum``a DOKUNULMADI.

    Yukarıdaki sınıf (iki yönlü bayrak sözleşmesi) mutasyonla tescil edilmiş
    SAĞLIKLI desendir ve olduğu gibi durur. Kampanyanın ölçtüğü iki körlük o
    sınıfın kapsamının DIŞINDA kaldığı için buraya, kardeş iddialar olarak
    yazılır:

    * ``P5B1-11`` — ``:350`` kapak kalınlığının ANALİZ bloğuna iletildiğini
      doğruluyor; aynı kalınlığın KÜTLE hesabına iletilmediğini görmüyor.
    * ``P5B1-17`` — ``:368`` totoloji haritasının YAYIMLANDIĞINI doğruluyor;
      haritanın DOĞRU olup olmadığını sormuyor.

    İkisi de yazıldıklarında ürün kusuru yüzünden kırmızıydı ve
    ``xfail(strict=True)`` borç imiyle duruyordu. ÖH D15 birleştirmesinde
    (1 Eyl 2026) İKİSİ DE ÖLÇÜLDÜ ve kusurların kapandığı görüldü; imler
    kaldırıldı ve testler artık DOĞRU davranışı kilitliyor. Ölçümler her
    testin kendi künyesinde durur.
    """

    # ÖH D15 birleştirme (1 Eyl 2026) — ``xfail(strict=True)`` BORÇ İMİ
    # KALDIRILDI. İm ÖH defter P5B1-11'i anıyordu: "``_calculate_weight``
    # kapak kalınlığını ``min(flat_head, dished_head)`` BOYUTLANDIRMA
    # değerlerinden okuyor, değerlendirilen ``head_thickness_used_mm``
    # alanını hiç okumuyor"; ölçümü de ``actual_end_cap_thickness`` =
    # 2 / 20 / 50 mm için ``end_caps_weight`` ÜÇÜNDE DE 0,265554 kg,
    # ``total_weight`` üçünde de 4,129509 kg idi.
    #
    # Kusur KAPANDI. Birleşik ağaçta aynı ölçüm (aynı REF_MOTOR, SF 3,0):
    #     2 mm  -> end_caps 0,270393 kg · total 4,134348 kg
    #    20 mm  -> end_caps 2,703932 kg · total 6,567887 kg
    #    50 mm  -> end_caps 6,759830 kg · total 10,623785 kg
    # Kütle kalınlıkla DOĞRUSAL (10 kat kalınlık -> 10 kat kapak kütlesi,
    # 25 kat -> 25 kat), yani değerlendirilen kalınlık artık kütle hesabına
    # da iletiliyor. Test bu davranışı kilitler; borç imi kalırsa ``strict``
    # XPASS ile kırmızı yanar ve kusur geri dönerse kimse göremez.
    @pytest.mark.parametrize('ince,kalin', [(0.002, 0.020), (0.002, 0.050)])
    def test_kapak_kalinligi_kutle_hesabina_da_iletiliyor(self, analyzer,
                                                          ince, kalin):
        """Değerlendirilen kapak kalınlığı kütleyi de belirlemeli.

        Kardeş bekçi (``:350``) argümanın ``end_cap_analysis``a ulaştığını
        kilitliyor; kütle kalemi aynı argümanı görmüyor ve motorun toplam
        kütlesi (dolayısıyla T/W) yanlış zemine oturuyor.
        """
        def _kos(t):
            r = analyzer.analyze_structure(
                REF_MOTOR, design_safety_factor=3.0,
                actual_end_cap_thickness=t)
            return r['end_cap_analysis'], r['weight_analysis']

        ec_i, w_i = _kos(ince)
        ec_k, w_k = _kos(kalin)
        # Kontrol: argüman ANALİZ bloğuna gerçekten iletiliyor (kardeş iddia).
        assert ec_i['head_thickness_used_mm'] == pytest.approx(ince * 1000)
        assert ec_k['head_thickness_used_mm'] == pytest.approx(kalin * 1000)
        assert ec_i['design_mode'] == ec_k['design_mode'] == 'verify'

        oran = kalin / ince
        assert w_k['end_caps_weight'] > w_i['end_caps_weight'], (
            f'{ince * 1000:.0f} mm ve {kalin * 1000:.0f} mm kapak ({oran:.0f} '
            f"kat) aynı kütleyi veriyor: {w_i['end_caps_weight']:.6f} kg — "
            'kütle hesabı değerlendirilen kalınlığı okumuyor')
        assert w_k['total_weight'] > w_i['total_weight']

    # ÖH D15 birleştirme (1 Eyl 2026) — ``xfail(strict=True)`` BORÇ İMİ
    # KALDIRILDI. İm, ÖH defter P5B1-17'yi anıyordu: "``safety_factor_is_
    # tautological`` bayrağı YALNIZ ``design_mode=='size'``e bakıyor",
    # ölçümü de şuydu — bayrak beş adayda da ``True`` iken sayılar
    # Pc=40 bar'da {chamber_hoop 5,7600 · chamber_von_mises 6,6511 ·
    # nozzle 4,8000 · end_cap 4,8000}, Pc=3000 bar'da {0,9741 · 0,5747 ·
    # 4,8000 · 4,8000}; yani hazne adayları tasarımla HAREKET ediyordu.
    #
    # Kusur yapısal kulvarda KAPANDI. Birleşik ağaçta AYNI ölçüm yeniden
    # alındı (aynı REF_MOTOR, SF hedefi 4,80, cidar verilmemiş):
    #   Pc=40   bayrak {chamber_hoop True · chamber_von_mises True ·
    #                   nozzle True · end_cap True · buckling_axial True}
    #   Pc=3000 bayrak {chamber_hoop False · chamber_von_mises False ·
    #                   nozzle True · end_cap True · buckling_axial False}
    # Yani hareket eden adaylar artık "totolojik" İDDİA EDİLMİYOR; işaretli
    # kalan ikisinin (nozzle, end_cap) sayısı iki koşuda da BİREBİR 4,8000 —
    # gerçekten girdinin geri okunması. Test bu davranışı kilitler; borç imi
    # kalırsa ``strict`` XPASS ile kırmızı yanar ve kapanan kusur geri
    # dönerse bunu KİMSE görmez.
    def test_totolojik_isaretli_aday_tasarimla_degismez(self, analyzer):
        """Bayrağın kendi tanımı sınanır: totoloji, girdinin geri okunmasıdır.

        İki koşu YALNIZ hazne basıncında ayrılır. Bir aday iki koşuda da
        "totolojik" işaretliyse sayısı DEĞİŞEMEZ; değişiyorsa o sayı girdinin
        geri okunması değildir ve bayrak fazla iddia ediyor demektir.
        """
        dusuk = analyzer.analyze_structure(
            dict(REF_MOTOR, chamber_pressure=40.0),
            design_safety_factor=4.8)['safety_analysis']
        yuksek = analyzer.analyze_structure(
            dict(REF_MOTOR, chamber_pressure=3000.0),
            design_safety_factor=4.8)['safety_analysis']

        h_d, h_y = (dusuk['safety_factor_is_tautological'],
                    yuksek['safety_factor_is_tautological'])
        ortak = [ad for ad in h_d if h_d[ad] and h_y.get(ad)]
        assert ortak, 'iki koşuda da totolojik işaretli aday yok — düzenek bozuk'

        sapan = {}
        for ad in ortak:
            a, b = dusuk['safety_factors'][ad], yuksek['safety_factors'][ad]
            if not np.isfinite(a) or not np.isfinite(b):
                continue
            if abs(b - a) > 1e-9 * max(1.0, abs(a)):
                sapan[ad] = (round(a, 4), round(b, 4))
        assert not sapan, (
            '"totolojik" işaretli adaylar tasarımla hareket ediyor '
            f'(Pc 40 -> 3000 bar): {sapan} — bayrak yalnız design_mode\'a '
            'bakıyor, sayının gerçekten girdinin geri okunması olup '
            'olmadığına bakmıyor')


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
