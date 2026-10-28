"""V301/UI-K kalem 4 — ortak "?" ipucu bileşeni: klavye, aria ve satır kırılması.

ÖLÇÜLDÜ (docs/scofield/raw/OH/V301/ui-k/balon_once_*.json ⟷ balon_sonra_*.json,
Playwright, 1280/1440 × EN/TR; hibrit 116, katı 143, sıvı 150, Fırlatma
Sahası 23 görünür ikon):
  * Esc balonu ODAĞI BIRAKARAK kapatıyordu (odak ikonda kalan 0/12), Enter ve
    Boşluk hiçbir şey yapmıyordu (0/12), ikon balon metnine aria ile bağlı
    değildi (0/12) → sonra 12/12, 12/12, 12/12;
  * uzun etikette ikon tek başına alt satıra iniyordu (hibrit 11–20, katı
    4–8, saha 1) → 0; etiket çevresinde yazı çakışması 0; taşan balon 0.
Bekçi field_help.js'i asgari sahte DOM'la node'da koşar ve theme.css
kurallarını denetler.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
FH = KOK / 'hrma' / 'static' / 'js' / 'field_help.js'
CSS = (KOK / 'hrma' / 'static' / 'css' / 'theme.css').read_text(encoding='utf-8')
NODE = shutil.which('node')


def test_kapatildi_kurali_acma_kuralindan_sonra():
    acma = CSS.index('.tooltip.tip-open .tooltip-text {')
    kapat = CSS.index('.tooltip.tip-dismissed .tooltip-text {')
    assert kapat > acma, 'tip-dismissed açma kuralından sonra gelmeli (aynı özgüllük)'
    govde = CSS[kapat:CSS.index('}', kapat)]
    assert 'visibility: hidden' in govde and 'scale(0)' in govde


def test_ikon_payi_konumu_korur():
    """Önceki öğenin ayırdığı yer = ikonun eski sol payı (5) + ikon (16);
    ikonun sol payı −16: net katkı 0, görünür aralık yine 5 px."""
    pad = re.search(r':where\(span, strong, b, em, small\):has\(\+ \.tooltip\) \{\s*'
                    r'padding-inline-end: (\d+)px;', CSS)
    marj = re.search(r':where\(span, strong, b, em, small\) \+ \.tooltip \{\s*'
                     r'margin-left: -(\d+)px;', CSS)
    ikon = re.search(r'\.tooltip-icon \{\s*width: (\d+)px;', CSS)
    eski = re.search(r'\.tooltip \{\s*position: relative;\s*display: inline-block;\s*'
                     r'margin-left: (\d+)px;', CSS)
    assert pad and marj and ikon and eski
    assert int(marj.group(1)) == int(ikon.group(1))
    assert int(pad.group(1)) == int(eski.group(1)) + int(ikon.group(1))
    m = re.search(r'\.ad-field-head > label,\s*\.hrma-ai-field-head > label \{\s*'
                  r'max-width: calc\(100% - (\d+)px\);', CSS)
    assert m and int(m.group(1)) >= int(ikon.group(1))


HARNESS = r"""
'use strict';
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[1], 'utf8');
const dinle = {};
function sinif() { const s = new Set(); return {
  add: (c) => s.add(c), remove: (c) => s.delete(c), contains: (c) => s.has(c),
  toggle: (c, v) => { if (v === undefined ? !s.has(c) : v) s.add(c); else s.delete(c); } }; }
let odak = null;
function dugum(etiket, sinifAdi) {
  const d = { tagName: etiket, attrs: {}, cocuk: [], parent: null, classList: sinif(), style: { setProperty() {} },
    id: '', textContent: '',
    setAttribute(k, v) { if (k === 'id') this.id = String(v); this.attrs[k] = String(v); },
    getAttribute(k) { return k === 'id' ? (this.id || null) : (k in this.attrs ? this.attrs[k] : null); },
    hasAttribute(k) { return k === 'id' ? !!this.id : k in this.attrs; },
    appendChild(c) { c.parent = this; this.cocuk.push(c); return c; },
    contains(x) { for (let e = x; e; e = e.parent) if (e === this) return true; return false; },
    closest(sec) { for (let e = this; e; e = e.parent) if (e.eslesir(sec)) return e; return null; },
    eslesir(sec) { return sec.split(',').some((p) => p.trim().split('.').filter(Boolean)
      .every((c) => e_sinif(this, c))); },
    matches(sec) { if (sec === ':focus-within') return !!odak && this.contains(odak); return this.eslesir(sec); },
    querySelector(sec) { return tum(this).find((e) => e !== this && e.eslesir(sec)) || null; },
    getBoundingClientRect() { return { left: 100, top: 300, right: 116, bottom: 316, width: 16, height: 16 }; },
    offsetWidth: 280, offsetHeight: 120, blur() { if (odak === this) odak = null; } };
  (sinifAdi || '').split(' ').filter(Boolean).forEach((c) => d.classList.add(c));
  return d;
}
function e_sinif(e, c) { return c === e.tagName.toLowerCase() || e.classList.contains(c); }
function tum(k) { const out = [k]; k.cocuk.forEach((c) => out.push(...tum(c))); return out; }
const govde = dugum('BODY', '');
function ipucuKur(ikonAttr) {
  const t = dugum('SPAN', 'tooltip'); const i = dugum('SPAN', 'tooltip-icon');
  const b = dugum('SPAN', 'tooltip-text'); b.textContent = 'açıklama';
  Object.keys(ikonAttr || {}).forEach((k) => i.setAttribute(k, ikonAttr[k]));
  t.appendChild(i); t.appendChild(b); govde.appendChild(t); return { t, i, b };
}
const A = ipucuKur({ tabindex: '0', role: 'button', 'aria-label': '?' });   // şablon ikonu (bağsız)
const B = ipucuKur({});                                                     // çıplak ikon
const document = {
  readyState: 'complete', documentElement: { clientWidth: 1440 },
  get activeElement() { return odak; },
  addEventListener(ad, f) { (dinle[ad] = dinle[ad] || []).push(f); },
  getElementById(id) { return tum(govde).find((e) => e.id === id) || null; },
  querySelectorAll(sec) {
    const parcalar = sec.split(',').map((s) => s.trim());
    return tum(govde).filter((e) => parcalar.some((p) => {
      if (p === '.tooltip:hover') return false;
      if (p === '.tooltip:focus-within') return e.classList.contains('tooltip') && e.matches(':focus-within');
      const m = /^\.tooltip-icon:not\(\[(\w[\w-]*)\]\)$/.exec(p);
      if (m) return e.classList.contains('tooltip-icon') && !e.hasAttribute(m[1]);
      return e.eslesir(p);
    }));
  } };
const window = { document, innerWidth: 1440, innerHeight: 900, addEventListener() {} };
window.window = window;
vm.createContext(window);
vm.runInContext(src, window, { filename: 'field_help.js' });
function olay(ad, hedef, ek) {
  const e = Object.assign({ type: ad, target: hedef, key: '', relatedTarget: null,
    preventDefault() { this.onlendi = true; } }, ek || {});
  (dinle[ad] || []).forEach((f) => f(e)); return e;
}
const acik = (x) => (x.t.classList.contains('tip-open') || x.t.matches(':focus-within'))
  && !x.t.classList.contains('tip-dismissed');
const out = {};
out.aria_A = A.i.getAttribute('aria-describedby') === A.b.id && !!A.b.id;
out.aria_B = B.i.getAttribute('aria-describedby') === B.b.id && B.i.getAttribute('tabindex') === '0';
out.rol_balon = A.b.getAttribute('role');
out.html_bag = /aria-describedby="(hrma-tip-[^"]+)"[\s\S]*id="\1"/.test(window.HRMAHelp.html('k', 'x'));
odak = A.i; olay('focusin', A.i);
out.odakta_acik = acik(A);
olay('keydown', A.i, { key: 'Escape' });
out.esc_kapali = !acik(A); out.esc_odak_ikonda = odak === A.i;
const e1 = olay('keydown', A.i, { key: 'Enter' });
out.enter_acik = acik(A); out.enter_onlendi = !!e1.onlendi;
olay('keydown', A.i, { key: 'Enter' }); out.enter2_kapali = !acik(A);
const e2 = olay('keydown', A.i, { key: ' ' }); out.bosluk_acik = acik(A); out.bosluk_onlendi = !!e2.onlendi;
olay('keydown', A.i, { key: 'Escape' });
odak = B.i; olay('focusout', A.i, { relatedTarget: B.i });
out.ayrilinca_isaret_kalkar = !A.t.classList.contains('tip-dismissed');
const e3 = olay('keydown', govde, { key: 'Enter' }); out.ikon_disi_enter_dokunulmaz = !e3.onlendi;
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_klavye_ve_aria():
    # V3.0.5 T-ÇAPA-C1: betik stdin ile (tests/test_node_cagri_sozlesmesi.py);
    # stdin koşusunda process.argv yalnız [node] — değer 'use strict'
    # önsözünden SONRA aynı konuma yazılır.
    onsoz = "'use strict';"
    assert HARNESS.count(onsoz) == 1
    betik = HARNESS.replace(onsoz, onsoz + '\nprocess.argv = [process.argv[0], %s];'
                            % json.dumps(str(FH)))
    r = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-1200:]
    o = json.loads(r.stdout)
    assert o == {
        'aria_A': True, 'aria_B': True, 'rol_balon': 'tooltip', 'html_bag': True,
        'odakta_acik': True, 'esc_kapali': True, 'esc_odak_ikonda': True,
        'enter_acik': True, 'enter_onlendi': True, 'enter2_kapali': True,
        'bosluk_acik': True, 'bosluk_onlendi': True,
        'ayrilinca_isaret_kalkar': True, 'ikon_disi_enter_dokunulmaz': True,
    }, o
