# -*- coding: utf-8 -*-
"""ÖH FAZ B-4 — Analiz MERKEZİ kiracılarının ``fromResults`` sözleşmesi.

ÖLÇÜLEN BOŞLUK (Faz B-3 P4 ölçümü, defter OH-B3-06 devri)
---------------------------------------------------------
``fromResults`` bildiren 13 panelin 11'i Analiz GÜVERTESİ'ne kaydoluyor ve
``tests/test_panel_units_v2626.py`` onları node içinde GERÇEKTEN çalıştırıp
birim sözleşmesini sınıyor. Kalan İKİSİ — ``panels/cfd_panel.js`` ve
``panels/stability_panel.js`` — Analiz MERKEZİ kiracısıdır: ``window.
AnalysisCenter.register`` çağırırlar, güverte kayıt defterine hiç girmezler.
O bekçi bu ayrımı türetilmiş bir ölçütle MUAF tutuyor (haklı olarak: kendi
koşum takımı güverteyi yükler), ama muafiyetin öbür yakasında bekçi YOKTU:

* iki kiracının ``fromResults``’ı hiçbir testte çalıştırılmıyordu;
* ürettikleri önerilerin BİRİMİ, ŞEMASI ve KAYNAĞI hiçbir yerde
  sınanmıyordu — oysa v2.6.26'nın kanıtladığı kusur tam olarak buydu
  (panel çözücü çıktısını yanlış birimde hesap ucuna yolluyordu);
* "kiracı gerçekten kaydoldu mu" sorusu da ölçülmüyordu: kayıt bir ``if
  (window.AnalysisCenter …)`` kapısının arkasında; kapı kapansa panel
  sessizce ekrandan düşerdi.

BU DOSYANIN YAPTIĞI
-------------------
D3'ün (``test_panel_units_v2626.py``) **byFile** desenini Merkez'e uyarlar:
her kiracı dosyası node içinde AYRI AYRI yüklenir ve kayıt defterinin o
yükleme sırasında ne kadar büyüdüğü ÖLÇÜLÜR. Kimlik dosya adından tahmin
EDİLMEZ. Sonra her kaydın ``fromResults``’ı ÜÇ motor tipinin GERÇEK
çözücü yanıtıyla çalıştırılır ve dört sözleşme sınanır:

1. **Şema** — öneri anahtarları kiracının BİLDİRDİĞİ alan kimlikleri
   olmalı (bilinmeyen anahtar Merkez tarafından sessizce yutulur).
2. **Tip** — her öneri SONLU bir sayı olmalı (``null``/dizge/NaN yok).
3. **Birim** — her alan fiziksel bandında olmalı; bant sınırları birim
   hatasını yakalayacak şekilde seçildi (bar sızarsa ``P0_Pa`` 1e5'in,
   mm sızarsa ``chamber_length_m`` 20'nin dışına düşer).
4. **Kaynak** — önerilen sayı UYDURULAMAZ: yükte belgelenmiş yollardan
   birinde ya AYNEN ya da beyan edilmiş dönüşümüyle (bar→Pa, R=Ru/MW)
   bulunmalıdır.

Ayrıca kapsam TEK YÖNLÜ çapalarla korunur: bugünkü öneri kümesi
küçülemez (sessizce kaybolan öneri = kırmızı), kiracı listesi daralamaz.

Kapsam kuralı (FAZ B): ürün kodu SALT OKUNUR. Bu dosya yalnız ölçer.
"""

import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

from hrma.constants import MOTOR_TYPES

# D3'ün gerçek çözücü yükü kurma yardımcıları — kopyalanmaz, İTHAL EDİLİR
# (iki bekçi aynı örnek projeleri aynı uçtan geçirsin diye). Emsal:
# tests/test_browser_harness_merkez.py'nin test_browser_harness_fea'dan
# ithali.
from tests.test_panel_units_v2626 import (  # noqa: E402
    _CENTER_REGISTER_RE,
    _FROM_RESULTS_TANIM_RE,
    _calculate_payload,
    _js_kod_govdesi,
    ENDPOINTS,
    EXAMPLES_DIR,
    HEADERS,
    NAMES,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PANELS_DIR = STATIC_JS / 'panels'
MERKEZ_KAYNAGI = STATIC_JS / 'analysis_center.js'

pytestmark = pytest.mark.skipif(shutil.which('node') is None,
                                reason='node kurulu değil')

#: Koşum takımına giren paneller — ELLE LİSTE DEĞİL, dizinin aynası
#: (``test_i18n_common.py`` / ``test_panel_units_v2626.py`` ile aynı
#: türetme). Yeni panel eklenince kendiliğinden kapsama girer.
PANEL_DOSYALARI = tuple(sorted(p.name for p in PANELS_DIR.glob('*.js')))

#: 27 Ağustos 2026 ölçümü — TABAN çapası. Kiracı listesi DARALAMAZ; yeni
#: kiracı doğarsa bu bekçi kırmızı verir ve kapsam bilinçli genişletilir.
#: Kimlik dosya adından TAHMİN edilmez: aşağıdaki ``kiraci_kosumu``
#: fikstürü her paneli node içinde ayrı ayrı yükleyip Merkez kayıt
#: defterinin ne kadar büyüdüğünü ÖLÇER (D3 byFile deseni).
TARIHSEL_KIRACILAR = ('cfd_panel.js', 'stability_panel.js')

#: Aynı ölçümün satır kimlikleri (bileşen:analiz) — dosya başına.
TARIHSEL_KIRACI_SATIRLARI = {
    'cfd_panel.js': ('nozzle_flow:cfd',),
    'stability_panel.js': ('chamber_acoustics:acoustic_modes',
                           'chamber_acoustics:combustion_stability'),
}


# ---------------------------------------------------------------------------
# node koşum takımı — Merkez + kiracılar sahte DOM içinde GERÇEKTEN çalışır
# ---------------------------------------------------------------------------
HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const [staticDir, tenantList, resultsPath] = process.argv.slice(2);
const results = JSON.parse(fs.readFileSync(resultsPath, 'utf8'));

// --- asgari sahte DOM (test_panel_units_v2626.py ile AYNI iskelet) ---------
function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this.dataset = {};
    this._attrs = {};
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k)
        ? this._attrs[k] : null;
};
El.prototype.querySelector = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.addEventListener = function () {};

const documentStub = {
    head: new El('head'),
    body: new El('body'),
    readyState: 'complete',
    createElement: function (t) { return new El(t); },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    getElementById: function () { return null; },
    addEventListener: function () {},
};

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: setInterval, clearInterval: clearInterval,
    fetch: function () { return Promise.reject(new Error('sandbox: ag yok')); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, isFinite: isFinite,
    parseFloat: parseFloat, parseInt: parseInt, document: documentStub,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

function run(file) {
    vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox, { filename: file });
}

// OH D25 / OH-D24-05: ortak birim modulu EN ONCE yuklenir. Tarayicida da
// sira boyledir (advanced/liquid/solid sablonlari): PA_PER_BAR panellerde
// yeniden tanimlanmaz, tek kaynaktan okunur.
run(path.join(staticDir, 'units_constants.js'));

// Guverte ONCE yuklenir: kiracinin guverteye kaydolup kaydolmadigi da
// olculebilsin diye (muafiyetin obur yakasi).
run(path.join(staticDir, 'analysis_dock.js'));
run(path.join(staticDir, 'analysis_center.js'));

if (!sandbox.window.AnalysisCenter) {
    console.log(JSON.stringify({ error: 'AnalysisCenter yuklenmedi' }));
    process.exit(0);
}

const acReg = sandbox.window.AnalysisCenter._registry;
const dockReg = sandbox.window.AnalysisDock
    ? sandbox.window.AnalysisDock._registry : null;
const byFile = {};
const dockByFile = {};
const exposedByFile = {};

// Bir nesne Merkez SPEC'i mi? (register'in zorunlu sozlesme alanlari)
function specMi(v) {
    return v && typeof v === 'object' && !Array.isArray(v)
        && typeof v.componentId === 'string'
        && typeof v.analysisId === 'string'
        && typeof v.render === 'function';
}

// ÖH FAZ D / D3 deseni: hangi DOSYA hangi satiri kaydetti — dosya adindan
// TAHMIN edilmez, kayit defterinin buyumesi olculur. Ayrica dosyanin
// window'a KOYDUGU spec'ler toplanir: "yazilmis ama kaydolmamis" spec
// boylece gorunur olur.
tenantList.split(',').forEach(function (name) {
    const acBefore = acReg.length;
    const dockBefore = dockReg ? dockReg.length : 0;
    const keysBefore = Object.keys(sandbox.window);
    run(path.join(staticDir, 'panels', name));
    byFile[name] = acReg.slice(acBefore).map(function (s) {
        return s.componentId + ':' + s.analysisId;
    });
    dockByFile[name] = dockReg
        ? dockReg.slice(dockBefore).map(function (s) { return s.id; }) : [];

    const yeni = Object.keys(sandbox.window).filter(function (k) {
        return keysBefore.indexOf(k) < 0;
    });
    const acik = [];
    yeni.forEach(function (k) {
        const v = sandbox.window[k];
        if (specMi(v)) { acik.push(v.componentId + ':' + v.analysisId); return; }
        if (v && typeof v === 'object') {
            Object.keys(v).forEach(function (alt) {
                let ic = null;
                try { ic = v[alt]; } catch (e) { ic = null; }
                if (specMi(ic)) acik.push(ic.componentId + ':' + ic.analysisId);
            });
        }
    });
    exposedByFile[name] = acik;
});

const out = {
    byFile: byFile,
    dockByFile: dockByFile,
    exposedByFile: exposedByFile,
    matrix: (sandbox.window.AnalysisCenter._matrix || []).map(function (m) {
        return m.componentId + ':' + m.analysisId;
    }),
    specs: {},
};
acReg.forEach(function (spec) {
    const rec = {
        fields: [], hasFromResults: typeof spec.fromResults === 'function',
        suggestions: {}, error: null, endpoint: spec.endpoint || null,
        motorTypes: spec.motorTypes || null,
    };
    (spec.fields || []).forEach(function (f) {
        rec.fields.push({ id: f[0], def: (f[2] === undefined ? null : f[2]),
                          secenekli: Array.isArray(f[3]) });
    });
    if (rec.hasFromResults) {
        let sug = null;
        try { sug = spec.fromResults(results); } catch (e) {
            rec.error = String(e && e.message ? e.message : e);
        }
        if (sug && typeof sug === 'object') {
            // undefined anahtarlar JSON.stringify'da DUSER; "oneri yok"
            // durumunu ayirt edebilmek icin acikca null'a cevriliyor.
            Object.keys(sug).forEach(function (k) {
                rec.suggestions[k] = (sug[k] === undefined) ? null : sug[k];
            });
        } else if (rec.error === null) {
            rec.error = 'fromResults nesne dondurmedi: ' + String(sug);
        }
    }
    out.specs[spec.componentId + ':' + spec.analysisId] = rec;
});
console.log(JSON.stringify(out));
"""


def _kosum_takimi(results):
    with tempfile.TemporaryDirectory() as tmp:
        harness = os.path.join(tmp, 'ac_harness.js')
        yuk = os.path.join(tmp, 'results.json')
        with open(harness, 'w', encoding='utf-8') as fh:
            fh.write(HARNESS_JS)
        with open(yuk, 'w', encoding='utf-8') as fh:
            json.dump(results, fh)
        proc = subprocess.run(
            ['node', harness, str(STATIC_JS), ','.join(PANEL_DOSYALARI), yuk],
            capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, (
        'node koşum takımı çöktü:\n' + proc.stderr[-3000:])
    veri = json.loads(proc.stdout.strip().splitlines()[-1])
    assert 'error' not in veri, veri.get('error')
    return veri


# ---------------------------------------------------------------------------
# Gerçek çözücü yanıtları (uydurma yük yok — örnek projeler hesap ucundan)
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def solver_results():
    from hrma.app import app

    app.config['TESTING'] = True
    out = {}
    with app.test_client() as client:
        for motor_type in MOTOR_TYPES:
            proje = json.loads(
                (EXAMPLES_DIR / (NAMES[motor_type] + '.hrma')).read_text(
                    encoding='utf-8'))
            yuk = _calculate_payload(motor_type, proje['inputs']['fields'])
            yanit = client.post(ENDPOINTS[motor_type], json=yuk,
                                headers=HEADERS)
            assert yanit.status_code == 200, (
                f'{ENDPOINTS[motor_type]} {yanit.status_code} döndü')
            out[motor_type] = yanit.get_json()
    return out


@pytest.fixture(scope='module')
def kiraci_kosumu(solver_results):
    """motor tipi -> node içinde GERÇEKTEN çalıştırılmış kiracı kaydı."""
    return {mt: _kosum_takimi(solver_results[mt]) for mt in MOTOR_TYPES}


def _motor_sozlugu(results):
    """Kiracıların `motorDict` yardımcısının Python ikizi (aynı kural)."""
    if not isinstance(results, dict):
        return None
    m = results.get('motor')
    return m if isinstance(m, dict) else results


def _pick(obj, yol):
    """Kiracıların `pick` yardımcısının Python ikizi (noktalı yol)."""
    cur = obj
    for parca in yol.split('.'):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(parca)
    return cur


# ---------------------------------------------------------------------------
# Sözleşme tabloları — kiracıların KENDİ belgelerinden (kaynak yorumları)
# ---------------------------------------------------------------------------
R_EVRENSEL = 8314.462618          # panels/cfd_panel.js: R_UNIVERSAL
PA_BAR = 1e5                      # tek kaynak: static/js/units_constants.js (PA_PER_BAR)

CHUG_DONGU_YOLLARI = (
    'combustion_analysis.stability_analysis.chug_loop',   # sıvı
    'combustion_stability.chug_loop',                     # hibrit
)

#: (kiracı satırı, alan) -> ((alt sınır, üst sınır), [(yük yolu, dönüşüm)])
#: Bantlar BİRİM hatasını yakalayacak şekilde seçildi; yollar kiracının
#: kaynağındaki öneri tablosunun AYNISIdır (sözleşme çift kayıtlıdır:
#: kaynak değişirse bu bekçi kırmızı verir ve değişiklik beyan edilir).
SOZLESME = {
    'nozzle_flow:cfd': {
        'P0_Pa': ((1e5, 5e8), (
            ('nozzle_flow_quasi1d.inputs.P0_Pa', 'aynen'),
            ('chamber_pressure', 'bar->Pa'))),
        'T0_K': ((500.0, 6000.0), (
            ('nozzle_flow_quasi1d.inputs.T0_K', 'aynen'),
            ('chamber_temperature', 'aynen'))),
        'gamma': ((1.0, 1.8), (
            ('nozzle_flow_quasi1d.inputs.gamma', 'aynen'),
            ('gamma', 'aynen'))),
        'R_J_per_kgK': ((100.0, 900.0), (
            ('nozzle_flow_quasi1d.inputs.R_J_kgK', 'aynen'),
            ('nozzle_flow_quasi1d.inputs_used.gas_constant_J_kgK', 'aynen'),
            ('molecular_weight', 'R=Ru/MW'))),
        'P_ambient_Pa': ((1e2, 2e5), (
            ('nozzle_expansion_screen.ambient_pressure_bar', 'bar->Pa'),
            ('nozzle_flow_separation.ambient_pressure_Pa', 'aynen'),
            ('nozzle_design.performance.ambient_pressure', 'bar->Pa'))),
    },
    'chamber_acoustics:acoustic_modes': {
        'sound_speed_m_s': ((100.0, 3000.0), (
            ('acoustic_modes.sound_speed_m_s', 'aynen'),
            ('combustion_analysis.stability_analysis.acoustic_modes'
             '.sound_speed_m_s', 'aynen'))),
        'chamber_length_m': ((0.02, 20.0), (
            ('acoustic_modes.inputs.chamber_length', 'aynen'),
            ('combustion_analysis.stability_analysis.acoustic_modes'
             '.inputs.chamber_length', 'aynen'))),
        'gamma': ((1.0, 1.8), (
            ('acoustic_modes.inputs.gamma', 'aynen'),
            ('combustion_analysis.stability_analysis.acoustic_modes'
             '.inputs.gamma', 'aynen'))),
        'nozzle_entrance_mach': ((0.0, 1.0), (
            ('combustion_stability.acoustic_response_threshold'
             '.mean_flow_mach_M_N', 'aynen'),
            # ÖH defter P17B3-03 (D23): sıvı bağlaması M_N'i KENDİ akustik
            # mod bloğunda çözüp yayımlar (hibrit/katıdaki eşik bloğunun
            # karşılığı sıvıda yok). Yol BELGELENİR ki öneri hâlâ "yükten
            # geliyor mu" diye ölçülebilsin - sözleşme gevşetilmiyor.
            ('combustion_analysis.stability_analysis.acoustic_modes'
             '.mean_flow_mach_M_N', 'aynen'),)),
    },
    'chamber_acoustics:combustion_stability': {
        'dp_ratio_j': ((0.0, 10.0), tuple(
            (p + '.inputs.dp_ratio_j', 'aynen') for p in CHUG_DONGU_YOLLARI)),
        'tau_s': ((1e-6, 1.0), tuple(
            (p + '.inputs.tau_s', 'aynen') for p in CHUG_DONGU_YOLLARI)),
        'tau_c_s': ((1e-6, 1.0), tuple(
            (p + '.inputs.tau_c_s', 'aynen') for p in CHUG_DONGU_YOLLARI)
            + (('combustion_stability.chamber_time_constant.tau_c_s',
                'aynen'),)),
        'tau_f_s': ((1e-6, 1.0), tuple(
            (p + '.inputs.tau_f_s', 'aynen') for p in CHUG_DONGU_YOLLARI)),
    },
}

#: 27 Ağustos 2026 ölçümü — bugün GERÇEKTEN öneri üreten alanlar.
#: TEK YÖNLÜ çapa: küme küçülemez (sessizce kaybolan öneri kusurdur),
#: büyümesi serbesttir (yeni kaynak eklenmesi onarımdır).
OLCULEN_ONERI_KAPSAMI = {
    'hybrid': {
        'nozzle_flow:cfd': ('P0_Pa', 'P_ambient_Pa', 'R_J_per_kgK', 'T0_K',
                            'gamma'),
        'chamber_acoustics:acoustic_modes': (
            'chamber_length_m', 'gamma', 'nozzle_entrance_mach',
            'sound_speed_m_s'),
        'chamber_acoustics:combustion_stability': (
            'dp_ratio_j', 'tau_c_s', 'tau_s'),
    },
    'solid': {
        'nozzle_flow:cfd': ('P0_Pa', 'P_ambient_Pa', 'R_J_per_kgK', 'T0_K',
                            'gamma'),
        'chamber_acoustics:acoustic_modes': (
            'chamber_length_m', 'gamma', 'nozzle_entrance_mach',
            'sound_speed_m_s'),
        # Katıda J ve τ'nun kaynağı yok (kiracının kendi beyanı); yalnız
        # τ_c chamber_time_constant bloğundan geliyor.
        'chamber_acoustics:combustion_stability': ('tau_c_s',),
    },
    'liquid': {
        'nozzle_flow:cfd': ('P0_Pa', 'P_ambient_Pa', 'R_J_per_kgK', 'T0_K',
                            'gamma'),
        # Sıvıda M_N kaynağı yok (kiracının kaynak tablosundaki not);
        # alan boş kalır, kullanıcı elle girer.
        'chamber_acoustics:acoustic_modes': (
            'chamber_length_m', 'gamma', 'sound_speed_m_s'),
        'chamber_acoustics:combustion_stability': (
            'dp_ratio_j', 'tau_c_s', 'tau_s'),
    },
}


def _kayit(kosum, satir):
    ozet = kosum['specs']
    assert satir in ozet, (
        f'{satir} Merkez kayıt defterinde yok: {sorted(ozet)}')
    rec = ozet[satir]
    assert rec['error'] is None, (
        f'{satir}.fromResults hata verdi: {rec["error"]}')
    return rec


# ===========================================================================
# 1. KAYIT DEFTERİ EŞLİĞİ — kiracı gerçekten kaydoluyor mu?
# ===========================================================================
class TestKayitDefteriEsligi:
    """Merkez muafiyetinin ÖBÜR yakası (D3 byFile deseni, KOŞUM tabanlı)."""

    def test_kiraci_turetmesi_daralmadi(self, kiraci_kosumu):
        """Kiracı kümesi node koşumunda ÖLÇÜLÜR, kaynaktan tahmin edilmez."""
        for motor_type in MOTOR_TYPES:
            by_file = kiraci_kosumu[motor_type]['byFile']
            olculen = {ad for ad, satirlar in by_file.items() if satirlar}
            eksik = sorted(set(TARIHSEL_KIRACILAR) - olculen)
            assert not eksik, (
                f'{motor_type}: Merkez kiracısı olduğu ölçülen panel(ler) '
                f'artık hiç satır kaydetmiyor: {eksik} — kayıt '
                '`if (window.AnalysisCenter && …)` kapısının arkasına '
                'düşmüş olabilir; panel ekrandan SESSİZCE kalkar')
            yeni = sorted(olculen - set(TARIHSEL_KIRACILAR))
            assert not yeni, (
                f'{motor_type}: YENİ Merkez kiracısı doğdu: {yeni} — '
                'sözleşme tabloları (SOZLESME + OLCULEN_ONERI_KAPSAMI) '
                'genişletilmeli, yoksa yeni kiracının birimi/şeması '
                'bekçisiz kalır')

    def test_kiraci_satirlari_daralmadi(self, kiraci_kosumu):
        """Dosya başına kaydolan SATIRLAR (bileşen:analiz) sabit mi?

        Kiracı iki satır kaydediyorsa (stability: akustik + chug) biri
        sessizce düşerse Merkez o satırı "kiracısı yok" diye gri basar ve
        kullanıcı analizin kaybolduğunu fark etmez.
        """
        for motor_type in MOTOR_TYPES:
            by_file = kiraci_kosumu[motor_type]['byFile']
            for ad, beklenen in TARIHSEL_KIRACI_SATIRLARI.items():
                gercek = tuple(by_file.get(ad) or ())
                assert set(gercek) >= set(beklenen), (
                    f'{motor_type}/{ad}: 27 Ağu 2026\'da kaydolan satırların '
                    f'bir kısmı artık kaydolmuyor (beklenen {beklenen}, '
                    f'ölçülen {gercek})')
                assert len(gercek) == len(set(gercek)), (
                    f'{motor_type}/{ad}: aynı satır iki kez kaydolmuş: '
                    f'{gercek}')

    def test_yazilmis_her_spec_kaydoldu(self, kiraci_kosumu):
        """Panelin window'a KOYDUĞU her spec kayıt defterinde olmalı.

        "Spec yazılmış ama register çağrısı unutulmuş/kapıya takılmış"
        hâli statik taramayla değil, koşumla yakalanır: her kiracı kendi
        hata ayıklama yüzeyinde (``window.CfdPanel.spec``,
        ``window.StabilityPanel.specAcoustic`` …) spec'lerini açıyor.
        """
        for motor_type in MOTOR_TYPES:
            kosum = kiraci_kosumu[motor_type]
            for ad in TARIHSEL_KIRACILAR:
                acik = set(kosum['exposedByFile'].get(ad) or ())
                kayitli = set(kosum['byFile'].get(ad) or ())
                assert acik, (
                    f'{motor_type}/{ad}: panel window\'a hiç spec açmıyor — '
                    'bu iddia artık bir şey ölçmüyor, yüzey değişmiş')
                kaydolmayan = sorted(acik - kayitli)
                assert not kaydolmayan, (
                    f'{motor_type}/{ad}: panel şu spec\'leri kuruyor ama '
                    f'Merkez\'e kaydetmiyor: {kaydolmayan}')

    def test_merkez_kiracisi_guvertede_gorunmuyor(self, kiraci_kosumu):
        """`test_panel_units_v2626` muafiyetinin dayanağı ölçülür.

        O bekçi bu iki paneli "güverte kayıt defterine hiç girmiyor" diye
        muaf tutuyor. Muafiyet türetilmiş bir ölçüt olduğu için sessizce
        genişleyebilir: kiracı bir gün güverteye de kaydolursa iki bekçi
        de onu görmez sanır. Bu iddia o yolu kapatır.
        """
        for motor_type in MOTOR_TYPES:
            dock = kiraci_kosumu[motor_type]['dockByFile']
            for ad in TARIHSEL_KIRACILAR:
                assert not dock.get(ad), (
                    f'{motor_type}/{ad} artık Analiz GÜVERTESİ\'ne de '
                    f'kaydoluyor ({dock.get(ad)}) — test_panel_units_v2626 '
                    'muafiyeti yeniden ölçülmeli')

    def test_hicbir_panel_iki_deftere_birden_kaydolmuyor(self, kiraci_kosumu):
        """Güverte ⟷ Merkez ayrımı ölçülür (kapsam boşluğu doğmasın)."""
        for motor_type in MOTOR_TYPES:
            kosum = kiraci_kosumu[motor_type]
            ikili = sorted(ad for ad in PANEL_DOSYALARI
                           if (kosum['byFile'].get(ad)
                               and kosum['dockByFile'].get(ad)))
            assert not ikili, (
                f'{motor_type}: şu panel(ler) hem Merkez\'e hem Güverte\'ye '
                f'kaydoluyor: {ikili} — iki bekçinin kapsam ayrımı geçersiz')

    def test_kiraci_satirlari_tasarim_matrisinde(self, kiraci_kosumu):
        """Kayıt §2 matrisinde olmalı; yoksa satır "matris dışı" basılır."""
        kosum = kiraci_kosumu[MOTOR_TYPES[0]]
        matris = set(kosum['matrix'])
        assert matris, 'Merkez matrisi boş okundu — çıkarım bozuk'
        for ad, satirlar in kosum['byFile'].items():
            disarda = [s for s in satirlar if s not in matris]
            assert not disarda, (
                f'{ad}: şu kiracı satırları tasarım §2 matrisinde yok: '
                f'{disarda} — Merkez onları "matris dışı" beyanıyla basar')


# ===========================================================================
# 2. fromResults SÖZLEŞMESİ — şema / tip / birim / kaynak
# ===========================================================================
class TestFromResultsSozlesmesi:
    """Kiracıların önerileri gerçek çözücü yanıtıyla ölçülür."""

    @pytest.mark.parametrize('motor_type', MOTOR_TYPES)
    def test_fromresults_gercek_yanitta_patlamiyor(self, kiraci_kosumu,
                                                   motor_type):
        hatalar = []
        for satir, rec in kiraci_kosumu[motor_type]['specs'].items():
            if rec['error']:
                hatalar.append(f'{satir} -> {rec["error"]}')
        assert not hatalar, (
            'kiracı fromResults gerçek çözücü yanıtında istisna attı:\n  '
            + '\n  '.join(hatalar))

    @pytest.mark.parametrize('motor_type', MOTOR_TYPES)
    def test_oneri_anahtarlari_bildirilen_alan(self, kiraci_kosumu,
                                               motor_type):
        """Merkez bilinmeyen anahtarı SESSİZCE yutar — o yüzden sınanır."""
        for satir in SOZLESME:
            rec = _kayit(kiraci_kosumu[motor_type], satir)
            alanlar = {f['id'] for f in rec['fields']}
            yabanci = sorted(set(rec['suggestions']) - alanlar)
            assert not yabanci, (
                f'{motor_type}/{satir}: fromResults bildirilmeyen alan(lar) '
                f'öneriyor: {yabanci} — Merkez bunları sessizce yutar, '
                f'kullanıcı öneriyi hiç görmez (bildirilen: {sorted(alanlar)})')

    @pytest.mark.parametrize('motor_type', MOTOR_TYPES)
    def test_oneri_degerleri_sonlu_sayi(self, kiraci_kosumu, motor_type):
        for satir in SOZLESME:
            rec = _kayit(kiraci_kosumu[motor_type], satir)
            for alan, deger in sorted(rec['suggestions'].items()):
                assert isinstance(deger, (int, float)) and not isinstance(
                    deger, bool), (
                    f'{motor_type}/{satir}/{alan}: öneri sayı değil '
                    f'({deger!r}) — form alanına bu değer YAZILIR')
                assert math.isfinite(float(deger)), (
                    f'{motor_type}/{satir}/{alan}: öneri sonlu değil '
                    f'({deger!r})')

    @pytest.mark.parametrize('motor_type', MOTOR_TYPES)
    def test_oneri_birim_bandinda(self, kiraci_kosumu, motor_type):
        """BİRİM sözleşmesi: bar/mm sızıntısı bandın dışına düşer."""
        for satir, tablo in SOZLESME.items():
            rec = _kayit(kiraci_kosumu[motor_type], satir)
            for alan, deger in sorted(rec['suggestions'].items()):
                assert alan in tablo, (
                    f'{motor_type}/{satir}: {alan!r} için birim sözleşmesi '
                    'yazılmamış — yeni öneri alanı bandsız geçemez')
                (alt, ust), _yollar = tablo[alan]
                assert alt <= float(deger) <= ust, (
                    f'{motor_type}/{satir}/{alan}: öneri {deger!r} fiziksel '
                    f'bandın ({alt}, {ust}) dışında — birim hatası '
                    '(bar↔Pa, mm↔m) en olası sebeptir')

    @pytest.mark.parametrize('motor_type', MOTOR_TYPES)
    def test_oneri_degeri_yukten_geliyor(self, solver_results, kiraci_kosumu,
                                         motor_type):
        """Sayı UYDURULAMAZ: yükte belgelenmiş bir yoldan gelmeli.

        Değer ya yolun kendisidir ya da beyan edilmiş dönüşümüdür
        (``bar→Pa``, ``R = 8314,462618 / MW``). Panel bir sabit koysa ya
        da yanlış ölçek uygulasa bu iddia kırmızı verir.
        """
        motor = _motor_sozlugu(solver_results[motor_type])
        assert isinstance(motor, dict), 'çözücü yanıtı sözlük değil'
        for satir, tablo in SOZLESME.items():
            rec = _kayit(kiraci_kosumu[motor_type], satir)
            for alan, deger in sorted(rec['suggestions'].items()):
                assert alan in tablo, (
                    f'{motor_type}/{satir}: {alan!r} için kaynak sözleşmesi '
                    'yazılmamış — öneri nereden geldiği ölçülmeden geçemez')
                _band, yollar = tablo[alan]
                adaylar = []
                for yol, donusum in yollar:
                    ham = _pick(motor, yol)
                    if not isinstance(ham, (int, float)) or isinstance(
                            ham, bool):
                        continue
                    if not math.isfinite(float(ham)):
                        continue
                    if donusum == 'aynen':
                        adaylar.append((yol, float(ham)))
                    elif donusum == 'bar->Pa':
                        adaylar.append((yol, float(ham) * PA_BAR))
                    elif donusum == 'R=Ru/MW':
                        if float(ham) != 0.0:
                            adaylar.append((yol, R_EVRENSEL / float(ham)))
                    else:                              # pragma: no cover
                        raise AssertionError(f'bilinmeyen dönüşüm {donusum}')
                assert adaylar, (
                    f'{motor_type}/{satir}/{alan}: öneri {deger!r} üretildi '
                    'ama yükte belgelenmiş yolların HİÇBİRİ sonlu sayı '
                    f'taşımıyor ({[y for y, _d in yollar]}) — sayı nereden '
                    'geldi?')
                assert any(math.isclose(float(deger), d, rel_tol=1e-9,
                                        abs_tol=0.0)
                           for _y, d in adaylar), (
                    f'{motor_type}/{satir}/{alan}: öneri {deger!r} '
                    'belgelenmiş kaynakların hiçbirine eşit değil '
                    f'(adaylar: {adaylar}) — ölçek/yol sözleşmesi kırılmış')

    @pytest.mark.parametrize('motor_type', MOTOR_TYPES)
    def test_oneri_kapsami_daralmadi(self, kiraci_kosumu, motor_type):
        """Sessizce kaybolan öneri = kusur (kullanıcı boş alan görür)."""
        for satir, beklenen in OLCULEN_ONERI_KAPSAMI[motor_type].items():
            rec = _kayit(kiraci_kosumu[motor_type], satir)
            uretilen = {a for a, d in rec['suggestions'].items()
                        if isinstance(d, (int, float))
                        and not isinstance(d, bool)}
            eksik = sorted(set(beklenen) - uretilen)
            assert not eksik, (
                f'{motor_type}/{satir}: 27 Ağu 2026\'da öneri üreten şu '
                f'alanlar artık üretmiyor: {eksik} — kaynak yolu kırılmış '
                f'olabilir (bugün üretilenler: {sorted(uretilen)})')

    def test_sayisal_alanlarin_uydurma_varsayilani_yok(self, kiraci_kosumu):
        """Kiracıların KENDİ beyanı: sayısal alanların sonlu varsayılanı yok.

        İkisi de dosya başında "öneri gelmeyen alan boş kalır ve body()
        isteği durdurur (uydurma sayı gösterilmez)" diyor. Beyan bir
        yorumda kalmasın diye ölçülür.
        """
        kosum = kiraci_kosumu[MOTOR_TYPES[0]]
        ihlal = []
        for satir in SOZLESME:
            rec = _kayit(kosum, satir)
            for alan in rec['fields']:
                if alan['secenekli']:
                    continue          # seçim listesi: varsayılan bir SEÇİM
                if isinstance(alan['def'], (int, float)) and not isinstance(
                        alan['def'], bool):
                    ihlal.append(f'{satir}/{alan["id"]} = {alan["def"]!r}')
        assert not ihlal, (
            'Merkez kiracısının sayısal alanında SONLU varsayılan var — '
            f'kullanıcıya uydurma sayı gösterilir: {ihlal}')


# ===========================================================================
# 3. Kiracı kaynağının sözleşme çapası (kaynak ⟷ bu bekçi ayrışmasın)
# ===========================================================================
def test_sozlesme_tablosu_kiraci_kaynagindan_sapmamis():
    """Bekçinin yol tablosu kiracının kaynağında GERÇEKTEN geçiyor mu?

    Bu dosya öneri kaynaklarını çift kayıtlı tutuyor (kiracıda + burada).
    Çift kayıt sessizce ayrışabilir; bu iddia her yolun kiracı kaynağında
    dizge olarak durduğunu ölçer. Kiracı yeni bir yol eklerse ya da eski
    yolu değiştirirse bekçi kırmızı verir ve tablo elle güncellenir.
    """
    kaynaklar = {
        'nozzle_flow:cfd': (PANELS_DIR / 'cfd_panel.js').read_text(
            encoding='utf-8'),
        'chamber_acoustics:acoustic_modes': (
            PANELS_DIR / 'stability_panel.js').read_text(encoding='utf-8'),
        'chamber_acoustics:combustion_stability': (
            PANELS_DIR / 'stability_panel.js').read_text(encoding='utf-8'),
    }
    eksik = []
    for satir, tablo in SOZLESME.items():
        metin = kaynaklar[satir]
        for alan, (_band, yollar) in tablo.items():
            for yol, _donusum in yollar:
                # Kaynak yolu satır sonlarında bölünmüş dizge birleştirmesiyle
                # yazılabiliyor; son parçayı aramak yeterli ve kararlıdır.
                parca = yol.split('.')[-1]
                if parca not in metin:
                    eksik.append(f'{satir}/{alan}: {yol}')
    assert not eksik, (
        'sözleşme tablosundaki şu kaynak yolları kiracı kaynağında '
        f'geçmiyor (tablo bayat): {eksik}')


def test_merkez_kayit_sozlesmesi_yerinde():
    """`register` sözleşmesinin zorunlu alanları hâlâ aynı mı?

    Bu bekçi ``componentId``/``analysisId``/``endpoint``/``render`` dörtlüsü
    üstüne kurulu (kayıt kimliği bu dörtlüden doğuyor). Sözleşme değişirse
    burada haber verilir.
    """
    metin = MERKEZ_KAYNAGI.read_text(encoding='utf-8')
    for parca in ('spec.componentId', 'spec.analysisId', 'spec.endpoint',
                  'spec.render'):
        assert parca in metin, (
            f'analysis_center.js `register` sözleşmesinde {parca} artık '
            'yok — kiracı kimliği başka bir dörtlüden doğuyor olabilir')


def test_d3_yapisal_taramasi_kiracilari_goruyor():
    """D3'ün kaynak taraması Merkez kiracılarını görebiliyor mu?

    ÖH D26 · defter **OH-B4-03** — borç imi KALKTI.

    Borcun kaynağı: ``test_panel_units_v2626._js_kod_govdesi`` iki fazlı
    çalışıyordu (satır satır tırnak takibi + sonda ``re.S``li
    ``_STRING_RE``). Satırda kapanmayan bir kesme işareti (Türkçe
    yorumlardaki *"Merkez'in"* gibi) ikinci fazda dosyanın ilerisine
    kadar HER ŞEYİ yutuyordu. ÖLÇÜLDÜ (``once_ohb403.json``, taban
    7751531): ``fromResults`` bildiren panel **9** (13 değil — defterin
    "11" sayısı da ölçümle 9'a düzeltildi), Merkez kiracısı **0**,
    ``safety_panel.js``in %97'si / ``cfd_panel.js``in %94'ü /
    ``stability_panel.js``in %96'sı kod gövdesinden düşüyordu.

    Süzgeç tek geçişli durum makinesine çevrildi (yorum ve dize aynı
    geçişte tüketilir; yorumun içindeki kesme işareti tarayıcıya hiç
    ulaşmaz). ÖLÇÜLDÜ (``sonra_ohb403.json``): ``fromResults`` **13**,
    güverte kiracısı **11**, Merkez kiracısı **2**. Muafiyet artık
    fiilen işliyor.
    """
    kor = []
    for ad in TARIHSEL_KIRACILAR:
        kod = _js_kod_govdesi((PANELS_DIR / ad).read_text(encoding='utf-8'))
        if not (_FROM_RESULTS_TANIM_RE.search(kod)
                and _CENTER_REGISTER_RE.search(kod)):
            kor.append(ad)
    assert not kor, (
        'D3 yapısal taraması şu Merkez kiracılarını göremiyor (yorum/dizge '
        f'süzgeci gövdeyi yutuyor): {kor}')


def test_kiraci_kayit_kapisi_beyanli():
    """Kayıt kapısı sessiz düşmez: `else` dalı konsola ADIYLA yazar."""
    for ad in TARIHSEL_KIRACILAR:
        metin = (PANELS_DIR / ad).read_text(encoding='utf-8')
        assert re.search(r'window\.AnalysisCenter\s*&&', metin), (
            f'{ad}: kiracı kaydı Merkez varlığını denetlemiyor')
        assert 'AnalysisCenter yok' in metin or 'kaydolamad' in metin, (
            f'{ad}: Merkez yüklenmemişse kiracı SESSİZCE düşüyor — yükleme '
            'sırası hatası ekranda hiçbir iz bırakmaz')
