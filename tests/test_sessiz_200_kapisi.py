"""``/calculate_solid`` ve ``/calculate_liquid`` sessiz-200 bekçileri (v2.6.27).

Denetçi kanıtı (2026-08-04): motor ``calculate_performance()`` dict yerine
``None`` döndürdüğünde iki uç da HTTP 200 + ``null`` gövde dönüyor ve
``success`` logluyordu. Kök neden: kesit çizimi/pano için konan İKİ geniş
``try/except Exception`` bloğu, bozuk sonucun ürettiği ``None[...] = ...``
(TypeError) ve ``None.setdefault`` (AttributeError) hatalarını yutuyordu;
akış hiç kırılmadan ``jsonify(None)``'a ulaşıyordu. İzleyen biri logda
``calculate_solid.success`` görüyor, istemci ise ``null`` alıyordu.

Yeni sözleşme:

* ``calculate_performance`` sonrası TİP KAPISI: sonuç dict değilse
  ``EngineContractViolation`` (bir ``TypeError`` alt sınıfı) yükselir.
* Uç 500 + açıklayıcı hata gövdesi döner (sözleşme ihlali SUNUCU hatasıdır,
  istemci hatası 400 değil) ve ``success`` LOGLANMAZ.
* Çizim ``try/except``leri artık YALNIZ kesit-çizim satırlarını sarar; motor
  sonucunun bozukluğunu yutamazlar.

Not: ``_SozlesmeyiBozanMotor`` bir pytest sahtesidir (test altyapısı) —
kullanıcıya gösterilen veri değildir.
"""

import pytest

import hrma.app as hrma_app
from hrma.app import EngineContractViolation, app
from tests.support import shake


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        yield test_client


def _sozlesmeyi_bozan_motor(donen):
    """``calculate_performance()`` sözlük dışı değer döndüren sahte motor.

    Sahte, motorun uç noktanın OKUDUĞU yüzeyini taşımak zorundadır; aksi
    hâlde kapı denenmeden başka bir hata yolu tetiklenir. v2.6.27'de
    ``/calculate_solid``, katsayı kaynağını beyan edebilmek için motorun
    çözdüğü yakıt kimliğini ve fiilen kullandığı Saint-Robert çiftini
    okumaya başladı (``app._build_solid_engine``: ``motor.propellant_type``,
    ``motor.a``, ``motor.n``). Bu alanlar sahtede yokken uç, sonucun tipine
    HİÇ bakamadan ``AttributeError`` ile 400 dönüyordu — yani test yeşil/
    kırmızı olmasından bağımsız olarak artık sessiz-200 kapısını
    SINAMIYORDU. Alanlar eklendi; kapının iddiası (sözlük dışı sonuç ->
    500) aynen korundu, gevşetilmedi.

    Değerler gerçek çözümden gelmez ve kullanıcıya gösterilmez — bu bir
    pytest sahtesidir (test altyapısı).
    """

    class _Motor:
        #: Uç noktanın katsayı-kaynağı beyanı için okuduğu yüzey.
        propellant_type = 'apcp'
        a = 0.0022334
        n = 0.35

        def __init__(self, *args, **kwargs):
            pass

        def calculate_performance(self):
            return donen

    return _Motor


#: Katı ucun 422 kritik-girdi kapısını geçen asgari geometri-kipi girdisi.
SOLID_GIRDI = {
    'chamber_pressure': 40, 'propellant_type': 'apcp',
    'chamber_diameter': 100, 'grain_length': 500, 'core_diameter': 30,
}

#: Sıvı ucun 422 kritik-girdi kapısını geçen beş zorunlu alan.
LIQUID_GIRDI = {
    'thrust': 10000, 'chamber_pressure': 100, 'mixture_ratio': 2.5,
    'fuel_type': 'rp1', 'oxidizer_type': 'lox',
}


def test_kapinin_istisnasi_typeerror_alt_sinifi():
    """Kapı bir TİP kapısıdır: istisna TypeError ailesinden olmalı (görev
    tarifi 'raise TypeError' der; alt sınıf adı sözleşmeyi de söyler)."""
    assert issubclass(EngineContractViolation, TypeError)


@pytest.mark.parametrize('bozuk', [None, ['liste'], 'metin'],
                         ids=['None', 'list', 'str'])
def test_solid_sozluk_disi_sonuc_500_doner(client, monkeypatch, capsys, bozuk):
    """ESKİ KUSUR: None sonuç HTTP 200 + 'null' + success logu üretiyordu."""
    monkeypatch.setattr(hrma_app, 'SolidRocketEngine',
                        _sozlesmeyi_bozan_motor(bozuk))
    resp = client.post('/calculate_solid', json=SOLID_GIRDI,
                       headers=shake.HEADERS)
    assert resp.status_code == 500, resp.get_data(as_text=True)[:300]
    body = resp.get_json()
    assert body['error_type'] == 'EngineContractViolation'
    assert 'must return a dict' in body['error']
    assert body['trace_id']
    out = capsys.readouterr().out
    assert 'calculate_solid.success' not in out, (
        'sözlük dışı sonuçta success LOGLANAMAZ — sessiz 200 kusuru geri '
        'gelmiş')
    assert 'calculate_solid.error' in out


@pytest.mark.parametrize('bozuk', [None, ['liste'], 'metin'],
                         ids=['None', 'list', 'str'])
def test_liquid_sozluk_disi_sonuc_500_doner(client, monkeypatch, capsys,
                                            bozuk):
    monkeypatch.setattr(hrma_app, 'LiquidRocketEngine',
                        _sozlesmeyi_bozan_motor(bozuk))
    resp = client.post('/calculate_liquid', json=LIQUID_GIRDI,
                       headers=shake.HEADERS)
    assert resp.status_code == 500, resp.get_data(as_text=True)[:300]
    body = resp.get_json()
    assert body['error_type'] == 'EngineContractViolation'
    assert 'must return a dict' in body['error']
    assert body['trace_id']
    out = capsys.readouterr().out
    assert 'calculate_liquid.success' not in out, (
        'sözlük dışı sonuçta success LOGLANAMAZ — sessiz 200 kusuru geri '
        'gelmiş')
    assert 'calculate_liquid.error' in out


def test_solid_gercek_motorla_hala_200(client, capsys):
    """Regresyon: kapı gerçek (dict dönen) hesabı ENGELLEMEZ."""
    resp = client.post('/calculate_solid', json=SOLID_GIRDI,
                       headers=shake.HEADERS)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    body = resp.get_json()
    assert isinstance(body, dict)
    # Geometri dönüşümü try dışına alındı — gerçek yolda hâlâ üretilmeli.
    assert 'motor_geometry' in body
    assert 'calculate_solid.success' in capsys.readouterr().out
