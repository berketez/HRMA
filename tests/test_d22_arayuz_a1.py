# -*- coding: utf-8 -*-
"""ÖH Dalga-22 · arayuz kulvarı · aşama-1 bekçileri.

Her sınıf BİR kalemin onarımını kilitler. Ölçüm betiği ve kanıt dosyaları:
``docs/scofield/raw/OH/D22/arayuz/a1/`` (kanit_node.js, once.json, sonra.json,
mutasyon.json, rapor.md).

Saf JS yardımcıları KAYNAKTAN SÖKÜLÜP node ile koşturulur (kopya yazılmaz;
kopya ürünle ayrışır) — ``kanit_node.js`` bu harness'tır.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KANIT = os.path.join(KOK, 'docs/scofield/raw/OH/D22/arayuz/a1')
HARNESS = os.path.join(KANIT, 'kanit_node.js')


def oku(rel: str) -> str:
    with open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def kanit():
    """Ürün kodunu gerçekten koşan kanıt harness'ının çıktısı."""
    if shutil.which('node') is None:
        pytest.skip('node yok — JS harness koşulamıyor')
    r = subprocess.run(['node', kanit_gerekli(HARNESS)], capture_output=True, text=True,
                       cwd=KOK, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


# ===========================================================================
# OH-D17-09 — hydraulic_flip_risk = None ("NOT DECIDED") panelde False ile
# AYNI görünüyordu; hydraulic_flip_risk_basis künyesi hiç basılmıyordu.
# ===========================================================================
class TestFlipHukmuUcDegerli:
    """Enjektör panelinde flip hükmü üç değerli okunur.

    Taban ölçümü (once.json M1): ``null_ile_false_ayni = True``,
    ``rozet_null = rozet_false = 2``, ``basis_null_ciktisinda = False``.
    """

    def test_not_decided_false_ile_ayni_gorunmez(self, kanit):
        m = kanit['M1_flip']
        assert m['null_ile_false_ayni'] is False, (
            'hüküm verilmedi (None) ile risk yok (False) AYNI HTML üretiyor — '
            'kullanıcı ölçülemeyeni güvenli sanır')

    def test_not_decided_kendi_rozetini_alir(self, kanit):
        m = kanit['M1_flip']
        assert m['not_decided_rozeti_var'] is True
        assert m['rozet_null'] == m['rozet_false'] + 1, (
            'NOT DECIDED durumunda fazladan bir rozet basılmalı')

    def test_ucun_kunyesi_ekrana_iner(self, kanit):
        m = kanit['M1_flip']
        assert m['basis_null_ciktisinda'] is True, (
            'hydraulic_flip_risk_basis (uçtan gelen gerekçe) hiçbir yerde '
            'basılmıyor')
        assert 'NOT DECIDED' in m['html_null']

    def test_uydurma_rozet_yok_alan_gelmezse(self):
        """Uç alanı hiç yayımlamazsa panel hüküm ÜRETMEZ (fail-closed)."""
        src = oku('hrma/static/js/injector_panel.js')
        assert "'hydraulic_flip_risk' in c" in src, (
            'alan varlığı sınanmadan rozet doğuyorsa eksik yükte uydurma '
            'hüküm basılır')

    def test_i18n_anahtarlari_iki_dilde(self):
        src = oku('hrma/static/js/i18n_common.js')
        for k in ('inj.flipUndecided', 'inj.flipUndecidedTip'):
            assert src.count("'%s':" % k) == 2, (
                '%s anahtarı EN+TR olmak üzere iki kez tanımlı olmalı' % k)


# ===========================================================================
# OH-D18-09 — su koçu isteğinde working_pressure_reference alanı yoktu;
# düzleme bağlı hüküm 400 alıyor ve kullanıcı çözecek alanı bulamıyordu.
# ===========================================================================
class TestSuKocuReferansDuzlemi:
    """Taban ölçümü (once.json M2): ``wpr_alani_var = False``,
    ``wpr_kaynakta_hic_gecmiyor = True`` (9 alan)."""

    def test_alan_panelde_sunuluyor(self, kanit):
        m = kanit['M2_feed']
        assert m['wpr_alani_var'] is True, (
            'panel working_pressure_reference alanını sunmuyor — kullanıcı '
            '400 alıyor ama hükmü kazanamıyor')
        assert 'working_pressure_bar' in m['alanlar']

    def test_secenekler_ucun_sozlesmesinden(self):
        """Değerler water_hammer.py'nin KENDİ demetinden gelir (tek kaynak)."""
        py = oku('hrma/analysis/water_hammer.py')
        es = re.search(r"WORKING_PRESSURE_REFERENCES\s*=\s*\(([^)]*)\)", py)
        assert es, 'uçtaki referans demeti bulunamadı'
        ucun = set(re.findall(r"'([a-z]+)'", es.group(1)))
        js = oku('hrma/static/js/panels/feed_panel.js')
        blok = js[js.index('WH_PRESSURE_REFS'):]
        blok = blok[:blok.index('];')]
        panelin = set(re.findall(r"\['([a-z]*)',", blok))
        assert ucun <= panelin, (
            'panel ucun kabul ettiği düzlemleri sunmuyor: uç=%r panel=%r'
            % (sorted(ucun), sorted(panelin)))
        assert '' in panelin, (
            'boş ("belirtilmedi") seçenek kalkmış — panel kullanıcı adına '
            'düzlem SEÇEMEZ (sessiz varsayılan yasak)')

    def test_varsayilan_bos_kalir(self):
        """Panel kullanıcı adına düzlem seçmez: alanın varsayılanı ''."""
        js = oku('hrma/static/js/panels/feed_panel.js')
        es = re.search(r"\['working_pressure_reference',[^\]]*", js)
        assert es, 'alan tanımı bulunamadı'
        assert re.search(r"'working_pressure_reference',\s*"
                         r"'[^']*',\s*''", es.group(0)), (
            'varsayılan boş değil — panel düzlemi kullanıcı adına seçiyor')

    def test_i18n_anahtarlari_iki_dilde(self):
        src = oku('hrma/static/js/i18n_common.js')
        for k in ('panel.feed.fWorkingPressureRef', 'panel.feed.wprUnspecified',
                  'panel.feed.wprAbsolute', 'panel.feed.wprGauge'):
            assert src.count("'%s':" % k) == 2, k


# ===========================================================================
# P17B4-03 — sayaç animasyonu ilk karede NEGATİF sayı basıyordu (5/5 kart).
# ===========================================================================
class TestSayacNegatifKareBasmaz:
    """Taban ölçümü (once.json M3): ``negatif_sayisi = 5``,
    ``alt_kirpma_var = False`` (itki −73,4 N, Isp −16,7 s, Pc −1,5 bar …)."""

    def test_gecikmis_karede_negatif_yok(self, kanit):
        m = kanit['M3_hud']
        assert m['negatif_sayisi'] == 0, (
            'rAF karesi start\'tan önce geldiğinde hâlâ negatif basılıyor: %r'
            % [k for k in m['kareler'] if k['negatif']])

    def test_basilanlar_hedefin_isaretini_korur(self, kanit):
        for k in kanit['M3_hud']['kareler']:
            assert float(k['basilan']) >= 0.0, k
            # v3.0.1 (NK-60): son değer yuvarlanarak basılır; aşım en çok
            # yarım son basamak olabilir (0,80766 → "0.81").
            dec = len(k['basilan'].split('.')[-1]) if '.' in k['basilan'] else 0
            assert abs(float(k['basilan'])) <= abs(k['hedef']) + 0.5 * 10 ** -dec + 1e-12, k

    def test_ilk_cagrida_son_deger_basilir(self, kanit):
        # v3.0.1 (NK-60): sayaç animasyonu kaldırıldı (ara sayı uydurma
        # sayıdır). Kırpma artık gerekmez: kare yok, ilk ve tek yazım hedefin
        # kendisidir. Eski bekçi (Math.max/Math.min kaynakta) bu yüzden
        # "son değer hemen basılır" bekçisine dönüştü.
        for k in kanit['M3_hud']['kareler']:
            dec = len(k['basilan'].split('.')[-1]) if '.' in k['basilan'] else 0
            assert float(k['basilan']) == round(k['hedef'], dec), k


# ===========================================================================
# P17B4-02 — sunucu ölüyken ağ kopmasına "Data type mismatch" deniyordu.
# ===========================================================================
class TestAgKopmasiTeshisi:
    """Taban ölçümü (once.json M4): üç tarayıcı imzasının 3'ü de
    'JavaScript Type Error' → 'Data type mismatch in calculations'."""

    def test_uc_imza_da_ag_kopmasi_diye_teshis_edilir(self, kanit):
        m = kanit['M4_hata']
        assert m['yanlis_teshis_sayisi'] == 0, m['ag_kopmasi']
        for s in m['ag_kopmasi']:
            assert 'Connection' in s['kaynak'], s

    def test_veri_tipi_cumlesi_ag_kopmasinda_gecmez(self, kanit):
        # ÖH D37 A1b panel-js · OH-D37-H1 — BOŞ LİSTE ÜSTÜNDE YEŞİL KALMAZ.
        # ÖLÇÜLDÜ (docs/scofield/raw/OH/A1b/panel-js/a1/once/
        # kanit_node_M4.json): CW-U6'dan sonra `handleError` kullanıcıya
        # `alert` DEĞİL sayfa içi bildirimle konuşuyor; düzenek yalnız
        # `alert`i topladığı için liste BOŞTU ve döngü hiç dönmeden yeşil
        # veriyordu. Düzenek artık bildirim kanalını da topluyor; üç imzanın
        # HER BİRİ kullanıcıya bir metin ulaştırmalı (yoksa ölçüm yoktur,
        # "temiz" değildir) ve o metin bağlantı teşhisini taşımalı.
        m = kanit['M4_hata']
        metinler = m['uyari_metinleri']
        assert len(metinler) == len(m['ag_kopmasi']) >= 3, (
            'kullanıcıya giden iletiler toplanmadı (bildirim/alert kanalı '
            'boş): %r' % metinler)
        for metin in metinler:
            assert 'Data type mismatch' not in metin, (
                'ağ kopmasına hâlâ veri tipi uyuşmazlığı deniyor: %r' % metin)
            assert 'Could not reach the HRMA server' in metin, (
                'kullanıcı iletisi bağlantı teşhisini taşımıyor: %r' % metin)

    def test_imza_listesi_tek_kaynakta(self, kanit):
        assert kanit['M4_hata']['ag_sabiti_kaynakta'] is True
        src = oku('hrma/static/js/app.js')
        assert src.count('FETCH_KOPMASI') >= 2
        # WKWebView (paketli pencere) imzası unutulmasın
        es = re.search(r'const FETCH_KOPMASI\s*=\s*\n?\s*(/.*?/i);', src, re.S)
        assert es, 'sabit bulunamadı'
        for imza in ('Failed to fetch', 'NetworkError', 'Load failed'):
            assert imza in es.group(1), imza

    def test_i18n_anahtarlari_iki_dilde(self):
        src = oku('hrma/static/js/i18n_common.js')
        for k in ('app.err.srcConnection', 'app.err.msgConnection'):
            assert src.count("'%s':" % k) == 2, k


# ===========================================================================
# OH-D18-07 — sıvı ihraç sarmalayıcısı 422 gövdesini adıyla basmıyordu.
# ===========================================================================
def _ihrac_govdesi(metin: str) -> str:
    """Şablondaki ``_ihracRetMetni`` gövdesini boşluk-normalize eder."""
    bas = metin.index('function _ihracRetMetni(')
    derinlik, i = 0, metin.index('{', bas)
    for j in range(i, len(metin)):
        if metin[j] == '{':
            derinlik += 1
        elif metin[j] == '}':
            derinlik -= 1
            if derinlik == 0:
                return re.sub(r'\s+', ' ', metin[bas:j + 1]).strip()
    raise AssertionError('gövde kapanmadı')


class TestIhracRetMetni:
    """Taban ölçümü (once.json M56): liquid.html'de ``_ihracRetMetni`` 0 atıf,
    ham ``(await response.json()).error`` okuması 1."""

    def test_sivi_sarmalayici_ret_govdesini_okur(self, kanit):
        m = kanit['M56_sablon']
        assert m['liquid_ihracRetMetni'] >= 3, (
            'liquid.html ihraç retlerini hâlâ ham `.error` ile basıyor')
        assert m['liquid_ham_error_okumasi'] == 0, (
            'ham `.error` okuması kaldı — 422 alan adları düşüyor')

    def test_uc_kopya_ayrismaz(self):
        """Şablon içi betikler ortak modül paylaşmıyor; üç kopya BİREBİR
        aynı kalmalı (bilinen borç, raporda ilan edildi)."""
        govdeler = {
            f: _ihrac_govdesi(oku('hrma/templates/%s.html' % f))
            for f in ('liquid', 'solid', 'advanced')
        }
        essiz = set(govdeler.values())
        assert len(essiz) == 1, (
            '_ihracRetMetni kopyaları ayrışmış: %r'
            % {k: v[:120] for k, v in govdeler.items()})


# ===========================================================================
# P17B3-03 — Merkez sonuç görüntüleyicisi hangi analize ait olduğunu
# söylemiyordu; geçmişe sabitlenmiş bir koşumun yeşil hükmü, reddedilen
# başka bir analizin altında sahipsiz duruyordu.
# ===========================================================================
class TestMerkezGoruntuleyiciAdiTasir:
    """Taban ölçümü (once.json M7): ``baslikta_analiz_adi = False`` —
    başlıkta yalnız saat damgası ve hüküm rozeti vardı."""

    def test_baslik_analiz_adini_tasir(self, kanit):
        m = kanit['M7_merkez']
        assert m['head_bulundu'] is True
        assert m['baslikta_analiz_adi'] is True, (
            'görüntüleyici başlığı hangi analize ait olduğunu söylemiyor')

    def test_ad_kayitli_spec_ten_gelir(self, kanit):
        m = kanit['M7_merkez']
        assert m['spec_ten_okuyor'] is True
        assert m['spec_yoksa_ham_anahtar'] is True, (
            'spec bulunamayınca ad TAHMİN EDİLMEMELİ; satır anahtarı basılır')

    def test_ad_saat_damgasindan_once_gelir(self, kanit):
        assert kanit['M7_merkez']['ad_saatten_once'] is True


# ===========================================================================
# P17B4-04 — ÇÜRÜTME BEKÇİSİ. Kalem "şema-geçersiz .hrma listede bozuk
# işaretlenmiyor, üstelik başa çıkıyor" diyordu; ÖLÇÜM (once.json M8 +
# aşağıdaki kod okuması) kusurun bu ağaçta KAPALI olduğunu gösterdi:
# list_projects yüklemeyle AYNI şema kapısından geçiyor ve sıralama
# anahtarı damgasızları sona atıyor. Bekçi kapanışı KİLİTLER.
# ===========================================================================
class TestProjeListesiSemaKapisi:

    def test_liste_sema_kapisindan_gecer(self):
        py = oku('hrma/utils/projects.py')
        govde = py[py.index('def list_projects('):]
        govde = govde[:govde.index('\ndef ', 1)]
        assert 'validate_payload(doc)' in govde, (
            'liste yükleme ile aynı şema kapısından geçmiyor — açılamayacak '
            'dosya listede sağlam görünür')
        assert "'schema'" in govde and "entry['corrupt'] = True" in govde

    def test_damgasiz_kayit_basa_gecmez(self):
        py = oku('hrma/utils/projects.py')
        assert "'\\uffff'" in py or '￿' in py, (
            'updated_at damgası olmayan kayıt için ters sıralama anahtarı yok')
        govde = py[py.index('def _sort_key('):]
        govde = govde[:govde.index('entries.sort(')]
        assert 'item[\'corrupt\']' in govde and 'return (1,' in govde, (
            'bozuk kayıtlar sona atılmıyor')
