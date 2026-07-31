"""examples/ dizinindeki üç örnek .hrma projesinin bekçileri.

Örnekler kullanıcıyı boş formla baş başa bırakmamak için var: uygulama ilk
açıldığında hibrit / katı / sıvı için hazır, HESAPLANABİLİR birer tasarım
sunarlar. Bu testler üç şeyi kilitler:

  1. Dosyalar uygulamanın kendi proje deposundan (hrma/utils/projects.py)
     şema doğrulamasıyla yüklenebilir — elle bozulmuş örnek yayınlanamaz.
  2. Örnekteki her form alanı ilgili şablonda GERÇEKTEN vardır ve select
     alanlarının değeri şablonun seçenek listesindedir — arayüzde alan adı
     ya da seçenek değeri değişirse örnek sessizce çürüyemez.
  3. Örnek, ait olduğu hesap ucundan (/calculate, /calculate_solid,
     /calculate_liquid) HTTP 200 ile geçer ve temel büyüklükler (itki, Isp,
     yanma süresi, c*, oda sıcaklığı) fiziksel olarak makul ARALIKTADIR.
     Aralıklar bilinçli olarak geniştir (mertebe denetimi): model
     rekalibrasyonunda kırılmasınlar ama saçma sonucu da geçirmesinler.

Uydurma-veri-yasağı bekçisi: dosyadaki results_summary, aynı girdilerle
yapılan TAZE hesapla karşılaştırılır — örnek dosyaya elle "güzel" sayı
yazılamaz.

Örnekler examples/generate_examples.py ile üretilir; o betik buradaki
NAMES / ENDPOINTS / calculate_payload tanımlarını import eder (tek doğruluk
kaynağı bu dosyadır).
"""

import json
import math
import pathlib

import pytest

from tests.support import inventory

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / 'examples'

# Uygulama yalnız geri döngü Host başlığına yanıt verir (DNS-rebinding kapısı)
HEADERS = {'Host': '127.0.0.1:8080'}

#: motor_type -> örnek proje adı (dosya adı = ad + '.hrma')
NAMES = {
    'hybrid': 'Example Hybrid N2O-HTPB 3kN',
    'solid': 'Example Solid KNDX BATES 75mm',
    'liquid': 'Example Liquid LOX-RP1 25kN',
}

#: motor_type -> hesap ucu
ENDPOINTS = {
    'hybrid': '/calculate',
    'solid': '/calculate_solid',
    'liquid': '/calculate_liquid',
}


def calculate_payload(motor_type, fields):
    """inputs.fields (form alan kimlikleri) -> hesap ucu yükü.

    Katı ve sıvı sayfalarında toplayıcı (collectAllParameters) alan
    kimliğini payload anahtarı olarak birebir kullanır. Hibrit toplayıcı
    (advanced.html::getFormData) üç istisna taşır ve burada aynen
    yansıtılır:

      * single_pressure -> atmospheric_pressure (tek irtifa modu),
      * total_impulse = thrust * burn_time (thrust/time modu aktifken),
      * calculate_trajectory: sayfada bu kimlikte checkbox yok, toplayıcı
        her koşuda false gönderir; contraction_ratio / mass_flux_chamber
        alan boşsa 0 gönderilir.
    """
    data = dict(fields)
    if motor_type == 'hybrid':
        if 'single_pressure' in data:
            data['atmospheric_pressure'] = data.pop('single_pressure')
        if 'thrust' in data and 'burn_time' in data:
            data['total_impulse'] = data['thrust'] * data['burn_time']
        data.setdefault('contraction_ratio', 0)
        data.setdefault('mass_flux_chamber', 0)
        data.setdefault('calculate_trajectory', False)
    return data


def load_example_doc(motor_type):
    """Örnek .hrma belgesini düz JSON olarak oku (depodan bağımsız)."""
    path = EXAMPLES_DIR / (NAMES[motor_type] + '.hrma')
    assert path.exists(), f'{path} yok — examples/generate_examples.py koşun'
    with open(path, encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


@pytest.fixture()
def store_env(monkeypatch):
    """Proje deposunu examples/ dizinine yönlendir (salt okunur kullanım)."""
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(EXAMPLES_DIR))


# Hesap sonuçları pahalı (sıvı ~5-10 s) — motor tipi başına BİR kez hesaplanır
_RESULTS = {}


def _fresh_results(client, motor_type):
    if motor_type not in _RESULTS:
        doc = load_example_doc(motor_type)
        payload = calculate_payload(motor_type, doc['inputs']['fields'])
        resp = client.post(ENDPOINTS[motor_type], json=payload,
                           headers=HEADERS)
        assert resp.status_code == 200, (
            f'{ENDPOINTS[motor_type]} {resp.status_code}: '
            + resp.get_data(as_text=True)[:400])
        body = resp.get_json()
        assert 'error' not in body, body.get('error')
        _RESULTS[motor_type] = body
    return _RESULTS[motor_type]


# ---------------------------------------------------------------------------
# 1. Dosyalar uygulamanın kendi deposundan yüklenebilir
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_example_loads_through_project_store(store_env, motor_type):
    from hrma.utils import projects as store
    doc, warnings = store.load_project(NAMES[motor_type])
    assert doc['format'] == 'hrma-project'
    assert doc['format_version'] == 1
    assert doc['motor_type'] == motor_type
    assert doc['inputs']['fields'], 'inputs.fields boş olamaz'
    assert doc.get('description'), 'örneğin açıklaması olmalı'
    # Damgalar mevcut olmalı (sürüm farkı uyarısı zamanla doğal olarak çıkar)
    for stamp in ('app_version', 'created_at', 'updated_at'):
        assert stamp in doc, f'{stamp} damgası eksik'
    assert not any('missing' in w for w in warnings), warnings


@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_example_loads_through_http_api(store_env, client, motor_type):
    resp = client.get('/api/projects/load/' + NAMES[motor_type],
                      headers=HEADERS)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    body = resp.get_json()
    assert body['status'] == 'loaded'
    assert body['source'] == 'hrma-project-file'
    assert body['project']['motor_type'] == motor_type
    assert body['estimated'] == []  # sunucu hiçbir alanı tahminle doldurmaz


# ---------------------------------------------------------------------------
# 2. Alan kimlikleri şablonda gerçekten var (örnek çürümesi bekçisi)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_example_fields_exist_on_the_page(motor_type):
    doc = load_example_doc(motor_type)
    specs = inventory.field_specs_for(motor_type)
    unknown, bad_options = [], []
    for field_id, value in doc['inputs']['fields'].items():
        spec = specs.get(field_id)
        if spec is None:
            unknown.append(field_id)
            continue
        if spec.tag == 'select' and str(value) not in (spec.options or []):
            bad_options.append(f'{field_id}={value!r} '
                               f'(seçenekler: {spec.options})')
    assert not unknown, (
        f'{motor_type} örneğindeki şu alanlar şablonda yok: {unknown}')
    assert not bad_options, (
        f'{motor_type} örneğinde şablon seçeneği olmayan değerler: '
        + '; '.join(bad_options))


# ---------------------------------------------------------------------------
# 3. Hesap: HTTP 200 + fiziksel olarak makul aralıklar
# ---------------------------------------------------------------------------
def test_hybrid_example_calculates_sensibly(client):
    motor = _fresh_results(client, 'hybrid')['motor']
    # Girdi yankıları: 3 kN / 10 s tasarım noktası
    assert 2700 <= motor['thrust'] <= 3300
    assert 9.0 <= motor['burn_time'] <= 11.0
    assert 25000 <= motor['total_impulse'] <= 35000
    # N2O/HTPB fiziksel bantları (Sutton & Biblarz; hibrit literatürü):
    # deniz seviyesi Isp ~200-260 s, c* ~1500-1700 m/s, Tc ~3100-3500 K
    assert 190 <= motor['isp'] <= 300, motor['isp']
    assert 1450 <= motor['c_star'] <= 1800, motor['c_star']
    assert 3000 <= motor['chamber_temperature'] <= 3700, \
        motor['chamber_temperature']


def test_solid_example_calculates_sensibly(client):
    results = _fresh_results(client, 'solid')
    # 75 mm, 3xBATES KNDX: L sınıfı, ~2 s yanma
    assert 800 <= results['average_thrust'] <= 3500
    assert results['max_thrust'] >= results['average_thrust']
    assert 1.0 <= results['burn_time'] <= 4.0
    assert 2000 <= results['total_impulse'] <= 6000
    # KN-şeker teslim Isp bandı (Nakka deneysel ~115-130 s, ideal ~137-164 s)
    assert 110 <= results['specific_impulse'] <= 175, \
        results['specific_impulse']
    # c* örnekte merkezi katalogdan girilir (propellants_db: 912.4 m/s)
    assert 850 <= results['c_star'] <= 1000, results['c_star']


def test_liquid_example_calculates_sensibly(client):
    results = _fresh_results(client, 'liquid')
    assert 24000 <= results['thrust'] <= 26000
    # LOX/RP-1 gaz jeneratörü sınıfı: Isp(deniz) ~260-300 s, c* ~1700-1800,
    # Tc ~3400-3700 K (O/F 2.3 civarı)
    assert 240 <= results['isp_sea_level'] <= 320, results['isp_sea_level']
    assert results['isp_vacuum'] > results['isp_sea_level']
    assert results['isp_vacuum'] <= 360
    assert 1600 <= results['c_star'] <= 1900, results['c_star']
    assert 3300 <= results['chamber_temperature'] <= 3800, \
        results['chamber_temperature']


# ---------------------------------------------------------------------------
# 4. results_summary uydurma değil: taze hesapla tutarlı
# ---------------------------------------------------------------------------
def _summary_reference(motor_type, body):
    """Özet anahtarı -> taze hesaptaki karşılığı (project_bar.js eşlemesi)."""
    if motor_type == 'hybrid':
        motor = body['motor']
        return {
            'thrust_N': motor.get('thrust'),
            'isp_s': motor.get('isp'),
            'burn_time_s': motor.get('burn_time'),
            'chamber_pressure_bar': motor.get('chamber_pressure'),
            'total_impulse_Ns': motor.get('total_impulse'),
        }
    if motor_type == 'solid':
        return {
            'total_impulse_Ns': body.get('total_impulse'),
            'burn_time_s': body.get('burn_time'),
            'chamber_pressure_bar': body.get('chamber_pressure'),
            'isp_s': body.get('isp_sea_level'),
            'peak_thrust_N': body.get('max_thrust'),
        }
    return {
        'thrust_N': body.get('thrust'),
        'isp_s': body.get('isp_sea_level'),
        'isp_vacuum_s': body.get('isp_vacuum'),
        'chamber_pressure_bar': body.get('chamber_pressure'),
    }


@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_results_summary_is_not_fabricated(client, motor_type):
    doc = load_example_doc(motor_type)
    summary = doc.get('results_summary')
    assert summary, 'örnekte results_summary olmalı (liste kartları için)'
    reference = _summary_reference(motor_type, _fresh_results(client,
                                                              motor_type))
    checked = 0
    for key, saved in summary.items():
        if key == 'computed_with_version' or key not in reference:
            continue
        fresh = reference[key]
        assert isinstance(fresh, (int, float)) and math.isfinite(fresh), (
            f'{motor_type}.{key}: taze hesapta karşılık yok')
        # Gevşek tolerans: model rekalibrasyonu özeti hemen kırmasın, ama
        # elle yazılmış "güzel" sayı da saklanamasın.
        assert math.isclose(saved, fresh, rel_tol=0.25, abs_tol=1e-9), (
            f'{motor_type}.{key}: kayıtlı {saved} / taze {fresh} — özet '
            'bayatlamış ya da elle yazılmış; örneği yeniden üretin '
            '(examples/generate_examples.py)')
        checked += 1
    assert checked >= 3, 'özet en az üç sayısal büyüklük taşımalı'


if __name__ == '__main__':                  # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, '-v']))
