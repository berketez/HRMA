"""V307/FS-İZLEME bekçisi — Fırlatma Sahası görev izleme ekranı.

NEDEN BU DOSYA VAR (ölçüldü, docs/scofield/raw/OH/V307/fs-izleme/RAPOR.md)
-------------------------------------------------------------------------
Berke (9 Kas): Fırlatma Sahası'ndaki uçuş "sadece çizgi şeklinde gidiyor".
Ölçüm: kamera bir sondaj roketinin 3-6 km'lik yayını ~136 km yükseklikten
gösteriyordu, canlı okuma üç satırdı. `hrma/static/js/launch_site_tracking.js`
çözülmüş uçuşu bir görev izleme ekranı olarak oynatır. Ekranda sahte veri
ya da sahte animasyon olamaz; bu dosya bunu saf işlevlerle kilitler:

  * zaman -> örnek indisi (ikili arama, kırpma) ve zaman -> konum (doğrusal);
  * panel değerleri ÖRNEK TUTAR: oynatma anına eşit ya da ondan önceki son
    çözücü örneği, yanıt alanıyla BİREBİR aynı sayı (gerçek uç yanıtıyla);
  * olay listesi yalnız yanıtın alanlarından (summary / flight_verdict ya da
    FS-UÇUŞ sözleşmesinin `events` listesi); paraşüt uydurulmaz;
  * doğrulama FAIL-CLOSED (tanınmayan datum, azalan zaman, yanlış şema);
  * yayımlanmayan büyüklük için gösterge yok, adı söylenir;
  * olay renkleri küre işaretçileriyle aynı; i18n EN/TR anahtar eşitliği;
    sayfada tek FS-İZLEME bloğu; kürede tek dışa açma.

Node betiği argv ile değil stdin ile verilir (tests/test_node_cagri_sozlesmesi.py).
"""

import json
import math
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
IZLEME_JS = KOK / 'hrma' / 'static' / 'js' / 'launch_site_tracking.js'
KURE_JS = KOK / 'hrma' / 'static' / 'js' / 'launch_site_globe.js'
I18N_JS = KOK / 'hrma' / 'static' / 'js' / 'i18n_launch_site.js'
SAYFA = KOK / 'hrma' / 'templates' / 'launch_site.html'

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')


def node_kos(govde, girdi):
    """Çekirdeği node'da yükler, `girdi`yi `G` olarak verir, JSON döndürür."""
    betik = ('const C = require(%s);\nconst G = %s;\n%s\n'
             % (json.dumps(str(IZLEME_JS)), json.dumps(girdi), govde))
    proc = subprocess.run([NODE], input=betik, capture_output=True,
                          text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr[:800]
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Test girdileri (test altyapısı; kullanıcıya gösterilen veri değildir)
# ---------------------------------------------------------------------------
def seri_yaniti(son_neden='apogee', yanma=2.0, apoje_t=10.0, t_son=None):
    t = [0.0, 1.0, 2.0, 4.0, 7.0, 10.0, 12.0]
    alt = [0.0, 30.0, 120.0, 500.0, 900.0, 1000.0, 980.0]
    yanit = {
        'status': 'success',
        'series': {
            'time': t, 'altitude': alt, 'altitude_datum': 'above_launch_site',
            'north': [0.0, 1.0, 3.0, 10.0, 30.0, 50.0, 55.0],
            'east': [0.0, 2.0, 4.0, 20.0, 40.0, 70.0, 80.0],
            'speed': [0.0, 40.0, 90.0, 180.0, 120.0, 20.0, 30.0],
            'mach': [0.0, 0.12, 0.27, 0.53, 0.36, 0.06, 0.09],
            'dynamic_pressure_pa': [0.0, 980.0, 4900.0, 18000.0, 7600.0, 220.0, 480.0],
        },
        'summary': {
            'apogee': 1000.0, 'apogee_time': apoje_t, 'apogee_datum': 'above_launch_site',
            'end_reason': son_neden,
            'flight_verdict': {'burn_time_s': yanma, 't_end_s': t_son if t_son is not None else 12.0},
        },
    }
    return yanit


def sozlesme(oynatma=True, inis='solved'):
    t = [0.0, 1.0, 2.0, 5.0, 9.0, 14.0]
    return {
        'schema': 'hrma.launch_site.flight_result/1',
        'status': 'solved',
        'playback_allowed': oynatma,
        'frame': {'altitude_agl': 'above_launch_site'},
        'solver': {'end_reason': 'apogee', 'static_margin_full': 0.45,
                   'static_margin_empty': 0.9},
        'samples': {
            'time_s': t,
            'phase': ['powered', 'powered', 'coast', 'coast', 'descent', 'descent'],
            'altitude_agl_m': [0.0, 50.0, 200.0, 600.0, 300.0, 0.0],
            'altitude_msl_m': [10.0, 60.0, 210.0, 610.0, 310.0, 10.0],
            'north_m': [0.0, 1.0, 2.0, 6.0, 9.0, 12.0],
            'east_m': [0.0, 3.0, 8.0, 20.0, 31.0, 40.0],
            'downrange_m': [0.0, 3.1622776601683795, 8.246211251235321,
                            20.880613017821101, 32.28002478313795, 41.7612260356422],
            'speed_mps': [0.0, 60.0, 120.0, 30.0, 80.0, 95.0],
            'mach': [0.0, 0.18, 0.35, 0.09, 0.24, 0.28],
            'dynamic_pressure_pa': [0.0, 2200.0, 8800.0, 500.0, 3900.0, 5500.0],
        },
        'events': [
            {'key': 'liftoff', 't_s': 0.0, 'altitude_agl_m': 0.0},
            {'key': 'burnout', 't_s': 1.5, 'altitude_agl_m': 120.0},
            {'key': 'max_q', 't_s': 2.0, 'dynamic_pressure_pa': 8800.0},
            {'key': 'apogee', 't_s': 5.0, 'altitude_agl_m': 600.0},
        ] + ([{'key': 'landing', 't_s': 14.0, 'altitude_agl_m': 0.0}] if inis == 'solved' else []),
        'descent': ({'model': 'ballistic_point_mass', 'status': 'solved'} if inis == 'solved'
                    else {'model': 'ballistic_point_mass', 'status': 'not_solved',
                          'reason': 'vehicle_not_statically_stable'}),
    }


# ---------------------------------------------------------------------------
# 1. Zaman -> indis / konum
# ---------------------------------------------------------------------------
@needs_node
def test_zaman_indis_ikili_arama_ve_kirpma():
    out = node_kos("""
const iz = C.normalize(G).iz;
const s = [1.5, -3, 99, 2, 10, NaN].map(t => C.konumla(iz, t));
const ciftT = C.normalize({series: {time: [0, 1, 1, 2], altitude: [0, 1, 2, 3],
    altitude_datum: 'above_launch_site'}}).iz;
console.log(JSON.stringify({s: s, cift: C.konumla(ciftT, 1)}));
""", seri_yaniti())
    s = out['s']
    assert (s[0]['i'], s[0]['j']) == (1, 2) and abs(s[0]['a'] - 0.5) < 1e-15
    assert s[1]['t'] == 0 and s[1]['i'] == 0          # öncesi: ilk örneğe kırpılır
    assert s[2]['t'] == 12 and s[2]['i'] == 6 and s[2]['a'] == 0   # sonrası: son örnek
    assert s[3]['i'] == 2 and s[3]['a'] == 0          # tam örnek zamanı
    assert s[4]['i'] == 5
    assert s[5]['i'] == 0                             # sonlu olmayan zaman ilk örnek
    # Eşit zamanlı iki örnekte t[i] <= t koşulunu sağlayan EN BÜYÜK indis.
    assert out['cift']['i'] == 2


@needs_node
def test_zaman_konum_dogrusal_enterpolasyon():
    out = node_kos("""
const iz = C.normalize(G).iz;
console.log(JSON.stringify([C.konumAt(iz, 3.0), C.konumAt(iz, 7.0)]));
""", seri_yaniti())
    a, b = out
    # t = 3 s, örnekler 2 s (i=2) ile 4 s (i=3) arasında, oran 0,5
    assert a['i'] == 2 and abs(a['a'] - 0.5) < 1e-15
    assert abs(a['up'] - (120.0 + 500.0) / 2) < 1e-12
    assert abs(a['north'] - (3.0 + 10.0) / 2) < 1e-12
    assert abs(a['east'] - (4.0 + 20.0) / 2) < 1e-12
    assert b['i'] == 4 and b['a'] == 0 and b['up'] == 900.0


# ---------------------------------------------------------------------------
# 2. Panel değerleri: örnek tutma, yanıt alanıyla BİREBİR aynı (gerçek uç)
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def gercek_yanit():
    from hrma.app import app
    app.config['TESTING'] = True
    govde = {'thrust': 1300.0, 'burn_time': 2.3, 'dry_mass': 7.4, 'propellant_mass': 2.4,
             'body_diameter': 0.1, 'body_length': 1.1, 'latitude_deg': 28.6}
    with app.test_client() as c:
        r = c.post('/api/six-dof-analysis', json=govde)
    d = r.get_json()
    assert r.status_code == 200 and d['status'] == 'success', d
    return d


@needs_node
def test_panel_degerleri_gercek_yanitla_birebir(gercek_yanit):
    d = gercek_yanit
    s = d['series']
    T = s['time'][-1]
    zamanlar = [0.0, s['time'][1], 0.25 * T, 0.5 * T, (s['time'][7] + s['time'][8]) / 2, T]
    out = node_kos("""
const iz = C.normalize(G.d).iz;
console.log(JSON.stringify(G.z.map(t => C.panelDegerleri(iz, t))));
""", {'d': d, 'z': zamanlar})
    alan = {'altitude': 'altitude', 'speed': 'speed', 'mach': 'mach', 'q': 'dynamic_pressure_pa'}
    for t, p in zip(zamanlar, out):
        i = max(k for k in range(len(s['time'])) if s['time'][k] <= t)
        assert p['i'] == i and p['ornekT'] == s['time'][i]
        kanallar = {r['anahtar'] for r in p['satirlar']}
        assert kanallar == {'altitude', 'downrange', 'speed', 'mach', 'q'}
        for r in p['satirlar']:
            if r['anahtar'] == 'downrange':
                bek = math.hypot(s['north'][i], s['east'][i])
                assert abs(r['deger'] - bek) <= 1e-12 * max(1.0, bek)
                assert r['alan'] == 'hypot(series.north[%d], series.east[%d])' % (i, i)
            else:
                # sayı enterpole edilmez: yanıttaki sayının KENDİSİ
                assert r['deger'] == s[alan[r['anahtar']]][i], (t, r)
                assert r['alan'] == 'series.%s[%d]' % (alan[r['anahtar']], i)


# ---------------------------------------------------------------------------
# 3. Olay listesi (seri yolu: summary / flight_verdict)
# ---------------------------------------------------------------------------
@needs_node
def test_olaylar_yanit_alanlarindan():
    out = node_kos("""
const r = {};
r.apoje = C.olaylar(C.normalize(G.apoje).iz);
r.yer = C.olaylar(C.normalize(G.yer).iz);
r.disari = C.olaylar(C.normalize(G.disari).iz);
const tut = JSON.parse(JSON.stringify(G.apoje)); tut.summary.apogee_withheld_because = 'x';
r.tutulan = C.olaylar(C.normalize(tut).iz);
const ozetsiz = JSON.parse(JSON.stringify(G.apoje)); delete ozetsiz.summary;
r.ozetsiz = C.olaylar(C.normalize(ozetsiz).iz);
console.log(JSON.stringify(r));
""", {'apoje': seri_yaniti(), 'yer': seri_yaniti('ground', t_son=12.0),
      'disari': seri_yaniti(yanma=30.0)})
    ad = lambda L: [(e['anahtar'], e['t']) for e in L]
    assert ad(out['apoje']) == [('liftoff', 0.0), ('burnout', 2.0), ('apogee', 10.0), ('end', 12.0)]
    assert out['apoje'][1]['alan'] == 'summary.flight_verdict.burn_time_s'
    assert out['apoje'][2]['alan'] == 'summary.apogee_time'
    assert ad(out['yer'])[-1] == ('impact', 12.0)
    assert 'end' not in [e['anahtar'] for e in out['yer']]
    # yanma çözüm sonundan sonra: olay "dışarıda" işaretli, sıralı
    disari = {e['anahtar']: e for e in out['disari']}
    assert disari['burnout']['disarida'] is True
    assert 'apogee' not in [e['anahtar'] for e in out['tutulan']]
    assert ad(out['ozetsiz']) == [('liftoff', 0.0), ('end', 12.0)]
    # paraşüt hiçbir yolda uydurulmaz
    for L in out.values():
        assert not any('chute' in e['anahtar'] or 'parachute' in e['anahtar'] for e in L)


# ---------------------------------------------------------------------------
# 4. FS-UÇUŞ sözleşmesi
# ---------------------------------------------------------------------------
@needs_node
def test_sozlesme_iz_olay_panel_oynatma():
    out = node_kos("""
const a = C.normalizeSozlesme(G.cozuldu), b = C.normalizeSozlesme(G.kararsiz);
console.log(JSON.stringify({
  aOk: a.ok, bOk: b.ok, kaynak: a.iz.kaynak,
  olayA: C.olaylar(a.iz), olayB: C.olaylar(b.iz),
  panel: C.panelDegerleri(a.iz, 9.5), oyA: a.iz.oynatma, oyB: b.iz.oynatma,
  inisA: a.iz.inis, inisB: b.iz.inis}));
""", {'cozuldu': sozlesme(), 'kararsiz': sozlesme(oynatma=False, inis='not')})
    assert out['aOk'] and out['bOk'] and out['kaynak'] == 'sozlesme'
    ad = lambda L: [(e['anahtar'], e['t']) for e in L]
    assert ad(out['olayA']) == [('liftoff', 0.0), ('burnout', 1.5), ('maxq', 2.0),
                                ('apogee', 5.0), ('impact', 14.0)]
    assert out['olayA'][-1]['inis'] is True and out['olayA'][-1]['alan'] == 'events[4].t_s'
    assert out['olayA'][2]['deger'] == 8800.0 and out['olayA'][3]['deger'] == 600.0
    # iniş çözülmedi: iniş olayı YOK, iz yükselişin bittiği yerde biter
    assert 'impact' not in [e['anahtar'] for e in out['olayB']]
    assert out['olayB'][-1]['anahtar'] == 'end' and out['olayB'][-1]['alan'] == 'samples.time_s[5]'
    # V307/FS-UÇUŞ-2 (A4): iniş kaydı paraşütlü iniş bayrağını da taşır
    # (sözleşmede descent.model 'parachute_point_mass' değil → False).
    assert out['inisB'] == {'durum': 'not_solved', 'neden': 'vehicle_not_statically_stable',
                            'parasut': False}
    assert out['oyA']['izin'] is True and out['oyB']['izin'] is False
    assert out['oyB']['smFull'] == 0.45 and out['oyB']['smEmpty'] == 0.9
    # panel: t = 9,5 s -> örnek i = 4 (9 s), alanlar sözleşme adlarıyla
    p = out['panel']
    assert p['i'] == 4
    sat = {r['anahtar']: r for r in p['satirlar']}
    smp = sozlesme()['samples']
    assert sat['phase']['deger'] == 'descent' and sat['phase']['alan'] == 'samples.phase[4]'
    assert sat['downrange']['deger'] == smp['downrange_m'][4]
    assert sat['downrange']['alan'] == 'samples.downrange_m[4]'
    assert sat['altitude']['deger'] == smp['altitude_agl_m'][4]
    assert sat['speed']['deger'] == smp['speed_mps'][4]
    assert sat['q']['deger'] == smp['dynamic_pressure_pa'][4]


# ---------------------------------------------------------------------------
# 5. Fail-closed doğrulama + yayımlanmayan büyüklükler
# ---------------------------------------------------------------------------
@needs_node
def test_dogrulama_fail_closed_ve_dusen_kanal():
    out = node_kos("""
const kopya = o => JSON.parse(JSON.stringify(o));
const r = {};
let x = kopya(G.y); x.series.altitude_datum = 'ellipsoid'; r.datum = C.normalize(x);
x = kopya(G.y); delete x.series.altitude_datum; r.datumYok = C.normalize(x);
x = kopya(G.y); x.series.time[3] = 0.5; r.azalan = C.normalize(x);
x = kopya(G.y); x.series.altitude.pop(); r.boy = C.normalize(x);
x = kopya(G.y); x.series.speed[2] = null; const d = C.normalize(x);
r.dusen = {ok: d.ok, speed: !!d.iz.kanal.speed, dusen: d.iz.dusen,
           satir: C.panelDegerleri(d.iz, 3).satirlar.map(s => s.anahtar)};
x = kopya(G.s); x.schema = 'baska/1'; r.sema = C.normalizeSozlesme(x);
x = kopya(G.s); x.frame.altitude_agl = 'mean_sea_level'; r.sDatum = C.normalizeSozlesme(x);
x = kopya(G.s); delete x.samples; r.ornekYok = C.normalizeSozlesme(x);
r.yayimlanmayan = C.yayimlanmayanlar(C.normalize(G.y).iz).map(b => b.anahtar);
console.log(JSON.stringify(r));
""", {'y': seri_yaniti(), 's': sozlesme()})
    assert out['datum'] == {'ok': False, 'neden': 'altitude_datum_unknown'}
    assert out['datumYok'] == {'ok': False, 'neden': 'altitude_datum_unknown'}
    assert out['azalan'] == {'ok': False, 'neden': 'time_not_monotonic'}
    assert out['boy'] == {'ok': False, 'neden': 'altitude_invalid'}
    assert out['dusen']['ok'] and not out['dusen']['speed']
    assert out['dusen']['dusen'] == ['speed'] and 'speed' not in out['dusen']['satir']
    assert out['sema'] == {'ok': False, 'neden': 'contract_schema_unknown'}
    assert out['sDatum'] == {'ok': False, 'neden': 'altitude_datum_unknown'}
    assert out['ornekYok'] == {'ok': False, 'neden': 'samples_missing'}
    assert out['yayimlanmayan'] == ['acceleration', 'mass']


# ---------------------------------------------------------------------------
# 6. Yapısal bekçiler: renk, i18n, sayfa bloğu, küre dışa açma, sahte veri
# ---------------------------------------------------------------------------
@needs_node
def test_olay_renkleri_kure_isaretcileriyle_ayni():
    kure = KURE_JS.read_text(encoding='utf-8')
    kureRenk = {k: int(h, 16) for h, k in
                re.findall(r"add\([^,]+,\s*0x([0-9a-fA-F]{6}),\s*'(\w+)'", kure)}
    assert set(kureRenk) >= {'liftoff', 'burnout', 'apogee', 'impact', 'end'}
    out = node_kos('console.log(JSON.stringify(C.OLAY_RENGI));', {})
    for k, v in kureRenk.items():
        assert out[k] == v, k


def _sozluk_anahtarlari(metin, dil):
    bas = metin.index('\n        %s: {' % dil)
    son = metin.index('\n        }', bas)
    return set(re.findall(r"'(site\.track\w*)'\s*:", metin[bas:son]))


def test_i18n_track_anahtarlari_en_tr_esit_ve_hepsi_tanimli():
    sozluk = I18N_JS.read_text(encoding='utf-8')
    en, tr = _sozluk_anahtarlari(sozluk, 'en'), _sozluk_anahtarlari(sozluk, 'tr')
    assert en and en == tr, en ^ tr
    kod = IZLEME_JS.read_text(encoding='utf-8')
    kullanilan = set(re.findall(r"'(site\.track\w*)'", kod))
    assert kullanilan <= en, kullanilan - en
    # tanımlı ama hiç kullanılmayan (ölü) izleme anahtarı yok
    assert en <= kullanilan, en - kullanilan
    # izleme kodu yeniden kullandığı genel anahtarları da sözlükte bulur
    for k in ('site.liftoff', 'site.impact', 'site.end', 'site.play', 'site.pause'):
        assert "'%s'" % k in sozluk


def test_sayfada_tek_fs_izleme_blogu_ve_yukleme_sirasi():
    html = SAYFA.read_text(encoding='utf-8')
    assert html.count('<!-- FS-İZLEME -->') == 1 and html.count('<!-- /FS-İZLEME -->') == 1
    blok = html[html.index('<!-- FS-İZLEME -->'):html.index('<!-- /FS-İZLEME -->')]
    assert '/static/js/launch_site_tracking.js' in blok
    assert '/static/css/launch_site_tracking.css' in blok
    assert 'id="ls-trk"' in blok and 'LaunchSiteTracking.bind(' in blok
    assert html.count('src="/static/js/launch_site_tracking.js"') == 1
    # küre betiğinden SONRA, sayfanın küreyi kuran betiğinden ÖNCE
    assert (html.index('/static/js/launch_site_globe.js')
            < html.index('<!-- FS-İZLEME -->')
            < html.index('new window.LaunchSiteGlobe('))


def test_kure_tek_disa_acma_ve_yer_izi_tek_tanim():
    kure = KURE_JS.read_text(encoding='utf-8')
    assert kure.count('LaunchSiteGlobe.prototype.getTrackingContext = function') == 1
    # yer izi yarıçapı tek tanımdan; eski sabit literal yer izinde kalmadı
    assert 'GLOBE_R * 1.0015' not in kure
    # çizim (yer izi noktaları) ve dışa açma (izleme ekranının düşey çizgisi)
    # AYNI işlevi çağırır
    assert kure.count('this._flightGroundRadius()') == 1
    assert kure.count('self._flightGroundRadius()') == 1
    kod = IZLEME_JS.read_text(encoding='utf-8')
    assert 'groundTrackRadius()' in kod and '1.0015' not in kod


def test_izleme_kodunda_uydurma_kaynak_yok():
    kod = IZLEME_JS.read_text(encoding='utf-8')
    for yasak in ('Math.random', 'setInterval(', 'fetch('):
        assert yasak not in kod, yasak
