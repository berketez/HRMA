# -*- coding: utf-8 -*-
"""ÖH Dalga-15 · ihracat kulvarı · aşama 1 — CAD/ihraç katmanı bekçileri.

Kapsanan defter kalemleri (hepsi P09 B1):

* **P9B1-04** — çizilen yakıt tanesi uydurma bir "liner" kadar küçültülüyordu
  (hibrit −%11,9 / katı −%9,5 hacim).
* **P9B1-07** — sıvı CAD panelinde çizilen lüle ``exit_radius`` argümanını
  kullanmıyordu (çizilen çıkış 116,96 mm ⟷ ``dimensions`` 217,56 mm).
* **P9B1-09** — dış görünümde kamara gövdesi ``[-L/2, +L/2]``e konuyordu,
  komşu parçalar ``[0, L]`` varsayıyordu (150 mm boşluk).
* **P9B1-10** — besleme hattı ve soğutma kanalı izleri base64 ``bdata``
  olarak yazılıyordu; gömülü plotly 1.58.5 çözemez, izler hiç çizilmez.
* **P9B1-11** — ``x=x_line * len(theta)`` numpy çarpımı hatları motorun 7 katı
  uzağa koyuyordu (1800 / 4200 mm).
* **P9B1-12** — KATI motora enjektör plakası konuyordu (kuru kütlenin %10,96'sı).
* **P9B1-13** — aynı koşuda dört ayrı enjektör plakası vardı.
* **P9B1-14** — kamara kütlesi çözücünün adlandırdığı malzeme yerine sessizce
  steel_4130 ile hesaplanıyordu.
* **P9B1-15** — ``bell_80`` lüle çizimde "conical 30 derece" etiketleniyordu.
* **P9B1-16** — boş sözlükten uydurma Ø100 x 300 mm motor üretiliyordu
  (bu kalem ÖLÇÜMLE ÇÜRÜTÜLDÜ; bekçi kapıyı KİLİTLER, ileride açılmasın diye).
* **P9B1-17** — ön kapak çizim sözlüğünde hiç görünmüyordu.

Her iddia ters-mutasyonla sınandı (bkz. ``docs/scofield/raw/OH/D15/ihracat/a1``).
"""
import contextlib
import io
import json
import math
import os

import pytest
from tests.support.kanit import kanit_gerekli

np = pytest.importorskip('numpy')
pytest.importorskip('trimesh')
pytest.importorskip('plotly')

from hrma.export.cad_visualization import (  # noqa: E402
    DetailedCADGenerator, MotorCADDesigner, NOT_AVAILABLE_SPEC,
    _chamber_material_resolved, _grain_outer_radius_m, _injector_evidence,
    _injector_plate_design, _nozzle_family, _nozzle_half_angles)
from hrma.export.motor_geometry import normalise_export_geometry  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'docs', 'scofield', 'raw', 'P09', 'cikti')

#: Mesh, daireyi çokgenle örneklediği için hacim daireselden biraz KÜÇÜKTÜR.
#: Ölçüldü (31 Ağustos 2026): sapma hibritte ve katıda BİREBİR aynı
#: (−%0,6413) — yani kalan fark tamamen fasetlemedir, geometrik kayıp değil.
FASET_TOLERANS_YUZDE = 1.5


def _fixture(name):
    yol = os.path.join(FIX, f'motor_{name}.json')
    if not os.path.exists(kanit_gerekli(yol)):
        pytest.skip(f'P09 fikstürü yok: {yol}')
    with open(kanit_gerekli(yol), encoding='utf-8') as fh:
        return json.load(fh)


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


@pytest.fixture(scope='module')
def montaj():
    """Üç motor tipinin CAD montajı (fikstür başına bir kez)."""
    d = MotorCADDesigner()
    out = {}
    for tip in ('hybrid', 'solid', 'liquid'):
        ham = _fixture(tip)
        out[tip] = {
            'ham': ham,
            'md': normalise_export_geometry(ham)[0],
            'cad': _sessiz(d.generate_3d_motor_assembly, dict(ham)),
        }
    return out


@pytest.fixture(scope='module')
def sivi_panel():
    """liquid.html'in GÖNDERDİĞİ gövdeyle sıvı CAD paneli (mm birimli)."""
    ham = _fixture('liquid')
    govde = {
        'motor_name': 'D15-SIVI', 'chamber_diameter': 61.53496638537138,
        'chamber_length': ham['chamber_length'], 'throat_diameter': 50,
        'exit_diameter': ham['exit_diameter'] * 1000,
        'nozzle_length': ham['chamber_length'] * 0.75,
        'injector_type': 'unlike_impinging', 'injector_holes': 24,
        'chamber_pressure': 100, 'thrust': ham['thrust'], 'isp': 320,
    }
    res = _sessiz(DetailedCADGenerator().generate_liquid_motor_cad, dict(govde))
    return {'govde': govde, 'res': res, 'fig': json.loads(res['plot_json'])}


def _iz(fig, ad):
    for t in fig['data']:
        if t.get('name') == ad:
            return t
    return None


def _eksen(iz, eksen):
    """bdata dâhil bir izin eksen dizisini python listesine indirger."""
    import base64
    v = iz.get(eksen)
    if isinstance(v, dict) and 'bdata' in v:
        return np.frombuffer(base64.b64decode(v['bdata']),
                             dtype=v.get('dtype', 'f8')).tolist()
    return list(v) if v is not None else []


def _mesh(cad, ad):
    return dict(cad['assembly_meshes']).get(ad)


def _rmax_mm(mesh):
    v = np.asarray(mesh.vertices)
    return float(np.hypot(v[:, 0], v[:, 1]).max()) * 1000.0


def _z_araligi_mm(mesh):
    v = np.asarray(mesh.vertices)
    return float(v[:, 2].min()) * 1000.0, float(v[:, 2].max()) * 1000.0


# ---------------------------------------------------------------------------
# P9B1-04 — tane dış çapı ÇÖZÜCÜNÜN çapıdır, uydurma liner kadar küçülmez
# ---------------------------------------------------------------------------

class TestTaneDisCapiCozucununku:

    @pytest.mark.parametrize('tip,anahtar', [
        ('hybrid', 'grain_outer_diameter_mm'), ('solid', 'outer_diameter_mm')])
    def test_cizilen_tane_cozucunun_capinda(self, montaj, tip, anahtar):
        md = montaj[tip]['md']
        cozucu_mm = float(md['grain_design'][anahtar])
        grain = _mesh(montaj[tip]['cad'], 'Fuel Grain')
        assert grain is not None, f'{tip}: tane çizilmeli'
        cizilen_mm = 2.0 * _rmax_mm(grain)
        assert cizilen_mm == pytest.approx(cozucu_mm, rel=1e-6), (
            f'{tip}: çözücü {cozucu_mm:.2f} mm derken STL {cizilen_mm:.2f} mm '
            'çiziyor — uydurma bir liner kalınlığı yakıtı siliyor')

    @pytest.mark.parametrize('tip,anahtar', [
        ('hybrid', 'grain_outer_diameter_mm'), ('solid', 'outer_diameter_mm')])
    def test_hacim_kaybi_yalniz_fasetleme_kadar(self, montaj, tip, anahtar):
        md = montaj[tip]['md']
        gd = md['grain_design']
        od_m = float(gd[anahtar]) / 1000.0
        port_m = float(gd.get('port_diameter_initial_mm')
                       or gd.get('inner_diameter_mm')) / 1000.0
        grain = _mesh(montaj[tip]['cad'], 'Fuel Grain')
        z0, z1 = _z_araligi_mm(grain)
        L = (z1 - z0) / 1000.0
        beklenen = math.pi * ((od_m / 2) ** 2 - (port_m / 2) ** 2) * L
        sapma = (float(grain.volume) - beklenen) / beklenen * 100.0
        assert abs(sapma) < FASET_TOLERANS_YUZDE, (
            f'{tip}: tane hacmi çözücünün geometrisinden %{sapma:.2f} sapıyor')

    def test_dis_cap_yoksa_uydurulmaz(self):
        """Çözücü dış çap yayımlamıyorsa yarıçap TÜRETİLMEZ (fail-closed)."""
        r, kunye = _grain_outer_radius_m({'grain_design': {
            'grain_length_mm': 300.0, 'port_diameter_initial_mm': 40.0}})
        assert r is None
        assert 'no grain outer diameter' in kunye

    def test_dis_cap_yoksa_tane_cizilmez(self, montaj):
        """OD'siz koşuda tane ya çizilmez ya gerekçesi adlandırılır."""
        ham = dict(montaj['solid']['ham'])
        for dugum in ('grain_design',):
            gd = dict(ham.get(dugum) or {})
            gd.pop('outer_diameter_mm', None)
            gd.pop('grain_outer_diameter_mm', None)
            ham[dugum] = gd
        geo = dict(ham.get('motor_geometry') or {})
        if geo.get('grain_design'):
            gg = dict(geo['grain_design'])
            gg.pop('outer_diameter_mm', None)
            gg.pop('grain_outer_diameter_mm', None)
            geo['grain_design'] = gg
            ham['motor_geometry'] = geo
        cad = _sessiz(MotorCADDesigner().generate_3d_motor_assembly, ham)
        assert _mesh(cad, 'Fuel Grain') is None, (
            'dış çapı olmayan koşuda tane çizilmemeli')
        gerekce = (cad['performance_summary']['geometry_summary']
                   ['grain_not_drawn_reason'])
        assert gerekce and 'outer diameter' in gerekce


# ---------------------------------------------------------------------------
# P9B1-07 — çizilen lüle ÇIKIŞI, aynı yanıtın ölçü tablosuyla aynıdır
# ---------------------------------------------------------------------------

class TestCizilenLuleCikisi:

    def test_cizilen_cikis_capi_dimensions_ile_ayni(self, sivi_panel):
        dims = sivi_panel['res']['dimensions']
        iz = _iz(sivi_panel['fig'], 'Nozzle')
        assert iz is not None
        y, z = _eksen(iz, 'y'), _eksen(iz, 'z')
        r_max_mm = max(math.hypot(a, b) for a, b in zip(y, z)) * 1000.0
        assert 2.0 * r_max_mm == pytest.approx(dims['exit_diameter'], rel=1e-6), (
            f'çizilen çıkış {2 * r_max_mm:.2f} mm, ölçü tablosu '
            f'{dims["exit_diameter"]:.2f} mm diyor')

    def test_bogaz_da_ayni_tablodan(self, sivi_panel):
        dims = sivi_panel['res']['dimensions']
        iz = _iz(sivi_panel['fig'], 'Nozzle')
        y, z = _eksen(iz, 'y'), _eksen(iz, 'z')
        r_min_mm = min(math.hypot(a, b) for a, b in zip(y, z)) * 1000.0
        # Profil 50 noktada örneklendiği için boğaz düzlemi tam bir örnek
        # noktasına düşmeyebilir; %2 bandı bu ayrıklaştırmanın payıdır.
        assert 2.0 * r_min_mm == pytest.approx(dims['throat_diameter'],
                                               rel=2e-2)

    def test_cikis_capi_degisince_cizim_de_degisir(self, sivi_panel):
        """Sabit 12 derecelik koni çizilseydi bu test kör kalırdı."""
        govde = dict(sivi_panel['govde'])
        govde['exit_diameter'] = govde['exit_diameter'] * 1.7
        res = _sessiz(DetailedCADGenerator().generate_liquid_motor_cad, govde)
        fig = json.loads(res['plot_json'])
        iz = _iz(fig, 'Nozzle')
        y, z = _eksen(iz, 'y'), _eksen(iz, 'z')
        r_max_mm = max(math.hypot(a, b) for a, b in zip(y, z)) * 1000.0
        assert 2.0 * r_max_mm == pytest.approx(res['dimensions']['exit_diameter'],
                                               rel=1e-6)


# ---------------------------------------------------------------------------
# P9B1-09 — kamara gövdesi [0, L] yerleşimindedir
# ---------------------------------------------------------------------------

class TestGovdeYerlesimi:

    def test_govde_sifirdan_L_ye_uzanir(self, sivi_panel):
        dims = sivi_panel['res']['dimensions']
        xs = _eksen(_iz(sivi_panel['fig'], 'Chamber Body'), 'x')
        assert min(xs) * 1000.0 == pytest.approx(0.0, abs=1e-6)
        assert max(xs) * 1000.0 == pytest.approx(dims['chamber_length'],
                                                 rel=1e-9)

    def test_govde_ile_lule_arasinda_bosluk_yok(self, sivi_panel):
        """Gövdenin arka ucu lülenin başladığı yerdedir."""
        xs = _eksen(_iz(sivi_panel['fig'], 'Chamber Body'), 'x')
        nx = _eksen(_iz(sivi_panel['fig'], 'Nozzle'), 'x')
        bosluk_mm = (min(nx) - max(xs)) * 1000.0
        assert abs(bosluk_mm) < 1e-6, (
            f'gövde ile lüle arasında {bosluk_mm:.1f} mm boşluk var')

    def test_sogutma_ceketi_cizilmez_beyanli(self, sivi_panel):
        """ÖH D37 A1a sahne-sahte-veri (CM-S2) — ÇEVRİLEN İDDİA (eski düğüm
        ``test_govde_sogutma_ceketinin_icinde``: gövde ceketin içinde).
        Ceketin ölçüsü (Ø+0,04 m × 0,8·L) hiçbir yanıt alanında yok; parça
        artık çizilmez ve figür bunu ADIYLA söyler. Gövdenin [0, L]
        yerleşimi yukarıdaki iki testte kilitli kalır."""
        assert _iz(sivi_panel['fig'], 'Cooling Jacket') is None
        notlar = [a.get('text') for a in
                  (sivi_panel['fig'].get('layout') or {}).get('annotations', [])
                  if a.get('name') == 'not_drawn_declaration']
        assert len(notlar) == 1 and 'cooling jacket' in notlar[0]


# ---------------------------------------------------------------------------
# P9B1-10 — hiçbir iz base64 bdata olarak yazılmaz
# ---------------------------------------------------------------------------

class TestPlotlyIkiliBicimYok:

    def test_hicbir_iz_bdata_degil(self, sivi_panel):
        kirli = [t.get('name') for t in sivi_panel['fig']['data']
                 if any(isinstance(t.get(e), dict) and 'bdata' in t.get(e)
                        for e in ('x', 'y', 'z'))]
        assert kirli == [], (
            f'{len(kirli)} iz base64 bdata: {sorted(set(map(str, kirli)))} — '
            'sayfaya gömülü plotly 1.58.5 bu biçimi çözemez, izler çizilmez')

    def test_kanallar_da_bdatasiz(self):
        """Çözücü kanal yayımladığında kanal izleri de düz liste olmalı."""
        ham = _fixture('liquid')
        # ÖH D22 / defter OH-D19-03 (ÇEVRİLEN BEKÇİ): bu fikstür
        # ``nozzle_length`` YAYIMLAMIYOR ve test eskiden üreticinin
        # UYDURMA 150 mm varsayılanına dayanıyordu (ölçüldü: boş gövde
        # Ø100 x 200 mm'lik bir motor çiziyordu). Uydurma varsayılan
        # söküldüğü için lüle boyu artık AÇIKÇA verilir — kardeş
        # ``sivi_panel`` fikstürüyle aynı bağıntı. Testin kendi iddiası
        # (kanal izleri bdata olmamalı) değişmedi.
        govde = dict(ham)
        govde.setdefault('nozzle_length', ham['chamber_length'] * 0.75)
        res = _sessiz(DetailedCADGenerator().generate_liquid_motor_cad,
                      govde)
        fig = json.loads(res['plot_json'])
        kanal = [t for t in fig['data']
                 if 'Cooling Channel' in str(t.get('name'))]
        if not kanal:
            pytest.skip('bu fikstür soğutma kanalı yayımlamıyor')
        for t in kanal:
            for e in ('x', 'y', 'z'):
                assert not isinstance(t.get(e), dict), (
                    'soğutma kanalı izi bdata olarak yazılmış')


# ---------------------------------------------------------------------------
# P9B1-11 — besleme hatları motorun üstündedir, 7 katı uzağında değil
# ---------------------------------------------------------------------------

class TestBeslemeHatlari:
    """ÖH D37 A1a sahne-sahte-veri (CM-S2) — ÇEVRİLEN BEKÇİ.

    Eski iddialar (P9B1-11: hatlar 0,3·L / 0,7·L'de, motor zarfının içinde,
    eksen dizileri eşit uzunlukta) sabit ölçülü bir parçayı kilitliyordu:
    boru yarıçapı 15/12 mm ve eksenel yeri 0,3·L / 0,7·L hiçbir yanıt
    alanında yok. Hatlar artık çizilmez, yardımcısı (``_create_feed_line``,
    P9B1-10/11 kusurlarının yeri) başka okuyucusu olmadığı için silindi;
    iddia "parça çizilmedi + beyan satırı var"dır."""

    @staticmethod
    def _beyan(fig):
        return [a.get('text') for a in
                (fig.get('layout') or {}).get('annotations', [])
                if a.get('name') == 'not_drawn_declaration']

    @pytest.mark.parametrize('ad', ['Oxidizer Feed', 'Fuel Feed'])
    def test_hat_cizilmez(self, sivi_panel, ad):
        assert _iz(sivi_panel['fig'], ad) is None, (
            f'{ad} yayımlanmayan ölçüyle yeniden çiziliyor')

    def test_beyan_satiri_besleme_hatlarini_anar(self, sivi_panel):
        notlar = self._beyan(sivi_panel['fig'])
        assert len(notlar) == 1, notlar
        assert 'feed lines' in notlar[0]
        assert sivi_panel['res']['not_drawn_parts']['declaration'] == notlar[0]


# ---------------------------------------------------------------------------
# P9B1-12 — enjektör yayımlamayan koşuda enjektör plakası ÜRETİLMEZ
# ---------------------------------------------------------------------------

class TestEnjektorKapisi:

    def test_kati_motorda_enjektor_yok(self, montaj):
        cad = montaj['solid']['cad']
        parcalar = [ad for ad, _m in cad['assembly_meshes']]
        assert 'Injector' not in parcalar, (
            f'katı motorun montajında enjektör var: {parcalar}')

    def test_kati_motorun_kutlesinde_enjektor_yok(self, montaj):
        mb = montaj['solid']['cad']['performance_summary']['mass_breakdown']
        assert mb['injector_mass'] == 0.0, (
            f'katı motorun kuru kütlesinin '
            f'%{100 * mb["injector_mass"] / mb["total_dry_mass"]:.1f}i var '
            'olmayan bir enjektör plakasından')

    def test_kati_motorda_gerekce_adlandirilir(self, montaj):
        cizim = montaj['solid']['cad']['technical_drawings']['injector']
        assert cizim['present_in_this_run'] is False
        assert 'injector' in (cizim['not_drawn_reason'] or '').lower()

    def test_hibritte_enjektor_korunur(self, montaj):
        parcalar = [ad for ad, _m in montaj['hybrid']['cad']['assembly_meshes']]
        assert 'Injector' in parcalar, 'hibritte enjektör çizilmeye devam etmeli'

    def test_kanit_kapisi_kati_kosuyu_reddeder(self, montaj):
        var, gerekce = _injector_evidence(montaj['solid']['md'])
        assert var is False and 'injector_not_in_result' in gerekce
        assert _injector_evidence(montaj['hybrid']['md'])[0] is True


# ---------------------------------------------------------------------------
# P9B1-13 — mesh, çizim ve kütle AYNI enjektör plakasını anlatır
# ---------------------------------------------------------------------------

class TestEnjektorPlakasiTekKaynak:

    def test_mesh_cizim_ve_cozucu_ayni_kalinlik(self, montaj):
        md = montaj['hybrid']['md']
        cozucu_mm = float(md['injector_results']['plate_structural']
                          ['plate_thickness_mm'])
        plaka = _mesh(montaj['hybrid']['cad'], 'Injector')
        z0, z1 = _z_araligi_mm(plaka)
        cizim = montaj['hybrid']['cad']['technical_drawings']['injector']
        assert (z1 - z0) == pytest.approx(cozucu_mm, rel=1e-6), (
            f'mesh {z1 - z0:.2f} mm, çözücü {cozucu_mm:.2f} mm')
        assert cizim['plate_thickness'] == pytest.approx(cozucu_mm, rel=1e-9)

    def test_mesh_ve_cizim_ayni_cap(self, montaj):
        plaka = _mesh(montaj['hybrid']['cad'], 'Injector')
        cizim = montaj['hybrid']['cad']['technical_drawings']['injector']
        assert 2.0 * _rmax_mm(plaka) == pytest.approx(cizim['plate_diameter'],
                                                     rel=1e-3)

    def test_kutle_cozucunun_otoritatif_plaka_kutlesi(self, montaj):
        md = montaj['hybrid']['md']
        beklenen = float(md['injector_results']['plate_structural']
                         ['plate_mass_kg'])
        mb = montaj['hybrid']['cad']['performance_summary']['mass_breakdown']
        assert mb['injector_mass'] == pytest.approx(beklenen, rel=1e-9), (
            'plaka kütlesi enjektör çözücüsünün kendi sayısı olmalı '
            '(plaka malzemesi kamaranınkinden farklı)')

    def test_plaka_kalinligi_yoksa_uydurulmaz(self):
        plaka = _injector_plate_design({'injector_design': {'n_holes': 12},
                                        'chamber_diameter': 0.1})
        assert plaka['thickness_m'] is None
        assert 'not_available' in plaka['source']

    def test_kalinligi_olmayan_kosuda_plaka_cizilmez(self, montaj):
        """Sıvı fikstürü plaka kalınlığı yayımlamıyor -> plaka çizilmez."""
        cad = montaj['liquid']['cad']
        assert _mesh(cad, 'Injector') is None
        cizim = cad['technical_drawings']['injector']
        assert cizim['plate_thickness'] == NOT_AVAILABLE_SPEC
        assert 'thickness' in (cizim['not_drawn_reason'] or '')


# ---------------------------------------------------------------------------
# P9B1-14 — kamara kütlesi ÇÖZÜCÜNÜN adlandırdığı malzemeden
# ---------------------------------------------------------------------------

class TestKamaraMalzemesi:

    def test_sivi_motorun_malzemesi_kaybolmuyor(self, montaj):
        md = montaj['liquid']['md']
        beklenen_key = md['structural_analysis']['chamber_structure'][
            'material_key']
        key, ad, rho, kunye = _chamber_material_resolved(md)
        assert key == beklenen_key
        assert rho == pytest.approx(8220.0)
        assert beklenen_key in kunye

    def test_kati_motorun_malzemesi_kaybolmuyor(self, montaj):
        md = montaj['solid']['md']
        key, ad, rho, _kunye = _chamber_material_resolved(md)
        assert key == md['structural_analysis']['case_analysis']['case_material']
        assert rho is not None and ad is not None

    def test_cad_ozeti_not_available_demiyor(self, montaj):
        for tip in ('solid', 'liquid'):
            # ÖH D29 (P15B4-12): malzeme adı ve yoğunluğu kütle dökümünden
            # ÇIKTI, ``material_summary`` sözlüğüne taşındı.
            ms = montaj[tip]['cad']['performance_summary']['material_summary']
            assert ms['chamber_material'] != NOT_AVAILABLE_SPEC, (
                f'{tip}: çözücü malzemeyi adlandırıyor, CAD "yok" diyor')

    def test_kutle_secilen_yogunlukla_hesaplanir(self, montaj):
        ozet = montaj['liquid']['cad']['performance_summary']
        # ÖH D29 (P15B4-12): yoğunluk ``material_summary``de, kütle
        # ``mass_breakdown``ta — iki sözlük, iki boyut, aynı koşum.
        assert ozet['material_summary']['chamber_mass_density_kg_m3'] == (
            pytest.approx(8220.0))
        assert ozet['mass_breakdown']['chamber_mass'] == pytest.approx(
            2.5772876405665492, rel=1e-6)

    def test_yedek_yogunluk_sessiz_degil(self):
        """Malzeme çözülemezse künye bunu ADIYLA söyler."""
        _k, _a, rho, kunye = _chamber_material_resolved(
            {'structural_analysis': {'chamber_structure': {}}})
        assert rho is None
        assert 'NOT RESOLVED' in kunye


# ---------------------------------------------------------------------------
# P9B1-15 — bell_80 bir BELL lülesidir, "conical 30 derece" değil
# ---------------------------------------------------------------------------

class TestBellLuleEtiketi:

    @pytest.mark.parametrize('tip', ['bell', 'bell_80', 'BELL_60', 'rao'])
    def test_aile_normalizasyonu(self, tip):
        assert _nozzle_family(tip) == 'bell'

    def test_conical_bell_olmaz(self):
        assert _nozzle_family('conical') == 'conical'

    def test_cizim_bell_diyor(self, montaj):
        cizim = montaj['liquid']['cad']['technical_drawings']['nozzle']
        assert cizim['nozzle_type'] == 'bell_80'
        assert cizim['divergence_angle_meaning'].startswith('bell:'), (
            f"50 genişleme oranlı çan lülesine "
            f"{cizim['divergence_angle_meaning']!r} yazılıyor — imalatçı "
            'sabit 30 derece yarı açılı koni tornalar')

    def test_cikis_acisi_sonuctan_okunur(self, montaj):
        md = montaj['liquid']['md']
        beklenen = float(md['nozzle_angles']['exit_angle_deg'])
        cizim = montaj['liquid']['cad']['technical_drawings']['nozzle']
        assert cizim['divergent_exit_angle'] == pytest.approx(beklenen), (
            'gerçek çıkış açısı sonuçta hazır dururken çizim '
            '"NOT AVAILABLE" diyor')

    def test_bell_ailesi_bogaz_acisini_kullanir(self):
        _c, div, tip = _nozzle_half_angles({
            'nozzle_angles': {'nozzle_type': 'bell_80',
                              'divergent_half_angle_deg': 30.0},
            'nozzle_contour': {'divergent': {'throat_angle': 33.0}}})
        assert tip == 'bell_80' and div == pytest.approx(33.0)


# ---------------------------------------------------------------------------
# P9B1-16 — boş sözlük UYDURMA motor üretmez (kapı KİLİTLİ kalsın)
# ---------------------------------------------------------------------------

class TestBosSozlukMotorUretmez:

    @pytest.fixture(scope='class')
    def bos(self):
        return _sessiz(MotorCADDesigner().generate_3d_motor_assembly, {})

    def test_hata_adiyla_doner(self, bos):
        """ÇEVRİLDİ — ÖH D17 / OH-D16-03, ÖK-05 (daraltma DEĞİL, genişletme).

        Satır ``'chamber_length' in bos['error']`` idi ve o ad, ret
        gerekçesini veren tek kapının kamara BOYU kapısı olduğu dönemden
        kalmaydı. D17'de üç uydurma ÇAP varsayılanı (0,1 / 0,02 / 0,04 m)
        kaldırıldı ve çap kapısı boy kapısından ÖNCE koşuyor (boy, L*
        türetmesinde çapları kullandığı için sırası zorunlu). Boş sözlük
        artık ``chamber_diameter_not_available`` ile reddediliyor — aynı
        hüküm, DAHA ERKEN ve daha doğru bir alan adıyla.

        Bekçinin niyeti korunur ve GENİŞLETİLİR: ret, STL sözleşmesinin
        alanlarından birini ADIYLA söylemek ZORUNDA; ayrıca ``_not_available``
        eki ile "hesaplanmadı" dediği doğrulanır. Böylece bekçi tek bir
        alan adına değil SÖZLEŞMEYE bağlanır.
        """
        assert bos.get('error'), 'boş sözlük başarı gibi dönemez'
        from hrma.app import _STL_REQUIRED_FIELDS
        sozlesme = set()
        for adlar in _STL_REQUIRED_FIELDS.values():
            sozlesme.update(adlar)
        sozlesme.update(('throat_diameter', 'exit_diameter'))
        adlanan = [ad for ad in sozlesme if ad in bos['error']]
        assert adlanan, (
            f'ret hiçbir geometri alanını adıyla söylemiyor: {bos["error"]!r}')
        assert '_not_available' in bos['error']

    def test_hicbir_kati_uretilmez(self, bos):
        assert bos['assembly_meshes'] == []

    def test_uydurma_olcu_basilmaz(self, bos):
        assert not bos.get('technical_drawings')
        assert bos.get('performance_summary') == {}


# ---------------------------------------------------------------------------
# P9B1-17 — ÇİZİLEN ön kapak çizim sözlüğünde de görünür
# ---------------------------------------------------------------------------

class TestOnKapakCizimde:

    @pytest.mark.parametrize('tip', ['hybrid', 'solid', 'liquid'])
    def test_kapak_alani_var(self, montaj, tip):
        cizim = montaj[tip]['cad']['technical_drawings']['chamber']
        assert 'front_cap_thickness' in cizim
        assert cizim['front_cap_thickness_source']

    def test_kapak_yapisal_analizden_geldiginde_soylenir(self, montaj):
        md = montaj['hybrid']['md']
        flat = float(md['structural_analysis']['end_cap_analysis']
                     ['flat_head_thickness'])
        cizim = montaj['hybrid']['cad']['technical_drawings']['chamber']
        assert cizim['front_cap_from_structural_analysis'] is True
        assert cizim['front_cap_thickness'] == pytest.approx(flat, rel=1e-9)

    def test_analizin_degerlendirdigi_kalinlik_da_yazar(self, montaj):
        md = montaj['hybrid']['md']
        used = float(md['structural_analysis']['end_cap_analysis']
                     ['head_thickness_used_mm'])
        cizim = montaj['hybrid']['cad']['technical_drawings']['chamber']
        assert cizim['front_cap_thickness_evaluated_by_analysis'] == \
            pytest.approx(used, rel=1e-9)
        assert cizim['front_cap_recommended_type'] in ('flat', 'dished')

    def test_cizilen_kapak_ile_alan_ayni_sayidir(self, montaj):
        """Sözlükteki kapak, KATIDA gerçekten çizilen kapaktır."""
        cizim = montaj['hybrid']['cad']['technical_drawings']['chamber']
        kamara = _mesh(montaj['hybrid']['cad'], 'Chamber')
        z0, _z1 = _z_araligi_mm(kamara)
        assert -z0 == pytest.approx(cizim['front_cap_thickness'], rel=1e-6), (
            'çizim sözlüğündeki kapak kalınlığı katıdaki kapakla aynı değil')
