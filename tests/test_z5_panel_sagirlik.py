# -*- coding: utf-8 -*-
"""ÖH Z5 / Paket B — PANEL SAĞIRLIĞI bekçileri.

Kapsanan defter kalemleri:

* **OH-B3-01 + OH-B4-02** — ``safety_panel.js`` ucun yayımladığı dokuz bloğu
  (89 çocuk alan) ekrana HİÇ indirmiyordu: ``explosive_hazards`` (11),
  ``thermal_safety`` (32), ``structural_safety`` (12), ``fire_hazards`` (7),
  ``toxic_hazards`` (7), ``inputs_used`` (6), ``operational_safety`` (6),
  ``emergency_procedures`` (4), ``safety_equipment`` (4). ÖLÇÜLDÜ (27 Ağustos
  2026, gerçek uç yanıtı + node içinde gerçek render): DOM'da bu adlardan
  **0** tanesi geçiyordu.
* **OH-Z3-01** — panel ısı zinciri kuramıyordu (gönderdiği alanlar yetmiyordu)
  ve ucun geri çekme beyanlarını (``risks_not_evaluated``,
  ``overall_risk_score_is_partial``, üst seviye ``thermal_basis``) OKUMUYORDU;
  termal eksen matristen ve tablodan sessizce düşüyordu. Ekran "termal risk
  yok" diyordu — oysa "termal risk ÖLÇÜLMEDİ".
* **OH-B4-01** — ``injector_panel.js`` uyarı/varsayım şeridi ``warnings_tr`` /
  ``assumptions_tr`` okuyordu; bu adların ÜRETİCİSİ depoda yok. Uç
  ``warnings`` / ``assumptions`` yayımlıyor ({code, params, severity}).
* **P17B3-02** — ``protection_panel.js`` katı ve sıvıda motorun ölçülmüş ısı
  akısını bulamıyor, alan panelin 2 000 000 W/m² varsayılanında kalıyor ve
  İKİ FARKLI motor için aynı varsayılanla ablatif hüküm basılıyordu.

Yöntem: Flask ``test_client`` (sunucuya port BAĞLANMAZ) + node içinde GERÇEK
``analysis_dock.js`` ve GERÇEK panel dosyaları. Beklenen alan kümeleri elle
yazılmaz; ucun O KOŞUMDAKİ yanıtından TÜRETİLİR (tautolojik bekçi yazmıyoruz).
Kalıp: ``tests/test_safety_panel_defaults.py``.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PANELS_DIR = STATIC_JS / 'panels'
SAFETY_JS = PANELS_DIR / 'safety_panel.js'
PROTECTION_JS = PANELS_DIR / 'protection_panel.js'
INJECTOR_JS = STATIC_JS / 'injector_panel.js'
EXAMPLES_DIR = REPO_ROOT / 'examples'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: Uygulama yalnız geri döngü Host başlığına yanıt verir (DNS-rebinding kapısı)
HEADERS = {'Host': '127.0.0.1:8080'}

#: Panelin kendi alan varsayılanlarıyla kurulan güvenlik yükü. Isı zinciri
#: alanları BİLEREK yok: uç termal hükmü geri çeker, panel de bunu basmalı.
GUVENLIK_YUKU = {
    'motor_type': 'hybrid',
    'chamber_pressure': 40.0,
    'chamber_temperature': 3000.0,
    'thrust': 1000.0,
    'burn_time': 10.0,
    'propellant_mass': 5.0,
    'propellant_type': 'composite',
    'facility_type': 'test_stand',
    'chamber_diameter': 0.1,
    'wall_thickness': 0.005,
    'material': 'steel_4130',
}

#: Eskiden EKRANA HİÇ İNMEYEN dokuz blok (OH-B3-01 + OH-B4-02).
SAGIR_BLOKLAR = (
    'explosive_hazards', 'fire_hazards', 'toxic_hazards', 'inputs_used',
    'operational_safety', 'emergency_procedures', 'safety_equipment',
    'structural_safety', 'thermal_safety',
)

ORNEK_PROJELER = {
    'hybrid': ('Example Hybrid N2O-HTPB 3kN', '/calculate'),
    'solid': ('Example Solid KNDX BATES 75mm', '/calculate_solid'),
    'liquid': ('Example Liquid LOX-RP1 25kN', '/calculate_liquid'),
}


# ---------------------------------------------------------------------------
# node koşum takımı — sahte DOM, GERÇEK dosyalar
# ---------------------------------------------------------------------------
HARNESS_JS = r"""
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const [staticDir, payloadPath] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));

function El(tag) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.style = {};
    this._attrs = {};
    this.innerHTML = '';
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); };
El.prototype.getAttribute = function (k) {
    return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null;
};
El.prototype.querySelectorAll = function () { return []; };

const documentStub = {
    head: new El('head'), body: new El('body'), readyState: 'complete',
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
    String: String, Boolean: Boolean, RegExp: RegExp,
    isFinite: isFinite, parseFloat: parseFloat, parseInt: parseInt,
    document: documentStub,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

function run(file) {
    vm.runInContext(fs.readFileSync(file, 'utf8'), sandbox, { filename: file });
}

run(path.join(staticDir, 'analysis_dock.js'));
(payload.panels || []).forEach(function (rel) {
    run(path.join(staticDir, rel));
});
if (payload.standalone) { run(path.join(staticDir, payload.standalone)); }

const out = { motorType: null, panels: {} };

if (payload.motorResult) {
    try {
        sandbox.window.AnalysisDock.init({
            motorType: payload.motorType || 'hybrid',
            resultsProvider: function () { return payload.motorResult; },
        });
    } catch (e) { /* gercek DOM yok; cfg yine de kuruldu */ }
}
out.motorType = sandbox.window.AnalysisDock.getMotorType();

(payload.fromResultsFor || []).forEach(function (panelId) {
    const spec = sandbox.window.AnalysisDock._registry.filter(function (s) {
        return s.id === panelId;
    })[0];
    const rec = { fields: (spec.fields || []).map(function (f) { return f[0]; }),
                  suggestion: null, error: null };
    try { rec.suggestion = spec.fromResults(payload.motorResult); }
    catch (e) { rec.error = String(e && e.message || e); }
    out.panels[panelId] = rec;
});

if (payload.safetyResponse) {
    const root = new El('div');
    sandbox.window.SafetyPanel._render(payload.safetyResponse, root);
    out.safetyHtml = root.innerHTML;
}
if (payload.ablativeResponse) {
    const root = new El('div');
    sandbox.window.ProtectionPanel._renderAblative(payload.ablativeResponse, root);
    out.ablativeHtml = root.children.map(function (c) { return c.innerHTML; }).join('');
}
if (payload.injectorDesign) {
    out.injectorHtml = sandbox.window.InjectorPanel._renderHtml(payload.injectorDesign);
}
process.stdout.write(JSON.stringify(out));
"""


def kos_harness(tmp_path, **payload):
    """Sahte DOM içinde gerçek panelleri koşar; JSON çıktısını döner."""
    script = tmp_path / 'kos_z5.js'
    script.write_text(HARNESS_JS, encoding='utf-8')
    girdi = tmp_path / 'girdi_z5.json'
    girdi.write_text(json.dumps(payload), encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(STATIC_JS), str(girdi)],
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, ('panel node altında çöktü:\n'
                                  + proc.stderr[-3000:])
    return json.loads(proc.stdout)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def guvenlik_yaniti(client):
    """Isı zinciri OLMADAN gerçek ``/analyze_safety`` yanıtı."""
    r = client.post('/analyze_safety', json=GUVENLIK_YUKU)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def guvenlik_yaniti_isili(client):
    """Isı çifti GÖNDERİLMİŞ gerçek ``/analyze_safety`` yanıtı."""
    r = client.post('/analyze_safety',
                    json=dict(GUVENLIK_YUKU, wall_temperature_hot=900.0,
                              wall_temperature_cold=600.0))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def motor_sonuclari(client):
    """motor_type -> gerçek ``/calculate*`` yanıtı (örnek projelerden)."""
    out = {}
    for motor_type, (ad, uc) in ORNEK_PROJELER.items():
        proje = json.loads((EXAMPLES_DIR / (ad + '.hrma')).read_text(
            encoding='utf-8'))
        r = client.post(uc, json=dict(proje['inputs']['fields']),
                        headers=HEADERS)
        assert r.status_code == 200, f'{uc} {r.status_code}'
        out[motor_type] = r.get_json()
    return out


def _beklenen_cocuklar(blok_govdesi, tanimsiz_beyanlar=()):
    """Ekranda GÖRÜNMESİ gereken çocuk adları — yanıttan TÜRETİLİR.

    Fail-closed sözleşmesi: değeri olmayan alan basılmaz. Bu yüzden
    beklenen küme, DEĞERİ olan alanlar (boş sözlük/liste değil) ile ucun
    "değerlendirilmedi" diye BEYAN ettiği alanların birleşimidir.
    """
    beklenen = set()
    for ad, deger in (blok_govdesi or {}).items():
        if deger is None:
            if ad in tanimsiz_beyanlar:
                beklenen.add(ad)
            continue
        if isinstance(deger, (dict, list, str)) and len(deger) == 0:
            continue
        beklenen.add(ad)
    return beklenen


# ---------------------------------------------------------------------------
# B1 + B2 — OH-B3-01 / OH-B4-02: dokuz blok ekrana iniyor
# ---------------------------------------------------------------------------
@node_gerekli
class TestSafetyPanelSagirBloklari:
    """Uçtan gelen dokuz blok artık DOM'da; adları ekranda geçiyor."""

    @pytest.fixture(scope='class')
    def cikti(self, tmp_path_factory, guvenlik_yaniti):
        return kos_harness(tmp_path_factory.mktemp('z5b1'),
                           panels=['panels/safety_panel.js'],
                           safetyResponse=guvenlik_yaniti)

    @pytest.fixture(scope='class')
    def cikti_isili(self, tmp_path_factory, guvenlik_yaniti_isili):
        return kos_harness(tmp_path_factory.mktemp('z5b1i'),
                           panels=['panels/safety_panel.js'],
                           safetyResponse=guvenlik_yaniti_isili)

    def test_uc_dokuz_blogu_gercekten_yayimliyor(self, guvenlik_yaniti):
        """Bekçinin dayanağı: bloklar uçtan GELİYOR mu? (iddianın uç ucu)"""
        sa = guvenlik_yaniti['safety_analysis']
        eksik = [b for b in SAGIR_BLOKLAR if not isinstance(sa.get(b), dict)]
        assert not eksik, (
            f'uç şu blokları artık yayımlamıyor: {eksik} — bekçinin dayanağı '
            'bayat, kalem yeniden ölçülmeli')
        assert sum(len(sa[b]) for b in SAGIR_BLOKLAR) >= 80, (
            'blokların toplam çocuk sayısı beklenenin çok altında')

    @pytest.mark.parametrize('blok', SAGIR_BLOKLAR)
    def test_blok_cocuklari_ekranda(self, cikti, guvenlik_yaniti, blok):
        html = cikti['safetyHtml']
        govde = guvenlik_yaniti['safety_analysis'][blok]
        beyan = set(govde.get('thermal_not_evaluated') or []) \
            if blok == 'thermal_safety' else set()
        beklenen = _beklenen_cocuklar(govde, beyan)
        eksik = sorted(ad for ad in beklenen if ad not in html)
        assert not eksik, (
            f'safety_panel {blok} bloğunun şu çocuklarını basmıyor: {eksik}')
        assert beklenen, f'{blok}: beklenen küme boş — ölçüt bozulmuş'

    def test_isi_cifti_gelince_de_bloklar_iniyor(self, cikti_isili,
                                                 guvenlik_yaniti_isili):
        """İkinci koşum biçimi (termal hüküm VERİLMİŞ) da kapsanır."""
        html = cikti_isili['safetyHtml']
        sa = guvenlik_yaniti_isili['safety_analysis']
        eksik = {}
        for blok in SAGIR_BLOKLAR:
            beyan = set(sa[blok].get('thermal_not_evaluated') or []) \
                if blok == 'thermal_safety' else set()
            kayip = sorted(ad for ad in _beklenen_cocuklar(sa[blok], beyan)
                           if ad not in html)
            if kayip:
                eksik[blok] = kayip
        assert not eksik, f'ısı çiftli koşumda basılmayan alanlar: {eksik}'

    def test_bos_kap_uydurma_deger_uretmiyor(self, cikti, guvenlik_yaniti):
        """FAIL-CLOSED: uç boş liste/sözlük yayımladıysa satır KONMAZ.

        ``toxic_components: []`` ve ``exposure_limits: {}`` bu koşumda
        boştur; panel bunlara sahte bir değer basmamalıdır.
        """
        html = cikti['safetyHtml']
        toksik = guvenlik_yaniti['safety_analysis']['toxic_hazards']
        assert toksik['toxic_components'] == [], (
            'ölçüm bayat: bu koşumda toxic_components artık boş değil')
        assert 'data-safety-field="toxic_components"' not in html, (
            'boş liste için satır basılmış — fail-closed sözleşmesi bozuk')

    def test_beyanli_bos_alan_not_modelled_cipiyle_basiliyor(
            self, cikti, guvenlik_yaniti):
        """Beyanlı boşluk sessiz değil: '—' + NOT MODELLED çipi.

        Beklenen küme yine uçtan türetilir: ``thermal_not_evaluated``
        listesindeki VE değeri gerçekten ``None`` olan her alan.
        """
        html = cikti['safetyHtml']
        termal = guvenlik_yaniti['safety_analysis']['thermal_safety']
        beyanli_bos = [ad for ad in (termal.get('thermal_not_evaluated') or [])
                       if termal.get(ad, 'YOK') is None]
        assert beyanli_bos, 'ölçüm bayat: uç artık hüküm geri çekmiyor'
        eksik = [ad for ad in beyanli_bos
                 if f'data-safety-withheld="{ad}"' not in html]
        assert not eksik, (
            f'uç bu alanları geri çekti ama panel satırlarını basmıyor: {eksik}')
        assert html.count('data-src-kind="missing"') >= len(beyanli_bos), (
            'geri çekilen alanlar için kaynak çipi basılmamış')


# ---------------------------------------------------------------------------
# B3 — OH-Z3-01: termal eksen ve geri çekme beyanları
# ---------------------------------------------------------------------------
@node_gerekli
class TestSafetyPanelTermalEkseni:

    @pytest.fixture(scope='class')
    def cikti(self, tmp_path_factory, guvenlik_yaniti, motor_sonuclari):
        return kos_harness(tmp_path_factory.mktemp('z5b3'),
                           panels=['panels/safety_panel.js'],
                           safetyResponse=guvenlik_yaniti,
                           motorResult=motor_sonuclari['hybrid'],
                           motorType='hybrid',
                           fromResultsFor=['safety'])

    def test_isi_zinciri_alanlari_koşum_kartinda(self, cikti):
        alanlar = cikti['panels']['safety']['fields']
        assert 'wall_temperature_hot' in alanlar, (
            'panel cidar sıcaklığı çiftini gönderemiyor — uç ısı zincirini '
            'hiçbir koşulda kuramaz')
        assert 'wall_temperature_cold' in alanlar

    def test_dock_verince_cift_taşiniyor(self, cikti, motor_sonuclari,
                                         tmp_path):
        """Öneri UYDURULMAZ: güvertenin kendi okuyucusuyla birebir aynı.

        ÖH D37 A1b panel-js 6. tur (14 Eki, devir 13) — dört koşulla
        çevrildi (ana model): (1) eski beklenti ("örnek hibrit çözülmüş cidar
        yayımlıyor, panel taşır"), ısı modülünün kendi
        ``wall_temperature_unphysical`` bayrağını yok sayan aktarımdan
        türemişti — ölçüm ``a1/t6/cidar_kaynagi.json``: çift 3312,5 /
        3289,4 K soğutmasız DENGE cidarı (T_aw 3321,3 K), çıplak cidar
        geçmişi ``model_valid = false``; (2) kâhin
        ``heat_transfer_analysis.py`` (bayrak = T_wall erime ya da kullanım
        sınırının üstünde): bayrak true iken çift taşınmaz, false iken
        güvertenin okuyucusuyla birebir taşınır; (3) tolerans değişmedi;
        (4) rapor ``docs/scofield/raw/OH/A1b/panel-js/a1/rapor.md`` '6. tur'.
        """
        import copy
        oneri = cikti['panels']['safety']['suggestion']
        assert cikti['panels']['safety']['error'] is None
        motor = motor_sonuclari['hybrid']['motor']
        assert motor['heat_transfer_analysis']['gas_side_analysis'][
            'wall_temperature_unphysical'] is True
        assert 'wall_temperature_hot' not in oneri, (
            'ısı modülünün fiziksel değil diye imlediği denge cidarı '
            f'panelden uca taşınıyor: {oneri!r}')
        assert 'wall_temperature_cold' not in oneri
        # Bayrak kalkınca çözülmüş çift güvertenin okuyucusuyla AYNEN gider.
        r = copy.deepcopy(motor_sonuclari['hybrid'])
        r['motor']['heat_transfer_analysis']['gas_side_analysis'][
            'wall_temperature_unphysical'] = False
        cikti2 = kos_harness(tmp_path, panels=['panels/safety_panel.js'],
                             motorResult=r, motorType='hybrid',
                             fromResultsFor=['safety'])
        assert cikti2['panels']['safety']['error'] is None
        oneri2 = cikti2['panels']['safety']['suggestion']
        sicak = oneri2.get('wall_temperature_hot')
        soguk = oneri2.get('wall_temperature_cold')
        assert isinstance(sicak, (int, float)) and isinstance(soguk, (int, float)), (
            'bayraksız çözülmüş cidar sıcaklığını panel taşımıyor: '
            f'{oneri2!r}')
        termal = r['motor']['structural_analysis']['thermal_analysis']
        assert sicak == pytest.approx(termal['wall_temperature_inner_K'])
        assert soguk == pytest.approx(termal['wall_temperature_outer_K'])
        assert sicak >= soguk

    def test_dock_veremiyorsa_alan_gonderilmez(self, tmp_path,
                                               motor_sonuclari):
        """FAIL-CLOSED: katı zincir cidar sıcaklığı YAYIMLAMIYOR."""
        cikti = kos_harness(tmp_path, panels=['panels/safety_panel.js'],
                            motorResult=motor_sonuclari['solid'],
                            motorType='solid', fromResultsFor=['safety'])
        oneri = cikti['panels']['safety']['suggestion']
        assert 'wall_temperature_hot' not in oneri, (
            'katı motorda cidar sıcaklığı UYDURULMUŞ — kaynağı yok')
        assert 'wall_temperature_cold' not in oneri

    def test_geri_cekme_beyanlari_ekranda(self, cikti):
        """Termal eksen artık matristen sessizce düşmüyor."""
        html = cikti['safetyHtml']
        for ad in ('risks_not_evaluated', 'overall_risk_score_is_partial',
                   'missing_thermal_inputs', 'thermal_verdict'):
            assert ad in html, f'{ad} beyanı ekrana inmiyor'
        assert 'data-risk-not-evaluated="thermal"' in html, (
            'değerlendirilmeyen termal ekseni bireysel risk tablosunda '
            'satırıyla görünmüyor (eski süzgeç geri gelmiş olabilir)')

    def test_cift_gonderilince_termal_eksen_sayi_oluyor(
            self, client, motor_sonuclari, tmp_path):
        """Kablo GERÇEK: güvertenin verdiği çift ucu değiştiriyor mu?

        Kanıt zinciri uçtan uca: /calculate -> panel önerisi -> uç yanıtı.
        Beyansız hiçbir sayı taşınmaz; taşınan sayı da hükmü GERÇEKTEN
        değiştirir (aksi hâlde alan dekoratif olurdu).

        ÖH D37 A1b panel-js 6. tur (14 Eki, devir 13) — dört koşulla
        çevrildi (ana model): (1) eski girdi, ısı modülünün fiziksel değil
        diye imlediği soğutmasız denge cidarıydı (``a1/t6/cidar_kaynagi.json``);
        (2) kâhin ``heat_transfer_analysis.py`` bayrağı: örnek hibritin
        bayraklı çifti artık uca gitmez (``test_dock_verince_cift_taşiniyor``),
        kablo bayraksız (çözülmüş) aynı çiftle sınanır; (3) tolerans yok;
        (4) rapor '6. tur'.
        """
        import copy
        r = copy.deepcopy(motor_sonuclari['hybrid'])
        r['motor']['heat_transfer_analysis']['gas_side_analysis'][
            'wall_temperature_unphysical'] = False
        cikti = kos_harness(tmp_path, panels=['panels/safety_panel.js'],
                            motorResult=r,
                            motorType='hybrid', fromResultsFor=['safety'])
        oneri = cikti['panels']['safety']['suggestion']
        yuk = dict(GUVENLIK_YUKU,
                   wall_temperature_hot=oneri['wall_temperature_hot'],
                   wall_temperature_cold=oneri['wall_temperature_cold'])
        js = client.post('/analyze_safety', json=yuk).get_json()
        risk = js['safety_analysis']['risk_assessment']
        assert risk['individual_risks']['thermal'] is not None, (
            'çift gönderildi ama termal eksen hâlâ değerlendirilmiyor')
        assert risk['risks_not_evaluated'] == []
        assert js['thermal_basis']['verdict'] != 'withheld'
        # Aynı yükün ısı çifti OLMADAN hâli hâlâ geri çekiyor mu?
        bos = client.post('/analyze_safety', json=GUVENLIK_YUKU).get_json()
        assert bos['safety_analysis']['risk_assessment'][
            'individual_risks']['thermal'] is None


# ---------------------------------------------------------------------------
# B4 — OH-B4-01: enjektör uyarı/varsayım şeridi
# ---------------------------------------------------------------------------
INJ_YUKLER = {
    'showerhead': {'motor_type': 'hybrid', 'injector_type': 'showerhead',
                   'mdot_ox': 1.5, 'rho_ox': 800.0, 'Pc_bar': 20.0,
                   'fluid_ox': 'generic', 'inlet_ox': 'sharp',
                   'l_over_d': 4.0, 'dp_ratio_ox': 0.2},
    'n2o_pintle': {'motor_type': 'hybrid', 'injector_type': 'pintle',
                   'mdot_ox': 1.5, 'Pc_bar': 20.0, 'fluid_ox': 'n2o',
                   'inlet_ox': 'sharp', 'l_over_d': 4.0, 'T_ox_K': 293.0},
}


class TestInjectorUyariSeridi:

    def test_olu_takma_adlar_kaynaktan_kalkti(self):
        """``warnings_tr``/``assumptions_tr`` üreticisi yok; panel de okumaz."""
        src = INJECTOR_JS.read_text(encoding='utf-8')
        kod = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
        kod = re.sub(r'//[^\n]*', '', kod)
        for ad in ('warnings_tr', 'assumptions_tr'):
            assert f'dz.{ad}' not in kod, (
                f'injector_panel.js hâlâ üreticisi olmayan {ad} adını okuyor')
        assert 'dz.warnings' in kod and 'dz.assumptions' in kod, (
            'panel ucun GERÇEK alanlarını okumuyor')

    @pytest.mark.parametrize('ad', sorted(INJ_YUKLER))
    def test_uc_kayit_sozlugu_yayimliyor(self, client, ad):
        """İddianın uç ucu: kayıtlar {code, params, severity} biçiminde."""
        js = client.post('/api/injector-design', json=INJ_YUKLER[ad]).get_json()
        dz = js['design']
        kayitlar = (dz.get('warnings') or []) + (dz.get('assumptions') or [])
        assert kayitlar, f'{ad}: uç hiç kayıt yayımlamıyor — ölçüm bayat'
        for k in kayitlar:
            assert set(k) >= {'code', 'severity'}, k
        assert 'warnings_tr' not in dz and 'assumptions_tr' not in dz

    @node_gerekli
    @pytest.mark.parametrize('ad', sorted(INJ_YUKLER))
    def test_kayitlar_serite_iniyor(self, client, tmp_path, ad):
        js = client.post('/api/injector-design', json=INJ_YUKLER[ad]).get_json()
        dz = js['design']
        cikti = kos_harness(tmp_path, standalone='injector_panel.js',
                            injectorDesign=dz)
        html = cikti['injectorHtml']
        kayitlar = (dz.get('warnings') or []) + (dz.get('assumptions') or [])
        assert '[object Object]' not in html, (
            'kayıt sözlüğü ham basılmış — çeviri fonksiyonundan geçmiyor')
        assert html.count('<li>') >= len(kayitlar), (
            f"{ad}: {len(kayitlar)} kayıt var, şeride "
            f"{html.count('<li>')} satır indi")
        if dz.get('warnings'):
            assert 'data-inj-warnings=' in html
        if dz.get('assumptions'):
            assert 'data-inj-assumptions=' in html

    @node_gerekli
    def test_severity_gorsel_olarak_ayriliyor(self, client, tmp_path):
        """critical/warning ayrımı renkle BİRLİKTE metin etiketi taşır."""
        js = client.post('/api/injector-design',
                         json=INJ_YUKLER['n2o_pintle']).get_json()
        dz = js['design']
        assert dz['warnings'], 'ölçüm bayat: bu yük artık uyarı üretmiyor'
        cikti = kos_harness(tmp_path, standalone='injector_panel.js',
                            injectorDesign=dz)
        html = cikti['injectorHtml']
        assert 'data-inj-severity="warn"' in html, (
            'uyarı satırı severity etiketi taşımıyor')
        assert 'data-inj-severity="info"' in html, (
            'varsayım satırı severity etiketi taşımıyor')


# ---------------------------------------------------------------------------
# B5 — P17B3-02: ablatif hüküm motorun ÖLÇÜLMÜŞ akısından
# ---------------------------------------------------------------------------
@node_gerekli
class TestProtectionOlculmusAki:

    @pytest.fixture(scope='class')
    def oneriler(self, tmp_path_factory, motor_sonuclari):
        out = {}
        for motor_type in ORNEK_PROJELER:
            cikti = kos_harness(tmp_path_factory.mktemp('z5b5' + motor_type),
                                panels=['panels/protection_panel.js'],
                                motorResult=motor_sonuclari[motor_type],
                                motorType=motor_type,
                                fromResultsFor=['protection'])
            assert cikti['panels']['protection']['error'] is None
            out[motor_type] = cikti['panels']['protection']['suggestion']
        return out

    def test_uc_motor_uc_farkli_aki(self, oneriler):
        """Varsayılan patolojisi bitti: her motorun KENDİ akısı."""
        akilar = {}
        for motor_type, oneri in oneriler.items():
            q = oneri.get('q_net_W_m2')
            assert isinstance(q, (int, float)) and q > 0, (
                f'{motor_type}: ölçülmüş ısı akısı okunmuyor ({oneri!r})')
            akilar[motor_type] = q
        assert len(set(akilar.values())) == 3, (
            f'iki motor aynı akıyı alıyor: {akilar}')
        # Hiçbiri panelin kendi varsayılanı olmamalı
        assert 2000000 not in set(akilar.values()), (
            f'bir motor hâlâ panel varsayılanında: {akilar}')

    def test_aki_motorun_yayimladigi_sayiyla_ayni(self, oneriler,
                                                  motor_sonuclari):
        """Sayı türetilmez, ucun yayımladığı alandan OKUNUR (birim dâhil)."""
        hibrit = motor_sonuclari['hybrid']['motor']
        assert oneriler['hybrid']['q_net_W_m2'] == pytest.approx(
            hibrit['heat_transfer_analysis']['gas_side_analysis']['heat_flux'],
            rel=0, abs=0), 'hibrit yolu değişmiş (bit-aynı çapa kırıldı)'
        kati = motor_sonuclari['solid']
        assert oneriler['solid']['q_net_W_m2'] == pytest.approx(
            kati['thermal_analysis']['heat_transfer'][
                'convective_heat_flux_kw_m2'] * 1e3, rel=1e-12)
        sivi = motor_sonuclari['liquid']
        assert oneriler['liquid']['q_net_W_m2'] == pytest.approx(
            sivi['cooling_system']['peak_heat_flux'] * 1e3, rel=1e-12)

    def test_farkli_aki_farkli_kalinlik_hukmu(self, client, oneriler):
        """Akı gerçekten hükmü değiştiriyor (alan dekoratif değil).

        ÇEVİRİ (ÖH D15 birleşmesi, 1 Eyl 2026). Bekçi eskiden tek şey
        soruyordu: üç akı ÜÇ FARKLI ``required_thickness_mm`` versin. Bu
        iddia ucun kazanılmış fail-closed hükmüyle çelişiyor: Level-1
        kararlı Q* modeli, hesaplanan gerileme hızı geçerlilik tavanını
        (``RECESSION_VALID_MAX_MM_S`` = 0,35 mm/s) aştığında KALINLIK
        YAYIMLAMIYOR — ``thickness_status = 'NOT_MODELLED'``,
        ``required_thickness_mm = None`` ve ``validity_note`` ile gerekçe.
        Üç örnek motorun ölçülmüş akıları (16-27 MW/m² mertebesi) zarfın
        dışında kalıyor; eski iddia yürürlükte kalsaydı bekçi "zarf dışında
        da bir kalınlık uydur" demiş olurdu.

        Bekçinin ASIL sorusu değişmedi ("akı dekoratif mi"), ölçüldüğü
        büyüklük ucun gerçekten yayımladığına taşındı ve iddia ARTTI:
          · gerileme (her koşulda hesaplanır) üç motorda da FARKLI olmalı;
          · zarf içindeki her yanıt POZİTİF ve birbirinden farklı kalınlık
            vermeli;
          · zarf dışındaki her yanıt kalınlığı SESSİZCE değil, durum adı +
            gerekçe metniyle geri çekmeli.
        """
        yanitlar = {}
        for motor_type, oneri in oneriler.items():
            yanitlar[motor_type] = client.post('/api/thermal-protection', json={
                'mode': 'ablative', 'q_net_W_m2': oneri['q_net_W_m2'],
                'burn_time_s': oneri.get('burn_time_s', 10.0),
                'material': 'silica_phenolic'}).get_json()

        gerilemeler = {m: j['total_recession_mm'] for m, j in yanitlar.items()}
        assert all(isinstance(v, (int, float)) and v > 0
                   for v in gerilemeler.values()), (
            f'gerileme hesaplanmamış: {gerilemeler}')
        assert len(set(gerilemeler.values())) == 3, (
            f'farklı akılar aynı gerilemeyi veriyor: {gerilemeler}')

        kalinliklar = {m: j['required_thickness_mm']
                       for m, j in yanitlar.items()}
        icerde = {m: k for m, k in kalinliklar.items() if k is not None}
        for motor_type, kalinlik in icerde.items():
            assert kalinlik > 0, f'{motor_type}: kalınlık pozitif değil'
            assert yanitlar[motor_type]['thickness_status'] != 'NOT_MODELLED'
        assert len(set(icerde.values())) == len(icerde), (
            f'zarf içindeki motorlar aynı kalınlığı veriyor: {icerde}')

        for motor_type, kalinlik in kalinliklar.items():
            if kalinlik is not None:
                continue
            js = yanitlar[motor_type]
            assert js['thickness_status'] == 'NOT_MODELLED', (
                f'{motor_type}: kalınlık sessizce None — durum adı yok '
                f"({js.get('thickness_status')!r})")
            assert (js.get('validity_note') or '').strip(), (
                f'{motor_type}: kalınlık geri çekildi ama gerekçe boş')
            assert js['required_thickness_m'] is None, (
                f'{motor_type}: mm geri çekildi ama m ikizi yayımlanıyor')

    def test_olcum_yoksa_hukum_geri_cekiliyor(self, client, tmp_path):
        """FAIL-CLOSED: ölçülmüş akı yoksa kalınlık kartı '—' basar."""
        tps = client.post('/api/thermal-protection', json={
            'mode': 'ablative', 'q_net_W_m2': 2000000, 'burn_time_s': 10.0,
            'material': 'silica_phenolic'}).get_json()
        assert tps['required_thickness_mm'] > 0, 'uç sayıyı üretmiş olmalı'
        cikti = kos_harness(tmp_path, panels=['panels/protection_panel.js'],
                            motorResult={'motor': {'burn_time': 10.0}},
                            motorType='hybrid', fromResultsFor=['protection'],
                            ablativeResponse=tps)
        html = cikti['ablativeHtml']
        assert 'data-tps-flux-kind="assumed"' in html, (
            'ölçüm yokken hüküm kazanılmış gibi basılıyor')
        assert 'Required liner thickness' in html or 'thickness' in html
        assert str(round(tps['required_thickness_mm'], 2)) not in html, (
            'kazanılmamış kalınlık sayısı hâlâ kartta')

    def test_olculmus_akida_kunye_computed(self, client, tmp_path,
                                           motor_sonuclari, oneriler):
        """Ölçüm varsa hüküm basılır ve künyesi 'computed' der."""
        oneri = oneriler['solid']
        tps = client.post('/api/thermal-protection', json={
            'mode': 'ablative', 'q_net_W_m2': oneri['q_net_W_m2'],
            'burn_time_s': oneri['burn_time_s'],
            'material': 'silica_phenolic'}).get_json()
        cikti = kos_harness(tmp_path, panels=['panels/protection_panel.js'],
                            motorResult=motor_sonuclari['solid'],
                            motorType='solid', fromResultsFor=['protection'],
                            ablativeResponse=tps)
        html = cikti['ablativeHtml']
        assert 'data-tps-flux-kind="computed"' in html
        assert 'convective_heat_flux_kw_m2' in html, (
            'akının geldiği makine yolu ekranda beyan edilmiyor')

    def test_yanlis_motorun_yolu_denenmiyor(self, tmp_path, motor_sonuclari):
        """Katı yanıtı 'liquid' etiketiyle verilirse akı UYDURULMAZ."""
        cikti = kos_harness(tmp_path, panels=['panels/protection_panel.js'],
                            motorResult=motor_sonuclari['solid'],
                            motorType='liquid', fromResultsFor=['protection'])
        oneri = cikti['panels']['protection']['suggestion']
        assert 'q_net_W_m2' not in oneri, (
            'başka motor tipinin yolu denenmiş — yanlış motorun sayısı '
            'basılabilirdi')
