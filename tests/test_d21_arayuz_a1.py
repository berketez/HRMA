# -*- coding: utf-8 -*-
"""ÖH Dalga-21 · arayuz kulvarı · aşama-1 bekçileri.

Her sınıf BİR kalemin onarımını kilitler. Ölçüm betiği ve kanıt dosyaları:
``docs/scofield/raw/OH/D21/arayuz/a1/`` (olcum.py, once.json, sonra.json,
kanit_node.js, kanit_node_taban.json, mutasyon.json).

Saf JS yardımcıları KAYNAKTAN SÖKÜLÜP node ile koşturulur (kopya yazılmaz;
kopya ürünle ayrışır) — ``kanit_node.js`` bu harness'tır.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANIT = os.path.join(KOK, 'docs/scofield/raw/OH/D21/arayuz/a1')
HARNESS = os.path.join(KANIT, 'kanit_node.js')


def oku(rel: str) -> str:
    with open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def node_kaniti():
    """Ürün kodunu gerçekten koşan kanıt harness'ının çıktısı."""
    if shutil.which('node') is None:
        pytest.skip('node yok — JS harness koşulamıyor')
    r = subprocess.run(['node', kanit_gerekli(HARNESS)], capture_output=True, text=True,
                       cwd=KOK, timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


# ---------------------------------------------------------------------------
# ÖH D37 taban-onarım — /api/validate-fuel ÜRÜN ucunu koşan istemci.
#
# D33-KOLAY (a21b9419, OH-D32-11, hüküm-22 KABUL) ucun ürün yüzündeki TEK
# tüketicisini (ölü karışım paneli + validateComposition + 26 sözlük anahtarı)
# söktü. CEA tablo hükmünün ürünün içinde yaşadığı tek yer artık ucun kendi
# gövdesidir; P10B4-02 ikizleri ve P15B3-04'ün ürün ayağı orada ölçülür.
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def istemci():
    import contextlib
    import io
    import tempfile
    os.environ.setdefault(
        'HRMA_USER_DATA_DIR',
        os.path.join(tempfile.gettempdir(), 'hrma-bekci-d21-a1'))
    os.makedirs(os.environ['HRMA_USER_DATA_DIR'], exist_ok=True)
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _yakit_dogrula(istemci, bilesim):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            r = istemci.post('/api/validate-fuel', json={'composition': bilesim})
    return r.status_code, r.get_json()


def _metin_yapraklari(dugum):
    """JSON gövdesindeki bütün dize yaprakları (anahtar değil, değer)."""
    if isinstance(dugum, str):
        yield dugum
    elif isinstance(dugum, dict):
        for v in dugum.values():
            yield from _metin_yapraklari(v)
    elif isinstance(dugum, (list, tuple)):
        for v in dugum:
            yield from _metin_yapraklari(v)


#: Arayüz kodu = şablonlar + tarayıcıya giden bütün JS (alt dizinler dahil).
ARAYUZ_KOKLERI = (('hrma/templates', '.html'), ('hrma/static/js', '.js'))


def _yorumsuz_satirlar(metin):
    """(satır_no, satır) — HTML yorumu, satır başında açılan blok yorumu ve
    tam-satır ``//`` yorumu ayıklanır. Satır numaraları korunur.

    Satır İÇİ ``/* */`` bilerek AYIKLANMAZ: dize içindeki ``*/*`` gibi bir
    kalıp gerçek kodu yutup bir tüketiciyi GİZLEYEBİLİRDİ; yanlış pozitif
    (yorumu kod saymak) gizlemekten güvenlidir.
    """
    temiz = re.sub(r'<!--.*?-->', lambda m: re.sub(r'[^\n]', ' ', m.group(0)),
                   metin, flags=re.S)
    temiz = re.sub(r'(?m)^[ \t]*/\*.*?\*/',
                   lambda m: re.sub(r'[^\n]', ' ', m.group(0)), temiz,
                   flags=re.S)
    return [(i, s) for i, s in enumerate(temiz.splitlines(), 1)
            if not s.lstrip().startswith('//')]


def _arayuz_kod_isabetleri(desen):
    """Arayüz KODUNDA (yorum değil) ``desen``i taşıyan (yol, satır) listesi."""
    out = []
    for kok, uzanti in ARAYUZ_KOKLERI:
        for dizin, _alt, dosyalar in os.walk(os.path.join(KOK, kok)):
            for ad in sorted(dosyalar):
                if not ad.endswith(uzanti):
                    continue
                yol = os.path.join(dizin, ad)
                rel = os.path.relpath(yol, KOK)
                with open(yol, encoding='utf-8') as f:
                    satirlar = _yorumsuz_satirlar(f.read())
                out.extend('%s:%d' % (rel, i) for i, s in satirlar
                           if desen.search(s))
    return sorted(out)


#: Arayüzün CEA TÜR TABLOSU hükmü/bilgisi taşıyan metni (iki dil).
TABLO_HUKMU = re.compile(r'species table|tür tablosu', re.IGNORECASE)


def _arayuz_tablo_hukmu():
    """Gelişmiş sayfanın şablonunda ve sözlüğünde, yorum OLMAYAN tablo satırları."""
    return [(yol, i) for yol in ('hrma/templates/advanced.html',
                                 'hrma/static/js/i18n_advanced.js')
            for i, s in _yorumsuz_satirlar(oku(yol)) if TABLO_HUKMU.search(s)]


# ===========================================================================
# P10B4-02 — kazanılmamış "NASA CEA doğrulandı" iddiası (ÜRÜN yarısı)
# ===========================================================================
IDDIA_DOSYALARI = (
    'hrma/templates/index.html',
    'hrma/static/js/i18n.js',
    'hrma/static/js/i18n_advanced.js',
)

# "CEA ile doğrulandı" hükmünü söyleyen her biçim — iddia_lint'in
# `cea_validated` deseninden GENİŞ: araya sözcük girmesi kaçırmaya yetmemeli
# ("validated successfully with NASA CEA database" tabanda kaçıyordu).
KOR_BANT = re.compile(
    r'validat\w*(?:\s+\w+){0,3}\s+(?:with|against)\s+(?:NASA\s+)?CEA'
    r'|(?:NASA\s+)?CEA(?:\s+\w+){0,3}\s+validat'
    r'|CEA(?:\s+\w+){0,3}\s+do[gğ]rula'
    r'|do[gğ]rula\w*(?:\s+\w+){0,3}\s+CEA',
    re.IGNORECASE)
# Olumsuz hüküm ("DOĞRULANMADI", "NOT validated") iddia DEĞİLDİR, kalmalıdır.
OLUMSUZ = re.compile(r'\bNOT\s+validated|DO[ĞG]RULANMADI', re.IGNORECASE)


def _cea_iddialari():
    out = []
    for yol in IDDIA_DOSYALARI:
        for i, satir in enumerate(oku(yol).splitlines(), 1):
            if KOR_BANT.search(satir) and not OLUMSUZ.search(satir):
                out.append((yol, i, satir.strip()))
    return out


class TestP10B402KazanilmamisCEAIddiasi:
    """Ürün metni yalnız GERÇEKTEN yapılan işi anlatır.

    ÖLÇÜLDÜ (hrma/data/database_integrations.py künyesi, D16/ihracat a2):
    ``NasaCeaAPI`` gövdesinde ``session.get/post`` çağrısı SIFIR — "doğrulama"
    yerel bir tür tablosunda aramadır. Bu yüzden ne "NASA CEA Validated"
    künyesi ne "validated with NASA CEA" hükmü kazanılmıştır.
    """

    def test_hicbir_kazanilmamis_cea_hukmu_kalmadi(self):
        kalanlar = _cea_iddialari()
        assert kalanlar == [], (
            'Kazanılmamış CEA doğrulama iddiası: %r' % (kalanlar,))

    def test_iddia_lint_cea_kuralinda_sifir_isabet(self):
        spec = importlib.util.spec_from_file_location(
            'iddia_lint_d21', os.path.join(KOK, 'tools/iddia_lint.py'))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        isabet = [(f.path, f.line_no, f.matched)
                  for yol in IDDIA_DOSYALARI for f in m.scan_file(yol)
                  if f.rule_id == 'cea_validated']
        assert isabet == [], isabet

    def test_acilis_ekrani_dogrulama_iddiasi_tasimiyor(self):
        for yol in ('hrma/templates/index.html', 'hrma/static/js/i18n.js'):
            metin = oku(yol)
            assert 'NASA CEA Validated' not in metin, yol
            assert 'NASA CEA Doğrulamalı' not in metin, yol

    def test_OLUMSUZ_HUKUM_SILINMEDI(self, istemci):
        """Aşırı kapanma ikizi: 'doğrulanmadı' diyen dürüst hüküm kalmalı.

        ÇEVRİLDİ (ÖH D37 taban-onarım). ESKİ ÖLÇÜM: hüküm cümlesi arayüz
        sözlüğünde aranıyordu (``adv.js.ceaNotInTable`` — 'NOT validated
        against the NASA CEA species table' / 'DOĞRULANMADI'). Kök commit
        a21b9419 (D33-KOLAY arayuz-panel a1, OH-D32-11; hüküm-22 KABUL) bu
        anahtarın TEK tüketicisi olan ölü karışım panelini ve
        ``validateComposition()``'ı 26 sözlük anahtarıyla birlikte söktü.
        Tüketicisiz anahtarı sözlükte tutmak ayrı bir kusur olurdu; bekçi o
        commit'ten beri kırmızıydı (D34/D35/D36 raporlarında taban kırmızısı).

        YENİ ÖLÇÜM — aynı kusur sınıfı (dürüst olumsuz hüküm sessizce
        kaybolmasın), hükmün BUGÜN yaşadığı yerde:
          1. Hükmü ÜRETEN ürün ucu: tabloda OLMAYAN bileşim için
             ``found_in_database: False`` ve 'not present in the NASA CEA
             species table' künyesi yayımlanmaya devam eder; gövdenin hiçbir
             dizesinde kazanılmamış doğrulama iddiası (KOR_BANT) yoktur.
          2. Arayüz yeniden CEA tablo hükmü basarsa (şablonda/sözlükte tablo
             cümlesi belirirse) ESKİ ölçüm AYNEN devreye girer: olumsuz hüküm
             iki dilde onunla birlikte gelmek zorundadır.
        """
        d, y = _yakit_dogrula(istemci, [{'formula': 'C4H6', 'percentage': 100}])
        assert d == 200 and y.get('status') == 'success', (d, y)
        assert [c.get('found_in_database') for c in y['components']] == [False]
        assert 'not present in the NASA CEA species table' in y.get('source', ''), (
            'uç tabloda olmayan bileşim için olumsuz künyeyi artık yayımlamıyor: '
            '%r' % y.get('source'))
        iddialar = [s for s in _metin_yapraklari(y)
                    if KOR_BANT.search(s) and not OLUMSUZ.search(s)]
        assert iddialar == [], iddialar

        if _arayuz_tablo_hukmu():
            metin = oku('hrma/static/js/i18n_advanced.js')
            assert 'ceaNotInTable' in metin
            assert 'DOĞRULANMADI' in metin
            assert 'NOT validated against the NASA CEA species table' in metin

    def test_tablo_aramasi_hala_ADIYLA_anlatiliyor(self, istemci):
        """Onarım iddiayı söktü, BİLGİYİ değil: tablo araması hâlâ ADIYLA söyleniyor.

        ÇEVRİLDİ (ÖH D37 taban-onarım; kök a21b9419 / OH-D32-11 — gerekçe
        yukarıdaki ikizde). ESKİ ÖLÇÜM: 'local NASA CEA species table' /
        'yerel NASA CEA tür tablosu' sözlükte aranıyordu; o cümleler sökülen
        panelin anahtarlarıydı.

        YENİ ÖLÇÜM: ürün ucu kaynağı bileşen bileşen ADIYLA söyler — tabloda
        olan bileşen 'NASA CEA species table', olmayan 'derived from formula'.
        "Yerel" ayağı (ağ çağrısı yok) ``DatabaseManager.CEA_LOCAL_STATUS``
        tek kaynağındadır (P9B5-10; tests/test_d16_ihracat_a2.py). Arayüz
        tablo cümlesi yeniden basarsa ESKİ ölçüm AYNEN devreye girer.
        """
        from hrma.data.database_integrations import DatabaseManager

        d, y = _yakit_dogrula(istemci, [{'formula': 'CH4', 'percentage': 100}])
        assert d == 200, (d, y)
        assert [c.get('found_in_database') for c in y['components']] == [True]
        assert y.get('source') == 'NASA CEA species table', y.get('source')

        d, y = _yakit_dogrula(istemci, [{'formula': 'CH4', 'percentage': 50},
                                        {'formula': 'C4H6', 'percentage': 50}])
        assert d == 200, (d, y)
        kaynak = y.get('source', '')
        assert 'NASA CEA species table for CH4' in kaynak, kaynak
        assert 'derived from formula for C4H6' in kaynak, kaynak

        assert DatabaseManager.CEA_LOCAL_STATUS == 'local'

        if _arayuz_tablo_hukmu():
            metin = oku('hrma/static/js/i18n_advanced.js')
            assert 'local NASA CEA species table' in metin
            assert 'yerel NASA CEA tür tablosu' in metin


# ===========================================================================
# OH-D17-03 — /api/validate-fuel ret gövdesi (422) ekrana iner
# ===========================================================================
class TestOHD1703RetGovdesiEkranaIner:
    """422 gövdesindeki ``message`` + ``invalid_fields`` kullanıcıya ulaşır.

    Taban (kanit_node_taban.json): ekranda yalnız
    ``Validation failed: invalid_fuel_composition_input`` görünüyordu; cümle
    ve alan adları HİÇ basılmıyordu (advanced.html'de ``invalid_fields``
    atıf sayısı 0).

    ÖH D37 taban-onarım NOTU: bu sınıfın dört node düğümü a21b9419'dan beri
    KURULUM HATASI veriyordu — kendi ölçümleri değil, harness'ın P15B3-04
    bloğu ``ceaSatir`` sökülünce koşulsuz ``throw`` ediyordu. Harness onarıldı,
    ölçülen değerler D21 ``kanit_node_sonra.json`` ile BİREBİR aynı. Durum
    beyanı: ``_cozumsuzGovdeHtml`` / ``_cozumsuzGovdeOzeti``'nin tek çağıranı
    (``validateComposition``) aynı commit'te söküldü; yardımcılar bugün
    çağıransız. Uca yeni bir arayüz tüketicisi eklenirse
    ``TestP15B304NullOzellikPatlamiyor::test_validate_fuel_arayuz_tuketicisi_yok``
    kırmızı olur ve ret gövdesinin bu yardımcılardan geçmesi yeniden kurulur.
    """

    def test_ret_kodu_cumle_ve_alanlar_ekrana_iner(self, node_kaniti):
        k = node_kaniti['OH_D17_03']
        assert k['html_kodu_gosteriyor']
        assert k['html_cumleyi_gosteriyor']
        assert k['html_alan_adlari'] == ['composition[0].formula',
                                         'composition[1].percentage']
        assert k['html_gerekce_kodlari'] == ['missing_required', 'not_a_number']
        assert k['ozet_alan_sayisi'] == 2

    def test_eski_sozlesme_de_desteklenir(self, node_kaniti):
        """`error` alanında CÜMLE taşıyan eski gövde de okunur, kod uydurulmaz."""
        k = node_kaniti['OH_D17_03']
        assert k['eski_sozlesme_cumlesi']
        assert k['eski_sozlesme_kod_uydurmuyor']

    def test_gerekcesiz_ret_FAIL_CLOSED_beyan_edilir(self, node_kaniti):
        assert node_kaniti['OH_D17_03']['gerekcesiz_ret_beyanli']

    def test_alan_adi_ham_html_olarak_basilmaz(self, node_kaniti):
        assert node_kaniti['OH_D17_03']['kacis_calisiyor']

    def test_sahte_baglanti_hatasi_metni_kalmadi(self):
        """CEA'ya AĞ BAĞLANTISI yok; 'bağlantı kurulamadı' metni yalandı.

        Yorum satırları (kusurun tarihçesi) hariç tutulur: ölçülen şey
        KULLANICIYA GİDEN metindir.
        """
        for yol in ('hrma/templates/advanced.html',
                    'hrma/static/js/i18n_advanced.js'):
            kalan = [(i, s.strip()) for i, s in enumerate(oku(yol).splitlines(), 1)
                     if not s.lstrip().startswith('//')
                     and ('Connection to NASA CEA' in s
                          or 'NASA CEA bağlantısı kurulamadı' in s)]
            assert kalan == [], (yol, kalan)


# ===========================================================================
# P15B3-04 — başarı dalı null özellikte patlamıyor (kalem ÇÜRÜTME mandalı)
# ===========================================================================
class TestP15B304NullOzellikPatlamiyor:
    """Kalemin iddiası D15/D16/D17'de kapanmış; bu sınıf onu KİLİTLER.

    İddia: ``density`` 3/3 null gelince koşulsuz ``.toFixed()`` TypeError
    fırlatıyor ve ``catch`` bunu olmayan bir "bağlantı hatası"na çeviriyor.

    ÇEVRİLDİ (ÖH D37 taban-onarım). ESKİ SÖZLEŞME: şablondaki ``ceaSatir``
    biçimleyicisi node'da null'lu gövdeyle koşturuluyor; fırlatmadığı,
    sunucunun üç beyanını bastığı ve sayı uydurmadığı ölçülüyordu
    (``test_null_ozellikte_TypeError_yok`` +
    ``test_deger_yoksa_sunucunun_beyani_basiliyor``). Kök commit a21b9419
    (D33-KOLAY arayuz-panel a1, OH-D32-11; birleşme 94350fa2, hüküm-22 KABUL)
    biçimleyiciyi TEK çağıranı ``validateComposition()`` ile birlikte söktü:
    fonksiyonun düğmesi OH-D31-05'te kalkmıştı, akış hiçbir yoldan
    açılamıyordu. Aynı söküm tests/test_d15_sablonlar_a3.py'de
    (``test_b3_13_olu_cea_sarmali_geri_gelmedi``) çevrildi, bu dosya
    atlanmıştı; harness koşulsuz ``throw`` ile 13 düğümü birden düşürüyordu.

    YENİ SÖZLEŞME — aynı kusur sınıfı (null özellik arayüzde patlama ya da
    uydurma sayı üretmesin) iki ayakta:
      * ARAYÜZ: biçimleyici sökülü kalır ve ucun arayüz tüketicisi YOKTUR.
        Tüketici geri gelirse kırmızı: null mandalı (eski node ölçümü —
        harness biçimleyiciyi bulursa onu yine koşar) yeni tüketicide
        yeniden kurulmadan geçilemez.
      * ÜRÜN UCU: değer yoksa alan ``null`` + adlandırılmış beyan
        yayımlanır, sayı uydurulmaz; gerçek değer (molekül ağırlığı) sayı
        olarak yayımlanır.
    """

    def test_olu_bicimleyici_sokuldu_geri_gelmedi(self, node_kaniti):
        k = node_kaniti['P15B3_04']
        assert k.get('sokuldu') is True, (
            'ceaSatir biçimleyicisi geri geldi (OH-D32-11). Eski null '
            'ölçümü: %r — tüketicisiyle birlikte P15B3-04 mandalını yeniden '
            'kur, sonra bu bekçiyi çevir.' % (k,))
        kod = oku('hrma/templates/advanced.html')
        yorumsuz = '\n'.join(s for _i, s in _yorumsuz_satirlar(kod))
        assert 'ceaSatir' not in yorumsuz
        assert not re.search(r'function\s+validateComposition\s*\(', yorumsuz)

    def test_validate_fuel_arayuz_tuketicisi_yok(self):
        """Uç bugün yalnız testlerden çağrılıyor (OH-D33-36 borç kaydı)."""
        isabet = _arayuz_kod_isabetleri(
            re.compile(r'/api/validate-fuel|mixture_properties'))
        assert isabet == [], (
            '/api/validate-fuel arayüzde yeniden tüketiliyor: %s — P15B3-04 '
            'null mandalı, P10B4-02 arayüz ikizleri ve OH-D17-03 ret gövdesi '
            'yönlendirmesi bu tüketicide yeniden kurulmalı.' % isabet)

    def test_deger_yoksa_uc_beyanini_yayimliyor_sayi_uydurmuyor(self, istemci):
        d, y = _yakit_dogrula(istemci, [{'formula': 'C4H6', 'percentage': 100}])
        assert d == 200 and y.get('status') == 'success', (d, y)
        p = y.get('mixture_properties') or {}
        mw = p.get('molecular_weight')
        assert isinstance(mw, float) and round(mw, 2) == 54.09, mw
        for alan, beyan in (('heat_of_formation', 'heat_of_formation_note'),
                            ('density', 'density_method'),
                            ('specific_heat', 'specific_heat_method')):
            assert p.get(alan) is None, (
                '%s artık sayı: %r — kaynağı beyanlı mı, uydurma mı?'
                % (alan, p.get(alan)))
            metin = p.get(beyan)
            assert isinstance(metin, str) and metin.strip(), (
                '%s null ama %s beyanı yok' % (alan, beyan))
            assert not re.search(r'\d+\.\d', metin), (
                '%s beyanı sayı taşıyor: %r' % (beyan, metin))


# ===========================================================================
# P15B3-01 — Excel L* satırı istenen/gerçekleşen ayrımını taşır
# ===========================================================================
class TestP15B301ExcelLStarIstenenGerceklesen:
    """Ekran "1,00 m requested -> 13,59 m achieved" derken Excel çıplak
    ``l_star`` yazıyordu (advanced.html'de ``l_star_achieved`` atıfı 0)."""

    def test_ciplak_lstar_satiri_kalmadi(self):
        metin = oku('hrma/templates/advanced.html')
        assert "['L* (m)'" not in metin

    def test_istenen_ve_gerceklesen_ayri_satirlarda(self):
        metin = oku('hrma/templates/advanced.html')
        assert "['L* requested (m)'" in metin
        assert "['L* achieved (m)'" in metin
        assert 'num(m.l_star_achieved, 3)' in metin

    def test_motorun_kendi_beyani_tabloya_giriyor(self):
        assert "['L* note'" in oku('hrma/templates/advanced.html')

    def test_ekrandaki_kaynak_ile_ayni_alanlar(self):
        """Excel, ekranın (app.js::lStarRow) okuduğu ALANLARIN aynısını okur."""
        appjs = oku('hrma/static/js/app.js')
        adv = oku('hrma/templates/advanced.html')
        for alan in ('l_star', 'l_star_achieved', 'l_star_note'):
            assert alan in appjs, alan
            assert alan in adv, alan


# ===========================================================================
# P11B1-06 — Isp çipi hangi referansta olduğunu söyler
# ===========================================================================
class TestP11B106IspCipiReferansiniSoyler:
    """Taban: çip niteliksiz 'Isp' basıyordu ve sıvı sayfası ona VAKUM
    değerini besliyordu (liquid.html: ``isp: num(results.isp_vacuum, 300)``)
    — yanındaki Thrust çipi ise tasarım/deniz seviyesi itkisiydi."""

    def test_beyan_edilen_referans_etikete_gecer(self, node_kaniti):
        k = node_kaniti['P11B1_06']
        assert k['vakum'] == 'Isp (vacuum)'
        assert k['deniz'] == 'Isp (sea level)'
        assert k['tasarim'] == 'Isp (design altitude)'

    def test_beyansiz_isp_NITELIKSIZ_yayimlanmaz(self, node_kaniti):
        k = node_kaniti['P11B1_06']
        assert k['beyansiz'] == 'Isp (reference not declared)'
        assert k['tanimsiz_beyan'] == 'Isp (reference not declared)'
        # Object.prototype üzerinden sızma da olmaz ('constructor' vb.)
        assert k['prototip_sizmasi'] == 'Isp (reference not declared)'

    def test_kati_sayfasi_referansini_beyan_ediyor(self, node_kaniti):
        assert node_kaniti['P11B1_06']['solid_beyan_ediyor']

    def test_yeni_etiketlerin_TR_karsiligi_var(self):
        charts = oku('hrma/static/js/i18n_charts.js')
        for en, tr in (('Isp (vacuum)', 'Isp (vakum)'),
                       ('Isp (sea level)', 'Isp (deniz seviyesi)'),
                       ('Isp (design altitude)', 'Isp (tasarım irtifası)'),
                       ('Isp (reference not declared)',
                        'Isp (referans beyan edilmedi)')):
            assert "'%s': '%s'" % (en, tr) in charts, en


# ===========================================================================
# P4B4-18 (ikinci ayak) — geri çekilmiş SP-8089 EŞİK atfı ekrandan kalktı
# ===========================================================================
BANT = re.compile(r'(?<![\d,.])(?:%\s*)?(\d{1,3}(?:[.,]\d+)?)\s*[-–]\s*'
                  r'(\d{1,3}(?:[.,]\d+)?)\s*%?')
# SP-8089'u bir SAYIYA/EŞİĞE dayanak yapan kalıplar (kaynak listesi değil).
ESIK_DAYANAGI = re.compile(
    r'SP-8089[^\']{0,40}(?:recommend|guidance|önerir|kılavuz)'
    r'|(?:recommend\w*|guidance|önerir|kılavuz\w*)[^\']{0,40}SP-8089'
    r'|%?\s*\d[\d.,]*\s*[-–]\s*\d[\d.,]*\s*%?[^\']{0,30}SP-8089'
    r'|SP-8089[^\']{0,30}%?\s*\d[\d.,]*\s*[-–]\s*\d[\d.,]*'
    r'|\(NASA SP-8089\)', re.IGNORECASE)


class TestP4B418SP8089EsikAtfiGeriCekildi:
    """Deponun kanonik künyesi (acoustic_modes.CHUG_THRESHOLD_SOURCE) bandın
    SP-8089'a DAYANDIRILAMAYACAĞINI yazıyor; ekran hâlâ bandı SP-8089'a
    bağlıyordu ve üstelik ÜÇ farklı sayı çiftiyle (15-20 / 15-25 / 0.15-0.30).
    """

    def test_kanonik_kunye_atfi_hala_geri_cekiyor(self):
        """Tek kaynak: bu cümle kalkarsa bekçinin dayanağı da kalkar."""
        src = oku('hrma/analysis/acoustic_modes.py')
        assert 'NOT been verified page-by-page' in src
        assert ("CHUG_THRESHOLD_CITATION = (\n"
                "    'Sutton & Biblarz 9th ed. Ch. 8; NASA SP-194 Ch. 5-6')") in src

    def test_hicbir_ekran_metni_esigi_SP8089a_dayandirmiyor(self):
        kalan = [(i, s.strip()) for i, s in
                 enumerate(oku('hrma/static/js/i18n_common.js').splitlines(), 1)
                 if 'SP-8089' in s and ESIK_DAYANAGI.search(s)]
        assert kalan == [], kalan

    def test_SP8089_anan_satirda_ikinci_bant_tanimi_yok(self):
        kalan = []
        for i, s in enumerate(oku('hrma/static/js/i18n_common.js').splitlines(), 1):
            if 'SP-8089' in s and BANT.findall(s):
                kalan.append((i, ['-'.join(t) for t in BANT.findall(s)]))
        assert kalan == [], kalan

    def test_panel_yedekleri_sozlukle_AYRISMIYOR(self):
        """Sözlük düzeldi ama panel içindeki İngilizce yedek eski kalırsa
        çeviri kapalıyken eski künye geri gelir."""
        for yol in ('hrma/static/js/injector_panel.js',
                    'hrma/static/js/transient_panel.js'):
            metin = oku(yol)
            kalan = [(i, s.strip()) for i, s in enumerate(metin.splitlines(), 1)
                     if 'SP-8089' in s and ESIK_DAYANAGI.search(s)]
            assert kalan == [], (yol, kalan)
            assert 'Sutton & Biblarz 9th ed. Ch. 8; NASA SP-194 Ch. 5-6' in metin, yol

    def test_KAYNAK_LISTESI_olarak_SP8089_silinmedi(self):
        """Aşırı kapanma ikizi: belge gerçekten var ve enjektörle ilgili;
        literatür listesinden çıkarmak bilgi kaybı olurdu."""
        common = oku('hrma/static/js/i18n_common.js')
        assert 'Sources: NASA SP-8089, Dyer 2007, Lefebvre.' in common
        assert 'Kaynaklar: NASA SP-8089, Dyer 2007, Lefebvre.' in common

    def test_sayisal_esik_urun_kodunda_TEK_YERDE_kaldi(self):
        src = oku('hrma/analysis/acoustic_modes.py')
        assert 'CHUG_DP_RATIO_RECOMMENDED = 0.20' in src
        assert 'CHUG_DP_RATIO_MINIMUM = 0.15' in src


# ===========================================================================
# OH-D18-07 — ihraç uçlarının 422'si ön yüzde ADIYLA görünür
# ===========================================================================
class TestOHD1807IhracRetiAdiylaGorunur:
    """D18 ŞARTI beş uca birim kapısı koydu (422 +
    ``unresolved_geometry_units`` + ``invalid_fields``); ön yüz yalnız
    ``.error`` okuyordu, ret kodu ve alan adları kullanıcıya ulaşmıyordu."""

    @pytest.mark.parametrize('sablon', ['advanced.html', 'solid.html'])
    def test_kod_cumle_alan_ve_gerekce_gorunur(self, node_kaniti, sablon):
        k = node_kaniti['OH_D18_07'][sablon]
        assert k['kod_gorunur'], k['metin']
        assert k['cumle_gorunur'], k['metin']
        assert k['alanlar'] == ['chamber_diameter', 'throat_diameter'], k['metin']
        assert k['gerekce_gorunur'], k['metin']

    @pytest.mark.parametrize('sablon', ['advanced.html', 'solid.html'])
    def test_govdesiz_yanitta_metin_UYDURULMAZ(self, node_kaniti, sablon):
        assert node_kaniti['OH_D18_07'][sablon]['govdesiz_yanit'] == 'HTTP 500'

    def test_eski_tek_alanli_okuma_deseni_kalmadi(self):
        eski = re.compile(r'msg = \(await response\.json\(\)\)\.error \|\| msg')
        for yol in ('hrma/templates/advanced.html', 'hrma/templates/solid.html'):
            assert not eski.search(oku(yol)), yol
