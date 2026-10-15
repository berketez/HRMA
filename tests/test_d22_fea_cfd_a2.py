# -*- coding: utf-8 -*-
"""ÖH D22 / fea-cfd aşama-2 bekçileri.

Her sınıf bir kalemi kilitler. Ölçüm kanıtı:
``docs/scofield/raw/OH/D22/fea-cfd/a2/once_p8b3.json`` (taban b84b10a) ve
``sonra_p8b3.json``. Ters-mutasyon: ``mutasyon.json``.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('HRMA_HEADLESS', '1')

from hrma.visualization import visualization as V  # noqa: E402


def _fig(s):
    return json.loads(s) if isinstance(s, str) else s


def _gostergeler(f):
    return [t for t in (f.get('data') or []) if t.get('type') == 'indicator']


#: Beyanlı-boş desenin kabul edilen cümleleri (tek kaynak: bu demet).
BEYAN_KALIPLARI = ('not available', 'no data available',
                   'no performance data available')


def _beyan_var(f):
    m = _metin(f).lower()
    return any(k in m for k in BEYAN_KALIPLARI)


def _metin(f):
    parca = []
    lay = f.get('layout') or {}
    for a in (lay.get('annotations') or []):
        if a.get('text'):
            parca.append(str(a['text']))
    t = lay.get('title') or {}
    if isinstance(t, dict) and t.get('text'):
        parca.append(str(t['text']))
    for tr in (f.get('data') or []):
        for k in ('name', 'hovertemplate'):
            if isinstance(tr.get(k), str):
                parca.append(tr[k])
        xs = tr.get('x')
        if isinstance(xs, (list, tuple)):
            parca.extend(str(q) for q in xs)
    return ' | '.join(parca)


REF_EGRI = {'time': [0.0, 1.0, 2.0], 'thrust': [1200.0, 1000.0, 600.0],
            'pressure': [35.0, 30.0, 25.0], 'mass_flow': [0.6, 0.5, 0.4]}


# ---------------------------------------------------------------------------
# P8B3-07 — iğne ölçek taşır
# ---------------------------------------------------------------------------
class TestP8B307IgneOlcekTasir:
    """Ölçüldü (once_p8b3.json): 1 N / 1 kN / 1 MN için iğne kesri
    0,833333 / 0,833333 / 0,833333 — altı mertebe fark eden üç motor
    görsel olarak AYNI. Skala değerin kendisinden türetiliyordu."""

    def test_referanssiz_hucrede_igne_CIZILMEZ(self):
        f = _fig(V.create_real_time_dashboard({'thrust': 1000.0}, None))
        g = _gostergeler(f)
        assert g, 'gösterge hücresi tümden kaybolmuş olamaz'
        for tr in g:
            assert not tr.get('gauge'), (
                'referans serisi yokken iğne çizilmiş: %r' % tr.get('gauge'))
            assert tr.get('mode') == 'number'

    def test_referanssiz_hucrede_sayi_GERCEK_kalir(self):
        f = _fig(V.create_real_time_dashboard({'thrust': 1234.5}, None))
        degerler = [t.get('value') for t in _gostergeler(f)]
        assert 1234.5 in degerler, degerler

    def test_ayni_egride_iki_calisma_noktasi_AYIRT_EDILIR(self):
        kesir = {}
        for itki in (600.0, 1200.0):
            f = _fig(V.create_real_time_dashboard(
                {'thrust': itki, 'thrust_curve': REF_EGRI}, None))
            tr = _gostergeler(f)[0]
            rng = (tr['gauge']['axis'])['range']
            kesir[itki] = tr['value'] / rng[1]
        assert kesir[600.0] != pytest.approx(kesir[1200.0]), kesir
        assert kesir[600.0] == pytest.approx(0.5)
        assert kesir[1200.0] == pytest.approx(1.0)

    def test_tam_skala_COZUCU_serisinden_gelir(self):
        f = _fig(V.create_real_time_dashboard(
            {'thrust': 1000.0, 'chamber_pressure': 30.0,
             'mdot_total': 0.5, 'thrust_curve': REF_EGRI}, None))
        araliklar = [t['gauge']['axis']['range'][1]
                     for t in _gostergeler(f) if t.get('gauge')]
        assert araliklar == [1200.0, 35.0, 0.6], araliklar
        assert 'thrust_curve.thrust peak' in _metin(f)

    def test_olcek_degerin_KENDISINDEN_turetilmez(self):
        """1,2x kuralı geri gelirse bu test kırmızıya döner.

        Tepe BİLEREK 1,2x değildir (1000 -> 2500), yoksa iki kural
        tesadüfen aynı sayıyı verirdi."""
        egri = dict(REF_EGRI, thrust=[2500.0, 1000.0, 600.0])
        f = _fig(V.create_real_time_dashboard(
            {'thrust': 1000.0, 'thrust_curve': egri}, None))
        tr = _gostergeler(f)[0]
        assert tr['gauge']['axis']['range'][1] == pytest.approx(2500.0)
        assert tr['gauge']['axis']['range'][1] != pytest.approx(1000.0 * 1.2)


# ---------------------------------------------------------------------------
# P8B3-08 — boş pano beyan eder
# ---------------------------------------------------------------------------
class TestP8B308BosPanoBeyanEder:
    """Ölçüldü: boş motor_data ile 6 gösterge, hepsi 0,0 ve hiçbir
    'veri yok' cümlesi yoktu (veri_yok_beyani: false)."""

    def test_bos_girdide_SIFIR_BASILMAZ(self):
        f = _fig(V.create_real_time_dashboard({}, None))
        assert _gostergeler(f) == [], 'boş girdide sıfır basan gösterge var'

    def test_bos_girdide_veri_yok_BEYANI_var(self):
        f = _fig(V.create_real_time_dashboard({}, None))
        assert _beyan_var(f), _metin(f)[:300]

    def test_beyan_eksik_alanlari_ADIYLA_sayar(self):
        m = _metin(V.create_real_time_dashboard({}, None)
                   if isinstance(V.create_real_time_dashboard({}, None), dict)
                   else _fig(V.create_real_time_dashboard({}, None)))
        for alan in ('thrust', 'chamber_pressure', 'isp'):
            assert alan in m, (alan, m[:300])

    def test_kismi_veride_yayimlanmayan_alan_BEYAN_edilir(self):
        f = _fig(V.create_real_time_dashboard({'thrust': 900.0}, None))
        m = _metin(f).lower()
        assert _beyan_var(f)
        assert 'isp' in m
        # Yayımlanmayan alanın sayısı UYDURULMAZ (0 basılmaz)
        assert all(t.get('value') is None or t.get('value') == 900.0
                   for t in _gostergeler(f)), \
            [t.get('value') for t in _gostergeler(f)]


# ---------------------------------------------------------------------------
# P8B3-09 — kaynaksız hüküm bandı yok
# ---------------------------------------------------------------------------
class TestP8B309KaynaksizBantYok:
    """Ölçüldü: exit_velocity 60 m/s bir koşuda KIRMIZI (#ff5d73),
    140 m/s skalalı koşuda aynı 60 m/s YEŞİL (#2dd4a8) idi — bant
    sınırları okunan değerle kayıyordu ve hiçbir kaynağa dayanmıyordu."""

    def _gauge(self, hiz):
        from plotly.subplots import make_subplots
        p = V._perf_gauge_panel('Oxidizer Injection Velocity', hiz)
        f = make_subplots(rows=1, cols=1, specs=[[{'type': 'indicator'}]])
        p['draw'](f, 1, 1)
        return json.loads(f.to_json())['data'][0]['gauge']

    def test_bant_yok(self):
        assert not self._gauge(60.0).get('steps')

    def test_esik_cizgisi_yok(self):
        assert 'threshold' not in self._gauge(60.0)

    def test_ayni_hiz_iki_kosuda_ZIT_hukum_ALMAZ(self):
        def renk(g, v):
            for s in (g.get('steps') or []):
                r = s.get('range')
                if r and r[0] <= v <= r[1]:
                    return s.get('color')
            return None
        assert renk(self._gauge(60.0), 60.0) == renk(self._gauge(140.0), 60.0)

    def test_okuma_skalasi_KORUNUR(self):
        assert self._gauge(60.0)['axis']['range'] == [0, 100.0]
        assert self._gauge(140.0)['axis']['range'] == [0, 150.0]

    def test_hibrit_panosu_hala_hiz_gosteriyor(self):
        p = V._perf_panels_hybrid(
            {'chamber_pressure': 20.0, 'mdot_total': 1.0, 'mdot_ox': 0.8,
             'mdot_f': 0.2}, {'exit_velocity': 60.0, 'pressure_drop': 4.0})
        assert 'Oxidizer Injection Velocity' in [q['title'] for q in p]


# ---------------------------------------------------------------------------
# P8B3-10 — verim skalası iğneyi içine alır
# ---------------------------------------------------------------------------
class TestP8B310VerimSkalasi:
    """Ölçüldü: skala [90, 100]'e çiviliydi; eta %85 ve %70 koşularında
    iğne skalanın DIŞINA düşüyordu (2/4 vaka)."""

    def _gauge(self, eta):
        cd = {'performance': {'c_star': 1500.0,
                              'c_star_delivered': 1500.0 * eta},
              'conditions': {'chamber': {'P': 20.0}}}
        f = _fig(V.create_combustion_analysis_plots(cd))
        return _gostergeler(f)[0]

    @pytest.mark.parametrize('eta', [0.70, 0.85, 0.90, 0.99])
    def test_igne_skalanin_ICINDE(self, eta):
        tr = self._gauge(eta)
        lo, hi = tr['gauge']['axis']['range']
        assert lo <= tr['value'] <= hi, (eta, lo, tr['value'], hi)

    def test_esikler_MUTLAK_kalir_deger_ile_KAYMAZ(self):
        """P8B3-09'un tersi hüküm: 95/98 sınırları sabittir."""
        for eta in (0.70, 0.85, 0.99):
            kenarlar = [s['range'][1]
                        for s in self._gauge(eta)['gauge']['steps']]
            assert kenarlar[0] == pytest.approx(95.0), (eta, kenarlar)
            assert kenarlar[1] == pytest.approx(98.0), (eta, kenarlar)

    def test_taban_gereginden_fazla_INMEZ(self):
        assert self._gauge(0.99)['gauge']['axis']['range'][0] == \
            pytest.approx(V.ETA_GAUGE_LO_PCT)

    def test_esikler_TEK_KAYNAKTAN(self):
        assert V.ETA_GAUGE_STEP_EDGES_PCT == (95.0, 98.0)


# ---------------------------------------------------------------------------
# P8B3-15 — yedi üreticinin girdi kapısı TEK politika
# ---------------------------------------------------------------------------
class TestP8B315TekGirdiPolitikasi:
    """Ölçüldü (once_p8b3.json): yedi üretici üç ayrı politika izliyordu —
    create_injector_plot ham KeyError ile ÇÖKÜYOR, create_real_time_dashboard
    altı sıfır BASIYOR, create_motor_plot ise 14 iz / 454 sıfırdan farklı
    sayı ile uydurma bir kesit ÇİZİYORDU (L=300 mm, D=100 mm, dt=20 mm —
    hepsi imzadaki varsayılanlar)."""

    URETICILER = (
        ('create_motor_plot', lambda: V.create_motor_plot({})),
        ('create_injector_plot',
         lambda: V.create_injector_plot({}, 'showerhead')),
        ('create_performance_plots', lambda: V.create_performance_plots({})),
        ('create_heat_transfer_plots',
         lambda: V.create_heat_transfer_plots({})),
        ('create_combustion_analysis_plots',
         lambda: V.create_combustion_analysis_plots({})),
        ('create_structural_analysis_plots',
         lambda: V.create_structural_analysis_plots({})),
        ('create_real_time_dashboard',
         lambda: V.create_real_time_dashboard({}, None)),
    )

    @pytest.mark.parametrize('ad,cagri', URETICILER,
                             ids=[a for a, _ in URETICILER])
    def test_bos_girdi_COKMEZ(self, ad, cagri):
        """Çökmemek YETMEZ: üretici çizilebilir bir şekil DÖNDÜRMELİ.

        ÖH D23 fix-20: bu test yalnız ``cagri()`` çağırıyordu, hiçbir
        iddia taşımıyordu (P13B2-10 iddiasız nüfus). Sessiz ``None``
        dönüşü de kusurdur: kardeş bekçiler (``test_bos_girdi_HIC_IZ_
        CIZMEZ``, ``..._BEYAN_eder``) ``_fig``in bir sözlük döndürmesine
        DAYANIYOR; o sözleşme sınanmadan onların yeşili bir şey
        kanıtlamaz. İddia ekleme kapsamı BÜYÜTMEZ, testin zaten
        varsaydığı şeyi ölçer.
        """
        f = _fig(cagri())
        assert isinstance(f, dict), (ad, type(f).__name__)
        assert 'layout' in f, (ad, sorted(f))

    @pytest.mark.parametrize('ad,cagri', URETICILER,
                             ids=[a for a, _ in URETICILER])
    def test_bos_girdi_HIC_IZ_CIZMEZ(self, ad, cagri):
        f = _fig(cagri())
        assert (f.get('data') or []) == [], (ad, len(f.get('data') or []))

    @pytest.mark.parametrize('ad,cagri', URETICILER,
                             ids=[a for a, _ in URETICILER])
    def test_bos_girdi_BEYAN_eder(self, ad, cagri):
        assert _beyan_var(_fig(cagri())), (ad, _metin(_fig(cagri()))[:200])

    def test_motor_kesiti_UYDURMA_olcu_yazmaz(self):
        m = _metin(_fig(V.create_motor_plot({})))
        for uydurma in ('L = 300.0 mm', 'D = 100.0 mm', 'dt = 20.00 mm',
                        'de = 80.0 mm'):
            assert uydurma not in m, uydurma

    def test_motor_kesiti_eksik_alani_ADIYLA_sayar(self):
        m = _metin(_fig(V.create_motor_plot({'chamber_length': 0.3})))
        assert 'throat_diameter' in m, m[:300]
        assert 'chamber_length' not in m, m[:300]

    def test_enjektor_cizimi_eksik_alani_ADIYLA_sayar(self):
        m = _metin(_fig(V.create_injector_plot({'n_holes': 12},
                                               'showerhead')))
        assert 'hole_diameter' in m, m[:300]

    def test_gecerli_girdide_kesit_HALA_cizilir(self):
        f = _fig(V.create_motor_plot({
            'chamber_length': 0.3, 'chamber_diameter': 0.1,
            'port_diameter_initial': 0.03, 'port_diameter_final': 0.05,
            'throat_diameter': 0.02, 'exit_diameter': 0.08}))
        assert len(f.get('data') or []) > 5

    def test_gecerli_girdide_enjektor_HALA_cizilir(self):
        f = _fig(V.create_injector_plot(
            {'n_holes': 12, 'hole_diameter': 1.5}, 'showerhead'))
        assert len(f.get('data') or []) >= 1


# ---------------------------------------------------------------------------
# P8B3-18 — varsayım künyesi figüre taşınır
# ---------------------------------------------------------------------------
class TestP8B318VarsayimKunyesi:
    """Ölçüldü: çözücü ``filter_note`` ("...assumed loss coefficient K=10")
    ve ``method`` (Crane TP-410) yayımlıyordu ama figürde hiçbiri yoktu
    (kunye_figurde: false)."""

    DROPS = {
        'tank_outlet': 0.05968, 'main_valve': 0.01790, 'filters': 1.19360,
        'feed_lines': 0.41884, 'injector': 11.0,
        'pump_discharge_pressure_ox': 62.690,
        'pump_discharge_pressure_fuel': 61.457,
        'oxidizer_line': {'tank_outlet': 0.05968, 'main_valve': 0.01790,
                          'filters': 1.19360, 'feed_lines': 0.41884,
                          'injector': 11.0},
        'fuel_line': {'tank_outlet': 0.01580, 'main_valve': 0.00474,
                      'filters': 0.31608, 'feed_lines': 0.11997,
                      'injector': 11.0},
        'method': ('Darcy-Weisbach with Haaland friction factor plus local '
                   'loss coefficients (Crane TP-410); the injector item is '
                   'taken from the injector design'),
        'filter_note': ('filter/strainer loss uses an assumed loss '
                        'coefficient K=10'),
    }

    def _fig(self, drops=None):
        md = {'motor_type': 'liquid', 'chamber_pressure': 50.0,
              'feed_system': {'pressure_drops': drops or self.DROPS,
                              'mass_flow_rates': {'total': 3.0,
                                                  'oxidizer': 2.1,
                                                  'fuel': 0.9}},
              'injector_design': {'injection_pressure_drop_ox_bar': 11.0,
                                  'ox_injection_velocity_m_s': 41.4,
                                  'fuel_injection_velocity_m_s': 49.5}}
        return _fig(V.create_performance_plots(md, {}))

    def test_K_degeri_figurde(self):
        assert 'K=10' in _metin(self._fig())

    def test_assumed_kelimesi_figurde(self):
        assert 'assumed' in _metin(self._fig()).lower()

    def test_yontem_kunyesi_figurde(self):
        assert 'Crane TP-410' in _metin(self._fig())

    def test_filters_cubugu_varsayimi_ADINDA_tasir(self):
        etiketler = []
        for tr in (self._fig().get('data') or []):
            xs = tr.get('x')
            if isinstance(xs, (list, tuple)):
                etiketler.extend(str(q) for q in xs)
        assert 'Filters (assumed K=10)' in etiketler, sorted(set(etiketler))

    def test_kunye_YENIDEN_YAZILMAZ_cozucudenden_gelir(self):
        """K değeri koda ikinci kez yazılmaz: çözücü başka söylerse figür
        de başka söyler (tek kaynak FEED_K_FILTER)."""
        d = dict(self.DROPS)
        d['filter_note'] = ('filter/strainer loss uses an assumed loss '
                            'coefficient K=42')
        m = _metin(self._fig(d))
        assert 'K=42' in m and 'K=10' not in m, m[:400]

    def test_kunye_yoksa_UYDURULMAZ(self):
        d = {k: v for k, v in self.DROPS.items()
             if k not in ('filter_note', 'method')}
        m = _metin(self._fig(d))
        assert 'assumed' not in m.lower(), m[:300]
        etiketler = []
        for tr in (self._fig(d).get('data') or []):
            xs = tr.get('x')
            if isinstance(xs, (list, tuple)):
                etiketler.extend(str(q) for q in xs)
        assert 'Filters' in etiketler, sorted(set(etiketler))


# ---------------------------------------------------------------------------
# P8B3-01 / P8B3-03 — ÇÜRÜTÜLDÜ, kapalı hâli kilitlenir
# ---------------------------------------------------------------------------
class TestP8B301ve03Curutuldu:
    """Her iki başlık da bu ağaçta ZATEN kapalıydı (commit a419179,
    ÖH D15 fea-viz a2 / P8B3-02). Bekçi, kapanışın geri alınmadığını
    kilitler: KeyError 'cycles' yok, sabit 'Min SF: 2.0' çizgisi yok."""

    def test_yapisal_pano_bos_sozlukte_COKMEZ(self):
        """Boş sözlükte KeyError yok — ve dönen şey çizilebilir bir şekil.

        ÖH D23 fix-20: iddiasızdı (P13B2-10). Kapanışın geri alınmadığını
        kilitlemek için çökmemek yetmez; üreticinin ``None`` dönmediği de
        ölçülür, yoksa "çökmedi" hükmü sessiz bir kayıpla da sağlanır.
        """
        f = _fig(V.create_structural_analysis_plots({}))
        assert isinstance(f, dict), type(f).__name__
        assert 'layout' in f, sorted(f)

    def test_yapisal_pano_yeni_semada_cycles_KeyError_ATMAZ(self):
        sd = {'chamber_analysis': {'hoop_stress': 41.2,
                                   'design_safety_factor_target': 4.0},
              'fatigue_analysis': {'mean_stress': 20.6,
                                   'stress_amplitude': 20.6,
                                   'max_stress': 41.2},
              'safety_analysis': {'safety_factors': {'chamber_hoop': 4.8}}}
        f = _fig(V.create_structural_analysis_plots(sd))
        assert len(f.get('data') or []) >= 1

    def test_emniyet_cizgisi_VERIDEN_gelir_sabit_degil(self):
        def hedef_cizgileri(hedef):
            sd = {'chamber_analysis': {'design_safety_factor_target': hedef},
                  'safety_analysis': {'safety_factors': {'chamber_hoop': 4.8}}}
            f = _fig(V.create_structural_analysis_plots(sd))
            return [s.get('y0') for s in
                    ((f.get('layout') or {}).get('shapes') or [])]
        assert 4.0 in hedef_cizgileri(4.0)
        assert 2.5 in hedef_cizgileri(2.5)

    def test_hedef_yoksa_hukum_cizgisi_CIZILMEZ(self):
        sd = {'safety_analysis': {'safety_factors': {'chamber_hoop': 4.8}}}
        f = _fig(V.create_structural_analysis_plots(sd))
        y0lar = [s.get('y0') for s in
                 ((f.get('layout') or {}).get('shapes') or [])]
        assert 2.0 not in y0lar, y0lar


# ---------------------------------------------------------------------------
# P6B1-06 — ÇÜRÜTÜLDÜ: sürücü kapıları ALTI bacakta da adlandırılmış
# ---------------------------------------------------------------------------
class TestP6B106SurucuKapilariCurutuldu:
    """Kalem "sürücü ayarlarının yarısını denetlemiyor" diyordu; altı
    bacağın altısı da bu ağaçta ölçümle kapalı çıktı
    (``once_p6b1_06.json``). Bekçi, kapanışın geri alınmadığını kilitler:
    ham IndexError/ZeroDivisionError geri gelirse ya da yanlış alan
    suçlanırsa kırmızı olur."""

    @staticmethod
    def _grid():
        import numpy as np
        from hrma.cfd.grid_axisym import build_grid_from_wall
        ni, nj = 24, 8
        z = np.linspace(0.0, 0.20, ni + 1)
        r = np.where(z <= 0.08,
                     0.05 - (0.05 - 0.02) * (z / 0.08),
                     0.02 + (0.05 - 0.02) * ((z - 0.08) / 0.12))
        return build_grid_from_wall(z, r, nj)

    def _coz(self, **kw):
        from hrma.cfd.steady import solve_steady_axisym
        return solve_steady_axisym(self._grid(), P0=2.0e6, T0=3000.0,
                                   gamma=1.2, R=320.0, **kw)

    @pytest.mark.parametrize('ayar,deger,ad', [
        ('max_iters', 0, 'max_iters'),
        ('max_iters', -1, 'max_iters'),
        ('ramp_iters', 0, 'ramp_iters'),
        ('ramp_iters', -5, 'ramp_iters'),
        ('settle_window', -1, 'settle_window'),
        ('settle_window', 0, 'settle_window'),
        ('settle_window', 1, 'settle_window'),
        ('tol_res', -1e-6, 'tol_res'),
        ('tol_res', 0.0, 'tol_res'),
        ('cfl_start', -0.5, 'cfl_start'),
    ])
    def test_gecersiz_ayar_ADLANDIRILMIS_ValueError_alir(self, ayar, deger,
                                                         ad):
        with pytest.raises(ValueError) as ex:
            self._coz(max_iters=3, **{ayar: deger}) if ayar != 'max_iters' \
                else self._coz(**{ayar: deger})
        assert ad in str(ex.value), str(ex.value)[:200]

    @pytest.mark.parametrize('deger', [0.0, -1e-6])
    def test_settle_tol_reddi_DOGRU_alani_sucluyor(self, deger):
        """Kalem "çağıranın vermediği freeze_settle_tol'u suçlayan
        ValueError" diyordu; mesaj artık settle_tol ile BAŞLIYOR."""
        with pytest.raises(ValueError) as ex:
            self._coz(max_iters=3, settle_tol=deger)
        m = str(ex.value).strip()
        assert m.startswith('settle_tol'), m[:200]
        assert not m.startswith('freeze_settle_tol'), m[:200]

    def test_ham_istisna_SIZMAZ(self):
        """IndexError / ZeroDivisionError bacakları kapandı.

        ÖH D23 fix-20: hüküm ``pytest.fail`` ile veriliyordu, gövdede hiç
        ``assert`` yoktu (P13B2-10 iddiasız nüfus taraması yalnız
        ``ast.Assert`` sayar). Hüküm AYNI kaldı, tek fark: üç ayarın
        tamamı koşulup ihlaller TOPLANIYOR ve tek iddiada veriliyor —
        ilkinde durmak diğer iki bacağı ölçülmeden bırakıyordu.
        """
        ihlaller = []
        for ayar, deger in (('max_iters', 0), ('ramp_iters', 0),
                            ('settle_window', -1)):
            try:
                self._coz(max_iters=3, **{ayar: deger}) \
                    if ayar != 'max_iters' else self._coz(**{ayar: deger})
            except ValueError:
                continue
            except Exception as exc:            # noqa: BLE001
                ihlaller.append('%s=%r ham %s sızdırdı: %s'
                                % (ayar, deger, type(exc).__name__, exc))
            else:
                ihlaller.append('%s=%r sessizce kabul edildi'
                                % (ayar, deger))
        assert not ihlaller, ihlaller

    def test_devasa_CFL_sessizce_KABUL_EDILMEZ_diverged_BEYAN_eder(self):
        """Üst sınır BİLEREK konmamıştır (steady.py §CFL rampası): aşırı
        değer Δt-sonluluk kapısından 'diverged' beyanıyla döner. Ölçüldü:
        cfl_max=1e6 -> converged=False, convergence_status='diverged'."""
        res = self._coz(max_iters=50, cfl_max=1.0e6)
        assert res.get('converged') is False
        assert res.get('convergence_status') == 'diverged', res.get(
            'convergence_status')

    def test_varsayilan_kosu_diverged_DEMEZ(self):
        """Yukarıdaki beyan CFL'e duyarlı olsun: varsayılan koşu
        'diverged' demiyor, yoksa test hiçbir şey ölçmezdi."""
        res = self._coz(max_iters=50)
        assert res.get('convergence_status') != 'diverged'


# ---------------------------------------------------------------------------
# OH-D16-04 — KISMEN: seçenek var, taşıyacak seviye YOK (ölçülen nj = 44)
# ---------------------------------------------------------------------------
class TestOHD1604DuvarCozumluSeviye:
    """ÖH D21 duvar-çözümlü ızgarayı ÜRÜN SEÇENEĞİ yaptı
    (``viscous.wall_resolved``). Bu aşamada ÖLÇÜLDÜ
    (``olcum_oh_d16_04.json``): seçenek uçta tanınıyor ve fail-closed
    çalışıyor, ama bugünkü İKİ seviyenin hiçbiri onu taşıyamıyor —
    ilk hücre 1,105e-6 m gerekiyor, ölçülen büyüme oranı coarse'ta
    2,633 / standard'ta 1,550, tavan 1,2; uç ikisini de reddediyor ve
    gereken radyal katman sayısını ADIYLA veriyor: **44**. Bugünkü en
    büyük nj = 24. Yani CFD→FEA köprüsü ürün akışında hâlâ AÇILMIYOR.

    Bekçi iki şeyi kilitler: (1) reddin ölçülmüş sayılarla geldiği,
    (2) tabloya nj >= 44 taşıyan bir seviye eklendiğinde bu testin
    kırmızıya dönüp defterin güncellenmesini zorlaması."""

    @staticmethod
    def _istemci():
        from hrma.app import app
        app.config['TESTING'] = True
        return app.test_client()

    @staticmethod
    def _yuk(seviye):
        from tests.test_cfd_endpoint import govde
        return dict(govde(), resolution=seviye,
                    viscous={'enabled': True, 'wall_thermal': 'isothermal',
                             'T_wall_K': 1800.0, 'turbulence': 'sa_neg',
                             'T_wall_source': 'measurement',
                             'wall_resolved': True})

    @pytest.mark.parametrize('seviye', ['coarse', 'standard'])
    def test_bugunku_seviye_duvar_cozumluyu_TASIYAMAZ_ve_REDDEDER(self,
                                                                  seviye):
        r = self._istemci().post('/api/cfd/nozzle', json=self._yuk(seviye))
        assert r.status_code == 400, r.status_code
        g = r.get_json() or {}
        assert g.get('field') == 'viscous.wall_resolved', g.get('field')
        m = g.get('measured') or {}
        assert m.get('radial_layers_required') == 44, m
        assert m.get('growth_ratio_max') > m.get('growth_ratio_ceiling'), m

    def test_red_IRAKSAK_ALAN_yayimlamaz(self):
        """Fail-closed: reddedilen koşu 'sonuç' gibi bir alan döndürmez."""
        g = (self._istemci().post('/api/cfd/nozzle',
                                  json=self._yuk('coarse')).get_json() or {})
        assert 'cfd' not in g, sorted(g)

    def test_secenek_UCTA_TANINIYOR(self):
        """Seçeneğin kendisi bilinmeyen alan reddi ALMIYOR (D21 teslimi)."""
        g = (self._istemci().post('/api/cfd/nozzle',
                                  json=self._yuk('coarse')).get_json() or {})
        assert g.get('error') == 'invalid_cfd_nozzle_input', g.get('error')

    def test_TASIYACAK_SEVIYE_HALA_YOK(self):
        """nj >= 44 taşıyan bir seviye eklendiğinde bu test kırmızıya döner
        ve OH-D16-04'ün kalan yarısının (ölçülmüş süre cüzdanı) yazılmasını
        zorlar."""
        from hrma.app import CFD_RESOLUTION_LEVELS, CFD_VISCOUS_WORST_CASE_S
        en_buyuk_nj = max(v[1] for v in CFD_RESOLUTION_LEVELS.values())
        assert en_buyuk_nj == 24, CFD_RESOLUTION_LEVELS
        assert en_buyuk_nj < 44, (
            'nj >= 44 seviye eklenmiş: OH-D16-04 kalan yarısı '
            '(CFD_VISCOUS_WORST_CASE_S ölçülmüş hücresi) yazılmalı')
        assert set(CFD_VISCOUS_WORST_CASE_S) == {'coarse', 'standard'}, \
            sorted(CFD_VISCOUS_WORST_CASE_S)
