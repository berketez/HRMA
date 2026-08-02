"""Faz 4B — ``hrma/app.py`` karar kapıları (B3, B4, C2, D7).

Kapattıkları somut kusurlar. Hepsi HEAD ``a7ff1e7`` üzerinde ölçüldü
(2 Ağustos 2026); kayıt: ``docs/FAZ4_CODEX_TEYIT.md`` §B, §C, §D.

* **B3 — totoloji bayrağı ile hüküm AYNI yanıtta.**
  ``POST /analyze_structural_safety -d '{}'`` şunu döndürüyordu:
  ``safety_factor_is_tautological: true`` **ve** ``status: 'ACCEPTABLE'``,
  ``risk_level: 'LOW'``, ``peak_wall_temperature_K: 300.0``. Yani modül
  "bu emniyet katsayısı bir doğrulama değil" diye yazıyor, aynı yanıtta
  uç kabul kararı veriyordu. Üstelik ortada motor da yoktu: 20 bar /
  100 mm / 500 mm / 20 mm hepsi uç varsayılanıydı. 300.0 K de hesaplanmış
  bir cidar sıcaklığı değil, ``structural_analysis._estimate_wall_delta_T``
  içindeki "gaz sıcaklığı yok -> termal modeli kapat, ortamı döndür"
  dalının çıktısıdır.

* **B4 — yapısal uç kendi kalınlığını boyutlandırıp SAFE diyordu.**
  ``wall_thickness=0.001`` (1 mm) ve ``safety_factor=2.0`` gönderildi;
  modül kendi boyutlandırdığı 5.887 mm'yi kullandı, ``design_mode='size'``
  kaldı ve SF 4.8 (= 4.0 hedef x 1.2 imalat payı) ile 'SAFE' dedi.
  Sebep: uç ``analyze_structure``'a ``actual_wall_thickness`` ve
  ``design_safety_factor`` argümanlarını HİÇ geçirmiyordu. Doğru desen
  aynı depoda vardı: ``hrma/engines/hybrid_rocket_engine.py:1380-1386``.

* **C2 — NASA-STD-5012 yanlış konu + yanlış başlık.** Lülede izantropik
  Mach-alan konturunun kaynağı olarak "NASA-STD-5012 Pressure Vessels &
  Pressurized Systems" gösteriliyordu. Belgenin gerçek adı *Strength and
  Life Assessment Requirements for Liquid-Fueled Space Propulsion System
  Engines* (Rev. B, 2016) ve bir mukavemet/ömür standardıdır — içinde gaz
  dinamiği bağıntısı yoktur. Doğru kaynak NACA Report 1135'tir; aynı
  düzeltme ``formulas.html``, ``i18n_formulas.js`` ve
  ``performance_panel.js`` içinde yapıldı (``docs/STANDART_ATIFLARI.md``).

* **D7 — tam istek gövdesi loga gidiyordu.** ``/calculate_solid`` ve
  ``/calculate_liquid`` ``print("... motor data received:", data)`` ile
  isteğin tamamını stdout'a basıyordu; başlatıcı stdout'u
  ``Documents/HRMA/hrma_log.txt``'ye yazıyor (``packaging/launcher.py:79``)
  ve destek paketi o dosyayı içine koyuyor (:651). Kullanıcının gizli motor
  tasarımı destek dosyasıyla dışarı çıkabiliyordu.

Testler hem ÇALIŞMA ZAMANI davranışını (test istemcisi) hem KAYNAK
METNİNİ sınar: bir sonraki kişinin kusuru geri koyması kaynakta olur.
"""

import contextlib
import io
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


APP_PY = os.path.join(REPO_ROOT, 'hrma', 'app.py')

#: structural_panel.js'in gönderdiği alanlarla birebir aynı (panel
#: ``wall_thickness`` ve ``safety_factor`` göndermiyor -> boyutlandırma modu).
STRUCTURAL_PAYLOAD = {
    'chamber_pressure': 40,      # bar
    'chamber_diameter': 0.1,     # m
    'chamber_length': 0.5,       # m
    'throat_diameter': 0.02,     # m
    'burn_time': 10,             # s
    'material': 'steel_4130',
}

#: Kabul edilebilir onay hükümleri — kazanılmadıkça bunlar görünmemeli.
ONAY_HUKUMLERI = ('SAFE', 'ACCEPTABLE')


def _read_app_source():
    with open(APP_PY, encoding='utf-8') as handle:
        return handle.read()


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _structural(client, **extra):
    payload = dict(STRUCTURAL_PAYLOAD)
    payload.update(extra)
    response = client.post('/analyze_structural_safety', json=payload)
    assert response.status_code == 200, response.get_data(as_text=True)[:400]
    return response.get_json()


# ---------------------------------------------------------------------------
# B3 — kazanılmamış yapısal hüküm
# ---------------------------------------------------------------------------
class TestB3YapisalHukumKapisi:

    def test_bos_govde_422_donuyor(self, client):
        """Boş istekten yapısal hüküm üretilemez (``/analyze_safety`` deseni)."""
        response = client.post('/analyze_structural_safety', json={})
        assert response.status_code == 422, (
            'Boş istek hâlâ hüküm üretiyor: '
            + response.get_data(as_text=True)[:300])
        body = response.get_json()
        assert body['error'] == 'incomplete_structural_input'
        # Hangi alanların eksik olduğu SÖYLENİR; kullanıcı tahmin etmez.
        assert set(body['missing_fields']) == {
            'chamber_pressure', 'chamber_diameter', 'chamber_length',
            'throat_diameter'}

    def test_bos_govdede_kabul_karari_yok(self, client):
        """Ölçülen kusurun birebir kendisi: '{}' -> ACCEPTABLE / LOW."""
        raw = client.post('/analyze_structural_safety',
                          json={}).get_data(as_text=True)
        for yasak in ('ACCEPTABLE', '"LOW"', 'peak_wall_temperature_K'):
            assert yasak not in raw, (
                f'Boş istek yanıtında {yasak!r} görünüyor')

    def test_boyutlandirma_modunda_onay_verilmiyor(self, client):
        """Cidarı HRMA boyutlandırdıysa emniyet katsayısı hedefin geri
        okunmasıdır; bundan kabul kararı çıkarılamaz."""
        data = _structural(client)
        chamber = data['structural_analysis']['chamber_analysis']
        safety = data['structural_analysis']['safety_analysis']
        # Modül bayrağı zaten yazıyordu — kapı artık onu OKUYOR.
        assert chamber['safety_factor_is_tautological'] is True
        assert chamber['design_mode'] == 'size'
        assert safety['status'] not in ONAY_HUKUMLERI, (
            'Totolojik emniyet katsayısından kabul kararı çıktı: '
            + str(safety['status']))
        assert safety['status'] == 'NOT_EVALUATED'
        assert safety['risk_level'] == 'NOT_EVALUATED'
        assert safety['minimum_safety_factor_is_tautological'] is True
        assert data['design_basis']['verdict'] == 'withheld'
        assert ('safety_factor_is_tautological'
                in data['design_basis']['verdict_withheld_reasons'])

    def test_hesaplanmayan_cidar_sicakligi_yayimlanmiyor(self, client):
        """Gaz/cidar sıcaklığı verilmediğinde termal yol KOŞMAZ; o hâlde
        'tepe cidar sıcaklığı' diye bir sayı yayımlanamaz.

        Ölçüm: eski yanıt ``peak_wall_temperature_K = 300.0`` diyordu; bu
        değer ``_estimate_wall_delta_T``'nin "sıcaklık bilgisi yok ->
        ortamı döndür" dalından gelen ortam varsayılanıydı.
        """
        data = _structural(client)
        safety = data['structural_analysis']['safety_analysis']
        thermal = data['structural_analysis']['thermal_analysis']
        for key in ('peak_wall_temperature_K', 'derating_wall_temperature_K',
                    'thermal_margin_ratio'):
            assert safety[key] is None, (
                f'{key} hesaplanmadığı hâlde sayı olarak yayımlanıyor: '
                f'{safety[key]}')
        assert safety['thermal_assessment'] == 'not_evaluated'
        assert thermal['wall_temperature_inner_K'] is None
        assert thermal['status'] == 'NOT_MODELLED'
        assert 'wall_temperature' in data['design_basis']['not_evaluated']

    def test_sicaklik_verilince_gercek_deger_donuyor(self, client):
        """Kapı sıcaklığı susturmuyor — girdi varsa hesap yayımlanır."""
        data = _structural(client, chamber_temperature=3000)
        safety = data['structural_analysis']['safety_analysis']
        assert safety['peak_wall_temperature_K'] is not None
        assert safety['peak_wall_temperature_K'] > 300.0
        assert safety['thermal_assessment'] == 'evaluated'
        assert data['design_basis']['not_evaluated'] == []

    def test_gercek_uyari_bastirilmiyor(self, client):
        """'NOT_EVALUATED' bir TAVANDIR: onayı çeker, uyarıyı çekmez.

        Sıcak soğutmasız motor termal marjdan MARGINAL/UNSAFE çıkar; bu
        hüküm cidar kalınlığından bağımsızdır, yani totolojik değildir.
        Onu 'değerlendirilmedi'ye çevirmek gerçek bir tehlikeyi susturur.
        """
        data = _structural(client, chamber_temperature=3000)
        safety = data['structural_analysis']['safety_analysis']
        assert safety['status'] in ('MARGINAL', 'UNSAFE'), safety['status']
        assert safety['risk_level'] not in ('LOW', 'VERY LOW')
        # Hüküm yine de "doğrulama" sayılmaz.
        assert data['design_basis']['verdict'] == 'withheld'

    def test_dogrulama_modunda_hukum_veriliyor(self, client):
        """Gerçek cidar verilirse hüküm KAZANILIR ve yayımlanır."""
        data = _structural(client, wall_thickness=0.006,
                           chamber_temperature=3000)
        chamber = data['structural_analysis']['chamber_analysis']
        safety = data['structural_analysis']['safety_analysis']
        assert chamber['safety_factor_is_tautological'] is False
        assert safety['status'] != 'NOT_EVALUATED'
        assert safety['minimum_safety_factor_is_tautological'] is False
        assert data['design_basis']['verdict'] == 'issued'
        assert data['design_basis']['is_verification'] is True


# ---------------------------------------------------------------------------
# B4 — kullanıcının cidarı ve emniyet katsayısı hedefi
# ---------------------------------------------------------------------------
class TestB4DogrulamaModuBaglandi:

    def test_kullanicinin_cidari_kullaniliyor(self, client):
        """Ölçüm: 1 mm gönderildi, modül 5.887 mm kullandı ve SAFE dedi."""
        data = _structural(client, wall_thickness=0.001, safety_factor=2.0)
        chamber = data['structural_analysis']['chamber_analysis']
        assert chamber['design_mode'] == 'verify'
        assert chamber['wall_thickness_used_mm'] == pytest.approx(1.0), (
            'Kullanıcının cidarı yerine modülün boyutlandırdığı kalınlık '
            'kullanılıyor')
        assert data['design_basis']['wall_thickness_source'] == 'user_supplied'

    def test_ince_cidar_artik_safe_gorunmuyor(self, client):
        """Aynı motor: 1 mm cidar 40 bar altında kabul edilemez.

        Eski davranışta SF 4.8 ve 'SAFE' dönüyordu, çünkü değerlendirilen
        cidar kullanıcının 1 mm'si değil modülün 5.887 mm'siydi.
        """
        ince = _structural(client, wall_thickness=0.001, safety_factor=2.0)
        kalin = _structural(client, wall_thickness=0.006, safety_factor=2.0)
        sf_ince = ince['structural_analysis']['safety_analysis'][
            'minimum_safety_factor']
        sf_kalin = kalin['structural_analysis']['safety_analysis'][
            'minimum_safety_factor']
        assert sf_ince < sf_kalin, (
            'Cidar kalınlığı emniyet katsayısını hiç etkilemiyor — argüman '
            'yine geçmiyor olabilir')
        assert ince['structural_analysis']['safety_analysis']['status'] \
            not in ONAY_HUKUMLERI

    def test_kullanicinin_sf_hedefi_geciyor(self, client):
        """'Safety Factor' alanı ölü değil: hedef modüle ulaşmalı."""
        data = _structural(client, safety_factor=2.5)
        chamber = data['structural_analysis']['chamber_analysis']
        assert chamber['design_safety_factor_target'] == pytest.approx(2.5)
        assert (data['design_basis']['design_safety_factor_source']
                == 'user_supplied')

    def test_cidar_verilmediginde_dogrulama_sayilmiyor(self, client):
        """Boyutlandırma modu bir DOĞRULAMA değildir ve öyle beyan edilir."""
        data = _structural(client)
        basis = data['design_basis']
        assert basis['design_mode'] == 'size'
        assert basis['is_verification'] is False
        assert basis['wall_thickness_source'] == 'sized_by_hrma'
        assert 'not a verification' in basis['message']

    def test_metre_yerine_milimetre_gonderimi_reddediliyor(self, client):
        """5 (mm sanılan) değer metre olarak yorumlanınca hazne yarıçapından
        büyük olur; sessizce kabul edilmez."""
        response = client.post('/analyze_structural_safety',
                               json=dict(STRUCTURAL_PAYLOAD,
                                         wall_thickness=5.0))
        assert response.status_code == 422
        assert response.get_json()['error'] == 'invalid_wall_thickness'

    def test_sifir_cidar_boyutlandirma_demektir(self, client):
        """0 = 'sen boyutlandır' (thrust alanındaki 0 sözleşmesiyle aynı)."""
        data = _structural(client, wall_thickness=0)
        assert data['structural_analysis']['chamber_analysis'][
            'design_mode'] == 'size'

    def test_negatif_sf_reddediliyor(self, client):
        response = client.post('/analyze_structural_safety',
                               json=dict(STRUCTURAL_PAYLOAD,
                                         safety_factor=-1.0))
        assert response.status_code == 422
        assert response.get_json()['error'] == 'invalid_safety_factor'


# ---------------------------------------------------------------------------
# C2 — Mach-alan konturunun kaynağı
# ---------------------------------------------------------------------------
class TestC2StandartAtfi:

    def test_kontur_yaniti_naca_1135_gosteriyor(self, client):
        response = client.post('/api/advanced-performance-analysis', json={
            'analysis_type': 'nozzle_mach',
            'throat_area': 0.001, 'nozzle_length': 0.1,
            'expansion_ratio': 16, 'chamber_pressure': 40,
            'chamber_temperature': 3000,
        })
        assert response.status_code == 200
        reference = response.get_json()['analysis_info']['reference']
        assert 'NACA Report 1135' in reference, reference
        assert 'NASA-STD-5012' not in reference, reference

    def test_app_py_kaynaginda_yanlis_baslik_yok(self):
        """Makine denetimi: ``tools/iddia_lint.py`` std5012 kuralı."""
        from tools import iddia_lint
        wrong_ids = {rule.rule_id
                     for rule in iddia_lint.WRONG_STANDARD_TITLES}
        hits = [f for f in iddia_lint.scan_file(APP_PY)
                if f.rule_id == 'std5012_wrong_title']
        assert not hits, [(f.line_no, f.matched) for f in hits]
        # Kural kümesi adı değişirse test sessizce boşa düşmesin.
        assert 'std5012_wrong_title' in wrong_ids

    def test_belge_adi_geciyorsa_dogru_basligiyla_geciyor(self):
        """Numara anılabilir — ama yalnız doğru adıyla ve 'burada kaynak
        değildi' açıklamasıyla (``docs/STANDART_ATIFLARI.md`` kuralı)."""
        flat = ' '.join(_read_app_source().split())
        if 'NASA-STD-5012' in flat:
            assert 'Strength and Life Assessment' in flat


# ---------------------------------------------------------------------------
# D7 — istek gövdesi loga / destek paketine gitmiyor
# ---------------------------------------------------------------------------
#: Yalnız istek gövdesinden stdout'a ulaşabilecek bir işaretçi. Uygulama bu
#: anahtarı tanımıyor, hiçbir hesapta kullanmıyor ve hiçbir hata mesajında
#: alıntılamıyor — dolayısıyla logda görünmesinin TEK yolu gövdenin tümüyle
#: basılmasıdır (kaldırılan kusurun kendisi).
GOVDE_ISARETCISI = 'BERKE_GIZLI_TASARIM_NOTU_9f3a'


def _stdout_of_post(client, url, payload):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        response = client.post(url, json=payload)
    return response, buffer.getvalue()


class TestD7IstekGovdesiLoglanmiyor:

    def test_solid_govdesi_loga_gitmiyor(self, client):
        response, logged = _stdout_of_post(client, '/calculate_solid', {
            'chamber_diameter': 75, 'grain_length': 300, 'core_diameter': 25,
            'chamber_pressure': 40, 'propellant_type': 'apcp',
            'design_note': GOVDE_ISARETCISI,
        })
        assert response.status_code == 200
        assert GOVDE_ISARETCISI not in logged, (
            'İstek gövdesi hâlâ loga basılıyor — hrma_log.txt destek '
            'paketine giriyor (packaging/launcher.py:651)')
        # Olay kaydı kaybolmadı: kararlı olay adı + korelasyon kimliği var.
        assert 'calculate_solid.request_accepted' in logged

    def test_liquid_govdesi_loga_gitmiyor(self, client):
        response, logged = _stdout_of_post(client, '/calculate_liquid', {
            'thrust': 5000, 'chamber_pressure': 50, 'mixture_ratio': 2.2,
            'fuel_type': 'rp1', 'oxidizer_type': 'lox',
            'design_note': GOVDE_ISARETCISI,
        })
        assert response.status_code == 200
        assert GOVDE_ISARETCISI not in logged
        assert 'calculate_liquid.request_accepted' in logged

    def test_hata_dalinda_da_govde_yazilmiyor(self, client):
        """Hata yolunda gövdeyi basmak "hata ayıklama" sayılmaz."""
        # Kritik girdiler EKSİKSİZ ama biri aralık dışı: istek eksiklik
        # kapısını (422) geçip aralık doğrulamasına (400) ulaşmalı — sınanan
        # şey, GÖVDENİN hata dalında da loga basılmaması.
        response, logged = _stdout_of_post(client, '/calculate_solid', {
            'chamber_diameter': 999999,        # aralık dışı -> 400
            'grain_length': 300, 'core_diameter': 25,
            'chamber_pressure': 40, 'propellant_type': 'apcp',
            'design_note': GOVDE_ISARETCISI,
        })
        assert response.status_code == 400
        assert GOVDE_ISARETCISI not in logged
        # Kullanıcı destek talebinde bu kimliği verir; log satırıyla eşleşir.
        trace_id = response.get_json()['trace_id']
        assert trace_id and trace_id in logged

    def test_kaynakta_govde_yazdiran_satir_kalmadi(self):
        """Bir sonraki kişi ``print(..., data)`` satırını geri koyarsa
        çalışma zamanı testi kaçırabilir; kaynak da sınanır."""
        source = _read_app_source()
        for yasak in ('print("Solid motor data received:", data)',
                      'print("Liquid motor data received:", data)'):
            assert yasak not in source, yasak


class TestEksikKritikGirdiKapisi:
    """Bulgu 57.3 — eksik kritik girdi sessizce varsayılanla dolmamalı.

    ÖLÇÜM (2 Ağustos 2026, HEAD a7ff1e7):
      ``POST /calculate_liquid -d '{}'``  -> 200, tam bir 10 kN RP1/LOX
                                             100 bar tasarımı, status OPTIMIZED
      ``POST /calculate_solid  -d '{}'``  -> 200, Ø100/500 mm APCP 40 bar,
                                             status CALCULATED
    Çağıran, sayıların kendi girdisinden mi gövdedeki ``data.get(ad, X)``
    varsayılanlarından mı geldiğini yanıta bakarak ayırt EDEMİYORDU.

    Katı uçta iki geçerli girdi kipi vardır ve kapı ikisini de tanır:
    geometri kipi (çap/boy/çekirdek) ve tasarım noktası kipi (itki + yanma
    süresi -> geometri boyutlandırılır).
    """

    def test_liquid_bos_govde_422(self, client):
        r = client.post('/calculate_liquid', json={})
        assert r.status_code == 422
        govde = r.get_json()
        assert govde['status'] == 'incomplete_input'
        assert set(govde['missing_fields']) == {
            'thrust', 'chamber_pressure', 'mixture_ratio',
            'fuel_type', 'oxidizer_type'}

    def test_liquid_kismi_govde_yalniz_eksigi_bildirir(self, client):
        r = client.post('/calculate_liquid',
                        json={'thrust': 5000, 'chamber_pressure': 40})
        assert r.status_code == 422
        assert set(r.get_json()['missing_fields']) == {
            'mixture_ratio', 'fuel_type', 'oxidizer_type'}

    def test_liquid_tam_govde_gecer(self, client):
        r = client.post('/calculate_liquid', json={
            'thrust': 10000, 'chamber_pressure': 100, 'mixture_ratio': 2.5,
            'fuel_type': 'rp1', 'oxidizer_type': 'lox'})
        assert r.status_code == 200

    def test_solid_bos_govde_422(self, client):
        r = client.post('/calculate_solid', json={})
        assert r.status_code == 422
        assert r.get_json()['status'] == 'incomplete_input'

    def test_solid_geometri_kipi_gecer(self, client):
        r = client.post('/calculate_solid', json={
            'chamber_diameter': 100, 'grain_length': 500, 'core_diameter': 30,
            'chamber_pressure': 40, 'propellant_type': 'apcp'})
        assert r.status_code == 200

    def test_solid_tasarim_noktasi_kipi_gecer(self, client):
        """Geometri verilmez, itki + yanma süresi verilir: geometri çıktıdır."""
        r = client.post('/calculate_solid', json={
            'thrust': 2000, 'burn_time': 5, 'chamber_pressure': 50,
            'propellant_type': 'apcp', 'grain_type': 'end_burner'})
        assert r.status_code == 200

    def test_solid_yakit_kimligi_uc_anahtardan_biriyle_karsilanir(self, client):
        """Kayıtlı projeler yakıtı ``propellant_type`` ile TAŞIMIYOR.

        examples/*.hrma dosyaları ``propellant_name`` + ``burn_rate_preset``
        kullanıyor. Kapı, veri modelinin kendisine uyar — tersi değil.
        """
        temel = {'chamber_diameter': 75, 'grain_length': 360,
                 'core_diameter': 32, 'chamber_pressure': 40}
        for kimlik in ({'propellant_type': 'apcp'},
                       {'propellant_name': 'KNDX - Potassium Nitrate/Dextrose'},
                       {'burn_rate_preset': 'kndx'},
                       {'burn_rate_a': 0.0007876, 'burn_rate_n': 0.688}):
            r = client.post('/calculate_solid', json=dict(temel, **kimlik))
            assert r.status_code == 200, f'{kimlik} reddedildi'

    def test_solid_yakit_kimligi_yoksa_reddedilir(self, client):
        r = client.post('/calculate_solid', json={
            'chamber_diameter': 75, 'grain_length': 360,
            'core_diameter': 32, 'chamber_pressure': 40})
        assert r.status_code == 422
        assert 'propellant_type' in r.get_json()['missing_fields']

    def test_ogretici_mod_kaynagini_beyan_eder(self, client):
        """Tanıtım senaryosu kaybolmadı ama sonuç kaynağını TAŞIR."""
        for uc in ('/calculate_liquid', '/calculate_solid'):
            r = client.post(uc, json={'use_tutorial_defaults': True})
            assert r.status_code == 200, uc
            govde = r.get_json()
            assert govde['input_source'] == 'tutorial_defaults', uc
            assert govde['defaults_applied'], uc
