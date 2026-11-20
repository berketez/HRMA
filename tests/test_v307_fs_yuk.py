"""V307/FS-YÜK — Fırlatma Sahası'nda faydalı yük (sıvı örnek uçsun).

Sorun (AĞIRLIK-MERKEZİ-2 RAPOR KARAR 2 / DEVİR 1): motor sayfası 6-DOF
panelinde faydalı yük alanları var (sıvı örnek: 120 kg, burun ucundan
0,75 m); Fırlatma Sahası formunda yoktu, sıvı örnek orada 422
``fin_rule_not_met`` ile reddediliyordu.

Ne kilitlenir:
  * Fırlatma Sahası formunda motor sayfasıyla aynı iki alan (EN + TR ipucu,
    i18n iki dilde), istekte ``payload_mass`` / ``payload_station`` ve kuru
    kütleye ekleme; kapı uçta tek (sayfa yalnız ikisinin birlikte olmasını,
    kütle >= 0 ve konum > 0'ı adıyla denetler);
  * kayıtlı proje / proje dosyası: ``/api/flight-vehicle`` belgenin 6-DOF
    kurulumundaki yük alanlarını ``vehicle.payload`` olarak döndürür
    (bileşen kipinde yok; sayı olmayan alan adıyla ``unreadable``);
  * oturum aracı: köprü kaydı panelin yükünü taşır, panel alanı değişince
    kayıt güncellenir;
  * aynı araç (yük girilmiş sıvı örnek) Fırlatma Sahası isteğiyle uçar;
    yük alanları boşken aynı araç adlı ret alır (alan yokkenki davranış).
"""

import contextlib
import io
import json
import pathlib
import re

import pytest

from hrma.analysis import flight_vehicle as fv

KOK = pathlib.Path(__file__).resolve().parents[1]
LS = (KOK / 'hrma' / 'templates' / 'launch_site.html').read_text(encoding='utf-8')
SOZLUK = (KOK / 'hrma' / 'static' / 'js' / 'i18n_launch_site.js').read_text(encoding='utf-8')
KOPRU = (KOK / 'hrma' / 'static' / 'js' / 'flight_handoff.js').read_text(encoding='utf-8')
PANEL = (KOK / 'hrma' / 'static' / 'js' / 'sixdof_panel.js').read_text(encoding='utf-8')
SIVI = KOK / 'examples' / 'Example Liquid LOX-RP1 25kN.hrma'


def _yuklu_sivi_belgesi():
    """Sıvı örnek + üreticinin faydalı yük tohumu (örnek yeniden üretilince
    dosyada olacak değerler; ``examples/generate_examples.py``)."""
    import examples.generate_examples as ge
    belge = json.loads(SIVI.read_text(encoding='utf-8'))
    sd = belge['inputs']['dynamic']['flight']['sixdof']
    sd['fields']['sd_payload_m'] = repr(ge.SIVI_ORNEK_FAYDALI_YUK_KG)
    sd['fields']['sd_payload_x'] = repr(ge.SIVI_ORNEK_FAYDALI_YUK_ISTASYON_M)
    sd['user_typed'] = sorted(set(sd.get('user_typed') or [])
                              | {'sd_payload_m', 'sd_payload_x'})
    return belge, ge


# --- Form ve istek (sayfa kaynağı) -----------------------------------------

@pytest.mark.parametrize('kimlik, anahtar, ipucu', [
    ('ls-a-payloadm', 'site.payloadMass', 'site.help.payloadMass'),
    ('ls-a-payloadx', 'site.payloadStation', 'site.help.payloadStation'),
])
def test_form_alani_etiket_ve_ipucu_iki_dilde(kimlik, anahtar, ipucu):
    blok = re.search(r'<div class="ls-field">((?:(?!<div class="ls-field">).)*?id="%s"[^>]*>)'
                     % kimlik, LS, re.S)
    assert blok, kimlik
    assert 'data-i18n="%s"' % anahtar in blok.group(1)
    assert 'data-i18n="%s"' % ipucu in blok.group(1)
    for k in (anahtar, ipucu):
        assert len(re.findall(r"'%s':" % re.escape(k), SOZLUK)) == 2, k   # EN + TR
    # Motor sayfasıyla aynı etiket (aynı EN -> aynı TR).
    assert "'site.payloadMass': 'Faydalı Yük Kütlesi (kg)'" in SOZLUK
    assert "'site.payloadStation': 'Faydalı Yük Konumu, Burundan (m)'" in SOZLUK


def test_istek_yuku_tasir_ve_kuru_kutleye_ekler():
    assert "payload_mass: fieldNum('ls-a-payloadm')" in LS
    assert "payload_station: fieldNum('ls-a-payloadx')" in LS
    # Kuru kütleye ekleme, boş alan silindikten SONRA ve yalnız sayı varsa.
    sil = LS.index("Object.keys(body).forEach(function (k) { if (body[k] === null) delete body[k]; });")
    ekle = LS.index("if (typeof body.payload_mass === 'number') body.dry_mass = body.dry_mass + body.payload_mass;")
    assert sil < ekle
    # Sonuç sözleşmesi yükü yazar (kuru kütlenin içinde).
    assert re.search(r"payload_mass_kg: \(typeof body\.payload_mass === 'number'\)", LS)


def test_sayfa_kapisi_ikisi_birlikte_ve_aralik():
    gov = LS[LS.index('function ucusReddi(veh)'):]
    gov = gov[:gov.index('\n    }\n')]
    assert "hamAlan('ls-a-payloadm'), yukX = hamAlan('ls-a-payloadx')" in gov
    assert "(yukM === null) !== (yukX === null)" in gov
    assert "yukM !== null && yukM < 0" in gov
    assert "yukX !== null && !(yukX > 0)" in gov
    for k in ('site.payloadPair', 'site.payloadMassNegative', 'site.payloadStationInvalid'):
        assert k in gov and len(re.findall(r"'%s':" % re.escape(k), SOZLUK)) == 2, k


def test_uc_reddi_sayfanin_adli_metniyle_ve_alan_isaretiyle():
    assert "d.error === 'payload_needs_component_cg'" in LS
    assert len(re.findall(r"'site\.payloadNeedsDerivedAirframe':", SOZLUK)) == 2
    assert "payload_mass: 'ls-a-payloadm', payload_station: 'ls-a-payloadx'" in LS
    assert '/^(fin_|parachute_|payload_)/' in LS


def test_alanlar_aracin_yuk_blogundan_dolar_elle_yazilan_korunur():
    assert "{ id: 'ls-a-payloadm', anahtar: 'payload_mass_kg', basamak: null, yuk: true }" in LS
    assert "{ id: 'ls-a-payloadx', anahtar: 'payload_station_m', basamak: null, yuk: true }" in LS
    kur = LS[LS.index('function govdeyiKaynaktanKur(v)'):]
    kur = kur[:kur.index('function renderAirframeNote()')]
    assert 'a.yuk ? (yukKaynagi ? num_(yukKaynagi[a.anahtar]) : null)' in kur
    # Elle yazılan alan (dataset.elle) yük alanında da ezilmez.
    assert kur.index("if (e.dataset.elle === '1')") < kur.index('if (a.yuk && deger !== null) yukDoldu = true;')
    # Oturum aracı: köprü kaydının yükü araca katılır.
    assert 'v = Object.assign({}, v, { payload: doc.payload });' in LS


def test_kopru_kaydi_panelin_yukunu_tasir_ve_esitler():
    assert 'var yuk = panelPayload();' in KOPRU and 'if (yuk) record.payload = yuk;' in KOPRU
    sync = KOPRU[KOPRU.index('function syncPayload()'):]
    sync = sync[:sync.index('\n    }\n')]
    # Yalnız bu sayfanın yazdığı kayıt güncellenir.
    assert 'kayit.saved_at !== buSayfaninKaydi' in sync
    assert 'syncPayload: syncPayload' in KOPRU
    # Panel: bileşen kipinde yük yok; alan değişince köprü eşitlenir.
    yuk = PANEL[PANEL.index('function payloadForFlight()'):]
    yuk = yuk[:yuk.index('\n    }\n')]
    # V307/ONARIM-UÇUŞ (M7-FS-14): bileşen kipinde yük yok (yük alanları null),
    # blok yalnız aracın 6-DOF kurulumunu (Cd₀ + ortam) taşır.
    assert "if (massMode === 'component') return yuksuz();" in yuk
    assert "payload_mass_kg: null, payload_station_m: null" in yuk
    assert 'payloadForFlight: payloadForFlight' in PANEL
    assert "yukEl.addEventListener('input', yukKoprusunuGuncelle);" in PANEL


# --- Uç: belgeden yük ------------------------------------------------------

def test_project_payload_okur_bilesen_kipinde_yok_bozugu_adlandirir():
    belge, ge = _yuklu_sivi_belgesi()
    y = fv.project_payload(belge, 'file')
    assert (y['payload_mass_kg'], y['payload_station_m']) == (
        ge.SIVI_ORNEK_FAYDALI_YUK_KG, ge.SIVI_ORNEK_FAYDALI_YUK_ISTASYON_M)
    assert y['source'] == 'file' and y['unreadable'] == []
    # 3.0.7 örnekleri yeniden üretildi (b867448f6, 19 Kas): gönderilen sıvı örnek
    # artık yükü taşır (üretici SIVI_ORNEK_FAYDALI_YUK_*), proje kaynağı bloğu döner.
    # (Bu satır örnekler üretilmeden önce 'yük yok -> blok yok' diyordu; rc.3 CI
    # dilim 12'de kırmızı.)
    y_ornek = fv.project_payload(json.loads(SIVI.read_text(encoding='utf-8')))
    assert (y_ornek['payload_mass_kg'], y_ornek['payload_station_m']) == (
        ge.SIVI_ORNEK_FAYDALI_YUK_KG, ge.SIVI_ORNEK_FAYDALI_YUK_ISTASYON_M)
    assert y_ornek['source'] == 'project' and y_ornek['unreadable'] == []
    sd = belge['inputs']['dynamic']['flight']['sixdof']
    sd['fields']['sd_payload_x'] = 'abc'
    y = fv.project_payload(belge)
    assert y['payload_station_m'] is None and y['unreadable'] == ['payload_station_m']
    sd['fields']['sd_payload_x'] = True
    assert fv.project_payload(belge)['unreadable'] == ['payload_station_m']
    sd['mass_mode'] = 'component'
    assert fv.project_payload(belge) is None
    for bozuk in (None, 5, {}, {'inputs': {'dynamic': {'flight': 'x'}}},
                  {'inputs': {'dynamic': {'flight': {'sixdof': {'fields': []}}}}}):
        assert fv.project_payload(bozuk) is None


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def dosya_araci(client):
    belge, ge = _yuklu_sivi_belgesi()
    with contextlib.redirect_stdout(io.StringIO()):
        r = client.post('/api/flight-vehicle', json={
            'source': 'file', 'file_name': 'Ornek Sivi Yuklu.hrma',
            'document_text': json.dumps(belge)})
    assert r.status_code == 200, r.get_json()
    return r.get_json()['vehicle'], ge


def test_dosya_kaynagi_yuk_blogunu_dondurur(dosya_araci):
    arac, ge = dosya_araci
    assert arac['payload']['payload_mass_kg'] == ge.SIVI_ORNEK_FAYDALI_YUK_KG
    assert arac['payload']['payload_station_m'] == ge.SIVI_ORNEK_FAYDALI_YUK_ISTASYON_M
    assert arac['payload']['source'] == 'file'
    # Gövde motordan türetilir: yerleşim var (yük bileşen ağırlık merkezine konur).
    assert arac['airframe_resolved']['source'] == 'derived'
    assert arac['airframe_resolved']['mass_layout'] is not None


def _ls_sabit():
    """Sayfanın sabit gövde nesnesi (``LS_FIXED_AIRFRAME``), şablondan."""
    blok = re.search(r'var LS_FIXED_AIRFRAME = \{(.*?)\};', LS, re.S).group(1)
    out = {}
    for ad, deger in re.findall(r"(\w+):\s*([^,\n]+)", blok):
        deger = deger.strip().strip("'")
        try:
            out[ad] = float(deger)
        except ValueError:
            out[ad] = deger
    return out


def _ls_form(kimlik):
    """Form alanının şablondaki varsayılanı (sayı teste kopyalanmaz)."""
    return float(re.search(r'id="%s"[^>]*value="([^"]+)"' % kimlik, LS).group(1))


def _fs_istegi(arac, yuk):
    """launch_site.html'in kurduğu istek (gövde kuru 0 kg: kuru = motorun uçan
    atıl kütlesi [+ yük], motor sayfası paneliyle aynı araç; rüzgâr 0,
    sayfa varsayılanları, çalkantı bloğu yok)."""
    ucus = arac['flight_thrust']
    af = arac['airframe_resolved']
    sabit = _ls_sabit()
    boy = (sabit['nose_length'] + af['length_behind_nose_m']
           if af.get('body_length_m') is None else af['body_length_m'])
    g = {'body_diameter': float('%.3f' % af['body_diameter_m']),
         'body_length': float('%.2f' % boy), 'nose_length': sabit['nose_length'],
         'nose_type': sabit['nose_type'],
         'dry_mass': arac['engine_inert_mass'] + (ucus.get('propellant_residual_kg') or 0.0),
         'propellant_mass': ucus['propellant_consumed_kg'],
         'nozzle_exit_area': ucus['nozzle_exit_area_m2'],
         'thrust_reference_pressure': ucus['thrust_reference_pressure_pa'],
         'thrust': arac['thrust'], 'burn_time': arac['burn_time'],
         'thrust_curve': arac['thrust_curve'], 'cd0': _ls_form('ls-a-cd0'),
         'fin_count': _ls_form('ls-a-fincount'),
         'fin_geometry_rule': 'static_margin',
         'launch_elevation_deg': _ls_form('ls-a-elev'),
         'launch_azimuth_deg': _ls_form('ls-a-azim'), 'rail_length': sabit['rail_length'],
         'wind_speed': _ls_form('ls-a-windspeed'),
         'wind_direction_deg': _ls_form('ls-a-winddir'), 't_max': 400,
         'descent_model': 'ballistic',
         'engine_od_m': arac['engine_od_m'], 'engine_length_m': arac['engine_length_m'],
         'propellant_volume_m3': arac['propellant_volume_m3'],
         'mass_layout': af['mass_layout']}
    if yuk:
        p = arac['payload']
        g['payload_mass'] = p['payload_mass_kg']
        g['payload_station'] = p['payload_station_m']
        g['dry_mass'] += p['payload_mass_kg']
    return {k: v for k, v in g.items() if v is not None}


def test_sivi_ornek_yukle_firlatma_sahasinda_ucar_yuksuz_adli_ret(client, dosya_araci):
    arac, ge = dosya_araci
    with contextlib.redirect_stdout(io.StringIO()):
        r = client.post('/api/six-dof-analysis', json=_fs_istegi(arac, yuk=True))
    assert r.status_code == 200, r.get_json()
    y = r.get_json()
    s, sb = y['summary'], y['stability_basis']
    assert sb['x_cg_source'] == 'components'
    assert sb['x_cg_components']['payload']['mass_kg'] == ge.SIVI_ORNEK_FAYDALI_YUK_KG
    assert s['static_margin_full'] > 1.5 and s['static_margin_empty'] > 1.5
    assert s['stable'] is True
    with contextlib.redirect_stdout(io.StringIO()):
        r = client.post('/api/six-dof-analysis', json=_fs_istegi(arac, yuk=False))
    assert r.status_code == 422 and r.get_json()['error'] == 'fin_rule_not_met'
