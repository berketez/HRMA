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

step_export = pytest.importorskip('hrma.export.step_export')

_B123D_YOK = not getattr(step_export, 'BUILD123D_AVAILABLE', True)
_kati_gerekli = pytest.mark.skipif(
    _B123D_YOK, reason='build123d kurulu değil (STEP üretimi atlanır)')


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
        """Tek tank verilse bile eksik kol uydurulmaz — reddedilir."""
        with pytest.raises(ValueError, match='oxidizer_tank'):
            step_export.generate_tank_step(
                {'fuel_tank': {'diameter': 300.0, 'length': 800.0}})

    def test_eksik_uzunluk_reddedilir(self):
        """Çap var boy yok: yarım ölçü de reddedilir, 800 mm uydurulmaz."""
        with pytest.raises(ValueError, match='refusing to emit'):
            step_export.generate_tank_step(
                {'fuel_tank': {'diameter': 300.0},
                 'oxidizer_tank': {'diameter': 300.0, 'length': 900.0}})

    def test_gercek_mm_veriyle_uretim_calisiyor(self, tmp_path):
        """Regresyon: gerçek mm ölçülerle tank STEP'i hâlâ üretilir."""
        files = step_export.generate_tank_step(
            {'fuel_tank': {'diameter': 300.0, 'length': 800.0},
             'oxidizer_tank': {'diameter': 300.0, 'length': 900.0}},
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
        geo = liquid_results_to_motor_geometry(liquid_results)
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
        files = _quiet(step_export.generate_step_assembly, hybrid_results,
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
