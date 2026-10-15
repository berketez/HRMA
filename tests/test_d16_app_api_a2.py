"""ÖH Dalga-16 · kulvar app-api · aşama 2 bekçileri.

Kapsanan kalemler:

``P12aB3-01``
    Çözücünün "senin girdini kullanmadım" beyanı (``inputs_not_used``)
    ürünün HİÇBİR yerinde okunmuyordu. ÖLÇÜLDÜ (taban ``6fde52b``,
    ``docs/scofield/raw/OH/D16/app-api/a2/once_a2.json``): gönderilen
    ``chamber_temperature = 3000``, kullanılan **3307,1286** (%10,2 fark),
    beyan **1** üretiliyor, ``app.js::collectResultWarnings``in ekrana
    bastığı **9** kaydın hiçbiri o alanı anmıyor → ekrana ulaşan beyan
    **0/1**. Onarımdan sonra **1/1** (kanal 10 kayıt).

``P14H1-C1``
    3B Isp yüzeyinde "tasarım noktası" işaretçisi, AYNI figürdeki yüzeyin
    çözülmüş maksimumunun üstünde çizilebiliyordu. ÖLÇÜLDÜ (aynı taban,
    panelin kendi form varsayılanları Pc 50 · O/F 3,5 · Isp 300 +
    ``fuel_type='htpb'`` / ``oxidizer_type='n2o'``): ``Sweep maximum``
    **270,042 s** ⟷ ``Design point (as supplied)`` **300,0 s**, yani
    **+29,96 s (%11,09)**. Onarımdan sonra işaretçi ÇİZİLMEZ ve gerekçe
    iki sayıyı da adıyla söyler; yüzeyin altındaki gerçek motor koşumu
    (Isp 230,35 s) aynen çizilmeye devam eder.
"""

import json

import numpy as np
import pytest

from hrma.app import app
from hrma.visualization.visualization import (
    create_chamber_pressure_mixture_ratio_3d_surface,
)


@pytest.fixture(scope='module')
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Ortak yardımcılar — yüklem, ölçüm betiğiyle (a2/olcum_a2.py) AYNI kanalları
# okur: app.js::collectResultWarnings (app.js:1620-1629).
# ---------------------------------------------------------------------------
def _ekran_kanallari(govde):
    motor = govde.get('motor') or {}
    kayitlar = []
    for kanal in ((motor.get('warnings') or motor.get('design_warnings')) or [],
                  motor.get('input_warnings') or govde.get('input_warnings') or [],
                  ((govde.get('injector') or {}).get('warnings')) or []):
        if isinstance(kanal, list):
            kayitlar.extend(kanal)
    return kayitlar


def _kayit_metni(k):
    if isinstance(k, str):
        return k
    if isinstance(k, dict):
        parcalar = [str(k.get(a, '')) for a in
                    ('code', 'message', 'text', 'fallback')]
        params = k.get('params')
        if isinstance(params, dict):
            parcalar.append(str(params.get('field', '')))
        return ' '.join(parcalar)
    return str(k)


def _figur(plot_json):
    return json.loads(plot_json) if isinstance(plot_json, str) else plot_json


def _yuzey_max(fig):
    for tr in fig.get('data', []):
        if tr.get('type') == 'surface':
            z = np.array(tr.get('z'), dtype=float)
            if np.isfinite(z).any():
                return float(np.nanmax(z))
    return None


def _tasarim_noktalari(fig):
    # ÇEVRİLDİ (ÖH D24 / P8B4-17): süzgeç ``startswith('Design point')``
    # idi. Haçın İZ ADI artık genleşme tabanı düzeltildiğinde değişiyor
    # ("Design (Pc, O/F) at this surface's expansion basis"); bu sınıfın
    # konusu haçın ADI değil ÇİZİLİP ÇİZİLMEDİĞİdir, o yüzden süzgeç role
    # (haç işareti taşıyan tasarım izi) bağlandı.
    return [tr for tr in fig.get('data', [])
            if str(tr.get('name', '')).startswith('Design')]


def _not_metni(fig):
    notlar = [a.get('text', '') for a in
              (fig.get('layout') or {}).get('annotations', [])]
    return ' '.join(notlar)


# ---------------------------------------------------------------------------
# P12aB3-01
# ---------------------------------------------------------------------------
# ÇAPA YENİLENDİ (ÖH D19 fix-12, 3 Eyl 2026): değiştiren D19 hibrit B3-12 (09867aa) — reaktan molekül ağırlığı TEK KAYNAĞA alındı, yanma çözümü ve ondan türeyen bütün yapraklar (T_c, boğaz/çıkış geometrisi, ısı akısı, itki eğrisi, apoje) ~1e-5…4e-4 bağıl kaydı; D19 hibrit çapa kaydı 03_capa_kiyas.txt atıflı. Sayı ölçüldü (taban kaydı-4, main d914908). (T_c 3307,1286→3308,1508 K; ızgara tavanı 270,0→270,1 s)
class TestP12aB3_01BeyanEkranaUlasiyor:
    """``inputs_not_used`` beyanı, ürünün BASTIĞI uyarı kanalında da durur."""

    GOVDE = {'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
             'chamber_pressure': 20, 'of_ratio': 6.0,
             'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
             'chamber_temperature': 3000}

    @pytest.fixture(scope='class')
    def yanit(self, istemci):
        r = istemci.post('/calculate', json=self.GOVDE)
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        return r.get_json()

    def test_beyan_hala_uretiliyor(self, yanit):
        """Kusurun ÖNKOŞULU: çözücü gerçekten kullanıcının sayısını eziyor."""
        beyanlar = yanit.get('inputs_not_used') or []
        alanlar = {b.get('field') for b in beyanlar}
        assert 'chamber_temperature' in alanlar, (
            'Beyan üretilmiyorsa bu bekçi kusuru ölçemez; ölçülen tabanda '
            f'beyan vardı. Gelen: {alanlar}')
        kullanilan = (yanit.get('motor') or {}).get('chamber_temperature')
        assert kullanilan is not None and abs(kullanilan - 3000.0) > 1.0, (
            'Gönderilen 3000 K ile kullanılan değer aynıysa beyan da olmaz; '
            f'kullanılan = {kullanilan}')

    def test_beyan_ekrana_basilan_kanalda(self, yanit):
        """P12aB3-01 ONARIMI: 0/1 → 1/1."""
        beyanlar = yanit.get('inputs_not_used') or []
        metinler = [_kayit_metni(k) for k in _ekran_kanallari(yanit)]
        ulasmayan = [b.get('field') for b in beyanlar
                     if not any(b.get('field') in m for m in metinler)]
        assert not ulasmayan, (
            'Çözücünün "girdini kullanmadım" beyanı ekrana basılan hiçbir '
            'kanalda yok (app.js::collectResultWarnings motor.warnings / '
            'input_warnings / injector.warnings okur). Ulaşamayan alanlar: '
            f'{ulasmayan}')

    def test_yansitilan_kayit_sayilari_tasiyor(self, yanit):
        """Kayıt, ekranda GÖSTERİLECEK iki sayıyı da taşımalı."""
        yansimalar = [k for k in (yanit.get('input_warnings') or [])
                      if isinstance(k, dict)
                      and k.get('source') == 'inputs_not_used']
        assert yansimalar, 'inputs_not_used yansıması hiç yok'
        kayit = yansimalar[0]
        params = kayit.get('params') or {}
        assert params.get('field') == 'chamber_temperature'
        assert abs(float(params['submitted']) - 3000.0) < 1e-9
        # ÇAPA YENİLENDİ — kitap p1a B16 (karar §28-18 (a)): N₂O 293,15 K
        # doymuş SIVI giriş entalpisi. Kâhin: CEA kök denetimi
        # (docs/scofield/raw/OH/KITAP/p1a/kanit/tur2b/kahin_cea.json) +
        # önce/sonra (p1a rapor §12). Tolerans DEĞİŞMEDİ.
        #   used 3308,150759944153 -> 3245,6920966427515
        assert abs(float(params['used']) - 3245.6920966427515) < 1e-6, (
            'Kullanılan sayı beyandan kopyalanmalı (TEK KAYNAK), yeniden '
            f'hesaplanmamalı; gelen {params.get("used")}')
        # Sözlükte karşılığı olmayan kod ham anahtar olarak basılmasın.
        assert kayit.get('fallback'), 'fallback yok — ekranda ham kod görünür'
        # fix-12: T_c 3307→3308 (D19 hibrit B3-12); kitap p1a B16: 3308 → 3245.
        assert '3000' in kayit['fallback'] and '3245' in kayit['fallback']
        assert kayit.get('severity') == 'warning'

    def test_ayni_alan_iki_kez_basilmaz(self, yanit):
        """Sıvı çözücü aynı olguyu zaten bildiriyorsa yansıma eklenmez."""
        metinler = [_kayit_metni(k) for k in _ekran_kanallari(yanit)]
        sayi = sum(1 for m in metinler if 'chamber_temperature' in m)
        assert sayi == 1, (
            f'chamber_temperature ekran kanalında {sayi} kez geçiyor — '
            'yansıtma kopya üretiyor')


# ---------------------------------------------------------------------------
# P14H1-C1
# ---------------------------------------------------------------------------
class TestP14H1_C1TasarimNoktasiYuzeyinUstunde:
    """İşaretçi, kendi figüründeki yüzeyin çözülmüş tavanını aşamaz."""

    # performance_panel.js:215-217 form varsayılanları — ÜRETİM yükü.
    URETIM = {'analysis_type': '3d_surface', 'grid_n': 5,
              'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
              'chamber_pressure': 50, 'optimal_of_ratio': 3.5,
              'base_isp': 300}

    @pytest.fixture(scope='class')
    def uretim_figuru(self, istemci):
        r = istemci.post('/api/advanced-performance-analysis', json=self.URETIM)
        assert r.status_code == 200
        return _figur(r.get_json()['plot_data'])

    def test_yuzey_tavani_olculdu(self, uretim_figuru):
        """ÖNKOŞUL: tavan gerçekten 300 s'nin altında (270,04 s)."""
        tavan = _yuzey_max(uretim_figuru)
        assert tavan is not None and tavan < 300.0, (
            f'Yüzey tavanı {tavan} — kusur bandı dışına çıkmış, bekçi bu '
            'tabanla ölçüm yapamaz')

    def test_yuzeyin_ustundeki_nokta_cizilmez(self, uretim_figuru):
        """P14H1-C1 ONARIMI: 300,0 s işaretçisi ARTIK ÇİZİLMİYOR."""
        noktalar = _tasarim_noktalari(uretim_figuru)
        assert not noktalar, (
            'Tasarım noktası, aynı figürdeki yüzeyin çözülmüş maksimumunun '
            f'üstünde olduğu hâlde çizildi: {[t.get("z") for t in noktalar]} '
            f'⟷ yüzey tavanı {_yuzey_max(uretim_figuru)}')

    def test_gerekce_iki_sayiyi_da_soyluyor(self, uretim_figuru):
        """Sessiz düşürme yok: neden çizilmediği sayılarıyla yazılır."""
        metin = _not_metni(uretim_figuru)
        assert 'NOT drawn' in metin
        assert '300.0' in metin, f'işaretçinin Isp\'si yazılmamış: {metin[:200]}'
        # ÇAPA YENİLENDİ — kitap p1a B16 (karar §28-18 (a)): N₂O 293,15 K
        # doymuş SIVI giriş entalpisi. Kâhin: CEA kök denetimi
        # (docs/scofield/raw/OH/KITAP/p1a/kanit/tur2b/kahin_cea.json) +
        # önce/sonra (p1a rapor §12). Tolerans DEĞİŞMEDİ.
        #   yüzey tavanı '270.1' -> '265.2'; fark '11.1' -> '13.1' (%)
        assert '265.2' in metin, f'yüzey tavanı yazılmamış: {metin[:200]}'
        assert '13.1' in metin, f'fark yüzdesi yazılmamış: {metin[:200]}'

    def test_yuzeyin_altindaki_gercek_nokta_cizilmeye_devam(self):
        """Kapı MEŞRU noktayı düşürmüyor (gerçek hibrit koşumu 230,35 s)."""
        fig = _figur(create_chamber_pressure_mixture_ratio_3d_surface({
            'fuel_type': 'htpb', 'oxidizer_type': 'n2o', 'grid_n': 5,
            'optimal_chamber_pressure': 20.0, 'optimal_of_ratio': 6.0,
            'base_isp': 230.34676978693597,
            'design_point_source': 'solver'}))
        noktalar = _tasarim_noktalari(fig)
        assert len(noktalar) == 1, (
            'Yüzeyin ALTINDAKİ gerçek motor sonucu da düşürüldü — kapı çok '
            'geniş')
        # ÇEVRİLDİ (ÖH D24 / P8B4-17) — GEREKÇE: bu iki satır haçın z
        # değerini gönderilen ``base_isp``e KİLİTLİYORDU. Gönderilen sayı
        # motorun kendi genleşme oranından, yüzey ise optimum/deniz
        # seviyesi genleşmesinden gelir; ikisini aynı z ekseninde eşit
        # saymak farklı tabanlardaki iki sayıyı karşılaştırılabilir
        # göstermekti (P8B4-17 ölçümü: eps=16'da %6,23 fark). Bu sınıfın
        # KENDİ konusu (P14H1-C1: yüzeyin ALTINDAKİ meşru nokta düşürülmez)
        # korunuyor; kilitlenen şey artık noktanın çizilmesi, kaynak
        # beyanının künyede durması ve gönderilen sayının kaybolmamasıdır.
        assert str(noktalar[0]['name']).startswith('Design')
        kunye = noktalar[0]['hovertemplate']
        assert 'by the motor solver' in kunye, kunye
        assert '230.3' in kunye, kunye

    def test_itici_kimligi_gerekcesi_once_gelir(self):
        """İki gerekçe birden geçerliyse daha TEMEL olanı yazılır."""
        fig = _figur(create_chamber_pressure_mixture_ratio_3d_surface({
            'grid_n': 5, 'optimal_chamber_pressure': 50.0,
            'optimal_of_ratio': 3.5, 'base_isp': 300.0}))
        assert not _tasarim_noktalari(fig)
        metin = _not_metni(fig)
        assert 'propellant identity' in metin, (
            'İtici kimliği verilmemişken yüzey BAŞKA bir çiftin yüzeyidir; '
            f'"yüzeyin üstünde" gerekçesi anlamsız kalır. Gelen: {metin[:200]}')


# ---------------------------------------------------------------------------
# P13B4-11
# ---------------------------------------------------------------------------
class TestP13B4_11VeriTabaniUclariBekcili:
    """961 satırlık ``database_integrations`` + ``external_data_fetcher``
    çiftinin İKİ CANLI UCU artık bekçili.

    ÖH D18 / P13B4-11 ŞARTI — BEKÇİ ENVANTERİ DÜZELTİLDİ. D16 turunda bu
    docstring beş sembolün de ``tests/`` altında **0** dosyada geçtiğini
    yazıyordu; sayı YANLIŞTI ve sebebi yöntemdi: sayım ``git archive`` ile
    açılmış taban ağacında yapılmış, o ağaç git deposu olmadığı için
    ``git grep`` sessizce boş dönmüştü. Doğru yöntem revizyona sormaktır
    (``git grep -l <sembol> 6fde52b -- tests/``) ve gerçek taban sayıları
    şunlardır: ``database_integrations`` **2**, ``external_data_fetcher``
    **7**, ``DatabaseManager`` **0**, ``ExternalDataFetcher`` **1**,
    ``data_fetcher`` **7**, ``/api/validate-fuel`` **2**.

    Kalemin geçerli kalan çekirdeği: bu ucun KENDİ sınır davranışı
    bekçisizdi. ÖLÇÜLDÜ (taban ``6fde52b``, ``a2/once_p13b411.json``):
    ``/api/validate-fuel`` on sınır olayının **4'ünde ham HTTP 500** ve
    çıplak Python istisna metni veriyordu (``'formula'``, ``'percentage'``,
    ``"string indices must be integers"``); adlandırılmış alan taşıyan ret
    **0/4**. Onarımdan sonra ham 500 **0**, alan adlı ret **6/6**.
    ``DatabaseManager`` ise gerçekten **0** dosyada anılıyordu.
    """

    def test_gecerli_bilesim_degismedi(self, istemci):
        r = istemci.post('/api/validate-fuel', json={
            'composition': [{'formula': 'C4H6', 'percentage': 100}]})
        assert r.status_code == 200
        j = r.get_json()
        assert j['status'] == 'success'
        assert j['components'][0]['formula'] == 'C4H6'

    @pytest.mark.parametrize('govde,beklenen_alan', [
        ({'composition': [{'percentage': 100}]}, 'composition[0].formula'),
        ({'composition': [{'formula': 'C4H6'}]}, 'composition[0].percentage'),
        ({'composition': [{'formula': 'C4H6', 'percentage': 'abc'}]},
         'composition[0].percentage'),
        ({'composition': [{'formula': 'C4H6', 'percentage': None}]},
         'composition[0].percentage'),
        ({'composition': ['C4H6']}, 'composition[0]'),
        ({'composition': {'formula': 'C4H6'}}, 'composition'),
    ])
    def test_bozuk_girdi_ham_500_degil_adlandirilmis_422(
            self, istemci, govde, beklenen_alan):
        r = istemci.post('/api/validate-fuel', json=govde)
        assert r.status_code == 422, (
            f'{govde} -> HTTP {r.status_code}; ham istisna 500\'ü geri geldi')
        j = r.get_json()
        alanlar = [k['field'] for k in j['invalid_fields']]
        assert beklenen_alan in alanlar, alanlar
        gerekce = {k['reason'] for k in j['invalid_fields']}
        assert gerekce and all(isinstance(g, str) for g in gerekce)
        # Ham Python istisna metni gövdeye SIZMAZ.
        ham = json.dumps(j)
        for parca in ('Traceback', 'unsupported operand',
                      'string indices must be', 'KeyError', 'TypeError'):
            assert parca not in ham, f'ham istisna metni sızdı: {parca}'

    def test_modulun_kendi_hukmu_korunuyor(self, istemci):
        """Yüzde toplamı kapısı ucun DEĞİL modülün hükmü — GÖVDE dokunulmadı.

        ÖH D24 / app-api a2 · P7B2-17 — **DURUM KODU İDDİASI ÇEVRİLDİ**
        (200 -> 422). Gerekçe: bu satır kalemin ölçtüğü kusuru KORUYORDU.

        ÖLÇÜLDÜ (taban ``88a29d3``,
        ``docs/scofield/raw/OH/D24/app-api/a2/once.json`` P7B2-17): aynı
        uçta ŞEKİL hatası 422 (``invalid_fuel_composition_input``),
        GERÇEK doğrulama hatası (%200 / %150 karışım) ise **HTTP 200 +
        ``status: 'error'``** dönüyordu. ``fetch`` sarmalayıcıları
        ``response.ok``a bakar ve bu gövdeyi BAŞARI sayar; kullanıcının
        %200'lük karışımı "doğrulandı" gibi görünür. Aynı sınıf ÖH D21 /
        OH-D17-23'te ``/api/oxidizer-properties``te kapatılmıştı.

        Bu testin KORUDUĞU şey (modülün kendi hükmünün uçta EZİLMEMESİ)
        aynen duruyor ve aşağıdaki iki iddia onu ölçmeye devam ediyor:
        gövde hâlâ ``status: 'error'`` ve metninde ``100%`` taşıyor —
        yani uç modülün hükmünü ne değiştiriyor ne yutuyor. Değişen tek
        şey, o hükmün HTTP sınıfının artık doğru olmasıdır.
        """
        r = istemci.post('/api/validate-fuel', json={
            'composition': [{'formula': 'C4H6', 'percentage': 50}]})
        assert r.status_code == 422
        assert r.get_json()['status'] == 'error'
        assert '100%' in r.get_json()['error']

    def test_cozulemeyen_formul_sayi_uydurmuyor(self, istemci):
        """``ZZZZ9`` için türetilmiş sayı üretilmez; künye bunu söyler."""
        r = istemci.post('/api/validate-fuel', json={
            'composition': [{'formula': 'ZZZZ9', 'percentage': 100}]})
        assert r.status_code == 200
        j = r.get_json()
        bilesen = j['components'][0]
        assert bilesen['found_in_database'] is False
        assert bilesen['molecular_weight'] is None
        assert bilesen['heat_of_formation'] is None
        karisim = j['mixture_properties']
        assert karisim['density'] is None and karisim['molecular_weight'] is None
        assert 'not present in the NASA CEA species table' in j['source']

    def test_database_status_ucu_ayakta(self, istemci):
        r = istemci.get('/api/database-status')
        assert r.status_code == 200
        j = r.get_json()
        assert set(j) >= {'nist', 'cea'}

    def test_kalan_bosluk_olculdu_element_sembolu_uyduruluyor(self, istemci):
        """KAPANMAYAN boşluk — adıyla dondurulmuştur.

        ``ZZZZ9`` formülü ``elements = {'Z': 12}`` diye ayrıştırılıyor: 'Z'
        diye bir kimyasal element YOK ve 12 katsayısı da formülde yazmıyor.
        Türetilmiş sayılar dürüstçe ``None`` döndüğü için zarar bugün
        sınırlı, ama ayrıştırıcı var olmayan bir elementi var sayıyor.
        Onarım adresi ``hrma/data/database_integrations.py``
        (``_validate_component`` formül ayrıştırıcısı) ve bu kulvarın
        sahası DIŞINDA. Boşluk kapanırsa bu test KIRMIZI verir ve defterin
        kaydını güncelletir — kusuru KORUMAK için değil, kapandığını
        haber vermek için duruyor.
        """
        r = istemci.post('/api/validate-fuel', json={
            'composition': [{'formula': 'ZZZZ9', 'percentage': 100}]})
        elements = r.get_json()['components'][0]['elements']
        assert elements == {'Z': 12}, (
            'Formül ayrıştırıcısı değişmiş görünüyor (ölçülen taban: '
            f"{{'Z': 12}}, gelen: {elements}). P13B4-11'in dondurulmuş "
            'boşluğu kapandıysa defter kaydı güncellenmeli.')
