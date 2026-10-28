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

TEK YOL (v3.0.5, V301/ÖRNEK): hesaplar sayfanın Hesapla'da GERÇEKTEN
gönderdiği gövdeyle yapılır (``tests/support/kabul_sayfa_yukleri.py``;
examples/generate_examples.py örneği gerçek sayfada açıp yazar, aynı gövdeyi
oraya kaydeder). Eskiden iki ayna vardı — API yolu (``calculate_payload``,
yalnız dosyanın alanları) ve FORM yolu (``form_defaults.form_yuku``, şablon
varsayılanları); 27 Eki ölçümünde ikisi de sayfanın gövdesinden sapıyordu
(katı 16, sıvı 7, hibrit 28 alan) ve özet bekçisi kullanıcının gördüğü
sayıyı ölçmüyordu (hibrit Isp 236,0 ⟷ Hesapla 210,1 s). Hasadın bugünkü
sayfayla aynılığını ``tests/test_v301_kabul_ui.py::test_u1_*``, bu dosyayla
aynılığını ``test_hasat_ornek_dosyasindan`` bekler.

Örnekler examples/generate_examples.py ile üretilir; o betik buradaki
NAMES / ENDPOINTS / ozet_referansi adlarını import eder. NAMES'in tek
doğruluk kaynağı bu dosyadır; ENDPOINTS ve calculate_payload V301/UÇUŞ C-1'den
beri ÜRÜNDEN yeniden dışa aktarılır (``hrma/analysis/flight_vehicle.py``:
``CALCULATION_ENDPOINTS``, ``page_payload``) — Fırlatma Sahası kayıtlı projeyi
aynı eşlemeyle hesaplar.
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

#: motor_type -> hesap ucu. V301/UÇUŞ C-1: tanım ÜRÜNE taşındı
#: (``hrma/analysis/flight_vehicle.CALCULATION_ENDPOINTS``); bu ad yeniden
#: dışa aktarımdır (examples/generate_examples.py ve testler içe aktarır).
from hrma.analysis.flight_vehicle import (  # noqa: E402
    CALCULATION_ENDPOINTS as ENDPOINTS)

#: inputs.fields (form alan kimlikleri) -> hesap ucu yükü. V301/UÇUŞ C-1:
#: eşleme ürüne taşındı (``hrma.analysis.flight_vehicle.page_payload`` —
#: Fırlatma Sahası kayıtlı projeyi AYNI eşlemeyle hesaplar); bu ad yeniden
#: dışa aktarımdır ve içe aktarılabilir KALIR (KABUL kulvarı, örnek üretici,
#: ~20 test dosyası ``calculate_payload`` adını kullanıyor).
from hrma.analysis.flight_vehicle import (  # noqa: E402
    page_payload as calculate_payload)


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
def store_env(monkeypatch, tmp_path):
    """Proje deposu = örneklerin KOPYASI (izlenen examples/ dizinine yazılmaz).

    V301/KABUL (ölçüldü 27 Eki): depo examples/'a yönlendirilince ürün oraya
    tazeleme damgası (``.examples_refresh.json``) yazabiliyor; kopya dizin
    ``git status examples/``i temiz tutar.
    """
    depo = tmp_path / 'projeler'
    depo.mkdir()
    for ad in NAMES.values():
        kaynak = EXAMPLES_DIR / (ad + '.hrma')
        (depo / kaynak.name).write_bytes(kaynak.read_bytes())
    monkeypatch.setenv('HRMA_PROJECTS_DIR', str(depo))


# Hesap sonuçları pahalı (sıvı ~5-10 s) — motor tipi başına BİR kez
_RESULTS = {}


def _kos(client, motor_type, payload):
    resp = client.post(ENDPOINTS[motor_type], json=payload, headers=HEADERS)
    assert resp.status_code == 200, (
        f'{ENDPOINTS[motor_type]} {resp.status_code}: '
        + resp.get_data(as_text=True)[:400])
    body = resp.get_json()
    assert 'error' not in body, body.get('error')
    return body


def sayfa_govdesi(motor_type):
    """Örnek sayfada açılıp Hesapla'ya basılınca GERÇEK sayfanın gönderdiği
    gövde (hasat; examples/generate_examples.py yazar)."""
    import copy
    from tests.support.kabul_sayfa_yukleri import SAYFA_YUKLERI
    return copy.deepcopy(SAYFA_YUKLERI[motor_type])


def _sayfa_sonucu(client, motor_type):
    """KULLANICININ gördüğü hesap: sayfanın gerçek gövdesiyle (tek yol)."""
    if motor_type not in _RESULTS:
        _RESULTS[motor_type] = _kos(client, motor_type,
                                    sayfa_govdesi(motor_type))
    return _RESULTS[motor_type]


#: Eski adlar (bu dosyanın içi): iki ayna kalktı, ikisi de TEK yola gider.
_fresh_results = _sayfa_sonucu
_form_results = _sayfa_sonucu


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
def _sayfa_betigi_kuruyor(motor_type, alan):
    """Şablonda olmayan alanı sayfanın KENDİ betiklerinden biri kuruyor mu?

    v3.0.5 (V301/ÖRNEK): örnek dosya proje şeridinin belgesidir; şerit
    belgedeki ``input[id]/select[id]/textarea[id]`` öğelerinin HEPSİNİ yazar
    (``project_bar.js::serializeFields``) — sayfa şablonunun yanında ortak
    bileşenlerin kurduklarını da (ölçüldü: ``hrma_ai_goal`` ai_assistant.js
    "proje ile kaydedilir", ``fea_show_mesh``/``fea_metric``/
    ``grainfea_show_mesh`` fea_panel.js, ``fea_t_ambient``/``fea_t_show_mesh``
    thermal_fea_panel.js). Böyle bir alan ancak sayfanın şablonda yüklediği
    bir betik onu adıyla kuruyorsa kabul edilir; dönen (betik adı, kaynak) ya
    da None.
    """
    from tests.support import kabul
    for ad in kabul.sayfa_scriptleri(motor_type):
        yol = REPO_ROOT / 'hrma' / 'static' / 'js' / ad
        if not yol.is_file():
            continue
        kaynak = yol.read_text(encoding='utf-8')
        if f'id="{alan}"' in kaynak or f"'{alan}'" in kaynak:
            return ad, kaynak
    return None


_ISLENMIS_SAYFA = {}


def _islenmis_secenekler(motor_type, alan):
    """Seçenekleri şablonda Jinja döngüsüyle basılan seçici (ham metinde
    ``{{ o.key }}``): seçenekler sunucunun İŞLEDİĞİ sayfadan okunur.

    Ölçüldü (27 Eki, V301/ÖRNEK): katı ``propellant_type`` seçicisi
    (``solid_propellants.options``, K-C2) için ``tests/support/inventory.py``
    çözücü taşımıyor; ham şablon ``['{{ o.key }}', '']`` veriyor.
    """
    import re
    from tests.test_v301_kabul_ui import KABUL_SAYFA_ISLEVI
    if motor_type not in _ISLENMIS_SAYFA:
        from hrma.app import app
        sayfa = KABUL_SAYFA_ISLEVI[motor_type][0]
        # Sayfa yolları literal: bekçi taraması (test_d18_bekci_cevirisi_a1)
        # çağrılan rotayı çözebilsin; KABUL tablosuyla eşliği ayrıca sınanır.
        if sayfa == '/solid':
            r = app.test_client().get('/solid', headers=HEADERS)
        elif sayfa == '/liquid':
            r = app.test_client().get('/liquid', headers=HEADERS)
        else:
            assert sayfa == '/hybrid', sayfa
            r = app.test_client().get('/hybrid', headers=HEADERS)
        assert r.status_code == 200, r.status_code
        _ISLENMIS_SAYFA[motor_type] = r.get_data(as_text=True)
    m = re.search(r'<select[^>]*\bid="%s"[^>]*>(.*?)</select>' % re.escape(alan),
                  _ISLENMIS_SAYFA[motor_type], re.S)
    if not m:
        return None
    return re.findall(r'<option[^>]*\bvalue="([^"]*)"', m.group(1))


@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_example_fields_exist_on_the_page(motor_type):
    doc = load_example_doc(motor_type)
    specs = inventory.field_specs_for(motor_type)
    unknown, bad_options = [], []
    for field_id, value in doc['inputs']['fields'].items():
        spec = specs.get(field_id)
        if spec is None:
            bulunan = _sayfa_betigi_kuruyor(motor_type, field_id)
            if bulunan is None:
                unknown.append(field_id)
            elif (f'<select id="{field_id}"' in bulunan[1]
                  and f'value="{value}"' not in bulunan[1]):
                bad_options.append(f'{field_id}={value!r} ({bulunan[0]} '
                                   'seçeneklerinde yok)')
            continue
        secenekler = spec.options or []
        if spec.tag == 'select' and any('{{' in s for s in secenekler):
            secenekler = _islenmis_secenekler(motor_type, field_id) or secenekler
        if spec.tag == 'select' and str(value) not in secenekler:
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
    # V301/H-PANEL (NK-15): manşet c* artık TESLİM c*'tır (η_c* · kuramsal;
    # N2O/HTPB kaynaklı varsayılan 0,89). Literatür c* bandı KURAMSAL denge
    # c*'ına aittir; teslim değeri η ile ondan türer.
    verim = motor['c_star_efficiency']
    assert 1450 <= verim['c_star_theoretical_m_s'] <= 1800, verim
    assert motor['c_star'] == pytest.approx(
        verim['eta_c_star'] * verim['c_star_theoretical_m_s'], rel=1e-12)
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
def _sonlu_sayi(v):
    """project_bar.js ``put``: yalnız sonlu sayı (bool değil) özetlenir."""
    if isinstance(v, (int, float)) and not isinstance(v, bool) \
            and math.isfinite(v):
        return v
    return None


def ozet_referansi(motor_type, body):
    """Özet anahtarı -> taze hesaptaki karşılığı.

    ``hrma/static/js/project_bar.js::serializeResultsSummary``'nin birebiri
    (v3.0.5, V301/ÖRNEK): örnek dosyanın ``results_summary``'si artık o
    işlevin KENDİ çıktısıdır (examples/generate_examples.py proje şeridinin
    belgesini kaydeder). Katıda tepe itki ``max(thrust_curve.thrust)``,
    sıvıda toplam itki ``openrocket.motor_summary.total_impulse`` (şerit de
    oradan okur; yanma süresi yoksa yayımlanmaz). Karşılığı olmayan anahtar
    ``None`` döner.
    """
    if motor_type == 'hybrid':
        motor = body.get('motor') or {}
        return {
            'thrust_N': _sonlu_sayi(motor.get('thrust')),
            'isp_s': _sonlu_sayi(motor.get('isp')),
            'burn_time_s': _sonlu_sayi(motor.get('burn_time')),
            'chamber_pressure_bar': _sonlu_sayi(motor.get('chamber_pressure')),
            'total_impulse_Ns': _sonlu_sayi(motor.get('total_impulse')),
        }
    if motor_type == 'solid':
        egri = (body.get('thrust_curve') or {}).get('thrust')
        tepe = None
        if isinstance(egri, list) and egri:
            tepe = _sonlu_sayi(max(egri))
        return {
            'total_impulse_Ns': _sonlu_sayi(body.get('total_impulse')),
            'burn_time_s': _sonlu_sayi(body.get('burn_time')),
            'chamber_pressure_bar': _sonlu_sayi(body.get('chamber_pressure')),
            'isp_s': _sonlu_sayi(body.get('isp_sea_level')),
            'peak_thrust_N': tepe,
        }
    ors = (body.get('openrocket') or {}).get('motor_summary') or {}
    return {
        'thrust_N': _sonlu_sayi(body.get('thrust')),
        'isp_s': _sonlu_sayi(body.get('isp_sea_level')),
        'isp_vacuum_s': _sonlu_sayi(body.get('isp_vacuum')),
        'chamber_pressure_bar': _sonlu_sayi(body.get('chamber_pressure')),
        'total_impulse_Ns': _sonlu_sayi(ors.get('total_impulse')),
    }


#: Eski ad (bu dosyanın içi); tek tanım ``ozet_referansi``.
_summary_reference = ozet_referansi


#: Özet ⟷ taze hesap bağıl toleransı. ÖH D35 · OH-ON-03'te %25'ten
#: indirildi: özet artık örneği üreten KOŞUMUN çıktısıdır (aynı sürüm, aynı
#: yol), dolayısıyla eşitlik yuvarlamaya kadar beklenir. %25'lik eski bant
#: KUSURU KORUYORDU — %14,8'lik gerçek kayma (16 Eylül, OH-D33) o bandın
#: içinde kalıp bekçiyi yeşil bırakmıştı.
OZET_BAGIL_TOLERANS = 0.005


@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_results_summary_is_not_fabricated(client, motor_type):
    """Özet, KULLANICININ gördüğü hesapla aynı sayıyı söylemeli.

    ÖH D35 · OH-ON-03 — BEKÇİ ÇEVRİLDİ (ÖLÇÜLDÜ 22 Eylül 2026,
    ``docs/scofield/raw/OH/D35/onemli-kati-cad/a1/10_once.json``).

    Bu bekçi API yolunu ölçüyordu: örneğin ``inputs.fields``ını doğrudan
    hesap ucuna veriyordu. Kullanıcı ise örneği ARAYÜZE yükler ve Hesapla'ya
    basar; dosyada olmayan alanlar sayfanın kendi ``value=`` varsayılanıyla
    gönderilir. Katı örnekte bu 51 fazladan alan demekti ve yayımlanan sayı
    ayrışıyordu: proje şeridi **Isp 140,109 s**, Hesapla **125,401 s**
    (%-10,5); toplam itki 3306,767 ⟷ 2959,642 N·s. Bekçi API yolunu ölçtüğü
    için kaymayı GÖRMÜYORDU — kusuru koruyan bekçi.

    Artık ölçülen yol FORM yoludur ve tolerans %25'ten %0,5'e indirilmiştir
    (özet, örneği üreten koşumun çıktısıdır; eşitlik beklenir).

    v3.0.5 (V301/ÖRNEK): FORM yolu da bir aynaydı ve sayfadan sapıyordu
    (hibrit özet Isp 236,034 ⟷ Hesapla 210,063 s). Ölçülen yol artık
    sayfanın GERÇEK gövdesidir (``sayfa_govdesi``); özet proje şeridinin kendi
    çıktısıdır, şeridin yazacağı her anahtar özette bulunmalıdır (eksik
    anahtar = bayat özet; ör. sıvıda yanma süresiyle gelen toplam itki).
    """
    doc = load_example_doc(motor_type)
    summary = doc.get('results_summary')
    assert summary, 'örnekte results_summary olmalı (liste kartları için)'
    reference = ozet_referansi(motor_type, _sayfa_sonucu(client, motor_type))
    eksik = sorted(k for k, v in reference.items()
                   if v is not None and k not in summary)
    assert not eksik, (
        f'{motor_type}: proje şeridinin yazacağı özet anahtarları örnekte '
        f'yok: {eksik} — örneği yeniden üretin (examples/generate_examples.py)')
    checked = 0
    for key, saved in summary.items():
        if key == 'computed_with_version' or key not in reference:
            continue
        fresh = reference[key]
        assert isinstance(fresh, (int, float)) and math.isfinite(fresh), (
            f'{motor_type}.{key}: taze hesapta karşılık yok')
        assert math.isclose(saved, fresh, rel_tol=OZET_BAGIL_TOLERANS,
                            abs_tol=1e-9), (
            f'{motor_type}.{key}: kayıtlı {saved} / sayfa yolu {fresh} — '
            'örneğin özeti kullanıcının gördüğü sayıyla ayrışıyor; örneği '
            'yeniden üretin (examples/generate_examples.py)')
        checked += 1
    assert checked >= 3, 'özet en az üç sayısal büyüklük taşımalı'


#: Hasat ⟷ örnek dosyası karşılaştırmasının BEYANLI istisnaları (ÖLÇÜLDÜ
#: 27 Eki 2026, V301/ÖRNEK; ``docs/scofield/raw/OH/V301/ornek/RAPOR.md``).
#: Sayfanın toplayıcısı bu gövde anahtarlarını alanlardan TÜRETİR ya da
#: başka adla gönderir — dosyada aynı adlı alan yoktur ya da farklı anlamdadır:
HASAT_TURETILEN_ANAHTARLAR = {
    # advanced.html toplayıcısı: atmospheric_pressure = tek irtifa basıncı
    # (single_pressure); design_config_* = tasarım paneli köken künyesi;
    # vehicle_* = yörünge alanlarından (final_mass, reference_area mm² → m²);
    # total_impulse = itki × süre (thrust_time sekmesi; aynı adlı form alanı
    # öteki sekmenin, toplam impuls tasarımının girdisidir).
    'hybrid': frozenset({
        'atmospheric_pressure', 'design_config_fields', 'design_config_opened',
        'design_config_source', 'vehicle_length', 'vehicle_mass_dry',
        'vehicle_reference_area_m2', 'total_impulse'}),
    # solid.html: salt okunur ε alanı geri yüklemede ``updateExpansionRatio``
    # ile kayıtlı (2 haneli) çaplardan yeniden türetilir; çözücü tasarım
    # kipinde ε'yu kendisi çözer (ölçüldü: gövde 6,75 ⟷ alan 6,89, sonuç
    # aynı).
    'solid': frozenset({'expansion_ratio'}),
    'liquid': frozenset(),
}


@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_hasat_ornek_dosyasindan(motor_type):
    """Hasat edilen gövde BU örnek dosyanın gövdesidir: gövdedeki her anahtar
    dosyada aynı değerle durur (boş alan → ``null``), türetilen anahtarlar
    beyanlı listededir. Örnek elle değiştirilip yeniden üretilmezse (ya da
    hasat yenilenmezse) bu düğüm kırmızıdır — testler bayat gövdeyle koşmaz.
    """
    alanlar = load_example_doc(motor_type)['inputs']['fields']
    govde = sayfa_govdesi(motor_type)
    istisna = HASAT_TURETILEN_ANAHTARLAR[motor_type]
    farklar = []
    for anahtar, deger in sorted(govde.items()):
        if anahtar in istisna:
            continue
        if anahtar not in alanlar:
            farklar.append(f'{anahtar}: gövdede var, dosyada alan yok')
            continue
        dosyada = alanlar[anahtar]
        if dosyada == '' and deger is None:
            continue
        if dosyada != deger:
            farklar.append(f'{anahtar}: dosya {dosyada!r} ⟷ gövde {deger!r}')
    assert not farklar, (
        f'{motor_type}: hasat (tests/support/kabul_sayfa_yukleri.py) bu örnek '
        'dosyanın gövdesi değil — örneği examples/generate_examples.py ile '
        'yeniden üretin:\n  ' + '\n  '.join(farklar))


@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_aciklama_girdilerden_uretilmis(motor_type):
    """Açıklama (EN + TR) dosyanın GİRDİLERİNDEN üretilmiştir.

    v3.0.5 (Berke 27 Eki): "Örnek tasarım / Example design" (HRMA ön tasarım
    ve analiz aracıdır, "eğitim amaçlı" değil) ve açıklamadaki her sayı
    örneğin kendi girdisinden gelir. Ölçülen kusur: sıvı örneğin açıklaması
    girdiler değiştikten sonra da "70 bar, O/F 2.3" diyordu.

    İki iddia: (1) açıklama = ``aciklama_kur(motor_type, inputs.fields)``
    (hibritte ``motor_description`` alanı da); (2) metinden girdilerin
    biçimlenmiş değerleri ve adlar çıkarılınca TEK rakam kalmaz (elle
    yazılmış sayı yok).
    """
    import re
    from examples import generate_examples as ge
    doc = load_example_doc(motor_type)
    alanlar = doc['inputs']['fields']
    beklenen = ge.aciklama_kur(motor_type, alanlar)
    assert doc['description'] == beklenen, (
        f'{motor_type}: açıklama girdilerden üretilen metinle aynı değil — '
        'examples/generate_examples.py ile yeniden üretin')
    if 'motor_description' in alanlar:
        assert alanlar['motor_description'] == beklenen
    assert 'Educational' not in beklenen and 'Öğretici' not in beklenen
    assert beklenen.startswith('Örnek tasarım: ') and ' / Example design: ' in beklenen
    parcalar = set()
    if isinstance(alanlar.get('propellant_name'), str):
        parcalar.add(alanlar['propellant_name'])
    for adlar in ge._ACIKLAMA_ADLARI.values():
        for tr, en in adlar.values():
            parcalar.update((tr, en))
    for alan, deger in alanlar.items():
        if isinstance(deger, (int, float)) and not isinstance(deger, bool):
            for dil in ('tr', 'en'):
                for bolen in (1.0, 1000.0):
                    parcalar.add(ge._sayi(alanlar, alan, dil, bolen))
    kalan = beklenen
    for parca in sorted(parcalar, key=len, reverse=True):
        kalan = kalan.replace(parca, ' ')
    assert not re.search(r'\d', kalan), (
        f'{motor_type}: açıklamada girdiden gelmeyen rakam var: {kalan!r}')


@pytest.mark.parametrize('motor_type', sorted(NAMES))
def test_ozet_BU_SURUMLE_hesaplanmis(motor_type):
    """results_summary'yi hangi sürüm ürettiyse o, bugünkü sürüm olmalı.

    ÖLÇÜLDÜ (16 Eyl 2026, Berke turda yakaladı): paketle gelen üç örneğin
    özeti 30-31 Temmuz'da, **2.6.26** ile hesaplanmıştı. Aradaki D30-D33
    onarımları sayıları kaydırdı; 2.6.27'de yeniden üretince katı örneğin
    tepe itkisi 1926,8 N'den 1641,9 N'ye (%-14,8), yanma süresi 2,024 s'den
    2,323 s'ye (%+14,8) gitti. Yani kullanıcı proje şeridinde 1927 N görüp
    Hesapla'ya bastığında 1642 N alıyordu: ürünün kendisiyle çelişen bir sayı.

    Neden ÜSTTEKI bekçi yakalamadı: test_results_summary_is_not_fabricated
    %25 bağıl toleransla karşılaştırıyor (gerekçesi: model rekalibrasyonunda
    hemen kırmamak) ve `computed_with_version` alanını AÇIKÇA atlıyordu.
    %14,8'lik kayma o bandın içinde kaldı; bekçi yeşil kalarak kusuru korudu
    (bu depoda adı konmuş sınıf: kusuru koruyan bekçi).

    Bu düğüm o boşluğu kapatır: sayısal tolerans kaba ağ olarak kalır,
    sürüm damgası ise KESİN ölçüdür. Sürüm yükseldiğinde örnekler yeniden
    üretilmelidir (examples/generate_examples.py).
    """
    import hrma
    doc = load_example_doc(motor_type)
    damga = (doc.get('results_summary') or {}).get('computed_with_version')
    assert damga, f'{motor_type}: özet hangi sürümle hesaplandığını yazmıyor'
    assert damga == hrma.__version__, (
        f'{motor_type}: özet {damga} ile hesaplanmış, ürün {hrma.__version__} — '
        'örnekleri yeniden üretin: python3 examples/generate_examples.py')


#: README tablosunun andığı özet alanları (motor tipi -> alanlar). Tablo bu
#: sayıları birebir yazar; bekçi de onları arar. Buraya alan eklenirse
#: examples/README.md tablosuna da eklenmelidir.
README_ALANLARI = {
    'hybrid': ('isp_s', 'total_impulse_Ns'),
    'solid': ('peak_thrust_N', 'burn_time_s', 'total_impulse_Ns', 'isp_s'),
    # v3.0.5: sıvı örnek yanma süresi taşıdığı için toplam itki de yayımlanır.
    'liquid': ('isp_s', 'isp_vacuum_s', 'total_impulse_Ns'),
}


def _tr_sayi(x):
    """Türkçe ondalık ayracıyla, README'deki gibi üç haneli."""
    return ('%.3f' % float(x)).replace('.', ',')


def test_readme_tablosu_ozetlerle_ayni():
    """examples/README.md tablosu .hrma özetleriyle AYNI sayıları yazmalı.

    ÖLÇÜLDÜ (16 Eyl 2026): üç katman, üç ayrı sürüm. README tablosu **v2.6.25**
    ile hesaplanmış sayıları taşıyordu, .hrma dosyaları **v2.6.26** ile, ürün
    ise **2.6.27**'ydi. Katı örneğin tepe itkisi README'de 1,67 kN, dosyada
    1926,8 N, üründe 1641,9 N görünüyordu.

    Bu düğüm README'yi özete bağlar: örnekler yeniden üretilirse README de
    güncellenmek zorundadır. Özeti ürüne bağlayan düğüm ayrıdır
    (test_ozet_BU_SURUMLE_hesaplanmis), yani zincir README -> özet -> ürün
    olarak kapanır.
    """
    import hrma
    metin = (EXAMPLES_DIR / 'README.md').read_text(encoding='utf-8')
    damga = '(v%s ile' % hrma.__version__
    assert damga in metin, (
        'README tablosu hangi sürümle ölçüldüğünü yazmıyor ya da sürüm eski: '
        f'{damga!r} aranıyordu')
    for motor_type, alanlar in sorted(README_ALANLARI.items()):
        ozet = load_example_doc(motor_type)['results_summary']
        for alan in alanlar:
            assert alan in ozet, f'{motor_type}: özette {alan} yok'
            sayi = _tr_sayi(ozet[alan])
            assert sayi in metin, (
                f'{motor_type}.{alan} = {sayi} README tablosunda yok; '
                'örnekler yeniden üretildiyse README de güncellenmeli')


if __name__ == '__main__':                  # pragma: no cover
    import sys
    sys.exit(pytest.main([__file__, '-v']))
