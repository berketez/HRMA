"""A1/A2/B1 bağlantı bekçileri (v2.6.2).

Neden bu dosya var:
``flight_vehicle.py``, ``tile_cache.py`` ve ``flight_handoff.js`` modülleri
yazıldı ama v2.6.2 boyunca HİÇBİR ROTAYA VE HİÇBİR ŞABLONA BAĞLANMADI —
``/api/flight-vehicle`` ve ``/api/tile/...`` uçları yoktu, üç motor şablonu
handoff betiğini yüklemiyordu. Aynı sessiz kopukluk ``input_guard.py``'da da
yaşandı (yazıldı, kimse import etmedi; ``safe_name`` NameError'ı oradan çıktı).

Bu testler "modül var" ile "kullanıcıya ulaşıyor" arasındaki farkı kilitler.
"""

import json

import pytest

from hrma.app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# A2 — uydu karosu uçları
# ---------------------------------------------------------------------------

class TestTileRoutes:
    def test_routes_are_registered(self):
        rules = {str(r) for r in app.url_map.iter_rules()}
        assert '/api/tile/<layer_key>/<int:z>/<int:x>/<int:y>' in rules
        assert '/api/tile/cache/status' in rules
        assert '/api/tile/cache/clear' in rules

    def test_cache_status_shape(self, client):
        r = client.get('/api/tile/cache/status')
        assert r.status_code == 200
        body = r.get_json()
        for key in ('bytes', 'tiles', 'dir', 'layers'):
            assert key in body, f'cache/status {key} alanını döndürmüyor'

    def test_unknown_layer_rejected(self, client):
        """Katman allowlist dışıysa 404 — SSRF/keyfi host yüzeyi yok."""
        r = client.get('/api/tile/bogus_layer/5/1/1')
        assert r.status_code == 404

    def test_out_of_range_tile_rejected(self, client):
        """z/x/y aralık kapısı: matris dışı karo 400."""
        r = client.get('/api/tile/bluemarble/99/1/1')
        assert r.status_code == 400

    def test_layer_key_cannot_traverse(self, client):
        """Katman anahtarı yol bileşeni taşıyamaz."""
        for bad in ('../../etc', '..%2f..%2fetc'):
            r = client.get(f'/api/tile/{bad}/4/1/1')
            assert r.status_code in (400, 404)


# ---------------------------------------------------------------------------
# A1 — araç köprüsü ucu
# ---------------------------------------------------------------------------

class TestFlightVehicleEndpoint:
    def test_route_registered(self):
        rules = {str(r) for r in app.url_map.iter_rules()}
        assert '/api/flight-vehicle' in rules

    def test_missing_fields_rejected(self, client):
        r = client.post('/api/flight-vehicle', json={'source': 'results'})
        assert r.status_code == 400

    def test_unknown_source_rejected(self, client):
        r = client.post('/api/flight-vehicle', json={'source': 'nope'})
        assert r.status_code == 400

    def test_solid_motor_normalises_to_vehicle_schema(self, client):
        """Gerçek katı motor sonucu tek araç şemasına inmeli."""
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        eng = SolidRocketEngine(grain_type='bates', propellant_type='apcp',
                                chamber_diameter=100, grain_length=500,
                                core_diameter=30, chamber_pressure=40)
        res = eng.calculate_performance()
        r = client.post('/api/flight-vehicle',
                        json={'source': 'results', 'motor_type': 'solid',
                              'results': res})
        assert r.status_code == 200
        v = r.get_json()['vehicle']
        for key in ('motor_type', 'motor_name', 'thrust', 'burn_time',
                    'propellant_mass', 'engine_inert_mass', 'source'):
            assert key in v, f'araç şemasında {key} yok'
        assert v['thrust'] > 0 and v['burn_time'] > 0
        assert v['propellant_mass'] > 0
        assert v['source'] == 'results'

    def test_solid_carries_real_thrust_curve(self, client):
        """Katı motorda itki eğrisi köprüden geçmeli — sabit itkiye düşmemeli.

        Eğri kaybolursa 6-DOF ortalama itkiyle uçar ve tepe ivme/Mach yanlış çıkar.
        """
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        eng = SolidRocketEngine(grain_type='bates', propellant_type='apcp',
                                chamber_diameter=100, grain_length=500,
                                core_diameter=30, chamber_pressure=40)
        res = eng.calculate_performance()
        v = client.post('/api/flight-vehicle',
                        json={'source': 'results', 'motor_type': 'solid',
                              'results': res}).get_json()['vehicle']
        curve = v.get('thrust_curve')
        assert curve and curve.get('time') and curve.get('thrust')
        assert len(curve['time']) == len(curve['thrust']) > 10


# ---------------------------------------------------------------------------
# Uçtan uca: motor -> araç -> 6-DOF
# ---------------------------------------------------------------------------

def test_full_chain_motor_to_flight(client):
    """Hesaplanan motor gerçekten uçabilmeli (zincirin hiçbir halkası kopuk değil)."""
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    eng = SolidRocketEngine(grain_type='bates', propellant_type='apcp',
                            chamber_diameter=100, grain_length=500,
                            core_diameter=30, chamber_pressure=40)
    v = client.post('/api/flight-vehicle',
                    json={'source': 'results', 'motor_type': 'solid',
                          'results': eng.calculate_performance()}
                    ).get_json()['vehicle']

    body = {
        'body_diameter': max(0.15, v['engine_od_m'] or 0.15),
        'body_length': 3.0, 'nose_length': 0.5, 'nose_type': 'ogive',
        # ÇİFT SAYIM: gövde kuru + motor atıl toplanır, propelan AYRI gider.
        'dry_mass': 18.0 + (v['engine_inert_mass'] or 0.0),
        'propellant_mass': v['propellant_mass'],
        'thrust': v['thrust'], 'burn_time': v['burn_time'],
        'cd0': 0.45, 'fin_count': 4, 'fin_root_chord': 0.20,
        'fin_tip_chord': 0.10, 'fin_span': 0.11, 'fin_sweep': 0.08,
        'launch_elevation_deg': 84, 'launch_azimuth_deg': 90,
        'rail_length': 5, 'wind_speed': 6, 'wind_direction_deg': 270,
        't_max': 400,
        'latitude_deg': 28.6084,   # B1 — Coriolis için saha enlemi
    }
    r = client.post('/api/six-dof-analysis', json=body)
    assert r.status_code == 200
    d = r.get_json()
    assert d['status'] == 'success'
    s = d['summary']
    assert s['apogee'] > 100, 'araç yükselmiyor — zincirde kopukluk olabilir'
    assert s['static_margin_full'] > 1.0, 'varsayılan kanatlar kararsız araç veriyor'
    assert len(d['series']['time']) > 10


def test_six_dof_rejects_unbounded_t_max(client):
    """t_max üst sınırı: kaçış yörüngesinde bitmeyen entegrasyon engellenmeli."""
    r = client.post('/api/six-dof-analysis', json={
        'body_diameter': 0.15, 'body_length': 3.0, 'dry_mass': 20,
        'propellant_mass': 8, 'thrust': 3000, 'burn_time': 5,
        't_max': 1e9,
    })
    assert r.status_code == 400
    assert 't_max' in (r.get_json() or {}).get('error', '')


# ---------------------------------------------------------------------------
# Ön yüz bağlantısı — "modül var" ile "kullanıcıya ulaşıyor" farkı
# ---------------------------------------------------------------------------

def test_motor_pages_load_and_call_flight_handoff():
    """Üç motor şablonu handoff betiğini YÜKLEMELİ ve ÇAĞIRMALI.

    Betik yüklenmezse ``window.FlightHandoff`` tanımsız kalır, publish çağrısı
    sessizce atlanır ve /launch-site hiçbir zaman gerçek motoru göremez —
    tam olarak v2.6.2'de yaşanan durum.
    """
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]

    for rel in ('hrma/templates/advanced.html', 'hrma/templates/solid.html',
                'hrma/templates/liquid.html'):
        text = (root / rel).read_text(encoding='utf-8')
        assert 'flight_handoff.js' in text, f'{rel}: handoff betiği yüklenmiyor'

    # publish çağrısı: hibrit app.js'te, katı/sıvı kendi şablonlarında
    calls = [
        ('hrma/static/js/app.js', "motor_type: 'hybrid'"),
        ('hrma/templates/solid.html', "motor_type: 'solid'"),
        ('hrma/templates/liquid.html', "motor_type: 'liquid'"),
    ]
    for rel, needle in calls:
        text = (root / rel).read_text(encoding='utf-8')
        assert 'FlightHandoff.publish' in text, f'{rel}: publish çağrısı yok'
        assert needle in text, f'{rel}: motor tipi geçilmiyor ({needle})'


def test_launch_site_has_no_hardcoded_demo_vehicle():
    """Sabit demo araç sökülmüş olmalı.

    Eskiden /launch-site her zaman aynı uydurma aracı (thrust 6500, dry 25,
    prop 18) uçuruyordu; kullanıcı bunu kendi motoru sanabiliyordu.
    """
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    text = (root / 'hrma/templates/launch_site.html').read_text(encoding='utf-8')

    # Araç artık değişkenden gelir
    assert 'currentVehicle' in text, 'araç köprüsü bağlanmamış'
    assert 'EXAMPLE_VEHICLE' in text, 'örnek araç ayrı etiketlenmemiş'
    # Coriolis: saha enlemi çözücüye geçmeli
    assert 'latitude_deg: la' in text, 'B1 — saha enlemi 6-DOF\'a geçmiyor'
    # A3: kontroller uçuş çözülene kadar kapalı
    assert 'setFlightControlsEnabled' in text, 'A3 kontrol kapısı yok'
