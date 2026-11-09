# -*- coding: utf-8 -*-
"""V306/DİL-HİBRİT bekçisi — hibrit sayfasının kullanıcıya görünen dili.

Kanıt: ``docs/scofield/raw/OH/V306/dil-hibrit/`` (PLAN, RAPOR, ölçüm json'u).

* K1 (NR-2 + UÇUŞ-3 DEVİR 1): Zaman Çözümlü rozetleri ham alan adı basmaz
  (``tank_phase_final vapor``, ``vapor_onset_s 10.41 s``, ``residual_*``,
  ``engine.lambda_eff``, ``(summerfield)``); etiket sözlükten, TR ondalık
  virgül, makine adı ``data-tp-field`` / ``data-tp-cutoff-field``'da.
* K3+K4 (BAYAT DEVİR 5, K-P5): Tasarım Raporu/Özeti kod değerleri
  (``cylindrical_bore``, ``outer_surface``, DESIGN_STATUS_*) sözlükten;
  YAPISAL ASGARİ EK künyesinde uç adı yok.
* K5/K6/K8: hibrit sözlüğünde uç/alan adı, gönderim kalıbı, kaynaksız
  "tipik değer" ve başka yazılım önerisi yok; Kütle Akısı ipucu çözücünün
  akı tabanı ve varsayılanıyla, irtifa profili ipuçları sunucunun okuduğu
  alanlarla tutarlı.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

from tests.support.kanit import kanit_gerekli  # docs'suz yayın dalında atlar

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(KOK, 'hrma', 'static', 'js')
NODE = shutil.which('node')
gerek_node = pytest.mark.skipif(NODE is None, reason='node yok')


def oku(rel):
    with open(os.path.join(KOK, rel), encoding='utf-8') as f:
        return f.read()


# ---------------------------------------------------------------------------
# Node düzeneği: GERÇEK sözlükler (i18n_common + i18n_advanced) yüklenir,
# I18N.t seçilen dilin değerini döndürür; I18N.number TR'de virgül basar.
# Betik stdin'den verilir (tests/test_node_cagri_sozlesmesi.py).
# ---------------------------------------------------------------------------
PRELUDE = r"""
const fs = require('fs'), vm = require('vm');
function yukle(dil, dosyalar) {
  const SOZ = {en: {}, tr: {}};
  function tf(k, p, f) {
    const sablon = (SOZ[dil][k] !== undefined) ? SOZ[dil][k] : f;
    return String(sablon).replace(/\{(\w+)\}/g,
      (w, n) => (p && n in p) ? String(p[n]) : w); }
  const ogeler = {};
  function oge(id) {
    if (!ogeler[id]) ogeler[id] = {id: id, innerHTML: '', textContent: '',
      style: {}, disabled: false, value: '', addEventListener() {},
      setAttribute() {}, getAttribute() { return null; },
      querySelectorAll() { return []; }, appendChild() {}};
    return ogeler[id];
  }
  const window = {
    I18N: {lang: dil,
      register: (d) => { ['en', 'tr'].forEach((l) => Object.assign(SOZ[l], d[l] || {})); },
      t: (k, f) => (SOZ[dil][k] !== undefined ? SOZ[dil][k] : f), tf: tf,
      has: (k) => SOZ[dil][k] !== undefined,
      number: (v, d) => { const s = v.toFixed(d); return dil === 'tr' ? s.replace('.', ',') : s; },
      onChange: () => {}, applyTo: () => {}},
  };
  const document = {getElementById: oge, addEventListener() {},
    querySelectorAll: () => [], querySelector: () => null,
    createElement: () => oge('__yeni' + Math.random())};
  const ctx = {window, document, console, Math, JSON, Number, String, Array,
    Object, isFinite, parseFloat, parseInt, Boolean, RegExp, Error, require,
    setTimeout: () => 0, clearTimeout: () => {},
    Plotly: {react() {}, newPlot() {}, purge() {}}};
  vm.createContext(ctx);
  ['hrma/static/js/i18n_common.js', 'hrma/static/js/i18n_advanced.js']
    .concat(dosyalar).forEach((d) => vm.runInContext(
      fs.readFileSync(d, 'utf8'), ctx, {filename: d}));
  return {window, ogeler};
}
"""


def node_kos(govde):
    r = subprocess.run([NODE], input=PRELUDE + govde, capture_output=True,
                       text=True, cwd=KOK, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


#: Örnek hibrit (blowdown) koşusunun Zaman Çözümlü bloğu — ölçülen değerler
#: (olcum/ekran_once_tr.json): faz, buhar başlangıcı, kesme alanları.
TRANSIENT = {
    'end_event': 'oxidizer_depleted', 'burn_duration': 10.41,
    'total_impulse': 26800.0, 'time': [0, 1], 'thrust': [1, 1],
    'chamber_pressure': [1e6, 1e6], 'feed_mode': 'blowdown',
    'tank_phase_final': 'vapor', 'vapor_onset_s': 10.41,
    'tank_phase': ['two_phase'] * 210 + ['vapor'],
    'residual_oxidizer_kg': 1.618, 'residual_impulse_at_cutoff_rate_Ns': 3755.2,
    'residual_impulse_fraction_at_cutoff_rate': 0.1399,
    'vapor_phase_integrated': False,
    'vapor_tail_off_leaves_model_envelope': True,
    'thrust_coefficient_contract': {
        'divergence_efficiency': 0.983,
        'divergence_efficiency_source': 'engine.lambda_eff',
        'loss_set': {'loss_product': 0.9885,
                     'source': 'engine.headline_loss_set'}},
    'flow_separation': {'criterion': 'summerfield', 'steps_floored': 0,
                        'steps_zero_clamped': 0, 'steps_total': 209},
}

#: Rozet METNİNDE (nitelik dışı) geçmemesi gereken makine adları.
HAM_ADLAR = ('tank_phase_final', 'vapor_onset_s', 'tank_phase ',
             'two_phase', 'residual_oxidizer_kg', 'residual_impulse',
             'vapor_phase_integrated', 'vapor_tail_off',
             'engine.lambda_eff', 'engine.headline_loss_set', '(summerfield)')


def _rozetler(dil, transient):
    return node_kos(r"""
    const Y = yukle(%s, ['hrma/static/js/units_constants.js',
                         'hrma/static/js/transient_panel.js']);
    Y.window.TransientPanel._render(%s);
    console.log(JSON.stringify({html: Y.ogeler['tp_badges'].innerHTML}));
    """ % (json.dumps(dil), json.dumps({'status': 'success',
                                        'transient': transient,
                                        'design_point': {}})))


def _gorunur(html):
    """Etiket ve nitelikler atılmış görünür metin."""
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', html))


@gerek_node
class TestZamanCozumluRozetleri:

    def test_tr_rozetlerde_ham_alan_adi_yok_etiket_ve_virgul_var(self):
        o = _rozetler('tr', TRANSIENT)
        metin = _gorunur(o['html'])
        kalan = [ad for ad in HAM_ADLAR if ad in metin]
        assert not kalan, ('TR rozet metninde makine adı: %s\n%s'
                           % (kalan, metin))
        for beklenen in ('SON TANK FAZI: buhar', 'BUHAR FAZI BAŞLANGICI 10,41 s',
                         'TANK FAZI (çözücü adımı): iki fazlı 210 / buhar 1',
                         'TANKTA KALAN OKSİTLEYİCİ 1,618 kg',
                         'BUHAR FAZI İNTEGRE EDİLDİ: hayır',
                         'BUHAR KUYRUĞU MODEL ZARFININ DIŞINDA: evet',
                         'motorun nozul konturu', 'Summerfield ölçütü'):
            assert beklenen in metin, (beklenen, metin)
        # (Düzenekte I18N.tf ondalık yerelleştirmez; kanal bu rozetin
        # kendi ekranSayisi çağrısıdır.)
        assert 'BAŞLANGICI 10.41' not in metin, 'TR ekranda noktalı ondalık'

    def test_en_rozetler_ingilizce_etiketle(self):
        o = _rozetler('en', TRANSIENT)
        metin = _gorunur(o['html'])
        assert not [ad for ad in HAM_ADLAR if ad in metin], metin
        for beklenen in ('TANK PHASE AT END: vapor', 'VAPOR PHASE ONSET 10.41 s',
                         'OXIDIZER LEFT IN TANK 1.618 kg',
                         'Summerfield criterion'):
            assert beklenen in metin, (beklenen, metin)

    def test_makine_adi_nitelikte_kalir(self):
        """Ad+değer bağı: makine adı rozeti saran niteliktedir."""
        h = _rozetler('tr', TRANSIENT)['html']
        for ad in ('tank_phase_final', 'vapor_onset_s', 'tank_phase'):
            assert 'data-tp-field="%s"' % ad in h, ad
        for ad in ('residual_oxidizer_kg', 'vapor_phase_integrated'):
            assert 'data-tp-cutoff-field="%s"' % ad in h, ad

    def test_taninmayan_kod_ham_ve_imli_basilir(self):
        """Sessiz yedek yok: tabloda olmayan faz/kaynak/ölçüt GÖRÜNÜR kalır."""
        t = dict(TRANSIENT, tank_phase_final='plasma')
        t['flow_separation'] = dict(TRANSIENT['flow_separation'],
                                    criterion='kalt')
        metin = _gorunur(_rozetler('tr', t)['html'])
        assert 'plasma (?)' in metin and 'kalt (?)' in metin, metin


# ---------------------------------------------------------------------------
# K3 + K4 — Tasarım Raporu / Özeti kod değerleri, YAPISAL ASGARİ EK künyesi
# ---------------------------------------------------------------------------
def _sozluk(dil):
    src = oku('hrma/static/js/i18n_advanced.js')
    bas = src.index('        tr: {')
    blok = src[:bas] if dil == 'en' else src[bas:]
    return dict(re.findall(r"^\s*'([^']+)':\s*'((?:\\.|[^'\\])*)',?$",
                           blok, re.M))


def test_rapor_kod_tablosu_motorun_butun_durumlarini_kapsar():
    """DESIGN_STATUS_* ve grain_design kodları tablodadır; anahtar EN+TR."""
    app = oku('hrma/static/js/app.js')
    m = re.search(r'const RAPOR_KOD_ETIKETI = \{(.*?)\n\};', app, re.S)
    assert m, 'RAPOR_KOD_ETIKETI tablosu yok'
    tablo = dict(re.findall(r"^\s*'?([\w]+)'?:\s*\['(adv\.js\.[\w]+)'",
                            m.group(1), re.M))
    motor = oku('hrma/engines/hybrid_rocket_engine.py')
    durumlar = set(re.findall(r"^DESIGN_STATUS_\w+ = '(\w+)'", motor, re.M))
    assert len(durumlar) == 6, durumlar
    kodlar = durumlar | {'cylindrical_bore', 'outer_surface'}
    assert "'grain_type': 'cylindrical_bore'" in motor
    assert "'inhibitor': 'outer_surface'" in motor
    eksik = sorted(kodlar - set(tablo))
    assert not eksik, 'raporda çevrilmeyen kod: %s' % eksik
    en, tr = _sozluk('en'), _sozluk('tr')
    for kod, anahtar in tablo.items():
        assert anahtar in en and anahtar in tr, anahtar
        assert en[anahtar] != tr[anahtar], (anahtar, 'TR çevrilmemiş')
    # üç rapor satırı tablodan okur (ham reportLabel'a düşmez)
    for satir in ('raporKodEtiketi(grainDesign.grain_type)',
                  'raporKodEtiketi(grainDesign.inhibitor)',
                  'raporKodEtiketi(designSummary.status)'):
        assert satir in app, satir


def test_yapisal_asgari_ek_kunyesinde_uc_adi_yok():
    app = oku('hrma/static/js/app.js')
    assert "kunye.push('/calculate')" not in app
    assert "kunye.push(T('adv.js.sfCardRunMotor'" in app


# ---------------------------------------------------------------------------
# K5 / K6 / K8 — hibrit sözlüğünün ipucu ve yardım metinleri
# ---------------------------------------------------------------------------
YASAK = re.compile(
    r"/api/|/calculate\b|/analyze|sent as\b|olarak gönderilir|inputs_not_read"
    r"|\btypical|\btypically\b|\busually\b|\btipik|\bgenellikle\b|eta_c\*"
    r"|\bANSYS\b", re.I)


@pytest.mark.parametrize('dil', ('en', 'tr'))
def test_hibrit_sozlugunde_uc_adi_ve_kaynaksiz_tipik_yok(dil):
    kalan = {k: YASAK.findall(v) for k, v in _sozluk(dil).items()
             if YASAK.search(v)}
    assert not kalan, 'hibrit sözlüğünde yasak kalıp (%s): %s' % (dil, kalan)


def test_kutle_akisi_ipucu_cozucunun_aki_tabani_ve_varsayilaniyla():
    """K-P6: ipucu çözücünün kullandığı G_ox'u, 350 varsayılanını ve 600
    taşma eşiğini söyler; sayılar kodla birlikte değişmek zorunda."""
    from hrma.analysis.regression_analysis import DEFAULT_FLUX_MODE
    from hrma.engines.hybrid_rocket_engine import OX_FLUX_FLOODING_WARN_KG_M2S
    assert DEFAULT_FLUX_MODE == 'ox'
    motor = oku('hrma/engines/hybrid_rocket_engine.py')
    m = re.search(r'self\.G_ox_design = (\d+(?:\.\d+)?)\s+# kg/m²·s', motor)
    assert m, 'G_ox varsayılanı bulunamadı'
    varsayilan = '%g' % float(m.group(1))
    esik = '%g' % OX_FLUX_FLOODING_WARN_KG_M2S
    for dil in ('en', 'tr'):
        v = _sozluk(dil)['adv.tip.massFluxKgM']
        assert 'G_ox' in v and varsayilan in v and esik in v, (dil, v)
    assert 'Typical' not in _sozluk('en')['adv.tip.massFluxKgM']


def test_irtifa_profili_ipuclari_sunucunun_okumadigini_soyler():
    """Sunucu ``altitude_profile``ı okumaz (Python'da 0 kez geçer): bitiş
    irtifası ve nokta sayısı ipuçları 'hesaplanır' iddia edemez."""
    py = []
    for kok, _, dosyalar in os.walk(os.path.join(KOK, 'hrma')):
        for d in dosyalar:
            if d.endswith('.py'):
                with open(os.path.join(kok, d), encoding='utf-8') as f:
                    if 'altitude_profile' in f.read():
                        py.append(d)
    assert not py, ('sunucu altitude_profile okuyor (%s) — ipuçlarını '
                    'yeniden yaz' % py)
    en = _sozluk('en')
    for k in ('adv.tip.finalAltitudeM', 'adv.tip.numberPoints'):
        assert 'does not read it' in en[k], (k, en[k])
        assert 'calculated at' not in en[k]


def test_blowdown_ornek_rozeti_sozlukten():
    js = oku('hrma/static/js/blowdown_panel.js')
    assert "TF('adv.js.bdSamples'" in js
    assert "badge('SAMPLES '" not in js


# ---------------------------------------------------------------------------
# K1 (blowdown) — teknik ayrıntı rozetleri de kullanıcı dilinde
# ---------------------------------------------------------------------------
BD_VM = {
    'tank_phase_final': 'vapor', 'vapor_onset_s': 10.41,
    'tank_phase': ['two_phase'] * 210 + ['vapor'],
    'bayraklar': [{'field': 'vapor_phase_integrated', 'value': False,
                   'limitsAt': False},
                  {'field': 'vapor_model_valid', 'value': True,
                   'limitsAt': False}],
    'kesme': [{'field': 'residual_oxidizer_kg', 'value': 1.618,
               'digits': 3, 'unit': ' kg'}],
}


def _bd_rozetler(dil, vm):
    return node_kos(r"""
    const Y = yukle(%s, ['hrma/static/js/units_constants.js',
                         'hrma/static/js/transient_panel.js',
                         'hrma/static/js/blowdown_panel.js']);
    const el = {innerHTML: ''};
    Y.window.BlowdownPanel._renderBadges(el, %s);
    console.log(JSON.stringify({html: el.innerHTML}));
    """ % (json.dumps(dil), json.dumps(vm)))


@gerek_node
def test_blowdown_teknik_rozetleri_kullanici_dilinde():
    h = _bd_rozetler('tr', BD_VM)['html']
    metin = _gorunur(h)
    kalan = [ad for ad in HAM_ADLAR + ('vapor_model_valid', 'true', 'false')
             if ad in metin]
    assert not kalan, (kalan, metin)
    for beklenen in ('SON TANK FAZI: buhar', 'BUHAR FAZI BAŞLANGICI 10,41 s',
                     'BUHAR FAZI İNTEGRE EDİLDİ: hayır',
                     'BUHAR MODELİ GEÇERLİ: evet',
                     'TANKTA KALAN OKSİTLEYİCİ 1,618 kg',
                     'Tank fazı ve kesme ayrıntısı'):
        assert beklenen in metin, (beklenen, metin)
    for ad in ('tank_phase_final', 'vapor_phase_integrated',
               'residual_oxidizer_kg'):
        assert 'data-bd-field="%s"' % ad in h, ad


# ---------------------------------------------------------------------------
# DİL-ORTAK DEVİR 2-4 (9 Kas ana model mesajı)
# ---------------------------------------------------------------------------
SIMGE = re.compile(r'(?<![A-Za-z0-9_])(?:t_b|d_o|D_s|A_p|eta_c)(?![A-Za-z0-9_])')


@pytest.mark.parametrize('dil', ('en', 'tr'))
def test_hibrit_sozlugunde_alan_adi_gibi_okunan_simge_yok(dil):
    """``ipucu_uc_adi.tsv`` 't_b', 'd_o', 'eta_c' satırları: formül kelimeyle
    ya da Unicode alt simgeyle (dₒ, Dₛ, Aₚ) yazılır."""
    kalan = {k: SIMGE.findall(v) for k, v in _sozluk(dil).items()
             if SIMGE.search(v)}
    assert not kalan, kalan


def test_kilavuz_p9_hibrit_cumleleri_ekranda_yok():
    """KILAVUZ P9 ``atilan_cumle`` listesinin hiçbiri hibrit sözlüğünde ya
    da şablonda kalmaz (DİL-ORTAK DEVİR 3: TR 20 / EN 16 kimlik)."""
    src = oku('hrma/static/js/i18n_advanced.js')
    tpl = oku('hrma/templates/advanced.html')
    kalan = []
    for dil in ('tr', 'en'):
        yol = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'V301',
                           'kilavuz-denetim', 'olcum',
                           'tablo_uret_rapor_%s.json' % dil)
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            for k in json.load(f)['kayitlar']:
                c = k.get('atilan_cumle')
                if c and (c in tpl or c in src or c.replace("'", "\\'") in src):
                    kalan.append((dil, k['kimlik'], c))
    assert not kalan, kalan


def test_yanma_tipi_tek_terim():
    """P11: etiket 'Combustion Type' ⟷ TR 'Yanma Tipi' (eski 'Yanma Modeli')."""
    assert _sozluk('en')['adv.label.combustionType'] == 'Combustion Type'
    assert _sozluk('tr')['adv.label.combustionType'] == 'Yanma Tipi'


def test_optimum_of_grafigi_dil_degisiminde_yeniden_cizilir_ve_daralir():
    """K12 (DİL-ORTAK DEVİR 1+6): çizim tek işlevde; dil değişimi aynı
    yanıttan yeniden çizer; Plotly ``responsive`` açık. (Davranış ölçümü:
    docs/…/dil-hibrit/olcum/of_grafik_sonra.json.)"""
    s = oku('hrma/templates/advanced.html')
    i = s.index('async function findOptimumOF(')
    bul = s[i:s.index('// 3D CAD Functions', i)]
    assert 'sonOptimumOfYaniti = result;' in bul
    assert 'optimumOfEgrisiniCiz(result);' in bul
    assert 'Plotly.newPlot' not in bul, 'çizim findOptimumOF içinde kalmış'
    j = s.index('function optimumOfEgrisiniCiz(')
    ciz = s[j:i]
    assert 'Plotly.newPlot(plotDiv, [trace], layout, { responsive: true });' in ciz
    assert re.search(r'I18N\.onChange\(function \(\) \{\s*try \{\s*if \(sonOptimumOfYaniti',
                     ciz), 'dil değişimi kancası yok'
