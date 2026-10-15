"""ÖH Dalga-26 / kulvar ``yapisal-sistem`` aşama 1 — bekçiler.

İki bölüm:

* **BEKÇİ BORCU** (``docs/scofield/raw/OH/D26/ana_model/p13b410_dagitim.json``,
  P13B4-10 dağıtımı): bu kulvara düşen ve doğrudan bekçisi olmayan KAPALI
  kalemlerin sembollerini doğrudan sınayan düğümler. Kalem yeniden AÇILMAZ;
  yalnız onarımın dosyada DURDUĞU kilitlenir.
* **P5B2-05 fizik çıpası**: patlama aşırı-basıncı artık elle yazılmış bir Z
  tablosundan değil Kinney-Graham bağıntısından türetiliyor; bağıntının
  yayımlanmış doğrulama düğümü, boyut tutarlılığı ve tekliği burada
  kilitlenir (kardeş bekçi ``tests/test_safety_honesty.py`` bağıntıyı
  BAĞIMSIZ kurup ürünün sayılarıyla karşılaştırır).

Kanıt dizini: ``docs/scofield/raw/OH/D26/yapisal-sistem/a1/``
(``once.json`` / ``sonra.json`` / ``mutasyon.json`` / ``rapor.md``).
"""

import ast
import contextlib
import io
import math
import pathlib

import pytest

from hrma.analysis.safety_analysis import (
    BLAST_OVERPRESSURE_TARGETS_KPA,
    KINNEY_GRAHAM_AMBIENT_KPA,
    SafetyAnalyzer,
    kinney_graham_overpressure_kpa,
    scaled_distance_for_overpressure,
)

KOK = pathlib.Path(__file__).resolve().parents[1]

MOTOR = {'motor_type': 'hybrid', 'chamber_pressure': 40,
         'chamber_temperature': 3000, 'thrust': 1000, 'burn_time': 10,
         'chamber_diameter': 0.1, 'wall_thickness': 0.005}

SAFETY_YUK = dict(MOTOR, propellant_mass=5, propellant_type='composite',
                  facility_type='test_stand')

REG_TABAN = {'burn_time': 10.0, 'mdot_ox': 1.0,
             'port_diameter_initial': 0.03, 'grain_length': 0.5}


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


# ===========================================================================
# P5B2-05 — Kinney-Graham bağıntısı: doğrulama düğümü + teklik + boyut
# ===========================================================================
class TestP5B205KinneyGraham:
    """Ürünün patlama mesafeleri artık ATIF VERDİĞİ modelden geliyor.

    ÖLÇÜLEN kusur (D26 tabanı 7751531, 5 kg hidrazin -> 2,1 kg TNT;
    ``once.json`` P5B2-05): elle yazılmış Z tablosu Kinney-Graham'a
    uymuyordu ve hepsi KISA taraftaydı — lethal %-12,7 (3,0734 m yerine
    3,5209 m; o mesafede 136,247 kPa), minor_injury %-20,9,
    property_damage %-52,8. ``serious_injury`` %-0,9 ile tesadüfen
    yakındı. Kodun yorumu "değerler konservatif (biraz büyük) tarafta"
    diyordu; ölçüm TERSİNİ söylüyordu.
    """

    def test_yayimlanmis_dogrulama_dugumu(self):
        """Z = 1 m/kg^(1/3) -> 1008 kPa (Kinney & Graham 1985, Böl. 5)."""
        assert kinney_graham_overpressure_kpa(1.0) == pytest.approx(
            1008.0, rel=0.01)

    def test_bagintisi_kesin_azalan_ve_cozum_tek(self):
        """Ters çözümün tekliği: P(Z) Z'de kesin azalandır."""
        onceki = None
        z = 0.05
        while z <= 400.0:
            deger = kinney_graham_overpressure_kpa(z)
            if onceki is not None:
                assert deger < onceki, z
            onceki = deger
            z *= 1.2

    @pytest.mark.parametrize('hedef', sorted(
        BLAST_OVERPRESSURE_TARGETS_KPA.values()))
    def test_ters_cozum_hedefi_geri_veriyor(self, hedef):
        z = scaled_distance_for_overpressure(hedef)
        assert kinney_graham_overpressure_kpa(z) == pytest.approx(
            hedef, rel=1e-9)

    def test_boyut_tutarliligi_hopkinson_cranz(self):
        """Z = R / W^(1/3): kütle k katına çıkarsa mesafe k^(1/3) katına.

        Boyut analizi ürünün SAYILARIYLA sınanır: bağıntı boyutsuzdur, tek
        boyutlu büyüklük Z'nin kendisidir (m·kg^(-1/3)).
        """
        a = SafetyAnalyzer()
        kucuk = _sessiz(a.analyze_comprehensive_safety, dict(MOTOR),
                        propellant_mass=5.0, propellant_type='composite')
        buyuk = _sessiz(a.analyze_comprehensive_safety, dict(MOTOR),
                        propellant_mass=40.0, propellant_type='composite')
        k = (buyuk['explosive_hazards']['tnt_equivalent_kg']
             / kucuk['explosive_hazards']['tnt_equivalent_kg'])
        for seviye in BLAST_OVERPRESSURE_TARGETS_KPA:
            d1 = kucuk['explosive_hazards']['blast_distances'][seviye][
                'distance_m']
            d2 = buyuk['explosive_hazards']['blast_distances'][seviye][
                'distance_m']
            assert d2 / d1 == pytest.approx(k ** (1.0 / 3.0), rel=1e-12), (
                seviye, d1, d2, k)

    def test_yayimlanan_kayit_dayanagini_tasiyor(self):
        a = SafetyAnalyzer()
        r = _sessiz(a.analyze_comprehensive_safety, dict(MOTOR),
                    propellant_mass=5.0, propellant_type='composite')
        W13 = float(r['explosive_hazards']['tnt_equivalent_kg']) ** (1 / 3)
        for seviye, kayit in r['explosive_hazards'][
                'blast_distances'].items():
            assert 'Kinney' in kayit['basis'], seviye
            assert kayit['scaled_distance_m_per_kg13'] == pytest.approx(
                kayit['distance_m'] / W13, rel=1e-12)
            assert kayit['overpressure_kpa'] == pytest.approx(
                BLAST_OVERPRESSURE_TARGETS_KPA[seviye])

    def test_aralik_disi_hedef_icin_sayi_UYDURULMAZ(self):
        with pytest.raises(ValueError) as ex:
            scaled_distance_for_overpressure(1e9)
        assert 'outside the bracket' in str(ex.value)
        for kotu in (0.0, -1.0, float('nan'), float('inf')):
            with pytest.raises(ValueError):
                scaled_distance_for_overpressure(kotu)

    def test_Z_tablosu_GERI_GELMEDI(self):
        """Mesafeler TÜRETİLİR: fonksiyonun gövdesinde eşik SAYI olmamalı.

        Eski gövde ``{'lethal': (100000, 2.4), ...}`` tablosunu taşıyordu.
        Onarımdan sonra ``_calculate_blast_distances`` içinde yalnız
        Hopkinson-Cranz üssü (1/3) ve sıfır kalır; her aşırı-basınç ve her
        Z, modül düzeyindeki TEK KAYNAKTAN gelir. Tablo geri konursa bu
        düğüm kırmızı düşer.
        """
        kaynak = (KOK / 'hrma' / 'analysis' / 'safety_analysis.py').read_text(
            encoding='utf-8')
        agac = ast.parse(kaynak)
        govde = None
        for dugum in ast.walk(agac):
            if (isinstance(dugum, ast.FunctionDef)
                    and dugum.name == '_calculate_blast_distances'):
                govde = dugum
        assert govde is not None
        sabitler = sorted({float(d.value) for d in ast.walk(govde)
                           if isinstance(d, ast.Constant)
                           and isinstance(d.value, (int, float))
                           and not isinstance(d.value, bool)})
        assert sabitler == [0.0, 1.0, 3.0], (
            f'_calculate_blast_distances gövdesinde beklenmedik sayı(lar): '
            f'{sabitler} — aşırı-basınç/Z tablosu geri mi geldi?')
        assert 'BLAST_OVERPRESSURE_TARGETS_KPA' in kaynak
        assert KINNEY_GRAHAM_AMBIENT_KPA == pytest.approx(101.325)


# ===========================================================================
# BEKÇİ BORCU — P13B4-10 dağıtımı, kulvar 'yapisal-sistem' (4/5 kalem)
#
# Beşinci kalem P5B1-01 ``structural_analysis.py``dedir; bu aşamada o dosyaya
# DOKUNULMADI, bu yüzden borcu da bu aşamada doğmaz (kural: yalnız dokunulan
# dosyanın kalemleri).
# ===========================================================================
class TestBekciBorcu:

    def test_P5B2_01_termal_panel_ORTAM_SICAKLIGINA_DUSMUYOR(self, client):
        """Kapalı kalem P5B2-01 — onarım dosyada DURUYOR mu.

        Kalemin cümlesi: ``/analyze_safety`` termal paneli HER istekte
        293,15 K'ye düşüyor, 2877,8 K cidara LOW/ACCEPTABLE veriyordu.
        ÖLÇÜLDÜ (D26, bu ağaç): ısı zinciri girdileri yokken hüküm
        GERİ ÇEKİLİYOR (``thermal_verdict='withheld'``,
        ``estimated_wall_temperature_k=None``) — ortam sıcaklığı yedeği
        yok. Bu düğüm yedeğin geri gelmesini yakalar.
        """
        r = client.post('/analyze_safety',
                        json=dict(SAFETY_YUK, chamber_temperature=2877.8))
        assert r.status_code == 200
        ts = r.get_json()['safety_analysis']['thermal_safety']
        assert ts['thermal_verdict'] == 'withheld', ts['thermal_verdict']
        assert ts['estimated_wall_temperature_k'] is None, ts
        assert 'NOT COMPUTED' in str(ts['wall_temperature_source'])
        # Ortam sıcaklığı bir CİDAR sıcaklığı olarak yayımlanmamalı.
        assert ts.get('estimated_wall_temperature_k') != pytest.approx(293.15)

    def test_P5B2_02_toksik_esleme_KENDINI_YENMIYOR(self):
        """Kapalı kalem P5B2-02 — 3 daldan 2'si ulaşılamaz sözlük.

        ÖLÇÜLDÜ (D26, bu ağaç): 120 kg N2O4/MMH artık NONE + boş PPE
        vermiyor; hüküm HIGH ve PPE listesi dolu, dayanak beyanlı.
        """
        a = SafetyAnalyzer()
        r = _sessiz(a.analyze_comprehensive_safety, dict(MOTOR),
                    propellant_mass=120.0, propellant_type='n2o4_mmh')
        t = r['toxic_hazards']
        assert t['toxic_hazard_level'] not in ('NONE', None), t
        assert t.get('ppe_requirements'), t
        assert t.get('guidance_basis'), t
        assert t.get('disclaimer_code'), t

    def test_P5B2_03_yazim_hatali_malzeme_SESSIZCE_DUSMUYOR(self):
        """Kapalı kalem P5B2-03 — yazım hatalı malzeme sessizce steel_4130.

        ÖLÇÜLDÜ (D26, bu ağaç): ``stell_4130`` artık
        ``UnresolvedChamberMaterial`` ile ADIYLA reddediliyor; eskiden
        sessizce ``steel_4130``a düşüp SF 1,964 -> 3,286 ve UNSAFE ->
        MARGINAL üretiyordu.
        """
        from hrma.analysis.safety_analysis import UnresolvedChamberMaterial
        a = SafetyAnalyzer()
        with pytest.raises(UnresolvedChamberMaterial) as ex:
            _sessiz(a.analyze_comprehensive_safety, dict(MOTOR),
                    propellant_mass=5.0, material='stell_4130')
        assert 'stell_4130' in str(ex.value)
        # Sağlıklı ad hâlâ geçiyor (kapı iki taraflı değil).
        saglikli = _sessiz(a.analyze_comprehensive_safety, dict(MOTOR),
                           propellant_mass=5.0, material='steel_4130')
        assert saglikli['structural_safety']['material'] == 'steel_4130'

    def test_P5B4_38_yakit_kimligi_KAYBOLMUYOR(self):
        """Kapalı kalem P5B4-38 — her yakıt sessizce HTPB oluyordu.

        ÖLÇÜLDÜ (D26, bu ağaç, aynı geometri/debi): htpb r[0] =
        2,062853 mm/s, paraffin r[0] = 10,509929 mm/s. Kimlik kaybolsaydı
        iki sayı BİT-AYNI olurdu (kalemin cümlesi: parafinde r_dot
        %-78,5 sapma).
        """
        from hrma.analysis.regression_analysis import RegressionAnalyzer
        sonuc = {}
        for yakit in ('htpb', 'paraffin'):
            r = _sessiz(RegressionAnalyzer().analyze_regression_vs_time,
                        dict(REG_TABAN, fuel_type=yakit))
            sonuc[yakit] = (r.get('fuel_type'), float(r['regression_rate'][0]))
        assert sonuc['htpb'][0] == 'htpb'
        assert sonuc['paraffin'][0] == 'paraffin'
        assert not math.isclose(sonuc['htpb'][1], sonuc['paraffin'][1],
                                rel_tol=1e-6), sonuc
        assert sonuc['paraffin'][1] > sonuc['htpb'][1], sonuc
