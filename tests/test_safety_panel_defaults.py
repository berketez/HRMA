"""Güvenlik paneli — uçun ``defaults_applied`` beyanının EKRANA çıkması.

KAPATILAN KUSUR (ölçüm, 2026-08-18)
-----------------------------------
``POST /analyze_safety`` zorunlu OLMAYAN bir alanı istekte bulamazsa kendi
varsayılanını kullanır ve bunu yanıtın ``defaults_applied`` listesiyle
BEYAN EDER (``hrma/app.py::analyze_safety``). Panel bu beyanı hiç
okumuyordu. Ölçüm (bu dosyadaki koşum takımıyla, GERÇEK uç yanıtı ve
GERÇEK panel kodu):

    istek  = yalnız dört zorunlu alan (chamber_pressure, propellant_mass,
             chamber_diameter, wall_thickness)
    yanıt  = defaults_applied: ['chamber_temperature', 'thrust',
             'burn_time', 'propellant_type', 'facility_type', 'material']
    ekran  = 27 637 bayt HTML; altı alan adının HİÇBİRİ geçmiyor,
             'ASSUMED' künyesi yok, 'default' kelimesi yok.

Yani hüküm (risk skorları, TNT eşdeğeri, tahliye mesafeleri, basınçlı kap
payları) altı sayının kullanıcıya ait olmadığı bilgisi GİZLENEREK
gösteriliyordu. Defterdeki "panel defaults_applied'ı okumuyor" satırı
ölçümle DOĞRULANDI (eskimemişti: ``safety_panel.js`` içindeki 2026-07
yorumları alan BAĞLAMA gerekçesini anlatıyor, beyanın gösterilmediğini
zaten söylüyor).

NE KİLİTLENİR
-------------
  1. Uç beyanı GERÇEKTEN üretiyor (bekçinin konusu kaybolursa kırmızı).
  2. Beyandaki her alan ekranda ADIYLA görünür (``data-safety-default``).
  3. Her alan güvertenin ASSUMED künyesini taşır (analysis_dock kaynak
     çipi — renk + şekil + ipucu tek kaynaktan).
  4. Etiketler koşum kartının alan listesinden gelir (ikinci bir etiket
     listesi tutulmaz — ayrışma yapısal olarak imkânsız).
  5. BOŞ liste ayrı bir beyandır ("hiçbiri varsayılandan gelmedi") ve
     satır üretmez; beyan HİÇ yoksa künye BASILMAZ (uydurma yok).
  6. Künye hükmün hemen ardındadır: risk tablosundan ÖNCE.

MUTASYON SÖZLEŞMESİ
-------------------
  * ``render()`` içinden ``defaultsBlock(data.defaults_applied)`` çağrısı
    sökülürse -> 2, 3, 5, 6 kırmızı.
  * Künye listesi ``data.defaults_applied`` yerine sabit bir listeden
    beslenirse -> 2 (alan kümesi eşitliği) kırmızı.
  * Boş listede satır basılırsa -> 5 kırmızı.

Koşum hedeflidir (süit disiplini):
    python3 -m pytest tests/test_safety_panel_defaults.py -q
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_JS = REPO_ROOT / 'hrma' / 'static' / 'js'
PANEL_JS = STATIC_JS / 'panels' / 'safety_panel.js'

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

#: Ucun zorunlu saydığı alanlar (app.py::REQUIRED_SAFETY_FIELDS ile aynı
#: küme; eksikse 422 döner, o yüzden her istek bunları taşır).
SAFETY_ZORUNLU_ALANLAR = {'chamber_pressure': 40.0, 'propellant_mass': 5.0,
                          'chamber_diameter': 0.1, 'wall_thickness': 0.005}

#: Ucun varsayılanı olan alanlar — istekte verilirse beyan listesi boşalır.
# ÖH D31 / OH-D30-11 — ``motor_type`` BU KÜMEYE EKLENDİ (bekçi çevrildi).
# Gerekçe: ``/analyze_safety`` onu D30'a kadar sessizce ``'hybrid'``a
# düşürüyor ama ``defaults_applied`` içinde ANMIYORDU; o değer patlayıcı
# sınıfını seçen koldur. ÖLÇÜLDÜ (``D31/app-api-uc/a1/once.json`` K1):
# ``propellant_type='apcp'`` motor tipi verilmeden hibrit N2O sınıfını,
# 22,2775 kg TNT ve 7,7363 m ölümcül mesafe alıyordu (``motor_type='solid'``
# ile 21,0 kg / 7,5855 m). ``hrma/app.py`` künyesi bu kümenin AYNI anda
# güncellenmesini şart koşuyordu (kendi yorumunda yazılıydı) — iki taraf
# bu dalgada birlikte güncellendi. Bekçinin niyeti korunur: kümenin her
# alanı ucun beyanında ADIYLA görünmeli.
SAFETY_VARSAYILANLI_ALANLAR = {'motor_type': 'hybrid',
                               'chamber_temperature': 3000.0,
                               'thrust': 1000.0, 'burn_time': 10.0,
                               'propellant_type': 'composite',
                               'facility_type': 'test_stand',
                               'material': 'inconel_718'}


# ---------------------------------------------------------------------------
# node koşum takımı: GERÇEK analysis_dock.js + GERÇEK safety_panel.js sahte
# bir DOM içinde yüklenir ve render GERÇEKTEN çağrılır (grep denetimi değil).
# Kalıp: tests/test_panel_units_v2626.py HARNESS_JS.
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
    fetch: function () { return Promise.reject(new Error('sandbox: ağ yok')); },
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
run(path.join(staticDir, 'panels', 'safety_panel.js'));

const SP = sandbox.window.SafetyPanel;
const root = new El('div');
SP._render(payload.response, root);

const spec = sandbox.window.AnalysisDock._registry.filter(function (s) {
    return s.id === 'safety';
})[0];

const out = {
    html: root.innerHTML,
    // Koşum kartının alan listesi PANELİN KENDİSİNDEN (kayıt sözleşmesi):
    // etiket kaynağının tekliği buradan ölçülür.
    specFieldIds: (spec.fields || []).map(function (f) { return f[0]; }),
    specFieldsIsSameArray: spec.fields === SP._fields,
    labels: {},
};
(payload.labelFor || []).forEach(function (k) { out.labels[k] = SP._fieldLabel(k); });
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def uc_yaniti(client, **ek):
    """GERÇEK uç yanıtı — biçim uydurulmaz, uçtan alınır."""
    govde = dict(SAFETY_ZORUNLU_ALANLAR)
    govde.update(ek)
    r = client.post('/analyze_safety', json=govde)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def kos_panel(tmp_path, response, label_for=()):
    script = tmp_path / 'kos_safety.js'
    script.write_text(HARNESS_JS, encoding='utf-8')
    girdi = tmp_path / 'girdi.json'
    girdi.write_text(json.dumps({'response': response,
                                 'labelFor': list(label_for)}),
                     encoding='utf-8')
    proc = subprocess.run([NODE, str(script), str(STATIC_JS), str(girdi)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        'panel node altında çöktü:\n' + proc.stderr[-3000:])
    return json.loads(proc.stdout)


ALAN_RE = re.compile(r'data-safety-default="([^"]+)"')
CIP_RE = re.compile(r'data-src-kind="(\w+)"')


@pytest.fixture(scope='module')
def eksik_yanit(client):
    """Yalnız zorunlu alanlar gönderilmiş koşum — uç altı varsayılan uygular."""
    return uc_yaniti(client)


@pytest.fixture(scope='module')
def tam_yanit(client):
    """Her alan istekte — uç hiçbir varsayılana düşmez."""
    return uc_yaniti(client, **SAFETY_VARSAYILANLI_ALANLAR)


class TestUcBeyani:
    def test_uc_varsayilan_listesini_gercekten_yayimliyor(self, eksik_yanit):
        """Bekçinin KONUSU: uç beyanı üretmezse panel de gösteremez —
        o gün bu bekçi kırmızı yanmalı, sessizce boşa dönmemeli."""
        applied = eksik_yanit.get('defaults_applied')
        assert isinstance(applied, list) and applied, (
            'uç defaults_applied beyanını üretmiyor — künye bekçisinin '
            'konusu kalmadı (uç sözleşmesi değişmiş olabilir)')
        assert set(applied) <= set(SAFETY_VARSAYILANLI_ALANLAR), (
            f'uç, bilinmeyen bir alanı varsayılan ilan etti: {applied}')

    def test_tam_govdede_beyan_bos(self, tam_yanit):
        assert tam_yanit.get('defaults_applied') == [], (
            'her alan istekte olduğu hâlde uç varsayılan beyan ediyor')


class TestKunyeEkranda:
    def test_her_varsayilan_alan_adiyla_gorunuyor(self, tmp_path, eksik_yanit):
        """KUSURUN BEKÇİSİ: beyandaki alan kümesi ile ekrandaki künye
        kümesi BİREBİR aynıdır (eksik = gizlenmiş sayı, fazla = uydurma)."""
        out = kos_panel(tmp_path, eksik_yanit)
        ekranda = ALAN_RE.findall(out['html'])
        assert ekranda == eksik_yanit['defaults_applied'], (
            f'künye {ekranda} ile uç beyanı '
            f"{eksik_yanit['defaults_applied']} ayrışıyor — beyan ekrana "
            'birebir çıkmalı (sıra dahil: kullanıcı listeyi yanıtla '
            'karşılaştırabilmeli)')

    def test_her_alan_assumed_kunyesi_tasiyor(self, tmp_path, eksik_yanit):
        """Künye güvertenin ASSUMED çipiyle basılır: aynı renk/şekil/ipucu
        her panelde aynı anlama gelsin (analysis_dock kaynak katmanı).

        Kapsam KÜNYE SATIRLARIDIR: panelin diğer blokları kendi meşru
        çiplerini (ör. geri çekilen termal alanların MISSING'i) taşıyabilir;
        bekçi yalnız her varsayılan alanın kendi satırındaki çipin ASSUMED
        olduğunu kilitler (Z5 kapsamlaması — eski hâli tüm paneli tarayıp
        her yeni dürüstlük çipini kırmızıya boyuyordu)."""
        out = kos_panel(tmp_path, eksik_yanit)
        html = out['html']
        for alan in eksik_yanit['defaults_applied']:
            seg = re.search(
                r'data-safety-default="%s"(.*?)'
                r'(?=data-safety-default="|\Z)' % re.escape(alan),
                html, re.S)
            assert seg, f'künye satırı yok: {alan}'
            cipler = CIP_RE.findall(seg.group(1))
            assert cipler and cipler[0] == 'assumed', (
                f'{alan} künye satırının kaynak çipi {cipler[:1]} — '
                'ASSUMED bekleniyordu')
        assert 'dock.src.assumed' in out['html'], (
            'künye çevrilebilir etiket taşımıyor (data-i18n) — dil '
            'değişiminde İngilizce kalır')

    def test_etiketler_kosum_karti_alan_listesinden(self, tmp_path,
                                                    eksik_yanit):
        """Etiket kaynağı TEK: künye, koşum kartının alan listesini okur.

        (İkinci bir etiket sözlüğü tutulsaydı alan adı değiştiğinde iki
        liste sessizce ayrışırdı; bu bekçi aynı dizi nesnesi olduğunu da
        ölçer.)
        """
        alanlar = eksik_yanit['defaults_applied']
        out = kos_panel(tmp_path, eksik_yanit, label_for=alanlar)
        assert out['specFieldsIsSameArray'], (
            'koşum kartı alanları ile künye etiket kaynağı AYRI diziler — '
            'tek kaynak bozulmuş')
        for k in alanlar:
            assert k in out['specFieldIds'], (
                f'{k}: uç varsayılan ilan etti ama koşum kartında böyle bir '
                'alan yok — kullanıcı o sayıyı veremez (kapalı alan)')
            etiket = out['labels'][k]
            assert etiket and etiket != k, (
                f'{k}: künye ham anahtar basıyor, koşum kartındaki etiket '
                'kullanılmamış')
            assert etiket in out['html'], (
                f'{k}: {etiket!r} etiketi ekranda yok')

    def test_kunye_risk_tablosundan_once(self, tmp_path, eksik_yanit):
        """Künye hükmün hemen ardında: aşağıdaki her sayı bu girdilere
        dayanıyor, kullanıcı önce neyin kendisine ait OLMADIĞINI görmeli."""
        out = kos_panel(tmp_path, eksik_yanit)
        html = out['html']
        kunye = html.index('data-safety-defaults="list"')
        risk = html.index('Individual Risks')
        assert kunye < risk, (
            'künye bireysel risk tablosundan SONRA basılıyor — hüküm '
            'okunduktan sonra görülür')

    def test_bos_beyan_satir_uretmez_ama_beyan_edilir(self, tmp_path,
                                                      tam_yanit):
        """Boş liste de bir BEYANDIR — ama MUTLAK bir dürüstlük iddiası
        DEĞİLDİR.

        ÖH D15 / P11B4-31 kardeşi **P11B4-13** ile ÇEVRİLDİ (2026-09-01).
        Bu bekçi eskiden `defaults_applied == []` gelen her koşuda
        ``data-safety-defaults="none"`` blokunu ŞART koşuyordu; o blok
        "The endpoint declared no defaults: every input behind the numbers
        below came from this form." cümlesini basar. ÖLÇÜLDÜ (gerçek
        ``/analyze_safety`` yanıtı, aşağıda `ASSUMED_ALANLARI` ile
        doğrulanır): panel BÜTÜN alanlarını gönderse bile aynı yanıt iki
        ayrı yerde ``ASSUMED L/D = 5 (chamber_length was not supplied)``
        beyan ediyor ve ``chamber_length`` panelin FIELDS listesinde HİÇ
        yok — yani o cümle FİİLEN YANLIŞ. Bekçi böylece kusuru
        KORUYORDU: yanlış cümlenin ekranda kalmasını şart koşuyordu.

        Çevrilmiş hâli: ucun kendi ASSUMED beyanı varsa mutlak cümle
        BASILMAZ ve beyanı yapan alanlar makine yoluyla listelenir; beyan
        yoksa eski davranış aynen korunur.
        """
        out = kos_panel(tmp_path, tam_yanit)
        assert not ALAN_RE.findall(out['html']), (
            'boş beyanla künye satırı basılmış — uydurma')

        sa = tam_yanit.get('safety_analysis') or {}
        assumed = [
            (sa.get('thermal_safety') or {}).get('radiating_area_basis'),
            ((sa.get('explosive_hazards') or {}).get('fragment_hazards')
             or {}).get('case_mass_basis'),
        ]
        beyanli = [v for v in assumed if isinstance(v, str) and 'ASSUMED' in v]
        if beyanli:
            assert 'data-safety-defaults="assumed"' in out['html'], (
                'uç kendi varsayımını beyan ederken panel hâlâ '
                '"hepsi bu formdan geldi" diyor')
            assert 'declared no defaults' not in out['html'], (
                'yanlış dürüstlük cümlesi geri gelmiş')
            for alan in ('radiating_area_basis', 'case_mass_basis'):
                assert alan in out['html'], alan
        else:
            assert 'data-safety-defaults="none"' in out['html'], (
                'boş beyan ekranda görünmüyor — kullanıcı künyenin hiç '
                'çalışmadığını mı yoksa temiz mi olduğunu ayırt edemez')
            assert 'data-src-kind="assumed"' not in out['html']

    def test_beyan_yoksa_kunye_basilmaz(self, tmp_path, eksik_yanit):
        """Alan yanıtta HİÇ yoksa (eski/başka bir uç) iddia da yoktur."""
        beyansiz = dict(eksik_yanit)
        beyansiz.pop('defaults_applied')
        out = kos_panel(tmp_path, beyansiz)
        assert 'data-safety-defaults' not in out['html'], (
            'beyan olmadan künye basılmış — "hepsi sizden geldi" iddiası '
            'ölçülmemiş bir iddiadır')
        assert not ALAN_RE.findall(out['html'])

    def test_panelin_kendi_hukumleri_yerinde(self, tmp_path, eksik_yanit):
        """Künye eklendi diye panelin geri kalanı düşmemeli (regresyon)."""
        out = kos_panel(tmp_path, eksik_yanit)
        # V301/T-ÇAPA-D: FİZİK-2 kalem 8b (ce7d13e1b) tesis ekseni ayrılınca
        # yanıt ``facility_hazard`` taşıyorsa motor rozeti 'MOTOR DESIGN RISK'
        # adını alır ve tesis rozeti ayrıca basılır; taşımıyorsa 'OVERALL
        # RISK' kalır (safety_panel.js). Bölüm aynı rozettir, adı yanıttan.
        risk = ((eksik_yanit.get('safety_analysis') or {})
                .get('risk_assessment') or {})
        if risk.get('facility_hazard'):
            rozet = ('MOTOR DESIGN RISK',)
            if (risk['facility_hazard'] or {}).get('risk_level'):
                rozet += ('FACILITY / SITING HAZARD',)
        else:
            rozet = ('OVERALL RISK',)
        for parca in rozet + ('Individual Risks', 'Risk Matrix',
                              'Pressure Vessel Summary'):
            assert parca in out['html'], f'{parca} bölümü kayboldu'
