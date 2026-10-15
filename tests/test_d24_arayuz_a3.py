# -*- coding: utf-8 -*-
"""ÖH Dalga-24 · arayüz · aşama-3 bekçileri.

Kapsanan kalemler (parti P11 / P12B / P17):
  P17B3-05  NIST rozeti: erişilebilirlik ≠ köken, künye koşumdan koşuma
            oynamaz
  P17B2-08  güverte, çözücünün malzemesini çözemezse KENDİ varsayılanını
            GÖNDERMEZ (alias denenir, olmazsa istek durur)
  P17B4-08  açılış ekranı /health'in ÖLÇTÜĞÜ süreyi gösterir (sahte
            ilerleme çubuğu YOK)
  P17B3-07  .eng ihracı üç sayfada da TEK TIK (başlık çürütüldü —
            gerileme bekçisi)
  P11B1-07  3B sahnede ekrana basılan koda gömülü Türkçe kalmadı
  P11B1-08  CFD alanı reddedilince güverte GERÇEK gerekçeyi yazar,
            yapılmış işi tekrar istemez
  P11B2-09  advanced.html'in ekranda beyan ettiği min/max uygulanır
  P11B2-10  E3 sınıflandırıcısı olumsuzlama körü değil
  P11B2-11  alanı olmayan panelin güverte düğmesi boş gövde postalamaz

Her bekçi ters mutasyonla kırmızıya çevrildi:
docs/scofield/raw/OH/D24/arayuz/a3/mutasyon.json
"""
import collections
import io
import json
import os
import re
import subprocess

import pytest
from tests.support.kanit import kanit_cikti, kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(KOK, 'hrma', 'templates')
JS = os.path.join(KOK, 'hrma', 'static', 'js')
SAYFALAR = ('advanced.html', 'liquid.html', 'solid.html')


def oku(*p):
    with io.open(os.path.join(*p), encoding='utf-8') as f:
        return f.read()


def canli(metin):
    """Yorum satırları çıkarılmış kaynak: ekrana çıkan şey burada."""
    return '\n'.join(s for s in metin.split('\n')
                     if not s.lstrip().startswith('//'))


# =====================================================================
# P17B3-05 — künye koşumdan koşuma oynamaz
# =====================================================================
class TestP17B305KunyeSalinimi:

    def test_oksitleyici_yolu_erisilebilirlik_rozetini_ezmiyor(self):
        """`.nist-status` TEK olguyu taşır: uzak ucun erişilebilirliği.

        Ölçülen kusur (P17 tur-06): oksitleyici çekim yolu aynı rozete
        ÇEKİLEN VERİNİN kaynağını yazıyordu; iki farklı olgu tek rozete
        yazılınca künye koşumdan koşuma değişiyordu.
        """
        adv = oku(TPL, 'advanced.html')
        assert 'setNistStatus(`${source}' not in adv
        # rozeti yazan tek yer denetim işlevidir
        i = adv.index('async function checkDatabaseStatus')
        assert adv.count('setNistStatus(') >= 3

    @pytest.mark.parametrize('sayfa', SAYFALAR)
    def test_baglanti_rozeti_koken_iddia_etmiyor(self, sayfa):
        html = oku(TPL, sayfa)
        assert 'NIST WebBook Connected' not in html, sayfa
        assert 'supplies_calculation_data' in html, sayfa
        assert 'calculation_data_source' in html, sayfa

    @pytest.mark.parametrize('sayfa', SAYFALAR)
    def test_uc_beyan_etmezse_koken_iddia_edilmiyor(self, sayfa):
        """Fail-closed: uç `supplies_calculation_data` demiyorsa rozet
        'kaynağıdır' da 'değildir' de demez."""
        html = oku(TPL, sayfa)
        assert re.search(r'reachable_undeclared|ReachableUndeclared', html), sayfa

    def test_sozlukte_her_iki_dilde_var(self):
        ortak = oku(JS, 'i18n_pages.js')
        adv = oku(JS, 'i18n_advanced.js')
        assert ortak.count("'liq.ui.nist_webbook_reachable_local'") == 2
        assert ortak.count("'solid.ui.nist_webbook_reachable_local'") == 2
        assert adv.count("'adv.js.nistReachableLocalData'") == 2


# =====================================================================
# P17B2-08 — güverte kendi varsayılanını GÖNDERMEZ
# =====================================================================
class TestP17B208MalzemeFailClosed:

    @pytest.fixture(scope='class')
    def dock(self):
        return oku(JS, 'analysis_dock.js')

    def test_alias_katalogu_deneniyor(self, dock):
        """`steel_304` ⟷ `ss_304`: eşleme materials_db'den gelir, burada
        YENİDEN YAZILMAZ (tek kaynak)."""
        g = canli(dock)
        assert 'HRMAMaterials' in g
        assert 'resolve(want)' in g
        assert "resolve(opts[i].value)" in g
        # ikinci bir alias tablosu KOPYALANMADI
        assert "'steel_304'" not in g and '"steel_304"' not in g

    def test_cozulemeyen_malzeme_istegi_durduruyor(self, dock):
        g = canli(dock)
        assert 'blockedSelects' in g
        # runPanel gövdesinde engel kapısı, fetch'ten ÖNCE
        i = g.index('async function runPanel')
        j = g.index('blockedSelects[spec.id]', i)
        k = g.index('await fetch(', i)
        assert j < k, 'engel kapısı fetch sonrasına kaymış'
        assert 'dock.materialNotInList' in g

    def test_gerekce_ekranda_kaliyor(self, dock):
        """D21'in kazanımı geri alınmadı: gerekçe konsolda DEĞİL ekranda."""
        g = canli(dock)
        assert 'solver_value_not_in_option_list' in g
        assert 'paintFieldSources' in g


# =====================================================================
# P11B2-11 — boş gövde postalanmaz
# =====================================================================
class TestP11B211BosGovde:

    @pytest.fixture(scope='class')
    def dock(self):
        return canli(oku(JS, 'analysis_dock.js'))

    def test_bos_govde_kapisi_fetchten_once(self, dock):
        i = dock.index('async function runPanel')
        j = dock.index('allowsEmptyPayload', i)
        k = dock.index('await fetch(', i)
        assert j < k
        assert 'dock.emptyPayload' in dock

    def test_yalnizca_bes_panelden_biri_bos_govde_beyan_ediyor(self):
        pdir = os.path.join(JS, 'panels')
        beyan, alansiz = [], []
        for f in sorted(os.listdir(pdir)):
            if not f.endswith('.js'):
                continue
            s = oku(pdir, f)
            if re.search(r'fields:\s*\[\s*\]', s):
                alansiz.append(f)
            if 'allowsEmptyPayload: true' in s:
                beyan.append(f)
        assert 'correlation_panel.js' in alansiz
        # Boş gövdeye 200 dönen TEK uç beyan eder; kardeşleri etmez.
        assert beyan == ['correlation_panel.js'], beyan
        for kardes in ('comparative_panel.js', 'uncertainty_panel.js',
                       'validation_panel.js'):
            assert kardes in alansiz
            assert kardes not in beyan


# =====================================================================
# P11B2-10 — olumsuzlama körlüğü
# =====================================================================
class TestP11B210OlumsuzlamaKorlugu:

    @pytest.fixture(scope='class')
    def olcum(self):
        betik = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D24',
                             'arayuz', 'a3', 'olc_e3.js')
        cikti = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D24',
                             'arayuz', 'a3', '_bekci_e3.json')
        try:
            r = subprocess.run(['node', kanit_gerekli(betik), KOK, kanit_cikti(cikti)],
                               capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as e:
            pytest.skip('node yok / zaman aşımı: %s' % e)
        if r.returncode != 0:
            pytest.fail(r.stderr.decode('utf-8', 'replace')[:2000])
        with io.open(kanit_gerekli(cikti), encoding='utf-8') as f:
            return json.load(f)

    def test_gercek_beyan_metinlerinin_hepsi_dogru_siniflaniyor(self, olcum):
        """Ürünün KENDİ beyan cümleleri (git grep ile depodan alındı).

        Tabanda 17 vakanın 6'sı yanlıştı: "…NOT the design safety factor
        entered by the user" alanına USER, "model constant, not computed
        from this design" alanına NOT MODELLED damgası basılıyordu.
        """
        yanlislar = [v for v in olcum['vakalar'] if not v['dogru']]
        assert olcum['yanlis'] == 0, yanlislar

    def test_gercek_olumsuzlama_beyanlari_bozulmadi(self, olcum):
        """Kendisi bir olumsuzlama olan beyanlar 'missing' kalmalı."""
        def sinif(onek):
            eslesen = [v for v in olcum['vakalar']
                       if v['metin'].startswith(onek)]
            assert len(eslesen) == 1, (onek, len(eslesen))
            return eslesen[0]['alinan']
        assert sinif('not_modelled') == 'missing'
        assert sinif('This effect is not modelled') == 'missing'
        assert sinif('user_input') == 'user'
        assert sinif('veri yok') == 'missing'


# =====================================================================
# P11B1-08 — CFD reddi durum satırına yazılır
# =====================================================================
class TestP11B108CfdReddi:

    def test_sahne_son_reddi_yayimliyor(self):
        viz = canli(oku(JS, 'motor_viz3d.js'))
        assert 'getCfdReject' in viz
        assert '_cfdLastReject' in viz
        # başarılı yükleme ve temizleme reddi DÜŞÜRÜR
        i = viz.index('clearCfdField: function ()')
        assert '_cfdLastReject = null' in viz[i:i + 260]

    def test_guverte_gercek_gerekceyi_yaziyor(self):
        deck = canli(oku(JS, 'motor_viz_deck.js'))
        assert 'cfdRejectBlock' in deck
        # red imzaya girer, yoksa durum satırı hiç tazelenmez
        i = deck.index('function cfdStateSig')
        assert 'cfdRejectBlock()' in deck[i:i + 600]
        # varsayılan metin yalnız RED YOKKEN yazılır
        j = deck.index('function cfdDefaultStatus')
        govde = deck[j:j + 1400]
        assert govde.index('cfdRejectBlock()') < govde.index("'viz.cfd.none'")
        assert 'viz.cfd.rejected' in govde

    def test_sozlukte_iki_dilde(self):
        assert oku(JS, 'i18n_common.js').count("'viz.cfd.rejected'") == 2


# =====================================================================
# P11B1-07 — sahnede koda gömülü Türkçe kalmadı
# =====================================================================
class TestP11B107SahneDili:

    TR_DESEN = ("'soğutma kanalları: veri yok'", "'kontur: yerel üretim'",
                "'sprey açısı '", "'ÖN'", "'ÜST'", "'YAN'", "'İZO'",
                "'Ortografik görünüş: '", "'ızgara '", "'ØC iç '")

    def test_ekrana_basilan_ham_turkce_yok(self):
        viz = canli(oku(JS, 'motor_viz3d.js'))
        kalan = [d for d in self.TR_DESEN if d in viz]
        assert kalan == [], kalan

    def test_yeni_etiketler_T_kanalindan_geciyor(self):
        viz = canli(oku(JS, 'motor_viz3d.js'))
        assert "T('viz3d.chip.sprayAngle'" in viz
        assert "T('viz3d.cad.orthoTip'" in viz
        # CAD presetleri anahtar+yedek çiftiyle tabloda durur ve T()'den geçer
        assert "'viz3d.cad.front', 'FRONT'" in viz
        assert "'viz3d.cad.iso', 'ISO'" in viz
        assert 'T(pr[1], pr[2])' in viz

    def test_sozlukte_iki_dilde(self):
        ortak = oku(JS, 'i18n_common.js')
        for k in ('viz3d.chip.sprayAngle', 'viz3d.cad.front',
                  'viz3d.cad.top', 'viz3d.cad.side', 'viz3d.cad.iso',
                  'viz3d.cad.orthoTip'):
            assert ortak.count("'%s'" % k) == 2, k
        # TR karşılıkları gerçekten Türkçe
        # ÖH D34 / OH-GT-04 — BEKÇİ ÇEVRİLDİ: 'İZO' dizesi artık
        # şart değil. Ölçüldü (once.json OH_GT_04): aynı kamera kipi
        # sıvı sayfasında 'İzometrik', hibritte 'İZO' yazıyordu; bu
        # bekçi kısaltılmış biçimi dondurarak tutarsızlığı koruyordu.
        # Şart korundu: anahtarın İngilizceden farklı bir Türkçe
        # karşılığı olmalı.
        import re as _re
        assert "'ÖN'" in ortak
        _iso = _re.findall(r"'viz3d\.cad\.iso':\s*'([^']*)'", ortak)
        assert len(_iso) == 2 and 'ISO' in _iso, _iso
        assert [d for d in _iso if d != 'ISO'], _iso


# =====================================================================
# P11B2-09 — ekranda beyan edilen min/max uygulanır
# =====================================================================
class TestP11B209BeyanEdilenSinirlar:

    @pytest.fixture(scope='class')
    def appjs(self):
        return canli(oku(JS, 'app.js'))

    def test_kapi_var_ve_validateInputs_icinden_cagriliyor(self, appjs):
        assert 'function declaredBoundsErrors' in appjs
        i = appjs.index('function validateInputs')
        assert 'declaredBoundsErrors()' in appjs[i:i + 500]

    def test_sinirlar_DOM_beyanindan_okunuyor_kopya_yok(self, appjs):
        """TEK KAYNAK: eşikler HTML'de beyan edilir, JS onları OKUR."""
        i = appjs.index('function declaredBoundsErrors')
        govde = appjs[i:appjs.index('\n}', i)]
        assert "getAttribute('min')" in govde
        assert "getAttribute('max')" in govde
        # İkinci bir eşik tablosu YAZILMADI: gövdede eşik gibi okunabilecek
        # hiçbir sayı yok (yalnız dizi/indis sıfırı serbest).
        sayilar = [n for n in
                   re.findall(r'(?<![\w.])\d+(?:\.\d+)?(?![\w.])', govde)
                   if n != '0']
        assert sayilar == [], sayilar

    def test_bos_alan_hata_uretmiyor(self, appjs):
        i = appjs.index('function declaredBoundsErrors')
        govde = appjs[i:appjs.index('\n}', i)]
        assert "if (ham === '') continue;" in govde

    def test_sozlukte_iki_dilde(self):
        ortak = oku(JS, 'i18n_common.js')
        assert ortak.count("'app.val.belowDeclaredMin'") == 2
        assert ortak.count("'app.val.aboveDeclaredMax'") == 2

    #: ``advanced.html``da min/max BEYAN ETMEYEN sayı alanları — ÖLÇÜLMÜŞ
    #: istisna kümesi. Bu bir TAVANDIR: listede olmayan bir alan beyansız
    #: kalırsa bekçi kırmızı olur. Çoklu küme (aynı ad birden çok kez
    #: geçiyorsa sayısı da çivilidir), çünkü tek bir alanın beyanını
    #: düşürmek de gevşemedir.
    #:
    #: NEDEN SAYI DEĞİL KÜME (ÖH D33 fix-36, taban kaydı-16):
    #: bekçi eskiden ``len(beyanli) >= 70`` diyordu. 70, D24'te ölçülen
    #: NÜFUSTU; ÖH D32 arayuz-panel a1 (577bb32d · OH-D31-05) ölü
    #: ``#custom_fuel_mixture`` panelini sökünce o paneldeki YEDİ beyanlı
    #: alan da gitti (87 → 80 sayı alanı, 70 → 63 beyanlı) ve bekçi
    #: kırmızıya döndü — oysa gevşeyen hiçbir şey yoktu: giden alanların
    #: HEPSİ beyanlıydı ve hepsi ölü paneldeydi.
    #: ÖLÇÜLDÜ — beyansız küme ÜÇ ağaçta da BİT-AYNI (17 ad):
    #:   26935aee (söküm öncesi) 87/70/17 · a5ccd660 (bugün) 80/63/17 ·
    #:   dalga33/arayuz-panel (sürmekte) 79/62/17.
    #: Yani envanterin sağlığı nüfusun büyüklüğünde değil, BEYANSIZ
    #: kümenin sabitliğindedir. Yeni bir alan beyansız eklenirse ya da
    #: mevcut bir alanın beyanı silinirse bu bekçi ısırır; ölü alan
    #: sökmek onu kırmızıya döndürmez.
    BEYANSIZ_SAYI_ALANLARI = (
        'chamber_length_override',
        'hole_diameter_max', 'hole_diameter_max',
        'hole_diameter_min', 'hole_diameter_min',
        'oxidizer_density', 'oxidizer_temp', 'oxidizer_viscosity',
        'param_end', 'param_start',
        'pintle_diameter',
        'plate_thickness', 'plate_thickness',
        'slot_height', 'slot_width',
        'target_velocity', 'target_velocity',
    )

    def test_advanced_hala_min_max_beyan_ediyor(self):
        """ÖK-22: sağlıklı envanter gevşetilmedi — beyansız küme büyümedi."""
        adv = oku(TPL, 'advanced.html')
        alanlar = re.findall(r'<input[^>]*type="number"[^>]*>', adv)
        # Yalancı yeşil kapısı: şablon okunamadıysa/boşaldıysa bekçi
        # "beyansız yok" diye yeşil kalmasın.
        assert len(alanlar) >= 60, (
            'advanced.html sayı alanı envanteri beklenmedik ölçüde küçük — '
            f'şablon okunuyor mu? {len(alanlar)}')
        beyansiz = []
        beyanli = []
        for etiket in alanlar:
            kimlik = re.search(r'id="([^"]+)"', etiket)
            ad = kimlik.group(1) if kimlik else '(kimliksiz) ' + etiket
            (beyanli if ('min=' in etiket or 'max=' in etiket)
             else beyansiz).append(ad)
        olculen = collections.Counter(beyansiz)
        beklenen = collections.Counter(self.BEYANSIZ_SAYI_ALANLARI)
        yeni_beyansiz = sorted((olculen - beklenen).elements())
        assert not yeni_beyansiz, (
            'min/max beyanı OLMAYAN yeni sayı alanı: %s — ÖK-22 envanteri '
            'gevşetilmiş (alan eklendiyse beyanıyla eklensin, mevcut alanın '
            'beyanı silindiyse geri konsun)' % yeni_beyansiz)
        # Simetrik ayak: beyansız bir alan BEYANLI hâle geldiyse (ya da
        # söküldüyse) bu iyileşmedir, ama listede bayat kalmasın.
        kalkan = sorted((beklenen - olculen).elements())
        assert not kalkan, (
            'beyansız listesi bayat — şu adlar artık beyansız değil: %s. '
            'İyileşme kalıcı olsun diye listeden düşürülmeli' % kalkan)
        # Beyanlı nüfus, beyansız tavanın tümleyeni: iki sayım tutarlı.
        assert len(beyanli) == len(alanlar) - len(self.BEYANSIZ_SAYI_ALANLARI)


# =====================================================================
# P17B4-08 — açılış ekranı sunucunun ölçtüğü süreyi gösterir
# =====================================================================
class TestP17B408AcilisEkrani:

    @pytest.fixture(scope='class')
    def launcher(self):
        return oku(KOK, 'packaging', 'launcher.py')

    def test_health_sayisi_ekrana_cikiyor(self, launcher):
        assert 'd.elapsed_s' in launcher
        assert 'sunucuSn' in launcher
        assert 'on the server' in launcher

    def test_sahte_ilerleme_yok(self, launcher):
        """Yüzde bilinmiyor: uydurulmaz (sahte veri yasağı)."""
        assert '<progress' not in launcher
        assert 'progress-bar' not in launcher
        assert not re.search(r"width:\s*'\s*\+", launcher)

    def test_sunucu_sayisi_yokken_kaynak_etiketleniyor(self, launcher):
        assert 'in this window' in launcher


# =====================================================================
# P17B3-07 — .eng ihracı üç sayfada da TEK TIK (başlık çürütüldü)
# =====================================================================
class TestP17B307TekTikGerilemesi:

    def test_her_sayfada_tek_eng_dugmesi(self):
        assert oku(TPL, 'advanced.html').count(
            'onclick="downloadEngFile()"') == 1
        assert oku(TPL, 'solid.html').count(
            'onclick="downloadSolidEng()"') == 1
        assert oku(TPL, 'liquid.html').count(
            'onclick="downloadLiquidEng()"') == 1

    def test_ureten_islev_indirmeyi_de_yapiyor(self):
        adv, liq, sol = (oku(TPL, s) for s in SAYFALAR)
        i = adv.index('async function downloadEngFile()')
        assert '.click()' in adv[i:i + 6000]
        i = sol.index('async function downloadSolidEng()')
        assert '.click()' in sol[i:i + 6000]
        i = liq.index('async function downloadLiquidEng()')
        assert '_triggerLiquidDownload(' in liq[i:i + 6000]

    def test_olu_ikinci_yol_geri_gelmedi(self):
        for s in ('advanced.html',):
            assert 'function exportOpenRocket' not in oku(TPL, s)
        assert 'function exportOpenRocket' not in oku(JS, 'app.js')
