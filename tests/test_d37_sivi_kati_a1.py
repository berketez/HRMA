"""ÖH D37 A1b · sivi-kati-form (kart A1b-1) — sıvı/katı sayfa şablonu bekçileri.

Tema: form çevrim tutarlılığı ve sonuç ekranında beyan — sessiz varsayım,
ham enum, ham alan adı, uydurma yedek, yerli ``alert`` kutusu. Kalemler ve
ölçümler: ``docs/scofield/raw/OH/A1b/sivi-kati-form/a1/rapor.md``.

Teknik: bekçiler DAVRANIŞ ölçer. Şablondaki GERÇEK işlev gövdeleri
parantez dengesiyle sökülüp ``node`` içinde koşturulur (tests/
test_viz_adaptorleri.py kalıbı); çeviri gerektiren düğümler gerçek sözlük
motorunu (i18n.js + i18n_common.js + i18n_pages.js, ``setLang('tr')``)
yükler. Ölçüm önermesi sunucuya dayanan düğümler Flask test istemcisiyle
gerçek uca gider. Bu dosya ``docs/`` kanıtı OKUMAZ (yayın dalında da koşar).

Kalem ⟷ sınıf:
  (a) CW-F1         TestCevrimFormu
  (b) CW-A4E6       TestDefaultsApplied
  (c) CW-U6         TestBildirim
  (d) CW-SU3b       TestCidarKaynagi
  (e) DV-KATIMOTOR  TestKatiPdfMotorTipi
  (f) DV36-09       TestKati3BKesit
  (g) OH-D37-S1     TestEngAlanEtiketi
  (h) OH-D37-S7     TestVizYedekleri
"""

import contextlib
import copy
import io
import json
import pathlib
import re
import math
import shutil
import subprocess
from html.parser import HTMLParser

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
LIQ = KOK / 'hrma' / 'templates' / 'liquid.html'
SOLID = KOK / 'hrma' / 'templates' / 'solid.html'
JS = KOK / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
ORNEK_SIVI = KOK / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma'
ORNEK_KATI = KOK / 'examples' / 'Example Solid KNDX BATES 75mm.hrma'

node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: CW-F1 — basınç beslemede gizlenen ve gövdeden düşen dört alan.
TURBIN_ALANLARI = ('turbopump_efficiency', 'generator_gas_temp',
                   'turbine_inlet_pressure', 'turbine_expansion_ratio')
FORM_CEVRIM_SECENEKLERI = ('pressure_fed', 'gas_generator', 'staged_combustion',
             'full_flow_staged', 'expander', 'tap_off')


# ---------------------------------------------------------------------------
# Kaynak sökücüler + node koşucusu
# ---------------------------------------------------------------------------
def _oku(yol: pathlib.Path) -> str:
    return yol.read_text(encoding='utf-8')


def _blok(kaynak: str, bas: str) -> str:
    """``bas`` ile başlayan ilk işlev/sabit bloğunu parantez dengesiyle al."""
    i = kaynak.index(bas)
    j = min(k for k in (kaynak.find('{', i), kaynak.find('[', i)) if k != -1)
    ac = kaynak[j]
    kap = '}' if ac == '{' else ']'
    derinlik = 0
    for k in range(j, len(kaynak)):
        if kaynak[k] == ac:
            derinlik += 1
        elif kaynak[k] == kap:
            derinlik -= 1
            if derinlik == 0:
                son = k + 1
                if kaynak[son:son + 1] == ';':
                    son += 1
                return kaynak[i:son]
    raise AssertionError('blok kapanmadı: %r' % bas)


def _fn(kaynak: str, ad: str) -> str:
    return _blok(kaynak, 'function %s(' % ad)


def _node(betik: str) -> dict:
    out = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout)


#: Gerçek sözlük motoru (TR/EN). ``global.window = global`` ile i18n.js
#: ``global.T``/``global.TF``'yi kurar (i18n.js:756).
_SOZLUK = r"""
global.window = global;
Object.defineProperty(global, 'localStorage', { value: { getItem() { return null; }, setItem() {} }, configurable: true });
Object.defineProperty(global, 'navigator', { value: { language: 'en' }, configurable: true });
global.document = global.document || { documentElement: { lang: 'en', setAttribute() {}, getAttribute() { return null; } },
    querySelectorAll() { return []; }, addEventListener() {}, readyState: 'complete' };
require(%(i18n)s); require(%(common)s); require(%(pages)s);
window.I18N.setLang(%(lang)s);
"""


def _sozluk(lang: str) -> str:
    return _SOZLUK % {'i18n': json.dumps(str(JS / 'i18n.js')),
                      'common': json.dumps(str(JS / 'i18n_common.js')),
                      'pages': json.dumps(str(JS / 'i18n_pages.js')),
                      'lang': json.dumps(lang)}


def _sozluk_degeri(anahtar: str, lang: str) -> str:
    betik = _sozluk(lang) + (
        'process.stdout.write(JSON.stringify({v: T(%s, null)}));\n'
        % json.dumps(anahtar))
    return _node(betik)['v']


def _js_yorumsuz(kod: str) -> str:
    """Blok ve satır yorumlarını söker (dizgedeki '://' korunur)."""
    kod = re.sub(r'/\*.*?\*/', ' ', kod, flags=re.S)
    return re.sub(r'(^|[\s;{}(),])//[^\n]*', r'\1', kod)


def _satir_ici_betikler(html: str) -> str:
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    govdeler = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>',
                          html, flags=re.S)
    return '\n'.join(_js_yorumsuz(g) for g in govdeler)


# ---------------------------------------------------------------------------
# Flask istemcisi (modül fikstürü)
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def istemci(tmp_path_factory, monkeypatch_module):
    monkeypatch_module.setenv('HRMA_PROJECTS_DIR',
                              str(tmp_path_factory.mktemp('hrma_projeler')))
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def _post(istemci, yol, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        r = istemci.post(yol, json=govde)
    return r.status_code, r.get_json()


def _duz(o, p='', out=None):
    if out is None:
        out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            _duz(v, '%s.%s' % (p, k) if p else k, out)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            _duz(v, '%s[%d]' % (p, i), out)
    else:
        out[p] = o
    return out


def _sivi_govde(cevrim):
    """Örnek sıvı projenin form alanları + istenen çevrim."""
    alanlar = json.loads(_oku(ORNEK_SIVI))['inputs']['fields']
    govde = {k: v for k, v in alanlar.items() if v not in (None, '')}
    govde['engine_cycle'] = cevrim
    if cevrim == 'pressure_fed':
        # V301/T-ÇAPA-D: örnek sıvı (ÖRNEK 5fa435893) gaz jeneratörü
        # çevrimi için feed_pressure = 75 bar taşıyor; basınç beslemede uç
        # gereken tank basıncını (yakıt tarafı 76,3 bar) adıyla istiyor
        # (422 pressure_fed_tank_below_required, ölçüldü 28 Eki). Vaka
        # geçerli besleme basıncıyla kurulur: sayfanın şablon varsayılanı
        # (tek kaynak; tests/test_d32_ihracat_a1.py Z5_SIVI ile aynı yol).
        from tests.support import form_defaults
        govde['feed_pressure'] = form_defaults.sayisal_varsayilanlar(
            'liquid')['feed_pressure']
    return govde


# ===========================================================================
# (a) CW-F1 — çevrim formu
# ===========================================================================
class TestCevrimFormu:

    @node_gerekli
    def test_tablo_basinc_beslemede_dort_alan_digerlerinde_bos(self):
        html = _oku(LIQ)
        betik = (_blok(html, 'const LIQ_CYCLE_UNREAD_FIELDS') + '\n'
                 + _fn(html, 'liqCycleUnreadFields') + '\n'
                 + 'const o = {};\n'
                 + 'for (const c of %s) o[c] = liqCycleUnreadFields(c);\n'
                 % json.dumps(list(FORM_CEVRIM_SECENEKLERI) + ['bilinmeyen']))
        betik += 'process.stdout.write(JSON.stringify(o));\n'
        o = _node(betik)
        assert sorted(o['pressure_fed']) == sorted(TURBIN_ALANLARI)
        # V301/L-D (L-A DEVİR 2) — BEKLENTİ DEĞİŞTİ: turbopompalı çevrimde
        # sunucu ``feed_pressure``ı okumuyor ve ``inputs_not_used`` ile
        # beyan ediyor (L-A SV-10, FEED_PRESSURE_UNUSED_REASON); form artık
        # alanı o beş çevrimde gizler ve göndermez. Tanınmayan çevrimde
        # hiçbir alan gizlenmez.
        for c in FORM_CEVRIM_SECENEKLERI[1:]:
            assert o[c] == ['feed_pressure'], c
        assert o['bilinmeyen'] == []

    @node_gerekli
    @pytest.mark.parametrize('cevrim,gizli', [('pressure_fed', True),
                                              ('gas_generator', False),
                                              ('staged_combustion', False)])
    def test_gizlenen_alan_govdeye_girmez_gorunen_girer(self, cevrim, gizli):
        """syncLiquidCycleFields (gerçek) → collectAllParameters (gerçek)."""
        html = _oku(LIQ)
        kod = '\n'.join([
            _blok(html, 'const LIQ_CYCLE_UNREAD_FIELDS'),
            _blok(html, 'const LIQ_CYCLE_FIELDS_WATCHED'),
            _fn(html, 'liqCycleUnreadFields'),
            _fn(html, 'liqOptNum'),
            # V3.0.5 T-ÇAPA-C1 (altyapı): V301/L-C (8ee59c845) toplayıcıya
            # enjektör tipinin kanon adı ve pintle/pintle-dışı alan yükünü
            # ekledi; ikiz bu gerçek tanımları da taşır (vekil yok).
            _blok(html, 'const LIQ_INJECTOR_LEGACY'),
            _fn(html, 'liqInjectorCanonical'),
            _blok(html, 'const LIQ_PINTLE_FIELDS'),
            _blok(html, 'const LIQ_NOT_PINTLE_FIELDS'),
            _fn(html, 'liqInjectorFieldPayload'),
            _fn(html, 'collectAllParameters'),
            _fn(html, 'syncLiquidCycleFields'),
        ])
        betik = r"""
const cevrim = %(cevrim)s;
const izlenen = %(izlenen)s;
const gruplar = [];
function grup(uye) {
  const g = { style: {}, _a: {}, uye: uye,
    setAttribute(a, v) { this._a[a] = String(v); },
    removeAttribute(a) { delete this._a[a]; },
    getAttribute(a) { return (a in this._a) ? this._a[a] : null; },
    querySelectorAll() { return [uye]; } };
  gruplar.push(g); return g;
}
const ogeler = {};
function oge(id) {
  if (!(id in ogeler)) {
    const o = { id: id, value: '', _a: {}, textContent: '', style: {},
      setAttribute(a, v) { this._a[a] = String(v); }, getAttribute(a) { return this._a[a] || null; } };
    if (izlenen.indexOf(id) !== -1 || id === 'feed_pressure') { const g = grup(o); o.closest = () => g; }
    else o.closest = () => null;
    ogeler[id] = o;
  }
  return ogeler[id];
}
global.document = {
  getElementById: oge,
  querySelectorAll(sel) {
    if (sel === '.form-group[data-cycle-hidden]') return gruplar.filter(g => g.getAttribute('data-cycle-hidden') !== null);
    return [];
  },
};
global.window = global;
function T(k, f) { return f; }
oge('engine_cycle').value = cevrim;
oge('preburner_type_group');
oge('feed_pressure').value = '130';
izlenen.forEach(id => { oge(id).value = '7'; });
%(kod)s
syncLiquidCycleFields();
const govde = JSON.parse(JSON.stringify(collectAllParameters()));
const gorunum = {};
izlenen.forEach(id => { gorunum[id] = oge(id).closest('.form-group').style.display; });
process.stdout.write(JSON.stringify({ anahtarlar: Object.keys(govde), gorunum: gorunum,
  not_anahtari: oge('feed_pressure_cycle_note').getAttribute('data-i18n') }));
""" % {'cevrim': json.dumps(cevrim), 'izlenen': json.dumps(list(TURBIN_ALANLARI)),
            'kod': kod}
        o = _node(betik)
        for alan in TURBIN_ALANLARI:
            if gizli:
                assert alan not in o['anahtarlar'], alan
                assert o['gorunum'][alan] == 'none', alan
            else:
                assert alan in o['anahtarlar'], alan
                assert o['gorunum'][alan] == '', alan
        # V301/L-D (L-A DEVİR 2) — BEKLENTİ DEĞİŞTİ: feed_pressure yalnız
        # basınç beslemede gövdeye girer (tank basıncı); turbopompalı
        # çevrimde sunucu onu okumuyor, form gizler ve göndermez.
        if cevrim == 'pressure_fed':
            assert 'feed_pressure' in o['anahtarlar']
        else:
            assert 'feed_pressure' not in o['anahtarlar']
        assert o['not_anahtari'] == ('liq.ui.feed_pressure_note_pressure_fed'
                                     if cevrim == 'pressure_fed'
                                     else 'liq.ui.feed_pressure_note_turbopump')

    def test_basinc_beslemede_dort_alan_hicbir_sayiyi_oynatmiyor(self, istemci):
        """Gizleme kararının ÖNERMESİ: alanlar o çevrimde okunmuyor.

        Motor bu alanlardan birini basınç beslemede okumaya başlarsa bu
        düğüm kırmızı olur ve form gizlemesi yeniden ölçülmelidir (gizli
        alan yayımlanan sayıyı değiştirirse kulvar DUR kuralı). İzin verilen
        tek fark gönderilen türbin alanlarının BEYANIDIR: V3 taban-a (14 Eki,
        KAB devri N7) türbinsiz motora basılan 'warn.liquid.turbine_pr_inconsistent'
        uyarısını kaldırdı; alanlar artık değerlendirilmez ve
        ``inputs_not_used`` (reason 'no_turbine_in_this_cycle') + bilgi
        uyarısı 'warn.liquid.turbine_input_not_used_pressure_fed' ile adıyla
        beyan edilir (tests/test_v3_taban_a_turbinsiz.py).
        """
        ile = _sivi_govde('pressure_fed')
        for alan, deger in zip(TURBIN_ALANLARI, (60, 800, 60, 8)):
            ile[alan] = deger
        olmadan = {k: v for k, v in ile.items() if k not in TURBIN_ALANLARI}
        d1, y1 = _post(istemci, '/calculate_liquid', ile)
        d2, y2 = _post(istemci, '/calculate_liquid', olmadan)
        assert d1 == 200 and d2 == 200
        beyan_kodu = 'warn.liquid.turbine_input_not_used_pressure_fed'
        for y in (y1, y2):
            assert 'warn.liquid.turbine_pr_inconsistent' not in [
                w.get('code') for w in y.get('input_warnings', [])]
        u1 = [w for w in y1.get('input_warnings', [])
              if w.get('code') != beyan_kodu]
        u2 = [w for w in y2.get('input_warnings', [])
              if w.get('code') != beyan_kodu]
        assert u1 == u2
        a = _duz({k: v for k, v in y1.items()
                  if k not in ('input_warnings', 'inputs_not_used')})
        b = _duz({k: v for k, v in y2.items()
                  if k not in ('input_warnings', 'inputs_not_used')})
        farkli = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        assert farkli == [], farkli[:10]
        # Türbinsiz çevrimde karşılaştırma YAPILMAZ: alan iki gövdede de
        # 'karşılaştırma' diye beyan edilmez; gönderilen türbin alanları
        # inputs_not_used'da adıyla durur.
        assert 'turbine_inlet_pressure' not in y1['unwired_inputs']['reported_for_comparison']
        assert 'turbine_inlet_pressure' not in y2['unwired_inputs']['reported_for_comparison']
        beyanli = sorted(b['field'] for b in (y1.get('inputs_not_used') or [])
                         if b.get('reason') == 'no_turbine_in_this_cycle')
        assert beyanli == sorted(('turbine_inlet_pressure',
                                  'turbine_expansion_ratio'))

    def test_tank_basinci_alani_eklenmedi(self):
        # tank_pressure çözücü girdisi DEĞİL (app.py _FORM_SOLVER_OWNED_FIELDS).
        assert 'id="tank_pressure"' not in _oku(LIQ)

    def test_sifirlama_ve_degisim_esitlemeyi_cagirir(self):
        html = _oku(LIQ)
        assert 'syncLiquidCycleFields()' in _fn(html, 'resetForm')
        assert "addEventListener('change', syncLiquidCycleFields)" in html

    @node_gerekli
    def test_gercek_sifirlama_dort_grubu_basinc_beslemeye_dondurur(self):
        """Denetçi Ş2 — DAVRANIŞ: gerçek resetForm + gerçek
        syncLiquidCycleFields (window üstünden, şablondaki atamayla).

        Önce form turbopompalı çevrimde (dört grup görünür); sıfırlama
        çevrimi programla 'pressure_fed' yazar ve 'change' yaymaz. Sıfırlama
        eşitlemeyi çağırmazsa gruplar görünür kalır — bu düğüm kırmızı olur
        (denetçi D2: ``if (false && typeof window.syncLiquidCycleFields``).
        """
        html = _oku(LIQ)
        atama = re.search(r'^[ \t]*window\.syncLiquidCycleFields\s*=\s*'
                          r'syncLiquidCycleFields;[ \t]*$', html, flags=re.M)
        assert atama, 'şablon eşitleyiciyi window üstüne yayımlamıyor'
        kod = '\n'.join([
            _blok(html, 'const LIQ_CYCLE_UNREAD_FIELDS'),
            _blok(html, 'const LIQ_CYCLE_FIELDS_WATCHED'),
            _fn(html, 'liqCycleUnreadFields'),
            _fn(html, 'syncLiquidCycleFields'),
            atama.group(0).strip(),
            # V3.0.5 T-ÇAPA-C1 (altyapı): V301/L-C (8ee59c845) sıfırlamaya
            # pintle alanlarını boşaltma + enjektör eşitlemesini ekledi.
            _blok(html, 'const LIQ_INJECTOR_LEGACY'),
            _fn(html, 'liqInjectorCanonical'),
            _blok(html, 'const LIQ_PINTLE_FIELDS'),
            _fn(html, 'syncLiquidInjectorFields'),
            _fn(html, 'resetForm'),
        ])
        betik = r"""
global.window = global;
const izlenen = %(izlenen)s;
function grup() {
  return { style: { display: '' }, _a: {},
    setAttribute(a, v) { this._a[a] = String(v); },
    removeAttribute(a) { delete this._a[a]; },
    getAttribute(a) { return (a in this._a) ? this._a[a] : null; } };
}
const ogeler = {};
function oge(id) {
  if (!(id in ogeler)) {
    const o = { id: id, value: '', _a: {}, textContent: '', style: {},
      setAttribute(a, v) { this._a[a] = String(v); },
      getAttribute(a) { return (a in this._a) ? this._a[a] : null; } };
    const g = izlenen.indexOf(id) !== -1 ? grup() : null;
    o.closest = () => g;
    ogeler[id] = o;
  }
  return ogeler[id];
}
global.document = { getElementById: oge, querySelectorAll() { return []; } };
function T(k, f) { return f; }
function updatePropellantPreview() {}
%(kod)s
function durum() {
  const o = { cevrim: oge('engine_cycle').value, gruplar: {},
    not_anahtari: oge('feed_pressure_cycle_note').getAttribute('data-i18n') };
  izlenen.forEach(id => { const g = oge(id).closest('.form-group');
    o.gruplar[id] = { display: g.style.display, im: g.getAttribute('data-cycle-hidden') }; });
  return o;
}
oge('engine_cycle').value = 'gas_generator';
syncLiquidCycleFields();
const once = durum();
resetForm();
process.stdout.write(JSON.stringify({ once: once, sonra: durum() }));
""" % {'izlenen': json.dumps(list(TURBIN_ALANLARI)), 'kod': kod}
        o = _node(betik)
        # Ön koşul (boş geçmesin): turbopompalı çevrimde dört grup görünür.
        assert o['once']['cevrim'] == 'gas_generator'
        for alan in TURBIN_ALANLARI:
            assert o['once']['gruplar'][alan] == {'display': '', 'im': None}, alan
        assert o['once']['not_anahtari'] == 'liq.ui.feed_pressure_note_turbopump'
        # Sıfırlama sonrası: basınç besleme, dört grup gizli ve imli, not döndü.
        assert o['sonra']['cevrim'] == 'pressure_fed'
        for alan in TURBIN_ALANLARI:
            assert o['sonra']['gruplar'][alan] == {'display': 'none',
                                                   'im': 'pressure_fed'}, alan
        assert o['sonra']['not_anahtari'] == 'liq.ui.feed_pressure_note_pressure_fed'


# ===========================================================================
# (b) CW-A4E6 — defaults_applied künyesi (sıvı + katı)
# ===========================================================================
SENTETIK_KUNYE = [
    {'field': 'fuel_density', 'value': 810, 'reason': 'endpoint_default'},
    {'field': 'max_burn_duration', 'value': 30, 'reason': 'tutorial_default'},
    {'field': 'cooling_type', 'value': 'regenerative', 'reason': 'not_supplied'},
    {'field': 'l_star', 'value': 0, 'reason': 'not_supplied_solver_derives'},
    {'field': 'weird_field', 'value': 5, 'reason': 'zz_unknown_reason_code'},
]


def _kunye_bloku_kos(sayfa: pathlib.Path, liste, lang='tr') -> dict:
    html = _oku(sayfa)
    yardimcilar = [_fn(html, 'escapeNoticeText'), _fn(html, 'ortakMetin'),
                   _fn(html, 'numTxt'), _fn(html, 'unitTxt'),
                   _fn(html, 'renderDefaultsAppliedBlock')]
    betik = _sozluk(lang) + r"""
const kap = { style: { display: 'none' }, _a: {}, innerHTML: '',
  setAttribute(a, v) { this._a[a] = String(v); }, removeAttribute(a) { delete this._a[a]; } };
document.getElementById = (id) => id === 'defaultsAppliedBlock' ? kap : null;
%s
renderDefaultsAppliedBlock({ defaults_applied: %s });
process.stdout.write(JSON.stringify({ html: kap.innerHTML, display: kap.style.display,
  sayi: kap._a['data-defaults-applied-count'] || null }));
""" % ('\n'.join(yardimcilar), json.dumps(liste))
    return _node(betik)


class TestDefaultsApplied:

    @node_gerekli
    @pytest.mark.parametrize('sayfa', [LIQ, SOLID], ids=['sivi', 'kati'])
    def test_sunucu_listesindeki_her_ad_ekranda_taninmayan_gerekce_ham_degil(self, sayfa):
        o = _kunye_bloku_kos(sayfa, SENTETIK_KUNYE)
        assert o['display'] == 'block'
        assert o['sayi'] == str(len(SENTETIK_KUNYE))
        for k in SENTETIK_KUNYE:
            assert 'data-defaults-applied-field="%s"' % k['field'] in o['html']
        # OH-D37-H2 X13 dersi: tanınmayan gerekçe kodu ekrana ham basılmaz.
        assert 'zz_unknown_reason_code' not in o['html']
        # TR ekranda başlık ve gerekçeler sözlükten.
        assert _sozluk_degeri('app.defaultsApplied.title', 'tr') in o['html']
        for anahtar in ('app.defaultsApplied.serverDefault',
                        'app.defaultsApplied.tutorialDefault',
                        'app.defaultsApplied.solverDerives',
                        'app.defaultsApplied.unknownReason'):
            assert _sozluk_degeri(anahtar, 'tr') in o['html'], anahtar
        # 'türet' işaretindeki 0 bir sayı DEĞİLDİR, basılmaz.
        assert 'l_star</code> = ' not in o['html']
        # Uygulanan sayı TR biçiminde (virgül yalnız ekranda).
        assert 'fuel_density</code> = <strong>810</strong>' in o['html']

    @node_gerekli
    @pytest.mark.parametrize('sayfa', [LIQ, SOLID], ids=['sivi', 'kati'])
    def test_liste_bossa_blok_yok(self, sayfa):
        for liste in ([], None):
            o = _kunye_bloku_kos(sayfa, liste)
            assert o['html'] == '' and o['display'] == 'none' and o['sayi'] is None

    @node_gerekli
    def test_gercek_sivi_uc_yaniti_ekranda(self, istemci):
        govde = _sivi_govde('gas_generator')
        govde.pop('max_burn_duration', None)
        govde.pop('cooling_type', None)
        govde['use_tutorial_defaults'] = True
        durum, yanit = _post(istemci, '/calculate_liquid', govde)
        assert durum == 200
        liste = yanit.get('defaults_applied') or []
        assert liste, 'uç künye yayımlamadı — ölçüm önermesi değişti'
        o = _kunye_bloku_kos(LIQ, liste)
        for k in liste:
            assert 'data-defaults-applied-field="%s"' % k['field'] in o['html']
        assert o['sayi'] == str(len(liste))

    @node_gerekli
    def test_gercek_kati_uc_yaniti_ekranda(self, istemci):
        govde = dict(json.loads(_oku(ORNEK_KATI))['inputs']['fields'])
        govde.pop('grain_type', None)
        durum, yanit = _post(istemci, '/calculate_solid', govde)
        assert durum == 200
        liste = yanit.get('defaults_applied') or []
        assert any(k.get('reason') == 'endpoint_default' for k in liste), liste
        o = _kunye_bloku_kos(SOLID, liste)
        for k in liste:
            assert 'data-defaults-applied-field="%s"' % k['field'] in o['html']

    def test_iki_sayfada_da_kablolu(self):
        sivi, kati = _oku(LIQ), _oku(SOLID)
        assert 'renderDefaultsAppliedBlock(results);' in _fn(sivi, 'displayLiquidWarnings')
        assert 'renderDefaultsAppliedBlock(results);' in _fn(kati, 'displayResults')
        for html in (sivi, kati):
            assert '<div id="defaultsAppliedBlock" class="panel" style="display: none;">' in html


# ===========================================================================
# (c) CW-U6 — yerli alert kutusu → sayfa-içi bildirim
# ===========================================================================
ALERT_RE = re.compile(r'(?<![\w.$])(?:window\.)?alert\s*\(')


def _bildirim_kos(sayfa: pathlib.Path, tur: str) -> dict:
    html = _oku(sayfa)
    betik = r"""
const zamanlayici = [];
global.setTimeout = (f, ms) => { zamanlayici.push(ms); return 1; };
function El(tag) {
  this.tag = tag; this.children = []; this._a = {}; this.style = {}; this.className = '';
  this._dinle = {}; this.parentNode = null; this.odaklandi = false;
}
El.prototype.setAttribute = function (a, v) { this._a[a] = String(v); };
El.prototype.getAttribute = function (a) { return (a in this._a) ? this._a[a] : null; };
El.prototype.appendChild = function (c) { c.parentNode = this; this.children.push(c); return c; };
El.prototype.remove = function () { if (this.parentNode) { const p = this.parentNode;
  p.children = p.children.filter(x => x !== this); this.parentNode = null; } };
El.prototype.addEventListener = function (t, f) { this._dinle[t] = f; };
El.prototype.focus = function () { this.odaklandi = true; global.document.activeElement = this; };
Object.defineProperty(El.prototype, 'innerHTML', { set(v) { this._html = v;
  this._kapat = new El('button'); }, get() { return this._html; } });
El.prototype.querySelector = function (s) { return s === 'button.close' ? this._kapat : null; };
const yigin = new El('div'); const govdeDom = new El('body');
const onceki = new El('button');
global.document = { body: govdeDom, activeElement: onceki,
  getElementById: (id) => id === 'toast-stack' ? yigin : null,
  createElement: (t) => new El(t), contains: () => true };
function T(k, f) { return f; }
function TF(k, p, f) { return f; }
%s
showMessage('Hata <b>x</b>', %s);
const kutu = yigin.children[0];
const sonuc = { rol: kutu.getAttribute('role'), odak: kutu.odaklandi, zamanlayici: zamanlayici.slice(),
  kapat_etiketi: /aria-label="Close"/.test(kutu._html) };
if (kutu._dinle.keydown) kutu._dinle.keydown({ key: 'Escape', preventDefault() {} });
sonuc.esc_sonrasi = yigin.children.length;
sonuc.odak_geri = onceki.odaklandi;
process.stdout.write(JSON.stringify(sonuc));
""" % ('\n'.join([_fn(html, 'escapeNoticeText'), _fn(html, 'ortakMetin'),
                  _fn(html, '_toastStack'), _fn(html, 'showMessage')]),
       json.dumps(tur))
    return _node(betik)


class TestBildirim:

    @pytest.mark.parametrize('sayfa', [LIQ, SOLID], ids=['sivi', 'kati'])
    def test_sablonda_yerli_alert_yok(self, sayfa):
        kod = _satir_ici_betikler(_oku(sayfa))
        assert not ALERT_RE.findall(kod)

    @node_gerekli
    @pytest.mark.parametrize('sayfa', [LIQ, SOLID], ids=['sivi', 'kati'])
    def test_hata_bildirimi_kalir_odaklanir_esc_ile_kapanir(self, sayfa):
        o = _bildirim_kos(sayfa, 'error')
        assert o['rol'] == 'alert'
        assert o['odak'] is True
        assert o['zamanlayici'] == [], 'hata bildirimi kendiliğinden siliniyor'
        assert o['kapat_etiketi'] is True
        assert o['esc_sonrasi'] == 0 and o['odak_geri'] is True

    @node_gerekli
    @pytest.mark.parametrize('sayfa', [LIQ, SOLID], ids=['sivi', 'kati'])
    def test_bilgi_bildirimi_bes_saniyede_gider(self, sayfa):
        o = _bildirim_kos(sayfa, 'info')
        assert o['rol'] == 'status' and o['odak'] is False
        assert o['zamanlayici'] == [5000]

    @pytest.mark.parametrize('sayfa', [LIQ, SOLID], ids=['sivi', 'kati'])
    def test_pdf_hatasi_sunucu_metnini_kacisli_basar(self, sayfa):
        pdf = _blok(_oku(sayfa), 'async function exportPDF(')
        assert pdf.count('showError(TF(') == 2
        assert 'escapeNoticeText(errorData.error)' in pdf
        assert 'escapeNoticeText(error.message)' in pdf

    @node_gerekli
    @pytest.mark.parametrize('dal', ['yanit', 'istisna'])
    @pytest.mark.parametrize('sayfa', [LIQ, SOLID], ids=['sivi', 'kati'])
    def test_pdf_hata_dali_davranisi_etiket_olusmaz(self, sayfa, dal):
        """Denetçi Ş3(i) — DAVRANIŞ: gerçek exportPDF hata dalı (sunucu
        ``{error: '<b>x</b>'}`` döner ya da istek istisna atar) → gerçek
        showError/showMessage. Bildirim HTML'i ayrıştırılır: ``<b>`` ETİKET
        olarak oluşmaz, kullanıcı metni harfiyen görür (denetçi D6)."""
        o = _pdf_hata_kos(sayfa, dal)
        assert o['adet'] == 1 and o['rol'] == 'alert'
        etiketler, metin = _ayristir(o['html'])
        assert 'b' not in etiketler, (etiketler, o['html'])
        assert set(etiketler) <= {'button', 'span'}, etiketler
        assert '&lt;b&gt;' in o['html']
        assert '<b>x</b>' in metin, metin

    @node_gerekli
    @pytest.mark.parametrize('sayfa', [LIQ, SOLID], ids=['sivi', 'kati'])
    def test_kunye_blogu_alan_ve_deger_etiket_uretmez(self, sayfa):
        """Denetçi Ş3(ii): sunucu listesindeki ``field``/``value`` metin
        olarak girer (``<img src=x>`` öğe olarak oluşmaz)."""
        o = _kunye_bloku_kos(sayfa, [
            {'field': '<img src=x>', 'value': 5, 'reason': 'endpoint_default'},
            {'field': 'ok_field', 'value': '<b>v</b>', 'reason': 'not_supplied'},
        ])
        etiketler, metin = _ayristir(o['html'])
        assert 'img' not in etiketler and 'b' not in etiketler, etiketler
        assert set(etiketler) <= {'div', 'code', 'strong'}, etiketler
        assert '<img src=x>' in metin and '<b>v</b>' in metin, metin


class _EtiketToplayici(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.etiketler, self.parcalar = [], []

    def handle_starttag(self, tag, attrs):
        self.etiketler.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.etiketler.append(tag)

    def handle_data(self, data):
        self.parcalar.append(data)


def _ayristir(parca: str):
    """innerHTML'i tarayıcı gibi ayrıştır: (başlangıç etiketleri, metin)."""
    t = _EtiketToplayici()
    t.feed(parca)
    t.close()
    return t.etiketler, ''.join(t.parcalar)


def _pdf_hata_kos(sayfa: pathlib.Path, dal: str) -> dict:
    """Gerçek exportPDF('summary') — ağ (fetch) ve DOM sahte, geri kalanı
    şablonun kendi gövdeleri; çeviri gerçek sözlükten (TR)."""
    html = _oku(sayfa)
    adlar = ['escapeNoticeText', 'ortakMetin', '_toastStack', 'showMessage',
             'showError', 'showSuccess', 'showWarning']
    if sayfa == LIQ:
        adlar += ['_pdfNum', '_liquidPdfMotorData', '_liquidPdfAnalysisResults',
                  '_liquidMotorName']
    kod = '\n'.join(_fn(html, a) for a in adlar) + '\n' + _blok(html, 'async function exportPDF(')
    betik = _sozluk('tr') + r"""
function El(tag) { this.tag = tag; this.children = []; this._a = {}; this.style = {};
  this._dinle = {}; this.parentNode = null; }
El.prototype.setAttribute = function (a, v) { this._a[a] = String(v); };
El.prototype.getAttribute = function (a) { return (a in this._a) ? this._a[a] : null; };
El.prototype.appendChild = function (c) { c.parentNode = this; this.children.push(c); return c; };
El.prototype.remove = function () {};
El.prototype.addEventListener = function (t, f) { this._dinle[t] = f; };
El.prototype.focus = function () {};
Object.defineProperty(El.prototype, 'innerHTML', { set(v) { this._html = v; }, get() { return this._html; } });
El.prototype.querySelector = function () { return new El('button'); };
const yigin = new El('div');
global.document = { body: new El('body'), activeElement: null,
  getElementById: (id) => id === 'toast-stack' ? yigin : null,
  createElement: (t) => new El(t), contains: () => true };
window.currentResults = { propellant_name: 'KNDX' };
const dal = %(dal)s;
global.fetch = async function () {
  if (dal === 'istisna') throw new Error('<b>x</b>');
  return { ok: false, json: async () => ({ error: '<b>x</b>' }) };
};
console.error = function () {};
%(kod)s
exportPDF('summary').then(function () {
  const kutu = yigin.children[0] || {};
  process.stdout.write(JSON.stringify({ adet: yigin.children.length,
    rol: kutu.getAttribute ? kutu.getAttribute('role') : null, html: kutu._html || '' }));
});
""" % {'dal': json.dumps(dal), 'kod': kod}
    return _node(betik)


# ===========================================================================
# (d) CW-SU3b — cidar kaynağı kodu ekranda çevrilir
# ===========================================================================
def _cidar_kos(ps: dict, lang='tr') -> str:
    html = _oku(SOLID)
    betik = _sozluk(lang) + '%s\nprocess.stdout.write(JSON.stringify({h: fmtTextField(%s, "wall_thickness_source", solidVesselWallSourceLabel)}));\n' % (
        '\n'.join([_fn(html, 'numTxt'), _fn(html, 'ortakMetin'),
                   _fn(html, 'escapeNoticeText'), _fn(html, 'missingReason'),
                   _fn(html, 'fmtTextField'), _fn(html, 'solidWallSourceText'),
                   _fn(html, 'solidVesselWallSourceLabel')]),
        json.dumps(ps))
    return _node(betik)['h']


class TestCidarKaynagi:

    @node_gerekli
    def test_sized_by_hrma_tr_ekranda_ham_basilmaz(self):
        h = _cidar_kos({'wall_thickness_source': 'sized_by_hrma',
                        'case_wall_hoop_required_mm': 1.62,
                        'case_wall_at_minimum_clamp': True,
                        'case_wall_manufacturing_floor_mm': 2.0})
        assert 'sized_by_hrma' not in h
        beklenen = _sozluk_degeri('solidgeo.wall_sized', 'tr').replace('{hoop}', '1,6')
        assert beklenen in h
        assert _sozluk_degeri('solidgeo.wall_floor', 'tr').replace('{floor}', '2,0') in h

    @node_gerekli
    def test_en_ekranda_da_kod_degil_cumle(self):
        h = _cidar_kos({'wall_thickness_source': 'user_supplied'}, lang='en')
        assert h == _sozluk_degeri('solidgeo.wall_user', 'en')

    @node_gerekli
    def test_bilinmeyen_kod_soru_isaretiyle(self):
        assert _cidar_kos({'wall_thickness_source': 'zz_new_code'}) == 'zz_new_code (?)'

    @node_gerekli
    def test_kod_yoksa_siniflandirilmadi(self):
        h = _cidar_kos({})
        assert 'hrma-na' in h

    def test_guvenlik_hucresi_ceviriciyle_kablolu(self):
        assert "fmtTextField(pressureSafety, 'wall_thickness_source', solidVesselWallSourceLabel)" in \
            _fn(_oku(SOLID), 'generateSafetyAnalysisHTML')

    @node_gerekli
    @pytest.mark.parametrize('lang', ['tr', 'en'])
    def test_tasarim_tablosu_eslemesiyle_ayni_metin(self, lang):
        """Kayma bekçisi: populateMotorDesignTable'ın satır içi case_geometry
        eşlemesi ile solidWallSourceText AYNI metni üretir (tablo satırı
        yardımcıya bağlanamadı — rapor Devirler)."""
        html = _oku(SOLID)
        tablo = _fn(html, 'populateMotorDesignTable')
        i = tablo.index('let kaynak;')
        j = tablo.index("rows.push([ortakMetin('solidgeo.wall_label'", i)
        satir_ici = 'function tabloKaynagi(cg) {\n' + tablo[i:j] + '\nreturn kaynak;\n}\n'
        vakalar = [
            {'thickness_source': 'sized_by_hrma', 'hoop_required_mm': 1.62,
             'raised_to_manufacturing_floor': True, 'manufacturing_floor_mm': 2.0},
            {'thickness_source': 'sized_by_hrma', 'hoop_required_mm': 3.4,
             'raised_to_manufacturing_floor': False},
            {'thickness_source': 'manufacturing_floor'},
            {'thickness_source': 'user_supplied', 'user_supplied': True},
        ]
        betik = _sozluk(lang) + '\n'.join([
            _fn(html, 'numTxt'), _fn(html, 'ortakMetin'), _fn(html, 'solidWallSourceText'),
            satir_ici]) + r"""
const vakalar = %s;
process.stdout.write(JSON.stringify(vakalar.map(cg => [tabloKaynagi(cg),
  solidWallSourceText(cg.thickness_source, { userSupplied: cg.user_supplied === true,
    hoopMm: cg.hoop_required_mm, raisedToFloor: cg.raised_to_manufacturing_floor === true,
    floorMm: cg.manufacturing_floor_mm })])));
""" % json.dumps(vakalar)
        for tablo_metni, yardimci_metni in _node(betik):
            assert tablo_metni == yardimci_metni


# ===========================================================================
# (e) DV-KATIMOTOR — katı PDF gövdesi motor tipini taşıyor
# ===========================================================================
class TestKatiPdfMotorTipi:

    @node_gerekli
    def test_pdf_govdesi_motor_type_solid(self):
        pdf = _blok(_oku(SOLID), 'async function exportPDF(')
        i = pdf.index('const _r = window.currentResults')
        j = pdf.index('Object.keys(_pdfAlanlar)')
        k = pdf.index('});', j) + 3
        betik = r"""
globalThis.window = { currentResults: { motor_geometry: { chamber_diameter: 0.085, chamber_length: 0.464 },
  propellant_name: 'KNDX', max_thrust: 1499.27 } };
globalThis.document = { getElementById: () => ({ value: 'bates' }) };
const motorName = 'X';
%s
process.stdout.write(JSON.stringify(motorData));
""" % pdf[i:k]
        md = _node(betik)
        assert md['motor_type'] == 'solid'

    def test_pdf_guvenligi_motor_tipini_sayfa_govdesinden_cozer(self, istemci):
        from hrma.export.pdf_safety import build_pdf_safety
        govde = json.loads(_oku(ORNEK_KATI))['inputs']['fields']
        durum, ar = _post(istemci, '/calculate_solid', govde)
        assert durum == 200
        geo = ar.get('motor_geometry') or {}
        md = {'motor_name': 'X', 'motor_type': 'solid',
              'propellant_type': ar.get('propellant_name') or ar.get('propellant_type'),
              'chamber_diameter': geo['chamber_diameter'] * 1000.0,
              'chamber_length': geo['chamber_length'] * 1000.0,
              'propellant_mass': ar.get('propellant_mass'),
              'chamber_pressure': ar.get('chamber_pressure')}
        with contextlib.redirect_stdout(io.StringIO()):
            ile, kunye = build_pdf_safety(md, ar)
            olmadan, kunye2 = build_pdf_safety(
                {k: v for k, v in md.items() if k != 'motor_type'}, ar)
        assert kunye['inputs_resolved'].get('motor_type') == 'md:motor_type'
        # ÖH D37 A1b panel-js 6. tur (14 Eki, devir 14) — dört koşulla
        # çevrildi (ana model): (1) eski beklenti 'explosive_class is not None'
        # şeker iticiye (KNDX) uygulanan KOMPOZİT yedeğinden türemişti
        # (a1/t6/once.json: composite, 1,0108 kg TNT, 1600 m); (2) kâhin
        # propellants_db: KNDX ailesi 'sugar' ∉ KNOWN_PROPELLANT_CLASSES ⇒
        # motor tipi çözülünce KARAR kazanılır ama bu karar sınıf değil, adlı
        # geri çekmedir; testin asıl amacı (tip sayfa gövdesinden çözülür,
        # gelmezse kimlik çözülmez) aynen kalır; (3) tolerans yok; (4) rapor
        # docs/scofield/raw/OH/A1b/panel-js/a1/rapor.md '6. tur'.
        assert ile['explosive_hazards']['explosive_class'] is None
        assert ile['explosive_hazards']['explosive_not_modelled']['code'] == (
            'solid_catalog_family_no_sourced_tnt')
        # Neden önemli: tip gelmezse patlayıcı kararı KAZANILMAZ (eksen geri çekilir).
        assert 'motor_type' in kunye2.get('unresolved_identity_fields', [])
        assert olmadan['explosive_hazards']['explosive_class'] is None
        assert not (olmadan['explosive_hazards'].get('explosive_not_modelled')
                    or {}).get('code')


# ===========================================================================
# (f) DV36-09 — katı 3B Plotly kesiti
# ===========================================================================
#: Denetçi Ş1 — üç gerçek katı gövde (a1/sonra/s7_yayim_olcumu.json ile aynı
#: üçlü). Tasarım noktası kipi AYIRT EDİCİDİR: kasa iç çapı (100 mm) grain dış
#: çapından (78,48 mm) farklıdır; ötekilerde yalıtım 0 olduğundan eşittir.
def _kati_govdeleri() -> dict:
    ks = json.loads(_oku(ORNEK_KATI))['inputs']['fields']
    tasarim = {k: v for k, v in ks.items()
               if k not in ('chamber_diameter', 'grain_length', 'core_diameter')}
    tasarim.update({'thrust': 1500, 'burn_time': 2.5})
    return {'ornek_KNDX_BATES': dict(ks),
            'ogretici_kip': {'use_tutorial_defaults': True},
            'tasarim_noktasi_kipi': tasarim}


KATI_GOVDE_ADLARI = tuple(_kati_govdeleri())


@pytest.fixture(scope='module')
def kati_cad(istemci):
    out = {}
    for ad, govde in _kati_govdeleri().items():
        durum, yanit = _post(istemci, '/calculate_solid', govde)
        assert durum == 200, ad
        out[ad] = yanit['cad_design']
    return out


def _kesit_kos(cad: dict, lang=None) -> dict:
    """Gerçek create3DMotorVisualization (+ üç iz kurucusu) → lüle halkaları.

    Her halkanın ilk tepe noktası açı 0'dadır (x = 0 + r·cos 0 = r): halka
    yarıçapı ve eksenel konumu doğrudan izden okunur."""
    html = _oku(SOLID)
    on = _sozluk(lang) if lang else 'function T(k, f) { return f; }\n'
    betik = on + '\n'.join([_fn(html, 'createCylinderTrace'),
                            _fn(html, 'createHollowCylinderTrace'),
                            _fn(html, 'createNozzleTrace'),
                            _fn(html, 'create3DMotorVisualization')]) + r"""
const r = create3DMotorVisualization({ cad_design: %s });
const ad = T('solid.msg.nozzle', 'Nozzle');
const lule = r.data.filter(t => t.name === ad)[0] || null;
const halkalar = [];
if (lule) {
  for (let q = 0; q < lule.z.length; q++) {
    if (!halkalar.length || halkalar[halkalar.length - 1].z !== lule.z[q]) {
      halkalar.push({ z: lule.z[q], r: lule.x[q], y: lule.y[q] });
    }
  }
}
const hepsi = lule ? lule.i.concat(lule.j, lule.k) : [];
process.stdout.write(JSON.stringify({ izler: r.data.map(t => t.name), halkalar: halkalar,
  n: lule ? lule.x.length : 0, yuz: lule ? lule.i.length : 0,
  maks: hepsi.length ? Math.max(...hepsi) : null,
  beyan: (r.layout.annotations || []).map(a => a.text) }));
""" % json.dumps(cad)
    return _node(betik)


class TestKati3BKesit:

    @node_gerekli
    def test_lule_izinin_yuz_dizinleri_gecerli(self):
        html = _oku(SOLID)
        betik = _fn(html, 'createNozzleTrace') + r"""
const t = createNozzleTrace(0, 0, 464, [{ z: 0, r: 37.5 }, { z: 49.16, r: 9.12 },
  { z: 103.9, r: 23.78 }], 'Nozul', '#2dd4a8', 0.9);
const n = t.x.length;
const hepsi = t.i.concat(t.j, t.k);
process.stdout.write(JSON.stringify({ n: n, maks: Math.max(...hepsi), min: Math.min(...hepsi),
  yuz: t.i.length, zmin: Math.min(...t.z), zmaks: Math.max(...t.z),
  dejenere: t.i.filter((a, q) => a === t.j[q] || a === t.k[q] || t.j[q] === t.k[q]).length }));
"""
        o = _node(betik)
        assert o['maks'] < o['n'] and o['min'] >= 0
        assert o['dejenere'] == 0
        # Üç istasyon × 20 nokta; iki bölüm × 20 dörtgen × 2 üçgen.
        assert o['n'] == 60 and o['yuz'] == 80
        assert o['zmin'] == 464.0 and o['zmaks'] == 464 + 103.9

    @node_gerekli
    def test_kadraj_eksen_basligi_payi_ve_oran(self):
        html = _oku(SOLID)
        betik = '\n'.join([_fn(html, 'createCylinderTrace'),
                           _fn(html, 'createHollowCylinderTrace'),
                           _fn(html, 'createNozzleTrace'),
                           _fn(html, 'create3DMotorVisualization')]) + r"""
function T(k, f) { return f; }
const r = create3DMotorVisualization({ cad_design: {
  case_design: { outer_diameter: 85, inner_diameter: 81, length: 464, grain_outer_diameter: 75 },
  grain_geometry: { outer_diameter: 75, core_diameter: 32, length: 360 },
  nozzle_design: { throat_diameter: 18.42, exit_diameter: 47.57, total_length: 103.9,
                   convergent_length: 49.16, divergent_length: 54.74 } } });
process.stdout.write(JSON.stringify({ L: r.layout, izler: r.data.length }));
"""
        o = _node(betik)
        sc = o['L']['scene']
        assert sc['aspectmode'] == 'data'
        assert sc['yaxis']['title'] == 'Y (mm)'
        assert sc['camera']['up'] == {'x': 0, 'y': 1, 'z': 0}
        # Bakış noktası aşağı kaydırılmış: alt kenardaki eksen başlığına pay.
        assert sc['camera']['center']['y'] < 0
        assert o['izler'] == 4
        assert 'annotations' not in o['L']

    # ---- Denetçi Ş1: lüle konturu YAYIMLANAN ölçülerle -------------------
    @node_gerekli
    @pytest.mark.parametrize('govde', KATI_GOVDE_ADLARI)
    def test_lule_konturu_yayimlanan_boy_ve_yaricaplarla(self, kati_cad, govde):
        cad = kati_cad[govde]
        cd, nd = cad['case_design'], cad['nozzle_design']
        z0, lc, ld = cd['length'], nd['convergent_length'], nd['divergent_length']
        o = _kesit_kos(cad)
        assert o['beyan'] == [], o['beyan']
        h = o['halkalar']
        assert len(h) == 3, h
        # Eksenel konum: yayımlanan mm boy DOĞRUDAN (birim/ölçek çevrimi yok);
        # istasyon koordinatı = kasa sonu + boy, bit-aynı.
        assert h[0]['z'] == z0
        assert h[1]['z'] == z0 + lc
        assert h[2]['z'] == z0 + (lc + ld)
        # Çizilen bölüm boyları = yayımlanan (tek toplama/çıkarma yuvarlaması).
        assert h[1]['z'] - h[0]['z'] == pytest.approx(lc, rel=1e-12)
        assert h[2]['z'] - h[1]['z'] == pytest.approx(ld, rel=1e-12)
        # Yarıçaplar: tek çevrim (çap / 2), bit-aynı.
        assert h[0]['r'] == cd['grain_outer_diameter'] / 2
        assert h[1]['r'] == nd['throat_diameter'] / 2
        assert h[2]['r'] == nd['exit_diameter'] / 2
        assert all(q['y'] == 0 for q in h)
        # Ölçüm önermesi: çizilen koni yarı açıları = yayımlanan açılar.
        # (Giriş için grain dış çapı seçiminin dayanağı; çözücü formülü
        # değişirse burası kırmızı olur ve alan yeniden ölçülür.)
        yak = math.degrees(math.atan((h[0]['r'] - h[1]['r']) / lc))
        ira = math.degrees(math.atan((h[2]['r'] - h[1]['r']) / ld))
        assert yak == pytest.approx(nd['convergent_angle'], abs=1e-9)
        assert ira == pytest.approx(nd['divergent_angle'], abs=1e-9)
        # Eski şema: boğazda düz bölüm (iki halka aynı yarıçap) YOK.
        assert h[0]['r'] > h[1]['r'] < h[2]['r']

    @node_gerekli
    def test_giris_capi_kasa_ic_capi_degil_cozucunun_kullandigi_grain_dis_capi(self, kati_cad):
        """Ayırt edici gövde: kasa iç çapı ≠ grain dış çapı. Çözücünün
        yakınsak boyu grain dış çapından hesaplanır; kasa iç çapıyla
        çizilseydi yarı açı yayımlanandan 8° sapardı."""
        cad = kati_cad['tasarim_noktasi_kipi']
        cd, nd = cad['case_design'], cad['nozzle_design']
        assert cd['inner_diameter'] - cd['grain_outer_diameter'] > 1.0, cd
        h = _kesit_kos(cad)['halkalar']
        assert h[0]['r'] == cd['grain_outer_diameter'] / 2
        assert h[0]['r'] != cd['inner_diameter'] / 2
        kasa_ile = math.degrees(math.atan(
            (cd['inner_diameter'] / 2 - nd['throat_diameter'] / 2) / nd['convergent_length']))
        assert abs(kasa_ile - nd['convergent_angle']) > 1.0

    @node_gerekli
    @pytest.mark.parametrize('blok,alan,deger,beklenen', [
        ('nozzle_design', 'convergent_length', None, 'yok'),
        ('nozzle_design', 'convergent_length', -48.97, 'yok'),
        ('nozzle_design', 'divergent_length', None, 'yakinsak'),
        ('nozzle_design', 'divergent_length', 0, 'yakinsak'),
        ('case_design', 'grain_outer_diameter', None, 'iraksak'),
    ])
    def test_olcu_yoksa_parca_cizilmez_ve_kesitte_beyan(self, kati_cad, blok, alan,
                                                         deger, beklenen):
        cad = copy.deepcopy(kati_cad['ornek_KNDX_BATES'])
        cd, nd = cad['case_design'], cad['nozzle_design']
        z0, lc, ld = cd['length'], nd['convergent_length'], nd['divergent_length']
        if deger is None:
            cad[blok].pop(alan)
        else:
            cad[blok][alan] = deger
        o = _kesit_kos(cad, lang='tr')
        h = o['halkalar']
        if beklenen == 'yok':
            # Boğazın eksenel yeri bilinmez: lüle izi HİÇ yok (gövde+tane var).
            assert _sozluk_degeri('solid.msg.nozzle', 'tr') not in o['izler']
            assert len(o['izler']) == 3 and h == []
        elif beklenen == 'yakinsak':
            assert [(q['z'], q['r']) for q in h] == [
                (z0, cd['grain_outer_diameter'] / 2), (z0 + lc, nd['throat_diameter'] / 2)]
        else:
            assert [(q['z'], q['r']) for q in h] == [
                (z0 + lc, nd['throat_diameter'] / 2),
                (z0 + (lc + ld), nd['exit_diameter'] / 2)]
        # Kesitte beyan: çeviri sözlükten (TR), eksik alan ADIYLA.
        assert len(o['beyan']) == 1, o['beyan']
        metin = o['beyan'][0]
        assert '%s.%s' % (blok, alan) in metin
        assert _sozluk_degeri('solid.msg.nozzle', 'tr') in metin
        assert _sozluk_degeri('solid.fea.acc_pct_missing', 'tr') in metin

    def test_kaynakta_kesir_deseni_ve_uydurma_giris_yok(self):
        """0,4 / 0,2 / 0,6 kesirleri ve 'giriş = çıkış yarıçapı' şeması
        kaynakta (yorumlar sökülerek) yok."""
        html = _oku(SOLID)
        for ad in ('createNozzleTrace', 'create3DMotorVisualization'):
            govde = _js_yorumsuz(_fn(html, ad))
            # Kesir aritmetikte (t < 0.4, 0.4 * L, / 0.4 …); ışık katsayısı
            # (specular: 0.4) aritmetik değildir, desen onu yakalamaz.
            assert not re.findall(r'[-+*/<>(=]\s*0?\.[246](?!\d)'
                                  r'|(?<![\d.])0?\.[246](?!\d)\s*[-+*/)<>]', govde), ad
            assert 'total_length;' not in govde.replace(' ', ''), ad
        viz = _js_yorumsuz(_fn(html, 'create3DMotorVisualization'))
        assert 'z:0,r:exitR' not in viz.replace(' ', '')


# ===========================================================================
# (g) OH-D37-S1 — .eng kaydında alan etiketi
# ===========================================================================
ENG_HATASI = {'openrocket': {'eng_error': {
    'error': 'missing_export_data',
    'missing_fields': ['burn_time', 'propellant_mass', 'zz_unlabelled']}}}


class TestEngAlanEtiketi:

    def _kos(self, lang='tr'):
        html = _oku(LIQ)
        kod = '\n'.join([
            _blok(html, 'const LIQUID_DEEP_WARNING_PATHS'),
            _fn(html, 'liquidDeepWarnings'),
            _blok(html, 'const LIQUID_ENG_FIELD_LABELS'),
            _fn(html, 'liquidEngFieldLabel'),
            _fn(html, 'liquidEngWarningLabelled'),
            _fn(html, '_liquidExportStatus'),
            _fn(html, 'liquidEngGateStatus'),
        ])
        betik = _sozluk(lang) + r"""
global.HRMAReject = undefined;
function numTxt(v) { return String(v); }
const el = { textContent: '', dataset: {}, style: {} };
document.getElementById = (id) => id === 'liquidExportStatus' ? el : null;
%s
const r = %s;
const w = liquidDeepWarnings(r).map(liquidEngWarningLabelled)
  .filter(x => x && x.code === 'panelwarn.liquid.eng_not_generated')[0];
const panel = window.I18N.tf(w.code, w.params, w.code);
liquidEngGateStatus(r);
process.stdout.write(JSON.stringify({ fields: w.params.fields, panel: panel, satir: el.textContent,
  ham: liquidDeepWarnings(r).filter(x => x && x.code === 'panelwarn.liquid.eng_not_generated')[0].params.fields }));
""" % (kod, json.dumps(ENG_HATASI))
        return _node(betik)

    @node_gerekli
    def test_tr_panelde_etiket_anahtar_bicimi(self):
        # V301/DİL-2 (yayın kapısı 7, Berke 26 Eki: TR ekranda ham anahtar
        # yok; DİL terim kararı 1: makine adı title/data-field'da). ÖNCE bu
        # iddia 'Etiket (anahtar)' biçimini kilitliyordu (OH-D37-S1); ekran
        # ölçümünde (dil-2/once.json liquid#warningsList) parantezdeki
        # anahtar ham anahtar sayılıyordu. Artık tanınan alan YALNIZ etiketle
        # basılır; makine adı uyarı kaydının ham `fields` parametresinde ve
        # durum satırının title'ında kalır.
        o = self._kos('tr')
        for k in ('burn_time', 'propellant_mass'):
            assert '(%s)' % k not in o['panel'], o['panel']
            assert k not in o['panel'], o['panel']
        for etk in (_sozluk_degeri('liq.js.burn_time', 'tr').rstrip(': '),
                    _sozluk_degeri('liq.js.propellant_mass', 'tr').rstrip(': ')):
            assert etk in o['panel'], (etk, o['panel'])
        onek = _sozluk_degeri('liq.js.eng_gate_unlabelled_field', 'tr').split('{field}')[0]
        assert onek + 'zz_unlabelled' in o['panel']
        # Makine metni (`fields`) Excel/sözleşme için ham kalır.
        assert o['ham'] == 'burn_time, propellant_mass, zz_unlabelled'

    @node_gerekli
    @pytest.mark.parametrize('lang', ['tr', 'en'])
    def test_panel_ve_durum_satiri_ayni_etiketleri_basar(self, lang):
        """Kayma bekçisi: liquidEngGateStatus'un yerel etiket kopyası ile
        ortak yardımcı AYNI metni üretir (rapor Devirler: bağlanamadı)."""
        o = self._kos(lang)
        assert o['fields'] in o['satir'], (o['fields'], o['satir'])

    def test_panel_kaydi_etiketli_yoldan_gecer(self):
        blok = _fn(_oku(LIQ), 'displayLiquidWarnings')
        assert 'liquidDeepWarnings(r).map(liquidEngWarningLabelled)' in blok


# ===========================================================================
# (h) OH-D37-S7 — viz adaptörlerinde uydurma performans yedeği yok
# ===========================================================================
def _adaptor(sayfa, ad, girdi):
    betik = _fn(_oku(sayfa), ad) + (
        '\nprocess.stdout.write(JSON.stringify(%s(%s)));\n' % (ad, json.dumps(girdi)))
    return _node(betik)


class TestVizYedekleri:

    @node_gerekli
    def test_sivi_alan_yoksa_null(self):
        o = _adaptor(LIQ, 'buildLiquidVizData', {})
        assert o['thrust'] is None and o['isp'] is None and o['chamber_pressure'] is None

    @node_gerekli
    def test_sivi_alan_varsa_bit_ayni(self):
        o = _adaptor(LIQ, 'buildLiquidVizData',
                     {'thrust': 24999.123, 'isp_vacuum': 311.51, 'chamber_pressure': 70.25})
        assert (o['thrust'], o['isp'], o['chamber_pressure']) == (24999.123, 311.51, 70.25)

    @node_gerekli
    def test_kati_alan_yoksa_null(self):
        o = _adaptor(SOLID, 'buildSolidVizData', {})
        for k in ('burn_time', 'thrust', 'isp', 'chamber_pressure', 'isp_reference'):
            assert o[k] is None, k

    @node_gerekli
    def test_kati_alan_varsa_bit_ayni_ve_oncelik_korunur(self):
        o = _adaptor(SOLID, 'buildSolidVizData',
                     {'burn_time': 2.2771, 'average_thrust': 1299.7, 'max_thrust': 1499.3,
                      'isp_sea_level': 125.4, 'chamber_pressure': 40.0})
        assert (o['burn_time'], o['thrust'], o['isp'], o['chamber_pressure']) == \
            (2.2771, 1299.7, 125.4, 40.0)
        assert o['isp_reference'] == 'sea_level'
        o2 = _adaptor(SOLID, 'buildSolidVizData', {'max_thrust': 1499.3})
        assert o2['thrust'] == 1499.3

    @pytest.mark.parametrize('sayfa,ad,desen', [
        (LIQ, 'buildLiquidVizData',
         r'num\(results\.(?:thrust|isp_vacuum|chamber_pressure),\s*-?\d'),
        (SOLID, 'buildSolidVizData',
         r'firstNum\((?:r\.(?:burn_time|average_thrust|specific_impulse|chamber_pressure))[^)]*,\s*-?\d+(?:\.\d+)?\s*\)'),
    ])
    def test_kaynakta_sayi_yedegi_yok(self, sayfa, ad, desen):
        govde = _js_yorumsuz(_fn(_oku(sayfa), ad))
        assert not re.findall(desen, govde)


# ===========================================================================
# A1b şart toplayıcı — sivi-kati-form şart denetimi (M1f / M3f)
#
# Şart denetçisinin kaçan iki ters mutasyonu (scratchpad sivi-kati-sart/
# mutasyon.py: M1f ``isFinite`` söküldü, M3f ``escapeNoticeText`` tırnak
# kaçışı söküldü — ikisi de YEŞİL kaldı) bu düğümlerle kırmızıya döner.
# Kanıt: docs/scofield/raw/OH/A1b/sart-toplayici/ (mutasyon.md).
# ===========================================================================
class TestSartSiviKati:

    @node_gerekli
    @pytest.mark.parametrize('deger', [float('nan'), float('inf'), float('-inf')],
                             ids=['NaN', 'Infinity', '-Infinity'])
    @pytest.mark.parametrize('blok,alan,beklenen', [
        ('nozzle_design', 'convergent_length', 'yok'),
        ('nozzle_design', 'divergent_length', 'yakinsak'),
        ('case_design', 'grain_outer_diameter', 'iraksak'),
    ])
    def test_m1f_sonlu_olmayan_olcu_cizilmez_ve_beyan(self, kati_cad, blok, alan,
                                                       beklenen, deger):
        """(M1f) ``luleOlcusu``na sonlu OLMAYAN ölçü (NaN / ±Infinity) → o
        parça ÇİZİLMEZ ve kesitte adıyla beyan edilir (eksik ölçüyle aynı
        yol). Sunucu yanıtı JSON olduğundan bu değerler bugün ``fetch``
        yolundan gelemez; ``isFinite`` bir SAVUNMA kapısıdır ve bekçi onu
        doğrudan ölçer (``json.dumps`` NaN/Infinity'yi JS sabiti olarak
        basar, gerçek ``create3DMotorVisualization`` onları alır).
        ``isFinite`` sökülürse (şart denetçisi M1f) +Infinity ``v > 0``'ı
        geçer ve sonsuz boylu/yarıçaplı halka çizilir."""
        cad = copy.deepcopy(kati_cad['ornek_KNDX_BATES'])
        cd, nd = cad['case_design'], cad['nozzle_design']
        z0, lc, ld = cd['length'], nd['convergent_length'], nd['divergent_length']
        cad[blok][alan] = deger
        o = _kesit_kos(cad, lang='tr')
        h = o['halkalar']
        if beklenen == 'yok':
            assert _sozluk_degeri('solid.msg.nozzle', 'tr') not in o['izler']
            assert len(o['izler']) == 3 and h == []
        elif beklenen == 'yakinsak':
            assert [(q['z'], q['r']) for q in h] == [
                (z0, cd['grain_outer_diameter'] / 2), (z0 + lc, nd['throat_diameter'] / 2)]
        else:
            assert [(q['z'], q['r']) for q in h] == [
                (z0 + lc, nd['throat_diameter'] / 2),
                (z0 + (lc + ld), nd['exit_diameter'] / 2)]
        # Çizilen her halka sonlu (JSON'da sonsuz → null olurdu)
        for q in h:
            assert isinstance(q['z'], (int, float)) and math.isfinite(q['z']), q
            assert isinstance(q['r'], (int, float)) and math.isfinite(q['r']), q
        assert len(o['beyan']) == 1, o['beyan']
        metin = o['beyan'][0]
        assert '%s.%s' % (blok, alan) in metin
        assert _sozluk_degeri('solid.fea.acc_pct_missing', 'tr') in metin

    @node_gerekli
    @pytest.mark.parametrize('sayfa', [LIQ, SOLID], ids=['sivi', 'kati'])
    def test_m3f_kunye_ozniteligi_tirnakla_kirilmaz(self, sayfa):
        """(M3f) Sunucu listesindeki alan adı çift tırnak taşısa da
        (``x" onmouseover="y``) künye satırının ``data-defaults-applied-field``
        özniteliği KIRILMAZ: ayrıştırılan öznitelik değeri alan adının
        KENDİSİ, satırda başka öznitelik (``onmouseover``) oluşmaz, metin
        harfiyen görünür. Tırnak kaçışı sökülürse (şart denetçisi M3f)
        öznitelik ``x``te biter ve olay özniteliği oluşur."""
        kotu = 'x" onmouseover="y'
        o = _kunye_bloku_kos(sayfa, [
            {'field': kotu, 'value': 5, 'reason': 'endpoint_default'},
            {'field': "q'z", 'value': 'a"b', 'reason': 'not_supplied'},
        ])
        t = _OznitelikToplayici()
        t.feed(o['html'])
        t.close()
        satirlar = [a for tag, a in t.ogeler
                    if tag == 'div' and 'data-defaults-applied-field' in a]
        assert [a['data-defaults-applied-field'] for a in satirlar] == [kotu, "q'z"], satirlar
        for a in satirlar:
            assert set(a) == {'class', 'data-defaults-applied-field', 'style'}, a
        assert not [a for _tag, a in t.ogeler
                    if any(k.startswith('on') for k in a)], t.ogeler
        metin = ''.join(t.parcalar)
        assert kotu in metin and 'a"b' in metin, metin


class _OznitelikToplayici(HTMLParser):
    """innerHTML'i tarayıcı gibi ayrıştır: (etiket, öznitelik sözlüğü)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ogeler, self.parcalar = [], []

    def handle_starttag(self, tag, attrs):
        self.ogeler.append((tag, dict(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.ogeler.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.parcalar.append(data)
