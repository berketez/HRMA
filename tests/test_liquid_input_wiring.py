"""Sıvı motor form alanlarının bağlanma denetimi — ÇİFT YÖNLÜ bekçi.

Bu projenin en pahalı hata sınıfı ÖLÜ GİRDİ: alan arayüzde var, kullanıcı
değerini giriyor, ama değer çözücüye hiç ulaşmıyor ya da ulaşıp hiçbir şeyi
değiştirmiyor. Ölçülmüş geçmiş: v2.5.2'de sıvı motorun 55 girdisi hiç bağlı
değildi; v2.6.25'te hibritte malzeme/cidar/soğutma termal modele ulaşmıyordu.

Motorun buna karşı bir mekanizması var: ``unwired_inputs()``. Bir alan ya
fiziğe GERÇEKTEN bağlanır ya da bu listeyle "sonuca girmiyor" diye beyan
edilir; sessiz bırakmak yasak. Ne var ki 2026-07-29 denetiminde mekanizmanın
KENDİSİNİN çürüdüğü ölçüldü — en sinsi hata sınıfı, çünkü rozet kullanıcıya
güven veriyor ama yalan söylüyor:

* ``throat_diameter`` "yalnız karşılaştırma için" diye beyan edilirken 781
  çıktı yaprağını sürüklüyordu (kinetik verim korelasyonuna sızıyordu),
* ``contraction_ratio`` hiçbir beyanda yokken tamamen ölüydü (form her koşuda
  oda çapını da gönderiyor, oda çapı önceliği alıyor),
* ``turbine_inlet_pressure`` ve ``fuel_boiling_point`` beyansızken yalnız
  uyarı üretiyordu.

Buradaki iki test bu çürümeyi kalıcı olarak yakalar:

1. Beyan edilen HER alan gerçekten etkisiz olmalı (yankı yolları hariç).
2. Beyan edilmeyen HER form alanı en az bir fiziksel sayıyı oynatmalı.

Ölçüm doğrudan ``/calculate_liquid`` üzerinden yapılır: hata arayüz ile arka
uç ARASINDA da doğabiliyor (v2.6.26'da arka uç okuyor, arayüz göndermiyordu),
motoru doğrudan kurmak o boşluğu göremez.
"""

import copy
import json
import math
import re
from pathlib import Path

import pytest

from hrma.app import app

TEMPLATE = Path(__file__).resolve().parents[1] / 'hrma' / 'templates' / 'liquid.html'

# Uygulama yalnız yerel Host başlığına yanıt veriyor (export enjeksiyon kapısı).
LOCAL_HOST = {'Host': '127.0.0.1:8080'}

# Yaprak karşılaştırma toleransı. Yanıtlar bit düzeyinde deterministik
# (aynı yük iki kez gönderildiğinde 2179 yaprağın hiçbiri oynamıyor —
# ölçüldü), bu yüzden tolerans yalnız kayan nokta gürültüsüne karşıdır.
REL_TOL = 1e-9


# ---------------------------------------------------------------------------
# Taban yük: liquid.html collectAllParameters() ile birebir aynı alan kümesi
# ---------------------------------------------------------------------------
BASE_PAYLOAD = {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox',
    'fuel_density': 810, 'oxidizer_density': 1141,
    'fuel_boiling_point': 500, 'oxidizer_boiling_point': 90.2,
    'fuel_freezing_point': 200, 'oxidizer_freezing_point': 54.4,
    'fuel_viscosity': 0.0012, 'oxidizer_viscosity': 0.00019,
    'fuel_heat_combustion': 43.1, 'fuel_heat_capacity': 2090,
    'fuel_thermal_conductivity': 0.145,
    'mixture_ratio': 2.5, 'stoichiometric_of': 3.4,
    'of_min': 2.0, 'of_max': 3.2,
    'throttling_of_strategy': 'constant', 'combustion_efficiency': 97,
    # v2.6.26 — film soğutma girdisi eklendi (analiz zaten vardı, onu
    # tetikleyecek alan yoktu; 6 çıktı yaprağı her motorda 0,0 kalıyordu).
    'film_cooling_percent': 0,
    'engine_cycle': 'gas_generator',
    'thrust': 10000, 'chamber_pressure': 100, 'feed_pressure': 130,
    'turbopump_efficiency': 75, 'generator_gas_temp': 1000,
    'turbine_inlet_pressure': 150, 'turbine_expansion_ratio': 4,
    'injector_type': 'impinging', 'injector_elements': 100,
    'fuel_injection_velocity': 25, 'oxidizer_injection_velocity': 40,
    'fuel_orifice_diameter': 2.0, 'oxidizer_orifice_diameter': 2.5,
    'injector_pressure_drop': 20, 'discharge_coefficient': 0.7,
    'chamber_diameter': 200, 'characteristic_length': 1.2,
    'contraction_ratio': 4, 'chamber_wall_thickness': 5,
    # v2.6.26: burada 'inconel718' yazıyordu; liquid.html'in seçeneği
    # 'inconel_718'. Motor tanımadığı değeri warn.liquid.option_not_recognised
    # ile reddedip varsayılana düşüyordu, yani bu dosyanın "collectAllParameters
    # ile birebir aynı" iddiası iki alanda YANLIŞTI ve testler farkında olmadan
    # yedek yolu sınıyordu.
    'chamber_material': 'inconel_718', 'chamber_roughness': 3.2,
    'stability_margin': 'medium', 'ignition_system': 'spark',
    'cooling_type': 'regenerative', 'nozzle_expansion_ratio': 50,
    # 'bell' liquid.html'de yok; seçenekler bell_80 / bell_60 (bkz. yukarıdaki not)
    'nozzle_type': 'bell_80', 'throat_diameter': 50,
    'cooling_channels': 80, 'coolant_flow_percent': 100,
    'coolant_inlet_temp': 300, 'max_wall_temp': 800,
    'startup_sequence': 'sequential', 'engine_start_time': 2.0,
    'engine_shutdown_time': 1.5, 'min_throttle': 40,
    'throttle_response': 0.5, 'restart_capability': 'multiple',
    'chill_down_time': 30, 'max_burn_duration': 400,
    'target_thrust_to_weight': 60, 'safety_factor': 2.5,
    'engine_mount': 'gimbal', 'gimbal_range': 8, 'actuator_response': 50,
    'engine_life_cycles': 10, 'vibration_environment': 'high',
    'acoustic_level': 165,
    'altitude_range': 'sea_to_vacuum', 'temp_range_min': 200,
    'temp_range_max': 350, 'storage_duration': 12,
    'contamination_sensitivity': 'medium', 'test_requirements': 'full',
    'ground_support': 'standard', 'hazard_classification': 'class_1_3',
}

# Alan -> (sarsım değeri, ek bağlam). Değerler alanın KABUL ARALIĞI İÇİNDE
# seçildi: aralık dışı bir değer sessizce reddedilip alanı YALANCI ölü
# gösterirdi (ölçülmüş tuzak: ambient_temp x1.5 = 447 K motorun [200,350]
# bandının dışında kalıyor). Bazı alanlar yalnız kendi bağlamında canlıdır;
# ek bağlam o durumda taban yüke uygulanır.
SHAKES = {
    'fuel_type': ('methane', {}),
    'oxidizer_type': ('n2o4', {}),
    'fuel_density': (1000.0, {}),
    'oxidizer_density': (1300.0, {}),
    'fuel_boiling_point': (800.0, {}),
    'oxidizer_boiling_point': (111.0, {}),
    'fuel_freezing_point': (260.0, {}),
    'oxidizer_freezing_point': (60.0, {}),
    'fuel_viscosity': (0.004, {}),
    'oxidizer_viscosity': (0.0009, {}),
    'fuel_heat_combustion': (55.0, {}),
    'fuel_heat_capacity': (3500.0, {}),
    'fuel_thermal_conductivity': (0.40, {}),
    'mixture_ratio': (3.4, {}),
    'stoichiometric_of': (2.1, {}),
    'of_min': (2.6, {}),
    'of_max': (4.4, {}),
    'throttling_of_strategy': ('variable', {}),
    'combustion_efficiency': (88.0, {}),
    # Kabul aralığı 0-30 (yakıt debisinin yüzdesi); %6 tipik bir film payı.
    'film_cooling_percent': (6.0, {}),
    'engine_cycle': ('staged_combustion', {}),
    # Ön yakıcı tipi YALNIZ staged combustion'da gönderilir ve yalnız orada
    # anlamlıdır; kendi bağlamı dışında ölçülürse yalancı ölü çıkar.
    'preburner_type': ('ox_rich', {'engine_cycle': 'staged_combustion',
                                   'preburner_type': 'fuel_rich'}),
    'thrust': (60000.0, {}),
    'chamber_pressure': (160.0, {}),
    'feed_pressure': (260.0, {}),
    'turbopump_efficiency': (55.0, {}),
    'generator_gas_temp': (1600.0, {}),
    'turbine_inlet_pressure': (320.0, {}),
    'turbine_expansion_ratio': (12.0, {}),
    'injector_type': ('pintle', {}),
    'injector_elements': (600.0, {}),
    'fuel_injection_velocity': (90.0, {}),
    'oxidizer_injection_velocity': (120.0, {}),
    'fuel_orifice_diameter': (6.0, {}),
    'oxidizer_orifice_diameter': (7.0, {}),
    'injector_pressure_drop': (45.0, {}),
    'discharge_coefficient': (0.45, {}),
    'chamber_diameter': (120.0, {}),
    'characteristic_length': (2.4, {}),
    'contraction_ratio': (6.0, {}),
    'chamber_wall_thickness': (14.0, {}),
    # Malzeme adı CHAMBER_MATERIAL_MAP anahtarı olmalı; tanınmayan bir ad
    # yalnız 'option_not_recognised' uyarısı üretip alanı ölü gösterirdi.
    'chamber_material': ('copper_c101', {}),
    'chamber_roughness': (25.0, {}),
    'stability_margin': ('high', {}),
    'ignition_system': ('hypergolic', {}),
    'cooling_type': ('ablative', {}),
    'nozzle_expansion_ratio': (14.0, {}),
    'nozzle_type': ('conical', {}),
    'throat_diameter': (95.0, {}),
    'cooling_channels': (220.0, {}),
    'coolant_flow_percent': (45.0, {}),
    'coolant_inlet_temp': (120.0, {}),
    'max_wall_temp': (1200.0, {}),
    'startup_sequence': ('simultaneous', {}),
    'engine_start_time': (6.0, {}),
    'engine_shutdown_time': (5.0, {}),
    # Izgara alt sınırının (%40) ALTINA sarsılır ki gerçek yol
    # sınansın: alt sınır taramaya yeni bir nokta ekliyor mu?
    'min_throttle': (20.0, {}),
    'throttle_response': (3.0, {}),
    'restart_capability': ('single', {}),
    'chill_down_time': (120.0, {}),
    'max_burn_duration': (90.0, {}),
    'target_thrust_to_weight': (140.0, {}),
    'safety_factor': (1.6, {}),
    'engine_mount': ('fixed', {}),
    'gimbal_range': (15.0, {}),
    'actuator_response': (90.0, {}),
    'engine_life_cycles': (900.0, {}),
    'vibration_environment': ('low', {}),
    'acoustic_level': (140.0, {}),
    'altitude_range': ('vacuum_only', {}),
    'temp_range_min': (240.0, {}),
    'temp_range_max': (310.0, {}),
    'storage_duration': (60.0, {}),
    'contamination_sensitivity': ('high', {}),
    'test_requirements': ('minimal', {}),
    'ground_support': ('minimal', {}),
    'hazard_classification': ('class_1_1', {}),
}

# ---------------------------------------------------------------------------
# "Kendi girdin hakkında rapor" düğümleri
# ---------------------------------------------------------------------------
# Beyan edilmiş bir alan bu düğümleri oynatabilir: bunlar zaten "değeriniz
# kullanılmadı" demenin biçimleridir, fiziksel bir büyüklük değildir. Örnek:
# kullanıcı 120 m/s enjeksiyon hızı girince motor kendi hesapladığı 41 m/s ile
# karşılaştırıp uyarı üretir -> input_warnings listesi kayar. Bu MEŞRUDUR.
ECHO_PREFIXES = ('$.input_warnings', '$.unwired_inputs', '$.warnings')

# Alana özel izinler. Blanket kural DEĞİL: her satır adıyla ve gerekçesiyle
# yazılır ki bir gün gerçek bir sızıntı buraya sessizce eklenmesin.
FIELD_ECHO_ALLOWANCES = {
    # v2.6.26 — min_throttle ARTIK FİZİĞE BAĞLI, bu izin KALDIRILDI.
    #
    # Eski gerekçe şuydu: "kısma haritasının noktaları SABİT bir ızgarada
    # hesaplanır, alt sınır yalnız hazır noktaları süzer". Ölçüm bunun bir
    # KUSUR olduğunu gösterdi: kullanıcı min_throttle=%20 girdiğinde
    # "en derin kısmada chug riski" hükmü hâlâ %40'ta veriliyordu — yani
    # kullanıcının sorduğu noktada hiç bakılmıyordu.
    #
    # Artık kullanıcının alt sınırı ızgaranın altındaysa taramaya EKLENİYOR
    # (liquid_rocket_engine.py::solve_throttle_map). Ölçüldü:
    #   min_throttle=20 -> noktalar [0.20, 0.40, 0.55, 0.70, 0.85, 1.00]
    #   min_throttle=10 -> noktalar [0.10, 0.40, ...]
    # Bu yüzden alan `unwired_inputs()` beyanından da çıkarıldı.
}


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _leaves(obj, prefix='$'):
    """Yanıt ağacını {yol: skaler} sözlüğüne düzleştirir."""
    out = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.update(_leaves(value, '%s.%s' % (prefix, key)))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            out.update(_leaves(value, '%s[%d]' % (prefix, index)))
    else:
        out[prefix] = obj
    return out


def _same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if math.isnan(float(a)) and math.isnan(float(b)):
            return True
        return math.isclose(float(a), float(b), rel_tol=REL_TOL, abs_tol=0.0)
    return a == b


def _changed_leaves(before, after):
    changed = []
    for path in sorted(set(before) | set(after)):
        if path not in before or path not in after:
            changed.append(path)
        elif not _same(before[path], after[path]):
            changed.append(path)
    return changed


def _calculate(client, payload):
    response = client.post('/calculate_liquid', json=payload,
                           headers=LOCAL_HOST)
    assert response.status_code == 200, (
        'çözücü %s döndü: %s'
        % (response.status_code, response.get_data(as_text=True)[:300]))
    body = response.get_json()
    assert not body.get('error'), body.get('error')
    return body


def _shake(client, field):
    """Alanı sarsar; (fiziksel değişen yapraklar, yankı yaprakları) döner."""
    value, extra = SHAKES[field]
    before_payload = copy.deepcopy(BASE_PAYLOAD)
    before_payload.update(extra)
    after_payload = copy.deepcopy(before_payload)
    after_payload[field] = value

    before = _leaves(_calculate(client, before_payload))
    after = _leaves(_calculate(client, after_payload))

    allowed = ECHO_PREFIXES + FIELD_ECHO_ALLOWANCES.get(field, ())
    physical, echo = [], []
    for path in _changed_leaves(before, after):
        (echo if path.startswith(allowed) else physical).append(path)
    return physical, echo


@pytest.fixture(scope='module')
def client():
    return app.test_client()


@pytest.fixture(scope='module')
def declared(client):
    """Motorun taban koşudaki beyanı: {alan: kategori}."""
    result = _calculate(client, copy.deepcopy(BASE_PAYLOAD))
    mapping = {}
    for category, fields in result['unwired_inputs'].items():
        for field in fields:
            mapping[field] = category
    return mapping


def _collector_fields():
    """liquid.html'in /calculate_liquid'e gönderdiği alan adları."""
    html = TEMPLATE.read_text(encoding='utf-8')
    # Gövde ya doğrudan `return {` ile ya da bir değişkene atanarak
    # (`const params = {`) kurulur; ikincisi koşullu alan eklemeye izin verir.
    block = re.search(r'function collectAllParameters\(\)\s*\{\s*'
                      r'(?:return|(?:const|let|var)\s+\w+\s*=)\s*\{'
                      r'(.*?)\n\s*\};', html, re.S)
    assert block, 'collectAllParameters() gövdesi bulunamadı'
    alanlar = re.findall(r'^\s+([A-Za-z_][A-Za-z_0-9]*)\s*:', block.group(1), re.M)
    # KOŞULLU eklenen alanlar: `params.chamber_diameter = ...`. Bunlar sözlük
    # gövdesinde görünmez ama forma aittir ve gönderilirler. chamber_diameter
    # tam olarak böyle: boş bırakılırsa gönderilmez ki daralma oranı hazne
    # çapını belirleyebilsin.
    fn_bas = html.find('function collectAllParameters()')
    fn_son = html.find('\n        }', fn_bas)
    govde = html[fn_bas:fn_son if fn_son > 0 else len(html)]
    alanlar += re.findall(r'^\s+params\.([A-Za-z_][A-Za-z_0-9]*)\s*=',
                          govde, re.M)
    return sorted(set(alanlar))


COLLECTED_FIELDS = _collector_fields()


# ---------------------------------------------------------------------------
# 0) Ölçüm zeminini koru
# ---------------------------------------------------------------------------
def test_shake_table_covers_every_field_the_form_sends():
    """Forma yeni alan eklenirse bu test kırmızı olur — sessizce kaçamaz.

    Bekçinin en kritik parçası bu: sarsım tablosu formdan geri kalırsa yeni
    alan hiç ölçülmez ve ölü doğabilir.
    """
    missing = sorted(set(COLLECTED_FIELDS) - set(SHAKES))
    assert not missing, (
        'liquid.html şu alanları gönderiyor ama sarsım tablosunda yok: %s '
        '— kabul aralığı İÇİNDE bir değer ekleyin' % missing)
    stale = sorted(set(SHAKES) - set(COLLECTED_FIELDS))
    assert not stale, ('sarsım tablosunda formda olmayan alanlar var: %s'
                       % stale)
    # Koşullu gönderilen alan (preburner_type) dışında taban yük formla eş.
    conditional = {'preburner_type'}
    assert set(BASE_PAYLOAD) == set(COLLECTED_FIELDS) - conditional


def test_response_is_deterministic(client):
    """Sarsım ölçümü ancak yanıt deterministikse anlam taşır."""
    first = _leaves(_calculate(client, copy.deepcopy(BASE_PAYLOAD)))
    second = _leaves(_calculate(client, copy.deepcopy(BASE_PAYLOAD)))
    assert _changed_leaves(first, second) == []


# ---------------------------------------------------------------------------
# 1) Her alan BEYANINA uymalı
#
# Bu eskiden İKİ ayrı parametrik testti: biri yalnız beyan edilen alanları
# sınıyor, öbürü yalnız beyansızları; her alan birinde çalışıp diğerinde
# `pytest.skip` alıyordu. Sonuç: 76 alan -> 76 skip ve her alan için İKİ kez
# sarsma isteği. Kapsam aynı kalacak biçimde tek teste indirildi — skip yok,
# istek sayısı yarıya indi, kural tek yerde okunuyor.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('field', sorted(SHAKES))
def test_field_matches_its_declaration(client, declared, field):
    """Alan ya beyanına uyar ya fiziğe bağlıdır; üçüncü seçenek yok.

    - Beyan edilmişse ('bu değeriniz kullanılmıyor' rozeti): gerçekten hiçbir
      fiziksel yaprağı oynatmamalı. Rozet kullanıcıya güven veriyor; yalan
      söylerse kullanıcı Inconel seçip çelik sonucu görür ve bunu anlamasının
      hiçbir yolu olmaz.
    - Beyansızsa: en az bir fiziksel sayıyı oynatmalı. Sessizce ölü kalmak
      yasak — alan ya fiziğe bağlanır ya `unwired_inputs()` ile bildirilir.
    """
    physical, echo = _shake(client, field)
    if field in declared:
        assert not physical, (
            "%s '%s' diye beyan edilmiş ama %d fiziksel yaprağı oynatıyor: %s"
            % (field, declared[field], len(physical), physical[:10]))
    else:
        assert physical, (
            '%s hiçbir beyanda yok ama sonucu da değiştirmiyor (yankı yaprağı: '
            '%d). Ya fiziğe bağlayın ya unwired_inputs() ile bildirin.'
            % (field, len(echo)))


# ---------------------------------------------------------------------------
# 3) Ölçülmüş çürümelere karşı hedefli bekçiler
# ---------------------------------------------------------------------------
def test_throat_diameter_stays_an_output(client):
    """Kullanıcının boğaz çapı çözümü SÜRÜKLEMEMELİ.

    Boğaz alanı serbest değişken değildir: verilen itki ve oda basıncında
    A_t = ṁ·c*/(P_c·C_D) kütle dengesinden çıkar. Kullanıcının değeri eskiden
    kinetik verim korelasyonuna sızıyordu; kinetik kayıp RAPORLANANDAN başka
    bir motorun boğazıyla hesaplanıyor (95 mm girdi -> 30.7 mm geometri) ve
    781 yaprak kayıyordu.
    """
    physical, _ = _shake(client, 'throat_diameter')
    assert not physical, ('boğaz çapı yine çözümü sürüklüyor: %s'
                          % physical[:10])

    # Geometri motorun kendi kütle dengesinden gelmeli, girdiden değil.
    payload = copy.deepcopy(BASE_PAYLOAD)
    payload['throat_diameter'] = 95.0
    result = _calculate(client, payload)
    assert result['throat_diameter'] * 1000.0 == pytest.approx(30.7, abs=1.0)

    # Ve kullanıcı bunu ÖĞRENMELİ: alan hem beyan edilir hem uyarı üretir.
    assert 'throat_diameter' in result['unwired_inputs'][
        'reported_for_comparison']
    codes = {w.get('code') for w in result['input_warnings']
             if isinstance(w, dict)}
    assert 'warn.liquid.throat_diameter_is_output' in codes


def test_contraction_ratio_declaration_follows_the_real_precedence(client):
    """Daralma oranı: oda çapı öncelik aldığında beyan edilir, almadığında hayır.

    Form her koşuda oda çapını da gönderdiğinden alan pratikte ölüydü ve
    hiçbir beyanda yoktu. Koşulsuz 'ölü' demek de yanlış olurdu: oda çapı
    gönderilmediğinde (API, proje yüklemesi) daralma oranı gerçekten çalışır.
    """
    with_diameter = _calculate(client, copy.deepcopy(BASE_PAYLOAD))
    assert 'contraction_ratio' in with_diameter['unwired_inputs'][
        'reported_for_comparison'], 'maskeli ölü alan yine sessiz'
    codes = {w.get('code') for w in with_diameter['input_warnings']
             if isinstance(w, dict)}
    assert 'warn.liquid.chamber_diameter_overrides_contraction' in codes
    # Karşılaştırılacak çözücü değeri yanıtta bulunmalı (arayüz onu basıyor).
    assert with_diameter['nozzle_angles']['contraction_ratio'] > 0

    payload = copy.deepcopy(BASE_PAYLOAD)
    payload.pop('chamber_diameter')
    without = _calculate(client, payload)
    assert 'contraction_ratio' not in without['unwired_inputs'][
        'reported_for_comparison'], 'canlı alan ölü diye işaretlendi'

    shaken = copy.deepcopy(payload)
    shaken['contraction_ratio'] = 6.0
    changed = _changed_leaves(_leaves(without), _leaves(_calculate(client, shaken)))
    assert changed, 'oda çapı yokken daralma oranı da ölü'


def test_chamber_diameter_out_of_band_does_not_claim_false_precedence(client):
    """Reddedilen oda çapı 'öncelik aldım' diye duyurulmamalı.

    Aralık dışı bir oda çapı geri çevrilip sıra daralma oranına geçer; eski
    kod uyarıyı girdi katmanında koşulsuz basıyordu ve kullanıcıya
    gerçekleşmeyen bir öncelik bildiriliyordu.
    """
    payload = copy.deepcopy(BASE_PAYLOAD)
    payload['chamber_diameter'] = 4000.0   # CR ~ 17000, bandın çok dışında
    result = _calculate(client, payload)
    codes = {w.get('code') for w in result['input_warnings']
             if isinstance(w, dict)}
    assert 'warn.liquid.contraction_ratio_out_of_band' in codes
    assert 'warn.liquid.chamber_diameter_overrides_contraction' not in codes
    assert 'contraction_ratio' not in result['unwired_inputs'][
        'reported_for_comparison']


def test_turbine_inlet_pressure_reports_a_comparable_solver_value(client):
    """Beyan edilen türbin giriş basıncının karşılaştırma değeri yayımlanmalı.

    Kullanıcı kendi girdisini çözücününkiyle kıyaslayabilsin diye motor, ima
    ettiği giriş basıncını çıktıya koyar. O değer ÇEVRİM GÜÇ DENGESİNİN basınç
    merdiveninden gelir.

    v2.6.26 — bu test eskiden ``implied == PR · P_atmosfer`` diyordu ve
    kusurun kendisini sözleşmeye çeviriyordu: aynı koşuda çevrim çözücüsü
    105,04 bar üretirken yaprak 4,05 bar diyor, arayüz de kullanıcının 150
    bar'lık girdisini o 4 bar ile kıyaslıyordu. Bir gaz jeneratörü türbini,
    100 bar'a basan pompaları 4 bar'lık gazla süremez. Ölçüt artık çözücünün
    kendi değeri.
    """
    result = _calculate(client, copy.deepcopy(BASE_PAYLOAD))
    assert 'turbine_inlet_pressure' in result['unwired_inputs'][
        'reported_for_comparison']
    turbine = result['detailed_feed_system']['turbopump_analysis']['turbine']
    implied = turbine['inlet_pressure_implied_bar']

    solved = (result['detailed_feed_system']['engine_cycle_solution']
              ['shafts'][0]['turbine']['inlet_pressure_bar'])
    assert implied == pytest.approx(solved), (
        'yayımlanan giriş basıncı çevrim çözümüyle aynı olmalı: '
        f'{implied} != {solved}')
    # Açık çevrimde türbin, odaya basan pompaları sürer; girişi oda
    # basıncının altına düşerse güç dengesi fiziksel değildir.
    assert implied > result['chamber_pressure']


def test_ui_can_show_a_solver_value_for_every_comparison_field(client):
    """Her 'karşılaştırma amaçlı' alanın arayüzde bir çözücü karşılığı olmalı.

    Rozet "çözücü kendi değerini hesaplıyor" diyorsa kullanıcı O DEĞERİ
    görebilmeli; eşlemesi olmayan alan 'Solver value not reported' yazısına
    düşer ve beyan yarım kalır.
    """
    html = TEMPLATE.read_text(encoding='utf-8')
    block = re.search(r'var COMPARISON_SOLVER_VALUE = \{(.*?)\n        \};',
                      html, re.S)
    assert block, 'COMPARISON_SOLVER_VALUE tablosu bulunamadı'
    mapped = set(re.findall(r'^\s{12}([A-Za-z_][A-Za-z_0-9]*)\s*:',
                            block.group(1), re.M))
    result = _calculate(client, copy.deepcopy(BASE_PAYLOAD))
    for field in result['unwired_inputs']['reported_for_comparison']:
        assert field in mapped, (
            '%s karşılaştırma alanı olarak beyan ediliyor ama liquid.html '
            'çözücü değerini nereden okuyacağını bilmiyor' % field)


def test_declaration_is_readable_without_a_solved_engine():
    """unwired_inputs() motor kurulmadan da çağrılabilmeli.

    tests/test_liquid_unwired_ui.py listeyi ``unwired_inputs(None)`` ile
    okuyor (CEA kurulumu pahalı). Koşullu dallar bu yüzden yalnız getattr ile
    durum sorgulamalı, metot çağırmamalı.
    """
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    declared = LiquidRocketEngine.unwired_inputs(None)
    assert set(declared) == {'informational', 'transient_not_modelled',
                             'reported_for_comparison'}
    # Durum bilinmiyorken koşullu alan beyan EDİLMEZ (yalan söylemektense sus).
    assert 'contraction_ratio' not in declared['reported_for_comparison']
    assert json.dumps(declared)  # serileştirilebilir olmalı (yanıta giriyor)
