"""Faz 6 / F7 — T13 bekçisi: girdap önleyici düzenek 1000 kat küçük iniyordu.

NEDEN BU DOSYA VAR
------------------
Sıvı motor çözücüsü ``anti_vortex_device`` sözlüğünü İKİ FARKLI birimle
yayımlıyor (``liquid_rocket_engine.py:5650-5673``):

    'diameter': av_diameter,                  # METRE
    'height':   av_height,                    # METRE
    'vane_radial_length_mm': ... * 1000.0,    # MİLİMETRE
    'vane_thickness': TANK_VANE_GAUGE_MM,     # MİLİMETRE

``hrma/export/cad_export.py`` ise ürettiği paketin tamamını milimetre olarak
beyan ediyor (``self.units = "mm"``, çizim künyesi ``'units': 'mm'``,
``project_info.units = 'mm'``) ve çapı doğrudan mm sanıyordu
(``diameter = av_config['diameter']  # mm``).

ÖLÇÜLDÜ (3 Ağustos 2026, 10 kN RP1/LOX, ``POST /export_tank_cad``):

    ÖNCE : oxidizer_tank_geometry.json -> anti_vortex_device.diameter
           = 0,235585 (paket mm diyor)          tank çapı 785,282 mm
           düzenek/tank oranı 0,0003   —  çözücünün beyanı 0,30
    SONRA: aynı alan 235,5846 mm, oran 0,30 (tam)

Aynı hata görünen yüzde de var (``liquid.html`` 3B tank görünümü) ama o dosya
başka bir ajanın; burada yalnız dışa aktarım tarafı kapatıldı.

DİKKAT — bu bekçilerin sınadığı şey DOĞRU davranıştır:
mm'ye çevrilmiş çap, çözücünün kendi geometrik özdeşliğini
(``diameter[mm] == 2 x vane_radial_length_mm``) ve kendi beyan ettiği
düzenek/tank oranını tutmalıdır. Düzeltme geri alınırsa bu dosyadaki
bekçilerin çoğu kırılır.
"""

import io
import json
import zipfile

import pytest

from hrma.engines.liquid_rocket_engine import (
    TANK_ANTIVORTEX_D_RATIO,
    TANK_ANTIVORTEX_H_RATIO,
)
from hrma.export.cad_export import (
    cad_generator,
    normalize_anti_vortex_mm,
    normalize_internal_structures,
)

#: Ölçüm koşumunda kullanılan gerçek tank boyutları (10 kN RP1/LOX).
OX_TANK_D_MM = 785.2819377980634
OX_TANK_L_MM = 1600.0
FUEL_TANK_D_MM = 647.4065211390316
FUEL_TANK_L_MM = 1320.0


def _engine():
    return __import__(
        'hrma.engines.liquid_rocket_engine', fromlist=['LiquidRocketEngine']
    ).LiquidRocketEngine(
        thrust=10000, chamber_pressure=20, mixture_ratio=2.5,
        fuel_type='rp1', oxidizer_type='lox')


@pytest.fixture(scope='module')
def solver_internals():
    """Çözücünün GERÇEK çıktısı — elle yazılmış sözlük değil.

    Elle kurulmuş bir sözlük, çözücü birimi bir gün değişirse bunu göremezdi;
    bekçi o zaman kendi uydurduğu veriyi doğrulardı.
    """
    eng = _engine()
    return {
        'oxidizer': eng._design_tank_internals(
            OX_TANK_D_MM / 1000.0, OX_TANK_L_MM / 1000.0, 'oxidizer',
            tank_pressure_pa=3.0e6, mdot=2.5),
        'fuel': eng._design_tank_internals(
            FUEL_TANK_D_MM / 1000.0, FUEL_TANK_L_MM / 1000.0, 'fuel',
            tank_pressure_pa=3.0e6, mdot=1.0),
    }


def _structural():
    return {'material': 'Aluminum 2024-T3', 'material_key': 'al_2024_t3',
            'yield_strength_mpa': 345.0, 'density_kg_m3': 2780.0,
            'pressure_rating': 42.0}


@pytest.fixture(scope='module')
def tank_data(solver_internals):
    """``/export_tank_cad`` uca giden gövdenin aynısı (tarayıcı bunu yollar)."""
    return {
        'oxidizer_tank': {
            'propellant_type': 'LOX',
            'dimensions': {'diameter': OX_TANK_D_MM, 'length': OX_TANK_L_MM,
                           'wall_thickness': 3.0},
            'structural': _structural(),
            'internal_structures': solver_internals['oxidizer'],
        },
        'fuel_tank': {
            'propellant_type': 'RP1',
            'dimensions': {'diameter': FUEL_TANK_D_MM,
                           'length': FUEL_TANK_L_MM, 'wall_thickness': 3.0},
            'structural': _structural(),
            'internal_structures': solver_internals['fuel'],
        },
    }


@pytest.fixture(scope='module')
def package(tank_data):
    """Kullanıcının indirdiği ZIP'in içindeki geometri dosyaları."""
    zip_path = cad_generator.generate_tank_cad(tank_data)
    with open(zip_path, 'rb') as fh:
        blob = fh.read()
    out = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for name in zf.namelist():
            if name.endswith('_geometry.json'):
                out[name] = json.loads(zf.read(name))
    assert out, 'pakette hiç geometri dosyası yok'
    return out


# ---------------------------------------------------------------------------
# 1) Kaynaktaki karışık birim GERÇEKTEN var mı? (hatanın önkoşulu)
# ---------------------------------------------------------------------------

class TestCozucuSozlesmesi:
    """Çözücü aynı sözlükte metre ve milimetreyi birlikte yayımlıyor."""

    @pytest.mark.parametrize('kind, tank_d_mm',
                             [('oxidizer', OX_TANK_D_MM),
                              ('fuel', FUEL_TANK_D_MM)])
    def test_diameter_is_published_in_metres(self, solver_internals, kind,
                                             tank_d_mm):
        av = solver_internals[kind]['anti_vortex_device']
        assert av['diameter'] == pytest.approx(
            tank_d_mm / 1000.0 * TANK_ANTIVORTEX_D_RATIO, rel=1e-9), (
            'çözücü çapı metre yayımlamayı bırakmış olabilir — dışa aktarımdaki '
            'çevirinin dayanağı budur')
        assert av['height'] == pytest.approx(
            tank_d_mm / 1000.0 * TANK_ANTIVORTEX_H_RATIO, rel=1e-9)

    @pytest.mark.parametrize('kind', ['oxidizer', 'fuel'])
    def test_vane_radial_length_is_the_millimetre_anchor(self, solver_internals,
                                                         kind):
        """Çeviri BÜYÜKLÜK SEZGİSİYLE değil, bu özdeşlikle çözülüyor.

        Çözücü kanadı göbekten dış çapa uzatır, yani
        ``vane_radial_length_mm == diameter[mm] / 2``. Bu alan kaybolursa
        normalleştirici artık birimi doğrulayamaz; bekçi o günü yakalar.
        """
        av = solver_internals[kind]['anti_vortex_device']
        assert 'vane_radial_length_mm' in av
        assert av['vane_radial_length_mm'] == pytest.approx(
            av['diameter'] * 1000.0 / 2.0, rel=1e-9)


# ---------------------------------------------------------------------------
# 2) ASIL BEKÇİ — indirilen pakette düzenek mm cinsinden ve doğru boyutta
# ---------------------------------------------------------------------------

class TestPaketBirimi:
    """Düzeltme geri alınırsa bu sınıf kırılır (0,2356 vs 235,58)."""

    @pytest.mark.parametrize('fname, tank_d_mm',
                             [('oxidizer_tank_geometry.json', OX_TANK_D_MM),
                              ('fuel_tank_geometry.json', FUEL_TANK_D_MM)])
    def test_exported_anti_vortex_diameter_is_millimetres(self, package, fname,
                                                          tank_d_mm):
        av = package[fname]['internal_structures']['anti_vortex_device']
        expected_mm = tank_d_mm * TANK_ANTIVORTEX_D_RATIO
        assert av['diameter'] == pytest.approx(expected_mm, rel=1e-9), (
            f'{fname}: çap {av["diameter"]} — {expected_mm:.4f} mm '
            'bekleniyordu (1000x birim hatası geri gelmiş olabilir)')
        assert av['height'] == pytest.approx(
            tank_d_mm * TANK_ANTIVORTEX_H_RATIO, rel=1e-9)

    @pytest.mark.parametrize('fname', ['oxidizer_tank_geometry.json',
                                       'fuel_tank_geometry.json'])
    def test_exported_diameter_matches_the_vane_identity(self, package, fname):
        """Paketin İÇİNDEKİ iki alan artık aynı birimde konuşuyor."""
        av = package[fname]['internal_structures']['anti_vortex_device']
        assert av['diameter'] == pytest.approx(
            2.0 * av['vane_radial_length_mm'], rel=1e-9), (
            'çap ile kanat radyal uzunluğu hâlâ farklı birimde')

    @pytest.mark.parametrize('fname, tank_d_mm',
                             [('oxidizer_tank_geometry.json', OX_TANK_D_MM),
                              ('fuel_tank_geometry.json', FUEL_TANK_D_MM)])
    def test_device_is_a_believable_fraction_of_the_tank(self, package, fname,
                                                         tank_d_mm):
        """Hatanın en görünür imzası: düzenek tankın on binde üçü kadardı."""
        av = package[fname]['internal_structures']['anti_vortex_device']
        ratio = av['diameter'] / tank_d_mm
        assert ratio == pytest.approx(TANK_ANTIVORTEX_D_RATIO, rel=1e-9), (
            f'düzenek/tank oranı {ratio:.6g} — çözücünün beyanı '
            f'{TANK_ANTIVORTEX_D_RATIO:g}')
        assert av['fits_inside_tank'] is True

    @pytest.mark.parametrize('fname', ['oxidizer_tank_geometry.json',
                                       'fuel_tank_geometry.json'])
    def test_conversion_is_declared_not_silent(self, package, fname):
        """Çeviri sessizce yapılmaz; paket ne yaptığını yazar."""
        av = package[fname]['internal_structures']['anti_vortex_device']
        assert av['units'] == 'mm'
        assert av['solver_units'] == 'm'
        assert av['unit_scale_to_mm'] == 1000.0
        assert 'vane_radial_length_mm' in av['unit_resolution_basis']
        # Ham değer kaybolmaz — izlenebilirlik.
        assert av['diameter_solver_value'] == pytest.approx(
            av['diameter'] / 1000.0, rel=1e-12)

    @pytest.mark.parametrize('fname, tank_d_mm',
                             [('oxidizer_tank_geometry.json', OX_TANK_D_MM),
                              ('fuel_tank_geometry.json', FUEL_TANK_D_MM)])
    def test_cad_modelling_instructions_use_the_same_millimetres(
            self, package, fname, tank_d_mm):
        """``step5_anti_vortex`` talimatı da mm — iki yer ayrışamaz."""
        specs = package[fname]['cad_instructions']['step5_anti_vortex']['specs']
        assert specs['diameter'] == pytest.approx(
            tank_d_mm * TANK_ANTIVORTEX_D_RATIO, rel=1e-9)
        assert specs['units'] == 'mm'

    def test_baffles_were_not_touched(self, package, solver_internals):
        """Bafl alanları zaten mm'ydi; çeviri onları BOZMAMALI.

        Naif bir "hepsini 1000 ile çarp" düzeltmesi tam burada yakalanır.
        """
        exported = (package['oxidizer_tank_geometry.json']
                    ['internal_structures']['slosh_baffles'])
        source = solver_internals['oxidizer']['slosh_baffles']
        assert len(exported) == len(source)
        for got, want in zip(exported, source):
            for key in ('outer_diameter', 'inner_diameter', 'thickness',
                        'hole_diameter', 'position'):
                assert got[key] == pytest.approx(want[key], rel=1e-12), (
                    f'bafl alanı {key} değişmiş — çeviri kapsamı taşmış')


# ---------------------------------------------------------------------------
# 3) Çizim tarafı (yan görünüm) da aynı birimi kullanır
# ---------------------------------------------------------------------------

def test_side_view_anti_vortex_is_millimetres(tank_data):
    """Çizim künyesi ``'units': 'mm'`` diyor; yan görünüm de mm taşımalı."""
    view = cad_generator._create_side_view(tank_data)
    av = view['anti_vortex']
    assert av['units'] == 'mm'
    assert av['diameter'] == pytest.approx(
        OX_TANK_D_MM * TANK_ANTIVORTEX_D_RATIO, rel=1e-9)


# ---------------------------------------------------------------------------
# 4) Normalleştiricinin kendisi: çift çevirme yok, uydurma yok
# ---------------------------------------------------------------------------

class TestNormalizeDavranisi:
    def test_already_millimetre_input_is_not_scaled_again(self):
        """mm gelen sözlük 1000 ile ÇARPILMAZ (çift çevirme bekçisi)."""
        av = {'type': 'Radial vanes', 'diameter': 235.5845813,
              'height': 78.5281938, 'vane_radial_length_mm': 117.79229065,
              'vane_thickness': 3.0, 'vane_count': 8}
        out = normalize_anti_vortex_mm(av)
        assert out['unit_scale_to_mm'] == 1.0
        assert out['solver_units'] == 'mm'
        assert out['diameter'] == pytest.approx(235.5845813, rel=1e-12)

    def test_metre_input_is_scaled_once(self):
        av = {'diameter': 0.2355845813, 'height': 0.0785281938,
              'vane_radial_length_mm': 117.79229065, 'vane_count': 8}
        out = normalize_anti_vortex_mm(av)
        assert out['unit_scale_to_mm'] == 1000.0
        assert out['diameter'] == pytest.approx(235.5845813, rel=1e-9)
        assert out['height'] == pytest.approx(78.5281938, rel=1e-9)

    def test_unresolvable_unit_is_declared_not_guessed(self):
        """Dayanak yoksa SAYI UYDURULMAZ — alan boş kalır ve öyle der."""
        av = {'diameter': 0.25, 'height': 0.08, 'vane_count': 8}
        out = normalize_anti_vortex_mm(av)
        assert out['units'] == 'UNRESOLVED'
        assert out['diameter'] is None
        assert out['height'] is None
        # Ham değer korunur; bilgi kaybı da yok, uydurma da yok.
        assert out['diameter_solver_value'] == 0.25
        assert 'No value is guessed' in out['unit_resolution_basis']

    @pytest.mark.parametrize('declared, scale',
                             [('mm', 1.0), ('m', 1000.0), ('metre', 1000.0)])
    def test_declared_units_are_honoured_when_no_anchor(self, declared, scale):
        av = {'diameter': 0.25, 'height': 0.08, 'units': declared,
              'vane_count': 8}
        out = normalize_anti_vortex_mm(av)
        assert out['unit_scale_to_mm'] == scale
        assert out['diameter'] == pytest.approx(0.25 * scale, rel=1e-12)

    def test_inconsistent_anchor_is_not_forced(self):
        """Özdeşlik ne 1x ne 1000x tutuyorsa çeviri UYDURULMAZ."""
        av = {'diameter': 0.25, 'height': 0.08,
              'vane_radial_length_mm': 900.0, 'vane_count': 8}
        out = normalize_anti_vortex_mm(av)
        assert out['units'] == 'UNRESOLVED'
        assert out['diameter'] is None

    def test_oversize_device_is_reported_not_hidden(self):
        """Tanka sığmayan düzenek sessizce geçmez."""
        av = {'diameter': 2.0, 'height': 0.5,
              'vane_radial_length_mm': 1000.0, 'vane_count': 8}
        out = normalize_anti_vortex_mm(av, tank_diameter_mm=800.0)
        assert out['diameter'] == pytest.approx(2000.0, rel=1e-12)
        assert out['fits_inside_tank'] is False

    def test_normalize_does_not_mutate_the_solver_dict(self, solver_internals):
        """Kaynak sözlük yerinde DEĞİŞTİRİLMEZ — çözücü çıktısı ortak nesne."""
        src = solver_internals['oxidizer']['anti_vortex_device']
        before = src['diameter']
        normalize_anti_vortex_mm(src, OX_TANK_D_MM)
        assert src['diameter'] == before, 'kaynak sözlük kirletildi'

    def test_internal_structures_helper_only_touches_the_device(
            self, tank_data):
        out = normalize_internal_structures(tank_data['oxidizer_tank'])
        src = tank_data['oxidizer_tank']['internal_structures']
        assert out is not src, 'kopya değil, kaynak döndürülmüş'
        assert out['anti_vortex_device']['units'] == 'mm'
        for key in ('slosh_baffles', 'inlet_configuration',
                    'outlet_configuration', 'instrumentation',
                    'mass_breakdown'):
            assert out[key] is src[key], f'{key} gereksiz yere kopyalandı'


def test_freecad_builder_refuses_an_unresolved_unit():
    """Birim bilinmiyorsa katı KURULMAZ.

    Sessizce 1000 kat küçük bir parça üretmek, açık bir hatadan beterdir:
    parça atölyeye kadar gider. (FreeCAD kurulu olmasa da denetim
    ``Part`` çağrılmadan önce yapıldığı için bu bekçi her ortamda koşar.)
    """
    av = normalize_anti_vortex_mm({'diameter': 0.25, 'height': 0.08,
                                   'vane_count': 8, 'vane_thickness': 3.0})
    with pytest.raises(ValueError, match='unresolved'):
        cad_generator._create_anti_vortex(av, 'Anti_Vortex_Device', None)
