"""ÖH Dalga-22 · arayuz kulvarı · aşama-2 bekçileri.

Her sınıf bir kalemi kilitler. Testler ÜRÜN KAYNAĞINI koşturur ya da
ürün kaynağının yapısını ölçer; kopya beklenen metin yazılmaz.

Kanıt: docs/scofield/raw/OH/D22/arayuz/a2/
  once.json / sonra.json        — node harness ölçümü
  canli_sonra.json              — CANLI Chrome (sistem kanalı) ölçümü
  mutasyon.json                 — ters-mutasyon kırmızı kanıtı
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
NODE = shutil.which('node')

I18N_JS = os.path.join(KOK, 'hrma', 'static', 'js', 'i18n.js')
HUD_JS = os.path.join(KOK, 'hrma', 'static', 'js', 'hud.js')
TUR_PY = os.path.join(KOK, 'tools', 'browser_harness', 'tur.py')
ADV_HTML = os.path.join(KOK, 'hrma', 'templates', 'advanced.html')
DOCK_JS = os.path.join(KOK, 'hrma', 'static', 'js', 'analysis_dock.js')


def _oku(yol: str) -> str:
    with open(yol, encoding='utf-8') as f:
        return f.read()


def _kume_sok(kaynak: str, bas_isaret: str) -> str:
    """`bas_isaret` ile başlayan bloğu süslü parantez sayarak söker."""
    bas = kaynak.index(bas_isaret)
    i = kaynak.index('{', bas)
    derinlik = 0
    for j in range(i, len(kaynak)):
        c = kaynak[j]
        if c == '{':
            derinlik += 1
        elif c == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[bas:j + 1]
    raise AssertionError('kapanmadi: ' + bas_isaret)


def _node(kod: str) -> dict:
    assert NODE, 'node bulunamadi'
    ci = subprocess.run([NODE], input=kod, capture_output=True, text=True,
                        timeout=120)
    assert ci.returncode == 0, ci.stderr[-2000:]
    return json.loads(ci.stdout)


# =====================================================================
# P17B1-11 — ekranda 17 anlamlı basamaklı ham kayan nokta
# =====================================================================
class TestEkranAnlamliBasamak:
    """I18N.number, `digits` verilmediğinde ham double repr'ini basmaz."""

    def _kos(self) -> dict:
        src = _oku(I18N_JS)
        parcalar = [_kume_sok(src, 'I18N.number = function') + ';',
                    _kume_sok(src, 'I18N.t = function') + ';']
        yardimci = ''
        if 'function ekranBasamagi(' in src:
            m = re.search(r'var YEDEK_SIGFIG\s*=\s*\d+;', src)
            yardimci = (m.group(0) if m else '') + '\n' \
                + _kume_sok(src, 'function ekranBasamagi(')
        # ÖH D30 / P12aB1-01 — DÜZENEK GENİŞLETMESİ (mandallar DEĞİŞMEDİ).
        # `I18N.number` ondalık ayracını artık kendi gövdesinde yazmıyor;
        # ayraç TEK KAYNAK olarak `ondalikAyraci()` yardımcısında yaşıyor
        # (aynı yardımcıyı `I18N.decimalText` de okur — iki yerde yazılsaydı
        # biri kayar ve "tek cümlede iki ondalık ayracı" kusuru geri gelirdi).
        # Bu sınıfın ÖLÇTÜĞÜ ŞEY basamak sayısı ve ayraç doğruluğudur;
        # aşağıdaki iddiaların hiçbiri gevşetilmedi — yalnız node dilimi,
        # kaynağın gerçekten ihtiyaç duyduğu yardımcıyı da alacak biçimde
        # genişletildi (`ekranBasamagi` için zaten var olan desenin aynısı).
        if 'function ondalikAyraci(' in src:
            yardimci += '\n' + _kume_sok(src, 'function ondalikAyraci(')
        kod = """
            var STRINGS = { en: {}, tr: {} };
            var DEFAULT_LANG = 'en';
            var global = { AnalysisDock: null };
            var I18N = { lang: 'en' };
            %s
            %s
            var o = {
                uzun: I18N.number(1.4241155826338074),
                tamsayi: I18N.number(5),
                kisa: I18N.number(101.325),
                sifir: I18N.number(0),
                negatif: I18N.number(-3.5),
                kucuk: I18N.number(0.0000368),
                buyuk: I18N.number(1234567),
                basamakli: I18N.number(1.4241155826338074, 2),
                metin: I18N.number('abc'),
                bos: I18N.number(null),
                sonsuz: I18N.number(Infinity)
            };
            I18N.lang = 'tr';
            o.tr_ondalik = I18N.number(1.4241155826338074);
            process.stdout.write(JSON.stringify(o));
        """ % (yardimci, '\n'.join(parcalar))
        return _node(kod)

    def test_ham_double_repr_basilmaz(self):
        """P17 turunun ekranda yakaladığı L/D 17 basamakla basılmamalı."""
        o = self._kos()
        basamak = len(re.sub(r'[^0-9]', '', o['uzun']))
        assert basamak <= 8, (
            'I18N.number ham double repr basiyor: %r (%d basamak)'
            % (o['uzun'], basamak))
        assert 'e' not in o['uzun'].lower()
        assert o['uzun'].startswith('1.424')

    def test_kisa_sayilar_degismez(self):
        """Zaten kısa yazılmış hiçbir sayı bozulmaz (regresyon nöbetçisi)."""
        o = self._kos()
        assert o['tamsayi'] == '5'
        assert o['kisa'] == '101.325'
        assert o['sifir'] == '0'
        assert o['negatif'] == '-3.5'
        assert o['kucuk'] == '0.0000368'
        assert o['buyuk'] == '1234567'

    def test_acik_basamak_ve_sayi_disi_yollar_korunur(self):
        o = self._kos()
        assert o['basamakli'] == '1.42', 'digits verildiginde eski davranis'
        assert o['metin'] == 'abc'
        assert o['bos'] == ''
        assert o['sonsuz'] == 'Infinity'

    def test_tr_ondalik_ayirici_korunur(self):
        o = self._kos()
        assert ',' in o['tr_ondalik'] and '.' not in o['tr_ondalik']

    def test_basamak_sayisi_tek_kaynaktan(self):
        """Ekran basamağı analysis_dock.js DOCK_SIGFIG ile aynı olmalı."""
        src = _oku(I18N_JS)
        m = re.search(r'var YEDEK_SIGFIG\s*=\s*(\d+);', src)
        assert m, 'YEDEK_SIGFIG tanimli degil'
        d = re.search(r'const DOCK_SIGFIG\s*=\s*(\d+);', _oku(DOCK_JS))
        assert d, 'analysis_dock.js DOCK_SIGFIG bulunamadi'
        assert m.group(1) == d.group(1), (
            'i18n.js YEDEK_SIGFIG=%s ile analysis_dock.js DOCK_SIGFIG=%s '
            'ayristi' % (m.group(1), d.group(1)))
        assert 'AnalysisDock' in src, (
            'canli tek kaynak (AnalysisDock.ui.SIGFIG) okunmuyor')


# =====================================================================
# P17B1-12 — turun metin taraması form alanlarına kördü
# =====================================================================
class TestTurMetinTaramasiFormAlanlariniGorur:

    def test_js_sayfa_metni_form_degeri_topluyor(self):
        src = _oku(TUR_PY)
        m = re.search(r'JS_SAYFA_METNI = ("""(.*?)"""|"[^"]*")', src, re.S)
        assert m, 'JS_SAYFA_METNI bulunamadi'
        ifade = m.group(0)
        assert 'innerText' in ifade, 'gorunen metin hala okunmali'
        assert 'querySelectorAll' in ifade and '.value' in ifade, (
            'metin taramasi hala yalniz innerText: form alani degerleri '
            'yapisal olarak gorunmez kalir (P17B1-12)')

    def test_gizli_ve_parola_alanlari_taranmaz(self):
        src = _oku(TUR_PY)
        m = re.search(r'JS_SAYFA_METNI = """(.*?)"""', src, re.S)
        assert m
        ifade = m.group(1)
        for tip in ('hidden', 'password'):
            assert tip in ifade, '%s alani atlanmali' % tip
        assert 'selectedOptions' in ifade, (
            'select icin kullanicinin GORDUGU secenek metni alinmali')

    def test_ifade_gecerli_javascript(self):
        src = _oku(TUR_PY)
        m = re.search(r'JS_SAYFA_METNI = """(.*?)"""', src, re.S)
        assert m
        o = _node(
            'const f = %s;\n'
            'process.stdout.write(JSON.stringify({tip: typeof f}));'
            % m.group(1).strip())
        assert o['tip'] == 'function'

    def test_canli_olcum_nobetciyi_goruyor(self):
        """CANLI Chrome ölçümü: nöbetçi alan değeri taranan metinde."""
        yol = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D22',
                           'arayuz', 'a2', 'canli_sonra.json')
        if not os.path.exists(kanit_gerekli(yol)):
            pytest.skip('canli olcum dosyasi yok')
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            d = json.load(f)
        o = d['P17B1-12']
        assert o['nobetci_eski_metinde'] is False
        assert o['nobetci_yeni_metinde'] is True
        assert o['ayirt_edici_yenide'] == o['ayirt_edici_deger']


# =====================================================================
# P17B2-01 — HUD hükmü: kapsayıcıda data-state iken LED rengi değişmiyordu
# =====================================================================
class TestHudHukumLedeUlasir:

    def _bind(self) -> str:
        return _kume_sok(_oku(HUD_JS), 'function bindState(')

    def test_bindState_led_dugumune_de_basar(self):
        govde = self._bind()
        assert 'hd-led' in _oku(HUD_JS), '.hd-led dugumu taninmali'
        # Hükmü LED'e YAZAN yol aranır; silen yol (removeAttribute) saymaz.
        assert re.search(r"led\.setAttribute\(\s*'data-state'", govde), (
            'bindState hukmu yalnizca kapsayiciya yaziyor: LED `--led` '
            'degerini kendi uzerinde tanimladigi icin hukum renge hic '
            'ulasmaz (P17B2-01, fail-open)')

    def test_renk_disi_kanal_var(self):
        govde = self._bind()
        assert re.search(r"led\.setAttribute\(\s*'aria-label'", govde), (
            'hukum YALNIZ renkle veriliyor: renk disi kanal yok')
        assert re.search(r"led\.setAttribute\(\s*'data-verdict'", govde)

    def test_taninmayan_hukumde_temizlenir(self):
        govde = self._bind()
        assert govde.count('removeAttribute') >= 3, (
            'taninmayan sozcukte LED uzerindeki hukum izleri de silinmeli '
            '(yoksa eski hukum ekranda kalir)')

    def test_canli_olcum_dort_hukum_ayrisiyor(self):
        yol = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'D22',
                           'arayuz', 'a2', 'canli_bind_sonra.json')
        if not os.path.exists(kanit_gerekli(yol)):
            pytest.skip('canli bind olcumu yok')
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            d = json.load(f)
        renkler = {k: v['arkaplan'] for k, v in d.items()
                   if not k.startswith('_')}
        assert renkler['MARGINAL'] != renkler['SAFE'], (
            'MARGINAL ile SAFE ayni renk: hukum ekrana ulasmiyor')
        assert renkler['UNSAFE'] != renkler['SAFE'], (
            'UNSAFE ile SAFE ayni renk: fail-open')
        assert d['_temizlendi']['state'] is None


# =====================================================================
# P17B4-01 — proje gidiş-dönüşü: fuel_density ezilmesi (ÇÜRÜTME KİLİDİ)
# =====================================================================
class TestKarisimYogunlugPaylasilanAlaniEzmez:
    """ÇEVRİLDİ (ÖH D33-KOLAY · OH-D32-11) — koruduğu şey artık YAPISAL.

    ESKİ SÖZLEŞME: ``updateMixtureDensity()`` node altında koşturulup
    ``fuel_type`` süzgecinin paylaşılan alanları (``fuel_density``,
    ``regression_a/n``) EZMEDİĞİ sınanıyordu. O sınamanın var olması, ölü
    fonksiyonun sayfada DURMASINI şart koşuyordu; yani KUSURU KORUYAN bir
    bekçiydi (D32 arayuz-panel a1 raporu bunu "iki mevcut çürütme kilidi
    onları hâlâ ölçtüğü için … ayrı karar" diye kaydetmişti).

    ÖLÇÜLDÜ (D33 arayuz-panel a1/once.json · M2b, ÜRÜN KODU node içinde):
    fonksiyonun okuduğu panel OH-D31-05'te sökülmüştü, yani her dil
    değişiminde ``null.value`` TypeError'ı fırlıyordu; zincir
    ``['inj','prs','imp']``de kesiliyor ve ``checkDatabaseStatus()`` HİÇ
    çalışmıyordu.

    YENİ SÖZLEŞME — P17B4-01'in kazanımı DAHA GÜÇLÜ biçimde kilitlenir:
    fonksiyon SİLİNDİ, dolayısıyla paylaşılan alanları ezebilecek yol
    kalmadı. Bekçi (1) dört ölü fonksiyonun geri gelmediğini, (2) dil
    değişimi zincirinin CANLI koşumda paylaşılan alanlara dokunmadığını
    ve zinciri sonuna kadar (``checkDatabaseStatus``) yürüttüğünü ölçer.
    """

    ZINCIR_KOSUMU = """
            var cagrilar = [];
            var dom = {};
            function kur(id, v) { dom[id] = { value: String(v),
                                              textContent: '', style: {} }; }
            kur('fuel_type', 'htpb');
            kur('fuel_density', '920');
            kur('regression_a', '3.68e-5');
            kur('regression_n', '0.555');
            var document = { getElementById: function (id) {
                return dom[id] || null; } };
            function updateInjectorParams() { cagrilar.push('inj'); }
            function refreshPressureModeLabels() { cagrilar.push('prs'); }
            function updateCalculatedImpulse() { cagrilar.push('imp'); }
            function checkDatabaseStatus() { cagrilar.push('db'); }
            var uyari = [];
            var console = { warn: function (m, e) {
                uyari.push(String(m) + ' ' + String(e)); } };
            %s
            process.stdout.write(JSON.stringify({
                cagrilar: cagrilar, uyari: uyari,
                fuel_density: dom.fuel_density.value,
                regression_a: dom.regression_a.value,
                regression_n: dom.regression_n.value
            }));
        """

    def _zincir_govdesi(self) -> str:
        adv = _oku(ADV_HTML)
        m = re.search(r'if \(I18N\.onChange\) I18N\.onChange\(function \(\) \{'
                      r'(.*?)\n            \}\);', adv, re.S)
        assert m, 'dil değişimi geri çağırımı bulunamadı'
        return m.group(1)

    def test_olu_karisim_fonksiyonlari_geri_gelmedi(self):
        adv = _oku(ADV_HTML)
        kod = re.sub(r'<!--.*?-->', '', adv, flags=re.S)
        for ad in ('updateMixtureDensity', 'addCompositionRow',
                   'removeCompositionRow', 'validateComposition'):
            assert not re.search(r'function %s\s*\(' % ad, kod), (
                '%s geri geldi: erişilemez panel okuyan ölü fonksiyon '
                '(OH-D32-11)' % ad)

    def test_dil_degisimi_paylasilan_alanlara_dokunmuyor(self):
        o = _node(self.ZINCIR_KOSUMU % self._zincir_govdesi())
        assert (o['fuel_density'], o['regression_a'], o['regression_n']) == \
            ('920', '3.68e-5', '0.555'), (
                'dil degisimi paylasilan motor alanlarini ezdi '
                '(P17B4-01 yeniden acildi): %r' % o)

    def test_dil_degisimi_zinciri_sonuna_kadar_yuruyor(self):
        """OH-D32-11 CANLI KUSURU: zincir ortasında kesilmiyor."""
        o = _node(self.ZINCIR_KOSUMU % self._zincir_govdesi())
        assert o['cagrilar'] == ['inj', 'prs', 'imp', 'db'], (
            'dil degisimi zinciri kesildi (olculen kusur: %r); '
            'checkDatabaseStatus calismiyor' % (o['cagrilar'],))
        assert o['uyari'] == [], (
            'zincir hala firlatiyor: %r' % (o['uyari'],))
