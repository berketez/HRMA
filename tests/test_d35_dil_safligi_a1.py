# -*- coding: utf-8 -*-
"""ÖH D35 · dil-safligi (a1) bekçileri — 22 Eylül 2026.

Kapsanan kalemler (ölçüm: docs/scofield/raw/OH/D35/dil-safligi/a1/):
  OH-GT-19  besleme hattı / vana ``validity`` mesajları TR ekranda
            İngilizceydi, aynı cümle iki kez çıkıyordu ve hangi hatta ait
            olduğu YAZMIYORDU.
  OH-GT-20  /formulas'ın "ürün gerçekte ne koşuyor" kutularının (4 adet)
            EN ve TR sözlük kaydı HİÇ YOKTU.
  OH-GT-21  sunucunun gerekçe paragrafları (chug, hüküm künyesi, kütle
            tanımı) ``serverText``ten geçiyor ama karşılıkları yoktu.
  OH-GT-22  figür KATEGORİ ekseni çeviri boğazından hiç geçmiyordu; enjektör
            şeması anotasyonları sözlükte yoktu.
  OH-GT-23  i18n_common.js sayfaya ÇALIŞTIRMA ZAMANINDA enjekte edildiği
            için 6-DOF rozeti İngilizce fallback ile donuyordu.
  OH-GT-24  desen yakalamaları ondalık ayracı kanonundan geçmiyordu
            ("8.2%", "5.0 mm"); TR ipucu İngilizce düğme adı anıyordu.

Bekçiler DAVRANIŞ ölçer: Python tarafı modülü doğrudan çağırır, JS tarafı
gerçek dosyaları node'da Plotly/DOM taklidiyle koşturur.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates' / 'formulas.html'

NODE = shutil.which('node')
node_gerek = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

# Türkçeye çevrilmiş bir cümlede kalmaması gereken İngilizce sözcükler.
# Sembol/kısaltma (dP, F_L, p1, Cv, IEC, NOT_EVALUATED) BİLEREK dışarıda.
EN_SOZCUK = re.compile(
    r'\b(the|was|were|not|computed|because|supplied|liquid|critical|needs|'
    r'cavitation|flashing|screened|from|vapour|alone|only|choked|limit|'
    r'missing|water|hammer|coupling|produced|required|wave|speed|depends|'
    r'pipe|wall|elasticity|valve|sized|line|budget|leaves|usable|inlet|fix|'
    r'sizing|first|flow|regime|verified|without|cannot|below|uses|full|drop|'
    r'lower|bound|capacity|turns|fluid|label|substituted|tabulated|bulk|'
    r'modulus|propellant|acceptance|issued|injector|feed|system|solid|motor|'
    r'plate|safety|factor|target|given|stable|overstable|unstable)\b', re.I)


# ---------------------------------------------------------------------------
# node düzeneği
# ---------------------------------------------------------------------------
DUZENEK = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const ROOT = process.argv[2];
const JOB = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

function makeDoc(plotNodes) {
    const listeners = {};
    return {
        readyState: 'complete',
        documentElement: { setAttribute() {}, appendChild() {} },
        head: { appendChild() {} },
        body: { appendChild() {} },
        createElement: () => ({ setAttribute() {}, appendChild() {}, style: {} }),
        getElementById: () => null,
        querySelector: (s) => (String(s).indexOf('i18n_charts.js') >= 0 ? {} : null),
        querySelectorAll: (s) => (s === '.js-plotly-plot' ? plotNodes : []),
        addEventListener: (n, f) => { (listeners[n] = listeners[n] || []).push(f); },
        dispatchEvent: (ev) => { (listeners[ev.type] || []).forEach((f) => f(ev)); return true; },
    };
}

function boot(files) {
    const calls = [];
    const sandbox = {
        console, setTimeout, clearTimeout, setInterval, clearInterval,
        JSON, Object, Array, Math, RegExp, String, Number, Boolean, Date, Error,
        parseFloat, parseInt, isNaN, isFinite,
    };
    sandbox.window = sandbox;
    sandbox.self = sandbox;
    sandbox.document = makeDoc([]);
    sandbox.localStorage = null;
    sandbox.CustomEvent = function (t, i) { this.type = t; this.detail = (i && i.detail) || null; };
    sandbox.Plotly = {
        newPlot(el, data, layout) { calls.push({ data, layout }); },
        react(el, data, layout) { calls.push({ data, layout }); },
    };
    vm.createContext(sandbox);
    for (const f of files) {
        vm.runInContext(fs.readFileSync(ROOT + '/' + f, 'utf8'), sandbox, { filename: f });
    }
    return { sandbox, calls };
}

const out = {};

/* --- 1. serverText / chartText / figür çevirisi --- */
{
    const { sandbox, calls } = boot(['i18n.js', 'i18n_common.js',
                                     'i18n_charts.js', 'plotly_dark.js']);
    sandbox.I18N.setLang('tr');
    out.serverTr = (JOB.serverTexts || []).map((s) => sandbox.I18N.serverText(s));
    out.figureTr = (JOB.figures || []).map(function (f) {
        sandbox.Plotly.newPlot('d', f.data, f.layout);
        const c = calls[calls.length - 1];
        return { x: c.data[0].x, name: c.data[0].name,
                 annotations: (c.layout.annotations || []).map((a) => a.text) };
    });
    sandbox.I18N.setLang('en');
    out.serverEn = (JOB.serverTexts || []).map((s) => sandbox.I18N.serverText(s));
}

/* --- 2. GEÇ GELEN SÖZLÜK: 6-DOF paneli (OH-GT-23) --- */
{
    /* i18n_common.js BİLEREK yüklenmez: gerçek sayfada onu analysis_dock.js
       çalışma zamanında enjekte ediyor, yani panel ondan ÖNCE çizilebiliyor. */
    const { sandbox } = boot(['i18n.js', 'sixdof_panel.js']);
    sandbox.I18N.setLang('tr');
    out.gecSozluk = {
        oncesi: sandbox.I18N.t('sixdof.bandStable', 'STABLE'),
        kancaVar: typeof sandbox.SixDofPanel._sozlukGelinceCalistir === 'function',
        atesledi: false,
    };
    let atesledi = false;
    sandbox.SixDofPanel._sozlukGelinceCalistir(function () { atesledi = true; });
    /* sözlük ŞİMDİ gelir (analysis_dock.js'in enjeksiyonu) */
    vm.runInContext(fs.readFileSync(ROOT + '/i18n_common.js', 'utf8'),
                    sandbox, { filename: 'i18n_common.js' });
    setTimeout(function () {
        out.gecSozluk.atesledi = atesledi;
        out.gecSozluk.sonrasi = sandbox.I18N.t('sixdof.bandStable', 'STABLE');
        process.stdout.write(JSON.stringify(out));
    }, 250);
}
"""


@pytest.fixture(scope='module')
def duzenek(tmp_path_factory):
    yol = tmp_path_factory.mktemp('d35_dil') / 'duzenek.js'
    yol.write_text(DUZENEK, encoding='utf-8')
    return yol


def node_kos(duzenek_yolu, tmp_path, **is_sozlugu):
    is_yolu = tmp_path / 'is.json'
    is_yolu.write_text(json.dumps(is_sozlugu), encoding='utf-8')
    p = subprocess.run([NODE, str(duzenek_yolu), str(STATIC_JS), str(is_yolu)],
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, 'node düzeneği düştü:\n%s' % p.stderr[-2500:]
    assert p.stdout.strip(), 'node düzeneği çıktı üretmedi:\n%s' % p.stderr[-2500:]
    return json.loads(p.stdout)


def en_kalinti(metin):
    return sorted(set(m.group(0).lower() for m in EN_SOZCUK.finditer(metin or '')))


# ---------------------------------------------------------------------------
# OH-GT-19 — besleme hattı mesajları
# ---------------------------------------------------------------------------
HAT_GIRDISI = dict(
    mass_flow_kg_s=2.0, density_kg_m3=810.0, viscosity_Pa_s=1.6e-3,
    line_id_m=0.02, line_length_m=2.0, inlet_pressure_Pa=30e5,
    valve_pressure_drop_Pa=1.0e5)


def _cagir(**ek):
    from hrma.analysis.valve_feedline import analyze_valve_feedline
    yuk = dict(HAT_GIRDISI)
    yuk.update(ek)
    return analyze_valve_feedline(**yuk)


def test_gt19_hat_adi_verilmezse_mesaj_aynen_kalir():
    """FAIL-CLOSED: etiket verilmeyen çağrıda uydurma hat adı yazılmaz."""
    res = _cagir()
    for kayit in res['validity']:
        assert not str(kayit.get('message', '')).startswith('['), kayit


def test_gt19_hat_adi_verilince_her_mesaj_hangi_hat_oldugunu_soyler():
    res = _cagir(line_label='fuel line')
    assert res['validity'], 'bu girdide validity kaydı beklenir'
    for kayit in res['validity']:
        assert str(kayit['message']).startswith('[fuel line] '), kayit
    if res.get('valve'):
        for kayit in res['valve'].get('validity') or []:
            assert str(kayit['message']).startswith('[fuel line] '), kayit
        for m in res['valve'].get('warnings') or []:
            assert str(m).startswith('[fuel line] '), m


def test_gt19_iki_hat_ayni_cumleyi_artik_ayirt_ediyor():
    """ÖLÇÜLEN KUSUR: su koçu mesajı iki hattan da AYNEN geliyordu."""
    yakit = _cagir(line_label='fuel line')
    oks = _cagir(line_label='oxidizer line')
    y = [k['message'] for k in yakit['validity']]
    o = [k['message'] for k in oks['validity']]
    assert y and o
    assert not (set(y) & set(o)), (
        'iki hattın mesajları hâlâ birebir aynı: %s' % (set(y) & set(o)))


def test_gt19_hat_adi_sayilari_ve_alan_adlarini_degistirmiyor():
    """Ön ek YALNIZ metne girer: alan adı, status ve sayılar aynı kalır."""
    ham = _cagir()
    etiketli = _cagir(line_label='fuel line')
    assert [k['field'] for k in ham['validity']] == \
           [k['field'] for k in etiketli['validity']]
    assert [k['status'] for k in ham['validity']] == \
           [k['status'] for k in etiketli['validity']]
    assert ham['budget'] == etiketli['budget']


@node_gerek
def test_gt19_mesajlar_tr_ekranda_ingilizce_kalmiyor(duzenek, tmp_path):
    res = _cagir(line_label='fuel line')
    mesajlar = [k['message'] for k in res['validity']]
    assert mesajlar
    out = node_kos(duzenek, tmp_path, serverTexts=mesajlar)
    for kaynak, tr in zip(mesajlar, out['serverTr']):
        assert tr != kaynak, 'çevrilmedi: %s' % kaynak[:90]
        assert '[yakıt hattı] ' in tr, tr[:90]
        assert not en_kalinti(tr.split('] ', 1)[-1]), \
            'İngilizce kalıntı %s -> %s' % (en_kalinti(tr), tr[:120])


@node_gerek
def test_gt19_en_kipinde_mesaja_dokunulmuyor(duzenek, tmp_path):
    res = _cagir(line_label='fuel line')
    mesajlar = [k['message'] for k in res['validity']]
    out = node_kos(duzenek, tmp_path, serverTexts=mesajlar)
    assert out['serverEn'] == mesajlar


# ---------------------------------------------------------------------------
# OH-GT-20 — /formulas model notları
# ---------------------------------------------------------------------------
MODEL_NOTLARI = ('fx.s5_3.model_note', 'fx.s6_1.model_note',
                 'fx.s7_1.model_note', 'fx.s8_2.model_note',
                 'fx.s13_2.model_note')


def _formul_sozlugu(anahtar):
    kaynak = (STATIC_JS / 'i18n_formulas.js').read_text(encoding='utf-8')
    return [m.group(1) for m in re.finditer(
        r"'%s':\s*'((?:[^'\\]|\\.)*)'" % re.escape(anahtar), kaynak)]


def test_gt20_sablondaki_model_notlarinin_hepsi_bulundu():
    metin = SABLON.read_text(encoding='utf-8')
    bulunan = sorted(set(re.findall(r'data-i18n="(fx\.[\w.]*model_note)"', metin)))
    assert bulunan == sorted(MODEL_NOTLARI), bulunan


@pytest.mark.parametrize('anahtar', MODEL_NOTLARI)
def test_gt20_model_notu_iki_dilde_de_kayitli(anahtar):
    kayit = _formul_sozlugu(anahtar)
    assert len(kayit) == 2, (
        '%s sözlükte %d kez geçti (EN + TR beklenir); eksikse TR kullanıcı '
        'İngilizce okur' % (anahtar, len(kayit)))


@pytest.mark.parametrize('anahtar', MODEL_NOTLARI)
def test_gt20_tr_karsiligi_ingilizce_kopyasi_degil(anahtar):
    en, tr = _formul_sozlugu(anahtar)
    assert tr.strip(), anahtar
    assert tr.strip() != en.strip(), '%s: TR karşılık EN kopyası' % anahtar
    assert len(en_kalinti(tr)) <= 2, \
        '%s TR metninde İngilizce kalıntı: %s' % (anahtar, en_kalinti(tr))


@pytest.mark.parametrize('anahtar', MODEL_NOTLARI)
def test_gt20_tr_karsiliginda_turkce_harfler_korunmus(anahtar):
    tr = _formul_sozlugu(anahtar)[1]
    assert re.search(r'[çğıöşüÇĞİÖŞÜ]', tr), \
        '%s TR metninde hiç Türkçe harf yok (ASCII kaçışı)' % anahtar


# ---------------------------------------------------------------------------
# OH-GT-21 — sunucunun gerekçe paragrafları
# ---------------------------------------------------------------------------
GT21_PARAGRAFLAR = [
    # solid_rocket_engine.py chug_applicability.reason
    'A solid motor has no injector and no feed system, so the classical chug '
    'criterion (injector pressure drop ratio decoupling the feed from the '
    'chamber) has no counterpart here. No injector input is passed to the '
    'module: its chug report is NOT_EVALUATED by construction, not because '
    'data is missing. The solid-motor low-frequency counterpart (L* / '
    'bulk-mode instability) is NOT modelled.',
    # app.py:20605 verdict_basis
    'No acceptance is issued: the wall was sized by HRMA to meet the target '
    'safety factor, so the reported safety factor is that target read back '
    '(target x manufacturing allowance), not an independent verification. '
    'Supply the real wall_thickness (m) to obtain a verification. A '
    'remaining MARGINAL/UNSAFE status is a warning and is never suppressed.',
    # app.py:20910 vessel_status_basis
    'No acceptance is issued: no case thickness was supplied, so HRMA sized '
    'the wall itself from the hoop stress to meet the design safety factor. '
    'Checking that wall and reporting a pass is the design target read back, '
    "not an independent verification. Supply 'case_thickness' (mm) to obtain "
    'one. A remaining MARGINAL/FAIL status is a warning and is never '
    'suppressed.',
    # hybrid_rocket_engine.py key_dimensions.total_mass_basis
    'LOADED lift-off mass: dry mass + LOADED oxidizer (oxidizer_mass) + '
    'LOADED fuel grain (fuel_mass_loaded, which includes the unburnt sliver '
    'that flies as dead weight). The mass budget uses loaded values; the '
    'performance budget uses the consumed ones (fuel_mass, '
    'oxidizer_mass_consumed_kg) - same rule as oxidizer_mass_basis.',
    # utils/injector_design.py:1849 (sayı taşır -> MSG_PATTERNS)
    'Injector plate safety factor 1.22 is below the target 4.00: 5.42 mm '
    'required, 3.00 mm given (showerhead).',
]


@node_gerek
def test_gt21_gerekce_paragraflari_tr_ekranda_cevriliyor(duzenek, tmp_path):
    out = node_kos(duzenek, tmp_path, serverTexts=GT21_PARAGRAFLAR)
    for kaynak, tr in zip(GT21_PARAGRAFLAR, out['serverTr']):
        assert tr != kaynak, 'çevrilmedi: %s' % kaynak[:100]
        assert re.search(r'[çğıöşüÇĞİÖŞÜ]', tr), tr[:100]


@node_gerek
def test_gt21_enjektor_plakasi_uyarisinda_sayilar_korunuyor(duzenek, tmp_path):
    """Çeviri BİREBİR: dört sayı ve enjektör adı aynen kalır (ayraç TR)."""
    out = node_kos(duzenek, tmp_path, serverTexts=[GT21_PARAGRAFLAR[-1]])
    tr = out['serverTr'][0]
    for sayi in ('1,22', '4,00', '5,42', '3,00'):
        assert sayi in tr, '%s yok: %s' % (sayi, tr)
    assert 'showerhead' in tr, tr
    # Sayıların korunması TEK BAŞINA yetmez: şablon boşaltılsa da sayılar
    # kalırdı. Cümlenin kendisi de Türkçe olmalı (ters mutasyon M5).
    assert 'Enjektör plakası emniyet katsayısı' in tr, tr
    assert not en_kalinti(tr.replace('showerhead', '')), en_kalinti(tr)


@node_gerek
def test_gt21_en_kipinde_paragraflara_dokunulmuyor(duzenek, tmp_path):
    out = node_kos(duzenek, tmp_path, serverTexts=GT21_PARAGRAFLAR)
    assert out['serverEn'] == GT21_PARAGRAFLAR


# ---------------------------------------------------------------------------
# OH-GT-22 — figür kategori / gösterge / anotasyon
# ---------------------------------------------------------------------------
GT22_KATEGORILER = ['Total', 'Oxidizer', 'Fuel', 'Peak', 'Average', 'Burnout',
                    'Design Pc', 'Chamber', 'Throat', 'Exit', 'Tank Outlet',
                    'Main Valve', 'Filters (assumed K=10)', 'Feed Lines']
GT22_ANOTASYONLAR = ['injector plate', 'parallel axial jets', 'feed manifold',
                     'included angle 2θ', 'impingement point',
                     'flat spray fan', 'chamber side →', 'dP → jet velocity']


def _figur():
    return {'data': [{'type': 'bar', 'x': list(GT22_KATEGORILER),
                      'y': [1] * len(GT22_KATEGORILER),
                      'name': 'This run (solver)'}],
            'layout': {'annotations': [{'text': a} for a in GT22_ANOTASYONLAR]}}


@node_gerek
def test_gt22_kategori_ekseni_ve_gosterge_adi_cevriliyor(duzenek, tmp_path):
    out = node_kos(duzenek, tmp_path, figures=[_figur()])
    f = out['figureTr'][0]
    kalan = [a for a, b in zip(GT22_KATEGORILER, f['x']) if a == b]
    assert not kalan, 'kategori ekseni çevrilmedi: %s' % kalan
    assert f['name'] != 'This run (solver)', f['name']


@node_gerek
def test_gt22_enjektor_semasi_anotasyonlari_cevriliyor(duzenek, tmp_path):
    out = node_kos(duzenek, tmp_path, figures=[_figur()])
    f = out['figureTr'][0]
    kalan = [a for a, b in zip(GT22_ANOTASYONLAR, f['annotations']) if a == b]
    assert not kalan, 'anotasyon çevrilmedi: %s' % kalan


@node_gerek
def test_gt22_sayisal_eksene_dokunulmuyor(duzenek, tmp_path):
    """FAIL-CLOSED: dize olmayan eksen kategori ekseni sanılmamalı."""
    fig = {'data': [{'type': 'scatter', 'x': [0, 1, 2], 'y': [3, 4, 5],
                     'name': 'Thrust'}], 'layout': {}}
    out = node_kos(duzenek, tmp_path, figures=[fig])
    assert out['figureTr'][0]['x'] == [0, 1, 2]


@node_gerek
def test_gt22_karisik_eksen_bozulmuyor(duzenek, tmp_path):
    fig = {'data': [{'type': 'bar', 'x': ['Total', 2], 'y': [1, 2],
                     'name': 'x'}], 'layout': {}}
    out = node_kos(duzenek, tmp_path, figures=[fig])
    assert out['figureTr'][0]['x'] == ['Total', 2]


# ---------------------------------------------------------------------------
# OH-GT-23 — geç gelen sözlük
# ---------------------------------------------------------------------------
@node_gerek
def test_gt23_gec_gelen_sozluk_paneli_tazeliyor(duzenek, tmp_path):
    out = node_kos(duzenek, tmp_path)
    g = out['gecSozluk']
    assert g['kancaVar'], 'sixdof_panel.js geç sözlük kancasını dışa vermiyor'
    assert g['oncesi'] == 'STABLE', (
        'ölçüm geçersiz: sözlük zaten yüklüymüş (%s)' % g['oncesi'])
    assert g['sonrasi'] != 'STABLE', g['sonrasi']
    assert g['atesledi'], (
        'sözlük geldiği hâlde panel tazelenmedi: rozet İngilizce donar')


def test_gt23_gec_sozluk_kancasi_inite_bagli():
    """Kanca çalışıyor olması yetmez: ``init`` onu TAKMALI.

    Bu tek kalem kaynak düzeyinde ölçülür (davranış değil): panelin
    ``init``i 1900 satırlık bir DOM ağacı (40+ giriş alanı, tablo gövdesi,
    dosya seçici) bekler; onu node'da kurmak bu bekçinin kapsamını kendi
    ölçtüğü kusurdan büyük yapardı. Kancanın KENDİ davranışı bir üstteki
    testte gerçek dosyalarla ölçülüyor; burada yalnız bağlantı kilitleniyor.
    """
    kaynak = (STATIC_JS / 'sixdof_panel.js').read_text(encoding='utf-8')
    i = kaynak.index('\n    function init(')
    govde = kaynak[i:kaynak.index('\n    window.SixDofPanel', i)]
    assert 'sozlukGelinceCalistir(' in govde, (
        'init() geç gelen sözlük kancasını takmıyor: sözlük panelden sonra '
        'gelirse rozet İngilizce fallback ile donar')


def test_gt23_sixdof_bant_karsiliklari_turkce():
    kaynak = (STATIC_JS / 'i18n_common.js').read_text(encoding='utf-8')
    for anahtar in ('sixdof.bandStable', 'sixdof.bandSlightlyOver',
                    'sixdof.bandOverstable', 'sixdof.cgEstimated'):
        kayit = [m.group(1) for m in re.finditer(
            r"'%s':\s*'((?:[^'\\]|\\.)*)'" % re.escape(anahtar), kaynak)]
        assert len(kayit) == 2, (anahtar, len(kayit))
        assert re.search(r'[çğıöşüÇĞİÖŞÜA-Z]', kayit[1]), (anahtar, kayit[1])
        assert kayit[1] != kayit[0], anahtar


# ---------------------------------------------------------------------------
# OH-GT-24 — ondalık / yüzde kanonu + sözlük hijyeni
# ---------------------------------------------------------------------------
REGEN_UYARISI = (
    'THIN-WALL ENVELOPE: the flat-plate conduction resistance used here '
    'differs from the cylindrical solution by 8.2% at the throat '
    '(wall_thickness 5.0 mm vs throat radius 27.4 mm); the published '
    'hot-wall temperature is biased HIGH by that order. Model note assumes '
    't_w << r_wall.')


@node_gerek
def test_gt24d_desen_yakalamalari_ondalik_kanonundan_geciyor(duzenek, tmp_path):
    out = node_kos(duzenek, tmp_path, serverTexts=[REGEN_UYARISI])
    tr = out['serverTr'][0]
    assert tr != REGEN_UYARISI, 'ince cidar uyarısı çevrilmedi'
    assert '%8,2' in tr, 'yüzde TDK yazımına ve virgüle geçmedi: %s' % tr
    assert '5,0 mm' in tr and '27,4 mm' in tr, tr
    assert not re.search(r'\d\.\d', tr), 'noktalı sayı kaldı: %s' % tr


@node_gerek
def test_gt24d_en_kipinde_sayiya_dokunulmuyor(duzenek, tmp_path):
    out = node_kos(duzenek, tmp_path, serverTexts=[REGEN_UYARISI])
    assert out['serverEn'][0] == REGEN_UYARISI


@node_gerek
def test_gt24d_tanimadigi_yakalama_degistirilmiyor(duzenek, tmp_path):
    """FAIL-CLOSED: sürüm/tarih gibi sayı BENZERİ yakalama bozulmamalı."""
    metin = 'Project document is 2.6.27 bytes; limit is 1048576 bytes (1 MB)'
    out = node_kos(duzenek, tmp_path, serverTexts=[metin])
    assert '2.6.27' in out['serverTr'][0], out['serverTr'][0]


@node_gerek
def test_gt24d_islev_sablonlu_kural_hala_kosuyor(duzenek, tmp_path):
    """Desen tablosunda şablon DİZE olmayan kurallar da var.

    `applyPatterns` eskiden bu dalı `text.replace(re, rules[i][1])` ile
    doğrudan JS'e veriyordu; ondalık kanonu eklenirken şablonun dize
    olduğu varsayılırsa bu kurallar `replace is not a function` ile
    PATLAR (ölçüldü: test_i18n_charts kapsam bekçisi kırmızıya döndü).
    Kavitasyon kuralı kendi değiştirici işlevini taşır.
    """
    metin = ('Cavitation risk: Nurick cavitation number K_c = 1.35 < 1.80 '
             '(injector inlet P_1 = 50.00 bar, dP = 12.00 bar, '
             'P_v = 44.00 bar at 293.00 K)')
    out = node_kos(duzenek, tmp_path, serverTexts=[metin])
    tr = out['serverTr'][0]
    assert tr != metin, 'işlev şablonlu kural koşmadı'
    assert re.search(r'[çğıöşüÇĞİÖŞÜ]', tr), tr


def test_gt24a_tr_ipucu_ingilizce_dugme_adi_anmiyor():
    kaynak = (STATIC_JS / 'i18n_advanced.js').read_text(encoding='utf-8')
    tr_blok = kaynak[kaynak.index("\n        tr: {"):]
    assert 'Find Optimum' not in tr_blok, (
        'TR sözlüğü hâlâ İngilizce düğme adını anıyor; ekranda o düğmenin '
        'yazısı "Optimumu Bul"dur')
    assert tr_blok.count('"Optimumu Bul"u kullanın') == 3
