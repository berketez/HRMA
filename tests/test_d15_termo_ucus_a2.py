"""ÖH Dalga-15 · kulvar ``termo-ucus`` · aşama 2 — BEKÇİLER.

Her sınıf bir kalemin ONARIMINI kilitler. Bekçilerin tamamı ters-mutasyonla
kırmızıya çevrilerek doğrulanmıştır (kanıt:
``docs/scofield/raw/OH/D15/termo-ucus/a2/04_mutasyon.txt``): onarım geçici
olarak BAYT düzeyinde geri alınır, ilgili test KIRMIZI olur, bayt geri
yazılır, test YEŞİL olur.

Ölçüm betiği: ``docs/scofield/raw/OH/D15/termo-ucus/a2/olcum.py``
Önce/sonra sayılar: ``once.json`` / ``sonra.json`` (aynı dizin).
"""
import math

import numpy as np
import pytest

from hrma.analysis.acoustic_modes import analyze_from_engine_result
from hrma.analysis.heat_transfer_analysis import (
    HeatTransferAnalyzer, MissingHeatTransferInput)
from hrma.analysis.kinetic_efficiency import KineticEfficiency
from hrma.analysis.slosh_analysis import analyze_slosh
from hrma.analysis.water_hammer import WaterHammerAnalyzer


# =====================================================================
# P4B4-03 — su koçu: kullanıcı basınç sınıfı hoop akmasının üstünde
# =====================================================================
class TestSuKocuBasincSinifiAkmayiAsamaz:
    """Anma basınç sınıfı, modellenen cidarın akma basıncının ÜSTÜNDE
    SAFE sertifikası veremez.

    ÖLÇÜLDÜ (onarımdan önce; su, L=50 m, ID=25 mm, t=1,0 mm, P_iş=20 bar,
    ss_304, pipe_mawp_bar=400, hoop akma 172,000 bar):
        v= 6 m/s -> design_peak 176,5815 bar -> SAFE
        v= 8 m/s -> design_peak 228,7753 bar -> SAFE
        v=10 m/s -> design_peak 280,9691 bar -> SAFE
    Üçünde de akmaya dair TEK uyarı bile üretilmiyordu.
    """

    ORTAK = dict(fluid='water', line_length_m=50.0, line_id_mm=25.0,
                 wall_thickness_mm=1.0, working_pressure_bar=20.0,
                 pipe_material='ss_304')

    @pytest.mark.parametrize('v_flow', [6.0, 8.0, 10.0])
    def test_akma_ustunde_safe_verilemez(self, v_flow):
        o = WaterHammerAnalyzer().analyze(
            flow_velocity_m_s=v_flow, pipe_mawp_bar=400.0, **self.ORTAK)
        akma = o['pipe']['hoop_yield_pressure_bar']
        assert o['design_peak_pressure_bar'] > akma, (
            'fikstür geçersiz: tepe basınç akmanın üstünde olmalı')
        assert o['status'] == WaterHammerAnalyzer.STATUS_UNSAFE, (
            f"tepe {o['design_peak_pressure_bar']:.4f} bar akma {akma:.4f} "
            f"bar'ın üstünde ama hüküm {o['status']}")

    def test_akma_asimi_uyariyla_soylenir(self):
        o = WaterHammerAnalyzer().analyze(
            flow_velocity_m_s=10.0, pipe_mawp_bar=400.0, **self.ORTAK)
        assert any('yield' in w.lower() for w in o['warnings'])
        assert any('pipe_mawp_bar' in w for w in o['warnings'])

    def test_etkin_mawp_akmayla_kirpilir_ve_yayimlanir(self):
        o = WaterHammerAnalyzer().analyze(
            flow_velocity_m_s=10.0, pipe_mawp_bar=400.0, **self.ORTAK)
        p = o['pipe']
        assert p['mawp_bar'] == pytest.approx(400.0)
        assert p['mawp_effective_bar'] == pytest.approx(
            p['hoop_yield_pressure_bar'])
        assert p['mawp_capped_by_hoop_yield'] is True

    def test_sinif_akmanin_altindayken_davranis_degismez(self):
        """Regresyon kilidi: kırpma yalnız çelişkili hâlde devreye girer."""
        o = WaterHammerAnalyzer().analyze(
            flow_velocity_m_s=2.0, pipe_mawp_bar=120.0, **self.ORTAK)
        assert o['status'] == WaterHammerAnalyzer.STATUS_SAFE
        assert o['design_peak_pressure_bar'] == pytest.approx(
            72.19382707043358, rel=1e-9)
        assert o['pipe']['mawp_capped_by_hoop_yield'] is False
        assert o['pipe']['mawp_effective_bar'] == pytest.approx(120.0)


# =====================================================================
# P4B4-04 — çalkalanma: aynı yanıtta iki çalkalanan kütle
# =====================================================================
class TestCalkalanmaKutlesiTekKaynak:
    """``slosh_mass_kg`` ile ``fill_sweep.slosh_mass_kg[-1]`` AYNI doluluğu
    anlatır; ikisi de tek kütle kaynağından gelir.

    ÖLÇÜLDÜ (onarımdan önce, radius=0,5 fill_height=1,0 rho=1000
    liquid_mass=500): üst seviye 113,4797 kg ⟷ tarama sonu 178,2534 kg,
    fark 64,7738 kg (1,5708 kat), sıfır uyarı.
    """

    def test_liquid_mass_yogunlugu_ezince_tarama_da_ezmeyi_gorur(self):
        o = analyze_slosh(radius=0.5, fill_height=1.0,
                          fluid_density=1000.0, liquid_mass=500.0)
        ust = o['slosh_mass_kg']
        son = o['fill_sweep']['slosh_mass_kg'][-1]
        assert son == pytest.approx(ust, rel=1e-12), (
            f'aynı yanıtta iki çalkalanan kütle: {ust} ⟷ {son}')

    def test_liquid_mass_tek_basinayken_tarama_kutle_yayimlar(self):
        """İkinci yüz: kütle biliniyorsa tarama da kütle verebilmeli."""
        o = analyze_slosh(radius=0.5, fill_height=1.0, liquid_mass=500.0)
        assert 'slosh_mass_kg' in o['fill_sweep']
        assert o['fill_sweep']['slosh_mass_kg'][-1] == pytest.approx(
            o['slosh_mass_kg'], rel=1e-12)

    def test_tarama_kutlesi_derinlikle_dogrusal(self):
        o = analyze_slosh(radius=0.5, fill_height=1.0, liquid_mass=500.0)
        h = np.asarray(o['fill_sweep']['fill_height'], dtype=float)
        m_slosh = np.asarray(o['fill_sweep']['slosh_mass_kg'], dtype=float)
        oran = np.asarray(o['fill_sweep']['slosh_mass_ratio'], dtype=float)
        np.testing.assert_allclose(m_slosh, oran * 500.0 * h / 1.0, rtol=1e-12)

    def test_yalniz_yogunluk_tabani_degismedi(self):
        """Regresyon kilidi: ezme yokken sayı eskisiyle bit-aynı."""
        o = analyze_slosh(radius=0.5, fill_height=1.0, fluid_density=1000.0)
        assert o['slosh_mass_kg'] == pytest.approx(
            178.25343032069424, rel=1e-12)
        assert o['fill_sweep']['slosh_mass_kg'][-1] == pytest.approx(
            178.25343032069424, rel=1e-12)

    def test_kutle_hic_bilinmiyorsa_sayi_uydurulmaz(self):
        o = analyze_slosh(radius=0.5, fill_height=1.0)
        assert o['slosh_mass_kg'] is None
        assert 'slosh_mass_kg' not in o['fill_sweep']


# =====================================================================
# P4B4-05 — kinetik verim: aynı alan adı, iki genişleme referansı
# =====================================================================
def _kinetik_cres():
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    return CombustionAnalyzer().analyze_combustion({'htpb': 100.0}, 'N2O',
                                                   6.0, 20.0)


def _kinetik_profil(st, pe_bar, n=60):
    t_e = st['exit']['temperature'] * (pe_bar / st['exit']['pressure']) ** 0.15
    xs = np.array([0.0, 0.10, 0.40])
    Ts = np.array([st['chamber']['temperature'],
                   st['throat']['temperature'], t_e])
    Ps = np.array([st['chamber']['pressure'],
                   st['throat']['pressure'], pe_bar]) * 1e5
    xg = np.linspace(0.0, 0.40, n)
    return {'x': xg.tolist(), 'T': np.interp(xg, xs, Ts).tolist(),
            'P': np.interp(xg, xs, Ps).tolist()}


class TestKinetikIspGenislemeReferansi:
    """Isp çiftinin hangi genişlemede kurulduğu ADIYLA yayımlanır; çağıranın
    lülesiyle uyuşmuyorsa sayı geri çekilir.

    ÖLÇÜLDÜ (onarımdan önce, htpb/N2O O/F=6 Pc=20 bar, profil çıkışı
    0,05 bar): engineering isp_shifting 231,6993 s ⟷ high_fidelity
    290,7203 s — %25,47 sapma, alan adları aynı, hiçbir etiket yok.
    """

    @pytest.fixture(scope='class')
    def cres(self):
        return _kinetik_cres()

    def test_referans_cikis_basinci_her_seviyede_yayimlanir(self, cres):
        r = KineticEfficiency().evaluate(
            combustion_results=cres, chamber_pressure=20.0,
            fidelity='engineering')
        d = r['diagnostics']
        assert d['isp_reference_exit_pressure_pa'] == pytest.approx(101325.0)
        assert d['isp_reference_source']
        # ÖH D18 fizik-a1 / F1 (B3-02): taban adı genişledi. Basınç hâlâ ISA
        # deniz seviyesine çapalı (F034 sözleşmesi), ama çıkış İSTASYONU
        # artık tek-γ bağıntısından değil kayan-denge izentropundan geliyor;
        # ad bunu söylüyor.
        assert d['isp_reference_basis'] == 'sea_level_default_equilibrium'

    def test_profil_referanstan_ayrilinca_isp_geri_cekilir(self, cres):
        st = cres['performance']['thermodynamic_properties']['stations']
        r = KineticEfficiency().evaluate(
            combustion_results=cres, chamber_pressure=20.0,
            fidelity='engineering', characteristic_length=1.0,
            throat_diameter=0.05,
            nozzle_profile=_kinetik_profil(st, 0.05))
        assert r['isp_shifting'] is None
        assert r['isp_frozen'] is None
        assert r['isp_predicted'] is None
        assert r['kinetic_loss_pct'] is None
        gerekce = r.get('isp_withheld_because') or ''
        assert '101325' in gerekce and '5000' in gerekce

    def test_profil_referansla_cakisinca_sayi_yayimlanir(self, cres):
        """Modülün KENDİ temiz noktası: iki basınç aynıysa kapı açık kalır."""
        st = cres['performance']['thermodynamic_properties']['stations']
        r = KineticEfficiency().evaluate(
            combustion_results=cres, chamber_pressure=20.0,
            fidelity='engineering', characteristic_length=1.0,
            throat_diameter=0.05,
            nozzle_profile=_kinetik_profil(st, st['exit']['pressure']))
        assert r.get('isp_withheld_because') is None
        # ÇAPA TÜRETİMLİ YENİLENDİ — ÖH D19 hibrit-a1 (kalem B3-12).
        # Eski sayı, elemental ayrıştırmanın KÜTLE KORUMADIĞI koddan
        # geliyordu: pay (atom kütleleri) ile payda (molekül ağırlığı)
        # ayrı ayrı elle yazılıydı, HTPB'de Σ(kütle kesri)=1,001851852
        # (+%0,1852) ve kullanıcının 6,0 dediği O/F dengeye 5,990270
        # olarak giriyordu. D19'da molekül ağırlığı formülden ve
        # _ATOMIC_MASS (IUPAC 2021) tablosundan TÜRETİLDİ; Σ=1,0 ve
        # efektif O/F = istenen O/F oldu. Yeni sayı bu DOĞRU girdiden
        # gelir; yön fiziksel olarak beklenendir (yakıt payı %0,185
        # şişkinken karışım daha zengin görünüyordu, düzeltilince
        # stokiyometriye yaklaşıp yanma çözümü stokiyometriye yaklaştı).
        # Ölçüm: docs/scofield/raw/OH/D19/hibrit/a1/capa_yenileme.json
        # Eski çapa 231,69934435781875 s -> yeni 231,70742206965735 s
        # (+0,00808 s, +%0,0035). Kapının KENDİSİ (iki basınç aynıysa sayı
        # yayımlanır) değişmedi; değişen yalnız yayımlanan sayıdır.
        # ÇAPA YENİLENDİ — kitap p1a B16 (karar §28-18 (a)): N₂O 293,15 K
        # doymuş SIVI giriş entalpisi. Kâhin: CEA kök denetimi
        # (docs/scofield/raw/OH/KITAP/p1a/kanit/tur2b/kahin_cea.json) +
        # önce/sonra (p1a rapor §12). Tolerans DEĞİŞMEDİ.
        #   isp_shifting 231,70742206965735 -> 227,9898428933753
        assert r['isp_shifting'] == pytest.approx(227.9898428933753,
                                                  rel=1e-9)

    def test_profil_verilmezse_davranis_degismez(self, cres):
        """Regresyon kilidi: profil yoksa belirsizlik de yok.

        isp_frozen ÇAPASI TÜRETİMLİ YENİLENDİ — ÖH D18 fizik-a1 / F1
        (B3-02). Eski çapa 223,48817666988433 s, CEA nfz=1 (ODA
        bileşimi tüm lülede donmuş) değeriydi. Sektörün kötümser referansı
        nfz=2'dir (oda+boğaz denge, boğazdan sonra donmuş; NASA RP-1311
        Part II; RPA v2.3 s.19), bu yüzden ``isp_frozen`` artık ona
        bağlıdır ve kinetik verim bandı frozen@throat–eq olur. Eski sayı
        SİLİNMEDİ: aynı yanıtta ``performance.isp_frozen_chamber`` olarak
        BİREBİR duruyor (223,488177 s) — aşağıda denetleniyor.
        isp_shifting DEĞİŞMEDİ (2e-13 bağıl): ε'suz yolda çıkış basıncı
        yine ISA deniz seviyesi, enerji denklemi aynı.
        """
        r = KineticEfficiency().evaluate(
            combustion_results=cres, chamber_pressure=20.0,
            fidelity='engineering', characteristic_length=1.0,
            throat_diameter=0.05)
        assert r.get('isp_withheld_because') is None
        # ÇAPA TÜRETİMLİ YENİLENDİ — ÖH D19 hibrit-a1 (kalem B3-12).
        # Eski sayılar, elemental ayrıştırmanın KÜTLE KORUMADIĞI koddan
        # geliyordu (HTPB'de Σ(kütle kesri)=1,001851852, dengeye giren O/F
        # 6,0 yerine 5,990270). D19'da molekül ağırlığı formülden ve
        # _ATOMIC_MASS (IUPAC 2021) tablosundan türetildi; Σ=1,0 ve efektif
        # O/F = istenen O/F oldu. Eski -> yeni:
        #   isp_frozen         227,29291289317993 -> 227,26756696545525
        #   isp_shifting       231,69934435781875 -> 231,70742206965735
        #   isp_frozen_chamber 223,48817666988433 -> 223,4520734187225
        # D18/F1'in nfz=2 sözleşmesi KORUNDU: isp_frozen hâlâ BOĞAZ
        # değeridir ve isp_frozen_chamber'dan (nfz=1) büyüktür.
        # Ölçüm: docs/scofield/raw/OH/D19/hibrit/a1/capa_yenileme.json
        # ÇAPA YENİLENDİ — kitap p1a B16 (karar §28-18 (a)): N₂O 293,15 K
        # doymuş SIVI giriş entalpisi. Kâhin: CEA kök denetimi
        # (docs/scofield/raw/OH/KITAP/p1a/kanit/tur2b/kahin_cea.json) +
        # önce/sonra (p1a rapor §12). Tolerans DEĞİŞMEDİ.
        #   isp_frozen   227,26756696545525 -> 224,35096688502733
        #   isp_shifting 231,70742206965735 -> 227,9898428933753
        assert r['isp_frozen'] == pytest.approx(224.35096688502733, rel=1e-9)
        assert r['isp_shifting'] == pytest.approx(227.9898428933753,
                                                  rel=1e-9)
        perf = cres['performance']
        # ÇAPA YENİLENDİ — kitap p1a B16: isp_frozen_chamber
        # 223,4520734187225 -> 220,83981681638403 (kâhin yukarıda).
        assert perf['isp_frozen_chamber'] == pytest.approx(220.83981681638403,
                                                           rel=1e-9)
        assert perf['isp_frozen_throat'] == pytest.approx(r['isp_frozen'],
                                                          rel=1e-9)


# =====================================================================
# P4B4-06 — akustik kavite hibrit kamara DIŞ çapını alıyor
# =====================================================================
_AKUSTIK_VAKALAR = [
    ('F=1kN/20bar', 0.078860, 0.683, 0.00128793),
    ('F=5kN/35bar', 0.140000, 1.100, 0.00674000),
    ('F=0.3kN/15bar', 0.045000, 0.400, 0.00023700),
]


def _akustik_motor(d_ch, l_ch, v_free=None):
    er = {
        'chamber_temperature': 3200.0, 'gamma': 1.19,
        'molecular_weight': 25.5, 'chamber_diameter': d_ch,
        'chamber_length': l_ch, 'chamber_pressure': 20.0,
    }
    if v_free is not None:
        er['chamber_volume_actual_m3'] = v_free
    return er


class TestAkustikEsdegerKavite:
    """Kavite, motorun yayımladığı GERÇEK serbest gaz hacmini korur.

    ÖLÇÜLDÜ (onarımdan önce): pi/4*D_ch^2*L kavitesi gerçek serbest gaz
    hacminin 2,5902 / 2,5123 / 2,6843 katıydı; 1T frekansı 8.281,1 ⟷
    13.327,6 Hz (1,6094 kat DÜŞÜK), 4.664,6 ⟷ 7.393,6 (1,5850),
    14.512,1 ⟷ 23.776,3 (1,6384). Doğru reçete depoda katı motorda vardı.
    """

    @pytest.mark.parametrize('ad,d_ch,l_ch,v_free', _AKUSTIK_VAKALAR)
    def test_kavite_gercek_hacmi_korur(self, ad, d_ch, l_ch, v_free):
        o = analyze_from_engine_result(_akustik_motor(d_ch, l_ch, v_free))
        d_kul = float(o['inputs']['chamber_diameter'])
        hacim = math.pi / 4.0 * d_kul ** 2 * l_ch
        assert hacim == pytest.approx(v_free, rel=1e-9), (
            f'{ad}: kavite hacmi {hacim} ⟷ gerçek {v_free}')

    @pytest.mark.parametrize('ad,d_ch,l_ch,v_free', _AKUSTIK_VAKALAR)
    def test_esdeger_cap_kati_motorun_recetesiyle_ayni(self, ad, d_ch, l_ch,
                                                       v_free):
        o = analyze_from_engine_result(_akustik_motor(d_ch, l_ch, v_free))
        d_eq = 2.0 * math.sqrt(v_free / (math.pi * l_ch))
        assert float(o['inputs']['chamber_diameter']) == pytest.approx(
            d_eq, rel=1e-12)
        ek = o['equivalent_cavity']
        assert ek['diameter_source'] == 'free_gas_volume'
        assert ek['free_gas_volume_m3'] == pytest.approx(v_free, rel=1e-12)
        assert ek['nominal_chamber_diameter_m'] == pytest.approx(d_ch)

    def test_enine_frekans_anma_capiyla_dusuk_kalmaz(self):
        """1T frekansı eşdeğer kaviteden gelir (anma çapıyla düşük kalmaz).

        ÇEVRİLDİ (ÖH D26 / defter P4B4-14): bu satır 1T'yi varsayılan
        ``n_modes=10`` TABLOSUNDAN okuyordu. 1T'nin o tabloda bulunması
        fizik değil, mod havuzunun ``q<=6`` KIRPMASININ yan ürünüydü:
        kırpma kalkıp havuz eksiksizleşince bu ince/uzun eşdeğer kavitede
        ilk on mod gerçekten saf boyuna çıkıyor ve 1T listeye girmiyor
        (girmemesi doğru; 1T yok olmuyor, daha yüksek frekansta duruyor).
        Testin GERÇEK iddiası — 1T'nin ANMA çapıyla değil EŞDEĞER kaviteyle
        hesaplanması — sayı 13.327,6 Hz ile aynen korunur; yalnız modun
        okunduğu yer, kırpmadan bağımsız hâle getirilir.
        """
        ad, d_ch, l_ch, v_free = _AKUSTIK_VAKALAR[0]
        o = analyze_from_engine_result(_akustik_motor(d_ch, l_ch, v_free),
                                       n_modes=400)
        f_1t = next(m['frequency_hz'] for m in o['modes']
                    if m['label'] == '1T')
        assert f_1t == pytest.approx(13327.6, rel=2e-4)
        # Havuzun en düşük enine modu, tabloya girmese bile ADIYLA yayımlanır
        # ve aynı sayıyı taşır (varsayılan n_modes ile de erişilebilir).
        vars_ = analyze_from_engine_result(_akustik_motor(d_ch, l_ch, v_free))
        en_dusuk = vars_['stability_report']['high_frequency'][
            'lowest_transverse_mode']
        assert en_dusuk['label'] == '1T'
        assert en_dusuk['frequency_hz'] == pytest.approx(13327.6, rel=2e-4)

    def test_hacim_yayimlanmayan_motorda_sayi_uydurulmaz(self):
        """Fail-closed'un öteki yüzü: hacim yoksa eşdeğer kavite kurulmaz,
        anma çapı kullanıldığı künyede ADIYLA söylenir."""
        ad, d_ch, l_ch, _ = _AKUSTIK_VAKALAR[0]
        o = analyze_from_engine_result(_akustik_motor(d_ch, l_ch, None))
        assert float(o['inputs']['chamber_diameter']) == pytest.approx(d_ch)
        assert o['equivalent_cavity']['diameter_source'] == (
            'nominal_chamber_diameter')
        assert o['equivalent_cavity']['free_gas_volume_m3'] is None


# =====================================================================
# P4B1-08 / P4B1-09 — ısı transferi
# =====================================================================
_Z = np.linspace(0.0, 0.30, 61)
_R = np.where(_Z <= 0.10, 0.075 - 0.45 * _Z, 0.030 + 0.30 * (_Z - 0.10))
_MD_KONTUR = {
    'chamber_pressure': 60.0, 'chamber_temperature': 3400.0,
    'chamber_diameter': 0.15, 'chamber_length': 0.5,
    'burn_time': 20.0, 'mdot_total': 8.0,
    'nozzle_contour': {'points': [[float(a), float(b)]
                                  for a, b in zip(_Z, _R)]},
}


class TestIslakYuzeyIntegraliKonturuIzler:
    """Islak yüzey integrali, PROFİLİN kendi istasyon yarıçaplarını kullanır.

    ÖLÇÜLDÜ (onarımdan önce): kontur boğaz yarıçapı 30,000 mm, çözülen
    26,650 mm (ölçek 0,8883); ıslak lüle alanı modülün kurduğu 0,100876 m²
    ⟷ konturun kendisi 0,114891 m² -> %12,1983 EKSİK (güvensiz yön).
    """

    @pytest.fixture(scope='class')
    def profil(self):
        return HeatTransferAnalyzer().analyze_axial_profile(
            dict(_MD_KONTUR), n_stations=41)

    def test_profil_istasyon_yaricaplarini_yayimlar(self, profil):
        assert 'r_mm' in profil
        assert len(profil['r_mm']) == len(profil['x_mm'])

    def test_yayimlanan_yaricaplar_konturu_izler(self, profil):
        x = np.asarray(profil['x_mm'], dtype=float) / 1000.0
        r = np.asarray(profil['r_mm'], dtype=float) / 1000.0
        np.testing.assert_allclose(r, np.interp(x, _Z, _R), rtol=1e-9)

    def test_iki_bogaz_ayrisinca_islak_alan_konturun_alanidir(self, profil):
        x = np.asarray(profil['x_mm'], dtype=float) / 1000.0
        r_ger = np.interp(x, _Z, _R)
        ds = np.hypot(np.diff(x), np.diff(r_ger))
        a_ger = float(np.sum(2 * np.pi * 0.5 * (r_ger[1:] + r_ger[:-1]) * ds))
        # fikstür geçerliliği: iki boğaz GERÇEKTEN ayrışmalı
        assert abs(0.5 * profil['throat_diameter_m'] - 0.030) > 1e-4
        gs = HeatTransferAnalyzer().analyze_heat_transfer(
            dict(_MD_KONTUR))['gas_side_analysis']
        assert gs['nozzle_wetted_area'] == pytest.approx(a_ger, rel=1e-9), (
            f"ıslak alan {gs['nozzle_wetted_area']} ⟷ kontur {a_ger}")

    def test_bogazlar_cakisikken_taban_degismedi(self):
        """Regresyon kilidi: bugünkü hibrit yolunda ölçek 1,0."""
        md = dict(_MD_KONTUR)
        md['throat_diameter'] = 0.060
        gs = HeatTransferAnalyzer().analyze_heat_transfer(
            md)['gas_side_analysis']
        assert gs['nozzle_wetted_area'] == pytest.approx(
            0.1148908221624843, rel=1e-9)


class TestBogazBasparmakKuraliKaldirildi:
    """A_t = pi*(0,3*D_ch/2)^2 kuralı ne kodda ne de davranışta kalmıştır.

    ÖLÇÜLDÜ (onarımdan önce, Python API):
        analyze_axial_profile({'chamber_pressure':60,
            'chamber_temperature':3400,'mdot_total':0})
            -> throat_diameter_m = 0,03  (= 0,3 * uydurma D_ch 0,1)
        aynı gövde + chamber_diameter=0,5 -> 0,15
    """

    @pytest.mark.parametrize('ek,beklenen_eski', [
        ({}, 0.03),
        ({'chamber_diameter': 0.5}, 0.15),
    ])
    def test_bogaz_cozulemiyorsa_sayi_uydurulmaz(self, ek, beklenen_eski):
        md = {'chamber_pressure': 60.0, 'chamber_temperature': 3400.0,
              'mdot_total': 0}
        md.update(ek)
        with pytest.raises(MissingHeatTransferInput) as exc:
            HeatTransferAnalyzer().analyze_axial_profile(md, n_stations=11)
        assert 'throat' in str(exc.value).lower()
        assert any('throat' in a for a in exc.value.missing_fields)

    def test_bogaz_cozulebiliyorsa_profil_uretilir(self):
        """Regresyon kilidi: kapı yalnız çözülemeyen boğazda kapanır."""
        p = HeatTransferAnalyzer().analyze_axial_profile(
            dict(_MD_KONTUR), n_stations=11)
        assert p['throat_diameter_m'] == pytest.approx(
            0.05330089056494905, rel=1e-9)


class TestIsiyanTurKesirleriBeyanEdilir:
    """P4B1-10 kalıntısı — ana iddia ÇÜRÜTÜLDÜ (üç kompozisyon üç ayrı akı
    veriyor: 35,5089 / 35,7942 / 35,2639 MW/m²), ama kullanılan mol
    kesirleri yanıtta hiç görünmüyordu."""

    TABAN = {'chamber_pressure': 60.0, 'chamber_temperature': 3400.0,
             'chamber_diameter': 0.15, 'chamber_length': 0.5,
             'burn_time': 20.0, 'mdot_total': 8.0}

    def test_varsayilan_kompozisyon_adiyla_yayimlanir(self):
        gs = HeatTransferAnalyzer().analyze_heat_transfer(
            dict(self.TABAN))['gas_side_analysis']
        assert gs['radiation_x_H2O'] is not None
        assert gs['radiation_x_CO2'] is not None
        assert 'default' in gs['radiation_composition_source']

    def test_verilen_kompozisyon_yankilanir_ve_akiyi_degistirir(self):
        hta = HeatTransferAnalyzer()
        md = dict(self.TABAN)
        md.update({'x_H2O': 0.60, 'x_CO2': 0.00})
        gs = hta.analyze_heat_transfer(md)['gas_side_analysis']
        assert gs['radiation_x_H2O'] == pytest.approx(0.60)
        assert gs['radiation_composition_source'] == (
            'caller supplied x_H2O / x_CO2')
        taban = hta.analyze_heat_transfer(
            dict(self.TABAN))['gas_side_analysis']
        assert gs['heat_flux'] != pytest.approx(taban['heat_flux'], rel=1e-9)

    def test_varsayilana_esit_verilen_deger_de_cagiranindir(self):
        """Fable-D15 ŞARTı (ÖH D17'de yerine getirildi) — KENAR VAKA.

        Köken etiketi DEĞER eşitliğinden kurulamaz: çağıran açıkça
        ``DEFAULT_X_H2O``/``DEFAULT_X_CO2``a eşit bir kompozisyon
        gönderdiğinde alan VERİLMİŞTİR. Taban (2426b4d) burada
        'module default … no x_H2O/x_CO2 was supplied' diyordu.
        """
        from hrma.analysis.heat_transfer_analysis import (
            DEFAULT_X_CO2, DEFAULT_X_H2O)
        md = dict(self.TABAN)
        md.update({'x_H2O': DEFAULT_X_H2O, 'x_CO2': DEFAULT_X_CO2})
        gs = HeatTransferAnalyzer().analyze_heat_transfer(
            md)['gas_side_analysis']
        assert gs['radiation_composition_source'] == (
            'caller supplied x_H2O / x_CO2')
        # Sayılar değişmedi: yalnız KÖKEN hükmü düzeldi.
        taban = HeatTransferAnalyzer().analyze_heat_transfer(
            dict(self.TABAN))['gas_side_analysis']
        assert gs['heat_flux'] == pytest.approx(taban['heat_flux'], rel=0)
