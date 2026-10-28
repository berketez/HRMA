"""V301/KABUL — baştan sona kabul testinin (yayın kapısı) yardımcıları.

Berke (26 Eki): "bu test geçmeden yayın yok". 3.0.0'ın doğrulaması kodun
bugünkü çıktısını kilitledi; kullanıcı yolculuğunu ve paneller arası
tutarlılığı ölçmedi (hafıza: feedback-yayin-kapilari-v301). Bu modül o
yolculuğu kurar: örnek proje → sayfanın gönderdiği yük → ana hesap →
arayüzün çağırdığı panel uçları → dışa aktarımlar.

İLKELER
-------
* Yük UYDURULMAZ. Ana hesap yükü GERÇEK sayfanın gövdesidir (tarayıcı
  hasadı ``tests.support.kabul_sayfa_yukleri``; tazeliğini kabul_ui düğümü
  U1 bekler). Panel yükleri
  panellerin KENDİ JS kodundan (``fields`` + ``fromResults``) node vm'de
  üretilir: güverte (``analysis_dock.js::buildPayload``) ve Analiz Merkezi
  (``analysis_center.js::readForm`` + ``spec.body``) kurallarının aynası.
  Dışa aktarım yükleri şablonların gövde kurucularının satır satır aynasıdır
  (kaynak satırı her kurucunun yanında yazılı); arayüz testi (kabul_ui)
  gerçek sayfanın gönderdiği gövdeyi bu aynayla karşılaştırır.
* Kırmızı gizlenmez: bu modül hiçbir bulguyu süzmez; yalnız TOPLAR.
* Ürün koduna dokunulmaz (hrma/** salt okunur).
"""

from __future__ import annotations

import copy
import io
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import zipfile
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATIC_JS = ROOT / 'hrma' / 'static' / 'js'
TEMPLATES = ROOT / 'hrma' / 'templates'
KANIT = ROOT / 'docs' / 'scofield' / 'raw' / 'OH' / 'V301' / 'kabul'

#: Uygulama yalnız geri döngü Host başlığına yanıt verir (DNS-rebinding
#: kapısı) — tests/test_example_projects.HEADERS ile aynı (tek kaynak orası).
def headers() -> Dict[str, str]:
    from tests.test_example_projects import HEADERS
    return dict(HEADERS)


#: Üç örnek (motor_type). Sıra raporda da bu sırayla basılır.
#: V3.0.5 T-ÇAPA-C1: üyelik merkezden (hrma.constants.MOTOR_TYPES — tek tanım
#: noktası, tests/test_sabit_tek_kaynak.py); yalnız rapor SIRASI burada.
from hrma.constants import MOTOR_TYPES as _MOTOR_TYPES  # noqa: E402
MOTORLAR: Tuple[str, ...] = tuple(sorted(
    _MOTOR_TYPES, key=lambda m: (m != 'solid', m != 'liquid')))

def sablon_yolu(motor_type: str) -> pathlib.Path:
    """Sayfa şablonu — tek kaynak ``tests.support.inventory.PAGES``."""
    from tests.support import inventory
    return TEMPLATES / inventory.PAGES[motor_type][0]

#: Geçici dosya kökü (ORTAK: /tmp YASAK; kalıcı diskte, kulvar dizini).
CALISMA = pathlib.Path(os.path.expanduser(
    '~/HRMA-calisma/2026-10-27/KABUL'))


# ---------------------------------------------------------------------------
# Örnek proje + sayfanın gönderdiği yük
# ---------------------------------------------------------------------------
def ornek_belgesi(motor_type: str) -> Dict:
    from tests.test_example_projects import load_example_doc
    return load_example_doc(motor_type)


def sayfa_yuku(motor_type: str) -> Dict:
    """Örnek ``?project=`` ile açılıp Hesapla'ya basılınca GERÇEK sayfanın
    gönderdiği gövde (tarayıcıdan hasat: ``tests.support.kabul_sayfa_yukleri``;
    tazeliği ``test_v301_kabul_ui::test_u1_*`` bekler).

    Şablon varsayılanı aynası (``form_defaults.form_yuku``) KULLANILMAZ:
    27 Eki ölçümünde üç örneğin üçünde de gerçek gövdeden saptı (ayrıntı
    hasat modülünün belgesinde).
    """
    from tests.support.kabul_sayfa_yukleri import SAYFA_YUKLERI
    return copy.deepcopy(SAYFA_YUKLERI[motor_type])


def ayna_yuku(motor_type: str) -> Dict:
    """Karşılaştırma için şablon-varsayılanı aynası (form_yuku)."""
    from tests.support.form_defaults import form_yuku
    return form_yuku(motor_type, ornek_belgesi(motor_type)['inputs']['fields'])


def hesap_ucu(motor_type: str) -> str:
    from tests.test_example_projects import ENDPOINTS
    return ENDPOINTS[motor_type]


def post(client, yol: str, govde: Any):
    """POST + (durum, gövde-json|None, ham bayt, içerik türü)."""
    resp = client.post(yol, json=govde, headers=headers())
    ham = resp.get_data()
    tur = resp.headers.get('Content-Type', '')
    js = None
    if 'json' in tur:
        try:
            js = json.loads(ham.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            js = None
    return resp.status_code, js, ham, tur


# ---------------------------------------------------------------------------
# Kritik bayrak + ret
# ---------------------------------------------------------------------------
def _kritik_mi(o: Dict) -> bool:
    """Sözlükte 'critical' değerli bir ŞİDDET alanı var mı?

    Okunan alanlar: ``severity``, ``level`` ve ``*_severity`` adlı her alan
    (yeni bir şiddet alanı adı yüzünden kritik kaçmasın). Hüküm OLMAYAN
    şiddet alanları ADIYLA dışarıda kalır (``HUKUM_OLMAYAN_SIDDET_ALANLARI``).
    """
    for k, v in o.items():
        if not isinstance(k, str):
            continue
        if k in HUKUM_OLMAYAN_SIDDET_ALANLARI:
            continue
        if k in ('severity', 'level') or k.endswith('_severity'):
            if isinstance(v, str) and v.lower() == 'critical':
                return True
    return False


def kritikler(obj: Any, yol: str = '') -> List[Dict]:
    """Yanıttaki HER kritik şiddet kaydı (yol + kod + param).

    ``severity``/``level``/``*_severity`` alanları okunur (``_kritik_mi``);
    ``consequence_severity`` (arıza listesinin sonuç ağırlığı) ve
    ``bare_wall_severity`` (çıplak cidar olsaydı ne olurdu) gibi hüküm
    olmayan alanlar ADIYLA dışarıda kalır. Aynı kod+param birden çok yerde
    (ör. openrocket ayna bloğu) çıkarsa tek kayıt + yol listesi.
    """
    bulunan: Dict[str, Dict] = {}

    def gez(o, p):
        if isinstance(o, dict):
            if _kritik_mi(o) and not _hukum_degil(p):
                kod = o.get('code') or o.get('id') or o.get('type') or ''
                par = o.get('params')
                anahtar = json.dumps([kod, par, o.get('message')],
                                     sort_keys=True, default=str)
                kayit = bulunan.setdefault(anahtar, {
                    'code': kod, 'params': par,
                    'message': (o.get('message') or o.get('fallback')
                                or '')[:300],
                    'paths': []})
                kayit['paths'].append(p)
            for k, v in o.items():
                gez(v, p + '.' + str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                gez(v, p + '[%d]' % i)

    gez(obj, yol)
    return list(bulunan.values())


#: Hüküm OLMAYAN şiddet ALANLARI (alan adı → gerekçe). ``_kritik_mi`` bu
#: adları okumaz; liste dışı her 'critical' şiddet alanı bayraktır.
#: V301/FİZİK-2 (27 Eki, PANEL DEVİR 5): PANEL arıza kipi listesindeki
#: ``severity`` alanını ``consequence_severity`` olarak yeniden adlandırdı
#: (hrma/analysis/safety_analysis.py ``failure_modes``). Değer FMEA sonuç
#: ağırlığıdır — "bu kip gerçekleşirse sonucu ne kadar ağır olur" — ve her
#: motorda aynı genel basınçlı kap kontrol listesidir
#: (``failure_modes_basis``). Hüküm ``structural_integrity``dir; panel listeyi
#: "hüküm değildir" notuyla basar. Bu yüzden kritik sayılmaz.
HUKUM_OLMAYAN_SIDDET_ALANLARI = {
    'consequence_severity':
        'arıza kipi listesinin SONUÇ AĞIRLIĞI (FMEA), hüküm değil; hüküm '
        'structural_integrity — PANEL 27 Eki severity → consequence_severity '
        '(DEVİR 2/5), ÖRNEK-PANEL notu',
    'bare_wall_severity':
        'çıplak cidar olsaydı kaydın şiddeti ne olurdu (betimleyici künye; '
        'kaydın kendi şiddeti severity: info) — bayrak değil',
}

#: Hüküm OLMAYAN 'critical' kayıtları (yol deseni → gerekçe). v3.0.5 öncesi
#: şema: arıza kipi ağırlığı ``failure_modes[i].severity`` adını taşıyordu
#: (kayıtlı eski yanıtlar için korunur; bugünkü şemada alan
#: ``consequence_severity``dir ve yukarıda adıyla dışarıdadır).
HUKUM_OLMAYAN_KRITIK = {
    r'\.structural_safety\.failure_modes\[\d+\]$':
        'arıza kipi listesinin sonuç ağırlığı (FMEA), hüküm değil — '
        'v3.0.5 öncesi şema (severity); bugün consequence_severity',
}


def _hukum_degil(yol: str) -> bool:
    return any(re.search(d, yol) for d in HUKUM_OLMAYAN_KRITIK)


#: Gövdede ret anlamı taşıyan durum değerleri.
RET_DURUMLARI = ('error', 'rejected', 'refused', 'failed')


def ret_nedeni(durum: int, govde: Any) -> Optional[str]:
    """Ret ise kısa neden; değilse None (200 + hata/ret işareti yok)."""
    if durum != 200:
        ozet = ''
        if isinstance(govde, dict):
            ozet = str(govde.get('error') or govde.get('status')
                       or govde.get('message') or '')[:240]
        return 'HTTP %d %s' % (durum, ozet)
    if isinstance(govde, dict):
        if govde.get('error'):
            return 'error=%s' % str(govde.get('error'))[:240]
        st = govde.get('status')
        if isinstance(st, str) and st.lower() in RET_DURUMLARI:
            return 'status=%s %s' % (st, str(govde.get('message', ''))[:200])
        if govde.get('rejected') is True:
            return 'rejected=True %s' % str(govde.get('reason', ''))[:200]
    return None


# ---------------------------------------------------------------------------
# Sessiz ikame: gönderilen alan yanıtta AYNI adla FARKLI değerle mi?
# ---------------------------------------------------------------------------
def _beyanli_alanlar(sonuc: Dict) -> set:
    """Sunucunun ADIYLA beyan ettiği alanlar (ikame/okunmama/varsayılan)."""
    ad = set()
    kaynaklar = [sonuc]
    if isinstance(sonuc.get('motor'), dict):
        kaynaklar.append(sonuc['motor'])
    for s in kaynaklar:
        for blok in ('inputs_not_used', 'defaults_applied'):
            for kayit in (s.get(blok) or []):
                if isinstance(kayit, dict) and kayit.get('field'):
                    ad.add(str(kayit['field']))
        un = s.get('unwired_inputs')
        if isinstance(un, dict):
            for liste in un.values():
                if isinstance(liste, list):
                    ad.update(str(x) for x in liste)
        for w in (s.get('input_warnings') or []):
            if isinstance(w, dict):
                f = (w.get('params') or {}).get('field')
                if f:
                    ad.add(str(f))
    return ad


def sessiz_ikameler(motor_type: str, yuk: Dict, sonuc: Dict) -> List[Dict]:
    """Gönderilen sayı alanı yanıtın aynı anahtarında farklı değerle duruyor
    ve ne ``inputs_not_used``/``defaults_applied``/``unwired_inputs``/
    ``input_warnings`` ne de ``<alan>_basis``/``_source`` ile beyanlı DEĞİL.

    Kural beyanlıdır ve dardır: yalnız aynı ad, yalnız sayı; birim farkı
    (mm ⟷ m) da beyansızsa bulgudur — yanıt anahtarı girdiyle aynı adı
    taşıyıp başka birimde başka sayı söylüyorsa kullanıcı onu ayırt edemez.
    """
    hedef = sonuc['motor'] if motor_type == 'hybrid' else sonuc
    beyan = _beyanli_alanlar(sonuc)
    out = []
    for k, v in yuk.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        w = hedef.get(k)
        if isinstance(w, bool) or not isinstance(w, (int, float)):
            continue
        if math.isclose(float(v), float(w), rel_tol=1e-9, abs_tol=1e-12):
            continue
        if k in beyan:
            continue
        if any((k + ek) in hedef for ek in ('_basis', '_source', '_kunye')):
            continue
        out.append({'field': k, 'sent': v, 'response': w})
    return out


# ---------------------------------------------------------------------------
# Panel yükleri: panellerin KENDİ JS kodu node vm'de
# ---------------------------------------------------------------------------
NODE = shutil.which('node')

#: Güverte/merkez kurallarının AYNASI. Kaynak:
#:   analysis_dock.js  fieldHtml (seçici ilk değeri: o[0] === defVal, yoksa
#:                     ilk seçenek), applySuggestions (sayı → toPrecision(6);
#:                     seçici → yalnız listedeyse, değilse HRMAMaterials
#:                     kanonik eşlemesi, o da yoksa KOŞUM DURUR),
#:                     requiredFieldInfo (sonlu varsayılan ya da
#:                     spec.required → zorunlu), buildPayload, runPanel
#:                     (boş gövde + allowsEmptyPayload yok → gönderilmez).
#:   analysis_center.js applySuggestions (seçici listede yoksa alan
#:                     DEĞİŞMEZ ve istek varsayılanla GİDER), readForm,
#:                     run (spec.body(formValues, results)), applicability.
GUVERTE_JS = r"""
'use strict';
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const inp = JSON.parse(fs.readFileSync(0, 'utf8'));
const staticDir = inp.staticDir, motorType = inp.motorType;
const results = inp.results, catalog = inp.materials || {materials: {}, aliases: {}};
function El(tag) { this.tagName = String(tag || 'div').toUpperCase(); this.children = [];
  this.style = {}; this.dataset = {}; this._attrs = {}; this.textContent = ''; this.innerHTML = '';
  this.disabled = false; this.value = ''; this.options = []; this._listeners = {};
  this.parentNode = null; this.hidden = false; this.checked = false;
  this.classList = {contains() { return false; }, add() {}, remove() {}, toggle() {}}; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.insertBefore = function (c) { this.children.push(c); return c; };
El.prototype.remove = function () {}; El.prototype.removeChild = function () {};
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) { return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null; };
El.prototype.hasAttribute = function (k) { return Object.prototype.hasOwnProperty.call(this._attrs, k); };
El.prototype.removeAttribute = function (k) { delete this._attrs[k]; };
El.prototype.addEventListener = function (t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); };
El.prototype.removeEventListener = function () {};
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.closest = function () { return null; };
El.prototype.insertAdjacentHTML = function () {};
El.prototype.contains = function () { return false; };
El.prototype.dispatchEvent = function () { return true; };
El.prototype.getBoundingClientRect = function () { return {left: 0, top: 0, width: 0, height: 0, right: 0, bottom: 0}; };
const byId = {};
function getEl(id) { if (!byId[id]) byId[id] = new El('div'); return byId[id]; }
const docListeners = [];
const documentStub = {head: new El('head'), body: new El('body'), documentElement: new El('html'),
  readyState: 'complete', createElement(t) { return new El(t); }, createTextNode() { return new El('#text'); },
  createDocumentFragment() { return new El('frag'); }, querySelector() { return null; },
  querySelectorAll() { return []; }, getElementById: getEl,
  addEventListener(t, fn) { docListeners.push([t, fn]); }, removeEventListener() {}};
const store = {};
const sandbox = {console: {log() {}, warn() {}, error() {}, info() {}, debug() {}},
  setTimeout() { return 0; }, clearTimeout() {}, setInterval() { return 0; }, clearInterval() {},
  requestAnimationFrame() { return 0; },
  // Yalnız /api/materials yanıtlanır (materials_catalog.js'in load()'u);
  // başka her istek ASILI kalır — harness sunucuya gitmez.
  fetch(url) { if (String(url).indexOf('/api/materials') !== -1) { return Promise.resolve({ok: true, status: 200,
      json() { return Promise.resolve(catalog); }, text() { return Promise.resolve(JSON.stringify(catalog)); }}); }
    return new Promise(function () {}); },
  JSON, Math, Number, Array, Object, String, Boolean, Promise, Error, TypeError, RangeError, RegExp,
  Date, Map, Set, WeakMap, Symbol, Intl, isFinite, isNaN, parseFloat, parseInt,
  encodeURIComponent, decodeURIComponent, document: documentStub,
  navigator: {language: 'en', userAgent: 'node'},
  location: {search: '', pathname: '/' + motorType, href: 'http://127.0.0.1/' + motorType, hash: ''},
  localStorage: {getItem(k) { return store[k] || null; }, setItem(k, v) { store[k] = String(v); }, removeItem(k) { delete store[k]; }},
  sessionStorage: {getItem() { return null; }, setItem() {}, removeItem() {}},
  addEventListener(t, fn) { docListeners.push([t, fn]); }, removeEventListener() {},
  matchMedia() { return {matches: false, addEventListener() {}, addListener() {}}; },
  getComputedStyle() { return {getPropertyValue() { return ''; }}; }, performance: {now() { return 0; }},
  CustomEvent: function () {}, Event: function () {},
  MutationObserver: function () { this.observe = function () {}; this.disconnect = function () {}; },
  ResizeObserver: function () { this.observe = function () {}; this.disconnect = function () {}; },
  IntersectionObserver: function () { this.observe = function () {}; this.disconnect = function () {}; },
  Node: {TEXT_NODE: 3, ELEMENT_NODE: 1}, NodeFilter: {SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2}};
sandbox.window = sandbox; sandbox.globalThis = sandbox; sandbox.self = sandbox;
// HRMAMaterials YALNIZ sayfa materials_catalog.js yüklüyorsa vardır (katı
// sayfası); sıvı/hibrit sayfalarında tarayıcıda da TANIMSIZDIR ve paneller
// kendi yedek seçenek listeleriyle kalır (typeof korumaları).
vm.createContext(sandbox);
const yukleme = {};
const dockSpecs = [], centerSpecs = [];
function sar() {
  const AD = sandbox.window.AnalysisDock;
  if (AD && !AD.__kabul) { const o = AD.register; AD.register = function (s) { dockSpecs.push(s); return o.call(AD, s); }; AD.__kabul = true; }
  const AC = sandbox.window.AnalysisCenter;
  if (AC && !AC.__kabul) { const o = AC.register; AC.register = function (s) { centerSpecs.push(s); return o.call(AC, s); }; AC.__kabul = true; }
}
for (const f of inp.files) {
  try { vm.runInContext(fs.readFileSync(path.join(staticDir, f), 'utf8'), sandbox, {filename: f}); yukleme[f] = 'ok'; }
  catch (e) { yukleme[f] = 'HATA: ' + String(e && e.message || e).slice(0, 300); }
  sar();
}
try { if (sandbox.window.AnalysisDock) sandbox.window.AnalysisDock.init({anchorId: 'x', motorType: motorType, resultsProvider() { return results; }}); } catch (e) { yukleme['AnalysisDock.init'] = 'HATA: ' + String(e && e.message || e).slice(0, 300); }
try { if (sandbox.window.AnalysisCenter) sandbox.window.AnalysisCenter.init({anchorId: 'y', motorType: motorType, resultsProvider() { return results; }}); } catch (e) { yukleme['AnalysisCenter.init'] = 'HATA: ' + String(e && e.message || e).slice(0, 300); }
for (const [t, fn] of docListeners.slice()) {
  if (t === 'DOMContentLoaded' || t === 'load') { try { fn({}); } catch (e) {} }
  sar();
}
(async function () {
for (let i = 0; i < 20; i++) { await new Promise(r => setImmediate(r)); }
function sig(v) { const x = Number(v); if (!Number.isFinite(x) || x === 0) return x; return Number(x.toPrecision(6)); }
function ilkDeger(f) {
  const def = f[2], step = f[3];
  if (Array.isArray(step)) { const s = step.filter(o => o[0] === def)[0] || (step.length ? step[0] : null);
    return {select: true, value: s ? String(s[0]) : '', options: step.map(o => String(o[0]))}; }
  return {select: false, value: (def === undefined || def === null) ? '' : String(def)};
}
function kur(spec, tur) {
  const out = {kind: tur, id: spec.id || (spec.componentId + '/' + spec.analysisId),
    endpoint: spec.endpoint, title: spec.title || '', motorTypes: spec.motorTypes || null,
    applies: !spec.motorTypes || spec.motorTypes.indexOf(motorType) !== -1,
    payload: {}, missing: [], blocked: {}, fallback_sent: {}, suggested: [], defaulted: [],
    withheld: {}, errors: [], allowsEmptyPayload: spec.allowsEmptyPayload === true,
    fields: (spec.fields || []).map(f => f[0])};
  if (!out.applies) return out;
  if (tur === 'center' && typeof spec.applicability === 'function') {
    try { const v = spec.applicability(results); out.applicability = v;
      if (v && v.ok === false) { out.applies = false; return out; } }
    catch (e) { out.errors.push('applicability: ' + String(e && e.message || e)); out.applies = false; return out; }
  }
  const alan = {};
  (spec.fields || []).forEach(f => { alan[f[0]] = ilkDeger(f); });
  let sug = null;
  if (typeof spec.fromResults === 'function') {
    try { sug = spec.fromResults(results); } catch (e) { out.errors.push('fromResults: ' + String(e && e.message || e)); }
  }
  if (sug && typeof sug === 'object') {
    const ger = (sug.__withheld && typeof sug.__withheld === 'object') ? sug.__withheld : {};
    Object.keys(sug).forEach(k => {
      if (k === '__withheld') return;
      const el = alan[k]; if (!el) return;
      const v = sug[k];
      if (el.select) {
        if (v == null) return;
        const want = String(v);
        if (el.options.indexOf(want) !== -1) { el.value = want; out.suggested.push(k); return; }
        if (tur === 'dock') {
          const HM = sandbox.window.HRMAMaterials;
          const kanon = (HM && typeof HM.resolve === 'function') ? HM.resolve(want) : null;
          if (kanon) { for (const o of el.options) { if (HM.resolve(o) === kanon) { el.value = o; out.suggested.push(k); return; } } }
          out.blocked[k] = {solver: want, sent: el.value};
        } else {
          out.fallback_sent[k] = {solver: want, sent: el.value};
        }
        return;
      }
      if (typeof v === 'number' && Number.isFinite(v)) {
        el.value = String(sig(v));
        if (ger[k]) out.withheld[k] = String(ger[k]); else out.suggested.push(k);
      }
    });
  }
  const zorunlu = {};
  if (Array.isArray(spec.required)) spec.required.forEach(k => { zorunlu[k] = true; });
  (spec.fields || []).forEach(f => {
    const k = f[0], el = alan[k];
    const opt = !(typeof f[2] === 'number' && Number.isFinite(f[2])) && !(tur === 'dock' && zorunlu[k]);
    if (out.suggested.indexOf(k) === -1) out.defaulted.push(k);
    if (el.select) {
      if (el.value === '' && !opt && tur === 'dock') { out.missing.push(k); return; }
      out.payload[k] = el.value; return;
    }
    const x = parseFloat(el.value);
    if (Number.isFinite(x)) { out.payload[k] = x; return; }
    if (!opt) out.missing.push(k);
  });
  if (tur === 'center' && typeof spec.body === 'function') {
    try { out.payload = spec.body(JSON.parse(JSON.stringify(out.payload)), results); }
    catch (e) { out.errors.push('body: ' + String(e && e.message || e)); }
  }
  // V301/T-ÇAPA-D (kalem 3; FİZİK-2 DEVİR 4a, ÖRNEK DEVİR 2): sayfanın
  // runPanel'i (analysis_dock.js, V301/PANEL NK-18) gövde kurulduktan ve
  // zorunlu alan / malzeme engeli yoksa panelin form DIŞI bağlamını
  // (spec.contextFromResults: güvenlik + yapısal panelinde motorun hüküm
  // bloğu — motor_result, motor_verdict_inputs) gövdeye ekler; aynı ad
  // varsa form alanı kazanır, null/undefined gönderilmez. Ayna bunu
  // üretmiyordu: U2 ×3 ve K2 [hybrid] kırmızısı ayna kaynaklıydı.
  if (tur === 'dock' && typeof spec.contextFromResults === 'function'
      && !out.missing.length && !Object.keys(out.blocked).length) {
    let baglam = null;
    try { baglam = spec.contextFromResults(results); } catch (e) { baglam = null; }
    if (baglam && typeof baglam === 'object') {
      Object.keys(baglam).forEach(k => {
        if (!Object.prototype.hasOwnProperty.call(out.payload, k)
            && baglam[k] !== undefined && baglam[k] !== null) {
          out.payload[k] = baglam[k];
        }
      });
    }
  }
  if (tur === 'dock' && !Object.keys(out.payload).length && !out.allowsEmptyPayload) out.own_controls_only = true;
  return out;
}
const cikti = {yukleme: yukleme, specs: []};
for (const s of dockSpecs) { try { cikti.specs.push(kur(s, 'dock')); } catch (e) { cikti.specs.push({kind: 'dock', id: s.id, endpoint: s.endpoint, errors: [String(e)]}); } }
for (const s of centerSpecs) { try { cikti.specs.push(kur(s, 'center')); } catch (e) { cikti.specs.push({kind: 'center', id: s.componentId + '/' + s.analysisId, endpoint: s.endpoint, errors: [String(e)]}); } }
cikti.hrmaMaterials = !!sandbox.window.HRMAMaterials;
process.stdout.write(JSON.stringify(cikti));
})();
"""


def sayfa_scriptleri(motor_type: str) -> List[str]:
    """Sayfanın yüklediği /static/js dosyaları (şablondaki sırayla)."""
    html = sablon_yolu(motor_type).read_text(encoding='utf-8')
    return re.findall(r'src="/static/js/([^"?]+)', html)


def guverte_yukleri(motor_type: str, sonuc: Dict, malzeme_katalogu: Dict
                    ) -> Dict:
    """Sayfanın güverte + merkez panellerinin bu sonuçla kuracağı gövdeler."""
    assert NODE, 'node kurulu değil — panel yükleri panel JS kodundan üretilir'
    girdi = json.dumps({'staticDir': str(STATIC_JS), 'motorType': motor_type,
                        'files': sayfa_scriptleri(motor_type),
                        'results': sonuc, 'materials': malzeme_katalogu})
    # V3.0.5 T-ÇAPA-C1: betik stdin ile (argv değil; Linux MAX_ARG_STRLEN —
    # tests/test_node_cagri_sozlesmesi.py); girdi betiğe JSON dize literali
    # olarak gömülür.
    oku = "JSON.parse(fs.readFileSync(0, 'utf8'))"
    assert GUVERTE_JS.count(oku) == 1
    betik = GUVERTE_JS.replace(oku, 'JSON.parse(%s)' % json.dumps(girdi))
    proc = subprocess.run([NODE], input=betik,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, 'node koşumu düştü:\n' + proc.stderr[-2000:]
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Dışa aktarım yükleri — şablon gövde kurucularının AYNASI
# ---------------------------------------------------------------------------
def _sonlu(v):
    return v if (isinstance(v, (int, float)) and not isinstance(v, bool)
                 and math.isfinite(v)) else None


def _motor_adi(motor_type: str, sonuc: Dict, yuk: Dict) -> str:
    if motor_type == 'solid':      # solid.html _solidMotorName
        return (sonuc.get('motor_geometry') or {}).get('motor_name') \
            or 'HRMA_SOLID'
    if motor_type == 'liquid':     # liquid.html _liquidMotorName
        return yuk.get('motor_name') or (sonuc.get('motor_geometry') or {}
                                         ).get('motor_name') or 'HRMA_LIQUID'
    return yuk.get('motor_name') or 'HRMA_Motor'   # advanced.html


def ihrac_yukleri(motor_type: str, sonuc: Dict, yuk: Dict) -> Dict[str, Tuple[str, Dict]]:
    """ad -> (uç, gövde). Her gövde şablondaki kurucunun aynasıdır."""
    ad = _motor_adi(motor_type, sonuc, yuk)
    out: Dict[str, Tuple[str, Dict]] = {}
    if motor_type == 'solid':
        geo = sonuc.get('motor_geometry')
        # solid.html _solidDownloadExport (~2970): motor_data = motor_geometry
        govde = {'motor_data': geo, 'motor_name': ad, 'motor_type': 'solid'}
        out['dxf'] = ('/api/export-dxf', govde)
        out['step'] = ('/api/export-step', govde)
        # V301/HİBRİT-DIŞA (kalem 2): paket .eng gövdesini .eng düğmesiyle
        # aynı kurucudan (solid.html _solidEngMotorData) ayrıca taşır.
        out['paket'] = ('/api/export-complete-zip',
                        dict(govde, eng_motor_data=eng_yuku('solid', sonuc, yuk)[1]['motor_data']))
        # solid.html generateDrawings (~8057): yalnız motor_data
        out['cizim_pdf'] = ('/api/export-drawings-pdf', {'motor_data': geo})
        # solid.html exportMotorCAD (~7336): {results: currentResults} → ZIP
        out['stl_step_zip'] = ('/export_solid_motor_cad', {'results': sonuc})
    elif motor_type == 'liquid':
        geo = dict(sonuc.get('motor_geometry') or {})
        geo['motor_name'] = ad                      # _liquidMotorData
        govde = {'motor_data': geo, 'motor_name': ad, 'motor_type': 'liquid'}
        out['dxf'] = ('/api/export-dxf', govde)
        out['cizim_pdf'] = ('/api/export-drawings-pdf', govde)
        out['step'] = ('/api/export-step', govde)
        # V301/HİBRİT-DIŞA (kalem 2): liquid.html _liquidEngMotorData —
        # paketin .eng'i sonucun kendisinden (.eng düğmesiyle aynı gövde).
        out['paket'] = ('/api/export-complete-zip',
                        dict(govde, eng_motor_data=dict(sonuc, motor_name=ad)))
        # liquid.html exportCAD (~5031): {results: currentResults} → ZIP
        out['stl_step_zip'] = ('/export_liquid_cad', {'results': sonuc})
    else:
        motor = sonuc.get('motor')
        # advanced.html _downloadExport (~8264): motor_data = currentResults.motor
        govde = {'motor_data': motor, 'motor_name': ad, 'motor_type': 'hybrid'}
        out['dxf'] = ('/api/export-dxf', govde)
        out['cizim_pdf'] = ('/api/export-drawings-pdf', govde)
        out['step'] = ('/api/export-step', govde)
        out['paket'] = ('/api/export-complete-zip', govde)
        out['stl_zip'] = ('/api/export-stl-zip', govde)
    rapor = pdf_rapor_yuku(motor_type, sonuc, yuk)
    if rapor is not None:
        out['rapor_pdf'] = ('/api/export-pdf/summary', rapor)
    eng = eng_yuku(motor_type, sonuc, yuk)
    if eng is not None:
        out['eng'] = eng
    return out


def _pdf_num(v):
    """liquid.html ``_pdfNum``: sonlu sayıya çevrilebilen → sayı, yoksa None."""
    if v is None or v == '' or isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def eng_yuku(motor_type: str, sonuc: Dict, yuk: Dict) -> Optional[Tuple[str, Dict]]:
    """.eng dışa aktarımı (katı: solid.html downloadSolidEng ~8088;
    hibrit: advanced.html downloadEngFile ~8327 → /api/export-openrocket)."""
    if motor_type == 'solid':
        geo = sonuc.get('motor_geometry') or {}
        tc = sonuc.get('thrust_curve') or {}
        kasa = ((sonuc.get('cad_design') or {}).get('case_design') or {}).get('outer_diameter')
        kuru = ((sonuc.get('design_summary') or {}).get('masses') or {}).get('dry_mass_kg')
        md = {'motor_name': 'HRMA-SOLID',
              'total_impulse': sonuc.get('total_impulse'),
              'thrust': sonuc.get('average_thrust'),
              'burn_time': sonuc.get('burn_time'),
              'isp': sonuc.get('specific_impulse'),
              'propellant_mass_total': sonuc.get('propellant_mass'),
              'chamber_pressure': sonuc.get('chamber_pressure'),
              'motor_geometry': geo,
              'throat_diameter': geo.get('throat_diameter'),
              'chamber_diameter': geo.get('chamber_diameter'),
              'chamber_length': geo.get('chamber_length'),
              'exit_diameter': geo.get('exit_diameter')}
        md = {k: v for k, v in md.items() if v is not None or k in ('motor_geometry',)}
        if _sonlu(kasa) is not None:
            md['case_outer_diameter'] = kasa / 1000.0
        if _sonlu(kuru) is not None:
            md['dry_mass'] = kuru
        t, f = tc.get('time'), tc.get('thrust')
        if isinstance(t, list) and isinstance(f, list) and len(t) == len(f) and len(t) > 3:
            md['thrust_curve'] = {'time': t, 'thrust': f}
            if tc.get('basis'):
                md['thrust_curve']['basis'] = tc['basis']
        return '/api/export-eng', {'motor_data': md}
    if motor_type == 'hybrid':
        return '/api/export-openrocket', {'motor_data': sonuc.get('motor'),
                                          'motor_name': yuk.get('motor_name') or 'HRMA_Motor'}
    # V301/HİBRİT-DIŞA (kalem 2): sıvı .eng düğmesi (liquid.html
    # downloadLiquidEng → _liquidEngMotorData): gövde sonucun kendisi.
    return '/api/export-eng', {'motor_data': dict(sonuc, motor_name=_motor_adi('liquid', sonuc, yuk))}


def pdf_rapor_yuku(motor_type: str, sonuc: Dict, yuk: Dict) -> Optional[Dict]:
    """Rapor PDF'i gövdesi (grafikler hariç: ``charts`` boş liste — sayfa
    yalnız çizilmiş Plotly div'lerini ekler, sayı alanlarını DEĞİL)."""
    if motor_type == 'hybrid':
        # advanced.html exportAnalysisPDF (~8046): motor + bütün sonuç
        return {'motor_data': sonuc.get('motor'), 'analysis_results': sonuc}
    if motor_type == 'liquid':
        # liquid.html _liquidPdfMotorData / _liquidPdfAnalysisResults (~6703)
        cr = sonuc
        md = {'motor_name': yuk.get('motor_name') or 'HRMA-LIQUID',
              'motor_type': 'liquid'}
        for hedef, kaynak in (('propellant_type', 'propellant_name'),
                              ('chamber_diameter', 'chamber_diameter'),
                              ('chamber_length', 'chamber_length'),
                              ('chamber_pressure', 'chamber_pressure'),
                              ('of_ratio', 'mixture_ratio'),
                              ('expansion_ratio', 'expansion_ratio')):
            if kaynak in cr:
                md[hedef] = cr[kaynak]
        md['oxidizer_type'] = cr.get('oxidizer_type') or yuk.get('oxidizer_type')
        md['fuel_type'] = cr.get('fuel_type') or yuk.get('fuel_type')
        for ad in ('throat_diameter', 'exit_diameter'):
            if cr.get(ad) is not None:
                md[ad] = cr[ad] * 1000
        itki, sure = _pdf_num(cr.get('thrust')), _pdf_num(cr.get('burn_time'))
        ap = cr.get('altitude_performance') if isinstance(cr.get('altitude_performance'), list) else []
        perf = {'thrust': itki, 'specific_impulse': _pdf_num(cr.get('isp_sea_level')),
                'chamber_pressure': _pdf_num(cr.get('chamber_pressure')),
                'exit_velocity': _pdf_num(ap[0].get('exit_velocity')) if ap else None,
                'mass_flow_rate': _pdf_num(cr.get('total_mass_flow')),
                'burn_time': sure,
                'total_impulse': itki * sure if (itki is not None and sure is not None) else None}
        perf.update(cr.get('performance') or {})
        ar = dict(cr)
        ar['performance'] = perf
        return {'motor_data': md, 'analysis_results': ar, 'charts': []}
    # solid.html generateReport (~8285-8384)
    geo = sonuc.get('motor_geometry') or {}

    def mm(v):
        x = _sonlu(v)
        return None if x is None else x * 1000
    motor = {'motor_name': yuk.get('motor_name') or 'HRMA-SOLID',
             'motor_type': 'solid', 'grain_type': yuk.get('grain_type')}
    alanlar = {
        'propellant_type': sonuc.get('propellant_name') or sonuc.get('propellant_type'),
        'chamber_diameter': mm(geo.get('chamber_diameter')),
        'chamber_length': mm(geo.get('chamber_length')),
        'throat_diameter': _sonlu(sonuc.get('throat_diameter')),
        'exit_diameter': _sonlu(sonuc.get('exit_diameter')),
        'grain_density': _sonlu(sonuc.get('density')),
        'propellant_mass': _sonlu(sonuc.get('propellant_mass')),
        'expansion_ratio': _sonlu(sonuc.get('expansion_ratio')),
        'max_thrust': _sonlu(sonuc.get('max_thrust')),
        'thrust': _sonlu(sonuc.get('max_thrust')),
        'specific_impulse': _sonlu(sonuc.get('specific_impulse')),
        'burn_time': _sonlu(sonuc.get('burn_time')),
        'total_impulse': _sonlu(sonuc.get('total_impulse')),
        'chamber_pressure': _sonlu(sonuc.get('chamber_pressure')),
        'exit_velocity': _sonlu(sonuc.get('exit_velocity')),
        'mass_flow_rate': _sonlu(sonuc.get('mass_flow_rate')),
    }
    for k, v in alanlar.items():
        if v is not None and v != '':
            motor[k] = v
    return {'motor_data': motor, 'analysis_results': sonuc, 'charts': []}


# ---------------------------------------------------------------------------
# Dosya okuyucular: STEP / STL / DXF sınır kutusu, PDF metni
# ---------------------------------------------------------------------------
def zip_icerigi(ham: bytes) -> Dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(ham)) as z:
        return {n: z.read(n) for n in z.namelist() if not n.endswith('/')}


def stl_kutusu(ham: bytes) -> Optional[Tuple[List[float], List[float]]]:
    """STL (ikili ya da ASCII) köşe noktalarının min/max'ı (dosya birimi)."""
    import struct
    import numpy as np
    if ham[:5].lower() == b'solid' and b'facet' in ham[:400]:
        sayilar = re.findall(rb'vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)', ham)
        if not sayilar:
            return None
        p = np.array([[float(a), float(b), float(c)] for a, b, c in sayilar])
    else:
        if len(ham) < 84:
            return None
        n = struct.unpack('<I', ham[80:84])[0]
        if n == 0 or len(ham) < 84 + 50 * n:
            return None
        dt = np.dtype([('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')])
        arr = np.frombuffer(ham, dtype=dt, count=n, offset=84)
        p = arr['v'].reshape(-1, 3).astype(float)
    return p.min(axis=0).tolist(), p.max(axis=0).tolist()


def step_kutusu(ham: bytes, calisma: pathlib.Path):
    """STEP katılarının birleşik sınır kutusu (dosya birimi, OCC)."""
    from build123d import import_step
    calisma.mkdir(parents=True, exist_ok=True)
    yol = calisma / 'kutu.step'
    yol.write_bytes(ham)
    try:
        sekil = import_step(str(yol))
        bb = sekil.bounding_box()
        return [bb.min.X, bb.min.Y, bb.min.Z], [bb.max.X, bb.max.Y, bb.max.Z]
    finally:
        try:
            yol.unlink()
        except OSError:
            pass


def dxf_kutusu(ham: bytes):
    """DXF modelspace varlıklarının kapsamı (ezdxf bbox)."""
    import ezdxf
    from ezdxf import bbox
    doc = ezdxf.read(io.StringIO(ham.decode('utf-8', errors='replace')))
    kutu = bbox.extents(doc.modelspace())
    if not kutu.has_data:
        return None
    return list(kutu.extmin)[:2], list(kutu.extmax)[:2]


def pdf_metni(ham: bytes) -> str:
    # pypdf: requirements-dev.txt'te beyanlı PDF okuyucu (CI onu kurar;
    # PyMuPDF/fitz kurmaz — 28 Eki CI koşusu K3 PDF'te ModuleNotFoundError).
    # Deponun öteki PDF bekçileriyle aynı çıkarım (test_d15_ihracat_a3).
    from pypdf import PdfReader
    okuyucu = PdfReader(io.BytesIO(ham))
    return '\n'.join((sayfa.extract_text() or '') for sayfa in okuyucu.pages)


# ---------------------------------------------------------------------------
# Belirlenimcilik: kanonik JSON (beyanlı oynak alanlar dışarıda)
# ---------------------------------------------------------------------------
#: Değeri her istekte DOĞASI GEREĞİ değişen alanlar (anahtar adı, her
#: derinlikte). Bu listedeki her ad RAPOR'da gerekçesiyle yazılıdır; liste
#: dışı her fark bulgudur.
OYNAK_ANAHTARLAR = frozenset({
    'timestamp', 'generated_at', 'computed_at', 'created_at', 'updated_at',
    'request_id', 'elapsed_s', 'elapsed_ms', 'duration_s', 'duration_ms',
    'runtime_s', 'wall_time_s', 'solve_time_s', 'calculation_time',
    'execution_time', 'job_id',
})


def kanonik(obj: Any, oynak: Iterable[str] = OYNAK_ANAHTARLAR) -> Any:
    oynak = frozenset(oynak)
    if isinstance(obj, dict):
        return {k: kanonik(v, oynak) for k, v in sorted(obj.items())
                if k not in oynak}
    if isinstance(obj, list):
        return [kanonik(v, oynak) for v in obj]
    return obj


def ilk_farklar(a: Any, b: Any, yol: str = '', sinir: int = 12) -> List[str]:
    """İki JSON ağacının ilk ``sinir`` farkı (yol: a ⟷ b)."""
    out: List[str] = []

    def gez(x, y, p):
        if len(out) >= sinir:
            return
        if type(x) is not type(y):
            out.append('%s: tür %s ⟷ %s' % (p, type(x).__name__, type(y).__name__))
            return
        if isinstance(x, dict):
            for k in sorted(set(x) | set(y)):
                if k not in x or k not in y:
                    out.append('%s.%s: yalnız %s' % (p, k, 'ilkinde' if k in x else 'ikincisinde'))
                    if len(out) >= sinir:
                        return
                    continue
                gez(x[k], y[k], p + '.' + str(k))
        elif isinstance(x, list):
            if len(x) != len(y):
                out.append('%s: uzunluk %d ⟷ %d' % (p, len(x), len(y)))
                return
            for i, (u, v) in enumerate(zip(x, y)):
                gez(u, v, '%s[%d]' % (p, i))
        elif x != y and not (isinstance(x, float) and isinstance(y, float)
                             and math.isnan(x) and math.isnan(y)):
            out.append('%s: %r ⟷ %r' % (p, x, y))

    gez(a, b, yol)
    return out


# ---------------------------------------------------------------------------
# Ana büyüklükler: her motor tipinin yanıtında nerede durdukları
# ---------------------------------------------------------------------------
def ana_buyuklukler(motor_type: str, s: Dict) -> Dict[str, Optional[float]]:
    """Paneller arası karşılaştırmanın 'ana sonuç' tarafı (SI, yanıttaki adla).

    Uzunluklar METRE (motor_geometry sözleşmesi), basınç bar, itki N.
    """
    def g(d, *yol):
        for k in yol:
            if not isinstance(d, dict):
                return None
            d = d.get(k)
        return _sonlu(d)
    if motor_type == 'solid':
        geo = s.get('motor_geometry') or {}
        return {
            'thrust_avg_N': g(s, 'average_thrust'),
            'thrust_max_N': g(s, 'max_thrust'),
            'isp_sl_s': g(s, 'isp_sea_level'),
            'isp_vac_s': g(s, 'isp_vacuum'),
            'specific_impulse_s': g(s, 'specific_impulse'),
            'pc_bar': g(s, 'chamber_pressure'),
            'throat_d_mm': g(s, 'throat_diameter'),
            'exit_d_mm': g(s, 'exit_diameter'),
            'burn_time_s': g(s, 'burn_time'),
            'total_impulse_Ns': g(s, 'total_impulse'),
            'c_star_m_s': g(s, 'c_star'),
            'propellant_mass_kg': g(s, 'propellant_mass'),
            'geo_total_length_m': g(geo, 'total_length'),
            'geo_chamber_length_m': g(geo, 'chamber_length'),
            'geo_case_outer_d_m': g(geo, 'case_outer_diameter') or g(geo, 'outer_diameter'),
            'geo_throat_d_m': g(geo, 'throat_diameter'),
            'geo_exit_d_m': g(geo, 'exit_diameter'),
        }
    if motor_type == 'liquid':
        geo = s.get('motor_geometry') or {}
        return {
            'thrust_N': g(s, 'thrust'),
            'thrust_vac_N': g(s, 'thrust_vacuum'),
            'isp_sl_s': g(s, 'isp_sea_level'),
            'isp_vac_s': g(s, 'isp_vacuum'),
            'pc_bar': g(s, 'chamber_pressure'),
            'mdot_kg_s': g(s, 'total_mass_flow'),
            'throat_d_mm': g(s, 'throat_diameter_mm'),
            'exit_d_mm': g(s, 'exit_diameter_mm'),
            'c_star_m_s': g(s, 'c_star'),
            'geo_total_length_m': g(geo, 'total_length'),
            'geo_throat_d_m': g(geo, 'throat_diameter'),
            'geo_exit_d_m': g(geo, 'exit_diameter'),
        }
    m = s.get('motor') or {}
    return {
        'thrust_N': g(m, 'thrust'),
        'isp_s': g(m, 'isp'),
        'pc_bar': g(m, 'chamber_pressure'),
        'burn_time_s': g(m, 'burn_time'),
        'total_impulse_Ns': g(m, 'total_impulse'),
        'c_star_m_s': g(m, 'c_star'),
        'mdot_kg_s': g(m, 'total_mass_flow') or g(m, 'mass_flow_rate'),
        'throat_d_mm': g(m, 'throat_diameter'),
        'exit_d_mm': g(m, 'exit_diameter'),
        'total_length_mm': g(m, 'total_length'),
    }


# ---------------------------------------------------------------------------
# K3 — paneller arası aynı sayı: karşılaştırma tablosu
# ---------------------------------------------------------------------------
#: Tolerans sınıfları (her satırda beyanlı):
#:   'REL9'  — aynı büyüklüğün iki JSON yayımı, bağıl 1e-9;
#:   'YARIM' — yayımlanan metin yuvarlaması: |a-b| ≤ ½·10^-d (+1e-12);
#:   'CAD'   — CAD dosyası (STEP B-spline / STL float32): bağıl 1e-6.
TOLERANS = {'REL9': 1e-9, 'CAD': 1e-6}

#: 'CAD_KONTUR_CAP' / 'CAD_KONTUR_BOY' — V301/T-ÇAPA-D (ana model kararı,
#: 28 Eki): STEP'in İNTERPOLASYONLU lüle konturundan gelen ölçüler (en büyük
#: çap, toplam boy). Lüle iç ve dış konturu ``step_export._contour_bspline_
#: edge`` ile GeomAPI_Interpolate B-spline'ıdır: eğri noktalardan TAM geçer,
#: aralarda aşma kendiliğindendir ve ürünün bu aşma için TEK beyanlı sınırı
#: imalat kontur kapısıdır — ``hrma.engines.nozzle_design.CONTOUR_ENVELOPE_
#: TOLERANCE_MM`` (eğri noktaların yarıçap zarfını en çok bu kadar taşar;
#: gerekçe kapının künyesi: STEP konum çözünürlüğü 10 µm). Ölçüt
#: |a − b| ≤ max(bağıl 1e-6, katsayı × o sınır); çapta katsayı 2 (çap = 2 ×
#: yarıçap), boyda 1. ÖLÇÜLDÜ (katı örnek, main 64c2713fd): STEP en büyük çap
#: 91,0001064 mm ⟷ uçuş zarfı 91,0 mm — yarıçapta 53 nm aşma; dört kutu
#: yöntemi aynı sayıyı veriyor (``docs/scofield/raw/OH/V301/tcapa-d/olcum/
#: step_kutu_olcum.py``). Kapsam YALNIZ bu iki STEP ölçüsüdür; STL (nokta
#: çokgeni) ve başka büyüklükler 'CAD' sınıfında kalır.
KONTUR_SINIF_KATSAYISI = {'CAD_KONTUR_CAP': 2.0, 'CAD_KONTUR_BOY': 1.0}


def kontur_siniri_mm(sinif: str) -> float:
    """Kontur sınıfının mutlak sınırı [mm] — ürünün kapı sabitinden."""
    from hrma.engines.nozzle_design import CONTOUR_ENVELOPE_TOLERANCE_MM
    return KONTUR_SINIF_KATSAYISI[sinif] * float(CONTOUR_ENVELOPE_TOLERANCE_MM)


def pdf_etiket_sayisi(metin: str, etiket: str) -> Optional[Tuple[float, int]]:
    """PDF metninde ``etiket`` satırından SONRAKİ ilk sayı (değer, ondalık)."""
    m = re.search(re.escape(etiket) + r'\s*\n\s*([-+]?[0-9][0-9.,]*)', metin)
    if not m:
        return None
    ham = m.group(1).replace(',', '')
    ond = len(ham.split('.')[1]) if '.' in ham else 0
    try:
        return float(ham), ond
    except ValueError:
        return None


def pdf_desen_sayisi(metin: str, desen: str) -> Optional[Tuple[float, int]]:
    m = re.search(desen, metin)
    if not m:
        return None
    ham = m.group(1).replace(',', '')
    ond = len(ham.split('.')[1]) if '.' in ham else 0
    return float(ham), ond


def _ozet_ond(v) -> int:
    s = repr(float(v))
    return len(s.split('.')[1]) if '.' in s and 'e' not in s else 0


def not_kutlesi(not_metni, parca: str) -> Optional[float]:
    """Künyedeki ``<parca> X kg`` sayısı (flight_vehicle._liquid_inert_mass
    biçimi, 3 ondalık); yoksa None."""
    import re as _re
    m = _re.search(_re.escape(parca) + r' (\d+(?:\.\d+)?) kg', str(not_metni or ''))
    return float(m.group(1)) if m else None


def sivi_ucan_atil(sonuc: Dict) -> Optional[float]:
    """Sıvı uçan atıl kütle, sonucun KENDİ alanlarından (V301/HİBRİT-DIŞA):
    motor kuru + itici tankı kuru yapısı + (yüklenen − nominal) yedek itici."""
    ms = ((sonuc.get('design_summary') or {}).get('masses') or {})
    ss = ((sonuc.get('propellant_tanks') or {}).get('system_summary') or {})
    motor = _sonlu(ms.get('engine_mass_kg'))
    if motor is None:
        return None
    tank = _sonlu(ss.get('total_tank_mass')) or 0.0
    yuk, nom = _sonlu(ss.get('total_propellant_mass')), _sonlu(ss.get('total_propellant_mass_nominal'))
    yedek = (yuk - nom) if (yuk is not None and nom is not None and yuk > nom) else 0.0
    return motor + max(tank, 0.0) + yedek


def satir(buyukluk: str, kaynak: str, deger, sinif: str = 'REL9',
          ond: Optional[int] = None) -> Dict:
    return {'buyukluk': buyukluk, 'kaynak': kaynak,
            'deger': _sonlu(deger) if deger is not None else None,
            'sinif': sinif, 'ond': ond}


def esit_mi(ref: float, s: Dict) -> bool:
    v = s['deger']
    if v is None or ref is None:
        return False
    if s['sinif'] == 'YARIM':
        return abs(v - ref) <= 0.5 * 10 ** (-(s['ond'] or 0)) + 1e-12
    if s['sinif'] in KONTUR_SINIF_KATSAYISI:
        return abs(v - ref) <= max(
            TOLERANS['CAD'] * max(abs(v), abs(ref)),
            kontur_siniri_mm(s['sinif']))
    tol = TOLERANS[s['sinif']]
    return math.isclose(v, ref, rel_tol=tol, abs_tol=0.0)


def k3_karsilastir(satirlar: List[Dict]) -> List[str]:
    """Her büyüklük için İLK satır referanstır; diğerleri ona eşit olmalı."""
    gruplar: Dict[str, List[Dict]] = {}
    for s in satirlar:
        gruplar.setdefault(s['buyukluk'], []).append(s)
    kotu = []
    for ad, liste in gruplar.items():
        ref = liste[0]
        for s in liste[1:]:
            if not esit_mi(ref['deger'], s):
                kotu.append('%s: %s = %r ⟷ %s = %r [%s%s]' % (
                    ad, ref['kaynak'], ref['deger'], s['kaynak'], s['deger'],
                    s['sinif'], '' if s['ond'] is None else ', %d ondalık' % s['ond']))
    return kotu


def ozet_satirlari(motor_type: str, ozet: Dict) -> List[Tuple[str, str, float]]:
    """Örnek dosyasının results_summary'si (proje şeridi/liste kartı)."""
    eslem = {'solid': {'peak_thrust_N': 'tepe itki [N]', 'isp_s': 'Isp deniz [s]',
                       'chamber_pressure_bar': 'Pc [bar]', 'burn_time_s': 'yanma süresi [s]',
                       'total_impulse_Ns': 'toplam impuls [N·s]'},
             'liquid': {'thrust_N': 'itki [N]', 'isp_s': 'Isp deniz [s]',
                        'isp_vacuum_s': 'Isp vakum [s]', 'chamber_pressure_bar': 'Pc [bar]'},
             'hybrid': {'thrust_N': 'itki [N]', 'isp_s': 'Isp [s]',
                        'chamber_pressure_bar': 'Pc [bar]', 'burn_time_s': 'yanma süresi [s]',
                        'total_impulse_Ns': 'toplam impuls [N·s]'}}[motor_type]
    return [(eslem[k], k, v) for k, v in (ozet or {}).items() if k in eslem]
