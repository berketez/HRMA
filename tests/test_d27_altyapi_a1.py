"""ÖH Dalga-27 / altyapi aşama 1 — bekçiler.

Kapsanan kalemler
-----------------
OH-D25-01(c)  "Bekçili 3 → 22" metriği AD GEÇİŞİ sayıyordu: muafiyet/kilit
              listesinde adı geçen sabit de "bekçili" görünüyordu, oysa o
              listeye girmek KAPSAM DIŞI ilan edilmektir. Ölçüldü (taban):
              30 addan sığ tanımla 23 "bekçili", ama 7'si YALNIZ
              ``KILITLI_OLU_SABITLER`` literalinde geçiyor; test gövdesinde
              adı geçen 16. ``sabit_envanteri.bekci_kapsami`` kapsamı üç
              kümeye ayırır ve gerçek boşluk (``bekcisiz``) çıkış koduna
              girer.
OH-D25-02(a)  ``hesap_var=False`` dalı 3B/tuval ölçümünü TOPTAN atlıyordu;
              ``/launch-site``in 1600×946 canlı WebGL küresi bu yüzden hiç
              ölçülmüyordu (canlı ölçüm: ``tuval_kaynagi`` None, piksel {}).
              Sayfa artık tuvalini BEYAN eder, tur onu ölçer, fail-closed.
OH-D25-02(b)  Dilimli tam-sayfa kanıtı "tekrar bant yok" künyesi basıyor
              ama bunu ölçmüyordu; kapsam da İSTENEN yüksekliklerden
              sayılıyordu. Artık her dilimin sha256'sı kaydedilir, üretilen
              yükseklik istenene eşit olmak zorundadır ve iki dilim birebir
              aynıysa kanıt SAHTEdir.
OH-D26-13     ``tur.JS_YERLESIM`` ``position:sticky`` kutuları hesaba
              katmıyordu: ölçüm KAYDIRMAYA BAĞLIYDI (aynı sayfa, scrollY
              2101'de 1 örtüşme, 23244'te 0). Yapışkan kutular ölçüm
              süresince akış konumuna alınır, sonra AYNEN geri konur.
OH-D26-19     ``hrma.stability.critical_response_table`` kamu API'sinden
              kaldırıldı ve 422 gerekçe kodları belgesizdi; sevk edilen
              sürüm notu (``hrma/data/changelog.json``) ile ÜRÜN bağlandı.
P10B1-07      bekçi borcu (p13b410 dağıtımı, altyapi) — imalat bloğu.
P10B4-01      bekçi borcu (p13b410 dağıtımı, altyapi) — ``iddia_lint``.

Ölçüm/kanıt: ``docs/scofield/raw/OH/D27/altyapi/a1/``
(``once_canli.json`` / ``sonra_canli.json`` / ``once_metrik.json`` /
``sonra_metrik.json``; canlı koşum sistem Chrome 152.0.7977.82).
"""

from __future__ import annotations

import ast
import importlib
import json
import pathlib
import re
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / 'tools'))

from tools.browser_harness import denetimler, sayfalar, tur  # noqa: E402

import sabit_envanteri  # noqa: E402

KANIT = KOK / 'docs/scofield/raw/OH/D27/altyapi/a1'

#: ``once_metrik.json``ın alındığı AĞAÇ. Ölçüm bir ağaca aittir; bugünkü
#: ağaçla karşılaştırmak metriği değil yalnızca zamanın geçtiğini ölçer.
D27_TABAN = '709a235e'


def _kanit(ad):
    yol = KANIT / ad
    if not kanit_gerekli(yol).exists():
        pytest.skip('kanıt dosyası yok: %s' % yol)
    return json.loads(kanit_gerekli(yol).read_text(encoding='utf-8'))


# ===========================================================================
# A. OH-D25-01(c) — "bekçili" AD GEÇİŞİ değil İDDİA
# ===========================================================================

class TestOHD2501CBekciKapsami:
    """Kapsam ölçüsü, muafiyet listesini kapsam sayamaz."""

    @pytest.fixture(scope='class')
    def kapsam(self):
        return sabit_envanteri.bekci_kapsami(KOK)

    def test_arac_kapsami_UC_kumeye_ayiriyor(self, kapsam):
        assert set(kapsam) >= {'govde', 'mandal', 'kapsam', 'bekcisiz',
                               'sig_tanim', 'yalniz_muafiyet_literalinde'}
        assert set(kapsam['kapsam']) == set(kapsam['govde']) | set(
            kapsam['mandal'])
        assert not (set(kapsam['kapsam']) & set(kapsam['bekcisiz']))

    def test_muafiyet_listesindeki_ad_GOVDE_kapsaminda_SAYILMIYOR(self, kapsam):
        """Kalemin özü: literalde adı geçmek sınanmak değildir."""
        assert not (set(kapsam['yalniz_muafiyet_literalinde'])
                    & set(kapsam['govde'])), (
            'Muafiyet/kilit literalinde adı geçen sabit "adıyla sınanan" '
            'kümesine sızmış: %s' % kapsam['yalniz_muafiyet_literalinde'])

    def test_sig_tanimin_SISMESI_olculuyor(self, kapsam):
        """D20 metriği (ad geçişi) ile iddia yüzeyi arasındaki fark."""
        sisme = len(kapsam['sig_tanim']) - len(kapsam['govde'])
        assert sisme == len(kapsam['yalniz_muafiyet_literalinde']), (
            'Şişmenin TAMAMI muafiyet literaliyle açıklanmalı; açıklanmayan '
            'fark var (sığ %d, gövde %d, literal %d)'
            % (len(kapsam['sig_tanim']), len(kapsam['govde']),
               len(kapsam['yalniz_muafiyet_literalinde'])))
        assert sisme >= 1, (
            'Şişme sıfıra düştüyse ölçüm değişmiş olabilir — sayıyı raporla, '
            'bekçiyi güncelle (bugünkü ölçüm: 7).')

    def test_bekcisiz_merkezi_sabit_YOK(self, kapsam):
        assert kapsam['bekcisiz'] == [], (
            'Ne adıyla sınanan ne kapsam mandalında olan merkezî sabit: %s'
            % kapsam['bekcisiz'])

    def test_kapsam_sayilari_OLCUMLE_uyusuyor(self, tmp_path):
        """Yayımlanan metrik ELLE YAZILMADI — ÖLÇÜLDÜĞÜ AĞAÇTA üretilir.

        ÖH D30 / fix-29a — SAYIM BEKÇİSİ ÇAPASI KAYMIŞTI. Bu test, D27
        raporunun yayımladığı sayıları (30 ad / 16 gövde / 7 şişme)
        BUGÜNKÜ ağacın ölçümüyle karşılaştırıyordu; oysa o sayılar
        ``once_metrik.json``ın ``kok`` alanının da söylediği gibi D27
        TABAN AĞACININ (709a235e) ölçümüdür. Merkeze meşru bir sabit
        eklendiği anda (D29: psi çevrimi + ortam bandı, 30 -> 36) test
        kırmızı yanıyordu: iddia ("rapordaki sayı uydurma değil")
        doğruydu ama çapası yanlış ağaca bağlıydı — sabit eklemeyi
        cezalandıran, hiçbir kusuru yakalamayan bir sayım bekçisi.

        Çapa artık ölçümün KENDİ ağacındadır: üç dosya (merkez + iki
        bekçi) ``git show`` ile o commit'ten çıkarılır ve araç onların
        üstünde koşturulur. Böylece iddia hem kalıcı hem de daha güçlü
        olur: aracın kapsam TANIMI ileride sessizce değişirse (yayımlanan
        rapor artık başka bir şey söylüyor demektir) burası kırmızı yanar.
        Bugünkü ağacın kapsamı ayrı bir iddiadır ve
        ``test_bekcisiz_merkezi_sabit_YOK`` onu ölçer.
        """
        import subprocess

        once = _kanit('once_metrik.json')
        dosyalar = (sabit_envanteri.MERKEZ_SABIT_DOSYASI,
                    ) + sabit_envanteri.BEKCI_DOSYALARI
        for bagil in dosyalar:
            r = subprocess.run(['git', 'show', '%s:%s' % (D27_TABAN, bagil)],
                               cwd=KOK, capture_output=True)
            assert r.returncode == 0, (
                'D27 taban ağacı (%s) okunamadı: %s — ölçümün çapası bu '
                'commit\'tir, sığ bir kopyada bu bekçi hüküm veremez.'
                % (D27_TABAN, r.stderr.decode('utf-8', 'replace')[:200]))
            hedef = tmp_path / bagil
            hedef.parent.mkdir(parents=True, exist_ok=True)
            hedef.write_bytes(r.stdout)

        o_gun = sabit_envanteri.bekci_kapsami(tmp_path)
        assert once['sabit_sayisi'] == o_gun['sabit_sayisi']
        assert once['govde_bekcili_sayisi'] == len(o_gun['govde'])
        assert once['sig_tanim_sayisi'] == len(o_gun['sig_tanim'])
        assert once['govde_bekcili'] == o_gun['govde']
        assert once['yalniz_muafiyet_literalinde_gecen'] == o_gun[
            'yalniz_muafiyet_literalinde']

    def test_arac_BEKCISIZ_sabitte_KIRMIZI_veriyor(self, tmp_path):
        """Fail-closed kapı: kapsam dışı sabit çıkış kodunu 1 yapar."""
        (tmp_path / 'hrma').mkdir()
        (tmp_path / 'tests').mkdir()
        (tmp_path / 'hrma' / 'constants.py').write_text(
            'G_0 = 9.80665\nDENETIM_TABLOSU = ("a", "b")\n', encoding='utf-8')
        (tmp_path / 'tests' / 'test_sabit_tek_kaynak.py').write_text(
            'from hrma import constants\n\n\n'
            'def test_g0():\n    assert constants.G_0 > 0\n', encoding='utf-8')
        kapsam = sabit_envanteri.bekci_kapsami(tmp_path)
        assert kapsam['bekcisiz'] == ['DENETIM_TABLOSU'], kapsam
        assert sabit_envanteri.main(['--kok', str(tmp_path)]) == 1

    def test_arac_YALNIZ_literalde_gecen_adi_GOVDEYE_yazmiyor(self, tmp_path):
        """Sentetik ağaç: ad SADECE modül düzeyi literalde geçiyor."""
        (tmp_path / 'hrma').mkdir()
        (tmp_path / 'tests').mkdir()
        (tmp_path / 'hrma' / 'constants.py').write_text(
            'G_0 = 9.80665\nOLU_SABIT = 1234.5678\n', encoding='utf-8')
        (tmp_path / 'tests' / 'test_sabit_tek_kaynak.py').write_text(
            'from hrma import constants\n\n'
            'KILITLI_OLU_SABITLER = {"OLU_SABIT"}\n\n\n'
            'def test_g0():\n    assert constants.G_0 > 0\n', encoding='utf-8')
        kapsam = sabit_envanteri.bekci_kapsami(tmp_path)
        assert 'OLU_SABIT' in kapsam['sig_tanim']
        assert 'OLU_SABIT' not in kapsam['govde']
        assert kapsam['yalniz_muafiyet_literalinde'] == ['OLU_SABIT']
        # Sayısal olduğu için kapsam mandalına GİRER — kapsam boşluğu değil,
        # metrik hatasıdır. İkisi ayrı sorulardır.
        assert 'OLU_SABIT' in kapsam['mandal']


# ===========================================================================
# B. OH-D25-02(a) — beyan edilen tuval ÖLÇÜLÜR
# ===========================================================================

def _gez(sayfa_adi, cikti, **degistir):
    """Sayfayı Playwright ikiziyle gezer; ``(rapor, gezgin, ikiz)`` döner."""
    from tests.support import sahte_sayfa as ikiz
    senaryo = ikiz.canli_senaryo(sayfa_adi, **degistir)
    sahte = ikiz.SahteSayfa(senaryo)
    gezgin = tur.SayfaGezgini(sahte, 'http://127.0.0.1:5000',
                              sayfalar.SAYFALAR[sayfa_adi], str(cikti))
    return gezgin.gez(), gezgin, sahte


class TestOHD2502ABeyanliTuval:
    """Hesapsız sayfa ≠ tuvalsiz sayfa."""

    def test_launch_site_TANIMI_tuvalini_BEYAN_ediyor(self):
        tanim = sayfalar.SAYFALAR['launch-site']
        assert tanim.hesap_var is False
        assert tanim.tuval_secici == '#ls-globe canvas'
        assert 'launchGlobe' in tanim.tuval_hazir_kosulu
        sablon = (KOK / 'hrma/templates/launch_site.html').read_text(
            encoding='utf-8')
        assert 'id="ls-globe"' in sablon, (
            'Beyan edilen tuval kabı şablonda YOK — beyan bayatlamış')
        assert 'window.launchGlobe = globe' in sablon, (
            'Hazır ölçütünün dayandığı nesne şablonda yayımlanmıyor')

    def test_tuvalsiz_hesapsiz_sayfada_HAYALET_denetim_uretilmiyor(self):
        """``/`` ve ``/formulas`` tuval BEYAN ETMEZ."""
        for ad in ('index', 'formulas'):
            assert sayfalar.SAYFALAR[ad].tuval_secici == '', ad

    def test_tur_beyanli_tuvali_OLCUYOR(self, tmp_path):
        rapor, gezgin, sahte = _gez(
            'launch-site', tmp_path,
            js_cevaplari={'JS_SAYFA_METNI': 'Launch site',
                          'JS_BEYANLI_TUVAL': {'tuval_genislik': 1600,
                                               'tuval_yukseklik': 946,
                                               'ekran_genislik': 1600,
                                               'ekran_yukseklik': 945}})
        assert gezgin.hatalar == []
        adlar = [d['ad'] for d in rapor['denetimler']]
        assert 'tuval_dolu' in adlar, (
            'Beyan edilen tuval için denetim ÜRETİLMEDİ — kalem geri geldi')
        assert 'plume_cizildi' not in adlar, (
            'Hesapsız sayfada egzoz denetimi hayalet olur')
        tuval = [d for d in rapor['denetimler'] if d['ad'] == 'tuval_dolu'][0]
        assert tuval['gecti'] is True, tuval['ozet']
        assert rapor['olcumler']['piksel']['dolu_oran'] > 0
        assert '#ls-globe canvas' in (rapor['olcumler']['tuval_kaynagi'] or '')
        assert ('locator_screenshot', '#ls-globe canvas') in sahte.gunluk

    def test_tuval_bulunamazsa_KIRMIZI_ama_akis_kesilmiyor(self, tmp_path):
        rapor, gezgin, _ = _gez(
            'launch-site', tmp_path,
            js_cevaplari={'JS_SAYFA_METNI': 'Launch site',
                          'JS_BEYANLI_TUVAL': {
                              'hata': 'beyan edilen tuval seçicisi hiçbir '
                                      'şeyi göstermiyor: #ls-globe canvas'}})
        assert gezgin.hatalar == [], 'ölçüm hatası akışı KESMEMELİ'
        tuval = [d for d in rapor['denetimler'] if d['ad'] == 'tuval_dolu'][0]
        assert tuval['gecti'] is False
        assert 'ölçülemedi' in tuval['ozet'] or 'göstermiyor' in tuval['ozet']

    def test_tuval_hazir_olmadan_OLCULMUYOR(self, tmp_path):
        """Hazır ölçütü patlarsa tuval "boş" değil ÖLÇÜLEMEDİ sayılır."""
        kosul = sayfalar.SAYFALAR['launch-site'].tuval_hazir_kosulu
        rapor, gezgin, _ = _gez(
            'launch-site', tmp_path,
            js_cevaplari={'JS_SAYFA_METNI': 'Launch site'},
            bekleme_hatalari={kosul: RuntimeError('küre çizmedi')})
        assert gezgin.hatalar == []
        tuval = [d for d in rapor['denetimler'] if d['ad'] == 'tuval_dolu'][0]
        assert tuval['gecti'] is False
        assert 'küre çizmedi' in tuval['ozet']

    def test_CANLI_olcum_kalemi_dogruluyor(self):
        once, sonra = _kanit('once_canli.json'), _kanit('sonra_canli.json')
        assert once['tur_launch_site']['tuval_kaynagi'] is None
        assert 'tuval_dolu' not in once['tur_launch_site']['denetimler']
        assert once['launch_site_dom']['tuval_sayisi'] == 1, (
            'Sayfada gerçekten bir tuval VARDI — atlama gerekçesi yanlıştı')
        assert sonra['tur_launch_site']['denetimler']['tuval_dolu'] is True
        assert sonra['tur_launch_site']['piksel']['dolu_oran'] > 0.2


# ===========================================================================
# C. OH-D25-02(b) — dilimli kanıtta TEKRAR BANT ölçülür
# ===========================================================================

def _dilim(yol, y0, h, uretilen=None, imza='a' * 64):
    return {'yol': yol, 'y0': y0, 'istenen_yukseklik': h,
            'px': {'genislik': 1600, 'yukseklik': uretilen or h},
            'sha256': imza}


def _goruntuler(dilimler, sayfa_y):
    return {'tam_sayfa': dilimler[0]['yol'],
            'tam_sayfa_px': dilimler[0]['px'],
            'tam_sayfa_dilimleri': dilimler,
            'sayfa_boyu_px': {'genislik': 1600, 'yukseklik': sayfa_y}}


class TestOHD2502BDilimImzalari:

    def test_saglam_dilimli_kanit_GECIYOR(self):
        d = [_dilim('a.png', 0, 8192, imza='1' * 64),
             _dilim('b.png', 8192, 8192, imza='2' * 64)]
        h = denetimler.tam_sayfa_goruntusu_denetimi(_goruntuler(d, 16384))
        assert h.gecti is True, h.ozet
        assert '2 ayrı içerik imzası' in h.ozet

    def test_BIREBIR_ayni_iki_dilim_SAHTE_KANIT(self):
        """Kalemin kökü: tavanı aşan bant üst bandın tekrarıydı."""
        d = [_dilim('a.png', 0, 8192, imza='9' * 64),
             _dilim('b.png', 8192, 8192, imza='9' * 64)]
        h = denetimler.tam_sayfa_goruntusu_denetimi(_goruntuler(d, 16384))
        assert h.gecti is False
        assert 'BİREBİR aynı' in h.ozet

    def test_imzasiz_dilim_FAIL_CLOSED(self):
        d = [_dilim('a.png', 0, 8192, imza='1' * 64),
             _dilim('b.png', 8192, 8192, imza=None)]
        h = denetimler.tam_sayfa_goruntusu_denetimi(_goruntuler(d, 16384))
        assert h.gecti is False
        assert 'imzası' in h.ozet

    def test_URETILEN_yukseklik_istenenden_kisa_ise_KIRMIZI(self):
        """Kapsam iddiası ÜRETİLEN görüntüden sayılır."""
        d = [_dilim('a.png', 0, 8192, uretilen=8192, imza='1' * 64),
             _dilim('b.png', 8192, 8192, uretilen=4096, imza='2' * 64)]
        h = denetimler.tam_sayfa_goruntusu_denetimi(_goruntuler(d, 16384))
        assert h.gecti is False
        assert 'üretildi' in h.ozet

    def test_tur_her_dilimin_IMZASINI_kaydediyor(self):
        kaynak = (KOK / 'tools/browser_harness/tur.py').read_text(
            encoding='utf-8')
        assert "'sha256': dosya_sha256(yol)" in kaynak, (
            'Dilim imzası kaydedilmiyorsa denetim onu ölçemez')
        assert tur.dosya_sha256(str(KOK / 'pytest.ini')), (
            'dosya_sha256 gerçek dosyada imza üretmeli')
        assert tur.dosya_sha256(str(KOK / 'yok-boyle-bir-dosya')) is None

    def test_CANLI_formulas_dilimleri_AYRI(self):
        sonra = _kanit('sonra_canli.json')
        f = sonra['formulas_dilimleri']
        assert f['dilim_sayisi'] == 5
        assert f['hepsi_farkli'] is True
        assert f['yinelenen_dilim_sayisi'] == 0
        assert f['uretilen_yukseklik_istenene_esit'] is True
        assert all(x['sha256_alani_var'] for x in f['dilimler'])
        assert (sonra['tur_formulas']['sayfa_boyu_px']['yukseklik']
                > denetimler.esikler.CHROMIUM_TEK_KARE_TAVANI_PX)


# ===========================================================================
# D. OH-D26-13 — yapışkan kutular yerleşim ölçümünü kaydırmaya bağlıyordu
# ===========================================================================

class TestOHD2613YapiskanYerlesim:

    def test_JS_YERLESIM_yapiskani_ETKISIZLESTIRIYOR(self):
        js = tur.JS_YERLESIM
        assert "yst.position !== 'sticky'" in js, (
            'Yapışkan kutular ölçüm öncesi akış konumuna alınmıyor')
        assert "el.style.position = 'static'" in js

    def test_JS_YERLESIM_satir_ici_stili_GERI_yaziyor(self):
        js = tur.JS_YERLESIM
        assert 'finally' in js, 'geri yazma finally dalında olmalı'
        kuyruk = js[js.index('finally'):]
        assert 'y.el.style.position = y.eski' in kuyruk, (
            'Ölçüm sayfayı DEĞİŞMİŞ bırakırsa sonraki adımlar (tam sayfa '
            'görüntüsü) yalan kanıt üretir')

    def test_JS_YERLESIM_yapiskan_sayisini_RAPORLUYOR(self):
        assert 'yapiskan_etkisizlestirilen: yapiskanlar.length' in tur.JS_YERLESIM

    def test_CANLI_olcum_ONCE_kaydirmaya_bagimliydi(self):
        once = _kanit('once_canli.json')
        assert once['olcum_kaydirmaya_BAGIMLI'] is True
        assert once['hybrid_sayfa_basinda']['ortusme_sayisi'] == 1
        assert once['hybrid_kaydirilmis']['ortusme_sayisi'] == 0
        kutular = {y['kimlik']: y for y
                   in once['hybrid_yapiskan_basta']['yapraklar']}
        kaydirilmis = {y['kimlik']: y for y
                       in once['hybrid_yapiskan_kaydirilmis']['yapraklar']}
        fark = abs(kutular['ac_history_box']['sayfa_y']
                   - kaydirilmis['ac_history_box']['sayfa_y'])
        assert fark == 654, (
            'Kalemin ölçülen büyüklüğü: aynı kutu iki kaydırma konumunda '
            '654 px farklı sayfa konumu bildiriyordu; ölçülen: %d' % fark)

    def test_CANLI_olcum_SONRA_kaydirmadan_BAGIMSIZ(self):
        sonra = _kanit('sonra_canli.json')
        assert sonra['olcum_kaydirmaya_BAGIMLI'] is False
        assert sonra['hybrid_sayfa_basinda']['ortusme_sayisi'] == 0
        assert sonra['hybrid_kaydirilmis']['ortusme_sayisi'] == 0
        assert sonra['hybrid_sayfa_basinda']['yapiskan_etkisizlestirilen'] == 3
        # Yaprak sayısı DEĞİŞMEDİ: ölçüm daraltılarak değil düzeltilerek
        # sessizleştirildi (örtüşmeyi gizlemek en kolay yalan olurdu).
        assert (sonra['hybrid_sayfa_basinda']['yaprak_sayisi']
                == _kanit('once_canli.json')['hybrid_sayfa_basinda'][
                    'yaprak_sayisi'])


# ===========================================================================
# E. OH-D26-19 — sürüm notu ile ÜRÜN bağlı
# ===========================================================================

#: Ürünün yayımladığı 422 gerekçe kodları ve onları basan dosya. Belge ile
#: kod ARASINDAKİ bağ budur: kod tarafı kaybolursa belge bayatlar, belge
#: tarafı kaybolursa sözleşme belgesiz kalır — iki yön de kırmızıdır.
_422_KODLARI = {
    'unread_canonical_field': 'hrma/app.py',
    'conflicting_combustion_input': 'hrma/app.py',
    'chamber_length_published_but_not_drawable': 'hrma/export/cad_visualization.py',
}


class TestOHD2619SurumNotu:

    @pytest.fixture(scope='class')
    def surum(self):
        ham = json.loads((KOK / 'hrma/data/changelog.json').read_text(
            encoding='utf-8'))
        return ham['versions'][0]

    def test_kaldirilan_API_kamu_yuzeyinde_YOK(self):
        stability = importlib.import_module('hrma.stability')
        assert not hasattr(stability, 'critical_response_table')
        assert 'critical_response_table' not in getattr(stability, '__all__', ())

    def test_kaldirilan_API_surum_notunda_ADIYLA_aniliyor(self, surum):
        for anahtar in ('notes_en', 'notes_tr'):
            assert 'critical_response_table' in surum[anahtar], (
                '%s: kaldırılan kamu API adı sürüm notunda geçmiyor'
                % anahtar)

    @pytest.mark.parametrize('kod,dosya', sorted(_422_KODLARI.items()))
    def test_422_kodu_hem_URUNDE_hem_BELGEDE(self, kod, dosya, surum):
        kaynak = (KOK / dosya).read_text(encoding='utf-8')
        assert kod in kaynak, (
            '%s artık %s içinde yok — sözleşme değişti, belge bayat'
            % (kod, dosya))
        for anahtar in ('notes_en', 'notes_tr'):
            assert kod in surum[anahtar], (
                '%s: 422 gerekçe kodu %s belgelenmemiş' % (anahtar, kod))

    def test_surum_notu_422yi_UYDURMA_YASAGIYLA_anlatiyor(self, surum):
        assert 'HTTP 422' in surum['notes_en']
        assert 'HTTP 422 ile reddedilir' in surum['notes_tr']
        assert 'UYDURULMAZ' in surum['notes_tr']


# ===========================================================================
# F. Bekçi borcu (p13b410 dağıtımı — altyapi'ye düşen iki kalem)
# ===========================================================================

class TestBekciBorcuP10B107ImalatBlogu:
    """XLSX 'Injector' sayfası İMALAT bloğunu döküyor mu (kalem sembolü)?

    P10B1-07 kapalı ama doğrudan bekçisi yoktu (D1 DOLAYLI). Kusur, üç
    enjektör bloğunun ayrışması ve ayrışan tek tüketicinin XLSX olmasıydı:
    dökülen sayılar STEP/DXF/teknik çizim zincirinin kullandığı bloktan
    BAŞKA bir bloktan geliyordu ve bu hiçbir yerde söylenmiyordu.
    """

    @pytest.fixture(scope='class')
    def sablon(self):
        return (KOK / 'hrma/templates/advanced.html').read_text(encoding='utf-8')

    def test_xlsx_IMALAT_blogunu_tercih_ediyor(self, sablon):
        assert 'const injMan = (currentResults.injector' in sablon, (
            'XLSX imalat bloğunu (motor.injector) okumuyor')
        yer_man = sablon.index('const injMan')
        yer_alt = sablon.index('const injAlt')
        assert yer_man < yer_alt, 'imalat bloğu ikincil bloktan sonra geliyor'

    def test_xlsx_KAYNAK_blogunu_beyan_ediyor(self, sablon):
        assert "inj.push(['(source block)'" in sablon
        assert 'the same block the STEP / DXF' in sablon, (
            'İmalat bloğu dökülürken kaynağı BEYAN edilmiyor')
        assert 'is NOT the block the STEP / DXF' in sablon, (
            'Yedek bloğa düşüldüğünde kullanıcı bunu ÖĞRENMİYOR — sessiz '
            'yedek yasağı (fail-closed beyanı)')

    def test_ucun_yayimladigi_blok_ADI_degismedi(self):
        kaynak = (KOK / 'hrma/app.py').read_text(encoding='utf-8')
        assert 'injector_results' in kaynak, (
            'app.py imalat bloğunu bu adla taşıyordu; ad değiştiyse XLSX '
            'beyanı bayatlar')


class TestBekciBorcuP10B401IddiaLint:
    """``iddia_lint`` kampanya künye-yalanı sınıfını GÖRÜYOR mu?"""

    @pytest.fixture(scope='class')
    def lint(self):
        from tools import iddia_lint
        return iddia_lint

    #: Her kural için ELLE yazılmış bir örnek: kural tablosu canlı mı?
    KURAL_ORNEKLERI = {
        'nasa_grade': 'This is a NASA-grade solver.',
        'nasa_validated': 'NASA validated results included.',
        'flight_certified': 'The design is flight-certified.',
        'safe_for_operation': 'The motor is safe for operation.',
        'professional_grade': 'A professional-grade toolchain.',
    }

    @pytest.mark.parametrize('kural_adi', sorted(KURAL_ORNEKLERI))
    def test_kampanya_kunye_yalani_YAKALANIYOR(self, lint, kural_adi, tmp_path):
        metin = self.KURAL_ORNEKLERI[kural_adi]
        dosya = tmp_path / 'ornek.md'
        dosya.write_text(metin + '\n', encoding='utf-8')
        bulgular = lint.scan_file(str(dosya))
        adlar = {b.rule_id for b in bulgular}
        assert kural_adi in adlar, (
            '%s kuralı %r metnini kaçırdı (bulunan: %s)'
            % (kural_adi, metin, sorted(adlar)))

    def test_kural_tablosu_KUCULMUYOR(self, lint):
        adlar = {k.rule_id for k in lint.ALL_RULES}
        assert adlar >= set(self.KURAL_ORNEKLERI), (
            'Kural tablosundan kural DÜŞTÜ: %s'
            % sorted(set(self.KURAL_ORNEKLERI) - adlar))
        assert len(lint.ALL_RULES) >= 15, (
            'Kampanya sınıfı 15 kuralla ölçülmüştü; tablo %d kurala düşmüş'
            % len(lint.ALL_RULES))

    def test_arac_BIR_OTOMASYONDA_kosuyor(self):
        """"Hiçbir kapıyı korumuyor" yarısı: bağ ÖLÇÜLÜR."""
        import subprocess
        r = subprocess.run(
            ['git', 'grep', '-l', 'iddia_lint', '--', 'tests/',
             '.github/workflows/', 'packaging/'],
            cwd=str(KOK), capture_output=True, text=True)
        bagli = sorted(x for x in r.stdout.split('\n') if x.strip())
        assert bagli, ('iddia_lint hiçbir teste/kapıya bağlı değil — '
                       'koşmayan araç kapı değildir')
        assert any(y.startswith('tests/') for y in bagli), bagli


# ===========================================================================
# G. Sözdizimi/bütünlük — dokunulan JS parçaları geçerli kalsın
# ===========================================================================

class TestDokunulanKaynaklarSaglam:

    @pytest.mark.parametrize('ad', ['JS_YERLESIM', 'JS_BEYANLI_TUVAL'])
    def test_js_parcasi_DENGELI(self, ad):
        js = getattr(tur, ad)
        assert js.count('{') == js.count('}'), '%s süslü parantez dengesiz' % ad
        assert js.count('(') == js.count(')'), '%s parantez dengesiz' % ad

    def test_sayfa_tanimi_AST_ile_gecerli(self):
        """ÖH D27 fix-27a — İDDİA GÖVDEYE GİRDİ (OH-D23-01 / OH-D24-04).

        Eski gövde yalnız ``ast.parse`` çağırıyordu: hiçbir ``assert``
        taşımıyordu ve "iddiasız test" envanterine düşüyordu. Kusur
        teorik değil: dosya BOŞALTILIRSA ``ast.parse('')`` sorunsuz
        çalışır, yani sözdizimi geçerliliği ayağı boş modülde de yeşil
        kalırdı. Onarım hem doğrudan iddia getirir hem de ölçütü
        sıkılaştırır: her dosya (i) ayrıştırılabilir, (ii) BOŞ DEĞİL,
        (iii) en az bir tanım (``def``/``class``/atama) taşır.
        """
        beklenen = ('tools/browser_harness/tur.py',
                    'tools/browser_harness/sayfalar.py',
                    'tools/browser_harness/denetimler.py',
                    'tools/sabit_envanteri.py')
        bos = []
        for yol in beklenen:
            tam = KOK / yol
            assert tam.is_file(), 'kaynak kayboldu: %s' % yol
            agac = ast.parse(tam.read_text(encoding='utf-8'))
            if not [d for d in agac.body
                    if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef, ast.Assign,
                                      ast.AnnAssign))]:
                bos.append(yol)
        assert bos == [], (
            'şu kaynaklar ayrıştırılıyor ama TANIM taşımıyor (boşaltılmış '
            'dosya sözdizimi geçerlidir, bu test onu geçirmemeli): %r' % bos)

    def test_changelog_JSON_gecerli_ve_TR_karakterli(self):
        ham = (KOK / 'hrma/data/changelog.json').read_text(encoding='utf-8')
        d = json.loads(ham)
        # karar §28-19/§28-46: yayımlanmamış 2.6.27 kaydı 3.0.0 adıyla çıkar.
        assert d['versions'][0]['version'] == '3.0.0'
        assert re.search(r'[çğıöşüÇĞİÖŞÜ]', d['versions'][0]['notes_tr'])
