"""V306/HİBRİT-SAYI — hibrit sonuçta her büyüklük tek sayı, her hüküm tek kural.

Mühendis turu (2 Kas 2026) bulguları; ölçümler
``docs/scofield/raw/OH/V306/hibrit-sayi/olcum/`` (önce: ``sayi_once.json``),
rapor ``docs/scofield/raw/OH/V306/hibrit-sayi/RAPOR.md``.

Kalem 1 (M-HIBRIT-5): "Optimumu Bul" ⟷ çözücü kanonu tek tanım.
Kalem 2 (M-HIBRIT-23): optimum araması ve O/F uyarısı tek bant kaynağı.
Kalem 3 (M-HIBRIT-12): c* uyarısı çiftin ölçülmüş η_c* bandından.
"""
import json
import pathlib
import warnings

import pytest

from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parent.parent
TUR = KOK / 'docs/scofield/raw/OH/V306/muhendis-turu/hibrit/vakalar'


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _tur_govde(seviye):
    # Docs'suz yayın dalında (CI) mühendis turu vakası yoktur: kanıt kapısı
    # gerekçeyle atlar (yayin_dali_uret.sh kuru koşusu 'kapı dışı okuma' buldu).
    d = json.loads(kanit_gerekli(TUR / f'{seviye}.json').read_text(encoding='utf-8'))
    return [r for r in d['istekler'] if r['uc'] == '/calculate'][-1]['govde']


def _analizor():
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    return CombustionAnalyzer()


# ---------------------------------------------------------------------------
# Kalem 1 — iki optimum
# ---------------------------------------------------------------------------
def _uc_ve_kanon(istemci, govde):
    opt = {'motor_type': 'hybrid', 'oxidizer': govde['oxidizer_type'],
           'fuel': govde['fuel_type'],
           'chamber_pressure': govde['chamber_pressure']}
    for k in ('expansion_ratio', 'atmospheric_pressure', 'oxidizer_temp',
              'oxidizer_phase'):
        if govde.get(k) not in (None, ''):
            opt[k] = govde[k]
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        r = istemci.post('/api/find-optimum-of', json=opt)
        h = istemci.post('/calculate', json=govde)
    assert r.status_code == 200, r.get_json()
    assert h.status_code == 200, (h.get_json() or {}).get('error')
    return r.get_json(), h.get_json()['motor']


@pytest.mark.parametrize('eps', [None, 5.0], ids=['eslesik_lule', 'sabit_lule'])
def test_k1_optimumu_bul_cozucunun_kanonuyla_ayni_sayi(istemci, eps):
    """ÖLÇÜLDÜ (L1): kutu 7,06 / 229,5 s ve 'çözücü kanonu' 6,30 / 232,3 s
    basıyordu. Aynı girdilerle uç ve çözücü artık AYNI sayıyı yayımlar."""
    govde = dict(_tur_govde('L1'))
    if eps is not None:
        govde['expansion_ratio'] = eps
    uc, motor = _uc_ve_kanon(istemci, govde)
    assert uc['optimum_of_ratio'] == pytest.approx(
        motor['optimum_of_ratio'], rel=1e-9)
    assert uc['max_isp'] == pytest.approx(motor['maximum_isp'], rel=1e-9)
    assert uc['optimum_definition'] == \
        motor['optimum_analysis']['optimum_definition']
    beklenen = ('fixed_expansion_ratio' if eps is not None
                else 'exit_pressure_matched_to_ambient')
    assert uc['optimum_definition']['nozzle'] == beklenen


def test_k1_amac_fonksiyonu_ortamdaki_ideal_isp():
    """Sabit lülede basınç terimi dahil; eşleşik lülede P_e = P_a."""
    from hrma.constants import G_0
    a = _analizor()
    yakit, ox, of, pc, pa, eps = {'htpb': 100.0}, 'n2o', 6.8, 20.0, 1.01325, 6.0
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        r = a.analyze_combustion(yakit, ox, of, pc, expansion_ratio=eps)
        sabit = a.ideal_isp_at_ambient(yakit, ox, of, pc, eps, pa)
        esl = a.ideal_isp_at_ambient(yakit, ox, of, pc, None, pa)
        r_esl = a.analyze_combustion(yakit, ox, of, pc, exit_pressure_bar=pa)
    p_e = r['conditions']['exit']['P']
    assert p_e < pa, 'fikstür aşırı genleşmiş lüle olmalı'
    beklenen = (r['performance']['isp']
                + (p_e - pa) / pc * eps * r['performance']['c_star'] / G_0)
    assert sabit == pytest.approx(beklenen, rel=1e-12)
    assert sabit < r['performance']['isp'], (
        'aşırı genleşmiş lülede momentum Isp iyimserdir; basınç terimi '
        'uygulanmadı')
    assert r_esl['conditions']['exit']['P'] == pytest.approx(pa, rel=1e-6)
    assert esl == pytest.approx(r_esl['performance']['isp'], rel=1e-12)


def test_k1_arayuz_ucuna_tasarim_girdilerini_gonderir():
    s = (KOK / 'hrma/templates/advanced.html').read_text(encoding='utf-8')
    i = s.index('async function findOptimumOF(')
    govde = s[i:s.index('// 3D CAD Functions', i)]
    for alan in ('expansion_ratio', 'atmospheric_pressure', 'oxidizer_temp',
                 'oxidizer_phase'):
        assert f"'{alan}'" in govde, alan
    assert 'getFormData()' in govde


# ---------------------------------------------------------------------------
# Kalem 2 — programın kendi optimumuna "aralık dışı" uyarısı
# ---------------------------------------------------------------------------
def _of_uyarilari(motor_data, combo):
    from hrma.validation.validation_system import ValidationSystem
    return [w for w in ValidationSystem().validate_performance_data(
        motor_data, combo)
        if str(w.get('code', '')).startswith('warn.validation.of_')]


@pytest.mark.parametrize('ox,yakit', [('lox', 'paraffin'), ('lox', 'htpb'),
                                      ('n2o', 'htpb')])
def test_k2_optimum_kendi_uyari_bandinin_icinde(ox, yakit):
    """ÖLÇÜLDÜ (L3 LOX/parafin): optimum 2,48 → "kullanılabilir 4-12
    aralığının dışında" (N2O bandı). Optimum hangi bantta arandıysa uyarı
    o banttır."""
    from hrma.engines.hybrid_rocket_engine import hybrid_of_band
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        opt = _analizor().find_optimum_of_ratio(
            {yakit: 100.0}, ox, 30.0,
            of_range=hybrid_of_band(ox, yakit)['band'],
            expansion_ratio=7.0, ambient_pressure=1.01325)
    md = {'of_ratio': opt['optimum_of_ratio'], 'optimum_analysis': opt}
    assert _of_uyarilari(md, f'{ox}_{yakit}') == []


def test_k2_tabloda_olmayan_cift_n2o_bandini_almaz():
    # Uç tarafında sessiz düşüş kalktı.
    app_kaynak = (KOK / 'hrma/app.py').read_text(encoding='utf-8')
    assert "combo = 'n2o_htpb'" not in app_kaynak
    # LOX/parafin 2,48: kaynaklı bandı yok → arama bandı (1-10) içinde.
    assert _of_uyarilari({'of_ratio': 2.48}, 'lox_paraffin') == []
    dis = _of_uyarilari({'of_ratio': 0.5}, 'lox_paraffin')
    assert [w['code'] for w in dis] == ['warn.validation.of_outside_search_band']
    # N2O çifti kaynaklı bandını korur.
    assert [w['code'] for w in _of_uyarilari({'of_ratio': 2.48}, 'n2o_htpb')] \
        == ['warn.validation.of_out_of_range']


def test_k2_uyari_kosunun_arama_bandini_okur():
    """Tek kaynak: arama stokiyometriğe genişlediyse uyarı da genişler.
    (Ters mutasyon: doğrulayıcı yalnız tabloyu okursa bu bekçi kırmızı.)"""
    md = {'of_ratio': 12.5,
          'optimum_analysis': {'of_range_searched': [1.0, 13.2]}}
    assert _of_uyarilari(md, 'lox_paraffin') == []
    md['of_ratio'] = 13.5
    assert len(_of_uyarilari(md, 'lox_paraffin')) == 1


# ---------------------------------------------------------------------------
# Kalem 3 — kendi aralığındaki η_c*'a KRİTİK
# ---------------------------------------------------------------------------
def _cs_uyarilari(eta, c_th=1537.8, combo='n2o_htpb'):
    from hrma.validation.validation_system import ValidationSystem
    md = {'c_star': eta * c_th, 'c_star_theoretical': c_th,
          'c_star_efficiency': {'eta_c_star': eta}}
    return [w for w in ValidationSystem().validate_performance_data(md, combo)
            if 'cstar' in str(w.get('code', ''))]


def test_k3_olculmus_aralikta_eta_uyari_almaz():
    """ÖLÇÜLDÜ (Carmicino t01): η_c* 0,79 (HRMA aralığı 0,77-0,99) →
    "KRİTİK — c* 1215 m/s, beklenen 1350-1650 m/s"."""
    from hrma.engines.hybrid_rocket_engine import (
        HYBRID_ETA_C_STAR_MEASURED, hybrid_c_star_efficiency_band)
    bant = hybrid_c_star_efficiency_band('n2o', 'htpb')
    assert bant['band'] == tuple(
        HYBRID_ETA_C_STAR_MEASURED[('n2o', 'htpb')]['measured_band'])
    lo, hi = bant['band']
    for eta in (lo, 0.79, 0.89, hi):
        assert _cs_uyarilari(eta) == [], eta


def test_k3_aralik_disi_eta_uyari_ama_kritik_degil():
    from hrma.engines.hybrid_rocket_engine import hybrid_c_star_efficiency_band
    lo, hi = hybrid_c_star_efficiency_band('n2o', 'htpb')['band']
    w = _cs_uyarilari(lo - 0.05)
    assert len(w) == 1
    assert w[0]['code'] == 'warn.validation.cstar_outside_eta_band'
    assert w[0]['severity'] == 'warning'
    assert w[0]['params']['lo'] == round(lo * 1537.8, 0)
    assert w[0]['params']['hi'] == round(hi * 1537.8, 0)


def test_k3_olcumu_olmayan_cift_genel_bandi_kullanir():
    from hrma.engines.hybrid_rocket_engine import (
        HYBRID_ETA_C_STAR_GENERAL, hybrid_c_star_efficiency_band)
    b = hybrid_c_star_efficiency_band('h2o2', 'pe')
    assert b['scope'] == 'all_hybrid_pairs'
    assert b['band'] == tuple(HYBRID_ETA_C_STAR_GENERAL['measured_band'])


# ---------------------------------------------------------------------------
# Kalem 4 — aynı etiketli iki "Yakıt Kütlesi"
# ---------------------------------------------------------------------------
def _sozluk_bloklari():
    d = (KOK / 'hrma/static/js/i18n_common.js').read_text(encoding='utf-8')
    i = d.index('        tr: {')
    return d[:i], d[i:]


def test_k4_yakit_kutlesi_satirlari_adiyla_ayri():
    """ÖLÇÜLDÜ (tur L2): Tasarım Raporu → İtici'de "Yakıt Kütlesi 2,24 kg" ve
    "Yakıt Kütlesi 2,70 kg" (yanan ⟷ artık et dahil yüklenen)."""
    import re
    js = (KOK / 'hrma/static/js/app.js').read_text(encoding='utf-8')
    assert "T('app.rep.fuelMass'," not in js
    # Her alan kendi anahtarıyla basılır.
    for anahtar, alan in (('fuelMassBurned', 'fuel_mass'),
                          ('fuelMassUnburned', 'fuel_mass_residual_kg'),
                          ('fuelMassLoaded', 'fuel_mass_loaded')):
        assert re.search(r"T\('app\.rep\.%s'.*?fieldTag\('%s'\)" % (anahtar, alan),
                         js, re.S), anahtar
    en, tr = _sozluk_bloklari()
    for blok in (en, tr):
        metinler = []
        for anahtar in ('fuelMassBurned', 'fuelMassUnburned', 'fuelMassLoaded'):
            m = re.search(r"'app\.rep\.%s': '([^']+)'" % anahtar, blok)
            assert m, anahtar
            metinler.append(m.group(1))
        assert len(set(metinler)) == 3, metinler
    assert "'app.rep.fuelMass':" not in en + tr


# ---------------------------------------------------------------------------
# Kalem 5 — GÜVENLİK ⟷ BASINÇLI KAP iki basınç merdiveni
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('meop,d_mm', [(20.0, 29.85), (35.0, 385.8)])
def test_k5_iki_sekme_tek_merdiven(meop, d_mm):
    """ÖLÇÜLDÜ (tur L1/L4): GÜVENLİK deneme = hidrostatik = 1,5 × MEOP,
    patlama 2,0 × MEOP; BASINÇLI KAP (S-080) deneme 1,5 × MEOP ama
    "hidrostatik (UG-99b)" 1,3 × MAWP (L4: 54,6 bar). Aynı MEOP, aynı
    katsayılar → aynı üç sayı; hidrostatik test patlama hedefinin altında.
    (Ters mutasyon: bir sekmede katsayı değişirse bu bekçi kırmızı.)"""
    from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
    from hrma.analysis.safety_analysis import SafetyAnalyzer
    g = SafetyAnalyzer()._analyze_pressure_vessel_safety(
        meop, d_mm / 1000.0, 0.005, 'steel_4130')
    k = PressureVesselAnalyzer().analyze(
        meop_bar=meop, inner_diameter_mm=d_mm, material='aluminum_6061',
        code_mode='aiaa_s080')
    for alan in ('proof_pressure_bar', 'hydrostatic_test_pressure_bar',
                 'required_burst_pressure_bar'):
        assert k[alan] == pytest.approx(g[alan], rel=1e-12), alan
    for d in (g, k):
        assert d['hydrostatic_test_pressure_bar'] == d['proof_pressure_bar']
        assert d['hydrostatic_test_pressure_bar'] < d[
            'required_burst_pressure_bar']


def test_k5_asme_kipi_ug99b_korunur():
    from hrma.analysis.pressure_vessel import (
        ASME_HYDRO_FACTOR, PressureVesselAnalyzer)
    k = PressureVesselAnalyzer().analyze(
        meop_bar=60.0, inner_diameter_mm=150.0, material='steel_4130',
        wall_thickness_mm=5.0, code_mode='asme_viii')
    assert k['hydrostatic_test_pressure_bar'] == pytest.approx(
        ASME_HYDRO_FACTOR * k['mawp_bar'], rel=1e-9)
    assert 'UG-99(b)' in k['hydrostatic_test_pressure_basis']


def test_k5_kap_sekmesi_guvenlikle_ayni_satiri_basar():
    js = (KOK / 'hrma/static/js/panels/vessel_panel.js').read_text(
        encoding='utf-8')
    i = js.index('var tekTest')
    blok = js[i:js.index('panel.vessel.requiredBurst', i)]
    assert "d.code_mode !== 'asme_viii'" in blok
    assert "T('panel.safety.pProofHydro'" in blok
    assert "T('panel.safety.pProofHydroTip'" in blok


# ---------------------------------------------------------------------------
# Kalem 7 — form ⟷ sunucu itki sınırı
# ---------------------------------------------------------------------------
def test_k7_form_bantlari_sunucunun_bandi(istemci):
    """ÖLÇÜLDÜ (tur K-9): form 1-100 000 N, sunucu 10-1 000 000 N (oda
    basıncı form 1-100 ⟷ sunucu 1-500 bar). Form bandı sayfaya sunucunun
    kanonundan gelir; şablonda ve istemci denetiminde sayı yazılmaz."""
    import re
    from hrma.validation.motor_validation import CANONICAL_LIMITS
    sayfa = istemci.get('/hybrid').get_data(as_text=True)
    m = re.search(r'<meta name="hrma-hybrid-input-limits" content=\'(\{.*?\})\'>',
                  sayfa)
    assert m, 'bant sayfaya inmedi'
    bant = json.loads(m.group(1))
    for alan in ('thrust', 'chamber_pressure', 'of_ratio', 'burn_time'):
        assert bant[alan] == [CANONICAL_LIMITS[alan]['min'],
                              CANONICAL_LIMITS[alan]['max']], alan
    lo, hi = bant['thrust']
    for kimlik in ('thrust', 'thrust_impulse'):
        el = re.search(r'<input[^>]*id="%s"[^>]*>' % kimlik, sayfa).group(0)
        assert f'min="{lo}"' in el and f'max="{hi}"' in el, el
    sablon = (KOK / 'hrma/templates/advanced.html').read_text(encoding='utf-8')
    i = sablon.index('function validateFormData(')
    govde = sablon[i:sablon.index('return errors;', i)]
    assert '100000' not in govde and '> 100)' not in govde
    # İpucu (EN + TR) sunucunun bandını söyler.
    d = (KOK / 'hrma/static/js/i18n_advanced.js').read_text(encoding='utf-8')
    for anahtar in ('adv.tip.thrustN', 'adv.tip.thrustImpulse'):
        metinler = re.findall(r"'%s': '((?:[^'\\]|\\.)*)'" % re.escape(anahtar), d)
        assert len(metinler) == 2, anahtar
        for t in metinler:
            assert f'{lo}-{hi} N' in t, t
            assert '100000 N' not in t.replace(f'{hi} N', '')


def test_k7_sunucu_bant_disini_adiyla_reddeder(istemci):
    govde = dict(_tur_govde('L1'))
    govde['thrust'] = 1.0e6 + 1
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        r = istemci.post('/calculate', json=govde)
    assert r.status_code == 400
    alan = [f for f in r.get_json()['invalid_fields'] if f['field'] == 'thrust']
    assert alan and alan[0]['accepted_range'] == [10, 1000000]


# ---------------------------------------------------------------------------
# Kalem 6 — termal FEA geçici tepesi denge sıcaklığının üstünde
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def l2_termal(istemci):
    govde = _tur_govde('L2')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        motor = istemci.post('/calculate', json=govde).get_json()['motor']
        wp = istemci.post('/api/analysis/wall-profile',
                          json={'motor_results': motor}).get_json()['wall_profile']
        r = istemci.post('/api/fea/thermal', json={
            'motor_results': motor, 'axial_profile': wp,
            'ambient_temperature_K': 293.15})
    assert r.status_code == 200
    j = r.get_json()
    return (j.get('fea') or j), wp


def test_k6_gecici_tepe_kendi_istasyonunun_dengesini_asmaz(l2_termal):
    """ÖLÇÜLDÜ (tur L2): "denge 3297 K ⟷ geçici tepe 3317 K, fark −20 K".
    Fiziksel: denge BOĞAZ cidarı (z ≈ 52 mm), FEA tepesi konverjan girişte
    (z = 0, M ≈ 0,07); orada geri kazanım sıcaklığı daha yüksek. Adyabatik
    dış yüzlü geçici çözüm kendi istasyonunun geri kazanım sıcaklığını aşmaz
    (en büyük ilkesi: tüm iç yüzey profilin en yüksek T_rec'i altında)."""
    import numpy as np
    fea, wp = l2_termal
    rc = fea['thermal_paths_reconciliation']
    assert rc['equilibrium_station'] == 'throat'
    assert rc['equilibrium_station_x_mm'] == pytest.approx(
        wp['x_throat_mm'], abs=0.5)
    assert rc['fea_peak_x_mm'] < rc['equilibrium_station_x_mm']
    yerel = float(np.interp(rc['fea_peak_x_mm'], wp['x_mm'], wp['T_recovery']))
    assert rc['fea_peak_local_recovery_K'] == pytest.approx(yerel, rel=1e-12)
    assert rc['fea_peak_within_local_recovery'] is True
    assert rc['fea_peak_K'] <= max(wp['T_recovery'])
    # Kusurun kendisi (boğaz dengesi < geçici tepe) bu vakada sürer ve
    # artık NEDENİ yayımlanır.
    assert rc['fea_peak_K'] > rc['equilibrium_K']
    assert 'THROAT' in rc['station_basis']


def test_k6_rozet_istasyonu_ve_nedeni_yazar():
    js = (KOK / 'hrma/static/js/thermal_fea_panel.js').read_text(
        encoding='utf-8')
    i = js.index('function reconciliationBadge(')
    govde = js[i:js.index('\n    }\n', i)]
    for parca in ('rc.fea_peak_x_mm', 'rc.equilibrium_station_x_mm',
                  'rc.fea_peak_local_recovery_K',
                  "'feaT.badgeReconciliationStations'",
                  "'feaT.badgeReconciliationHotterStation'",
                  "'feaT.badgeReconciliationAboveLocal'"):
        assert parca in govde, parca
