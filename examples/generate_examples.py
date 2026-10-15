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
    python3 examples/generate_examples.py            # üç örnek
    python3 examples/generate_examples.py hybrid     # yalnız hibrit
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

from tests.support.form_defaults import (         # noqa: E402
    sayisal_varsayilanlar)
from tests.test_example_projects import (          # noqa: E402
    ENDPOINTS, HEADERS, NAMES, calculate_payload)

#: KATI örnekte ``.hrma``nın TAŞIMASI ZORUNLU form varsayılanları.
#:
#: ÖH D35 · OH-ON-03 (ÖLÇÜLDÜ 22 Eylül 2026,
#: ``docs/scofield/raw/OH/D35/onemli-kati-cad/a1/10_once.json`` A bölümü).
#: Örnek yüklenip "Hesapla"ya basıldığında sayfa, dosyada OLMAYAN 51 sayı
#: alanını kendi ``value=`` varsayılanıyla gönderiyordu; yayımlanan sayı
#: proje şeridindekinden sapıyordu::
#:
#:     yaprak            API yolu (.hrma)    FORM yolu       fark
#:     isp_sea_level        140,109 s         125,401 s     -%10,4974
#:     total_impulse       3306,767 N·s      2959,642 N·s   -%10,4974
#:     c_star               915,900 m/s       870,105 m/s    -%5,0000
#:     max_thrust          1641,901 N        1499,272 N      -%8,6868
#:
#: ``11_once_duyarlilik.json``: o 51 alandan yaprağı oynatan TAM OLARAK
#: aşağıdaki altısıdır; altısı eklendiğinde FORM yolu API yoluyla BİT-AYNI
#: olur (``asgari_form_ile_AYNI_MI: true``). Liste ÖLÇÜMLE kurulmuştur,
#: varsayımla değil; yeni bir alan duyarlı hâle gelirse bekçi
#: (``test_ornek_API_ve_FORM_yollari_ayni_sayiyi_verir``) onu yakalar.
#:
#: DEĞERLER BURADA YAZILMAZ (Doktrin 4): ``solid.html``in kendi ``value=``
#: öznitelikleri ``tests.support.form_defaults`` ile okunur.
KATI_ORNEGE_TASINAN_FORM_ALANLARI = (
    'combustion_efficiency',   # c* verimi   (solid.html:1289)
    'nozzle_efficiency',       # lüle verimi (solid.html:1198)
    'cf_efficiency',           # Cf verimi   (solid.html:1299)
    'kinetic_efficiency',      # kinetik verim (solid.html:1329)
    'erosion_factor',          # boğaz erozyonu
    'initial_temp',            # itici başlangıç sıcaklığı [K]
)


from hrma.engines.hybrid_rocket_engine import (    # noqa: E402
    HYBRID_CHAMBER_MATERIAL_DEFAULT, TANK_TEMPERATURE_DEFAULT_K)

#: Hibrit örneğin N2O tank sıcaklığı [K]. Özellik ucu, ``oxidizer_temp``
#: alanı ve tank basıncının doyma değeri AYNI sıcaklıktan okunur (tek kaynak).
#: ÖH D37 A2 hibrit · 10. tur (HB9 devir 45): eskiden ``293`` literaliydi;
#: motorun ve ucun TEK varsayılanı ``TANK_TEMPERATURE_DEFAULT_K`` (293,15 K)
#: içe aktarılır — örnek = ucun varsayılan durumu.
HIBRIT_TANK_SICAKLIGI_K = TANK_TEMPERATURE_DEFAULT_K

#: Form alanı ``tank_pressure``in adımı 0,1 bar (advanced.html ``step="0.1"``):
#: doyma basıncı bu haneye yuvarlanır.
TANK_BASINCI_ONDALIK = 1


def _round_maybe(value, digits):
    return round(float(value), digits)


def n2o_doyma_basinci_bar(sicaklik_k):
    """Kendinden basınçlı N2O tankının basıncı = P_sat(T) [bar].

    ÖH D37 A2 hibrit · 9. tur (7. tur Devir 33). Örnek eskiden 55 bar
    taşıyordu (kaynaksız); 293 K'de doyma basıncı ≈ 50,4 bar olduğu için
    (10. turdan beri tank sıcaklığı 293,15 K: ≈ 50,5 bar)
    API'de ``warn.hybrid.tank_pressure_not_used`` uyarısını alıyordu (YB-04:
    devre P_sat(T_tank) kullanır, istekteki değer devreye girmez). Değer
    uydurulmaz: enjektör devresinin KULLANDIĞI doyma tablosundan okunur
    (``hrma.analysis.tank_blowdown.N2OSaturation(use_coolprop=False)`` —
    ``hrma/engines/injector_design.py::_SAT`` ile aynı yapılandırma; tablo
    CoolProp 6.8.0 / Lemmon & Span 2006 EOS'tan üretilmiştir). Bağımsız
    kâhin (CoolProp ``PropsSI``) bekçide: ``tests/test_d37_hibrit_f1.py``.
    """
    from hrma.analysis.tank_blowdown import N2OSaturation
    from hrma.constants import PA_PER_BAR
    return float(N2OSaturation(use_coolprop=False).psat(float(sicaklik_k))
                 / PA_PER_BAR)


def sayisal_varsayilanlari_secili(sayfa, adlar):
    """Adı verilen alanların ŞABLON varsayılanları (eksikse hata).

    Alan sayfadan kalkarsa ya da ``value=`` özniteliği silinirse örnek
    SESSİZCE eski sayıyla üretilmesin diye eksiklik burada patlar.
    """
    tum = sayisal_varsayilanlar(sayfa)
    eksik = [ad for ad in adlar if ad not in tum]
    assert not eksik, (
        f'{sayfa} sablonunda su alanlarin sayisal varsayilani yok: {eksik}; '
        'alan kaldirildiysa KATI_ORNEGE_TASINAN_FORM_ALANLARI guncellenmeli')
    return {ad: tum[ad] for ad in adlar}


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
                       json={'oxidizer_type': 'n2o',
                             'temperature': HIBRIT_TANK_SICAKLIGI_K},
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
        # Kendinden basınçlı N2O: tank basıncı = P_sat(T_tank) (Devir 33)
        'tank_pressure': _round_maybe(
            n2o_doyma_basinci_bar(HIBRIT_TANK_SICAKLIGI_K),
            TANK_BASINCI_ONDALIK),
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
        # Oksitleyici (yoğunluk/viskozite: uygulamanın N2O kataloğu @T_tank)
        'oxidizer_type': 'n2o',
        'oxidizer_phase': 'liquid',
        'oxidizer_temp': HIBRIT_TANK_SICAKLIGI_K,
        'oxidizer_density': _round_maybe(n2o['density'], 1),
        'oxidizer_viscosity': float(n2o['viscosity']),
        # Enjektör (sayfa varsayılanları)
        'injector_type': 'showerhead',
        'target_velocity': 30,
        'hole_diameter_min': 0.3,
        'hole_diameter_max': 2.0,
        'plate_thickness': 3.0,
        # Kamara malzemesi: formun seçili seçeneği = ucun TEK varsayılanı
        # (10. tur). Örnek alanı AÇIKÇA taşır → yüklenince proje dosyası
        # damgasıyla gider; örnek = form yolu.
        'chamber_material': HYBRID_CHAMBER_MATERIAL_DEFAULT,
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
    # Form varsayılanları (OH-ON-03): örnek yüklenip Hesapla'ya basıldığında
    # sayfanın dolduracağı DUYARLI alanlar dosyada da taşınır, yoksa proje
    # şeridindeki sayı ile hesabın sayısı ayrışır. Değerler sayfanın KENDİ
    # ``value=`` özniteliklerinden okunur — burada ikinci kez yazılmaz.
    _solid_form_varsayilanlari = sayisal_varsayilanlari_secili(
        'solid', KATI_ORNEGE_TASINAN_FORM_ALANLARI)
    solid_fields.update(_solid_form_varsayilanlari)

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


def main(secilen=None):
    """Örnekleri üret; ``secilen`` verilirse YALNIZ o motor türleri yazılır.

    9. tur (Devir 33): bir örneğin girdisi düzeltildiğinde öbür örnekler
    yeniden kaydedilmez (damga ``created_at`` / ``app_version`` değişmesin,
    md5 aynı kalsın). Tanınmayan tür adı sessizce yutulmaz.
    """
    from hrma.app import app
    from hrma.utils import projects as store

    turler = ('hybrid', 'solid', 'liquid')
    if secilen:
        bilinmeyen = [t for t in secilen if t not in turler]
        if bilinmeyen:
            raise SystemExit(f'bilinmeyen motor türü: {bilinmeyen}; '
                             f'geçerli: {list(turler)}')
        turler = tuple(t for t in turler if t in secilen)

    client = app.test_client()
    examples = build_examples(client)

    for motor_type in turler:
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
    main(sys.argv[1:])
