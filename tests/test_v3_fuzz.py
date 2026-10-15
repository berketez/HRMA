"""V3 SG-1 — API fuzz düzeneği bekçileri (karar §28-33; §27-11).

Düzenek ``tools/fuzz_api.py``: ürünün bütün uçları tohumlu rastgele ve sınır
değer girdileriyle Flask ``test_client`` üzerinden sınanır. Bu dosya üç şeyi
kilitler:

1. **Hızlı kip süitte** — alt süreçte (kalkanlar ve geçici dizinler süreç
   genelinde kurulduğu için pytest sürecine sızmasın), sabit tohum, uç
   başına ``FAST_CASES_PER_ENDPOINT`` vaka, toplam ≤ ``MODE_WALL_BUDGET_S``.
   Bulgu SIFIR olmalı; her (kural, metod) planda ve vaka almış olmalı.
   TAM kip elle: ``HRMA_FUZZ_KIP=tam pytest tests/test_v3_fuzz.py``.
2. **Kalkan ve kâhinler ısırır** — kalkan öz sınaması (ağ, süreç, dosya)
   alt süreçte; kâhinler bilinen kötü yanıtı yakalar.
3. **Küçültülmüş fuzz vakaları** — düzeltilen bulguların regresyonu
   (rapor: ``docs/scofield/raw/OH/V3/guvenlik/sg1/rapor.md``).

Bu dosya ``docs/`` okumaz (docs'suz yayın dalında da koşar).
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FUZZ_TOOL = ROOT / 'tools' / 'fuzz_api.py'


def _load_tool():
    spec = importlib.util.spec_from_file_location('hrma_fuzz_api', FUZZ_TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fuzz = _load_tool()

SELF_HOST = f'127.0.0.1:{fuzz.FUZZ_SELF_PORT}'


def _mode():
    mode = os.environ.get(fuzz.FUZZ_MODE_ENV, 'hizli')
    assert mode in fuzz.FUZZ_MODES, mode
    return mode


def _child_env():
    env = dict(os.environ)
    env.pop('PYTEST_CURRENT_TEST', None)
    env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
    return env


# ---------------------------------------------------------------------------
# 1) Hızlı kip: bütün yüzey, bulgu sıfır
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def fuzz_sonucu(tmp_path_factory):
    mode = _mode()
    work = tmp_path_factory.mktemp('fuzz')
    out = work / 'sonuc.json'
    budget = fuzz.MODE_WALL_BUDGET_S[mode]
    proc = subprocess.run(
        [sys.executable, str(FUZZ_TOOL), '--kip', mode,
         '--gecici-kok', str(work), '--cikti', str(out)],
        cwd=str(work), env=_child_env(), capture_output=True, text=True,
        timeout=budget * 3 + 120)
    assert out.is_file(), (proc.returncode, proc.stderr[-2000:])
    return proc.returncode, json.loads(out.read_text(encoding='utf-8'))


class TestFuzzKipi:
    def test_bulgu_yok(self, fuzz_sonucu):
        code, result = fuzz_sonucu
        bulgular = result['bulgular']
        ozet = [(b['tur'], b.get('uc'), b.get('sinif'), b.get('alt'),
                 b.get('status'), b.get('ayrinti', '')[:120])
                for b in bulgular[:20]]
        assert bulgular == [], ozet
        assert code == 0

    def test_her_kural_metod_planda(self, fuzz_sonucu):
        from hrma.app import app
        _, result = fuzz_sonucu
        planned = {(u['rule'], u['method']) for u in result['uclar']}
        expected = set()
        for rule in app.url_map.iter_rules():
            for method in rule.methods or ():
                if method not in ('HEAD', 'OPTIONS'):
                    expected.add((rule.rule, method))
        assert expected - planned == set()

    def test_uc_basina_vaka_sayisi(self, fuzz_sonucu):
        _, result = fuzz_sonucu
        per = result['_meta']['uc_basina_vaka']
        expected = (fuzz.FAST_CASES_PER_ENDPOINT if _mode() == 'hizli'
                    else fuzz.FULL_CASES_PER_ENDPOINT)
        assert per >= expected
        eksik = [(u['rule'], u['method'], u.get('vaka'))
                 for u in result['uclar']
                 if u['kip'] != 'dislandi' and u.get('vaka', 0) < per]
        assert eksik == []

    def test_dislanan_her_uc_gerekceli(self, fuzz_sonucu):
        _, result = fuzz_sonucu
        for u in result['uclar']:
            if u['kip'] in ('dislandi', 'agir', 'yan_etkili'):
                assert u.get('gerekce'), u

    def test_sure_butcesi_ve_tohum(self, fuzz_sonucu):
        _, result = fuzz_sonucu
        meta = result['_meta']
        assert meta['tohum'] == fuzz.FUZZ_DEFAULT_SEED
        assert meta['sure_s'] <= fuzz.MODE_WALL_BUDGET_S[_mode()]

    def test_depo_agacina_yazilmadi(self, fuzz_sonucu):
        _, result = fuzz_sonucu
        meta = result['_meta']
        assert meta['depo_agaci_fark'] == {'degisen_ya_da_yeni': [],
                                           'silinen': []}
        assert meta['kalkan']['dosya_engellenen'] == 0


# ---------------------------------------------------------------------------
# 2) Kalkan ve kâhinler ısırır
# ---------------------------------------------------------------------------

class TestKalkanOzSinama:
    def test_ag_surec_dosya_engellenir(self, tmp_path):
        out = tmp_path / 'kalkan.json'
        proc = subprocess.run(
            [sys.executable, str(FUZZ_TOOL), '--kalkan-oz-sinama',
             '--gecici-kok', str(tmp_path), '--cikti', str(out)],
            cwd=str(tmp_path), env=_child_env(), capture_output=True,
            text=True, timeout=120)
        result = json.loads(out.read_text(encoding='utf-8'))
        assert result == {k: True for k in result}, result
        assert set(result) >= {'socket_create_connection', 'socket_connect',
                               'urllib', 'subprocess', 'os_system',
                               'os_exit', 'dosya_disari_yazma',
                               'dosya_disari_silme', 'ic_yazma_serbest',
                               'disari_dosya_olusmadi'}
        assert proc.returncode == 0

    @pytest.mark.parametrize('address,local', [
        (('127.0.0.1', 80), True), (('::1', 80, 0, 0), True),
        (('localhost', 1), True), ('/tmp/x.sock', True),
        (('203.0.113.1', 9), False), (('172.65.90.24', 443), False),
        (('example.com', 443), False), (None, False),
    ])
    def test_yerel_adres_ayrimi(self, address, local):
        assert fuzz.Shield.is_local_address(address) is local

    def test_surec_olayi_yalniz_yuk_ulasirsa_bulgu(self):
        sabit = {'olay': 'subprocess.Popen', 'arg': "('fc-list', ['fc-list'])"}
        assert fuzz.shield_event_problem(sabit) is None
        yuklu = {'olay': 'subprocess.Popen',
                 'arg': f"('open', ['{fuzz.SENTINEL}'])"}
        assert fuzz.shield_event_problem(yuklu) == 'komut_enjeksiyonu'
        assert fuzz.shield_event_problem(
            {'olay': 'socket.connect', 'hedef': 'x'}) is None
        assert fuzz.shield_event_problem(
            {'olay': 'open', 'yol': '/x'}) == 'yan_etki'


def _turler(**kw):
    base = dict(status=200, content_type='application/json', raw=b'{}',
                path='/api/x', method='POST', case_class='bozuk_json',
                elapsed_s=0.01, rss_growth=0)
    base.update(kw)
    return [t for t, _ in fuzz.classify_response(**base)]


class TestKahinler:
    def test_temiz_yanit_bulgusuz(self):
        assert _turler() == []

    def test_500_yakalanir_501_503_bilincli(self):
        assert 'http_500' in _turler(status=500)
        assert 'http_500' not in _turler(status=503)
        assert 'http_500' not in _turler(status=501)

    def test_nan_sizintisi(self):
        assert 'json_gecersiz' in _turler(raw=b'{"a": NaN}')
        assert 'json_gecersiz' in _turler(raw=b'{"a": -Infinity}')

    def test_sablon_degerlendirmesi(self):
        raw = (f'{{"a": "{fuzz.SENTINEL}49{fuzz.SENTINEL_END}"}}').encode()
        assert 'yansima' in _turler(raw=raw)

    def test_html_kacissiz_betik(self):
        raw = f'<p><script>alert("{fuzz.SENTINEL}")</script>'.encode()
        assert 'yansima' in _turler(content_type='text/html', raw=raw,
                                    method='GET', path='/')
        kacisli = json.dumps({'a': f'<script>alert("{fuzz.SENTINEL}")'})
        assert 'yansima' not in _turler(raw=kacisli.encode())

    def test_sure_sinirlari(self):
        sinir = fuzz.VALIDATION_TIME_LIMIT_S
        assert 'kararlilik_sure' in _turler(status=400, elapsed_s=sinir + 1)
        assert 'kararlilik_sure' not in _turler(status=200,
                                                elapsed_s=sinir + 1)
        assert 'kararlilik_sure' in _turler(
            status=200, elapsed_s=fuzz.VALID_EDGE_TIME_LIMIT_S + 1)

    def test_bellek_ve_json_olmayan_hata(self):
        assert 'bellek' in _turler(
            rss_growth=fuzz.MEMORY_PEAK_LIMIT_BYTES + 1)
        assert 'json_olmayan_hata' in _turler(status=400,
                                              content_type='text/html')

    def test_vakalar_deterministik(self):
        entry = {'rule': '/api/altitude-to-pressure', 'method': 'POST',
                 'classes': list(fuzz.JSON_FIELD_CLASSES), 'kip': 'tam',
                 'seed': {'altitude': 1000}, 'fields': ['altitude']}
        a = [c.summary() for c in fuzz.generate_cases(entry, 8, 7, 0)]
        b = [c.summary() for c in fuzz.generate_cases(entry, 8, 7, 0)]
        assert a == b
        assert {c['govde_bas'] for c in a} != {
            c.summary()['govde_bas']
            for c in fuzz.generate_cases(entry, 8, 8, 0)}


# ---------------------------------------------------------------------------
# 3) Küçültülmüş fuzz vakaları — düzeltilen bulguların regresyonu
# ---------------------------------------------------------------------------

from hrma import app as app_module  # noqa: E402
from hrma.security import json_parse  # noqa: E402

#: Ayrıştırıcı özyineleme sınırını aşan derinlik (fuzz vakası; ≈200 KB,
#: gövde kapısının bütçesi altında).
DERIN = fuzz.EXTREME_DEEP_JSON_LEVELS
#: float64'e sığmayan tam sayı (``float()`` OverflowError).
TASAN_TAM_SAYI = '1' + '0' * 400


@pytest.fixture
def istemci(monkeypatch):
    """Gerçek sunucu ayarı: işlenmemiş hata HTML 500 olarak döner."""
    monkeypatch.setitem(app_module.app.config, 'TESTING', False)
    monkeypatch.setitem(app_module.app.config, 'PROPAGATE_EXCEPTIONS', False)
    return app_module.app.test_client()


def _gonder(istemci, yol, govde):
    if not isinstance(govde, (bytes, str)):
        govde = json.dumps(govde, allow_nan=True)
    return istemci.post(yol, data=govde, content_type='application/json',
                        headers={'Host': SELF_HOST})


def _json_400(r, kod=400):
    ham = r.get_data()
    assert r.status_code == kod, (r.status_code, ham[:200])
    assert r.is_json, ham[:200]
    assert fuzz.strict_json_problem(ham) is None
    return r.get_json()


class TestF01DerinJson:
    """ÖNCE: 100 000 düzeyli gövde 55 uçta HTML 500 (RecursionError)."""

    @pytest.mark.parametrize('tur', ['list', 'dict'])
    @pytest.mark.parametrize('yol', ['/api/altitude-to-pressure',
                                     '/api/burn-rate/resolve',
                                     '/api/flow-analysis'])
    def test_kapi_400(self, istemci, yol, tur):
        r = _gonder(istemci, yol, fuzz._deep_text(DERIN, tur))
        assert _json_400(r)['error'] == 'json_nesting_too_deep'

    @pytest.mark.parametrize('yol', ['/api/import/ork',
                                     '/api/import/motor-file',
                                     '/api/projects/save'])
    def test_kendi_kapili_uc_buyuk_derin_govde_500_degil(self, istemci, yol):
        """Kapının okumadığı (> 1 MiB) uçlarda ``app.json`` sağlayıcısı."""
        seviye = app_module._JSON_BODY_GATE_MAX_BYTES  # gövde > 2 × kapı
        r = _gonder(istemci, yol, fuzz._deep_text(seviye, 'list'))
        govde = _json_400(r)
        # Ucun KENDİ adlı ret iletisi; derin yük iletiye yankılanmaz
        # (test_d22 iddiasız nüfus bekçisi: iddia test gövdesinde durur).
        assert isinstance(govde.get('error'), str) and govde['error']
        assert '[[[' not in govde['error']

    def test_saglayici_kayitli(self):
        assert isinstance(app_module.app.json, json_parse.StrictJSONProvider)


class TestF02KapiUstuNesneOlmayanGovde:
    """ÖNCE: 1 MiB üstü dizi gövde 51 uçta 500 (SG-2 devri C11-1)."""

    GOVDE = b'[' + b'1,' * (app_module._JSON_BODY_GATE_MAX_BYTES // 2) + b'1]'

    @pytest.mark.parametrize('yol', ['/api/advanced-performance-analysis',
                                     '/api/comparative-analysis',
                                     '/api/regen-cooling',
                                     '/api/six-dof-analysis',
                                     '/api/correlation-report'])
    def test_kapi_400(self, istemci, yol):
        assert len(self.GOVDE) > app_module._JSON_BODY_GATE_MAX_BYTES
        r = _gonder(istemci, yol, self.GOVDE)
        assert _json_400(r)['error'] == 'body_not_an_object'

    def test_kendi_kapili_uclar_adiyla(self):
        assert app_module._OWN_LENGTH_GATE_ENDPOINTS == frozenset({
            'importers_api.import_ork', 'importers_api.import_motor_file',
            'projects_api.api_projects_save'})


class TestF03TasanTamSayi:
    """ÖNCE: ``10**400`` 26 uçta 500 ('int too large to convert to float')."""

    @pytest.mark.parametrize('yol,alan', [
        ('/api/altitude-to-pressure', 'altitude'),
        ('/analyze_safety', 'thrust'),
        ('/api/flow-analysis', 'molecular_weight'),
        ('/calculate', 'wall_thickness'),
    ])
    def test_kapi_400(self, istemci, yol, alan):
        govde = '{"%s": %s}' % (alan, TASAN_TAM_SAYI)
        assert _json_400(_gonder(istemci, yol, govde))['error'] == \
            'number_out_of_range'

    def test_sinir_degerleri(self):
        en_buyuk = str(int(sys.float_info.max))
        assert len(en_buyuk) == json_parse.FLOAT_MAX_INT_DIGITS
        assert json_parse.loads_strict('[%s]' % en_buyuk)[0] == int(en_buyuk)
        with pytest.raises(json_parse.JSONNumberOutOfRange):
            json_parse.loads_strict('[%s0]' % en_buyuk)
        with pytest.raises(json_parse.JSONNumberOutOfRange):
            json_parse.loads_strict(b'{"a": -%s}' % TASAN_TAM_SAYI.encode())
        # Dize içindeki uzun rakam dizisi sayı değildir.
        assert json_parse.loads_strict(
            '{"a": "%s"}' % TASAN_TAM_SAYI) == {'a': TASAN_TAM_SAYI}

    def test_hatalar_valueerror_alt_sinifi(self):
        assert issubclass(json_parse.JSONNumberOutOfRange, ValueError)
        assert issubclass(json_parse.JSONNestingTooDeep, ValueError)


class TestF04F12UcTipKapilari:
    """ÖNCE: her vaka HTTP 500 + ham Python metni (fuzz tam koşusu)."""

    def test_f04_advanced_analysis_cooling_type(self, istemci):
        govde = {'motor_data': {'chamber_pressure': 30.0,
                                'chamber_temperature': 3000.0,
                                'chamber_diameter': 0.12,
                                'chamber_length': 0.4, 'burn_time': 10.0,
                                'mdot_total': 1.2},
                 'analysis_types': ['heat_transfer'],
                 'material_type': 'steel', 'wall_thickness': 0.005,
                 'cooling_type': {'a': 1}}
        g = _json_400(_gonder(istemci, '/api/advanced-analysis', govde))
        assert g['invalid_fields'][0]['field'] == 'cooling_type'

    def test_f05_flight_vehicle_results(self, istemci):
        govde = {'source': 'results', 'motor_type': 'hybrid',
                 'results': '../../../../etc/passwd'}
        g = _json_400(_gonder(istemci, '/api/flight-vehicle', govde))
        assert g['invalid_fields'][0] == {'field': 'results',
                                          'reason': 'not_an_object',
                                          'received_type': 'str'}

    def test_f06_get_fuel_properties(self, istemci):
        g = _json_400(_gonder(istemci, '/api/get-fuel-properties',
                              {'fuel_type': [1, 2], 'temperature': 2000}))
        assert g['invalid_fields'][0]['field'] == 'fuel_type'
        assert 'NASA CEA' not in g['message']

    def test_f07_find_optimum_of(self, istemci):
        govde = {'motor_type': 'hybrid', 'oxidizer': 'n2o',
                 'fuel': {'a': 1}, 'chamber_pressure': 20.0}
        g = _json_400(_gonder(istemci, '/api/find-optimum-of', govde))
        assert g['invalid_fields'][0]['field'] == 'fuel'

    def test_f08_bolted_joint_sonsuz_civata(self, istemci):
        govde = ('{"pressure_bar": 40.0, "seal_diameter_mm": 100.0, '
                 '"bolt_count": 1e999, "member_material": "aluminum_6061"}')
        g = _json_400(_gonder(istemci, '/api/bolted-joint', govde))
        assert 'bolt_count' in g['error']

    @pytest.mark.parametrize('yol', ['/api/analysis/combustion-stability',
                                     '/api/combustion-stability'])
    def test_f09_mod_yankisi_kati_json(self, istemci, yol):
        g = _json_400(_gonder(istemci, yol, '{"mode": NaN}'))
        assert g['invalid_fields'][0]['submitted'] is None

    @pytest.mark.parametrize('alan,deger', [('analysis_results', 'metin'),
                                            ('charts', 5)])
    def test_f10_export_pdf(self, istemci, alan, deger):
        govde = {'motor_data': {'motor_type': 'hybrid', 'motor_name': 'BARE',
                                'thrust': 1000.0, 'burn_time': 5.0},
                 'analysis_results': {}, 'charts': []}
        govde[alan] = deger
        g = _json_400(_gonder(istemci, '/api/export-pdf/complete', govde))
        assert g['invalid_fields'][0]['field'] == alan

    def test_f11_export_xlsx_uzun_ad(self, istemci):
        govde = {'filename': 'A' * 300,
                 'sheets': [{'name': 'S', 'headers': ['a'], 'rows': [[1]]}]}
        g = _json_400(_gonder(istemci, '/api/export-xlsx', govde))
        assert g['invalid_fields'][0]['field'] == 'filename'

    def test_f11_propellant_uzun_ad(self, istemci):
        govde = {'propellant_type': 'oxidizer', 'propellant_name': 'A' * 300}
        g = _json_400(_gonder(istemci, '/api/get-propellant-properties',
                              govde))
        assert g['invalid_fields'][0]['field'] == 'propellant_name'

    def test_f11_chart_pdf_uzun_baslik(self):
        """Görünüm doğrudan çağrılır: bu uç ürün yüzünden hiç çağrılmıyor
        (test_d18 P13B2-08 envanteri); HTTP üzerinden sınamak onu 'yalnız
        testin tanımladığı uç' borcuna çevirirdi. Fuzz düzeneği ucu HTTP
        üzerinden zaten sınıyor (``tools/fuzz_api.py``)."""
        govde = {'chart_data': '{"data":[],"layout":{}}',
                 'chart_title': 'A' * 300, 'motor_name': 'T'}
        with app_module.app.test_request_context(
                method='POST', json=govde, headers={'Host': SELF_HOST}):
            yanit, kod = app_module.export_chart_as_pdf()
        assert kod == 400
        g = yanit.get_json()
        assert g['invalid_fields'][0]['field'] == 'chart_title'

    @pytest.mark.parametrize('deger', ["'; DROP TABLE t;--", {'a': 1}])
    def test_f12_thermal_protection(self, istemci, deger):
        govde = {'mode': 'ablative', 'material': 'silica_phenolic',
                 'design_margin': deger, 'burn_time_s': 10,
                 'h_gas_W_m2K': 3000, 'T_recovery_K': 3200,
                 'q_net_W_m2': 2000000.0}
        g = _json_400(_gonder(istemci, '/api/thermal-protection', govde))
        assert g['invalid_fields'][0]['field'] == 'design_margin'

    def test_f12_dizi_aki_hala_gecer(self):
        assert app_module._TP_FIELD_TYPES['q_net_W_m2'] == 'number_or_array'
        assert app_module._TP_FIELD_TYPES['store_history'] is None

    def test_f15_kararlilik_tasmasi_422(self, istemci):
        govde = {'mode': 'chug', 'dp_ratio_j': 0.2, 'tau_s': 0.001,
                 'tau_c_s': 1e308}
        g = _json_400(_gonder(istemci, '/api/analysis/combustion-stability',
                              govde), kod=422)
        assert g['error'] == 'not_numerically_evaluable'
