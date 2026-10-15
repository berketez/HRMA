# -*- coding: utf-8 -*-
"""ÖH Dalga-19 · kulvar **ihracat** · aşama 1 — bekçiler.

Kapsanan kalemler:

- **P9B1-08** sıvı CAD kesitindeki lüle profilinin yarıçapı NEGATİF
  başlıyordu (−822,10 mm; 50 noktanın 15'i eksenin öbür tarafında).
- **P9B1-22** ``generate_solid_motor_cad`` sıfır iz içeren boş bir figürü
  sıradan bir üretim sözlüğü gibi döndürüyordu (kendi durumunu söylemiyordu).
- **P9B1-23** STL'e giden enjektör plakasında 16 delik varken çizim 125
  diyordu; kırpma HİÇBİR çıktı alanında bildirilmiyordu.
- **P15B4-11** ``geometry_summary.total_length`` motorun yayımladığı boy
  tanımlarının hiçbirine eşit değildi (CAD'in kendi dördüncü tanımı).

Her bekçi ters mutasyonla kırmızıya çevrilebildiği ÖLÇÜLEREK yazıldı;
mutasyon defteri ``docs/scofield/raw/OH/D19/ihracat/a1/mutasyon.json``.
Ölçüm kayıtları ``once.json`` (onarımdan önce) / ``sonra.json``.
"""
import contextlib
import io
import json
import math

import pytest

from hrma.export import cad_visualization as CV


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


#: ``DetailedCADGenerator`` gövdeyi MİLİMETRE okur (kendi içinde /1000 yapar) —
#: ``liquid.html``in gönderdiği sözleşme budur.
PANEL_MM = {
    'motor_name': 'D19-PANEL',
    'chamber_diameter': 61.53496638537138,
    'chamber_length': 300.0,
    'throat_diameter': 50.0,
    'exit_diameter': 217.559,
    'nozzle_length': 225.0,
    'injector_type': 'unlike_impinging',
    'chamber_pressure': 100.0, 'thrust': 10000.0,
}


def _profil_ust_yarisi(sonuc):
    """``Nozzle Profile`` izinin ÜST yarısındaki yarıçaplar [m]."""
    fig = json.loads(sonuc['plot_json'])
    prof = [t for t in (fig.get('data') or [])
            if str(t.get('name')) == 'Nozzle Profile']
    assert prof, 'kesitte lüle profili izi yok — bekçi inert olurdu'
    ys = [float(v) for v in (prof[0].get('y') or [])]
    n = len(ys) // 2            # alt yarı bilerek aynalanır (dolgu için)
    assert n >= 10, f'profil örneklemesi beklenmedik ({len(ys)} nokta)'
    return ys[:n]


# =====================================================================
# P9B1-08 — kesit lüle profilinin yarıçapı negatif olamaz
# =====================================================================
class TestP9B108KesitLuleProfili:
    """ÖLÇÜM (once.json): ilk beş yarıçap
    ``[-822,10; -784,50; -747,66; -711,61; -676,33] mm``, 15/50 nokta
    negatif. Kök sebep konverjan dalının işaret koruması olmayan parabolü:
    ``progress = 0``'da ``((1-0)/0,3)**2 = 11,111`` → çarpan −10,111."""

    def test_hicbir_yaricap_negatif_degil(self):
        uretici = CV.DetailedCADGenerator()
        sonuc = _sessiz(uretici.generate_liquid_motor_cad, dict(PANEL_MM))
        ust = _profil_ust_yarisi(sonuc)
        negatif = [r * 1000.0 for r in ust if r < 0]
        assert not negatif, (
            'yarıçap negatif olamaz; eksenin öbür tarafından gelen '
            f'{len(negatif)} nokta: {negatif[:5]}')

    def test_profil_KAMARA_yaricapindan_basliyor(self):
        """Konverjan kamaradan boğaza iner: başlangıç kamara yarıçapıdır.

        Eski formül başlangıcı ÇIKIŞ yarıçapı ölçeğinden kuruyordu; kamara
        çapını hiç okumuyordu. Bu iddia olmadan 'negatif değil' yetmez —
        boğazdan başlayan düz bir çizgi de negatif olmazdı.
        """
        uretici = CV.DetailedCADGenerator()
        sonuc = _sessiz(uretici.generate_liquid_motor_cad, dict(PANEL_MM))
        ust = _profil_ust_yarisi(sonuc)
        beklenen_m = PANEL_MM['chamber_diameter'] / 2.0 / 1000.0
        assert ust[0] == pytest.approx(beklenen_m, rel=1e-9), (
            f'profil {ust[0] * 1000.0:.3f} mm ile başlıyor; kamara yarıçapı '
            f'{beklenen_m * 1000.0:.3f} mm')

    def test_profil_COZUCUNUN_cikis_yaricapinda_bitiyor(self):
        uretici = CV.DetailedCADGenerator()
        sonuc = _sessiz(uretici.generate_liquid_motor_cad, dict(PANEL_MM))
        ust = _profil_ust_yarisi(sonuc)
        beklenen_m = PANEL_MM['exit_diameter'] / 2.0 / 1000.0
        assert ust[-1] == pytest.approx(beklenen_m, rel=1e-9)

    def test_profil_bogazdan_dar_yere_inmiyor(self):
        """En dar kesit boğazdır: hiçbir nokta boğazın altına düşemez."""
        uretici = CV.DetailedCADGenerator()
        sonuc = _sessiz(uretici.generate_liquid_motor_cad, dict(PANEL_MM))
        ust = _profil_ust_yarisi(sonuc)
        bogaz_m = PANEL_MM['throat_diameter'] / 2.0 / 1000.0
        assert min(ust) >= bogaz_m - 1e-12, (
            f'profil boğazın ({bogaz_m * 1000.0:.3f} mm) altına indi: '
            f'{min(ust) * 1000.0:.3f} mm')

    def test_kamara_capi_verilmezse_bogazdan_baslar_UYDURMA_yok(self):
        """Kamara yarıçapı yoksa uydurma bir daralma çizilmez."""
        uretici = CV.DetailedCADGenerator()
        iz = uretici._create_nozzle_cross_section(
            0.3, 0.05, 0.2, 0.225, chamber_dia=None)
        ys = [float(v) for v in iz['y']]
        n = len(ys) // 2
        assert ys[0] == pytest.approx(0.05 / 2.0)
        assert min(ys[:n]) >= 0.0


# =====================================================================
# P9B1-22 — taslak üretici kendi durumunu ADIYLA söyler
# =====================================================================
KATI_MM = {'motor_type': 'solid', 'chamber_diameter': 100.0,
           'chamber_length': 500.0, 'throat_diameter': 25.0,
           'exit_diameter': 60.0, 'nozzle_length': 150.0,
           'grain_type': 'bates'}


class TestP9B122KatiUreticiTaslakBeyani:
    """ÖLÇÜM (once.json): üretici 0 iz döndürüyor ve dönen sözlükte hata
    alanı YOK; hüküm tamamen tüketicinin çıkarımına kalmıştı."""

    @pytest.fixture(scope='class')
    def sonuc(self):
        return _sessiz(CV.DetailedCADGenerator().generate_solid_motor_cad,
                       dict(KATI_MM))

    def test_uretici_kendi_iz_sayisini_YAYIMLIYOR(self, sonuc):
        iz = len(json.loads(sonuc['plot_json']).get('data') or [])
        assert sonuc['trace_count'] == iz, (
            'yayımlanan sayı ÖLÇÜM olmalı, ayrı bir iddia değil')

    def test_izsiz_uretici_reddini_ADIYLA_beyan_ediyor(self, sonuc):
        """İddia ölçüme koşulludur: üretici çizmeye başladığı gün beyan
        kendiliğinden düşer (sabit bayrak değil)."""
        if sonuc['trace_count'] == 0:
            assert sonuc['error'] == 'solid_detailed_cad_not_modelled'
            assert sonuc['error_message']
        else:
            assert sonuc.get('error') is None

    def test_uc_URETICININ_gerekcesini_tasiyor(self, istemci, sonuc):
        r = _sessiz(istemci.post, '/api/detailed-cad/solid', json=dict(KATI_MM))
        if sonuc['trace_count'] == 0:
            assert r.status_code == 501
            j = r.get_json()
            assert j['error'] == 'cad_not_modelled'
            assert j['generator_error'] == 'solid_detailed_cad_not_modelled'
            assert j['message'] == sonuc['error_message'], (
                'uç kendi metnini uydurmamalı; üreticinin gerekçesini taşımalı')
        else:
            assert r.status_code == 200


# =====================================================================
# P9B1-23 — MESH kırpması yayımlanır
# =====================================================================
SIVI_125 = {
    'motor_type': 'liquid', 'motor_name': 'D19-INJ',
    'chamber_diameter': 0.1, 'chamber_length': 0.3,
    'throat_diameter': 0.05, 'exit_diameter': 0.2,
    'thrust': 10000.0, 'chamber_pressure': 30.0,
    'injector_design': {'number_of_orifices': 125,
                        'orifice_diameter': 0.000957,
                        'injector_type': 'unlike_impinging'},
}


class TestP9B123EnjektorKirpmasiBildiriliyor:
    """ÖLÇÜM (once.json): ``orifice_count = 125`` yayımlanıyordu, STL'e
    giden plaka ``MESH_MAX_INJECTOR_ORIFICES = 16`` ile kırpılmıştı ve
    dönen sözlüğün tamamı tarandığında kırpmayı bildiren alan YOKTU."""

    @pytest.fixture(scope='class')
    def cizim(self):
        montaj = _sessiz(CV.MotorCADDesigner().generate_3d_motor_assembly,
                         dict(SIVI_125))
        return (montaj.get('technical_drawings') or {}).get('injector') or {}

    def test_mesh_delik_sayisi_YAYIMLANIYOR(self, cizim):
        assert cizim['orifice_count'] == 125, 'tasarım sayısı korunmalı'
        assert cizim['orifice_count_in_mesh'] == CV.MESH_MAX_INJECTOR_ORIFICES

    def test_kunye_farki_ADIYLA_soyluyor(self, cizim):
        kunye = str(cizim['orifice_count_in_mesh_basis'])
        assert '125' in kunye and str(CV.MESH_MAX_INJECTOR_ORIFICES) in kunye
        assert 'MESH_MAX_INJECTOR_ORIFICES' in kunye, (
            'kullanıcı sınırı hangi kuralın koyduğunu görmeli')
        assert 'not a drilling master' in kunye

    def test_sinir_IKINCI_KEZ_yazilmiyor(self):
        """Kırpma kuralı TEK tanım noktasından: üretici ile çizim aynı
        yardımcıyı okur."""
        assert CV._mesh_orifice_count(125) == CV.MESH_MAX_INJECTOR_ORIFICES
        assert CV._mesh_orifice_count(3) == 3
        assert CV._mesh_orifice_count(0) == 0
        assert CV._mesh_orifice_count(None) == 0

    def test_kirpilmayan_kosuda_yanlis_alarm_YOK(self):
        kunye = CV._mesh_orifice_basis(8)
        assert 'no mesh cap applied' in kunye
        assert CV._mesh_orifice_count(8) == 8

    def test_delik_yoksa_bunu_da_soyluyor(self):
        assert CV._mesh_orifice_count(0) == 0
        assert 'no orifices are drilled' in CV._mesh_orifice_basis(0)


# =====================================================================
# P15B4-11 — toplam boy ÖLÇÜLÜR, CAD kendi dördüncü tanımını basmaz
# =====================================================================
class TestP15B411ToplamBoyOlculuyor:
    """ÖLÇÜM (once.json, 1 kN hibrit): CAD 771,7501 mm basıyordu; motorun
    yayımladığı iki tanım 771,2074 (kamara+lüle) ve 772,2390 (kapak dâhil)
    idi — CAD'inki üçüncü bir sayıydı ve künyesi yoktu."""

    @pytest.fixture(scope='class')
    def montaj(self):
        return _sessiz(CV.MotorCADDesigner().generate_3d_motor_assembly,
                       dict(SIVI_125))

    def test_yayimlanan_boy_KATIDAN_olculuyor(self, montaj):
        gs = montaj['performance_summary']['geometry_summary']
        boy = gs['total_length']
        assert boy is not None and math.isfinite(boy) and boy > 0
        assert 'MEASURED on the generated 3D solids' in gs['total_length_basis']

        # Sayı gerçekten ÇİZİLEN katıların eksenel zarfı mı? Bağımsız ölç.
        z_min, z_max = None, None
        for _ad, mesh in montaj['assembly_meshes']:
            zs = [float(v[2]) for v in mesh.vertices]
            z_min = min(zs) if z_min is None else min(z_min, min(zs))
            z_max = max(zs) if z_max is None else max(z_max, max(zs))
        assert boy == pytest.approx((z_max - z_min) * 1000.0, rel=1e-9)

    def test_formulun_sayisi_KAYBOLMUYOR_ama_adi_tahmin(self, montaj):
        gs = montaj['performance_summary']['geometry_summary']
        tahmin = gs['total_length_estimate']
        assert tahmin is not None and tahmin > 0
        kunye = str(gs['total_length_estimate_basis'])
        assert kunye.startswith('ESTIMATE')
        # Künye motorun KENDİ tanımlarını adıyla anmalı: okuyucu hangi
        # sayıyla kıyaslayacağını bilmeli.
        assert 'total_motor_length_with_caps_mm' in kunye
        assert 'total_motor_length_chamber_nozzle_mm' in kunye

    def test_kati_yoksa_boy_BASILMIYOR(self):
        """Fail-closed: özet katılar olmadan çağrılırsa ölçüm uydurulmaz."""
        gs = _sessiz(CV.MotorCADDesigner()._generate_cad_performance_summary,
                     dict(SIVI_125))['geometry_summary']
        assert gs['total_length'] is None
        assert 'not measured' in str(gs['total_length_basis'])
        # Tahmin alanı ise dolu kalır (alan kaybı değil, künye dürüstlüğü).
        assert gs['total_length_estimate'] is not None

    def test_olculen_boy_ZARF_CAPIYLA_ayni_kurali_izliyor(self, montaj):
        """İki alan da aynı sözleşmeye tabi: ölçüm varsa basılır, yoksa
        None ve künye nedenini söyler."""
        gs = montaj['performance_summary']['geometry_summary']
        for olculen, kunye in (('total_length', 'total_length_basis'),
                               ('max_diameter', 'max_diameter_basis')):
            if gs[olculen] is None:
                assert 'not measured' in str(gs[kunye])
            else:
                assert 'MEASURED' in str(gs[kunye])


# =====================================================================
# P14M3-07 — Isp haçı: sayı gönderilmediyse haç ÇİZİLMEZ
# =====================================================================
class TestP14M307TasarimNoktasiKunyesi:
    """Kalem defterde ``[EK (bekçi)]`` etiketliydi: ürün P8B4-16 ile
    (ÖH D15 / fea-viz a2) onarılmış — uç katmanındaki sayısal varsayılanlar
    (Pc 50 / O/F 3,5 / Isp 300) kalktı ve künye ``design_point_source``
    beyanını sınıyor. ÖLÇÜLDÜ (mutasyon.json):

    * ``MI`` (künye koşulsuz 'motor result') → mevcut bekçilerde 2 KIRMIZI,
    * ``MI2`` (varsayılanlar GÖRSELLEŞTİRME katmanına konur) → 78 passed,
      yani YEŞİL. Mevcut bekçiler kusuru UÇ katmanında ölçüyor; aynı
      uydurmanın çizim katmanında yapılması görünmüyordu.

    Bu sınıf o boşluğu kapatır: iddia katmandan bağımsızdır — çağıran sayı
    vermediyse figürde tasarım noktası haçı olmaz.
    """

    OKSITLEYICI = {'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
                   'grid_n': 3}

    def _figur(self, ek):
        from hrma.visualization import visualization as VZ
        veri = dict(self.OKSITLEYICI)
        veri.update(ek)
        ham = _sessiz(
            VZ.create_chamber_pressure_mixture_ratio_3d_surface, veri)
        return json.loads(ham) if isinstance(ham, str) else ham

    def _hac_izleri(self, fig):
        return [t for t in (fig.get('data') or [])
                if str(t.get('name') or '').startswith('Design point')]

    def test_sayi_gonderilmediyse_HAC_CIZILMIYOR(self):
        """Fail-closed: üç sayıdan biri bile yoksa nokta yayımlanmaz."""
        fig = self._figur({})
        assert self._hac_izleri(fig) == [], (
            'hiçbir tasarım sayısı gönderilmediği hâlde haç çizildi — '
            'üreteç varsayılanı motor sonucu gibi okunuyor')

    def test_eksik_ISP_de_haci_dusuruyor(self):
        fig = self._figur({'optimal_chamber_pressure': 60.0,
                           'optimal_of_ratio': 4.0})
        assert self._hac_izleri(fig) == []

    def test_sayi_geldiyse_KUNYE_kaynagi_soyluyor(self):
        """Beyan yoksa 'motor result' denemez (P14M3-07'nin manşeti)."""
        fig = self._figur({'optimal_chamber_pressure': 60.0,
                           'optimal_of_ratio': 4.0, 'base_isp': 150.0})
        haclar = self._hac_izleri(fig)
        if not haclar:
            pytest.skip('bu çalışma noktasında haç yüzeyin üstünde kaldı '
                        '(P14H1-C1 kapısı) — künye iddiası uygulanamaz')
        adlar = [str(t.get('name')) for t in haclar]
        assert adlar == ['Design point (as supplied)'], adlar

    def test_beyan_varsa_motor_result_diyebiliyor(self):
        """Ters yarı: gerçek beyanla künye hakkını kazanır."""
        fig = self._figur({'optimal_chamber_pressure': 60.0,
                           'optimal_of_ratio': 4.0, 'base_isp': 150.0,
                           'design_point_source': 'solver'})
        haclar = self._hac_izleri(fig)
        if not haclar:
            pytest.skip('haç yüzeyin üstünde kaldı — künye iddiası '
                        'uygulanamaz')
        assert [str(t.get('name')) for t in haclar] == [
            'Design point (motor result)']
