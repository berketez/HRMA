"""Parametreli i18n rozetlerinin applyTo tarafından EZİLMEMESİ (2026-08-18).

ÖLÇÜLEN KUSUR (canlı Playwright turunda, parti 32)
--------------------------------------------------
Analiz Merkezi hüküm rozeti ``verdictBadge`` TF ile DOĞRU basılıyordu
("CONVERGED (13847 iterations)"), ama ``badge()`` span'a
``data-i18n="panel.cfd.verdictConverged"`` yazdığı için hemen ardından
çağrılan ``I18N.applyTo`` düğümü PARAMETRESİZ ``t(key)`` ile yeniden
yazıp ekrana çiğ ``CONVERGED ({iters} iterations)`` şablonunu basıyordu.
Koşum kartında ve geçmiş şeridinde iki kopya halinde görüldü.

Bu, parti 28'in "{yer_tutucu} şablon kuralı"nın DOM katmanındaki ikizi:
parametreli şablon, parametresi olmadan kullanıcıya BASILMAZ.

KAPANIŞ (iki bacak)
-------------------
1. ``i18n.js`` / ``translateElement``:
   * ``data-i18n-params`` (JSON) desteği — varsa ``tf`` aynı
     parametrelerle doldurur (dil değişiminde de).
   * Ezme koruması — params YOKSA ve çeviri hâlâ ``{yer_tutucu}``
     taşıyorsa mevcut metin KORUNUR (title/placeholder dahil).
2. ``analysis_center.js`` / ``badge()`` + ``verdictBadge``:
   parametreli hüküm params'ını ``data-i18n-params`` ile taşır.

Buradaki testler kusuru YAKALAYAN bekçilerdir: düzeltme geri alınırsa
(translateElement parametresiz t'ye dönerse ya da badge params'ı
taşımazsa) kırmızıya dönerler. Harness GERÇEK ``i18n.js`` +
``i18n_common.js`` sözlüklerini ve ``analysis_center.js``'in GERÇEK
``badge`` fonksiyonunu koşturur — Python kopyası yoktur.

Node çağrıları tests/test_node_cagri_sozlesmesi.py sözleşmesine uyar:
betik argv'ye değil DOSYA yoluyla verilir.
"""

import json
import pathlib
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
I18N_JS = STATIC_JS / 'i18n.js'
I18N_COMMON_JS = STATIC_JS / 'i18n_common.js'
CENTER_JS = STATIC_JS / 'analysis_center.js'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

# Canlı turda ölçülen gerçek vaka: bu anahtar + bu parametre.
VERDICT_KEY = 'panel.cfd.verdictConverged'
ITERS = 13847

HARNESS = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');

const staticDir = process.argv[2];

// ---- Gerçek i18n katmanı, sahte pencereyle -------------------------------
const sandbox = {};
sandbox.window = sandbox;           // i18n.js IIFE'si window'a yazar
sandbox.console = console;
vm.createContext(sandbox);
for (const f of ['i18n.js', 'i18n_common.js']) {
    vm.runInContext(fs.readFileSync(staticDir + '/' + f, 'utf8'),
                    sandbox, { filename: f });
}
const I18N = sandbox.I18N || (sandbox.window && sandbox.window.I18N);
if (!I18N) { console.log(JSON.stringify({err: 'I18N yuklenemedi'})); process.exit(1); }
I18N.setLang('en');

// ---- analysis_center.js'in GERÇEK badge zinciri --------------------------
// IIFE'den dört yardımcıyı kaynak-kesitiyle çıkar (kopya mantık yazılmaz).
const centerSrc = fs.readFileSync(staticDir + '/analysis_center.js', 'utf8');
function slice(marker) {
    const start = centerSrc.indexOf(marker);
    if (start < 0) throw new Error('bulunamadi: ' + marker);
    let depth = 0;
    for (let i = start; i < centerSrc.length; i++) {
        const ch = centerSrc[i];
        if (ch === '{') depth++;
        else if (ch === '}') {
            depth--;
            if (depth === 0) return centerSrc.slice(start, i + 1);
        }
    }
    throw new Error('kapanmiyor: ' + marker);
}
function sliceConst(name) {
    const m = centerSrc.match(new RegExp('const ' + name + ' = \\{'));
    if (!m) throw new Error('sabit yok: ' + name);
    const start = centerSrc.indexOf(m[0]);
    let depth = 0;
    for (let i = start; i < centerSrc.length; i++) {
        if (centerSrc[i] === '{') depth++;
        else if (centerSrc[i] === '}') {
            depth--;
            if (depth === 0) return centerSrc.slice(start, i + 2); // '};'
        }
    }
    throw new Error('sabit kapanmiyor: ' + name);
}
const badgeScope = {};
vm.createContext(badgeScope);
vm.runInContext(
    sliceConst('COLORS') + '\n'
    + slice('function kindColor') + '\n'
    + slice('function esc(') + '\n'
    + slice('function i18nAttr') + '\n'
    + slice('function badge') + '\n'
    + 'this.badge = badge;\n',
    badgeScope, { filename: 'badge-kesiti.js' });

// Gerçek badge çıktısı: TF ile DOLU metin + parametreli anahtar + params.
const filledEN = 'CONVERGED (13847 iterations)';
const html = badgeScope.badge(filledEN, 'ok', '', 'panel.cfd.verdictConverged',
                              { iters: 13847 });

// ---- span HTML'ini sahte DOM düğümüne çevir ------------------------------
function unesc(v) {
    return v.replace(/&quot;/g, '"').replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}
function parseSpan(spanHtml) {
    const attrs = {};
    const re = /([a-zA-Z0-9-]+)="([^"]*)"/g;
    let m;
    while ((m = re.exec(spanHtml)) !== null) attrs[m[1]] = unesc(m[2]);
    const inner = spanHtml.replace(/^[^>]*>/, '').replace(/<\/span>$/, '');
    return { attrs, text: unesc(inner) };
}
function fakeEl(attrs, text) {
    return {
        nodeType: 1,
        textContent: text,
        _attrs: Object.assign({}, attrs),
        getAttribute(k) {
            return Object.prototype.hasOwnProperty.call(this._attrs, k)
                ? this._attrs[k] : null;
        },
        setAttribute(k, v) { this._attrs[k] = String(v); },
        querySelectorAll() { return []; },
    };
}
const parsed = parseSpan(html);
const rozet = fakeEl(parsed.attrs, parsed.text);

// Kök: applyTo(root) çocukları querySelectorAll ile bulur.
const root = {
    nodeType: 1,
    getAttribute() { return null; },
    setAttribute() {},
    querySelectorAll() { return [rozet, ciplak]; },
};

// Params TAŞIMAYAN eski-tip düğüm (ezme koruması vakası): TF ile doldurulmuş
// metin + parametreli anahtar, data-i18n-params YOK.
const ciplak = fakeEl({ 'data-i18n': 'panel.cfd.verdictConverged' }, filledEN);

const out = { htmlAttrs: parsed.attrs };

// 1) applyTo (EN): iki düğümde de çiğ şablon YASAK.
I18N.applyTo(root);
out.en_rozet = rozet.textContent;
out.en_ciplak = ciplak.textContent;

// 2) Dil değişimi: params taşıyan rozet TR şablonuyla YENİDEN dolmalı.
I18N.setLang('tr');
I18N.applyTo(root);
out.tr_rozet = rozet.textContent;
out.tr_ciplak = ciplak.textContent;

console.log(JSON.stringify(out));
"""


def _kosum(tmp_path):
    harness = tmp_path / 'harness_param_rozet.js'
    harness.write_text(HARNESS, encoding='utf-8')
    proc = subprocess.run([NODE, str(harness), str(STATIC_JS)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr[:1200]
    return json.loads(proc.stdout.strip().splitlines()[-1])


@needs_node
def test_badge_paramlari_oznitelikle_tasiyor(tmp_path):
    """Gerçek badge() çıktısı data-i18n-params taşır ve JSON'u geçerlidir."""
    out = _kosum(tmp_path)
    attrs = out['htmlAttrs']
    assert attrs.get('data-i18n') == VERDICT_KEY
    params = json.loads(attrs['data-i18n-params'])
    assert params == {'iters': ITERS}


@needs_node
def test_applyto_parametreli_rozeti_cig_sablona_cevirmiyor(tmp_path):
    """KUSURUN KENDİSİ: applyTo sonrası ekranda {iters} kalamaz.

    Düzeltme öncesi bu metin 'CONVERGED ({iters} iterations)' oluyordu
    (canlı ölçüm). params yolu tf ile doldurur; ezme koruması olmayan
    eski-tip düğümde de dolu metin korunur.
    """
    out = _kosum(tmp_path)
    assert '{iters}' not in out['en_rozet'], out
    assert '13847' in out['en_rozet'], out
    assert '{iters}' not in out['en_ciplak'], out
    assert '13847' in out['en_ciplak'], out


@needs_node
def test_dil_degisiminde_params_yeniden_doluyor(tmp_path):
    """setLang('tr') sonrası params taşıyan rozet TR şablonuyla DOLU basılır;
    params taşımayan düğüm ezilmez (eski dilde dolu kalması kabul, çiğ
    şablon kabul DEĞİL)."""
    out = _kosum(tmp_path)
    assert '{iters}' not in out['tr_rozet'], out
    assert '13847' in out['tr_rozet'], out
    assert 'YAKINSADI' in out['tr_rozet'], out
    assert '{iters}' not in out['tr_ciplak'], out


def test_mekanizma_kaynakta_duruyor():
    """Yapısal bekçi: iki bacağın kaynak izleri. (Davranışı yukarıdaki
    node testleri ölçer; bu test yalnız 'yanlışlıkla söküldü' vakasını
    isimle yakalar.)"""
    i18n_src = I18N_JS.read_text(encoding='utf-8')
    assert 'data-i18n-params' in i18n_src, \
        'translateElement params desteği söküldü'
    assert 'hasBarePlaceholder' in i18n_src, \
        'çiğ şablon ezme koruması söküldü'
    center_src = CENTER_JS.read_text(encoding='utf-8')
    assert 'data-i18n-params' in center_src, \
        'badge() params özniteliğini yazmıyor'
    assert center_src.count("v.params || null") >= 1, \
        'verdictBadge params\'ı badge\'e geçirmiyor'
