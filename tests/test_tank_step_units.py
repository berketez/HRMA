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
"""

import re

import pytest

step_export = pytest.importorskip('hrma.export.step_export')

pytestmark = pytest.mark.skipif(
    not getattr(step_export, 'BUILD123D_AVAILABLE', True),
    reason='build123d kurulu değil (STEP üretimi atlanır)')


def _bbox(path):
    """STEP dosyasındaki CARTESIAN_POINT'lerden koordinat aralıklarını çıkarır."""
    txt = open(path, encoding='utf-8', errors='ignore').read()
    xs, ys, zs = [], [], []
    for grp in re.findall(r"CARTESIAN_POINT\s*\(\s*''\s*,\s*\(([^)]*)\)", txt):
        try:
            a, b, c = (float(v) for v in grp.split(','))
        except ValueError:
            continue
        xs.append(a); ys.append(b); zs.append(c)
    return xs, ys, zs


@pytest.fixture(scope='module')
def tank_files(tmp_path_factory):
    out = tmp_path_factory.mktemp('tank_step')
    try:
        return step_export.generate_tank_step(
            {'fuel_tank': {'diameter': 300.0, 'length': 800.0},
             'oxidizer_tank': {'diameter': 300.0, 'length': 900.0}},
            out_dir=str(out))
    except Exception as exc:  # build123d/OCC yoksa anlamlı atla
        pytest.skip(f'STEP üretilemedi: {exc}')


class TestTankStepGeometry:
    def test_files_are_not_empty(self, tank_files):
        """Boş katı üretilmemeli — asıl regresyon buydu."""
        import os
        for key, path in tank_files.items():
            assert os.path.getsize(path) > 1000, f'{key} neredeyse boş'

    def test_dimensions_are_millimetres_not_metres(self, tank_files):
        """300 mm girdi -> yarıçap 150 mm; 1000× ölçeklenirse test kırılır."""
        xs, ys, zs = _bbox(tank_files['fuel_tank'])
        assert xs and zs, 'STEP koordinatları ayrıştırılamadı'
        radius = max(max(abs(v) for v in zs), max(abs(v) for v in ys or [0]))
        assert radius == pytest.approx(150.0, abs=1.0), (
            f'yarıçap {radius:.1f} mm — 150 mm bekleniyordu '
            '(1000× birim hatası geri gelmiş olabilir)')
        length = max(xs) - min(xs)
        assert length == pytest.approx(800.0, abs=1.0), (
            f'gövde boyu {length:.1f} mm — 800 mm bekleniyordu')

    def test_no_coordinate_is_absurdly_large(self, tank_files):
        """Hiçbir koordinat 10 m'yi aşmamalı (birim hatasının imzası)."""
        for key, path in tank_files.items():
            xs, ys, zs = _bbox(path)
            worst = max((abs(v) for v in xs + ys + zs), default=0.0)
            assert worst < 10_000.0, f'{key}: {worst:.0f} mm koordinat var'


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
