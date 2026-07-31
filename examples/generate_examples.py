"""Örnek .hrma projelerini uygulamanın KENDİ kayıt yolundan üretir.

Neden betik: örnek dosyayı elle JSON yazmak şema çürümesine açıktır. Burada
üç örnek (hibrit / katı / sıvı):

  1. alan değerleri uygulamanın kendi kataloglarından okunarak kurulur
     (KNDX termokimyası: hrma/data/propellants_db.py; KNDX yanma hızı:
     hrma/data/burn_rate_db.py rejim fiti; N2O yoğunluk/viskozite:
     /api/oxidizer-properties ucu; HTPB regresyon katsayıları:
     advanced.html form varsayılanı = Doran et al. AIAA 2007-5352),
  2. ilgili hesap ucundan (/calculate, /calculate_solid, /calculate_liquid)
     GERÇEKTEN geçirilir (HTTP 200 şartı) ve results_summary o koşunun
     çıktısından doldurulur (uydurma sayı yasak),
  3. hrma/utils/projects.py::save_project ile yazılır — şema doğrulaması
     ve damgalar (app_version, created_at) uygulamanın kendisinden gelir.

Alan kimliği -> hesap yükü eşlemesi tests/test_example_projects.py'daki
calculate_payload'dan import edilir (tek doğruluk kaynağı test dosyasıdır).

Kullanım (depo kökünden):
    python3 examples/generate_examples.py
"""

import os
import pathlib
import sys

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = EXAMPLES_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

# Proje deposu examples/ dizinine yönlendirilir; save_project dosyaları
# doğrudan buraya yazar. Import'lardan ÖNCE ayarlanmalı.
os.environ['HRMA_PROJECTS_DIR'] = str(EXAMPLES_DIR)

from tests.test_example_projects import (          # noqa: E402
    ENDPOINTS, HEADERS, NAMES, calculate_payload)


def _round_maybe(value, digits):
    return round(float(value), digits)


def build_examples(client):
    """Üç örneğin (ad, belge) çiftlerini uygulama kataloglarından kur."""
    from hrma.data import burn_rate_db, propellants_db

    # --- Katalog okumaları (sayı uydurmak yasak) ---------------------------
    kndx = propellants_db.get_propellant('kndx')
    # Tasarım basıncı 40 bar: KNDX rejim fitinin yayımlanmış aralığında
    # (2.57-5.93 MPa rejimi); resolve_engine_coeffs motor konvansiyonuna
    # çevirir (r[m/s] = a * P[bar]^n). Sayfadaki preset akışı da aynı ucu
    # kullanır (/api/burn-rate/resolve) ve a'yı 7, n'yi 4 haneye yazar.
    kndx_coeffs = burn_rate_db.resolve_engine_coeffs('kndx', 40.0)
    assert kndx_coeffs['in_range'], 'KNDX fiti 40 bar kapsamalı'

    resp = client.post('/api/oxidizer-properties',
                       json={'oxidizer_type': 'n2o', 'temperature': 293},
                       headers=HEADERS)
    assert resp.status_code == 200, 'N2O özellik ucu yanıt vermedi'
    n2o = resp.get_json()['properties']

    hybrid_desc = (
        'Öğretici örnek: N2O/HTPB hibrit motor, 3 kN itki, 10 s yanma, '
        '30 bar oda basıncı. Regresyon katsayıları uygulamanın HTPB/N2O '
        'varsayılanıdır (Doran et al., AIAA 2007-5352). / Educational '
        'example: N2O/HTPB hybrid motor, 3 kN thrust, 10 s burn, 30 bar '
        'chamber pressure. Regression coefficients are the application '
        'defaults for HTPB/N2O (Doran et al., AIAA 2007-5352).')

    hybrid_fields = {
        # Motor kimliği
        'motor_name': NAMES['hybrid'],
        'motor_description': hybrid_desc,
        # Ortam: tek irtifa (deniz seviyesi)
        'single_pressure': 1.013,
        # Tasarım noktası
        'thrust': 3000.0,
        'burn_time': 10.0,
        'of_ratio': 7.0,
        'chamber_pressure': 30.0,
        'tank_pressure': 55.0,
        # Geometri / lüle: 0 = otomatik optimum genişleme oranı
        'l_star': 1.0,
        'expansion_ratio': 0,
        'nozzle_type': 'conical',
        'combustion_type': 'infinite',
        'chamber_diameter_input': 0,
        # Yakıt (advanced.html HTPB varsayılanları; a-n: Doran et al.)
        'fuel_type': 'htpb',
        'fuel_density': 920,
        'regression_a': 3.68e-05,
        'regression_n': 0.555,
        # Oksitleyici (yoğunluk/viskozite: uygulamanın N2O kataloğu @293 K)
        'oxidizer_type': 'n2o',
        'oxidizer_phase': 'liquid',
        'oxidizer_temp': 293,
        'oxidizer_density': _round_maybe(n2o['density'], 1),
        'oxidizer_viscosity': float(n2o['viscosity']),
        # Enjektör (sayfa varsayılanları)
        'injector_type': 'showerhead',
        'target_velocity': 30,
        'hole_diameter_min': 0.3,
        'hole_diameter_max': 2.0,
        'plate_thickness': 3.0,
    }

    solid_desc = (
        'Öğretici örnek: KNDX (KNO3/dekstroz 65/35) katı motor, 75 mm gövde, '
        '3 BATES segmenti, 40 bar tasarım basıncı, L sınıfı. Termokimya ve '
        'yanma hızı uygulamanın merkezi kataloglarından (propellants_db + '
        'Nakka 1999 rejim fitleri). / Educational example: KNDX '
        '(KNO3/dextrose 65/35) solid motor, 75 mm case, 3 BATES segments, '
        '40 bar design pressure, L class. Thermochemistry and burn rate '
        'come from the application catalogues (propellants_db + Nakka 1999 '
        'regime fits).')

    solid_fields = {
        # Yakıt: merkezi katalog (hrma/data/propellants_db.py 'kndx')
        'propellant_name': kndx['name'],
        'density': float(kndx['density']),
        'flame_temp': float(kndx['flame_temperature']),
        'molecular_weight': float(kndx['molecular_weight']),
        'gamma': float(kndx['gamma']),
        'char_velocity': float(kndx['c_star']),
        # Yanma hızı: merkezi rejim fiti, 40 bar'da çözülmüş (sayfadaki
        # preset akışıyla aynı hane sayısı: a 7, n 4)
        'burn_rate_a': _round_maybe(kndx_coeffs['a'], 7),
        'burn_rate_n': _round_maybe(kndx_coeffs['n'], 4),
        'burn_rate_preset': 'kndx',
        # Grain: 3 x BATES, uçlar yanar, dış yüzey inhibitörlü
        'grain_type': 'bates',
        'grain_count': 3,
        'outer_diameter': 75.0,
        'core_diameter': 32.0,
        'grain_length': 360.0,
        'web_thickness': 21.5,
        'grain_gap': 2.0,
        'inhibit_front': False,
        'inhibit_rear': False,
        'inhibit_outer': True,
        # Oda
        'chamber_diameter': 75.0,
        'chamber_pressure': 40.0,
    }

    liquid_desc = (
        'Öğretici örnek: LOX/RP-1 sıvı motor, 25 kN itki, 70 bar oda '
        'basıncı, O/F 2.3, gaz jeneratörü çevrimi, rejeneratif soğutma. / '
        'Educational example: LOX/RP-1 liquid engine, 25 kN thrust, 70 bar '
        'chamber pressure, O/F 2.3, gas-generator cycle, regenerative '
        'cooling.')

    liquid_fields = {
        # Yakıt çifti (liquid.html RP-1/LOX varsayılan yoğunlukları)
        'fuel_type': 'rp1',
        'oxidizer_type': 'lox',
        'fuel_density': 810,
        'oxidizer_density': 1141,
        # O/F
        'mixture_ratio': 2.3,
        'stoichiometric_of': 3.4,
        'of_min': 2.0,
        'of_max': 3.2,
        'combustion_efficiency': 97,
        # Besleme. turbine_inlet_pressure BİLEREK dışarıda: motorun türbin
        # basınç oranı varsayılanıyla karşılaştırılıp her koşuda
        # warn.liquid.turbine_pr_inconsistent üretiyor (öğretici örnekte
        # gereksiz uyarı kartı). throat_diameter dışarıda: çözücünün
        # ÇIKTISIDIR (warn.liquid.throat_diameter_is_output).
        'engine_cycle': 'gas_generator',
        'thrust': 25000,
        'chamber_pressure': 70,
        'feed_pressure': 105,
        # Türbin: genişleme oranı sayfanın kendi varsayılanı (4); jeneratör
        # gazı 900 K — soğutmasız türbin pratiğinin muhafazakar ucu (Sutton
        # & Biblarz Böl. 10). 1000 K + PR 8.5 motor varsayılanları tek
        # kademeli türbinde uç hızı sınırını aşıp uyarı üretiyordu; bu ikili
        # ile koşu uyarısızdır.
        'turbine_expansion_ratio': 4,
        'generator_gas_temp': 900,
        # Enjektör
        'injector_type': 'impinging',
        'injector_pressure_drop': 20,
        'discharge_coefficient': 0.7,
        # Oda. chamber_diameter BİLEREK yok: hazne çapı daralma oranından
        # türetilsin (d_c = d_t·√CR). Eskiden burada 120 mm sabit duruyordu
        # ve çözücüde çap önceliği olduğu için kullanıcının daralma oranı
        # hiçbir sayıyı oynatamıyordu; arayüzde de alan artık varsayılan boş.
        'contraction_ratio': 4,
        'characteristic_length': 1.2,
        'chamber_material': 'inconel_718',
        # Lüle / soğutma (12: deniz seviyesine yakın genişleme)
        'cooling_type': 'regenerative',
        'nozzle_expansion_ratio': 12,
        'nozzle_type': 'bell_80',
        'safety_factor': 2.5,
    }

    return {
        'hybrid': {
            'description': hybrid_desc,
            'fields': hybrid_fields,
            'ui_state': {'environment_tab': 'single',
                         'design_tab': 'thrust_time',
                         'analysis_tab': 'single'},
        },
        'solid': {'description': solid_desc, 'fields': solid_fields},
        'liquid': {'description': liquid_desc, 'fields': liquid_fields},
    }


def results_summary(motor_type, body):
    """Taze hesabın çıktısından project_bar.js ile aynı özet anahtarları."""
    from hrma import __version__

    def put(out, key, value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = round(float(value), 3)

    out = {}
    if motor_type == 'hybrid':
        motor = body['motor']
        put(out, 'thrust_N', motor.get('thrust'))
        put(out, 'isp_s', motor.get('isp'))
        put(out, 'burn_time_s', motor.get('burn_time'))
        put(out, 'chamber_pressure_bar', motor.get('chamber_pressure'))
        put(out, 'total_impulse_Ns', motor.get('total_impulse'))
    elif motor_type == 'solid':
        put(out, 'total_impulse_Ns', body.get('total_impulse'))
        put(out, 'burn_time_s', body.get('burn_time'))
        put(out, 'chamber_pressure_bar', body.get('chamber_pressure'))
        put(out, 'isp_s', body.get('isp_sea_level'))
        put(out, 'peak_thrust_N', body.get('max_thrust'))
    else:
        put(out, 'thrust_N', body.get('thrust'))
        put(out, 'isp_s', body.get('isp_sea_level'))
        put(out, 'isp_vacuum_s', body.get('isp_vacuum'))
        put(out, 'chamber_pressure_bar', body.get('chamber_pressure'))
    out['computed_with_version'] = __version__
    return out


def main():
    from hrma.app import app
    from hrma.utils import projects as store

    client = app.test_client()
    examples = build_examples(client)

    for motor_type in ('hybrid', 'solid', 'liquid'):
        spec = examples[motor_type]
        name = NAMES[motor_type]

        # 1) Örnek gerçekten hesaplanıyor mu? (HTTP 200 şartı)
        payload = calculate_payload(motor_type, spec['fields'])
        resp = client.post(ENDPOINTS[motor_type], json=payload,
                           headers=HEADERS)
        if resp.status_code != 200:
            raise SystemExit(
                f'{name}: {ENDPOINTS[motor_type]} {resp.status_code} — '
                + resp.get_data(as_text=True)[:400])
        body = resp.get_json()
        if 'error' in body:
            raise SystemExit(f'{name}: hesap hatası: {body["error"]}')

        # 2) Belgeyi kur ve uygulamanın kendi deposuyla kaydet
        inputs = {'fields': spec['fields']}
        if spec.get('ui_state'):
            inputs['ui_state'] = spec['ui_state']
        doc = {
            'format': 'hrma-project',
            'format_version': 1,
            'name': name,
            'description': spec['description'],
            'motor_type': motor_type,
            'inputs': inputs,
            'results_summary': results_summary(motor_type, body),
        }
        info = store.save_project(name, doc, overwrite=True)

        # 3) Gidiş-dönüş doğrulaması (bozuk örnek yayınlanamaz)
        loaded, _warnings = store.load_project(name)
        assert loaded['inputs']['fields'] == spec['fields']

        print(f"{name}.hrma  yazıldı (app {info['app_version']})")
        print('  özet:', doc['results_summary'])


if __name__ == '__main__':
    main()
