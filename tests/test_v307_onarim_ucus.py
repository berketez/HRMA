"""V307/ONARIM-UÇUŞ — mühendis turu (19 Kas) 6-DOF, araç kütlesi ve Fırlatma
Sahası bulgularının bekçileri.

Ne kilitlenir (fizik ve sözleşme; bugünkü çıktı değil):
  * M7-UCUS-5: α penceresi boşsa ``max_alpha_deg`` bir ölçüm değildir
    (None, 0,0 değil) ve α koşulu ölçülmediği için hüküm verilmez.
  * M7-UCUS-16: negatif statik marj (basınç merkezi ağırlık merkezinin
    önünde) TEK kural: takla eşiği tetiklensin ya da tetiklenmesin apoje
    yayımlanmaz; statik marj ve kararlılık hükmü (geometri) kalır.
  * M7-UCUS-8: motor burnun arkasındaki silindirik gövdeye sığmalı; alan
    yuvarlaması (2 ondalık) çelişki sayılmaz.
  * M7-FS-4: iniş reddi gerçek nedenle (hücum açısı ⟷ statik marj).
  * M7-FS-14: kayıtlı projenin 6-DOF Cd₀'ı ve ortamı araçla taşınır.
  * M7-UCUS-9 / M7-UCUS-2: 6-DOF Kuru Kütle satırı tek tanım: Faydalı Yük
    alanı hariç, uçan kuru kütle dökümü, motordan gelmeyen kütle 0 ise
    adıyla.
  * M7-FS-9: saha değişimi önceki uçuşu geçersiz kılar (üç yol da).
"""

import contextlib
import io
import json
import pathlib
import shutil
import subprocess

import pytest

from hrma.analysis import flight_vehicle as fv
from hrma.analysis import launch_site_flight as lsf

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
PANEL = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
LS = (KOK / 'hrma' / 'templates' / 'launch_site.html').read_text(encoding='utf-8')
I18N_LS = (JS / 'i18n_launch_site.js').read_text(encoding='utf-8')
I18N_C = (JS / 'i18n_common.js').read_text(encoding='utf-8')
TAKIP = (JS / 'launch_site_tracking.js').read_text(encoding='utf-8')
UC = '/api/six-dof-analysis'
HIBRIT = KOK / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma'


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(client, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        r = client.post(UC, json=govde)
    return r.status_code, r.get_json()


#: Katı örnek motorun sabit itki karşılığı (örnek proje alanları sd_thrust /
#: sd_burn / sd_dry_m / sd_prop_m; gövde örnekten).
KATI = dict(body_diameter=0.091, body_length=1.06, nose_length=0.5,
            nose_type='ogive', fin_count=4, cd0=0.45, wind_speed=5,
            wind_direction_deg=0, launch_elevation_deg=90,
            launch_azimuth_deg=0, rail_length=5, dry_mass=3.42,
            propellant_mass=2.407, thrust=1298.5, burn_time=2.28)
#: Hibrit örnek motor (sd_thrust / sd_burn; kuru = 25 + 1,694 yanmayan).
HIB = dict(body_diameter=0.218, body_length=1.94, nose_length=0.5,
           nose_type='ogive', fin_count=4, cd0=0.5, wind_speed=5,
           wind_direction_deg=0, launch_elevation_deg=90,
           launch_azimuth_deg=0, rail_length=5, dry_mass=26.694,
           propellant_mass=13.307, thrust=2577.1, burn_time=10.41)
#: Mühendisin negatif marj denemeleri (kanatçık ölçüleri aynen).
KATI_KUCUK_KANAT = dict(fin_root_chord=0.121, fin_tip_chord=0.061,
                        fin_sweep=0.049, fin_span=0.02)
HIB_KUCUK_KANAT = dict(fin_root_chord=0.291, fin_tip_chord=0.145,
                       fin_sweep=0.116, fin_span=0.03)


# --- M7-UCUS-5 / M7-UCUS-16 ---------------------------------------------------

def test_takla_bos_alfa_penceresi_sifir_degil(client):
    kod, d = _post(client, dict(KATI, **KATI_KUCUK_KANAT))
    assert kod == 200, d
    s = d['summary']
    assert s['static_margin_full'] < 0 and s['static_margin_empty'] < 0
    # Uçuş α penceresine (t > 1 s) girmeden bitti: ölçüm yok.
    assert s['max_alpha_deg'] is None
    assert s['apogee'] is None
    assert s['flight_verdict']['stability'] in (
        'not_evaluated', 'static_margin_at_or_below_1_cal')


def test_negatif_marjda_apoje_yok_takla_olmasa_da(client):
    kod, d = _post(client, dict(HIB, **HIB_KUCUK_KANAT))
    assert kod == 200, d
    s = d['summary']
    assert s['static_margin_full'] < 0 and s['static_margin_empty'] < 0
    # Takla eşiği tetiklenmedi (entegrasyon "apoje" olayıyla bitti) ama
    # araç statik olarak kararsız: tepe noktası apoje diye yayımlanmaz.
    assert s['end_reason'] == 'apogee'
    assert s['flight_verdict']['flight'] == 'apogee'
    assert s['apogee'] is None and s['apogee_time'] is None
    assert s['apogee_withheld_because'].startswith('NEGATIVE STATIC MARGIN')
    # Hüküm geometridir, kalır.
    assert s['stable'] is False
    assert s['flight_verdict']['stability'] == 'static_margin_at_or_below_1_cal'


def test_pozitif_marjda_apoje_degismez(client):
    kod, d = _post(client, HIB)
    assert kod == 200, d
    s = d['summary']
    assert s['static_margin_full'] > 0 and s['static_margin_empty'] > 0
    assert s['apogee'] is not None and s['apogee'] > 1000.0
    assert 'apogee_withheld_because' not in s


def test_panel_negatif_marj_rozeti_iki_dilde():
    assert "T('sixdof.apogeeNegativeMargin'," in PANEL
    assert I18N_C.count("'sixdof.apogeeNegativeMargin':") == 2


# --- M7-UCUS-8 ------------------------------------------------------------------

def test_motor_burna_giremez_yuvarlama_celiski_degil():
    # Katı örnek: burun 0,50 + motor 0,562 = 1,062 m; alan 1,06 (2 ondalık).
    assert fv.airframe_fit_conflicts(0.091, 0.562, 0.091, 1.06, 0.50) == []
    c = fv.airframe_fit_conflicts(0.091, 0.562, 0.091, 0.80, 0.50)
    assert [x['reason'] for x in c] == ['engine_reaches_into_nose']
    assert c[0]['length_behind_nose_m'] == pytest.approx(0.30)
    # Burun verilmezse eski kural (geri uyum).
    assert fv.airframe_fit_conflicts(0.091, 0.562, 0.091, 0.80) == []
    # Motordan kısa gövde yine eski adıyla.
    c2 = fv.airframe_fit_conflicts(0.091, 0.562, 0.091, 0.40, 0.50)
    assert [x['reason'] for x in c2] == ['body_shorter_than_engine']


def test_kisa_govde_ucta_adli_ret(client):
    g = dict(KATI, body_length=0.80, engine_od_m=0.091, engine_length_m=0.5621)
    kod, d = _post(client, g)
    assert kod == 422
    assert d['error'] == 'airframe_cannot_carry_engine'
    assert [c['reason'] for c in d['invalid_fields']] == ['engine_reaches_into_nose']


def test_govde_notu_formdaki_olcuyu_yazar():
    blok = PANEL[PANEL.index('function govdeNotunuYaz()'):]
    blok = blok[:blok.index('\n    }\n')]
    assert 'sd_body_l: [govdeNotu.boy, 2]' in blok
    assert "ad + ' = ' + sayiEkran(v, turetilen[id][1])" in blok
    assert "['sd_body_d', 'sd_body_l', 'sd_nose_l'].forEach" in PANEL


# --- M7-FS-4 --------------------------------------------------------------------

class _Cozucu:
    pass


def _res(**ek):
    r = {'end_reason': 'apogee', 'stable': False, 'static_margin_full': 3.43,
         'static_margin_empty': 4.43, 'max_alpha_deg': 15.39,
         'time': [0.0, 1.0], 'position': [[0, 0], [0, 0], [0, 1]],
         'velocity': [[0, 0], [0, 0], [0, 0]]}
    r.update(ek)
    return r


def test_inis_reddi_gercek_nedenle():
    x = lsf.descent_flight(_Cozucu(), _res(), None, 100.0)
    assert x['reason'] == 'ascent_alpha_above_linear_limit'
    x = lsf.descent_flight(_Cozucu(), _res(static_margin_full=0.6), None, 100.0)
    assert x['reason'] == 'vehicle_not_statically_stable'
    x = lsf.descent_flight(_Cozucu(), _res(stable=None, max_alpha_deg=None), None, 100.0)
    assert x['reason'] == 'stability_not_evaluated'


def test_durum_satiri_hukmu_nedeniyle_yazar():
    assert 'if (unstable) setStatus(kararsizlikMetni(d));' in LS
    f = LS[LS.index('function kararsizlikMetni(d)'):]
    f = f[:f.index('\n    }\n')]
    assert "fv.stability === 'alpha_above_linear_limit'" in f
    for k in ('site.unstableAlpha', 'site.unstableTumble', 'site.flightDescentAlpha',
              'site.flightDescentNotEvaluated', 'site.trackDescentAlpha',
              'site.trackDescentNotEvaluated'):
        assert I18N_LS.count("'" + k + "':") == 2, k
    assert "ascent_alpha_above_linear_limit: 'site.trackDescentAlpha'" in TAKIP


# --- M7-FS-14 -------------------------------------------------------------------

def test_proje_kurulumu_cd0_ve_ortam_tasir():
    belge = json.loads(HIBRIT.read_text(encoding='utf-8'))
    k = fv.project_sixdof_setup(belge, 'project')
    assert k['cd0'] == 0.5
    assert (k['wind_speed'], k['launch_elevation_deg'], k['launch_azimuth_deg']) == (5, 90, 0)
    assert k['source'] == 'project' and k['unreadable'] == []
    # Bozuk alan adıyla.
    belge['inputs']['dynamic']['flight']['sixdof']['fields']['sd_cd0'] = 'abc'
    assert fv.project_sixdof_setup(belge)['unreadable'] == ['cd0']
    assert fv.project_sixdof_setup({'inputs': {}}) is None


def test_uc_ve_sayfa_cd0_yi_aractan_doldurur():
    app_py = (KOK / 'hrma' / 'app.py').read_text(encoding='utf-8')
    assert "vehicle['sixdof_setup'] = _proje_kurulumu" in app_py
    assert "vehicle['sixdof_setup'] = _dosya_kurulumu" in app_py
    kur = LS[LS.index('function govdeyiKaynaktanKur(v)'):]
    kur = kur[:kur.index('function aracKurulumu(v)')]
    assert "cdEl.value = (cdKur !== null) ? String(cdKur) : cdEl.defaultValue;" in kur
    # Oturum aracı: panel köprüye Cd₀ + ortamı verir.
    assert "sd_cd0: 'cd0'" in PANEL and 'out.sixdof_setup = kurulum;' in PANEL


# --- M7-UCUS-9 / M7-UCUS-2 (düğüm düzeneği) ------------------------------------

def _js_islevi(kaynak, ad):
    bas = kaynak.index('function ' + ad + '(')
    i = kaynak.index('{', bas)
    derinlik = 0
    for j in range(i, len(kaynak)):
        if kaynak[j] == '{':
            derinlik += 1
        elif kaynak[j] == '}':
            derinlik -= 1
            if derinlik == 0:
                return kaynak[bas:j + 1]
    raise AssertionError(ad + ' kapanmıyor')


NODE = shutil.which('node')


def _kuru_kutle(arac, alan, yuk_m='', yuk_x='', kip='simple', kalan=None,
                tohum=False):
    islev = _js_islevi(PANEL, 'kuruKutleTanimi')
    betik = """
var ELS = { sd_payload_m: { value: %(ym)s, dataset: {} }, sd_payload_x: { value: %(yx)s, dataset: {} },
            sd_dry_m: { value: %(alan)s, dataset: %(ds)s } };
function $(id) { return ELS[id] || null; }
function T(k, fb) { return fb; }
function TF(k, p, fb) { return fb.replace(/\\{(\\w+)\\}/g, function (_, a) { return p[a]; }); }
function sayiEkran(v, n) { return Number(v).toFixed(n); }
var massMode = %(kip)s, sayfaMotoruSatiri = %(sat)s, tohumNotu = %(tn)s;
var window = { FlightHandoff: { inertLedgerText: function (a, f) {
    return 'Engine flying inert mass: ' + a.engine_inert_mass + ' kg'; } } };
%(islev)s
process.stdout.write(JSON.stringify(kuruKutleTanimi(%(arac)s, %(alanS)s)));
""" % {'ym': json.dumps(yuk_m), 'yx': json.dumps(yuk_x), 'alan': json.dumps(str(alan)),
       'ds': json.dumps({'tohumDegeri': str(alan)} if tohum else {}),
       'kip': json.dumps(kip), 'sat': json.dumps({'kalan': kalan} if kalan else None),
       'tn': json.dumps({'satir': [['sd_dry_m', 'final_mass', '25 kg', None]]} if tohum else None),
       'islev': islev, 'arac': json.dumps(arac), 'alanS': json.dumps(alan)}
    out = subprocess.run([NODE, '-'], input=betik, capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_kuru_kutle_tek_tanim_ve_ucan_dokum():
    arac = {'engine_inert_mass': 12.719}
    # Mühendisin adımı: kuru 85, yük 60 @ 0,30, yanmayan 1,694.
    r = _kuru_kutle(arac, 85.0, '60', '0.30', kalan=1.694)
    m = r['metin']
    assert 'The mass in the Payload Mass field is not part of this field' in m
    assert '(airframe, payload' not in m
    assert 'Flown dry mass = this field 85.000 kg + payload 60.000 kg + unburnt propellant 1.694 kg = 146.694 kg.' in m
    assert r['uyari'] is False
    # Yörünge Bitiş Kütlesi'nden tohumlu alan + dolu yük alanı: çift sayım adıyla.
    r2 = _kuru_kutle(arac, 25.0, '5', '0.30', kalan=1.694, tohum=True)
    assert 'counted twice' in r2['metin'] and r2['uyari'] is True
    # Bileşen kipinde yük alanı kullanılmaz: döküm yok.
    r3 = _kuru_kutle(arac, 85.0, '60', '0.30', kip='component')
    assert 'Flown dry mass' not in r3['metin']


@pytest.mark.skipif(NODE is None, reason='node yok')
def test_motordan_gelmeyen_kutle_sifirsa_adiyla():
    r = _kuru_kutle({'engine_inert_mass': 3.42}, 3.42)
    assert 'is the engine alone: nose, body tube, fins and recovery system fly with 0 kg' in r['metin']
    assert r['uyari'] is True
    r2 = _kuru_kutle({'engine_inert_mass': 3.42}, 4.42)
    assert 'engine alone' not in r2['metin']


def test_kuru_kutle_metinleri_iki_dilde_ve_yardim_tanimi():
    for k in ('sixdof.dryMassEngineOnly', 'sixdof.dryMassLedgerAbove', 'sixdof.dryMassFlown',
              'sixdof.dryMassFlownResidual', 'sixdof.dryMassSeededHasPayload'):
        assert I18N_C.count("'" + k + "':") == 2, k
    assert 'NOT including the mass entered in Payload Mass' in I18N_C
    assert 'Faydalı Yük Kütlesi alanına girilen kütle bu alana dahil değildir (koşu onu ayrıca ekler)' in I18N_C
    # Fırlatma Sahası yardım metni 6-DOF alanıyla ilişkiyi söyler (iki dil).
    assert 'that sum is the Dry Mass field of the motor page 6-DOF panel' in I18N_LS
    assert "bu toplam, motor sayfasındaki 6-DOF panelinin Kuru Kütle alanıdır" in I18N_LS


# --- M7-FS-9 --------------------------------------------------------------------

def test_saha_degisimi_ucusu_gecersiz_kilar():
    f = LS[LS.index('function sahaDegistiyseUcusuSil()'):]
    f = f[:f.index('\n    }\n')]
    assert "ucusSonucunuGecersizKil('site_changed');" in f
    # Üç yol: küre seçimi (onSelect), Uygula, kısayol; elle enlem/boylam.
    sec = LS[LS.index('onSelect: function (ll) {'):]
    sec = sec[:sec.index('},')]
    assert 'sahaDegistiyseUcusuSil();' in sec
    uygula = LS[LS.index("el('ls-apply').addEventListener('click'"):]
    uygula = uygula[:uygula.index('});')]
    assert 'sahaDegistiyseUcusuSil();' in uygula
    kisa = LS[LS.index("sel.addEventListener('change', function () {"):]
    kisa = kisa[:kisa.index('});')]
    assert 'sahaDegistiyseUcusuSil();' in kisa
    assert "e.addEventListener('change', sahaDegistiyseUcusuSil);" in LS
    assert I18N_LS.count("'site.siteChangedFlightCleared':") == 2
