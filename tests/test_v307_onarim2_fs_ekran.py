"""V307/ONARIM2-FS-EKRAN bekçisi — Fırlatma Sahası sonuç ekranı (dalga 2).

NEDEN BU DOSYA VAR (ölçüldü, docs/scofield/raw/OH/V307/onarim2-fs-ekran/RAPOR.md)
---------------------------------------------------------------------------------
* M7-FS-1: WebGL yoksa "Uçuş özeti" (Apoje, çözüm sonu yatay mesafe) ve
  "Olaylar" boş kalıyordu; çözüm vardı. Özet ve olay listesi artık
  çözümden (sözleşme, ``window.LaunchSiteFlightResult``) kurulur; küre
  yalnız çizer.
* M7-UCUS-4 (a) Fırlatma Sahası eşi: yayım kuralının İKİ neden kodu
  (doğrusal sınır aşıldı / kararsızlık penceresi), sınır
  ``t_gecersiz_bas_s`` (null → FAIL-CLOSED), metin nedeni adıyla, yayımlanan
  apoje çalkantısız referans koşudan etiketiyle.

Sayfa içi işlevler şablondan metin olarak çıkarılır ve node'da sahte DOM
yardımcılarıyla koşulur (test altyapısı; kullanıcıya gösterilen veri değil).
Node betiği stdin ile verilir (tests/test_node_cagri_sozlesmesi.py).
"""

import copy
import json
import pathlib
import re
import shutil
import subprocess

import pytest

import tests.test_v307_fs_izleme as FI

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
SABLON = KOK / 'hrma' / 'templates' / 'launch_site.html'
IZLEME_JS = JS / 'launch_site_tracking.js'
I18N_JS = JS / 'i18n_launch_site.js'

NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

# Neden kodları sunucunun TEK tanımından (hrma/app.py yayım kuralı).
from hrma.app import (CALKANTI_YAYIM_NEDENI as NEDEN_SINIR_ASIMI,  # noqa: E402
                      CALKANTI_YAYIM_NEDENI_PENCERE as NEDEN_PENCERE)


def _oku(p):
    return pathlib.Path(p).read_text(encoding='utf-8')


def _islev(kaynak, ad):
    """`function ad(` ile başlayan işlevin tam metni (parantez sayarak)."""
    i = kaynak.index('function %s(' % ad)
    j = kaynak.index('{', i)
    derinlik = 0
    for k in range(j, len(kaynak)):
        c = kaynak[k]
        if c == '{':
            derinlik += 1
        elif c == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[i:k + 1]
    raise AssertionError('işlev kapanmadı: ' + ad)


def _degisken(kaynak, ad):
    i = kaynak.index('var %s = ' % ad)
    return kaynak[i:kaynak.index(';', i) + 1]


_SAHTE = r"""
const E = {};
function el(id) { if (!E[id]) E[id] = {textContent: '', title: ''}; return E[id]; }
function t(k, d) { return '<' + k + '>'; }
function tf(k, p, d) { return '<' + k + ' ' + JSON.stringify(p) + '>'; }
function num_(v) { return (typeof v === 'number' && isFinite(v)) ? v : null; }
function fmtKmM(v) { return 'U(' + v + ')'; }
function fmtNum(v, d) { return 'N(' + v + ')'; }
// `var` (const değil): izleme modülü yüklenirken `typeof window` TDZ'ye düşmesin.
var window = { LaunchSiteFlightResult: G.sonuc,
               LaunchSiteTrackingCore: { OLAY_RENGI: require(%s).OLAY_RENGI } };
var ucusGecerlilikSiniri = (G.sinir === undefined) ? null : G.sinir;
"""


def _sayfa_kos(govde, girdi):
    s = _oku(SABLON)
    parcalar = [_degisken(s, 'UCUS_GECERSIZ_NEDENLERI'), _degisken(s, 'OLAY_SOZLESME_ANAHTARI')]
    for ad in ('ucusGecersizNedeni', 'ucusGecerlilikSiniriOku', 'ucusGecersizKisa',
               'ucusGecersizUyarisi', 'ucusOzetiniBas', 'cozumOlaylari'):
        parcalar.append(_islev(s, ad))
    betik = ('const G = %s;\n' % json.dumps(girdi)
             + _SAHTE % json.dumps(str(IZLEME_JS))
             + '\n'.join(parcalar) + '\n' + govde)
    proc = subprocess.run([NODE], input=betik, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr[:1200]
    return json.loads(proc.stdout)


def _sozlesme_sunucu_bicimli():
    """FS-UÇUŞ sözleşmesi + yanıtın özeti ve sahası (sayfanın kurduğu biçim)."""
    c = FI.sozlesme()
    c['summary'] = {'apogee': 600.0, 'apogee_datum': 'above_launch_site', 'end_reason': 'apogee'}
    c['site'] = {'latitude_deg': 42.0, 'longitude_deg': 35.0, 'elevation_m': 10.0}
    return c


def _yayim(neden, t_gec):
    return {'kosu_turu': 'BAGLASIK', 'neden_kodu': neden, 't_gecersiz_bas_s': t_gec,
            't_ilk_asim_s': t_gec if neden == NEDEN_SINIR_ASIMI else None,
            'gecerlilik': ('DOGRUSAL_MODEL_GECERLILIGI_DISINDA' if neden == NEDEN_SINIR_ASIMI
                           else 'KARARSIZ_PENCERE_GENLIK_TOHUMA_BAGLI' if neden == NEDEN_PENCERE
                           else 'GECERLI'),
            'referans_kosu': {'kosu_turu': 'RIJIT', 'etiket_kodu': 'CALKANTISIZ_REFERANS_KOSU',
                              'alan': 'calkanti.rijit_karsilastirma'}}


_OZET = """
ucusOzetiniBas();
console.log(JSON.stringify({apo: el('ls-apogee').textContent, apoT: el('ls-apogee').title,
  rng: el('ls-range').textContent, ev: cozumOlaylari()}));
"""


# ---------------------------------------------------------------- M7-FS-1
@node_gerekli
def test_fs1_ozet_ve_olaylar_cozumden_kureden_bagimsiz():
    c = _sozlesme_sunucu_bicimli()
    out = _sayfa_kos(_OZET, {'sonuc': c})
    # Apoje = summary.apogee (saha üstü), yatay mesafe = izin son örneği.
    assert out['apo'] == 'U(600)'
    assert 'site.altDatumTip' in out['apoT'] and '"msl":"U(610)"' in out['apoT']
    assert out['rng'] == 'U(%r)' % c['samples']['downrange_m'][-1] or \
        out['rng'] == 'U(' + json.dumps(c['samples']['downrange_m'][-1]) + ')'
    ev = out['ev']
    assert [e['key'] for e in ev] == ['liftoff', 'burnout', 'apogee', 'impact']
    assert [e['t'] for e in ev] == [0.0, 1.5, 5.0, 14.0]
    renk = FI.node_kos('console.log(JSON.stringify(C.OLAY_RENGI));', {})
    assert all(e['color'] == renk[e['key']] for e in ev)
    assert not any(e['invalid'] for e in ev)
    # Sözleşme yoksa özet boş ("--"), liste boş: sayı uydurulmaz.
    bos = _sayfa_kos(_OZET, {'sonuc': None})
    assert bos['apo'] == '--' and bos['rng'] == '--' and bos['ev'] == []


@node_gerekli
def test_fs1_downrange_yoksa_kuzey_doguden_ve_cozum_sonu_olayi():
    c = _sozlesme_sunucu_bicimli()
    del c['samples']['downrange_m']
    c['events'] = [e for e in c['events'] if e['key'] != 'landing']
    c['summary']['end_reason'] = 'time_limit'
    out = _sayfa_kos(_OZET, {'sonuc': c})
    assert out['rng'] == 'U(%s)' % json.dumps((12.0 ** 2 + 40.0 ** 2) ** 0.5)
    assert out['ev'][-1]['key'] == 'end' and out['ev'][-1]['t'] == 14.0


def test_fs1_sayfa_ozeti_ve_listeyi_kureye_baglamaz():
    s = _oku(SABLON)
    # Uçuş işleyicisi özeti ve listeyi KOŞULSUZ basar (WebGL yoksa da).
    assert 'ucusOzetiniBas();\n            renderEvents();' in s
    assert 'if (cizildi) renderEvents();' not in s
    # Liste kürenin işaretçilerinden değil çözümden.
    blok = _islev(s, 'renderEvents')
    assert 'var evs = cozumOlaylari();' in blok and 'globe._events' not in blok
    # Oynatma durumu (küre) özet satırlarını yazmaz.
    oyna = _islev(s, 'updatePlayUI')
    assert "el('ls-apogee')" not in oyna and "el('ls-range')" not in oyna
    # Dil değişiminde özet yeniden basılır.
    assert 'I18N.apply(document.body); ucusOzetiniBas(); renderEvents();' in s


# ---------------------------------------------------------------- M7-UCUS-4 (a)
@node_gerekli
@pytest.mark.parametrize('neden', [NEDEN_SINIR_ASIMI, NEDEN_PENCERE])
def test_u4a_iki_neden_sinir_t_gecersiz_bas_s(neden):
    s = """
const d = {calkanti: {yayim: G.y}};
console.log(JSON.stringify({s: ucusGecerlilikSiniriOku(d, 0.25), n: ucusGecersizNedeni(G.y)}));
"""
    out = _sayfa_kos(s, {'sonuc': None, 'y': _yayim(neden, 2.5)})
    assert out == {'s': 2.5, 'n': neden}
    # Sınır null -> FAIL-CLOSED: izin tamamı (t0'dan) geçerlilik dışı.
    out = _sayfa_kos(s, {'sonuc': None, 'y': _yayim(neden, None)})
    assert out == {'s': 0.25, 'n': neden}
    # Geçerli koşu ya da tanınmayan kod: sınır yok.
    for y in (_yayim(None, None), dict(_yayim(neden, 2.5), neden_kodu='BASKA')):
        assert _sayfa_kos(s, {'sonuc': None, 'y': y})['s'] is None


@node_gerekli
@pytest.mark.parametrize('neden,kisa,uyari', [
    (NEDEN_SINIR_ASIMI, 'site.trackOutsideValidity', 'site.sloshUnpublishedLimit'),
    (NEDEN_PENCERE, 'site.trackOutsideValidityWindow', 'site.sloshUnpublishedWindow')])
def test_u4a_ozet_referans_kosu_etiketli_metin_nedeni_adiyla(neden, kisa, uyari):
    c = _sozlesme_sunucu_bicimli()
    c['summary']['apogee'] = None          # sunucu yayımlamadı
    c['slosh_publication'] = _yayim(neden, 2.5)
    c['slosh_reference'] = {'apogee': 640.0, 'max_alpha_deg': 1.0}
    out = _sayfa_kos(_OZET, {'sonuc': c, 'sinir': 2.5})
    assert out['apo'] == 'U(640) (<site.sloshReferenceRun>)'
    assert out['rng'] == '<%s>' % kisa
    assert out['apoT'].startswith('<%s ' % uyari) and '"t":"N(2.5)"' in out['apoT']
    assert '"apo":"U(640)"' in out['apoT'] and 'site.sloshNoBoundary' not in out['apoT']
    ev = {e['key']: e for e in out['ev']}
    assert ev['limit']['t'] == 2.5 and not ev['limit']['invalid']
    assert not ev['liftoff']['invalid'] and not ev['burnout']['invalid']
    assert ev['apogee']['invalid'] and ev['impact']['invalid']
    # Sınır yok (null): FAIL-CLOSED cümlesi eklenir.
    c['slosh_publication'] = _yayim(neden, None)
    out = _sayfa_kos(_OZET, {'sonuc': c, 'sinir': 0.0})
    assert 'site.sloshNoBoundary' in out['apoT'] and '"t":"—"' in out['apoT']
    assert all(e['invalid'] for e in out['ev'] if e['key'] != 'limit')


_IZ = """
const n = C.normalizeSozlesme(G);
console.log(JSON.stringify({ok: n.ok, gec: n.iz.gecerlilik, ev: C.olaylar(n.iz)}));
"""


@node_gerekli
@pytest.mark.parametrize('neden', [NEDEN_SINIR_ASIMI, NEDEN_PENCERE])
def test_u4a_izleme_iki_neden_ve_referans_apoje(neden):
    soz = FI.sozlesme()
    soz['slosh_publication'] = _yayim(neden, 3.0)
    soz['slosh_reference'] = {'apogee': 640.0}
    out = FI.node_kos(_IZ, soz)
    assert out['ok'] and out['gec'] == {'t': 3.0, 'tVar': True, 'neden': neden,
                                        'referansApoje': 640.0}
    ev = {e['anahtar']: e for e in out['ev']}
    assert ev['limit']['t'] == 3.0 and ev['limit']['alan'] == 'slosh_publication.t_gecersiz_bas_s'
    assert ev['apogee']['gecersiz'] is True and ev['apogee']['deger'] is None
    assert not ev['burnout'].get('gecersiz')
    # Sınır null -> FAIL-CLOSED: t0'dan, sınır olayı yok, hepsi işaretli.
    soz['slosh_publication'] = _yayim(neden, None)
    out = FI.node_kos(_IZ, soz)
    assert out['gec']['t'] == 0.0 and out['gec']['tVar'] is False
    assert 'limit' not in [e['anahtar'] for e in out['ev']]
    assert all(e.get('gecersiz') for e in out['ev'])


def _sozluk(dil):
    metin = _oku(I18N_JS)
    bas = metin.index('\n        %s: {' % dil)
    son = metin.index('\n        }', bas)
    return dict(re.findall(r"'(site\.[\w.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'", metin[bas:son]))


def test_u4a_metinler_iki_dilde_ve_nedeni_adiyla():
    en, tr = _sozluk('en'), _sozluk('tr')
    for k in ('site.trackWindowStart', 'site.trackOutsideValidityWindow', 'site.trackInvalidWindow',
              'site.trackReferenceApogee', 'site.sloshReferenceRun', 'site.sloshUnpublishedLimit',
              'site.sloshUnpublishedWindow', 'site.sloshNoBoundary', 'site.liveOutsideValidityWindow'):
        assert k in en and k in tr and en[k] != tr[k], k
    assert tr['site.sloshReferenceRun'] == 'çalkantısız referans koşu'
    assert 'başlangıç bozucusuna bağlıdır' in tr['site.sloshUnpublishedWindow']
    assert 'initial disturbance' in en['site.sloshUnpublishedWindow']
    assert 'doğrusal sınırı t = {t} s' in tr['site.sloshUnpublishedLimit']
    izleme = _oku(IZLEME_JS)
    assert ("GECERLILIK_DISI_NEDENLERI = ['BAGLASIK_KOSU_DOGRUSAL_SINIRI_ASTI', "
            "'BAGLASIK_KOSU_KARARSIZ_PENCERE']") in izleme
    assert 'sonluSayi(y.t_gecersiz_bas_s)' in izleme and 't_ilk_asim_s' not in _islev(izleme, 'gecerlilikOku')


# ---------------------------------------------------------------- M7-FS-10 / 11 / 12 / 6 / 15
_SAHTE2 = r"""
const E = {};
function el(id) { if (!E[id]) E[id] = {textContent: '', title: ''}; return E[id]; }
function t(k, d) { return '<' + k + '>'; }
function tf(k, p, d) { return '<' + k + ' ' + JSON.stringify(p) + '>'; }
function num_(v) { return (typeof v === 'number' && isFinite(v)) ? v : null; }
function fmtNum(v, d) { return (v === null) ? '--' : v.toFixed(d); }
function srv(x) { return x; }
function alanEtiketi(id) { return '[' + id + ']'; }
"""


def _sayfa_kos2(adlar, degiskenler, govde, girdi=None):
    s = _oku(SABLON)
    parcalar = [_degisken(s, ad) for ad in degiskenler] + [_islev(s, ad) for ad in adlar]
    betik = ('const G = %s;\n' % json.dumps(girdi) + _SAHTE2 + '\n'.join(parcalar) + '\n' + govde)
    proc = subprocess.run([NODE], input=betik, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr[:1200]
    return json.loads(proc.stdout)


@node_gerekli
def test_fs10_inis_hizi_dusey_ve_bileske_ayri():
    out = _sayfa_kos2(['inisHiziMetni'], [], """
console.log(JSON.stringify([
  inisHiziMetni({vertical_speed_mps: -11.958668755100586, speed_mps: 15.59}),
  inisHiziMetni({vertical_speed_mps: -11.958668755100586, speed_mps: 11.958668859683744}),
  inisHiziMetni({speed_mps: 15.59}), inisHiziMetni({})]));""")
    # Mühendisin ölçümü: rüzgâr 10 m/s, düşey 11,96, bileşke 15,59 (betik/a3).
    assert out[0] == '<site.landingSpeedWind {"v":"12.0","g":"15.6"}>'
    assert out[1] == '<site.landingSpeedVertical {"v":"12.0"}>'      # rüzgârsız: tek sayı, düşey
    assert out[2] == '<site.landingSpeedGround {"g":"15.6"}>'        # düşey yoksa adı "yere göre"
    assert out[3] == '—'
    # Durum satırının iniş cümlesi bu metni kullanır (paraşütlü iniş yanıtı).
    satir = _sayfa_kos2(['inisHiziMetni', 'ruzgarBeyani', 'inisNotu'], [], """
console.log(JSON.stringify(inisNotu({track: {descent: {status: 'solved', model: 'parachute_point_mass',
  recovery: {parachute_area_m2: 2.0, parachute_cd: 1.4, parachute_deploy_delay_s: 2.0, assumed: {}},
  impact: {vertical_speed_mps: -11.958668755100586, speed_mps: 15.59}}}}, {wind_speed: 10})));""")
    assert '"landing":"<site.landingSpeedWind {\\"v\\":\\"12.0\\",\\"g\\":\\"15.6\\"}>"' in satir, satir
    assert satir.endswith(' <site.windConstantNote>')
    en, tr = _sozluk('en'), _sozluk('tr')
    assert tr['site.landingSpeedWind'] == 'düşey {v} m/s; yere göre bileşke {g} m/s (rüzgârla)'
    assert '{landing}' in tr['site.flightDescentParachute'] and 'ile iner' not in tr['site.flightDescentParachute']
    assert 'lands at {landing} m/s' not in en['site.flightDescentParachute']


@node_gerekli
def test_fs11_ruzgar_irtifayla_sabit_beyani():
    out = _sayfa_kos2(['ruzgarBeyani'], [], """
console.log(JSON.stringify([ruzgarBeyani({wind_speed: 10}), ruzgarBeyani({wind_speed: 0}),
  ruzgarBeyani({}), ruzgarBeyani(null)]));""")
    assert out == [' <site.windConstantNote>', '', '', '']
    s = _oku(SABLON)
    assert 'var inisMetni = inisNotu(d, body);' in s
    assert _islev(s, 'inisNotu').count('+ ruzgarBeyani(body)') == 2   # paraşütlü + balistik
    en, tr = _sozluk('en'), _sozluk('tr')
    for k in ('site.help.windSpeed', 'site.help.windDir'):
        assert 'independent of altitude (high-altitude wind is not modelled)' in en[k], k
        assert 'irtifadan bağımsız' in tr[k] and 'yüksek irtifa rüzgârı modellenmez' in tr[k], k
    assert tr['site.windConstantNote'] == ('Rüzgâr bütün uçuş boyunca, irtifadan bağımsız aynı kabul '
                                           'edilir (yüksek irtifa rüzgârı modellenmez).')
    # Görev izleme notu: rüzgârlı çözülmüş inişte aynı beyan (aynı anahtar).
    soz = FI.sozlesme()
    soz['request'] = {'wind_speed': 10.0}
    out = FI.node_kos('console.log(JSON.stringify(C.normalizeSozlesme(G).iz.ruzgar));', soz)
    assert out == 10.0
    izleme = _oku(IZLEME_JS)
    assert "iz.ruzgar != null && iz.ruzgar > 0" in izleme and "t('site.windConstantNote'" in izleme


@node_gerekli
def test_fs12_girdi_reddi_oneki_ret_sinifindan():
    govde = """
const d = {error: 'centre_of_gravity_not_built', status: 'error',
  invalid_fields: [{field: 'payload_station', reason: 'PAYLOAD_OUTSIDE_BODY'}],
  message: 'The payload station 5 m from the nose tip is beyond the 3.37 m body. Nothing was integrated.'};
console.log(JSON.stringify([ucRetMetni(d, 422), ucRetMetni(d, 400), ucRetMetni(d, 500),
  ucRetMetni({error: 'six_dof_time_budget_exceeded'}, 503), ucRetMetni(null, 0)]));"""
    out = _sayfa_kos2(['ucRetMetni'], ['UC_ALAN_KIMLIGI', 'GIRDI_RET_DURUMLARI'], govde)
    assert out[0].startswith('<site.inputRejected> · The payload station 5 m')
    assert out[0].endswith('[ls-a-payloadx]"}>') or '[ls-a-payloadx]' in out[0]
    assert out[1].startswith('<site.inputRejected>')
    for o in out[2:]:
        assert o.startswith('<site.solveError>'), o
    en, tr = _sozluk('en'), _sozluk('tr')
    assert en['site.inputRejected'] == 'Input rejected.' and tr['site.inputRejected'] == 'Girdi reddedildi.'


def test_fs6_ic_varsayilan_ad_motor_geometry_ile_ayni():
    s = _oku(SABLON)
    blok = _degisken(s, 'MOTOR_IC_VARSAYILAN_ADI')
    mg = _oku(KOK / 'hrma' / 'export' / 'motor_geometry.py')
    for tur, ad in re.findall(r"(\w+): '(HRMA_\w+)'", blok):
        assert "'motor_name': r.get('motor_name') or '%s'" % ad in mg, (tur, ad)
        assert ad == 'HRMA_' + tur.upper()
    assert len(re.findall(r"(\w+): '(HRMA_\w+)'", blok)) == 3


@node_gerekli
def test_fs6_oturum_araci_ic_adla_gosterilmez():
    out = _sayfa_kos2(['aracAdi'], ['MOTOR_IC_VARSAYILAN_ADI', 'MOTOR_TURU_ADI'], """
console.log(JSON.stringify([
  aracAdi({motor_type: 'liquid', motor_name: 'HRMA_LIQUID', source: 'results'}),
  aracAdi({motor_type: 'hybrid', motor_name: 'HRMA_HYBRID'}),
  aracAdi({motor_type: 'solid', motor_name: null}),
  aracAdi({motor_type: 'liquid', motor_name: 'Example Liquid LOX-RP1 25kN'}),
  aracAdi({motor_type: 'liquid', motor_name: 'HRMA_HYBRID'}),
  aracAdi({name_key: 'site.srcExample', motor_name: 'Example vehicle'}), aracAdi(null)]));""")
    assert out == ['<site.motorTypeName.liquid>', '<site.motorTypeName.hybrid>',
                   '<site.motorTypeName.solid>', 'Example Liquid LOX-RP1 25kN', 'HRMA_HYBRID',
                   '<site.srcExample>', None]
    tr = _sozluk('tr')
    assert (tr['site.motorTypeName.liquid'], tr['site.motorTypeName.hybrid'],
            tr['site.motorTypeName.solid']) == ('Sıvı motor', 'Hibrit motor', 'Katı motor')


def test_fs7_olay_etiketi_sozcuk_ortasindan_kirilmaz():
    css = _oku(KOK / 'hrma' / 'static' / 'css' / 'launch_site_tracking.css')
    ad = re.search(r'\.ls-ev\.ls-trk-olay \.ad \{([^}]*)\}', css).group(1)
    tm = re.search(r'\.ls-ev\.ls-trk-olay \.t \{([^}]*)\}', css).group(1)
    assert 'anywhere' not in ad and 'overflow-wrap: normal' in ad
    assert 'white-space: normal' in tm and 'nowrap' not in tm


@node_gerekli
def test_fs15_neden_notun_kendisinde():
    out = _sayfa_kos2(['projeYuklenemediNotu'], [], """
console.log(JSON.stringify([projeYuklenemediNotu(function () { return 'NEDEN'; })(),
  projeYuklenemediNotu(function () { return ''; })()]));""")
    assert out == ['<site.projectLoadFailed {"reason":"NEDEN"}>', '<site.projectLoadFailed {"reason":"—"}>']
    s = _oku(SABLON)
    assert "applyVehicle(null, 'site.projectLoadFailed'" not in s
    assert s.count('applyVehicle(null, projeYuklenemediNotu(') == 4
    en, tr = _sozluk('en'), _sozluk('tr')
    assert '{reason}' in en['site.projectLoadFailed'] and '{reason}' in tr['site.projectLoadFailed']
    assert 'aşağıda' not in tr['site.projectLoadFailed'] and 'below' not in en['site.projectLoadFailed']
    assert 'ipucunda' not in tr['site.fileRejectedContent'] and 'tooltip' not in en['site.fileRejectedContent']


def test_fs3_bolge_referansi_rampa_demez():
    mp = _oku(JS / 'launch_site_map_packs.js')
    assert ("tf(bolgeReferansiMi(paketId) ? 'site.mapPackImageryDetailRef' : "
            "'site.mapPackImageryDetail',") in mp
    assert "s.id === id && s.approx === true" in mp and "getElementById('ls-presets-data')" in mp
    assert 'halkaMetni(b.detail, p && p.id)' in mp
    en, tr = _sozluk('en'), _sozluk('tr')
    assert 'reference point' in en['site.mapPackImageryDetailRef'] and 'pad' not in en['site.mapPackImageryDetailRef']
    assert 'referans noktasının' in tr['site.mapPackImageryDetailRef'] and 'rampa' not in tr['site.mapPackImageryDetailRef']
    # Bayrağın tek kaynağı kısayol listesi: Sinop ve Konya bölge referansı, paket kimliği aynı.
    from hrma.analysis.launch_site import LAUNCH_SITE_PRESETS
    yaklasik = {p['id'] for p in LAUNCH_SITE_PRESETS if p.get('approx')}
    assert yaklasik == {'sinop_tr', 'konya_tr'}
    paketler = json.loads(_oku(KOK / 'hrma' / 'static' / 'map' / 'harita_paketleri.json'))['packs']
    assert yaklasik <= {p['id'] for p in paketler}


@node_gerekli
def test_fs1_ozet_apoje_deniz_seviyesi_bildirilirse_saha_ustune_cevrilir():
    c = _sozlesme_sunucu_bicimli()
    c['summary'].update(apogee=610.0, apogee_datum='mean_sea_level')
    assert _sayfa_kos(_OZET, {'sonuc': c})['apo'] == 'U(600)'
    c['site']['elevation_m'] = None                  # rakım yok: sayı uydurulmaz
    assert _sayfa_kos(_OZET, {'sonuc': c})['apo'] == '<site.trackApogeeNotPublished>'
