"""V307/ONARIM2-UÇUŞ-ARAÇ (20 Kas 2026) — araç girdisi, kanatçık ve saha
seçimi bekçileri (mühendis turu dalga 2).

Kanıt ve önce/sonra ölçümleri: ``docs/scofield/raw/OH/V307/onarim2-ucus-arac/``.
"""
import contextlib
import io
import json
import math
import pathlib
import re
import shutil
import subprocess
import warnings

import pytest

KOK = pathlib.Path(__file__).resolve().parent.parent
HOST = {'Host': '127.0.0.1:8080'}
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _ornek(ad):
    yol = KOK / 'examples' / ad
    return json.loads(yol.read_text(encoding='utf-8'))


# ===========================================================================
# M7-FS-8 — hesaplanan oran "ölçülen" diye yazılmaz
# ===========================================================================
def test_fs8_hibrit_kunyesi_hesaplanan_oran():
    from hrma.analysis.flight_vehicle import _hybrid_inert_note
    m = _hybrid_inert_note(12.72, 15.0, None)
    assert '; computed dry/propellant ratio 0.85' in m
    assert 'measured' not in m


@node_gerekli
def test_fs8_tr_ekranda_hesaplanan():
    from tests.test_v3_kucuk import _sunucu_metni
    from hrma.analysis.flight_vehicle import _hybrid_inert_note
    m = _hybrid_inert_note(12.72, 15.0, None)
    t = _sunucu_metni([m])[0]
    assert 'hesaplanan kuru/itici oranı 0,85' in t and 'ölçülen' not in t


def test_fs8_tr_deseni_hesaplanan():
    kaynak = (KOK / 'hrma/static/js/i18n_charts.js').read_text(encoding='utf-8')
    assert "'; hesaplanan kuru/itici oranı '" in kaynak
    assert 'ölçülen kuru/itici' not in kaynak
    assert 'measured dry\\/propellant' not in kaynak


# ===========================================================================
# İTKİ-A DEVİR — hibrit sayfa aynası tasarım irtifasını geçirir
# ===========================================================================
def _sayfa_basinci(h):
    """Sayfanın tek irtifa kipi: geometrik irtifa → ISA → toFixed(6)."""
    from hrma.constants import isa_pressure_geometric
    return float('%.6f' % (isa_pressure_geometric(h) / 1e5))


def test_itki_devir_ayna_irtifayi_gecirir():
    from hrma.analysis.flight_vehicle import page_payload
    alanlar = dict(_ornek('Example Hybrid N2O-HTPB 3kN.hrma')['inputs']['fields'])
    alanlar['single_altitude'] = 10000
    alanlar['single_pressure'] = _sayfa_basinci(10000.0)
    y = page_payload('hybrid', alanlar)
    assert y['design_ambient_altitude_m'] == 10000
    assert y['atmospheric_pressure'] == _sayfa_basinci(10000.0)
    # Sayı olmayan irtifa aynaya girmez (sayfa da göndermez).
    alanlar['single_altitude'] = ''
    assert 'design_ambient_altitude_m' not in page_payload('hybrid', alanlar)


@pytest.mark.slow
def test_itki_devir_kayitli_proje_irtifa_adiyla(client):
    from hrma.analysis import flight_vehicle as fv
    alanlar = dict(_ornek('Example Hybrid N2O-HTPB 3kN.hrma')['inputs']['fields'])
    alanlar['single_altitude'] = 10000
    alanlar['single_pressure'] = _sayfa_basinci(10000.0)
    durum, govde = _sessiz(fv.run_page_calculation, 'hybrid',
                           fv.page_payload('hybrid', alanlar))
    assert durum == 200
    da = govde['motor']['design_ambient']
    assert da['mode'] == 'altitude' and da['source'] == 'altitude_isa'
    assert da['altitude_m'] == 10000.0


# ===========================================================================
# M7-UCUS-7 — 0 kg faydalı yük = yük yok (konum istenmez), iki sayfa aynı
# ===========================================================================
PANEL = (KOK / 'hrma/static/js/sixdof_panel.js').read_text(encoding='utf-8')
SAHA = (KOK / 'hrma/templates/launch_site.html').read_text(encoding='utf-8')


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


def _node(betik):
    out = subprocess.run([NODE, '-'], input=betik, capture_output=True,
                         text=True, timeout=30)
    assert out.returncode == 0, out.stderr[:800]
    return json.loads(out.stdout)


@node_gerekli
def test_ucus7_sifir_kg_yuk_yok():
    islev = _js_islevi(PANEL, 'faydaliYukSifir')
    sonuc = _node(islev + """
process.stdout.write(JSON.stringify(['0', ' 0 ', '0.0', '', '0.5', 'abc'].map(
    function (v) { return faydaliYukSifir({ value: v }); })));""")
    assert sonuc == [True, True, True, False, False, False]


def test_ucus7_panel_denetimi_ve_istek_sifiri_tanir():
    # Çift denetimi ve istek kurucusu aynı yardımcıyı çağırır.
    a = PANEL.index("errors.push(T('sixdof.errPayloadPair'")
    assert 'faydaliYukSifir(ym)' in PANEL[a - 400:a]
    b = PANEL.index('payload.payload_mass = num(')
    assert 'faydaliYukSifir(yukM)' in PANEL[b - 300:b]


def test_ucus7_firlatma_sahasi_ayni_kural():
    a = SAHA.index("return t('site.payloadPair'")
    assert 'yukM !== 0 && (yukM === null) !== (yukX === null)' in SAHA[a - 500:a]
    assert 'if (body.payload_mass === 0) { delete body.payload_mass; ' \
           'delete body.payload_station; }' in SAHA


def test_ucus7_iletiler_iki_dilde_sifiri_soyler():
    ortak = (KOK / 'hrma/static/js/i18n_common.js').read_text(encoding='utf-8')
    saha = (KOK / 'hrma/static/js/i18n_launch_site.js').read_text(encoding='utf-8')
    assert 'a Payload Mass of 0 kg means no payload and needs no station' in ortak
    assert '0 kg Faydalı Yük Kütlesi yük yok demektir, konum gerekmez' in ortak
    assert 'a payload mass of 0 kg means no payload and needs no station' in saha
    assert '0 kg faydalı yük kütlesi yük yok demektir, konum gerekmez' in saha


# ===========================================================================
# M7-CALK-15 (ikinci yarı) — yüklenen tank gövdeye girer
# ===========================================================================
GENIS = [[0.0, 0.0], [0.3, 0.0], [0.3, 0.8], [0.0, 0.8]]
DAR = [[0.0, 0.0], [0.2, 0.0], [0.2, 1.6577], [0.0, 1.6577]]


@pytest.fixture(scope='module')
def sivi():
    from hrma.app import app  # noqa: F401  (uç kayıtları)
    from hrma.analysis import flight_vehicle as fv
    doc = _ornek('Example Liquid LOX-RP1 25kN.hrma')
    durum, govde = _sessiz(fv.run_page_calculation, 'liquid',
                           fv.page_payload('liquid', doc['inputs']['fields']))
    assert durum == 200
    return govde


def _panel_istegi(arac, sonuc, tg, ruzgar=5):
    """Motor sayfası 6-DOF panelinin isteği: alanlar türetilmiş gövdenin
    alan çözünürlüğünde, kütle yerleşimi, örneğin 6-DOF kurulumu (faydalı
    yük 120 kg @ 0,75 m; kuru kütle alanı 143,346 kg + yük)."""
    g = arac['airframe_resolved']
    u = arac['flight_thrust']
    b = {'body_diameter': round(g['body_diameter_m'], 3),
         'body_length': round(g['nose_length_m'] + g['length_behind_nose_m'], 2),
         'nose_length': g['nose_length_m'], 'nose_type': g['nose_type'],
         'fin_count': 4, 'fin_geometry_rule': 'static_margin', 'cd0': 0.45,
         'wind_speed': ruzgar, 'wind_direction_deg': 0,
         'launch_elevation_deg': 90, 'launch_azimuth_deg': 0, 'rail_length': 5,
         'dry_mass': 143.346 + 120.0, 'payload_mass': 120.0,
         'payload_station': 0.75,
         'propellant_mass': round(u['propellant_consumed_kg'], 3),
         'thrust_curve': arac['thrust_curve'],
         'thrust': None if arac['thrust_curve'] else arac['thrust'],
         'burn_time': None if arac['thrust_curve'] else arac['burn_time'],
         'nozzle_exit_area': u['nozzle_exit_area_m2'],
         'thrust_reference_pressure': u['thrust_reference_pressure_pa'],
         'engine_od_m': arac['engine_od_m'],
         'engine_length_m': arac['engine_length_m'],
         'mass_layout': g['mass_layout'],
         'calkanti': {'motor_type': 'liquid', 'motor_sonucu': sonuc,
                      'arac_duzeni': {'ardisik': {}}}}
    if tg:
        b['calkanti']['tank_geometrileri'] = tg
    return {k: v for k, v in b.items() if v is not None}


def test_calk15_gove_yuklenen_tanktan_turer(sivi):
    from hrma.analysis import flight_vehicle as fv
    arac = fv.normalize('liquid', sivi)
    ox = next(t for t in arac['propellant_tanks'] if t['key'] == 'oxidizer_tank')
    y = fv.vehicle_with_loaded_tanks(
        'liquid', sivi, arac, {'oksitleyici': {'profil_rz_m': GENIS}})
    g = y['airframe_resolved']
    assert g['loaded_tanks'] == ['oxidizer_tank']
    # Dış çap = yüklenen iç çap 0,600 + 2 × motorun cidarı, 1 mm'ye yukarı.
    beklenen = math.ceil((0.6 + 2 * ox['wall_thickness_m']) * 1000 - 1e-9) / 1000
    assert g['body_diameter_m'] == pytest.approx(beklenen, abs=1e-12)
    assert g['body_diameter_m'] == pytest.approx(0.606, abs=1e-12)
    # Dizilim yüklenen iç boyla (0,800 m) kurulur; kaynak araç değişmez.
    st = {s['key']: s for s in g['tank_stations']}
    ic = st['oxidizer_tank']['base_behind_nose_m'] - st['oxidizer_tank']['top_behind_nose_m']
    assert ic == pytest.approx(0.8, abs=1e-12)
    assert arac['airframe_resolved']['body_diameter_m'] == pytest.approx(0.48)
    sutun = next(p for p in g['mass_layout']['propellant']
                 if p['key'] == 'oxidizer_tank')
    assert sutun['inner_profile_rz_m'] == GENIS
    assert sutun['inner_diameter_m'] == pytest.approx(0.6)


def test_calk15_arac_disi_tank_adiyla_reddedilir(sivi):
    from hrma.analysis import flight_vehicle as fv
    arac = fv.normalize('liquid', sivi)
    with pytest.raises(fv.LoadedTankRejected) as e:
        fv.vehicle_with_loaded_tanks('liquid', sivi, arac,
                                     {'n2o': {'profil_rz_m': GENIS}})
    assert e.value.code == 'LOADED_TANK_NOT_IN_VEHICLE'


def test_calk15_ucus_araci_ucu_yuklenen_tankla(client, sivi):
    r = _sessiz(client.post, '/api/flight-vehicle', headers=HOST, json={
        'source': 'results', 'motor_type': 'liquid', 'results': sivi,
        'tank_geometrileri': {'oksitleyici': {'profil_rz_m': DAR}}})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    v = r.get_json()
    v = v.get('vehicle', v)
    assert v['airframe_resolved']['loaded_tanks'] == ['oxidizer_tank']
    assert v['airframe_resolved']['body_diameter_m'] == pytest.approx(0.435)
    r = _sessiz(client.post, '/api/flight-vehicle', headers=HOST, json={
        'source': 'project', 'name': 'x',
        'tank_geometrileri': {'oksitleyici': {'profil_rz_m': DAR}}})
    assert r.status_code == 400
    assert r.get_json()['field'] == 'tank_geometrileri'


@pytest.mark.slow
@pytest.mark.parametrize('profil', [GENIS, DAR], ids=['genis', 'dar'])
def test_calk15_yuklenen_tank_baglanir_hukum_gercek_tarama(client, sivi, profil):
    """Mühendis adımı: sıvı örnek + yüklenen oksitleyici tankı → 6-DOF.
    ÖNCE: tank düşüyor (TANK_GOVDEDEN_GENIS / TANK_BURUN_ICINDE), hüküm
    tank olmadan. SONRA: iki tank da bağlı, hüküm taramanın kendisi."""
    from hrma.analysis import flight_vehicle as fv
    tg = {'oksitleyici': {'profil_rz_m': profil}}
    arac = fv.vehicle_with_loaded_tanks('liquid', sivi,
                                        fv.normalize('liquid', sivi), tg)
    r = _sessiz(client.post, '/api/six-dof-analysis', headers=HOST,
                json=_panel_istegi(arac, sivi, tg))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    c = r.get_json()['calkanti']
    assert c['durum'] == 'BAGLANDI'
    assert {t['tank_id']: t['durum'] for t in c['tanklar']} == {
        'oksitleyici': 'BAGLANDI', 'yakit': 'BAGLANDI'}
    st = c['slosh_stability']
    assert 'baglanmayan_tanklar' not in st
    assert st['genel_hukum'] == 'CALKANTI_KAYNAKLI_KARARSIZLIK'
    assert any(p.get('mod') == 'calkanti' and p.get('tank_id') == 'oksitleyici'
               for p in st['pencereler'])


@pytest.mark.slow
@pytest.mark.parametrize('profil,kod', [(GENIS, 'TANK_GOVDEDEN_GENIS'),
                                        (DAR, 'TANK_BURUN_ICINDE')],
                         ids=['genis', 'dar'])
def test_calk15_elle_gove_sigmayan_yuklenen_tank_adli_ret(client, sivi, profil,
                                                           kod):
    """Gövde motorun tankından (kullanıcının yazdığı gibi) kalırsa yüklenen
    tank sığmaz: koşu adıyla reddedilir (sessizce düşülmez)."""
    from hrma.analysis import flight_vehicle as fv
    tg = {'oksitleyici': {'profil_rz_m': profil}}
    arac = fv.normalize('liquid', sivi)
    r = _sessiz(client.post, '/api/six-dof-analysis', headers=HOST,
                json=_panel_istegi(arac, sivi, tg))
    assert r.status_code == 422, r.get_data(as_text=True)[:300]
    y = r.get_json()
    assert y['error'] == 'loaded_tank_does_not_fit_airframe'
    assert y['invalid_fields'][0]['tank_id'] == 'oksitleyici'
    assert y['invalid_fields'][0]['reason'] == kod


def test_calk15_panel_kosudan_once_govdeyi_yuklenen_tankla_kurar():
    a = PANEL.index('async function run()')
    b = PANEL.index('const check = validateAll(', a)
    govde = PANEL[a:b]
    assert 'await yuklenenTankliAraci(kosuSonucu)' in govde
    assert 'tankliGovdeyiKur(tankliGovde(yt.arac))' in govde
    islev = _js_islevi(PANEL, 'yuklenenTankliAraci')
    assert "'/api/flight-vehicle'" in islev and 'tank_geometrileri' in islev
    assert "['sd_body_d', 'sd_body_l', 'sd_nose_l'].some(alanElleYazildi)" in islev
    assert 'yuklenenTankAraci ||' in _js_islevi(PANEL, 'bilesenYerlesimi')
    assert "data.error === 'loaded_tank_does_not_fit_airframe'" in PANEL


def test_calk15_metinler_iki_dilde():
    ortak = (KOK / 'hrma/static/js/i18n_common.js').read_text(encoding='utf-8')
    for k in ('sixdof.errLoadedTankAirframe', 'sixdof.errLoadedTankAirframeUnknown',
              'sixdof.errLoadedTankFit', 'sixdof.errLoadedTankFit.TANK_GOVDEDEN_GENIS',
              'sixdof.errLoadedTankFit.TANK_BURUN_ICINDE',
              'sixdof.errLoadedTankFit.TANK_ARAC_DISI',
              'sixdof.errLoadedTankFit.TANKLAR_CAKISIYOR',
              'sixdof.seed.bodyLoadedTank'):
        assert ortak.count("'%s':" % k) == 2, k


@node_gerekli
@pytest.mark.parametrize('dosya', ['sixdof_panel.js', 'i18n_common.js',
                                   'i18n_launch_site.js', 'i18n_charts.js'])
def test_degisen_js_sozdizimi(dosya):
    r = subprocess.run([NODE, '--check', str(KOK / 'hrma/static/js' / dosya)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:400]


# ===========================================================================
# M7-UCUS-11 — kanat rüzgârsız referans uçuştan boyutlanır
# ===========================================================================
def _kanat(y):
    return y['fin_geometry']['fields']['fin_span']['value']


@pytest.mark.slow
def test_ucus11_ayni_aracta_ruzgar_kanadi_degistirmez(client, sivi):
    """Mühendis adımı: sıvı örnek, rüzgâr 5 ⟷ 0 m/s. ÖNCE 0,970 ⟷ 0,983 m."""
    from hrma.analysis import flight_vehicle as fv
    arac = fv.normalize('liquid', sivi)
    sonuc = {}
    for w in (0, 5):
        r = _sessiz(client.post, '/api/six-dof-analysis', headers=HOST,
                    json=_panel_istegi(arac, sivi, None, ruzgar=w))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        sonuc[w] = r.get_json()
    assert _kanat(sonuc[0]) == _kanat(sonuc[5])
    fg5 = sonuc[5]['fin_geometry']
    assert fg5['sizing']['reference_flight']['wind_speed_mps'] == 0.0
    assert fg5['sizing']['final_flight']['wind_speed_mps'] == 5.0
    # Nottaki en düşük marj referans aralığında ölçütü sağlar (hedef ya da
    # 4·d içinde sağlanamadıysa eşik; adıyla).
    assert fg5['min_margin_over_reference_mach_range_cal'] >= \
        fg5['criterion']['target_used_cal'] - 1e-9
    # Rüzgâr yalnız uçuşu etkiler: yayımlanan uçuşlar farklı.
    assert fg5['sizing']['final_flight']['flight_max_mach'] != \
        sonuc[0]['fin_geometry']['sizing']['final_flight']['flight_max_mach']


def test_ucus11_kural_metni_iki_dilde_referans_ucusu_soyler():
    ortak = (KOK / 'hrma/static/js/i18n_common.js').read_text(encoding='utf-8')
    saha = (KOK / 'hrma/static/js/i18n_launch_site.js').read_text(encoding='utf-8')
    assert ortak.count('Mach range of the windless reference flight') == 2
    assert ortak.count('rüzgârsız referans uçuşun Mach aralığında') == 2
    assert 'over the windless reference flight at least {target}' in saha
    assert 'rüzgârsız referans uçuş boyunca en düşük statik marj' in saha
    assert 'highest Mach of the windless reference flight' in saha
    assert 'rüzgârsız referans uçuşun (rüzgâr hızı 0' in saha
    assert 'min_margin_over_reference_mach_range_cal' in PANEL


# ===========================================================================
# M7-UCUS-18 — bileşen tablosu motordan; ret iletisi iç alan yolu taşımaz
# ===========================================================================
def _tablo_cg(satirlar):
    m = sum(r[0] for r in satirlar)
    mk = sum(r[0] for r in satirlar if not r[2])
    return (sum(r[0] * r[1] for r in satirlar) / m,
            sum(r[0] * r[1] for r in satirlar if not r[2]) / mk)


@pytest.mark.parametrize('mt', ['liquid', 'hybrid', 'solid'])
def test_ucus18_tablo_satirlari_bilesen_agirlik_merkezini_verir(mt):
    """Motordan tohumlanan tablo (+ gövde L/2, faydalı yük) bileşen ağırlık
    merkeziyle aynı dolu ve boş ağırlık merkezini verir."""
    from hrma.app import app  # noqa: F401
    from hrma.analysis import flight_vehicle as fv
    ad = {'liquid': 'Example Liquid LOX-RP1 25kN.hrma',
          'hybrid': 'Example Hybrid N2O-HTPB 3kN.hrma',
          'solid': 'Example Solid KNDX BATES 75mm.hrma'}[mt]
    doc = _ornek(ad)
    durum, sonuc = _sessiz(fv.run_page_calculation, mt,
                           fv.page_payload(mt, doc['inputs']['fields']))
    assert durum == 200
    arac = fv.normalize(mt, sonuc)
    g = arac['airframe_resolved']
    rows = g['component_rows']
    assert rows and g['component_rows_not_built'] is None
    L = g['nose_length_m'] + g['length_behind_nose_m']
    kuru_motor = sum(r['mass_kg'] for r in rows if not r['propellant'])
    yanan = sum(r['mass_kg'] for r in rows if r['propellant'])
    ek, yuk = 7.5, (20.0, 0.4 * L)
    kuru = kuru_motor + ek + yuk[0]
    cg = fv.component_cg(g['mass_layout'], L, kuru, yanan,
                         payload_mass_kg=yuk[0], payload_station_m=yuk[1])
    tablo = [(r['mass_kg'], L - r['x_from_tail_m'], r['propellant']) for r in rows]
    tablo += [(ek, 0.5 * L, False), (yuk[0], yuk[1], False)]
    dolu, bos = _tablo_cg(tablo)
    # component_cg burun ucundan yazar (tablo gibi).
    assert dolu == pytest.approx(cg['x_cg_full_m'], abs=1e-9)
    assert bos == pytest.approx(cg['x_cg_empty_m'], abs=1e-9)


@node_gerekli
def test_ucus18_panel_tablosu_motordan_ve_sozlukten():
    a = PANEL.index('const BILESEN_ADLARI = {')
    sabit = PANEL[a:PANEL.index('};', a) + 2]
    islevler = (sabit + '\n' + _js_islevi(PANEL, 'bilesenAdi') + '\n'
                + _js_islevi(PANEL, 'defaultComponents'))
    betik = """
var TR = { 'sixdof.comp.engine_dry': 'Motor kuru kütlesi',
           'sixdof.comp.oxidizer_tank': 'Oksitleyici (yanan)',
           'sixdof.comp.oxidizer_tank.residual': 'Tankta kalan oksitleyici',
           'sixdof.comp.airframe': 'Gövde yapısı', 'sixdof.comp.payload': 'Faydalı yük' };
function T(k, fb) { return TR[k] || fb; }
function TF(k, p, fb) { return T(k, fb).replace(/\\{(\\w+)\\}/g, function (_, a) { return p[a]; }); }
var ELS = { sd_body_l: { value: '3.00' }, sd_dry_m: { value: '50' },
            sd_payload_m: { value: '10' }, sd_payload_x: { value: '0.6' } };
function $(id) { return ELS[id] || null; }
var yuklenenTankAraci = null;
var window = { currentResults: {}, FlightHandoff: { vehicleFor: function () { return {
    flight_thrust: { propellant_residual_kg: 0 },
    airframe_resolved: { component_rows: [
        { key: 'engine_dry', mass_kg: 20, x_from_tail_m: 0.3, propellant: false },
        { key: 'oxidizer_tank', mass_kg: 30, x_from_tail_m: 1.0, propellant: true },
        { key: 'oxidizer_tank.residual', mass_kg: 5, x_from_tail_m: 0.8, propellant: false } ] } }; } } };
var FlightHandoff = window.FlightHandoff;
%s
process.stdout.write(JSON.stringify(defaultComponents()));
""" % islevler
    satirlar = _node(betik)
    assert [s['name'] for s in satirlar] == [
        'Motor kuru kütlesi', 'Oksitleyici (yanan)',
        'Tankta kalan oksitleyici', 'Gövde yapısı', 'Faydalı yük']
    assert [s['mass'] for s in satirlar] == [20, 30, 5, 25, 10]
    assert [s['x'] for s in satirlar] == [2.7, 2.0, 2.2, 1.5, 0.6]
    assert [s['propellant'] for s in satirlar] == [False, True, False, False, False]
    # Kütle yuvarlanmaz (yanan satırların toplamı motorunkine eşit kalsın).
    assert 'mass: yuv6(Number(r.mass_kg))' in PANEL
    # Eski sabit oyuncak satırları kodda yok.
    assert "mass: 0.5, x: 0.20" not in PANEL


@pytest.mark.slow
def test_ucus18_ret_iletisi_ic_alan_yolu_tasimaz(client, sivi):
    """Mühendisin adımı: bileşen kipinde 12 kg araç + sıvı motorun tankları."""
    from hrma.analysis import flight_vehicle as fv
    arac = fv.normalize('liquid', sivi)
    b = _panel_istegi(arac, sivi, None)
    for k in ('mass_layout', 'payload_mass', 'payload_station'):
        b.pop(k, None)
    b.update(dry_mass=8.0, propellant_mass=4.0, x_cg_full=1.471, x_cg_empty=1.431)
    r = _sessiz(client.post, '/api/six-dof-analysis', headers=HOST, json=b)
    assert r.status_code == 422, r.get_data(as_text=True)[:300]
    y = r.get_json()
    assert y['error'] == 'slosh_coupling_rejected'
    assert 'slosh_tanks[' not in y['message']
    f = y['invalid_fields'][0]
    assert f['reason'] == 'KUTLE_TUTARSIZ'
    assert f['tank_id'] == 'oksitleyici'
    assert f['tank_kg'] == pytest.approx(225.825, abs=1e-3)
    assert f['vehicle_kg'] == pytest.approx(12.0)


def test_ucus18_panel_ret_metni_sozlukten_iki_dilde():
    ortak = (KOK / 'hrma/static/js/i18n_common.js').read_text(encoding='utf-8')
    assert ortak.count("'sixdof.errSloshTankMass':") == 2
    for k in ('engine_dry', 'engine_dry_estimate', 'tank_structure.oxidizer_tank',
              'tank_structure.fuel_tank', 'oxidizer_tank', 'fuel_tank',
              'fuel_grain', 'propellant_grain', 'oxidizer_tank.residual',
              'fuel_tank.residual', 'fuel_grain.residual',
              'propellant_grain.residual', 'airframe', 'payload'):
        assert ortak.count("'sixdof.comp.%s':" % k) == 2, k
    assert "sk.reason === 'KUTLE_TUTARSIZ'" in PANEL
    assert 'sayiEkran(sk.tank_kg, 3)' in PANEL


# ===========================================================================
# M7-FS-13 — kısayol seçimi sahayı çözer; çözülmeden uçulmaz
# ===========================================================================
@node_gerekli
def test_fs13_rakim_cozuldugu_koordinata_ait():
    islevler = '\n'.join(_js_islevi(SAHA, ad) for ad in (
        'ayniNokta', 'sahaRakimi', 'kisayolCozulmedi'))
    betik = """
var ALAN = { 'ls-lat': { value: '27.9881' }, 'ls-lon': { value: '86.9250' } };
function el(id) { return ALAN[id]; }
var cozulenSaha = null, kisayolSahasi = { lat: 27.9881, lon: 86.925 };
%s
var out = [];
out.push([kisayolCozulmedi(), sahaRakimi()]);              // kısayol, çözülmedi
cozulenSaha = { lat: 27.9881, lon: 86.925, elev: 6529 };
out.push([kisayolCozulmedi(), sahaRakimi()]);              // çözüldü
ALAN['ls-lat'].value = '37.8746'; ALAN['ls-lon'].value = '32.4932';
out.push([kisayolCozulmedi(), sahaRakimi()]);              // elle başka nokta
process.stdout.write(JSON.stringify(out));
""" % islevler
    assert _node(betik) == [[True, None], [False, 6529], [False, None]]


def test_fs13_kisayol_cozumu_tetikler_ve_ucus_adiyla_bekler():
    a = SAHA.index("sel.addEventListener('change', function () {")
    b = SAHA.index('})();', a)
    assert 'sahayiCoz();' in SAHA[a:b]
    assert "el('ls-resolve').addEventListener('click', function () { sahayiCoz(); });" in SAHA
    assert 'var red = kisayolCozulmedi()' in SAHA
    a = SAHA.index('var red = kisayolCozulmedi()')
    assert "t('site.resolveShortcutFirst'" in SAHA[a:a + 300]
    assert ': ucusReddi(veh);' in SAHA[a:a + 600]
    assert 'var siteAltM = sahaRakimi();' in SAHA
    saha = (KOK / 'hrma/static/js/i18n_launch_site.js').read_text(encoding='utf-8')
    assert saha.count("'site.resolveShortcutFirst':") == 2


# ===========================================================================
# M7-FS-2 — kısayol adı paket adıyla tek kaynaktan, dile göre
# ===========================================================================
def _paket_adlari():
    kaynak = (KOK / 'hrma/static/js/i18n_launch_site.js').read_text(encoding='utf-8')
    bulunan = re.findall(r"'site\.mapPackName\.([a-z0-9_]+)': '((?:[^'\\]|\\.)*)'", kaynak)
    en, tr = {}, {}
    for k, v in bulunan:
        (tr if k in en else en)[k] = v
    return en, tr


@node_gerekli
@pytest.mark.parametrize('dil', ['en', 'tr'])
def test_fs2_kisayol_ve_paket_ayni_ad(dil):
    from hrma.analysis.launch_site import LAUNCH_SITE_PRESETS
    en, tr = _paket_adlari()
    sozluk = {('site.mapPackName.' + k): v for k, v in (en if dil == 'en' else tr).items()}
    betik = """
var S = %s;
function t(k, fb) { return S.hasOwnProperty(k) ? S[k] : fb; }
%s
process.stdout.write(JSON.stringify(%s.map(function (p) { return presetLabel(p); })));
""" % (json.dumps(sozluk, ensure_ascii=False), _js_islevi(SAHA, 'presetLabel'),
       json.dumps([dict(p, approx=False) for p in LAUNCH_SITE_PRESETS]))
    etiketler = _node(betik)
    for p, e in zip(LAUNCH_SITE_PRESETS, etiketler):
        assert e == sozluk['site.mapPackName.' + p['id']], (p['id'], e)
    if dil == 'tr':
        assert 'Andøya Uzay Üssü' in etiketler and 'Andoya Space' not in etiketler
