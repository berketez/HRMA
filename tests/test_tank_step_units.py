"""Tank STEP birim sözleşmesi bekçisi (v2.6.2).

Neden bu test var — 1000× birim hatası:
``generate_tank_step`` girdiyi METRE varsayıp 1000 ile çarpıyordu. Ama çağıran
adaptör (``cad_export.generate_tank_cad``) sıvı motorun ürettiği
``dimensions.diameter`` değerini geçiriyordu ve o değer ZATEN mm
(``liquid_rocket_engine`` içinde ``ox_tank_diameter * 1000``).

Sonuç: 300 mm'lik tank 300.000 mm = **300 metre** olarak kuruluyordu.
OpenCascade 300 metrelik silindir + küre birleşimini kuramayıp SESSİZCE boş
bir katı döndürüyor, istisna fırlamadığı için ``STEP_NOT_AVAILABLE`` emniyet
yolu hiç tetiklenmiyor ve kullanıcı geçerli görünen ama içi tamamen boş bir
STEP dosyası indiriyordu.

Hata yalnızca veri VARKEN ortaya çıkıyordu: veri yoksa varsayılan 0.3 metreydi
ve ×1000 ile doğru 300 mm'yi veriyordu. Bu yüzden gözden kaçmıştı.

---------------------------------------------------------------------------
Faz 4B / F — BU BEKÇİ TESTİ KUSURU KORUYORDU (2 Ağustos 2026)

Eski ölçüm yöntemi STEP dosyasının METNİNDEKİ ``CARTESIAN_POINT`` girdilerini
tarıyordu ve "gövde boyu 800 mm" iddiasını GEÇİRİYORDU. Oysa aynı dosya CAD
çekirdeğiyle geri okunduğunda (``import_step(...).bounding_box()``) katının
gerçek zarfı **1100 mm** çıkıyor. Sebep: yarıküre başlıklar
``SPHERICAL_SURFACE`` olarak yazılır ve kürenin kutupları dosyada nokta
olarak GEÇMEZ; metin taraması yalnız silindirin uçlarını görür.

Yani test, ölçtüğünü sandığı şeyi ölçmüyordu. Artık ölçüm CAD çekirdeğiyle
yapılır. Ölçülen fark analiz modeliyle katı modelin FARKLI GEOMETRİLER
olmasından kaynaklanır (A11: analiz düz kapaklı silindir, STEP silindir + iki
TAM küre) ve bu dosyada açıkça raporlanır; tank tek-geometri işi ayrı bir
dalgada yapılacak.
"""

import pytest

# DEPO-İÇİ ``pytest.importorskip`` KALDIRILDI — P13B1-05, ÖH FAZ B-3
# (27 Ağustos 2026). Kardeşiyle (tests/test_step_durustluk_kapisi.py:32)
# birebir aynı kusur: MODÜL DÜZEYİNDE depo-içi ithal atlaması. K8'in
# gerekçesindeki "iki dosya" tam olarak bu ikisiydi; ithal kırıldığında bu
# dosyanın 13 kalemi (11 passed + 2 xfailed) junit XML'de ``type`` alanı
# OLMAYAN tek bir "collection skipped" satırına dönüşüp CI atlama
# bütçesinden kayboluyordu.
#
# build123d kapısı DURUYOR (aşağıdaki ``pytestmark``): step_export modülü
# build123d olmadan da ithal edilir; eksik olan yalnız üretim yoludur.
#
# ÖLÇÜLDÜ (ithal bellekte kırılarak, 27 Ağustos 2026):
#   eski gövde -> "1 skipped"  (dosyanın tamamı sessizce yok olur)
#   bu gövde   -> "1 error during collection" (dürüstçe kırmızı)
from hrma.export import step_export
from tests.bagimlilik_kapisi import kurulu_mu

# Kapının KOŞULU da düzeltildi: eskiden ``BUILD123D_AVAILABLE`` bayrağına
# bakıyordu ve o bayrak ``except Exception`` ile kuruluyor — build123d
# KURULUYKEN OCC yüklemesi patlarsa da "build123d kurulu değil" diyerek
# atlıyordu (YALAN gerekçe; depo tarayıcısı
# test_ci_kapsam_kapisi.py::TestAtlamaGerekcesiDurust bu sınıfı kovalar).
# Kurulum sorusu artık find_spec'e dayanır; "kurulu ama üretim yolu kapalı"
# üçüncü durumunun bekçisi kardeş dosyadadır
# (test_step_durustluk_kapisi.py::test_build123d_kuruluyken_step_uretim_
# yolu_acik) — tek yerde durması yeterli, ürün bayrağı ortak.
pytestmark = pytest.mark.skipif(
    not kurulu_mu('build123d'),
    reason='build123d kurulu değil (STEP üretimi atlanır; gerekçe '
           'DOĞRULANDI: find_spec)')

#: Testte üretilen tankların analiz (girdi) boyutları — mm.
#: ``wall_thickness`` EKLENDİ (ÖH D15 / a2, defter P9B2-15): ürün sözleşmesi
#: (``cad_export.TANK_CAD_REQUIRED_DIMENSIONS``) onu zorunlu sayıyor ve tank
#: STEP'i artık gerçek bir KABUKTUR — cidarsız girdi fail-closed reddedilir.
#: Bu dosyanın ölçtüğü şey DIŞ ZARFTIR; oyma dış zarfı değiştirmez, yani
#: buradaki 1000× ve zarf bekçileri aynen geçerlidir.
TANK_INPUT_MM = {
    'fuel_tank': {'diameter': 300.0, 'length': 800.0, 'wall_thickness': 3.0},
    'oxidizer_tank': {'diameter': 300.0, 'length': 900.0,
                      'wall_thickness': 3.0},
}


def _solid_size_mm(path):
    """STEP'i CAD çekirdeğiyle geri okur; GERÇEK katı zarfını (X, Y, Z) verir.

    Metin taraması değil: küresel yüzeylerin kutupları dosyada nokta olarak
    bulunmadığı için metinden ölçülen zarf eksik çıkıyordu (bkz. modül notu).
    """
    from build123d import import_step
    bb = import_step(path).bounding_box()
    return float(bb.size.X), float(bb.size.Y), float(bb.size.Z)


@pytest.fixture(scope='module')
def tank_files(tmp_path_factory):
    out = tmp_path_factory.mktemp('tank_step')
    # Faz 5 / H5-6 — FAIL-OPEN ATLAMA kaldırıldı: burası eskiden
    # ``except Exception as exc: pytest.skip(f'STEP üretilemedi: {exc}')``
    # yazıyordu. Modülün başındaki ``pytestmark`` zaten build123d yokluğunu
    # ATLAMAYLA karşılıyor; buraya gelen bir istisna kütüphane VARKEN
    # üreticinin kırıldığı anlamına gelir ve tam olarak bu dosyanın (A11
    # tank geometrisi bekçileri) yakalaması gereken şeydir. Sessizce
    # atlanırsa 13 bekçi birden görünmez olur.
    return step_export.generate_tank_step(
        {k: dict(v) for k, v in TANK_INPUT_MM.items()},
        out_dir=str(out))


class TestTankStepGeometry:
    def test_files_are_not_empty(self, tank_files):
        """Boş katı üretilmemeli — asıl regresyon buydu."""
        import os
        for key, path in tank_files.items():
            assert os.path.getsize(path) > 1000, f'{key} neredeyse boş'

    @pytest.mark.parametrize('key', sorted(TANK_INPUT_MM))
    def test_diameter_is_millimetres_not_metres(self, tank_files, key):
        """Çap 1000× hatasına karşı KESİN bekçi: 300 mm girdi -> 306 mm zarf.

        ÖH V3 CAD A2 · H4 — ÇEVRİLDİ (12 Eki 2026, ana model izni, dört
        koşul; rapor ``docs/scofield/raw/OH/V3/cad-duzeltme/rapor.md``
        "Bölüm T"). Eski beklenti "enine zarf = girdi çapı" idi, yani D'yi
        DIŞ çap sayıyordu. Karar §28-21 (b): CAD, boyutlandırmanın düz uçlu
        modelini çizer; boyutlandırma D'yi itici BOŞLUĞUNUN çapı olarak kurar
        (``V = π·D²·L/4``, basınçlı kap analizi ``inner_diameter_mm = D``)
        ve cidar t dışarı eklenir. Kâhin bu tanım ve girdinin D, t'sidir:
        enine zarf D + 2t. Zarf hâlâ girdiyle BİREBİR ilişkilidir; tam eşitlik
        aranır ve 1000× hata anında yakalanır.
        """
        _x, y, z = _solid_size_mm(tank_files[key])
        girdi = TANK_INPUT_MM[key]
        expected = girdi['diameter'] + 2 * girdi['wall_thickness']
        for axis, size in (('Y', y), ('Z', z)):
            assert size == pytest.approx(expected, rel=1e-6), (
                f'{key} {axis} zarfı {size:.3f} mm — {expected:.1f} mm '
                'bekleniyordu (1000× birim hatası geri gelmiş olabilir)')

    @pytest.mark.parametrize('key', sorted(TANK_INPUT_MM))
    def test_axial_envelope_difference_is_reported_and_understood(
            self, tank_files, key):
        """Katı zarfı ile analiz boyu arasındaki fark ÖLÇÜLÜR ve açıklanır.

        Ölçüldü (HEAD a7ff1e7): fuel_tank X zarfı 1100.0 mm, analiz gövde boyu
        800.0 mm; oxidizer_tank 1200.0 / 900.0. Fark her ikisinde de tam
        olarak bir ÇAP kadardır (300 mm) çünkü STEP modeli silindirin iki
        ucuna TAM küre ekler (yarıküre değil, kesişim değil). Yani fark
        rastgele bir sapma değil, bilinen bir geometri farkıdır (A11).

        Bu test farkın BEKLENEN büyüklükte kalmasını sabitler: başlık modeli
        değişirse (ör. eliptik kapak, yarıküre kesişimi) burası kırmızıya
        döner ve kimse farkı sessizce büyütemez.

        ÖH V3 CAD A2 · H4 — ÇEVRİLDİ (12 Eki 2026, ana model izni, dört
        koşul; rapor ``docs/scofield/raw/OH/V3/cad-duzeltme/rapor.md``
        "Bölüm T"). Yukarıdaki ölçüm (fark = bir çap) iki tam küre başlıklı
        ESKİ katınındı. Karar §28-21 (b): CAD, boyutlandırmanın DÜZ UÇLU
        modelini çizer (boşluk Ø D × L, cidar t gövdeye ve iki düz kapağa
        dışarıdan eklenir). Kâhin bu tanım ve girdinin L, t'sidir: X − L = 2t.
        """
        x, _y, _z = _solid_size_mm(tank_files[key])
        body_mm = TANK_INPUT_MM[key]['length']
        wall_mm = TANK_INPUT_MM[key]['wall_thickness']
        overhang = x - body_mm
        assert overhang == pytest.approx(2 * wall_mm, rel=1e-6), (
            f'{key}: katı zarfı {x:.1f} mm, analiz gövdesi {body_mm:.1f} mm; '
            f'fark {overhang:.1f} mm — iki düz kapak için beklenen fark '
            f'2 × {wall_mm:.1f} mm. Başlık geometrisi değişmiş olabilir.')

    @pytest.mark.parametrize('key', sorted(TANK_INPUT_MM))
    def test_no_dimension_is_absurdly_large(self, tank_files, key):
        """Hiçbir zarf ölçüsü 10 m'yi aşmamalı (birim hatasının imzası)."""
        worst = max(_solid_size_mm(tank_files[key]))
        assert worst < 10_000.0, f'{key}: {worst:.0f} mm zarf ölçüsü var'


class TestAcikBorcTankTekGeometri:
    """AÇIK BORÇ — analiz ile katı model AYNI tankı anlatmıyor (A11).

    Analiz düz kapaklı silindir kabul eder (gövde boyu = toplam boy); STEP
    modeli silindire iki TAM küre ekler. Ölçüldü: fuel_tank analiz 800.0 mm,
    STEP 1100.0 mm (%37,5 fark); oxidizer_tank 900.0 / 1200.0 (%33,3).
    Hacim de aynı sebeple ayrışır.

    Aşağıdaki test DOĞRU sözleşmeyi yazar: katının eksenel zarfı analizin
    verdiği boya eşit olmalıdır. Bugün geçmiyor, bu yüzden ``xfail`` ile
    AÇIK BORÇ olarak işaretli — atlanmıyor, her koşuda GERÇEKTEN çalışıyor.
    Tank tek-geometri işi bitince test geçecek ve ``strict=True`` sayesinde
    XPASS raporlanıp KIRMIZI verecek: o an bu işaretin kaldırılması gerekir.
    Yani borç kapanınca kimse bunu unutamaz.
    """

    @pytest.mark.xfail(
        strict=True,
        reason='A11 açık borç: tank tek geometri işi henüz yapılmadı — STEP '
               'silindire iki tam küre ekliyor, analiz düz kapak varsayıyor')
    @pytest.mark.parametrize('key', sorted(TANK_INPUT_MM))
    def test_solid_axial_envelope_equals_analysis_length(self, tank_files, key):
        x, _y, _z = _solid_size_mm(tank_files[key])
        assert x == pytest.approx(TANK_INPUT_MM[key]['length'], rel=1e-3)


class TestUnitEnvelopeGuard:
    def test_metre_input_is_rejected(self):
        """Eski hata biçimi (metre geçirmek) sessizce kabul EDİLMEMELİ."""
        with pytest.raises(ValueError, match='envelope'):
            step_export.generate_tank_step(
                {'fuel_tank': {'diameter': 0.3, 'length': 0.8},
                 'oxidizer_tank': {'diameter': 0.3, 'length': 0.9}})

    def test_absurdly_large_input_is_rejected(self):
        """1000× şişmiş değer de reddedilmeli (300 m tank)."""
        with pytest.raises(ValueError, match='envelope'):
            step_export.generate_tank_step(
                {'fuel_tank': {'diameter': 300_000.0, 'length': 800_000.0},
                 'oxidizer_tank': {'diameter': 300_000.0, 'length': 900_000.0}})


def test_adapter_defaults_are_millimetres():
    """cad_export adaptörünün varsayılanları mm olmalı, metre değil.

    Varsayılanlar metre kalırsa (0.3/0.8) hata yalnız veri yokken gizlenir ve
    gerçek veriyle tekrar ortaya çıkar — orijinal hatanın gizlenme biçimi buydu.
    """
    from pathlib import Path

    import hrma.export.cad_export as cad_export

    src = Path(cad_export.__file__).read_text(encoding='utf-8')
    start = src.find('generate_tank_step({')
    assert start != -1, 'generate_tank_step çağrısı bulunamadı'
    block = src[start:src.find('out_dir=', start)]
    assert "get('diameter', 0.3)" not in block, 'metre varsayılanı geri gelmiş'
    assert "get('length', 0.8)" not in block, 'metre varsayılanı geri gelmiş'
    assert '300.0' in block and '800.0' in block, 'mm varsayılanı bulunamadı'


# ---------------------------------------------------------------------------
# Tank imalat kontrol listesi — kaynak dürüstlüğü
# ---------------------------------------------------------------------------

def test_tank_manufacturing_checklist_labels_its_sources(tmp_path):
    """Her alan analysis/template olarak etiketlenmeli.

    Bu dosya eskiden 'manufacturing_specifications.json' adıyla iniyor ve bir
    imalat spesifikasyonu havası veriyordu; oysa bafl/bağlantı elemanı
    malzemesi, kaynak prosesi, ±0,1 mm tolerans, yüzey pürüzlülüğü, 1,5x
    basınç testi, helyum sızıntı eşiği ve montaj sırası SABİT metinlerdi.
    Yalnız tank kabuğu malzemesi girdiden geliyordu ve kullanıcının bu ayrımı
    görmesi imkânsızdı.

    FreeCAD pratikte hiçbir zaman kurulu olmadığı için tank CAD paketi HER
    ZAMAN bu yoldan çıkar — yani şablon her kullanıcıya ulaşır.
    """
    import json

    from hrma.export.cad_export import cad_generator

    struct = {'material': 'Aluminum 2024-T3', 'material_key': 'al_2024_t3',
              'yield_strength_mpa': 345.0, 'density_kg_m3': 2780,
              'pressure_rating': 42.0}
    td = {
        'oxidizer_tank': {'dimensions': {'diameter': 300.0, 'length': 900.0,
                                         'wall_thickness': 3.0},
                          'structural': dict(struct)},
        'fuel_tank': {'dimensions': {'diameter': 300.0, 'length': 800.0,
                                     'wall_thickness': 3.0},
                      'structural': dict(struct)},
    }
    out = tmp_path / 'specs'
    out.mkdir()
    cad_generator._generate_manufacturing_specs(td, str(out))

    path = out / 'manufacturing_checklist_TEMPLATE.json'
    assert path.exists(), 'dosya adı şablon olduğunu söylemiyor'
    spec = json.loads(path.read_text(encoding='utf-8'))

    assert 'DISCLAIMER' in spec
    assert 'NOT derived from your design' in spec['DISCLAIMER']

    def leaves(node, prefix=''):
        if isinstance(node, dict) and 'source' in node:
            yield prefix, node['source']
        elif isinstance(node, dict):
            for k, v in node.items():
                yield from leaves(v, f'{prefix}.{k}' if prefix else k)

    tagged = dict(leaves(spec))
    assert tagged, 'hiçbir alan kaynak etiketi taşımıyor'
    assert set(tagged.values()) <= {'analysis', 'template'}

    # Tank kabuğu malzemesi GERÇEKTEN hesaptan gelir
    assert tagged['materials.oxidizer_tank'] == 'analysis'
    assert tagged['materials.fuel_tank'] == 'analysis'
    # Bunlar hesaptan GELMEZ — şablon olarak işaretli kalmalı
    for key in ('materials.baffles', 'materials.fasteners',
                'manufacturing_processes.welding',
                'manufacturing_processes.machining',
                'quality_requirements.pressure_test',
                'quality_requirements.leak_test',
                'assembly_sequence'):
        assert tagged[key] == 'template', (
            f'{key} hesaplanmış gibi işaretlenmiş — uydurma değer '
            'analysis etiketi taşıyamaz')
