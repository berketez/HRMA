"""STEP dürüstlük kapıları bekçileri (v2.6.27).

İki ampirik denetçi bulgusunu kilitler (2026-08-04):

* **Tank kolu** — ``generate_tank_step({})`` hiç veri olmadan Ø300 mm ×
  800 mm İKİ eksiksiz "imalat" tankı üretiyordu; 300/800 tamamen üreteç
  varsayımıydı. Adaptör (``cad_export._generate_fallback_files``) da eksik
  ölçüyü aynı sabitlerle dolduruyordu — yani veri hiç yokken bile kullanıcı
  geçerli görünen bir tank STEP'i indiriyordu.
* **Enjektör kolu** — orifis sayısı yoksa 12, çap yoksa 1,5 mm varsayılıyor
  (``step_export`` birinci katman + ``motor_geometry`` sıvı adaptörü ikinci
  katman), halka yarıçapı da hiçbir desen verisi olmadan 0,7·r_c çiziliyordu.
  Motorun kendi sözleşmesi (v2.6.26) delik planı üretilemediğinde
  ``status: not_analyzed`` beyan eder ve uydurma yedek üretmez — imalat
  çıktısı, motorun reddettiği planı uyduramaz.

Yeni sözleşme (kamara/cidar A8 ilkesiyle aynı dil):

* Ölçü çözülemiyorsa STEP ``ValueError`` ile REDDEDİLİR
  ("refusing to emit a manufacturing STEP built from generator defaults").
* Hiçbir çözücünün modellemediği orifis halka yarıçapı ise ancak parça adına
  gömülü açık ``ASSUMED`` beyanıyla çizilir (beyan STEP dosyasının içinde
  taşınır; CAD ağacını açan imalatçı varsayımı görmeden konum okuyamaz).
"""

import contextlib
import io
import os

import pytest

# DEPO-İÇİ ``pytest.importorskip`` KALDIRILDI — P13B1-05, ÖH FAZ B-3
# (27 Ağustos 2026). Eski satır ``step_export = pytest.importorskip(
# 'hrma.export.step_export')`` idi ve MODÜL DÜZEYİNDEydi: modül kırılırsa
# dosyanın tamamı toplama düzeyinde atlanıyor, junit XML'de ``type`` alanı
# OLMAYAN tek bir "collection skipped" satırına dönüşüyor ve CI atlama
# bütçesine HİÇ GÖRÜNMEDEN kayboluyordu (K8'in gerekçesi: "step_export
# kırılsa iki dosya sessizce yok olur" — ikinci dosya
# tests/test_tank_step_units.py).
#
# Modül DEPONUN KENDİSİdir; "isteğe bağlı bağımlılık" gerekçesi burada
# geçerli değil. build123d'nin YOKLUĞU ayrı bir sorudur ve aşağıdaki
# ``BUILD123D_AVAILABLE`` kapısıyla dürüstçe ele alınır — o kapı DURUYOR:
# step_export build123d olmadan da ithal edilebilir (yalnız üretim yolu
# RuntimeError verir, hrma/export/step_export.py:27-35).
#
# ÖLÇÜLDÜ (ithal bellekte kırılarak, 27 Ağustos 2026 — sabotajsız taban
# bu dosyada 14 passed):
#   eski gövde -> "1 skipped"; junit XML'de tek satır, ``type=None``,
#                 ``message='collection skipped'`` — 14 bekçi RAPORDAN DÜŞER
#                 ve toplanan sayısı 14 azalır, atlama sayısı 1 artar;
#   bu gövde   -> "1 error during collection" (dürüstçe kırmızı).
from hrma.export import step_export
from tests.bagimlilik_kapisi import kurulu_mu

# ---------------------------------------------------------------------------
# build123d kapısı — ÜÇ DURUMLU (tests/bagimlilik_kapisi.py'nin kuralı)
# ---------------------------------------------------------------------------
# Kapının koşulu ÖLÇÜMLE değişti (27 Ağustos 2026, P13B1-05'in yan etkisi):
# eskiden ``step_export.BUILD123D_AVAILABLE`` bayrağına bakıyordu; o bayrak
# ``except Exception`` ile kuruluyor (hrma/export/step_export.py:34), yani
# build123d KURULUYKEN OCC yüklemesi patlarsa da False oluyor ve bekçi
# "build123d kurulu değil" diye atlıyordu — YALAN gerekçe. Depo bu sınıfı
# adlandırmış ve tarayıcısını yazmış durumda
# (test_ci_kapsam_kapisi.py::TestAtlamaGerekcesiDurust); eski hâl ancak
# ``importorskip`` sayesinde "kurulum sorusu" sayılıyordu, o kaldırılınca
# tarayıcı kusuru gösterdi.
#
#   build123d KURULU DEĞİL            -> ATLA    (find_spec ile DOĞRULANIR)
#   kurulu + üretim yolu AÇIK         -> KOŞ
#   KURULU ama üretim yolu KAPALI     -> KIRMIZI (aşağıdaki bekçi; ürün kusuru)
_B123D_KURULU = kurulu_mu('build123d')
_kati_gerekli = pytest.mark.skipif(
    not _B123D_KURULU,
    reason='build123d kurulu değil (STEP üretimi atlanır; gerekçe '
           'DOĞRULANDI: find_spec)')


@pytest.mark.skipif(
    not _B123D_KURULU,
    reason='build123d kurulu değil (STEP üretimi atlanır; gerekçe '
           'DOĞRULANDI: find_spec)')
def test_build123d_kuruluyken_step_uretim_yolu_acik():
    """Üçüncü durum: KURULU ama yol KAPALI — bu atlanamaz, ürün kusurudur.

    Yukarıdaki kapı artık yalnız KURULUM sorusunu soruyor. Üretim yolunun
    açıklığı ayrı bir bekçinin işi olmalı, yoksa OCC yüklemesi bozulduğunda
    bu dosyanın bütün bekçileri "kütüphane yok" diyerek sessizce atlanır ve
    kusur görünmez (parti 31 / T2-2'de cantera'da ölçülen desen).
    """
    assert getattr(step_export, 'BUILD123D_AVAILABLE', False), (
        'build123d KURULU (find_spec buldu) ama hrma.export.step_export '
        'onu yükleyemedi — BUILD123D_AVAILABLE False. Bu bir ÜRÜN/ORTAM '
        'kusurudur, "kütüphane yok" gerekçesiyle atlanamaz. '
        'Teşhis: `python -c "import build123d"` çıktısına bakın.')


def _quiet(fn, *args, **kwargs):
    """Çözücülerin print gürültüsünü yutar, sonucu döndürür."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Gerçek çözümler — uydurma sözlük yok (regresyon bekçileri bunları kullanır)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def liquid_results():
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    r = _quiet(LiquidRocketEngine(
        thrust=10000, chamber_pressure=50,
        mixture_ratio=2.3).calculate_performance)
    r['motor_name'] = 'KAPI_SIVI'
    return r


@pytest.fixture(scope='module')
def hybrid_results():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    r = _quiet(HybridRocketEngine(
        thrust=3000, burn_time=10, of_ratio=7.96, chamber_pressure=20,
        fuel_type='paraffin', oxidizer_type='n2o', fuel_density=900,
        regression_a=1.17e-4, regression_n=0.62, expansion_ratio=0).calculate)
    r['motor_name'] = 'KAPI_HIBRIT'
    return r


#: Enjektör panelinin TASARLANAN plaka kalınlığı [mm] — ÖH D32 / OH-D31-16.
#: Ürün yolunda bu sayı kullanıcının enjektör panelinden gelir; HRMA onu
#: TÜRETMEZ (``injector_plate_structural`` kalınlığı çağırandan alır ve
#: ``plate_thickness_earned`` ile künyeler).
_D32_PANEL_PLAKA_MM = 6.0


def _d32_panel_plakali(sonuc, t_mm=_D32_PANEL_PLAKA_MM):
    """Sonuca enjektör panelinin tasarlanan plakasını ekler.

    ÖH D32 / OH-D31-16 — ÇEVRİLEN BEKÇİ GEREKÇESİ. Aşağıdaki bekçiler
    STEP paketinde enjektör parçasının BULUNMASINI şart koşuyordu. O şart,
    plaka kalınlığının kamaranın ÖN KAPAĞINDAN (ya da bir üreteç
    sabitinden) türetildiği dönemden kalmaydı. ÖH D15 / P9B1-13 o ikameyi
    ölçüp reddetti (mesh/gerçek plaka oranı 10,0x) ve kardeş üretici
    ``cad_visualization`` plakayı ancak kalınlık YAYIMLANMIŞSA çiziyor.

    Ölçüldü (taban dd1dcddc): bu dosyanın ham çözücü fikstürleri plaka
    kalınlığı yayımlamıyor, dolayısıyla STL plakayı çizmiyordu; STEP ise
    çiziyordu. Aynı motorun iki katı dosyası iki farklı makineyi
    anlatıyordu ve ``/api/export-complete-zip`` paketi 422 ile
    reddediyordu. D32'de STEP de aynı çözümleyiciye bağlandı.

    Bekçilerin ASIL niyeti (gerçek çözüm verisiyle STEP üretimi kırılmaz;
    üretilen parçalar geçerli ve dolu) KORUNUR: fikstür artık kalınlığın
    KAZANILDIĞI koşuyu kurar. Kalınlığın YOKLUĞUNDA parçanın çizilmediği
    ``tests/test_d32_ihracat_a1.py``de ayrıca sınanır.
    """
    r = dict(sonuc)
    r['injector_results'] = {
        'plate_structural': {
            'status': 'analyzed',
            'plate_thickness_mm': float(t_mm),
            'material': 'stainless_steel_316',
        },
    }
    return r


def _sivi_geo_enjektorsuz():
    """Enjektör verisi TAŞIMAYAN, diğer kapıları geçen asgari sıvı geometrisi.

    Kamara ölçüleri ve yapısal cidar gerçekçi değerlerdir; amaç yalnız
    enjektör kapısına ulaşmaktır (kapı katı üretiminden ÖNCE koşar, lüle
    konturu hiç örneklenmez).
    """
    return {
        'motor_name': 'KAPI_ENJEKTORSUZ',
        'length_units': 'm',
        'chamber_diameter': 0.1,
        'chamber_length': 0.3,
        'throat_diameter': 0.03,
        'exit_diameter': 0.09,
        'nozzle_angles': {'nozzle_type': 'conical'},
        'structural_analysis': {'chamber_structure': {'wall_thickness': 3.0}},
    }


# ---------------------------------------------------------------------------
# Tank kolu
# ---------------------------------------------------------------------------

@_kati_gerekli
class TestTankKapisi:
    def test_bos_tank_verisi_reddedilir(self):
        """ESKİ KUSUR: ``generate_tank_step({})`` Ø300×800 mm iki tam tank
        üretiyordu. Artık üreteç varsayımından imalat STEP'i çıkmaz."""
        with pytest.raises(ValueError, match='refusing to emit'):
            step_export.generate_tank_step({})

    def test_eksik_tank_kolu_reddedilir(self):
        """Tek tank verilse bile eksik kol uydurulmaz — reddedilir.

        FİKSTÜR TAMAMLANDI (ÖH D15 / a2, defter P9B2-15): verilen kol artık
        ``wall_thickness`` de taşır. O alan ürün sözleşmesinde ZORUNLUDUR
        (``cad_export.TANK_CAD_REQUIRED_DIMENSIONS``) ve onsuz tank STEP'i içi
        DOLU bir kütük çiziliyordu (ölçüldü: 2844,64 kg ⟷ yayımlanan 47,62
        kg). Cidar artık kendi gerekçesiyle reddedildiği için, eksik cidarlı
        fikstürde ``fuel_tank`` önce takılıyor ve bu testin ölçmek istediği
        EKSİK KOL reddi hiç ölçülemiyordu.
        """
        with pytest.raises(ValueError, match='oxidizer_tank'):
            step_export.generate_tank_step(
                {'fuel_tank': {'diameter': 300.0, 'length': 800.0,
                               'wall_thickness': 3.0}})

    def test_eksik_uzunluk_reddedilir(self):
        """Çap var boy yok: yarım ölçü de reddedilir, 800 mm uydurulmaz."""
        with pytest.raises(ValueError, match='refusing to emit'):
            step_export.generate_tank_step(
                {'fuel_tank': {'diameter': 300.0, 'wall_thickness': 3.0},
                 'oxidizer_tank': {'diameter': 300.0, 'length': 900.0,
                                   'wall_thickness': 3.0}})

    def test_eksik_cidar_reddedilir(self):
        """Cidar yoksa tank İÇİ DOLU çizilmez — reddedilir (P9B2-15).

        Ölçüldü (31 Ağustos 2026, oksitleyici tankı Ø743,7556 / gövde
        1859,3891 mm, Al 2024-T3): ``wall_thickness`` geometriye hiç
        girmediği için çizilen katının hacmi 1 023 252 929 mm3 = **2844,64
        kg**, aynı pakette yayımlanan tank kütlesi **47,62 kg** (59,7 kat).
        Paketin kendi ``*_geometry.json``ı oymayı zaten tarif ediyordu.
        """
        with pytest.raises(ValueError, match='SOLID BILLET'):
            step_export.generate_tank_step(
                {'fuel_tank': {'diameter': 300.0, 'length': 800.0},
                 'oxidizer_tank': {'diameter': 300.0, 'length': 900.0}})

    def test_gercek_mm_veriyle_uretim_calisiyor(self, tmp_path):
        """Regresyon: gerçek mm ölçülerle tank STEP'i hâlâ üretilir."""
        files = step_export.generate_tank_step(
            {'fuel_tank': {'diameter': 300.0, 'length': 800.0,
                           'wall_thickness': 3.0},
             'oxidizer_tank': {'diameter': 300.0, 'length': 900.0,
                               'wall_thickness': 3.0}},
            out_dir=str(tmp_path))
        assert set(files) == {'fuel_tank', 'oxidizer_tank'}
        for key, path in files.items():
            assert os.path.getsize(path) > 1000, f'{key} neredeyse boş'


def test_adaptor_uydurma_varsayilan_tasimiyor():
    """``cad_export`` adaptörü eksik ölçüyü 300/800 sabitleriyle DOLDURMAZ.

    Eski çağrı ``dimensions.get('diameter', 300.0)`` idi: tank boyutlandırma
    hiç koşmamışken bile STEP koluna "geçerli" ölçü gidiyor, ret kapısı hiç
    tetiklenmiyordu. Artık eksik ölçü None olarak geçer ve reddi
    ``generate_tank_step`` verir.
    """
    from pathlib import Path

    import hrma.export.cad_export as cad_export

    src = Path(cad_export.__file__).read_text(encoding='utf-8')
    start = src.find('generate_tank_step({')
    assert start != -1, 'generate_tank_step çağrısı bulunamadı'
    block = src[start:src.find('out_dir=', start)]
    assert "get('diameter', 300.0)" not in block, 'uydurma çap geri gelmiş'
    assert "get('length', 800.0)" not in block, 'uydurma boy geri gelmiş'
    assert "get('diameter', 0.3)" not in block, 'metre varsayılanı geri gelmiş'


# ---------------------------------------------------------------------------
# Enjektör kolu
# ---------------------------------------------------------------------------

@_kati_gerekli
class TestEnjektorKapisi:
    def test_bos_enjektor_blogu_reddedilir(self):
        """ESKİ KUSUR: boş enjektör bloğundan 12×Ø1,5 mm plaka çıkıyordu.
        Artık blok var ama plan çözülemiyorsa STEP reddedilir."""
        geo = _sivi_geo_enjektorsuz()
        geo['injector_design'] = {}
        with pytest.raises(ValueError, match='injector orifice'):
            _quiet(step_export.generate_step_assembly, geo,
                   motor_type='liquid')

    def test_not_analyzed_enjektor_reddedilir(self):
        """Motor 'not_analyzed' beyan ettiyse imalat çıktısı plan uyduramaz."""
        geo = _sivi_geo_enjektorsuz()
        geo['injector_design'] = {
            'status': 'not_analyzed', 'injector_type': 'coaxial',
            'reason': 'devre modeli bu tipi boyutlandıramadı'}
        with pytest.raises(ValueError, match='not_analyzed'):
            _quiet(step_export.generate_step_assembly, geo,
                   motor_type='liquid')

    def test_ret_yarim_dosya_birakmaz(self, tmp_path):
        """Kapı katı üretiminden ÖNCE koşar: ret hâlinde dizine hiçbir
        .step yazılmamış olmalı (yarım paket yasak)."""
        geo = _sivi_geo_enjektorsuz()
        geo['injector_design'] = {}
        out = tmp_path / 'ret'
        with pytest.raises(ValueError):
            _quiet(step_export.generate_step_assembly, geo,
                   out_dir=str(out), motor_type='liquid')
        kalanlar = list(out.glob('*.step')) if out.exists() else []
        assert kalanlar == [], f'ret sonrası yarım dosya kaldı: {kalanlar}'

    def test_enjektor_iddiasi_olmayan_sonucta_parca_uydurulmaz(
            self, hybrid_results, tmp_path):
        """Sonuç enjektörden HİÇ söz etmiyorsa parça çizilmez (grain ilkesi
        H4-1'in eşleniği): katı motor sonucu varsayılan 'hybrid' rotasından
        geçtiğinde eskiden 12×Ø1,5 mm plaka uyduruluyordu; artık dosya
        kümesinde 'injector' HİÇ yer almaz — reddedilmez de (o sonuçta
        boyutlandırılamamış bir enjektör iddiası yoktur)."""
        r = {k: v for k, v in hybrid_results.items()
             if k not in ('injector_design', 'injector',
                          'injector_design_detail')}
        files = _quiet(step_export.generate_step_assembly, r,
                       out_dir=str(tmp_path))
        assert 'injector' not in files, sorted(files)
        assert {'chamber', 'nozzle', 'assembly'} <= set(files)


@_kati_gerekli
class TestGercekVeriRegresyonu:
    """Gerçek çözümlerle STEP üretimi KIRILMAMALI (görev kalemi 3/5c)."""

    @pytest.fixture(scope='class')
    def liquid_step_files(self, liquid_results, tmp_path_factory):
        from hrma.export.motor_geometry import liquid_results_to_motor_geometry
        geo = _d32_panel_plakali(
            liquid_results_to_motor_geometry(liquid_results))
        out = tmp_path_factory.mktemp('kapi_sivi_step')
        return _quiet(step_export.generate_step_assembly, geo,
                      out_dir=str(out), motor_type='liquid')

    def test_gercek_sivi_veriyle_step_uretilir(self, liquid_step_files):
        files = liquid_step_files
        assert set(files) == {'chamber', 'nozzle', 'injector', 'assembly'}
        for key, path in files.items():
            head = open(path, 'r', errors='ignore').read(200)
            assert 'ISO-10303' in head, f'{key} geçerli STEP değil'
            assert os.path.getsize(path) > 2000

    def test_gercek_hibrit_veriyle_step_uretilir(self, hybrid_results,
                                                 tmp_path):
        files = _quiet(step_export.generate_step_assembly,
                       _d32_panel_plakali(hybrid_results),
                       out_dir=str(tmp_path))
        assert set(files) == {'chamber', 'nozzle', 'fuel_grain',
                              'injector', 'assembly'}
        for key, path in files.items():
            assert os.path.getsize(path) > 2000, f'{key} neredeyse boş'

    def test_halka_yaricapi_varsayimi_beyan_edilir(self, liquid_step_files):
        """Orifis halka yarıçapını HİÇBİR çözücü modellemez; katı ancak
        parça adına gömülü 'ASSUMED' beyanıyla çizilebilir. Beyan STEP
        dosyasının İÇİNDE aranır — dönen sözlükte değil: imalatçıya giden
        şey dosyadır."""
        text = open(liquid_step_files['injector'], 'r',
                    errors='ignore').read()
        assert 'ASSUMED' in text, (
            'enjektör STEP\'i halka yarıçapı varsayımını beyan etmiyor — '
            '0.7*R_chamber yerleşimi desen verisi değildir, beyansız '
            'çizilemez')


# ---------------------------------------------------------------------------
# Sıvı adaptörü (motor_geometry) — ikinci katman uydurma bekçisi
# ---------------------------------------------------------------------------

def test_sivi_adaptor_uydurma_enjektor_tasimaz():
    """ESKİ KUSUR: ``liquid_results_to_motor_geometry({})`` bile 12 delik ×
    Ø1,5 mm 'hesaplanmış' enjektör taşıyordu. Artık motor yayımlamadıysa
    None taşınır — tüketici uydurma sayıyı gerçek sanamaz."""
    from hrma.export.motor_geometry import liquid_results_to_motor_geometry
    inj = liquid_results_to_motor_geometry({})['injector_design']
    assert inj['number_of_orifices'] is None
    assert inj['orifice_diameter_mm'] is None


def test_sivi_adaptor_gercek_sayilari_aynen_tasir(liquid_results):
    """Motorun GERÇEKTEN hesapladığı orifis planı adaptörde bozulmadan taşınır."""
    from hrma.export.motor_geometry import liquid_results_to_motor_geometry
    inj = liquid_results_to_motor_geometry(liquid_results)['injector_design']
    kaynak = liquid_results['injector_design']
    assert inj['number_of_orifices'] == int(round(
        kaynak['number_of_elements']))
    assert inj['number_of_orifices'] > 0
    assert inj['orifice_diameter_mm'] == pytest.approx(
        kaynak['fuel_orifice_diameter_mm'])
