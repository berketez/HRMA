# -*- coding: utf-8 -*-
"""ÖH D37 · A1c · kulvar ``panel-dil`` (a1) bekçileri.

Kanıt paketi: ``docs/scofield/raw/OH/A1c/panel-dil/a1/`` (``once/`` taban
68c55a27, ``sonra/`` kulvar — aynı ``olcum.py`` bu dosyanın düzeneklerini içe
aktarır; yön kanıt → test, bu dosya ``docs/``a bağlı DEĞİLDİR; ``mutasyon.md``;
``rapor.md``).

Kalemler (kart A1c-1 + görev ekleri):

  K1  dil-sozluk Devir 1 — katalog (``materials_catalog.js`` populateSelect)
      seçenek adları sözlükten (``mat.*`` / ``tps.*``), seçenek DEĞERLERİ
      aynen, yeniden kurulumdan sonra ipucu (``title`` + ``data-i18n-title``)
      görünen seçenekle aynı.
  K2  dil-sozluk Devir 2 — ``safety_panel.js`` / ``structural_panel.js``
      İngilizce malzeme listeleri anahtarlı; değerler bit-aynı.
  K3  dil-sozluk Devir 3 — çağrı yeri İngilizce yedekleri sözlüğün EN
      metniyle BİREBİR (deste 'viz.btnFrame', 'viz.cfd.none'; CFD
      'panel.cfd.viz3dShown').
  K4  dil-sozluk Devir 5 — ``viz3dOkLines`` birimsiz yolda çift boşluk yok.
  K5  sunucu beyan cümleleri TR (i18n_charts.js; eşleşmeyen AYNEN):
      (a) DetailedCAD 'Parts not drawn: …' sıvı + katı, (b) CAD performans
      grafiği iki gerekçesi (süre / itki), (c) yanma süresi verilmedi
      gerekçeleri (güvenlik, sıvı motor, itki-irtifa), (d) A1b-3 panel-js
      OH-D37-G2 koşu noktası ipucu/not metinleri.
  EK  dil-cozucu-nesri denetçi Ş3 — bekçisiz dört desen: L* üst kelepçe
      notu, G-1 'This run O/F … OUTSIDE', 'Sweep maximum sits on the END',
      'Grid maximum was' (yalnız TR + virgül iddiası).

Cümleler ÜRETİCİDEN alınır (gerçek motor / çizici / uç); elle yazılmış
kopya yalnız iki yerde: fail-closed sınaması (tanınmayan parça) ve K5(d)
— G2 metinleri A1b-3 panel-js dalında (henüz main'de değil); onlar panel-js
raporundan BİREBİR alınmıştır ve ``TestG2Uretici`` (2. tur) panel-js
birleşince G2 metinlerini ÜRETİCİDEN alıp bu kopyalarla birebirliği sınar.
Beklenen TR cümleler (3. tur) bekçinin KENDİ tablolarıdır: ``G2_IPUCU_TR``,
``G2_NOT_SABLONLARI_TR``, ``K5_TR_TAM``, ``CAD_PARCA_TR``/``CAD_NEDEN_TR``.

Denetçi şartları 2. tur (28 Eyl):
  Ş1  ``test_g2_ipucu_ve_not_TR`` künye kodu (makine) her künyeli notta —
      verilen-ε notu 'supplied_expansion_ratio_equilibrium' dahil — sunucu
      çıktısında ve grafik notunda '(çıkış künyesi <kod>)' kalıbında AYNEN.
  Ş2  ``test_cad_beyani_tam_cumle``: CAD beyanı TR cümlesi üreticinin
      demetlerinden bekçinin kendi TR tablosuyla kurulan cümleye BİREBİR.
  Ş4  panel-js 4bbbd32f G2 metinleri (2. turdaki 'p_e not published' dahil);
      ``TestG2Uretici`` panel-js main'e girince metinleri ÜRETİCİDEN alır
      (o zamana dek adıyla atlanır).

Denetçi şartları 3. tur (29 Eyl) — kara liste yerine TAM CÜMLE:
  Ş1  G2'nin üç not hâli bekçinin kendi TR şablon tablosuyla
      (``G2_NOT_SABLONLARI_TR``, künye doldurulur) ``test_g2_ipucu_ve_not_TR``
      ve ``TestG2Uretici``'de BİREBİR (denetçi E3, E3b, E10).
  Ş2  K5 (b)/(c) cümleleri (perf_suresiz, perf_itkisiz, sivi_sure,
      itki_irtifa, guvenlik_sure) bekçinin ``K5_TR_TAM`` tablosuyla, K5 (a)
      ``cad_beklenen_tr`` ile ``test_TR_cevrildi_EN_aynen``'de BİREBİR (E15).
  Ş3  ``TestG2Uretici`` atlaması fail-closed: kaynakta (``hrma/**/*.py``)
      G2 izlerinin (``G2_URETICI_IZLERI``) hiçbiri ve figürde hiçbir iz yoksa
      adıyla atlanır; iz varsa ve figürde koşu noktası yoksa KIRMIZI (E17).
"""
import contextlib
import io
import json
import re
import shutil
import tempfile
from pathlib import Path

import pytest

from tests.test_d37_dil_a1 import (SECICI_KARAKTER_BUTCESI, DOCK_DUZENEK,
                                   I18N_ZINCIRI,
                                   DILDEN_BAGIMSIZ as A1A_DILDEN_BAGIMSIZ)
from tests.test_d37_dil_b1 import ceviri, node_calistir

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node kurulu değil')
UC_BASLIGI = {'Host': '127.0.0.1:8080'}


def _oku(yol):
    return Path(yol).read_text(encoding='utf-8')


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


# ===========================================================================
# Ortak ölçütler
# ===========================================================================
#: Dile bağlı OLMAYAN adlar: A1a dil-sozluk kümesi + katalogdaki aynı sınıf
#: (alaşım kodu / özel ad; iki dilde aynı yazılır). Listeye SÖZCÜK girmez.
DILDEN_BAGIMSIZ = frozenset(A1A_DILDEN_BAGIMSIZ)

#: TR ekranda kalmaması gereken İngilizce malzeme sözcükleri. A1a
#: dil-sozluk düzenli ifadesinin kapsamı + katalog adlarında ölçülen
#: sözcükler (``once/olcum.json`` katalog adları: 'low-alloy', 'annealed',
#: 'aged', 'normalized', 'isostatic', 'wrought', 'free-cutting'…).
INGILIZCE_MALZEME_SOZCUGU = re.compile(
    r'\b(steel|stainless|aluminum|aluminium|copper|titanium|magnesium|graphite|'
    r'beryllium|rubber|insulation|coated|class|liner|generic|wall|extension|'
    r'sizing|transient|natural|forced|regenerative|carbon|ablative|brass|'
    r'molybdenum|tungsten|niobium|alloy|low-alloy|annealed|aged|normalized|'
    r'isostatic|wrought|stress-relieved|free-cutting|grade|insert)\b', re.I)


def ingilizce_mi(metin):
    """TR ekranda İngilizce kalmış malzeme adı mı?"""
    if metin in DILDEN_BAGIMSIZ:
        return False
    # Alaşım kodu kalıbı 'CP Grade 2' A1a'dan beri TR'de de 'CP Grade 2'
    # yazılıyor (mat.titaniumGrade2 TR 'Titanyum CP Grade 2'); ad Türkçe,
    # kod aynen — sözcük sayılmaz.
    return bool(INGILIZCE_MALZEME_SOZCUGU.search(metin.replace('CP Grade', '')))


def katalog_yaniti():
    """GERÇEK ``/api/materials`` yanıtı (Flask test istemcisi)."""
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    r = app.test_client().get('/api/materials', headers=UC_BASLIGI)
    assert r.status_code == 200, r.status_code
    return r.get_json()


# ===========================================================================
# K1 — katalog seçicileri (materials_catalog.js populateSelect)
# ===========================================================================
#: populateSelect çağıran paneller (dosya, dizi adı). Çağrı parametreleri
#: (panelId/fieldId/tags/merge) panel dosyasındaki çağrıdan OKUNUR — bu
#: tablo yalnız hangi dosyaya bakılacağını söyler.
KATALOG_CAGRILARI = (
    'panels/thermal_panel.js', 'panels/protection_panel.js',
    'panels/safety_panel.js', 'panels/structural_panel.js',
    'panels/joint_panel.js', 'panels/vessel_panel.js',
    'panels/feed_panel.js', 'panels/cooling_panel.js',
)

_SATIR_RE = re.compile(
    r"\[\s*'([^']*)'\s*,\s*'([^']*)'\s*(?:,\s*'([^']*)')?\s*\]")


def panel_dizisi(kaynak, ad):
    m = re.search(r'(?:var|const)\s+' + ad + r'\s*=\s*\[(.*?)\n\s*\];', kaynak, re.S)
    assert m, ad
    return [[a, b] + ([c] if c else []) for a, b, c in _SATIR_RE.findall(m.group(1))]


def katalog_cagrilari(kok=ROOT):
    """Panel dosyalarındaki populateSelect çağrıları + yedek dizileri."""
    out = []
    for dosya in KATALOG_CAGRILARI:
        src = _oku(Path(kok) / 'hrma' / 'static' / 'js' / dosya)
        for m in re.finditer(r'populateSelect\(\{(.*?)\}\)', src, re.S):
            g = m.group(1)
            pid = re.search(r"panelId:\s*'(\w+)'", g)
            fid = re.search(r"fieldId:\s*'(\w+)'", g)
            tags = re.findall(r"'(\w+)'", re.search(r'tags:\s*\[([^\]]*)\]', g).group(1))
            yedek = re.search(r'fallback:\s*(\w+)', g).group(1)
            out.append({
                'dosya': dosya,
                'panelId': pid.group(1) if pid else None,
                'fieldId': fid.group(1) if fid else None,
                'selectId': None if pid else 'secici_' + yedek.lower(),
                'tags': tags,
                'merge': bool(re.search(r'merge:\s*true', g)),
                'yedek_adi': yedek,
                'fallback': panel_dizisi(src, yedek),
            })
    return out


KATALOG_JS = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const ROOT = process.argv[2]; const JOB = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
function unesc(s) { return String(s).replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&'); }
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function secici(id) {
    const el = { id: id, tagName: 'SELECT', attrs: {}, options: [], selectedIndex: -1,
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return (k in this.attrs) ? this.attrs[k] : null; },
        removeAttribute(k) { delete this.attrs[k]; } };
    // innerHTML ayrıştırıcısı: tarayıcının <option> kuralı (yeni içerik
    // ilk seçeneği seçer; olmayan değere value atamak seçimi düşürür).
    Object.defineProperty(el, 'innerHTML', { set(html) {
        const re = /<option\b([^>]*)>([\s\S]*?)<\/option>/g; let m; const ops = [];
        while ((m = re.exec(html))) {
            const at = {};
            m[1].replace(/([\w-]+)="([^"]*)"/g, function (w, k, v) { at[k] = unesc(v); return w; });
            ops.push({ value: at.value || '', textContent: unesc(m[2]), attrs: at,
                getAttribute(k) { return (k in this.attrs) ? this.attrs[k] : null; } });
        }
        this.options = ops; this.selectedIndex = ops.length ? 0 : -1; } });
    Object.defineProperty(el, 'value', {
        get() { const o = this.options[this.selectedIndex]; return o ? o.value : ''; },
        set(v) { this.selectedIndex = this.options.findIndex(function (o) { return o.value === String(v); }); } });
    return el;
}
async function kos(lang) {
    const secililer = {};
    const sb = { console: { warn() {}, log() {}, error() {} }, setTimeout, clearTimeout, setInterval,
        clearInterval, JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error, Promise,
        parseFloat, parseInt, isNaN, isFinite };
    sb.window = sb; sb.self = sb; sb.localStorage = null;
    sb.document = { readyState: 'loading', documentElement: { setAttribute() {} }, addEventListener() {},
        querySelectorAll: () => [], querySelector: () => null,
        getElementById: function (id) { return secililer[id] || null; } };
    sb.fetch = function () { return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve(JOB.katalog); } }); };
    vm.createContext(sb);
    for (const f of ['i18n.js', 'i18n_common.js']) {
        vm.runInContext(fs.readFileSync(ROOT + '/hrma/static/js/' + f, 'utf8'), sb, { filename: f }); }
    sb.I18N.setLang(lang);
    vm.runInContext(fs.readFileSync(ROOT + '/hrma/static/js/materials_catalog.js', 'utf8'), sb,
                    { filename: 'materials_catalog.js' });
    const out = [];
    for (const c of JOB.cagrilar) {
        const domId = c.selectId || ('ad_f_' + c.panelId + '_' + c.fieldId);
        const el = secici(domId); secililer[domId] = el;
        // Güvertenin kurulumu (fieldHtml): yedek dizisi, anahtarlı seçenek
        // sözlükten; ilk değer seçili (kurulum ipucu o seçenekte).
        el.innerHTML = c.fallback.map(function (o) {
            return '<option value="' + esc(o[0]) + '"' + (o[2] ? ' data-i18n="' + o[2] + '"' : '') + '>'
                + esc(o[2] ? sb.I18N.t(o[2], o[1]) : o[1]) + '</option>'; }).join('');
        const ilk = c.secili || (c.fallback[0] && c.fallback[0][0]);
        el.value = ilk;
        const o0 = el.options[el.selectedIndex];
        el.setAttribute('title', o0 ? o0.textContent : '');
        if (o0 && o0.getAttribute('data-i18n')) el.setAttribute('data-i18n-title', o0.getAttribute('data-i18n'));
        const yedek = c.fallback.map(function (o) { return o.slice(); });
        const dolduruldu = await sb.HRMAMaterials.populateSelect({ panelId: c.panelId, fieldId: c.fieldId,
            selectId: c.selectId || undefined, tags: c.tags, fallback: yedek, merge: c.merge || undefined });
        const s = el.options[el.selectedIndex];
        out.push({ select: domId, dolduruldu: dolduruldu,
            secenekler: el.options.map(function (o) { return { deger: o.value, metin: o.textContent,
                data_i18n: o.getAttribute('data-i18n') }; }),
            secili: s ? s.value : null, secili_metin: s ? s.textContent : null,
            secili_anahtar: s ? s.getAttribute('data-i18n') : null,
            title: el.getAttribute('title'), data_i18n_title: el.getAttribute('data-i18n-title'),
            yedek_sonra: yedek });
    }
    return out;
}
(async function () {
    const out = { en: await kos('en'), tr: await kos('tr') };
    process.stdout.write(JSON.stringify(out));
})().catch(function (e) { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""


def katalog_olc(kok=ROOT, tmpdir=None, katalog=None, cagrilar=None):
    """Katalog seçicilerinin iki dilde görünen hâli (gerçek dosyalar + gerçek
    /api/materials yanıtı, en küçük <select> taklidi)."""
    tmp = tmpdir or tempfile.mkdtemp(prefix='paneldil_k1_')
    return node_calistir(kok, KATALOG_JS, {
        'katalog': katalog if katalog is not None else katalog_yaniti(),
        'cagrilar': cagrilar if cagrilar is not None else katalog_cagrilari(kok),
    }, tmp, 'katalog')


def katalog_ozeti(olcum):
    """Seçici başına sayım (rapor + bekçi aynı ölçütü kullanır)."""
    ozet = {}
    for dil in ('en', 'tr'):
        for s in olcum[dil]:
            ops = s['secenekler']
            ozet.setdefault(s['select'], {})[dil] = {
                'secenek': len(ops),
                'ingilizce_TR': (sum(1 for o in ops if ingilizce_mi(o['metin']))
                                 if dil == 'tr' else None),
                'butce_ustu': sum(1 for o in ops if len(o['metin']) > SECICI_KARAKTER_BUTCESI),
                'anahtarsiz': sum(1 for o in ops if not o['data_i18n']),
                'title_esit_gorunen': s['title'] == s['secili_metin'],
                'ipucu_anahtari_esit': s['data_i18n_title'] == s['secili_anahtar'],
                'secili': s['secili'], 'secili_metin': s['secili_metin'],
            }
    return ozet


@pytest.fixture(scope='module')
def katalog():
    return katalog_yaniti()


@pytest.fixture(scope='module')
def k1(katalog, tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    r = katalog_olc(ROOT, tmp_path_factory.mktemp('k1'), katalog)
    assert 'error' not in r, r
    return r


class TestK1KatalogSecicileri:
    def test_cagrilar_okundu(self):
        c = katalog_cagrilari()
        # termal 1 + koruma 3 + güvenlik + yapısal + bağlantı + kap + besleme + soğutma
        assert len(c) == 10, [(x['dosya'], x['fieldId']) for x in c]

    def test_her_katalog_kaydinin_kisa_adi_var(self, k1, katalog):
        """Tanınmayan yeni kayıt veritabanı adına düşer (uydurma çeviri yok) —
        bugünkü kayıtların HİÇBİRİ o yola (anahtarsız veritabanı adı) düşmemeli."""
        adlar = {v.get('name') for v in katalog['materials'].values()}
        dusen = sorted({(d, s['select'], o['deger'], o['metin']) for d in ('en', 'tr')
                        for s in k1[d] for o in s['secenekler']
                        if not o['data_i18n'] and o['metin'] in adlar
                        and o['metin'] not in DILDEN_BAGIMSIZ})
        assert not dusen, 'veritabanı adıyla basılan seçenek: %s' % dusen

    def test_TR_ingilizce_secenek_yok(self, k1):
        kalan = [(s['select'], o['deger'], o['metin']) for s in k1['tr']
                 for o in s['secenekler'] if ingilizce_mi(o['metin'])]
        assert not kalan, 'TR ekranda İngilizce seçenek: %s' % kalan

    def test_anahtarli_secenek_TR_de_cevrilmis(self, k1):
        en = {(s['select'], o['deger']): o['metin'] for s in k1['en'] for o in s['secenekler']}
        ayni = [(s['select'], o['deger'], o['metin']) for s in k1['tr'] for o in s['secenekler']
                if o['data_i18n'] and o['metin'] == en[(s['select'], o['deger'])]
                and o['metin'] not in DILDEN_BAGIMSIZ]
        assert not ayni, ayni

    def test_anahtarsiz_secenek_yalniz_dilden_bagimsiz_ad(self, k1):
        kalan = sorted({o['metin'] for d in ('en', 'tr') for s in k1[d]
                        for o in s['secenekler']
                        if not o['data_i18n'] and o['metin'] not in DILDEN_BAGIMSIZ})
        assert not kalan, kalan

    def test_her_secenek_butceye_sigiyor(self, k1):
        tasan = [(d, s['select'], o['metin'], len(o['metin'])) for d in ('en', 'tr')
                 for s in k1[d] for o in s['secenekler']
                 if len(o['metin']) > SECICI_KARAKTER_BUTCESI]
        assert not tasan, tasan

    def test_ipucu_yeniden_kurulumdan_sonra_gorunen(self, k1):
        """Kurulum ipucu yedek dizisinin seçeneğindeydi; katalog seçenekleri
        yeniden kurunca ipucu YERİNDE (üzerine gelmeden) görünen metin."""
        for d in ('en', 'tr'):
            for s in k1[d]:
                assert s['dolduruldu'] is True, s['select']
                assert s['title'] == s['secili_metin'], (d, s['select'], s['title'], s['secili_metin'])
                assert s['data_i18n_title'] == s['secili_anahtar'], (d, s['select'])

    def test_secenek_degerleri_katalog_sozlesmesi(self, k1, katalog):
        """Değerler (uca giden) katalog + etiket filtresi + panel takma adı
        sözleşmesiyle aynı: onarım yalnız görünen metni değiştirir."""
        mats = katalog['materials']
        alias = katalog.get('aliases') or {}
        cagrilar = {(c['selectId'] or 'ad_f_%s_%s' % (c['panelId'], c['fieldId'])): c
                    for c in katalog_cagrilari()}
        for s in k1['en']:
            c = cagrilar[s['select']]
            beklenen = {k for k, m in mats.items() if set(m.get('tags') or []) & set(c['tags'])}
            degerler = [o['deger'] for o in s['secenekler']]
            assert len(degerler) == len(set(degerler)), s['select']
            if c['merge']:
                cozum = {v: (v if v in mats else alias.get(v)) for v in degerler}
                assert beklenen <= {cozum[v] for v in degerler if cozum[v]}, s['select']
                assert {r[0] for r in c['fallback']} <= set(degerler), s['select']
            else:
                assert set(degerler) == beklenen, s['select']
        assert [o['deger'] for s in k1['en'] for o in s['secenekler']] == \
               [o['deger'] for s in k1['tr'] for o in s['secenekler']]

    def test_panelin_kendi_etiketi_korunur(self, k1, katalog):
        """Panelin anahtarlı satırı (aynı değer) ve takma ad değeri (ör. koruma
        'silica_phenolic', termal 'aluminum' / 'inconel') katalog yeniden
        kurulumunda panelin KENDİ etiketiyle görünür — katalog kimliğinin
        genel adı değer anlamını değiştirmez ve katalogsuz sayfayla aynıdır."""
        cagrilar = {(c['selectId'] or 'ad_f_%s_%s' % (c['panelId'], c['fieldId'])): c
                    for c in katalog_cagrilari()}
        anahtarli = takma = 0
        for s in k1['en']:
            panel = {r[0]: r for r in cagrilar[s['select']]['fallback']}
            for o in s['secenekler']:
                r = panel.get(o['deger'])
                if r and len(r) > 2:
                    assert (o['data_i18n'], o['metin']) == (r[2], r[1]), (s['select'], o, r)
                    anahtarli += 1
                elif r and o['deger'] not in katalog['materials']:
                    assert o['metin'] == r[1], (s['select'], o, r)
                    takma += 1
        assert anahtarli >= 30 and takma >= 1, (anahtarli, takma)

    def test_EN_etiket_sozluk_metniyle_ayni(self, k1, tmp_path):
        """Anahtarlı seçeneğin EN metni sözlüğün EN metni (yedek kaymadı)."""
        anahtarlar = sorted({o['data_i18n'] for s in k1['en'] for o in s['secenekler'] if o['data_i18n']})
        r = ceviri_anahtar(anahtarlar, tmp_path)
        for s in k1['en']:
            for o in s['secenekler']:
                if o['data_i18n']:
                    assert r['en'][o['data_i18n']] == o['metin'], (s['select'], o)
        for s in k1['en']:
            for row in s['yedek_sonra']:
                if len(row) > 2:
                    assert r['en'].get(row[2], row[1]) == row[1], (s['select'], row)


ANAHTAR_JS = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const ROOT = process.argv[2]; const JOB = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const sb = { console: { warn() {}, log() {}, error() {} }, setTimeout, clearTimeout, setInterval, clearInterval,
    JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error, parseFloat, parseInt, isNaN, isFinite };
sb.window = sb; sb.self = sb; sb.localStorage = null;
sb.document = { readyState: 'loading', documentElement: { setAttribute() {} }, addEventListener() {},
    querySelectorAll: () => [], querySelector: () => null, getElementById: () => null };
vm.createContext(sb);
for (const f of ['i18n.js', 'i18n_common.js']) {
    vm.runInContext(fs.readFileSync(ROOT + '/hrma/static/js/' + f, 'utf8'), sb, { filename: f }); }
const out = {};
for (const lang of ['en', 'tr']) {
    sb.I18N.setLang(lang); out[lang] = {};
    for (const k of JOB.anahtarlar) out[lang][k] = sb.I18N.has(k) ? sb.I18N.t(k, null) : null;
}
process.stdout.write(JSON.stringify(out));
"""


def ceviri_anahtar(anahtarlar, tmpdir=None):
    tmp = tmpdir or tempfile.mkdtemp(prefix='paneldil_k_')
    r = node_calistir(ROOT, ANAHTAR_JS, {'anahtarlar': list(anahtarlar)}, tmp, 'anahtar')
    assert 'error' not in r, r
    return r


# ===========================================================================
# K2 — safety / structural malzeme listeleri
# ===========================================================================
K2_DIZILERI = (('panels/safety_panel.js', 'MATERIALS'),
               ('panels/structural_panel.js', 'MATERIALS'))

#: Seçenek DEĞERLERİ (uca giden kanonik anahtarlar) — taban 68c55a27'de
#: ölçüldü (``once/olcum.json`` K2). Onarım yalnız 2./3. öğeyi değiştirir.
K2_DEGERLER = (
    'steel_4130', 'steel_4340', 'steel', 'ss_304', 'ss_316', 'ss_17_4ph',
    'aluminum_6061', 'al_7075_t6', 'al_2024_t3', 'titanium_6al4v',
    'ti_grade2_cp', 'inconel_718', 'inconel_625', 'cucrzr',
    'beryllium_copper_c17200', 'magnesium_az31b',
)


def k2_olc(kok=ROOT, tmpdir=None):
    diziler = {'%s:%s' % (d, a): panel_dizisi(_oku(Path(kok) / 'hrma' / 'static' / 'js' / d), a)
               for d, a in K2_DIZILERI}
    anahtarlar = sorted({r[2] for v in diziler.values() for r in v if len(r) > 2})
    s = ceviri_anahtar(anahtarlar, tmpdir) if anahtarlar else {'en': {}, 'tr': {}}
    out = {}
    for ad, satirlar in diziler.items():
        out[ad] = []
        for r in satirlar:
            k = r[2] if len(r) > 2 else None
            out[ad].append({'deger': r[0], 'yedek': r[1], 'anahtar': k,
                            'en': s['en'].get(k) if k else r[1],
                            'tr': s['tr'].get(k) if k else r[1]})
    return out


@pytest.fixture(scope='module')
def k2(tmp_path_factory):
    if NODE is None:
        pytest.skip('node kurulu değil')
    return k2_olc(ROOT, tmp_path_factory.mktemp('k2'))


class TestK2GuvenlikYapisalListeleri:
    def test_degerler_bit_ayni(self, k2):
        for ad, satirlar in k2.items():
            assert tuple(r['deger'] for r in satirlar) == K2_DEGERLER, ad

    def test_iki_liste_birebir(self, k2):
        a, b = k2.values()
        assert a == b

    def test_TR_ingilizce_yok_ve_anahtarlar_sozlukte(self, k2):
        for ad, satirlar in k2.items():
            for r in satirlar:
                if r['anahtar']:
                    assert r['tr'] and r['en'], (ad, r)
                    if r['tr'] not in DILDEN_BAGIMSIZ:
                        assert r['tr'] != r['en'], (ad, r)
                else:
                    assert r['yedek'] in DILDEN_BAGIMSIZ, (ad, r)
                assert not ingilizce_mi(r['tr']), (ad, r)

    def test_EN_yedek_sozluk_metniyle_ayni(self, k2):
        for ad, satirlar in k2.items():
            for r in satirlar:
                assert r['en'] == r['yedek'], (ad, r)

    def test_butce(self, k2):
        for ad, satirlar in k2.items():
            for r in satirlar:
                for d in ('en', 'tr'):
                    assert len(r[d]) <= SECICI_KARAKTER_BUTCESI, (ad, d, r)


# ===========================================================================
# K3 — çağrı yeri yedekleri sözlük EN metniyle birebir
# ===========================================================================
#: (dosya, çağrı adı, anahtar, beklenen çağrı sayısı)
K3_CAGRILARI = (
    ('motor_viz_deck.js', 'T', 'viz.btnFrame', 2),
    ('motor_viz_deck.js', 'T', 'viz.cfd.none', 1),
    ('panels/cfd_panel.js', 'TF', 'panel.cfd.viz3dShown', 1),
    ('panels/cfd_panel.js', 'TF', 'panel.cfd.viz3dShownNoUnit', 1),
)

YEDEK_JS = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const ROOT = process.argv[2]; const JOB = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
// Çağrının SON argümanı (yedek metin) — dizge ve parantez/ayraç duyarlı
// ayrıştırma; ifade (dizge birleştirmesi) node'da DEĞERLENDİRİLİR.
function argumanlar(src, i) {
    const args = []; let d = 0, bas = i, q = null;
    for (let k = i; k < src.length; k++) {
        const c = src[k];
        if (q) { if (c === '\\') { k++; continue; } if (c === q) q = null; continue; }
        if (c === "'" || c === '"' || c === '`') { q = c; continue; }
        if (c === '/' && src[k + 1] === '/') { k = src.indexOf('\n', k); continue; }
        if (c === '(' || c === '[' || c === '{') { d++; continue; }
        if (c === ')' || c === ']' || c === '}') {
            if (d === 0) { args.push(src.slice(bas, k).trim()); return args; } d--; continue; }
        if (c === ',' && d === 0) { args.push(src.slice(bas, k).trim()); bas = k + 1; }
    }
    throw new Error('kapanmayan çağrı');
}
const out = [];
for (const c of JOB.cagrilar) {
    const src = fs.readFileSync(ROOT + '/hrma/static/js/' + c[0], 'utf8');
    const imza = new RegExp('\\b' + c[1] + "\\(\\s*'" + c[2].replace(/\./g, '\\.') + "'\\s*,", 'g');
    let m; const bulunan = [];
    while ((m = imza.exec(src))) {
        const args = argumanlar(src, m.index + m[0].length);
        bulunan.push(vm.runInNewContext('(' + args[args.length - 1] + ')', {}));
    }
    out.push({ dosya: c[0], anahtar: c[2], yedekler: bulunan });
}
process.stdout.write(JSON.stringify(out));
"""


def k3_olc(kok=ROOT, tmpdir=None):
    tmp = tmpdir or tempfile.mkdtemp(prefix='paneldil_k3_')
    r = node_calistir(kok, YEDEK_JS, {'cagrilar': [list(c[:3]) for c in K3_CAGRILARI]},
                      tmp, 'yedek')
    assert not (isinstance(r, dict) and 'error' in r), r
    s = ceviri_anahtar(sorted({c[2] for c in K3_CAGRILARI}), tmp)
    for x in r:
        x['sozluk_en'] = s['en'].get(x['anahtar'])
    return r


class TestK3CagriYeriYedekleri:
    @node_gerek
    def test_yedek_sozluk_EN_metniyle_birebir(self, tmp_path):
        r = k3_olc(ROOT, tmp_path)
        beklenen = {(c[0], c[2]): c[3] for c in K3_CAGRILARI}
        for x in r:
            assert len(x['yedekler']) == beklenen[(x['dosya'], x['anahtar'])], x
            assert x['sozluk_en'], x
            for y in x['yedekler']:
                assert y == x['sozluk_en'], (x['dosya'], x['anahtar'], y, x['sozluk_en'])


# ===========================================================================
# K4 — viz3dOkLines birimsiz yol (panels/cfd_panel.js)
# ===========================================================================
OK_SATIRI_JS = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const ROOT = process.argv[2]; const JOB = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
function kutu() { return { style: {}, attrs: {}, setAttribute() {}, getAttribute() { return null; },
    appendChild(c) { return c; }, addEventListener() {}, querySelector() { return null; },
    querySelectorAll() { return []; } }; }
const sb = { console: { warn() {}, log() {}, error() {} }, setTimeout, clearTimeout, setInterval, clearInterval,
    JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error, Promise,
    parseFloat, parseInt, isNaN, isFinite };
sb.window = sb; sb.self = sb; sb.localStorage = null;
sb.document = { readyState: 'loading', documentElement: { setAttribute() {} }, addEventListener() {},
    querySelectorAll: () => [], querySelector: () => null, getElementById: () => null,
    createElement: kutu, body: kutu() };
sb.AnalysisCenter = { register() {} };
vm.createContext(sb);
for (const f of ['i18n.js', 'i18n_common.js', 'units_constants.js']) {
    vm.runInContext(fs.readFileSync(ROOT + '/hrma/static/js/' + f, 'utf8'), sb, { filename: f }); }
// GERÇEK kapanış: viz3dOkLines IIFE içinde; test yüzeyine (window.CfdPanel)
// dokunulmadan, bellekteki kopyada dışa açılır.
let src = fs.readFileSync(ROOT + '/hrma/static/js/panels/cfd_panel.js', 'utf8');
const i = src.lastIndexOf('    window.CfdPanel = {');
if (i < 0) throw new Error('CfdPanel yüzeyi bulunamadı');
src = src.slice(0, i) + '    window.__viz3dOkLines = viz3dOkLines;\n' + src.slice(i);
vm.runInContext(src, sb, { filename: 'cfd_panel.js' });
const out = {};
for (const lang of ['en', 'tr']) {
    sb.I18N.setLang(lang); out[lang] = {};
    for (const ad of Object.keys(JOB.vakalar)) out[lang][ad] = sb.__viz3dOkLines(JOB.vakalar[ad]);
}
process.stdout.write(JSON.stringify(out));
"""

#: Sahnenin dönüş sözlüğü (``motor_viz3d.js`` bindirme yanıtı) biçiminde
#: iki vaka: Mach (``unitLabel`` '' — birimsiz) ve basınç (Pa).
K4_VAKALARI = {
    'mach_birimsiz': {'metric': 'mach', 'unitLabel': '',
                      'range': {'min': 0.1, 'max': 2.91214},
                      'stations': {'shown': 60, 'total': 60},
                      'cells': {'axial': 60, 'radial': 12}},
    'basinc_Pa': {'metric': 'pressure', 'unitLabel': 'Pa',
                  'range': {'min': 1200.5, 'max': 2.0e6},
                  'stations': {'shown': 40, 'total': 60},
                  'cells': {'axial': 60, 'radial': 12}},
}


def k4_olc(kok=ROOT, tmpdir=None):
    tmp = tmpdir or tempfile.mkdtemp(prefix='paneldil_k4_')
    return node_calistir(kok, OK_SATIRI_JS, {'vakalar': K4_VAKALARI}, tmp, 'oksatiri')


class TestK4BirimsizSatir:
    @node_gerek
    def test_birimsiz_satirda_cift_bosluk_yok(self, tmp_path):
        r = k4_olc(ROOT, tmp_path)
        assert 'error' not in r, r
        for d in ('en', 'tr'):
            for ad, satirlar in r[d].items():
                for s in satirlar:
                    assert '  ' not in s, (d, ad, s)
                assert ' ,' not in satirlar[0] and ' — ' in satirlar[0], (d, ad, satirlar[0])
        assert '2.91214 — 60x12' in r['en']['mach_birimsiz'][0]
        assert '2,91214 — 60x12' in r['tr']['mach_birimsiz'][0]

    @node_gerek
    def test_birimli_satir_birimi_tasir(self, tmp_path):
        r = k4_olc(ROOT, tmp_path)
        assert 'Pa — 60x12' in r['en']['basinc_Pa'][0], r['en']
        assert 'Pa — 60x12' in r['tr']['basinc_Pa'][0], r['tr']


# ===========================================================================
# K5 — sunucu beyan cümleleri TR
# ===========================================================================
#: A1b-3 panel-js OH-D37-G2 metinleri — panel-js raporundan BİREBİR
#: (``docs/scofield/raw/OH/A1b/panel-js/a1/rapor.md`` K6; üretici
#: ``visualization.py`` o dalda). Değişken alanlara örnek değer: çıkış
#: künyesi ``sea_level_default_equilibrium`` (panel-js ölçümü) ve p_e.
#: Denetçi 2. tur Ş4: panel-js 4bbbd32f ``visualization.py`` ile karakter
#: karakter karşılaştırıldı; 2. turda eklenen dördüncü ipucu ('p_e not
#: published', ε yolunda çıkış basıncı yayımlanmadıysa) eklendi. panel-js
#: main'e girince ``TestG2Uretici`` aynı metinleri ÜRETİCİDEN alır ve bu
#: kopyaların üreticiyle birebir olduğunu da sınar.
G2_IPUCU = (
    'Exit: ISA sea level, no nozzle ε',
    'Exit: supplied nozzle ε, p_e 1.013 bar',
    'Exit basis not published',
    'Exit: supplied nozzle ε, p_e not published',
)
#: İpucu çıkış satırının beklenen TR karşılığı (bekçinin kendi tablosu).
G2_IPUCU_TR = {
    'Exit: ISA sea level, no nozzle ε': 'Çıkış: ISA deniz seviyesi, nozul ε yok',
    'Exit: supplied nozzle ε, p_e 1.013 bar': 'Çıkış: verilen nozul ε, p_e 1,013 bar',
    'Exit basis not published': 'Çıkış künyesi yayımlanmadı',
    'Exit: supplied nozzle ε, p_e not published': 'Çıkış: verilen nozul ε, p_e yayımlanmadı',
}
#: Koşu noktası notunun üç hâli; ``{kunye}`` üreticinin çıkış künyesi kodu
#: (``conditions.exit.basis``; makine kodudur, TR'de AYNEN kalır).
G2_NOT_SABLONLARI = (
    'This run point: the run O/F solved with the exit anchored to ISA sea '
    'level and no nozzle expansion ratio (exit basis {kunye}) - the same exit '
    "anchor as the sweep curve; it is not the motor's delivered Isp at its "
    'nozzle expansion ratio.',
    'This run point: the run O/F solved with the exit at the supplied nozzle '
    'expansion ratio (exit basis {kunye}); the sweep curve is anchored to ISA '
    'sea level with no expansion ratio - a different thermochemistry path, so '
    'the point need not lie on the curve.',
    'This run point: the solver result does not publish its exit basis, so '
    "whether the point shares the sweep curve's sea-level path or uses the "
    'design expansion ratio is not stated.',
)
#: Denetçi 3. tur Ş1 — üç not hâlinin beklenen TR cümlesi: bekçinin KENDİ
#: şablon tablosu (Ş2'deki CAD tam cümle deseninin aynısı; ürünün
#: ``i18n_charts.js`` desen/sözlük değerleri OKUNMAZ). ``{kunye}`` makine
#: kodudur, AYNEN doldurulur. TR not bu cümleye BİREBİR eşit olmalı: kara
#: liste (``G2_INGILIZCE``) yarı İngilizce yan cümleyi ya da terim kaymasını
#: (nozul → başka sözcük) yakalamıyordu (denetçi E3, E3b, E10).
G2_NOT_SABLONLARI_TR = (
    'Bu koşum noktası: koşumun O/F değeri, çıkışı ISA deniz seviyesine '
    'bağlanarak ve nozul genişleme oranı olmadan çözüldü (çıkış künyesi '
    '{kunye}) - tarama eğrisiyle aynı çıkış çapası; motorun kendi nozul '
    'genişleme oranındaki teslim Isp değeri değildir.',
    'Bu koşum noktası: koşumun O/F değeri, çıkış verilen nozul genişleme '
    'oranında alınarak çözüldü (çıkış künyesi {kunye}); tarama eğrisi '
    'genişleme oranı olmadan ISA deniz seviyesine bağlıdır - farklı bir '
    'termokimya yolu, bu yüzden noktanın eğrinin üzerinde olması gerekmez.',
    'Bu koşum noktası: çözücü çıktısı çıkış künyesini yayımlamıyor; bu yüzden '
    'noktanın tarama eğrisinin deniz seviyesi yolunu mu paylaştığı yoksa '
    'tasarım genişleme oranını mı kullandığı belirtilmiyor.',
)
G2_NOTLAR = (
    G2_NOT_SABLONLARI[0].format(kunye='sea_level_default_equilibrium'),
    G2_NOT_SABLONLARI[1].format(kunye='supplied_expansion_ratio_equilibrium'),
    G2_NOT_SABLONLARI[2],
)
#: Künye kodu sınaması: denetçi Ş1'in örnek kodu + üreticinin yayımladığı
#: dört gerçek çıkış künyesi (combustion_analysis.py exit_pressure_basis:
#: deniz seviyesi yolu 'sea_level_default*' → not 0, ε yolu → not 1).
G2_KUNYELI_NOTLAR = (
    (0, 'sea_level_default_equilibrium'), (0, 'sea_level_default'),
    (1, 'supplied_expansion_ratio_equilibrium'),
    (1, 'expansion_ratio_equilibrium'), (1, 'expansion_ratio'),
)
#: G2 TR çıktısında kalmaması gereken İngilizce.
#: ('supplied' yok: Ş1'in örnek künye kodu 'supplied_expansion_ratio_
#: equilibrium' makine kodu olarak TR'de AYNEN kalır; 'nozzle' onu tutar.)
G2_INGILIZCE = ('Exit', 'This run', 'sweep curve', 'not published',
                'solver result', 'nozzle', 'sea level', 'thermochemistry')

#: Ş2 — CAD çizilmeyen parça beyanının beklenen TR sözcükleri: bekçinin
#: KENDİ tablosu (ürünün CIZILMEYEN_PARCA_TR / CIZILMEME_NEDENI_TR tablosu
#: okunmaz). Üretici (cad_visualization.py LIQUID/SOLID_NOT_DRAWN_PARTS)
#: yeni parça eklerse bu tablo eksik kalır → bekçi adıyla kırmızı olur
#: (ürün cümlesi o durumda fail-closed İngilizce AYNEN kalır).
CAD_PARCA_TR = {
    'injector head': 'enjektör kafası',
    'cooling jacket': 'soğutma ceketi',
    'feed lines': 'besleme hatları',
    'flanges/bolts': 'flanşlar/cıvatalar',
    'sensors': 'sensörler',
    'grain pattern': 'yakıt bloğu deseni',
    'inhibitor': 'yanma engelleyici',
    'case details': 'kasa ayrıntıları',
}
CAD_NEDEN_TR = {
    'no dimension is published for them': 'bunlar için yayımlanmış ölçü yok',
    'the detailed solid-motor generator is not modelled':
        'ayrıntılı katı motor üreticisi modellenmedi',
}

#: TR çıktıda KALMAMASI gereken İngilizce gövde işaretleri. 3. turdan beri
#: yalnız EK KEMER: asıl ölçüt aşağıdaki tam cümle tabloları (``K5_TR_TAM``,
#: ``cad_beklenen_tr``); kara liste bu tabloların kendisini de sınar.
K5_INGILIZCE = ('not drawn', 'not published', 'not supplied', 'no duration',
                'is assumed', 'were not', 'was not', 'Supply ', 'Fill ',
                'dimension', 'generator', 'This run', 'sweep curve', 'Exit',
                'thermochemistry', 'sea level', 'the solver')

#: Denetçi 3. tur Ş2 — K5 (b)/(c) cümlelerinin beklenen TR karşılığı:
#: bekçinin KENDİ tablosu, anahtar = ÜRETİCİNİN EN cümlesi (üretici cümleyi
#: değiştirirse anahtar bulunmaz → adıyla KIRMIZI; ürün sözlüğü o durumda
#: cümleyi zaten çeviremez). TR çıktı bu cümleye BİREBİR eşit olmalı (kara
#: liste yarı İngilizce yan cümleyi yakalamıyordu — denetçi E15).
K5_TR_TAM = {
    'perf_suresiz': (
        'Performance chart not drawn: burn_time was not published by the '
        'solver (no burn time was supplied) and no duration is assumed.',
        'Performans grafiği çizilmedi: çözücü burn_time yayımlamadı (yanma '
        'süresi verilmedi) ve süre varsayılmıyor.'),
    'perf_itkisiz': (
        'Performance chart not drawn: thrust was not published by the solver '
        'and no design thrust is assumed.',
        'Performans grafiği çizilmedi: çözücü itkiyi (thrust) yayımlamadı ve '
        'tasarım itkisi varsayılmıyor.'),
    'guvenlik_sure': (
        'burn time not supplied: motor_data carries no burn_time and no '
        'duration is assumed (the previous code silently used 10 s), so the '
        'quantities that depend on it were not evaluated. Supply burn_time '
        '[s] to get them.',
        'yanma süresi verilmedi: motor_data burn_time taşımıyor ve süre '
        'varsayılmıyor (önceki kod sessizce 10 s kullanıyordu); bu yüzden ona '
        'bağlı büyüklükler değerlendirilmedi. Bunları almak için burn_time '
        '[s] verin.'),
    'sivi_sure': (
        'the burn time was not supplied (max_burn_duration is empty) and no '
        'default is assumed, so nothing that depends on it was computed: '
        'burn_time, total_impulse, propellant_mass_kg, the propellant tank '
        'card, the feed-system tank volumes and the autogenous pressurant '
        'budget. Fill "Maximum Burn Duration" (or send use_tutorial_defaults '
        'for the declared tutorial value) to get them.',
        'yanma süresi verilmedi (max_burn_duration boş) ve varsayılan kabul '
        'edilmiyor; bu yüzden ona bağlı hiçbir şey hesaplanmadı: burn_time, '
        'total_impulse, propellant_mass_kg, itici tankı kartı, besleme '
        'sistemi tank hacimleri ve otojen basınçlandırıcı bütçesi. Bunları '
        'almak için "Azami Yanma Süresi" alanını doldurun (ya da beyan edilen '
        'eğitim değeri için use_tutorial_defaults gönderin).'),
    'itki_irtifa': (
        'burn time not supplied (motor_data has no positive burn_time) and no '
        'duration is assumed, so the sea-level thrust (total impulse / burn '
        'time) and the altitude table built on it were not computed. The '
        'previous code silently used 10 s here.',
        'yanma süresi verilmedi (motor_data pozitif bir burn_time taşımıyor) '
        've süre varsayılmıyor; bu yüzden deniz seviyesi itkisi (toplam itki '
        '/ yanma süresi) ve onun üzerine kurulan irtifa tablosu hesaplanmadı. '
        'Önceki kod burada sessizce 10 s kullanıyordu.'),
}


def cad_beklenen_tr(parcalar, neden):
    """Ş2 (2. tur): CAD beyanının beklenen TR cümlesi bekçinin tablosundan."""
    etiketler = [etiket for _anahtar, etiket in parcalar]
    eksik = [e for e in etiketler if e not in CAD_PARCA_TR]
    eksik += [] if neden in CAD_NEDEN_TR else [neden]
    assert not eksik, ('üretici bekçinin TR tablosunda olmayan parça/neden '
                       'yayımlıyor', eksik)
    return ('Çizilmeyen parçalar: ' + ', '.join(CAD_PARCA_TR[e] for e in etiketler)
            + ' (' + CAD_NEDEN_TR[neden] + ')')


def beyan_cumleleri(istemci=None):
    """K5 cümleleri ÜRETİCİDEN (gerçek sınıf / sabit / uç)."""
    with contextlib.redirect_stdout(io.StringIO()):
        import plotly.graph_objects as go  # noqa: F401
        from plotly.subplots import make_subplots
        from hrma.export.cad_visualization import (DetailedCADGenerator,
                                                   MotorCADDesigner)
        from hrma.engines.liquid_rocket_engine import (
            BURN_TIME_NOT_SUPPLIED_REASON as SIVI_GEREKCE)
        from hrma.engines.combustion_analysis import CombustionAnalyzer
    G = DetailedCADGenerator
    out = {
        'cad_sivi': G._not_drawn_block(G.LIQUID_NOT_DRAWN_PARTS,
                                       G.LIQUID_NOT_DRAWN_REASON)['declaration'],
        'cad_kati': G._not_drawn_block(G.SOLID_NOT_DRAWN_PARTS,
                                       G.SOLID_NOT_DRAWN_REASON)['declaration'],
    }
    for ad, md in (('perf_suresiz', {'thrust': 1000.0}),
                   ('perf_itkisiz', {'burn_time': 5.0})):
        fig = make_subplots(rows=1, cols=1)
        out[ad] = _sessiz(MotorCADDesigner()._add_performance_chart, fig, md, 1, 1)
    out['sivi_sure'] = SIVI_GEREKCE
    ca = CombustionAnalyzer()
    # Gerçek yanma paketi (süre alanı YOK — tek çağıran hibrit süreyi daima
    # verir; bu dal süre verilmezse ne yazıldığını ölçer).
    paket = _sessiz(ca.analyze_combustion, {'htpb': 100.0}, 'n2o', 6.0, 20.0)
    assert 'burn_time' not in paket
    t = _sessiz(ca.calculate_thrust_at_altitudes, 21000.0, dict(paket), [0.0, 5000.0])
    out['itki_irtifa'] = t.get('reason')
    if istemci is not None:
        r = _sessiz(istemci.post, '/analyze_safety', json=GUVENLIK_SURESIZ,
                    headers=UC_BASLIGI)
        assert r.status_code == 200, (r.status_code, r.get_json())
        out['guvenlik_sure'] = _derin_bul(r.get_json(), 'burn_time_dependent_not_evaluated')
    return out


def _derin_bul(x, anahtar):
    if isinstance(x, dict):
        if isinstance(x.get(anahtar), dict):
            return x[anahtar].get('reason')
        for v in x.values():
            r = _derin_bul(v, anahtar)
            if r:
                return r
    elif isinstance(x, list):
        for v in x:
            r = _derin_bul(v, anahtar)
            if r:
                return r
    return None


#: /analyze_safety — yanma süresi YOK (sıvı; diğer alanlar dil-cozucu-nesri
#: GUVENLIK_TABAN'ı ile aynı geometri).
GUVENLIK_SURESIZ = {
    'chamber_pressure': 40.0, 'chamber_temperature': 3000.0,
    'propellant_mass': 5.0, 'chamber_diameter': 0.1, 'chamber_length': 0.5,
    'wall_thickness': 0.005, 'thrust': 1000.0,
    'facility_type': 'test_stand', 'material': 'steel_4130',
    'propellant_type': 'lox_rp1', 'motor_type': 'liquid',
}

#: Hangi cümle hangi kanaldan ekrana iner: figür metni (chartText —
#: plotly_dark translateFigure) ya da sunucu nesri (serverText).
K5_KANAL = {
    'cad_sivi': 'chart', 'cad_kati': 'chart', 'perf_suresiz': 'chart',
    'perf_itkisiz': 'chart', 'sivi_sure': 'server', 'itki_irtifa': 'server',
    'guvenlik_sure': 'server',
}


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def beyan(istemci):
    return beyan_cumleleri(istemci)


def _tr_en(server=(), chart=(), tmpdir=None, ad='ceviri'):
    r = ceviri(ROOT, server=server, chart=chart, tmpdir=tmpdir, ad=ad)
    assert 'error' not in r, r
    return r


class TestK5BeyanCumleleri:
    def test_uretici_cumleleri_var(self, beyan):
        for ad, c in beyan.items():
            assert isinstance(c, str) and len(c) > 30, (ad, c)
        assert beyan['cad_sivi'].startswith('Parts not drawn: ')
        assert beyan['perf_itkisiz'].startswith('Performance chart not drawn: thrust')

    @node_gerek
    def test_TR_cevrildi_EN_aynen(self, beyan, tmp_path):
        """Denetçi 3. tur Ş2: yedi cümlenin HER BİRİ bekçinin kendi tam cümle
        tablosuna BİREBİR eşit (K5 b/c: ``K5_TR_TAM``; K5 a: ``cad_beklenen_tr``).
        Kara liste yalnız ek kemer."""
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.export.cad_visualization import DetailedCADGenerator as G
        beklenen = {
            'cad_sivi': cad_beklenen_tr(G.LIQUID_NOT_DRAWN_PARTS, G.LIQUID_NOT_DRAWN_REASON),
            'cad_kati': cad_beklenen_tr(G.SOLID_NOT_DRAWN_PARTS, G.SOLID_NOT_DRAWN_REASON),
        }
        for ad, (en, tr) in K5_TR_TAM.items():
            assert beyan[ad] == en, ('üretici K5 cümlesi bekçinin tablosundakinden '
                                     'farklı', ad, beyan[ad])
            beklenen[ad] = tr
        assert sorted(beklenen) == sorted(beyan), (sorted(beklenen), sorted(beyan))
        adlar = sorted(beyan)
        server = [beyan[a] for a in adlar if K5_KANAL[a] == 'server']
        chart = [beyan[a] for a in adlar if K5_KANAL[a] == 'chart']
        r = _tr_en(server, chart, tmp_path, 'k5')
        assert r['en']['server'] == server and r['en']['chart'] == chart
        tr_cikti = dict(zip([a for a in adlar if K5_KANAL[a] == 'server']
                            + [a for a in adlar if K5_KANAL[a] == 'chart'],
                            r['tr']['server'] + r['tr']['chart']))
        for ad in adlar:
            tr = tr_cikti[ad]
            assert tr == beklenen[ad], (ad, tr, beklenen[ad])
            assert tr != beyan[ad], beyan[ad]
            for ing in K5_INGILIZCE:
                assert ing not in tr, (ing, tr)
            assert re.search('[çğıİöşü]', tr), tr

    @node_gerek
    def test_cad_beyani_parca_adlari_ve_neden(self, beyan, tmp_path):
        r = _tr_en(chart=[beyan['cad_sivi'], beyan['cad_kati']], tmpdir=tmp_path, ad='cad')
        sivi, kati = r['tr']['chart']
        assert sivi.startswith('Çizilmeyen parçalar: enjektör kafası, ') and sivi.endswith(')'), sivi
        assert kati.startswith('Çizilmeyen parçalar: yakıt bloğu deseni, '), kati

    @node_gerek
    def test_cad_alt_grafik_basliklari_TR(self, tmp_path):
        """Beyanla aynı figürün alt grafik başlıkları — ÜRETİCİDEN (gerçek
        DetailedCADGenerator figürü, sıvı + katı)."""
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.export.cad_visualization import DetailedCADGenerator
        g = DetailedCADGenerator()
        # mm girdili gövde (tests/test_d16_kati_a1.py IYI ölçüleri)
        govde = dict(chamber_diameter=100.0, chamber_length=500.0,
                     throat_diameter=25.0, exit_diameter=60.0, nozzle_length=150.0)
        basliklar = []
        for ureten in (g.generate_liquid_motor_cad, g.generate_solid_motor_cad):
            fig = json.loads(_sessiz(ureten, dict(govde))['plot_json'])
            basliklar += [a['text'] for a in fig['layout'].get('annotations') or []
                          if a.get('name') != 'not_drawn_declaration']
        assert 'External View' in basliklar and 'Grain Cross-Section' in basliklar, basliklar
        r = _tr_en(chart=basliklar, tmpdir=tmp_path, ad='cadbas')
        assert r['en']['chart'] == basliklar
        tr = dict(zip(basliklar, r['tr']['chart']))
        assert tr['External View'] == 'Dış Görünüm' and tr['Grain Cross-Section'] == 'Yakıt Bloğu Kesiti'
        assert tr['Cross-Section View'] == 'Kesit Görünümü'

    @node_gerek
    def test_cad_beyani_bilinmeyen_parca_AYNEN(self, beyan, tmp_path):
        """Fail-closed: tanınmayan parça adı ya da neden → cümle İngilizce AYNEN
        (yarı Türkçe cümle üretilmez)."""
        bozuk = [beyan['cad_sivi'].replace('sensors', 'warp coils'),
                 beyan['cad_kati'].replace('is not modelled', 'is on holiday')]
        r = _tr_en(chart=bozuk, server=bozuk, tmpdir=tmp_path, ad='cadb')
        assert r['tr']['chart'] == bozuk and r['tr']['server'] == bozuk

    @node_gerek
    def test_guvenlik_paneli_cip_ipucu_TR(self, istemci, beyan, tmp_path):
        """Ekran yolu: süresiz güvenlik yanıtı GERÇEK güvenlik paneline
        (güverte düzeneği, A1a dil-sozluk) verilir; geri çekilen satırın
        kaynak çipi ipucu gerekçeyi serverText'ten geçirir — TR'de İngilizce
        gerekçe 0, EN'de aynen."""
        import html as _html
        r = _sessiz(istemci.post, '/analyze_safety', json=GUVENLIK_SURESIZ,
                    headers=UC_BASLIGI)
        tr_cumle = _tr_en(server=[beyan['guvenlik_sure']], tmpdir=tmp_path,
                          ad='gp0')['tr']['server'][0]
        out = {}
        for dil in ('en', 'tr'):
            ciz = node_calistir(ROOT, DOCK_DUZENEK, {
                'panelId': 'safety', 'body': r.get_json(), 'lang': dil,
                'preFiles': list(I18N_ZINCIRI),
                'panelFiles': ['hrma/static/js/panels/safety_panel.js']},
                tmp_path, 'gp_' + dil)
            assert not ciz.get('error'), ciz.get('error')
            out[dil] = _html.unescape(ciz['html'])
        assert out['en'].count(beyan['guvenlik_sure']) >= 1, 'EN panelde gerekçe yok'
        assert beyan['guvenlik_sure'] not in out['tr']
        assert out['tr'].count(tr_cumle) >= 1, 'TR panelde çevrilmiş gerekçe yok'

    @node_gerek
    def test_cad_beyani_tam_cumle(self, tmp_path):
        """Denetçi Ş2: TR cümle, üreticinin demetlerinden (LIQUID/SOLID_
        NOT_DRAWN_PARTS + *_REASON) bekçinin kendi TR tablosuyla kurulan
        beklenen cümleye BİREBİR eşit; demetlerdeki hiçbir İngilizce parça
        adı ya da neden TR çıktıda kalmaz (ortadaki/sondaki parça dahil)."""
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.export.cad_visualization import DetailedCADGenerator as G
        vakalar = ((G.LIQUID_NOT_DRAWN_PARTS, G.LIQUID_NOT_DRAWN_REASON),
                   (G.SOLID_NOT_DRAWN_PARTS, G.SOLID_NOT_DRAWN_REASON))
        en, beklenen = [], []
        for parcalar, neden in vakalar:
            en.append(G._not_drawn_block(parcalar, neden)['declaration'])
            beklenen.append(cad_beklenen_tr(parcalar, neden))
        r = _tr_en(chart=en, server=en, tmpdir=tmp_path, ad='cadtam')
        assert r['en']['chart'] == en and r['en']['server'] == en
        assert r['tr']['chart'] == beklenen, (r['tr']['chart'], beklenen)
        assert r['tr']['server'] == beklenen, (r['tr']['server'], beklenen)
        for (parcalar, neden), tr in zip(vakalar, r['tr']['chart']):
            for _anahtar, etiket in parcalar:
                assert etiket not in tr, (etiket, tr)
            assert neden not in tr, (neden, tr)

    @node_gerek
    def test_g2_ipucu_ve_not_TR(self, tmp_path):
        ipucu = ['This run<br>O/F 7.00<br>Isp 245.1 s (solver)<br>%s<extra></extra>' % s
                 for s in G2_IPUCU]
        # Üç not hâli + künye kodu sınaması (denetçi Ş1: 'supplied_expansion_
        # ratio_equilibrium' dahil; üreticinin dört gerçek künyesi).
        notlar = list(G2_NOTLAR) + [G2_NOT_SABLONLARI[i].format(kunye=k)
                                    for i, k in G2_KUNYELI_NOTLAR]
        kunyeler = ['sea_level_default_equilibrium',
                    'supplied_expansion_ratio_equilibrium', None] + \
            [k for _i, k in G2_KUNYELI_NOTLAR]
        # Denetçi 3. tur Ş1: her notun beklenen TR cümlesi bekçinin kendi
        # şablon tablosundan (künye AYNEN doldurulur).
        beklenen_tr = [G2_NOT_SABLONLARI_TR[0].format(kunye=kunyeler[0]),
                       G2_NOT_SABLONLARI_TR[1].format(kunye=kunyeler[1]),
                       G2_NOT_SABLONLARI_TR[2]] + \
            [G2_NOT_SABLONLARI_TR[i].format(kunye=k) for i, k in G2_KUNYELI_NOTLAR]
        chart = ipucu + ['- ' + n for n in notlar]
        r = _tr_en(chart=chart, server=notlar, tmpdir=tmp_path, ad='g2')
        assert r['en']['chart'] == chart and r['en']['server'] == notlar
        for t in r['tr']['chart'] + r['tr']['server']:
            for ing in G2_INGILIZCE:
                assert ing not in t, (ing, t)
            # D27 tek terim kuralı (test_d27_arayuz_a2 p12ab205): nozzle → nozul
            assert not re.search('[Ll]üle', t), t
        # ipucu çıkış satırı BİREBİR (p_e ondalığı virgül; 'not published' hâli)
        for kaynak, t in zip(G2_IPUCU, r['tr']['chart'][:len(ipucu)]):
            assert t.split('<br>')[-1] == G2_IPUCU_TR[kaynak] + '<extra></extra>', t
        assert 'p_e 1,013 bar' in r['tr']['chart'][1], r['tr']['chart'][1]
        # not: grafik kanalı (figür '- ' satırı) = sunucu kanalı; künye kodu
        # MAKİNE — TR'de '(çıkış künyesi <kod>)' kalıbında AYNEN, bir kez.
        tr_not_grafik = r['tr']['chart'][len(ipucu):]
        assert len(r['tr']['server']) == len(beklenen_tr) == len(tr_not_grafik)
        for kunye, t_srv, t_graf, t_bek in zip(kunyeler, r['tr']['server'],
                                              tr_not_grafik, beklenen_tr):
            # Ş1 (3. tur): TAM CÜMLE — sunucu ve grafik kanalı BİREBİR
            assert t_srv == t_bek, (kunye, t_srv, t_bek)
            assert t_graf == '- ' + t_bek, (kunye, t_graf, t_bek)
            assert t_srv.startswith('Bu koşum noktası: '), t_srv
            if kunye is None:
                assert 'çıkış künyesini yayımlamıyor' in t_srv, t_srv
                assert '(çıkış künyesi ' not in t_srv, t_srv
            else:
                assert t_srv.count('(çıkış künyesi %s)' % kunye) == 1, (kunye, t_srv)
        # Denetçi Ş1 (D10): verilen-ε notunun künyesi sunucu çıktısında ve
        # grafik notunda AYNEN.
        assert '(çıkış künyesi supplied_expansion_ratio_equilibrium)' in r['tr']['server'][1]
        assert '(çıkış künyesi supplied_expansion_ratio_equilibrium)' in tr_not_grafik[1]
        assert 'sea_level_default_equilibrium' in r['tr']['server'][0]


# ===========================================================================
# Sözlük gövdesindeki kulvar yorumları — kesme işareti paritesi
# ===========================================================================
def test_kulvar_yorumlarinda_kesme_isareti_paritesi():
    """Sözlük gövdesindeki (ilk girdiden son girdiye) ``A1c panel-dil`` ya da
    ``Denetçi 2. tur`` yorum bloklarında kesme işareti sayısı ÇİFT olmalı:
    tırnak duyarlı ayrıştırıcılar tek sayıda kesme işaretinde EN/TR sınırını
    kaçırır (tests/test_d29_arayuz_i18n_a2.py
    test_a2_sozluk_yorumlarinda_kesme_isareti_paritesi aynı ölçüt; o düğüm
    main'de başka dosyaların yorumları yüzünden zaten kırmızı, bu yüzden bu
    kulvarın payı burada ayrıca kilitlenir). Ölçüldü (28 Eyl, kural 14
    süpürmesi): ilk turun G2 desen yorumu tek sayıdaydı."""
    girdi = re.compile(r"^\s*'[\w.]+':\s*'", re.M)
    kiran, bakilan = [], 0
    for ad in ('i18n_charts.js', 'i18n_common.js'):
        src = _oku(JS / ad)
        girdiler = list(girdi.finditer(src))
        bas, son = girdiler[0].start(), girdiler[-1].end()
        for m in re.finditer(r'/\*.*?\*/', src[bas:son], re.S):
            blok = m.group(0)
            if 'A1c panel-dil' not in blok and 'Denetçi 2. tur' not in blok:
                continue
            bakilan += 1
            if blok.count("'") % 2:
                kiran.append('%s:%d' % (ad, src[:bas + m.start()].count('\n') + 1))
    assert bakilan >= 8, bakilan
    assert not kiran, kiran


# ===========================================================================
# K5 (d) — panel-js G2 metinleri ÜRETİCİDEN (denetçi 2. tur Ş4)
# ===========================================================================
def g2_uretici_metinleri():
    """panel-js OH-D37-G2 koşu noktası ipucu + notu ÜRETİCİDEN
    (``create_combustion_analysis_plots``). Gerçek ``analyze_combustion``:
    ε verilmeden (deniz seviyesi künyesi) ve ε = 8 ile (ε künyesi). Künyenin
    / p_e'nin yayımlanmadığı ve tek-γ künyeli hâller AYNI gerçek yanıt
    üstünde alan silinerek / künye kodu değiştirilerek kurulur (sayı
    uydurulmaz; yalnız üreticinin künye dalı seçilir). Üretici bu ağaçta G2
    yayımlamıyorsa (panel-js main'e girmediyse) o vaka None.

    Denetçi 3. tur Ş3: ilk koşu noktasız vakada None dönmek yerine altı
    vakanın hepsi koşulur; her vaka için figürde G2'nin HERHANGİ bir izi
    (``meta`` içinde ``point_kind``/``exit_basis`` ya da 'This run point'
    notu) ayrıca kaydedilir — atlama kararı tek işarete bağlı değildir."""
    import copy
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        from hrma.visualization.visualization import create_combustion_analysis_plots
        ca = CombustionAnalyzer()
        deniz = ca.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0)
        eps = ca.analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0,
                                    expansion_ratio=8.0)

    def degis(cd, basis=None, sil=None):
        cd = copy.deepcopy(cd)
        cikis = cd['conditions']['exit']
        if basis is not None:
            cikis['basis'] = basis
        if sil:
            cikis.pop(sil, None)
        return cd

    vakalar = {
        'deniz': deniz, 'eps': eps,
        'deniz_tek_gamma': degis(deniz, basis='sea_level_default'),
        'eps_tek_gamma': degis(eps, basis='expansion_ratio'),
        'kunye_yok': degis(deniz, sil='basis'),
        'eps_pe_yok': degis(eps, sil='P'),
    }
    out, figur_izi = {}, {}
    for ad, cd in vakalar.items():
        with contextlib.redirect_stdout(io.StringIO()):
            fig = create_combustion_analysis_plots(cd, {
                'fuel_composition': {'htpb': 100.0}, 'oxidizer_type': 'n2o',
                'chamber_pressure': 20.0})
        fig = json.loads(fig) if isinstance(fig, str) else fig
        nokta = [t for t in fig['data'] if isinstance(t.get('meta'), dict)
                 and t['meta'].get('point_kind') == 'run_operating_point']
        notlar = [a['text'] for a in fig['layout'].get('annotations') or []
                  if isinstance(a.get('text'), str) and a['text'].startswith('- ')]
        figur_izi[ad] = (
            any(isinstance(t.get('meta'), dict)
                and ('point_kind' in t['meta'] or 'exit_basis' in t['meta'])
                for t in fig['data'])
            or any('This run point' in n for n in notlar))
        out[ad] = None if not nokta else {
            'kunye': nokta[0]['meta'].get('exit_basis'),
            'ipucu': nokta[0]['hovertemplate'], 'notlar': notlar}
    return {'vakalar': out, 'figur_izi': figur_izi}


#: Denetçi 3. tur Ş3 — üretici kaynağında (``hrma/**/*.py``) OH-D37-G2
#: kodunun izleri. HİÇBİRİ yoksa (ve figürde de iz yoksa) panel-js bu
#: ağaçta değildir → adıyla atlanır. Biri bile varsa ve figürde koşu
#: noktası (``point_kind == 'run_operating_point'``) bulunamazsa KIRMIZI:
#: tek işarete bağlı koşul fail-open'dı (denetçi E17 tam o işareti
#: 'run_point' yapıyordu ve düğüm ATLANIYORDU).
G2_URETICI_IZLERI = ('This run point', '_run_kunye', 'run_operating_point')


def g2_kaynak_izleri(kok=ROOT):
    """``hrma/**/*.py`` içinde G2 izleri: {iz: [dosya, …]} (dosyadan okunur;
    ``inspect.getsource`` KULLANILMAZ)."""
    bulunan = {}
    for yol in sorted((Path(kok) / 'hrma').rglob('*.py')):
        metin = yol.read_text(encoding='utf-8', errors='replace')
        for iz in G2_URETICI_IZLERI:
            if iz in metin:
                bulunan.setdefault(iz, []).append(str(yol.relative_to(kok)))
    return bulunan


@pytest.fixture(scope='module')
def g2_uretici():
    return g2_uretici_metinleri()


class TestG2Uretici:
    @node_gerek
    def test_uretici_metinleri_TR_ve_kopyalar_birebir(self, g2_uretici, tmp_path):
        # Denetçi 3. tur Ş3 — fail-closed atlama: G2 kodunun HİÇBİR izi yoksa
        # (kaynakta üç işaretin hiçbiri, figürde hiçbir iz) adıyla atla; iz
        # varsa ve figürde koşu noktası yoksa KIRMIZI.
        izler = g2_kaynak_izleri()
        figur_izi = sorted(ad for ad, var in g2_uretici['figur_izi'].items() if var)
        if not izler and not figur_izi:
            pytest.skip('panel-js OH-D37-G2 üreticisi bu ağaçta yok (hrma/**/*.py '
                        'içinde %s izlerinin hiçbiri yok, figürde koşu noktası '
                        'izi yok; dalga37b/panel-js main\'e girmedi); metinler '
                        'test_g2_ipucu_ve_not_TR\'de rapordan birebir kopyayla '
                        'sınanıyor' % ' / '.join(G2_URETICI_IZLERI))
        eksik = sorted(ad for ad, v in g2_uretici['vakalar'].items() if v is None)
        assert not eksik, ('G2 kodunun izi var ama figürde koşu noktası '
                           "(meta point_kind == 'run_operating_point') yok",
                           {'kaynak_izleri': izler, 'figur_izi': figur_izi,
                            'noktasiz_vakalar': eksik})
        vakalar = g2_uretici['vakalar']
        # Hand-copy ⟷ üretici: ipucu çıkış satırı G2_IPUCU ailesinden, not
        # satırı şablon + üreticinin künyesiyle BİREBİR.
        beklenen_sablon = {'deniz': 0, 'deniz_tek_gamma': 0, 'eps': 1,
                           'eps_tek_gamma': 1, 'eps_pe_yok': 1, 'kunye_yok': 2}
        assert sorted(vakalar) == sorted(beklenen_sablon), sorted(vakalar)
        metinler, g2_satir = [], {}
        for ad, v in vakalar.items():
            cikis = v['ipucu'].replace('<extra></extra>', '').split('<br>')[-1]
            if ad == 'eps' or ad == 'eps_tek_gamma':
                assert re.fullmatch(r'Exit: supplied nozzle ε, p_e \d+\.\d{3} bar', cikis), cikis
            else:
                assert cikis in G2_IPUCU, (ad, cikis)
            satir = [s for n in v['notlar'] for s in n.split('<br>')
                     if 'This run point' in s]
            assert len(satir) == 1, (ad, v['notlar'])
            sablon = G2_NOT_SABLONLARI[beklenen_sablon[ad]]
            assert satir[0] == '- ' + sablon.format(kunye=v['kunye']), (ad, satir[0])
            g2_satir[ad] = satir[0]
            metinler += [v['ipucu']] + v['notlar']
        r = _tr_en(chart=metinler, tmpdir=tmp_path, ad='g2u')
        assert r['en']['chart'] == metinler
        tr = dict(zip(metinler, r['tr']['chart']))
        for ad, v in vakalar.items():
            tr_cikis = tr[v['ipucu']].replace('<extra></extra>', '').split('<br>')[-1]
            if ad in ('eps', 'eps_tek_gamma'):
                assert re.fullmatch(r'Çıkış: verilen nozul ε, p_e \d+,\d{3} bar', tr_cikis), tr_cikis
            else:
                assert tr_cikis == G2_IPUCU_TR[v['ipucu'].replace(
                    '<extra></extra>', '').split('<br>')[-1]], tr_cikis
            tr_g2 = [s for n in v['notlar'] for s in tr[n].split('<br>')
                     if 'This run point' in s or 'Bu koşum noktası' in s]
            assert len(tr_g2) == 1 and tr_g2[0].startswith('- Bu koşum noktası: '), (ad, tr_g2)
            # Ş1 (3. tur): TR not bekçinin kendi şablon tablosuna BİREBİR
            beklenen = '- ' + G2_NOT_SABLONLARI_TR[beklenen_sablon[ad]].format(
                kunye=v['kunye'])
            assert tr_g2[0] == beklenen, (ad, tr_g2[0], beklenen)
            for ing in G2_INGILIZCE:
                assert ing not in tr_g2[0] and ing not in tr_cikis, (ad, ing, tr_g2[0], tr_cikis)
            if v['kunye'] is not None:
                assert tr_g2[0].count('(çıkış künyesi %s)' % v['kunye']) == 1, (ad, tr_g2[0])
            assert not re.search('[Ll]üle', tr_g2[0] + tr_cikis), (ad, tr_g2[0], tr_cikis)
        # gerçek künyeler: deniz seviyesi ve ε yolu ikisi de koşuldu
        assert vakalar['deniz']['kunye'].startswith('sea_level_default')
        assert vakalar['eps']['kunye'].startswith('expansion_ratio')


# ===========================================================================
# EK — dil-cozucu-nesri denetçi Ş3: bekçisiz dört desen (TR + virgül)
# ===========================================================================
def ek_cumleleri():
    """Dört desenin cümleleri ÜRETİCİDEN: hibrit motor (L* üst kelepçe),
    yanma panosu (dar O/F bandı: koşu noktası dışarıda + tepe uçta), Isp
    yüzeyi (inceltilmiş tavan ipucu)."""
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        from hrma.engines.combustion_analysis import CombustionAnalyzer
        from hrma.visualization.visualization import (
            create_combustion_analysis_plots,
            create_chamber_pressure_mixture_ratio_3d_surface)
        m = HybridRocketEngine(thrust=1000, chamber_pressure=20, of_ratio=6.0,
                               l_star=1e3)
        m.calculate()
        cd = CombustionAnalyzer().analyze_combustion({'htpb': 100.0}, 'n2o', 6.0, 20.0)
        pano = create_combustion_analysis_plots(cd, {
            'fuel_composition': {'htpb': 100.0}, 'oxidizer_type': 'n2o',
            'chamber_pressure': 20.0, 'of_range': (1.0, 2.0)})
        yuzey = create_chamber_pressure_mixture_ratio_3d_surface({
            'fuel_type': 'htpb', 'oxidizer_type': 'n2o', 'grid_n': 3,
            'of_range': (4.0, 9.0)})
    pano = json.loads(pano) if isinstance(pano, str) else pano
    yuzey = json.loads(yuzey) if isinstance(yuzey, str) else yuzey
    not_ = [a['text'] for a in pano['layout'].get('annotations') or []
            if isinstance(a.get('text'), str) and a['text'].startswith('- ')]
    tavan = [t.get('hovertemplate') for t in yuzey['data']
             if 'Grid maximum was' in (t.get('hovertemplate') or '')]
    return {'l_star_note': m.l_star_note, 'l_star_clamped_high': m.l_star_clamped_high,
            'pano_notu': not_[0] if not_ else None,
            'tavan_ipucu': tavan[0] if tavan else None}


@pytest.fixture(scope='module')
def ek():
    return ek_cumleleri()


class TestEkDortDesen:
    def test_uretici_dallari_olustu(self, ek):
        assert ek['l_star_clamped_high'] is True and 'NOT applied' in ek['l_star_note']
        assert 'is OUTSIDE the swept band' in ek['pano_notu']
        assert 'sits on the END of the swept band' in ek['pano_notu']
        assert ek['tavan_ipucu'] and 'Grid maximum was' in ek['tavan_ipucu']

    @node_gerek
    def test_l_star_ust_kelepce_TR_virgul(self, ek, tmp_path):
        r = _tr_en(server=[ek['l_star_note']], tmpdir=tmp_path, ad='lstar2')
        tr = r['tr']['server'][0]
        assert r['en']['server'][0] == ek['l_star_note']
        assert tr.startswith('İstenen L* = ') and 'UYGULANMADI' in tr, tr
        assert 'kelepçelenir' in tr and not re.search(r'\d\.\d', tr), tr

    @node_gerek
    def test_pano_disarida_ve_uc_notlari_TR_virgul(self, ek, tmp_path):
        r = _tr_en(chart=[ek['pano_notu']], tmpdir=tmp_path, ad='pano')
        assert r['en']['chart'][0] == ek['pano_notu']
        satirlar = r['tr']['chart'][0].split('<br>')
        disari = [s for s in satirlar if 'DIŞINDA' in s]
        uc = [s for s in satirlar if 'UCUNDA' in s]
        assert len(disari) == 1 and len(uc) == 1, satirlar
        assert re.fullmatch(r'- Bu koşumun O/F değeri \d+,\d\d, taranan \d+,\d\d-\d+,\d\d '
                            r'bandının DIŞINDA; eğri çalışma noktasını kapsamıyor\.', disari[0]), disari
        assert re.search(r'\(O/F \d+,\d\d\)', uc[0]) and 'Sweep' not in uc[0], uc
        # panel-js OH-D37-G2 birleşince koşu noktası notu da ÜRETİCİDEN gelir:
        # varsa İngilizce kalmamalı (yoksa bu satır boş kümedir).
        g2 = [s for s in satirlar if 'This run point' in s or 'Bu koşum noktası' in s]
        for s in g2:
            assert 'This run point' not in s, s

    @node_gerek
    def test_izgara_azamisi_TR_virgul(self, ek, tmp_path):
        r = _tr_en(chart=[ek['tavan_ipucu']], tmpdir=tmp_path, ad='tavan')
        tr = r['tr']['chart'][0]
        assert r['en']['chart'][0] == ek['tavan_ipucu']
        assert re.search(r'<br>Izgara azamisi \d+,\d s idi<extra>', tr), tr
        assert 'Grid maximum' not in tr
