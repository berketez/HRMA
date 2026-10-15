# -*- coding: utf-8 -*-
"""ÖH Dalga-19 / kulvar `electron` / aşama a1 — bekçiler.

Kapsam: Fable-D17 denetçisinin iki ŞART'ı.

  P12aB3-09 ŞART-1  `chartCap.altitude_preview` altyazısı figürü "uçuş
                    çözümünün önizlemesi" sayıyordu. Ürün öyle çalışmıyor:
                    `advanced.html previewAltProfile()` hiçbir çözücüye
                    gitmez; kullanıcının girdiği alt_start/alt_end/alt_points
                    taraması boyunca `altitudeToPressure()` = ISA 1976 ortam
                    basıncını çizer. Üç metin (EN yedek + sözlük EN + TR)
                    yanlış beyan taşıyordu.
  P12aB3-09 ŞART-2  Katı sayfasında Three.js güverte yolu kurulduğunda
                    `Plotly.newPlot` hiç çağrılmıyor, dolayısıyla altyazı
                    katmanının sarmalayıcısı da tetiklenmiyordu: CAD 3B
                    görünümü YALNIZ o yolda açıklamasız kalıyordu.
  P12aB3-08 ŞART    D17 ölçüm betiğinin `site.ballistic` regex'i kaçışı iki
                    kez yazıyordu (`'site\\.ballistic'`), bu yüzden hiçbir
                    ağaçta eşleşmiyordu; rapordaki "false→true" iddiasının
                    arkasında üretilmiş bir sayı yoktu. Kanıt hijyeni bu
                    bekçiyle kilitlenir.

Her iddia, onarımın geri alınmasıyla kırmızıya döner (bkz.
docs/scofield/raw/OH/D19/electron/a1/mutasyon.json).
"""
import json
import os
import re
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D17 = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D17',
                   'electron', 'a1')


def oku(rel):
    with open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


def _dengeli(metin, desen):
    """`desen` eşleşmesinden sonraki ilk `{`...`}` gövdesini döndürür."""
    m = re.search(desen, metin)
    if not m:
        return ''
    i = metin.index('{', m.start())
    derinlik = 0
    for j in range(i, len(metin)):
        if metin[j] == '{':
            derinlik += 1
        elif metin[j] == '}':
            derinlik -= 1
            if derinlik == 0:
                return metin[i + 1:j]
    return ''


def _yorumsuz(govde):
    return '\n'.join(s for s in govde.split('\n')
                     if not s.lstrip().startswith('//'))


def dil_bloklari(rel):
    metin = oku(rel)
    return (_dengeli(metin, r'\ben:\s*\{'), _dengeli(metin, r'\btr:\s*\{'))


def deger(govde, anahtar):
    m = re.search(r"'" + re.escape(anahtar) + r"':\s*'((?:[^'\\]|\\.)*)'",
                  govde)
    return m.group(1) if m else None


# ==========================================================================
# P12aB3-09 ŞART-1 — irtifa önizlemesi altyazısı ürünü anlatıyor mu?
# ==========================================================================
class TestP12aB309Sart1AltitudeOnizlemesi:
    ANAHTAR = 'chartCap.altitude_preview'

    def _uc_metin(self):
        en, tr = dil_bloklari('hrma/static/js/i18n_shell.js')
        cc = _yorumsuz(_dengeli(oku('hrma/static/js/chart_captions.js'),
                                r'var CAPTIONS = \{'))
        return (deger(cc, self.ANAHTAR), deger(en, self.ANAHTAR),
                deger(tr, self.ANAHTAR))

    def test_uc_metnin_ucu_de_tanimli(self):
        yedek, en, tr = self._uc_metin()
        assert yedek and en and tr, (
            'EN yedek / sözlük EN / sözlük TR üçü de bulunmalı: %r'
            % ((bool(yedek), bool(en), bool(tr)),))

    def test_ucus_cozumu_iddiasi_hicbir_dilde_kalmadi(self):
        yedek, en, tr = self._uc_metin()
        assert 'flight solution' not in yedek.lower()
        assert 'flight solution' not in en.lower()
        assert 'uçuş çözümünün' not in tr.lower()

    def test_ne_cizdigini_soyluyor(self):
        yedek, en, tr = self._uc_metin()
        assert 'ambient pressure' in en.lower(), (
            'EN metin figürün ORTAM BASINCI çizdiğini söylemeli')
        assert 'ambient pressure' in yedek.lower(), (
            'sözlük yüklenemezse görünen EN yedek de düzeltilmiş olmalı')
        assert 'ortam basıncı' in tr.lower(), (
            'TR metin figürün ORTAM BASINCI çizdiğini söylemeli')

    def test_standart_atmosfer_kaynagi_adiyla_yaziyor(self):
        _yedek, en, tr = self._uc_metin()
        assert 'standard atmosphere' in en.lower()
        assert 'standart atmosfer' in tr.lower()

    def test_iddia_urunle_ortusuyor(self):
        """Altyazının 'çözücü sonucu değildir' iddiası ÜRÜNDE de doğru mu?"""
        adv = oku('hrma/templates/advanced.html')
        govde = _dengeli(adv, r'function previewAltProfile\(\)')
        assert 'altitudeToPressure(' in govde, (
            'önizleme artık basıncı ISA yardımcısından almıyor — altyazı '
            'iddiası ürünle örtüşmüyor')
        assert '_isaPressurePaJS' in adv
        assert 'fetch(' not in govde and 'await ' not in govde, (
            'önizleme bir çözücüye gidiyorsa "solver result değildir" '
            'beyanı yalan olur')
        for alan in ('alt_start', 'alt_end', 'alt_points'):
            assert "getElementById('%s')" % alan in govde, (
                'altyazı kullanıcının %s taramasını anıyor; ürün onu '
                'okumuyorsa beyan yanlıştır' % alan)


# ==========================================================================
# P12aB3-09 ŞART-2 — Three.js güverte yolunda CAD altyazısı
# ==========================================================================
class TestP12aB309Sart2GuverteAltyazisi:
    def _guverte_dali(self):
        solid = oku('hrma/templates/solid.html')
        show3d = _dengeli(solid, r'function show3DVisualization\(\)')
        assert 'MotorVizDeck.create(' in show3d, (
            'güverte yolu kayboldu — bekçi ölçtüğü şeyi bulamıyor')
        return _dengeli(show3d, r'if \(deck\) \{')

    def test_guverte_kurulunca_altyazi_bagleniyor(self):
        dal = self._guverte_dali()
        assert 'HRMA_CAPTIONS' in dal, (
            'Three.js güvertesi kurulduğunda Plotly.newPlot çağrılmıyor; '
            'altyazı açıkça bağlanmazsa CAD görünümü açıklamasız kalır')
        assert 'attachKnown(cadView)' in dal
        assert 'return;' in dal, (
            'ölçtüğümüz dal erken dönüşü olan güverte dalı olmalı')

    def test_altyazi_katmani_attachKnown_disa_aciyor(self):
        cc = oku('hrma/static/js/chart_captions.js')
        m = re.search(r'window\.HRMA_CAPTIONS = \{([^}]*)\}', cc)
        assert m, 'dışa açık API kayboldu'
        assert 'attachKnown' in m.group(1)
        assert 'attachKnown: maybeAttach' in m.group(1), (
            'attachKnown, anahtarı ve yedek metni konteynerin id\'sinden '
            'çözen maybeAttach olmalı (tek kaynak)')

    def test_metin_solid_html_te_yeniden_yazilmadi(self):
        """TEK KAYNAK: altyazı metni şablona kopyalanmamalı."""
        solid = oku('hrma/templates/solid.html')
        assert 'not a manufacturing drawing' not in solid, (
            'CAD altyazı metni şablona kopyalanmış — ikinci tanım')

    def test_cad_3d_view_anahtari_altyazi_katmaninda_duruyor(self):
        cc = _yorumsuz(_dengeli(oku('hrma/static/js/chart_captions.js'),
                                r'var CAPTIONS = \{'))
        assert deger(cc, 'chartCap.cad_3d_view'), (
            'attachKnown yedek metni CAPTIONS gövdesinden okur; anahtar '
            'yoksa güverte yolunda sessizce hiçbir şey eklenmez')


# ==========================================================================
# P12aB3-08 ŞART — kanıt hijyeni: D17 ölçüm betiği gerçekten ölçüyor mu?
# ==========================================================================
class TestP12aB308SartKanitHijyeni:
    @staticmethod
    def olcum_kodu():
        """D17 ölçüm betiğinin YORUMSUZ kodu.

        Düzeltmenin kendi açıklaması bozuk deseni alıntılıyor; ölçüt koda
        bakmalı, yoruma değil (ilk sürümde bu bekçi kendi yorumundan
        kırmızıya döndü).
        """
        kaynak = open(kanit_gerekli(os.path.join(D17, 'olcum.py')), encoding='utf-8').read()
        return '\n'.join(satir for satir in kaynak.split('\n')
                         if not satir.lstrip().startswith('#'))

    def test_olcum_regexi_iki_kez_kacis_yazmiyor(self):
        kaynak = self.olcum_kodu()
        assert r"'site\\.ballistic'" not in kaynak, (
            "regex kaçışı iki kez yazılmış (r\"...\\\\.\"): hiçbir ağaçta "
            'eşleşmez, ölçüm her zaman false döner')
        assert r"'site\.ballistic'" in kaynak

    def test_regex_gercek_sozlukte_esleşiyor(self):
        """Betiğin kullandığı desen ÜRÜN sözlüğünde eşleşmeli."""
        kaynak = self.olcum_kodu()
        m = re.search(r"anahtar_sozlukte_tanimli_mi'?\s*:\s*bool\(re\.search\("
                      r'r"([^"]+)"', kaynak)
        assert m, 'ölçüm satırı bulunamadı'
        ls = oku('hrma/static/js/i18n_launch_site.js')
        assert re.search(m.group(1), ls), (
            'betiğin deseni gerçek sözlükte eşleşmiyor')

    def test_yeniden_uretilen_sayilar_iddiayi_tasiyor(self):
        once = json.load(open(kanit_gerekli(os.path.join(D17, 'once.json')),
                              encoding='utf-8'))
        sonra = json.load(open(kanit_gerekli(os.path.join(D17, 'sonra.json')),
                               encoding='utf-8'))
        assert once['P12aB3-08']['anahtar_sozlukte_tanimli_mi'] is False
        assert sonra['P12aB3-08']['anahtar_sozlukte_tanimli_mi'] is True, (
            'raporun "false→true" iddiası yeniden üretilen sayıya bağlanmalı')

    def test_aciklanan_grafik_sayisi_yorumdan_beslenmiyor(self):
        sonra = json.load(open(kanit_gerekli(os.path.join(D17, 'sonra.json')),
                               encoding='utf-8'))
        cc = oku('hrma/static/js/chart_captions.js')
        govde = set(re.findall(r"'chartCap\.([A-Za-z0-9_]+)'",
                               _yorumsuz(_dengeli(cc, r'var CAPTIONS = \{'))))
        tum = set(re.findall(r"'chartCap\.([A-Za-z0-9_]+)'", cc))
        assert tum - govde, 'dosyada yalnız yorumda geçen anahtar kalmadı'
        assert sonra['P12aB3-09']['aciklanan_grafik_sayisi'] <= len(govde), (
            'kanıttaki sayı CAPTIONS gövdesindeki gerçek anahtar sayısını '
            'aşıyor — yorum satırları sayılmış')
