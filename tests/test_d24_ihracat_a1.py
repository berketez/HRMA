"""ÖH D24 / ihracat a1 bekçileri.

Kapsanan kalemler:
  P15B4-04  iki ZIP ucunun katı parça listesi + STEP/STL enjektör çelişkisi
  OH-D23-06 /api/export-dxf bit-kararsızlığı (kanonikleştirme)
  OH-D23-05 (a) database_integrations state_reason varsayılanı
            (b) cad_visualization kesici ``is_volume`` kapısı
  OH-D18-06 STL indirme penceresinin arayüzde okunması
  P9B1-27   enjektör plakası ⟷ yakıt tanesi girişimi
  P9B1-28/29/30 ölü sembollerin geri gelmemesi
  P9B2-21   tek orifisli enjektör yüzünde daire sayısı
  P9B2-23   birim beyanı ⟷ geometrik özdeşlik çelişkisi

Her bekçi TERS-MUTASYONLA doğrulandı; kırmızı kanıtları
``docs/scofield/raw/OH/D24/ihracat/a1/mutasyon.json``.
"""
import ast
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess

import pytest

from tests.bagimlilik_kapisi import kurulu_mu

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: STEP üreten düğümlerin kapısı. CI'ın ana ``pytest`` işi build123d'yi
#: BİLEREK kurmaz; bu düğümler orada atlanır, ``step-export`` işinde koşar.
#: Kurulum sorusu find_spec ile sorulur (``tests/bagimlilik_kapisi.py``):
#: ``step_export.BUILD123D_AVAILABLE`` ``except Exception`` ile kurulduğu
#: için "kurulu değil" gerekçesine dayanak olamaz
#: (``test_ci_kapsam_kapisi.py::TestAtlamaGerekcesiDurust``).
_STEP_GEREKLI = pytest.mark.skipif(
    not kurulu_mu('build123d'),
    reason='build123d kurulu değil (STEP üretimi atlanır)')


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


@pytest.fixture(scope='module')
def kati_sonuc(istemci):
    r = _sessiz(istemci.post, '/calculate_solid', json={
        'motor_name': 'D24-KATI', 'propellant_type': 'apcp',
        'grain_type': 'bates', 'chamber_pressure': 40.0,
        'thrust': 5000.0, 'burn_time': 3.0, 'chamber_diameter': 100.0,
        'grain_length': 500.0, 'core_diameter': 30.0,
        'expansion_ratio': 8.0})
    assert r.status_code == 200
    return r.get_json()


#: Enjektör PANELİ sonucu — ``injector_results``. Ürün yolunda kullanıcı
#: enjektör panelini koşturunca motor sonucuna eklenir.
ENJEKTOR_PANELI = {
    'number_of_orifices': 24, 'orifice_diameter_mm': 1.2,
    'injector_type': 'showerhead',
    'plate_structural': {'plate_thickness_mm': 6.0,
                         'plate_diameter_mm': 90.0,
                         'plate_mass_kg': 0.31,
                         'material': 'aluminum_6061'},
}


def _zip_parcalari(veri):
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(veri))
    adlar = z.namelist()
    stl = {os.path.splitext(os.path.basename(a))[0].lower()
           for a in adlar if a.lower().endswith('.stl')}
    # STEP dosya adları motor adıyla ÖN EKLENİR (``<ad>_injector.step``);
    # karşılaştırma parça adı üzerinden yapılır.
    step = set()
    for a in adlar:
        if not a.lower().endswith('.step'):
            continue
        taban = os.path.splitext(os.path.basename(a))[0].lower()
        for parca in ('assembly', 'chamber', 'nozzle', 'fuel_grain',
                      'injector', 'tank'):
            if taban == parca or taban.endswith('_' + parca):
                step.add(parca)
                break
        else:
            step.add(taban)
    return stl, step, adlar


# ---------------------------------------------------------------------------
# P15B4-04 — iki katı üreticisi aynı motoru anlatır
# ---------------------------------------------------------------------------
class TestP15B404KatiUreticiParcaListesi:
    """ÖLÇÜLDÜ (taban 88a29d3, once.json M1 alt vakası): enjektör paneli
    taşıyan katı sonuçta ``/api/export-complete-zip`` 5 STL / 4 STEP
    üretiyordu (enjektör STL'de vardı, STEP'te YOKTU) ve MANIFEST ikisine de
    "[OK]" yazıyordu.
    """

    @_STEP_GEREKLI
    def test_complete_zip_enjektoru_hem_stl_hem_step_ciziyor(
            self, istemci, kati_sonuc):
        yuk = dict(kati_sonuc)
        yuk['injector_results'] = dict(ENJEKTOR_PANELI)
        r = _sessiz(istemci.post, '/api/export-complete-zip',
                    json={'motor_data': yuk})
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        stl, step, _ = _zip_parcalari(r.get_data())
        assert 'injector' in stl, stl
        # KUSUR BUYDU: enjektör STL'de var, STEP'te yok.
        assert 'injector' in step, (
            'STL enjektör çiziyor ama STEP çizmiyor: %s / %s' % (stl, step))
        assert (stl - {'motor_assembly'}) == (step - {'assembly'}), (stl, step)

    def test_panel_step_uretecine_de_kanit_sayilir(self, kati_sonuc):
        """``resolve_injector_plan`` panel sonucunu okur (tek kanıt tanımı)."""
        from hrma.export.step_export import resolve_injector_plan
        yuk = dict(kati_sonuc)
        yuk['injector_results'] = dict(ENJEKTOR_PANELI)
        plan = resolve_injector_plan(yuk, motor_type='hybrid')
        assert plan['claimed'] is True
        assert plan['circuits'], plan

    def test_panel_yokken_davranis_degismez(self, kati_sonuc):
        """Yedek YALNIZ yedektir: panel yoksa iddia da yoktur."""
        from hrma.export.step_export import resolve_injector_plan
        plan = resolve_injector_plan(dict(kati_sonuc), motor_type='solid')
        assert plan['claimed'] is False

    def test_kati_ucu_enjektoru_suzmeye_devam_eder(self, istemci, kati_sonuc):
        """``/export_solid_motor_cad`` motor tipini BİLİR: katıda enjektör yok."""
        yuk = dict(kati_sonuc)
        yuk['injector_results'] = dict(ENJEKTOR_PANELI)
        r = _sessiz(istemci.post, '/export_solid_motor_cad',
                    json={'results': yuk})
        assert r.status_code == 200
        stl, step, _ = _zip_parcalari(r.get_data())
        assert 'injector' not in stl
        assert 'injector' not in step

    def test_ayrisma_kapisi_gorunur(self):
        """Kapı kodu, iki üretici ayrışırsa 422 vermek üzere yerinde."""
        kaynak = open(os.path.join(KOK, 'hrma/app.py'),
                      encoding='utf-8').read()
        assert 'generators_disagree_on_parts' in kaynak
        assert "cizilen['step'].add" in kaynak


# ---------------------------------------------------------------------------
# OH-D23-06 — DXF bit-kararsızlığı
# ---------------------------------------------------------------------------
class TestOHD2306DxfKanonik:
    """ÖLÇÜLDÜ (taban 88a29d3, once.json M2): aynı ağaç, aynı gövde, üç
    ardışık çağrı -> 200 / 45.491 B ama sha256 ÜÇÜ DE FARKLI.
    """

    def test_kanonik_metin_ardısık_kosumlarda_ayni(self, istemci, kati_sonuc):
        from hrma.export.drawing_generator import canonicalize_dxf_text
        ozetler = set()
        ham = set()
        for _ in range(3):
            r = _sessiz(istemci.post, '/api/export-dxf',
                        json={'motor_data': kati_sonuc})
            assert r.status_code == 200
            veri = r.get_data()
            ham.add(hashlib.sha256(veri).hexdigest())
            ozetler.add(
                hashlib.sha256(canonicalize_dxf_text(veri)).hexdigest())
        assert len(ozetler) == 1, 'kanonik DXF hâlâ kararsız'
        # Ham akışın kararsız OLDUĞU bu bekçinin varlık sebebidir; kararlı
        # hâle gelirse (ezdxf sürümü) bu bekçi yine doğrudur, yalnız
        # aşağıdaki iddia gevşetilir.
        assert len(ham) >= 1

    def test_kanonik_gercek_degisikligi_GIZLEMEZ(self, istemci):
        """Kanonikleştirme yalnız damgayı siler; geometri değişirse görünür."""
        from hrma.export.drawing_generator import canonicalize_dxf_text

        def coz(itki):
            r = _sessiz(istemci.post, '/calculate_solid', json={
                'motor_name': 'D24', 'propellant_type': 'apcp',
                'grain_type': 'bates', 'chamber_pressure': 40.0,
                'thrust': itki, 'burn_time': 3.0, 'chamber_diameter': 100.0,
                'grain_length': 500.0, 'core_diameter': 30.0,
                'expansion_ratio': 8.0})
            d = _sessiz(istemci.post, '/api/export-dxf',
                        json={'motor_data': r.get_json()})
            return hashlib.sha256(
                canonicalize_dxf_text(d.get_data())).hexdigest()

        assert coz(5000.0) != coz(9000.0)

    def test_kanonik_yalniz_kararsiz_alanlari_maskeler(self):
        from hrma.export.drawing_generator import (
            DXF_CANONICAL_PLACEHOLDER, canonicalize_dxf_text)
        metin = ('9\n$FINGERPRINTGUID\n  2\n{AAAA}\n'
                 '9\n$TDCREATE\n 40\n2461289.44\n'
                 '  0\n  1\n1.4.4 @ 2026-09-05T07:41:20.709149+00:00\n'
                 '  0\nLWPOLYLINE\n 10\n123.456\n')
        k = canonicalize_dxf_text(metin)
        assert '{AAAA}' not in k
        assert '2461289.44' not in k
        assert '1.4.4 @' not in k
        assert k.count(DXF_CANONICAL_PLACEHOLDER) == 3
        assert '123.456' in k            # geometriye dokunulmaz
        assert 'LWPOLYLINE' in k


# ---------------------------------------------------------------------------
# OH-D23-05 (a) — state_reason varsayılanı fail-closed'dır
# ---------------------------------------------------------------------------
class TestOHD2305StateReasonBekcisi:
    """Fable-D18 kısım-2 bulgu 22: varsayılan ``'outside_liquid_band'``
    fail-closed diye yorumlanmıştı ama BEKÇİSİZDİ — varsayılan
    ``'not_modelled'`` yapılınca TestP9B512HalGerekcesi 4/4 yeşil kalıyordu.
    """

    def test_state_reason_TASIMAYAN_kaynakta_yogunluk_YAYIMLANMAZ(
            self, monkeypatch):
        import hrma.data.database_integrations as di

        def sahte(key, temperature):
            # Eski/yabancı bir sağlayıcı: yapısal ``state_reason`` YOK.
            return {'density': 1141.0,
                    'note': 'stored reference value',
                    'source': 'sahte-saglayici',
                    'reference_T_K': 90.19}

        monkeypatch.setattr(di, 'oxidizer_reference_density', sahte)
        out = di.NistWebBookAPI()._get_fallback_properties('O2', 293.15)
        assert 'density' not in out, (
            'state_reason TAŞIMAYAN bir kaynağın sayısı yayımlandı: %r'
            % out.get('density'))
        assert 'density_error' in out
        assert 'O2' in out['density_error']

    def test_state_reason_bant_ICI_dediginde_yogunluk_yayimlanir(
            self, monkeypatch):
        """Kapı KÖRLEMESİNE kapalı değil: yapısal beyan varsa sayı geçer."""
        import hrma.data.database_integrations as di

        def sahte(key, temperature):
            return {'density': 1141.0, 'note': 'in band',
                    'source': 'sahte-saglayici',
                    'state_reason': 'in_liquid_band', 'reference_T_K': 90.19}

        monkeypatch.setattr(di, 'oxidizer_reference_density', sahte)
        out = di.NistWebBookAPI()._get_fallback_properties('O2', 90.19)
        assert out.get('density') == 1141.0
        assert 'density_error' not in out

    def test_urun_kodunda_varsayilan_HALA_fail_closed(self):
        """Varsayılan dizesi değişirse (mutasyon) bu bekçi kırmızıya döner."""
        kaynak = open(os.path.join(KOK, 'hrma/data/database_integrations.py'),
                      encoding='utf-8').read()
        assert "rho.get('state_reason', 'outside_liquid_band')" in kaynak


# ---------------------------------------------------------------------------
# OH-D23-05 (b) — kesici ``is_volume`` kapısının KENDİ bekçisi
# ---------------------------------------------------------------------------
class TestOHD2305KesiciKapisi:
    """Fable-D18 kısım-2 bulgu 23: ilk (kesici) ``is_volume`` kapısı
    sökülünce TestOHD1606EnjektorPlakasi 5/5 yeşil kalıyordu — çünkü ikinci
    (plaka) kapı yakalıyordu. İlk kapının kendi kırmızısı yoktu.
    """

    def _md(self, n, d_m):
        return {'chamber_diameter': 0.1,
                'injector_results': {
                    'number_of_orifices': n,
                    'orifice_diameter_mm': d_m * 1000.0,
                    'plate_structural': {'plate_thickness_mm': 6.0,
                                         'plate_diameter_mm': 90.0}},
                'injector_orifices': n, 'orifice_diameter': d_m}

    def test_kesici_katisi_gecersizse_ADIYLA_reddedilir(self, monkeypatch):
        """İLK kapı (kesici katısı) kendi adıyla ateşlenir.

        ÖLÇÜLDÜ (D24, ``once_kesici.json``): kapı ÜRÜN YÜKÜYLE ateşlenemiyor.
        Delikler D18'de MİLİMETRE uzayına taşındığından
        ``trimesh.creation.cylinder`` ürünün üretebileceği HER çapta
        (0,001 .. 1,2 mm) su geçirmez bir katı veriyor ve
        ``trimesh.util.concatenate`` çakışan silindirlerde bile
        ``is_volume=True`` döndürüyor — 400 x Ø4,00 mm gibi tümüyle iç içe
        geçmiş bir desende bile. Yani kusuru İKİNCİ kapı
        (``injector_plate_not_a_solid``) yakalıyor ve Fable'ın ölçtüğü şey
        buydu: ilk kapı sökülünce hiçbir bekçi kırmızıya dönmüyordu.

        Kapı KALDIRILMADI (kütüphane davranışı değişirse tek savunma odur),
        ama bekçisi artık DAVRANIŞI ölçüyor: birleştirici DİKİŞİNDEN
        su geçirmez OLMAYAN bir kesici verildiğinde ilk kapının kendi
        gerekçesi dönmeli — ikinci kapının gerekçesi DEĞİL.
        """
        import trimesh
        from hrma.export import cad_visualization as cv

        gercek = trimesh.util.concatenate

        def sahte(*a, **kw):
            m = gercek(*a, **kw)
            # Tek üçgeni sil: ağ artık kapalı bir hacim değil.
            m.update_faces([i for i in range(len(m.faces)) if i != 0])
            return m

        monkeypatch.setattr(trimesh.util, 'concatenate', sahte)
        with pytest.raises(ValueError) as e:
            _sessiz(cv.MotorCADDesigner()._create_injector_head, 0.1,
                    self._md(20, 0.0012))
        mesaj = str(e.value)
        assert 'injector_orifices_not_manufacturable' in mesaj, mesaj
        assert 'injector_plate_not_a_solid' not in mesaj, mesaj

    def test_ikinci_kapi_da_kendi_adiyla_ateslenir(self):
        """İki kapı ayrı ayrı ölçülür (biri diğerini maskelemesin)."""
        from hrma.export.cad_visualization import MotorCADDesigner
        with pytest.raises(ValueError) as e:
            _sessiz(MotorCADDesigner()._create_injector_head, 0.1,
                    self._md(400, 0.004))
        assert 'injector_plate_not_a_solid' in str(e.value), str(e.value)

    def test_ilk_kapi_urun_kodunda_DURUYOR(self):
        """İlk kapının varlığı doğrudan ölçülür (ikinci kapı onu maskeler)."""
        kaynak = open(os.path.join(KOK, 'hrma/export/cad_visualization.py'),
                      encoding='utf-8').read()
        agac = ast.parse(kaynak)
        bulundu = False
        for d in ast.walk(agac):
            if (isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and d.name == '_create_injector_head'):
                govde = ast.get_source_segment(kaynak, d) or ''
                bulundu = ('injector_orifices_not_manufacturable' in govde
                           and 'kesici_mesh' in govde
                           and "getattr(kesici_mesh, 'is_volume'" in govde)
        assert bulundu, ('kesicilerin is_volume kapısı _create_injector_head '
                         'içinden kalkmış')

    def test_saglikli_plaka_HALA_uretilir(self):
        from hrma.export.cad_visualization import MotorCADDesigner
        mesh = _sessiz(MotorCADDesigner()._create_injector_head, 0.1,
                       self._md(20, 0.0012))
        assert bool(getattr(mesh, 'is_volume', False))


# ---------------------------------------------------------------------------
# P9B1-27 — enjektör plakası ⟷ yakıt tanesi girişimi
# ---------------------------------------------------------------------------
class TestP9B127PlakaTaneGirisimi:
    """ÖLÇÜLDÜ (taban 88a29d3, once.json M3): 30 mm plakada plaka
    [6,00; 36,00] mm, tane [35,00; 485,32] mm -> 1,0000 mm eksenel örtüşme,
    1.810,30 mm³ gerçek kesişim; montaj bunu HİÇBİR yerde söylemiyordu.
    """

    def _cad(self, kati_sonuc, t_mm):
        from hrma.export.cad_visualization import MotorCADDesigner
        md = dict(kati_sonuc)
        panel = dict(ENJEKTOR_PANELI)
        panel['plate_structural'] = dict(ENJEKTOR_PANELI['plate_structural'])
        panel['plate_structural']['plate_thickness_mm'] = t_mm
        md['injector_results'] = panel
        return _sessiz(MotorCADDesigner().generate_3d_motor_assembly, md)

    def _kutu(self, cad, ad):
        for n, m in (cad.get('assembly_meshes') or []):
            if n == ad:
                return (float(m.bounds[0][2]) * 1000.0,
                        float(m.bounds[1][2]) * 1000.0)
        return None

    @pytest.mark.parametrize('t_mm', [6.0, 30.0])
    def test_plaka_tane_ile_CAKISMAZ(self, kati_sonuc, t_mm):
        cad = self._cad(kati_sonuc, t_mm)
        plaka = self._kutu(cad, 'Injector')
        tane = self._kutu(cad, 'Fuel Grain')
        assert plaka is not None and tane is not None, cad.get('error')
        ortusme = min(plaka[1], tane[1]) - max(plaka[0], tane[0])
        assert ortusme <= 0.0, (
            'plaka %s mm, tane %s mm -> %.4f mm çakışma'
            % (plaka, tane, ortusme))

    def test_plaka_kapak_IC_YUZUNE_oturur(self, kati_sonuc):
        """Sabit 0,006 + 0,015 m ofseti geri gelmesin."""
        cad = self._cad(kati_sonuc, 6.0)
        plaka = self._kutu(cad, 'Injector')
        assert plaka is not None
        assert abs(plaka[0]) < 1e-6, plaka
        assert abs((plaka[1] - plaka[0]) - 6.0) < 1e-3, plaka

    def test_gercek_cakisma_ADIYLA_reddedilir(self, kati_sonuc):
        """Tane plakanın içinde başlıyorsa montaj YAYIMLANMAZ."""
        from hrma.export.cad_visualization import MotorCADDesigner
        md = dict(kati_sonuc)
        panel = dict(ENJEKTOR_PANELI)
        panel['plate_structural'] = dict(ENJEKTOR_PANELI['plate_structural'])
        # Tane 35 mm'de başlıyor; 60 mm plaka kaçınılmaz olarak içine girer.
        panel['plate_structural']['plate_thickness_mm'] = 60.0
        md['injector_results'] = panel
        cad = _sessiz(MotorCADDesigner().generate_3d_motor_assembly, md)
        hata = str(cad.get('error') or '')
        assert 'injector_plate_intersects_fuel_grain' in hata, hata
        assert not any(
            n == 'Injector' for n, _ in (cad.get('assembly_meshes') or []))

    def test_girisim_toleransi_TEK_KAYNAK(self):
        from hrma.export import cad_visualization as cv
        assert cv._MONTAJ_GIRISIM_TOLERANS_MM == 1e-3
        kaynak = open(os.path.join(KOK, 'hrma/export/cad_visualization.py'),
                      encoding='utf-8').read()
        assert '0.006 + 0.015' not in kaynak


# ---------------------------------------------------------------------------
# P9B1-28 / -29 / -30 — ölü kod geri gelmesin
# ---------------------------------------------------------------------------
class TestP9B128OluKodGeriGelmez:

    @pytest.mark.parametrize('ad', ['_create_combustion_chamber',
                                    '_create_nozzle', '_create_fuel_grain',
                                    'generate_cad_report'])
    def test_silinen_sembol_geri_gelmedi(self, ad):
        kaynak = open(os.path.join(KOK, 'hrma/export/cad_visualization.py'),
                      encoding='utf-8').read()
        agac = ast.parse(kaynak)
        adlar = {d.name for d in ast.walk(agac)
                 if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert ad not in adlar, (
            '%s geri geldi; ölçüldü: 0 ürün okuyucusu vardı ve düzeltilmiş '
            'kusurların sessiz-yedekli eski sürümünü taşıyordu' % ad)

    def test_kurucu_kaldirildi_ve_alanlar_yok(self):
        from hrma.export.cad_visualization import MotorCADDesigner
        d = MotorCADDesigner()
        assert not hasattr(d, 'materials_db')
        assert not hasattr(d, 'standard_dimensions')
        assert '__init__' not in MotorCADDesigner.__dict__

    def test_hayatta_kalan_kardesler_DURUYOR(self):
        """Silme, canlı ``_create_nozzle_mesh`` ailesine dokunmadı."""
        kaynak = open(os.path.join(KOK, 'hrma/export/cad_visualization.py'),
                      encoding='utf-8').read()
        adlar = {d.name for d in ast.walk(ast.parse(kaynak))
                 if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for ad in ('_create_nozzle_mesh', '_create_nozzle_cross_section',
                   '_create_combustion_chamber_cross_section',
                   '_create_injector_head'):
            assert ad in adlar, ad


# ---------------------------------------------------------------------------
# P9B2-21 — tek orifiste çizilen daire sayısı
# ---------------------------------------------------------------------------
class TestP9B221EnjektorYuzDaireSayisi:
    """ÖLÇÜLDÜ (taban 88a29d3, once.json M5): n = 1 için başlık
    "1 x d1.20 mm" derken yüzde 2 daire çiziliyordu.
    """

    @staticmethod
    def _daireler(n):
        from hrma.export import drawing_generator as dg
        tutucu = {}

        def _tut(fig, width=None, height=None):
            tutucu['fig'] = fig
            return b''

        gercek = dg._render_or_raise
        try:
            dg._render_or_raise = _tut
            _sessiz(dg._injector_face_png, {
                'chamber_diameter': 0.1,
                'injector_design': {'number_of_orifices': n,
                                    'orifice_diameter_mm': 1.2,
                                    'injector_type': 'showerhead'}}, 500)
        finally:
            dg._render_or_raise = gercek
        fig = tutucu['fig']
        daire = [s for s in (fig.layout.shapes or []) if s.type == 'circle']
        return len(daire), fig.layout.title.text

    @pytest.mark.parametrize('n', [1, 2, 3, 4, 7, 20, 125])
    def test_cizilen_daire_sayisi_BASLIKLA_ayni(self, n):
        adet, baslik = self._daireler(n)
        assert adet == n, ('n=%d için %d daire çizildi; başlık: %s'
                           % (n, adet, baslik))
        assert ('%d x d' % n) in baslik


# ---------------------------------------------------------------------------
# P9B2-23 — birim beyanı ⟷ geometrik özdeşlik çelişkisi
# ---------------------------------------------------------------------------
class TestP9B223BirimCeliskisi:
    """ÖLÇÜLDÜ (taban 88a29d3, once.json M6): ``units: "m"`` beyan eden
    sözlüğün çıktısı, çelişkinin hiç olmadığı ``units: "mm"`` sözlüğünkiyle
    BİREBİR aynıydı; çelişki hiçbir yerde bildirilmiyordu.
    """

    AV_UYUMLU = {'diameter': 40.0, 'height': 20.0,
              'vane_radial_length_mm': 20.0, 'units': 'mm'}
    AV_CELISKILI = {'diameter': 40.0, 'height': 20.0,
                 'vane_radial_length_mm': 20.0, 'units': 'm'}

    def test_celiski_ADIYLA_bildirilir(self):
        from hrma.export.cad_export import normalize_anti_vortex_mm
        o = normalize_anti_vortex_mm(dict(self.AV_CELISKILI))
        c = o.get('unit_declaration_conflict')
        assert isinstance(c, dict), o
        assert c['declared_units'] == 'm'
        assert c['resolved_units'] == 'mm'
        assert 'unit_declaration_conflict' in o['unit_resolution_basis']

    def test_celiski_YOKKEN_alan_da_yok(self):
        from hrma.export.cad_export import normalize_anti_vortex_mm
        for gir in (dict(self.AV_UYUMLU),
                    {'diameter': 40.0, 'height': 20.0,
                     'vane_radial_length_mm': 20.0}):
            o = normalize_anti_vortex_mm(gir)
            assert 'unit_declaration_conflict' not in o, o

    def test_olculen_deger_DEGISMEDI(self):
        """Seçim özdeşlikte kalır; yalnız çelişki artık görünür."""
        from hrma.export.cad_export import normalize_anti_vortex_mm
        a = normalize_anti_vortex_mm(dict(self.AV_UYUMLU))
        b = normalize_anti_vortex_mm(dict(self.AV_CELISKILI))
        assert a['diameter'] == b['diameter'] == 40.0
        assert a['units'] == b['units'] == 'mm'


# ---------------------------------------------------------------------------
# OH-D18-06 — STL indirme penceresi arayüzde okunur
# ---------------------------------------------------------------------------
class TestOHD1806IndirmePenceresi:
    """ÖLÇÜLDÜ (taban 88a29d3, once.json M7): ``stl_download_window_s``
    yanıtta 1 kez yayımlanıyor, ``app.js``te 0 kez okunuyordu; uzun açık
    sekmede kullanıcı bağlantının öldüğünü ancak 410 alınca öğreniyordu.
    """

    @staticmethod
    def _app_js_kod():
        """app.js — YORUMLAR AYIKLANMIŞ hâli.

        Ham metinde arama yapmak yetmez: bu onarımın kendi açıklama satırı da
        alan adını yazıyor, dolayısıyla okuma silinse bile ham sayım >= 1
        kalırdı (ölçüldü: ilk mutasyon turunda bekçi yeşil kaldı).
        """
        ham = open(os.path.join(KOK, 'hrma/static/js/app.js'),
                   encoding='utf-8').read()
        kod = re.sub(r'/\*.*?\*/', '', ham, flags=re.S)
        kod = '\n'.join(re.sub(r'//.*$', '', s) for s in kod.split('\n'))
        return kod

    def test_arayuz_pencereyi_OKUYOR(self):
        kod = self._app_js_kod()
        assert 'cad.stl_download_window_s' in kod, (
            'arayüz indirme penceresini KOD içinde okumuyor')

    def test_arayuz_kalan_sureyi_gosteriyor(self):
        kod = self._app_js_kod()
        assert 'stlPencereMetni' in kod
        assert 'stlDownloadExpiresAt' in kod
        # Süre beyan edilmemişse UYDURULMAZ:
        assert 'stlWindowUndeclared' in kod

    # -- ÖH D33-KOLAY · OH-D18-06 DENETİM RET'i --------------------------
    # Yukarıdaki üç bekçi app.js'in KAYNAK METNİNİ ölçüyor. Yardımcının
    # TANIMI orada durduğu sürece üçü de yeşil kalır — ÇAĞRILIP
    # çağrılmadığını hiçbiri görmez. D30 a1 app.js'teki ölü
    # `generateCompletePackage` kopyasını sökerken TEK çağrı sahası da
    # gitti; onarım geriledi, bekçiler yeşil kaldı (ölçüm: D33
    # a1/once.json · M3 — tanım 1, çağrı 0). Aşağıdakiler CANLI yolu ve
    # DAVRANIŞI ölçer.

    @staticmethod
    def _canli_govde():
        """advanced.html — canlı `generateCompletePackage` gövdesi."""
        ham = open(os.path.join(KOK, 'hrma/templates/advanced.html'),
                   encoding='utf-8').read()
        bas = ham.index('async function generateCompletePackage()')
        i = ham.index('{', bas)
        derinlik, son = 0, i
        while son < len(ham):
            if ham[son] == '{':
                derinlik += 1
            elif ham[son] == '}':
                derinlik -= 1
                if derinlik == 0:
                    break
            son += 1
        govde = ham[bas:son + 1]
        return '\n'.join(re.sub(r'//.*$', '', r) for r in govde.split('\n'))

    def test_canli_basari_satiri_pencereyi_okuyor(self):
        """Çağrı CANLI şablonda, başarı satırında olmalı.

        `generateCompletePackage`ın ürüne ulaşan sürümü advanced.html
        içindeki satır içi sürümdür (app.js kopyası D30 a1'de söküldü).
        Pencere metni oraya bağlı değilse kullanıcıya HİÇ ulaşmaz.
        """
        govde = self._canli_govde()
        assert 'stlPencereMetni(' in govde, (
            'pencere metni canlı başarı satırına bağlı değil: yardımcı '
            'app.js te tanımlı ama ürüne ulaşan yoldan çağrılmıyor '
            '(D30 a1 gerilemesinin aynısı)')
        assert 'completePackageGeneratedSuccessfully' in govde

    def test_canli_satir_sure_UYDURMUYOR(self):
        """Başarı satırı kendi başına dakika/saat sayısı yazmaz.

        Pencere TEK KAYNAKTAN (sunucunun beyanı) gelir. Şablona gömülü
        bir süre, sunucu bambaşka bir TTL yayımlarken ekranda sessizce
        yalan söylerdi.
        """
        govde = self._canli_govde()
        i = govde.index('completePackageGeneratedSuccessfully')
        satir = govde[i:i + 400]
        assert not re.search(r'\b(?:3600|60\s*(?:dk|min))\b', satir), (
            'başarı satırına gömülü pencere süresi: sunucunun beyanı '
            'yerine sabit sayı basılıyor')

    @pytest.mark.skipif(shutil.which('node') is None, reason='node yok')
    def test_pencere_metni_fail_closed(self, tmp_path):
        """DAVRANIŞ bekçisi: yardımcı üç girdide de sayı UYDURMUYOR.

        Metin varlığı değil, ÜRETİLEN DİZE ölçülür: (a) sunucu pencereyi
        beyan ettiyse sayı ve dosya adedi yazılır, (b) dosya var ama
        pencere beyan edilmemişse "beyan edilmedi" cümlesi çıkar ve sayı
        UYDURULMAZ, (c) beyan hiç yoksa dize BOŞTUR (ekrana hiçbir şey
        eklenmez). Canlı uçlar bugün sözleşmeyi yayımlamıyor, bu yüzden
        ürünün gördüğü dal (c)'dir ve boş kalması DOĞRUDUR.
        """
        ham = open(os.path.join(KOK, 'hrma/static/js/app.js'),
                   encoding='utf-8').read()
        bas = ham.index('function stlPencereMetni(')
        i = ham.index('{', bas)
        derinlik, son = 0, i
        while son < len(ham):
            if ham[son] == '{':
                derinlik += 1
            elif ham[son] == '}':
                derinlik -= 1
                if derinlik == 0:
                    break
            son += 1
        betik = (
            'var window = {};\n'
            'function T(k, f) { return f; }\n'
            'function TF(k, p, f) { return String(f).replace('
            '/\\{(\\w+)\\}/g, function (t, a) {\n'
            '    return (p && a in p) ? String(p[a]) : t; }); }\n'
            + ham[bas:son + 1] + '\n'
            'console.log(JSON.stringify({\n'
            '  beyanli: stlPencereMetni({ stl_files: ["a", "b", "c"],'
            ' stl_download_window_s: 3600 }),\n'
            '  beyansiz: stlPencereMetni({ stl_files: ["a"] }),\n'
            '  yok: stlPencereMetni(null),\n'
            '  bos: stlPencereMetni({ stl_files: [] })\n'
            '}));\n')
        yol = tmp_path / 'pencere.js'
        yol.write_text(betik, encoding='utf-8')
        p = subprocess.run(['node', str(yol)], capture_output=True,
                           text=True, timeout=120)
        assert p.returncode == 0, p.stderr
        out = json.loads(p.stdout)
        # (a) beyan varsa adet ve dakika ekrana çıkar
        assert '3' in out['beyanli'] and '60' in out['beyanli'], out['beyanli']
        assert '410' in out['beyanli'], (
            'bağlantının sona erdiğinde ne olacağı söylenmiyor')
        # (b) beyan yoksa SAYI UYDURULMAZ
        assert 'did not declare' in out['beyansiz'], out['beyansiz']
        assert not re.search(r'\d', out['beyansiz']), (
            'pencere beyan edilmemişken ekrana sayı uyduruluyor: '
            '%r' % out['beyansiz'])
        # (c) beyan hiç yoksa hiçbir şey eklenmez
        assert out['yok'] == '' and out['bos'] == '', (
            'sözleşme gelmediğinde başarı satırına artık metin ekleniyor')

    def test_pencere_TEK_KAYNAKTAN_yayimlaniyor(self):
        kaynak = open(os.path.join(KOK, 'hrma/app.py'),
                      encoding='utf-8').read()
        assert "'stl_download_window_s': _STL_REGISTRY_TTL_S" in kaynak
