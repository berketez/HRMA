"""Örnek .hrma projelerini GERÇEK SAYFADAN üretir (v3.0.5, V301/ÖRNEK).

Neden sayfa (ÖLÇÜLDÜ 27 Eki 2026, V301/KABUL + V301/UÇUŞ raporları): örnekler
eskiden şablon varsayılanlarından kurulan bir aynayla (``calculate_payload`` +
``tests/support/form_defaults.form_yuku``) üretiliyordu. Ayna, sayfanın
Hesapla'da gönderdiği gövdeden üç örneğin üçünde de sapıyordu (katı 16, sıvı 7,
hibrit 28 alan; hibritte ``calculate_trajectory`` ayna False ⟷ sayfa True).
Kullanıcıya görünen sonuçları:

  * proje şeridi bayat Isp gösteriyordu (hibrit 236,0 s ⟷ Hesapla 210,1 s);
  * Fırlatma Sahası örnek DOSYADAN sayfadakinden farklı motor uçuruyordu
    (katı kuru kütle 3,090 ⟷ 3,734 kg, çap 83 ⟷ 89 mm), çünkü dosya sayfanın
    gönderdiği alanların bir kısmını taşımıyordu.

Ayna kaldırıldı; tek kaynak sayfanın kendisidir:

  1. TOHUM — tasarımı tanımlayan alanlar uygulamanın kataloglarından kurulur
     (``build_examples``; sayı uydurulmaz) ve KOPYA proje dizinine
     ``hrma/utils/projects.py::save_project`` ile yazılır.
  2. SAYFA — kendi sunucusu (``HRMA_PROJECTS_DIR`` = kopya dizin) ve gerçek
     tarayıcı (Playwright, headless, 3B kapalı) ile örnek ``?project=<ad>``
     olarak açılır, Hesapla düğmesinin çağırdığı sayfa işlevi koşar ve
     tarayıcının hesap ucuna gönderdiği POST gövdesi kaydedilir.
  3. KAYIT — proje şeridinin KENDİ belgesi (``HRMAProjectBar._buildPayload``)
     şeridin Kaydet isteğiyle (``POST /api/projects/save``, overwrite)
     yazılır. ``inputs.fields`` sayfanın bütün alanlarını, ``results_summary``
     sayfanın kendi özetini (``computed_with_version`` dahil) taşır.
  4. SABİT NOKTA — kaydedilen belge yeniden açılıp Hesapla'ya basılır; gövde
     ve belge bir önceki turla AYNI olana dek (en çok ``TUR_SINIRI`` tur).
     Örnek dosya = sabit noktadaki belge; hasat = o belgenin gövdesi.
  5. DENETİM — aynı gövde test istemcisiyle de koşulur (HTTP 200) ve özetin
     her sayısı yanıttaki karşılığıyla BİT-AYNI olmalıdır
     (``tests/test_example_projects.ozet_referansi``: project_bar.js eşlemesi).
  6. YAZIM — .hrma bayt bayt ``examples/``e kopyalanır, karması dağıtılmış
     sürümler listesine eklenir, gövde ``tests/support/kabul_sayfa_yukleri.py``
     hasadına yazılır. ``tests/test_example_projects.py`` ve
     ``tests/test_v301_kabul.py`` bu gövdeyle koşar (test ve üretici aynı
     yol); hasadın bugünkü sayfayla aynılığını
     ``tests/test_v301_kabul_ui.py::test_u1_hesap_govdesi_hasatla_ayni`` bekler.

Yan etki yok: üretici ``examples/``i proje dizini olarak KULLANMAZ (ürün orada
``.seeded_v1`` / ``.examples_refresh.json`` damgası yazardı). Kopya dizin
``HRMA_ORNEK_CALISMA`` altında (verilmezse sistemin geçici dizininde) açılır.

Kullanım (depo kökünden; Playwright + Chrome for Testing gerekir):
    python3 examples/generate_examples.py            # üç örnek
    python3 examples/generate_examples.py hybrid     # yalnız hibrit
Ortam: ``HRMA_ORNEK_PORT`` (sunucu portu, varsayılan 8821),
``HRMA_ORNEK_CALISMA`` (kopya proje dizini ve sunucu günlüğünün kökü).
"""

import copy
import datetime
import hashlib
import json
import os
import pathlib
import pprint
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = EXAMPLES_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from tests.support.form_defaults import (         # noqa: E402
    sayisal_varsayilanlar)
from tests.test_example_projects import (          # noqa: E402
    ENDPOINTS, HEADERS, NAMES, ozet_referansi)

#: KATI örnekte ``.hrma``nın TAŞIMASI ZORUNLU form varsayılanları.
#:
#: ÖH D35 · OH-ON-03 (ÖLÇÜLDÜ 22 Eylül 2026,
#: ``docs/scofield/raw/OH/D35/onemli-kati-cad/a1/10_once.json`` A bölümü):
#: dosyada OLMAYAN alanlar sayfanın ``value=`` varsayılanıyla gidiyor ve
#: yayımlanan sayıyı oynatıyordu (Isp 140,109 ⟷ 125,401 s). v3.0.5'ten beri
#: örnek dosya sayfanın BÜTÜN alanlarını taşır (proje şeridinin belgesi); bu
#: liste tohumda da açıkça bulunur ve ``tests/test_d35_onemli_kati_cad_a1.py``
#: adlarını sınar. DEĞERLER BURADA YAZILMAZ (Doktrin 4): ``solid.html``in kendi
#: ``value=`` öznitelikleri ``tests.support.form_defaults`` ile okunur.
KATI_ORNEGE_TASINAN_FORM_ALANLARI = (
    'combustion_efficiency',   # c* verimi
    'nozzle_efficiency',       # lüle verimi
    'cf_efficiency',           # Cf verimi
    'kinetic_efficiency',      # kinetik verim
    'initial_temp',            # itici başlangıç sıcaklığı [K]
)


from hrma.engines.hybrid_rocket_engine import (    # noqa: E402
    HYBRID_CHAMBER_MATERIAL_DEFAULT, TANK_TEMPERATURE_DEFAULT_K)

#: Hibrit örneğin N2O tank sıcaklığı [K]. Özellik ucu, ``oxidizer_temp``
#: alanı ve tank basıncının doyma değeri AYNI sıcaklıktan okunur (tek kaynak).
#: ÖH D37 A2 hibrit · 10. tur (HB9 devir 45): motorun ve ucun TEK varsayılanı
#: ``TANK_TEMPERATURE_DEFAULT_K`` (293,15 K) içe aktarılır.
HIBRIT_TANK_SICAKLIGI_K = TANK_TEMPERATURE_DEFAULT_K

#: Form alanı ``tank_pressure``in adımı 0,1 bar (advanced.html ``step="0.1"``):
#: doyma basıncı bu haneye yuvarlanır.
TANK_BASINCI_ONDALIK = 1

#: Sabit nokta turu üst sınırı. Tur 1 tohumu açar ve sayfanın tam belgesini
#: kaydeder; tur 2 o belgeyi açar ve aynı gövdeyi/belgeyi vermelidir. Sınır
#: aşılırsa sayfa kendi kaydettiği projeyi aynı motor olarak açamıyor demektir
#: (ürün hatası) — örnek YAZILMAZ.
TUR_SINIRI = 3

#: Örnek üretim sunucusunun varsayılan portu (V301 kulvar tablosu: ÖRNEK 8821).
VARSAYILAN_PORT = 8821

#: Hasat dosyası (KABUL'un gerçek sayfa gövdeleri; tests/test_v301_kabul_ui.py
#: ``_hasat_yaz`` ile aynı biçim).
HASAT_YOLU = REPO_ROOT / 'tests' / 'support' / 'kabul_sayfa_yukleri.py'


def _round_maybe(value, digits):
    return round(float(value), digits)


def n2o_doyma_basinci_bar(sicaklik_k):
    """Kendinden basınçlı N2O tankının basıncı = P_sat(T) [bar].

    ÖH D37 A2 hibrit · 9. tur (7. tur Devir 33): değer uydurulmaz, enjektör
    devresinin KULLANDIĞI doyma tablosundan okunur
    (``hrma.analysis.tank_blowdown.N2OSaturation(use_coolprop=False)``;
    tablo CoolProp 6.8.0 / Lemmon & Span 2006 EOS'tan üretilmiştir). Bağımsız
    kâhin (CoolProp ``PropsSI``) bekçide: ``tests/test_d37_hibrit_f1.py``.
    """
    from hrma.analysis.tank_blowdown import N2OSaturation
    from hrma.constants import PA_PER_BAR
    return float(N2OSaturation(use_coolprop=False).psat(float(sicaklik_k))
                 / PA_PER_BAR)


# ---------------------------------------------------------------------------
# Açıklamalar (EN + TR) — GİRDİLERDEN üretilir
# ---------------------------------------------------------------------------
# v3.0.5 (Berke 27 Eki): HRMA eğitim aracı değil, ön tasarım ve analiz
# aracıdır → "Örnek tasarım / Example design". Açıklamadaki her sayı örneğin
# kendi girdisinden biçimlenir; elle yazılmış sayı yoktur (eski sıvı metni
# girdiler değiştikten sonra da "70 bar, O/F 2.3" diyebiliyordu). Adlar
# girdinin değerine bağlı haritalardan gelir; haritada olmayan değer KeyError
# ile üretimi durdurur (açıklama sessizce yanlış kalmaz). Bekçi:
# tests/test_example_projects.py::test_aciklama_girdilerden_uretilmis.

#: Girdi değeri -> açıklamadaki ad (TR, EN).
_ACIKLAMA_ADLARI = {
    'oxidizer_type': {'n2o': ('N2O', 'N2O'), 'lox': ('LOX', 'LOX')},
    'fuel_type': {'htpb': ('HTPB', 'HTPB'), 'rp1': ('RP-1', 'RP-1')},
    'grain_type': {'bates': ('BATES', 'BATES')},
    'grain_support': {'cartridge_loaded': ('kartuş yüklü, gövdeye takılan',
                                           'cartridge-loaded, inserted into the case')},
    'engine_cycle': {'gas_generator': ('gaz jeneratörü çevrimi',
                                       'gas-generator cycle')},
    'cooling_type': {'regenerative': ('rejeneratif soğutma',
                                      'regenerative cooling')},
    'chamber_material': {'cucrzr': ('CuCrZr', 'CuCrZr')},
}

#: Ondalık hane: formun adımıyla aynı (O/F ve cidar kalınlığı 0,1 adımlı).
_ACIKLAMA_ONDALIK = {'of_ratio': 1, 'mixture_ratio': 1,
                     'chamber_wall_thickness': 1}


def _ad(alanlar, alan, dil):
    return _ACIKLAMA_ADLARI[alan][alanlar[alan]][0 if dil == 'tr' else 1]


def _sayi(alanlar, alan, dil, bolen=1.0):
    """Girdinin değeri (gerekirse birim çevrimiyle) TR/EN ondalık ayracıyla."""
    x = float(alanlar[alan]) / bolen
    ond = _ACIKLAMA_ONDALIK.get(alan)
    metin = ('%g' % x) if ond is None else ('%.*f' % (ond, x))
    return metin.replace('.', ',') if dil == 'tr' else metin


def aciklama_kur(motor_type, alanlar):
    """Örneğin açıklaması (TR / EN) — yalnız ``alanlar``dan (dosyanın girdisi)."""
    def s(alan, dil, bolen=1.0):
        return _sayi(alanlar, alan, dil, bolen)

    def a(alan, dil):
        return _ad(alanlar, alan, dil)

    if motor_type == 'hybrid':
        tr = (f"Örnek tasarım: {a('oxidizer_type', 'tr')}/{a('fuel_type', 'tr')} "
              f"hibrit motor, {s('thrust', 'tr', 1000.0)} kN itki, "
              f"{s('burn_time', 'tr')} s yanma, {s('chamber_pressure', 'tr')} bar "
              f"oda basıncı, O/F {s('of_ratio', 'tr')}. Regresyon katsayıları "
              f"sayfanın {a('fuel_type', 'tr')}/{a('oxidizer_type', 'tr')} "
              "varsayılanıdır.")
        en = (f"Example design: {a('oxidizer_type', 'en')}/{a('fuel_type', 'en')} "
              f"hybrid motor, {s('thrust', 'en', 1000.0)} kN thrust, "
              f"{s('burn_time', 'en')} s burn, {s('chamber_pressure', 'en')} bar "
              f"chamber pressure, O/F {s('of_ratio', 'en')}. Regression "
              f"coefficients are the page defaults for "
              f"{a('fuel_type', 'en')}/{a('oxidizer_type', 'en')}.")
    elif motor_type == 'solid':
        ad = alanlar['propellant_name']
        tr = (f"Örnek tasarım: {ad} katı motor, {s('outer_diameter', 'tr')} mm "
              f"yakıt bloğu, {s('grain_count', 'tr')} {a('grain_type', 'tr')} "
              f"segmenti ({a('grain_support', 'tr')}), "
              f"{s('chamber_pressure', 'tr')} bar tasarım basıncı. "
              "Kasa iç çapını HRMA tane çapından türetir ve sonuçta beyan "
              "eder. Termokimya ve yanma hızı uygulamanın merkezi "
              "kataloglarındandır (propellants_db, burn_rate_db rejim "
              "fitleri).")
        en = (f"Example design: {ad} solid motor, {s('outer_diameter', 'en')} mm "
              f"grain, {s('grain_count', 'en')} {a('grain_type', 'en')} segments "
              f"({a('grain_support', 'en')}), "
              f"{s('chamber_pressure', 'en')} bar design pressure. HRMA derives "
              "the case inner diameter from the grain diameter and declares it "
              "in the results. Thermochemistry and burn rate come from the "
              "application catalogues (propellants_db, burn_rate_db regime "
              "fits).")
    elif motor_type == 'liquid':
        # Dış kabuk alanları BOŞ olmalı: metin "HRMA'nın boyutlandırdığı dış
        # kabuk (varsayılan malzeme)" diyor; doluysa metin yanlış olur.
        if alanlar.get('closeout_material') or alanlar.get('closeout_thickness'):
            raise ValueError('sıvı örnek açıklaması dış kabuk alanlarını boş '
                             'varsayıyor; açıklamayı güncelleyin')
        tr = (f"Örnek tasarım: {a('oxidizer_type', 'tr')}/{a('fuel_type', 'tr')} "
              f"sıvı motor, {s('thrust', 'tr', 1000.0)} kN itki, "
              f"{s('chamber_pressure', 'tr')} bar oda basıncı, O/F "
              f"{s('mixture_ratio', 'tr')}, {a('engine_cycle', 'tr')}, "
              f"{a('cooling_type', 'tr')}; iki katmanlı cidar: "
              f"{s('chamber_wall_thickness', 'tr')} mm "
              f"{a('chamber_material', 'tr')} astar + HRMA'nın boyutlandırdığı "
              "dış kabuk (varsayılan malzeme). Yanma süresi "
              f"{s('max_burn_duration', 'tr')} s bir örnek girdisidir (HRMA "
              "seçimi); itici kütlesi, toplam itki ve tanklar bundan "
              "hesaplanır. Bu cidar için bu O/F ve oda basıncı geçerli "
              "noktadır ve dökülme payı dardır: O/F yükseltilirse dökülen "
              "birikimin altındaki yerel cidar sıcaklığı erime sınırını aşar "
              "(kritik).")
        en = (f"Example design: {a('oxidizer_type', 'en')}/{a('fuel_type', 'en')} "
              f"liquid engine, {s('thrust', 'en', 1000.0)} kN thrust, "
              f"{s('chamber_pressure', 'en')} bar chamber pressure, O/F "
              f"{s('mixture_ratio', 'en')}, {a('engine_cycle', 'en')}, "
              f"{a('cooling_type', 'en')}; two-layer wall: "
              f"{s('chamber_wall_thickness', 'en')} mm "
              f"{a('chamber_material', 'en')} liner + a closeout shell sized "
              "by HRMA (default material). The burn time of "
              f"{s('max_burn_duration', 'en')} s is an example input (HRMA "
              "choice); propellant mass, total impulse and tanks are computed "
              "from it. This O/F and chamber pressure are the valid point for "
              "this wall and the spallation margin is narrow: at a higher O/F "
              "the local wall temperature under a spalled deposit exceeds the "
              "melting limit (critical).")
    else:
        raise ValueError(f'bilinmeyen motor türü: {motor_type!r}')
    return tr + ' / ' + en


def sayisal_varsayilanlari_secili(sayfa, adlar):
    """Adı verilen alanların ŞABLON varsayılanları (eksikse hata)."""
    tum = sayisal_varsayilanlar(sayfa)
    eksik = [ad for ad in adlar if ad not in tum]
    assert not eksik, (
        f'{sayfa} sablonunda su alanlarin sayisal varsayilani yok: {eksik}; '
        'alan kaldirildiysa KATI_ORNEGE_TASINAN_FORM_ALANLARI guncellenmeli')
    return {ad: tum[ad] for ad in adlar}


def build_examples(client):
    """Üç örneğin TOHUM belgelerini uygulama kataloglarından kur.

    Tohum yalnız tasarımı tanımlayan alanları taşır; sayfanın geri kalan
    alanları (varsayılanlar, sayfanın itici tablosundan doldurduğu
    yoğunluklar vb.) sayfada açılınca proje şeridinin belgesine girer.
    """
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

    hybrid_fields = {
        # Motor kimliği (motor_description aşağıda GİRDİLERDEN üretilir)
        'motor_name': NAMES['hybrid'],
        # Ortam: tek irtifa (deniz seviyesi)
        'single_pressure': 1.013,
        # Tasarım noktası. O/F 6,0 (v3.0.5, NK-5; ana model kararı): O/F 7'de
        # lüle boğazı 3304 K ile grafitin 3300 K izin sınırını aşıyordu
        # (warn.hybrid.nozzle_material_over_temp, KRİTİK).
        'thrust': 3000.0,
        'burn_time': 10.0,
        'of_ratio': 6.0,
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
    hybrid_desc = aciklama_kur('hybrid', hybrid_fields)
    hybrid_fields['motor_description'] = hybrid_desc

    solid_fields = {
        # Yakıt: merkezi katalog (hrma/data/propellants_db.py 'kndx')
        'propellant_type': 'kndx',
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
        # Grain: 3 x BATES (sayfanın varsayılan tane ailesi), uçlar yanar,
        # dış yüzey inhibitörlü
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
        # V301/S1-6 (28 Eki): KN-şeker BATES segmentleri kalıpta (astar
        # tüpünde) dökülüp gövdeye takılır — kartuş yüklü (NASA SP-8073 §1).
        # Gövdeye yapıştırılmış varsayımı bu tanede kürleme büzülmesini
        # kısıtlıyor ve gerinimi %2,21'e (SF 0,906) çıkarıyordu.
        'grain_support': 'cartridge_loaded',
        # Oda. V301/K-A (22 Eki): ``chamber_diameter`` DAİMA kasa iç
        # çapıdır; gönderilmez — kasa tane + 2·(astar + yalıtım) türetilir ve
        # ``case_bore``da beyan edilir.
        'chamber_pressure': 40.0,
    }
    solid_fields.update(sayisal_varsayilanlari_secili(
        'solid', KATI_ORNEGE_TASINAN_FORM_ALANLARI))
    solid_desc = aciklama_kur('solid', solid_fields)

    liquid_fields = {
        # Yakıt çifti. Yoğunluklar BİLEREK yok (L-D DEVİR 2): sayfa onları
        # itici tablosundan doldurur (tek kaynak); eski 810/1141 kartın
        # yuvarlak sayılarıydı ve kullanıcı girdisi diye taşınıyordu.
        'fuel_type': 'rp1',
        'oxidizer_type': 'lox',
        # O/F (v3.0.5, V301/L-KABUK §7 geçerli noktası). stoichiometric_of
        # formdan kalktı (L-D DEVİR 2).
        'mixture_ratio': 2.0,
        'of_min': 2.0,
        'of_max': 3.2,
        'combustion_efficiency': 97,
        # Besleme. throat_diameter dışarıda: çözücünün ÇIKTISIDIR
        # (warn.liquid.throat_diameter_is_output). feed_pressure gaz
        # jeneratörü çevriminde formda gizli ve gönderilmez (L-A DEVİR 2);
        # değer L-KABUK geçerli noktasıyla aynı tutulur (Pc ile birlikte).
        'engine_cycle': 'gas_generator',
        'thrust': 25000,
        'chamber_pressure': 50,
        'feed_pressure': 75,
        # Türbin: genişleme oranı sayfanın kendi varsayılanı (4); jeneratör
        # gazı 900 K — soğutmasız türbin pratiğinin muhafazakar ucu (Sutton
        # & Biblarz Böl. 10).
        'turbine_expansion_ratio': 4,
        'generator_gas_temp': 900,
        # Enjektör (V301/L-C: 'impinging' → 'unlike_impinging')
        'injector_type': 'unlike_impinging',
        'injector_pressure_drop': 20,
        'discharge_coefficient': 0.7,
        # Oda. chamber_diameter BİLEREK yok: hazne çapı daralma oranından
        # türetilir (d_c = d_t·√CR).
        'contraction_ratio': 4,
        'characteristic_length': 1.2,
        # İki katmanlı cidar (V301/L-KABUK §7): astar CuCrZr 1,0 mm. Dış
        # kabuk alanları BOŞ: varsayılan malzeme, kalınlığı HRMA boyutlandırır.
        # Inconel 718 astar bu noktada geçersizdir (1119 K > 977 K izin,
        # ısıl SF 1,04 < 2,5 — KRİTİK).
        'chamber_material': 'cucrzr',
        'chamber_wall_thickness': 1.0,
        # Lüle / soğutma (12: deniz seviyesine yakın genişleme)
        'cooling_type': 'regenerative',
        'nozzle_expansion_ratio': 12,
        'nozzle_type': 'bell_80',
        'safety_factor': 2.5,
        # Yanma süresi: örnek girdisi (HRMA seçimi, açıklamada beyanlı). Yoksa
        # itici kütlesi / toplam itki / tank / .eng yayımlanmaz ve ısıl,
        # güvenlik panelleri adıyla reddeder (fail-closed, SV-04).
        'max_burn_duration': 30,
    }
    liquid_desc = aciklama_kur('liquid', liquid_fields)

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


def _dagitilmis_karmaya_ekle(dosya_adi):
    """Yeni üretilen örneğin sha256'sını dağıtılmış sürümler listesine ekler.

    v3.0.1 (26 Eki): kullanıcı dizinindeki örnek kopyası bu listedeki bir
    sürümle bayt bayt aynıysa (kullanıcı değiştirmemiş) bir sonraki sürüm
    onu güncel örnekle değiştirir (hrma/utils/projects.py
    refresh_seeded_examples). Liste güncellenmezse bu sürümün örneği
    "kullanıcı değiştirmiş" sanılır ve hiç tazelenmez.
    """
    from hrma.utils import projects as store
    yol = EXAMPLES_DIR / store.SHIPPED_EXAMPLE_HASHES_FILENAME
    belge = json.loads(yol.read_text(encoding='utf-8')) if yol.exists() else {}
    karmalar = belge.setdefault('hashes', {})
    h = hashlib.sha256((EXAMPLES_DIR / dosya_adi).read_bytes()).hexdigest()
    liste = karmalar.setdefault(dosya_adi, [])
    if h not in liste:
        liste.append(h)
        liste.sort()
    yol.write_text(json.dumps(belge, ensure_ascii=False, indent=1) + '\n',
                   encoding='utf-8')


# ---------------------------------------------------------------------------
# Sayfa (gerçek tarayıcı)
# ---------------------------------------------------------------------------
def _calisma_dizini():
    """Kopya proje dizini + sunucu günlüğü için BENZERSİZ kök."""
    kok = os.environ.get('HRMA_ORNEK_CALISMA')
    if kok:
        d = pathlib.Path(kok).expanduser() / (
            'uretim-%d-%d' % (os.getpid(), int(time.time())))
        d.mkdir(parents=True)
        return d
    return pathlib.Path(tempfile.mkdtemp(prefix='hrma-ornek-'))


def _hazir_mi(url):
    try:
        with urllib.request.urlopen(url + '/', timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


class _Sunucu:
    """``python -m hrma.run``: proje deposu kopya dizin, örnek kaynağı YOK
    (tohumlama/tazeleme kopya dizine örnek getirmez, damga yazmaz)."""

    def __init__(self, port, projeler, calisma):
        self.url = 'http://127.0.0.1:%d' % port
        if _hazir_mi(self.url):
            raise SystemExit(f'{self.url} zaten dolu — HRMA_ORNEK_PORT ile '
                             'boş bir port verin (başka sunucuya dokunulmaz)')
        env = dict(os.environ, HRMA_PORT=str(port), BROWSER='echo',
                   HRMA_PROJECTS_DIR=str(projeler),
                   HRMA_EXAMPLES_DIR=str(calisma / 'ornek-kaynagi-yok'),
                   PYTHONDONTWRITEBYTECODE='1')
        for k in ('OMP_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS',
                  'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                  'NUMEXPR_NUM_THREADS'):
            env.setdefault(k, '2')
        env.setdefault('MPLBACKEND', 'Agg')
        self.gunluk = open(calisma / ('sunucu-%d.log' % port), 'w')
        self.proc = subprocess.Popen(
            [sys.executable, '-m', 'hrma.run'], cwd=str(REPO_ROOT), env=env,
            stdout=self.gunluk, stderr=subprocess.STDOUT)
        bitis = time.time() + 90
        while time.time() < bitis and not _hazir_mi(self.url):
            if self.proc.poll() is not None:
                self.kapat()
                raise SystemExit('sunucu açılırken düştü: ' + self.gunluk.name)
            time.sleep(0.5)
        if not _hazir_mi(self.url):
            self.kapat()
            raise SystemExit('sunucu 90 s içinde yanıt vermedi')

    def kapat(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.gunluk.close()


#: Kaydet: proje şeridinin ``apiSave(name, true)`` isteğinin birebiri
#: (hrma/static/js/project_bar.js) — gövde ``buildPayload(name)``.
_JS_KAYDET = """
async (ad) => {
  const r = await fetch('/api/projects/save', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: ad, payload: HRMAProjectBar._buildPayload(ad),
                          overwrite: true})});
  let govde = null;
  try { govde = await r.json(); } catch (e) { govde = null; }
  return {durum: r.status, govde: govde};
}
"""


def _sayfa_turu(tarayici, url, motor_type, ad):
    """Projeyi sayfada aç → Hesapla → gövde + şeridin belgesi → Kaydet."""
    from tests.test_v301_kabul_ui import KABUL_SAYFA_ISLEVI
    yol, islev = KABUL_SAYFA_ISLEVI[motor_type]
    uc = ENDPOINTS[motor_type]
    sayfa = tarayici.new_page(viewport={'width': 1440, 'height': 900})
    sayfa.set_default_timeout(30000)
    govdeler, durumlar = [], []

    def istek(req):
        if req.method == 'POST' and req.url.replace(url, '') == uc:
            govdeler.append(req.post_data_json)

    def yanit(resp):
        if resp.url.replace(url, '') == uc:
            durumlar.append(resp.status)

    sayfa.on('request', istek)
    sayfa.on('response', yanit)
    try:
        sayfa.goto(url + yol + '?project=' + urllib.parse.quote(ad))
        sayfa.wait_for_load_state('networkidle')
        # Hazırlık kapısı: proje şeridi projeyi YÜKLEDİ (sabit bekleme yok).
        sayfa.wait_for_function(
            'window.HRMAProjectBar && HRMAProjectBar._state && '
            'HRMAProjectBar._state.name === ' + json.dumps(ad))
        sayfa.wait_for_timeout(800)
        # Taze bağlam İngilizce açılır; dil değiştirilmez (KABUL U3: hibrit
        # sayfada dil seçicisi iki girdiyi siliyor — ürün hatası, DEVİR).
        dil = sayfa.evaluate('() => window.I18N ? I18N.lang : null')
        sayfa.evaluate("() => localStorage.removeItem('hrma.flight.lastVehicle')")
        sayfa.evaluate('() => { window.__ornekBitti = false; }')
        sayfa.evaluate('async (f) => { try { await window[f](); } finally '
                       '{ window.__ornekBitti = true; } }', islev)
        sayfa.wait_for_function('() => window.__ornekBitti === true',
                                timeout=180000)
        sayfa.wait_for_function('() => window.currentResults != null',
                                timeout=180000)
        sayfa.wait_for_load_state('networkidle')
        sayfa.wait_for_timeout(1500)
        belge = sayfa.evaluate('(a) => HRMAProjectBar._buildPayload(a)', ad)
        kayit = sayfa.evaluate(_JS_KAYDET, ad)
    finally:
        sayfa.close()
    return {'govdeler': govdeler, 'durumlar': durumlar, 'belge': belge,
            'kayit': kayit, 'dil': dil}


def sayfadan_uret(motor_type, ad, tarayici, url):
    """Sabit noktaya dek tur: dönen (gövde, belge, tur sayısı)."""
    onceki = None
    for tur in range(1, TUR_SINIRI + 1):
        o = _sayfa_turu(tarayici, url, motor_type, ad)
        if o['dil'] != 'en':
            raise SystemExit(f'{ad}: sayfa {o["dil"]!r} dilinde açıldı (en '
                             'bekleniyordu)')
        if len(o['govdeler']) != 1 or o['durumlar'] != [200]:
            raise SystemExit(
                f'{ad}: tur {tur}: Hesapla {len(o["govdeler"])} istek, '
                f'durum {o["durumlar"]} (beklenen 1 istek, [200])')
        if o['kayit']['durum'] != 200:
            raise SystemExit(f'{ad}: tur {tur}: Kaydet {o["kayit"]}')
        if not (o['belge'] or {}).get('results_summary'):
            raise SystemExit(f'{ad}: tur {tur}: şeridin belgesinde '
                             'results_summary yok')
        govde = o['govdeler'][0]
        if onceki is not None and govde == onceki[0] and o['belge'] == onceki[1]:
            return govde, o['belge'], tur
        onceki = (govde, o['belge'])
    raise SystemExit(f'{ad}: {TUR_SINIRI} turda sabit noktaya ulaşılamadı — '
                     'sayfa kendi kaydettiği projeyi aynı gövdeyle açmıyor')


def _ozeti_denetle(client, motor_type, ad, govde, ozet):
    """Gövde test istemcisinde 200 + özetin her sayısı yanıtla BİT-AYNI."""
    import hrma
    resp = client.post(ENDPOINTS[motor_type], json=govde, headers=HEADERS)
    if resp.status_code != 200:
        raise SystemExit(f'{ad}: {ENDPOINTS[motor_type]} {resp.status_code} — '
                         + resp.get_data(as_text=True)[:400])
    referans = ozet_referansi(motor_type, resp.get_json())
    farklar = [f'{k}: özet {ozet.get(k)!r} ⟷ yanıt {v!r}'
               for k, v in referans.items()
               if v is not None and ozet.get(k) != v]
    eksik = [k for k, v in referans.items() if v is not None and k not in ozet]
    if farklar or eksik:
        raise SystemExit(f'{ad}: şeridin özeti yanıttan farklı: {farklar}; '
                         f'eksik: {eksik}')
    if ozet.get('computed_with_version') != hrma.__version__:
        raise SystemExit(f'{ad}: özet sürümü {ozet.get("computed_with_version")!r}'
                         f' ⟷ ürün {hrma.__version__}')


def _hasat_yaz(govdeler):
    """Gövdeleri KABUL hasadına yaz (tests/test_v301_kabul_ui._hasat_yaz biçimi)."""
    from tests.support import kabul_sayfa_yukleri
    yukler = copy.deepcopy(kabul_sayfa_yukleri.SAYFA_YUKLERI)
    yukler.update(govdeler)
    eski = HASAT_YOLU.read_text(encoding='utf-8')
    bas = eski[:eski.index('SAYFA_YUKLERI = ')]
    bas = re.sub(r'Hasat tarihi: \S+',
                 'Hasat tarihi: ' + datetime.date.today().isoformat(), bas)
    HASAT_YOLU.write_text(bas + 'SAYFA_YUKLERI = ' + pprint.pformat(
        yukler, indent=1, width=100, sort_dicts=True) + '\n', encoding='utf-8')


def main(secilen=None):
    """Örnekleri üret; ``secilen`` verilirse YALNIZ o motor türleri yazılır.

    9. tur (Devir 33): bir örneğin girdisi düzeltildiğinde öbür örnekler
    yeniden kaydedilmez (damga ``created_at`` / ``app_version`` değişmesin,
    md5 aynı kalsın). Tanınmayan tür adı sessizce yutulmaz.
    """
    turler = ('hybrid', 'solid', 'liquid')
    if secilen:
        bilinmeyen = [t for t in secilen if t not in turler]
        if bilinmeyen:
            raise SystemExit(f'bilinmeyen motor türü: {bilinmeyen}; '
                             f'geçerli: {list(turler)}')
        turler = tuple(t for t in turler if t in secilen)

    calisma = _calisma_dizini()
    projeler = calisma / 'projeler'
    projeler.mkdir()
    # Bu süreçteki depo da kopya dizin; örnek kaynağı yok (damga yazılmaz).
    os.environ['HRMA_PROJECTS_DIR'] = str(projeler)
    os.environ['HRMA_EXAMPLES_DIR'] = str(calisma / 'ornek-kaynagi-yok')
    # Mevcut örnekler kopyalanır: save_project overwrite'ta created_at korunur.
    for ad in NAMES.values():
        kaynak = EXAMPLES_DIR / (ad + '.hrma')
        if kaynak.exists():
            shutil.copy2(kaynak, projeler / kaynak.name)
    print('çalışma dizini:', calisma)

    from hrma.app import app
    from hrma.utils import projects as store
    app.config['TESTING'] = True
    client = app.test_client()
    examples = build_examples(client)

    # 1) Tohumlar kopya dizine (uygulamanın kendi deposuyla)
    for motor_type in turler:
        spec = examples[motor_type]
        inputs = {'fields': spec['fields']}
        if spec.get('ui_state'):
            inputs['ui_state'] = spec['ui_state']
        store.save_project(NAMES[motor_type], {
            'format': 'hrma-project', 'format_version': 1,
            'name': NAMES[motor_type], 'description': spec['description'],
            'motor_type': motor_type, 'inputs': inputs}, overwrite=True)

    # 2-4) Sayfa: gövde + şeridin belgesi, sabit noktaya dek
    from playwright.sync_api import sync_playwright
    from tests.test_v301_kabul_ui import ARGS, KABUL_CHROME_YOLU
    port = int(os.environ.get('HRMA_ORNEK_PORT', VARSAYILAN_PORT))
    sunucu = _Sunucu(port, projeler, calisma)
    sonuclar = {}
    try:
        with sync_playwright() as p:
            tarayici = p.chromium.launch(executable_path=KABUL_CHROME_YOLU,
                                         args=ARGS)
            try:
                for motor_type in turler:
                    sonuclar[motor_type] = sayfadan_uret(
                        motor_type, NAMES[motor_type], tarayici, sunucu.url)
            finally:
                tarayici.close()
    finally:
        sunucu.kapat()

    # 5-6) Denetim + yazım
    govdeler = {}
    for motor_type in turler:
        name = NAMES[motor_type]
        govde, belge, tur = sonuclar[motor_type]
        dosya = projeler / (name + store.FILE_EXT)
        diskte = json.loads(dosya.read_text(encoding='utf-8'))
        for anahtar in ('inputs', 'results_summary', 'description',
                        'motor_type', 'name'):
            if diskte.get(anahtar) != belge.get(anahtar):
                raise SystemExit(f'{name}: diskteki {anahtar} şeridin '
                                 'belgesinden farklı')
        _ozeti_denetle(client, motor_type, name, govde,
                       diskte['results_summary'])
        shutil.copyfile(dosya, EXAMPLES_DIR / dosya.name)
        _dagitilmis_karmaya_ekle(name + store.FILE_EXT)
        govdeler[motor_type] = govde
        print(f"{name}.hrma  yazıldı (app {diskte['app_version']}, "
              f"{len(diskte['inputs']['fields'])} alan, sabit nokta tur {tur})")
        print('  özet:', diskte['results_summary'])
    _hasat_yaz(govdeler)
    print('hasat yazıldı:', HASAT_YOLU.relative_to(REPO_ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
