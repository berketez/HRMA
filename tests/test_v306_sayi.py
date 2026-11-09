# -*- coding: utf-8 -*-
"""V306/SAYI — yayın kapısı 6: aynı büyüklük her panelde aynı sayıdır.

Kalemler (brif ``docs/scofield/raw/OH/V306/ana-model/brif_02kas/SAYI.md``;
kanıt ``docs/scofield/raw/OH/V306/sayi/``):

* **1 (NR-1)** hibrit Yanma Analizi panosu motorun manşette uyguladığı
  η_c*'ı ve kaynağını gösterir; η_kin ayrı, adlı satırdır ve motorun C_F'e
  uyguladığı sayının kendisidir; ham anahtar yok.

Beklenen değerler ucun O KOŞUMDAKİ yanıtından okunur (manşet bloğu); ürün
sabitinden türetilmez.
"""

import contextlib
import io
import json
import os
import pathlib
import re
import shutil
import warnings

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
ORNEK = KOK / 'examples'
HIBRIT = ORNEK / 'Example Hybrid N2O-HTPB 3kN.hrma'
SIVI = ORNEK / 'Example Liquid LOX-RP1 25kN.hrma'
KATI = ORNEK / 'Example Solid KNDX BATES 75mm.hrma'
NODE = shutil.which('node')
node_gerekli = pytest.mark.skipif(NODE is None, reason='node yok')

#: Yanma panosu notunda kalmaması gereken ham anahtarlar (NR-1).
YANMA_NOTU_YASAK_ANAHTAR = ('eta_c*', 'eta_kin', 'sea_level_default', 'exit basis',
                  'motor.optimum_of_ratio', 'expansion_ratio_equilibrium')


def _govde(yol, **ek):
    from tests.support.ornek_alanlari import ornek_alanlari
    f = ornek_alanlari(yol)
    f.pop('motor_name', None)
    f.pop('motor_description', None)
    if 'single_pressure' in f:
        f['atmospheric_pressure'] = f.pop('single_pressure')
    f.update(ek)
    return {k: v for k, v in f.items() if v is not None}


def _post(uc, govde):
    from hrma.app import app
    app.config['TESTING'] = True
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with app.test_client() as c:
            r = c.post(uc, json=govde)
    return r.status_code, r.get_json() or {}


def _pano(j):
    fig = (j.get('plots') or {}).get('combustion_analysis')
    fig = json.loads(fig) if isinstance(fig, str) else fig
    assert fig, 'yanma panosu üretilmedi'
    gosterge = [t for t in fig['data'] if t.get('type') == 'indicator']
    notlar = ' '.join(a['text'] for a in fig['layout'].get('annotations') or []
                      if str(a.get('text', '')).startswith('- '))
    # sarılmış madde satırlarını birleştir ('<br>  ' devam satırı)
    notlar = re.sub(r'<br>\s+', ' ', notlar).replace('<br>', ' ')
    basliklar = [a['text'] for a in fig['layout'].get('annotations') or []
                 if not str(a.get('text', '')).startswith('- ')]
    return gosterge, notlar, basliklar


def _maddeler(j):
    """Dipnotun maddeleri: '- ' ile başlayan satır + '  ' devam satırları."""
    fig = (j.get('plots') or {}).get('combustion_analysis')
    fig = json.loads(fig) if isinstance(fig, str) else fig
    out = []
    for a in fig['layout'].get('annotations') or []:
        t = str(a.get('text', ''))
        if not t.startswith('- '):
            continue
        for satir in t.split('<br>'):
            if satir.startswith('- '):
                out.append(satir[2:])
            else:
                out[-1] += ' ' + satir.strip()
    return out


@pytest.fixture(scope='module')
def hibrit_yanitlari():
    out = {
        'ornek': _post('/calculate', _govde(HIBRIT)),
        'eta95': _post('/calculate', _govde(HIBRIT, combustion_efficiency=95)),
        'parafin': _post('/calculate', {
            k: v for k, v in _govde(HIBRIT, fuel_type='paraffin').items()
            if k not in ('fuel_density', 'regression_a', 'regression_n')}),
    }
    for ad, (kod, j) in out.items():
        assert kod == 200, (ad, kod, str(j)[:400])
    return {ad: j for ad, (kod, j) in out.items()}


# ---------------------------------------------------------------------------
# Kalem 1 — NR-1: Yanma Analizi panosu η_c* = manşet η_c*
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('ad, kaynak', [('ornek', 'sourced_default'),
                                        ('eta95', 'user_input'),
                                        # V306/HİBRİT-MODEL M-HIBRIT-25:
                                        # ölçümü olmayan çift (N2O/parafin)
                                        # artık beyanlı genel varsayılanı
                                        # alır; ideal c* kolu kalktı.
                                        ('parafin', 'sourced_default')])
def test_k1_pano_eta_c_manset_ile_ayni(hibrit_yanitlari, ad, kaynak):
    j = hibrit_yanitlari[ad]
    blok = j['motor']['c_star_efficiency']
    assert blok['source'] == kaynak
    gosterge, notlar, basliklar = _pano(j)
    assert len(gosterge) == 1
    # Gösterge = motorun manşete uyguladığı η_c* (bit-aynı yüzde)
    assert gosterge[0]['value'] == blok['percent'], (gosterge[0]['value'], blok)
    assert 'Combustion (c*) Efficiency' in basliklar
    # Kaynaksız hüküm bandı yok
    assert not gosterge[0]['gauge'].get('steps')
    if kaynak == 'ideal_no_source':
        assert 'c* efficiency: none applied' in notlar, notlar
    else:
        assert ('c* efficiency η_c* = %.2f%%, applied to this run\'s '
                'headline' % blok['percent']) in notlar, notlar
        beklenen = {'sourced_default': 'source: not entered; sourced default',
                    'user_input': 'source: your input.'}[kaynak]
        assert beklenen in notlar, notlar
    # Girilen / kaynaklı değer "verilmedi" diye bildirilmez
    assert 'no measured c* efficiency supplied' not in notlar
    assert 'no c* efficiency was supplied' not in notlar


@pytest.mark.parametrize('ad', ['ornek', 'eta95', 'parafin'])
def test_k1_pano_eta_kin_motorun_uyguladigi(hibrit_yanitlari, ad):
    """η_kin tek sayı: panodaki = motorun C_F'e uyguladığı
    (nozzle_design.performance.kinetic_efficiency); büyük göstergeye girmez."""
    j = hibrit_yanitlari[ad]
    m = j['motor']
    kin = m['nozzle_design']['performance']['kinetic_efficiency']
    assert m['nozzle_angles']['thrust_coefficient_source'] == 'computed_isentropic'
    gosterge, notlar, _ = _pano(j)
    assert ('Kinetic efficiency η_kin = %.2f%% (finite-rate nozzle loss): '
            "applied to this run's headline thrust coefficient, not to c*."
            % (kin * 100.0)) in notlar, notlar
    assert gosterge[0]['value'] != pytest.approx(
        m['c_star_efficiency']['percent'] * kin)


@pytest.mark.parametrize('ad', ['ornek', 'eta95', 'parafin'])
def test_k1_pano_notunda_ham_anahtar_yok(hibrit_yanitlari, ad):
    _g, notlar, _b = _pano(hibrit_yanitlari[ad])
    for ham in YANMA_NOTU_YASAK_ANAHTAR:
        assert ham not in notlar, (ham, notlar)


def test_k1_kullanici_cf_verince_eta_kin_uygulanmadi_der():
    from hrma.visualization.visualization import (
        _combustion_efficiency_breakdown)
    applied = {'percent': 89.0, 'source': 'sourced_default', 'applied': True,
               'kinetic_efficiency': 0.998, 'kinetic_resolved': True,
               'kinetic_applied_to_cf': False}
    pct, satirlar = _combustion_efficiency_breakdown({}, None, applied=applied)
    assert pct == 89.0
    assert any('not applied - this run uses the thrust coefficient you '
               'entered as given' in s for s in satirlar), satirlar
    applied.update(kinetic_resolved=False)
    _p, satirlar = _combustion_efficiency_breakdown({}, None, applied=applied)
    assert any('not resolved for this run' in s for s in satirlar), satirlar


def test_k1_motorsuz_analiz_kendi_kestirimini_beyan_eder():
    """/api/advanced-analysis yolu: motor koşusu yok; η_c* çözümün kendi
    oranıdır, η_kin kestirimi 'hiçbir motor sonucuna uygulanmadı' der."""
    from hrma.visualization.visualization import (
        _combustion_efficiency_breakdown)
    cd = {'performance': {'c_star': 1500.0, 'c_star_delivered': 1500.0},
          'conditions': {'chamber': {'P': 20.0}}}
    pct, satirlar = _combustion_efficiency_breakdown(cd)
    assert pct == 100.0
    assert satirlar[0].startswith('c* efficiency η_c* = 100.00%: no c* '
                                  'efficiency was supplied to this analysis')
    cd['performance']['c_star_delivered'] = 1350.0
    pct, satirlar = _combustion_efficiency_breakdown(cd)
    assert pct == pytest.approx(90.0)
    assert satirlar[0] == ('c* efficiency η_c* = 90.00% = delivered c* / '
                           'theoretical equilibrium c* of this analysis.')


def test_k1_kati_ve_sivi_karsilik_alanlari_tek_sayi():
    """Katı ve sıvı sayfasında Yanma Analizi panosu yok (pano yalnız hibrit
    /calculate ve /api/advanced-analysis'te). Karşılık alanları ölçüldü
    (olcum/k1_kati_sivi_once.json): her biri kendi içinde tek sayı."""
    kod, s = _post('/calculate_liquid', _govde(SIVI, include_plots=False))
    assert kod == 200
    girdi = json.loads(SIVI.read_text())['inputs']['fields']['combustion_efficiency']
    yuzde = [s['combustion_analysis']['combustion_analysis']['combustion_efficiency'],
             s['efficiency_breakdown']['efficiency_by_mechanism']['combustion_efficiency']]
    kesir = [s['injection_system']['combustion_efficiency'],
             s['injector_design']['combustion_efficiency']]
    assert yuzde == [girdi, girdi] and kesir == [girdi / 100.0] * 2, (yuzde, kesir)
    kod, k = _post('/calculate_solid', _govde(KATI, include_plots=False))
    assert kod == 200
    assert (k['detailed_analysis']['performance_metrics']['c_star_efficiency_percent']
            == k['advanced_performance']['combustion_analysis']['c_star_efficiency_percent'])


@node_gerekli
def test_k1_pano_notlari_TR_cevrilir(hibrit_yanitlari, tmp_path):
    """Üretici cümleleri (motorlu üç kaynak + kullanıcı C_F + çözülmemiş
    kinetik + motorsuz iki hâl) TR'de tam cümle çevrilir, ondalık virgüllü,
    yüzde işareti önde; EN aynen."""
    from tests.test_d37_dil_b1 import ceviri
    from hrma.visualization.visualization import (
        _combustion_efficiency_breakdown)
    cumleler = []
    for ad in ('ornek', 'eta95', 'parafin'):
        cumleler += _maddeler(hibrit_yanitlari[ad])
    for ek in ({'kinetic_applied_to_cf': False}, {'kinetic_resolved': False},
               {'kinetic_applied_to_cf': None}):
        applied = {'percent': 89.0, 'source': 'sourced_default',
                   'applied': True, 'kinetic_efficiency': 0.998,
                   'kinetic_resolved': True, 'kinetic_applied_to_cf': True}
        applied.update(ek)
        cumleler += _combustion_efficiency_breakdown({}, None, applied)[1]
    for cd in ({'performance': {'c_star': 1500.0, 'c_star_delivered': 1500.0}},
               {'performance': {'c_star': 1500.0, 'c_star_delivered': 1350.0}}):
        cumleler += _combustion_efficiency_breakdown(cd)[1]
    cumleler = list(dict.fromkeys(cumleler))
    # Figürde not maddesi '- ' ile başlar (tire kuralı gövdeyi sunucu
    # desenlerinden geçirir); başlık sözlükten.
    hedef = ['- ' + c for c in cumleler
             if 'efficiency' in c.lower() and c != 'Combustion (c*) Efficiency']
    hedef.append('Combustion (c*) Efficiency')
    assert len(hedef) >= 10, hedef
    r = ceviri(KOK, chart=hedef, tmpdir=str(tmp_path), ad='k1')
    assert 'error' not in r, r
    assert r['en']['chart'] == hedef
    for en, tr in zip(hedef, r['tr']['chart']):
        assert tr != en, en
        for ing in ('efficiency', 'applied', 'source', 'headline', 'not ',
                    'this run', 'analysis'):
            assert ing not in tr, (ing, tr)
        assert not re.search(r'\d\.\d', tr), tr
        assert not re.search(r'\d%', tr), tr


# ---------------------------------------------------------------------------
# Kalem 2 — NR-5: BELİRSİZLİK nominali = manşet (üç motor, gerçek sayfa gövdesi)
# ---------------------------------------------------------------------------
def _sayfa(mt):
    from tests.support.kabul_sayfa_yukleri import SAYFA_YUKLERI
    return dict(SAYFA_YUKLERI[mt])


@pytest.fixture(scope='module')
def uq_hibrit():
    g = _sayfa('hybrid')
    kod, j = _post('/calculate', dict(g, include_plots=False))
    assert kod == 200, str(j)[:400]
    kod, u = _post('/api/uncertainty-analysis', {
        'motor_type': 'hybrid', 'level': 'fast', 'seed': 42, 'inputs': g,
        'n_samples': 3})
    assert kod == 200, str(u)[:400]
    return j, u


def test_k2_hibrit_nominal_mansetle_bit_ayni(uq_hibrit):
    j, u = uq_hibrit
    m = j['motor']
    for anahtar, manset in (('isp', m['isp']), ('c_star', m['c_star']),
                            ('thrust', m['thrust']),
                            ('chamber_pressure', m['chamber_pressure']),
                            ('regression_rate_avg', m['regression_rate_avg']),
                            ('total_impulse', m['total_impulse'])):
        assert u['outputs'][anahtar]['nominal'] == manset, (
            anahtar, u['outputs'][anahtar]['nominal'], manset)
    # NR-5'in kendi sayıları: manşet teslim impulsu (integral), istenen değil
    assert m['total_impulse'] != m['total_impulse_requested_Ns']


def test_k2_hibrit_impuls_bu_seviyede_orneklenmedi_adiyla(uq_hibrit):
    _j, u = uq_hibrit
    ti = u['outputs']['total_impulse']
    assert ti['sampled'] is False
    assert ti['not_sampled_reason'] == 'time_march_off_at_this_level'
    for k in ('mean', 'std', 'p5', 'p50', 'p95', 'histogram'):
        assert ti[k] is None, k          # dağılım uydurulmaz
    assert 'total_impulse' not in u['mean_shift_percent']
    # itki tasarım hedefi: σ = 0'ın nedeni adıyla
    th = u['outputs']['thrust']
    assert th['std'] == 0 and th['zero_spread_reason'] == 'design_target'
    # dağılımı olan çıktıda gerekçe alanı yok
    assert 'zero_spread_reason' not in u['outputs']['isp']


def test_k2_hibrit_yuruyuslu_seviye_ayni_tanimla_ornekler(uq_hibrit):
    """high_fidelity (track_performance) yolunda total_impulse örneklenir
    ve nominal örnek manşetle BİT-AYNI (aynı tanım: itki eğrisi integrali)."""
    import contextlib as _c
    from hrma.analysis import uq_adapters as uqa
    j, _u = uq_hibrit
    with _c.redirect_stdout(io.StringIO()):
        f = uqa.make_factory('hybrid', _sayfa('hybrid'), track_performance=True)
        nominal = f({})
    assert nominal['total_impulse'] == j['motor']['total_impulse']
    assert f.not_sampled_outputs() == {}
    # Ters yön: yürüyüşsüz fabrika impulsu ÖRNEKLEMEZ (F × t_b tanımıyla
    # dağılım üretilmez; ters mutasyon M4 bunu ister).
    with _c.redirect_stdout(io.StringIO()):
        f0 = uqa.make_factory('hybrid', _sayfa('hybrid'),
                              track_performance=False)
        nominal0 = f0({})
    assert 'total_impulse' not in nominal0
    ns = f0.not_sampled_outputs()['total_impulse']
    assert ns['nominal'] == j['motor']['total_impulse'] and ns['sampled'] is False


def test_k2_kati_nominal_mansetle_bit_ayni():
    g = _sayfa('solid')
    kod, j = _post('/calculate_solid', dict(g, include_plots=False))
    assert kod == 200
    kod, u = _post('/api/uncertainty-analysis', {
        'motor_type': 'solid', 'level': 'fast', 'seed': 42, 'inputs': g,
        'n_samples': 3})
    assert kod == 200, str(u)[:400]
    o = u['outputs']
    assert o['isp']['nominal'] == j['specific_impulse']
    assert o['c_star']['nominal'] == j['c_star']
    assert o['total_impulse']['nominal'] == j['total_impulse']
    assert o['max_pressure']['nominal'] == pytest.approx(
        j['throat_sizing']['peak_chamber_pressure_bar'], rel=1e-12)


def test_k2_sivi_nominal_mansetle_bit_ayni():
    """Sıvı fabrika /calculate_liquid ile aynı kurulumu (overrides=data)
    kullanır; nominal örnek manşetle bit-aynı. Önce: Isp 272,36 ⟷ 257,11 s,
    c* 1792,06 ⟷ 1738,30 m/s, ṁ 9,360 ⟷ 9,915 kg/s (olcum/k2_once.json)."""
    import contextlib as _c
    from hrma.analysis import uq_adapters as uqa
    g = _sayfa('liquid')
    kod, j = _post('/calculate_liquid', dict(g, include_plots=False))
    assert kod == 200
    with _c.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        f = uqa.make_factory('liquid', g)
        nominal = f({})
    assert nominal['isp'] == j['isp_sea_level']
    assert nominal['c_star'] == j['c_star']
    assert nominal['mdot_total'] == j['total_mass_flow']
    assert nominal['thrust'] == j['thrust']
    # η dağılımı formun η'sına oturur (nominal = ortalama = 0,97)
    d = uqa.center_liquid_eta_distribution(
        uqa.build_distributions('liquid', None), f.eta_c_star_nominal)
    assert f.eta_c_star_nominal == (0.97, True)
    assert d['eta_c_star'].nominal_value() == 0.97 and d['eta_c_star'].mean == 0.97


# ---------------------------------------------------------------------------
# Kalem 3 — NR-6: "BOŞ BIRAKTIĞINIZ ALANLAR" kullanılmayan tank basıncı
# ---------------------------------------------------------------------------
_LOX = {'oxidizer_type': 'lox', 'oxidizer_temp': 90.0, 'of_ratio': 2.2,
        'oxidizer_density': 1141.0, 'oxidizer_viscosity': 1.9e-4}


def _tank_kaydi(j):
    k = [r for r in (j.get('defaults_applied') or [])
         if isinstance(r, dict) and r.get('field') == 'tank_pressure']
    assert len(k) <= 1, k
    return k[0] if k else None


@pytest.fixture(scope='module')
def nr6_yanitlari():
    g = dict(_sayfa('hybrid'), include_plots=False)
    out = {
        'lox_varsayilan': _post('/calculate', dict(g, **_LOX)),
        'lox_tasarim_dp': _post('/calculate', dict(
            g, tank_pressure_source='design_pressure_drop', **_LOX)),
        'lox_user': _post('/calculate', dict(
            g, tank_pressure_source='user', tank_pressure=50.0, **_LOX)),
        'n2o_varsayilan': _post('/calculate', g),
        'n2o_user': _post('/calculate', dict(
            g, tank_pressure_source='user', tank_pressure=60.0)),
    }
    for ad, (kod, j) in out.items():
        assert kod == 200, (ad, kod, str(j)[:400])
    return {ad: j for ad, (kod, j) in out.items()}


@pytest.mark.parametrize('ad, kaynak', [
    ('lox_varsayilan', 'chamber_pressure_plus_design_pressure_drop'),
    ('lox_tasarim_dp', 'chamber_pressure_plus_design_pressure_drop'),
    ('n2o_varsayilan', 'n2o_saturation_at_tank_temperature')])
def test_k3_kullanilmayan_tank_basinci_kullanilmadi_der(nr6_yanitlari, ad,
                                                         kaynak):
    j = nr6_yanitlari[ad]
    idd = j['motor']['injector_design']
    assert idd['feed_pressure_source'] == kaynak
    kayit = _tank_kaydi(j)
    assert kayit is not None and kayit['reason'] == 'not_supplied'
    assert kayit['applied'] is False, kayit
    assert kayit['used_by_model'] == idd['feed_pressure_bar']
    assert kayit['used_by_model_source'] == kaynak
    assert 'NOT used in this run' in kayit['message']
    assert 'describes THAT input' not in kayit['message']


@pytest.mark.parametrize('ad', ['lox_user', 'n2o_user'])
def test_k3_kullanici_tank_kipinde_kayit_yok(nr6_yanitlari, ad):
    j = nr6_yanitlari[ad]
    assert j['motor']['injector_design']['feed_pressure_source'] == \
        'user_tank_pressure'
    assert _tank_kaydi(j) is None


def test_k3_lox_tank_basinci_motor_sonucuna_girmez():
    """Kâhin: LOX tasarım ΔP kipinde tank_pressure 50 ⟷ 80 → motor sonucu
    (yankı alanları dışında) bit-aynı (olcum/k3_once.json: md5 aynı)."""
    g = dict(_sayfa('hybrid'), include_plots=False, **_LOX)
    sonuc = []
    for tp in (50.0, 80.0):
        kod, j = _post('/calculate', dict(g, tank_pressure=tp))
        assert kod == 200
        m = dict(j['motor'])
        for k in ('tank_pressure', 'tank_pressure_bar'):
            m.pop(k, None)
        sonuc.append(json.dumps(m, sort_keys=True, default=str))
    assert sonuc[0] == sonuc[1]


@node_gerekli
def test_k3_ekran_satiri_tasarim_dp_kullanilmadi_der(nr6_yanitlari):
    from tests.test_d37_hibrit_f1 import _t10_varsayilan_satiri
    j = nr6_yanitlari['lox_varsayilan']
    tr, _ = _t10_varsayilan_satiri(j, 'tr', 'tank_pressure')
    en, _ = _t10_varsayilan_satiri(j, 'en', 'tank_pressure')
    assert 'KULLANILMADI' in tr and 'tasarım basınç düşümü oranından' in tr, tr
    assert 'kendi varsayılanını uyguladı' not in tr, tr
    assert '36' in tr and 'P_c·(1 + ΔP/P_c)' in tr, tr
    assert 'NOT used in this run' in en and 'design pressure-drop ratio' in en, en
    assert 'applied its own default' not in en, en


# ---------------------------------------------------------------------------
# Kalem 4 — PANEL-SAYI DEVİR 1: aynı koşuda TEK N2O doyma basıncı
# ---------------------------------------------------------------------------
def _doyma_alanlari(j):
    m = j['motor']
    ox = m['injector_design_detail']['ox_circuit']
    out = {
        'tank_blowdown.initial_pressure_bar':
            m['tank_blowdown']['initial_pressure_bar'],
        'injector_design.feed_pressure_bar':
            m['injector_design']['feed_pressure_bar'],
        'ox_circuit.vapor_pressure_bar': ox['vapor_pressure_bar'],
        'ox_circuit.nhne.p_sat_bar': ox['nhne']['p_sat_bar'],
        'injector.vapor_pressure_bar': j['injector']['vapor_pressure_bar'],
        'oxidizer_tank_pressure_vessel.meop_bar':
            m['oxidizer_tank_pressure_vessel']['meop_bar'],
    }
    k = _tank_kaydi(j)
    if k is not None:
        out['defaults_applied.tank_pressure.used_by_model'] = k['used_by_model']
    return out


@pytest.mark.parametrize('sicaklik', [None, 280.0])
def test_k4_ayni_kosuda_n2o_doyma_basinci_tek_sayi(sicaklik):
    """Önce (olcum/k4_once.json): blowdown/MEOP 50,52509 bar ⟷ enjektör
    devresi 50,54336 bar (tablo ara değeri). Sonra hepsi bit-aynı ve tek
    kaynağın (tank_blowdown.N2OSaturation, CoolProp) değeri."""
    from hrma.analysis.tank_blowdown import N2OSaturation
    g = dict(_sayfa('hybrid'), include_plots=False)
    if sicaklik is not None:
        g['oxidizer_temp'] = sicaklik
    kod, j = _post('/calculate', g)
    assert kod == 200, str(j)[:400]
    alanlar = _doyma_alanlari(j)
    assert len(set(alanlar.values())) == 1, alanlar
    t = j['motor']['oxidizer_inlet_state']['temperature_K']
    assert next(iter(alanlar.values())) == N2OSaturation().psat(t) / 1e5


def test_k4_doyma_kaynagi_tek_kural():
    from hrma.analysis.tank_blowdown import N2OSaturation
    from hrma.engines import injector_design as eng
    from hrma.utils.injector_design import _sat_n2o
    tek = N2OSaturation().use_coolprop
    assert eng._SAT.use_coolprop == tek and _sat_n2o().use_coolprop == tek
    if tek:
        assert 'CoolProp equation of state' in eng.N2O_SATURATION_BASIS



def test_k2_kart_metinleri_sozlukte():
    """Belirsizlik kartının iki yeni gerekçe metni EN + TR sözlükte ve panel
    onları ucun kendi gerekçe kodlarıyla seçer (sayı uydurulmaz)."""
    sozluk = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(
        encoding='utf-8')
    for anahtar in ('panel.uncertainty.notSampledMarch',
                    'panel.uncertainty.zeroSpreadDesignTarget'):
        assert sozluk.count(f"'{anahtar}':") == 2, anahtar
    assert "itki bir tasarım hedefidir" in sozluk
    assert 'bu seviyede örneklenmedi' in sozluk
    panel = (KOK / 'hrma' / 'static' / 'js' / 'panels' /
             'uncertainty_panel.js').read_text(encoding='utf-8')
    assert "o.not_sampled_reason === 'time_march_off_at_this_level'" in panel
    assert "o.zero_spread_reason === 'design_target'" in panel
