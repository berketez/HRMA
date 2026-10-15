"""E5 bekçileri — duyarlılık: "hangi girdi amacı GERÇEKTEN oynatıyor".

Bu dosya tek bir soruyu kilitler: kullanıcı tornado grafiğine bakıp bir
parametreyi "amacı süren girdi" ilan ettiğinde, bu hüküm ÖLÇÜMDEN mi
geliyor yoksa örnekleme gürültüsünden mi?

ÖLÇÜLEN KUSUR (2026-08-18, bu partiden önce):
  Çekirdek (hrma/analysis/uncertainty.py) her satır için 'significant'
  hükmünü v2.6.2'den beri HESAPLIYORDU (|rho| > Sidak düzeltmeli gürültü
  tabanı). Ama G3 kontrat gövdesi (_uq_contract_body) satırdan yalnız
  'param' + 'rho' + 'noise_floor' taşıyordu; hüküm KONTRATTA DÜŞÜYORDU.
  Panel de tabanı hiç okumuyor, bütün çubukları yeşil/kırmızı çiziyordu.
  Sonuç, katı motor n=60 koşusunda ölçüldü: 'max_pressure' çıktısında
  DÖRT parametrenin DÖRDÜ de tabanın (0,324) altındaydı — yani sıralama
  tamamen gürültüydü — ve panel bunu güvenli bir sıralama gibi gösterip
  "yoğunluk basıncı sürüyor" okumasına davet ediyordu.

Bu bekçiler üç katmanı birden bağlar:
  1. Çekirdek  — rho el hesabıyla, işaret monotonlukla, yetersiz örnekte
     'not_modelled' beyanı (uydurma sayı yok), aynı tohum aynı sonuç.
  2. Kontrat   — 'significant' + 'status' + 'basis' kullanıcıya ULAŞIR.
  3. Panel     — izler yanıt dizilerinden kurulur, gürültü çubuğu sinyal
     gibi boyanmaz, sıralama yoksa grafik ÇİZİLMEZ (gerekçe yazılır).

MUTASYONLA ÖLÇÜLDÜ (hepsi ters-değiştirmeyle geri alındı; ayrıntı raporda):
  * app.py'de 'significant' taşıması sökülürse    -> 3 kırmızı
  * panel hükmü yok sayıp hepsini renklendirirse  -> 3 kırmızı
  * çekirdek örnek kapısı kaldırılırsa            -> 3 kırmızı
"""

import json
import math
import os
import pathlib
import re
import shutil
import subprocess

import numpy as np
import pytest

from hrma.analysis.uncertainty import (
    DEFAULT_UQ_MODELS,
    SENSITIVITY_MAX_NOISE_FLOOR,
    SENSITIVITY_METHOD,
    SENSITIVITY_MIN_SAMPLES,
    UncertainInput,
    run_uncertainty,
    sensitivity_noise_floor,
    spearman_sensitivity,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PANEL_JS = STATIC_JS / 'panels' / 'uncertainty_panel.js'
DOCK_JS = STATIC_JS / 'analysis_dock.js'
THEME_CSS = REPO_ROOT / 'hrma' / 'static' / 'css' / 'theme.css'
APP_PY = REPO_ROOT / 'hrma' / 'app.py'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def _dists(n_inputs=3):
    """Kapalı formda çözülebilir oyuncak dağılımlar (hepsi uniform)."""
    return {
        f'x{i + 1}': UncertainInput(name=f'x{i + 1}', dist='uniform',
                                    mode='absolute', mean=0.5,
                                    low=0.0, high=1.0)
        for i in range(n_inputs)
    }


# ===========================================================================
# 1) ÇEKİRDEK — rho'nun kendisi
# ===========================================================================

class TestRhoHesabi:
    """Spearman değeri el hesabıyla doğrulanır (kütüphaneye güven yok)."""

    def test_rho_el_hesabiyla_ayni(self):
        """Bilinen küçük örneklem: rho = 1 - 6*sum(d^2)/(n*(n^2-1)).

        Bağsız sıralarda Spearman'ın kapalı formu budur (Kendall & Stuart,
        The Advanced Theory of Statistics). Bekçi kütüphane çıktısını bu
        formülle KARŞILAŞTIRIR, formülü kütüphaneden türetmez.
        """
        x = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
        # y sıralaması bilerek bozuk: sıra farkları d = [0,0,+1,-1,0,+1,-1]
        y = [1.0, 2.0, 4.0, 3.0, 5.0, 7.0, 6.0]
        n = len(x)
        d2 = sum((rx - ry) ** 2 for rx, ry in zip(
            [1, 2, 3, 4, 5, 6, 7], [1, 2, 4, 3, 5, 7, 6]))
        beklenen = 1.0 - 6.0 * d2 / (n * (n * n - 1))
        assert d2 == 4  # el hesabı: 0+0+1+1+0+1+1

        satirlar = spearman_sensitivity(np.asarray(x).reshape(-1, 1),
                                        np.asarray(y), ['x'])
        assert satirlar[0]['spearman'] == pytest.approx(beklenen, abs=1e-12), (
            f"rho el hesabından sapıyor: {satirlar[0]['spearman']} != {beklenen}")
        # Elle: 1 - 24/336 = 0.928571...
        assert beklenen == pytest.approx(0.9285714285714286, abs=1e-15)

    def test_tam_monoton_ciftlerde_isaret_dogru(self):
        """Artan bağımlılık +1, azalan bağımlılık -1 vermeli."""
        x = np.linspace(0.0, 1.0, 40).reshape(-1, 1)
        artan = spearman_sensitivity(x, np.exp(x[:, 0]), ['x'])
        azalan = spearman_sensitivity(x, -3.0 * x[:, 0] ** 3, ['x'])
        assert artan[0]['spearman'] == pytest.approx(1.0, abs=1e-12)
        assert azalan[0]['spearman'] == pytest.approx(-1.0, abs=1e-12)

    def test_monoton_bagimlilikta_isaret_kosuda_da_dogru(self):
        """Tam koşuda: y = 2*x1 - 3*x2 -> x1 pozitif, x2 negatif."""
        res = run_uncertainty(lambda s: {'y': 2.0 * s['x1'] - 3.0 * s['x2']},
                              _dists(2), n_samples=200, seed=7,
                              output_keys=['y'])
        rho = {r['param']: r['spearman']
               for r in res['sensitivity']['per_output']['y']}
        assert rho['x1'] > 0.4, rho
        assert rho['x2'] < -0.4, rho
        # 3 kat daha güçlü katsayı daha büyük |rho| vermeli
        assert abs(rho['x2']) > abs(rho['x1']), rho

    def test_ayni_tohum_ayni_sonuc(self):
        """Deterministik tekrarlanabilirlik: bit düzeyinde aynı."""
        f = lambda s: {'y': s['x1'] ** 2 + 0.5 * s['x2']}   # noqa: E731
        a = run_uncertainty(f, _dists(3), n_samples=120, seed=99,
                            output_keys=['y'])['sensitivity']['per_output']['y']
        b = run_uncertainty(f, _dists(3), n_samples=120, seed=99,
                            output_keys=['y'])['sensitivity']['per_output']['y']
        assert [r['spearman'] for r in a] == [r['spearman'] for r in b]
        assert [r['param'] for r in a] == [r['param'] for r in b]
        # Farklı tohum farklı örneklem -> aynı sayı ÇIKMAMALI (aksi halde
        # tohum hiç kullanılmıyor demektir; sessiz sabitleme yakalanır)
        c = run_uncertainty(f, _dists(3), n_samples=120, seed=100,
                            output_keys=['y'])['sensitivity']['per_output']['y']
        assert [r['spearman'] for r in a] != [r['spearman'] for r in c]

    def test_gurultu_girdisi_anlamsiz_isaretlenir(self):
        """Modele HİÇ girmeyen parametre 'significant=False' olmalı."""
        res = run_uncertainty(lambda s: {'y': 5.0 * s['x1']}, _dists(3),
                              n_samples=200, seed=42, output_keys=['y'])
        rows = {r['param']: r for r in res['sensitivity']['per_output']['y']}
        assert rows['x1']['significant'] is True
        assert rows['x2']['significant'] is False, rows['x2']
        assert rows['x3']['significant'] is False, rows['x3']


# ===========================================================================
# 2) ÇEKİRDEK — yetersiz örnekte blok DÜŞER
# ===========================================================================

class TestOrnekKapisi:

    def test_esik_altinda_not_modelled(self):
        res = run_uncertainty(lambda s: {'y': 5.0 * s['x1']}, _dists(3),
                              n_samples=SENSITIVITY_MIN_SAMPLES - 5, seed=42,
                              output_keys=['y'])
        sens = res['sensitivity']
        assert res['status'] == 'success'          # koşunun kendisi sağlam
        assert sens['status'] == 'not_modelled'
        assert sens['per_output'] == {}
        # Uydurma yok: çıktı anahtarı hiç görünmemeli
        assert 'y' not in sens
        # Gerekçe SAYILI olmalı (boş "veri yok" cümlesi değil)
        assert str(SENSITIVITY_MIN_SAMPLES) in sens['reason']
        assert str(sens['n_used']) in sens['reason']

    def test_esik_ustunde_modelled(self):
        res = run_uncertainty(lambda s: {'y': 5.0 * s['x1']}, _dists(3),
                              n_samples=SENSITIVITY_MIN_SAMPLES, seed=42,
                              output_keys=['y'])
        sens = res['sensitivity']
        assert sens['status'] == 'modelled'
        assert len(sens['per_output']['y']) == 3

    def test_esik_olcumden_turetildi_secilmedi(self):
        """MIN_SAMPLES sihirli sayı DEĞİL: eşikte gürültü tabanı, varsayılan
        modellerin HEPSİ için MAX_NOISE_FLOOR'un altında olmalı."""
        for motor, model in DEFAULT_UQ_MODELS.items():
            d = len(model)
            taban = sensitivity_noise_floor(SENSITIVITY_MIN_SAMPLES, d)
            assert taban < SENSITIVITY_MAX_NOISE_FLOOR, (
                f'{motor}: d={d} için eşikteki taban {taban:.3f} >= '
                f'{SENSITIVITY_MAX_NOISE_FLOOR} — eşik bu modeli kapsamıyor')
        # Eşiğin BİR ALTINDA kapsanmayan bir model olmalı ki eşik gevşek
        # seçilmiş olmasın (d=6 hibrit: n=28'de taban 0.506 > 0.5)
        assert sensitivity_noise_floor(28, 6) > SENSITIVITY_MAX_NOISE_FLOOR

    def test_taban_kapisi_yuksek_boyutta_da_isliyor(self):
        """n eşiği geçse bile taban yüksekse blok düşer (d-tarafı kapısı).

        d=10, n=31: n >= 30 ama taban 0.5'in üstünde -> sıralama yok.
        """
        assert sensitivity_noise_floor(31, 10) >= SENSITIVITY_MAX_NOISE_FLOOR
        res = run_uncertainty(lambda s: {'y': sum(s.values())}, _dists(10),
                              n_samples=31, seed=42, output_keys=['y'])
        assert res['sensitivity']['status'] == 'not_modelled'
        assert res['sensitivity']['per_output'] == {}

    def test_beyan_ornek_sayisini_ve_kaynagi_soyluyor(self):
        res = run_uncertainty(lambda s: {'y': 5.0 * s['x1']}, _dists(3),
                              n_samples=80, seed=42, output_keys=['y'])
        sens = res['sensitivity']
        assert sens['method'] == SENSITIVITY_METHOD
        basis = sens['basis']
        assert '80' in basis, basis                     # örneklem boyutu
        assert 'SAME Monte Carlo sample' in basis       # hangi örneklemden
        assert 'no extra model runs' in basis           # yeni koşum yok
        assert f"{sens['noise_floor']:.3f}" in basis    # okunamaz bant

    def test_duz_anahtarlar_per_output_ile_ayni(self):
        """Geriye dönük düz okuma korunur ve İKİ KAYNAK AYRIŞMAZ."""
        res = run_uncertainty(lambda s: {'y': 5.0 * s['x1'], 'z': s['x2']},
                              _dists(3), n_samples=90, seed=42,
                              output_keys=['y', 'z'])
        sens = res['sensitivity']
        for key in ('y', 'z'):
            assert sens[key] is sens['per_output'][key]


# ===========================================================================
# 3) KONTRAT — hüküm kullanıcıya ULAŞIYOR mu?
# ===========================================================================

def _sahte_kosu_sonucu(status='modelled'):
    """_uq_contract_body'yi motor koşmadan besleyen asgari sonuç sözlüğü.

    (Motor koşusu gerektirmez: bu bekçi KABLOYU ölçer, fiziği değil.)
    """
    ortak = {
        'n_samples': 60, 'failed_samples': 0, 'seed': 42, 'sampler': 'lhs',
        'uq_version': '1', 'inputs_used': [],
        'timing': {'wall_s': 1.0},
        'outputs': {'isp': {'nominal': 1.0, 'mean': 1.0, 'std': 0.1,
                            'cv_percent': 10.0, 'p5': 0.9, 'p25': 0.95,
                            'p50': 1.0, 'p75': 1.05, 'p95': 1.1,
                            'histogram': {'edges': [], 'counts': []}}},
        'consistency': {'mean_shift_percent': {'isp': 0.0}, 'note': 'n'},
    }
    if status == 'modelled':
        rows = [{'param': 'a', 'spearman': 0.8, 'noise_floor': 0.3,
                 'significant': True},
                {'param': 'b', 'spearman': -0.1, 'noise_floor': 0.3,
                 'significant': False}]
        ortak['sensitivity'] = {
            'status': 'modelled', 'method': SENSITIVITY_METHOD,
            'basis': 'beyan metni', 'method_note': 'yöntem notu',
            'noise_floor': 0.3, 'n_used': 60, 'n_requested': 60,
            'min_samples': SENSITIVITY_MIN_SAMPLES,
            'per_output': {'isp': rows}, 'isp': rows,
        }
    else:
        ortak['sensitivity'] = {
            'status': 'not_modelled', 'method': SENSITIVITY_METHOD,
            'basis': 'gerekçe metni', 'reason': 'gerekçe metni',
            'method_note': 'yöntem notu', 'noise_floor': 0.9,
            'n_used': 12, 'n_requested': 12,
            'min_samples': SENSITIVITY_MIN_SAMPLES, 'per_output': {},
        }
    return ortak


class TestKontrat:

    def test_significant_kullaniciya_ulasiyor(self):
        from hrma.app import _uq_contract_body
        body = _uq_contract_body('solid', 'fast', _sahte_kosu_sonucu())
        satirlar = body['sensitivity']['isp']
        assert [r['param'] for r in satirlar] == ['a', 'b']
        assert satirlar[0]['significant'] is True
        assert satirlar[1]['significant'] is False, (
            'gürültü satırı anlamlı gibi taşınıyor — panel sinyal ile '
            'gürültüyü ayıramaz')
        assert satirlar[0]['noise_floor'] == 0.3

    def test_hukum_ve_dayanak_govdede(self):
        from hrma.app import _uq_contract_body
        body = _uq_contract_body('solid', 'fast', _sahte_kosu_sonucu())
        assert body['sensitivity_status'] == 'modelled'
        assert body['sensitivity_basis'] == 'beyan metni'
        assert body['sensitivity_method_note'] == 'yöntem notu'

    def test_not_modelled_govdede_bos_ve_gerekceli(self):
        from hrma.app import _uq_contract_body
        body = _uq_contract_body('solid', 'fast',
                                 _sahte_kosu_sonucu('not_modelled'))
        assert body['sensitivity'] == {}
        assert body['sensitivity_status'] == 'not_modelled'
        assert body['sensitivity_basis'] == 'gerekçe metni'
        # Sıfır uydurulmadı
        assert 'isp' not in body['sensitivity']

    def test_meta_satirlari_kopyalamiyor(self):
        """sensitivity_meta yalnız SKALER künye taşır; per_output oraya
        kopyalanırsa yanıt iki katına çıkar ve tek kaynak bölünür."""
        from hrma.app import _uq_contract_body
        body = _uq_contract_body('solid', 'fast', _sahte_kosu_sonucu())
        meta = body['sensitivity_meta']
        assert 'per_output' not in meta
        assert 'isp' not in meta
        assert meta['noise_floor'] == 0.3      # v2.6.2 sözleşmesi korunuyor
        assert meta['status'] == 'modelled'

    def test_kablo_gercekten_bagli(self):
        """KANAL VAR KAPI YOK kontrolü: app.py gerçekten 'significant'
        taşıyan satır kuruyor mu (kaynak kanıtı)."""
        src = APP_PY.read_text(encoding='utf-8')
        assert "'significant': bool(row['significant'])" in src, (
            'kontrat gövdesi significant taşımıyor — panel hükmü göremez')
        assert "'sensitivity_status'" in src and "'sensitivity_basis'" in src


# ===========================================================================
# 4) PANEL — node altında gerçek dosya
# ===========================================================================

HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const staticDir = process.argv[2];
const cfg = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

const byId = {};
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this._attrs = {};
    this._id = '';
    this.textContent = '';
    this.innerHTML = '';
    this.disabled = false;
    this.value = '';
    this.selectors = [];
}
Object.defineProperty(El.prototype, 'id', {
    get: function () { return this._id; },
    set: function (v) { this._id = String(v); byId[this._id] = this; },
});
Object.defineProperty(El.prototype, 'firstElementChild', {
    get: function () { return this._first || (this._first = new El('div')); },
});
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.insertBefore = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k)
        ? this._attrs[k] : null;
};
El.prototype.addEventListener = function () {};
El.prototype.querySelector = function (sel) {
    this.selectors.push(sel);
    return new El('select');
};
El.prototype.querySelectorAll = function () { return []; };

// Yalnız şablondan/güverteden GERÇEKTEN doğan kaplar vardır; bilinmeyen id
// null döner (gerçek DOM davranışı).
['ad_sec_uncertainty', 'ad_status_uncertainty', 'ad_root_uncertainty',
 'uq_run', 'uq_level', 'uq_seed', 'ad_panes', 'ad_tabs', 'ad_toolbar'
].forEach(function (id) { const e = new El('div'); e.id = id; });

const documentStub = {
    head: new El('head'),
    body: new El('body'),
    readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function (id) { return byId[id] || null; },
    addEventListener: function () {},
};

const plotly = [];
const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: function (fn) { return 0; },
    clearTimeout: function () {},
    setInterval: function () { return 0; },
    clearInterval: function () {},
    requestAnimationFrame: function (fn) { fn(); return 1; },   // eşzamanlı
    fetch: function () { return Promise.resolve({ ok: true, status: 200,
        json: function () { return Promise.resolve({}); } }); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, Promise: Promise, Error: Error,
    RegExp: RegExp, isFinite: isFinite, parseFloat: parseFloat,
    parseInt: parseInt, document: documentStub,
    localStorage: { getItem: function () { return null; },
                    setItem: function () {}, removeItem: function () {} },
    Plotly: {
        react: function (el, traces, layout) {
            plotly.push({ traces: traces, layout: layout });
        },
        purge: function () {},
    },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(staticDir, 'analysis_dock.js'), 'utf8'),
                sandbox, { filename: 'analysis_dock.js' });
vm.runInContext(fs.readFileSync(
    path.join(staticDir, 'panels', 'uncertainty_panel.js'), 'utf8'),
    sandbox, { filename: 'uncertainty_panel.js' });

const P = sandbox.window.UncertaintyPanel;
const out = { figures: {}, themeHex: P._themeHex, maxBars: P._maxBars };

// Saf katman: çizim nesnesi doğrudan yanıttan kurulur
(cfg.keys || []).forEach(function (k) {
    const fig = P._tornadoFigure(cfg.data, k);
    out.figures[k] = fig;
});
out.selectableKeys = P._selectableKeys(cfg.data);
out.noiseFloor = P._noiseFloorOf(cfg.data,
    P._sensitivityRows(cfg.data, (cfg.keys || [])[0]));

// Uçtan uca: gerçek render (DOM + Plotly taklidi)
if (cfg.render) {
    const root = new El('div');
    root.id = 'render_root';
    P._render(cfg.data, root);
    out.plotly = plotly;
    out.rootHtml = (function collect(el) {
        let s = el.innerHTML || '';
        (el.children || []).forEach(function (c) { s += collect(c); });
        return s;
    })(root);
}
process.stdout.write(JSON.stringify(out));
"""


def _kos_panel(tmp_path, data, keys, render=False):
    script = tmp_path / 'kos_uq_panel.js'
    script.write_text(HARNESS_JS, encoding='utf-8')
    girdi = tmp_path / 'girdi.json'
    girdi.write_text(json.dumps({'data': data, 'keys': keys,
                                 'render': render}), encoding='utf-8')
    proc = subprocess.run(
        [NODE, str(script), str(STATIC_JS), str(girdi)],
        capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, ('panel node altında çöktü:\n'
                                  + proc.stderr[-3000:])
    return json.loads(proc.stdout)


#: Gerçek uç gövdesinin biçimi (katı motor, n=60 koşusundan alınan alan
#: kümesi; sayılar bekçinin kendi senaryosu için seçildi — biçim gerçektir).
def _yanit(status='modelled'):
    hist = {'edges': [0.0, 1.0, 2.0], 'counts': [1, 2]}
    body = {
        'status': 'ok', 'motor_type': 'solid', 'level': 'fast',
        'n_samples': 60, 'failed_samples': 0, 'seed': 42, 'timing_s': 1.0,
        'mean_shift_percent': {'isp': 0.0, 'max_pressure': 0.0},
        'outputs': {
            'isp': {'nominal': 220.0, 'mean': 220.0, 'std': 3.0, 'cv': 1.4,
                    'p5': 215.0, 'p25': 218.0, 'p50': 220.0, 'p75': 222.0,
                    'p95': 225.0, 'histogram': hist},
            'max_pressure': {'nominal': 50.0, 'mean': 50.0, 'std': 1.0,
                             'cv': 2.0, 'p5': 48.0, 'p25': 49.0, 'p50': 50.0,
                             'p75': 51.0, 'p95': 52.0, 'histogram': hist},
        },
        'sensitivity_method_note': 'monotonic effects only',
        'sensitivity_meta': {'noise_floor': 0.324, 'n_used': 60,
                             'min_samples': 30, 'status': status},
    }
    if status == 'modelled':
        body['sensitivity'] = {
            # isp: iki gerçek etki + bir gürültü
            'isp': [
                {'param': 'c_star', 'rho': 0.812, 'noise_floor': 0.324,
                 'significant': True},
                {'param': 'burn_rate_a', 'rho': -0.417, 'noise_floor': 0.324,
                 'significant': True},
                {'param': 'density', 'rho': 0.155, 'noise_floor': 0.324,
                 'significant': False},
            ],
            # max_pressure: DÖRDÜ DE tabanın altında (gerçek ölçümün deseni)
            'max_pressure': [
                {'param': 'density', 'rho': 0.173, 'noise_floor': 0.324,
                 'significant': False},
                {'param': 'c_star', 'rho': 0.150, 'noise_floor': 0.324,
                 'significant': False},
                {'param': 'burn_rate_n_delta', 'rho': -0.128,
                 'noise_floor': 0.324, 'significant': False},
            ],
        }
        body['sensitivity_status'] = 'modelled'
        body['sensitivity_basis'] = ('Computed from the SAME Monte Carlo '
                                     'sample as the statistics above; 60 of '
                                     '60 samples.')
    else:
        body['sensitivity'] = {}
        body['sensitivity_status'] = 'not_modelled'
        body['sensitivity_basis'] = ('Sensitivity ranking not reported: 12 '
                                     'usable sample(s) ... noise floor 0.720')
    return body


def _yorumsuz(kaynak):
    """JS kaynağından yorumları düşürür (dize içindekilere dokunmadan).

    Basit bir durum makinesi: dize/şablon-dizesi içindeyken ``//`` ve
    ``/*`` yorum BAŞLATMAZ. Düzenli ifadeyle yapılmaz çünkü panelde
    ``'https://...'`` gibi dizeler var ve kaba bir ``//`` kuralı onları
    yorum sanıp KOD siler — o da taramayı sessizce köreltirdi.
    """
    out = []
    i, n = 0, len(kaynak)
    tirnak = None
    while i < n:
        c = kaynak[i]
        if tirnak:
            out.append(c)
            if c == '\\' and i + 1 < n:
                out.append(kaynak[i + 1])
                i += 2
                continue
            if c == tirnak:
                tirnak = None
            i += 1
            continue
        if c in ('"', "'", '`'):
            tirnak = c
            out.append(c)
            i += 1
            continue
        if c == '/' and i + 1 < n and kaynak[i + 1] == '/':
            j = kaynak.find('\n', i)
            i = n if j < 0 else j
            continue
        if c == '/' and i + 1 < n and kaynak[i + 1] == '*':
            j = kaynak.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)


@pytest.fixture(scope='module')
def panel_kodu():
    return PANEL_JS.read_text(encoding='utf-8')


@needs_node
class TestPanelCizimi:

    @pytest.fixture(scope='class')
    def olcum(self, tmp_path_factory):
        return _kos_panel(tmp_path_factory.mktemp('uq'), _yanit(),
                          ['isp', 'max_pressure'], render=True)

    def test_izler_yanit_dizilerinden_kuruluyor(self, olcum):
        """x/y dizileri yanıtın KENDİ satırlarıdır (ters sırayla)."""
        fig = olcum['figures']['isp']
        satirlar = _yanit()['sensitivity']['isp']
        trace = fig['traces'][0]
        assert trace['x'] == [r['rho'] for r in reversed(satirlar)]
        assert trace['y'] == [r['param'] for r in reversed(satirlar)]

    def test_gurultu_cubugu_sinyal_gibi_boyanmiyor(self, olcum):
        """E5'in ÇEKİRDEĞİ: tabanın altındaki çubuk sönük ve desenli."""
        fig = olcum['figures']['isp']
        trace = fig['traces'][0]
        renk = trace['marker']['color']
        desen = trace['marker']['pattern']['shape']
        # ters sıra: [density(gürültü), burn_rate_a(-), c_star(+)]
        assert renk[0] == olcum['themeHex']['dim'], (
            'gürültü çubuğu sinyal rengiyle çizilmiş')
        assert desen[0] == '.', 'gürültü çubuğunun deseni yok (renk tek taşıyıcı)'
        assert renk[1] == olcum['themeHex']['red']    # anlamlı negatif
        assert renk[2] == olcum['themeHex']['green']  # anlamlı pozitif
        assert desen[1] == '' and desen[2] == ''

    def test_gurultu_eki_metinde_de_var(self, olcum):
        """Renk körlüğü/gri baskı: hüküm metinle de taşınır (WCAG 1.4.1)."""
        trace = olcum['figures']['isp']['traces'][0]
        assert '(noise)' in trace['text'][0]
        assert '(noise)' not in trace['text'][2]
        # İşaret metinde açıkça yazıyor
        assert trace['text'][2].startswith('+')
        assert trace['text'][1].startswith('−')

    def test_tamami_gurultu_olan_cikti_hepsini_sonuk_ciziyor(self, olcum):
        """Ölçülen gerçek vaka: max_pressure'da dördü de taban altı."""
        trace = olcum['figures']['max_pressure']['traces'][0]
        assert set(trace['marker']['color']) == {olcum['themeHex']['dim']}, (
            'gürültü sıralaması güvenli bir tornado gibi gösteriliyor')
        assert set(trace['marker']['pattern']['shape']) == {'.'}

    def test_taban_cizgileri_yanittaki_degerden(self, olcum):
        sekiller = olcum['figures']['isp']['layout']['shapes']
        taban = _yanit()['sensitivity_meta']['noise_floor']
        xler = sorted(s['x0'] for s in sekiller)
        assert xler == [-taban, taban]
        assert olcum['noiseFloor'] == taban

    def test_beyan_grafikle_birlikte_geliyor(self, olcum):
        notlar = ' '.join(olcum['figures']['isp']['notes'])
        assert 'SAME Monte Carlo sample' in notlar, 'dayanak beyanı yok'
        assert 'monotonic effects only' in notlar, 'yöntem sınırı beyanı yok'
        assert '0.324' in notlar, 'gürültü tabanı beyanda yazmıyor'

    def test_cikti_seciciler_veriden(self, olcum):
        assert olcum['selectableKeys'] == ['isp', 'max_pressure']

    def test_render_beyani_dom_a_koyuyor(self, olcum):
        assert 'data-uq-sens-basis="1"' in olcum['rootHtml'], (
            'beyan bloğu DOM\'a hiç yazılmamış')
        assert 'SAME Monte Carlo sample' in olcum['rootHtml']

    def test_render_tornado_ciziyor(self, olcum):
        # histogram + tornado
        assert len(olcum['plotly']) >= 2
        yatay = [c for c in olcum['plotly']
                 if c['traces'][0].get('orientation') == 'h']
        assert len(yatay) == 1
        assert yatay[0]['traces'][0]['y'] == ['density', 'burn_rate_a',
                                              'c_star']


@needs_node
class TestPanelBosVeri:

    @pytest.fixture(scope='class')
    def olcum(self, tmp_path_factory):
        return _kos_panel(tmp_path_factory.mktemp('uq2'),
                          _yanit('not_modelled'), ['isp'], render=True)

    def test_siralama_yoksa_grafik_cizilmez(self, olcum):
        fig = olcum['figures']['isp']
        assert fig['status'] == 'not_modelled'
        assert fig['traces'] is None
        yatay = [c for c in olcum.get('plotly', [])
                 if c['traces'][0].get('orientation') == 'h']
        assert not yatay, 'sıralama yokken tornado çizilmiş (boş/sıfır çubuk)'

    def test_gerekce_ucun_kendi_metni(self, olcum):
        """Panel kendi cümlesini KURMAZ: ucun gerekçesini aynen gösterir."""
        notlar = olcum['figures']['isp']['notes']
        assert notlar[0] == _yanit('not_modelled')['sensitivity_basis']
        assert 'data-uq-sens-basis="1"' in olcum['rootHtml']

    def test_histogram_hala_ciziliyor(self, olcum):
        """Duyarlılık düşse de dağılım grafiği kaybolmamalı."""
        assert any(c['traces'][0].get('orientation') != 'h'
                   for c in olcum['plotly'])


class TestPanelKaynagi:

    def test_izlerde_sayisal_literal_yok(self, panel_kodu):
        """SAHTE SAYI TARAMASI (kalıp: test_stability_panel.py)."""
        assert re.search(r'\bx:\s*', panel_kodu), 'panelde hiç iz kurulmuyor'
        kacak = re.findall(r'\b[xyz]\s*:\s*\[\s*[-+0-9.]', panel_kodu)
        assert not kacak, f'izlere sayısal dizi literali yazılmış: {kacak}'

    def test_sabit_parametre_listesi_yok(self, panel_kodu):
        """Tornado'nun y ekseni panelin KENDİ tablosundan gelemez.

        Liste elle yazılmaz, GERÇEK modelden türetilir: bütün motor
        tiplerinin belirsiz girdi adları alınır, panelin çıktı etiketi
        tablosunda (OUTPUT_LABEL_KEYS) da geçen adlar DÜŞÜLÜR. Düşme
        gerekçesi ölçüldü: 'c_star' ve 'chamber_pressure' katı/sıvı
        modelinde girdi adı olmakla birlikte panelde ÇIKTI etiketi olarak
        meşru şekilde bulunur (insan-okunur ad + i18n anahtarı); bunları
        yasaklamak kusuru değil doğru davranışı kilitlerdi.
        """
        etiket_blogu = re.search(r'OUTPUT_LABEL_KEYS\s*=\s*\{(.*?)\n    \};',
                                 panel_kodu, re.S)
        assert etiket_blogu, 'çıktı etiketi tablosu bulunamadı (vaka değişmiş)'
        cikti_adlari = set(re.findall(r'^\s*(\w+):',
                                      etiket_blogu.group(1), re.M))
        assert 'c_star' in cikti_adlari, 'ölçüm öncülü değişmiş'

        girdi_adlari = {ad for model in DEFAULT_UQ_MODELS.values()
                        for ad in model}
        yalniz_girdi = sorted(girdi_adlari - cikti_adlari)
        assert len(yalniz_girdi) >= 6, yalniz_girdi   # tarama boşa düşmesin

        # ÖH D15 birleştirme (1 Eyl 2026) — TARAMA KODA BAKAR, YORUMA DEĞİL.
        # Bekçi ham metinde ad arıyordu ve ui-paneller a3 kulvarı (c1351d3)
        # P11B4-16 onarımının GEREKÇESİNİ panele yazınca kırmızı yandı: o
        # gerekçe ucun kendi ``consistency_note`` cümlesini AYNEN alıntılıyor
        # ("… eta_c_star: nominal 1 vs distribution mean 0.93 (-7.00%)") ve
        # cümlede parametre adı geçiyor. Alıntı bir PARAMETRE TABLOSU değil;
        # onu silmek ölçülmüş bir gerekçeyi silmek olurdu, adı kısaltmak ise
        # bekçiyi kandırmak. Kilitlenen iddia zaten koda dair: "tornado'nun
        # y ekseni panelin KENDİ tablosundan gelemez". Yorumlar bu yüzden
        # taramadan düşülür — ve düşürücünün gerçekten iş yaptığı ölçülür ki
        # bozuk bir düşürücü taramayı sessizce köreltmesin.
        kod = _yorumsuz(panel_kodu)
        assert len(kod) < len(panel_kodu), (
            'yorum düşürücü hiçbir şey silmedi — tarama körelmiş olabilir')
        assert 'OUTPUT_LABEL_KEYS' in kod, (
            'yorum düşürücü KOD sildi (vaka bozuk)')
        kacak = [ad for ad in yalniz_girdi if ad in kod]
        assert not kacak, (
            f'panelde sabit girdi parametresi adı: {kacak} — tornado '
            'yanıttan beslenmeli, panel tablosundan değil')

    @needs_node
    def test_yorum_dusurucu_KOD_silmiyor(self, panel_kodu):
        """Yukarıdaki taramanın ön koşulu: düşürücü yalnız yorumu siler.

        Bozuk bir düşürücü (ör. dize içindeki ``//`` ile yanılan kaba bir
        düzenli ifade) taramayı SESSİZCE köreltirdi: kod silinir, aranan ad
        bulunamaz, bekçi yeşil yanar. Bu yüzden düşürülmüş kaynağın hâlâ
        geçerli JavaScript olduğu ``node --check`` ile ölçülür.
        """
        import tempfile
        kod = _yorumsuz(panel_kodu)
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as f:
            f.write(kod)
            yol = f.name
        try:
            p = subprocess.run([NODE, '--check', yol], capture_output=True,
                               text=True, timeout=60)
            assert p.returncode == 0, (
                'yorum düşürücü KOD bozdu — tarama güvenilmez:\n'
                + p.stderr[-1500:])
        finally:
            os.unlink(yol)

    def test_hukum_ucdan_okunuyor(self, panel_kodu):
        assert 'row.significant' in panel_kodu, (
            'panel anlamlılık hükmünü uçtan okumuyor')
        assert 'sensitivity_status' in panel_kodu
        assert 'sensitivity_basis' in panel_kodu

    def test_tema_hex_ikizleri_theme_css_ile_ayni(self, panel_kodu):
        """Plotly düzeni var() çözmez; HEX ikizler jetonlarla KİLİTLİ."""
        css = THEME_CSS.read_text(encoding='utf-8')
        for jeton, sabit in (('--hd-green', 'GREEN_HEX'),
                             ('--hd-red', 'RED_HEX'),
                             ('--hd-ink-dim', 'INK_DIM_HEX')):
            m = re.search(re.escape(jeton) + r':\s*(#[0-9a-fA-F]{3,8})', css)
            assert m, f'{jeton} theme.css\'te yok'
            p = re.search(sabit + r"\s*=\s*'(#[0-9a-fA-F]{3,8})'", panel_kodu)
            assert p, f'{sabit} panelde tanımlı değil'
            assert p.group(1).lower() == m.group(1).lower(), (
                f'{sabit} ({p.group(1)}) theme.css {jeton} '
                f'({m.group(1)}) ile ayrışmış')

    def test_kesme_tavani_beyanli(self, panel_kodu):
        assert 'TORNADO_MAX_BARS' in panel_kodu
        assert 'tornadoTruncated' in panel_kodu, (
            'çubuk kesmesi sessiz — kaç parametrenin gizlendiği yazılmıyor')


@needs_node
def test_kesme_beyani_gercekten_tetikleniyor(tmp_path):
    """Tavandan fazla parametre gelince kaç tanesinin gizlendiği YAZILIR."""
    data = _yanit()
    data['sensitivity']['isp'] = [
        {'param': f'p{i}', 'rho': 0.9 - 0.05 * i, 'noise_floor': 0.324,
         'significant': True} for i in range(9)
    ]
    out = _kos_panel(tmp_path, data, ['isp'])
    trace = out['figures']['isp']['traces'][0]
    assert len(trace['x']) == out['maxBars']
    notlar = ' '.join(out['figures']['isp']['notes'])
    assert str(out['maxBars']) in notlar and '9' in notlar, notlar


@needs_node
def test_eski_cekirdek_hukum_gondermezse_taban_ile_karar(tmp_path):
    """Geriye dönüklük: 'significant' alanı yoksa taban ile karşılaştırılır
    (panel yine de kendi eşiğini uydurmaz — taban yanıttan gelir)."""
    data = _yanit()
    for row in data['sensitivity']['isp']:
        row.pop('significant')
    out = _kos_panel(tmp_path, data, ['isp'])
    renk = out['figures']['isp']['traces'][0]['marker']['color']
    # ters sıra: density |0.155| < 0.324 -> sönük
    assert renk[0] == out['themeHex']['dim']
    assert renk[2] == out['themeHex']['green']
