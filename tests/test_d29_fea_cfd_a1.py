"""ÖH Dalga-29 — kulvar fea-cfd, aşama 1/1 bekçileri.

Kapsanan kalemler:

* **OH-D28-02** (hüküm-17) — geometri örnekleme tabanı kapısı ince mesh'te
  (na >= 1024) ihlal veriyordu ve 1 kN sıvı vakası bu yüzden HÜKÜMSÜZ
  kalıyordu. ÖLÇÜLDÜ (``docs/scofield/raw/OH/D29/fea-cfd/a1/once_d2802.json``):
  ihlalli HER turda üretilen dış zincirin en küçük konkav yarıçapının
  düğümü bir DÜZELTME KOŞUSU ÇAPASIDIR (``min_dugum_bir_capa``) — yani
  kusur kapamada değil koşu SINIRINDADIR. Çapa ham kaldığı için zincirde
  ``(-h, 0), (0, -Δ), (h, 0)`` çentiği kalıyor; çevrel yarıçapı
  R = (h²+Δ²)/(2Δ) ≈ h²/(2Δ) olduğundan, Δ istasyon sayısından bağımsız
  bir artık iken h ~ 1/n_axial küçüldükçe R 1/n² gibi ÇÖKÜYOR.

  | n_axial | 256 | 512 | 1024 | 2048 |
  |---|---|---|---|---|
  | hibrit oran (önce) | 0,99752 | **0,24488** | **0,05547** | **0,01544** |
  | hibrit oran (sonra) | 0,99752 | 0,99010 | 0,96569 | 0,89103 |
  | sıvı 1 kN (önce) | 1,29963 | 1,02401 | **0,52654** | **0,14238** |
  | sıvı 1 kN (sonra) | 1,29963 | 1,02401 | **1,00262** | 0,96306 |

  Onarım tabanı GEVŞETMEZ (pay ``OUTER_FLOOR_SAMPLE_TOL`` = %1 sabit):
  düzeltme koşusu, üretilen zincirde taban altı konkav düğüm kalmayana
  dek büyütülür ve ölçüt bir vekil değil KAPININ KENDİSİDİR
  (``polyline_concave_radii``). Ürün etkisi ölçüldü (capa_once/capa_sonra):
  /calculate ailesi BİT-AYNI; ``/api/fea/structural`` dört vakadan üçünde
  bit-aynı, 1 kN sıvıda ``geometri_ornekleme_tabani_ihlali`` gerekçesi
  DÜŞTÜ.

* **OH-D28-06** (hüküm-17) — ad ⟷ davranış kapısı (oran/verim iddia eden
  başlık ⇒ çizilen büyüklük boyutsuz) yalnız karşılaştırma figürünün
  statik panel tablosunda koşuyordu ve sözlüğü İngilizceydi. ÖLÇÜLDÜ
  (``once_d2806.json``): 19 yayımlanan figür, 1 kapı çağrısı; altı Türkçe
  iddia ('Kütle Verimi', 'KÜTLE VERİMİ', 'Karışım Oranı', 'Yüzde Kayıp',
  'Kütle Kesri', ASCII 'Kutle Verimi') boyutlu eksenlerle kapıdan GEÇTİ.
  Kapı artık ORTAK yayım noktasında (``_fig_json``) ve sözlük iki dilli;
  eşleşme casefold+NFKD normali üzerinden SÖZCÜK BAŞINDAN yapılır
  (ham alt dize araması 'Acceleration Profile' başlığını 'ratio' sanıyordu
  — kapsam genişleyince ortaya çıkan gizli yanlış-pozitif).
"""

import contextlib
import io
import pathlib
import sys

import numpy as np
import pytest
from tests.support.platform_capa import capa_rel

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


#: ÖLÇÜM FİKSTÜRÜ — once_d2802.json / capa_once.json ile AYNI istek.
D29F_SIVI_1KN = {
    'motor_name': 'OHD2802', 'thrust': 1000.0, 'burn_time': 30.0,
    'chamber_pressure': 10.0, 'mixture_ratio': 2.2, 'fuel_type': 'rp1',
    'oxidizer_type': 'lox', 'expansion_ratio': 4.0,
    # V3.0.5 T-ÇAPA-C1 — SOĞUTMA TİPİ AÇIKÇA 'radiative' (tek katmanlı
    # cidar). V301/L-KABUK (6f8240043) rejeneratif yolda köprüye çizilen
    # YIĞINI (astar + kanal + dış kabuk) veriyor: bu istek varsayılan
    # rejeneratifle cidarı 2,0 → 5,0 mm yaptı ve çapalar (once_d2802.json /
    # once_d2903.json, 2,0 mm cidarda ölçüldü) geometri değiştiği için
    # tutmadı. ÖLÇÜLDÜ (e038d626f): 'radiative' ile köprü cidarı 0,002 m ve
    # kontur (68 nokta, toplam 3,7933785254) sabah tabanı ad0737bd4'ün
    # varsayılan isteğiyle BİREBİR — yani ölçüm fikstürünün geometrisi.
    'cooling_type': 'radiative',
}
D29F_HIBRIT = {
    'motor_name': 'OHD2802H', 'thrust': 2000.0, 'chamber_pressure': 30.0,
    'burn_time': 10.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'of_ratio': 6.0, 'expansion_ratio': 8.0,
}


def _girdiler(istemci, yol, gonderi):
    from hrma.fea import bridge
    md = _sessiz(istemci.post, yol, json=gonderi).get_json() or {}
    g = _sessiz(bridge.extract_structural_inputs, md.get('motor', md))
    assert g.get('status') == 'ok', g.get('missing')
    return g


@pytest.fixture(scope='module')
def sivi_girdiler(istemci):
    return _girdiler(istemci, '/calculate_liquid', D29F_SIVI_1KN)


@pytest.fixture(scope='module')
def hibrit_girdiler(istemci):
    return _girdiler(istemci, '/calculate', D29F_HIBRIT)


def _mesh(girdiler, na, nr=4):
    from hrma.fea import mesh_axisym as MA
    return _sessiz(MA.build_wall_mesh, girdiler['contour'],
                   girdiler['thickness_m'], n_axial=na, n_radial=nr,
                   offset_mode='normal')


def _taban(mesh):
    return mesh.meta['dis_yuzey_egrilik_tabani']


# ===========================================================================
# OH-D28-02 — KOŞU KAPANIŞI
# ===========================================================================
class TestOHD2802KosuKapanisi:
    """Kapı ince mesh'te çapanın ham kalmasından düşüyordu; artık düşmüyor."""

    def test_sivi_1kN_na1024_kapi_GECIYOR(self, sivi_girdiler):
        """Kalemin vakası: 1 kN sıvı, ürün turu na = 1024."""
        from hrma.fea import mesh_axisym as MA
        tb = _taban(_mesh(sivi_girdiler, 1024))
        oran = tb['dis_egri_ornek_taban_orani']
        assert oran is not None
        assert oran >= 1.0 - MA.OUTER_FLOOR_SAMPLE_TOL, (
            f'na=1024 oranı {oran} — tabanda 0,52654 idi, onarım geri '
            'alınmış olabilir')
        assert tb['ornek_taban_kapisi'] is True

    def test_hibrit_na512_kapi_GECIYOR(self, hibrit_girdiler):
        """Tabanda 0,24488 ile düşen tur."""
        from hrma.fea import mesh_axisym as MA
        tb = _taban(_mesh(hibrit_girdiler, 512))
        assert tb['dis_egri_ornek_taban_orani'] >= \
            1.0 - MA.OUTER_FLOOR_SAMPLE_TOL, tb['dis_egri_ornek_taban_orani']
        assert tb['ornek_taban_kapisi'] is True

    @pytest.mark.parametrize('na', (512, 1024))
    def test_min_konkav_dugum_artik_CAPA_DEGIL(self, sivi_girdiler, na):
        """Kökün kendisi: min yarıçap düğümü bir koşu çapası olmamalı.

        Kapının sayısına değil MEKANİZMASINA bağlı bekçi: çapa ham kalırsa
        min düğüm yine sınıra kayar (tabanda öyleydi, ölçüldü).
        """
        from hrma.fea import mesh_axisym as MA
        m = _mesh(sivi_girdiler, na)
        nodes = m.nodes.reshape(m.meta['n_axial'] + 1,
                                m.meta['n_radial_kullanilan'] + 1, 2)
        dis = nodes[:, -1, :]
        R, konkav = MA.polyline_concave_radii(dis)
        gecerli = konkav & np.isfinite(R)
        assert np.any(gecerli)
        j = int(np.argmin(np.where(gecerli, R, np.inf)))
        floor_m = _taban(m)['outer_curvature_floor_m']
        assert R[j] >= floor_m * (1.0 - MA.OUTER_FLOOR_SAMPLE_TOL), (
            f'min konkav yarıçap {R[j]} < taban {floor_m}')

    @pytest.mark.parametrize('na,oran,duzeltilen', (
        (64, 2.0869899128215375, 7),
        (128, 1.804886871637926, 13),
        (256, 1.29962680467731, 23),
        (512, 1.0240081745107796, 51),
    ))
    def test_kaba_turlar_TABANLA_AYNI(self, sivi_girdiler, na, oran,
                                      duzeltilen):
        """Çapa koruması: onarım yalnız ihlalli turlarda iş yapar.

        Sayılar taban ağacından ölçüldü (once_d2802.json); koşu kapanışı
        bu turlarda hiçbir istasyon EKLEMEZ, geometri bit-özdeş kalır.
        """
        tb = _taban(_mesh(sivi_girdiler, na))
        # v3.0.0 (15 Eki) — çapa darwin/arm64'te ölçüldü; CI linux/x86_64'te
        # AYNI kod 1,4e-10 bağıl sapma verdi (koşum 38770162288). Tolerans
        # referans platformda aynen; başkasında 1e-8 (tests/support/platform_capa.py).
        assert tb['dis_egri_ornek_taban_orani'] == pytest.approx(
            oran, rel=capa_rel(1e-12, 1e-8))
        assert tb['duzeltilen_istasyon'] == duzeltilen

    def test_pay_ve_kalinlik_esigi_GEVSEMEDI(self):
        """Onarım eşik büyütmesi DEĞİLDİR (ÖK: tolerans gevşetme yasak)."""
        from hrma.fea import mesh_axisym as MA
        assert MA.OUTER_FLOOR_SAMPLE_TOL == 0.01
        assert MA.GEOMETRY_THICKNESS_TOL == 0.10

    def test_kapanis_olcutu_KAPININ_KENDISI(self):
        """Tek kaynak: kapanış ölçütü vekil bir sayı değil, kapının ölçüsü."""
        kaynak = (KOK / 'hrma/fea/mesh_axisym.py').read_text(encoding='utf-8')
        blok = kaynak.split('# --- KOŞU KAPANIŞI (OH-D28-02)', 1)[1]
        blok = blok.split('# --- Uygulama bölgesi beyanı', 1)[0]
        assert 'polyline_concave_radii(outer)' in blok
        assert 'OUTER_FLOOR_SAMPLE_TOL' in blok
        # Kapanışta yeni bir sayısal eşik TANIMLANMAZ.
        assert '0.0' not in blok.replace('floor > 0.0', '')

    def test_hukumden_ihlal_gerekcesi_DUSTU(self, istemci):
        """Ürün yüzü: 1 kN sıvı artık bu gerekçeyle geri çekilmiyor."""
        from hrma.fea import bridge
        md = _sessiz(istemci.post, '/calculate_liquid',
                     json=D29F_SIVI_1KN).get_json() or {}
        s = _sessiz(bridge.run_structural_from_motor, md.get('motor', md),
                    n_axial0=1024, n_radial0=3, max_rounds=0)
        h = (s.get('meta') or {}).get('hukum') or {}
        assert 'geometri_ornekleme_tabani_ihlali' not in \
            h.get('geri_cekme_gerekceleri', []), h.get(
                'geri_cekme_gerekceleri')
        assert (h.get('geometri_ornekleme_tabani') or {})['kapi'] is True


# ===========================================================================
# OH-D28-06 — AD ⟷ DAVRANIŞ KAPISI: KAPSAM + İKİ DİLLİ SÖZLÜK
# ===========================================================================
class TestOHD2806AdDavranisKapisi:
    """Kapı yayım noktasında ve sözlüğü Türkçeyi de görüyor."""

    @staticmethod
    def _figur(baslik, x, y):
        import plotly.graph_objects as go
        fig = go.Figure(data=[go.Bar(x=['A', 'B'], y=[1.0, 2.0])])
        fig.update_layout(title=baslik, xaxis_title=x, yaxis_title=y)
        return fig

    def test_yalan_baslikli_figur_YAYIMLANMAZ(self):
        """Kapsam: kapı artık statik tabloda değil YAYIM yolunda."""
        import hrma.visualization.visualization as V
        with pytest.raises(ValueError, match='dimensioned'):
            V._fig_json(self._figur('Nozzle Efficiency', 'Configuration',
                                    'Thrust (N)'))

    @pytest.mark.parametrize('baslik', (
        'Kütle Verimi', 'KÜTLE VERİMİ', 'Kutle Verimi', 'Karışım Oranı',
        'Yüzde Kayıp', 'Kütle Kesri', 'Soğutma Etkinliği',
    ))
    def test_turkce_iddia_ENGELLENIR(self, baslik):
        """Sözlük: tabanda altısı da kapıdan geçiyordu (ölçüldü)."""
        import hrma.visualization.visualization as V
        with pytest.raises(ValueError):
            V._fig_json(self._figur(baslik, 'Configuration',
                                    'Toplam Kütle (kg)'))

    @pytest.mark.parametrize('baslik,x,y', (
        # Ham alt dize araması 'Accele-RATIO-n' derdi (gizli yanlış-pozitif).
        ('Acceleration Profile', 'Time (s)', 'Acceleration (g)'),
        # İddia sözcüğü BOYUTSUZ bir eksenin adından geliyorsa iddia yoktur.
        ('Thrust vs Expansion Ratio', 'Expansion Ratio (-)', 'Thrust (N)'),
        # İddia + boyutsuz eksen: oran gerçekten çizilidir.
        ('Nozzle Efficiency', 'Configuration', 'Efficiency (-)'),
        ('Isp Comparison', 'Configuration', 'Isp (s)'),
    ))
    def test_dogru_baslik_YAYIMLANIR(self, baslik, x, y):
        """Kapı fail-closed'dır ama yanlış-pozitif üretmez."""
        import hrma.visualization.visualization as V
        govde = V._fig_json(self._figur(baslik, x, y))
        assert '"data"' in govde

    def test_ALT_GRAFIK_basligi_da_denetlenir(self):
        """Alt grafik başlığı annotation'dır; kapı onu eksenine EŞLER."""
        import hrma.visualization.visualization as V
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=1, cols=2,
                            subplot_titles=('Thrust Comparison',
                                            'Mass Efficiency'))
        fig.add_trace(go.Bar(x=['A'], y=[1.0]), row=1, col=1)
        fig.add_trace(go.Bar(x=['A'], y=[2.0]), row=1, col=2)
        fig.update_xaxes(title_text='Configuration', row=1, col=1)
        fig.update_yaxes(title_text='Thrust (N)', row=1, col=1)
        fig.update_xaxes(title_text='Configuration', row=1, col=2)
        fig.update_yaxes(title_text='Total Mass (kg)', row=1, col=2)
        with pytest.raises(ValueError, match='Mass Efficiency'):
            V._fig_json(fig)

    def test_urun_karsilastirma_figuru_YAYIMLANIYOR(self):
        """Yanlış-pozitif yok: gerçek ürün figürü kapıdan geçer."""
        import json as _json
        import hrma.visualization.visualization as V
        govde = _sessiz(V.create_comparative_analysis_plot, {
            'A': {'thrust': 1000.0, 'isp': 250.0,
                  'total_impulse': 30000.0, 'total_mass': 10.0},
            'B': {'thrust': 2000.0, 'isp': 260.0,
                  'total_impulse': 60000.0, 'total_mass': 18.0}})
        d = _json.loads(govde)
        assert V._figur_ad_davranis_kapisi(d) == 4

    def test_sozluk_TEK_KAYNAK_ve_iki_dilli(self):
        """Eşleşme normali sözlüğe de uygulanır; ayrışma imkânsız."""
        import hrma.visualization.visualization as V
        assert 'verim' in V.PANEL_ORAN_IDDIA_SOZCUKLERI
        assert 'oran' in V.PANEL_ORAN_IDDIA_SOZCUKLERI
        assert V._panel_metin_normali('KÜTLE VERİMİ') == 'kutle verimi'
        assert V._panel_metin_normali('Yüzde') == 'yuzde'
        for ham, normal in V._PANEL_IDDIA_NORMALLERI:
            assert normal == V._panel_metin_normali(ham)
