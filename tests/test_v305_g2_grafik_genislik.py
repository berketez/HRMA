# -*- coding: utf-8 -*-
"""v3.0.5 (V305/G2) — alttan taşma düzeltmesi grafiğin genişliğini çivilemez.

Yayın kapısının görsel turu ``/hybrid``de 15 px YATAY taşma buldu (belge
1615 px, pencere 1600 px). Ölçülen zincir (hesap + 3B + FEA + Analiz
Merkezi sonrası, 1600 × 1000, TR; ölçüm ve ekran görüntüleri
``~/HRMA-calisma/2026-10-28/v305-ci/G2/``):

1. ``plotly_dark.js`` ``altTasmayiKapat`` (V301/N-grafik G3, e591f44d9)
   ``Plotly.relayout(gd, {height, 'margin.b'})`` çağırıyordu. Plotly
   1.58.5 ``relayout``u ``height`` verilince öbür boyutu o anki
   ``_fullLayout.width``e çiviler ve ``autosize``ı siler
   (vendor/plotly-1.58.5.min.js ``E("autosize",null); E(K,l[K])``;
   güncelleme nesnesinde BULUNAN anahtara dokunmaz).
2. ``#fea_plot_sf`` 1526 × 503 px'e çivilendi, ``.svg-container`` piksel
   genişlik aldı. Bu genişlik kabın dış (border-box) genişliğidir; iç
   genişliği dolgu + çerçeve (42 px) kadar aştığı için ``#feaPanel``in asgari
   içerik genişliği 1614 px oldu.
3. Tek sütunlu ızgaranın ``1fr`` izi 1570 → 1614 px büyüdü, bütün paneller
   genişledi, duyarlı grafiklerin SVG'leri 1615 px'e uzadı → 15 px taşma.

Düzeltme: figür genişliği açıkça verilmemişse güncellemeye ``width: null``
konur (Plotly genişliği kabından ölçmeye devam eder); açık sayısal genişlik
aynen korunur. Ölçüm (sonra): /hybrid 1600 TR taşma 0 px, ızgara izi
1570 px, ``#fea_plot_sf`` kabı ``100%``.

Bu bekçi düzeneği tarayıcısız koşar: ``plotly_dark.js`` node ``vm``
içinde, Plotly sahte bir nesneyle yüklenir; ``relayout``a giden güncelleme
nesnesi yakalanır.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')

_DUZENEK = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const relayoutlar = [];
const sandbox = { console, JSON, Object, Array, Math, Number, String,
                  isFinite, RegExp, Error, Promise, setTimeout: () => 0 };
sandbox.window = sandbox;
sandbox.document = { querySelector: () => null, querySelectorAll: () => [],
                     createElement: () => ({}), head: { appendChild() {} },
                     addEventListener() {}, getElementById: () => null };
sandbox.window.__HRMA_I18N_CHARTS = true;   // sözlük yükleyicisi devre dışı
sandbox.Plotly = {
    newPlot: (el) => Promise.resolve(el),
    react: (el) => Promise.resolve(el),
    relayout: (gd, upd) => { relayoutlar.push(upd); return Promise.resolve(gd); },
    Icons: { camera: {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(%(dosya)s, 'utf8'), sandbox,
                { filename: 'plotly_dark.js' });

// Sahte çizim kabı: SVG 340 px, eksen başlığı SVG'nin dibinden 40 px taşıyor
// (altTasmayiKapat'ın düzeltme dalına girmesi için).
function sahteGd(layout) {
    const svg = { getBoundingClientRect: () => ({ height: 340, bottom: 340 }) };
    const metin = { textContent: 'Eksen', closest: () => null,
                    getBoundingClientRect: () => ({ height: 14, bottom: 380 }) };
    return {
        layout: layout,
        _fullLayout: { height: 340, width: 1526, margin: { b: 80 } },
        style: {},
        getBoundingClientRect: () => ({ bottom: 400 }),
        querySelector: (s) => (s === 'svg.main-svg' ? svg : null),
        querySelectorAll: (s) => (s === 'svg text' ? [metin] : []),
        on() {},
    };
}

const GIRDI = %(girdi)s;
const sozler = GIRDI.map((lay) => sandbox.Plotly.newPlot(sahteGd(lay), [], {}));
Promise.all(sozler).then(() => Promise.resolve()).then(() => {
    process.stdout.write(JSON.stringify(relayoutlar));
});
"""


def _relayoutlar(layoutlar):
    betik = _DUZENEK % {
        'dosya': json.dumps(str(JS / 'plotly_dark.js')),
        'girdi': json.dumps(layoutlar)}
    r = subprocess.run([NODE], input=betik, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


@node_gerekli
def test_genisligi_verilmemis_figurde_genislik_civilenmez():
    """Genişlik açık değilse güncellemede ``width`` ANAHTARI ``null`` durur.

    Anahtarın varlığı şarttır: Plotly'nin ``relayout``u yalnız güncelleme
    nesnesinde OLMAYAN öbür boyutu çiviler. Ters mutasyon: anahtarı
    çıkarmak (e591f44d9 hâli) bu testi kırmızıya çevirir.
    """
    out = _relayoutlar([{'height': 340}])
    assert len(out) == 1, out
    upd = out[0]
    assert 'width' in upd, upd
    assert upd['width'] is None, upd
    # Alttan taşma düzeltmesinin kendisi yerinde: 40 px taşma + 8 px pay.
    assert upd['height'] == 340 + 48, upd
    assert upd['margin.b'] == 80 + 48, upd


@node_gerekli
def test_acik_sayisal_genislik_aynen_korunur():
    out = _relayoutlar([{'height': 340, 'width': 900}])
    assert len(out) == 1, out
    assert out[0]['width'] == 900, out[0]


@node_gerekli
def test_yuksekligi_acik_olmayan_figure_dokunulmaz():
    """autosize figürüne yükseklik yazılmaz (V301/N-grafik kuralı korunur)."""
    assert _relayoutlar([{}]) == []
