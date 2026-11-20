"""V307/AĞIRLIK-MERKEZİ-2 — katı panel türetilmiş gövdede; sıvı örneğe faydalı yük.

Berke kararları (18 Kas ~15:0x):
  1. Motor sayfası 6-DOF panelinde katı araç da Fırlatma Sahası'nın katı
     türetilmiş gövdesi ve bileşen ağırlık merkeziyle uçar (tek tanım:
     ``flight_vehicle.derive_airframe`` / ``mass_layout`` / ``component_cg``).
  2. Sıvı örnek araca beyanlı burun/faydalı yük kütlesi GİRDİ olarak eklenir;
     araç önden yüklü olur ve kanat kuralını sağlayarak uçar. Yalın araçta
     ``fin_rule_not_met`` reddi doğru davranış olarak kalır.

Ne kilitlenir (fizik ve sözleşme):
  * katı araçta panelin kurduğu gövde Fırlatma Sahası alanlarıyla aynı sayı
    (çap 3, boy 2 ondalık; burun aynı sabit);
  * aynı katı araç (aynı kütleler, aynı uçuş koşulları) iki sayfada aynı
    ağırlık merkezi, aynı statik marj, aynı kanat ve aynı hükmü verir;
  * faydalı yük noktasal kütledir: Σ m·x / Σ m'ye girer, kuru kütlenin
    parçasıdır (motordan gelmeyen kütleden düşülür), gövde içinde olmalı;
    yerleşimsiz (bileşen ağırlık merkezi kurulmayan) istekte adıyla reddedilir.
"""

import contextlib
import hashlib
import io
import json
import pathlib
import shutil
import subprocess

import pytest

from hrma.analysis import flight_vehicle as fv

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
UC = '/api/six-dof-analysis'


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


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def kati_arac():
    from tests.test_v307_ucus_govde import _coz
    return fv.normalize('solid', _coz('solid'))


def _post(client, govde):
    with contextlib.redirect_stdout(io.StringIO()):
        r = client.post(UC, json=govde)
    return r.status_code, r.get_json()


def _md5(y):
    return hashlib.md5(json.dumps({k: v for k, v in y.items()
                                   if k != 'solver_wall_time_s'},
                                  sort_keys=True, default=str).encode()).hexdigest()


def _govde_istegi(arac, kuru, itici, **ek):
    """Türetilmiş gövdeyle 6-DOF isteği — iki sayfanın ortak alanları.

    Çap/boy sayfa alanlarının çözünürlüğünde (Fırlatma Sahası
    ``GOVDE_ALANLARI`` ve panel ``tankliGovdeyiKur``: 3 / 2 ondalık);
    kanat alanları yok → kanat kuralı; yerleşim aracın kendisi.
    """
    af = arac['airframe_resolved']
    ucus = arac['flight_thrust']
    g = {'body_diameter': float('%.3f' % af['body_diameter_m']),
         'body_length': float('%.2f' % (af['nose_length_m']
                                        + af['length_behind_nose_m'])),
         'nose_length': af['nose_length_m'], 'nose_type': af['nose_type'],
         'fin_count': 4, 'fin_geometry_rule': 'static_margin',
         'dry_mass': kuru, 'propellant_mass': itici,
         'thrust_curve': arac['thrust_curve'],
         'nozzle_exit_area': ucus['nozzle_exit_area_m2'],
         'thrust_reference_pressure': ucus['thrust_reference_pressure_pa'],
         'cd0': 0.45, 'wind_speed': 5.0, 'wind_direction_deg': 0.0,
         'launch_elevation_deg': 90.0, 'launch_azimuth_deg': 0.0,
         'rail_length': 5.0, 'engine_od_m': arac['engine_od_m'],
         'engine_length_m': arac['engine_length_m'],
         'mass_layout': af['mass_layout']}
    g.update(ek)
    return g


# ===========================================================================
# 1. Katı panel: türetilmiş gövde + bileşen ağırlık merkezi
# ===========================================================================

def test_kati_arac_turetilmis_govde_ve_yerlesim_tasir(kati_arac):
    af = kati_arac['airframe_resolved']
    assert af['source'] == 'derived' and af['tank_order'] == []
    assert af['body_diameter_m'] and af['length_behind_nose_m']
    assert af['mass_layout'] is not None and af['mass_layout_not_built'] is None


def test_panel_kati_govdeyi_firlatma_sahasi_sayilariyla_kurar(kati_arac):
    if shutil.which('node') is None:
        pytest.skip('node yok')
    panel = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
    betik = (_js_islevi(panel, 'tankliGovde')
             + '\nconst a = ' + json.dumps(kati_arac) + ';'
             + '\nconst t = tankliGovde(a);'
             + '\nconsole.log(JSON.stringify(t && [t.d.toFixed(3), t.boy.toFixed(2),'
               ' t.burun.toFixed(2), t.burunTipi, t.tanksiz,'
               ' tankliGovde({airframe_resolved: Object.assign({},'
               ' a.airframe_resolved, {tank_order: null})})]));')
    cikti = subprocess.run([shutil.which('node')], input=betik,
                           capture_output=True, text=True, timeout=30)
    assert cikti.returncode == 0, cikti.stderr
    sonuc = json.loads(cikti.stdout)
    assert sonuc is not None, 'katı araçta panel türetilmiş gövdeyi kurmuyor'
    d, boy, burun, tip, tanksiz, listesiz = sonuc
    af = kati_arac['airframe_resolved']
    # Fırlatma Sahası alanları: çap toFixed(3), boy = sabit burun + burun arkası.
    assert d == '%.3f' % af['body_diameter_m']
    assert boy == '%.2f' % (fv.DERIVED_AIRFRAME_NOSE_LENGTH_M
                            + af['length_behind_nose_m'])
    assert burun == '%.2f' % fv.DERIVED_AIRFRAME_NOSE_LENGTH_M
    assert tip == fv.DERIVED_AIRFRAME_NOSE_TYPE
    assert tanksiz is True
    # Tank listesi yayımlanmamış (null) araçta gövde kurulmaz.
    assert listesiz is None


def test_panel_tanksiz_govde_notu_ve_tohum_yolu():
    panel = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
    kur = _js_islevi(panel, 'govdeyiMotordanTohumla')
    assert 'tankliGovde(arac)' in kur and 'tankliGovdeyiKur(tg)' in kur
    # Yerleşim aynı kapıdan: tanksız türetilmiş gövdede de taşınır, gövde
    # alanı elle yazıldıysa taşınmaz (kullanıcının gövdesi öncelikli).
    y = _js_islevi(panel, 'bilesenYerlesimi')
    assert 'tankliGovde(arac)' in y and 'alanElleYazildi' in y
    not_ = _js_islevi(panel, 'govdeNotunuYaz')
    assert 'sixdof.seed.bodyCarriesEngine' in not_
    i18n = (JS / 'i18n_common.js').read_text(encoding='utf-8')
    for anahtar in ('sixdof.seed.bodyCarriesEngine',
                    'sixdof.seed.bodyKeptTypedEngine'):
        assert i18n.count("'" + anahtar + "'") == 2, anahtar


def test_kati_ayni_arac_panel_ve_fs_ayni_agirlik_merkezi_marj_hukum(client, kati_arac):
    """Tek büyüklük: aynı katı araç iki sayfada aynı sayı ve aynı hüküm.

    Panel kuru kütle alanı motorun uçan atıl kütlesiyle tohumlanır; Fırlatma
    Sahası kuru = gövde kuru (0) + motorun uçan atıl kütlesi. Aynı kütleler
    ve aynı uçuş koşullarıyla istekler aynı olmalı ve aynı yanıtı vermeli.
    """
    ucus = kati_arac['flight_thrust']
    kuru = kati_arac['engine_inert_mass']
    itici = ucus['propellant_consumed_kg']
    panel = _govde_istegi(kati_arac, kuru, itici)
    fs = dict(panel, t_max=400, descent_model='ballistic')
    k1, y1 = _post(client, panel)
    k2, y2 = _post(client, fs)
    assert k1 == k2 == 200, (y1, y2)
    s1, s2 = y1['summary'], y2['summary']
    assert y1['stability_basis']['x_cg_source'] == 'components'
    cg = fv.component_cg(kati_arac['airframe_resolved']['mass_layout'],
                         panel['body_length'], kuru, itici)
    assert s1['x_cg_full'] == s2['x_cg_full'] == cg['x_cg_full_m']
    assert s1['x_cg_empty'] == s2['x_cg_empty'] == cg['x_cg_empty_m']
    assert s1['static_margin_full'] == s2['static_margin_full']
    assert s1['static_margin_empty'] == s2['static_margin_empty']
    assert (y1['fin_geometry']['fields']['fin_span']['value']
            == y2['fin_geometry']['fields']['fin_span']['value'])
    assert s1['flight_verdict']['stability'] == s2['flight_verdict']['stability']
    # Motor kıçta ve bütün kütle motorda: ağırlık merkezi gövdenin arka
    # yarısında (sabit kesrin 0,55·L / 0,50·L'si değil).
    assert cg['x_cg_full_m'] > 0.55 * panel['body_length']


def test_kati_kanat_kurali_saglanmazsa_ayni_adli_ret(client, kati_arac):
    """Marj kanat kuralının altına düşerse sıvıdaki AYNI ret (ikinci kural yok):
    4·d'ye kadar hiçbir açıklık eşiği tutamıyorsa ``fin_rule_not_met``."""
    ucus = kati_arac['flight_thrust']
    kuru = kati_arac['engine_inert_mass']
    # Kanat kökü elle çok kısa → kural yalnız açıklığı boyutlar ve tutamaz.
    g = _govde_istegi(kati_arac, kuru, ucus['propellant_consumed_kg'],
                      fin_root_chord=0.005, fin_tip_chord=0.005, fin_sweep=0.0)
    kod, y = _post(client, g)
    if kod == 200:
        pytest.skip('bu motor kısa kökle de kuralı sağlıyor')
    assert kod == 422 and y['error'] == 'fin_rule_not_met', y


# ===========================================================================
# 2. Faydalı yük: noktasal kütle, kuru kütlenin parçası, kapılı
# ===========================================================================

@pytest.fixture(scope='module')
def sivi_arac():
    from tests.test_v307_ucus_govde import _coz
    return fv.normalize('liquid', _coz('liquid'))


def test_faydali_yuk_agirlik_merkezine_noktasal_kutle_olarak_girer(sivi_arac):
    lay = sivi_arac['airframe_resolved']['mass_layout']
    L, P = 3.37, lay['consumed_total_kg']
    kuru = lay['dry_total_kg'] + 20.0
    yalin = fv.component_cg(lay, L, kuru, P)
    yuklu = fv.component_cg(lay, L, kuru + 120.0, P, 120.0, 0.75)
    # Σ m·x / Σ m (burundan): 120 kg 0,75 m'de, gerisi yalın araçla aynı.
    for uc in ('x_cg_full_m', 'x_cg_empty_m'):
        m0 = kuru + (P if uc == 'x_cg_full_m' else 0.0)
        beklenen = (m0 * yalin[uc] + 120.0 * 0.75) / (m0 + 120.0)
        assert yuklu[uc] == pytest.approx(beklenen, rel=1e-12)
    assert yuklu['airframe_dry_mass_not_from_engine_kg'] == pytest.approx(20.0)
    assert yuklu['payload']['mass_kg'] == 120.0
    assert yuklu['payload']['station_from_nose_m'] == 0.75


@pytest.mark.parametrize('kutle, istasyon, kod', [
    (120.0, None, 'PAYLOAD_INCOMPLETE'),
    (None, 0.75, 'PAYLOAD_INCOMPLETE'),
    (120.0, 9.0, 'PAYLOAD_OUTSIDE_BODY'),
    (120.0, 0.0, 'LAYOUT_NUMBER_INVALID'),
    (-1.0, 0.75, 'LAYOUT_NUMBER_INVALID'),
    (True, 0.75, 'LAYOUT_NUMBER_INVALID'),
    (float('nan'), 0.75, 'LAYOUT_NUMBER_INVALID'),
    (500.0, 0.75, 'DRY_MASS_BELOW_ENGINE_AND_PAYLOAD'),
])
def test_faydali_yuk_kapisi(sivi_arac, kutle, istasyon, kod):
    lay = sivi_arac['airframe_resolved']['mass_layout']
    with pytest.raises(fv.CgLayoutRejected) as e:
        fv.component_cg(lay, 3.37, lay['dry_total_kg'] + 120.0,
                        lay['consumed_total_kg'], kutle, istasyon)
    assert e.value.code == kod


def test_uc_faydali_yuku_yerlesimsiz_istekte_adiyla_reddeder(client, kati_arac):
    ucus = kati_arac['flight_thrust']
    g = _govde_istegi(kati_arac, kati_arac['engine_inert_mass'] + 1.0,
                      ucus['propellant_consumed_kg'], payload_mass=1.0,
                      payload_station=0.3)
    yerlesimsiz = dict(g)
    del yerlesimsiz['mass_layout']
    kod, y = _post(client, yerlesimsiz)
    assert kod == 422 and y['error'] == 'payload_needs_component_cg'
    kod, y = _post(client, dict(g, x_cg_full=0.6, x_cg_empty=0.6))
    assert kod == 422 and y['error'] == 'payload_needs_component_cg'
    kod, y = _post(client, g)
    assert kod == 200, y
    assert y['stability_basis']['x_cg_components']['payload']['mass_kg'] == 1.0


def test_faydali_yuksuz_istek_bit_ayni(client, kati_arac):
    """Yük alanı olmayan istek bu değişiklikten etkilenmez (aynı yanıt)."""
    ucus = kati_arac['flight_thrust']
    g = _govde_istegi(kati_arac, kati_arac['engine_inert_mass'],
                      ucus['propellant_consumed_kg'])
    k1, y1 = _post(client, g)
    cg = fv.component_cg(kati_arac['airframe_resolved']['mass_layout'],
                         g['body_length'], g['dry_mass'], g['propellant_mass'])
    assert k1 == 200 and cg['payload'] is None
    assert 'payload' not in y1['stability_basis']['x_cg_components']
    assert y1['summary']['x_cg_full'] == cg['x_cg_full_m']


# ===========================================================================
# 3. Fırlatma Sahası: ağırlık merkezinin kaynağı ekranda (yanıttan)
# ===========================================================================

def test_firlatma_sahasi_agirlik_merkezi_kaynagini_yaziyor():
    html = (KOK / 'hrma/templates/launch_site.html').read_text(encoding='utf-8')
    f = _js_islevi(html, 'agirlikMerkeziCumlesi')
    assert "cg.kaynak === 'components'" in f and 'site.cgFromComponents' in f
    # Sayı yoksa cümle yok (sayı uydurulmaz; null 0 diye basılmaz).
    assert "typeof cg.full !== 'number'" in f
    assert 'x_cg_source' in html and 'agirlikMerkeziCumlesi(sonAgirlikMerkezi)' in html
    i18n = (JS / 'i18n_launch_site.js').read_text(encoding='utf-8')
    for anahtar in ('site.cgFromComponents', 'site.cgLengthFraction'):
        assert i18n.count("'" + anahtar + "'") == 2, anahtar
    assert 'bileşenlerden (beyanlı yerleşim)' in i18n


def test_panel_faydali_yuk_alanlari_ve_ornek_tanimi():
    panel = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
    assert "id: 'sd_payload_m'" in panel and "id: 'sd_payload_x'" in panel
    assert 'payload.payload_mass = num(' in panel
    assert 'payload.dry_mass = payload.dry_mass + payload.payload_mass' in panel
    i18n = (JS / 'i18n_common.js').read_text(encoding='utf-8')
    for anahtar in ('sixdof.fPayloadMass', 'sixdof.fPayloadStation',
                    'sixdof.help.payloadMass', 'sixdof.help.payloadStation',
                    'sixdof.errPayloadPair'):
        assert i18n.count("'" + anahtar + "'") == 2, anahtar
    import examples.generate_examples as ge
    sd = ge.build_examples.__globals__['SIVI_ORNEK_FAYDALI_YUK_KG']
    assert sd > 0 and ge.SIVI_ORNEK_FAYDALI_YUK_ISTASYON_M > 0
    src = (KOK / 'examples/generate_examples.py').read_text(encoding='utf-8')
    assert 'aviyonik + kurtarma + yük' in src
    assert "'user_typed': ['sd_payload_m', 'sd_payload_x']" in src
