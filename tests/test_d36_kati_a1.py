"""ÖH D36 · onemli2-kati (a1) — katı sayfası beyan/gösterim bekçileri.

Kalemler ve ölçümleri: ``docs/scofield/raw/OH/D36/onemli2-kati/a1/rapor.md``
(``once.json`` / ``ui_once.json`` = bb7ee57c, 23 Eylül 2026, KNDX örneği, TR,
1440x900; ``sonra.json`` / ``ui_sonra.json`` = bu dal).

* **E-2** — iki-faz düzeltme durumu ALANIN YANINDA: ``twoPhaseFieldStatusHTML``
  enum'u sözlükten adına çevirir (bilinmeyen enum adıyla, durum yoksa
  "yayımlamadı"), X_p ve uygulanan verimi çözücünün kendi alanlarından okur
  (alan yoksa satır çizilmez), künyeyi çevirmeden taşır.
* **case_geometry / head_geometry** — Motor Tasarımı tablosunda "Cidar" ve
  "Kapak" satırları; alan yoksa satır YOK, kaynak adı bilinmiyorsa ad aynen.
* **grain_gap_mm** — ``grain_design`` artık boşluğu ve kaynağını yayımlıyor;
  STEP segment planı boşluğu görüyor (``stack = N·L + (N-1)·gap``).
* **TR ondalık** — ``tpSatir`` / ``hrmaSigStr`` ayracı kanondan alır, Plotly
  ``separators`` kanondan türetilir, SVG öznitelikleri YERELLEŞMEZ
  (ölçüldü: ``r="24,00"`` 4 konsol hatası).
* **OH-P-15** — seçici "…" ile kısalır, tam metin title'da.

Bekçiler kaynağı DOSYADAN okur (inspect.getsource yok); JS gövdeleri node
içinde koşturulur. Ters-mutasyonlar: aynı dizindeki ``mutasyon.md``.
"""
import contextlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

# V301/T-ÇAPA-A: katı örnek motor geometrisi tek tanımdan (çekirdek
# 30 -> 48 mm). Eski Ø100/500/30 @ 40 bar BATES portu boğuluyordu
# (A_p/A_t 0,947) ve K-A port kapısından 422 alıyor; bu dosyadaki
# düğümlerin konusu boğulan port değil (K-A RAPOR §6, kural 1).
from hrma.engines.solid_rocket_engine import SOLID_DEFAULT_GEOMETRY_MM  # noqa: E402
_CEKIRDEK_MM = SOLID_DEFAULT_GEOMETRY_MM['core_diameter']


KOK = pathlib.Path(__file__).resolve().parents[1]
SOLID = KOK / 'hrma' / 'templates' / 'solid.html'
ENGINE = KOK / 'hrma' / 'engines' / 'solid_rocket_engine.py'
COMMON = KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js'

node_gerekli = pytest.mark.skipif(shutil.which('node') is None,
                                  reason='node yok')

HELPERS_BEGIN = '>>> HRMA-HONEST-FORMATTERS-BEGIN <<<'
HELPERS_END = '>>> HRMA-HONEST-FORMATTERS-END <<<'
PREVIEW_MARKERS = ('// >>> SOLID_GRAIN_PREVIEW_START',
                   '// <<< SOLID_GRAIN_PREVIEW_END')


def _html():
    return SOLID.read_text(encoding='utf-8')


def _fn(html, name):
    """``function name(`` gövdesini söker (8 boşluk girintili üst düzey)."""
    for marker in ('\n        function %s(' % name,
                   '\n        async function %s(' % name):
        start = html.find(marker)
        if start >= 0:
            break
    assert start >= 0, '%s fonksiyonu solid.html içinde yok' % name
    end = html.find('\n        }\n', start)
    assert end > start, '%s kapanışı bulunamadı' % name
    # Sonda satır sonu: parçalar art arda eklenince yorum satırı bir sonraki
    # fonksiyon başlığını yutmasın (ölçüldü: helpers bloğu '// ' ile bitiyor).
    return html[start + 1:end + len('\n        }')] + '\n'


def _helpers(html):
    a = html.index(HELPERS_BEGIN) + len(HELPERS_BEGIN)
    b = html.index(HELPERS_END)
    return html[a:b] + '\n'


def _blok(html, start, end):
    a = html.index(start) + len(start)
    return html[a:html.index(end)]


def _node(script):
    fd, path = tempfile.mkstemp(suffix='.js')
    os.write(fd, script.encode('utf-8'))
    os.close(fd)
    try:
        return subprocess.run(['node', path], capture_output=True, text=True,
                              timeout=60)
    finally:
        os.unlink(path)


def _node_json(script):
    proc = _node(script)
    assert proc.returncode == 0, 'node hatası:\n%s\n%s' % (proc.stdout,
                                                           proc.stderr)
    return json.loads(proc.stdout.strip().splitlines()[-1])


#: TR sözlük taklidi: ayraç virgül; T/TF İngilizce yedeği döndürür (metin
#: sözlüğün işi, burada ayraç ve yapı sınanır). TF sayıyı kanon gibi
#: yerelleştirir.
STUB_TR = r"""
const T = (k, en) => en;
const TF = (k, vars, en) => String(en).replace(/\{(\w+)\}/g, (w, n) =>
    (vars && Object.prototype.hasOwnProperty.call(vars, n))
        ? (typeof vars[n] === 'number' ? String(vars[n]).replace('.', ',') : vars[n]) : w);
const window = { I18N: {
    number: (v, d) => ((typeof v === 'number' && isFinite(v))
        ? (d === undefined ? String(v) : v.toFixed(d)) : String(v)).replace('.', ','),
    decimalText: (t) => (/^[+-]?\d+\.\d+(?:[eE][+-]?\d+)?$/.test(t) ? t.replace('.', ',') : t),
    percent: (v, d) => '%' + v.toFixed(d).replace('.', ','),
    unit: (v, u, d) => v.toFixed(d).replace('.', ',') + ' ' + u
} };
"""
STUB_EN = r"""
const T = (k, en) => en;
const TF = (k, vars, en) => String(en).replace(/\{(\w+)\}/g, (w, n) =>
    (vars && Object.prototype.hasOwnProperty.call(vars, n)) ? vars[n] : w);
const window = { I18N: {
    number: (v, d) => (typeof v === 'number' && isFinite(v))
        ? (d === undefined ? String(v) : v.toFixed(d)) : String(v),
    decimalText: (t) => t,
    percent: (v, d) => v.toFixed(d) + '%',
    unit: (v, u, d) => v.toFixed(d) + ' ' + u
} };
"""


def _iki_faz_parcalari(html):
    return '\n'.join([_helpers(html), _fn(html, 'tpKacis'),
                      _fn(html, 'twoPhaseStatusLabel'),
                      _fn(html, 'twoPhaseFieldStatusHTML')])


def _sonuc(durum=None, xp=0.44, eta=1.0, verified=False,
           kunye='X_p = 0.440 lies OUTSIDE the published data window'):
    tva = {}
    if durum is not None:
        tva['two_phase_correction_status'] = durum
        tva['two_phase_correction_verified'] = verified
        tva['two_phase_correction_status_basis'] = kunye
    if eta is not None:
        tva['two_phase_efficiency_applied'] = eta
    r = {'isp_sea_level': 125.4,
         'detailed_analysis': {'performance_metrics': {
             'theoretical_vs_actual_isp': tva}},
         'two_phase_loss': {}}
    if xp is not None:
        r['two_phase_loss']['inputs_used'] = {'condensed_mass_fraction': xp}
    return r


# ---------------------------------------------------------------------------
# E-2 — iki-faz beyanı alanın yanında
# ---------------------------------------------------------------------------
@node_gerekli
def test_e2_durum_enumu_adina_cevrilir_bilinmeyen_adiyla_basilir():
    from hrma.engines.solid_rocket_engine import (
        TWO_PHASE_STATUS_NOT_APPLIED, TWO_PHASE_STATUS_NO_FRACTION,
        TWO_PHASE_STATUS_OUT_OF_ENVELOPE, TWO_PHASE_STATUS_USER,
        TWO_PHASE_STATUS_ZERO)
    html = _html()
    enumlar = [TWO_PHASE_STATUS_USER, TWO_PHASE_STATUS_NO_FRACTION,
               TWO_PHASE_STATUS_ZERO, TWO_PHASE_STATUS_OUT_OF_ENVELOPE,
               TWO_PHASE_STATUS_NOT_APPLIED]
    govde = STUB_TR + _iki_faz_parcalari(html) + """
const out = {};
%s.forEach(function (d) { out[d] = twoPhaseFieldStatusHTML(%s); });
out.bilinmeyen = twoPhaseFieldStatusHTML(%s);
out.yok = twoPhaseFieldStatusHTML(%s);
out.isp_yok = twoPhaseFieldStatusHTML({two_phase_loss: {}});
console.log(JSON.stringify(out));
""" % (json.dumps(enumlar),
       json.dumps(_sonuc('__D__')).replace('"__D__"', 'd'),
       json.dumps(_sonuc('weird_enum_from_future')),
       json.dumps(_sonuc(None)))
    out = _node_json(govde)
    for d in enumlar:
        assert 'data-two-phase-field-status="%s"' % d in out[d], d
        assert 'unknown status' not in out[d], (
            '%s sözlükte adına çevrilmemiş' % d)
    assert 'data-two-phase-field-status="weird_enum_from_future"' in out['bilinmeyen']
    assert 'unknown status: weird_enum_from_future' in out['bilinmeyen'], (
        'bilinmeyen enum ADIYLA basılmalı (hüküm uydurulmaz)')
    assert 'data-two-phase-field-status="missing"' in out['yok']
    assert 'did not publish' in out['yok'], 'durum yoksa fail-closed beyan'
    assert out['isp_yok'] == '', 'hesap yoksa blok çizilmez'


@node_gerekli
def test_e2_xp_ve_verim_cozucuden_okunur_yoksa_satir_cizilmez():
    from hrma.engines.solid_rocket_engine import TWO_PHASE_STATUS_OUT_OF_ENVELOPE
    html = _html()
    govde = STUB_TR + _iki_faz_parcalari(html) + """
console.log(JSON.stringify({
  tam: twoPhaseFieldStatusHTML(%s),
  xp_yok: twoPhaseFieldStatusHTML(%s),
  eta_yok: twoPhaseFieldStatusHTML(%s),
  kullanici: twoPhaseFieldStatusHTML(%s)
}));
""" % (json.dumps(_sonuc(TWO_PHASE_STATUS_OUT_OF_ENVELOPE)),
       json.dumps(_sonuc(TWO_PHASE_STATUS_OUT_OF_ENVELOPE, xp=None)),
       json.dumps(_sonuc(TWO_PHASE_STATUS_OUT_OF_ENVELOPE, eta=None)),
       json.dumps(_sonuc('user_supplied_unvalidated', eta=0.98)))
    out = _node_json(govde)
    tam = out['tam']
    assert 'X_p' in tam and '0,440' in tam, 'X_p TR ayraçla basılmalı'
    assert '1,000' in tam and 'NO two-phase correction' in tam, (
        'η = 1,0 uygulandığı AÇIKÇA yazılmalı')
    assert 'X_p = 0.440 lies OUTSIDE' in tam, 'künye çevrilmeden taşınmalı'
    assert 'solver basis' in tam
    # Künye KATLANMIŞ: açık İngilizce paragraf alanın yanında tekrar edilmez.
    assert re.search(r'<details data-hd-declaration="two_phase_correction_status_basis"'
                     r'[^>]*><summary[^>]*><em>solver basis', tam), tam
    assert tam.index('<details') < tam.index('X_p = 0.440 lies OUTSIDE')
    assert 'mass fraction X_p' not in out['xp_yok'], (
        'X_p yoksa satır çizilmez (sayı uydurulmaz)')
    assert 'not published by the solver' in out['eta_yok']
    assert '0,980' in out['kullanici'] and 'NO two-phase correction' not in out['kullanici']


def test_e2_beyan_alanin_hemen_yanina_basiliyor():
    html = _html()
    assert 'renderTwoPhaseFieldStatus(results);' in html, (
        'E-2 beyanı displayResults içinde çağrılmıyor (alanın yanı boş kalır)')
    i_cagri = html.index('renderTwoPhaseFieldStatus(results);')
    i_tablo = html.index('populateMotorDesignTable(results);')
    assert i_cagri < i_tablo, 'beyan displayResults içinde çizilmeli'
    govde = _fn(html, 'renderTwoPhaseFieldStatus')
    assert "getElementById('two_phase_loss')" in govde
    assert "insertAdjacentHTML('afterend'" in govde, (
        'beyan alanın hemen yanına (afterend) basılmalı')
    assert '[data-two-phase-field-status]' in govde, 'yeniden çizimde eski blok sökülmeli'


def test_e2_sozluk_iki_dilde_ve_anahtarlar_literal():
    from hrma.engines.solid_rocket_engine import (
        TWO_PHASE_STATUS_NOT_APPLIED, TWO_PHASE_STATUS_NO_FRACTION,
        TWO_PHASE_STATUS_OUT_OF_ENVELOPE, TWO_PHASE_STATUS_USER,
        TWO_PHASE_STATUS_ZERO)
    html = _html()
    sozluk = COMMON.read_text(encoding='utf-8')
    for d in (TWO_PHASE_STATUS_USER, TWO_PHASE_STATUS_NO_FRACTION,
              TWO_PHASE_STATUS_ZERO, TWO_PHASE_STATUS_OUT_OF_ENVELOPE,
              TWO_PHASE_STATUS_NOT_APPLIED):
        anahtar = "'solidtp.status.%s'" % d
        assert sozluk.count(anahtar + ':') == 2, (
            '%s EN ve TR sözlüklerinde birer kez olmalı' % anahtar)
        assert anahtar in html, (
            '%s solid.html içinde LİTERAL yazılmalı (şablon taraması)' % anahtar)
    for k in ('solidtp.status.unknown', 'solidtp.status.missing',
              'solidtp.xp', 'solidtp.eta_applied', 'solidtp.eta_one',
              'solidtp.eta_missing', 'solidtp.basis',
              'solidtp.field_blank_ok'):
        assert sozluk.count("'%s':" % k) == 2, k
        assert "'%s'" % k in html, k


def test_ortak_sozluk_kanali_yazim_hatasina_karsi_korunur():
    """``ortakMetin`` kanalı: sayfa sözlüğü bekçisi (test_i18n_pages) bu
    anahtarları görmez, çünkü ORTAK sözlüktedirler. Yazım hatası koruması
    burada: şablonda ``ortakMetin('k'`` ile geçen HER anahtar i18n_common.js
    EN ve TR bloklarında birer kez tanımlı, hiçbiri sayfa sözlüğünde değil,
    ve solidtp./solidgeo. anahtarları T()/TF() ile doğrudan çağrılmıyor."""
    html = _html()
    sozluk = COMMON.read_text(encoding='utf-8')
    sayfa = (KOK / 'hrma' / 'static' / 'js' / 'i18n_pages.js').read_text(
        encoding='utf-8')
    anahtarlar = set(re.findall(r"\bortakMetin\('([\w.]+)'", html))
    assert len(anahtarlar) >= 25, sorted(anahtarlar)
    for k in sorted(anahtarlar):
        assert sozluk.count("'%s':" % k) == 2, (
            '%s i18n_common.js EN ve TR bloklarında birer kez olmalı' % k)
        assert "'%s':" % k not in sayfa, '%s sayfa sözlüğüne sızmış' % k
    dogrudan = re.findall(r"\bTF?\('(solid(?:tp|geo)\.[\w.]+)'", html)
    assert not dogrudan, (
        'ortak sözlük anahtarı sayfa T()/TF() kanalından çağrılıyor: %s'
        % dogrudan)
    # Yer tutucular EN ve TR değerlerinde aynı (TF boşluk bırakmasın).
    for k in sorted(anahtarlar):
        degerler = re.findall(r"'%s':\s*'((?:[^'\\]|\\.)*)'" % re.escape(k),
                              sozluk)
        assert len(degerler) == 2, k
        en, tr = (set(re.findall(r'\{(\w+)\}', d)) for d in degerler)
        assert en == tr, '%s yer tutucuları ayrışıyor: %s / %s' % (k, en, tr)


# ---------------------------------------------------------------------------
# case_geometry / head_geometry — Motor Tasarımı tablosu satırları
# ---------------------------------------------------------------------------
TABLO_STUB = r"""
let TBODY = { innerHTML: '' };
const document = {
    getElementById() { return null; },
    querySelector(sel) { return sel === '#solid_motor_table tbody' ? TBODY : null; },
    querySelectorAll() { return []; }
};
function satirlar() { return TBODY.innerHTML.split('<tr>').slice(1); }
"""
KATI_TABAN = {
    'throat_diameter': 18.4, 'exit_diameter': 47.6, 'expansion_ratio': 6.7,
    'grain_design': {'outer_diameter_mm': 75.0, 'inner_diameter_mm': 25.0,
                     'grain_length_mm': 360.0, 'web_thickness_mm': 25.0,
                     'web_burnout_mm': 25.0, 'Kn_initial': 145, 'Kn_final': 148},
    'nozzle_angles': {}, 'design_summary': {'key_dimensions': {}},
}
CASE_GEO = {'wall_thickness_mm': 2.0, 'thickness_source': 'manufacturing_floor',
            'user_supplied': False, 'hoop_required_mm': 1.62,
            'manufacturing_floor_mm': 2.0, 'raised_to_manufacturing_floor': True,
            'note': 'case_thickness was not supplied'}
HEAD_GEO = {'analysis': {'type': 'dished', 'recommended_type': 'dished',
                         'thickness_mm': 1.6265},
            'cad_model': {'type': 'flat', 'thickness_mm': 8.997},
            'reason': 'flat closure head at chamber pressure'}


def _tablo_kos(html, ekler):
    govde = STUB_TR + TABLO_STUB + _helpers(html) + '\n' + _fn(html, 'tpKacis') \
        + '\n' + _fn(html, 'populateMotorDesignTable') + """
const out = {};
const CASES = %s;
Object.keys(CASES).forEach(function (ad) {
    TBODY = { innerHTML: '' };
    populateMotorDesignTable(CASES[ad]);
    out[ad] = satirlar().map(function (s) { return s.replace(/<[^>]+>/g, '|'); });
});
console.log(JSON.stringify(out));
""" % json.dumps(ekler)
    return _node_json(govde)


@node_gerekli
def test_geo_cidar_satiri_kaynagini_soyler_alan_yoksa_cizilmez():
    html = _html()
    boyutlandi = dict(KATI_TABAN, case_geometry=CASE_GEO)
    kullanici = dict(KATI_TABAN, case_geometry=dict(
        CASE_GEO, user_supplied=True, thickness_source='user_supplied',
        raised_to_manufacturing_floor=False))
    bilinmeyen = dict(KATI_TABAN, case_geometry=dict(
        CASE_GEO, thickness_source='some_new_source', user_supplied=False))
    # app.py user_supplied'ı "HRMA boyutlandırmadı" diye TÜRETİR; tanınmayan
    # bir kaynakta bayrak True gelse de "kullanıcı girdi" hükmü VERİLMEZ.
    bilinmeyen_bayrak = dict(KATI_TABAN, case_geometry=dict(
        CASE_GEO, thickness_source='some_new_source', user_supplied=True,
        raised_to_manufacturing_floor=False))
    out = _tablo_kos(html, {'yok': KATI_TABAN, 'boyutlandi': boyutlandi,
                            'kullanici': kullanici, 'bilinmeyen': bilinmeyen,
                            'bilinmeyen_bayrak': bilinmeyen_bayrak})
    def cidar(ad):
        s = [r for r in out[ad] if 'Case wall' in r]
        return s[0] if s else None
    assert cidar('yok') is None, 'case_geometry yokken satır ÇİZİLMEZ'
    b = cidar('boyutlandi')
    assert b and '2,0' in b and 'sized by HRMA' in b and '1,6' in b, b
    assert 'manufacturing floor' in b and '|mm|' in b, b
    k = cidar('kullanici')
    assert k and 'user input' in k and 'sized by HRMA' not in k, k
    u = cidar('bilinmeyen')
    assert u and 'source: some_new_source' in u, (
        'bilinmeyen kaynak adı OLDUĞU GİBİ basılmalı, hüküm uydurulmaz: %r' % u)
    ub = cidar('bilinmeyen_bayrak')
    assert ub and 'source: some_new_source' in ub and 'user input' not in ub, (
        'user_supplied bayrağı tek başına "kullanıcı girdi" hükmü vermez: %r' % ub)
    assert len(out['boyutlandi']) == len(out['yok']) + 1


@node_gerekli
def test_geo_kapak_satiri_analiz_ve_imalat_kalinligini_ayri_soyler():
    html = _html()
    tam = dict(KATI_TABAN, head_geometry=HEAD_GEO)
    kazanilmadi = dict(KATI_TABAN, head_geometry={
        'status': 'not_established', 'reason': 'no end_cap_analysis'})
    # Kalınlığın tipi analysis.type'tır (head_thickness_used_type);
    # önerilen tip başka bir kalınlığın tipi olabilir, onun yerine geçmez.
    ayri_tip = dict(KATI_TABAN, head_geometry=dict(HEAD_GEO, analysis={
        'type': 'flat', 'recommended_type': 'dished', 'thickness_mm': 7.5}))
    tipsiz = dict(KATI_TABAN, head_geometry=dict(HEAD_GEO, analysis={
        'thickness_mm': 7.5}))
    out = _tablo_kos(html, {'yok': KATI_TABAN, 'tam': tam,
                            'kazanilmadi': kazanilmadi, 'ayri_tip': ayri_tip,
                            'tipsiz': tipsiz})
    def kapak(ad):
        s = [r for r in out[ad] if 'Closure head' in r]
        return s[0] if s else None
    assert kapak('yok') is None
    t = kapak('tam')
    assert t and 'analysis: dished 1,63 mm' in t, t
    assert 'manufacturing solid: flat 9,00 mm' in t, t
    assert 'not established' in kapak('kazanilmadi')
    assert 'analysis: flat 7,50 mm' in kapak('ayri_tip'), kapak('ayri_tip')
    assert 'analysis: 7,50 mm' in kapak('tipsiz'), (
        'tip yayımlanmadıysa tip sözcüğü uydurulmaz: %r' % kapak('tipsiz'))


# ---------------------------------------------------------------------------
# grain_gap_mm yayımı
# ---------------------------------------------------------------------------
def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(overrides=None):
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    p = dict(grain_type='bates', propellant_type='apcp',
             chamber_diameter=100, grain_length=500,
             core_diameter=_CEKIRDEK_MM, chamber_pressure=40)
    if overrides is not None:
        p['overrides'] = dict(overrides)
    return SolidRocketEngine(**p)


def test_grain_gap_mm_ve_kaynagi_yayimlanir_step_plani_gorur():
    from hrma.export.step_export import _grain_segment_plan
    r = _sessiz(_motor(overrides={'grain_gap': 2.0}).calculate_performance)
    gd = r['grain_design']
    assert 'grain_gap_mm' in gd, 'grain_design boşluğu yayımlamıyor (D35 devri 3)'
    assert gd['grain_gap_mm'] == pytest.approx(2.0)
    assert gd['grain_gap_source'] == 'user_input'
    assert gd['grain_gap_applies'] is True and gd['number_of_segments'] > 1
    assert 'grain_gap_basis' in gd and 'not propellant' in gd['grain_gap_basis']
    plan = _grain_segment_plan({'grain_design': gd})
    assert plan['gap_published'] is True
    n, seg = plan['n'], plan['segment_mm']
    assert plan['stack_mm'] == pytest.approx(n * seg + (n - 1) * 2.0)
    # Gönderilmediyse SIFIR kullanıldı ve bu ADIYLA söylenir (sayı uydurulmaz).
    r0 = _sessiz(_motor().calculate_performance)
    gd0 = r0['grain_design']
    assert gd0['grain_gap_mm'] == 0.0
    assert gd0['grain_gap_source'] == 'not_supplied_zero'
    # Hesap değişmedi: boşluk zaten kasa boyunda görülüyordu.
    assert r['grain_design']['volumetric_loading'] < gd0['volumetric_loading']


def test_grain_gap_kaynak_engine_dosyasinda_tek_yerde():
    src = ENGINE.read_text(encoding='utf-8')
    assert src.count("'grain_gap_mm': self.grain_gap_m * 1000.0") == 1
    assert "self.grain_gap_source = (" in src
    for ad in ('user_input', 'rejected_input', 'not_supplied_zero'):
        assert "'%s'" % ad in src, ad


# ---------------------------------------------------------------------------
# TR ondalık kalanları
# ---------------------------------------------------------------------------
@node_gerekli
def test_tpsatir_ve_sigstr_ayraci_kanondan_alir():
    html = _html()
    govde = STUB_TR + _helpers(html) + _fn(html, 'tpKacis') + _fn(html, 'tpSatir') \
        + _fn(html, 'hrmaSigStr') + """
console.log(JSON.stringify({satir: tpSatir('a', 1.5, false), sig: hrmaSigStr(899.7),
                            sig2: hrmaSigStr(25.586), tam: hrmaSigStr(40)}));
"""
    out = _node_json(govde)
    assert '1,5' in out['satir'] and '1.5' not in out['satir'], out['satir']
    assert out['sig'] == '899,7' and out['sig2'] == '25,586' and out['tam'] == '40'
    en = _node_json(STUB_EN + _helpers(html) + _fn(html, 'tpKacis') + _fn(html, 'tpSatir')
                    + _fn(html, 'hrmaSigStr')
                    + "\nconsole.log(JSON.stringify({sig: hrmaSigStr(899.7)}));")
    assert en['sig'] == '899.7', 'İngilizce arayüzde ayraç nokta kalır'


@node_gerekli
def test_plotly_ayraci_kanondan_turetilir():
    html = _html()
    parcalar = _fn(html, 'hrmaPlotSeparators') + _fn(html, 'hrmaFigureLayout')
    tr = _node_json(STUB_TR + parcalar
                    + "\nconsole.log(JSON.stringify({s: hrmaFigureLayout({}).separators,"
                    " k: hrmaFigureLayout({separators: 'x,'}).separators}));")
    assert tr.get('s') == ',.', 'TR: Plotly ondalık ayracı virgül olmalı: %r' % tr
    assert tr['k'] == 'x,', 'figürün kendi ayracı korunur'
    en = _node_json(STUB_EN + parcalar
                    + "\nconsole.log(JSON.stringify({s: hrmaFigureLayout({}).separators}));")
    assert en['s'] == '.,'
    govde = _fn(html, 'hrmaPlotLayout')
    assert 'out.separators = hrmaPlotSeparators()' in govde, (
        'hrmaPlotLayout (itki/basınç/irtifa eksenleri) da ayracı kanondan almalı')


@node_gerekli
def test_svg_oznitelikleri_yerellesmez_onizleme_blogu_kendine_yeter():
    html = _html()
    blok = _blok(html, *PREVIEW_MARKERS)
    assert 'numTxt(' not in blok, (
        'önizleme bloğu numTxt kullanamaz: SVG öznitelikleri yerelleşmez '
        've blok node\'da tek başına koşar')
    assert 'function svgAttrNum(' in blok
    for kalip in ('r="\' + svgAttrNum(', 'cx="\' + svgAttrNum('):
        assert kalip in blok, kalip
    govde = STUB_TR + _fn(html, 'svgAttrNum') + _fn(html, 'grainSlotPath') + """
const sh = {c: 90, scale: 0.8, Di: 30, Do: 100};
const yol = grainSlotPath(sh, 0, 3, 10, 40);
console.log(JSON.stringify({r: svgAttrNum(24.004), r2: svgAttrNum(25.6), yol: yol}));
"""
    out = _node_json(govde)
    assert out['r'] == '24' and out['r2'] == '25.6'
    assert re.match(r'^M-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?(?: L-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?)+ Z$',
                    out['yol']), out['yol']


# ---------------------------------------------------------------------------
# OH-P-15 — seçiciler
# ---------------------------------------------------------------------------
def test_ohp15_secici_css_ve_title_esitleme():
    html = _html()
    css = html[:html.index('</style>')]
    assert re.search(r'\.form-group select\s*\{[^}]*text-overflow:\s*ellipsis', css), (
        'form seçicileri "…" ile kısalmalı (OH-P-15)')
    m = re.search(r'\.catalog-toolbar select\s*\{([^}]*)\}', css)
    assert m and re.search(r'min-width:\s*(\d+)px', m.group(1)), 'katalog seçicisine genişlik'
    assert int(re.search(r'min-width:\s*(\d+)px', m.group(1)).group(1)) >= 180
    # Eşitleme GÖSTERİM ANINDA ve yalnız olayın hedefi: toptan ilk-yükleme
    # eşitlemesi 6-DOF seçicilerine çeviriden önceki İngilizce metni
    # yazıyordu (ölçüldü, a1/rapor.md).
    for olay in ('mouseover', 'focusin', 'change'):
        assert "document.addEventListener('%s', tazele)" % olay in html, olay
    assert 'window.syncSelectTitles(ev.target)' in html
    assert 'window.syncSelectTitles();' not in html, 'toptan eşitleme geri geldi'


def _secici_kos(govde_ek):
    html = _html()
    kapsam = re.search(r"\n        const SELECT_TITLE_SCOPE = [^\n]+\n", html).group(0)
    return _node_json(STUB_TR + kapsam + _fn(html, 'syncSelectTitles') + govde_ek)


@node_gerekli
def test_ohp15_title_secili_secenegin_tam_metni():
    out = _secici_kos("""
const sel = { tagName: 'SELECT', title: '', selectedIndex: 1,
              matches: () => true,
              options: [{textContent: 'A'}, {textContent: ' KNDX — KNO3/Dekstroz 65/35 (Nakka uyumu) '}] };
const document = { querySelectorAll: () => [sel] };
const n = syncSelectTitles();
console.log(JSON.stringify({n: n, title: sel.title}));
""")
    assert out['n'] == 1
    assert out['title'] == 'KNDX — KNO3/Dekstroz 65/35 (Nakka uyumu)'


@node_gerekli
def test_ohp15_hedef_secici_bayat_titlei_tazeler_kapsam_disina_dokunmaz():
    out = _secici_kos("""
const document = { querySelectorAll: () => [] };
const sd = { tagName: 'SELECT', title: 'Ogive', selectedIndex: 0,
             matches: (q) => q.indexOf('.form-group select') >= 0,
             options: [{textContent: 'Ojiv'}] };
const dil = { tagName: 'SELECT', title: 'Dil', selectedIndex: 1,
              matches: () => false,
              options: [{textContent: 'English'}, {textContent: 'Türkçe'}] };
const n1 = syncSelectTitles(sd), n2 = syncSelectTitles(dil);
console.log(JSON.stringify({sd: sd.title, dil: dil.title, n1: n1, n2: n2}));
""")
    assert out['sd'] == 'Ojiv' and out['n1'] == 1, 'bayat (eski dil) title tazelenmeli'
    assert out['dil'] == 'Dil' and out['n2'] == 0, (
        "kapsam dışı seçicinin (dil anahtarı) kendi title'ı ezilmez")
