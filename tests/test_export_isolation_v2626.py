"""Dışa aktarım yollarının istekler arası izolasyonu (v2.6.26).

Kapattığı ölçülmüş kusur: ``export_stl_files`` sabit bir dizine (``./cad_exports/``)
sabit adlarla (``motor_assembly.stl``, ``chamber.stl`` ...) yazıyor, uç nokta da
dosyayı diskten GERİ OKUYORDU. İki eşzamanlı istek aynı yola yazınca biri
diğerinin geometrisini indiriyordu.

Ölçüldü (düzeltmeden önce): iki farklı motorla altı eşzamanlı denemenin
ikisinde A isteği HTTP 200 ile B'nin STL'ini aldı. Üretimde sunucu sekiz iş
parçacığıyla koşuyor (``packaging/launcher.py``), yani yarış teorik değil.

Neden ciddi: kullanıcı indirdiği dosyanın kendi motoruna ait olduğunu
varsayar ve imalata götürür. Sessiz veri bozulmasının en kötü türü — hata
mesajı yok, dosya geçerli, sadece BAŞKA motorun.
"""

from __future__ import annotations

import hashlib
import threading

import pytest


HEADERS = {'Host': '127.0.0.1:8080'}

BASE = {
    'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
    'chamber_pressure': 20, 'tank_pressure': 50, 'of_ratio': 2.5,
    'l_star': 1.0, 'expansion_ratio': 4.0, 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'oxidizer_phase': 'liquid',
    'oxidizer_density': 1220, 'chamber_temperature': 3000,
}


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


def _solved(client, chamber_diameter_mm: int, name: str):
    """Gerçek bir çözüm üretir ve STL uç noktasının beklediği biçime getirir."""
    payload = dict(BASE, chamber_diameter_input=chamber_diameter_mm,
                   motor_name=name)
    resp = client.post('/calculate', json=payload, headers=HEADERS)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    motor = resp.get_json()['motor']
    motor['motor_type'] = 'hybrid'
    motor['motor_name'] = name
    motor.setdefault('port_diameter',
                     motor.get('port_diameter_initial') or 0.03)
    return motor


def _stl_hash(client, motor):
    resp = client.post('/api/export-stl', json={'motor_data': motor},
                       headers=HEADERS)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    return hashlib.md5(resp.data).hexdigest()


def test_two_motors_produce_different_stl(client):
    """Ön koşul: iki farklı motor gerçekten farklı STL üretmeli.

    Bu tutmazsa aşağıdaki yarış testi anlamsızdır (her şey aynı görünür).
    """
    a = _stl_hash(client, _solved(client, 120, 'A'))
    b = _stl_hash(client, _solved(client, 300, 'B'))
    assert a != b


def test_concurrent_exports_do_not_contaminate_each_other(client):
    """Eşzamanlı iki istek birbirinin geometrisini almamalı."""
    motor_a = _solved(client, 120, 'A')
    motor_b = _solved(client, 300, 'B')
    ref_a = _stl_hash(client, motor_a)
    ref_b = _stl_hash(client, motor_b)
    assert ref_a != ref_b

    contaminated = []
    for _round in range(4):
        got = {}

        def grab(key, motor):
            got[key] = _stl_hash(client, motor)

        threads = [threading.Thread(target=grab, args=('a', motor_a)),
                   threading.Thread(target=grab, args=('b', motor_b))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if got.get('a') != ref_a or got.get('b') != ref_b:
            contaminated.append(got)

    assert not contaminated, (
        'Eszamanli STL isteklerinde kirlenme: %s (beklenen a=%s b=%s)'
        % (contaminated, ref_a[:12], ref_b[:12]))


def test_export_does_not_write_to_a_shared_default_directory():
    """Varsayılan çıktı dizini paylaşılan sabit bir yol OLMAMALI.

    Yarış testi zamanlamaya bağlıdır ve şanslı bir koşuda yeşil kalabilir.
    Bu test sözleşmenin kendisini sabitler: varsayılan ``None``, yani her
    çağrı kendi geçici dizinini alır.
    """
    import inspect
    from hrma.export.cad_visualization import MotorCADDesigner
    sig = inspect.signature(MotorCADDesigner.export_stl_files)
    default = sig.parameters['output_dir'].default
    assert default is None, (
        'export_stl_files varsayilan cikti dizini paylasilan sabit bir yol '
        f'olamaz (bulunan: {default!r}); istek basina gecici dizin kullanin.')
