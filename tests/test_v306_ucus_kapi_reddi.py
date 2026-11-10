"""3.0.6 ana model (9 Kas) — SIVI-CEKET-A DEVİR 1: ceket yayım kapısı motorun
itkisini ve kütlesini bekletince uçuş aracı reddi kapının ADLI nedenini taşır.

ÖLÇÜLEN KUSUR: K5 EK7 kapısı F-1 sınıfında (``design`` kapsamı) motor itkisini
de bekletiyor. ``/api/flight-vehicle`` önce genel ``unflyable_vehicle``
reddini soruyordu ("itki kaynağı çözülemedi"); adlı kütle reddi
(``engine_mass_not_published`` + ``cause: cooling_circuit_not_solved``,
istemcide ``flight.refusedCooling`` EN + TR) hiç ulaşılmıyordu.
"""
import contextlib
import io

import pytest

from tests.test_v306_sivi_ceket_a import F1

HEADERS = {'Host': '127.0.0.1:8080'}


def _sessiz(fn, *a, **k):
    t = io.StringIO()
    with contextlib.redirect_stdout(t), contextlib.redirect_stderr(t):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def f1(client):
    r = _sessiz(client.post, '/calculate_liquid', json=dict(F1), headers=HEADERS)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    y = r.get_json()
    ccp = y.get('cooling_circuit_publication') or {}
    assert ccp.get('withheld_reason_code'), (
        'fikstür dayanağı düştü: F-1 artık kapıyı tetiklemiyor')
    return y


def test_kapi_tetiklenince_ret_adli_neden_tasir(client, f1):
    r = _sessiz(client.post, '/api/flight-vehicle', json={
        'source': 'results', 'motor_type': 'liquid', 'results': f1},
        headers=HEADERS)
    assert r.status_code == 422, r.get_data(as_text=True)[:300]
    j = r.get_json()
    assert j['error'] == 'engine_mass_not_published', j.get('error')
    assert j['cause'] == 'cooling_circuit_not_solved'
    ccp = j['cooling_circuit_publication']
    assert ccp['withheld_reason_code'] == f1['cooling_circuit_publication'][
        'withheld_reason_code']
    assert ccp.get('withheld_reason_key')


def test_itkisiz_bos_arac_hala_genel_retle_reddedilir(client):
    """Tasarım sonucu olmayan gövdede sıra değişikliği genel reddi örtmez."""
    r = _sessiz(client.post, '/api/flight-vehicle', json={
        'source': 'results', 'motor_type': 'hybrid', 'results': {'banana': 1}},
        headers=HEADERS)
    assert r.status_code == 422
    assert r.get_json()['error'] == 'unflyable_vehicle'
