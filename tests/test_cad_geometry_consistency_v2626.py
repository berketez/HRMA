"""CAD BEKÇİSİ: ölçü tablosu ile KATI MODELİN gerçek geometrisi tutmalı.

Bu dosya vaka listelemez, ÖLÇER. Teknik çizim sözlüğündeki her imalat ölçüsü,
aynı koşuda üretilen trimesh katısının köşe koordinatlarından geri okunur ve
ikisi karşılaştırılır. Kusur sınıfı şudur: **çizim ile katı aynı motoru
anlatmıyor.** Bu sınıf, sayıların tek tek "makul" görünmesi yüzünden gözden
kaçar; ancak iki bağımsız temsil karşılaştırılınca ortaya çıkar.

v2.6.26 denetiminde ölçülen ve burada kilitlenen kusurlar:

* **Y3** ``technical_drawings.chamber.outer_diameter`` motorun İÇ çapını
  yazıyordu, hemen yanında ayrı bir ``wall_thickness`` alanı dururken. Katı
  model ise aynı değeri doğru şekilde iç yarıçap kabul ediyordu. Ölçüldü:
  mesh köşelerinden okunan gerçek dış çap 184,37 mm iken tablo 152,53 mm
  diyordu (152,53 + 2 x 15,92 = 184,37). Atölye Ø152 mm boru alıp 15,92 mm
  cidar bırakacak şekilde tornalasa kalan delik grain'in dış çapından küçük
  olurdu — parça takılmazdı. ``performance_summary.max_diameter`` aynı hatayı
  taşıyordu, gövde tüpü seçimi 2 x cidar kadar küçük çıkıyordu.

* **Y5** CAD çizimi ve 3B katı kullanıcının ``wall_thickness`` girdisini YOK
  SAYIP her zaman yapısal analizin ÖNERDİĞİ kalınlığı çiziyordu. Ölçüldü:
  kullanıcı 3 / 5 / 10 / 20 mm girse de çizim 15,92 mm ve kamara kütlesi
  232,04 kg SABİT kalıyordu. Daha kötüsü, emniyet katsayıları kullanıcının
  kalınlığına göre hesaplanıyordu — yani ekrandaki SF çizilen parçaya ait
  değildi (Alüminyum 6061: çizim 49,92 mm, panel kullanıcının 5 mm'si için
  SF 0,466 "güvensiz").

* **K2** Aynı koşuda İKİ bağımsız enjektör çözücüsü koşuyordu; teknik çizim
  birinden, 3B mesh diğerinden okuyordu (125 delik x 0,957 mm'ye karşı
  11 delik x 2,457 mm). Ayrıca delik sayısı bir kaynaktan, basınç düşümü
  diğerinden alınabiliyordu (ΔP 4,00 bar yerine 30,37 bar) — hiçbir çözücüde
  var olmayan MELEZ bir enjektör raporlanıyordu.

Ölçüm yöntemi ``trimesh`` köşe koordinatlarıdır: her katı için
``r = hypot(x, y)`` dizisinin en büyüğü parçanın gerçek dış yarıçapıdır.
Revolve poligonal olduğu için hacimlerde ~%0,6 fasetleme sapması vardır;
YARIÇAPLAR ise poligonun köşelerinden geçtiği için TAM okunur, bu yüzden
bekçi çap üzerinden ölçer.
"""

import contextlib
import io
import json
import math
import pathlib
import shutil
import subprocess

import numpy as np
import pytest

from hrma.export.cad_visualization import (
    NOT_AVAILABLE_SPEC,
    MotorCADDesigner,
    _injector_spec,
)


def _silent(fn, *args, **kwargs):
    """Çözücülerin ve CAD katmanının print gürültüsünü yutar."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Gerçek uygulama koşusu — /calculate ile, kablolamanın tamamı devrede
# ---------------------------------------------------------------------------
#
# Doğrudan HybridRocketEngine çağırmak YETMEZ: enjektör panelinin sonucunu
# CAD'e bağlayan dikiş app.py'dedir ve K2 kusuru tam orada yaşıyordu. Bekçi
# kullanıcının gerçekten gördüğü yolu ölçmelidir.

from tests.test_field_wiring_layer_b import HYBRID_BASE  # noqa: E402


def _calculate(**overrides):
    from hrma.app import app

    client = app.test_client()
    response = _silent(
        client.post, '/calculate',
        json=dict(HYBRID_BASE, **overrides),
        headers={'Host': '127.0.0.1:8080'},
    )
    assert response.status_code == 200, f'/calculate HTTP {response.status_code}'
    return response.get_json()


def _cad_input(payload_result):
    """app.py'nin CAD'e verdiği sözlüğün AYNISI (panel sonucu iliştirilmiş)."""
    motor = dict(payload_result['motor'])
    panel = payload_result.get('injector') or {}
    if panel:
        motor['injector_results'] = panel
    return motor


def _mesh_radii(assembly_meshes):
    """Her katının GERÇEK dış yarıçapı [m] — mesh köşe koordinatlarından."""
    radii = {}
    for name, mesh in assembly_meshes:
        vertices = np.asarray(mesh.vertices)
        radii[name] = float(np.hypot(vertices[:, 0], vertices[:, 1]).max())
    return radii


@pytest.fixture(scope='module')
def run():
    """Varsayılan hibrit koşu (kullanıcı 5 mm cidar girmiş)."""
    return _calculate()


@pytest.fixture(scope='module')
def cad(run):
    motor = _cad_input(run)
    return _silent(MotorCADDesigner().generate_3d_motor_assembly, motor)


@pytest.fixture(scope='module')
def radii(cad):
    return _mesh_radii(cad['assembly_meshes'])


# ---------------------------------------------------------------------------
# Y3 — ölçü tablosu katı modelin GERÇEK geometrisiyle tutmalı
# ---------------------------------------------------------------------------

class TestDrawingMatchesSolid:

    def test_outer_diameter_is_really_the_outer_diameter(self, cad, radii):
        """Çizimdeki dış çap, katının mesh'ten okunan dış çapı olmalı."""
        chamber = cad['technical_drawings']['chamber']
        drawn_od_mm = chamber['outer_diameter']
        assert isinstance(drawn_od_mm, (int, float)), \
            f'dış çap sayı değil: {drawn_od_mm!r}'

        solid_od_mm = 2.0 * radii['Chamber'] * 1000.0
        assert drawn_od_mm == pytest.approx(solid_od_mm, abs=1e-6), (
            f'ölçü tablosu {drawn_od_mm:.3f} mm dış çap yazıyor ama katının '
            f'gerçek dış çapı {solid_od_mm:.3f} mm '
            f'(fark {abs(drawn_od_mm - solid_od_mm):.3f} mm)')

    def test_inner_diameter_is_the_bore_not_the_outside(self, cad, run):
        """İç çap kamara deliği olmalı; dış çapla karışmamalı."""
        chamber = cad['technical_drawings']['chamber']
        bore_mm = run['motor']['chamber_diameter'] * 1000.0
        assert chamber['inner_diameter'] == pytest.approx(bore_mm, abs=1e-6)
        assert chamber['outer_diameter'] > chamber['inner_diameter'], \
            'dış çap iç çaptan büyük olmalı'

    def test_wall_thickness_closes_the_diameter_arithmetic(self, cad):
        """ic + 2 x cidar = dis. Üçü aynı parçayı anlatmalı."""
        chamber = cad['technical_drawings']['chamber']
        expected = chamber['inner_diameter'] + 2.0 * chamber['wall_thickness']
        assert chamber['outer_diameter'] == pytest.approx(expected, abs=1e-9), (
            f"{chamber['inner_diameter']:.3f} + 2 x "
            f"{chamber['wall_thickness']:.3f} != "
            f"{chamber['outer_diameter']:.3f} mm")

    def test_max_diameter_is_the_envelope_not_the_bore(self, cad, radii, run):
        """Zarf çapı gövde tüpü seçimine girer; iç çap yazılırsa tüp küçük gelir."""
        geometry = cad['performance_summary']['geometry_summary']
        envelope_mm = 2.0 * max(radii.values()) * 1000.0
        bore_mm = run['motor']['chamber_diameter'] * 1000.0

        assert geometry['max_diameter'] == pytest.approx(envelope_mm, abs=1e-6), (
            f"max_diameter {geometry['max_diameter']:.3f} mm, katının gerçek "
            f'zarfı {envelope_mm:.3f} mm')
        assert geometry['max_diameter'] > bore_mm, \
            'zarf çapı iç çaptan büyük olmalı (2 x cidar kadar)'
        # İç çap kaybolmamalı; ayrı alanda taşınmalı
        assert geometry['chamber_bore_diameter'] == pytest.approx(bore_mm, abs=1e-6)

    def test_grain_fits_inside_the_drawn_bore(self, cad, radii):
        """Grain'in dış çapı çizilen deliğe SIĞMALI (Y3'ün imalat sonucu)."""
        chamber = cad['technical_drawings']['chamber']
        grain_od_mm = 2.0 * radii['Fuel Grain'] * 1000.0
        assert grain_od_mm <= chamber['inner_diameter'] + 1e-6, (
            f'grain dış çapı {grain_od_mm:.2f} mm, çizilen delik '
            f"{chamber['inner_diameter']:.2f} mm — parça takılmaz")


# ---------------------------------------------------------------------------
# Y5 — kullanıcının cidar kalınlığı ÇİZİLENE yansımalı
# ---------------------------------------------------------------------------

class TestUserWallThicknessIsDrawn:

    @pytest.mark.parametrize('wall_mm', [3.0, 10.0, 20.0])
    def test_drawing_and_solid_follow_the_user(self, wall_mm):
        """Girilen cidar hem ölçü tablosuna hem katıya birebir geçmeli."""
        result = _calculate(wall_thickness=wall_mm)
        motor = _cad_input(result)
        cad = _silent(MotorCADDesigner().generate_3d_motor_assembly, motor)

        chamber = cad['technical_drawings']['chamber']
        assert chamber['wall_thickness'] == pytest.approx(wall_mm, abs=1e-6), (
            f"kullanıcı {wall_mm} mm girdi, çizim "
            f"{chamber['wall_thickness']} mm gösteriyor")

        radii = _mesh_radii(cad['assembly_meshes'])
        solid_wall_mm = (2.0 * radii['Chamber'] * 1000.0
                         - chamber['inner_diameter']) / 2.0
        assert solid_wall_mm == pytest.approx(wall_mm, abs=1e-6), (
            f'katının gerçek cidarı {solid_wall_mm:.3f} mm, kullanıcı '
            f'{wall_mm} mm girdi')

    def test_chamber_mass_moves_with_the_user_wall(self):
        """Kütle dökümü de kullanıcının cidarını izlemeli (sabit kalmamalı)."""
        masses = {}
        for wall_mm in (3.0, 20.0):
            result = _calculate(wall_thickness=wall_mm)
            summary = _silent(
                MotorCADDesigner()._generate_cad_performance_summary,
                _cad_input(result))
            masses[wall_mm] = summary['mass_breakdown']['chamber_mass']
        assert masses[20.0] > 3.0 * masses[3.0], (
            f'kamara kütlesi cidarla değişmiyor: {masses}')

    def test_recommended_thickness_is_still_reported(self, cad):
        """Öneri kaybolmamalı — kullanıcının kalınlığıyla YAN YANA durmalı."""
        chamber = cad['technical_drawings']['chamber']
        assert isinstance(chamber['wall_thickness_recommended'], (int, float))
        assert chamber['wall_thickness_recommended'] > 0

    def test_disagreement_is_stated_out_loud(self, cad):
        """Çizilen ile önerilen farklıysa bu AÇIKÇA yazılmalı."""
        chamber = cad['technical_drawings']['chamber']
        drawn = chamber['wall_thickness']
        recommended = chamber['wall_thickness_recommended']
        if abs(drawn - recommended) > 1e-6:
            note = chamber['wall_thickness_note']
            assert note, 'çizilen ile önerilen farklı ama uyarı yok'
            assert f'{drawn:.2f}' in note and f'{recommended:.2f}' in note
            # Hangi emniyet katsayısının hangi kalınlığa ait olduğu yazmalı
            assert 'safety factor' in note.lower()
        assert chamber['safety_factor_at_drawn_wall'] != NOT_AVAILABLE_SPEC

    def test_safety_factor_belongs_to_the_drawn_wall(self, run, cad):
        """Çizimdeki SF, yapısal analizin DEĞERLENDİRDİĞİ kalınlığa ait olmalı."""
        chamber_analysis = run['motor']['structural_analysis']['chamber_analysis']
        chamber = cad['technical_drawings']['chamber']
        assert chamber['wall_thickness'] == pytest.approx(
            chamber_analysis['wall_thickness_used_mm'], abs=1e-6), (
            'çizilen cidar, emniyet katsayısının hesaplandığı cidar değil')
        assert chamber['safety_factor_at_drawn_wall'] == pytest.approx(
            chamber_analysis['safety_factor_total'])

    def test_sizing_mode_still_draws_the_recommendation(self):
        """Kullanıcı cidar VERMEDİYSE (boyutlandırma modu) öneri çizilir."""
        from hrma.export.cad_visualization import _chamber_wall_design
        design = _chamber_wall_design({
            'structural_analysis': {'chamber_analysis': {
                'design_mode': 'size',
                'recommended_thickness': 8.0,
                'wall_thickness_used_mm': 8.0,
            }}})
        assert design['thickness_m'] == pytest.approx(0.008)
        assert design['source'].startswith('structural analysis')
        assert design['note'] is None, 'ikisi eşitken uyarı üretilmemeli'

    def test_no_structural_result_gives_no_manufacturing_number(self):
        """Yapısal sonuç yoksa imalat ölçüsü UYDURULMAZ."""
        drawings = MotorCADDesigner()._generate_technical_drawings({
            'chamber_diameter': 0.1, 'chamber_length': 0.4,
            'throat_diameter': 0.02, 'exit_diameter': 0.05})
        assert drawings['chamber']['wall_thickness'] == NOT_AVAILABLE_SPEC
        assert drawings['chamber']['outer_diameter'] == NOT_AVAILABLE_SPEC, \
            'cidar bilinmiyorken dış çap yazmak uydurmadır'


# ---------------------------------------------------------------------------
# K2 — çizim, katı ve kütle AYNI enjektörü anlatmalı
# ---------------------------------------------------------------------------

class TestInjectorSingleSourceReachesTheSolid:

    def test_drawing_uses_the_panel_result(self, run, cad):
        """Ekran tablosu ile teknik çizim aynı deliği göstermeli."""
        panel = run.get('injector') or {}
        assert panel.get('n_holes'), 'test koşusu panel sonucu üretmeli'
        drawing = cad['technical_drawings']['injector']
        assert drawing['orifice_count'] == int(round(panel['n_holes']))
        assert drawing['orifice_diameter'] == pytest.approx(
            panel['hole_diameter'])

    def test_pressure_drop_is_not_borrowed_from_the_other_solver(self, run):
        """Delik sayısı bir kaynaktan, ΔP diğerinden alınamaz (melez yasağı)."""
        motor = _cad_input(run)
        spec = _injector_spec(motor)
        panel = run.get('injector') or {}
        other = (run['motor'].get('injector_design') or {})

        assert spec['n_orifices'] == int(round(panel['n_holes']))
        assert spec['pressure_drop_bar'] == pytest.approx(
            panel['pressure_drop']), (
            f"ΔP {spec['pressure_drop_bar']} bar panelin "
            f"{panel['pressure_drop']} bar değeri değil")
        # Diğer çözücünün ΔP'si gerçekten farklı olmalı ki bekçi anlamlı olsun
        if other.get('injection_pressure_drop_bar'):
            assert not math.isclose(
                other['injection_pressure_drop_bar'], panel['pressure_drop'],
                rel_tol=1e-3), 'iki çözücü aynı ΔP veriyor; bekçi kör kalır'

    def test_solid_drills_the_same_holes_as_the_drawing(self, run):
        """3B katının GERÇEKTEN açtığı delikler çizimdekiyle aynı olmalı.

        Plaka hacmini karşılaştırmak yeterli DEĞİLDİR: yanlış desen bile
        plakanın %0,2'sini oynatır ve gürültüde kaybolur. Bu yüzden delinmemiş
        referans silindirle FARK alınır — yani mesh'ten SÖKÜLEN hacim ölçülür.
        """
        import trimesh

        from hrma.export.cad_visualization import MESH_MAX_INJECTOR_ORIFICES

        motor = _cad_input(run)
        spec = _injector_spec(motor)
        designer = MotorCADDesigner()
        cad = _silent(designer.generate_3d_motor_assembly, motor)
        drawing = cad['technical_drawings']['injector']

        assert drawing['orifice_count'] == spec['n_orifices']
        assert drawing['orifice_diameter'] == pytest.approx(
            spec['orifice_diameter_mm'])

        plate = dict(cad['assembly_meshes'])['Injector']
        radius = motor['chamber_diameter'] / 2.0
        thickness = 0.03  # _create_injector_head ile aynı
        # AYNI fasetlemeye sahip delinmemiş referans (fasetleme hatası düşer)
        undrilled = trimesh.creation.cylinder(radius=radius, height=thickness)
        removed = undrilled.volume - plate.volume

        drilled = min(spec['n_orifices'], MESH_MAX_INJECTOR_ORIFICES)
        r_hole = spec['orifice_diameter_mm'] / 2000.0
        expected = drilled * math.pi * r_hole ** 2 * (thickness + 0.001)
        assert removed == pytest.approx(expected, rel=0.05), (
            f'mesh {removed * 1e9:.1f} mm3 malzeme sökmüş; çizimdeki desen '
            f'({drilled} x d{spec["orifice_diameter_mm"]:.3f} mm) '
            f'{expected * 1e9:.1f} mm3 sökerdi — katı ile çizim farklı '
            f'enjektör anlatıyor')

    def test_no_injector_data_means_no_holes_are_invented(self):
        """İki kaynak da yoksa delik açılmaz — 8 delikli varsayılan uydurulmaz."""
        import trimesh

        bare = {'chamber_diameter': 0.1, 'chamber_length': 0.4,
                'throat_diameter': 0.02, 'exit_diameter': 0.05,
                'mdot_ox': 1.0, 'oxidizer_density': 1200}
        designer = MotorCADDesigner()
        cad = _silent(designer.generate_3d_motor_assembly, bare)
        assert cad.get('technical_drawings'), 'CAD üretimi çökmemeli'
        assert cad['technical_drawings']['injector']['orifice_count'] == \
            NOT_AVAILABLE_SPEC

        # Plakadan HİÇ malzeme sökülmemiş olmalı (delinmemiş referansla birebir)
        plate = dict(cad['assembly_meshes'])['Injector']
        undrilled = trimesh.creation.cylinder(radius=0.1 / 2, height=0.03)
        assert plate.volume == pytest.approx(undrilled.volume, rel=1e-9), (
            f'veri yokken plakadan {(undrilled.volume - plate.volume) * 1e9:.1f}'
            ' mm3 sökülmüş — uydurma delik deseni açılmış')


# ---------------------------------------------------------------------------
# O3 — lüle kütlesi kullanıcının SEÇTİĞİ malzemeden gelmeli
# ---------------------------------------------------------------------------

class TestNozzleMassUsesSelectedMaterial:

    @pytest.mark.parametrize('material,density', [
        ('graphite', 1800.0), ('tungsten', 19300.0), ('steel', 7850.0)])
    def test_mass_scales_with_the_selected_density(self, material, density):
        """Aynı geometri, farklı malzeme -> kütle yoğunlukla orantılı olmalı."""
        result = _calculate(nozzle_material=material)
        motor = _cad_input(result)
        mass = MotorCADDesigner()._estimate_component_mass('nozzle', motor)

        from hrma.engines.nozzle_design import sample_nozzle_inner_contour
        points, _meta = sample_nozzle_inner_contour(motor)
        wall_m = (motor.get('nozzle_geometry') or {}).get('wall_thickness') / 1000.0
        # Cidar iç kontura DIŞARI eklenir (cad_visualization._nozzle_solid:613),
        # dolayısıyla hacim halka hacmidir: pi*((r+t)^2 - r^2)*dz.
        # Bu testin ilk sürümü ince-kabuk yaklaşımını (2*pi*r*t*dz) bekliyordu;
        # o yaklaşım pi*t^2*dz terimini atlar ve cidar kalınlaştıkça
        # (t=7,79 mm ölçüldü) kütleyi %7,7 eksik verir — yani beklenen değer
        # ÇİZİLEN katıya ait değildi. Bu sınıfın konusu yoğunluk seçimi
        # olduğu için ölçüt katının kendi geometrisine hizalandı.
        volume = 0.0
        for (z0, r0), (z1, r1) in zip(points[:-1], points[1:]):
            r_mid = (r0 + r1) / 2000.0
            volume += (math.pi * ((r_mid + wall_m) ** 2 - r_mid ** 2)
                       * abs((z1 - z0) / 1000.0))
        assert mass == pytest.approx(volume * density, rel=1e-9), (
            f'{material} lüle kütlesi seçilen malzemenin yoğunluğundan '
            f'gelmiyor (beklenen {volume * density:.5f} kg, gelen {mass:.5f})')

    def test_solver_declares_when_it_falls_back_to_steel(self, run):
        """Malzeme verilmediğinde SESSİZ çelik düşüşü olmamalı; beyan edilmeli."""
        geometry = ((run['motor'].get('nozzle_design') or {}).get('geometry')
                    or run['motor'].get('nozzle_geometry') or {})
        assert 'wall_material_source' in geometry, \
            'lüle cidar malzemesinin kaynağı raporlanmıyor'
        if geometry['wall_material_source'] != 'caller':
            assert geometry['wall_material_is_default'] is True
            assert geometry['wall_material_warning'], \
                'varsayılana düşüldü ama uyarı üretilmedi'
            assert str(int(geometry['wall_material_density'])) in \
                geometry['wall_material_warning']

    def test_nozzle_mass_matches_the_drawn_solid(self, run, cad, radii):
        """CAD kütlesi ÇİZİLEN lüle katısıyla tutmalı (çözücü yüzeyiyle değil).

        Çözücünün ``estimated_mass``'i yalnız diverjan koninin yüzeyini sayar;
        CAD katısı konverjanı da içerir. Ölçüldü: 0,03885 kg'a karşı katının
        gerçek kabuğu 0,08948 kg (2,30 kat) — kütle dökümü çizilen parçaya ait
        değildi.
        """
        motor = _cad_input(run)
        mass = cad['performance_summary']['mass_breakdown']['nozzle_mass']
        meshes = dict(cad['assembly_meshes'])
        from hrma.data.materials_db import get_material
        density = get_material(motor['nozzle_material'])['density']
        # Revolve fasetlemesi hacimde ~%1 sapma bırakır; oran 1'e yakın olmalı
        assert mass == pytest.approx(meshes['Nozzle'].volume * density,
                                     rel=0.05), (
            f'lüle kütlesi {mass:.5f} kg, çizilen katının kütlesi '
            f'{meshes["Nozzle"].volume * density:.5f} kg')


# ---------------------------------------------------------------------------
# Y4 — CAD kütle dökümü gerçekten geometri x yoğunluk mu?
# ---------------------------------------------------------------------------

class TestMassBreakdownIsGeometryTimesDensity:

    def test_chamber_mass_is_the_shell_volume_times_density(self, run, cad):
        """Kamara kütlesi elle kurulabilen hacim x yoğunluk olmalı."""
        from hrma.data.materials_db import get_material

        motor = run['motor']
        breakdown = cad['performance_summary']['mass_breakdown']
        inner_r = motor['chamber_diameter'] / 2.0
        outer_r = inner_r + breakdown['wall_thickness_mm'] / 1000.0
        volume = math.pi * motor['chamber_length'] * (outer_r ** 2 - inner_r ** 2)
        density = get_material(
            motor['structural_analysis']['design_parameters']['material']
        )['density']
        assert breakdown['chamber_mass'] == pytest.approx(volume * density,
                                                          rel=1e-9)

    def test_breakdown_agrees_with_structural_chamber_weight(self, run, cad):
        """CAD ve yapısal analiz aynı kamarayı tartmalı."""
        structural = run['motor']['structural_analysis']['weight_analysis']
        cad_mass = cad['performance_summary']['mass_breakdown']['chamber_mass']
        assert cad_mass == pytest.approx(structural['chamber_weight'], rel=0.01)

    def test_total_is_the_sum_of_its_parts(self, cad):
        breakdown = cad['performance_summary']['mass_breakdown']
        parts = (breakdown['chamber_mass'] + breakdown['nozzle_mass']
                 + breakdown['injector_mass'])
        assert breakdown['total_dry_mass'] == pytest.approx(parts, rel=1e-12)
        assert breakdown['mass_basis'], 'kütlenin dayanağı beyan edilmeli'
