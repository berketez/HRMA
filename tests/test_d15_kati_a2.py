"""ÖH Dalga-15 · kulvar 'kati' · aşama 2 — onarım bekçileri.

Sekiz kalem: P2B3-01, P2B3-02, P2B4-02, P2B4-03 (+P2B3-07),
P2B4-05 (+P2B4-06), P2B1-01 (ENGELLİ — kilidi sınar), P2B1-05, P2B1-06.

Her sınıf, onarım geçici olarak geri alındığında KIRMIZI olacak biçimde
yazılmıştır (ters-mutasyon kanıtı: docs/scofield/raw/OH/D15/kati/a2/
mutasyon.py + mutasyon_sonuc.json).
"""
import contextlib
import io

import numpy as np
import pytest

from hrma.engines.solid_rocket_engine import (
    SOLID_CONDENSED_MASS_FRACTION,
    SOLID_COST_PARAMS,
    SOLID_DEFAULT_GEOMETRY_MM,
    SOLID_PROPELLANT_COST_FAMILY,
    SolidRocketEngine,
)
from hrma.utils.numeric_compat import trapezoid


@pytest.fixture
def cea_kapali(monkeypatch):
    """V301/N-CEA-2: NASA CEA kapalı — katı motor katalog (tek basınçlı)
    termokimyasına BEYANLA döner (desen ``tests/test_d17_kati_a1.py``).
    Motor ⟷ katalog TEK KAYNAK öncülü bu yedek yolda korunur; CEA yolu
    ``tests/test_v301_n_cea2.py``de."""
    from hrma.engines import cea_bridge
    monkeypatch.setattr(cea_bridge, 'is_rocketcea_available', lambda: False)


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(**kw):
    # V301/T-ÇAPA-A: çekirdek 30 mm -> tek tanım (SOLID_DEFAULT_GEOMETRY_MM,
    # 48 mm). Eski Ø100/500/30 @ 40 bar BATES portu boğuluyordu
    # (A_p/A_t 0,947) ve K-A'nın port kapısından 422 alıyor; bu dosyadaki
    # sınıfların konusu boğulan port değil (K-A RAPOR §6, kural 1).
    ov = kw.pop('overrides', None)
    p = dict(grain_type='bates', propellant_type='apcp',
             chamber_diameter=SOLID_DEFAULT_GEOMETRY_MM['chamber_diameter'],
             grain_length=SOLID_DEFAULT_GEOMETRY_MM['grain_length'],
             core_diameter=SOLID_DEFAULT_GEOMETRY_MM['core_diameter'],
             chamber_pressure=40)
    p.update(kw)
    if ov is not None:
        p['overrides'] = dict(ov)
    return SolidRocketEngine(**p)


#: V301/T-ÇAPA-A: ``burn_rate_a=0.005`` (katalog APCP a'sının ~2,24 katı)
#: çözücüye daha büyük bir boğaz boyutlandırtır; tek tanımın 48 mm çekirdeği
#: bu hızda BATES/slotted/wagon_wheel'de boğulur (BATES A_p/A_t 0,958, 422).
#: 76 mm, aynı motorda ölçülen A_p/A_t 2,218 verir (K-A'nın 48 mm için
#: seçtiği 2,211 payıyla aynı; 72 mm 2,006, 74 mm 2,111). Ölçüm: T-ÇAPA-A
#: RAPOR. Bu sınıfların konusu web tanımıdır, boğulan port değil.
HIZLI_YAKIT_CEKIRDEK_MM = 76


# ===========================================================================
# P2B3-01 — star raporundaki yanma alanı ÇÖZÜCÜNÜN alanıdır
# ===========================================================================
class TestP2B3_01StarYanmaAlani:
    """Rapor ikinci bir alan modeli kurmaz; çözücünün Ab(0)'ını yayımlar."""

    GEOMETRILER = [
        (100, 30, 500, 6), (100, 30, 500, 5), (100, 30, 500, 8),
        (200, 60, 1000, 6), (75, 25, 300, 6),
    ]

    @pytest.mark.parametrize('D,dc,L,N', GEOMETRILER)
    def test_total_burning_area_cozucunun_ab0_idir(self, D, dc, L, N):
        e = _motor(grain_type='star', chamber_diameter=D, core_diameter=dc,
                   grain_length=L, overrides={'star_points': N})
        rapor = _sessiz(e._analyze_star_grain)
        ab0 = float(_sessiz(e.calculate_burn_area, 0.0))
        yayin = rapor['burning_surfaces']['total_burning_area']
        assert yayin == pytest.approx(ab0, rel=1e-12), (
            f'D={D} dc={dc} L={L} N={N}: rapor {yayin} ⟷ çözücü {ab0} '
            f'(oran {yayin / ab0:.4f}); ölçülen kusur bandı 0,629-0,881x idi')

    @pytest.mark.parametrize('D,dc,L,N', GEOMETRILER)
    def test_initial_core_area_kesit_degil_yanma_yuzeyidir(self, D, dc, L, N):
        e = _motor(grain_type='star', chamber_diameter=D, core_diameter=dc,
                   grain_length=L, overrides={'star_points': N})
        bs = _sessiz(e._analyze_star_grain)['burning_surfaces']
        yuzey = 2 * np.pi * (e.D_core / 2) * e.L_grain
        kesit = np.pi * (e.D_core / 2) ** 2
        assert bs['initial_core_area'] == pytest.approx(yuzey, rel=1e-12)
        # Port KESİTİ olmadığını ayrıca sına: 48-67 kat fark vardı.
        assert bs['initial_core_area'] != pytest.approx(kesit, rel=1e-6)

    @pytest.mark.parametrize('D,dc,L,N', GEOMETRILER)
    def test_terimler_toplama_kapanir(self, D, dc, L, N):
        e = _motor(grain_type='star', chamber_diameter=D, core_diameter=dc,
                   grain_length=L, overrides={'star_points': N})
        bs = _sessiz(e._analyze_star_grain)['burning_surfaces']
        assert (bs['initial_core_area'] + bs['star_enhancement_area']
                == pytest.approx(bs['total_burning_area'], rel=1e-12))

    def test_ayni_yanitta_tek_baslangic_alani(self):
        """throat_sizing ile CAD grain raporu AYNI sayıyı söyler."""
        r = _sessiz(_motor(grain_type='star').calculate_performance)
        ts = r['throat_sizing']['initial_burn_area_m2']
        cad = (r['cad_design']['grain_geometry']['burning_surfaces']
               ['total_burning_area'])
        assert cad == pytest.approx(ts, rel=1e-12), (
            f'aynı yanıtta iki başlangıç yanma alanı: {ts} ⟷ {cad}')


# ===========================================================================
# P2B3-02 — Monte Carlo, parçalı yasalı yakıtta da a/n toleransını uygular
# ===========================================================================
class TestP2B3_02MonteCarloPartiSacilimi:

    @pytest.mark.parametrize('yakit', ['kndx', 'knsb'])
    def test_lot_carpani_parcali_yolda_canli(self, yakit):
        taban = _motor(propellant_type=yakit)
        r0 = taban.burn_rate(40.0)
        olcekli = _motor(propellant_type=yakit)
        olcekli.pin_burn_rate_lot(scale=1.03, exponent_shift=0.0)
        assert olcekli.burn_rate(40.0) == pytest.approx(1.03 * r0, rel=1e-12)

    @pytest.mark.parametrize('yakit', ['kndx', 'knsb'])
    def test_us_kaymasi_tek_uslu_yolla_ozdes(self, yakit):
        """r' / r = P^d_n — tek üslü yasadaki a*P^(n+d) ile birebir aynı."""
        taban = _motor(propellant_type=yakit)
        r0 = taban.burn_rate(40.0)
        kaydirilmis = _motor(propellant_type=yakit)
        kaydirilmis.pin_burn_rate_lot(scale=1.0, exponent_shift=0.005)
        assert (kaydirilmis.burn_rate(40.0) / r0
                == pytest.approx(40.0 ** 0.005, rel=1e-12))

    def test_tek_uslu_yolda_cift_sayim_yok(self):
        """a/n zaten kurucudan geldiği için lot çarpanı APCP'ye UYGULANMAZ."""
        taban = _motor()
        lotlu = _motor()
        lotlu.pin_burn_rate_lot(scale=1.03, exponent_shift=0.005)
        assert lotlu.burn_rate(40.0) == pytest.approx(taban.burn_rate(40.0),
                                                      rel=0, abs=0)

    def test_parcali_yakitin_sacilimi_olu_degil(self):
        """kndx yanma süresi saçılımı ölçülen ölü tabanın (%1,4164) üstünde."""
        mc = _sessiz(_motor(propellant_type='kndx').run_monte_carlo,
                     n_samples=120, seed=7)
        cv = mc['burn_time']['cv_percent']
        assert cv > 3.0, (
            f'kndx yanma süresi CV %{cv:.4f}; a/n ölüyken %1,4164 ölçülmüştü, '
            f'apcp (a/n canlı) %5,5489')

    def test_kunye_kosulan_analizle_ayrisamaz(self):
        """Parçalı yasada 'criteria' hangi yoldan uygulandığını söyler."""
        mc = _sessiz(_motor(propellant_type='kndx').run_monte_carlo,
                     n_samples=20, seed=1)
        assert mc['criteria_detail']['burn_rate_law'] == 'kndx'
        assert 'base rate scaled' in (
            mc['criteria_detail']['burn_rate_law_sampling'])
        assert 'kndx' in mc['criteria']
        duz = _sessiz(_motor().run_monte_carlo, n_samples=20, seed=1)
        assert duz['criteria_detail']['burn_rate_law'] is None
        assert 'perturbed directly' in (
            duz['criteria_detail']['burn_rate_law_sampling'])

    def test_pin_burn_rate_lot_gecersiz_girdiyi_reddeder(self):
        e = _motor(propellant_type='kndx')
        with pytest.raises(ValueError):
            e.pin_burn_rate_lot(scale=0.0)
        with pytest.raises(ValueError):
            e.pin_burn_rate_lot(scale=float('nan'))
        with pytest.raises(ValueError):
            e.pin_burn_rate_lot(exponent_shift=float('inf'))


# ===========================================================================
# P2B4-02 — yayımlanan web grain tipini görür; burnout gerçekten tüketilendir
# ===========================================================================
class TestP2B4_02WebTanimlari:

    TIPLER = ['bates', 'star', 'end_burner', 'finocyl', 'slotted',
              'wagon_wheel']

    @pytest.mark.parametrize('gt', TIPLER)
    def test_burnout_fiilen_tuketilendir(self, gt):
        e = _motor(grain_type=gt, burn_rate_a=0.005,
                   core_diameter=HIZLI_YAKIT_CEKIRDEK_MM)
        r = _sessiz(e.calculate_performance)
        c = _sessiz(e.calculate_thrust_curve)
        tuketilen = float(trapezoid(np.asarray(c['burn_rate'], float),
                                   np.asarray(c['time'], float))) * 1000.0
        assert r['grain_design']['web_burnout_mm'] == pytest.approx(
            tuketilen, rel=1e-9), (
            f'{gt}: künye "the thickness ACTUALLY consumed" diyor')

    def test_end_burner_ekseneldir(self):
        """Radyal formül end-burner'da tanımsız: web = grain BOYU."""
        e = _motor(grain_type='end_burner')
        r = _sessiz(e.calculate_performance)
        assert r['grain_design']['web_thickness_mm'] == pytest.approx(
            e.L_grain * 1000.0)
        # Ölçülen kusur: 35,0 mm yazılıp 500,06 mm tüketiliyordu (14,3 kat).
        assert r['grain_design']['web_thickness_mm'] > 100.0

    def test_web_grain_tipine_duyarli(self):
        """Altı tip altı FARKLI web verir; tek bir sayı basılamaz."""
        webler = set()
        for gt in self.TIPLER:
            r = _sessiz(_motor(grain_type=gt).calculate_performance)
            webler.add(round(r['grain_design']['web_thickness_mm'], 6))
        assert len(webler) == len(self.TIPLER), (
            f'grain tipine kör web: {sorted(webler)}')

    @pytest.mark.parametrize('gt', TIPLER)
    def test_uc_buyukluk_ayri_yayimlanir(self, gt):
        r = _sessiz(_motor(grain_type=gt).calculate_performance)
        gd = r['grain_design']
        for alan in ('web_thickness_mm', 'web_available_mm', 'web_burnout_mm'):
            assert gd.get(alan) is not None, f'{gt}: {alan} eksik'
        assert 'ACTUALLY consumed' in gd['web_basis_note']

    def test_mevcut_web_kurali_tek_yerde(self):
        """_web_utilization_percent kendi kopyasını taşımaz.

        ÖH D15 a3 (P2B2-04) — BEKÇİ ÇEVRİLDİ. Bu test paydayı
        ``_max_web_thickness()`` diye ÇİVİLİYORDU; o büyüklük shapely'li
        tiplerde çözücünün TARAMA ÜST SINIRIDIR (kasa yarıçapı, bilerek
        geniş) ve kullanım yüzdesinin paydası olarak PORT YARIÇAPINI da
        yakıt sayar. Testin bu hâli kusuru KORUYORDU: tamamen tükenmiş
        star %56,08, slotted %45,67 gösterirken test yeşil kalıyordu.
        Testin ASIL amacı ("kural satır içi kopyalanmasın") korunuyor;
        değişen tek şey, hangi TEK kaynağın çivilendiği —
        ``_available_web_thickness()`` (port yüzeyinden kasaya kalan et).
        """
        for gt in self.TIPLER:
            e = _motor(grain_type=gt, burn_rate_a=0.005,
                   core_diameter=HIZLI_YAKIT_CEKIRDEK_MM)
            c = _sessiz(e.calculate_thrust_curve)
            tuketilen = float(trapezoid(np.asarray(c['burn_rate'], float),
                                       np.asarray(c['time'], float)))
            beklenen = min(100.0,
                           100.0 * tuketilen / e._available_web_thickness())
            assert e._web_utilization_percent(c) == pytest.approx(
                beklenen, rel=1e-12), gt

    def test_star_raporu_grain_design_ile_ayni_webi_soyler(self):
        e = _motor(grain_type='star')
        r = _sessiz(e.calculate_performance)
        rapor = _sessiz(e._analyze_star_grain)
        assert rapor['web_thickness'] == pytest.approx(
            r['grain_design']['web_thickness_mm'], rel=1e-12)


# ===========================================================================
# P2B4-03 (+P2B3-07) — Kn ve çıkış çapı ETKİN boğazdan
# ===========================================================================
class TestP2B4_03KnVeGenislemeOrani:

    CD = [1.00, 0.98, 0.90, 0.70]

    @pytest.mark.parametrize('cd', CD)
    def test_kn_basinci_ureten_alandan(self, cd):
        e = _motor(overrides={'discharge_coeff': cd})
        r = _sessiz(e.calculate_performance)
        c = _sessiz(e.calculate_thrust_curve)
        ab0 = float(_sessiz(e.calculate_burn_area, 0.0))
        beklenen = ab0 / float(c['throat_area'])
        assert r['grain_design']['Kn_initial'] == pytest.approx(
            beklenen, rel=1e-12), (
            f'Cd={cd}: yayımlanan Kn geometrik boğazdan geri okunuyor '
            f'(ölçülen sapma Cd=0,70de -%30)')

    @pytest.mark.parametrize('cd', CD)
    def test_cizilen_lulenin_gercek_epsilonu_yayimlanandir(self, cd):
        e = _motor(overrides={'discharge_coeff': cd})
        r = _sessiz(e.calculate_performance)
        c = _sessiz(e.calculate_thrust_curve)
        nd = r['cad_design']['nozzle_design']
        a_exit = np.pi * (nd['exit_diameter'] / 2000.0) ** 2
        gercek = a_exit / float(c['throat_area'])
        assert gercek == pytest.approx(nd['expansion_ratio'], rel=1e-9), (
            f'Cd={cd}: çizilen lülenin eps\'i {gercek:.4f}, yayımlanan '
            f'{nd["expansion_ratio"]:.4f} (ölçülen sapma Cd=0,70de +%42,86)')

    def test_cikis_capi_cd_den_bagimsizdir(self):
        """Çıkışta vena contracta yok: A_e = eps * A_t_ETKİN."""
        capilar = set()
        for cd in self.CD:
            r = _sessiz(_motor(overrides={'discharge_coeff': cd})
                        .calculate_performance)
            capilar.add(round(r['cad_design']['nozzle_design']
                              ['exit_diameter'], 9))
        assert len(capilar) == 1, f'çıkış çapı Cd ile oynuyor: {capilar}'

    def test_bogaz_capi_cd_ile_buyur(self):
        """İmal edilecek boğaz Cd ile büyümeye DEVAM eder (kardeş iddia)."""
        capilar = [round(_sessiz(_motor(overrides={'discharge_coeff': cd})
                                 .calculate_performance)['cad_design']
                         ['nozzle_design']['throat_diameter'], 9)
                   for cd in self.CD]
        assert capilar == sorted(capilar), capilar
        assert len(set(capilar)) == len(self.CD)

    def test_geometrik_etkin_ayrimi_beyan_edilir(self):
        r = _sessiz(_motor(overrides={'discharge_coeff': 0.98})
                    .calculate_performance)
        ts = r['throat_sizing']
        for alan in ('discharge_coefficient', 'throat_area_effective_m2',
                     'throat_area_geometric_m2',
                     'throat_diameter_effective_mm',
                     'throat_diameter_geometric_mm',
                     'expansion_ratio_effective', 'expansion_ratio_geometric',
                     'throat_area_basis'):
            assert alan in ts, f'throat_sizing içinde {alan} yok'
        assert ts['throat_area_geometric_m2'] == pytest.approx(
            ts['throat_area_effective_m2'] / 0.98, rel=1e-12)
        assert ts['expansion_ratio_geometric'] == pytest.approx(
            ts['expansion_ratio_effective'] * 0.98, rel=1e-12)

    def test_cd_verilmezse_davranis_degismez(self):
        a = _sessiz(_motor().calculate_performance)
        ts = a['throat_sizing']
        assert ts['discharge_coefficient'] == 1.0
        assert ts['throat_area_geometric_m2'] == pytest.approx(
            ts['throat_area_effective_m2'], rel=0, abs=0)


# ===========================================================================
# P2B4-05 (+P2B4-06) — tek hazne hacmi, kasadan kurulan toplam boy
# ===========================================================================
class TestP2B4_05HacimVeUzunluk:

    GAPLER = [0.0, 2.0, 20.0, 50.0]

    @pytest.mark.parametrize('gap', GAPLER)
    def test_tek_hacimsel_doluluk(self, gap):
        r = _sessiz(_motor(overrides={'grain_gap': gap}).calculate_performance)
        gd = r['grain_design']['volumetric_loading'] * 100.0
        adv = (r['advanced_performance']['mass_utilization']
               ['volumetric_efficiency_percent'])
        assert gd == pytest.approx(adv, rel=1e-9), (
            f'grain_gap={gap} mm: aynı yanıtta iki doluluk ({gd} ⟷ {adv})')

    @pytest.mark.parametrize('gap', GAPLER)
    def test_loading_density_de_araliklari_gorur(self, gap):
        e = _motor(overrides={'grain_gap': gap})
        r = _sessiz(e.calculate_performance)
        adv = r['advanced_performance']['mass_utilization']
        beklenen = r['propellant_mass'] / e._grain_envelope_volume()
        assert adv['loading_density_kgm3'] == pytest.approx(beklenen, rel=1e-9)

    @pytest.mark.parametrize('gap', GAPLER)
    def test_toplam_boy_kasa_arti_luledir(self, gap):
        e = _motor(overrides={'grain_gap': gap})
        r = _sessiz(e.calculate_performance)
        kd = r['design_summary']['key_dimensions']
        # V301/FİZİK-2 (kalem 6) — GEREKÇELİ: lüle terimi artık ÇİZİLEN
        # lüledir (CAD-2'nin tek tanımı; STEP/STL'in tek kontur örnekleyicisi,
        # konik lülede boğaz yayıyla çözücü boyundan biraz uzun). Bu sınıfın
        # iddiası (toplam = KASA + lüle; segment araları kasada) aynen.
        lule = kd['nozzle_drawn_length_mm']
        assert lule >= r['cad_design']['nozzle_design']['total_length'] - 1e-9
        assert kd['total_length_mm'] == pytest.approx(
            kd['motor_length_mm'] + lule, rel=1e-9), (
            f'grain_gap={gap} mm')

    @pytest.mark.parametrize('gap', GAPLER)
    def test_toplam_boy_kasadan_kisa_olamaz(self, gap):
        r = _sessiz(_motor(overrides={'grain_gap': gap}).calculate_performance)
        kd = r['design_summary']['key_dimensions']
        assert kd['total_length_mm'] > kd['motor_length_mm'], (
            f'grain_gap={gap} mm: motor kendi kasasından kısa bildiriliyor')

    def test_hacim_tek_kaynaktan(self):
        e = _motor(overrides={'grain_gap': 20.0})
        assert e._grain_envelope_volume() == pytest.approx(
            np.pi * (e.D_chamber / 2) ** 2 * (e._case_inner_length() - 0.1),
            rel=1e-12)


# ===========================================================================
# P2B1-01 — ENGELLİ. Kilidi ve ölçülen sapmayı sınar, KUSURU KİLİTLEMEZ.
# ===========================================================================
class TestP2B1_01KayitTutarliligi:
    """double_base kaydı Eq. 3-32 ile tutarsız; onarım İKİ dosya ister.

    Bu sınıf kusuru KORUMAZ: (a) motor ⟷ katalog TEK KAYNAK bağını sınar —
    onarım iki dosyada birlikte yapıldığında bu bağ korunur ve test yeşil
    kalır; (b) iki-fazlı gerekçesi OLAN kayıtların sapmasının beyanlı, tek
    fazlı kaydınkinin beyansız olduğunu ölçer. Sapma kapandığında (b)
    kendiliğinden yeşile döner (tek fazlı kayıt artık sapmaz).
    """

    @staticmethod
    def _eq332(gamma, T_c, mw):
        from hrma.data.propellants_db import cstar_from_thermo
        return cstar_from_thermo(gamma, T_c, mw)

    @pytest.mark.parametrize('yakit', ['apcp', 'sugar', 'knsu',
                                       'black_powder', 'double_base'])
    def test_motor_tablosu_katalogla_ayrisamaz(self, yakit, cea_kapali):
        """TEK KAYNAK: onarım yalnız bir dosyada yapılamaz."""
        from hrma.data.propellants_db import PROPELLANTS
        e = _motor(propellant_type=yakit)
        rec = PROPELLANTS[yakit]
        assert e.c_star == pytest.approx(rec['c_star'], rel=1e-9)
        assert e.gamma == pytest.approx(rec['gamma'], rel=1e-9)
        assert e.T_c == pytest.approx(rec['flame_temperature'], rel=1e-9)

    def test_tek_fazli_kayitlar_eq332_yi_saglamali(self):
        """Yoğuşmuş faz kesri 0 olan kayıt Eq. 3-32'yi sağlamak ZORUNDADIR.

        Bugün double_base bunu %15,64 ile İHLAL ediyor ve onarımı bu
        kulvarın sahası dışında (propellants_db.py). Borç imi olarak
        xfail(strict) ile durur; onarım dalgası imi kaldırır.
        """
        ihlal = []
        for yakit, kesir in SOLID_CONDENSED_MASS_FRACTION.items():
            if kesir != 0.0:
                continue
            try:
                e = _motor(propellant_type=yakit)
            except Exception:
                continue
            ideal = self._eq332(e.gamma, e.T_c, e.mw_exhaust)
            sapma = 100.0 * (e.c_star / ideal - 1.0)
            if abs(sapma) > 1.0:
                ihlal.append((yakit, round(sapma, 4)))
        assert not ihlal, f'tek fazlı kayıtta beyansız c* sapması: {ihlal}'

    def test_eq332_sapmasi_kapandi_ve_olculur(self):
        """Kalem kapanana kadar sapma bu sayıyla durur (kanıt kaydı)."""
        e = _motor(propellant_type='double_base')
        ideal = self._eq332(e.gamma, e.T_c, e.mw_exhaust)
        sapma = 100.0 * (e.c_star / ideal - 1.0)
        assert SOLID_CONDENSED_MASS_FRACTION['double_base'] == 0.0
        # Sapma ya ölçülen değerdedir (engel sürüyor) ya da kapanmıştır.
        assert sapma == pytest.approx(-15.6439, abs=1e-3) or abs(sapma) <= 1.0


# ÖH D15 P2B1-01 ONARILDI (ana model, 1 Eyl 2026): xfail(strict) borç imi söküldü —
# double_base c* iki dosyada 1406,8; test_tek_fazli_kayitlar_eq332_yi_saglamali artık düz bekçi.


# ===========================================================================
# P2B1-05 — yakıt fiyatı aile eşlemesiyle çözülür, sessiz 'default' yok
# ===========================================================================
class TestP2B1_05YakitFiyati:

    def test_ayni_kimya_ayni_birim_fiyat(self):
        """sugar ⟷ knsu aynı formülasyon: 3,50 kat fiyat farkı olamaz."""
        birim = {}
        for yakit in ('sugar', 'knsu'):
            # V301/T-ÇAPA-A: maliyet kalemleri 0,1 USD'ye yuvarlanıyor; tek
            # tanımın 48 mm çekirdeğinde yakıt kütlesi küçülünce yuvarlama
            # payı tek başına 1e-3'ü aşıyor (ölçülen 1,04e-3). KN-şeker 40
            # bar'da 30 mm çekirdekte port GEÇERLİ (ölçülen A_p/A_t sugar
            # 1,663, knsu 1,568); konu aile fiyatıdır, geometri değil.
            r = _sessiz(_motor(propellant_type=yakit, core_diameter=30)
                        .calculate_performance)
            mat = r['cost_analysis']['material_costs_usd']
            birim[yakit] = mat['propellant'] / r['propellant_mass']
        assert birim['sugar'] == pytest.approx(birim['knsu'], rel=1e-3), birim

    def test_katalog_anahtari_kendi_ailesinden_fiyatlanir(self):
        """solid.html varsayılanı 'htpb_ap_al' çözer; APCP fiyatı almalı."""
        birim = {}
        for yakit in ('htpb_ap_al', 'apcp'):
            r = _sessiz(_motor(propellant_type=yakit).calculate_performance)
            mat = r['cost_analysis']['material_costs_usd']
            birim[yakit] = mat['propellant'] / r['propellant_mass']
        assert birim['htpb_ap_al'] == pytest.approx(birim['apcp'], rel=1e-3)

    def test_esleneyen_yakit_fiyatlanmaz(self):
        """double_base fiyat ailesine ait değil: sessiz 'default' YASAK."""
        r = _sessiz(_motor(propellant_type='double_base')
                    .calculate_performance)
        mat = r['cost_analysis']['material_costs_usd']
        assert mat['propellant'] is None
        assert mat['total_materials'] is None
        assert 'propellant' in mat['unpriced_items']
        assert 'not_priced' in mat['propellant_cost_basis']

    def test_fiyat_satiri_beyan_edilir(self):
        r = _sessiz(_motor(propellant_type='apcp').calculate_performance)
        mat = r['cost_analysis']['material_costs_usd']
        assert 'SOLID_PROPELLANT_COST_FAMILY' in mat['propellant_cost_basis']
        assert mat['unpriced_items'] == []

    def test_aile_tablosu_gercek_fiyat_satirlarina_bakar(self):
        satirlar = set(SOLID_COST_PARAMS['propellant_usd_per_kg'])
        for anahtar, aile in SOLID_PROPELLANT_COST_FAMILY.items():
            assert aile in satirlar, f'{anahtar} -> {aile} satırı yok'
            assert aile != 'default', f'{anahtar} sessiz varsayılana bakıyor'

    def test_sessiz_default_a_dusen_katalog_yakiti_kalmadi(self):
        """Fiyatlanan her katalog yakıtı KENDİ ailesinden fiyatlanır."""
        from hrma.data.propellants_db import PROPELLANTS
        sessiz = [k for k in PROPELLANTS
                  if k not in SOLID_PROPELLANT_COST_FAMILY]
        # Eşlenmeyen tek yakıt double_base'dir ve o FİYATLANMAZ (test üstte).
        assert sessiz == ['double_base'], sessiz


# ===========================================================================
# P2B1-06 — unwired_inputs beyanı çürümez
# ===========================================================================
class TestP2B1_06BeyanCurumesi:

    def test_canli_alanlar_olu_ilan_edilemez(self):
        beyan = _sessiz(_motor(grain_type='star').unwired_inputs)
        olu = beyan['geometry_not_modelled']
        for alan in ('star_radius', 'fin_length'):
            assert alan not in olu, (
                f'{alan} "modellenmiyor" ilan edilmiş ama canlı')

    @pytest.mark.parametrize('alan,gt,degerler,esik', [
        ('star_radius', 'star', (5.0, 15.0), 5.0),
        ('fin_length', 'finocyl', (5.0, 20.0), 5.0),
    ])
    def test_alanlar_gercekten_canli(self, alan, gt, degerler, esik):
        """Beyanın kaldırılması haklı: alan itkiyi ölçülür biçimde oynatır."""
        itkiler = []
        for v in degerler:
            r = _sessiz(_motor(grain_type=gt,
                               overrides={alan: v}).calculate_performance)
            itkiler.append(r['average_thrust'])
        salinim = 100.0 * (max(itkiler) / min(itkiler) - 1.0)
        assert salinim > esik, f'{alan}: salınım %{salinim:.2f}'

    def test_star_fillet_gercekten_olu(self):
        """Beyanın KALAN yarısı doğru: üç değerde bit-aynı sonuç."""
        sonuc = set()
        for v in (1.0, 5.0, 10.0):
            r = _sessiz(_motor(grain_type='star',
                               overrides={'star_fillet': v})
                        .calculate_performance)
            sonuc.add(repr(r['average_thrust']))
        assert len(sonuc) == 1, sonuc

    def test_cozulen_uc_yaricapi_yayimlanir(self):
        """Ad ⟷ davranış farkı SAYIYLA görünür (girilen 4,000x'e kadar)."""
        # V301/T-ÇAPA-A: eski çapa (5->20, 15->30, 30->43) 30 mm çekirdekte
        # ölçülmüştü; orada star_radius=5 portu boğuluyor (ölçülen A_p/A_t
        # 0,991 -> 422). 40 mm çekirdek: A_p/A_t 1,662 (36 mm 1,372). Yeni
        # çapa aynı bağıntıyla ölçüldü: uç = çekirdek/2 + derinlik ->
        # 20+5, 20+15, 20+24 (30 mm derinlik 24,0'a kırpılıyor).
        for girilen, beklenen in ((5.0, 25.0), (15.0, 35.0), (30.0, 44.0)):
            e = _motor(grain_type='star', core_diameter=40,
                       overrides={'star_radius': girilen})
            gd = _sessiz(e.calculate_performance)['grain_design']
            assert gd['star_tip_radius_mm'] == pytest.approx(beklenen,
                                                             rel=1e-9)
            assert gd['star_tip_radius_mm'] == pytest.approx(
                (e.D_core / 2.0) * 1000.0 + gd['point_depth'], rel=1e-12)
        assert 'RADIAL DEPTH' in gd['point_depth_basis']

    def test_sessiz_kirpma_beyan_edilir(self):
        """star_radius=40 mm sessizce 28,0 mm'ye kırpılıyordu."""
        # V301/T-ÇAPA-A: 28,0 mm kırpma 30 mm çekirdekte ölçüldü; star
        # portu orada geçerli (K-A RAPOR §6).
        e = _motor(grain_type='star', core_diameter=30,
                   overrides={'star_radius': 40.0})
        gd = _sessiz(e.calculate_performance)['grain_design']
        assert 'star_radius' in gd['clipped_inputs']
        assert gd['point_depth'] == pytest.approx(28.0, rel=1e-9)
        temiz = _sessiz(_motor(grain_type='star', core_diameter=30,
                               overrides={'star_radius': 10.0})
                        .calculate_performance)['grain_design']
        assert temiz['clipped_inputs'] == []

    def test_varsayilana_dusus_beyan_edilir(self):
        gd = _sessiz(_motor(grain_type='star').calculate_performance)[
            'grain_design']
        assert set(gd['assumed_defaults']) == {'star_points', 'star_radius'}
