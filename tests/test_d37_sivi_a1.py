"""ÖH D37 A2-2 · sivi-sogutma — davranış bekçileri.

Kalemler (kanıt: docs/scofield/raw/OH/A2/sivi-sogutma/a1/):

* **F-17** (CW-F2b + CW-F3) — kanal sığma ölçütü TEK tanım
  (``regen_cooling.channel_fit_limit``): N·(w + s) <= 2·pi·(r_boğaz + t);
  motor ve ``RegenCooling`` aynı geometride aynı hükmü verir; kullanıcı
  sayısı sığmıyorsa kritik uyarı + ``channel_count_fit.status``; form ön-
  dolgusu 80 yok.
* **F-19** (CW-L5) — formda 5 mm cidar ön-dolgusu yok; boş alan gövdeye
  girmez ve çözücü cidarı kendisi boyutlandırır.
* **F-20** (OH-FB-02) — enjektör kalemi çözülemezse bütçenin kalem ve
  toplamları None; yedi tüketici sayı üretmez; normal yol aynı.
* **F-18a** (CW-L4a) — STEP montaj künyesinde kanal beyanı.
* **uc-kapi devri** ``fuel_heat_capacity`` — cp kurucuda çözülür ve
  künyesiyle yayımlanır.

Bekçiler ölçüm yapar (dize aramaz): davranışı bozan mutasyonlar
``a1/mutasyon.md``de listelidir ve her biri burada en az bir testi kırar.
"""
import contextlib
import io
import math
import os
import re
import tempfile

import pytest

os.environ.setdefault('HRMA_PROJECTS_DIR',
                      tempfile.mkdtemp(prefix='hrma-d37-sivi-'))

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIVI_HTML = os.path.join(KOK, 'hrma', 'templates', 'liquid.html')


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _motor(**over):
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    temel = dict(thrust=10000.0, chamber_pressure=100.0, mixture_ratio=2.5,
                 fuel_type='rp1', oxidizer_type='lox')
    for k in ('fuel_type', 'cooling_type'):
        if k in over:
            temel[k] = over.pop(k)
    m = _sessiz(LiquidRocketEngine, overrides=dict(over), **temel)
    _sessiz(m.calculate_nozzle_geometry)
    return m


def _kodlar(motor):
    return [w for w in motor.design_warnings if isinstance(w, dict)]


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


def _sivi(istemci, **govde):
    g = dict(thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
             fuel_type='rp1', oxidizer_type='lox')
    g.update(govde)
    r = _sessiz(istemci.post, '/calculate_liquid', json=g)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# =========================================================================
# F-17 — tek sığma ölçütü
# =========================================================================
@pytest.mark.parametrize('r_gaz,t,w,s', [
    (0.0154, 0.008, 3e-3, 1.5e-3),
    (0.0368, 0.005, 3e-3, 1.5e-3),
    (0.0161, 0.001, 3e-3, 1.5e-3),
    (0.005, 0.0005, 1e-3, 0.889e-3),
    # tam bölünen kenar: c = 10·p
    (10 * 4.5e-3 / (2 * math.pi) - 1e-3, 1e-3, 3e-3, 1.5e-3),
    # Kayan nokta kenarı (arandı, bulundu): c = 189·p iken c/p bölmesi
    # 188,999…'a yuvarlanıyor; düz floor 188 verir, doğru cevap 189'dur
    # (189·p <= c). Düzeltme döngüsü olmadan bu vaka kırmızı.
    (0.09420778962360234, 0.001, 0.0017748943326183907,
     0.0013902283387681876),
])
def test_f17_sigma_siniri_tanimi_saglar(r_gaz, t, w, s):
    """n_max en büyük N'dir ki N·(w+s) <= 2·pi·(r+t) (kayan nokta dâhil)."""
    from hrma.analysis.regen_cooling import channel_fit_limit
    u = channel_fit_limit(r_gaz, t, w, s)
    c = 2.0 * math.pi * (r_gaz + t)
    p = w + s
    assert u['n_max'] * p <= c
    assert (u['n_max'] + 1) * p > c
    assert u['reference_radius_m'] == pytest.approx(r_gaz + t, rel=0, abs=0)
    assert u['pitch_m'] == pytest.approx(p)


@pytest.mark.parametrize('bozuk', [0.0, -1e-3, float('nan'), float('inf'),
                                   None, 'x'])
def test_f17_sigma_siniri_bozuk_girdide_sayi_uydurmaz(bozuk):
    from hrma.analysis.regen_cooling import channel_fit_limit
    with pytest.raises(ValueError):
        channel_fit_limit(0.015, bozuk, 3e-3, 1.5e-3)


def test_f17_varsayilan_kanal_sayisi_sigma_sinirinin_kendisi():
    """Kullanıcı sayı vermezse N = n_max; sınır kanal TABANINDA ölçülür."""
    from hrma.analysis.regen_cooling import (channel_fit_limit,
                                             COOLING_CHANNEL_LAND_M)
    from hrma.engines.liquid_rocket_engine import (
        COOLING_CHANNEL_WIDTH_DEFAULT_M)
    m = _motor()
    n, w, _h, kaynak = m._cooling_channel_geometry()
    t, _ = m._channel_base_wall_thickness()
    beklenen = channel_fit_limit(m.d_t / 2.0, t,
                                 COOLING_CHANNEL_WIDTH_DEFAULT_M,
                                 COOLING_CHANNEL_LAND_M)['n_max']
    assert n == beklenen
    assert w == COOLING_CHANNEL_WIDTH_DEFAULT_M
    assert 'sized by HRMA' in kaynak
    # İç gaz çevresi ölçütü (eski kopya) bu geometride FARKLI sayı verir;
    # motor onu kullanıyorsa bu bekçi kırmızıdır.
    eski = int(math.floor(math.pi * m.d_t
                          / (COOLING_CHANNEL_WIDTH_DEFAULT_M
                             + COOLING_CHANNEL_LAND_M)))
    assert eski != n
    assert m._channel_count_fit['status'] == 'fits'


def test_f17_motor_ve_regen_ayni_geometride_ayni_hukum():
    """İkinci kopya kırmızı: RegenCooling'in kendi uyarısı motorun n_max'ı ile
    birebir aynı sınırda açılır (n_max sığar, n_max + 1 sığmaz)."""
    from hrma.analysis.regen_cooling import RegenCooling
    m = _motor(fuel_type='methane')
    t, _ = m._channel_base_wall_thickness()
    n_max = m._cooling_channel_geometry()[0]
    assert m._channel_count_fit['n_max'] == n_max

    def geometri_uyarisi(n):
        rc = RegenCooling(
            chamber_pressure=100e5, chamber_temperature=3500.0, gamma=1.2,
            molecular_weight=22.0, throat_diameter=float(m.d_t),
            expansion_ratio=5.0, coolant='water', coolant_mdot=1.0,
            coolant_inlet_temp=300.0, coolant_inlet_pressure=150e5,
            n_channels=int(n), channel_width=3e-3, channel_height=2e-3,
            wall_thickness=t, wall_material='copper')
        ozet = _sessiz(rc.solve)['summary']
        return rc.channel_fit, [u for u in ozet.get('warnings', [])
                                if u.startswith('GEOMETRY')]

    fit, uyari = geometri_uyarisi(n_max)
    assert fit['n_max'] == n_max and fit['fits'] and not uyari
    fit, uyari = geometri_uyarisi(n_max + 1)
    assert not fit['fits'] and len(uyari) == 1
    assert str(n_max) in uyari[0]


def test_f17_sigmayan_kullanici_sayisi_adiyla_ve_kritik(istemci):
    d = _sivi(istemci, cooling_channels=80)
    cs = d['cooling_system']
    fit = cs['channel_count_fit']
    assert cs['cooling_channels'] == 80
    assert fit['status'] == 'does_not_fit'
    assert fit['n_max'] < 80
    assert fit['hydraulics_basis']
    # Kanal tabanı çevresi = 2·pi·(r_boğaz + t_sıcak_cidar)
    assert fit['reference_circumference_mm'] == pytest.approx(
        2 * math.pi * (fit['throat_radius_mm']
                       + fit['hot_wall_thickness_mm']), rel=1e-12)
    uy = [w for w in d['input_warnings']
          if w.get('code') == 'warn.liquid.cooling_channels_exceed_fit_limit']
    assert len(uy) == 1 and uy[0]['severity'] == 'critical'
    assert uy[0]['params']['n_max'] == fit['n_max']
    assert uy[0]['params']['c_ref_mm'] == pytest.approx(
        fit['reference_circumference_mm'], abs=0.05)
    # Eski (iç çevre) uyarı kodu artık basılmaz: iki ölçüt yok.
    assert not [w for w in d['input_warnings']
                if w.get('code') == 'warn.liquid.cooling_channels_do_not_fit']


def test_f17_sigan_kullanici_sayisi_uyarisiz(istemci):
    d = _sivi(istemci, cooling_channels=12)
    assert d['cooling_system']['cooling_channels'] == 12
    assert d['cooling_system']['channel_count_fit']['status'] == 'fits'
    assert not [w for w in d['input_warnings']
                if 'cooling_channels' in str(w.get('code'))]


def test_f17_ceketsiz_tipte_sigma_hukmu_yok(istemci):
    d = _sivi(istemci, cooling_type='ablative', cooling_channels=80)
    assert d['cooling_system']['channel_count_fit'] is None
    assert not [w for w in d['input_warnings']
                if 'cooling_channels' in str(w.get('code'))]


def test_f17_kaburga_kanal_tabaninda_turetilir(istemci):
    d = _sivi(istemci)
    cs = d['cooling_system']
    blok = d['cooling_channels']
    c_ref_m = cs['channel_count_fit']['reference_circumference_mm'] / 1000.0
    n = blok['n_channels']
    assert n == cs['cooling_channels']
    assert blok['land_width_m'] == pytest.approx(
        c_ref_m / n - blok['channel_width_m'], rel=1e-12)
    # N = n_max iken kaburga en az tasarım kaburgası kadardır.
    assert blok['land_width_m'] >= cs['channel_count_fit']['land_width_mm'] \
        / 1000.0 - 1e-12


def test_f17_kaburga_kunyesi_kaynagi_dogru_soyler():
    """Değerin kaynağı doğrulanmadı; doğrulanan alt sınır adıyla durur."""
    from hrma.analysis.regen_cooling import (COOLING_CHANNEL_LAND_BASIS,
                                             COOLING_CHANNEL_LAND_M)
    from hrma.engines import liquid_rocket_engine as L
    assert L.COOLING_CHANNEL_LAND_DEFAULT_M is COOLING_CHANNEL_LAND_M
    assert 'NOT VERIFIED' in COOLING_CHANNEL_LAND_BASIS
    assert '0.035 in' in COOLING_CHANNEL_LAND_BASIS
    assert COOLING_CHANNEL_LAND_M * 1000.0 > 0.035 * 25.4


# =========================================================================
# F-17 / F-19 — form ön-dolguları
# =========================================================================
def _girdi_etiketi(html, alan):
    m = re.search(r'<input[^>]*\bid="%s"[^>]*>' % re.escape(alan), html)
    assert m, alan
    return m.group(0)


@pytest.mark.parametrize('alan', ['cooling_channels',
                                  'chamber_wall_thickness'])
def test_f17_f19_form_on_dolgusuz_ve_gonderimde_bos_kalir(alan):
    html = open(SIVI_HTML, encoding='utf-8').read()
    etiket = _girdi_etiketi(html, alan)
    deger = re.search(r'\bvalue="([^"]*)"', etiket)
    assert deger is None or deger.group(1) == '', etiket
    assert 'data-prefilled="none"' in etiket
    # Toplayıcı: boşsa gövdeye KONMAZ (sabit yedek yok).
    toplayici = re.search(r'\b%s:\s*([^\n]+)' % re.escape(alan),
                          html[html.index('function collectAllParameters'):])
    assert toplayici, alan
    assert toplayici.group(1).strip().startswith(
        "liqOptNum('%s')" % alan), toplayici.group(1)
    # Sıfırla: ön-dolguyu geri getirmez.
    for m in re.finditer(r"getElementById\('%s'\)\.value\s*=\s*'([^']*)'"
                         % re.escape(alan), html):
        assert m.group(1) == '', m.group(0)


def test_f19_bos_cidar_boyutlandirilir(istemci):
    d = _sivi(istemci)
    cs = d['structural_analysis']['chamber_structure']
    assert cs['design_mode'] == 'size'
    assert cs['wall_thickness'] >= cs['required_wall_thickness']
    assert 'user input' not in str(cs['wall_thickness_source'])


# =========================================================================
# F-20 — enjektör kalemi çözülemezse sayı yok
# =========================================================================
def _patlat(*_a, **_k):
    raise RuntimeError('kapı DIŞI arıza (bekçi)')


def test_f20_ariza_yolunda_kalem_ve_toplamlar_none():
    m = _motor()
    m.calculate_injector_design = _patlat
    d = _sessiz(m._calculate_feed_system_pressure_drops)
    assert d['injector_drop_status'] == 'not_computed'
    for alan in ('injector', 'total_ox', 'total_fuel',
                 'pump_discharge_pressure_ox', 'pump_discharge_pressure_fuel'):
        assert d[alan] is None, alan
    assert d['oxidizer_line']['injector'] is None
    assert d['fuel_line']['injector'] is None
    # Alt sınır YAYIMLANMIYOR: bayrak alt sınır iddiası taşımaz.
    assert d['feed_budget_is_lower_bound'] is False
    assert 'not_computed' in d['injector_drop_basis']


def test_f20_normal_yolda_toplam_kimligi_ve_anahtarlar():
    d = _sessiz(_motor()._calculate_feed_system_pressure_drops)
    assert d['injector_drop_status'] == 'computed'
    assert d['injector'] > 0.0
    for yan, hat in (('ox', 'oxidizer_line'), ('fuel', 'fuel_line')):
        # V301/L-REJ kalem 7 (NK-36): yakıt hattında rejeneratif ceket
        # kalemi ('regen_jacket') de toplamın bir kalemidir; kimlik "toplam =
        # kalemlerin toplamı" aynen sınanır (oksitleyicide kalem yok).
        kalemler = ('tank_outlet', 'main_valve', 'filters', 'feed_lines',
                    'injector') + (('regen_jacket',)
                                   if 'regen_jacket' in d[hat] else ())
        toplam = sum(d[hat][k] for k in kalemler)
        assert d['total_' + yan] == toplam
        assert d['pump_discharge_pressure_' + yan] == 100.0 + toplam
    assert d['feed_budget_is_lower_bound'] is False
    assert d['feed_budget_lower_bound_fields'] is None
    # Birleşme (main 083762a5, V3 taban-a): gerekçe iki durumda da düzyazı
    # (main'in test_liquid_declarations_v2626::test_beyan_metinleri_bos_degil
    # kararı); hesaplanan yolda 'tasarım değeri, alt sınır değil' der.
    assert 'was computed on this run' in d['feed_budget_lower_bound_basis']


def test_f20_turbopompa_blogu_basma_basinci_yoksa_boyutlanmaz():
    m = _motor(engine_cycle='gas_generator')
    m.calculate_injector_design = _patlat
    m._cycle_result = {'status': 'not_modelled'}
    tp = _sessiz(m._design_turbopump_system, m.mdot_ox, m.mdot_fuel)
    assert tp['status'] == 'not_computed'
    assert tp['oxidizer_pump'] is None and tp['turbine'] is None


def _yalniz_butcede_ariza(monkeypatch):
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    asil = LiquidRocketEngine._calculate_feed_system_pressure_drops

    def sarmal(self):
        self.calculate_injector_design = _patlat
        try:
            return asil(self)
        finally:
            del self.calculate_injector_design
    monkeypatch.setattr(LiquidRocketEngine,
                        '_calculate_feed_system_pressure_drops', sarmal)


def test_f20_uc_arizada_200_ve_tuketiciler_sayi_uretmez(istemci,
                                                         monkeypatch):
    _yalniz_butcede_ariza(monkeypatch)
    d = _sivi(istemci, engine_cycle='pressure_fed')
    pd = d['feed_system']['pressure_drops']
    assert pd['injector_drop_status'] == 'not_computed'
    assert pd['pump_discharge_pressure_ox'] is None
    dfs = d['detailed_feed_system']
    assert dfs['status'] == 'not_computed'
    assert dfs['required_pump_discharge_bar'] is None
    assert dfs['performance_margins'] is None
    assert 'water_hammer' not in dfs and 'valve_feedline' not in dfs


def test_f20_cevrim_basma_basinci_verirse_pompa_zinciri_ondan(istemci,
                                                              monkeypatch):
    """Turbopompalı çevrimde basma basıncı çevrim çözümünden gelir; bütçenin
    enjektör kalemi olmadan da o zincir kendi sayısıyla sürer."""
    _yalniz_butcede_ariza(monkeypatch)
    d = _sivi(istemci, engine_cycle='gas_generator')
    assert d['feed_system']['pressure_drops']['total_ox'] is None
    dfs = d['detailed_feed_system']
    cyc = dfs['engine_cycle_solution']
    assert cyc['status'] == 'converged'
    assert dfs['required_pump_discharge_bar'] is not None


# =========================================================================
# F-18a — STEP künyesi
# =========================================================================
def test_f18a_kanal_beyani_cozucunun_sayisindan():
    from hrma.export.step_export import _cooling_channel_note
    notu = _cooling_channel_note({'cooling_system': {
        'cooling_channels': 32, 'channel_width_mm': 3.0,
        'channel_height_mm': 2.0}})
    assert notu.startswith('cooling_channels: NOT_MODELLED (n=32, '
                           'w=3.00 mm, h=2.00 mm)')
    eksik = _cooling_channel_note({'cooling_system': {
        'cooling_channels': 7}})
    assert 'n=7' in eksik and 'not published (channel_width_mm)' in eksik


@pytest.mark.parametrize('md', [{}, {'cooling_system': {}},
                                {'cooling_system': {'cooling_channels': 0}},
                                {'cooling_system': None}])
def test_f18a_kanal_yoksa_beyan_uretilmez(md):
    from hrma.export.step_export import _cooling_channel_note
    assert _cooling_channel_note(md) is None


# =========================================================================
# uc-kapi devri — fuel_heat_capacity kurucuda çözülür
# =========================================================================
def test_cp_kurucuda_tablodan_ve_kunyeli():
    from hrma.engines.liquid_rocket_engine import (COOLANT_CP_TABLE_J_KGK,
                                                   COOLANT_CP_FALLBACK_J_KGK)
    m = _motor()
    assert m.coolant_cp_J_kgK == COOLANT_CP_TABLE_J_KGK['rp1']
    assert 'table' in m.coolant_cp_source
    k = _motor(fuel_heat_capacity=2500)
    assert k.coolant_cp_J_kgK == 2500.0
    assert k.coolant_cp_source.startswith('user input')
    g = _motor(fuel_type='mmh')
    assert g.coolant_cp_J_kgK == COOLANT_CP_FALLBACK_J_KGK
    assert 'ASSUMED' in g.coolant_cp_source


def test_cp_yayimlanir_ve_toplu_dt_onu_kullanir():
    m = _motor(fuel_heat_capacity=2500)
    c = _sessiz(m.calculate_cooling_requirements)
    assert c['coolant_heat_capacity'] == 2500.0
    assert c['coolant_heat_capacity_source'].startswith('user input')
    # Toplu ΔT = Q_ceket / (ṁ·cp): cp iki katına çıkınca ΔT yarıya iner.
    m2 = _motor(fuel_heat_capacity=5000)
    c2 = _sessiz(m2.calculate_cooling_requirements)
    assert c2['coolant_temperature_rise'] == pytest.approx(
        c['coolant_temperature_rise'] / 2.0, rel=1e-12)


# Denetçi Ş7 (4. tur): iki STEP uçtan uca testi (montaj STEP dosyasının
# KENDİ metni) ``tests/step_d37_sivi_a1.py``ye taşındı. O dosya ``test_*.py``
# desenine uymaz: ana ``pytest tests/`` işi onu TOPLAMAZ (build123d'siz işte
# atlama bütçesine +2 yazılmaz), yalnız ``step-export`` işi adıyla koşar
# (build123d kurulu ve fail-closed). Yama: a1/patch/tests_yml_step_export.patch.


# =========================================================================
# Denetçi şartları (3. tur, 28 Eyl) — bekçi açıkları D1/D2, D5, D6, D11,
# D12 + Ş4(iii)/(iv) + Ş7. Kanıt: a1/mutasyon.md (3. tur bölümü) ve
# a1/sart3/mutasyon_sart3.json (her biri kendi ters mutasyonuyla KIRMIZI,
# md5 eşit).
# =========================================================================
class _KurulanRegen:
    """``RegenCooling`` casusu: marşın GERÇEKTEN kurduğu nesne (kurulum
    reddedilirse de denenen cidar kaydedilir; ``kurulan`` yalnız başarılı)."""

    def __init__(self, monkeypatch):
        import hrma.analysis.regen_cooling as rcmod
        self.kurulan = []
        self.denenen_cidar = []
        asil = rcmod.RegenCooling
        kayit, deneme = self.kurulan, self.denenen_cidar

        class Casus(asil):
            def __init__(self, *a, **kw):
                deneme.append(kw.get('wall_thickness'))
                super().__init__(*a, **kw)
                kayit.append(self)
        monkeypatch.setattr(rcmod, 'RegenCooling', Casus)


# Sabit beklenen değerler (bağımsız): kullanıcı hazne cidarı 6 mm verir.
# RP-1 yolunda kanal tabanı o cidarın dış yüzündedir (model ayrı liner
# taşımaz) -> 6,0 mm; metan/LH2 rejeneratifte süperkritik marşın 1 mm
# liner'ı -> 1,0 mm (REGEN_LINER_THICKNESS_M'nin DEĞERİ burada literal;
# sabit değişirse bu bekçi kırmızıdır, çünkü yayımlanan N değişir).
_CIDAR_MM = 6.0


@pytest.mark.parametrize('yakit,mr,beklenen_mm', [
    ('rp1', 2.5, 6.0),
    ('methane', 3.2, 1.0),
    ('lh2', 6.0, 1.0),
])
def test_d1_d2_sicak_cidar_yakit_yoluna_gore_sabit_deger(istemci, yakit, mr,
                                                        beklenen_mm):
    """D1/D2: RP-1 -> hazne cidarı, metan/LH2 -> 1 mm liner (sabit beklenen)."""
    d = _sivi(istemci, fuel_type=yakit, mixture_ratio=mr,
              chamber_wall_thickness=_CIDAR_MM)
    fit = d['cooling_system']['channel_count_fit']
    assert fit['hot_wall_thickness_mm'] == pytest.approx(beklenen_mm,
                                                         rel=0, abs=1e-12)
    assert fit['reference_radius_mm'] == pytest.approx(
        fit['throat_radius_mm'] + beklenen_mm, rel=1e-12)


@pytest.mark.parametrize('yakit,mr,cidar_mm', [
    # RP-1 marşı ince cidar zarfında koşsun diye 2 mm (6 mm'de marş zarf
    # dışı diye kurulmuyor — F-19 yan etkisi, rapor DEVİR 2).
    ('rp1', 2.5, 2.0),
    ('methane', 3.2, _CIDAR_MM),
])
def test_d1_d2_motor_cidari_marsin_kurdugu_regen_cidari(istemci, monkeypatch,
                                                       yakit, mr, cidar_mm):
    """Uçtan uca: yayımlanan hot_wall_thickness_mm, AYNI yanıtta istasyon
    marşının GERÇEKTEN kurduğu RegenCooling'in wall_thickness'ıdır."""
    casus = _KurulanRegen(monkeypatch)
    d = _sivi(istemci, fuel_type=yakit, mixture_ratio=mr,
              chamber_wall_thickness=cidar_mm)
    fit = d['cooling_system']['channel_count_fit']
    assert len(casus.kurulan) == 1, casus.denenen_cidar
    rc = casus.kurulan[0]
    assert rc.wall_thickness * 1e3 == pytest.approx(
        fit['hot_wall_thickness_mm'], rel=0, abs=1e-12)
    # Aynı geometri: marşın kendi sığma hükmü motorun sınırıyla bire bir.
    assert rc.channel_fit is not None
    assert rc.channel_fit['n_max'] == fit['n_max']
    assert rc.n_channels == d['cooling_system']['cooling_channels']


def test_d5_cp_tablo_degerleri_sabit():
    """D5: 'değerler bit-aynı' iddiasının bekçisi (sabit beklenen)."""
    from hrma.engines.liquid_rocket_engine import COOLANT_CP_TABLE_J_KGK
    assert COOLANT_CP_TABLE_J_KGK == {'rp1': 2090.0, 'lh2': 14300.0,
                                      'methane': 3480.0}
    for yakit, beklenen in (('rp1', 2090.0), ('lh2', 14300.0),
                            ('methane', 3480.0)):
        assert _motor(fuel_type=yakit).coolant_cp_J_kgK == beklenen, yakit


def test_d6_kullanici_n_kaburgasi_kullanici_n_ile_bolunur(istemci):
    """D6: kullanıcı N = 12 (sığıyor, n_max'tan küçük) iken 3B kaburga
    c_ref/12 - w'dir; n_max ile bölünmüş değer DEĞİL."""
    d = _sivi(istemci, cooling_channels=12)
    fit = d['cooling_system']['channel_count_fit']
    blok = d['cooling_channels']
    assert blok['n_channels'] == 12 and fit['n_max'] > 12
    c_ref_m = fit['reference_circumference_mm'] / 1000.0
    assert blok['land_width_m'] == pytest.approx(
        c_ref_m / 12 - blok['channel_width_m'], rel=1e-12)
    assert blok['land_width_m'] != pytest.approx(
        c_ref_m / fit['n_max'] - blok['channel_width_m'], rel=1e-6)


def test_d11_dump_ceketi_modellenmemisken_sigma_blogu_yok(istemci):
    """D11: dump soğutmada ceket modellenmiyor -> channel_count_fit None."""
    d = _sivi(istemci, cooling_type='dump_cooling', cooling_channels=80)
    cs = d['cooling_system']
    assert cs['channel_count_fit'] is None
    assert not [w for w in d['input_warnings']
                if 'cooling_channels' in str(w.get('code'))]


def test_d12_sigmayan_kullanici_n_step_kunyesinde_kullanici_n(istemci):
    """D12: STEP künyesindeki n, KULLANILAN (kullanıcının) N'dir; n_max değil."""
    from hrma.export.step_export import _cooling_channel_note
    d = _sivi(istemci, cooling_channels=80)
    fit = d['cooling_system']['channel_count_fit']
    assert fit['status'] == 'does_not_fit' and fit['n_max'] != 80
    notu = _cooling_channel_note(d)
    assert notu.startswith('cooling_channels: NOT_MODELLED (n=80, '), notu


def test_s4_iv_sigan_durumda_hidrolik_beyani_gercek(istemci):
    """Ş4(iv): sığan durumda hydraulics_basis None değil, >= 20 karakterlik
    ve blokta yayımlanan sayılarla tutarlı bir beyan."""
    d = _sivi(istemci)
    fit = d['cooling_system']['channel_count_fit']
    assert fit['status'] == 'fits'
    beyan = fit['hydraulics_basis']
    assert isinstance(beyan, str) and len(beyan.strip()) >= 20
    n = d['cooling_system']['cooling_channels']
    assert 'these %d channels' % n in beyan
    assert '%.1f mm)' % fit['reference_circumference_mm'] in beyan


def test_s4_iii_kaburga_kurucu_parametresi_degil_modul_sabiti():
    """Ş4(iii): land_width RegenCooling imzasında YOK (uçta bağlı olmayan
    girdi olurdu); nesne modülün tek sabitini kullanır."""
    import inspect
    from hrma.analysis.regen_cooling import (COOLING_CHANNEL_LAND_M,
                                             RegenCooling)
    assert 'land_width' not in inspect.signature(
        RegenCooling.__init__).parameters
    rc = RegenCooling(chamber_pressure=50e5, chamber_temperature=3400.0,
                      throat_diameter=0.05, expansion_ratio=5.0)
    assert rc.land_width == COOLING_CHANNEL_LAND_M


def test_s7_sp8087_sayfasi_ve_coolprop_surumu():
    """Ş7 künye: 'spin liners with milled channels' basılı s. 58'dedir
    (s. 57 değil); cp karşılaştırması CoolProp 6.8.0 ile yapıldı."""
    import io as _io
    import tokenize
    from hrma.analysis.regen_cooling import CHANNEL_FIT_BASIS
    assert 'pp. 1, 26, 58' in CHANNEL_FIT_BASIS
    assert '57' not in CHANNEL_FIT_BASIS
    yol = os.path.join(KOK, 'hrma', 'engines', 'liquid_rocket_engine.py')
    kaynak = open(yol, encoding='utf-8').read()
    yorumlar = [t.string for t in tokenize.generate_tokens(
        _io.StringIO(kaynak).readline) if t.type == tokenize.COMMENT]
    assert any('CoolProp 6.8.0' in y for y in yorumlar)
    assert not any(re.search(r'CoolProp 7\b', y) for y in yorumlar)


_TABAN_IMI = 'the manufacturing minimum, not the pressure, set the thickness'


def test_s2_kunye_imalat_tabani_baglayinca_bunu_soyler(istemci):
    """Ş2: size kipinde cidarı imalat tabanı belirlediyse künye bunu söyler
    (örnek proje sınıfı: basınç tek başına daha ince cidar ister)."""
    from hrma.engines.liquid_rocket_engine import (
        WALL_THICKNESS_MANUFACTURING_MIN_M)
    # L-B (v3.0.1, SV-05): RP-1 rejeneratifte 2 mm cidarda istasyon marşı
    # tepe cidarı erime üstünde çözüyor -> yapı hükmü geri çekilir ve
    # safety_factor_basis tanı metnine döner. Kipe göre kurulan cümle
    # GEÇERLİLİK İÇİ koşumda sınanır: film tipi (1B cidar çözücüsü yok,
    # hüküm beyanlı hedef sıcaklıkta). Kalınlık ve gereksinim zarfı
    # soğutma tipinden bağımsızdır.
    d = _sivi(istemci, chamber_pressure=30, mixture_ratio=2.2,
              cooling_type='film_cooling', film_cooling_percent=5.0)
    cs = d['structural_analysis']['chamber_structure']
    assert cs['design_mode'] == 'size'
    assert cs['model_validity_limit_exceeded'] is False
    # Bağımsız ölçüm: basıncın tek başına istediği kalınlık = p·d/(2·σ_izin)
    # (yanıtın kendi yayımladığı iç basınç [bar], çap [mm], izin [MPa]).
    p_pa = float(cs['internal_pressure']) * 1e5
    d_c = float(cs['chamber_diameter']) / 1000.0
    izin = float(cs['allowable_stress_sizing']) * 1e6
    t_basinc = p_pa * d_c / (2.0 * izin)
    assert t_basinc < WALL_THICKNESS_MANUFACTURING_MIN_M
    assert _TABAN_IMI in cs['safety_factor_basis']
    assert 'the wall was sized so that' in cs['safety_factor_basis']


def test_s2_kunye_basinc_baglayinca_taban_cumlesi_yok(istemci):
    """Karşı durum: 304 / 100 bar'da basınç bağlar (8 mm) — taban cümlesi YOK."""
    d = _sivi(istemci, chamber_material='steel_304')
    cs = d['structural_analysis']['chamber_structure']
    assert cs['design_mode'] == 'size'
    assert cs['required_wall_thickness'] > 2.0
    assert _TABAN_IMI not in cs['safety_factor_basis']


# =========================================================================
# Denetçi şartları (4. tur, 29 Eyl) — Ş2 (Berke §27-18: boğaz eksenel yükü),
# Ş4 (küçük motor fail-closed), Ş5 (imalat tabanı yüklemi), Ş6 (A1/A8, A3,
# A4, A7). Kanıt: a1/sart4/ (her bekçi kendi ters mutasyonuyla KIRMIZI,
# md5 eşit — a1/mutasyon.md 4. tur bölümü).
# =========================================================================
def _ornek_govdesi():
    """Örnek proje (examples/*.hrma) FORM yolu gövdesi — F1'in 'ornek:liquid'
    vakasıyla aynı kurulum (tests.support.form_defaults)."""
    from tests.support import form_defaults
    from tests.test_example_projects import load_example_doc
    alanlar = dict(load_example_doc('liquid')['inputs']['fields'])
    return form_defaults.form_yuku('liquid', alanlar)


@pytest.fixture(scope='module')
def ornek_marssiz(istemci):
    """L-B (v3.0.1, SV-05): ÖRNEK'in film tipli hâli. RP-1 rejeneratif
    örnekte istasyon marşı 2 mm cidarı 2876,6 K çözüyor (erime üstü) ve
    yapı hükmü geri çekiliyor; GEÇERLİLİK İÇİ referans gereken bekçiler
    (FEA hedefi, imalat tabanı cümlesi) aynı geometriyi film tipinde koşar
    (1B cidar çözücüsü yok, hüküm beyanlı 800 K hedefte)."""
    g = _ornek_govdesi()
    g.update(cooling_type='film_cooling', film_cooling_percent=5.0)
    r = _sessiz(istemci.post, '/calculate_liquid', json=g)
    assert r.status_code == 200, r.get_json()
    j = r.get_json()
    assert j['structural_analysis']['chamber_structure'][
        'model_validity_limit_exceeded'] is False
    return j


@pytest.fixture(scope='module')
def ornek(istemci):
    r = _sessiz(istemci.post, '/calculate_liquid', json=_ornek_govdesi())
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _izantropik_izdusum(g, a_lo, a_hi, supersonic):
    """∫ p/P_c d(A/A_t), a_lo..a_hi — BAĞIMSIZ ikinci yol: her alanda Mach
    kökü ayrı çözülür ve basınç sayısal integrallenir (ürünün kapalı biçim
    itki fonksiyonunu KULLANMAZ). Sutton & Biblarz 9. baskı Eş. 3-14."""
    from scipy.integrate import quad
    from scipy.optimize import brentq

    def ar(m):
        return (1 / m) * ((2 / (g + 1)) * (1 + (g - 1) / 2 * m * m)) ** (
            (g + 1) / (2 * (g - 1)))

    def p(a):
        if a <= 1 + 1e-14:
            m = 1.0
        elif supersonic:
            m = brentq(lambda x: ar(x) - a, 1 + 1e-12, 80.0, xtol=1e-14)
        else:
            m = brentq(lambda x: ar(x) - a, 1e-9, 1 - 1e-12, xtol=1e-15)
        return (1 + (g - 1) / 2 * m * m) ** (-g / (g - 1))
    return quad(p, a_lo, a_hi, limit=400, epsabs=1e-13, epsrel=1e-11)[0]


def _bogaz_ikinci_yol(d):
    """Yanıtın yayımladığı geometriden boğaz yükleri, elle (MPa, kN, mm)."""
    cs = d['structural_analysis']['chamber_structure']
    b = cs['throat_meridional_check']
    g, eps, cr = b['gamma'], b['expansion_ratio'], b['contraction_ratio']
    pc = float(cs['internal_pressure']) * 1e5
    r_t = b['throat_radius_mm'] / 1e3
    a_t = math.pi * r_t ** 2
    n_asagi = _izantropik_izdusum(g, 1.0, eps, True)
    n_yukari = cr - _izantropik_izdusum(g, 1.0, cr, False)
    p_t = (2 / (g + 1)) ** (g / (g - 1))
    t = cs['wall_thickness'] / 1e3
    s_h = p_t * pc * r_t / t

    def vm(s_m):
        return math.sqrt(s_h * s_h - s_h * s_m + s_m * s_m)
    s_yukari = vm(n_yukari * pc * a_t / (2 * math.pi * r_t * t))
    s_asagi = vm(-n_asagi * pc * a_t / (2 * math.pi * r_t * t))
    s_eq = max(s_yukari, s_asagi)
    # L-B (v3.0.1, SV-05): gereken kalınlık BOYUTLANDIRMA izin gerilmesiyle
    # (hedef cidar sıcaklığında); allowable_stress artık hükmün (çözülmüş)
    # sıcaklığındadır.
    izin = float(cs['allowable_stress_sizing']) * 1e6
    return {'asagi_kn': n_asagi * pc * a_t / 1e3,
            'yukari_kn': n_yukari * pc * a_t / 1e3,
            'p_t_bar': p_t * pc / 1e5,
            'esdeger_mpa': s_eq / 1e6,
            'esdeger_yukari_mpa': s_yukari / 1e6,
            'esdeger_asagi_mpa': s_asagi / 1e6,
            't_bogaz_mm': s_eq * t / izin * 1e3,
            'sabit_pc_asagi_kn': (eps - 1.0) * pc * a_t / 1e3,
            # Kapalı enjektör ucu − yakınsak izdüşüm, sabit P_c ile:
            # P_c·A_c − P_c·(A_c − A_t) = P_c·A_t (n = 1).
            'sabit_pc_yukari_kn': pc * a_t / 1e3}


@pytest.mark.parametrize('govde', [
    None,                                    # ÖRNEK (examples/liquid)
    {},                                      # 10 kN / 100 bar RP-1
    {'chamber_material': 'steel_304'},       # hazne çemberi bağlar
    {'thrust': 250000, 'chamber_pressure': 20},
], ids=['ornek', '10kN-100bar', 'ss304', '250kN-20bar'])
def test_s2_bogaz_eksenel_yuk_ikinci_yol(istemci, ornek, govde):
    """Ş2: boğaz eksenel zar kuvveti (iki serbest cisim), boğaz statik
    basıncı, eşdeğer gerilme ve gereken kalınlık BAĞIMSIZ integralle aynı."""
    d = ornek if govde is None else _sivi(istemci, **govde)
    cs = d['structural_analysis']['chamber_structure']
    b = cs['throat_meridional_check']
    assert b['status'] == 'evaluated'
    e = _bogaz_ikinci_yol(d)
    assert b['meridional_force_downstream_kn'] == pytest.approx(
        e['asagi_kn'], rel=1e-7)
    assert b['meridional_force_upstream_kn'] == pytest.approx(
        e['yukari_kn'], rel=1e-7)
    assert b['throat_static_pressure_bar'] == pytest.approx(
        e['p_t_bar'], rel=1e-12)
    assert b['equivalent_stress'] == pytest.approx(e['esdeger_mpa'],
                                                   rel=1e-7)
    assert b['required_wall_thickness'] == pytest.approx(e['t_bogaz_mm'],
                                                         rel=1e-7)
    assert cs['required_wall_thickness_throat'] == pytest.approx(
        e['t_bogaz_mm'], rel=1e-7)
    # Karşılaştırma bandı (üst sınır): sabit-P_c yükü (ε − 1)·P_c·A_t ve
    # yukarı akımda P_c·A_t.
    assert b['constant_pc_meridional_force_downstream_kn'] == pytest.approx(
        e['sabit_pc_asagi_kn'], rel=1e-12)
    assert b['constant_pc_to_isentropic_equivalent_ratio'] > 1.0
    # 5. tur Ş2 (denetçi X3/X5/X6): yayımlanan üç alan da bağımsız yoldan.
    # (a) bağlayan serbest cisim = iki eşdeğer gerilmenin BÜYÜĞÜ (bant:
    # etiketin dönmesi için iki gerilme 1e-7'den yakın olmamalı).
    assert abs(e['esdeger_yukari_mpa'] - e['esdeger_asagi_mpa']) > (
        1e-6 * e['esdeger_mpa'])
    assert b['governing_free_body'] == (
        'upstream' if e['esdeger_yukari_mpa'] >= e['esdeger_asagi_mpa']
        else 'downstream')
    # (b) boğaz SF'si = sıcak cidarda düşürülmüş AKMA / eşdeğer gerilme
    # (izin verilen gerilme DEĞİL — o zaten hedef SF'yi içerir).
    assert b['safety_factor'] == pytest.approx(
        float(cs['yield_strength_at_wall_temp']) / e['esdeger_mpa'],
        rel=1e-7)
    # (c) sabit-P_c yukarı akım kuvveti = P_c·A_t.
    assert b['constant_pc_meridional_force_upstream_kn'] == pytest.approx(
        e['sabit_pc_yukari_kn'], rel=1e-12)


def test_s2_sabit_pc_bandi_fea_yukunu_iddia_etmez(ornek):
    """Karar §28-18 (B): sabit-P_c bandının künyesi bir ÜST SINIR
    karşılaştırmasıdır; FEA'nın yükünü iddia etmez (FEA yükünü kendi
    fea.load_model'inde yazar — fea-yuk ile birlikte birleşince 'FEA lüle
    boyunca P_c uygular' cümlesi yanlış olurdu)."""
    b = ornek['structural_analysis']['chamber_structure'][
        'throat_meridional_check']
    metin = b['constant_pc_basis']
    assert 'upper-bound comparison' in metin
    assert 'fea.load_model' in metin
    assert 'applies the chamber pressure' not in metin
    assert 'expected until the FEA load' not in metin


def test_s2_gereksinim_zarfi_ve_etiketi(istemci, ornek):
    """Ş2: gereken kalınlık = max(hazne çemberi, boğaz eşdeğeri, taban)."""
    from hrma.engines.liquid_rocket_engine import (
        WALL_THICKNESS_MANUFACTURING_MIN_M)
    taban = WALL_THICKNESS_MANUFACTURING_MIN_M * 1e3
    for d in (ornek, _sivi(istemci, chamber_material='steel_304')):
        cs = d['structural_analysis']['chamber_structure']
        bilesen = {'chamber_hoop': cs['required_wall_thickness_hoop'],
                   'throat_meridional': cs['required_wall_thickness_throat'],
                   'manufacturing_floor': taban}
        assert cs['required_wall_thickness'] == pytest.approx(
            max(bilesen.values()), rel=1e-12)
        assert cs['required_wall_thickness_governing'] == max(
            bilesen, key=bilesen.get)
        # Hazne çemberi bileşeni bağımsız: p·d/(2·σ_izin).
        assert cs['required_wall_thickness_hoop'] == pytest.approx(
            float(cs['internal_pressure']) * 1e5 * cs['chamber_diameter']
            / (2.0 * float(cs['allowable_stress_sizing']) * 1e6), rel=1e-9)


def test_s2_zarf_bogaz_baglayinca_kalinligi_o_belirler(monkeypatch):
    """Zarfın KENDİSİ: boğaz gereksinimi en büyük bileşen olursa çizilen
    levha ondan seçilir ve etiket 'throat_meridional' olur. (İzantropik
    yükle boğaz bugünkü HRMA yapılandırmalarında BAĞLAMIYOR — ölçüldü,
    a1/sart4/; bu yüzden zarf burada doğrudan sınanır.)"""
    m = _motor()
    asil = m._throat_meridional_check

    def sisik(p_int, allowable):
        k = dict(asil(p_int, allowable))
        assert k['status'] == 'evaluated'
        k['required_thickness_m'] = 0.0123
        return k
    monkeypatch.setattr(m, '_throat_meridional_check', sisik)
    s = m._structural_design()
    assert s['required_thickness_m'] == pytest.approx(0.0123, rel=1e-12)
    assert s['thickness_m'] == pytest.approx(0.015, rel=1e-12)
    assert s['requirement_governing'] == 'throat_meridional'
    assert s['manufacturing_floor_governs'] is False


def _fea(istemci, d):
    r = _sessiz(istemci.post, '/api/fea/structural',
                json={'motor_results': d})
    assert r.status_code == 200, r.get_json()
    return r.get_json()['fea']


def test_s2_ornek_fea_fiziksel_yukte_hedefi_saglar(istemci, ornek_marssiz):
    """Ş2 FEA ikinci yolu: ÖRNEK'in HRMA boyutlu cidarı (2,00 mm), AYNI FEA
    çözücüsünde fiziksel yükle (izantropik P(x)) min SF >= 1 ve >= hedef
    (ölçüldü 29 Eyl: 2,630 ⟷ hedef 2,5; sabit P_c yüküyle 0,819).

    SADELEŞTİ (fea-yuk 2. tur, 14 Eki; karar §28-18 (B), kart OH-DK-04):
    bu test eskiden FEA iç yüzey yükünü yalnız kendi içinde izantropiğe
    çeviren bir yamayla (``_izantropik_fea_yuku`` → ``_add_edge_pressure``)
    koşuyordu. Ürün artık iç yükü kendisi izantropik kuruyor (tutarlı
    Gauss yükü) ve yama ürünün sayısına ULAŞMIYORDU: yamalı/yamasız min SF
    bit-aynı 3,6294805605792457 (ölçüldü; docs/scofield/raw/OH/V3/fea-yuk/
    kanit/tur2/yama_etkisiz.json). Yama kaldırıldı; test ürünün
    yük modelini DOĞRUDAN sınar: dağılım izantropik, γ motorun kendi
    yayımladığı γ, kuvvet dengesi tutuyor. Beklenti (SF >= 1 ve >= hedef)
    DEĞİŞMEDİ; ters mutasyon (eski sabit P_c yükü) bu düğümü KIRMIZI yapar
    (0,819 < 1)."""
    # L-B (v3.0.1, SV-05): ölçüldü — RP-1 rejeneratif örnekte FEA artık
    # çözülmüş 2876,6 K cidar akmasını alıyor (min SF 1,458 < hedef 2,5);
    # örnek geçerlilik dışı. Yük modeli bekçisi geçerlilik içi ikizde.
    ornek = ornek_marssiz
    cs = ornek['structural_analysis']['chamber_structure']
    f = _fea(istemci, ornek)
    lm = f.get('load_model') or {}
    assert lm.get('distribution') == 'isentropic_1d', lm.get('distribution')
    assert lm.get('gamma') == pytest.approx(float(ornek['gamma']),
                                            rel=1e-12)
    assert (lm.get('force_balance') or {}).get('holds') is True
    sf = f['scalars']['min_safety_factor']
    assert sf is not None and sf >= 1.0
    assert sf >= cs['safety_factor']


def test_s2_ornek_fea_zinciri_min_sf_en_az_1(istemci, ornek):
    """Ş2 (denetçi bekçisi): ÖRNEK FEA zinciri min SF >= 1.

    Karar §28-18 (B), 5. tur: 4. turdaki strict xfail SÖKÜLDÜ. FEA yük
    modeli (izantropik P(x) + kapalı uç kuvveti; dalga37/v3-fea-yuk,
    OH-DK-04) bu dalla BİRLİKTE birleşir — bu yüzden bu dal TEK BAŞINA
    (FEA hâlâ sabit P_c, min SF 0,819) bu testte KIRMIZIDIR ve fea-yuk'tan
    ÖNCE birleşmez. Birleşik ağaçta (bu dal ⊕ fea-yuk, ölçüldü 14 Eki,
    a1/sart5/fea/) min SF 3,629 ve kuvvet dengesi tutuyor.

    FEA'nın min SF'si ASME VIII-2 elastik yolunun oranıdır: akma /
    max(1,5·P_m, P_L+P_b) (``hrma.fea.structural_axisym``, ASME_MEMBRAN_KATI);
    1 geçme sınırıdır. Motorun hedef SF'si (çember gerilmesi ⟷ akma) bu
    ölçekte membran için hedef/1,5'e karşılık gelir.
    """
    f = _fea(istemci, ornek)
    lm = f.get('load_model') or {}
    assert lm.get('distribution') == 'isentropic_1d', (
        'FEA iç yüzey yükü izantropik değil (load_model yok ya da sabit '
        'P_c): bu dal dalga37/v3-fea-yuk ile birlikte birleşir, karar '
        '§28-18 (B)', lm.get('distribution'))
    assert (lm.get('force_balance') or {}).get('holds') is True
    assert f['scalars']['min_safety_factor'] >= 1.0


# ---- Ş4: küçük motor, HRMA en az COUNT_MIN kanalı sığdıramıyor ----------
def test_s4_kucuk_motor_kanal_sayisi_uydurulmaz(istemci):
    """metan/LOX 100 N / 100 bar rejeneratif, kanal alanı boş: n_max 3 <
    COUNT_MIN 4. N yayımlanmaz, ceket hidroliği ve yakıt tankı basıncı
    hesaplanmaz, künye/uyarı 'entered/girilen' DEMEZ."""
    from hrma.engines.liquid_rocket_engine import COOLING_CHANNEL_COUNT_MIN
    d = _sivi(istemci, thrust=100, chamber_pressure=100, mixture_ratio=3.2,
              fuel_type='methane', cooling_type='regenerative')
    cs = d['cooling_system']
    fit = cs['channel_count_fit']
    assert fit['n_max'] < COOLING_CHANNEL_COUNT_MIN == fit['n_min']
    assert fit['status'] == 'not_sized' and fit['n_used'] is None
    assert cs['cooling_channels'] == 0
    for alan in ('coolant_velocity', 'coolant_reynolds',
                 'cooling_pressure_drop'):
        assert cs[alan] is None, alan
    assert cs['jacket_hydraulics_status'] == 'not_computed'
    assert d['injection_system']['required_fuel_tank_pressure'] is None
    for metin in (fit['hydraulics_basis'], cs['channel_count_source']):
        assert 'entered' not in metin and 'sized by HRMA' not in metin
    kodlar = [w for w in d['input_warnings']
              if 'cooling_channels' in str(w.get('code'))]
    assert [(w['code'], w['severity']) for w in kodlar] == [
        ('warn.liquid.cooling_channels_min_count_does_not_fit', 'critical')]
    assert kodlar[0]['params']['n_max'] == fit['n_max']
    assert kodlar[0]['params']['n_min'] == COOLING_CHANNEL_COUNT_MIN


# ---- Ş5: imalat tabanı cümlesinin yüklemi ------------------------------
def _taban_cumlesi_var(cs):
    return _TABAN_IMI in cs['safety_factor_basis']


def test_s5_taban_ornekte_levhayi_degistirir(ornek_marssiz):
    """ÖRNEK: basınç gerilmeleri 1,0 mm levhayla karşılanır, çizilen 2,0 mm
    → taban levhayı DEĞİŞTİRDİ, cümle VAR. (L-B: geçerlilik içi ikizde —
    rejeneratif örnekte hüküm geri çekildiği için künye tanı metnidir.)"""
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    cs = ornek_marssiz['structural_analysis']['chamber_structure']
    t_yapi = max(cs['required_wall_thickness_hoop'],
                 cs['required_wall_thickness_throat']) / 1e3
    std, _ = LiquidRocketEngine._next_standard_plate_m(t_yapi)
    assert std * 1e3 < cs['wall_thickness']
    assert cs['manufacturing_floor_changed_plate'] is True
    assert _taban_cumlesi_var(cs)


def test_s5_taban_bandinda_levha_ayni_cumle_yok(istemci):
    """inconel 718, 100 kN / 70 bar: basınç 1,5-2,0 mm bandında (t 1,763 mm)
    ister, bir üst standart 2,0 mm = çizilen → taban levhayı DEĞİŞTİRMEDİ,
    cümle YOK (eski yüklem t < 2 mm burada yanlış VAR diyordu)."""
    d = _sivi(istemci, thrust=100000, chamber_pressure=70,
              chamber_material='inconel_718')
    cs = d['structural_analysis']['chamber_structure']
    assert 1.5 < cs['required_wall_thickness_hoop'] < 2.0
    assert cs['wall_thickness'] == pytest.approx(2.0, abs=1e-12)
    assert cs['manufacturing_floor_changed_plate'] is False
    assert not _taban_cumlesi_var(cs)


def test_s5_basinc_baglarken_cumle_yok(istemci):
    """304 / 100 bar: basınç 8 mm levhayı seçtirir → cümle YOK."""
    d = _sivi(istemci, chamber_material='steel_304')
    cs = d['structural_analysis']['chamber_structure']
    assert cs['manufacturing_floor_changed_plate'] is False
    assert not _taban_cumlesi_var(cs)


# ---- Ş6 bekçileri ------------------------------------------------------
def test_s6_a1_a8_sigan_kullanici_n_beyani_kendi_sayisi(istemci):
    """A1/A8: kullanıcı N = 12 (sığıyor, n_max'tan küçük): beyan 'these 12
    channels' ve gereken çevre 12 × adım (adım = w + kaburga)."""
    d = _sivi(istemci, cooling_channels=12)
    fit = d['cooling_system']['channel_count_fit']
    assert fit['status'] == 'fits' and fit['n_max'] > 12
    adim = fit['channel_width_mm'] + fit['land_width_mm']
    beyan = fit['hydraulics_basis']
    assert 'these 12 channels' in beyan
    assert '(12 x %.2f mm = %.1f mm of %.1f mm)' % (
        adim, 12 * adim, fit['reference_circumference_mm']) in beyan


def test_s6_a3_film_sogutmada_sigmayan_n_kritik(istemci):
    """A3 — L-B (v3.0.1, SV-08) ile SÖZLEŞME DEĞİŞTİ: film tipinde
    rejeneratif ceket YOKTUR (FILM_COOLING_NO_JACKET_BASIS), dolayısıyla
    kanal sığma hükmü de yoktur. Eski beklenti (film + N = 80 → kritik
    exceed_fit_limit) var olmayan bir ceketin kanalına hüküm veriyordu.
    Rejeneratif tipte aynı hüküm aşağıdaki karşı ölçümde DURUR."""
    d = _sivi(istemci, cooling_type='film_cooling', cooling_channels=80)
    cs = d['cooling_system']
    assert cs['channel_count_fit'] is None
    assert cs['regenerative_jacket_status'] == 'NOT_APPLICABLE'
    assert not [w for w in d['input_warnings'] if w.get('code')
                == 'warn.liquid.cooling_channels_exceed_fit_limit']
    r = _sivi(istemci, cooling_type='regenerative', cooling_channels=80)
    uy = [w for w in r['input_warnings'] if w.get('code')
          == 'warn.liquid.cooling_channels_exceed_fit_limit']
    assert len(uy) == 1 and uy[0]['severity'] == 'critical'
    assert uy[0]['params']['n'] == 80


def test_s6_a4_step_kunyesi_derinligi_yayimlanan_derinlik(istemci):
    """A4: derinliğin OTO-boyutlandığı vakada (kullanıcı N = 4) STEP
    künyesindeki h, yayımlanan channel_height_mm'dir (sabit 2,00 değil)."""
    from hrma.export.step_export import _cooling_channel_note
    d = _sivi(istemci, cooling_channels=4)
    cs = d['cooling_system']
    assert cs['channel_height_auto_sized'] is True
    assert cs['channel_height_mm'] > 2.0 + 1e-6
    notu = _cooling_channel_note(d)
    assert 'h=%.2f mm)' % cs['channel_height_mm'] in notu, notu


# L-B (v3.0.1, SV-08): film tipinde ceket yok (channel_count_fit None);
# yüklem yalnız ceketli tipte sınanır.
@pytest.mark.parametrize('sogutma', ['regenerative'])
@pytest.mark.parametrize('yakit,mr', [('rp1', 2.5), ('methane', 3.2),
                                      ('lh2', 6.0)])
def test_s6_a7_kanal_cidari_ve_superkritik_mars_ayni_yuklem(
        istemci, monkeypatch, sogutma, yakit, mr):
    """A7: sığma ölçütünün cidarı liner İSE süperkritik marş koşar, değilse
    koşmaz (iki kapı tek yüklemden: _supercritical_march_applies)."""
    from hrma.engines import liquid_rocket_engine as lre
    cagri = []
    asil = lre.LiquidRocketEngine._solve_supercritical_regen

    def casus(self, *a, **kw):
        cagri.append(1)
        return asil(self, *a, **kw)
    monkeypatch.setattr(lre.LiquidRocketEngine, '_solve_supercritical_regen',
                        casus)
    d = _sivi(istemci, fuel_type=yakit, mixture_ratio=mr,
              cooling_type=sogutma, chamber_wall_thickness=6.0)
    fit = d['cooling_system']['channel_count_fit']
    liner = fit['hot_wall_thickness_mm'] == pytest.approx(
        lre.REGEN_LINER_THICKNESS_M * 1e3, abs=1e-12)
    assert liner == bool(cagri), (sogutma, yakit, fit['hot_wall_thickness_mm'],
                                  len(cagri))
    assert liner == (sogutma == 'regenerative' and yakit != 'rp1')


# =========================================================================
# 5. tur (14 Eki) — denetçi Ş2 bekçi açıkları (X11, X12, X16), çevrim
# dengesinin sessiz hatası (DEVİR) ve §28-31 (c) regen TEK EŞİK.
# Ters mutasyonlar: a1/mutasyon.md "5. tur".
# =========================================================================
_KUCUK = dict(thrust=100, chamber_pressure=100, mixture_ratio=3.2,
              fuel_type='methane', cooling_type='regenerative')


def test_s4_kucuk_gg_motorda_cevrim_dengesi_cozulmez(istemci):
    """Ş4 (X11): ceket ΔP'si hesaplanmadıysa (not_computed) gaz jeneratörlü
    çevrim dengesi ΔP'yi 0 sayıp KAPANMAZ; neden ceket durumunu adıyla
    anar."""
    d = _sivi(istemci, engine_cycle='gas_generator', **_KUCUK)
    assert d['cooling_system']['jacket_hydraulics_status'] == 'not_computed'
    ecs = d['detailed_feed_system']['engine_cycle_solution']
    assert ecs['status'] == 'not_modelled', ecs.get('status')
    assert 'jacket_hydraulics_status' in ecs['reason']


def test_s4_kucuk_basinc_beslemeli_motorda_en_buyuk_tank_basinci_yok(
        istemci):
    """Ş4 (X12): yakıt tankı basıncı hesaplanmadıysa (None) en büyük tank
    basıncı da yayımlanmaz — yalnız oksitleyiciden gelen kısmi bir sayı
    'max' diye basılmaz."""
    d = _sivi(istemci, engine_cycle='pressure_fed',
              feed_system_type='pressure_fed', **_KUCUK)
    assert d['injection_system']['required_fuel_tank_pressure'] is None
    # V301/L-A (SV-03) — BEKLENTİ DEĞİŞTİ: gerekli tank basıncı TEK tanımdır
    # (engine_cycle_solution.required_tank_pressure_*); çevrim çözümü bu
    # koşuda sayı yayımlamadığı için oksitleyici tarafı da kısmi bir toplamla
    # (Pc + ΔP + 8 bar pay, hat kaybı yok) doldurulmaz. Basınç beslemeli
    # çevrimin pompa bloğu artık tank basıncı hiç yayımlamaz.
    assert d['injection_system']['required_ox_tank_pressure'] is None
    assert 'max_tank_pressure' not in d['turbopump_system']


def test_s5_dogrulama_kipinde_taban_bayragi_yok(istemci):
    """Ş5 (X16): cidarı KULLANICI verdiğinde (doğrulama kipi, 5 mm) imalat
    tabanı seçilen levhayı DEĞİŞTİRMEMİŞTİR — levhayı HRMA seçmedi."""
    d = _sivi(istemci, chamber_wall_thickness=5.0)
    cs = d['structural_analysis']['chamber_structure']
    assert cs['design_mode'] == 'verify'
    assert cs['wall_thickness'] == pytest.approx(5.0, abs=1e-12)
    # Bayrak yanlışsa basınç gerilmesinin seçtireceği levha 5 mm'den ince
    # olduğu için True olurdu (yüklem bunu kipten bağımsız ölçüyor).
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    t_yapi = max(cs['required_wall_thickness_hoop'],
                 cs['required_wall_thickness_throat'] or 0.0) / 1e3
    assert LiquidRocketEngine._next_standard_plate_m(t_yapi)[0] * 1e3 < 5.0
    assert cs['manufacturing_floor_changed_plate'] is False
    assert not _taban_cumlesi_var(cs)


def test_devir_cevrim_sogutma_hatasi_sessizce_yutulmaz(monkeypatch):
    """DEVİR ('except Exception: pass'): soğutma çözümü hata verirse çevrim
    ceket ΔP'sini 0 sayıp kapanmaz — çözülmez, hata adıyla yazılır."""
    from hrma.engines import liquid_rocket_engine as lre
    m = _motor(cooling_type='regenerative', engine_cycle='gas_generator')

    def patlar(self, *a, **k):
        raise RuntimeError('sonda: soğutma çözümü çöktü')
    monkeypatch.setattr(lre.LiquidRocketEngine,
                        'calculate_cooling_requirements', patlar)
    out = _sessiz(m._solve_cycle_balance, force=True)
    assert out['status'] == 'not_modelled'
    assert 'RuntimeError' in out['reason'] and 'sonda' in out['reason']


def test_devir_dump_ceketi_dengede_beyanla_tasinir(istemci):
    """DEVİR: dump soğutmada ceket modellenmemiş (NOT_MODELLED, ΔP None).
    Çevrim sayıları eskisiyle BİT-AYNI (ΔP 0) ama dengeye girmeyen terim
    artık beyanla yazılır (önce: TypeError yutuluyordu, beyan yoktu)."""
    d = _sivi(istemci, cooling_type='dump_cooling',
              engine_cycle='gas_generator')
    cs = d['cooling_system']
    assert cs['dump_cooling_jacket_status'] == 'NOT_MODELLED'
    assert cs['cooling_pressure_drop'] is None
    ecs = d['detailed_feed_system']['engine_cycle_solution']
    assert ecs['status'] == 'converged'
    assert 'NOT_MODELLED' in ecs['regen_jacket_dp_basis']
    assert 'lower bound' in ecs['regen_jacket_dp_basis']
    # Rejeneratif koşuda (ΔP hesaplı) beyan yok.
    d2 = _sivi(istemci, cooling_type='regenerative',
               engine_cycle='gas_generator')
    assert 'regen_jacket_dp_basis' not in (
        d2['detailed_feed_system']['engine_cycle_solution'])


def _regen(**over):
    from hrma.analysis.regen_cooling import RegenCooling
    kw = dict(chamber_pressure=20e5, chamber_temperature=3000.0, gamma=1.2,
              molecular_weight=24.0, throat_diameter=0.03,
              expansion_ratio=6.0, coolant='water', coolant_mdot=6.0,
              coolant_inlet_temp=300.0, coolant_inlet_pressure=40e5,
              n_channels=60, channel_width=1.5e-3, channel_height=3.0e-3,
              wall_thickness=1.0e-3, wall_material='cucrzr', n_stations=40,
              coolant_props_source='table')
    kw.update(over)
    return RegenCooling(**kw)


@pytest.mark.parametrize('malzeme', ['copper', 'steel_4130', 'ss_304',
                                     'cucrzr', 'inconel_718'])
def test_28_31c_regen_esikleri_kanonik_merdivenden(malzeme):
    """§28-31 (c): yayımlanan eşikler kanonik merdivenden
    (materials_db.temperature_limits): izin = 'service limit' (aynı
    motorun ısıl koruma künyesiyle aynı sayı), erime = erime; 'service
    limit' ERİME sayısını taşımaz."""
    from hrma.data.materials_db import get_material, temperature_limits
    tl = temperature_limits(get_material(malzeme))
    sm = _regen(wall_material=malzeme).solve()['summary']
    assert sm['material_allowable_temp_K'] == tl['allowable_K']
    assert sm['material_service_limit_K'] == tl['allowable_K']
    assert sm['material_melting_K'] == tl['melting_K']
    assert sm['material_service_limit_K'] < sm['material_melting_K']
    assert sm['wall_temp_margin_K'] == pytest.approx(
        tl['allowable_K'] - sm['max_wall_hot_K'], rel=1e-12)


# V301/L-REJ (26 Eki): su/RP-1 yoluna kanat modeli + Sieder-Tate girdi;
# aynı debide cidar daha soğuk. Bekçinin iddiası (dal ERİŞİLİR) aynı kaldı,
# yalnız dala düşen vaka yeniden seçildi — ölçüldü: copper 1,5 kg/s artık
# 605,5 K (izin altı), 0,6 kg/s 729,8 K (723 < T < 1358); steel_4130
# 1,0 kg/s 1029,8 K (811 < T < erime, değişmeden dalda).
@pytest.mark.parametrize('malzeme,debi,ham_izin', [
    ('copper', 0.6, 1000.0),       # T 729,8 K: ham izinle hüküm YOKTU
    ('steel_4130', 1.0, 1000.0),   # T 1029,8 K: ham izinle yalnız WARNING
])
def test_28_31c_unsafe_dali_erisilir_kanonik_izinde(malzeme, debi, ham_izin):
    """§28-31 (c): UNSAFE dalı artık ERİŞİLİR ve kanonik izin basamağında
    tetiklenir (copper 723 / steel_4130 811 K). Seçilen vakalarda tepe
    cidar kanonik izin ile erime arasında — eski ham eşikle (1000 K /
    erime) copper'da hiç hüküm yoktu, 4130'da yalnız WARNING vardı."""
    from hrma.data.materials_db import get_material, temperature_limits
    tl = temperature_limits(get_material(malzeme))
    sm = _regen(wall_material=malzeme, coolant_mdot=debi).solve()['summary']
    t = sm['max_wall_hot_K']
    assert tl['allowable_K'] < t < tl['melting_K'], t
    hukum = [w for w in sm['warnings']
             if w.split(':')[0] in ('CRITICAL', 'UNSAFE', 'WARNING')]
    assert len(hukum) == 1 and hukum[0].startswith('UNSAFE:'), hukum
    assert f"service limit {tl['allowable_K']:.0f} K" in hukum[0]
    assert str(int(ham_izin)) not in hukum[0].split('service limit')[1]


def test_28_31c_erime_ustunde_critical():
    """§28-31 (c): erime basamağı CRITICAL olarak kalır (inconel 718,
    zayıf soğutma: tepe cidar > 1533 K)."""
    # V301/L-REJ (26 Eki): kanat + Sieder-Tate ile 1,0 kg/s artık 1503,4 K
    # (erime altı, UNSAFE); erime dalına düşen vaka 0,5 kg/s (1590,6 K).
    sm = _regen(wall_material='inconel_718', coolant_mdot=0.5).solve()[
        'summary']
    assert sm['max_wall_hot_K'] > sm['material_melting_K']
    hukum = [w for w in sm['warnings']
             if w.split(':')[0] in ('CRITICAL', 'UNSAFE', 'WARNING')]
    assert len(hukum) == 1 and hukum[0].startswith('CRITICAL:'), hukum


def test_28_31c_regen_ham_esik_alani_okunmaz():
    """§28-31 (c): regen_cooling.py hüküm eşiği için kaydın HAM alanlarını
    OKUMAZ; tek kaynak temperature_limits. AST ile: 'max_service_temperature'
    / 'melting_point' / 'max_service_temp' dize sabitleri modülde hiç geçmez;
    'allowable_temperature' YALNIZ iterasyon başlangıcının yardımcısında
    (_seed_allowable_K — hüküm değil, bayt-aynı tutuldu; gerekçe orada)."""
    import ast
    from hrma.analysis import regen_cooling as rc
    agac = ast.parse(open(rc.__file__, encoding='utf-8').read())
    yasak = {'max_service_temperature', 'melting_point', 'max_service_temp'}
    bulunan = sorted({n.value for n in ast.walk(agac)
                      if isinstance(n, ast.Constant)
                      and isinstance(n.value, str) and n.value in yasak})
    assert bulunan == [], bulunan
    izinli = set()
    for fn in ast.walk(agac):
        if isinstance(fn, ast.FunctionDef) and fn.name == '_seed_allowable_K':
            izinli = {id(n) for n in ast.walk(fn)}
    ham = [n.lineno for n in ast.walk(agac)
           if isinstance(n, ast.Constant) and n.value == 'allowable_temperature'
           and id(n) not in izinli]
    assert izinli and ham == [], ham


def test_28_31c_motor_marsi_ayni_esigi_yayimlar(istemci):
    """§28-31 (c): /calculate_liquid thermal_protection.station_march.
    material_allowable_K kanonik izin (copper_c101 → copper 723 K; marşın
    koşması için ince cidar kullanıcıdan, 2 mm) — aynı motorda ikinci eşik
    yok; hüküm de o eşikten."""
    from hrma.data.materials_db import temperature_limits
    d = _sivi(istemci, chamber_material='copper_c101',
              chamber_wall_thickness=2.0)
    sm = d['thermal_protection']['station_march']
    mat = d['structural_analysis']['chamber_structure']['material_key']
    assert mat == 'copper'
    izin = temperature_limits(mat)['allowable_K']
    assert sm['material_allowable_K'] == izin == 723.0
    if sm['peak_wall_temperature_K'] > izin:
        assert any(w.startswith(('UNSAFE:', 'CRITICAL:'))
                   for w in sm['warnings']), sm['warnings']
