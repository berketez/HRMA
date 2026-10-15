# -*- coding: utf-8 -*-
"""ÖH D37 · A1b · kulvar ``dil-cozucu-nesri`` (a1) bekçileri.

Kanıt paketi: ``docs/scofield/raw/OH/A1b/dil-cozucu-nesri/a1/`` (``once.json``
taban 4989c4a6 dondurulmuş ağaçta, ``sonra.json`` kulvarda, aynı ``olcum.py``
ile — o betik düzenekleri BU dosyadan içe aktarır; yön kanıt → test, bu dosya
``docs/``a bağlı DEĞİLDİR; ``mutasyon.md``; ``rapor.md``).

Kalemler (kart A1b-2):

  DV36-02   enjektör şemasının "Solver warnings for this injector" kutusu:
            '- SEV: mesaj' satırı serverText çekirdeğinden geçer (TR).
  DV36-03   toksik envanter + hibrit patlayıcı sınıfı dayanak cümleleri TR
            (fail-closed: tanınmayan iç parça → cümle AYNEN).
  DV-GT21   thrust_curve.basis, sampling.basis, dry_mass_basis, katı iki-faz
            durum künyesi (beş dal) TR.
  DV36-21   G-1 tarama işaretinin hover/not metinleri TR.
  DV36-22   İngilizce sunucu nesrindeki ondalıklar (L* notu) — TR virgül.
  DV36-16   'Final port' figür metni TR ondalık (I18N.decimalText).
  DV-MIXED  köken notu yapısal kod (``provenance`` + ``provenance_basis_en``)
            + istemci eşlemesi.
  DV-LIQUID proje rozetleri TR sözlük etiketi.
  CW-D4     sıvı satırında It: çözücü yayımladıysa sayı, yoksa nedeni.

Cümleler ÜRETİCİDEN alınır (gerçek uç / gerçek motor fonksiyonu); elle
yazılmış kopya yalnız fail-closed (tanınmayan parça) sınamasında kullanılır.
Kaynak okuyan bekçi yok; JS gövdeleri dosyadan sökülüp node'da koşulur.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node kurulu değil')
UC_BASLIGI = {'Host': '127.0.0.1:8080'}

#: Örnek projeler (ürünün kendi örnekleri; yük elde uydurulmaz).
ORNEK_PROJELER = {
    '/calculate': 'Example Hybrid N2O-HTPB 3kN',
    '/calculate_solid': 'Example Solid KNDX BATES 75mm',
    '/calculate_liquid': 'Example Liquid LOX-RP1 25kN',
}

#: /analyze_safety gövdeleri: aynı geometri, itici kimliği değişir. Her biri
#: toksik/patlayıcı dayanak ailesinin bir dalını üretir (ölçüldü, once.json).
GUVENLIK_TABAN = {
    'chamber_pressure': 40.0, 'chamber_temperature': 3000.0,
    'propellant_mass': 5.0, 'chamber_diameter': 0.1, 'chamber_length': 0.5,
    'wall_thickness': 0.005, 'thrust': 1000.0, 'burn_time': 10.0,
    'facility_type': 'test_stand', 'material': 'steel_4130',
}
GUVENLIK_VAKALARI = {
    'hib_n2o_htpb': {'propellant_type': 'n2o_htpb', 'motor_type': 'hybrid'},
    'hib_htpb': {'propellant_type': 'htpb', 'motor_type': 'hybrid'},
    'hib_ox_n2o': {'propellant_type': 'htpb', 'motor_type': 'hybrid',
                   'oxidizer_type': 'n2o'},
    'sivi_lox_rp1': {'propellant_type': 'lox_rp1', 'motor_type': 'liquid'},
    'sivi_n2o4_mmh': {'propellant_type': 'n2o4_mmh', 'motor_type': 'liquid'},
    'sivi_mono': {'propellant_type': 'liquid_monoprop', 'motor_type': 'liquid'},
    'sivi_biprop': {'propellant_type': 'liquid_biprop', 'motor_type': 'liquid'},
    'kati_apcp': {'propellant_type': 'apcp', 'motor_type': 'solid'},
    'hib_class': {'propellant_type': 'hybrid_n2o', 'motor_type': 'hybrid'},
}
GUVENLIK_ALANLARI = ('explosive_class_basis', 'toxic_inventory_basis')

#: Katı iki-faz durum künyesinin beş dalı: (X_p, kullanıcı eta).
IKI_FAZ_DALLARI = {
    'pencere_disi': (0.44, None),
    'uygulanmadi': (0.2, None),
    'sifir': (0.0, None),
    'kesir_yok': (None, None),
    'kullanici': (0.2, 0.95),
}

#: TR çıktıda KALMAMASI gereken İngilizce gövde işaretleri (kalem başına).
INGILIZCE_ISARET = {
    'guvenlik': ('is not a tabulated class', 'names a propellant CLASS',
                 'tabulated exposure-limit', 'The value sent in',
                 'hydrazine family', 'was read from it', 'ASSUMPTION about'),
    'iki_faz': ('The delivered Isp', 'lies OUTSIDE', 'no user multiplier',
                'A user two-phase', 'No condensed-phase', 'exactly zero'),
    'gt21': ('time-marching solution', 'burn-back solver', 'UNCHANGED',
             'AUTHORITATIVE'),
}

SOZLUK_DOSYALARI_B1 = ('i18n.js', 'i18n_common.js', 'i18n_charts.js')


# ===========================================================================
# Ortak düzenekler (olcum.py bunları içe aktarır)
# ===========================================================================
def node_calistir(kok, script_metni, yuk, tmpdir, ad):
    """``node <script> <kok> <girdi.json>`` → JSON (ya da {'error': ...})."""
    script = os.path.join(str(tmpdir), ad + '.js')
    with open(script, 'w', encoding='utf-8') as fh:
        fh.write(script_metni)
    girdi = os.path.join(str(tmpdir), ad + '.json')
    with open(girdi, 'w', encoding='utf-8') as fh:
        json.dump(yuk, fh, ensure_ascii=False)
    p = subprocess.run([NODE or 'node', script, str(kok), girdi],
                       capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        return {'error': p.stderr[-2000:]}
    return json.loads(p.stdout)


CEVIRI_JS = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const ROOT = process.argv[2]; const JOB = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const sandbox = { console: { warn() {}, log() {}, error() {} }, setTimeout, clearTimeout, setInterval, clearInterval,
    JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error, parseFloat, parseInt, isNaN, isFinite };
sandbox.window = sandbox; sandbox.self = sandbox; sandbox.localStorage = null;
sandbox.document = { readyState: 'loading', documentElement: { setAttribute() {} }, addEventListener() {},
    querySelectorAll: () => [], querySelector: () => null, getElementById: () => null };
vm.createContext(sandbox);
for (const f of JOB.files) {
    vm.runInContext(fs.readFileSync(ROOT + '/hrma/static/js/' + f, 'utf8'), sandbox, { filename: f }); }
const out = {};
for (const lang of ['tr', 'en']) {
    sandbox.I18N.setLang(lang);
    out[lang] = { server: (JOB.server || []).map((m) => sandbox.I18N.serverText(m)),
                  chart: (JOB.chart || []).map((m) => sandbox.I18N.chartText(m)) };
}
process.stdout.write(JSON.stringify(out));
"""


def ceviri(kok, server=(), chart=(), tmpdir=None, ad='ceviri'):
    """Gerçek sözlük dosyalarıyla serverText / chartText (TR ve EN)."""
    tmp = tmpdir or tempfile.mkdtemp(prefix='dilb1_')
    return node_calistir(kok, CEVIRI_JS, {
        'files': list(SOZLUK_DOSYALARI_B1), 'server': list(server),
        'chart': list(chart)}, tmp, ad)


# --- proje şeridi (project_bar.js) -----------------------------------------
PROJE_JS = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const ROOT = process.argv[2]; const JOB = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const src = fs.readFileSync(ROOT + '/hrma/static/js/project_bar.js', 'utf8');
function govde(ad) {
    const m = new RegExp('(?:async\\s+)?function\\s+' + ad + '\\s*\\(').exec(src);
    if (!m) throw new Error(ad + ' bulunamadı');
    let d = 0; const j = src.indexOf('{', m.index + m[0].length - 1);
    for (let k = j; k < src.length; k++) {
        if (src[k] === '{') d++;
        else if (src[k] === '}') { d--; if (!d) return src.slice(m.index, k + 1); }
    }
    throw new Error(ad + ' kapanmadı');
}
function dugum(tag) {
    return { tag: tag, cocuk: [], style: { cssText: '' }, attrs: {}, className: '', href: '',
        textContent: '', dataset: {},
        setAttribute: function (k, v) { this.attrs[k] = String(v); },
        addEventListener: function () {},
        appendChild: function (c) { this.cocuk.push(c); return c; },
        insertBefore: function (c) { this.cocuk.push(c); return c; },
        querySelector: function () { return null; } };
}
async function kos(lang) {
    const kap = dugum('div');
    const sb = { console: { warn() {}, log() {}, error() {} }, setTimeout, clearTimeout, setInterval, clearInterval,
        JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error, Promise,
        parseFloat, parseInt, isNaN, isFinite };
    sb.window = sb; sb.self = sb; sb.localStorage = null;
    sb.document = { readyState: 'loading', documentElement: { setAttribute() {} }, addEventListener() {},
        querySelectorAll: () => [], getElementById: () => null, createElement: dugum,
        querySelector: (s) => (s === '.container' ? kap : null) };
    vm.createContext(sb);
    for (const f of ['i18n.js', 'i18n_common.js']) {
        vm.runInContext(fs.readFileSync(ROOT + '/hrma/static/js/' + f, 'utf8'), sb, { filename: f }); }
    sb.I18N.setLang(lang);
    sb.__JOB = JOB;
    const govdeler = ['T', 'TF', 'nf', 'summaryMini', 'projectRow', 'serializeResultsSummary',
                      'buildRecentStrip'].map(govde).join('\n');
    vm.runInContext(
        'var TYPE_PATH = { liquid: "/liquid", solid: "/solid", hybrid: "/hybrid" };\n'
        + 'var motorType = null;\n'
        + 'function srv(s) { return s; } function toast() {} function loadIntoPage() {}\n'
        + 'function closeModal() {}\n'
        + 'async function apiList() { return __JOB.strip; }\n'
        + govdeler + '\n'
        + 'var __out = { rozet: {}, mini: {}, ozet: {} };\n'
        + '__JOB.rozet.forEach(function (t) { var r = projectRow({ name: "x", motor_type: t });'
        + '  __out.rozet[String(t)] = r.cocuk[1].textContent; });\n'
        + 'Object.keys(__JOB.mini).forEach(function (k) { __out.mini[k] = summaryMini(__JOB.mini[k]); });\n'
        + 'Object.keys(__JOB.ozet).forEach(function (k) { motorType = __JOB.ozet[k].motorType;'
        + '  window.currentResults = __JOB.ozet[k].cr; __out.ozet[k] = serializeResultsSummary(); });\n',
        sb, { filename: 'project_bar_parca.js' });
    await vm.runInContext('buildRecentStrip()', sb);
    const liste = (kap.cocuk[0] || { cocuk: [] }).cocuk[1] || { cocuk: [] };
    sb.__out.serit = liste.cocuk.map(function (a) { return (a.cocuk[1] || {}).textContent || null; });
    return sb.__out;
}
(async function () {
    const out = { tr: await kos('tr'), en: await kos('en') };
    process.stdout.write(JSON.stringify(out));
})().catch(function (e) { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""


def proje_olc(kok, job, tmpdir=None):
    tmp = tmpdir or tempfile.mkdtemp(prefix='dilb1p_')
    return node_calistir(kok, PROJE_JS, job, tmp, 'proje')


def sivi_ozet_girdisi(govde):
    """serializeResultsSummary'nin okuduğu alt küme — GERÇEK uç yanıtından."""
    ors = ((govde.get('openrocket') or {}).get('motor_summary') or {})
    return {
        'thrust': govde.get('thrust'), 'isp_sea_level': govde.get('isp_sea_level'),
        'isp_vacuum': govde.get('isp_vacuum'),
        'chamber_pressure': govde.get('chamber_pressure'),
        'burn_time_source': govde.get('burn_time_source'),
        'openrocket': {'motor_summary': {
            'total_impulse': ors.get('total_impulse'),
            'total_impulse_source': ors.get('total_impulse_source')}},
    }


# --- üretici cümleleri ------------------------------------------------------
def ornek_govdesi(ucu):
    yol = ROOT / 'examples' / (ORNEK_PROJELER[ucu] + '.hrma')
    return dict(json.loads(yol.read_text(encoding='utf-8'))['inputs']['fields'])


def uc_yaniti(istemci, ucu, **ek):
    govde = ornek_govdesi(ucu)
    govde.update(ek)
    r = istemci.post(ucu, json=govde, headers=UC_BASLIGI)
    return r.status_code, r.get_json()


def figur_metinleri(govde):
    """Yanıttaki bütün Plotly figürlerinin görünen metinleri (sırasız küme)."""
    out = set()

    def fig_topla(fig):
        if isinstance(fig, str):
            try:
                fig = json.loads(fig)
            except ValueError:
                return
        if not isinstance(fig, dict):
            return
        lay = fig.get('layout') or {}
        for a in (lay.get('annotations') or []):
            if isinstance(a, dict) and isinstance(a.get('text'), str):
                out.add(a['text'])
        for t in (fig.get('data') or []):
            if isinstance(t, dict):
                for k in ('name', 'hovertemplate'):
                    if isinstance(t.get(k), str):
                        out.add(t[k])

    def gez(x, d=0):
        if d > 9:
            return
        if isinstance(x, dict):
            if 'data' in x and 'layout' in x:
                fig_topla(x)
                return
            for v in x.values():
                gez(v, d + 1)
        elif isinstance(x, list):
            for v in x[:60]:
                gez(v, d + 1)
        elif isinstance(x, str) and x.lstrip().startswith('{') \
                and '"layout"' in x and '"data"' in x:
            fig_topla(x)
    gez(govde)
    return sorted(out)


def guvenlik_cumleleri(istemci):
    out = {}
    for ad, ek in GUVENLIK_VAKALARI.items():
        r = istemci.post('/analyze_safety', json=dict(GUVENLIK_TABAN, **ek),
                         headers=UC_BASLIGI)
        bulunan = {}

        def gez(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    if k in GUVENLIK_ALANLARI and isinstance(v, str):
                        bulunan.setdefault(k, set()).add(v)
                    gez(v)
            elif isinstance(x, list):
                for v in x:
                    gez(v)
        gez(r.get_json() or {})
        out[ad] = {'status': r.status_code,
                   **{k: sorted(v) for k, v in bulunan.items()}}
    return out


def iki_faz_cumleleri():
    from hrma.engines.solid_rocket_engine import _two_phase_correction_state
    return {ad: _two_phase_correction_state(xp, eta)[
        'two_phase_correction_status_basis']
        for ad, (xp, eta) in IKI_FAZ_DALLARI.items()}


def nesir_cumleleri(hibrit, kati):
    """DV-GT21 / DV36-22 cümleleri gerçek yanıtlardan."""
    m = hibrit['motor']
    return {
        'hibrit_thrust_basis': m['thrust_curve']['basis'],
        'hibrit_sampling_basis': m['thrust_curve']['sampling']['basis'],
        'hibrit_port_sampling_basis': (
            (m.get('motor_geometry') or {}).get('port_history') or {}
        ).get('sampling', {}).get('basis'),
        'hibrit_dry_mass_basis': m['design_summary']['key_dimensions']['dry_mass_basis'],
        'hibrit_l_star_note': m.get('l_star_note'),
        'kati_thrust_basis': kati['thrust_curve']['basis'],
        'kati_sampling_basis': kati['thrust_curve']['sampling']['basis'],
        'kati_iki_faz': kati['two_phase_loss']['two_phase_correction_status_basis'],
    }


def koken_olc(istemci):
    """DV-MIXED: iki uç, dört hâl (karma / hepsi CoolProp / bileşim üç dal)."""
    out = {}
    for ad, (tip, isim) in {'n2o_karma': ('oxidizer', 'n2o'),
                            'lox_coolprop': ('oxidizer', 'lox')}.items():
        r = istemci.post('/api/get-propellant-properties',
                         json={'propellant_type': tip, 'propellant_name': isim},
                         headers=UC_BASLIGI)
        j = r.get_json() or {}
        p = j.get('properties') or {}
        out[ad] = {'status': r.status_code, 'source': j.get('source'),
                   'data_source': p.get('data_source'),
                   'provenance': p.get('provenance'),
                   'provenance_basis_en': p.get('provenance_basis_en')}
    for ad, bilesim in {
            'bilesim_karma': [{'formula': 'C2H4', 'percentage': 50},
                              {'formula': 'C4H6', 'percentage': 50}],
            'bilesim_formul': [{'formula': 'C4H6', 'percentage': 100}],
            'bilesim_cea': [{'formula': 'C2H4', 'percentage': 100}]}.items():
        r = istemci.post('/api/validate-fuel', json={'composition': bilesim},
                         headers=UC_BASLIGI)
        j = r.get_json() or {}
        out[ad] = {'status': r.status_code, 'source': j.get('source'),
                   'provenance': j.get('provenance'),
                   'provenance_basis_en': j.get('provenance_basis_en')}
    return out


def capa_sayimi(kok):
    """i18n_common.js'te bu kulvarın +k çapa arası anahtar sayısı (EN, TR)."""
    satirlar = (Path(kok) / 'hrma/static/js/i18n_common.js').read_text(
        encoding='utf-8').split('\n')
    ac = [i for i, s in enumerate(satirlar)
          if s.strip() == '// A1b dil-cozucu-nesri +k ↓']
    kp = [i for i, s in enumerate(satirlar)
          if s.strip() == '// A1b dil-cozucu-nesri +k ↑']
    if len(ac) != 2 or len(kp) != 2:
        return {'hata': {'ac': len(ac), 'kapa': len(kp)}}
    anahtar = re.compile(r"^\s*'([^']+)'\s*:")
    return {dil: [anahtar.match(s).group(1)
                  for s in satirlar[ac[i] + 1:kp[i]] if anahtar.match(s)]
            for i, dil in enumerate(('en', 'tr'))}


# ===========================================================================
# Fikstürler (modül kapsamı: uçlar bir kez koşar)
# ===========================================================================
@pytest.fixture(scope='module')
def istemci(tmp_path_factory):
    os.environ.setdefault('HRMA_PROJECTS_DIR',
                          str(tmp_path_factory.mktemp('dilb1_projeler')))
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def hibrit(istemci):
    durum, govde = uc_yaniti(istemci, '/calculate')
    assert durum == 200, govde
    return govde


@pytest.fixture(scope='module')
def kati(istemci):
    durum, govde = uc_yaniti(istemci, '/calculate_solid')
    assert durum == 200, govde
    return govde


@pytest.fixture(scope='module')
def tmp(tmp_path_factory):
    return tmp_path_factory.mktemp('dilb1_node')


def _tr_en(kok, tmp, server=(), chart=(), ad='c'):
    r = ceviri(kok, server=server, chart=chart, tmpdir=tmp, ad=ad)
    assert 'error' not in r, r.get('error')
    return r


# ===========================================================================
# DV36-02 — enjektör uyarı kutusu
# ===========================================================================
@node_gerek
def test_dv3602_uyari_kutusu_TR_satir_satir(hibrit, tmp):
    kutu = [t for t in figur_metinleri(hibrit)
            if t.startswith('<b>Solver warnings for this injector')]
    assert kutu, 'enjektör şemasında çözücü uyarı kutusu yok (örnek hibrit)'
    mesajlar = [w if isinstance(w, str) else (w.get('message') or w.get('code'))
                for w in hibrit['injector']['warnings']]
    r = _tr_en(ROOT, tmp, server=mesajlar, chart=kutu, ad='dv3602')
    tr = r['tr']['chart'][0]
    assert r['en']['chart'][0] == kutu[0], 'EN metin değişti'
    assert 'Solver warnings' not in tr and 'WARNING:' not in tr, tr
    satirlar = tr.split('<br>')
    assert satirlar[0].startswith('<b>Bu enjektör için çözücü uyarıları (')
    beklenen = ['- UYARI: ' + m for m in r['tr']['server']]
    assert satirlar[1:] == beklenen, (satirlar[1:], beklenen)
    # sayılar ekranda TR virgül (serverText kanonu)
    assert not re.search(r'\d\.\d', re.sub(r'<[^>]*>', '', tr)), tr


@node_gerek
def test_dv3602_taninmayan_duzey_ve_mesaj_aynen(tmp):
    satirlar = ['- NOTICE: L/D ratio (1.2) outside optimal range (3-5)',
                '- WARNING: a sentence the dictionary has never seen']
    r = _tr_en(ROOT, tmp, chart=satirlar, ad='dv3602b')
    assert r['tr']['chart'] == satirlar, r['tr']['chart']


# ===========================================================================
# DV36-03 — güvenlik dayanak cümleleri
# ===========================================================================
@pytest.fixture(scope='module')
def guvenlik(istemci):
    return guvenlik_cumleleri(istemci)


@node_gerek
def test_dv3603_dayanaklar_TR(guvenlik, tmp):
    cumleler = sorted({c for v in guvenlik.values()
                       for k in GUVENLIK_ALANLARI for c in v.get(k, [])})
    assert len(cumleler) >= 12, cumleler
    r = _tr_en(ROOT, tmp, server=cumleler, ad='dv3603')
    assert r['en']['server'] == cumleler
    kalan = [(c, t) for c, t in zip(cumleler, r['tr']['server'])
             if c == t or any(i in t for i in INGILIZCE_ISARET['guvenlik'])]
    assert not kalan, kalan
    # hibrit varsayılan oksitleyici cümlesindeki sayılar TR virgül
    varsayim = [t for c, t in zip(cumleler, r['tr']['server'])
                if 'names no hybrid oxidiser' in c]
    assert varsayim and all(re.search(r'\d,\d{3}', t) for t in varsayim)
    assert not any(re.search(r'\b0\.\d', t) for t in varsayim), varsayim


@node_gerek
def test_dv3603_taninmayan_tane_notu_ve_govde_aynen(tmp):
    cumleler = [
        "propellant_type 'n2o_xyz' is not a tabulated class; the hybrid oxidiser "
        "'n2o' was read from it and selected the 'hybrid_n2o' class. The "
        "equivalence is derived from the oxidiser decomposition enthalpy "
        "(Karabeyoglu, Dyer, Stevens & Cantwell, AIAA 2008-4933, eq. 2), not "
        "from a liquid-bipropellant table: a grain note the table does not know.",
        "The value sent in propellant_type ('zz') is not one of the propellant "
        "classes HRMA has a toxic inventory rule for and no tabulated component "
        "name was found in it, so the class below was taken from motor_type "
        "('solid'), NOT from what you typed. A body sentence nobody translated.",
    ]
    r = _tr_en(ROOT, tmp, server=cumleler, ad='dv3603b')
    assert r['tr']['server'] == cumleler, r['tr']['server']


# ===========================================================================
# DV-GT21 + DV36-22 — çözücü nesri
# ===========================================================================
@node_gerek
def test_gt21_itki_egrisi_ornekleme_kuru_kutle_TR(hibrit, kati, tmp):
    n = nesir_cumleleri(hibrit, kati)
    anahtarlar = ['hibrit_thrust_basis', 'hibrit_sampling_basis',
                  'hibrit_dry_mass_basis', 'kati_thrust_basis',
                  'kati_sampling_basis']
    if n['hibrit_port_sampling_basis']:
        anahtarlar.append('hibrit_port_sampling_basis')
    cumleler = [n[k] for k in anahtarlar]
    r = _tr_en(ROOT, tmp, server=cumleler, ad='gt21')
    assert r['en']['server'] == cumleler
    for k, c, t in zip(anahtarlar, cumleler, r['tr']['server']):
        assert c != t, '%s çevrilmedi: %s' % (k, c[:120])
        assert not any(i in t for i in INGILIZCE_ISARET['gt21']), (k, t)


@node_gerek
def test_gt21_ornekleme_bilinmeyen_liste_aynen(tmp):
    c = ('The solver time step is UNCHANGED; only the published array is thinned. '
         'Thinning keeps, in every bucket, the samples of largest and smallest '
         'thrust (so the peak and the envelope survive) plus the first and last '
         'sample, the peak-pressure sample, and a list nobody tabulated. Every '
         'derived quantity in this response (total impulse, average thrust, curve '
         'shape, stability, warnings) is computed from the FULL-resolution '
         'solution, not from this array.')
    r = _tr_en(ROOT, tmp, server=[c], ad='gt21b')
    assert r['tr']['server'] == [c]


@node_gerek
def test_gt21_iki_faz_bes_dal_TR(kati, tmp):
    dallar = iki_faz_cumleleri()
    # ürün yanıtının kendi künyesi de dallardan biri (pencere dışı, KNDX)
    assert kati['two_phase_loss']['two_phase_correction_status_basis'] \
        == dallar['pencere_disi']
    adlar = sorted(dallar)
    r = _tr_en(ROOT, tmp, server=[dallar[a] for a in adlar], ad='ikifaz')
    assert r['en']['server'] == [dallar[a] for a in adlar]
    tr = dict(zip(adlar, r['tr']['server']))
    for a in adlar:
        assert tr[a] != dallar[a], a
        assert not any(i in tr[a] for i in INGILIZCE_ISARET['iki_faz']), (a, tr[a])
    assert 'X_p = 0,440' in tr['pencere_disi']
    assert '(0-0,4 (NASA SP-8039' in tr['pencere_disi'], 'pencere künyesi'
    assert 'eta_2phase = 1 - 0,12*X_p' in tr['uygulanmadi']
    assert 'eta = 0,950000' in tr['kullanici']
    # makine künyesi (alan = değer) nokta kalır
    assert 'two_phase_efficiency_applied = 1.0' in tr['uygulanmadi']


@node_gerek
def test_gt21_iki_faz_bilinmeyen_bas_aynen(tmp):
    dal = iki_faz_cumleleri()['uygulanmadi']
    bozuk = 'An unknown head sentence. ' + dal.split('. ', 1)[1]
    r = _tr_en(ROOT, tmp, server=[bozuk], ad='ikifazb')
    assert r['tr']['server'] == [bozuk]


@node_gerek
def test_dv3622_l_star_notu_TR_virgul(hibrit, tmp):
    not_ = hibrit['motor'].get('l_star_note')
    assert not_, 'örnek hibritte l_star_note boş (ölçüm önkoşulu)'
    r = _tr_en(ROOT, tmp, server=[not_], ad='lstar')
    tr = r['tr']['server'][0]
    assert tr.startswith('İstenen L* = ') and not re.search(r'\d\.\d', tr), tr
    assert r['en']['server'][0] == not_


# ===========================================================================
# DV36-21 — G-1 tarama işareti
# ===========================================================================
@node_gerek
def test_dv3621_g1_hover_ve_not_TR(hibrit, tmp):
    metin = [t for t in figur_metinleri(hibrit)
             if 'Sweep maximum (grid node' in t or 'is a grid node of a' in t
             or t.startswith('This run<br>')]
    assert len(metin) >= 3, metin
    r = _tr_en(ROOT, tmp, chart=metin, ad='g1')
    assert r['en']['chart'] == metin
    for c, t in zip(metin, r['tr']['chart']):
        for ing in ('Sweep maximum', 'grid node', 'Sea-level exit', 'Band ',
                    'step ', 'This run', '(solver)'):
            assert ing not in t, (ing, t)
    hover = [t for t in r['tr']['chart'] if 'Tarama azamisi (ızgara' in t]
    assert hover and re.search(r'Bant \d+,\d\d-\d+,\d\d, adım \d+,\d+', hover[0]), hover


# ===========================================================================
# DV36-16 — figür metni TR ondalık
# ===========================================================================
@node_gerek
def test_dv3616_final_port_TR_virgul(kati, tmp):
    gercek = [t for t in figur_metinleri(kati) if t.startswith('Final port ')]
    assert gercek, 'katı kesitte Final port etiketi yok'
    metin = gercek + ['Final port Ø99.8 mm (web fully consumed)',
                      'End-of-burn port: Ø75.0 mm<extra></extra>']
    r = _tr_en(ROOT, tmp, chart=metin, ad='port')
    assert r['en']['chart'] == metin
    for t in r['tr']['chart']:
        assert not re.search(r'Ø\d+\.\d', t), t
    assert r['tr']['chart'][-2] == 'Son port Ø99,8 mm (web tamamen tükendi)'


# ===========================================================================
# DV-MIXED — köken yapısal kodu
# ===========================================================================
@pytest.fixture(scope='module')
def koken(istemci):
    return koken_olc(istemci)


def test_dvmixed_uc_yapisal_kod(koken):
    k = koken['n2o_karma']
    assert k['status'] == 200
    assert k['provenance'] == 'mixed'
    # İngilizce cümle ve rozet dizesi DEĞİŞMEDİ
    assert k['provenance_basis_en'] == k['data_source'] == k['source'] \
        == 'Mixed provenance (see property_sources)'
    assert koken['lox_coolprop']['provenance'] is None, 'tek kaynaklıda kod uyduruldu'
    assert koken['bilesim_karma']['provenance'] == 'mixed'
    assert koken['bilesim_formul']['provenance'] == 'formula_derived'
    assert koken['bilesim_cea']['provenance'] == 'cea_species_table'
    for ad in ('bilesim_karma', 'bilesim_formul', 'bilesim_cea'):
        assert koken[ad]['provenance_basis_en'] == koken[ad]['source'], ad


@node_gerek
def test_dvmixed_istemci_eslemesi_TR(koken, tmp):
    cumleler = [koken[a]['source'] for a in
                ('n2o_karma', 'bilesim_karma', 'bilesim_formul', 'bilesim_cea')]
    r = _tr_en(ROOT, tmp, server=cumleler, ad='koken')
    assert r['en']['server'] == cumleler
    for c, t in zip(cumleler, r['tr']['server']):
        assert c != t and 'provenance' not in t.replace('property_sources', ''), t
    assert r['tr']['server'][0] == 'Karma köken (bkz. property_sources)'


# ===========================================================================
# DV-LIQUID + CW-D4 — proje şeridi
# ===========================================================================
@pytest.fixture(scope='module')
def sivi(istemci):
    durum, bos = uc_yaniti(istemci, '/calculate_liquid')
    assert durum == 200
    durum2, dolu = uc_yaniti(istemci, '/calculate_liquid', max_burn_duration=60)
    assert durum2 == 200
    return {'sure_yok': bos, 'sure_60': dolu}


def proje_isi(sivi):
    return {
        'rozet': ['liquid', 'solid', 'hybrid', 'weird', None],
        'mini': {
            'sivi_neden': {'thrust_N': 25000.0, 'isp_s': 277.4,
                           'burn_time_source': 'not_supplied'},
            'sivi_eski_kayit': {'thrust_N': 25000.0, 'isp_s': 277.4},
            'sivi_it': {'thrust_N': 25000.0, 'total_impulse_Ns': 1500000.0},
        },
        'ozet': {
            'sivi_sure_yok': {'motorType': 'liquid',
                              'cr': sivi_ozet_girdisi(sivi['sure_yok'])},
            'sivi_sure_60': {'motorType': 'liquid',
                             'cr': sivi_ozet_girdisi(sivi['sure_60'])},
        },
        'strip': [{'name': 'a', 'motor_type': 'liquid', 'results_summary': {}},
                  {'name': 'b', 'motor_type': 'hybrid', 'results_summary': {}},
                  {'name': 'c', 'motor_type': 'weird', 'results_summary': {}}],
    }


@pytest.fixture(scope='module')
def proje(sivi, tmp):
    r = proje_olc(ROOT, proje_isi(sivi), tmpdir=tmp)
    assert 'error' not in r, r.get('error')
    return r


@node_gerek
def test_dvliquid_rozet_ve_serit_TR(proje):
    assert proje['tr']['rozet'] == {'liquid': 'SIVI', 'solid': 'KATI',
                                    'hybrid': 'HİBRİT', 'weird': 'WEIRD',
                                    'null': '?'}
    assert proje['en']['rozet'] == {'liquid': 'LIQUID', 'solid': 'SOLID',
                                    'hybrid': 'HYBRID', 'weird': 'WEIRD',
                                    'null': '?'}
    assert proje['tr']['serit'] == [' [SIVI]', ' [HİBRİT]', ' [WEIRD]']
    assert proje['en']['serit'] == [' [LIQUID]', ' [HYBRID]', ' [WEIRD]']


@node_gerek
def test_cwd4_sivi_ozeti_sayi_uydurmaz(proje, sivi):
    for dil in ('tr', 'en'):
        yok = proje[dil]['ozet']['sivi_sure_yok']
        assert 'total_impulse_Ns' not in yok
        assert yok['burn_time_source'] == 'not_supplied'
        dolu = proje[dil]['ozet']['sivi_sure_60']
        beklenen = sivi['sure_60']['openrocket']['motor_summary']['total_impulse']
        assert isinstance(beklenen, (int, float)) and dolu['total_impulse_Ns'] == beklenen
        assert 'burn_time_source' not in dolu


@node_gerek
def test_cwd4_serit_nedeni_basar_sayi_basmaz(proje):
    tr, en = proje['tr']['mini'], proje['en']['mini']
    assert tr['sivi_neden'].endswith('It: yanma süresi verilmedi'), tr
    assert en['sivi_neden'].endswith('It: burn time not supplied'), en
    assert 'It' not in tr['sivi_eski_kayit'], 'nedeni bilinmeyen yokluğa neden uyduruldu'
    assert 'It 1' in tr['sivi_it'] and 'verilmedi' not in tr['sivi_it']


def test_capa_arasi_EN_TR_esit_ve_kodda_kullaniliyor():
    s = capa_sayimi(ROOT)
    assert 'hata' not in s, s
    assert s['en'] == s['tr'] and len(s['en']) == 4, s
    kod = (ROOT / 'hrma/static/js/project_bar.js').read_text(encoding='utf-8')
    for k in s['en']:
        assert "'%s'" % k in kod, k
