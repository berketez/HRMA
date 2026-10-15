"""
Analiz Güvertesi (Analysis Dock) sözleşme testleri — BOL TEST dalgası (2026-07-14).

Kapsam (test_client ile — sunucuya port BAĞLANMAZ):
  1. Sayfa sözleşmesi: /, /hybrid, /solid, /liquid 200 döner; motor
     sayfalarında analysis_dock.js panellerden ÖNCE yüklenir ve
     #analysis-dock-anchor mevcuttur (analysis_dock.js başlık yorumundaki
     "entegrasyon sözleşmesi — DEĞİŞTİRME" bloğu).
  2. Panel yanıt sözleşmesi: /analyze_structural_safety,
     /analyze_thermal_safety, /analyze_safety gerçek payload'larla 200 döner
     ve panellerin render() içinde okuduğu anahtarlar yanıtta VARDIR
     (anahtar listeleri panels/*.js dosyalarından çıkarıldı — grep ile).
  3. 501 bekçileri: kinetic / cfd / professional-analysis dürüst 501 döner.
  4. /calculate: motor.gamma + motor.molecular_weight üst seviyede;
     ölü plots.heat_transfer / plots.structural_analysis anahtarları YOK;
     tam varsayılan hibrit akışı 30 sn altında tamamlanır.
  5. Uçtan uca duman: /calculate → structural panelin fromResults eşlemesi →
     /analyze_structural_safety → SF alanları sayısal ve tutarlı
     (SF_pressure >= SF_total; basınç-yalnız SF, termal içeren toplamdan
     küçük olamaz).

Panellerin okuduğu alan adları kaynakları:
  - panels/structural_panel.js  → structural_analysis.* anahtarları
  - panels/thermal_panel.js     → thermal_analysis.* anahtarları
  - panels/safety_panel.js      → safety_analysis.* anahtarları
"""

import math
import re
import time
import warnings

import pytest


def _band_tavani_bar():
    """Hazne basıncı üst sınırını deponun KANONİK tablosundan okur.

    ÖH D17 / OH-D16 ŞART (defter OH-Z5-16). Uç kapısı
    (``hrma/app.py::_ust_sinir_bandi``) üst sınırlarını
    ``MotorDataValidator().limits``ten alır ve orada yeni eşik icat
    etmediğini açıkça beyan eder. Bekçinin bandı da AYNI yerden okumak
    zorundadır; yoksa tablo değiştiğinde test kendi eski sayısını
    savunur.
    """
    from hrma.validation.motor_validation import MotorDataValidator
    return float(MotorDataValidator().limits['chamber_pressure']['max'])

warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Sabitler — panel varsayılanları panels/*.js `fields` listeleriyle birebir
# ---------------------------------------------------------------------------

MOTOR_PAGES = ['/hybrid', '/solid', '/liquid']
ALL_PAGES = ['/'] + MOTOR_PAGES

DOCK_SCRIPT = '/static/js/analysis_dock.js'
PANEL_SCRIPTS = [
    '/static/js/panels/structural_panel.js',
    '/static/js/panels/thermal_panel.js',
    '/static/js/panels/safety_panel.js',
]
HUD_SCRIPT = '/static/js/hud.js'
DOCK_ANCHOR_ID = 'analysis-dock-anchor'

GUARDED_501_ENDPOINTS = [
    '/api/kinetic-analysis',
    '/api/cfd-analysis',
    '/api/professional-analysis',
]

# structural_panel.js `fields` varsayılanları
STRUCTURAL_PAYLOAD = {
    'chamber_pressure': 40,      # bar
    'chamber_diameter': 0.1,     # m
    'chamber_length': 0.5,       # m
    'throat_diameter': 0.02,     # m
    'burn_time': 10,             # s
    'material': 'steel_4130',
}

# thermal_panel.js `fields` varsayılanları
THERMAL_PAYLOAD = {
    'chamber_pressure': 40,      # bar
    'chamber_temperature': 3000, # K
    'chamber_diameter': 0.1,     # m
    'chamber_length': 0.5,       # m
    'burn_time': 10,             # s
    'mdot_total': 1.0,           # kg/s
    'wall_thickness': 0.005,     # m
    'material': 'steel',
    'cooling_type': 'natural',
}

# safety_panel.js `fields` varsayılanları
SAFETY_PAYLOAD = {
    'motor_type': 'hybrid',
    'chamber_pressure': 40,      # bar
    'chamber_temperature': 3000, # K
    'thrust': 1000,              # N
    'burn_time': 10,             # s
    'propellant_mass': 5,        # kg
    'propellant_type': 'composite',
    'facility_type': 'test_stand',
    'chamber_diameter': 0.1,     # m
    'wall_thickness': 0.005,     # m
    # ÖH D27 / arayuz a2 — P5B2-12 PANEL YARISI ÖDENDİ. Bu sözlük
    # safety_panel.js `FIELDS` listesinin AYNASIdır; panel D27'de ısı
    # zinciri geometrisini de göndermeye başladı (ölçüm:
    # a2/once.json `safety_fields_isi_zinciri_sayisi` 2 -> 4), o yüzden
    # ayna da güncellendi. Değerler `THERMAL_CHAIN_PAYLOAD`ınkilerle
    # AYNI — ikisi arasındaki tek fark artık kalmadığı için aşağıdaki
    # ısı zinciri yükü bu sözlükten TÜRETİLİR.
    'chamber_length': 0.3,       # m
    'throat_diameter': 0.03,     # m
}

# ÖH Faz B / B5 — risk ekseninin girdiye tepkisini ölçen iki türev yük.
# Varsayılanın YALNIZ tek alanı değişir ki fark o alana atfedilebilsin.
# ÖH D27 / arayuz a2 — ILIMAN ISIL TABAN. P5B2-12'nin panel yarısı
# ödendikten sonra ``SAFETY_PAYLOAD`` ısı zincirini de gönderiyor ve
# 3000 K'de TERMAL EKSEN ZATEN TAVANDA (ölçüldü, bu depo: thermal 5,0,
# overall 5,0). Toplama kuralı worst-axis(max) olduğundan doygun bir
# tabanda "girdi arttı, skor arttı" iddiası MATEMATİKSEL OLARAK
# ölçülemez — başka bir eksen zaten 5,0'ı çivilemiştir. İki tepki
# bekçisi bu yüzden doygun OLMAYAN bir tabandan ölçer (600 K: thermal
# 2,0, explosive 3,0, overall 3,0). Bu bir gevşetme DEĞİLDİR: tavana
# ulaşılabilirliği kardeş bekçi
# ``test_thermal_axis_ladder_reaches_the_ceiling`` ayrıca ölçüyor.
MILD_THERMAL_PAYLOAD = dict(SAFETY_PAYLOAD, chamber_temperature=600)  # K
HEAVY_CHARGE_PAYLOAD = dict(MILD_THERMAL_PAYLOAD, propellant_mass=500)  # 100×
# ÖH D26 / P5B2-12 — ESKİ YÜK 1e6 K'YDI VE ARTIK UÇTAN GEÇMİYOR.
# ÖLÇÜLDÜ (D26 tabanı 7751531): ``chamber_temperature = 1e6`` gönderilen
# istek HTTP **422 invalid_safety_input** ile reddediliyor — D16'da kurulan
# kanonik bant kapısı (``motor_validator.limits['temperature']`` 200-5000 K)
# doğru çalışıyor. Yani bu fikstür bir SAĞLIKLI KAPIYA çarpıyordu: taşıdığı
# borç imi, panel yükü düzelse bile asla yeşile dönemezdi. Uç ısıl yük
# bandın İÇİNE çekildi (4500 K); "uç" olma niteliği cidar kalınlığından
# (0,1 mm) ve sıcaklıktan gelir, bandı delmekten değil.
EXTREME_THERMAL_PAYLOAD = dict(SAFETY_PAYLOAD,
                               chamber_temperature=4500,  # K, bandın içi
                               wall_thickness=1e-4)       # m, 0,1 mm

#: Isı zinciri TAM yük — ``_SAFETY_THERMAL_CHAIN_FIELDS`` (app.py) ucun
#: kabul ettiği alanlar. ÖH D27 / arayuz a2'ye kadar ``safety_panel.js``
#: bunları GÖNDERMİYORDU (P5B2-12 panel yarısı); artık gönderiyor, yani
#: bu yük ile ``SAFETY_PAYLOAD`` ARTIK AYNIDIR. Ad korunuyor çünkü
#: aşağıdaki merdiven bekçisi "ısı zinciri TAM" olduğunu adıyla söyler;
#: türetme ise iki sözlüğün bir daha ayrışmasını engeller.
THERMAL_CHAIN_PAYLOAD = dict(SAFETY_PAYLOAD)

# /calculate — hibrit varsayılan akış (UI'nin gönderdiği çekirdek alanlar;
# ağır adımlar BİLEREK açık bırakıldı: süre sözleşmesi gerçek akışı ölçer)
CALCULATE_PAYLOAD = {
    'thrust': 1000,
    'burn_time': 10,
    'of_ratio': 6.0,
    'chamber_pressure': 20.0,
    'fuel_type': 'htpb',
    'oxidizer_type': 'n2o',
}

CALCULATE_TIME_BUDGET_S = 30.0

# --- Ürünün kendi ürettiği kapalı değer kümeleri (etiket alanları) --------
# Kaynaklar: structural_analysis.py:1534-1541 (yorulma durumu üç dal),
# :1416 (cıvata künyesi f"M{çap_mm}"), :1272 + :1244 (kapak tipi ikili).
FATIGUE_STATUSES = ('SAFE', 'MARGINAL', 'CRITICAL')
END_CAP_TYPES = ('dished', 'flat')
BOLT_SIZE_PATTERN = re.compile(r'^M\d+$')


def _finite(x):
    """Gerçek bir SAYI ve sonlu mu?

    ÖH Faz B / adım B5: ``bool`` Python'da ``int`` alt sınıfıdır, yani
    ``True`` eski hâlde "sonlu sayı" sayılıyor ve ``True > 0`` da geçiyordu.
    Bir ölçüm alanına düşen ``True`` bir ölçüm değildir; tip ekseni burada
    kapatılır (yardımcının tüm çağrı yerleri bundan yararlanır).
    """
    return (isinstance(x, (int, float)) and not isinstance(x, bool)
            and math.isfinite(x))


def _assert_keys(d, keys, where, positive=(), fraction=(), text=()):
    """Anahtar VARLIĞI **ve** SAYI SAĞLIĞI sözleşmesi.

    ÖH Faz B / adım B5 — defter P13B2-01 (yüksek, "test-totolojik"):
    bu yardımcı 2026-08-27'ye kadar yalnız ``k not in d`` bakıyordu.
    Savcı ölçtü ki panel sözleşmesi "anahtar var" diye YEŞİL geçiyor,
    anahtarın DEĞERİ ne olursa olsun: ``bolt_safety_factor = -1e12``,
    NaN ısı akısı ve ``recommended_bolt_size = "kırmızı balık"`` üç
    bekçiyi de kırmızıya döndürmüyordu. Paneller bu alanları kullanıcıya
    ÇİZDİĞİ için sözleşmenin cümlesi "alan var" değil "alan
    KULLANILABİLİR" olmak zorundadır.

    Sayı sınama deseni bu dosyada zaten VARDI — ``test_chamber_analysis_
    keys`` (``_finite(ca[k]) and ca[k] > 0``) ve ``test_panel_source_
    fields_present``. B5 o kardeş deseni yardımcının içine taşır ki
    sözleşmenin tamamı aynı ekseni kullansın.

    Eksenler:
      * **varlık** — listelenen (ve eksen tuple'larında anılan) her anahtar
        sözlükte olmalı (eski davranış, korunur);
      * **sonluluk** — beklenen anahtarların SAYISAL olanları NaN/±inf
        taşıyamaz (varsayılan eksen, çağrı yerinde bir şey yazmak gerekmez);
      * **pozitiflik** (``positive``) — fiziksel olarak sıfır/negatif
        olamayan alanlar (kalınlık, kütle, alan, kuvvet, emniyet katsayısı);
      * **oran** (``fraction``) — 0 < v <= 1 aralığındaki verim/oran alanları;
      * **metin** (``text``) — boş olmayan dize (etiket ve künye alanları).
    """
    beklenen = list(keys) + [k for k in (*positive, *fraction, *text)
                             if k not in keys]
    missing = [k for k in beklenen if k not in d]
    assert not missing, f"{where} eksik anahtarlar: {missing}"

    for k in beklenen:
        v = d[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        assert math.isfinite(v), (
            f"{where}.{k} sonlu bir sayı değil ({v!r}) — panel bu alanı "
            "kullanıcıya çizer; NaN/±inf 'anahtar var' diye geçemez")

    for k in positive:
        assert _finite(d[k]) and d[k] > 0, (
            f"{where}.{k} pozitif sonlu bir sayı değil ({d[k]!r}) — bu alan "
            "fiziksel olarak sıfır ya da negatif olamaz")

    for k in fraction:
        assert _finite(d[k]) and 0.0 < d[k] <= 1.0, (
            f"{where}.{k} 0 < v <= 1 aralığında bir oran değil ({d[k]!r})")

    for k in text:
        assert isinstance(d[k], str) and d[k].strip(), (
            f"{where}.{k} boş olmayan bir dize değil ({d[k]!r})")


# ---------------------------------------------------------------------------
# Ortak fikstürler — ağır /calculate yalnız BİR kez koşar (modül kapsamı)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def calc_response(client):
    """Tam varsayılan hibrit /calculate — süre ölçümüyle birlikte."""
    t0 = time.monotonic()
    r = client.post('/calculate', json=CALCULATE_PAYLOAD)
    elapsed = time.monotonic() - t0
    assert r.status_code == 200, f"/calculate {r.status_code} döndü"
    return {'json': r.get_json(), 'elapsed': elapsed}


@pytest.fixture(scope='module')
def structural_json(client):
    r = client.post('/analyze_structural_safety', json=STRUCTURAL_PAYLOAD)
    assert r.status_code == 200
    return r.get_json()


@pytest.fixture(scope='module')
def thermal_json(client):
    r = client.post('/analyze_thermal_safety', json=THERMAL_PAYLOAD)
    assert r.status_code == 200
    return r.get_json()


@pytest.fixture(scope='module')
def safety_json(client):
    r = client.post('/analyze_safety', json=SAFETY_PAYLOAD)
    assert r.status_code == 200
    return r.get_json()


@pytest.fixture(scope='module')
def safety_json_mild(client):
    """Doygun OLMAYAN ısıl taban — bkz. MILD_THERMAL_PAYLOAD notu."""
    r = client.post('/analyze_safety', json=MILD_THERMAL_PAYLOAD)
    assert r.status_code == 200, r.status_code
    return r.get_json()


@pytest.fixture(scope='module')
def safety_json_heavy_charge(client):
    """Yalnız itici kütlesi 100 katına çıkarılmış varsayılan yük."""
    r = client.post('/analyze_safety', json=HEAVY_CHARGE_PAYLOAD)
    assert r.status_code == 200
    return r.get_json()


@pytest.fixture(scope='module')
def safety_json_extreme_thermal(client):
    """Isıl ekseni zorlayan uç yük (1e6 K hazne, 0,01 mm cidar)."""
    r = client.post('/analyze_safety', json=EXTREME_THERMAL_PAYLOAD)
    assert r.status_code == 200
    return r.get_json()


# ---------------------------------------------------------------------------
# 1. Sayfa sözleşmesi
# ---------------------------------------------------------------------------

class TestPageContract:
    @pytest.mark.parametrize('page', ALL_PAGES)
    def test_page_returns_200_html(self, client, page):
        r = client.get(page)
        assert r.status_code == 200, f"{page} -> {r.status_code}"
        assert 'text/html' in r.content_type
        assert len(r.data) > 500, f"{page} şüpheli derecede boş"

    @pytest.mark.parametrize('page', MOTOR_PAGES)
    def test_dock_loads_before_panels(self, client, page):
        """analysis_dock.js paneller kendilerini register edebilsin diye
        HER panel script'inden önce gelmeli (yükleme sırası sözleşmesi)."""
        html = client.get(page).get_data(as_text=True)
        dock_idx = html.find(DOCK_SCRIPT)
        assert dock_idx != -1, f"{page} sayfasında {DOCK_SCRIPT} yok"
        for panel in PANEL_SCRIPTS:
            p_idx = html.find(panel)
            assert p_idx != -1, f"{page} sayfasında {panel} yok"
            assert p_idx > dock_idx, (
                f"{page}: {panel} analysis_dock.js'ten ÖNCE yükleniyor — "
                "panel register edilemez (window.AnalysisDock tanımsız)")

    @pytest.mark.parametrize('page', MOTOR_PAGES)
    def test_hud_script_present_before_dock(self, client, page):
        """hud.js HUD katmanını kurar; dock'tan önce gelmeli."""
        html = client.get(page).get_data(as_text=True)
        hud_idx = html.find(HUD_SCRIPT)
        dock_idx = html.find(DOCK_SCRIPT)
        assert hud_idx != -1, f"{page} sayfasında {HUD_SCRIPT} yok"
        assert hud_idx < dock_idx

    @pytest.mark.parametrize('page', MOTOR_PAGES)
    def test_dock_anchor_present(self, client, page):
        html = client.get(page).get_data(as_text=True)
        assert f'id="{DOCK_ANCHOR_ID}"' in html, (
            f"{page}: #{DOCK_ANCHOR_ID} yok — AnalysisDock.init kurulamaz")

    @pytest.mark.parametrize('page', MOTOR_PAGES)
    def test_dock_init_wired_to_anchor(self, client, page):
        """AnalysisDock.init çağrısı anchor'a bağlanmış olmalı."""
        html = client.get(page).get_data(as_text=True)
        assert 'AnalysisDock.init' in html
        assert f"anchorId: '{DOCK_ANCHOR_ID}'" in html

    def test_landing_page_has_no_partial_dock(self, client):
        """Açılış sayfası (/) güverte içermez; yarım entegrasyon (script var,
        anchor yok gibi) regresyonunu yakalar."""
        html = client.get('/').get_data(as_text=True)
        if DOCK_SCRIPT in html:
            # Güverte eklenmişse sözleşmenin tamamı gelmeli
            assert f'id="{DOCK_ANCHOR_ID}"' in html
            for panel in PANEL_SCRIPTS:
                assert panel in html


# ---------------------------------------------------------------------------
# 2. Panel yanıt sözleşmeleri — panellerin render() içinde okuduğu anahtarlar
# ---------------------------------------------------------------------------

class TestStructuralResponseContract:
    def test_status_success(self, structural_json):
        assert structural_json['status'] == 'success'
        assert 'structural_analysis' in structural_json

    def test_sections_panel_reads(self, structural_json):
        sa = structural_json['structural_analysis']
        _assert_keys(sa, [
            'chamber_analysis', 'safety_analysis', 'buckling_analysis',
            'fatigue_analysis', 'fastener_analysis', 'end_cap_analysis',
            'material_properties', 'design_parameters', 'weight_analysis',
        ], 'structural_analysis')

    def test_chamber_analysis_keys(self, structural_json):
        ca = structural_json['structural_analysis']['chamber_analysis']
        _assert_keys(ca, [
            'von_mises_stress', 'von_mises_safety_factor',
            'pressure_hoop_stress', 'hoop_safety_factor',
            'thermal_hoop_stress', 'longitudinal_stress',
            'minimum_thickness', 'recommended_thickness',
            'governing_thermal_scenario', 'yield_strength_used_MPa',
            'pressure_hoop_model',
            # Dalga 0 çift-SF raporu (app.js exportu + panel bunları okur)
            'safety_factor_pressure', 'safety_factor_total',
        ], 'chamber_analysis')
        for k in ('von_mises_stress', 'von_mises_safety_factor',
                  'hoop_safety_factor', 'safety_factor_pressure',
                  'safety_factor_total'):
            assert _finite(ca[k]) and ca[k] > 0, f"chamber_analysis.{k} sayısal değil"

    def test_top_level_dual_sf_report(self, structural_json):
        """app.js SF exportu structural_analysis üst seviyesinden okur."""
        sa = structural_json['structural_analysis']
        _assert_keys(sa, ['safety_factor_pressure', 'safety_factor_total',
                          'safety_factor'], 'structural_analysis (üst seviye SF)')
        assert _finite(sa['safety_factor_pressure'])
        assert _finite(sa['safety_factor_total'])
        # Geriye dönük tek-SF alanı toplam SF'ye eşit olmalı
        assert sa['safety_factor'] == pytest.approx(sa['safety_factor_total'])

    def test_safety_analysis_keys(self, structural_json):
        sf = structural_json['structural_analysis']['safety_analysis']
        _assert_keys(sf, ['status', 'risk_level', 'minimum_safety_factor',
                          'safety_factors', 'recommendations'],
                     'safety_analysis')
        # Panel mod etiketleri: chamber_hoop / chamber_von_mises / end_cap /
        # nozzle / buckling_axial
        modes = sf['safety_factors']
        _assert_keys(modes, ['chamber_hoop', 'chamber_von_mises', 'end_cap',
                             'nozzle', 'buckling_axial'],
                     'safety_analysis.safety_factors')
        assert _finite(sf['minimum_safety_factor'])
        assert sf['minimum_safety_factor'] == pytest.approx(
            min(v for v in modes.values() if _finite(v)), rel=1e-9)

    def test_buckling_analysis_keys(self, structural_json):
        buck = structural_json['structural_analysis']['buckling_analysis']
        _assert_keys(buck, [
            'buckling_status', 'applied_axial_stress_MPa',
            'critical_axial_buckling_stress_MPa',
            'axial_buckling_safety_factor', 'knockdown_factor_gamma',
            'critical_external_pressure_bar', 'source',
        ], 'buckling_analysis')
        # ÖH D31 / P5B1-15 — BEKÇİ ÇEVRİLDİ (sözleşme genişledi).
        # ``buckling_status`` artık İKİ modun (eksenel + dış basınç)
        # BİRLEŞİK hükmüdür ve dış basınç yük durumu beyan edilmediğinde
        # 'NOT_EVALUATED' der. Eski üçlü küme, kazanılmamış bir 'SAFE'i
        # sözleşme hâline getiriyordu: aynı gövdede kritik dış basınç
        # 1 atm'in altındayken hüküm SAFE basılıyordu (ölçüm
        # docs/scofield/raw/OH/D31/yapisal-sistem/a1/once.json K1).
        # Küme genişledi ama GEVŞEMEDİ: hüküm sözlüğü kapalıdır ve
        # eksenel modun kendi adlı hükmü ayrıca sınanır.
        assert buck['buckling_status'] in ('SAFE', 'MARGINAL', 'CRITICAL',
                                           'NOT_EVALUATED')
        assert buck['axial_buckling_status'] in ('SAFE', 'MARGINAL',
                                                 'CRITICAL')
        assert buck['external_buckling_status'] in ('SAFE', 'MARGINAL',
                                                    'CRITICAL',
                                                    'NOT_EVALUATED')
        # NASA SP-8007 düşürme katsayısı fiziksel aralıkta
        assert 0.0 < buck['knockdown_factor_gamma'] <= 1.0

    def test_fatigue_fastener_endcap_keys(self, structural_json):
        """Üç alt blok: anahtarlar VAR **ve** değerleri kullanılabilir.

        ÖH Faz B / adım B5 — defter P13B2-01. Bu bekçi savcının iki
        adresinden biriydi (``:291``): altı cıvata alanını ADIYLA anıyor
        ama hiçbirinin değerini sormuyordu, dolayısıyla
        ``bolt_safety_factor = -1e12`` ve ``recommended_bolt_size =
        "kırmızı balık"`` yeşil geçiyordu.

        Bu turda güçlenen kardeş kalemler:
          * **P5B1-06** (yüksek) — ``bolt_safety_factor`` bir DOĞRULAMA
            değil, geri okunan tasarım hedefidir (aynı depodaki
            ``bolted_joint`` modeli aynı bağlantı için proof ihlali
            diyebiliyor). Sayı tek başına yayımlanamaz: künyesi
            (``bolt_safety_factor_source``) yanında durmak zorunda.
          * **P5B1-21** (düşük) — cıvata aralığı gerekli cıvata çapından
            büyük olmalı (aksi hâlde cıvatalar geometrik olarak birbirine
            girer). Nominal vaka burada; kusurun göründüğü uç vaka ayrı
            bekçide (``test_bolt_layout_does_not_interfere_at_high_
            pressure``, xfail).

        Not (kapsam dışı, B-3): ``estimated_cycles``/``estimated_life``
        aynı sayının iki adıdır; burada yalnız TİP sözleşmesi sınanır
        (sayı ya da açık ``'Infinite'`` beyanı), ad ikiliği sınanmaz.
        """
        sa = structural_json['structural_analysis']

        fat = sa['fatigue_analysis']
        _assert_keys(fat,
                     ['fatigue_status', 'estimated_cycles', 'estimated_life',
                      'fatigue_safety_factor', 'fatigue_limit'],
                     'fatigue_analysis',
                     positive=('fatigue_safety_factor', 'fatigue_limit'),
                     text=('fatigue_status',))
        assert fat['fatigue_status'] in FATIGUE_STATUSES, (
            f"fatigue_analysis.fatigue_status ürünün ürettiği küme dışında "
            f"({fat['fatigue_status']!r}); panel bunu rozet olarak çizer")
        for k in ('estimated_cycles', 'estimated_life'):
            v = fat[k]
            assert v == 'Infinite' or (_finite(v) and v >= 0.0), (
                f"fatigue_analysis.{k} ne sayı ne de açık 'Infinite' beyanı "
                f"({v!r}) — ömür alanı serbest metin olamaz")

        fas = sa['fastener_analysis']
        _assert_keys(fas,
                     ['num_bolts', 'recommended_bolt_size',
                      'bolt_safety_factor', 'force_per_bolt', 'total_force',
                      'bolt_spacing'],
                     'fastener_analysis',
                     positive=('num_bolts', 'bolt_safety_factor',
                               'force_per_bolt', 'total_force', 'bolt_spacing',
                               'required_bolt_diameter'),
                     # P5B1-06: emniyet katsayısı künyesiz yayımlanamaz.
                     text=('recommended_bolt_size',
                           'bolt_safety_factor_source'))
        assert isinstance(fas['num_bolts'], int) \
            and not isinstance(fas['num_bolts'], bool), (
                f"fastener_analysis.num_bolts tam sayı değil "
                f"({fas['num_bolts']!r}) — cıvata sayısı kesirli olamaz")
        assert BOLT_SIZE_PATTERN.match(fas['recommended_bolt_size']), (
            "fastener_analysis.recommended_bolt_size ISO metrik cıvata "
            f"künyesi değil ({fas['recommended_bolt_size']!r}); ürün bu alanı "
            "f\"M{çap_mm}\" biçiminde üretir (structural_analysis.py:1416)")
        # Tanım gereği: toplam kuvvet = cıvata başına kuvvet × cıvata sayısı.
        assert fas['total_force'] == pytest.approx(
            fas['num_bolts'] * fas['force_per_bolt'], rel=1e-9), (
                f"fastener_analysis.total_force ({fas['total_force']!r}) "
                f"num_bolts × force_per_bolt ile tutarsız "
                f"({fas['num_bolts']} × {fas['force_per_bolt']!r}) — iki alan "
                "panelde yan yana çiziliyor")
        # P5B1-21 nominal yön: cıvatalar birbirine girmemeli.
        assert fas['bolt_spacing'] > fas['required_bolt_diameter'], (
            f"cıvata aralığı ({fas['bolt_spacing']!r} mm) gerekli cıvata "
            f"çapından ({fas['required_bolt_diameter']!r} mm) küçük — "
            "cıvatalar geometrik olarak birbirine giriyor")

        ec = sa['end_cap_analysis']
        _assert_keys(ec,
                     ['recommended_type', 'dished_head_thickness',
                      'flat_head_thickness', 'head_safety_factor'],
                     'end_cap_analysis',
                     positive=('dished_head_thickness', 'flat_head_thickness',
                               'head_safety_factor'),
                     text=('recommended_type',))
        assert ec['recommended_type'] in END_CAP_TYPES, (
            f"end_cap_analysis.recommended_type ürünün ürettiği küme dışında "
            f"({ec['recommended_type']!r})")
        # Düz kapak eğilmeyle, 2:1 elipsoidal kapak membranla taşır: aynı
        # basınç ve malzemede düz kapak DAİMA daha kalın olmak zorundadır
        # (Roark Tablo 11.2 ⟷ ASME VIII-1 UG-32(d)). Sıralamanın bozulması
        # iki formülden birinin birim/geometri hatası demektir.
        assert ec['flat_head_thickness'] > ec['dished_head_thickness'], (
            f"düz kapak ({ec['flat_head_thickness']!r} mm) elipsoidal "
            f"kapaktan ({ec['dished_head_thickness']!r} mm) ince çıktı — "
            "eğilme/membran sıralaması ters")

    #: Ucun kabul ettiği en yüksek hazne basıncı [bar]. Üst sınır kapısı
    #: ÖH Z5S / S3 (P16S1-01) ile kondu; ``hrma/app.py``
    #: ``_ust_sinir_ihlalleri`` -> ``_ust_sinir_bandi`` deponun KANONİK
    #: tablosunu okur ("yeni eşik icat edilmiyor", app.py:2171-2177).
    #:
    #: ÖH D17 (bekci-cevirisi a1 — defter OH-Z5-16 ŞART'ı): değer artık
    #: ölçülerek sabitlenmiyor, O KANONİK TABLODAN okunuyor. Tablo
    #: değişirse bekçi kendiliğinden yeni bandın tavanını sınar; ikinci
    #: bir 500 yazısı depoda kalmaz (Doktrin 4 — tek kaynak).
    #: Ölçüm kaydı yine yerinde:
    #: ``docs/scofield/raw/OH/D15/bekci-cevirisi/a1/olcum_civata.py``
    #: (500 bar -> 200, 501 bar -> 422 invalid_structural_input) ve
    #: ÖH D29 / OH-D19-26 (g) — SARKAN ATIF DÜZELTİLDİ. Burada
    #: ``docs/scofield/raw/OH/D17/bekci-cevirisi/a1/once_ohz516.json`` YOK
    #: (ölçüldü: o dizinde 22 dosya var, hiçbiri ohz516). OH-Z5-16
    #: kaydı gerçekte şurada:
    #: ``docs/scofield/raw/OH/D17/bekci-cevirisi/a1/rapor.md`` (OH-Z5-16
    #: bölümü) ve ters-mutasyon kanıtı
    #: ``docs/scofield/raw/OH/D17/bekci-cevirisi/a1/mutasyon.json``.
    BAND_TAVANI_BAR = _band_tavani_bar()

    @pytest.fixture(scope='class')
    def structural_json_high_pressure(self, client):
        """Ucun KABUL ETTİĞİ en yüksek basınç vakası: 500 bar, D = 400 mm.

        ÇEVİRİ (ÖH D15 / bekci-cevirisi, defter OH-Z5-16). Savcı P5B1-21'i
        Pc = 1000 bar / D = 400 mm'de ölçmüştü (oran 0,884). O çalışma
        noktası artık UCA GİRMİYOR: S3'ün üst sınır kapısı 500 bar üstünü
        422 ``invalid_structural_input`` ile reddediyor. Fixture eski hâlde
        ``assert r.status_code == 200`` satırında ölüyordu — yani aşağıdaki
        xfail(strict) imi cıvata yerleşimini DEĞİL, fixture çöküşünü
        tutuyordu. Bekçi bandın içine çekildi ki yine cıvata yerleşimini
        ölçsün.

        ÖLÇÜLDÜ (bu depo, çeviriden önce — betik yukarıda; tam tablo
        ``civata_tarama.json``): bandın İÇİNDE aralık/çap oranı hiçbir
        noktada 1'in altına inmiyor —

        ======  =====  ==========  ==========  ======
        Pc bar  D m    aralık mm   ger. çap mm  oran
        ======  =====  ==========  ==========  ======
        40      0,4    117,810      26,667      4,418
        400     0,4    353,429     146,059      2,420
        500     0,4    353,429     163,299      2,164
        500     2,0   1610,066     816,497      1,972
        ======  =====  ==========  ==========  ======

        1,972 bandın ölçülen EN KÖTÜ oranıdır. Yani P5B1-21 bu uçtan artık
        üretilemiyor: modül onarımı PK6'da yapıldı
        (``structural_analysis.py`` ``_BOLT_MIN_PITCH_FACTOR`` + yerleşim
        merdiveni), uç tarafında da 1000 bar kapıya takılıyor.

        ÖH D15 BİRLEŞME (1 Eyl 2026): borç imi SÖKÜLDÜ. 12 kulvar ana ağaçta
        birleşince PK6 onarımı bu ucun arkasına geldi ve im XPASS(strict)
        vermeye başladı — yani "kusur duruyor" iddiası artık YALAN. Kapanış
        ölçütü gereği im kaldırıldı, bekçi normal (yeşil beklenen) bekçi
        oldu: bundan sonra oran 1'in altına düşerse KIRMIZI verir.
        """
        payload = dict(STRUCTURAL_PAYLOAD,
                       chamber_pressure=self.BAND_TAVANI_BAR,
                       chamber_diameter=0.4)
        r = client.post('/analyze_structural_safety', json=payload)
        assert r.status_code == 200, (
            f"uç basınç vakası {r.status_code} döndü")
        return r.get_json()

    def test_bolt_layout_does_not_interfere_at_high_pressure(
            self, structural_json_high_pressure):
        """Cıvatalar hiçbir çalışma noktasında birbirine giremez.

        ÖH Faz B / adım B5 — defter P5B1-21 (düşük). Savcı ölçtü:
        Pc = 1000 bar, D = 400 mm'de gerekli cıvata çapı 133,33 mm iken
        ``bolt_spacing`` 117,81 mm çıkıyor (oran 0,884) — yani ürün
        birbirinin içine giren bir cıvata deseni yayımlıyor ve hiçbir
        uyarı vermiyor. Nominal vakada (Pc = 40 bar) oran 7,09 olduğu için
        ``test_fatigue_fastener_endcap_keys``in aynı iddiası bugün yeşil;
        kusuru gören vaka BUDUR.

        Ölçüm (2026-08-27, bu depo): Pc 40/200/1000 bar için oran
        7,093 / 2,195 / **0,884**.

        ÖH D15 BİRLEŞME (1 Eyl 2026): PK6 yerleşim merdiveni ana ağaca
        girdikten sonra bandın tavanında (500 bar / D = 400 mm) oran
        2,164 ölçüldü; kusur kapandı ve xfail(strict) borç imi söküldü.
        """
        fas = structural_json_high_pressure[
            'structural_analysis']['fastener_analysis']
        assert fas['bolt_spacing'] > fas['required_bolt_diameter'], (
            f"cıvata aralığı {fas['bolt_spacing']:.3f} mm, gerekli cıvata "
            f"çapı {fas['required_bolt_diameter']:.3f} mm "
            f"(oran {fas['bolt_spacing'] / fas['required_bolt_diameter']:.3f})"
            " — cıvatalar birbirine giriyor; ürün ne uyarı ne de cıvata "
            "sayısı/çapı düzeltmesi üretiyor")

    def test_material_and_design_keys(self, structural_json):
        sa = structural_json['structural_analysis']
        # Panel "gerekli SF" değerini malzeme kartından okur
        assert _finite(sa['material_properties']['safety_factor'])
        dp = sa['design_parameters']
        _assert_keys(dp, ['material', 'design_pressure',
                          'design_pressure_factor'], 'design_parameters')
        assert dp['material'] == STRUCTURAL_PAYLOAD['material']
        # Tasarım basıncı = işletme x faktör (bar)
        assert dp['design_pressure'] == pytest.approx(
            STRUCTURAL_PAYLOAD['chamber_pressure'] * dp['design_pressure_factor'])

    def test_weight_analysis_keys(self, structural_json):
        wt = structural_json['structural_analysis']['weight_analysis']
        _assert_keys(wt, ['total_weight', 'chamber_weight', 'nozzle_weight',
                          'end_caps_weight'], 'weight_analysis')
        assert wt['total_weight'] == pytest.approx(
            wt['chamber_weight'] + wt['nozzle_weight'] + wt['end_caps_weight'])


class TestThermalResponseContract:
    def test_status_success(self, thermal_json):
        assert thermal_json['status'] == 'success'
        assert 'thermal_analysis' in thermal_json

    def test_sections_panel_reads(self, thermal_json):
        ta = thermal_json['thermal_analysis']
        _assert_keys(ta, [
            'heat_transfer_coefficients', 'gas_side_analysis',
            'wall_analysis', 'cooling_analysis', 'safety_analysis',
            'material_properties', 'design_parameters',
        ], 'thermal_analysis')

    def test_bartz_coefficient(self, thermal_json):
        htc = thermal_json['thermal_analysis']['heat_transfer_coefficients']
        _assert_keys(htc, ['gas_side', 'correlation'],
                     'heat_transfer_coefficients')
        assert _finite(htc['gas_side']) and htc['gas_side'] > 0
        assert 'Bartz' in str(htc['correlation'])

    def test_gas_side_keys(self, thermal_json):
        gsa = thermal_json['thermal_analysis']['gas_side_analysis']
        _assert_keys(gsa, ['gas_temperature', 'adiabatic_wall_temperature',
                           'throat_heat_flux', 'chamber_heat_flux',
                           'surface_area'], 'gas_side_analysis')
        # Boğaz akısı hazne akısından yüksek olmalı (Bartz ~ A_t/A oranı)
        assert gsa['throat_heat_flux'] > gsa['chamber_heat_flux'] > 0

    def test_wall_temperatures_ordered(self, thermal_json):
        ta = thermal_json['thermal_analysis']
        wa = ta['wall_analysis']
        gsa = ta['gas_side_analysis']
        _assert_keys(wa, ['inner_temperature', 'outer_temperature'],
                     'wall_analysis')
        # İç cidar dış cidardan sıcak; hiçbiri gaz sıcaklığını aşamaz
        assert wa['inner_temperature'] > wa['outer_temperature']
        assert wa['inner_temperature'] <= gsa['gas_temperature'] + 1e-6

    def test_cooling_keys(self, thermal_json):
        """Soğutma bloğu: anahtarlar VAR **ve** değerleri kullanılabilir.

        ÖH Faz B / adım B5 — defter P13B2-01. Savcının ikinci adresi
        (``:365``): beş alanın yalnız varlığı sayılıyordu, dolayısıyla NaN
        ısı akısı ve ``required_cooling_area = 0,0 m²`` (P4B1-06'nın
        ürettiği değer, 3370 kW yükte) yeşil geçiyordu.

        Güçlenen kalem: **P4B1-06** (yüksek) — nominal (tanınan) soğutma
        tipinde gerekli soğutma alanı pozitif olmak zorunda. Bilinmeyen
        tipte sessiz düşüş ayrı bekçide (aşağıda, xfail).
        """
        cool = thermal_json['thermal_analysis']['cooling_analysis']
        _assert_keys(cool, ['cooling_efficiency', 'peak_heat_rate',
                            'total_heat_energy', 'required_cooling_area',
                            'heat_sink_mass'], 'cooling_analysis',
                     positive=('peak_heat_rate', 'total_heat_energy',
                               'required_cooling_area', 'heat_sink_mass'),
                     fraction=('cooling_efficiency',))
        # Tanım gereği: enerji = güç × süre. Ürün MJ (total_heat_energy) ve
        # kW (peak_heat_rate) yayımlar; 1 MJ = 1 kW · 1000 s.
        assert cool['total_heat_energy'] * 1e3 == pytest.approx(
            cool['peak_heat_rate'] * THERMAL_PAYLOAD['burn_time'],
            rel=1e-9), (
                f"total_heat_energy ({cool['total_heat_energy']!r} MJ) ile "
                f"peak_heat_rate × burn_time "
                f"({cool['peak_heat_rate']!r} kW × "
                f"{THERMAL_PAYLOAD['burn_time']} s) tutarsız — panelde iki "
                "alan yan yana çiziliyor, biri diğerinin birimini bozarsa "
                "kullanıcı 1000 kat hatalı ısı yükü okur")

    @pytest.fixture(scope='class')
    def thermal_json_unknown_cooling(self, client):
        """Tanınmayan ama gerçek bir soğutma seçeneği: film soğutma."""
        r = client.post('/analyze_thermal_safety',
                        json=dict(THERMAL_PAYLOAD, cooling_type='film'))
        assert r.status_code in (200, 400, 422), (
            f"beklenmedik durum kodu {r.status_code}")
        return {'status': r.status_code, 'json': r.get_json()}

    def test_unknown_cooling_type_is_not_silently_natural(
            self, thermal_json_unknown_cooling):
        """Tanınmayan soğutma tipi ya REDDEDİLMELİ ya da hesaplanmalı.

        ÖH Faz B / adım B5 — defter P4B1-06 (yüksek). Film, ablatif ve
        radyasyon soğutma bir roket haznesinde gerçek seçeneklerdir;
        ürün üçünü de beyaz listeye almadan kabul ediyor, sessizce doğal
        taşınım katsayısına (h = 25 W/m²K) düşüyor ve
        ``required_cooling_area = 0,0 m²`` yayımlıyor — bu arada
        ``design_parameters.cooling_type`` kullanıcıya *seçtiği* tipi geri
        okuyor. Panel "0,00 m²" stat kartını çiziyor.

        Ölçüm (2026-08-27, bu depo): ``film`` / ``ablative`` /
        ``radiation`` / ``"kırmızı balık"`` → HTTP **200**,
        ``required_cooling_area = 0.0``, ``design_delta_T_K = None``,
        yankı alanı kullanıcının dizesini aynen geri veriyor.

        Kabul: uç ya bilinmeyen tipi reddeder (400/422) ya da tipe ait
        gerçek bir tasarım ΔT'siyle pozitif bir soğutma alanı üretir.

        ÖH D15 BİRLEŞME (1 Eyl 2026): borç imi SÖKÜLDÜ. Termo-uçuş
        kulvarı bu kalemi onardı ve 12 kulvar ana ağaçta birleşince im
        XPASS(strict) vermeye başladı — "kusur duruyor" iddiası artık
        YALAN. Kapanış ölçütü gereği im kaldırıldı; bekçi normal
        (yeşil beklenen) bekçi oldu ve kusur geri gelirse KIRMIZI verir.
        """
        durum = thermal_json_unknown_cooling['status']
        if durum in (400, 422):
            return  # fail-closed: kabul
        cool = thermal_json_unknown_cooling[
            'json']['thermal_analysis']['cooling_analysis']
        assert _finite(cool['required_cooling_area']) \
            and cool['required_cooling_area'] > 0.0, (
                "bilinmeyen cooling_type 200 ile kabul edildi ve gerekli "
                f"soğutma alanı {cool['required_cooling_area']!r} m² çıktı "
                f"(design_delta_T_K={cool.get('design_delta_T_K')!r}) — "
                "sessiz doğal taşınıma düşüş")

    def test_cooling_efficiency_carries_a_source(self, thermal_json):
        """``cooling_efficiency`` künyesiz yayımlanamaz.

        ÖH Faz B / adım B5 — defter P4B1-20 (düşük). Değer üç satırlık
        kaynaksız bir tablodan geliyor (natural 0,3 / forced 0,6 /
        regenerative 0,9); ısı yükünden, hazne boyundan, malzemeden ve
        cidar kalınlığından TAMAMEN bağımsız. Arayüz bu TEK sayıyı üç
        bölgeye kopyalayıp "Cooling Effectiveness" çubuk grafiği çiziyor.

        Asimetri ölçüldü (2026-08-27, bu depo): aynı sözlükteki üç kardeş
        alan künye taşıyor — ``heat_sink_delta_T_basis``,
        ``heat_sink_initial_temperature_basis``,
        ``heat_sink_specific_heat_source`` — ``cooling_efficiency`` için
        eşi yok. Depoda tescilli sağlıklı desen budur; eksik olan onun
        buraya uygulanmamış olması.

        ÖH D15 BİRLEŞME (1 Eyl 2026): borç imi SÖKÜLDÜ. Termo-uçuş
        kulvarı bu kalemi onardı ve 12 kulvar ana ağaçta birleşince im
        XPASS(strict) vermeye başladı — "kusur duruyor" iddiası artık
        YALAN. Kapanış ölçütü gereği im kaldırıldı; bekçi normal
        (yeşil beklenen) bekçi oldu ve kusur geri gelirse KIRMIZI verir.
        """
        cool = thermal_json['thermal_analysis']['cooling_analysis']
        kunye = [k for k in ('cooling_efficiency_basis',
                             'cooling_efficiency_source') if k in cool]
        assert kunye, (
            "cooling_efficiency künyesiz yayımlanıyor; aynı sözlükte künye "
            "taşıyan kardeşler: "
            f"{sorted(k for k in cool if k.endswith(('_basis', '_source')))}")

    def test_thermal_safety_keys(self, thermal_json):
        safe = thermal_json['thermal_analysis']['safety_analysis']
        _assert_keys(safe, ['risk_level', 'melting_safety_factor',
                            'temperature_safety_factor',
                            'stress_safety_factor', 'thermal_stress'],
                     'thermal safety_analysis')
        matp = thermal_json['thermal_analysis']['material_properties']
        _assert_keys(matp, ['allowable_temperature', 'melting_point'],
                     'material_properties')
        # Ergime noktası izin verilen sıcaklıktan yüksek olmalı
        assert matp['melting_point'] > matp['allowable_temperature']

    def test_design_parameters_echo(self, thermal_json):
        dpp = thermal_json['thermal_analysis']['design_parameters']
        _assert_keys(dpp, ['cooling_type', 'wall_thickness', 'material'],
                     'thermal design_parameters')
        assert dpp['cooling_type'] == THERMAL_PAYLOAD['cooling_type']
        assert dpp['material'] == THERMAL_PAYLOAD['material']

    def test_wall_thickness_carries_a_source(self, thermal_json):
        """``wall_thickness`` künyesiz yayımlanamaz — kardeşi künyeli.

        ÖH Faz B-4 — defter P4B1-18 (düşük). Aynı sözlükteki
        ``ambient_temperature`` alanı, bir GİRDİ YANKISI olduğunu ve
        çağıran bir şey vermediğinde modülün kendi 293,15 K varsayılanında
        kaldığını anlatan ayrıntılı bir ``ambient_temperature_basis``
        künyesiyle geliyor (``heat_transfer_analysis.py:851-869``).
        ``wall_thickness`` aynı yankı sınıfındadır — modülün kendi
        varsayılanı 5,0 mm (``:723`` imza varsayılanı) — ama künyesi YOK;
        üstelik alan panele doğrudan bağlı (``analysis_dock.js:899``), yani
        kullanıcı 5,0 mm'yi kendi girdisi sanıyor.

        Ölçüldü (2026-08-27, bu depo): ``design_parameters`` anahtarları
        ``material``, ``wall_thickness``, ``cooling_type``,
        ``ambient_temperature``, ``ambient_temperature_basis`` — künye
        asimetrisi 1/1 (iki yankı alanının biri künyeli, öteki değil).

        Kabul: ``wall_thickness_basis`` (ya da eşdeğer adlı künye)
        yayımlanır ve değerin bir GİRDİ YANKISI olduğunu söyler.

        ÖH D15 BİRLEŞME (1 Eyl 2026): borç imi SÖKÜLDÜ. Termo-uçuş
        kulvarı bu kalemi onardı ve 12 kulvar ana ağaçta birleşince im
        XPASS(strict) vermeye başladı — "kusur duruyor" iddiası artık
        YALAN. Kapanış ölçütü gereği im kaldırıldı; bekçi normal
        (yeşil beklenen) bekçi oldu ve kusur geri gelirse KIRMIZI verir.
        """
        dpp = thermal_json['thermal_analysis']['design_parameters']
        adaylar = [k for k in dpp
                   if k.startswith('wall_thickness')
                   and k.endswith(('_basis', '_source'))]
        assert adaylar, (
            "design_parameters.wall_thickness künyesiz yayımlanıyor "
            "(yayımlanan anahtarlar: %s); aynı sözlükteki kardeşi "
            "ambient_temperature_basis ile taşınıyor" % sorted(dpp))
        metin = ' '.join(str(dpp[k]) for k in adaylar).lower()
        assert 'input' in metin or 'girdi' in metin or 'default' in metin, (
            "wall_thickness künyesi (%s) değerin bir girdi yankısı / modül "
            "varsayılanı olduğunu söylemiyor: %r" % (adaylar, metin[:200]))


class TestSafetyResponseContract:
    RISK_AREAS = ['structural', 'pressure', 'thermal', 'explosive',
                  'toxic', 'fire']

    def test_status_success(self, safety_json):
        assert safety_json['status'] == 'success'
        assert 'safety_analysis' in safety_json

    def test_risk_assessment_keys(self, safety_json):
        risk = safety_json['safety_analysis']['risk_assessment']
        _assert_keys(risk, ['risk_level', 'acceptability',
                            'overall_risk_score', 'individual_risks',
                            'mitigation_priority'], 'risk_assessment')
        assert risk['risk_level'] in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')

    def test_individual_risks_in_band(self, safety_json):
        """Risk skorları banda düşer, DÜZLEŞMEZ ve genel skor beyanına uyar.

        ÖH Faz B / adım B5 — defter P5B2-12 (orta), P14M2-12 ile mutasyon
        onaylı. ``1.0 <= risks[area] <= 5.0`` bandı tek başına KÖR: P14
        ölçtü ki termal ve yangın skorları 1,0'a düzleştirildiğinde bekçi
        yeşil kalıyor (bant "içinde" oldukları için). Bir band iddiası
        "değerlendirme yapıldı" demez; altı eksenin hepsi aynı sayıya
        çökse de geçer.

        Eklenen eksenler:
          * **saçılım** — altı eksen aynı skora çökemez (düzleşme reddi);
          * **birleştirme beyanı ⟷ davranış** — ürün toplama kuralını
            ``aggregation_basis`` alanında "worst-axis (max of individual
            risk scores)" diye ilan ediyor; genel skor gerçekten
            eksenlerin maksimumu olmak zorunda.

        Ölçüm (2026-08-27, bu depo): explosive 3,0 · fire 2,0 ·
        pressure 2,0 · structural 1,0 · thermal 2,0 · toxic 1,0 →
        yayılım 2,0; genel skor 3,0 = maksimum.
        """
        ra = safety_json['safety_analysis']['risk_assessment']
        risks = ra['individual_risks']
        # Z3 onarımı (2026-08-27): değerlendirilemeyen eksen artık SAYI
        # UYDURMAZ — None + risks_not_evaluated beyanı yayımlar (deponun
        # kendi kuralı: "a missing computation is not a low risk").
        # Sözleşme: None YALNIZ beyanlı eksende meşrudur; beyansız None
        # ya da beyanlı-ama-sayılı eksen KIRMIZI.
        beyan = set(ra.get('risks_not_evaluated') or ())
        degerlendirilen = [a for a in self.RISK_AREAS if a not in beyan]
        for area in self.RISK_AREAS:
            if area in beyan:
                assert risks[area] is None, (
                    f"{area} 'değerlendirilmedi' beyanlı ama skor "
                    f"{risks[area]!r} basılmış — beyan ile sayı çelişiyor")
                continue
            assert risks[area] is not None and 1.0 <= risks[area] <= 5.0, (
                f"{area} skoru 1-5 dışı ({risks[area]!r})")
        assert degerlendirilen, 'tüm eksenler değerlendirilemedi beyanlı'
        overall = ra['overall_risk_score']
        assert _finite(overall) and 1.0 <= overall <= 5.0, (
            f"overall_risk_score 1-5 dışı ({overall!r})")

        # Düzleşme reddi: tek bir sabit altı eksene dağıtılmış olamaz.
        degerler = [risks[a] for a in degerlendirilen]
        assert max(degerler) > min(degerler), (
            f"altı risk ekseninin hepsi aynı skoru taşıyor ({degerler}) — "
            "bu bir değerlendirme değil, banda düşen tek bir sabittir")

        # Beyan ⟷ davranış: ilan edilen toplama kuralı EN KÖTÜ EKSEN.
        assert 'max' in ra.get('aggregation_basis', ''), (
            "toplama kuralı beyanı (aggregation_basis) değişmiş: "
            f"{ra.get('aggregation_basis')!r} — aşağıdaki iddia 'worst-axis "
            "(max)' beyanına dayanıyor, beyan değiştiyse iddia da güncellenir")
        assert overall == pytest.approx(max(degerler)), (
            f"overall_risk_score ({overall!r}) eksenlerin maksimumu "
            f"({max(degerler)!r}) değil — ürün toplama kuralını "
            "'worst-axis (max of individual risk scores)' diye ilan ediyor")

    def test_risk_scores_respond_to_inputs(self, safety_json_mild,
                                           safety_json_heavy_charge):
        """Risk skoru girdinin FONKSİYONU olmalı — sabit değil.

        ÖH Faz B / adım B5 — P14M2-12'nin doğrudan karşılığı: bir ekseni
        1,0'a çivilemek bugün hiçbir bekçiyi kırmızıya döndürmüyordu.
        Saçılım iddiası "hepsi aynı" hâlini görür; bu bekçi bir ADIM
        ötesini görür: itici kütlesi 100 katına çıktığında patlayıcı
        ekseni YÜKSELMEK zorunda.

        Ölçüm (2026-08-27, bu depo): itici kütlesi 5 kg → 500 kg'da
        patlayıcı ekseni 3,0 → 5,0, genel hüküm MEDIUM → CRITICAL.
        """
        taban = safety_json_mild['safety_analysis']['risk_assessment']
        agir = safety_json_heavy_charge['safety_analysis']['risk_assessment']
        assert agir['individual_risks']['explosive'] > \
            taban['individual_risks']['explosive'], (
                "itici kütlesi 100 katına çıktığında patlayıcı risk ekseni "
                f"{taban['individual_risks']['explosive']!r} → "
                f"{agir['individual_risks']['explosive']!r} olarak DEĞİŞMEDİ "
                "— eksen girdiye sağır (sabit üretiliyor)")
        assert agir['overall_risk_score'] > taban['overall_risk_score'], (
            "genel risk skoru itici kütlesindeki 100 kat artışa tepki "
            "vermiyor")

    def test_thermal_axis_ladder_reaches_the_ceiling(self, client):
        """ONARILDI/ÇÜRÜTÜLDÜ (ÖH D26 / P5B2-12): eksen 4,0 tavanlı DEĞİL.

        Kalemin cümlesi "termal ve yangın eksenleri 4,0 tavanlı: cidar
        1e6 K olsa bile genel hüküm en fazla HIGH kalıyor, CRITICAL/
        UNACCEPTABLE hiç üretilemiyor" idi. ÖLÇÜLDÜ (D26 tabanı 7751531,
        canlı ``/analyze_safety``, ısı zinciri TAM yük, composite/HTPB
        varsayılan malzeme; erime noktası 1705 K)::

            hazne 400 K  -> cidar  397,6 K  SF 2,040  termal eksen 2,0
            hazne 600 K  -> cidar  596,2 K  SF 1,360  termal eksen 2,0
            hazne 800 K  -> cidar  794,6 K  SF 1,021  termal eksen 4,0
            hazne 1500 K -> cidar 1489,1 K  SF 0,545  termal eksen 4,0
            hazne 2000 K -> cidar 1984,9 K  SF 0,409  termal eksen 5,0
            hazne 3000 K -> cidar 2976,3 K  SF 0,272  termal eksen 5,0

        Yani eksen hem ısıl girdiye TEPKİ VERİYOR hem de bandın tavanına
        (5,0) ULAŞIYOR; genel hüküm 5,0'a çıkıyor. 4,0 tavanı iddiası bu
        ağaçta ÜRETİLEMEZ (Z3 / OH-B2-03 onarımının uçtaki kanıtı).

        Bu bekçi merdivenin üç düğümünü birden kilitler; biri sağırlaşırsa
        (sabit skor) ya da tavan yeniden 4,0'a düşerse kırmızı olur.
        """
        def eksen(chamber_temperature, wall_thickness=0.005):
            yuk = dict(THERMAL_CHAIN_PAYLOAD,
                       chamber_temperature=chamber_temperature,
                       wall_thickness=wall_thickness)
            r = client.post('/analyze_safety', json=yuk)
            assert r.status_code == 200, (chamber_temperature, r.status_code)
            j = r.get_json()['safety_analysis']
            return (j['risk_assessment']['individual_risks']['thermal'],
                    j['risk_assessment']['overall_risk_score'],
                    j['thermal_safety']['thermal_verdict'])

        dusuk, orta, yuksek = eksen(400), eksen(1000), eksen(3000)
        for ad, kayit in (('400 K', dusuk), ('1000 K', orta),
                          ('3000 K', yuksek)):
            assert kayit[2] == 'issued', (
                f'{ad}: ısı zinciri TAM yükle bile hüküm üretilmedi '
                f'({kayit[2]!r}) — motor tarafı bozulmuş')
        assert dusuk[0] < orta[0] < yuksek[0], (
            'termal eksen ısıl girdiye SAĞIR: '
            f'400 K -> {dusuk[0]!r}, 1000 K -> {orta[0]!r}, '
            f'3000 K -> {yuksek[0]!r}')
        assert yuksek[0] == 5.0, (
            f'uç ısıl koşulda termal eksen {yuksek[0]!r} — bandın tavanı '
            '(5,0) bu eksen için ulaşılamaz')
        assert yuksek[1] >= 5.0, (
            f'genel hüküm {yuksek[1]!r} — termal eksen 5,0 iken genel '
            'skor CRITICAL/UNACCEPTABLE bandına çıkamıyor')

    # BORÇ İMİ KALDIRILDI — ÖH D27 / arayuz a2 (P5B2-12 PANEL YARISI).
    # Eski im: "kalan borç YALNIZ PANEL YÜKÜDÜR; safety_panel.js 10 alan
    # yolluyor, ısı zinciri (chamber_length + throat_diameter/...) YOK, bu
    # yüzden hüküm fail-closed geri çekiliyor ve eksen None kalıyor."
    # ÖLÇÜLDÜ (taban 709a235e, ``a2/once.json``
    # ``safety_fields_isi_zinciri_sayisi`` = 2 → ``a2/sonra.json``: 4):
    # panel artık ``chamber_length`` ve ``throat_diameter`` alanlarını da
    # taşıyor (boş bırakılabilir; boşsa uç eskisi gibi hükmü geri çeker,
    # sayı UYDURULMAZ). Yukarıdaki ``SAFETY_PAYLOAD`` panelin aynası
    # olduğu için o da güncellendi ve bu düğüm XPASS(strict) ile KIRMIZI
    # veriyordu. Bekçi artık CANLIdır: panel ısı zincirini yeniden
    # göndermeyi bırakırsa termal eksen tepkisiz kalır ve test kırmızıya
    # döner. Taban ``MILD_THERMAL_PAYLOAD``tır çünkü 3000 K'lik eski
    # taban artık kendi başına tavandadır (bkz. o sözlüğün notu).
    def test_thermal_axis_responds_and_can_reach_ceiling(
            self, safety_json_mild, safety_json_extreme_thermal):
        """Termal eksen ısıl girdiye tepki vermeli ve tavana ulaşabilmeli.

        ÖH Faz B / adım B5 — defter P5B2-12 (orta). Kalemin cümlesi:
        termal ve yangın eksenleri 4,0 tavanlı (diğer dördü 5,0 üretiyor),
        yani cidar 1e6 K olsa bile genel hüküm en fazla HIGH çıkabiliyor.

        Savcının cümlesinden DAHA AĞIR bir hâl ölçüldü (2026-08-27, bu
        depo): ``/analyze_safety`` ucunda termal eksen
        ``chamber_temperature`` = 3000 K → 1e6 K değişiminde **2,0'da
        sabit kalıyor** (skor ``cooling_required`` /
        ``thermal_protection_required`` bayraklarından geliyor, bu uçta
        hiçbiri set edilmiyor). Yangın ekseni ancak 3,0'a çıkabildi.
        Karşılaştırma: basınç ve yapısal eksenler aynı koşumda 5,0 üretti.

        Bu bekçi iki şeyi ister: (1) eksen ısıl girdiye tepki versin,
        (2) bandın tavanı (5,0) termal eksen için de ulaşılabilir olsun.
        """
        taban = safety_json_mild['safety_analysis']['risk_assessment'][
            'individual_risks']
        uc = safety_json_extreme_thermal['safety_analysis'][
            'risk_assessment']['individual_risks']
        assert uc['thermal'] > taban['thermal'], (
            f"hazne sıcaklığı {MILD_THERMAL_PAYLOAD['chamber_temperature']} K → "
            f"{EXTREME_THERMAL_PAYLOAD['chamber_temperature']:g} K "
            f"olduğunda termal risk ekseni {taban['thermal']!r} → "
            f"{uc['thermal']!r} (değişmedi) — eksen ısıl girdiye sağır")
        assert uc['thermal'] == 5.0, (
            f"uç ısıl koşulda termal eksen {uc['thermal']!r} — bandın "
            "tavanı (5,0) bu eksen için ulaşılamaz; diğer eksenler aynı "
            "koşumda 5,0 üretiyor")

    def test_mitigation_priority_sorted(self, safety_json):
        pri = safety_json['safety_analysis']['risk_assessment']['mitigation_priority']
        assert isinstance(pri, list) and len(pri) >= 1
        for i, p in enumerate(pri, start=1):
            _assert_keys(p, ['priority', 'area', 'risk_score'],
                         'mitigation_priority öğesi')
            assert p['priority'] == i
        scores = [p['risk_score'] for p in pri]
        assert scores == sorted(scores, reverse=True), (
            'mitigation_priority skorları azalan sırada olmalı')

    def test_pressure_vessel_ladder(self, safety_json):
        press = safety_json['safety_analysis']['pressure_safety']
        _assert_keys(press, ['operating_pressure_bar', 'design_pressure_bar',
                             'proof_pressure_bar',
                             'hydrostatic_test_pressure_bar',
                             'required_burst_pressure_bar'],
                     'pressure_safety')
        # Basınç merdiveni: işletme < tasarım <= proof <= hidrostatik;
        # burst hedefi tasarımın üstünde
        assert press['operating_pressure_bar'] == pytest.approx(
            SAFETY_PAYLOAD['chamber_pressure'])
        assert press['operating_pressure_bar'] < press['design_pressure_bar']
        assert press['design_pressure_bar'] <= press['proof_pressure_bar']
        assert press['proof_pressure_bar'] <= press['hydrostatic_test_pressure_bar']
        assert press['required_burst_pressure_bar'] > press['design_pressure_bar']

    def test_compliance_and_recommendations(self, safety_json):
        s = safety_json['safety_analysis']
        comp = s['compliance']
        _assert_keys(comp, ['nfpa_compliance', 'osha_compliance',
                            'dot_compliance'], 'compliance')
        assert isinstance(s['recommendations'], list)

    def test_compliance_never_claims_conformity(self, safety_json):
        """Uygunluk alanları hüküm ÜRETMEMELİ — yalnız NOT_EVALUATED.

        Bu alanlar eskiden koşulsuz ``True`` dönüyor ve arayüzde yeşil
        "NFPA: OK" rozeti olarak çiziliyordu; backend'in kendi yorumları
        gerçek bir kontrol yapılmadığını söylüyordu. Gerçek uygunluk
        değerlendirmesi requirement karşılaştırması, saha bilgisi ve yetkili
        bir değerlendirici ister — hiçbiri yazılıma girdi değil.
        """
        comp = safety_json['safety_analysis']['compliance']
        for key in ('nfpa_compliance', 'osha_compliance', 'dot_compliance',
                    'local_regulations', 'insurance_requirements'):
            assert comp[key] == 'NOT_EVALUATED', (
                f'{key} bir uygunluk hükmü üretiyor ({comp[key]!r}); '
                'yazılım mevzuat uygunluğu değerlendiremez.'
            )
        # Model riski kabul edilebilirliği mevzuat uygunluğu DEĞİLDİR;
        # eski 'overall_compliance' adı bu ikisini karıştırıyordu.
        assert 'overall_compliance' not in comp
        assert 'model_risk_acceptability' in comp


# ---------------------------------------------------------------------------
# 3. 501 bekçileri
# ---------------------------------------------------------------------------

class TestGuards501:
    @pytest.mark.parametrize('endpoint', GUARDED_501_ENDPOINTS)
    def test_honest_501(self, client, endpoint):
        r = client.post(endpoint, json={'motor_type': 'hybrid'})
        assert r.status_code == 501, f"{endpoint} 501 dönmeli"
        j = r.get_json()
        assert j['status'] == 'unavailable'


# ---------------------------------------------------------------------------
# 4. /calculate sözleşmesi
# ---------------------------------------------------------------------------

class TestCalculateContract:
    def test_completes_within_budget(self, calc_response):
        assert calc_response['elapsed'] < CALCULATE_TIME_BUDGET_S, (
            f"/calculate {calc_response['elapsed']:.1f} sn sürdü "
            f"(bütçe {CALCULATE_TIME_BUDGET_S} sn)")

    def test_gamma_and_mw_top_level(self, calc_response):
        motor = calc_response['json']['motor']
        _assert_keys(motor, ['gamma', 'molecular_weight'], 'motor sonuçları')
        # Fiziksel aralıklar: yanma gazı için γ ve MW
        assert 1.05 < motor['gamma'] < 1.45
        assert 10.0 < motor['molecular_weight'] < 60.0

    def test_dead_plot_keys_absent(self, calc_response):
        plots = calc_response['json']['plots']
        assert 'heat_transfer' not in plots, (
            'plots.heat_transfer geri gelmiş — Dalga 0 ölü yük temizliği bozuldu')
        assert 'structural_analysis' not in plots, (
            'plots.structural_analysis geri gelmiş — Dalga 0 temizliği bozuldu')

    def test_panel_source_fields_present(self, calc_response):
        """Structural panelin fromResults() okuduğu motor alanları."""
        motor = calc_response['json']['motor']
        for k in ('chamber_pressure', 'chamber_diameter', 'chamber_length',
                  'throat_diameter', 'burn_time', 'mdot_total',
                  'chamber_temperature'):
            assert _finite(motor.get(k)) and motor[k] > 0, (
                f"motor.{k} yok ya da sayısal değil — panel önerileri boş kalır")


# ---------------------------------------------------------------------------
# 5. Uçtan uca duman: /calculate -> structural panel akışı
# ---------------------------------------------------------------------------

class TestEndToEndStructuralFlow:
    @pytest.fixture(scope='class')
    def flow_structural(self, client, calc_response):
        """structural_panel.js fromResults() eşlemesinin Python kopyası."""
        motor = calc_response['json']['motor']
        payload = {
            'chamber_pressure': motor['chamber_pressure'],
            'chamber_diameter': motor['chamber_diameter'],
            'chamber_length': motor['chamber_length'],
            'throat_diameter': motor['throat_diameter'],
            'burn_time': motor['burn_time'],
            'material': 'steel_4130',  # panel varsayılanı
        }
        r = client.post('/analyze_structural_safety', json=payload)
        assert r.status_code == 200, (
            f"/calculate değerleriyle yapısal analiz {r.status_code} döndü")
        return r.get_json()

    def test_sf_fields_numeric(self, flow_structural):
        sa = flow_structural['structural_analysis']
        for k in ('safety_factor_pressure', 'safety_factor_total'):
            assert _finite(sa[k]) and sa[k] > 0, f"{k} sayısal/pozitif değil"
        ca = sa['chamber_analysis']
        for k in ('von_mises_safety_factor', 'hoop_safety_factor'):
            assert _finite(ca[k]) and ca[k] > 0

    def test_sf_pressure_ge_sf_total(self, flow_structural):
        """Basınç-yalnız SF, termal gerilme içeren toplam SF'den küçük
        OLAMAZ (termal katkı gerilmeyi artırır, SF'yi düşürür)."""
        sa = flow_structural['structural_analysis']
        assert sa['safety_factor_pressure'] >= sa['safety_factor_total'] - 1e-9

    def test_top_level_matches_chamber_analysis(self, flow_structural):
        """Üst seviye SF raporu chamber_analysis ile tutarlı olmalı
        (app.js exportu üst seviyeden, panel chamber_analysis'ten okur)."""
        sa = flow_structural['structural_analysis']
        ca = sa['chamber_analysis']
        assert sa['safety_factor_pressure'] == pytest.approx(
            ca['safety_factor_pressure'])
        assert sa['safety_factor_total'] == pytest.approx(
            ca['safety_factor_total'])

    def test_minimum_sf_not_above_chamber_sf(self, flow_structural):
        """Tüm modların minimumu, hazne SF'lerinden büyük olamaz."""
        sa = flow_structural['structural_analysis']
        min_sf = sa['safety_analysis']['minimum_safety_factor']
        assert _finite(min_sf)
        assert min_sf <= sa['safety_factor_total'] + 1e-9


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
