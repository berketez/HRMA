"""V301 / kulvar N-YZ — "Yapay Zekâ ile Tasarla" bekçisi.

Berke (26 Eki): "Yapay zekaya sor butonunda ben ne yapıyorsam, ne girdileri
veriyorsam, nasıl motor yapmak istiyorsam hepsini sormak gerekiyor ...
programdaki yapay zeka kullanımını arttıralım, son kullanıcı bazında."

ÖNCE (taban ``a95ed4b60``): üç sayfada üç ayrı "Ask AI to Analyze Results"
kopyası (app.js / solid.html / liquid.html ``askAI``), satır içi tema dışı
gradyanlar (mor / pembe / mavi), elle seçilmiş JSON (katı 9, sıvı 8 girdi;
hibrit 7), İngilizce SABİT istem, asistanın önerisini geri almanın yolu yok.

SONRA: tek ortak modül ``hrma/static/js/ai_assistant.js`` (``window.HRMAAI``):
tasarım hedefi + formun TAMAMI + sonuçlar/uyarılar/hükümler/CEA + arayüz
dilinde istem; asistanın ``hrma-oneri`` bloğu GÜVENİLMEZ girdi olarak
doğrulanır ve önce/sonra tablosuyla, onayla uygulanır; devam paketi.

Bekçiler:
  (a) paket formun HER alanını içerir — Playwright ölçümü (kanıt dizini
      ``playwright.json``) okunur; üç sayfa × TR/EN.
  (b) öneri ayrıştırıcı — node altında GERÇEK modül: geçerli blok geçer;
      bilinmeyen alan, birim uyuşmazlığı, metin değer, seçenek dışı değer,
      sonlu olmayan sayı, motor tipi uyuşmazlığı, fazla değişiklik → ADLI ret;
      modül hiçbir yerde HTML yorumlamaz (gerekçe metin olarak basılır).
  (c) üç sayfa aynı modülü kullanır, eski üç ``askAI`` kopyası yok.
  (d) düğme ve panel stili tema tokenından (satır içi stil yok).
  (e) istem TR arayüzde Türkçe, EN arayüzde İngilizce.

Ters mutasyon: ``docs/scofield/raw/OH/V301/yapay-zeka/mutasyon.py``.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
YZ_MODUL_YOLU = JS / 'ai_assistant.js'
SABLON = KOK / 'hrma' / 'templates'
YZ_SAYFA_SABLONLARI = {'hybrid': SABLON / 'advanced.html',
            'solid': SABLON / 'solid.html',
            'liquid': SABLON / 'liquid.html'}
TEMA = KOK / 'hrma' / 'static' / 'css' / 'theme.css'
KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'V301' / 'yapay-zeka'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node bulunamadı')


def _node(betik: str) -> dict:
    r = subprocess.run([NODE, '-e', betik], capture_output=True, text=True,
                       timeout=120, cwd=str(KOK))
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


#: Doğrulamanın alan tanımları — sayfadaki gerçek alanlardan seçilmiş
#: temsilciler (katı sayfa: chamber_pressure bar, grain_type seçici,
#: inhibit_front onay kutusu, propellant_name metin, gamma birimsiz).
YZ_ORNEK_ALAN_TANIMLARI = {
    'chamber_pressure': {'id': 'chamber_pressure', 'type': 'number',
                         'unit': 'bar', 'options': None, 'min': 1,
                         'max': 300, 'label': 'Chamber Pressure (bar)',
                         'value': 40},
    'grain_type': {'id': 'grain_type', 'type': 'select', 'unit': None,
                   'options': ['bates', 'star', 'finocyl'], 'min': None,
                   'max': None, 'label': 'Grain Type', 'value': 'bates'},
    'inhibit_front': {'id': 'inhibit_front', 'type': 'checkbox',
                      'unit': None, 'options': None, 'min': None,
                      'max': None, 'label': 'Front Face', 'value': False},
    'propellant_name': {'id': 'propellant_name', 'type': 'text',
                        'unit': None, 'options': None, 'min': None,
                        'max': None, 'label': 'Propellant', 'value': 'KNDX'},
    'gamma': {'id': 'gamma', 'type': 'number', 'unit': None, 'options': None,
              'min': 1.05, 'max': 1.5, 'label': 'Specific Heat Ratio',
              'value': 1.122},
}


def _dogrula(metin: str, tip: str = 'solid') -> dict:
    betik = (
        "const A = require('./hrma/static/js/ai_assistant.js');\n"
        "const r = A.oneriDogrula(%s, %s, %s);\n"
        "if (r.ok) r.reddedilen.forEach(x => x.metin = A.retMetni(x.kod, x.params));\n"
        "else r.metin = A.retMetni(r.kod, r.params);\n"
        "process.stdout.write(JSON.stringify(r));"
    ) % (json.dumps(metin), json.dumps(tip), json.dumps(YZ_ORNEK_ALAN_TANIMLARI))
    return _node(betik)


def _blok(degisiklikler, tip='solid', surum=1) -> str:
    govde = json.dumps({'hrma_oneri': surum, 'motor_type': tip,
                        'degisiklikler': degisiklikler}, ensure_ascii=False)
    return 'Önerim şu:\n\n```hrma-oneri\n' + govde + '\n```\nBaşarılar.'


# ---------------------------------------------------------------------------
# (b) Öneri ayrıştırıcı — yapıştırılan metin GÜVENİLMEZDİR
# ---------------------------------------------------------------------------
@node_gerekli
class TestOneriAyristirici:

    def test_gecerli_blok_uygulanabilir(self):
        r = _dogrula(_blok([
            {'alan': 'chamber_pressure', 'deger': 25, 'birim': 'bar',
             'gerekce': 'kasa kütlesi'},
            {'alan': 'grain_type', 'deger': 'star', 'gerekce': 'itki eğrisi'},
            {'alan': 'inhibit_front', 'deger': True},
            {'alan': 'gamma', 'deger': 1.2, 'birim': '-'},
        ]))
        assert r['ok'], r
        assert [g['alan'] for g in r['gecerli']] == [
            'chamber_pressure', 'grain_type', 'inhibit_front', 'gamma']
        assert r['reddedilen'] == []
        g0 = r['gecerli'][0]
        assert (g0['simdiki'], g0['onerilen'], g0['birim']) == (40, 25, 'bar')

    def test_cit_olmadan_duz_json_da_okunur(self):
        govde = json.dumps({'hrma_oneri': 1, 'motor_type': 'solid',
                            'degisiklikler': [{'alan': 'chamber_pressure',
                                               'deger': 30, 'birim': 'bar'}]})
        r = _dogrula(govde)
        assert r['ok'] and len(r['gecerli']) == 1, r

    @pytest.mark.parametrize('satir, kod', [
        ({'alan': 'yok_boyle_alan', 'deger': 1}, 'unknown_field'),
        ({'alan': '__proto__', 'deger': 1}, 'unknown_field'),
        ({'alan': 'chamber_pressure', 'deger': 25, 'birim': 'psi'}, 'unit_mismatch'),
        ({'alan': 'chamber_pressure', 'deger': 25}, 'unit_missing'),
        ({'alan': 'gamma', 'deger': 1.2, 'birim': 'bar'}, 'unit_unexpected'),
        ({'alan': 'chamber_pressure', 'deger': '25', 'birim': 'bar'}, 'not_number'),
        ({'alan': 'chamber_pressure', 'deger': 900, 'birim': 'bar'}, 'out_of_range'),
        ({'alan': 'grain_type', 'deger': 'moon_shape'}, 'not_option'),
        ({'alan': 'inhibit_front', 'deger': 'yes'}, 'not_boolean'),
        ({'alan': 'propellant_name', 'deger': 42}, 'not_text'),
        ({'alan': 'propellant_name', 'deger': 'x' * 501}, 'text_too_long'),
        ({'deger': 3}, 'bad_row'),
    ])
    def test_satir_adiyla_reddedilir(self, satir, kod):
        # Eş satır reddedilen satırın alanına DOKUNMAZ (aynı alan ikinci kez
        # 'duplicate' olurdu): seçici değişikliği, seçici satırı sınanıyorsa
        # onay kutusu.
        es = ({'alan': 'inhibit_front', 'deger': True}
              if satir.get('alan') == 'grain_type'
              else {'alan': 'grain_type', 'deger': 'star'})
        r = _dogrula(_blok([satir, es]))
        assert r['ok'], r
        assert [x['kod'] for x in r['reddedilen']] == [kod], r['reddedilen']
        assert r['reddedilen'][0]['metin'], 'ret nedeni metinsiz'
        # Kısmi geçerli blok: geçerli satır seçilebilir kalır.
        assert [g['alan'] for g in r['gecerli']] == [es['alan']]

    def test_sonlu_olmayan_sayi_reddedilir(self):
        # JSON NaN/Infinity yazamaz; 1e999 ayrıştırmada Infinity olur.
        metin = ('```hrma-oneri\n{"hrma_oneri": 1, "motor_type": "solid", '
                 '"degisiklikler": [{"alan": "chamber_pressure", '
                 '"deger": 1e999, "birim": "bar"}]}\n```')
        r = _dogrula(metin)
        assert r['ok'] and [x['kod'] for x in r['reddedilen']] == ['not_finite'], r

    def test_ayni_alan_iki_kez_reddedilir(self):
        r = _dogrula(_blok([
            {'alan': 'chamber_pressure', 'deger': 25, 'birim': 'bar'},
            {'alan': 'chamber_pressure', 'deger': 26, 'birim': 'bar'}]))
        assert [x['kod'] for x in r['reddedilen']] == ['duplicate']

    @pytest.mark.parametrize('metin, kod', [
        (_blok([{'alan': 'chamber_pressure', 'deger': 25, 'birim': 'bar'}],
               tip='liquid'), 'motor_type'),
        (_blok([{'alan': 'chamber_pressure', 'deger': 25, 'birim': 'bar'}],
               surum=2), 'version'),
        (_blok([{'alan': 'chamber_pressure', 'deger': 20 + i, 'birim': 'bar'}
                for i in range(9)]), 'too_many'),
        (_blok([]), 'no_changes'),
        ('```hrma-oneri\n{"hrma_oneri": 1, "motor_type": \n```', 'json'),
        ('```hrma-oneri\n[1, 2]\n```', 'not_object'),
        ('Merhaba, önerim yok.', 'no_block'),
        ('', 'empty'),
        (_blok([{'alan': 'gamma', 'deger': 1.2}]) + '\n'
         + _blok([{'alan': 'gamma', 'deger': 1.3}]), 'multiple_blocks'),
        ('x' * 100001, 'too_long'),
    ])
    def test_blok_butunuyle_adiyla_reddedilir(self, metin, kod):
        r = _dogrula(metin)
        assert not r['ok'] and r['kod'] == kod, r
        assert r['metin'] and r['metin'] != kod

    def test_ust_sinir_tek_kaynaktan(self):
        """Fazla değişiklik eşiği modülün sabitidir; istem de aynı sayıyı söyler."""
        out = _node("const A=require('./hrma/static/js/ai_assistant.js');"
                    "process.stdout.write(JSON.stringify({n:A.AZAMI_DEGISIKLIK,"
                    "tr:A.istemMetni('tr','solid'),en:A.istemMetni('en','solid')}));")
        assert out['n'] == 8
        assert 'en çok 8 değişiklik' in out['tr']
        assert 'at most 8 changes' in out['en']

    def test_gerekce_html_olarak_yorumlanmaz(self):
        """Modül HTML yorumlayan HİÇBİR API kullanmaz; gerekçe ``textContent``."""
        src = YZ_MODUL_YOLU.read_text(encoding='utf-8')
        kod = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
        kod = re.sub(r'(?m)^\s*//.*$', '', kod)
        for yasak in ('innerHTML', 'outerHTML', 'insertAdjacentHTML',
                      'document.write', 'eval(', 'new Function'):
            assert yasak not in kod, 'ai_assistant.js %s kullanıyor' % yasak
        assert "el(doc, 'td', 'hrma-ai-reason', g.gerekce || '')" in src
        r = _dogrula(_blok([{'alan': 'chamber_pressure', 'deger': 25,
                             'birim': 'bar',
                             'gerekce': '<img src=x onerror=alert(1)><script>x()</script>'}]))
        assert r['gecerli'][0]['gerekce'].startswith('<img'), (
            'gerekçe ham metin olarak taşınmalı (basım textContent ile)')


# ---------------------------------------------------------------------------
# OH-GT-07 deseni ortak modülde korunur (pano başarısızsa metin kaybolmaz)
# ---------------------------------------------------------------------------
_SAHTE_DOM = r"""
const kayit = { eklenen: [], uyari: [] };
function dugum(tag) {
  return { tagName: String(tag).toUpperCase(), attrs: {}, children: [], parentNode: null,
    className: '', id: '', textContent: '', value: '', disabled: false, readOnly: false,
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] || null; },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; },
    addEventListener() {}, focus() {}, select() {} };
}
const body = dugum('body');
body.appendChild = function (c) { c.parentNode = body; kayit.eklenen.push(c); return c; };
global.document = { body, createElement: dugum, getElementById: () => null,
  addEventListener() {}, removeEventListener() {}, readyState: 'complete' };
global.window = global;
console.warn = function () { kayit.uyari.push(Array.from(arguments)); };
function bul(d, sinif) {
  if (!d) return null;
  if ((d.className || '').split(' ').indexOf(sinif) >= 0) return d;
  for (const c of d.children || []) { const x = bul(c, sinif); if (x) return x; }
  return null;
}
"""


def _pano(navigator_js: str) -> dict:
    # Node 21+ `navigator`ı salt-okunur bir global olarak taşır; sahte nesne
    # defineProperty ile yerleşir (düz atama sessizce yok sayılırdı).
    navigator_js = navigator_js.replace(
        'global.navigator = ', "Object.defineProperty(global, 'navigator', "
        "{configurable: true, writable: true, value: ").rstrip(';') + '});'
    betik = _SAHTE_DOM + navigator_js + r"""
const A = require('./hrma/static/js/ai_assistant.js');
const P = A._Panel;
const ctx = { doc: document, gosterDugmesi: { disabled: true }, durumlar: [],
  bildir(m, t) { this.durumlar.push([t, m]); } };
P.prototype.metniVer.call(ctx, 'VERI <script>alert(1)</script> SON', 'KOPYALANDI').then(function (ok) {
  const m = kayit.eklenen[0] || null;
  const ta = bul(m, 'hrma-ai-modal-text');
  const giris = bul(m, 'hrma-ai-modal-intro');
  process.stdout.write(JSON.stringify({ ok, pencere: !!m, id: m && m.id,
    role: m && m.getAttribute('role'), metin: ta && ta.value,
    giris: giris && giris.textContent, uyari: kayit.uyari.map(a => a.map(String)),
    durum: ctx.durumlar, goster_acik: !ctx.gosterDugmesi.disabled }));
});
"""
    return _node(betik)


@node_gerekli
class TestPanoDaliOrtakModul:

    def test_pano_reddedilince_metin_pencerede(self):
        out = _pano("global.navigator = { clipboard: { writeText: () => Promise.reject("
                    "{ name: 'NotAllowedError', message: 'denied' }) } };")
        assert out['ok'] is False
        assert out['pencere'] and out['id'] == 'hrmaAiModal'
        assert out['role'] == 'dialog'
        assert out['metin'] == 'VERI <script>alert(1)</script> SON', (
            'metin textarea.value ile, kaçışsız ama YORUMLANMADAN yerleşmeli')
        assert 'NotAllowedError: denied' in out['giris']
        assert out['goster_acik'], '"Metni göster" düğmesi açılmalı'

    def test_ham_hata_nesnesi_loglanmaz(self):
        out = _pano("global.navigator = { clipboard: { writeText: () => Promise.reject("
                    "{ name: 'NotAllowedError', message: 'denied' }) } };")
        assert out['uyari'], 'pano hatası konsola hiç yazılmıyor'
        assert out['uyari'][0][1] == 'NotAllowedError: denied', out['uyari']

    @pytest.mark.parametrize('nav', [
        "global.navigator = {};",
        "global.navigator = { clipboard: { writeText: () => { throw new Error('senkron'); } } };",
    ])
    def test_pano_apisi_yoksa_senkron_firlatmaz(self, nav):
        out = _pano(nav)
        assert out['pencere'] and out['metin'].startswith('VERI'), out

    def test_basarida_pencere_acilmaz_durum_yazilir(self):
        out = _pano("global.navigator = { clipboard: { writeText: () => Promise.resolve() } };")
        assert out['ok'] is True and not out['pencere']
        assert out['durum'][-1] == ['ok', 'KOPYALANDI']


# ---------------------------------------------------------------------------
# (c) Üç sayfa aynı modül; eski kopyalar yok
# ---------------------------------------------------------------------------
class TestTekModul:

    @pytest.mark.parametrize('tip', sorted(YZ_SAYFA_SABLONLARI))
    def test_sayfa_ortak_modulu_ve_kabi_tasir(self, tip):
        src = YZ_SAYFA_SABLONLARI[tip].read_text(encoding='utf-8')
        assert src.count('<script src="/static/js/ai_assistant.js"></script>') == 1
        kap = re.findall(r'<section id="hrmaAiPanel"[^>]*>', src)
        assert len(kap) == 1, kap
        assert 'data-motor-type="%s"' % tip in kap[0]
        assert 'style=' not in kap[0], 'panel kabında satır içi stil'
        # Proje şeridinden SONRA yüklenir (alan kümesinin tek tanımı oradadır).
        assert (src.index('<script src="/static/js/project_bar.js">')
                < src.index('<script src="/static/js/ai_assistant.js">'))

    @pytest.mark.parametrize('dosya', ['static/js/app.js', 'templates/advanced.html',
                                       'templates/solid.html', 'templates/liquid.html'])
    def test_eski_askai_kopyasi_yok(self, dosya):
        src = (KOK / 'hrma' / dosya).read_text(encoding='utf-8')
        for iz in ('function askAI(', 'onclick="askAI()"', 'function showAIDataModal(',
                   'Ask AI to Analyze Results', 'navigator.clipboard.writeText(prompt)'):
            assert iz not in src, '%s hâlâ eski kopyayı taşıyor: %s' % (dosya, iz)

    def test_modul_uc_adaptoru_tasir(self):
        if NODE is None:
            pytest.skip('node yok')
        out = _node("const A=require('./hrma/static/js/ai_assistant.js');"
                    "process.stdout.write(JSON.stringify(Object.keys(A.ADAPTORLER).map("
                    "k=>[k,A.ADAPTORLER[k].hesapIslevi])));")
        assert sorted(out) == [['hybrid', 'calculate'], ['liquid', 'calculateLiquid'],
                               ['solid', 'calculateSolid']]


# ---------------------------------------------------------------------------
# (d) Görünüm tema tokenından
# ---------------------------------------------------------------------------
def _css_kurallari(src: str, onek: str):
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', src):
        secici = m.group(1).strip()
        if onek in secici:
            yield secici, m.group(2)


class TestTemaTokeni:

    def test_dugme_ve_panel_renkleri_token(self):
        css = TEMA.read_text(encoding='utf-8')
        kurallar = list(_css_kurallari(css, '.hrma-ai'))
        assert len(kurallar) >= 20, 'hrma-ai bölümü theme.css içinde yok'
        btn = [g for s, g in kurallar if s.startswith('.hrma-ai-btn')]
        assert btn, '.hrma-ai-btn kuralı yok'
        for govde in btn:
            for satir in govde.split(';'):
                if re.search(r'(^|\s|-)(color|background|border(-color)?)\s*:', satir):
                    deger = satir.split(':', 1)[1]
                    assert not re.search(r'#[0-9a-fA-F]{3,8}\b|rgba?\(', deger), (
                        'düğme rengi token dışı: ' + satir.strip())
        for eski in ('#667eea', '#f093fb', '#4facfe'):
            for s, g in kurallar:
                assert eski not in g

    def test_modul_satir_ici_stil_yazmaz(self):
        src = YZ_MODUL_YOLU.read_text(encoding='utf-8')
        assert '.style.' not in src and "'style'" not in src and 'cssText' not in src


# ---------------------------------------------------------------------------
# (e) İstem arayüz dilinde
# ---------------------------------------------------------------------------
@node_gerekli
class TestIstemDili:

    @pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
    def test_tr_istem_turkce_en_istem_ingilizce(self, tip):
        out = _node("const A=require('./hrma/static/js/ai_assistant.js');"
                    "process.stdout.write(JSON.stringify({tr:A.istemMetni('tr',%r),"
                    "en:A.istemMetni('en',%r)}));" % (tip, tip))
        tr, en = out['tr'], out['en']
        assert 'Kurallar:' in tr and 'Sen bir itki sistemi' in tr
        assert re.search(r'[çğıöşüİ]', tr)
        assert 'Rules:' not in tr and 'You are' not in tr
        assert 'Rules:' in en and 'Kurallar' not in en
        assert not re.search(r'[çğıöşüİ]', en.replace('hrma-oneri', ''))
        for metin in (tr, en):
            assert '```hrma-oneri' in metin and '"motor_type": "%s"' % tip in metin
            assert '"hrma_oneri": 1' in metin


# ---------------------------------------------------------------------------
# (a) Paket formun HER alanını içerir — Playwright ölçümü (kanıt)
# ---------------------------------------------------------------------------
class TestPaketTamami:

    @pytest.fixture(scope='class')
    def olcum(self):
        # Ters mutasyon kancası: mutasyon.py ölçümü ayrı bir dosyaya yazar.
        ozel = os.environ.get('HRMA_YZ_OLCUM')
        yol = pathlib.Path(ozel) if ozel else kanit_gerekli(KANIT / 'playwright.json')
        return json.loads(yol.read_text(encoding='utf-8'))

    def test_uc_sayfa_iki_dil_olculdu(self, olcum):
        if os.environ.get('HRMA_YZ_OLCUM'):
            pytest.skip('ters mutasyon koşusu: tek sayfa ölçüldü')
        assert sorted(olcum['kosumlar']) == sorted(
            '%s-%s' % (t, d) for t in ('hybrid', 'solid', 'liquid') for d in ('tr', 'en'))

    @pytest.mark.parametrize('kosum', ['%s-%s' % (t, d) for t in ('hybrid', 'solid', 'liquid')
                                       for d in ('tr', 'en')])
    def test_alan_sayisi_esit_ve_her_alan_pakette(self, olcum, kosum):
        if kosum not in olcum['kosumlar'] and os.environ.get('HRMA_YZ_OLCUM'):
            pytest.skip('ters mutasyon koşusu: bu sayfa ölçülmedi')
        k = olcum['kosumlar'][kosum]
        assert k['form_alan_sayisi'] >= 60, k['form_alan_sayisi']
        assert k['paket_alan_sayisi'] == k['form_alan_sayisi'], k
        assert k['pakette_olmayan'] == [], k['pakette_olmayan'][:10]
        assert k['metinde_olmayan'] == [], k['metinde_olmayan'][:10]
        assert k['hesap_durumu'] == 200 and k['uygula_hesap_durumu'] == 200
        assert k['form_degisti'], 'öneri uygulandıktan sonra form değeri değişmedi'
        assert k['istem_dili_dogru']
        assert k['cakisma'] == [], k['cakisma'][:5]
