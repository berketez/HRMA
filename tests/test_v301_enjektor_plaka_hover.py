"""V301/HİBRİT-DIŞA DEVİR (28 Eki) — plakasız hibritte enjektör figürü kalınlık/L-D basmaz.

HİBRİT-DIŞA kalem 4: plaka kalınlığı verilmediyse ``injector_design`` artık
``plate_thickness`` ve ``L_D_ratio`` için null yayımlıyor. Figür
(``create_showerhead_with_tooltips``) ise ``_num_safe(..., 3.0)`` ile 3,0 mm'ye
düşüp delik balonunda "L/D" ve plaka balonunda "Thickness: 3.0 mm" yazıyordu.
"""
import json

from hrma.visualization.visualization import create_showerhead_with_tooltips

TEMEL = {'n_holes': 12, 'hole_diameter': 1.5, 'exit_velocity': 25.0,
         'reynolds_number': 40000.0}


def _balonlar(veri):
    fig = json.loads(create_showerhead_with_tooltips(veri))   # figür JSON'u
    return [str(t.get('hovertemplate') or '') for t in fig['data']]


def test_plaka_yokken_kalinlik_ve_ld_basilmaz():
    balonlar = _balonlar(dict(TEMEL, plate_thickness=None))
    assert balonlar
    assert not any('Thickness:' in b for b in balonlar)
    assert not any('L/D:' in b for b in balonlar)


def test_plaka_verilince_kalinlik_ve_ld_basilir():
    balonlar = _balonlar(dict(TEMEL, plate_thickness=4.5))
    assert any('Thickness: 4.5 mm' in b for b in balonlar)
    assert any('L/D: 3.0' in b for b in balonlar)
