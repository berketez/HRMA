"""V301/NK-25 (28 Eki) — yörünge profili menzil ekseni SI öneki basmaz.

26 ve 28 Eki son kullanıcı turları: dikey atışta "Menzil (km)" ekseni
"0, 0,2f, 0,4f, 0,6f, 0,8f" basıyordu. Ölçüldü: menzil verisi 0 ile
1,3·10⁻¹⁵ km arasında kayan nokta gürültüsü; Plotly bu aralığa yakınlaşıp
tikleri femto önekiyle ("f") yazıyordu. Bekçiler:

* menzil ekseni her durumda ``exponentformat = 'none'``;
* açıklık 1 m'nin altındaysa eksen sıfır merkezli, irtifa ölçeğinde bir
  pencereye sabitlenir (0,1 × tepe irtifa, en az 0,1 km);
* eğik atışta (gerçek menzil) pencere KONMAZ, Plotly kendi ölçeğini seçer;
* veri değişmez (yalnız görünüm).
"""
import contextlib
import io
import json

import pytest

from hrma.analysis.trajectory_analysis import (
    MENZIL_EKSENI_DIKEY_ESIK_KM, MENZIL_EKSENI_EN_KUCUK_PENCERE_KM,
    MENZIL_EKSENI_PENCERE_IRTIFA_ORANI)
from hrma.app import app

DIKEY_YORUNGE_GOVDESI = {'initial_mass': 50.0, 'final_mass': 35.0, 'drag_coefficient': 0.5,
         'reference_area': 0.01, 'thrust': 4000.0, 'burn_time': 8.0}


def _figur(aci):
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()):
        yanit = app.test_client().post('/api/trajectory-analysis',
                                       json=dict(DIKEY_YORUNGE_GOVDESI, launch_angle=aci))
    assert yanit.status_code == 200
    govde = yanit.get_json()
    assert govde.get('plot_error') in (None, '')
    figur = govde['plot_data']
    return json.loads(figur) if isinstance(figur, str) else figur


def _iz(figur, ad):
    return next(t for t in figur['data'] if t.get('name') == ad)


def test_dikey_atista_si_oneki_yok_ve_pencere_sabit():
    figur = _figur(90.0)
    eksen = figur['layout']['xaxis']
    assert eksen['exponentformat'] == 'none'
    menzil = _iz(figur, 'Flight Path')['x']
    irtifa = _iz(figur, 'Flight Path')['y']
    assert max(menzil) - min(menzil) < MENZIL_EKSENI_DIKEY_ESIK_KM
    yari = max(MENZIL_EKSENI_PENCERE_IRTIFA_ORANI * max(abs(z) for z in irtifa),
               MENZIL_EKSENI_EN_KUCUK_PENCERE_KM)
    assert eksen['range'][1] - eksen['range'][0] == pytest.approx(2 * yari)


def test_egik_atista_pencere_konmaz():
    figur = _figur(80.0)
    eksen = figur['layout']['xaxis']
    assert eksen['exponentformat'] == 'none'
    menzil = _iz(figur, 'Flight Path')['x']
    assert max(menzil) - min(menzil) > MENZIL_EKSENI_DIKEY_ESIK_KM
    assert 'range' not in eksen
