"""ÖH Z5S / P09-A — CAD GEOMETRİSİ BEKÇİSİ.

Bu dosya vaka listelemez, ÖLÇER. Kusur sınıfı tektir: **``cad_visualization``
modülünün ÇİZDİĞİ sayı, çözücünün teslim ettiği sayı değil.** Sekiz kalem aynı
sınıfın sekiz yüzüdür:

* ``P9B1-02`` (kritik) — yayımlanan ZARF çapı bir formüldü; formül lüle cidarı
  yoksa lüleyi zarftan tamamen düşürüyordu, oysa 3B katı lüleyi yedek cidarla
  çizmeye devam ediyordu. Ölçüldü (27 Ağustos 2026): yayımlanan 187,015 mm,
  aynı koşuda üretilen katının gerçek zarfı 364,485 mm (1,949x).
* ``P9B1-03`` (kritik) — "verified against the pressure load" künyesi,
  çözücü aynı blokta ``design_mode='size'`` + ``safety_factor_is_tautological``
  yazarken de basılıyordu. Kod onarımı ÖH Z2'de (defter P9B2-07) yapıldı;
  BEKÇİSİ yoktu — dört ürün yüzü ve torna notu burada kilitlenir.
* ``P9B1-05`` — bant dışı kamara boyu sessizce 300 mm oluyordu. Ölçüldü:
  ``chamber_length`` 5 m, 15 mm ve "alan hiç yok" ÜÇÜ DE aynı 300 mm'lik
  kamarayı çiziyordu; kullanıcının girdisiyle girdisizlik ayırt edilemiyordu.
* ``P9B1-06`` — kamaradan uzun tane sessizce ``0.98 x kamara boyu``na
  kırpılıyordu (3.387 mm tane 980 mm çiziliyordu); sığan tane bile %2
  kısalıyordu.
* ``P9B1-19`` — sıvı kesitte kamara cidarı sabit 8 mm; kullanıcı 5 mm girmiş
  ve yapısal analiz de 5 mm demişken.
* ``P9B1-20`` — kesit HER motorda tam 24 soğutma kanalı çiziyordu; aynı
  yanıttaki bileşen tablosu kanal sayısı için "NOT AVAILABLE" diyordu.
* ``P9B1-21`` — enjektör delikleri, bileşen tablosunun BİLEREK reddettiği
  arayüz sabitinden (``injector_holes``, varsayılan 24) çiziliyordu.
* ``P9B1-24`` — çizimdeki ``angle_source`` künyesi, çözücünün "bu açılar
  VARSAYILAN" beyanını (``nozzle_angles.angles_source``) siliyordu.

Ölçüm yöntemi iki bağımsız temsili karşılaştırmaktır: bir yanda YAYIMLANAN
sözlük, öte yanda AYNI koşuda ÜRETİLEN trimesh katısının köşe koordinatları
(``r = hypot(x, y)``, eksen z) ya da üretilen Plotly izlerinin kendisi.
"""

import contextlib
import copy
import io

import numpy as np
import pytest

from hrma.export.cad_visualization import (
    CROSS_SECTION_MAX_CHANNELS,
    CROSS_SECTION_MAX_INJECTOR_HOLES,
    DetailedCADGenerator,
    MotorCADDesigner,
    NOT_AVAILABLE_SPEC,
    _cross_section_basis,
    _measured_envelope_diameter_mm,
    _nozzle_angle_source_label,
)

VERIFIED_CLAIM = 'verified against the pressure load'


def _silent(fn, *args, **kwargs):
    """CAD katmanının print gürültüsünü yutar."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        return fn(*args, **kwargs)


def _base_motor(**over):
    """Katı/hibrit rotasının ihraç katmanına verdiği gövdenin sadeleştirilmişi.

    Çözücü ÇALIŞTIRILMAZ: bu bekçi ihraç katmanının kendi davranışını ölçer,
    çözücünün doğruluğunu değil. Alanlar gerçek bir ``/calculate`` yanıtının
    aynı adlı alanlarıdır.
    """
    motor = {
        'chamber_diameter': 0.100,      # m
        'chamber_length': 0.500,        # m
        'throat_diameter': 0.025,       # m
        'exit_diameter': 0.060,         # m
        'thrust': 2000.0,               # N
        'chamber_pressure': 40.0,       # bar
        'l_star': 1.0,                  # m
        'nozzle_geometry': {'wall_thickness': 4.0},   # mm
        'nozzle_angles': {'convergent_half_angle_deg': 30.0,
                          'divergent_half_angle_deg': 15.0,
                          'nozzle_type': 'conical'},
        # ÇEVRİLDİ (ÖH D15 birleşme etkileşimi, 1 Eylül 2026):
        # ``outer_diameter_mm`` EKLENDİ. D15 / defter P9B1-04 tanenin dış
        # çapını artık ÇÖZÜCÜDEN okuyor; eski kod ``kamara_yarıçapı - liner``
        # çiziyordu ve o ``liner`` hiçbir hesaptan gelmiyordu (ölçüldü:
        # katıda çözücü 100,00 mm derken STL 96,00 mm, hacim −%9,5). Çözücü
        # dış çapı yayımlamıyorsa tane artık HİÇ çizilmiyor.
        # Bu fikstür o alanı taşımadığı için P9B1-06'nın üç bekçisi
        # (kırpılmayan tane) ölçemez hale gelmişti. Sayı uydurulmadı,
        # ÖLÇÜLDÜ: /calculate_solid (Ø100 mm kamara) yanıtı
        # ``grain_design.outer_diameter_mm = 100.0`` yayımlıyor; hibritte
        # aynı alan ``grain_outer_diameter_mm`` adıyla ve yine kamara çapına
        # eşit geliyor (103,13 mm / kamara 103,13 mm).
        'grain_design': {'grain_length_mm': 400.0,
                         'port_diameter_initial_mm': 40.0,
                         'outer_diameter_mm': 100.0},
        'structural_analysis': {
            'case_analysis': {'wall_thickness_mm': 2.0,
                              'recommended_wall_thickness_mm': 2.0,
                              'design_mode': 'size',
                              'safety_factor_is_tautological': True,
                              'safety_factor': 2.5,
                              'design_safety_factor': 2.5},
            'material_properties': {'name': 'AISI 4130', 'density': 7850.0},
            'design_parameters': {'material': 'steel_4130'},
        },
    }
    motor = copy.deepcopy(motor)
    motor.update(copy.deepcopy(over))
    return motor


def _assembly(motor):
    return _silent(MotorCADDesigner().generate_3d_motor_assembly, motor)


def _mesh_envelope_mm(assembly_meshes):
    """Üretilen katıların GERÇEK zarf çapı [mm] — köşe koordinatlarından."""
    return 2000.0 * max(
        float(np.hypot(np.asarray(mesh.vertices)[:, 0],
                       np.asarray(mesh.vertices)[:, 1]).max())
        for _name, mesh in assembly_meshes)


def _mesh_by_name(assembly_meshes, name):
    for part, mesh in assembly_meshes:
        if part == name:
            return mesh
    return None


def _liquid_motor(**over):
    """``DetailedCADGenerator`` gövdesi (bu sınıf ölçüleri mm bekler)."""
    motor = {
        'chamber_diameter': 120.0,      # mm
        'chamber_length': 300.0,        # mm
        'throat_diameter': 50.0,        # mm
        'exit_diameter': 90.0,          # mm
        'nozzle_length': 150.0,         # mm
        'motor_name': 'Z5S liquid',
        'thrust': 5000.0,
        'chamber_pressure': 25.0,
        'injector_holes': 24,           # ARAYÜZ sabiti — tasarım sonucu DEĞİL
        'injector_type': 'unlike_impinging',
        'injector_design': {'number_of_elements': 41,
                            'injector_type': 'unlike_impinging',
                            'injection_pressure_drop_bar': 4.2},
        'cooling_system': {'cooling_channels': 80},
        'cooling_type': 'regenerative',
        'fuel_type': 'rp1',
        'structural_analysis': {
            'chamber_structure': {'wall_thickness': 5.0,
                                  'required_wall_thickness': 4.1,
                                  'safety_factor': 2.5,
                                  'safety_factor_source': 'user input '
                                                          '(safety factor)'},
            'material_properties': {'name': 'Stainless Steel 316',
                                    'density': 8000.0},
        },
    }
    motor = copy.deepcopy(motor)
    for key, value in over.items():
        if value is _MISSING:
            motor.pop(key, None)
        else:
            motor[key] = copy.deepcopy(value)
    return motor


class _Missing:
    pass


_MISSING = _Missing()


# ---------------------------------------------------------------------------
# P9B1-02 (KRİTİK) — zarf çapı ÜRETİLEN KATIDAN ölçülür, hesaplanmaz
# ---------------------------------------------------------------------------

class TestZarfCapiOlculur:

    def test_zarf_capi_katinin_kendi_zarfidir(self):
        """Yayımlanan ``max_diameter`` mesh'ten okunan zarfla BİREBİR olmalı."""
        cad = _assembly(_base_motor())
        assert not cad.get('error'), cad.get('error')
        geometry = cad['performance_summary']['geometry_summary']
        olculen = _mesh_envelope_mm(cad['assembly_meshes'])
        assert geometry['max_diameter'] == pytest.approx(olculen, rel=1e-12), (
            f"yayimlanan zarf {geometry['max_diameter']} mm, katinin gercek "
            f'zarfi {olculen} mm')
        assert 'MEASURED' in geometry['max_diameter_basis']

    def test_lule_cidari_yokken_zarf_lüleyi_dusurmez(self):
        """Kusurun tam repro'su: lüle cidarı yoksa formül lüleyi düşürüyordu.

        Katı lüleyi yedek cidarla ÇİZMEYE devam ettiği için yayımlanan sayı
        çizilen parçadan küçük kalıyordu (ölçülen koşuda 1,949x).
        """
        motor = _base_motor(exit_diameter=0.240)
        motor['nozzle_geometry'] = {}          # cidar yayımlanmıyor
        cad = _assembly(motor)
        assert not cad.get('error'), cad.get('error')
        geometry = cad['performance_summary']['geometry_summary']
        olculen = _mesh_envelope_mm(cad['assembly_meshes'])

        assert geometry['max_diameter'] == pytest.approx(olculen, rel=1e-12)
        # Eski formülün sayısı kaybolmadı ama adı artık "tahmin"dir ve
        # gerçekten katıdan KÜÇÜK olduğu bu koşumda görünür.
        tahmin = geometry['max_diameter_estimate']
        assert tahmin is not None and tahmin < olculen * 0.75, (
            f'bu koşum kusuru üretmiyor: tahmin {tahmin} mm, katı {olculen} mm')
        assert 'ESTIMATE' in geometry['max_diameter_estimate_basis']

    def test_kati_yoksa_zarf_basilmaz(self):
        """Özet katılar olmadan çağrıldıysa zarf İDDİA EDİLMEZ (fail-closed)."""
        summary = _silent(
            MotorCADDesigner()._generate_cad_performance_summary, _base_motor())
        geometry = summary['geometry_summary']
        assert geometry['max_diameter'] is None
        assert 'not measured' in geometry['max_diameter_basis']
        # Tahmin kaybolmaz, ama adı zarf değildir.
        assert geometry['max_diameter_estimate'] is not None

    @pytest.mark.parametrize('meshes', [None, [], ()])
    def test_katisiz_olcum_sayi_uretmez(self, meshes):
        capi, kunye = _measured_envelope_diameter_mm(meshes)
        assert capi is None
        assert 'not measured' in kunye

    def test_bozuk_katidan_sayi_uretilmez(self):
        """Köşesiz/bozuk katı zarf üretmemeli; patlamamalı da."""

        class _Bos:
            vertices = np.empty((0, 3))

        capi, kunye = _measured_envelope_diameter_mm([('Chamber', _Bos())])
        assert capi is None
        assert 'not measured' in kunye


# ---------------------------------------------------------------------------
# P9B1-03 (KRİTİK) — "doğrulandı" künyesi KAZANILIR
# ---------------------------------------------------------------------------

def _wall_faces(motor):
    """Cidar künyesinin bastığı DÖRT ürün yüzü + torna notu."""
    designer = MotorCADDesigner()
    drawing = designer._generate_technical_drawings(motor)['chamber']
    summary = _silent(designer._generate_cad_performance_summary, motor)
    notes = _silent(designer._generate_manufacturing_notes, motor)
    return {
        'drawing_source': drawing['wall_thickness_source'],
        'drawing_flag': drawing['wall_verified_against_pressure_load'],
        # ÖH D29 (P15B4-12): cidar künyesi kütle dökümünden ÇIKTI, kendi
        # boyut sözlüğüne (geometry_summary) taşındı. Yüz sayısı DEĞİŞMEDİ
        # — dördüncü yüz hâlâ ürün yüzeyidir, yalnız adresi doğrudur.
        'mass_source': summary['geometry_summary']['wall_thickness_source'],
        'estimate_basis': summary['geometry_summary'][
            'max_diameter_estimate_basis'],
        'turning_note': next((n for n in notes if 'leave' in n), None),
    }


class TestCidarDogrulamaKunyesiKazanilir:

    def _kasa(self, **over):
        motor = _base_motor()
        motor['structural_analysis']['case_analysis'].update(over)
        return motor

    def test_boyutlandirilan_cidar_dogrulama_iddia_etmez(self):
        """``design_mode='size'`` + tautological -> hiçbir yüzde "verified"."""
        faces = _wall_faces(self._kasa(design_mode='size',
                                       safety_factor_is_tautological=True))
        assert faces['drawing_flag'] is False
        for ad, metin in faces.items():
            if ad == 'drawing_flag':
                continue
            assert metin, f'{ad} yüzü boş'
            assert VERIFIED_CLAIM not in metin, (
                f'{ad} yüzü boyutlandırmayı doğrulama diye basıyor: {metin}')
        assert 'NOT a pressure-load verification' in faces['drawing_source']

    def test_dogrulanan_cidarda_kunye_gercekten_basilir(self):
        """Künye susturulmaz: gerçek doğrulamada DÖRT yüzde de yazmalı."""
        faces = _wall_faces(self._kasa(design_mode='verify',
                                       safety_factor_is_tautological=False))
        assert faces['drawing_flag'] is True
        for ad, metin in faces.items():
            if ad == 'drawing_flag':
                continue
            assert VERIFIED_CLAIM in metin, f'{ad} yüzünde künye kayboldu'

    def test_beyansiz_blok_hicbir_sey_iddia_etmez(self):
        """Çözücü beyan etmiyorsa ihraç ne doğrular ne yalanlar (fail-closed)."""
        kasa = self._kasa()
        kasa['structural_analysis']['case_analysis'].pop('design_mode')
        kasa['structural_analysis']['case_analysis'].pop(
            'safety_factor_is_tautological')
        faces = _wall_faces(kasa)
        assert faces['drawing_flag'] is False
        assert VERIFIED_CLAIM not in faces['drawing_source']
        assert 'does not state' in faces['drawing_source']

    def test_iki_mod_ayni_kunyeyi_basmaz(self):
        """Boyutlandırma ile doğrulama BİREBİR aynı metni üretemez."""
        sized = _wall_faces(self._kasa(design_mode='size',
                                       safety_factor_is_tautological=True))
        verified = _wall_faces(self._kasa(design_mode='verify',
                                          safety_factor_is_tautological=False))
        assert sized != verified


# ---------------------------------------------------------------------------
# P9B1-05 — kamara boyu SESSİZCE değiştirilmez
# ---------------------------------------------------------------------------

class TestKamaraBoyuUydurulmaz:

    # ÖH D26 / OH-Z5-12 — LİSTEDEN 5.0 ÇIKARILDI, 5.5 GİRDİ.
    # 5,0 m bandın UCUdur ve ihracatın kendi ret iletisi onu kapalı aralıkla
    # ("[0.02, 5] m") bandın İÇİNDE gösteriyordu; kapı ise ``lo < v < hi``
    # ile reddediyordu. Ölçüldü (taban 7751531,
    # ``raw/OH/D26/ihracat/a1/once.json`` -> ``OH-Z5-12.sinirlar``): ürün,
    # kabul ettiğini söylediği sayıyı reddediyordu. Bant artık KAPALI ve
    # ileti de öyle yazıyor; bu iddia gerçekten bant DIŞI değerleri sınar.
    @pytest.mark.parametrize('length_m', [5.5, 6.5, 0.015, 0.001])
    def test_bant_disi_boy_sessizce_300mm_olmaz(self, length_m):
        cad = _assembly(_base_motor(chamber_length=length_m))
        assert cad.get('error'), (
            f'{length_m} m kamara boyu sessizce kabul edildi')
        assert 'chamber_length_out_of_range' in cad['error']
        assert cad['assembly_meshes'] == []

    def test_bant_disi_girdi_ile_girdisizlik_ayirt_edilir(self):
        """Kusurun imzası: 5 m, 15 mm ve "alan yok" AYNI motoru çiziyordu."""
        uzun = _assembly(_base_motor(chamber_length=5.5))   # D26: bant DIŞI
        kisa = _assembly(_base_motor(chamber_length=0.015))
        yok = _base_motor()
        yok.pop('chamber_length')
        yoksa = _assembly(yok)

        assert uzun.get('error') and kisa.get('error')
        assert not yoksa.get('error')
        # Üçü aynı 300 mm'lik kamarayı ÜRETEMEZ
        assert uzun['error'] != kisa['error']
        chamber = _mesh_by_name(yoksa['assembly_meshes'], 'Chamber')
        boy_m = float(np.asarray(chamber.vertices)[:, 2].max())
        assert boy_m != pytest.approx(0.300, abs=1e-6), (
            'girdisiz koşum yine 300 mm uyduruyor')

    def test_lstar_yoksa_boy_uydurulmaz(self):
        """L* de yoksa türetme yapılamaz; 1,0 m'lik varsayılan L* YASAK."""
        motor = _base_motor()
        motor.pop('chamber_length')
        motor.pop('l_star')
        cad = _assembly(motor)
        assert cad.get('error')
        assert 'chamber_length_not_available' in cad['error']

    def test_lstar_turetmesi_kelepcelenmez(self):
        """Türetilen boy [0,3 - 2,0] m aralığına KELEPÇELENMEZ."""
        motor = _base_motor()
        motor.pop('chamber_length')
        motor['l_star'] = 1.0
        cad = _assembly(motor)
        assert not cad.get('error'), cad.get('error')

        beklenen = (motor['l_star'] * (motor['throat_diameter'] / 2) ** 2
                    / (motor['chamber_diameter'] / 2) ** 2)
        assert beklenen < 0.3, 'bu koşum eski kelepçeyi tetiklemiyor'
        chamber = _mesh_by_name(cad['assembly_meshes'], 'Chamber')
        cizilen = float(np.asarray(chamber.vertices)[:, 2].max())
        assert cizilen == pytest.approx(beklenen, rel=1e-9), (
            f'çizilen kamara {cizilen} m, L* türetmesi {beklenen} m')
        assert cizilen != pytest.approx(0.300, abs=1e-6)

    def test_cizilen_boyun_kaynagi_yaninda_yazar(self):
        """Sayının nereden geldiği okunabilmeli (künye kazanılır)."""
        cad = _assembly(_base_motor())
        kaynak = cad['performance_summary']['geometry_summary'][
            'chamber_length_source']
        assert kaynak == 'solver/user chamber_length'

        turetilmis = _base_motor()
        turetilmis.pop('chamber_length')
        kaynak2 = _assembly(turetilmis)['performance_summary'][
            'geometry_summary']['chamber_length_source']
        assert 'L*' in kaynak2 and kaynak2 != kaynak

    def test_override_de_ayni_banda_tabi(self):
        motor = _base_motor(design_config={'motor': {
            'chamber_length_override': 9000.0}})
        cad = _assembly(motor)
        assert cad.get('error')
        assert 'chamber_length_override_out_of_range' in cad['error']


# ---------------------------------------------------------------------------
# P9B1-06 — tane ya OLDUĞU GİBİ çizilir ya HİÇ çizilmez
# ---------------------------------------------------------------------------

class TestTaneKirpilmaz:

    def test_kamaradan_uzun_tane_cizilmez(self):
        motor = _base_motor()
        motor['grain_design']['grain_length_mm'] = 3387.0   # kamara 500 mm
        cad = _assembly(motor)
        assert not cad.get('error'), cad.get('error')

        assert _mesh_by_name(cad['assembly_meshes'], 'Fuel Grain') is None, \
            'kamaradan uzun tane yine çiziliyor (kırpılmış olarak)'
        sebep = cad['performance_summary']['geometry_summary'][
            'grain_not_drawn_reason']
        assert sebep and sebep.startswith('grain_longer_than_chamber')
        assert '3387.0 mm' in sebep and '500.0 mm' in sebep

    def test_sigan_tane_yuzde_iki_kisalmaz(self):
        """Sığan tane bile ``0.98 x L``ye kırpılıyordu — sessiz %2 kayıp."""
        motor = _base_motor()
        motor['grain_design']['grain_length_mm'] = 498.0    # kamara 500 mm
        cad = _assembly(motor)
        grain = _mesh_by_name(cad['assembly_meshes'], 'Fuel Grain')
        assert grain is not None, 'sığan tane çizilmedi'

        z = np.asarray(grain.vertices)[:, 2]
        cizilen_mm = (float(z.max()) - float(z.min())) * 1000.0
        assert cizilen_mm == pytest.approx(498.0, abs=1e-6), (
            f'tane {cizilen_mm:.3f} mm çizildi, çözücü 498,0 mm dedi')
        # Eski kırpma 0.98 x 500 = 490 mm üretiyordu
        assert cizilen_mm != pytest.approx(490.0, abs=1e-3)

    def test_tane_cizildiyse_gerekce_bos_kalir(self):
        cad = _assembly(_base_motor())
        assert _mesh_by_name(cad['assembly_meshes'], 'Fuel Grain') is not None
        assert cad['performance_summary']['geometry_summary'][
            'grain_not_drawn_reason'] is None

    def test_dis_cap_yoksa_tane_cizilmez(self):
        """P9B1-04 kapısı bu sınıfın içinden de kilitlenir.

        Yukarıdaki üç bekçi "tane ÇİZİLİR" diyor; onları yeşil tutmanın
        gevşek yolu, dış çap yokken uydurma bir liner ile yine çizmek
        olurdu. Bu bekçi o yolu kapatır: çözücü dış çapı yayımlamıyorsa
        tane çizilMEZ ve sebebi ADIYLA yazılır.
        """
        motor = _base_motor()
        motor['grain_design'].pop('outer_diameter_mm')
        cad = _assembly(motor)
        assert _mesh_by_name(cad['assembly_meshes'], 'Fuel Grain') is None, (
            'dış çap yokken tane yine çiziliyor — uydurma liner geri gelmiş '
            'olabilir (P9B1-04)')
        sebep = cad['performance_summary']['geometry_summary'][
            'grain_not_drawn_reason']
        assert sebep and sebep.startswith('grain_outer_diameter_not_available')


# ---------------------------------------------------------------------------
# P9B1-19 — sıvı kesitteki cidar ÇÖZÜCÜDEN gelir
# ---------------------------------------------------------------------------

def _wall_trace(motor):
    gen = DetailedCADGenerator()
    basis = _cross_section_basis(motor)
    traces = gen._create_cross_section_components(
        motor['chamber_diameter'] / 1000.0, motor['chamber_length'] / 1000.0,
        motor['throat_diameter'] / 1000.0, motor['exit_diameter'] / 1000.0,
        motor['nozzle_length'] / 1000.0, motor, basis=basis)
    return basis, traces[0]


class TestKesitCidariCozucuden:

    def test_cidar_sabit_8mm_degil(self):
        motor = _liquid_motor()
        basis, trace = _wall_trace(motor)
        assert basis['chamber_wall_thickness_mm'] == pytest.approx(5.0)
        assert basis['chamber_wall_thickness_mm'] != pytest.approx(8.0)

        bore_m = motor['chamber_diameter'] / 1000.0
        dis_yaricap = max(float(v) for v in trace.y)
        assert dis_yaricap == pytest.approx(bore_m / 2.0 + 0.005, abs=1e-9), (
            f'kesitin dış hattı {dis_yaricap * 1000.0:.3f} mm yarıçapta, '
            f'çözücünün 5 mm cidarıyla tutmuyor')
        assert '5.00 mm' in trace.name

    @pytest.mark.parametrize('wall_mm', [3.0, 12.0, 20.0])
    def test_cidar_kullaniciyla_birlikte_hareket_eder(self, wall_mm):
        motor = _liquid_motor()
        motor['structural_analysis']['chamber_structure']['wall_thickness'] = \
            wall_mm
        basis, trace = _wall_trace(motor)
        assert basis['chamber_wall_thickness_mm'] == pytest.approx(wall_mm)
        dis_yaricap = max(float(v) for v in trace.y)
        assert dis_yaricap == pytest.approx(
            motor['chamber_diameter'] / 2000.0 + wall_mm / 1000.0, abs=1e-9)

    def test_cidar_yoksa_dis_hat_cizilmez(self):
        motor = _liquid_motor(structural_analysis=_MISSING)
        basis, trace = _wall_trace(motor)
        assert basis['chamber_wall_thickness_m'] is None
        assert trace.name.startswith('Chamber Bore')
        assert NOT_AVAILABLE_SPEC in trace.name
        # Çizilen tek profil kamara deliğidir: yarıçap tam bore/2
        assert max(float(v) for v in trace.y) == pytest.approx(
            motor['chamber_diameter'] / 2000.0, abs=1e-12)


# ---------------------------------------------------------------------------
# P9B1-20 — soğutma kanalı sayısı ÇÖZÜCÜDEN gelir
# ---------------------------------------------------------------------------

def _kanal_izleri(motor):
    gen = DetailedCADGenerator()
    basis = _cross_section_basis(motor)
    return basis, gen._create_cooling_channels_cross_section(0.12, 0.30,
                                                             basis=basis)


class TestKanalSayisiCozucuden:

    @pytest.mark.parametrize('n', [1, 12, 40, 64])
    def test_cizilen_kanal_sayisi_cozucununki(self, n):
        motor = _liquid_motor(cooling_system={'cooling_channels': n})
        basis, izler = _kanal_izleri(motor)
        assert basis['cooling_channels_solver'] == n
        assert basis['cooling_channels_drawn'] == n
        assert len(izler) == n, f'çözücü {n} kanal dedi, {len(izler)} çizildi'

    def test_yirmidort_sabiti_bitti(self):
        """Çözücü 80 derken 24 çizen sabit ortadan kalkmalı."""
        motor = _liquid_motor()          # çözücü 80 kanal
        basis, izler = _kanal_izleri(motor)
        assert basis['cooling_channels_solver'] == 80
        assert len(izler) != 24, 'kesit hâlâ 24 kanal çiziyor'
        assert len(izler) == CROSS_SECTION_MAX_CHANNELS
        assert 'render limit' in basis['cooling_channels_source']
        assert '80 channels' in basis['cooling_channels_source']

    def test_kanal_yoksa_kanal_cizilmez(self):
        motor = _liquid_motor(cooling_system=_MISSING)
        basis, izler = _kanal_izleri(motor)
        assert basis['cooling_channels_solver'] is None
        assert izler == []
        assert 'not available' in basis['cooling_channels_source']

    def test_tablo_ile_kesit_ayni_seyi_soyler(self):
        """Tablo "NOT AVAILABLE" derken kesit kanal çizemez."""
        motor = _liquid_motor(cooling_system=_MISSING)
        tablo = DetailedCADGenerator()._get_component_details(motor)
        basis, izler = _kanal_izleri(motor)
        assert tablo['cooling']['channel_count'] == NOT_AVAILABLE_SPEC
        assert len(izler) == 0

        motor2 = _liquid_motor(cooling_system={'cooling_channels': 18})
        tablo2 = DetailedCADGenerator()._get_component_details(motor2)
        basis2, izler2 = _kanal_izleri(motor2)
        assert tablo2['cooling']['channel_count'] == 18
        assert basis2['cooling_channels_solver'] == 18 == len(izler2)


# ---------------------------------------------------------------------------
# P9B1-21 — enjektör delikleri ARAYÜZ SABİTİNDEN çizilmez
# ---------------------------------------------------------------------------

def _delik_izleri(motor):
    gen = DetailedCADGenerator()
    basis = _cross_section_basis(motor)
    traces = gen._create_injector_cross_section(0.12, motor, basis=basis)
    delikler = [t for t in traces if t.mode == 'markers']
    yuz = [t for t in traces if t.mode == 'lines']
    return basis, delikler, yuz


class TestEnjektorDeligiArayuzSabitindenGelmez:

    def test_cozucunun_sayisi_kazanir(self):
        motor = _liquid_motor()   # injector_holes=24 (arayüz), çözücü 41
        basis, delikler, _yuz = _delik_izleri(motor)
        assert basis['injector_holes_solver'] == 41
        assert basis['injector_holes_drawn'] == 41
        assert len(delikler) == 41, (
            f'{len(delikler)} delik çizildi; çözücü 41 eleman raporladı')
        assert len(delikler) != 24, 'kesit hâlâ arayüz sabitini çiziyor'

    def test_arayuz_sabiti_tek_basina_delik_actiramaz(self):
        """``injector_holes`` VARSA ama tasarım sonucu YOKSA delik açılmaz."""
        motor = _liquid_motor(injector_design=_MISSING)
        assert motor['injector_holes'] == 24     # arayüz sabiti duruyor
        basis, delikler, yuz = _delik_izleri(motor)
        assert basis['injector_holes_solver'] is None
        assert delikler == []
        assert 'is NOT a design result' in basis['injector_holes_source']
        # Efsanede sebep görünür
        assert len(yuz) == 1 and 'holes not drawn' in yuz[0].name

    def test_tablo_ile_kesit_ayni_seyi_soyler(self):
        motor = _liquid_motor(injector_design=_MISSING)
        tablo = DetailedCADGenerator()._get_component_details(motor)
        basis, delikler, _yuz = _delik_izleri(motor)
        assert tablo['injector']['hole_count'] == NOT_AVAILABLE_SPEC
        assert len(delikler) == 0

        motor2 = _liquid_motor(
            injector_design={'number_of_orifices': 9,
                             'injector_type': 'coaxial'})
        tablo2 = DetailedCADGenerator()._get_component_details(motor2)
        basis2, delikler2, _y = _delik_izleri(motor2)
        assert tablo2['injector']['hole_count'] == 9
        assert basis2['injector_holes_solver'] == 9
        assert len(delikler2) >= 1

    def test_cok_delikte_kirpma_beyanli(self):
        motor = _liquid_motor(
            injector_design={'number_of_elements': 500,
                             'injector_type': 'unlike_impinging'})
        basis, delikler, _yuz = _delik_izleri(motor)
        assert basis['injector_holes_solver'] == 500
        assert basis['injector_holes_drawn'] == CROSS_SECTION_MAX_INJECTOR_HOLES
        assert len(delikler) == CROSS_SECTION_MAX_INJECTOR_HOLES
        assert 'render limit' in basis['injector_holes_source']
        assert '500 elements' in basis['injector_holes_source']

    def test_desen_bilinmiyorsa_varsayim_adlandirilir(self):
        motor = _liquid_motor(injector_type=_MISSING,
                              injector_design={'number_of_elements': 6})
        basis = _cross_section_basis(motor)
        assert basis['injector_pattern'] == 'unlike_impinging'
        assert basis['injector_pattern_source'].startswith('ASSUMED')

    def test_kesit_kunyesi_cikti_ile_birlikte_yayimlanir(self):
        """Çizilen sayı YAYIMLANMALI ki tüketici çelişkiyi görebilsin."""
        out = _silent(DetailedCADGenerator().generate_liquid_motor_cad,
                      _liquid_motor())
        basis = out['cross_section_basis']
        assert basis['injector_holes_solver'] == 41
        assert basis['cooling_channels_solver'] == 80
        assert basis['chamber_wall_thickness_mm'] == pytest.approx(5.0)
        # Tablo ile künye aynı sayıyı söylemeli
        assert out['component_details']['injector']['hole_count'] == 41
        assert out['component_details']['cooling']['channel_count'] == 80


# ---------------------------------------------------------------------------
# P9B1-24 — çözücünün "bu açılar VARSAYILAN" beyanı düşürülmez
# ---------------------------------------------------------------------------

class TestAciKunyesiKazanilir:

    def _angle_source(self, angles_source):
        motor = _base_motor()
        if angles_source is not None:
            motor['nozzle_angles']['angles_source'] = angles_source
        return MotorCADDesigner()._generate_technical_drawings(
            motor)['nozzle']['angle_source']

    def test_varsayilan_beyani_dusurulmez(self):
        kunye = self._angle_source('conical_default_30_15')
        assert 'conical_default_30_15' in kunye
        assert 'DEFAULT' in kunye
        assert 'NOT a user input' in kunye

    def test_kullanici_girdisi_varsayilan_diye_etiketlenmez(self):
        kunye = self._angle_source('user_input')
        assert 'user_input' in kunye
        assert 'DEFAULT' not in kunye

    def test_iki_kosum_ayni_kunyeyi_basamaz(self):
        """Kusurun imzası: iki koşum BİREBİR aynı künyeyi basıyordu."""
        assert (self._angle_source('conical_default_30_15')
                != self._angle_source('user_input'))

    def test_beyan_yoksa_iddia_edilmez(self):
        """Hibrit çözücüsü beyan yayımlamıyor -> künye "bilinmiyor" demeli."""
        kunye = self._angle_source(None)
        assert 'does not state' in kunye
        assert 'user_input' not in kunye
        assert 'DEFAULT' not in kunye

    @pytest.mark.parametrize('bozuk', ['', '   ', 42, None, {}])
    def test_bozuk_beyan_kunye_uretmez(self, bozuk):
        kunye = _nozzle_angle_source_label({'nozzle_angles':
                                            {'angles_source': bozuk}})
        assert 'does not state' in kunye

    def test_kunye_cozucunun_temel_kaynagini_korur(self):
        """Beyan eklenirken eski künye metni KAYBOLMAZ (geriye dönük)."""
        for kaynak in (None, 'user_input', 'conical_default_30_15'):
            assert self._angle_source(kaynak).startswith(
                'solver nozzle_angles / nozzle_contour')
