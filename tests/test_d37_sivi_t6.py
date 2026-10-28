"""ÖH A2 sivi-sogutma · 6. tur (14 Eki) — v3.0 devirleri, bekçiler.

Kalemler (rapor: docs/scofield/raw/OH/A2/sivi-sogutma/a1/rapor.md
"6. tur (14 Eki) — v3.0 devirleri"):

1. Marş zarfı uyarı kanalı: RP-1 istasyon marşı DENENİP koşmadığında ısıl
   hüküm sessizce düşmez — ``warn.liquid.station_march_not_run`` (EN = TR).
2. Kaynaksız ön-dolgu (F-17 ilkesi): regen paneli N'yi motorun yayımladığı
   ``cooling_system.cooling_channels``tan alır (yoksa boş); ``/api/regen-
   cooling`` n_channels'ı ister (adlı 400).
3. SO1 D-1: CEA KURULU ama çağrı düştüyse köprünün ``fallback_warning``
   kaydı basılır, 'RocketCEA kullanılamıyor' DEĞİL.
4. 'Feed (Ox)' etiketi: pompa basma basıncı yokken çizilen oksitleyici TANK
   basıncı ayrı adla ('Ox Tank (required)', EN = TR).
5. Süperkritik marşta kanal derinliği yayımlanan hızla AYNI yoğunluk
   tabanında (istasyonun yerel T, P'sindeki gerçek akışkan) boyutlanır.
"""
import contextlib
import io
import json
import os
import re
import tempfile

import pytest

os.environ.setdefault('HRMA_PROJECTS_DIR',
                      tempfile.mkdtemp(prefix='hrma-d37-sivi-t6-'))

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _js(yol):
    with open(os.path.join(KOK, yol), encoding='utf-8') as fh:
        return fh.read()


def _i18n_metinleri(dosya, anahtar):
    """Anahtarın dosyadaki bütün değerleri (EN ve TR bloğu sırasıyla)."""
    return re.findall(r"'" + re.escape(anahtar) + r"'\s*:\s*'((?:[^'\\]|\\.)*)'",
                      _js(dosya))


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


def _ornek_govde(**degisiklik):
    """Örnek sıvı proje gövdesi (F1 yayın izinin 'ornek' / 'varyant' kuralı)."""
    from tests.support import form_defaults
    from tests.test_example_projects import load_example_doc
    alanlar = dict(load_example_doc('liquid')['inputs']['fields'])
    alanlar.update(degisiklik)
    return form_defaults.form_yuku('liquid', alanlar)


def _sivi_form(istemci, **degisiklik):
    r = _sessiz(istemci.post, '/calculate_liquid',
                json=_ornek_govde(**degisiklik))
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# =========================================================================
# 1 — marş zarfı uyarı kanalı
# =========================================================================
KOD_MARS = 'warn.liquid.station_march_not_run'


@pytest.fixture(scope='module')
def al_varyanti(istemci):
    # Ölçülen vaka (5. tur §8.3 d): Al 6061 örnekte cidar 50 mm, ince-cidar
    # zarfı marşı reddediyor; önce CRITICAL tepe sıcaklığı hükmü vardı.
    # V3.0.5 T-ÇAPA-C1 — VAKA AÇIKÇA KURULDU (V301/L-KABUK 6f8240043):
    # rejeneratif cidar iki katman; marşın ısıl cidarı ASTARDIR ve astar
    # kalınlığı chamber_wall_thickness (boşsa 1 mm). Eskiden 50 mm yapısal
    # cidar ölçüldüğü için Al 6061 tek başına zarfı aşıyordu; artık aynı
    # vaka 50 mm astarla AÇIKÇA kurulur. ÖLÇÜLDÜ (e038d626f): marş koşmuyor,
    # 'wall_thickness (50.0 mm) is outside the thin-wall envelope …', uyarı
    # kanalında tek kayıt.
    return _sivi_form(istemci, chamber_material='aluminum_6061',
                      chamber_wall_thickness=50)


@pytest.fixture(scope='module')
def ornek(istemci):
    return _sivi_form(istemci)


def test_mars_kosmayinca_hukum_kaybi_uyari_kanalinda_adiyla(al_varyanti):
    tp = al_varyanti['thermal_protection']
    assert 'station_march' not in tp
    durum = tp['station_march_status']
    assert durum.startswith('1D station march not run: ')
    kayitlar = [w for w in al_varyanti['input_warnings']
                if w.get('code') == KOD_MARS]
    assert len(kayitlar) == 1, al_varyanti['input_warnings']
    w = kayitlar[0]
    assert w['severity'] == 'warning'
    # neden künyedeki metnin AYNISI (iki ayrı ifade yok)
    assert w['params']['detail'] == durum[len('1D station march not run: '):]
    assert w['params']['fuel'] == 'rp1'


def test_mars_kostugunda_uyari_yok(ornek):
    tp = ornek['thermal_protection']
    assert 'station_march' in tp
    assert not [w for w in ornek['input_warnings']
                if w.get('code') == KOD_MARS]


def test_mars_uyarisinin_en_tr_metni_var():
    metinler = _i18n_metinleri('hrma/static/js/i18n_common.js', KOD_MARS)
    assert len(metinler) == 2, metinler                   # EN + TR
    for m in metinler:
        assert '{fuel}' in m and '{detail}' in m, m
    assert metinler[0] != metinler[1]                     # TR çevrilmiş


# =========================================================================
# 2 — kaynaksız ön-dolgu: panel N'si ve uçta zorunlu n_channels
# =========================================================================
def _panel(results):
    from tests.test_panel_units_v2626 import _run_harness
    return _run_harness(results, 'liquid')['panels']['cooling']


@pytest.mark.skipif(__import__('shutil').which('node') is None,
                    reason='node kurulu değil')
class TestReganPaneliKanalSayisi:
    def test_tanim_degeri_bos_sayi_yok(self):
        rec = _panel({})
        assert rec['fields']['n_channels'] == ''
        assert 'n_channels' not in rec['suggestions']

    def test_on_dolgu_motorun_yayimladigi_N(self):
        rec = _panel({'cooling_system': {'cooling_channels': 37}})
        assert rec['suggestions']['n_channels'] == 37

    @pytest.mark.parametrize('n', [0, -3, 2.5, '37', None, True])
    def test_gecersiz_N_onerilmez(self, n):
        rec = _panel({'cooling_system': {'cooling_channels': n}})
        assert 'n_channels' not in rec['suggestions'], rec['suggestions']


def _regen_govde(**degisiklik):
    from tests.support.uc_katalogu import KAYITLAR
    g = dict(KAYITLAR['/api/regen-cooling'].yuk)
    g.update(degisiklik)
    return g


def test_uc_n_channels_yoksa_adli_400(istemci):
    g = _regen_govde()
    g.pop('n_channels')
    r = _sessiz(istemci.post, '/api/regen-cooling', json=g)
    assert r.status_code == 400, r.get_json()
    assert "'n_channels' is required" in r.get_json()['error']
    assert 'cooling' not in r.get_json()


@pytest.mark.parametrize('deger', [None, '', 'Infinity', 12.5])
def test_uc_n_channels_gecersizse_400(istemci, deger):
    r = _sessiz(istemci.post, '/api/regen-cooling',
                json=_regen_govde(n_channels=deger))
    assert r.status_code == 400, r.get_json()
    assert 'n_channels' in r.get_json()['error']


def test_uc_n_channels_verilince_200(istemci):
    r = _sessiz(istemci.post, '/api/regen-cooling', json=_regen_govde())
    assert r.status_code == 200, r.get_json()


# =========================================================================
# 3 — SO1 D-1: CEA çağrısı düştüyse doğru neden
# =========================================================================
def _gecerli_validity():
    from hrma.engines import cea_bridge as cb
    return {'fallback_reason': cb.FALLBACK_REASON_CEA_CALL_FAILED,
            'fallback_warning': {'code': cb.WARN_CEA_CALL_FAILED,
                                 'params': {'error': 'RuntimeError'},
                                 'severity': 'warning'}}


def test_d1_kayit_kopruden_aynen():
    from hrma.engines.liquid_rocket_engine import _cea_call_failed_record
    from hrma.engines import cea_bridge as cb
    assert _cea_call_failed_record(_gecerli_validity()) == {
        'code': cb.WARN_CEA_CALL_FAILED, 'params': {'error': 'RuntimeError'},
        'severity': 'warning'}


@pytest.mark.parametrize('bozuk', [
    lambda v: v.update(fallback_reason='other'),
    lambda v: v.pop('fallback_reason'),
    lambda v: v.pop('fallback_warning'),
    lambda v: v.update(fallback_warning='metin'),
    lambda v: v['fallback_warning'].update(code='warn.liquid.x'),
    lambda v: v['fallback_warning'].update(severity='fatal'),
    lambda v: v['fallback_warning'].update(params={'error': 3}),
    lambda v: v['fallback_warning'].update(params={'error': 'x', 'y': 1}),
    lambda v: v['fallback_warning'].update(params=None),
])
def test_d1_bicim_tutmazsa_kayit_yok(bozuk):
    from hrma.engines.liquid_rocket_engine import _cea_call_failed_record
    v = _gecerli_validity()
    bozuk(v)
    assert _cea_call_failed_record(v) is None
    assert _cea_call_failed_record(None) is None


def _motor():
    from tests.test_d37_sivi_a1 import _motor as m
    return m()


@pytest.mark.parametrize('cagri_dustu', [True, False])
def test_d1_motor_dogru_uyariyi_basiyor(monkeypatch, cagri_dustu):
    from hrma.engines import cea_bridge as cb
    m = _motor()
    validity = _gecerli_validity() if cagri_dustu else {'note': 'tablo'}

    def sahte(*a, **k):        # test altyapısı: köprünün fallback yanıtı
        return {'source': 'static_table', 'validity': dict(validity)}

    monkeypatch.setattr(cb, 'get_combustion_properties', sahte)
    m.design_warnings = []
    _sessiz(m._resolve_combustion_reference, None)
    kodlar = [w['code'] for w in m.design_warnings]
    if cagri_dustu:
        assert cb.WARN_CEA_CALL_FAILED in kodlar, kodlar
        assert 'warn.liquid.rocketcea_unavailable' not in kodlar, kodlar
    else:
        assert 'warn.liquid.rocketcea_unavailable' in kodlar, kodlar
        assert cb.WARN_CEA_CALL_FAILED not in kodlar, kodlar


# =========================================================================
# 4 — 'Feed (Ox)' etiketi tank basıncını pompa çıkışıyla karıştırmaz
# =========================================================================
ETIKET_TANK = 'Ox Tank (required)'


def _basinc_etiketleri(motor_data):
    from plotly.subplots import make_subplots
    from hrma.visualization.visualization import _perf_panels_liquid
    paneller = {p['title']: p for p in
                _perf_panels_liquid(motor_data, {}) if p}
    panel = paneller['Pressure Distribution']
    f = make_subplots(rows=1, cols=1, specs=[[dict(panel['spec'])]])
    panel['draw'](f, 1, 1)
    d = json.loads(f.to_json())['data'][0]
    return list(d['x']), list(d['y'])


def test_tank_basinci_ayri_adla():
    x, y = _basinc_etiketleri({
        'chamber_pressure': 70.0,
        'injection_system': {'required_ox_tank_pressure': 95.5,
                             'ox_pressure_drop': 14.0},
        'feed_system': {'pressure_drops': {}}})
    assert ETIKET_TANK in x and 'Feed (Ox)' not in x, x
    assert y[x.index(ETIKET_TANK)] == pytest.approx(95.5)


def test_pompa_cikisi_feed_ox_kalir():
    x, y = _basinc_etiketleri({
        'chamber_pressure': 70.0,
        'injection_system': {'required_ox_tank_pressure': 5.0,
                             'ox_pressure_drop': 14.0},
        'feed_system': {'pressure_drops': {
            'pump_discharge_pressure_ox': 101.0}}})
    assert 'Feed (Ox)' in x and ETIKET_TANK not in x, x
    assert y[x.index('Feed (Ox)')] == pytest.approx(101.0)


def test_tank_etiketinin_en_tr_karsiligi():
    metinler = _i18n_metinleri('hrma/static/js/i18n_charts.js', ETIKET_TANK)
    assert len(metinler) == 2, metinler
    assert metinler[0] == ETIKET_TANK and metinler[1] != ETIKET_TANK


# =========================================================================
# 5 — süperkritik marş: boyutlandırma ve yayımlanan hız AYNI yoğunlukta
# =========================================================================
@pytest.fixture(scope='module')
def lh2_mars():
    from tests.test_d37_sivi_a1 import _motor as mk
    m = mk(fuel_type='lh2', cooling_type='regenerative')
    n, w, h0, _ = _sessiz(m._cooling_channel_geometry)
    cf = float(m.mdot_fuel)
    march, h, not_ = _sessiz(m._size_supercritical_regen, cf, n, w, h0)
    return dict(m=m, n=n, w=w, h0=h0, cf=cf, march=march, h=h, note=not_)


def test_lh2_yayimlanan_hiz_hedefi_tutuyor_ya_da_tavanda(lh2_mars):
    from hrma.engines import liquid_rocket_engine as L
    v = lh2_mars['march']['summary']['max_coolant_velocity_m_s']
    hedef = L.COOLANT_CHANNEL_TARGET_VELOCITY_MS
    assert (v <= hedef * (1.0 + L.REGEN_MARCH_SIZING_REL_TOL)
            or lh2_mars['h'] >= L.COOLING_CHANNEL_HEIGHT_MAX_M), (
        v, lh2_mars['h'])
    # Bu vakada boyutlandırma GERÇEKTEN çalıştı (sınama boş değil)
    assert lh2_mars['h'] > lh2_mars['h0']
    assert 'SAME density basis' in lh2_mars['note']


def test_lh2_yayimlanan_hiz_yerel_gercek_akiskan_yogunlugunda(lh2_mars):
    """Bağımsız kâhin: en hızlı istasyonun (T, P)'sinde CoolProp
    yoğunluğuyla süreklilik v = ṁ / (N·w·h·ρ). Marş özelliklerini kendi
    entalpi durum noktasından okur; (T, P) yeniden değerlendirmesiyle
    ölçülen fark %0,21 → tolerans %1 (hesaptan önce yazıldı)."""
    import numpy as np
    CP = pytest.importorskip('CoolProp.CoolProp')
    mr = lh2_mars['march']
    v = np.asarray(mr['velocity_m_s'], dtype=float)
    i = int(np.argmax(v))
    rho = CP.PropsSI('D', 'T', float(mr['T_coolant_K'][i]),
                     'P', float(mr['P_coolant_bar'][i]) * 1e5, 'Hydrogen')
    v_kahin = lh2_mars['cf'] / (lh2_mars['n'] * lh2_mars['w']
                                * lh2_mars['h'] * rho)
    assert v[i] == pytest.approx(v_kahin, rel=1e-2)
    assert mr['summary']['max_coolant_velocity_m_s'] == pytest.approx(v[i])


def test_lh2_yanit_derinligi_marsin_derinligi(istemci):
    """Uç: yayımlanan derinlik ve hız aynı marştan (sıvı yoğunluklu sonda
    kararı yayımlanmaz). Örnek gövdenin fuel_density'si 810 kg/m³ (RP-1
    örneği) — eski kodda sonda 11,4 m/s deyip derinliği 2 mm bırakıyordu,
    yayımlanan hız 168,9 m/s idi.

    V301/CI-FİZİK (28 Eki): sözleşme kardeş birim testiyle
    (``test_lh2_yayimlanan_hiz_hedefi_tutuyor_ya_da_tavanda``) AYNI —
    hedef tutar YA DA derinlik tavanındadır ve bu adıyla beyan edilir.
    Eski beklenti koşulsuz "hedef tutar" idi; V301/ÖRNEK (5fa435893,
    27 Eki) örneği yeniden üretince (Pc 70→50, gaz jeneratörü) bu
    varyantta derinlik 1 adımda 10 mm tavanına çıktı, yayımlanan hız
    42,15 m/s (hedef 40 m/s, kabul 40,4). Ürün bunu channel_count_source
    künyesinde söylüyor; 40 m/s HRMA'nın yumuşak tasarım hedefi, sert
    sınır (COOLANT_VELOCITY_LIMIT_MS, uyarı) aşılmıyor."""
    import re as _re
    from hrma.engines import liquid_rocket_engine as L
    j = _sivi_form(istemci, fuel_type='lh2')
    cs = j['cooling_system']
    assert cs['wall_temperature_source'].startswith('solved (1D supercritical')
    v = cs['coolant_velocity']
    kaynak = cs['channel_count_source']
    hedef_tuttu = v <= (L.COOLANT_CHANNEL_TARGET_VELOCITY_MS
                        * (1.0 + L.REGEN_MARCH_SIZING_REL_TOL))
    tavanda = (cs['channel_height_mm']
               >= L.COOLING_CHANNEL_HEIGHT_MAX_M * 1e3 - 1e-9)
    assert hedef_tuttu or tavanda, (v, cs['channel_height_mm'])
    if not hedef_tuttu:
        # Hedef tutmadıysa adıyla beyan: tavana varıldı, hedef tutmadı.
        assert 'depth ceiling was reached before the target was met' \
            in kaynak, kaynak
    assert v < L.COOLANT_VELOCITY_LIMIT_MS
    assert cs['channel_height_auto_sized'] is True
    assert 'SAME density basis' in kaynak
    # Künyedeki son tepe hız yayımlanan hızın KENDİSİ (aynı marş).
    son = _re.search(r'final peak channel velocity ([0-9.]+) m/s', kaynak)
    assert son is not None, kaynak
    assert float(son.group(1)) == pytest.approx(v, abs=0.05)
    assert not [w for w in j['input_warnings']
                if w.get('code') == 'warn.liquid.coolant_velocity_above_limit']


def test_boyutlandirma_adimi_sinirli():
    """Hesap kaynağı sınırı: yeniden çözüm sayısı adlı sabitle sınırlı."""
    import inspect
    from hrma.engines import liquid_rocket_engine as L
    kaynak = inspect.getsource(L.LiquidRocketEngine._size_supercritical_regen)
    assert 'n_iter >= REGEN_MARCH_SIZING_MAX_ITER' in kaynak
    assert isinstance(L.REGEN_MARCH_SIZING_MAX_ITER, int)
    assert 1 <= L.REGEN_MARCH_SIZING_MAX_ITER <= 10
