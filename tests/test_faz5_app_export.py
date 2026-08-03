"""Faz 5B bekçileri — ``hrma/app.py`` girdi kapıları, export ve birim sözleşmesi.

Bu dosya Faz 5 avında ÖLÇÜLEN altı kusuru kilitler. Her sınıfın başında
düzeltme öncesi ham ölçüm durur; test o ölçümün geri gelmesini engeller.

* **H3-B4** — ``/api/export-stl-zip`` hiçbir geometri kapısından geçmiyordu.
  Boş ``motor_data`` ile HTTP 200 ve 120 426 baytlık bir ZIP dönüyordu;
  içindeki ``motor_assembly.stl``'in sınırlayıcı kutusu ``109 x 109 x 489.7``
  — yani kullanıcının motoru değil, ``cad_visualization.py``'nin şablonu.
  Kardeşleri (``/api/export-stl`` 400/422, ``/api/export-complete-zip`` 422)
  aynı isteği reddediyordu.
* **H3-B7** — bozuk JSON 47 uçta, JSON skaler 54 uçta, JSON dizi 23 uçta,
  boş gövde 5+ uçta **HTTP 500** üretiyordu (``except Exception`` bloğu
  ``werkzeug.BadRequest``'i yutuyor ya da ``data.get`` ``AttributeError``
  atıyordu). Kapı artık ``app.before_request`` içinde TEK yerde.
* **H3-B9** — üç uç RFC 8259 dışı JSON yayımlıyordu (ham ``NaN`` / ``Infinity``).
  Python ``json.loads`` bunu kabul eder, tarayıcının ``JSON.parse``'ı ETMEZ:
  panel gerçek sorun yerine ayrıştırma hatası gösterir.
* **H3-B13** — 100 000 karakterlik tek bir alan ``/calculate``'te 200 109
  baytlık bir hata gövdesi üretiyordu (girdi iki kez kopyalanmıştı).
* **H3-B14** — ``/api/export-step`` REDDETTİĞİ istekte bile build123d/OCC
  yığınını yüklüyordu: tepe RSS 216 MB → 649 MB, 3,41 s, ve modül süreçte
  kalıcı. Sebep sıra hatasıydı (ithalat kapıdan önce).
* **H4-2** — çizim uçlarının birim sözleşmesi yazılı değildi; üretici girdiyi
  koşulsuz metre kabul edip 1000 ile çarpıyordu. ``/calculate_solid`` yanıtı
  doğrudan uca verilince ``Ø_chamber = 100000.0 mm`` (gerçek 100.0),
  ``Ø_throat = 47927.25 mm`` (gerçek 47.93) çıkıyordu.

Not: H4-2 bekçileri UCUN sözleşmesini ölçer (üreticiye ne verildiğini),
üreticinin çıktısını değil — üretici tarafı ``hrma/export/drawing_generator.py``
ayrı bir bekçi kümesine sahiptir ve iki taraf birbirinden bağımsız
kilitlenmelidir.
"""

import json
import sys

import pytest

from hrma.app import (app, _clip_echo, _declare_drawing_units,
                      _ERROR_TEXT_MAX_CHARS, _JSON_BODY_GATE_MAX_BYTES,
                      DRAWING_ENDPOINT_LENGTH_UNIT)


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        yield test_client


def _post_raw(client, path, raw, content_type='application/json'):
    """Ham gövde gönderir — bozuk JSON'u ``jsonify`` düzeltmesin."""
    return client.post(path, data=raw, content_type=content_type)


def _browser_parseable(text):
    """Tarayıcı ``JSON.parse``'ını taklit eder: NaN/Infinity KABUL ETMEZ.

    Python'un ``json.loads``'ı bu sabitleri varsayılan olarak kabul ettiği
    için düz bir ``json.loads`` bu kusuru göremez; ``parse_constant`` kancası
    tam olarak o üç sabitte (``NaN``, ``Infinity``, ``-Infinity``) tetiklenir.
    """
    def _reject(name):
        raise ValueError('RFC 8259 disi sabit: ' + name)

    json.loads(text, parse_constant=_reject)
    return True


# ---------------------------------------------------------------------------
# H3-B7 — merkezi gövde doğrulaması
# ---------------------------------------------------------------------------

#: Ölçümde 500 dönen uçlardan bir kesit (hepsi POST + JSON gövde bekler).
BODY_GATE_ENDPOINTS = [
    '/calculate',
    '/api/quick-geometry',
    '/api/altitude-to-pressure',
    '/api/oxidizer-properties',
    '/api/export-stl-zip',
    '/analyze_structural_safety',
    '/api/transient-analysis',
    '/api/regression-analysis',
]

#: (etiket, ham gövde, beklenen ``error`` kodu)
BAD_BODIES = [
    ('bozuk_json', '{"a":', 'malformed_json_body'),
    ('json_skaler', '42', 'body_not_an_object'),
    ('json_dizi', '[]', 'body_not_an_object'),
    ('json_metin', '"merhaba"', 'body_not_an_object'),
    ('json_null', 'null', 'body_not_an_object'),
    ('bos_govde', '', 'empty_json_body'),
]


class TestMalformedBodyGate:
    @pytest.mark.parametrize('endpoint', BODY_GATE_ENDPOINTS)
    @pytest.mark.parametrize('label,raw,code', BAD_BODIES,
                             ids=[c[0] for c in BAD_BODIES])
    def test_bad_body_is_400_not_500(self, client, endpoint, label, raw, code):
        """Ölçüm öncesi bu 48 kombinasyonun büyük kısmı 500'dü."""
        response = _post_raw(client, endpoint, raw)
        assert response.status_code == 400, (
            f'{endpoint} {label} -> {response.status_code} '
            f'({response.get_data(as_text=True)[:200]})')
        body = response.get_json()
        assert body['error'] == code
        assert body['status'] == 'error'

    def test_gate_does_not_touch_non_json_content_type(self, client):
        """``multipart/form-data`` yükleme uçları kapının DIŞINDA.

        Kapı ``request.is_json`` şartına bağlı; dosya yükleyen uçlar
        (``/api/import/*``, ``/api/step/import``) kendi kapılarını
        çalıştırmaya devam etmeli. Kapı devreye girseydi bu istek
        ``malformed_json_body`` alırdı.
        """
        response = client.post('/api/import/motor-file',
                               data={'file': (None, '')},
                               content_type='multipart/form-data')
        body = response.get_json() or {}
        assert body.get('error') != 'malformed_json_body'

    def test_gate_skips_bodies_above_its_budget(self, client):
        """Kendi bütçesinin üstündeki gövdeyi kapı OKUMAZ.

        ``/api/import/ork`` (20 MiB) ve ``/api/projects/save`` kendi boyut
        kapılarını ``request.content_length`` ile ÖNCE çalıştırıyor; gövdeyi
        burada okumak o kapıları etkisiz bırakırdı. Bütçe üstü bozuk bir
        gövde bu yüzden ``malformed_json_body`` DEĞİL, ucun kendi yanıtını
        almalı.
        """
        raw = '{"a":' + ' ' * (_JSON_BODY_GATE_MAX_BYTES + 1024)
        response = _post_raw(client, '/api/import/ork', raw)
        body = response.get_json() or {}
        assert body.get('error') != 'malformed_json_body'

    def test_valid_object_body_still_reaches_the_endpoint(self, client):
        """Kapı meşru isteği geçirmeli — aksi hâlde uygulama hesap yapmaz."""
        response = client.post('/api/altitude-to-pressure',
                               json={'altitude': 1000})
        assert response.status_code == 200
        assert response.get_json()['pressure'] > 0

    def test_get_requests_are_not_gated(self, client):
        """Kapı yalnız gövde taşıyan metodlarda; GET dokunulmaz."""
        assert client.get('/').status_code == 200


# ---------------------------------------------------------------------------
# H3-B9 — RFC 8259 uyumu
# ---------------------------------------------------------------------------

#: (uç, gövde) — ölçümde ham ``Infinity`` sızdıran üç uç.
NON_FINITE_LEAK_CASES = [
    ('/api/altitude-to-pressure', {'altitude': -float('inf')}),
    ('/api/oxidizer-properties',
     {'oxidizer_type': 'n2o', 'temperature': float('inf')}),
    ('/api/regression-analysis',
     {'motor_data': {'chamber_diameter': 0.12, 'chamber_length': 0.5,
                     'throat_diameter': 0.03, 'exit_diameter': 0.08,
                     'port_diameter': 0.03, 'burn_time': float('inf'),
                     'regression_a': 0.0003, 'regression_n': 0.5,
                     'mass_flux': float('inf')}}),
]


class TestResponsesAreBrowserParseable:
    @pytest.mark.parametrize('endpoint,payload', NON_FINITE_LEAK_CASES,
                             ids=[c[0] for c in NON_FINITE_LEAK_CASES])
    def test_no_bare_nan_or_infinity_in_body(self, client, endpoint, payload):
        response = _post_raw(client, endpoint, json.dumps(payload))
        text = response.get_data(as_text=True)
        # Ham sabit metin olarak da bulunmamalı (ölçümde
        # /api/regression-analysis gövdesinde 198 adet vardı).
        assert 'Infinity' not in text, endpoint
        assert 'NaN' not in text, endpoint
        assert _browser_parseable(text)

    def test_non_finite_becomes_null_not_a_made_up_number(self, client):
        """Sonlu olmayan değer ``null`` olur; uydurma sayıya çevrilmez."""
        response = _post_raw(client, '/api/altitude-to-pressure',
                             json.dumps({'altitude': -float('inf')}))
        body = response.get_json()
        assert body['pressure'] is None
        assert body['temperature'] is None
        assert body['altitude'] is None


# ---------------------------------------------------------------------------
# H3-B13 — devasa girdi yankısı
# ---------------------------------------------------------------------------

LONG_INPUT = 'A' * 100_000


class TestHugeInputIsNotEchoedBack:
    def test_calculate_error_body_is_clipped(self, client):
        """Ölçüm: 200 109 bayt. Kırpma sonrası birkaç KB olmalı."""
        response = _post_raw(client, '/calculate',
                             json.dumps({'motor_type': LONG_INPUT}))
        assert response.status_code == 400
        assert len(response.data) < 10_000, len(response.data)
        text = response.get_data(as_text=True)
        assert 'truncated by HRMA' in text
        # Hiçbir metin alanı sınırın (+beyan cümlesi) üstünde kalmamalı.
        for value in _all_strings(response.get_json()):
            assert len(value) <= _ERROR_TEXT_MAX_CHARS + 120

    def test_success_body_with_long_echo_is_clipped_at_source(self, client):
        """``/api/get-fuel-properties`` HTTP 200 döner — kırpma kaynakta.

        Ölçüm: ``note`` alanı 100 049 karakterdi. ``_clip_error_body``
        yalnız HTTP >= 400 gövdelerine bakar, bu yüzden burada yankı
        ``_clip_echo`` ile kaynağında kırpılır.
        """
        response = _post_raw(client, '/api/get-fuel-properties',
                             json.dumps({'fuel_type': LONG_INPUT}))
        assert len(response.data) < 10_000, len(response.data)

    def test_normal_error_body_is_left_byte_identical(self, client):
        """Kısa hata gövdesine DOKUNULMAZ — kırpma beyanı da eklenmez."""
        response = _post_raw(client, '/api/export-step',
                             json.dumps({'motor_data': {}}))
        assert response.status_code == 422
        assert 'truncated by HRMA' not in response.get_data(as_text=True)
        assert response.get_json()['error'] == 'missing_export_geometry'

    def test_success_plot_payload_is_not_clipped(self, client):
        """Başarı gövdesindeki büyük çizim JSON'u KIRPILMAZ (veri kaybı olurdu).

        Ölçüldü: ``/api/quick-geometry`` yanıtında ``plots.motor`` 27 238
        karakter. Kırpıcı yalnız hata gövdelerine baktığı için buna
        dokunmamalı.
        """
        response = client.post('/api/quick-geometry',
                               json={'motor_type': 'hybrid'})
        assert response.status_code == 200
        assert 'truncated by HRMA' not in response.get_data(as_text=True)

    def test_clip_echo_declares_what_it_dropped(self):
        clipped = _clip_echo('B' * 5000, limit=100)
        assert clipped.startswith('B' * 100)
        assert '100 of 5000 characters' in clipped
        assert _clip_echo('kisa') == 'kisa'


def _all_strings(node):
    """Gövdedeki bütün metin yapraklarını dolaşır."""
    if isinstance(node, dict):
        for value in node.values():
            yield from _all_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _all_strings(value)
    elif isinstance(node, str):
        yield node


# ---------------------------------------------------------------------------
# H3-B4 — /api/export-stl-zip geometri kapısı
# ---------------------------------------------------------------------------

#: (etiket, motor_data) — kardeş uçların hepsinin reddettiği geometriler.
UNEXPORTABLE_GEOMETRIES = [
    ('bos', {}),
    ('hepsi_sifir', {'chamber_diameter': 0, 'chamber_length': 0,
                     'throat_diameter': 0, 'exit_diameter': 0}),
    ('negatif', {'chamber_diameter': -0.1, 'chamber_length': -0.5}),
    ('nan', {'chamber_diameter': float('nan'), 'chamber_length': 0.5}),
    ('metin', {'chamber_diameter': 'abc', 'chamber_length': 0.5}),
]


class TestStlZipHasTheSameGateAsItsSiblings:
    @pytest.mark.parametrize('label,motor_data', UNEXPORTABLE_GEOMETRIES,
                             ids=[c[0] for c in UNEXPORTABLE_GEOMETRIES])
    def test_unexportable_geometry_is_rejected(self, client, label,
                                               motor_data):
        """Ölçüm öncesi: boş ``{}`` → 200 + 120 426 baytlık şablon ZIP."""
        response = _post_raw(client, '/api/export-stl-zip',
                             json.dumps({'motor_data': motor_data}))
        assert response.status_code == 422, (
            f'{label} -> {response.status_code}')
        assert response.mimetype == 'application/json'
        assert response.get_json()['status'] in ('error',
                                                 'incomplete_geometry')

    @pytest.mark.parametrize('label,motor_data', UNEXPORTABLE_GEOMETRIES,
                             ids=[c[0] for c in UNEXPORTABLE_GEOMETRIES])
    def test_no_zip_is_produced(self, client, label, motor_data):
        """Reddedilen istekte ZIP baytı ÜRETİLMEZ (şablon motor sızmasın)."""
        response = _post_raw(client, '/api/export-stl-zip',
                             json.dumps({'motor_data': motor_data}))
        assert not response.data.startswith(b'PK')

    def test_gate_matches_its_export_siblings(self, client):
        """Kapı, kardeş export uçlarıyla AYNI kararı vermeli.

        Ölçüm öncesi ayrışma buydu: aynı ``motor_data`` kardeşlerde 422,
        burada 200 + şablon ZIP alıyordu.
        """
        for label, motor_data in UNEXPORTABLE_GEOMETRIES:
            raw = json.dumps({'motor_data': motor_data})
            here = _post_raw(client, '/api/export-stl-zip', raw)
            sibling = _post_raw(client, '/api/export-complete-zip', raw)
            assert here.status_code == sibling.status_code == 422, label
            assert (here.get_json()['error']
                    == sibling.get_json()['error']), label

    def test_stl_field_contract_is_a_named_testable_gate(self):
        """Sözleşme adlandırılmış TEK bir işlevde durmalı.

        Kusurun sınıfı buydu: denetim ``/api/export-stl`` gövdesine gömülü
        olduğu için ne adı ne de tek başına sınanabilirliği vardı.

        NOT: ``/api/export-stl-zip`` bu kapıyı bilinçli olarak KULLANMIYOR —
        sözleşmeyi oraya genişletmek ``tests/test_faz4_app_export.py``
        fikstürünü de değiştirmeyi gerektirir (ayrı karar, ayrı sahiplik).
        """
        from hrma.app import _reject_incomplete_stl_geometry
        # ``jsonify`` uygulama bağlamı ister.
        with app.test_request_context():
            assert _reject_incomplete_stl_geometry(
                {'chamber_diameter': 0.12, 'chamber_length': 0.5,
                 'port_diameter': 0.04}) is None
            rejected = _reject_incomplete_stl_geometry({'motor_type': 'solid'})
            assert rejected is not None and rejected[1] == 422


# ---------------------------------------------------------------------------
# H3-B14 — reddedilen istek ağır ithalatı ödemesin
# ---------------------------------------------------------------------------

class TestRejectedStepExportDoesNotLoadBuild123d:
    def test_import_happens_behind_the_gate(self):
        """Kaynak sırası kilitlenir: ithalat kapıdan SONRA gelmeli.

        Davranış ölçümü (bellek) ayrı süreç ister; bu bekçi aynı kusuru
        kaynağın kendisinden yakalar ve testin ölçüm sırasına bağımlı
        olmasını önler.
        """
        import ast
        import inspect
        import textwrap

        from hrma.app import export_step_files

        # Docstring'in kendisi de bu iki dizeyi ANLATIYOR; metin araması
        # açıklamayı ölçerdi. Bu yüzden gerçek sözdizimi ağacı taranır.
        tree = ast.parse(textwrap.dedent(
            inspect.getsource(export_step_files)))
        gate = heavy = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == '_reject_unexportable_geometry'):
                gate = node.lineno
            elif (isinstance(node, ast.ImportFrom)
                    and node.module == 'hrma.export.step_export'):
                heavy = node.lineno
        assert gate is not None and heavy is not None
        assert gate < heavy, (
            'step_export ithalati kapidan ONCE — reddedilen istek '
            '+433 MB kalici bellek oder (olculdu: 216 MB -> 649 MB).')

    def test_rejected_request_leaves_module_unloaded(self, client):
        """Modül zaten yüklüyse (başka test yükledi) bu bekçi atlanır."""
        if 'hrma.export.step_export' in sys.modules:
            pytest.skip('step_export bu surecte zaten yuklu')
        response = _post_raw(client, '/api/export-step',
                             json.dumps({'motor_data': {}}))
        assert response.status_code == 422
        assert 'hrma.export.step_export' not in sys.modules


# ---------------------------------------------------------------------------
# H4-2 — çizim uçlarının birim sözleşmesi
# ---------------------------------------------------------------------------

class TestDrawingEndpointDeclaresItsUnits:
    def test_contract_is_metres(self):
        assert DRAWING_ENDPOINT_LENGTH_UNIT == 'm'

    def test_millimetre_input_is_reduced_to_metres(self):
        """Ölçülen katı yanıtı: ``chamber_diameter = 75.0`` (mm).

        Düzeltme öncesi üretici bunu koşulsuz metre sayıp 1000 ile çarpıyor
        ve çizime ``75000 mm`` basıyordu.
        """
        declared = _declare_drawing_units({
            'chamber_diameter': 75.0, 'chamber_length': 460.0,
            'throat_diameter': 17.93, 'exit_diameter': 46.38})
        assert declared['length_units'] == 'm'
        assert declared['chamber_diameter'] == pytest.approx(0.075)
        assert declared['chamber_length'] == pytest.approx(0.460)
        assert declared['throat_diameter'] == pytest.approx(0.01793)
        assert declared['exit_diameter'] == pytest.approx(0.04638)

    def test_si_input_is_left_alone(self):
        """Hibrit yanıtı zaten SI — dokunulmamalı (kusur orada görünmüyordu)."""
        raw = {'chamber_diameter': 0.12004, 'chamber_length': 1.00316,
               'throat_diameter': 0.02974, 'exit_diameter': 0.06771}
        declared = _declare_drawing_units(dict(raw))
        for key, value in raw.items():
            assert declared[key] == pytest.approx(value)

    def test_mixed_unit_response_is_brought_to_one_scale(self):
        """Ölçülen sıvı yanıtı TEK sözlükte iki birim taşıyor.

        ``chamber_*`` mm, ``throat/exit`` metre. Düzeltme öncesi çizimde
        kamara lülenin 1000 katı çıkıyordu.
        """
        declared = _declare_drawing_units({
            'chamber_diameter': 99.1920877629081,
            'chamber_length': 97.95918367346941,
            'throat_diameter': 0.028340596503688,
            'exit_diameter': 0.10305780541018})
        assert declared['chamber_diameter'] == pytest.approx(0.0991920877629)
        assert declared['throat_diameter'] == pytest.approx(0.028340596503688)
        # Lüle çıkışı kamaradan büyük olmalı — ölçekler artık aynı.
        assert declared['exit_diameter'] > declared['chamber_diameter']

    def test_declaration_is_idempotent(self):
        """Üretici aynı normalize ediciyi tekrar çağırırsa ÇİFT dönüşüm olmaz.

        Üretici tarafı (``hrma/export/drawing_generator.py``) da ortak
        ``normalise_export_geometry``'yi çağırıyor; bu bekçi iki tarafın
        birbirini bozmadığını kilitler.
        """
        from hrma.export.motor_geometry import normalise_export_geometry

        once = _declare_drawing_units({'chamber_diameter': 75.0,
                                       'chamber_length': 460.0})
        twice, _ = normalise_export_geometry(once)
        thrice, _ = normalise_export_geometry(twice)
        assert twice['chamber_diameter'] == pytest.approx(0.075)
        assert thrice['chamber_diameter'] == pytest.approx(0.075)

    def test_unresolved_field_is_not_invented(self):
        """Çözülemeyen ölçüye uydurma değer YAZILMAZ."""
        declared = _declare_drawing_units({'chamber_diameter': 75.0})
        assert 'exit_diameter' not in declared

    def test_endpoint_hands_declared_units_to_the_generator(self, client,
                                                            monkeypatch):
        """Uç, üreticiye METRE + ``length_units`` damgası verir.

        Üreticinin çıktısı BİLEREK ölçülmüyor: bu bekçi ucun sözleşmesini
        kilitler, üretici tarafının kendi bekçileri vardır.
        """
        import hrma.export.drawing_generator as drawing_generator

        seen = {}

        def _capture(motor_data):
            seen['motor_data'] = motor_data
            raise RuntimeError('bekci: uretici cagrildi, cizim uretilmiyor')

        monkeypatch.setattr(drawing_generator, 'generate_dxf', _capture)
        client.post('/api/export-dxf', json={'motor_data': {
            'chamber_diameter': 75.0, 'chamber_length': 460.0,
            'throat_diameter': 17.93, 'exit_diameter': 46.38}})

        handed = seen['motor_data']
        assert handed['length_units'] == 'm'
        assert handed['chamber_diameter'] == pytest.approx(0.075)
        assert handed['throat_diameter'] == pytest.approx(0.01793)
        # Hangi alanın hangi yoldan çözüldüğü raporlanmalı (sessiz dönüşüm yok).
        assert 'geometry_unit_resolution' in handed

    def test_drawings_pdf_endpoint_shares_the_contract(self, client,
                                                       monkeypatch):
        import hrma.export.drawing_generator as drawing_generator

        seen = {}

        def _capture(motor_data):
            seen['motor_data'] = motor_data
            raise RuntimeError('bekci: uretici cagrildi')

        monkeypatch.setattr(drawing_generator, 'generate_drawing_pdf',
                            _capture)
        client.post('/api/export-drawings-pdf', json={'motor_data': {
            'chamber_diameter': 75.0, 'chamber_length': 460.0}})
        assert seen['motor_data']['length_units'] == 'm'
        assert seen['motor_data']['chamber_diameter'] == pytest.approx(0.075)

    def test_unit_declaration_runs_after_the_finite_gate(self, client):
        """Sonlu olmayan geometri birim çözümüne HİÇ ulaşmamalı.

        Sıra tersine dönerse normalize edici NaN'ı sessizce eleyip kapıyı
        kör edebilirdi.
        """
        response = _post_raw(client, '/api/export-dxf', json.dumps(
            {'motor_data': {'chamber_diameter': float('nan'),
                            'chamber_length': 0.5}}))
        assert response.status_code == 422
        assert response.get_json()['error'] == 'invalid_export_geometry'
