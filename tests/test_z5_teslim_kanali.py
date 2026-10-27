"""
ÖH Z5 — Paket A: TESLİM KANALI (app.js uyarı/hüküm boru hattı + ihraç).

Bu dosya, motorun/ucun ÜRETTİĞİ hükmün ve uyarının kullanıcıya GERÇEKTEN
ulaştığını ölçer. Beş kalem:

  A1 (P11B2-01, KRİTİK) — ``/calculate`` yanıtındaki yapısal hüküm
     (``status``), risk seviyesi (``risk_level``) ve ADLANDIRILMIŞ onarım
     önerileri (``recommendations``) ana sonuç ekranına iniyor mu?
     ÖLÇÜLEN KUSUR (taban 9ddbb22, hibrit varsayılan koşum): yanıt
     ``UNSAFE`` + ``HIGH`` + 7 öneri taşırken ana ekranda bunlardan
     HİÇBİRİ yoktu — DOM'da 0 geçiş.

  A2 (P11B2-06) — motorun ``severity: 'critical'`` uyarıları amber
     ``WARNING`` olarak basılıyordu. ÖLÇÜLEN: 10 uyarı ögesinin 10'u
     ``warning-regular``, kritik rozet sayısı 0 (oysa 4 kayıt kritik).

  A3 (P14M3-04) — ``displayWarnings`` hiçbir testte çalışmıyordu (grep 0),
     bu yüzden uyarı dizisini boşaltan mutasyon yakalanmıyordu. Ayrıca DİL
     DEĞİŞİMİ yolu motor uyarılarını hiç okumuyordu: aynı sonuç sözlüğüyle
     10 öge yerine 5 öge basılıyor, 4 kritik kayıt ekrandan siliniyordu.

  A4 (OH-Z2-05) — ``warn.liquid.wall_thickness_below_required`` (severity
     critical) ÜRETİLİYOR ama hiçbir ihraç dosyasına inmiyordu. ÖLÇÜLEN:
     özet PDF metninde kodun geçiş sayısı 0; komple paket ZIP'inde uyarı
     dosyası yok.

  A5 (OH-Z2-07) — ``structural_design_basis`` künyesi ekranda YALNIZ
     ``title=`` ipucu içinde duruyordu; görünür metinde hiç yoktu.

Kapsam: Flask ``test_client`` (sunucuya port BAĞLANMAZ) + ``node`` ile
app.js'in GERÇEK çalıştırılması (sahte DOM) + kaynak sözleşmesi taraması.
Sahte veri YOKTUR: DOM ölçümleri, çözücünün o koşumda ürettiği yanıtın
kendi alanlarına karşı doğrulanır.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import warnings
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

warnings.filterwarnings('ignore')

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_JS = REPO_ROOT / 'hrma' / 'static' / 'js' / 'app.js'
NODE = shutil.which('node')

#: Hibrit varsayılan tasarım — bu koşum UNSAFE hüküm + 7 öneri üretiyor.
Z5_HIBRIT_ISTEK = {
    'motor_type': 'hybrid', 'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
    'chamber_pressure': 20.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'include_plots': False,
}

#: Sıvı koşum: cidar 1 mm — gerekenin (2,0 mm) ALTINDA, kritik girdi hükmü.
Z5_SIVI_INCE_CIDAR = {
    'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'thrust': 10000,
    'chamber_pressure': 100, 'mixture_ratio': 2.5,
    'nozzle_expansion_ratio': 50, 'max_burn_duration': 400,
    'combustion_efficiency': 97, 'contraction_ratio': 4,
    'characteristic_length': 1.2,
    'chamber_wall_thickness': 1,
    'cooling_type': 'regenerative', 'injector_type': 'impinging',
    'engine_cycle': 'pressure_fed', 'safety_factor': 2.5,
    # v3.0.1 (26 Eki, L-A SV-03): basınç beslemeli çevrimde besleme basıncı
    # verilmezse uç 422 pressure_fed_feed_pressure_not_supplied döner (tank
    # gereksinimi tek tanım: Pc + ΔP_enj + ceket + hat). Bu gövdenin konusu
    # ince cidar uyarısının taşınması; besleme gereksinimi (ölçüldü: yakıt
    # 126,03 bar) karşılanacak bir değer verilir.
    'feed_pressure': 140,
}

Z5_CIDAR_UYARI_KODU = 'warn.liquid.wall_thickness_below_required'


# ---------------------------------------------------------------------------
# node koşum takımı — app.js'i sahte DOM ile GERÇEKTEN çalıştırır
# ---------------------------------------------------------------------------
#: Sayfada gerçekten var olan kaplar (advanced.html); başka kap uydurulmaz.
Z5_DOM_IDS = ('warningsPanel', 'warningsList', 'performanceMetrics')

Z5_HARNESS = r"""
'use strict';
const fs = require('fs');
const vm = require('vm');
const APP_JS = process.argv[2];
const R = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

function El(id) {
    this.id = id; this.style = {}; this.dataset = {};
    this.innerHTML = ''; this.children = [];
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function () {};
El.prototype.getAttribute = function () { return null; };
El.prototype.querySelectorAll = function () { return []; };
El.prototype.addEventListener = function () {};

const nodes = {};
__IDS__.forEach(function (id) { nodes[id] = new El(id); });

const sandbox = {
    console: { log: function () {}, warn: function () {}, error: function () {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    setInterval: function () {}, clearInterval: clearInterval,
    fetch: function () { return Promise.reject(new Error('sandbox: ag yok')); },
    JSON: JSON, Math: Math, Number: Number, Array: Array, Object: Object,
    String: String, Boolean: Boolean, isFinite: isFinite, Date: Date,
    parseFloat: parseFloat, parseInt: parseInt, alert: function () {},
    document: {
        readyState: 'complete',
        createElement: function (t) { return new El(t); },
        querySelector: function () { return null; },
        querySelectorAll: function () { return []; },
        getElementById: function (id) { return nodes[id] || null; },
        addEventListener: function () {},
    },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(APP_JS, 'utf8'), sandbox, { filename: APP_JS });

function say(dom) {
    return {
        oge: (dom.match(/class="warning-item /g) || []).length,
        kritik_sinif: (dom.match(/warning-item warning-critical/g) || []).length,
        amber_sinif: (dom.match(/warning-item warning-regular/g) || []).length,
        bilgi_sinif: (dom.match(/warning-item warning-info/g) || []).length,
        kritik_rozet: (dom.match(/>CRITICAL</g) || []).length,
        amber_rozet: (dom.match(/>WARNING</g) || []).length,
    };
}
function uyarilar(res) {
    nodes.warningsList.innerHTML = '';
    nodes.warningsPanel.style.display = '';
    sandbox.displayWarnings(sandbox.collectResultWarnings(res), res.validation);
    const out = say(nodes.warningsList.innerHTML);
    out.panel = nodes.warningsPanel.style.display;
    out.dom = nodes.warningsList.innerHTML;
    return out;
}
function ekran(res) {
    nodes.performanceMetrics.innerHTML = '';
    sandbox.displayPerformanceMetrics(res.motor, res);
    return nodes.performanceMetrics.innerHTML;
}
function kopya(o) { return JSON.parse(JSON.stringify(o)); }

const OUT = {};
const sf = ((R.motor || {}).structural_analysis || {}).safety_analysis || {};
const dbasis = R.structural_design_basis || {};

// --- Kaynak sayımı: yanıtın KENDİ kayıtları (beklenti buradan gelir) ----
const kanal = sandbox.collectResultWarnings(R);
OUT.kaynak = {
    kanal_toplam: kanal.length,
    kanal_kritik: kanal.filter(sandbox.warnIsCritical).length,
    // v3.0.1 (V301/H3): 'info' önemli kayıt (doymuş N2O girişi) amber DEĞİL,
    // kendi sınıfıyla (warning-info) basılır; beklenti ayrı sayılır.
    kanal_bilgi: kanal.filter(sandbox.warnIsInfo).length,
    validation_kritik: ((R.validation || {}).critical_warnings || []).length,
    validation_normal: ((R.validation || {}).regular_warnings || []).length,
    oneri: (sf.recommendations || []).length,
};

// --- 1) Uyarı kanalı (hesap sonrası = dil değişimi; ortak toplayıcı) ----
OUT.uyari = uyarilar(R);
delete OUT.uyari.dom;

// --- 2) MUTASYON: motor uyarı dizisi render ÖNCESİ boşaltılırsa ---------
const bos = kopya(R);
if (bos.motor) { bos.motor.warnings = []; bos.motor.design_warnings = []; }
OUT.mutasyon_bos = uyarilar(bos);
delete OUT.mutasyon_bos.dom;

// --- 3) input_warnings kanalı (OH-Z2-05 taşıma sözleşmesi) -------------
const ig = kopya(R);
if (ig.motor) { ig.motor.warnings = []; ig.motor.design_warnings = []; }
ig.validation = null;
ig.injector = null;
ig.motor.input_warnings = [{
    code: 'warn.liquid.wall_thickness_below_required',
    params: { t_used_mm: 1.0, t_required_mm: 2.0 },
    severity: 'critical',
}];
const igOut = uyarilar(ig);
OUT.input_warnings = {
    oge: igOut.oge, kritik_sinif: igOut.kritik_sinif,
    kod_dom_da: igOut.dom.indexOf(
        'warn.liquid.wall_thickness_below_required') !== -1,
};

// --- 4) Yapısal hüküm şeridi (A1 + A5) ---------------------------------
const pm = ekran(R);
// title="..." içeriği çıkarılırsa geriye GÖRÜNÜR metin kalır.
const gorunur = pm.replace(/title="[^"]*"/g, '');
OUT.hukum = {
    serit: pm.indexOf('structuralVerdictStrip') !== -1,
    status_gorunur: !!sf.status
        && gorunur.indexOf('STRUCTURE: ' + sf.status) !== -1,
    risk_gorunur: !!sf.risk_level
        && gorunur.indexOf('RISK: ' + sf.risk_level) !== -1,
    oneri_ekranda: (sf.recommendations || []).filter(function (r) {
        return gorunur.indexOf(r.code) !== -1;
    }).length,
    kunye_gorunur: gorunur.indexOf('hd-verdict-kunye') !== -1,
    kunye_alanlari: ['design_mode', 'wall_thickness_source',
                     'is_verification', 'stations_not_verified']
        .filter(function (k) {
            return dbasis[k] !== undefined && gorunur.indexOf(k + ':') !== -1;
        }),
    dbasis_mesaji_gorunur: !!dbasis.message
        && gorunur.indexOf(dbasis.message.slice(0, 40)) !== -1,
};

// --- 5) MUTASYON: hüküm alanı yoksa şerit BASILMAZ (fail-closed) -------
const yok = kopya(R);
delete yok.motor.structural_analysis;
delete yok.structural_design_basis;
OUT.hukum_yok = { serit: ekran(yok).indexOf('structuralVerdictStrip') !== -1 };

// --- 6) MUTASYON: öneri listesi boşaltılırsa madde kalmamalı -----------
const onerisiz = kopya(R);
onerisiz.motor.structural_analysis.safety_analysis.recommendations = [];
const pm2 = ekran(onerisiz).replace(/title="[^"]*"/g, '');
OUT.onerisiz = {
    oneri_ekranda: (sf.recommendations || []).filter(function (r) {
        return pm2.indexOf(r.code) !== -1;
    }).length,
};

process.stdout.write(JSON.stringify(OUT));
"""


def _node_kosum(response_json):
    """app.js'i sahte DOM ile çalıştırır, ölçüm sözlüğünü döndürür."""
    script = Z5_HARNESS.replace('__IDS__', json.dumps(list(Z5_DOM_IDS)))
    with tempfile.TemporaryDirectory() as tmp:
        harness = os.path.join(tmp, 'harness.js')
        veri = os.path.join(tmp, 'yanit.json')
        with open(harness, 'w', encoding='utf-8') as fh:
            fh.write(script)
        with open(veri, 'w', encoding='utf-8') as fh:
            json.dump(response_json, fh)
        proc = subprocess.run([NODE, harness, str(APP_JS), veri],
                              capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, 'node çöktü:\n' + proc.stderr[-3000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------------------
# Fikstürler — ağır uçlar modül kapsamında BİR kez koşar
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def hibrit(client):
    # v3.0.1 (V301/H-termal): korunan yolda (yakıt bloğu + HRMA'nın
    # boyutlandırdığı astar) bu hibritin ne kritik termal kaydı ne de UNSAFE
    # yapısal hükmü kalır — ikisi de çıplak cidarı ≈ adyabatik sıcaklıkta
    # değerlendiren model kusurundan doğuyordu. Bu dosyanın konusu TESLİM
    # KANALIDIR (hüküm üretildiyse ekrana iniyor mu); hükmü üreten senaryo
    # artık ürünün fail-closed termal yoludur (astar boyutlandırması
    # koşmadı: kritik hüküm aynen kalır), ``tests.support.hibrit_termal``.
    from tests.support.hibrit_termal import astar_boyutlandirmasi_kosmaz
    with astar_boyutlandirmasi_kosmaz():
        r = client.post('/calculate', json=Z5_HIBRIT_ISTEK)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def sivi(client):
    r = client.post('/calculate_liquid', json=Z5_SIVI_INCE_CIDAR)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def dom(hibrit):
    if not NODE:
        pytest.skip('node bulunamadı')
    return _node_kosum(hibrit)


def _safety(hibrit):
    return ((hibrit.get('motor') or {}).get('structural_analysis') or {}) \
        .get('safety_analysis') or {}


# ---------------------------------------------------------------------------
# A1 — P11B2-01 (KRİTİK): hüküm + risk + adlandırılmış öneriler ekrana
# ---------------------------------------------------------------------------
class TestA1YapisalHukumEkrana:

    def test_yanit_hukum_risk_ve_onerileri_yayimliyor(self, hibrit):
        """Sözleşme: taşınacak alanlar yanıtta GERÇEKTEN var."""
        sf = _safety(hibrit)
        assert isinstance(sf.get('status'), str) and sf['status'], (
            'safety_analysis.status yok — taşıma kaleminin girdisi kayıp')
        assert isinstance(sf.get('risk_level'), str) and sf['risk_level']
        oneriler = sf.get('recommendations')
        assert isinstance(oneriler, list) and oneriler, (
            'recommendations boş — ölçülen koşumda 7 adlandırılmış öneri vardı')
        for kayit in oneriler:
            assert isinstance(kayit, dict) and kayit.get('code'), (
                'öneri kaydı {code, params, severity} sözleşmesinde değil: '
                + repr(kayit)[:200])

    def test_hukum_ana_sonuc_ekranina_iniyor(self, dom):
        """P11B2-01: hüküm rozeti ve risk seviyesi GÖRÜNÜR metinde.

        Taban ölçümü (9ddbb22): status geçişi 0, risk geçişi 0 — ekranda
        kalan tek iz 'Min SF' kartı ve metin rengiydi.
        """
        assert dom['hukum']['serit'], 'yapısal hüküm şeridi hiç basılmıyor'
        assert dom['hukum']['status_gorunur'], (
            'yapısal hüküm (status) ana sonuç ekranında görünmüyor')
        assert dom['hukum']['risk_gorunur'], (
            'risk seviyesi ana sonuç ekranında görünmüyor')

    def test_adlandirilmis_onerilerin_hepsi_ekranda(self, dom):
        """Yedi önerinin YEDİSİ de basılır — sayı yanıttan gelir."""
        assert dom['kaynak']['oneri'] > 0, 'bu koşumda öneri üretilmemiş'
        assert dom['hukum']['oneri_ekranda'] == dom['kaynak']['oneri'], (
            'öneri sayısı ekranda eksik: %d/%d'
            % (dom['hukum']['oneri_ekranda'], dom['kaynak']['oneri']))

    def test_hukum_alani_yoksa_serit_basilmaz(self, dom):
        """FAIL-CLOSED: kazanılmamış hüküm gösterilmez."""
        assert dom['hukum_yok']['serit'] is False, (
            'yapısal alanlar yokken bile şerit basılıyor — uydurma hüküm')

    def test_oneri_listesi_bosalirsa_madde_kalmaz(self, dom):
        """MUTASYON duyarlılığı: öneriler boşaltılırsa ekranda iz kalmaz."""
        assert dom['onerisiz']['oneri_ekranda'] == 0, (
            'öneri listesi boşaltıldığı hâlde ekranda öneri kodu duruyor — '
            'metin yanıttan değil koddan geliyor olabilir')


# ---------------------------------------------------------------------------
# A2 — P11B2-06: kritik uyarı amber basılmaz
# ---------------------------------------------------------------------------
class TestA2KritikUyariAyrimi:

    def test_motorun_kritik_uyarilari_var(self, hibrit):
        """Sözleşme: bu koşumda severity:'critical' kayıt GERÇEKTEN var."""
        motor = hibrit.get('motor') or {}
        kayitlar = motor.get('warnings') or motor.get('design_warnings') or []
        kritik = [w for w in kayitlar
                  if isinstance(w, dict)
                  and str(w.get('severity', '')).lower() == 'critical']
        assert kritik, (
            'motor uyarılarında kritik kayıt yok — ölçülen koşumda 4 vardı '
            '(warn.thermal.wall_exceeds_melting vb.)')

    def test_kritik_kayit_kritik_sinif_ve_rozet_aliyor(self, dom):
        """Taban ölçümü: 10 ögenin 10'u amber, kritik rozet 0."""
        beklenen = dom['kaynak']['kanal_kritik'] \
            + dom['kaynak']['validation_kritik']
        assert beklenen > 0
        assert dom['uyari']['kritik_sinif'] == beklenen, (
            'kritik kayıt sayısı ile kritik sınıflı öge sayısı tutmuyor: '
            '%d != %d' % (dom['uyari']['kritik_sinif'], beklenen))
        assert dom['uyari']['kritik_rozet'] == beklenen, (
            'CRITICAL rozeti kritik kayıt sayısını karşılamıyor')

    def test_kritik_olmayanlar_amber_kalir(self, dom):
        """Ayrım tek yönlü değil: normal uyarılar kırmızıya boyanmaz."""
        toplam = dom['kaynak']['kanal_toplam'] \
            + dom['kaynak']['validation_kritik'] \
            + dom['kaynak']['validation_normal']
        amber = toplam - (dom['kaynak']['kanal_kritik']
                          + dom['kaynak']['validation_kritik']
                          + dom['kaynak']['kanal_bilgi'])
        assert dom['uyari']['amber_sinif'] == amber, (
            'amber öge sayısı beklenenden farklı: %d != %d'
            % (dom['uyari']['amber_sinif'], amber))
        # v3.0.1 (V301/H3): BİLGİ kayıtları amber'a da kırmızıya da boyanmaz.
        assert dom['uyari']['bilgi_sinif'] == dom['kaynak']['kanal_bilgi'], (
            'bilgi öge sayısı kaynaktaki info kayıt sayısını tutmuyor: %d != %d'
            % (dom['uyari']['bilgi_sinif'], dom['kaynak']['kanal_bilgi']))

    def test_durum_satiri_kritik_kayitla_kirmiziya_doner(self, hibrit):
        """Kaynak sözleşmesi: durum satırının sınıfı kanaldaki kritiği görür."""
        kaynak = APP_JS.read_text(encoding='utf-8')
        assert re.search(r'injector\.some\(\s*warnIsCritical\s*\)', kaynak), (
            'durum satırı yalnız validation.critical_warnings sayısına '
            'bakıyor — motorun kritik uyarısı durum rengine yansımaz')


# ---------------------------------------------------------------------------
# A3 — P14M3-04: displayWarnings gerçekten koşuyor + dil yolu uyarı düşürmüyor
# ---------------------------------------------------------------------------
class TestA3UyariKanaliBekcisi:

    def test_displaywarnings_gercekten_kosuyor(self, dom):
        """Bekçi borcu: bu satıra kadar hiçbir test bu işlevi çağırmıyordu."""
        beklenen = dom['kaynak']['kanal_toplam'] \
            + dom['kaynak']['validation_kritik'] \
            + dom['kaynak']['validation_normal']
        assert beklenen > 0, 'bu koşumda hiç uyarı yok — ölçüm anlamsız'
        assert dom['uyari']['oge'] == beklenen, (
            'DOM öge sayısı kaynak kayıt sayısını tutmuyor: %d != %d'
            % (dom['uyari']['oge'], beklenen))
        assert dom['uyari']['panel'] == 'block', 'uyarı paneli açılmıyor'

    def test_uyari_dizisi_bosaltilirsa_olcum_dusuyor(self, dom):
        """MUTASYON duyarlılığı: dizi boşalınca bekçi KIRMIZI olmalı.

        Kusurun kendisi buydu — uyarı dizisini boşaltan mutasyon 467 testin
        hiçbirinde yakalanmıyordu.
        """
        assert dom['kaynak']['kanal_kritik'] > 0
        assert dom['mutasyon_bos']['oge'] < dom['uyari']['oge'], (
            'motor uyarıları boşaltıldığı hâlde DOM öge sayısı değişmiyor — '
            'ölçüm uyarı dizisine bağlı değil')
        assert dom['mutasyon_bos']['kritik_sinif'] == 0, (
            'motor uyarıları boşken hâlâ kritik öge basılıyor')

    def test_dil_degisimi_yolu_ortak_toplayiciyi_kullaniyor(self):
        """Kaynak sözleşmesi: iki render yolu AYNI kaynağı okur.

        ÖLÇÜLEN KUSUR: I18N.onChange yolu
        ``displayWarnings(r.injector && r.injector.warnings, r.validation)``
        çağırıyordu — motor uyarıları (4'ü kritik) dil değişiminde ekrandan
        siliniyordu (10 öge -> 5 öge).
        """
        kaynak = APP_JS.read_text(encoding='utf-8')
        # Tanım satırı ('function displayWarnings(...)') hariç TÜM çağrılar.
        gercek = re.findall(r'(?<!function )displayWarnings\(([^;]*?)\);',
                            kaynak, re.DOTALL)
        assert len(gercek) >= 2, (
            'beklenen iki çağrı yeri bulunamadı: ' + repr(gercek)[:300])
        for c in gercek:
            assert 'collectResultWarnings' in c, (
                'displayWarnings çağrısı ortak toplayıcıdan geçmiyor: '
                + c.strip()[:200])
        assert 'r.injector && r.injector.warnings, r.validation' not in kaynak, (
            'dil değişimi yolu hâlâ yalnız enjektör uyarılarını geçiriyor')

    def test_toplayici_uc_kanali_da_okuyor(self):
        """collectResultWarnings motor + girdi + enjektör kanallarını okur."""
        kaynak = APP_JS.read_text(encoding='utf-8')
        govde = re.search(
            r'function collectResultWarnings\(results\) \{(.*?)\n\}',
            kaynak, re.DOTALL)
        assert govde, 'collectResultWarnings tanımı bulunamadı'
        for alan in ('design_warnings', 'input_warnings', 'injector'):
            assert alan in govde.group(1), (
                'toplayıcı %r kanalını okumuyor' % alan)


# ---------------------------------------------------------------------------
# A4 — OH-Z2-05: input_warnings ekrana ve ihraca iniyor
# ---------------------------------------------------------------------------
class TestA4GirdiUyarisiTasima:

    def test_ince_cidar_kritik_uyari_uretiyor(self, sivi):
        """Sözleşme: 1 mm cidar koşumu kritik girdi hükmü üretiyor."""
        kayitlar = sivi.get('input_warnings') or []
        hedef = [w for w in kayitlar
                 if isinstance(w, dict) and w.get('code') == Z5_CIDAR_UYARI_KODU]
        assert hedef, ('%s üretilmedi — kalemin girdisi kayıp'
                       % Z5_CIDAR_UYARI_KODU)
        assert str(hedef[0].get('severity', '')).lower() == 'critical'
        # Parametreler ÖLÇÜLMÜŞ değerlerdir; uydurma yok.
        p = hedef[0].get('params') or {}
        assert float(p['t_used_mm']) < float(p['t_required_mm'])

    def test_input_warnings_dom_kanalina_iniyor(self, dom):
        """Taşıma sözleşmesi: girdi uyarısı ekranın uyarı kanalında."""
        assert dom['input_warnings']['oge'] == 1, (
            'input_warnings kanalı DOM\'a hiç inmiyor')
        assert dom['input_warnings']['kritik_sinif'] == 1, (
            'kritik girdi uyarısı kritik sınıf almıyor')
        assert dom['input_warnings']['kod_dom_da'], (
            'uyarı kodu DOM metninde yok — çeviri/fallback zinciri kopuk')

    def test_ozet_pdf_uyari_kodunu_tasiyor(self, client, sivi):
        """PDF ihracı: taban ölçümünde kodun geçiş sayısı 0'dı."""
        pypdf = pytest.importorskip('pypdf')
        r = client.post('/api/export-pdf/summary',
                        json={'motor_data': sivi, 'analysis_results': sivi})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        metin = '\n'.join(
            (s.extract_text() or '')
            for s in pypdf.PdfReader(BytesIO(r.data)).pages)
        duz = metin.replace('\n', '').replace(' ', '')
        assert Z5_CIDAR_UYARI_KODU in duz, (
            'kritik cidar uyarısı özet PDF metninde yok')
        assert 'CRITICAL' in metin, 'PDF uyarı önemini basmıyor'
        assert 'input_warnings' in duz, 'PDF uyarının KAYNAK kanalını basmıyor'
        # Parametreler de iner: hangi kalınlık, ne gerekiyordu?
        assert 't_used_mm=1.0' in duz and 't_required_mm=2.0' in duz, (
            'PDF ölçülen parametreleri basmıyor — okuyan sayıyı göremez')

    def test_pdf_uyari_yoksa_bolum_hic_basilmaz(self, sivi):
        """FAIL-CLOSED: boş 'Warnings: none' başlığı basılmaz."""
        from hrma.export.pdf_generator import PDFReportGenerator
        temiz = {k: v for k, v in sivi.items()
                 if k not in ('input_warnings', 'warnings', 'design_warnings',
                              'validation')}
        gen = PDFReportGenerator()
        assert gen._create_solver_warnings_section(temiz, temiz) == []
        assert gen._create_solver_warnings_section(sivi, sivi) != []

    def test_pdf_ayni_kaydi_iki_kez_basmaz(self, sivi):
        """motor_data ile analysis_results çoğu çağrıda aynı sözlüktür."""
        from hrma.export.pdf_generator import PDFReportGenerator
        satirlar = PDFReportGenerator._collect_solver_warnings(sivi, sivi)
        kodlar = [(s[0], s[2], s[3]) for s in satirlar]
        assert len(kodlar) == len(set(kodlar)), 'uyarı kayıtları çiftleniyor'
        assert len(satirlar) == len(sivi['input_warnings'])

    def test_komple_paket_uyari_json_tasiyor(self, client, sivi):
        """ZIP ihracı: paketi alan imalatçı uyarıyı dosyadan okuyabilmeli."""
        r = client.post('/api/export-complete-zip', json={'motor_data': sivi})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        zf = zipfile.ZipFile(BytesIO(r.data))
        assert 'warnings/solver_warnings.json' in zf.namelist(), (
            'komple pakette uyarı dosyası yok')
        kayit = json.loads(zf.read('warnings/solver_warnings.json'))
        kodlar = [x['code'] for x in kayit['records']]
        assert Z5_CIDAR_UYARI_KODU in kodlar
        hedef = [x for x in kayit['records']
                 if x['code'] == Z5_CIDAR_UYARI_KODU][0]
        assert hedef['severity'] == 'critical'
        assert hedef['source'] == 'input_warnings'
        assert float(hedef['params']['t_used_mm']) == 1.0
        # MANIFEST paketin içinde ne olduğunu söyler (sessiz eksilme yok).
        man = zf.read('MANIFEST.txt').decode('utf-8')
        assert 'Solver warnings:' in man and 'CRITICAL' in man

    def test_uyarisiz_yukte_uyari_dosyasi_konmaz(self, client, sivi):
        """FAIL-CLOSED: uyarı yoksa boş dosya üretilmez."""
        temiz = {k: v for k, v in sivi.items()
                 if k not in ('input_warnings', 'warnings', 'design_warnings',
                              'validation')}
        r = client.post('/api/export-complete-zip', json={'motor_data': temiz})
        assert r.status_code == 200
        adlar = zipfile.ZipFile(BytesIO(r.data)).namelist()
        assert 'warnings/solver_warnings.json' not in adlar

    def test_toplayici_govdesi_uydurma_alan_uretmiyor(self):
        """Kayıt yoksa liste boş; sözlük olmayan girdi sessizce atlanır."""
        from hrma.app import _collect_solver_warning_records
        assert _collect_solver_warning_records({}) == []
        assert _collect_solver_warning_records(None) == []
        assert _collect_solver_warning_records({'input_warnings': 'x'}) == []
        assert _collect_solver_warning_records(
            {'input_warnings': [{'params': {}}]}) == []


# ---------------------------------------------------------------------------
# A5 — OH-Z2-07: structural_design_basis künyesinin ekranda tüketicisi
# ---------------------------------------------------------------------------
class TestA5TasarimDayanagiKunyesi:

    def test_yanit_kunyeyi_yayimliyor(self, hibrit):
        basis = hibrit.get('structural_design_basis')
        assert isinstance(basis, dict) and basis, (
            'structural_design_basis yayımlanmıyor')
        assert basis.get('wall_thickness_source')
        assert isinstance(basis.get('message'), str) and basis['message']

    def test_kunye_gorunur_metinde(self, dom):
        """Taban: künye YALNIZ title= ipucundaydı, görünür metinde yoktu."""
        assert dom['hukum']['kunye_gorunur'], 'künye satırı basılmıyor'
        assert dom['hukum']['dbasis_mesaji_gorunur'], (
            'sunucunun gerekçe cümlesi görünür metinde yok (yalnız ipuçunda)')

    def test_kunye_makine_alanlarini_adiyla_basiyor(self, dom):
        """Alan adresleri açık yazılır — kullanıcı hangi kapıdan geldiğini görür."""
        alanlar = set(dom['hukum']['kunye_alanlari'])
        assert {'design_mode', 'wall_thickness_source'} <= alanlar, (
            'künyede temel alanlar yok: ' + repr(sorted(alanlar)))


# ---------------------------------------------------------------------------
# Bütünlük
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not NODE, reason='node bulunamadı')
def test_app_js_sozdizimi_gecerli():
    proc = subprocess.run([NODE, '--check', str(APP_JS)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr[:800]


# ---------------------------------------------------------------------------
# Fable Z5 denetimi şartları (ana model, ŞART 1 + ŞART 3)
# ---------------------------------------------------------------------------
class TestFableZ5Sartlari:
    """Denetimin iki şartının kaynak-sözleşme bekçileri.

    ŞART 1: VERDICT ISSUED bir SÜREÇ rozetidir — yeşil basılamaz (yeşil
    YALNIZ 'geçti' demektir; P17B2-11/C2 anlambilimi). ŞART 3: liquid.html
    uyarı yolu kaydın KENDİ severity alanını okur (P11B2-06 ikizi)."""

    def test_verdict_issued_rozeti_yesil_degil(self):
        kaynak = APP_JS.read_text(encoding='utf-8')
        m = re.search(r"verdictIssued'[^)]*\)\s*,\s*(\w+)\s*\)", kaynak)
        assert m, 'VERDICT ISSUED rozet çağrısı bulunamadı'
        assert m.group(1) != 'GREEN', (
            'VERDICT ISSUED yeşil basılıyor — süreç rozeti geçme rengi '
            'alamaz (Fable ŞART 1, P17B2-11 anlambilimi)')
        assert m.group(1) == 'CYAN', (
            f'VERDICT ISSUED beklenen nötr tonda değil: {m.group(1)}')

    def test_liquid_uyari_yolu_severity_okuyor(self):
        kaynak = (REPO_ROOT / 'hrma' / 'templates'
                  / 'liquid.html').read_text(encoding='utf-8')
        i = kaynak.find('const liquidIsCritical')
        assert i != -1, (
            'liquid.html liquidIsCritical yardımcısını kaybetti — '
            'kritik ayrım (Fable ŞART 3) geri dönmüş')
        blok = kaynak[i:i + 2600]
        assert "severity" in kaynak[i:i + 400], (
            'liquidIsCritical kaydın severity alanını okumuyor')
        assert blok.count('liquidIsCritical(w)') >= 2, (
            'injector/inputs kanalları liquidIsCritical ile ayrışmıyor — '
            'kritik kayıtlar yine amber basılır')
