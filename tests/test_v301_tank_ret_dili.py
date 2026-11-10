"""v3.0.1 — kullanıcı tank kipinin 422 cümleleri Türkçe arayüzde çevrilir.

V301/E2 raporu devir 5: tank kulvarının ret cümleleri (tank basıncı yok,
tank basıncı oda basıncının altında, N2O doyma basıncının altında) için
``i18n_charts.js`` ``MSG_PATTERNS`` deseni yoktu; Türkçe arayüzde bildirim
İngilizce kalıyordu. Cümleler burada ÜRÜNDEN alınır (``/calculate`` 422
gövdesi), elle kopyalanmaz: motor metni değişirse desen tutmaz ve bekçi
kırılır.
"""
import contextlib
import io
import json
import subprocess
import warnings

import pytest

from tests.test_app_hata_dili import (
    NODE, NODE_DUZENEGI, STATIC_JS, TURKCE_KARAKTER, needs_node)
from tests.test_v301_tank_basinci import H1, U

#: Örnek-H1 yükü, kullanıcı tank kipinde ve tank basıncı OLMADAN (ret
#: vakaları tank basıncını kendisi ekler).
_TANK_RET_TABAN = dict({k: v for k, v in H1.items() if k != 'tank_pressure'},
                       **U)

#: (beklenen makine kodu, yük eki)
_TANK_RET_VAKALARI = (
    ('tank_pressure_required', {}),
    ('tank_pressure_not_above_chamber_pressure',
     {'tank_pressure': 15.0, 'oxidizer_type': 'lox', 'of_ratio': 2.5}),
    ('tank_pressure_below_saturation', {'tank_pressure': 40.0}),
)


def _ret_cumleleri():
    from hrma.app import app
    app.config['TESTING'] = True
    cumleler = []
    for kod, ek in _TANK_RET_VAKALARI:
        with contextlib.redirect_stdout(io.StringIO()), \
                warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with app.test_client() as ist:
                r = ist.post('/calculate', json=dict(_TANK_RET_TABAN, **ek))
        govde = r.get_json()
        assert r.status_code == 422, (kod, r.status_code, govde)
        assert govde['error'] == kod, govde
        cumleler.append(govde['message'])
    return cumleler


@needs_node
def test_tank_ret_cumleleri_turkcede_cevrilir(tmp_path):
    cumleler = _ret_cumleleri()
    duzenek = tmp_path / 'srv.js'
    duzenek.write_text(NODE_DUZENEGI, encoding='utf-8')
    girdi = tmp_path / 'in.json'
    girdi.write_text(json.dumps(cumleler), encoding='utf-8')
    islem = subprocess.run(
        [NODE, str(duzenek), str(STATIC_JS), str(girdi)],
        capture_output=True, text=True, timeout=120)
    assert islem.returncode == 0, islem.stderr
    sonuc = json.loads(islem.stdout)

    assert sonuc['en'] == cumleler, 'EN kipinde metin değişti'
    for kaynak, tr in zip(cumleler, sonuc['tr']):
        assert tr != kaynak and TURKCE_KARAKTER.search(tr), (
            f'çevrilmedi: {kaynak}')
    # Ondalık kanonu: Türkçede ayraç virgül (P_sat 50.53 -> 50,53).
    # V306/SIVI-ONARIM kalem 5: sayı elle yazılmaz, TEK KAYNAKTAN okunur.
    # V306/SAYI kalem 4 (cb11df981) aynı koşudaki bütün N₂O doyma
    # alanlarını CoolProp EOS'una (Lemmon & Span 2006) bağladı: 293,15 K'de
    # 50,543358 (tablo ara değeri) -> 50,525093 bar; ret metni '.4g' ile
    # 50,54 -> 50,53 yazar. Çapa '50,54' o tablo değerini kilitliyordu.
    from hrma.engines.hybrid_rocket_engine import TANK_TEMPERATURE_DEFAULT_K
    from hrma.engines.injector_design import n2o_vapor_pressure_bar
    en_sayi = '%.4g' % n2o_vapor_pressure_bar(TANK_TEMPERATURE_DEFAULT_K)
    tr_sayi = en_sayi.replace('.', ',')
    assert ('P_sat(293.15 K) = %s bar' % en_sayi) in cumleler[2], cumleler[2]
    assert tr_sayi in sonuc['tr'][2] and en_sayi not in sonuc['tr'][2], (
        sonuc['tr'][2])
    assert '%2' in sonuc['tr'][2], sonuc['tr'][2]
    assert '15 - 20 = -5' in sonuc['tr'][1], sonuc['tr'][1]
