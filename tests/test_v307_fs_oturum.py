"""V307/FS-OTURUM — oturum aracında çalkantı köprüsü + sıvı tank çapının mm son biti.

Kalem 1 (FS-YÜK AÇIK 2; FS-KÜÇÜK kalem 5 tasarımı): motor sayfasından
taşınan oturum aracında Fırlatma Sahası çalkantıyı bağlamıyordu ("The flight
is solved rigid"); aynı motor proje kaynağında ÇKK / geçerlilik dışı hükmü
alıyordu. Köprü kaydı artık motor sonucunun çalkantı izdüşümünü taşır
(flight_handoff.js CALKANTI_KAYNAK_YOLLARI: çalkantı bağlamanın motor
sonucundan OKUDUĞU yapraklar; tam sonucu değil — örnek sıvı 476 564 B,
hibrit 3 004 267 B). Bekçiler: ölçülen her okuma listede; izdüşümle çalkantı
çıktısı ve 6-DOF hükmü/sayıları tam sonuçla bit-aynı; JS izdüşümü Python
aynasıyla aynı; kayıt bloğu yazılır, depo almazsa bloksuz + neden; Fırlatma
Sahası bozuk/başka sürüm bloğu okumaz.

Kalem 2 (TEK-TANIM DEVİR 1): uçuş kaydı sıvı tank çapını (D·1000)/1000 ile
kuruyordu; rastgele tasarımların %2,25'inde D'den 1 ulp farklı (200 000
örnek: docs/scofield/raw/OH/V307/fs-oturum/mm_gidis_donus.json, 4506 → 0).
Kayıt artık motorun metre değerinden (slosh.radius·2, mm alanını bit bit
üretiyorsa).
"""
import contextlib
import copy
import io
import json
import pathlib
import random
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates' / 'launch_site.html'
ORNEKLER = KOK / 'examples'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')
SIVI_HIBRIT = ('liquid', 'hybrid')
ORNEK_DOSYASI = {'liquid': 'Example Liquid LOX-RP1 25kN.hrma',
         'hybrid': 'Example Hybrid N2O-HTPB 3kN.hrma'}
#: Çalkantı yolunun araç düzeni (kanıt gövdesi; ÇALKANTI-ARAYÜZ / FS-KÜÇÜK).
DUZEN = {'liquid': {'ardisik': {'sira': ['oksitleyici', 'yakit']},
                    'govde_boyu_m': 3.6, 'govde_capi_m': 0.5, 'burun_boyu_m': 0.5},
         'hybrid': {'ardisik': {'sira': ['n2o']},
                    'govde_boyu_m': 1.94, 'govde_capi_m': 0.218, 'burun_boyu_m': 0.5}}


def _oku(yol):
    return pathlib.Path(yol).read_text(encoding='utf-8')


# --------------------------------------------------------------------------
# Yardımcılar (kanıt betikleri de bunları ithal eder: izdusum_olcumu.py)
# --------------------------------------------------------------------------
def kopru_yollari():
    """flight_handoff.js'teki yol listesi (iki işaret arası JSON)."""
    js = _oku(JS / 'flight_handoff.js')
    m = re.search(r'// CALKANTI_KAYNAK_YOLLARI_BASI\s*var CALKANTI_KAYNAK_YOLLARI = '
                  r'(\{.*?\});\s*// CALKANTI_KAYNAK_YOLLARI_SONU', js, re.S)
    assert m, 'yol listesi işaretleri bulunamadı'
    return json.loads(m.group(1))


def izdusum(sonuc, yollar):
    """``FlightHandoff.calkantiKaynagi``'nın Python aynası (aynı kural)."""
    out = {}
    for yol in yollar:
        parca = yol.split('.')
        kaynak, hedef = sonuc, out
        for i, k in enumerate(parca):
            if k not in kaynak:
                break
            v = kaynak[k]
            if i == len(parca) - 1 or not isinstance(v, dict):
                hedef[k] = v
                break
            hedef = hedef.setdefault(k, {})
            kaynak = v
    return out


class _KDict(dict):
    """Okunan anahtar yollarını kaydeden sözlük (yalnız ölçüm için)."""

    def __init__(self, d, yol, kayit):
        super().__init__(d)
        self._yol, self._k = yol, kayit

    def _sar(self, k, v):
        return _KDict(v, self._yol + (k,), self._k) if isinstance(v, dict) else v

    def __getitem__(self, k):
        self._k.add(self._yol + (k,))
        return self._sar(k, super().__getitem__(k))

    def get(self, k, d=None):
        self._k.add(self._yol + (k,))
        return self._sar(k, super().__getitem__(k)) if super().__contains__(k) else d

    def __contains__(self, k):
        self._k.add(self._yol + (k,))
        return super().__contains__(k)

    def __iter__(self):
        self._k.add(self._yol + ('*',))
        return super().__iter__()

    def items(self):
        self._k.add(self._yol + ('*',))
        return [(k, self._sar(k, v)) for k, v in super().items()]

    def keys(self):
        self._k.add(self._yol + ('*',))
        return super().keys()

    def values(self):
        self._k.add(self._yol + ('*',))
        return [self._sar(k, v) for k, v in super().items()]

    def __deepcopy__(self, memo):
        # Lüle/kamara zarfı (engine_od_m) derin kopyayla okunur; çalkantı
        # çıktısına girmez — bunu izdüşüm eşitliği ölçer.
        return copy.deepcopy(dict(super().items()), memo)


def okunan_yollar(tur, sonuc, duzen):
    """Çalkantı yolunun (slosh_tanklari + içindeki normalize) okuduğu yollar."""
    from hrma.analysis import slosh_motor_baglanti as k4
    kayit = set()
    k4.slosh_tanklari(tur, _KDict(sonuc, (), kayit), arac_duzeni=duzen)
    return sorted(kayit)


def _kapsaniyor(y, yollar):
    """Okunan yol y listede mi: bir liste yolunun altında (yaprak alt ağacı
    kopyalanır) ya da bir liste yolunun atası (ara düğüm)."""
    son = y[-1]
    tum_alt = son == '*'
    if son in ('*', '#len'):
        y = y[:-1]
    for p in (tuple(s.split('.')) for s in yollar):
        if y[:len(p)] == p:
            return True
        if not tum_alt and p[:len(y)] == y:
            return True
    return False


def _post(istemci, uc, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        r = istemci.post(uc, json=govde)
    return r.status_code, r.get_json()


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def dosya_kaynagi(istemci):
    """Örnek sıvı + hibrit, proje DOSYASINDAN: araç + motor sonucu (sayfanın
    hesap ucunun gövdesi = motor sayfasının currentResults'ı)."""
    out = {}
    for tur, ad in ORNEK_DOSYASI.items():
        doc = (ORNEKLER / ad).read_text(encoding='utf-8')
        k, d = _post(istemci, '/api/flight-vehicle',
                     {'source': 'file', 'file_name': 'x.hrma', 'document_text': doc,
                      'include_motor_result': True})
        assert k == 200, d
        out[tur] = d
    return out


# ====================================================================== kalem 1
def test_yol_listesi_bicimi():
    yollar = kopru_yollari()
    assert sorted(yollar) == sorted(SIVI_HIBRIT)
    for tur, liste in yollar.items():
        assert len(liste) == len(set(liste)), tur
        parcalar = [tuple(s.split('.')) for s in liste]
        for a in parcalar:
            assert all(a[:len(b)] != b for b in parcalar if b != a), (tur, a)  # ön ek yok
    js = _oku(JS / 'flight_handoff.js')
    assert 'var CALKANTI_KAYNAK_SURUMU = 1;' in js
    assert 'calkantiKaynagi: calkantiKaynagi,' in js


@pytest.mark.parametrize('tur', SIVI_HIBRIT)
def test_olculen_her_okuma_listede(tur, dosya_kaynagi):
    ms = dosya_kaynagi[tur]['motor_result']
    yollar = kopru_yollari()[tur]
    okunan = okunan_yollar(tur, ms, copy.deepcopy(DUZEN[tur]))
    assert len(okunan) > 40
    eksik = ['.'.join(y) for y in okunan if not _kapsaniyor(y, yollar)]
    assert eksik == [], eksik


@pytest.mark.parametrize('tur', SIVI_HIBRIT)
def test_izdusumle_calkanti_ciktisi_bit_ayni(tur, dosya_kaynagi):
    from hrma.analysis import slosh_motor_baglanti as k4
    ms = dosya_kaynagi[tur]['motor_result']
    iz = json.loads(json.dumps(izdusum(ms, kopru_yollari()[tur])))   # depo gidiş-dönüşü
    assert len(json.dumps(iz)) < len(json.dumps(ms)) / 20             # tam sonuç taşınmıyor
    a = k4.slosh_tanklari(tur, ms, arac_duzeni=copy.deepcopy(DUZEN[tur]))
    b = k4.slosh_tanklari(tur, iz, arac_duzeni=copy.deepcopy(DUZEN[tur]))
    assert a['durum'] == 'BAGLANDI'
    assert json.dumps(k4.json_ozeti(a), sort_keys=True) == json.dumps(k4.json_ozeti(b), sort_keys=True)


def _fs_govdesi(veh, kuru, **ek):
    """launch_site.html "Bu sahadan uçur" gövdesi (test_v307_fs_kucuk ile aynı)."""
    ft = veh.get('flight_thrust') or {}
    g = {'body_diameter': 0.5, 'body_length': 3.6, 'nose_length': 0.5, 'nose_type': 'ogive',
         'dry_mass': kuru + veh['engine_inert_mass'] + (ft.get('propellant_residual_kg') or 0.0),
         'propellant_mass': ft.get('propellant_consumed_kg') or veh['propellant_mass'],
         'nozzle_exit_area': ft.get('nozzle_exit_area_m2'),
         'thrust_reference_pressure': ft.get('thrust_reference_pressure_pa'),
         'thrust': veh['thrust'], 'burn_time': veh['burn_time'], 'cd0': 0.45,
         'fin_count': 4, 'fin_geometry_rule': 'static_margin',
         'launch_elevation_deg': 84.0, 'launch_azimuth_deg': 90.0,
         'rail_length': 5.0, 'wind_speed': 0.0, 'wind_direction_deg': 270.0, 't_max': 400.0,
         'descent_model': 'ballistic', 'engine_od_m': veh.get('engine_od_m'),
         'engine_length_m': veh.get('engine_length_m'),
         'propellant_volume_m3': veh.get('propellant_volume_m3'),
         'latitude_deg': 28.6084, 'longitude_deg': -80.6043}
    g.update(ek)
    return {k: v for k, v in g.items() if v is not None}


@pytest.mark.slow
def test_iki_kaynak_ayni_hukum_ve_bit_ayni_sayilar_sivi(istemci, dosya_kaynagi):
    """Aynı sıvı motor: proje dosyası kaynağı (tam motor sonucu) ⟷ oturum
    kaynağı (motor sayfasının köprüsü: 'results' aracı + kaydın izdüşümü,
    depo gidiş-dönüşüyle). Hüküm, pencereler, tanklar ve uçuş bit-aynı."""
    d = dosya_kaynagi['liquid']
    ms = d['motor_result']
    k, r = _post(istemci, '/api/flight-vehicle',
                 {'source': 'results', 'motor_type': 'liquid', 'results': ms})
    assert k == 200, r
    oturum_araci = r['vehicle']
    iz = json.loads(json.dumps(izdusum(ms, kopru_yollari()['liquid'])))
    duzen = {'ardisik': {'sira': ['oksitleyici', 'yakit']}}
    sonuc = []
    for veh, kaynak in ((d['vehicle'], ms), (oturum_araci, iz)):
        blok = {'motor_type': 'liquid', 'motor_sonucu': kaynak, 'arac_duzeni': duzen}
        k, s = _post(istemci, '/api/six-dof-analysis', _fs_govdesi(veh, 60.0, calkanti=blok))
        assert k == 200, s
        sonuc.append(s)
    p, o = sonuc
    assert p['calkanti']['durum'] == 'BAGLANDI'
    assert p['calkanti']['slosh_stability']['genel_hukum'] != 'KARARLI'   # örnek: ÇKK
    for anahtar in ('slosh_stability', 'tanklar', 'rijit_karsilastirma', 'durum'):
        assert json.dumps(o['calkanti'][anahtar], sort_keys=True) == \
            json.dumps(p['calkanti'][anahtar], sort_keys=True), anahtar
    assert o['summary'] == p['summary'] and o['series'] == p['series']
    # Bloksuz (eski oturum) uçuş rijit: hüküm yok — iki kaynak iki sınıf idi.
    k, eski = _post(istemci, '/api/six-dof-analysis', _fs_govdesi(oturum_araci, 60.0))
    assert k == 200 and eski.get('calkanti') is None
    assert eski['summary'] != o['summary']


@pytest.mark.slow
def test_iki_kaynak_ayni_calkanti_hibrit(istemci, dosya_kaynagi):
    from hrma.analysis import slosh_motor_baglanti as k4
    d = dosya_kaynagi['hybrid']
    ms = d['motor_result']
    k, r = _post(istemci, '/api/flight-vehicle',
                 {'source': 'results', 'motor_type': 'hybrid', 'results': ms})
    assert k == 200, r
    iz = json.loads(json.dumps(izdusum(ms, kopru_yollari()['hybrid'])))
    a = k4.json_ozeti(k4.slosh_tanklari('hybrid', ms, arac_duzeni=copy.deepcopy(DUZEN['hybrid'])))
    b = k4.json_ozeti(k4.slosh_tanklari('hybrid', iz, arac_duzeni=copy.deepcopy(DUZEN['hybrid'])))
    assert a['durum'] == 'BAGLANDI' and 'TUKETIM_BOSALMA_COZUMU' in a['tanklar'][0]['beyan']
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    # Oturum aracı (köprü) ve dosya aracı aynı uçuş girdilerini taşır.
    for alan in ('thrust', 'burn_time', 'engine_inert_mass', 'propellant_mass',
                 'engine_length_m', 'propellant_tanks', 'flight_thrust'):
        assert r['vehicle'][alan] == d['vehicle'][alan], alan


_DOM = r"""
var document = { getElementById: function () { return null; },
  dispatchEvent: function () {}, querySelector: function () { return null; } };
var depo = {};
var window = { document: document, location: { pathname: '/liquid' },
  localStorage: { getItem: function (k) { return depo[k] || null; },
                  setItem: function (k, v) { if (global.DEPO_DOLU && v.indexOf('calkanti_kaynagi"') >= 0
                                                 && v.indexOf('motor_sonucu') >= 0) {
                                               throw new Error('QuotaExceededError'); }
                                             depo[k] = v; },
                  removeItem: function (k) { delete depo[k]; } } };
global.window = window; global.document = document;
"""


def _node(betik, girdi=None):
    # Betik argv ile GEÇİLMEZ (test_node_cagri_sozlesmesi: Linux
    # MAX_ARG_STRLEN); betik stdin'den, girdi betiğe JSON dize olarak gömülür.
    if girdi is not None:
        betik = betik.replace("require('fs').readFileSync(0, 'utf8')",
                              json.dumps(girdi))
    sonuc = subprocess.run([NODE], input=betik, capture_output=True,
                           text=True, timeout=60)
    assert sonuc.returncode == 0, sonuc.stderr
    return json.loads(sonuc.stdout.strip().splitlines()[-1])


@node_gerekli
@pytest.mark.parametrize('tur', SIVI_HIBRIT)
def test_js_izdusumu_python_aynasiyla_ayni(tur, dosya_kaynagi):
    ms = dosya_kaynagi[tur]['motor_result']
    betik = _DOM + _oku(JS / 'flight_handoff.js') + r"""
var veri = require('fs').readFileSync(0, 'utf8');
var ms = JSON.parse(veri);
console.log(JSON.stringify(window.FlightHandoff.calkantiKaynagi(ms, '%s')));
""" % tur
    js_iz = _node(betik, json.dumps(ms))
    # Değer eşitliği (JSON.stringify tam sayı değerli kayan sayıyı '30' yazar;
    # Python 30 == 30.0; kayan sayılar en kısa gidiş-dönüş yazımıyla aynı bit).
    assert js_iz == izdusum(ms, kopru_yollari()[tur])


@node_gerekli
def test_kopru_kaydi_blogu_yazar_depo_almazsa_bloksuz_ve_nedenli(dosya_kaynagi):
    ms = dosya_kaynagi['liquid']['motor_result']
    veh = dosya_kaynagi['liquid']['vehicle']
    sablon = _DOM + _oku(JS / 'flight_handoff.js') + r"""
global.DEPO_DOLU = %s;
var girdi = JSON.parse(require('fs').readFileSync(0, 'utf8'));
global.fetch = function () { return Promise.resolve({ ok: true,
  json: function () { return Promise.resolve({ vehicle: girdi.veh }); } }); };
window.FlightHandoff.publish(girdi.ms, { motor_type: 'liquid' }).then(function () {
  var durum = {};
  var k = window.FlightHandoff.readLast(durum);
  console.log(JSON.stringify({ durum: durum.status, kayit: k }));
});
"""
    girdi = json.dumps({'ms': ms, 'veh': veh})
    tam = _node(sablon % 'false', girdi)
    assert tam['durum'] == 'ok'
    blok = tam['kayit']['calkanti_kaynagi']
    assert blok['surum'] == 1 and blok['motor_type'] == 'liquid'
    assert blok['motor_sonucu'] == izdusum(ms, kopru_yollari()['liquid'])
    assert 'calkanti_kaynagi_yazilamadi' not in tam['kayit']
    dolu = _node(sablon % 'true', girdi)
    assert dolu['durum'] == 'ok' and dolu['kayit']['vehicle'] == veh    # araç kaybolmaz
    assert 'calkanti_kaynagi' not in dolu['kayit']
    assert dolu['kayit']['calkanti_kaynagi_yazilamadi'] is True


def _fs_islevi(ad):
    saha = _oku(SABLON)
    i = saha.index('function %s(' % ad)
    j = saha.index('\n    }\n', i) + 6
    return saha[i:j]


@node_gerekli
def test_fs_oturum_blogunu_okur_bozugu_okumaz():
    betik = ('var window = { FlightHandoff: { CALKANTI_KAYNAK_SURUMU: 1 } };'
             'var FlightHandoff = window.FlightHandoff;'
             + _fs_islevi('oturumCalkantiKaynagi') + r"""
var ms = { propellant_tanks: {} }, v = { motor_type: 'liquid' };
function k(b) { return oturumCalkantiKaynagi({ vehicle: v, calkanti_kaynagi: b }, v); }
console.log(JSON.stringify([
  k({ surum: 1, motor_type: 'liquid', motor_sonucu: ms }) === ms,
  k(undefined), k(null), k('x'), k({ surum: 2, motor_type: 'liquid', motor_sonucu: ms }),
  k({ surum: 1, motor_type: 'hybrid', motor_sonucu: ms }),
  k({ surum: 1, motor_type: 'liquid', motor_sonucu: [1] }),
  k({ surum: 1, motor_type: 'liquid', motor_sonucu: 'x' }),
  oturumCalkantiKaynagi({ vehicle: v, calkanti_kaynagi_yazilamadi: true }, v)]));
""")
    assert _node(betik) == [True] + [None] * 8


def test_fs_oturum_kaynagini_proje_ile_ayni_bloga_koyar():
    saha = _oku(SABLON)
    i = saha.index('function loadSessionVehicle(')
    govde = saha[i:saha.index('\n    }\n', i)]
    assert ("applyVehicle(v, 'site.sessionVehicleLoaded', 'Loaded from the last motor calculation.',\n"
            "                         oturumCalkantiKaynagi(doc, v), OTURUM_KAYNAK_YOK);") in govde
    # Blok motor sayfasının ve proje kaynağının bloğuyla aynı alan.
    assert 'return { motor_type: mt, motor_sonucu: currentMotorResult, arac_duzeni: duzen };' in saha
    # Neden metni tek yardımcıdan; oturumda yeni neden, diğer kaynaklarda eski.
    assert saha.count('= calkantiKaynakYok();') == 2
    assert "currentMotorResultYok = currentMotorResult ? null : (motorSonucuYok || null);" in saha


def test_yeni_metin_en_tr_ilgili_anahtarin_ardinda():
    sozluk = _oku(JS / 'i18n_launch_site.js')
    assert sozluk.count("'site.sloshSessionNoSource':") == 2
    for dil_basi in ("'site.sloshNoMotorResult': 'Slosh", "'site.sloshNoMotorResult': 'Çalkantı"):
        i = sozluk.index(dil_basi)
        sonraki = sozluk[sozluk.index('\n', i) + 1:]
        satir = [s for s in sonraki.splitlines() if s.strip() and not s.strip().startswith('/*')][0]
        assert satir.strip().startswith("'site.sloshSessionNoSource':"), satir
    i = sozluk.index("'site.sloshSessionNoSource': 'Motor")
    tr = sozluk[i:sozluk.index('\n', i)]
    assert 'Uçuş rijit çözülür.' in tr and 'yeniden hesaplayın' in tr
    saha = _oku(SABLON)
    i = saha.index("var OTURUM_KAYNAK_YOK = ['site.sloshSessionNoSource',")
    en = re.search(r"'site\.sloshSessionNoSource': ('(?:[^'\\]|\\.)*')", sozluk).group(1)
    assert en in saha[i:i + 600]                                    # yedek = EN sözlük


# ====================================================================== kalem 2
def test_sivi_tank_capi_motorun_metre_degerinden_ornek(dosya_kaynagi):
    from hrma.analysis import slosh_motor_baglanti as k4
    d = dosya_kaynagi['liquid']
    ms, veh = d['motor_result'], d['vehicle']
    tanklar = {t['key']: t for t in veh['propellant_tanks']}
    k = k4.json_ozeti(k4.slosh_tanklari('liquid', ms, arac_duzeni=copy.deepcopy(DUZEN['liquid'])))
    for anahtar, tid in (('oxidizer_tank', 'oksitleyici'), ('fuel_tank', 'yakit')):
        r = ms['propellant_tanks'][anahtar]['slosh']['radius']
        assert tanklar[anahtar]['diameter_m'] == 2.0 * r
        assert tanklar[anahtar]['diameter_m'] * 1000.0 == \
            ms['propellant_tanks'][anahtar]['dimensions']['diameter']
        satir = [t for t in k['tanklar'] if t['tank_id'] == tid][0]
        assert satir['geometri']['R_ref_m'] == r                    # tablo R = motor R


def test_sivi_tank_capi_rastgele_bit_ayni():
    """Betik 200 000 örnek ölçtü (önce 4506, sonra 0); burada 20 000."""
    from hrma.analysis import flight_vehicle as fv
    rnd = random.Random(19)
    once = 0
    for _ in range(20_000):
        D = rnd.uniform(0.03, 4.0)
        blok = json.loads(json.dumps({'dimensions': {'diameter': D * 1000},
                                      'slosh': {'radius': D / 2}}))
        assert fv._liquid_tank_diameter_m(blok) == D
        once += fv._mm_to_m(blok['dimensions']['diameter']) != D
    assert once > 200        # eski yol bu örneklemde gerçekten kayıyordu


def test_sivi_tank_capi_yaricap_yoksa_ya_da_tutmuyorsa_kart_mm_alani():
    from hrma.analysis import flight_vehicle as fv
    D = 0.3141592653589793
    mm = fv._mm_to_m(D * 1000)
    assert fv._liquid_tank_diameter_m({'dimensions': {'diameter': D * 1000}}) == mm
    assert fv._liquid_tank_diameter_m({'dimensions': {'diameter': D * 1000},
                                       'slosh': {'radius': D / 2 * (1 + 1e-12)}}) == mm
    assert fv._liquid_tank_diameter_m({'dimensions': {'diameter': D * 1000},
                                       'slosh': {'status': 'not_computed'}}) == mm
    assert fv._liquid_tank_diameter_m({'dimensions': {'diameter': -5.0},
                                       'slosh': {'radius': 0.1}}) is None
    assert fv._liquid_tank_diameter_m(None) is None
