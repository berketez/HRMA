"""ÖH Dalga-27 · kulvar fea-cfd · aşama 2/2 — ONBİR KALEMİN BEKÇİSİ.

Her test bir defter kalemine bağlıdır ve TERS-MUTASYONLA kanıtlanmıştır
(onarım geçici geri alınır -> test KIRMIZI; geri konur -> YEŞİL). Ölçüm
kanıtı: ``docs/scofield/raw/OH/D27/fea-cfd/a2/once_a2.json`` (taban ağacı)
ve ``sonra_a2.json`` (bu ağaç); mutasyon kanıtı ``mutasyon_a2.json``.
"""

import base64
import importlib
import json
import pathlib
import subprocess
import sys

import numpy as np
import plotly.graph_objects as go
import pytest

import hrma.visualization.visualization as V


def _fig(js):
    return json.loads(js) if isinstance(js, str) else js


def _metin(fig):
    return json.dumps(fig, ensure_ascii=False)


# ---------------------------------------------------------------- P8B3-16
class TestP8B316BdataDtypeKapsami:
    """Çözücü desteklemediği dtype'ı SESSİZCE geçiremez (fail-closed)."""

    def test_desteklenmeyen_dtype_REDDEDILIR(self):
        blok = {'dtype': 'c16',
                'bdata': base64.b64encode(b'\x00' * 16).decode()}
        with pytest.raises(ValueError) as exc:
            V._to_plain({'y': blok})
        # Hata, reddedilen dtype'ı ADIYLA söylemeli
        assert 'c16' in str(exc.value)

    def test_desteklenen_dtype_HALA_COZULUYOR(self):
        for dt in sorted(V._BDATA_DTYPES):
            fig = go.Figure(data=[go.Scatter(y=np.arange(8).astype(dt))])
            out = V._fig_json(fig)
            assert 'bdata' not in out, dt

    def test_bdata_ANAHTARI_OLMAYAN_sozluk_dokunulmaz(self):
        # 'dtype' tek başına (bdata yok) plotly'nin normal alanı olabilir
        assert V._to_plain({'dtype': 'c16'}) == {'dtype': 'c16'}


# ---------------------------------------------------------------- P8B3-20
class TestP8B320SogutmaBandi:
    """Renk eşikleri TEK KAYNAK + figürde beyanlı."""

    MD = {'motor_type': 'liquid',
          'cooling_analysis': {'zones': ['Chamber', 'Throat', 'Nozzle'],
                               'effectiveness': [0.3, 0.3, 0.3]}}

    def test_esik_MODUL_SABITI(self):
        lo, hi = V.COOLING_EFF_STEP_EDGES_PCT
        assert 0.0 < lo < hi <= 100.0

    def test_esik_KODA_GOMULU_DEGIL(self):
        """Çubuk rengi sabitten okunur; 80/60 çıplak yazılmaz."""
        import inspect
        kaynak = inspect.getsource(V.create_heat_transfer_plots)
        assert 'v > 80' not in kaynak and 'v > 60' not in kaynak
        assert '_c_hi' in kaynak and '_c_lo' in kaynak

    def test_bant_FIGURDE_BEYANLI(self):
        fig = _fig(V.create_heat_transfer_plots(self.MD))
        t = _metin(fig)
        assert 'colour bands' in t
        lo, hi = V.COOLING_EFF_STEP_EDGES_PCT
        assert ('red below %.0f%%' % lo) in t
        assert ('green above %.0f%%' % hi) in t

    def test_bant_SOLVER_SINIRI_DIYE_SATILMIYOR(self):
        t = _metin(_fig(V.create_heat_transfer_plots(self.MD)))
        assert 'not a solver limit' in t


# ---------------------------------------------------------------- P8B3-21
class TestP8B321TurKirpmasi:
    """31 türden 10'u çiziliyorsa figür bunu SAYIYLA söyler."""

    @staticmethod
    def _cd(n=31):
        tur = {'SP%02d' % i: {'mole_fraction': 0.5 / (i + 1)}
               for i in range(n)}
        return {'compositions': {'chamber': {'species': tur}},
                'conditions': {'chamber': {'T': 3000.0}}}

    def test_kirpma_BEYAN_EDILIR(self):
        t = _metin(_fig(V.create_combustion_analysis_plots(self._cd(31))))
        assert 'largest of 31 species' in t
        assert '21 not drawn' in t

    def test_kalan_pay_OLCULUR_tahmin_edilmez(self):
        toplam, cizilen, kalan = V._combustion_species_clip(self._cd(31))
        assert (toplam, cizilen) == (31, 10)
        beklenen = sum(0.5 / (i + 1) for i in range(10, 31))
        assert kalan == pytest.approx(beklenen, rel=1e-12)

    def test_KIRPMA_YOKSA_beyan_da_YOK(self):
        t = _metin(_fig(V.create_combustion_analysis_plots(self._cd(4))))
        assert 'largest of' not in t


# ---------------------------------------------------------------- P8B3-22
class TestP8B322MotorTipi:
    """Tip çözülemiyorsa pano bir motor tipi İDDİA ETMEZ."""

    def test_cozulemeyen_tip_NONE(self):
        assert V._perf_motor_type({}) is None
        assert V._perf_motor_type({'foo': 1}) is None
        assert V._perf_motor_type({'motor_type': 'zebra'}) is None

    def test_pano_HIBRIT_DEMEZ(self):
        fig = _fig(V.create_performance_plots({}, {}))
        baslik = fig['layout']['title']['text']
        assert 'Hybrid' not in baslik
        assert baslik == V.PERF_TITLE_UNKNOWN
        assert 'not available' in _metin(_fig(
            V.create_performance_plots({}, {})))

    def test_sebep_ALAN_ADIYLA_yazilir(self):
        t = _metin(_fig(V.create_performance_plots({}, {})))
        for alan in ('motor_type', 'mdot_ox', 'feed-system'):
            assert alan in t

    def test_UC_TIP_HALA_COZULUYOR(self):
        assert V._perf_motor_type({'mdot_ox': 1.0, 'mdot_f': 0.2}) == 'hybrid'
        assert V._perf_motor_type(
            {'thrust_curve': {'burn_area': [1, 2]}}) == 'solid'
        assert V._perf_motor_type(
            {'feed_system': {'mass_flow_rates': {'total': 3.0}}}) == 'liquid'
        assert V._perf_motor_type({'motor_type': 'solid'}) == 'solid'


# ---------------------------------------------------------------- P8B3-25
class TestP8B325CubukKapisi:
    """Düşen çubuk beyan edilir; negatif değer çizilmez."""

    def test_eksik_alan_BEYAN_EDILIR(self):
        p = V._perf_bar_panel('Mass Flow Rates', ['Total', 'Ox', 'Fuel'],
                              [3.0, None, 1.0],
                              ['#ff5d73', '#2dd4a8', '#00e5ff'],
                              '{:.2f}', 'x', 'y')
        assert p is not None
        assert 'Ox' in p['note'] and 'not reported' in p['note']

    def test_negatif_deger_CIZILMEZ(self):
        p = V._perf_bar_panel('Thrust', ['A', 'B'], [-5000.0, 2.0],
                              ['#ff5d73', '#2dd4a8'], '{:.1f}', 'x', 'y')
        assert 'physically impossible' in p['note']
        # çubuk gerçekten düşmüş olmalı
        fig = go.Figure()
        fig.set_subplots(1, 1)
        p['draw'](fig, 1, 1)
        assert list(fig.data[0].x) == ['B']

    def test_saglam_panelde_NOT_YOK(self):
        p = V._perf_bar_panel('T', ['A', 'B'], [1.0, 2.0],
                              ['#ff5d73', '#2dd4a8'], '{:.1f}', 'x', 'y')
        assert 'note' not in p

    def test_pano_ALTINDA_gorunur(self):
        md = {'motor_type': 'liquid',
              'feed_system': {'mass_flow_rates': {'total': 3.0, 'fuel': 1.0}},
              'mixture_ratio': 2.0, 'chamber_pressure': 30.0}
        t = _metin(_fig(V.create_performance_plots(md, {})))
        assert 'not reported by this solution' in t


# ---------------------------------------------------------------- P8B4-03
class TestP8B403UcBoyutluCidar:
    """3B 'Chamber Wall' izinin kalınlığı yapısal çözümden gelir."""

    MD = {'motor_type': 'hybrid', 'chamber_length': 0.3,
          'chamber_diameter': 0.12, 'port_diameter_initial': 0.05,
          'throat_diameter': 0.04, 'exit_diameter': 0.1,
          'chamber_pressure': 40.0,
          'structural_analysis': {
              'chamber_analysis': {'wall_thickness_used_mm': 12.522}},
          'motor_name': 'P8B4-03 bekci'}

    @staticmethod
    def _yaricap(iz):
        x = np.asarray(iz['x'], dtype=float)
        y = np.asarray(iz['y'], dtype=float)
        r = np.sqrt(x ** 2 + y ** 2)
        return float(np.nanmin(r)), float(np.nanmax(r))

    def test_IC_ve_DIS_yuzey_cizilir(self):
        fig = _fig(V.create_3d_motor_visualization(self.MD))
        adlar = [str(t.get('name')) for t in fig['data']]
        assert 'Chamber Wall (inner)' in adlar
        # Dış yüzeyin ADI değişmez: mevcut bekçiler (d15/d23) onu bu adla
        # arıyor ve birim/geometri sözleşmesi o ada bağlı.
        assert 'Chamber Wall' in adlar

    def test_kalinlik_YAPISAL_COZUMLE_AYNI(self):
        fig = _fig(V.create_3d_motor_visualization(self.MD))
        ic = [t for t in fig['data']
              if str(t.get('name')) == 'Chamber Wall (inner)'][0]
        dis = [t for t in fig['data']
               if str(t.get('name')) == 'Chamber Wall'][0]
        r_ic = self._yaricap(ic)[1]
        r_dis = self._yaricap(dis)[1]
        # 2B kesitin kullandığı TEK KAYNAK ile birebir
        kal_mm, _src, _rec = V._cross_section_wall_mm(
            V._scene_3d_si_kopya(self.MD, {'chamber_diameter': 120.0}), 60.0)
        assert (r_dis - r_ic) == pytest.approx(kal_mm, rel=1e-9)
        assert (r_dis - r_ic) == pytest.approx(12.522, rel=1e-9)

    def test_SIFIR_KALINLIK_KALMADI(self):
        fig = _fig(V.create_3d_motor_visualization(self.MD))
        izler = [t for t in fig['data']
                 if str(t.get('name', '')).startswith('Chamber Wall')]
        assert len(izler) == 2
        r_hepsi = [self._yaricap(t) for t in izler]
        assert max(r[1] for r in r_hepsi) - min(r[0] for r in r_hepsi) > 1.0

    def test_YAPISAL_YOKSA_CIDAR_CIZILMEZ_ve_ADI_DURUST(self):
        md = dict(self.MD)
        md.pop('structural_analysis')
        md['chamber_pressure'] = 0.0        # yapısal çözüm kurulamaz
        fig = _fig(V.create_3d_motor_visualization(md))
        adlar = [str(t.get('name')) for t in fig['data']]
        if 'Chamber Wall (inner)' not in adlar:
            # İç yüzey ÇİZİLMEZ ve nota "bu bir cidar değil" yazılır
            assert 'not a wall' in _metin(fig)


# ---------------------------------------------------------------- P8B4-09
class TestP8B409SelaleManseti:
    """Manşet ÇİZİLEN yüzeyin maksimumunu da söyler."""

    TD = {'chamber_pressure': 40.0, 'chamber_temperature': 3200.0,
          'throat_diameter': 0.04, 'exit_diameter': 0.1,
          'chamber_diameter': 0.12, 'chamber_length': 0.3,
          'burn_time': 10.0, 'mdot_total': 2.0, 'material': 'steel',
          'wall_thickness': 0.005, 'cooling_type': 'regenerative',
          'gamma': 1.2, 'molecular_weight': 22.0}

    def test_manset_YUZEY_MAKSIMUMUNU_soyler(self):
        fig = _fig(V.create_wall_heat_flux_waterfall_plot(self.TD))
        manset = fig['layout']['title']['text']
        yuzey = [t for t in fig['data'] if t.get('type') == 'surface'][0]
        z_max = float(np.nanmax(np.asarray(yuzey['z'], dtype=float)))
        assert 'peak surface flux' in manset
        assert ('%.2f MW/m2' % z_max) in manset

    def test_manset_TASARIM_AKISINI_da_soyler(self):
        fig = _fig(V.create_wall_heat_flux_waterfall_plot(self.TD))
        manset = fig['layout']['title']['text']
        tasarim = [t for t in fig['data']
                   if 'Design flux' in str(t.get('name', ''))][0]
        q_max = float(np.nanmax(np.asarray(tasarim['z'], dtype=float)))
        assert 'peak design flux' in manset
        assert ('%.2f MW/m2' % q_max) in manset

    def test_iki_sayinin_CIDAR_DURUMU_yazili(self):
        manset = _fig(V.create_wall_heat_flux_waterfall_plot(
            self.TD))['layout']['title']['text']
        assert 'cold wall' in manset and 'reference cooled wall' in manset


# ---------------------------------------------------------------- P8B4-10
class TestP8B410BogazKapisi:
    """Sıfır/olmayan boğaz temiz ValueError verir (ZeroDivisionError yok)."""

    TABAN = {'throat_diameter': 0.04, 'expansion_ratio': 8.0,
             'chamber_pressure': 40.0, 'chamber_temperature': 3200.0,
             'gamma': 1.2, 'molecular_weight': 22.0}

    @pytest.mark.parametrize('deger', [0.0, -0.04, float('nan'),
                                       float('inf'), -0.0])
    def test_uc_deger_TEMIZ_VALUEERROR(self, deger):
        cd = dict(self.TABAN, throat_diameter=deger)
        with pytest.raises(ValueError):
            V.create_nozzle_mach_area_ratio_contour(cd)

    def test_sifir_bogaz_ZERODIVISION_DEGIL(self):
        cd = dict(self.TABAN, throat_diameter=0.0)
        try:
            V.create_nozzle_mach_area_ratio_contour(cd)
        except ZeroDivisionError:               # pragma: no cover
            pytest.fail('sıfır boğaz hâlâ ZeroDivisionError atıyor')
        except ValueError as exc:
            assert 'throat_diameter' in str(exc)

    def test_saglam_bogaz_HALA_CIZIYOR(self):
        js = V.create_nozzle_mach_area_ratio_contour(dict(self.TABAN))
        assert 'Mach field' in js


# ---------------------------------------------------------------- P8B4-21
class TestP8B421EnjektorUyarilari:
    """Çözücünün uyarıları çizime TAŞINIR."""

    UYARILAR = [
        {'code': 'cavitation_risk', 'severity': 'warning',
         'message': 'Cavitation risk: sigma < 1'},
        {'code': 'flash_boiling', 'severity': 'warning',
         'message': 'Flash boiling expected downstream'},
        {'code': 'low_stiffness', 'severity': 'warning',
         'message': 'Injector stiffness below 15%'},
        {'code': 'hydraulic_flip', 'severity': 'warning',
         'message': 'Hydraulic flip risk'},
        {'code': 'l_over_d_low', 'severity': 'info',
         'message': 'L/D below recommended'},
    ]

    def _idata(self, **kw):
        d = {'n_holes': 19, 'hole_diameter': 1.5, 'plate_thickness': 3.0,
             'exit_velocity': 30.0, 'reynolds_number': 50000.0,
             'total_mass_flow': 2.0, 'chamber_diameter': 100.0}
        d.update(kw)
        return d

    def test_BES_UYARININ_BESI_de_gorunur(self):
        t = _metin(_fig(V.create_showerhead_with_tooltips(
            self._idata(warnings=self.UYARILAR))))
        for w in self.UYARILAR:
            assert w['message'] in t, w['code']

    def test_uyari_METNI_YENIDEN_YAZILMAZ(self):
        t = _metin(_fig(V.create_showerhead_with_tooltips(
            self._idata(warnings=self.UYARILAR))))
        assert 'Solver warnings for this injector (5)' in t
        assert 'INFO: L/D below recommended' in t

    def test_UYARI_YOKSA_kutu_da_YOK(self):
        t = _metin(_fig(V.create_showerhead_with_tooltips(self._idata())))
        assert 'Solver warnings' not in t


# ---------------------------------------------------------------- P8B4-22
class TestP8B422PaketImportu:
    """Bir alt modül düşerse ötekinin adları HAYATTA kalır.

    ÖH D33-KOLAY / OH-D32-05: paket yüzeyi artık GECİKMELİ çözülür;
    sonda ``_load_exports()`` çağırarak yüzeyin tamamını çözdürür
    (aşağıdaki künye). Ölçülen sözleşme DEĞİŞMEDİ — 18 ad, yalıtım,
    vekil, uyarı metni.

    Sonda AYRI BİR SÜREÇTE koşar: ``sys.modules`` üzerinde oynayan bir
    simülasyon aynı süreçteki başka bekçilerin monkeypatch'ini bozuyordu
    (ölçüldü: ``test_d23_fea_cfd_a1.py::TestP8B406YedekGovdeYok`` tek
    başına yeşil, bu sınıfla aynı süreçte kırmızıydı). Yalıtım
    süreç düzeyinde kurulur.
    """

    KOK = pathlib.Path(__file__).resolve().parents[1]

    SONDA = r"""
import importlib, json, sys, warnings
kirilan = sys.argv[1]
sys.modules[kirilan] = None
with warnings.catch_warnings(record=True) as yakalanan:
    warnings.simplefilter('always')
    paket = importlib.import_module('hrma.visualization')
    # ÖH D33-KOLAY / OH-D32-05 — ``_load_exports()`` ÇAĞRISI EKLENDİ.
    # Paket yüzeyi artık GECİKMELİ çözülüyor (PEP 562 ``__getattr__``);
    # arıza uyarısı paket içe aktarımında DEĞİL adın ilk çözüldüğü anda
    # basılıyor. Çağrı olmadan bu sonda uyarıyı ölçmeden geçerdi
    # (körleşmiş bekçi). Ölçülen davranış AYNI: yüzeyin tamamı çözülür,
    # uyarı hangi modülün hangi hatayla düştüğünü adlarıyla söyler.
    paket._load_exports()
    uyarilar = [str(w.message) for w in yakalanan]
out = {'uyarilar': uyarilar, 'adlar': {}}
for ad in paket.__all__:
    fn = getattr(paket, ad, None)
    if fn is None:
        out['adlar'][ad] = 'YOK'
    elif hasattr(fn, 'unavailable_reason'):
        try:
            fn()
            out['adlar'][ad] = 'VEKIL_SESSIZ'
        except ImportError as exc:
            out['adlar'][ad] = 'VEKIL:' + str(exc)
    else:
        out['adlar'][ad] = 'GERCEK'
print(json.dumps(out))
"""

    def _sonda(self, kirilan):
        r = subprocess.run([sys.executable, '-c', self.SONDA, kirilan],
                           cwd=str(self.KOK), capture_output=True, text=True,
                           timeout=300)
        assert r.returncode == 0, r.stderr[-800:]
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_YALITIM_bir_modul_dusse_otekinin_adlari_GERCEK_kalir(self):
        """ÖLÇÜLDÜ: tabanda advanced_results düşünce 4 ad KAYBOLUYORDU."""
        d = self._sonda('hrma.visualization.advanced_results')
        adlar = d['adlar']
        assert len(adlar) == 18
        assert adlar['create_motor_plot'] == 'GERCEK'
        assert adlar['create_performance_plots'] == 'GERCEK'
        for ad in ('create_cea_style_results', 'create_mass_fractions_plot'):
            assert adlar[ad].startswith('VEKIL:'), (ad, adlar[ad])
            assert 'advanced_results' in adlar[ad]

    def test_ILK_MODUL_DUSSE_de_ad_KAYBOLMAZ(self):
        """Tabanda 18/18 ad kayboluyordu; bugün 18/18 duruyor."""
        d = self._sonda('hrma.visualization.visualization')
        adlar = d['adlar']
        assert len(adlar) == 18
        assert 'YOK' not in adlar.values()
        # kayıp ad çağrılınca GERÇEK sebebi söyler (AttributeError değil)
        assert adlar['create_motor_plot'].startswith('VEKIL:')
        assert 'hrma.visualization.visualization' in adlar['create_motor_plot']

    def test_uyari_MODULU_ve_ADLARI_yazar(self):
        d = self._sonda('hrma.visualization.advanced_results')
        assert d['uyarilar']
        birlesik = ' '.join(d['uyarilar'])
        assert 'advanced_results' in birlesik
        assert 'create_cea_style_results' in birlesik

    def test_SAGLAM_PAKETTE_18_ad(self):
        paket = importlib.import_module('hrma.visualization')
        assert len(paket.__all__) == 18
        for ad in paket.__all__:
            assert callable(getattr(paket, ad)), ad
            assert not hasattr(getattr(paket, ad), 'unavailable_reason'), ad


# ---------------------------------------------------------------- P8B4-23
class TestP8B423KarsilastirmaKapisi:
    """NaN / inf / negatif / bool kapıdan GEÇEMEZ."""

    @pytest.mark.parametrize('deger', [float('nan'), float('inf'),
                                       float('-inf'), -5000.0, True, False])
    def test_uc_deger_REDDEDILIR(self, deger):
        with pytest.raises(ValueError):
            V._validate_comparative_configs({'A': {'thrust': deger}})

    def test_bool_MESAJI_bool_der(self):
        with pytest.raises(ValueError) as exc:
            V._validate_comparative_configs({'A': {'thrust': True}})
        assert 'boolean' in str(exc.value)

    def test_negatif_MESAJI_isareti_soyler(self):
        with pytest.raises(ValueError) as exc:
            V._validate_comparative_configs({'A': {'thrust': -1.0}})
        assert 'non-negative' in str(exc.value)

    def test_saglam_deger_HALA_GECER(self):
        V._validate_comparative_configs({'A': {'thrust': 5000.0}})
        V._validate_comparative_configs({'A': {'thrust': 0.0}})
        js = V.create_comparative_analysis_plot({'A': {'thrust': 5000.0}})
        assert 'nan' not in js.lower().replace('nan_', '')
