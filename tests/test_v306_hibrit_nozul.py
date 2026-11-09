"""V306/HİBRİT-NOZUL-ENJEKTÖR-HATA — kulvar bekçileri (4 Kasım 2026).

Kanıt ve önce/sonra ölçümü: ``docs/scofield/raw/OH/V306/hibrit-nozul/``.

k1 (S1, FİZİK-2 DEVİR 1): hibrit lüle ısıl analizi (``_analyze_nozzle_
   material``) eksenel profili motorun KENDİ gazıyla (γ, MW, c*, ışıyan tür
   kesirleri) koşar ve lüle malzemesiyle kurulmuş boğaz katsayısını
   yayımlar; termal FEA köprüsünün h(z) makullük kapısı lüle bölgesinde bu
   çapayla koşar (köprü bekçileri: ``tests/test_v301_fizik2_fea_capa.py``).
"""
import contextlib
import copy
import io
import json
import pathlib

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
ORNEK = KOK / 'examples' / 'Example Hybrid N2O-HTPB 3kN.hrma'
H = {'Host': '127.0.0.1:8080'}


def _sessiz(fn, *a, **k):
    t = io.StringIO()
    with contextlib.redirect_stdout(t), contextlib.redirect_stderr(t):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _ornek_alanlari():
    return json.loads(ORNEK.read_text(encoding='utf-8'))['inputs']['fields']


def _sayfa_govdesi(**degisen):
    """Sayfanın itki/süre kipindeki Hesapla gövdesi (ürünün eşlemesi)."""
    from hrma.analysis.flight_vehicle import page_payload
    alan = dict(_ornek_alanlari())
    alan.update(degisen)
    govde = page_payload('hybrid', alan)
    return {k: v for k, v in govde.items() if v != ''}


def _hesapla(client, govde):
    r = _sessiz(client.post, '/calculate', json=govde, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


@pytest.fixture(scope='module')
def ornek(client):
    return _hesapla(client, _sayfa_govdesi())


# ---------------------------------------------------------------------------
# k1 — lüle ısıl analizi motorun gazıyla; lüle çapası yayımlanır
# ---------------------------------------------------------------------------
def test_k1_lule_profili_motorun_gaziyla(ornek):
    motor = ornek['motor']
    tt = motor['nozzle_material_analysis']['throat_thermal']
    gaz = tt['gas_properties_basis']
    assert gaz['assumed_fields'] == [], gaz
    assert gaz['all_from_caller'] is True
    assert gaz['gamma']['value'] == pytest.approx(motor['gamma'], rel=1e-12)
    assert gaz['molecular_weight']['value'] == pytest.approx(
        motor['molecular_weight'], rel=1e-9)
    assert gaz['c_star']['value'] == pytest.approx(motor['c_star'],
                                                   rel=1e-12)


def test_k1_lule_capasi_kunyeli(ornek):
    motor = ornek['motor']
    nma = motor['nozzle_material_analysis']
    tt = nma['throat_thermal']
    assert tt['h_g_material'] == nma['material'] == 'graphite'
    assert tt['throat_h_g_W_m2K'] > 0
    # Referans cidar lüle malzemesinin (grafit izin 3300 K, 0,8·T_aw
    # sınırı) — kamara zincirininkiyle (ss_304: 1073 K) aynı sayı değil.
    ref = tt['gas_side_reference_wall_temperature']
    assert ref == pytest.approx(min(3300.0, 0.8 * tt[
        'gas_recovery_temperature_K']), rel=1e-12)
    kamara_ref = motor['heat_transfer_analysis'][
        'heat_transfer_coefficients']['gas_side_reference_wall_temperature']
    assert kamara_ref != pytest.approx(ref, rel=1e-3)
    assert 'NOZZLE' in tt['throat_h_g_basis']


def test_k1_lule_capasi_panel_profiliyle_ayni(client, ornek):
    """Panelin profil zinciri (wall-profile ucu, motor sözlüğünden) ile
    motorun lüle katsayısı aynı tanımdır: aynı gaz, aynı malzeme."""
    motor = ornek['motor']
    r = _sessiz(client.post, '/api/analysis/wall-profile',
                json={'motor_results': motor}, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    wp = r.get_json()['wall_profile']
    assert wp['material'] == 'graphite'
    hg_profil = wp['h_g'][wp['throat_index']]
    tt = motor['nozzle_material_analysis']['throat_thermal']
    assert hg_profil == pytest.approx(tt['throat_h_g_W_m2K'], rel=1e-9)


def test_k1_kapi_lulede_kosar_olumlu_hukum_capa_disi_degil(client, ornek):
    from hrma.fea import bridge
    motor = ornek['motor']
    wp = _sessiz(client.post, '/api/analysis/wall-profile',
                 json={'motor_results': motor},
                 headers=H).get_json()['wall_profile']
    out = _sessiz(bridge.extract_thermal_inputs, motor, axial_profile=wp)
    assert out['status'] == bridge.BRIDGE_STATUS_OK, out.get('reason')
    kapi = out['_basis']['h_profili']['makulluk_kapisi']
    assert kapi['durum'] == 'gecti'
    assert kapi['capa_malzemesi'] == 'graphite'
    # Çapası silinmiş sözlükte eski (adlı) yol aynen döner.
    m = copy.deepcopy(motor)
    m['nozzle_material_analysis']['throat_thermal'].pop('throat_h_g_W_m2K')
    eski = _sessiz(bridge.extract_thermal_inputs, m, axial_profile=wp)
    kapi = eski['_basis']['h_profili']['makulluk_kapisi']
    assert kapi['durum'] == 'calistirilamadi'
    assert kapi['neden'] == bridge.HG_GATE_NOT_RUN_ANCHOR_MATERIAL


# ---------------------------------------------------------------------------
# k2 — delik sayısı kazanılmamış plakayla seçilmez
# ---------------------------------------------------------------------------
def _dus_basligi(**kw):
    from hrma.utils.injector_design import InjectorDesign
    d = dict(mdot_ox=1.2, chamber_pressure=30.0, tank_pressure=55.0,
             oxidizer_density=786.0, pressure_drop=8.0,
             pressure_drop_source='user', injector_type='showerhead')
    d.update(kw)
    inj = InjectorDesign(**d)
    return inj


def _plan(plaka=None):
    inj = _dus_basligi()
    inj.set_showerhead_params(plate_thickness=plaka)
    r = _sessiz(inj.calculate)
    return r


def test_k2_plakasiz_plan_devre_kuraliyla_ve_varsayilandan_bagimsiz(
        monkeypatch):
    import hrma.utils.injector_design as U
    from hrma.engines.injector_design import _plan_orifices
    r = _plan()
    assert r['plate_thickness'] is None and r['L_D_ratio'] is None
    assert r['hole_count_basis'] == U.HOLE_COUNT_BASIS_NO_PLATE
    # Devre çözücüsünün kuralı: bandı tutan EN AZ delik.
    alan_m2 = r['n_holes'] * 3.141592653589793 * (
        r['hole_diameter'] / 2000.0) ** 2
    n_kural, d_kural = _plan_orifices(
        alan_m2, {'d_min_mm': U.ORIFICE_D_BAND_MM[0],
                  'd_max_mm': U.ORIFICE_D_BAND_MM[1],
                  'n_max': U.SHOWERHEAD_HOLE_COUNT_SEARCH[1]}, [])
    assert r['n_holes'] == n_kural
    assert r['hole_diameter'] == pytest.approx(d_kural * 1000.0, rel=1e-9)
    # Kimsenin seçmediği modül varsayılan plakası planı DEĞİŞTİRMEZ.
    monkeypatch.setattr(U, 'PLATE_THICKNESS_DEFAULT_MM', 6.0)
    r6 = _plan()
    assert (r6['n_holes'], r6['hole_diameter']) == (
        r['n_holes'], r['hole_diameter'])


def test_k2_kazanilmis_plakada_eski_amac_islevi():
    """Kullanıcı plakası L/D bandı seçimine AYNEN girer (bit-aynı yol)."""
    import hrma.utils.injector_design as U
    r3, r6 = _plan(3.0), _plan(6.0)
    for r in (r3, r6):
        assert r['hole_count_basis'] == U.HOLE_COUNT_BASIS_EARNED_PLATE
        assert r['plate_thickness_earned'] is True
    # Plaka seçimi değiştirir (L/D 3-5 buluşsal bandı plakadan).
    assert r3['n_holes'] != r6['n_holes']
    assert 3.0 <= r6['L_D_ratio'] <= 5.0


def test_k2_uctan_kanon_disi_yol(client):
    """Örnek hibrit, kullanıcı ΔP'si 8 bar, plakasız: önce 125 × Ø0,679 mm
    (3,0 mm varsayılan plakanın L/D bandı), sonra 10 × Ø2,40 mm."""
    import hrma.utils.injector_design as U
    g = _sayfa_govdesi()
    g.update(pressure_drop=8.0, pressure_drop_source='user')
    g.pop('plate_thickness', None)
    inj = _hesapla(client, g)['injector']
    assert inj['orifice_plan_is_canon'] is False
    assert inj['plate_thickness'] is None
    assert inj['hole_count_basis'].startswith(U.HOLE_COUNT_BASIS_NO_PLATE)
    assert inj['n_holes'] == 10
    assert inj['hole_diameter'] == pytest.approx(2.3995, abs=5e-4)


def test_k2_kanon_planda_dayanak_verilen_sayi(ornek):
    import hrma.utils.injector_design as U
    inj = ornek['injector']
    assert inj['orifice_plan_is_canon'] is True
    assert inj['hole_count_basis'] == U.HOLE_COUNT_BASIS_SUPPLIED


# ---------------------------------------------------------------------------
# k3 — boğaz ısıl hükmünün künyesi (kararlı hâl, yanma süresi yok)
# ---------------------------------------------------------------------------
def test_k3_throat_thermal_kunyesi(ornek):
    from hrma.engines import hybrid_rocket_engine as E
    tt = ornek['motor']['nozzle_material_analysis']['throat_thermal']
    assert tt['temperature_kind'] == E.THROAT_THERMAL_TEMPERATURE_KIND \
        == 'steady_state_equilibrium'
    assert tt['burn_time_used'] is False
    assert tt['verdict_basis'] == E.THROAT_THERMAL_VERDICT_BASIS
    for parca in ('steady-state equilibrium', 'burn time is not used',
                  'conservative upper bound', 'thermal FEA'):
        assert parca in tt['verdict_basis'], parca


def test_k3_hukum_yanma_suresinden_bagimsiz(ornek):
    """Künyenin iddiası ölçülür: lüle zincirinin çağırdığı eksenel profil
    yanma süresini kullanmaz (aynı girdide süre 1 s ⟷ 300 s, boğaz denge
    sıcaklığı bit-aynı)."""
    from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
    m = ornek['motor']
    girdi = {k: m[k] for k in ('chamber_pressure', 'chamber_temperature',
                               'chamber_diameter', 'chamber_length',
                               'mdot_total', 'throat_diameter', 'gamma',
                               'molecular_weight', 'c_star')}
    an = HeatTransferAnalyzer()
    sonuc = []
    for sure in (1.0, 300.0):
        p = _sessiz(an.analyze_axial_profile, dict(girdi, burn_time=sure),
                    material='graphite', wall_thickness=0.005)
        sonuc.append(p['T_wall_eq'][p['throat_index']])
    assert sonuc[0] == sonuc[1]


def test_k3_asim_uyarisi_kunyeyi_iki_dilde_soyler():
    i18n = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    satirlar = [s for s in i18n.splitlines()
                if "'warn.hybrid.nozzle_material_over_temp':" in s]
    assert len(satirlar) == 2
    en, tr = satirlar
    assert 'steady-state equilibrium' in en and 'burn time is not used' in en
    assert 'conservative upper bound' in en
    assert 'kararlı hâl denge sıcaklığı' in tr
    assert 'Yanma süresi kullanılmaz' in tr and 'tutucu üst sınır' in tr
    for metin in (en, tr):
        for yer in ('{wall_K}', '{allowable_K}', '{material}', '{cooling}'):
            assert yer in metin, yer
    assert 'This throat will fail' not in en
    assert 'Bu boğaz dayanmaz' not in tr


# ---------------------------------------------------------------------------
# k4 — örnek dosyanın çelişen alanı; I = F·t_b öncelik kuralı tek yerde
# ---------------------------------------------------------------------------
def _eski_motor_kurali(thrust, burn_time, total_impulse):
    """Taban 700a67586 motor kurucusunun dallanması (BİREBİR kopya)."""
    if total_impulse is not None:
        I_total = total_impulse
        if thrust is not None:
            F = thrust
            t_b = total_impulse / thrust
            bagimsiz, turetilen = ('total_impulse', 'thrust'), 'burn_time'
        elif burn_time is not None:
            t_b = burn_time
            F = total_impulse / burn_time
            bagimsiz, turetilen = ('total_impulse', 'burn_time'), 'thrust'
        else:
            F = total_impulse / 10
            t_b = 10
            bagimsiz, turetilen = ('total_impulse',), 'thrust'
    else:
        F = thrust if thrust is not None else 1000
        t_b = burn_time if burn_time is not None else 10
        I_total = F * t_b
        bagimsiz, turetilen = ('thrust', 'burn_time'), 'total_impulse'
    return F, t_b, I_total, tuple(bagimsiz), turetilen


def _eski_turetilen(data):
    """Taban app.py ``_turetilen_buyukluk_ihlali``nin dallanma kısmı."""
    from hrma.utils import input_guard
    impuls = input_guard.finite_number(data.get('total_impulse'))
    if impuls is None or impuls <= 0:
        return None
    itki = input_guard.finite_number(data.get('thrust'))
    sure = input_guard.finite_number(data.get('burn_time'))
    if itki is not None and itki > 0:
        return 'burn_time', impuls / itki, ('total_impulse', 'thrust')
    if sure is not None and sure > 0:
        return 'thrust', impuls / sure, ('total_impulse', 'burn_time')
    return 'thrust', impuls / 10.0, ('total_impulse',)


def _eski_gorunum(data):
    """Taban app.py ``_hibrit_dogrulama_gorunumu`` (BİREBİR kopya)."""
    from hrma.utils import input_guard
    if not isinstance(data, dict):
        return data
    sayi = input_guard.finite_number
    impuls, itki, sure = (sayi(data.get('total_impulse')),
                          sayi(data.get('thrust')), sayi(data.get('burn_time')))
    if impuls is None or impuls <= 0:
        return data
    gorunum = dict(data)
    if itki is not None and itki > 0 and data.get('burn_time') in (None, ''):
        gorunum['burn_time'] = impuls / itki
    elif sure is not None and sure > 0 and data.get('thrust') in (None, ''):
        gorunum['thrust'] = impuls / sure
    return gorunum


_IZGARA = (None, '', 0, -5, 'abc', 0.5, 7, 3000, 1e9)


def _izgara():
    import itertools
    for f, t, i in itertools.product(_IZGARA, repeat=3):
        d = {}
        for ad, v in (('thrust', f), ('burn_time', t), ('total_impulse', i)):
            if v is not None:
                d[ad] = v
        yield d


def test_k4_motor_islevi_eski_oncelik_kurali():
    import itertools
    from hrma.engines.hybrid_rocket_engine import resolve_impulse_inputs
    degerler = (None, 0.5, 7, 3000, 1e9)
    for f, t, i in itertools.product(degerler, repeat=3):
        r = resolve_impulse_inputs(f, t, i)
        F, t_b, I, bag, tur = _eski_motor_kurali(f, t, i)
        yeni = (r['thrust_N'], r['burn_time_s'], r['total_impulse_Ns'],
                tuple(r['independent_inputs']), r['derived_quantity'])
        assert yeni == (F, t_b, I, bag, tur), (f, t, i)
        # Tür de aynı (JSON'da 10 ⟷ 10.0 ayrımı yanıt md5'ini değiştirir).
        assert [type(x) for x in yeni[:3]] == [type(x) for x in (F, t_b, I)]


def test_k4_uc_yardimcilari_motor_islevini_kullanir():
    import inspect
    from hrma import app as A
    for ad in ('_turetilen_buyukluk_ihlali', '_hibrit_dogrulama_gorunumu'):
        kaynak = inspect.getsource(getattr(A, ad))
        assert 'resolve_impulse_inputs(' in kaynak, ad
        assert 'impuls / itki' not in kaynak, ad
    for d in _izgara():
        eski = _eski_turetilen(d)
        yeni = A._turetilen_buyukluk_ihlali(d)
        if eski is None:
            assert yeni is None, d
        else:
            alan, deger, kaynak = eski
            # İhlal yoksa None; varsa alan/değer/kaynak eski dallanmayla aynı.
            if yeni is not None:
                assert (yeni['field'], yeni['value'],
                        tuple(yeni['derived_from'])) == (alan, deger, kaynak), d
        assert A._hibrit_dogrulama_gorunumu(d) == _eski_gorunum(d), d


def test_k4_ornek_dosyasi_dogrudan_apide_10_s(client):
    """Örnek dosyanın alanları kip alanı olmadan doğrudan API'ye: önce
    t_b = 10000/3000 = 3,33 s + 'süre ezildi' uyarısı; sonra 10 s."""
    from tests.support.ornek_alanlari import ornek_alanlari
    alan = ornek_alanlari(ORNEK)
    assert 'total_impulse' not in alan
    alan['atmospheric_pressure'] = alan.pop('single_pressure')
    motor = _hesapla(client, alan)['motor']
    # V306/HİBRİT-ÇAPRAZ-2 — çapraz kırılma (HİBRİT-NOZUL k4 ⟷ HİBRİT-ÇAPRAZ
    # kalem 1, aynı gün paralel). Öncelik kuralının çözdüğü TASARIM süresi
    # ``burn_time_requested_s``tir; N₂O kendinden basınçlı tankta
    # ``burn_time`` TESLİM süresidir (boşalma çözümü; ölçüldü, taban
    # 78dbb287e: 10,4143 s). Bekçinin sorusu (3,33 s değil 10 s) tasarım
    # süresinde sorulur; teslim süresi aşağıda sayfa yoluyla eşitlenir.
    assert motor['burn_time_requested_s'] == pytest.approx(10.0, rel=1e-12)
    assert motor['delivered_source'] == 'tank_blowdown'
    assert motor['impulse_input_resolution']['independent_inputs'] == [
        'thrust', 'burn_time']
    kodlar = {w.get('code') for w in motor.get('design_warnings') or []
              if isinstance(w, dict)}
    assert 'warn.hybrid.burn_time_overridden_by_impulse' not in kodlar
    # Sayfa yolu (I = F·t gönderir) aynı sayıları yayımlar.
    sayfa = _hesapla(client, _sayfa_govdesi())['motor']
    assert sayfa['burn_time'] == motor['burn_time']
    assert sayfa['total_impulse'] == pytest.approx(motor['total_impulse'],
                                                   rel=1e-12)


# ---------------------------------------------------------------------------
# k5 — örnek kendi narinlik uyarısını üretmez (kaynaklı regresyon çifti)
# ---------------------------------------------------------------------------
def test_k5_ornek_kendi_uyarilarini_uretmez(ornek):
    from hrma.engines.hybrid_rocket_engine import GRAIN_LD_WARN_THRESHOLD
    motor = ornek['motor']
    geo = motor['motor_geometry']
    kodlar = {w.get('code') for w in motor.get('design_warnings') or []
              if isinstance(w, dict)}
    assert 'warn.hybrid.grain_slenderness_high' not in kodlar
    assert 'warn.hybrid.htpb_coeff_bias' not in kodlar
    # Katalog dışı çift adıyla beyan edilir (bilgi notu, düzeltme yok).
    assert 'warn.hybrid.regression_coeff_user_override' in kodlar
    assert geo['grain_length'] / geo['chamber_diameter'] \
        < GRAIN_LD_WARN_THRESHOLD
    assert geo['chamber_length'] / geo['chamber_diameter'] \
        < GRAIN_LD_WARN_THRESHOLD
    assert motor.get('port_count', 1) == 1     # CAD tek port çizer


def test_k5_ornek_regresyonu_depo_kayitlarindan():
    """Örneğin a, n ve başlangıç akısı üreticinin uyarlamasından; uyarlama
    depo kayıtlarından yeniden üretilir ve akı ölçüm bandının içindedir."""
    from examples import generate_examples as ge
    u = ge.carmicino2013_htpb_uyarlamasi()
    assert len(u['kayitlar']) == 16
    assert u['oksitleyici_fazi'] == ['gaseous']
    assert u['a_SI'] == pytest.approx(6.399e-05, rel=1e-3)
    assert u['n'] == pytest.approx(0.554, abs=5e-4)
    assert u['G_bandi'] == pytest.approx((73.0, 258.9))
    assert u['medAPE'] == pytest.approx(0.088, abs=5e-4)
    alan = _ornek_alanlari()
    tohum = ge.ornek_hibrit_regresyonu()
    for k, v in tohum.items():
        assert float(alan[k]) == pytest.approx(v, rel=1e-12), k
    assert u['G_bandi'][0] <= float(alan['mass_flux_chamber']) \
        <= u['G_bandi'][1]


def test_k5_uretici_celisen_alani_yazmaz():
    from examples import generate_examples as ge
    assert 'total_impulse' in ge.KAYITTAN_DUSEN_ALANLAR['hybrid']
    assert 'total_impulse' not in _ornek_alanlari()
