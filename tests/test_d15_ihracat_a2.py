"""ÖH Dalga-15 · kulvar **ihracat** · aşama 2 — onarım bekçileri.

Her sınıf BİR defter kalemini kilitler. Sayılar
``docs/scofield/raw/OH/D15/ihracat/a2/{once,sonra}.json`` ölçümünden gelir;
girdiler P09 partisinin ürettiği GERÇEK ``/calculate*`` yanıtlarıdır
(``docs/scofield/raw/P09/cikti/motor_{hybrid,solid,liquid}.json``).

ÖK-05: her bekçi TERS-MUTASYONLA sınanmıştır — onarım geçici olarak geri
alınır, bekçi KIRMIZI olur, bayt geri yazılır (kanıt: ``mutasyon.json``).
"""
import contextlib
import importlib.util
import io
import json
import math
import os
import re
import sys

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

P09 = os.path.join(KOK, 'docs', 'scofield', 'raw', 'P09', 'cikti')

pytestmark = pytest.mark.skipif(
    not os.path.isdir(kanit_gerekli(P09)),
    reason=f'P09 fikstür dizini yok: {P09} (gerekçe DOĞRULANDI: os.path.isdir)')


def _fixture(ad):
    with open(kanit_gerekli(os.path.join(P09, f'motor_{ad}.json')), encoding='utf-8') as fh:
        return json.load(fh)


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def solid():
    return _fixture('solid')


@pytest.fixture(scope='module')
def liquid():
    return _fixture('liquid')


@pytest.fixture(scope='module')
def hybrid():
    return _fixture('hybrid')


def _step_metni(path):
    """STEP dosyasını okur ve SATIR KAYDIRMASINI temizler.

    OpenCascade uzun dizgileri (parça adları) sabit sütunda kırar; ham metinde
    aranan cümle iki satıra bölünmüş olabilir. Bekçiler dizgiyi ararken bu
    biçimlendirmeye takılmamalı.
    """
    ham = open(path, encoding='utf-8', errors='replace').read()
    return re.sub(r'\s+', ' ', ham)


def _bbox(path):
    from build123d import import_step
    bb = _sessiz(import_step, path).bounding_box()
    return bb


_b123d = pytest.mark.skipif(
    importlib.util.find_spec('build123d') is None,
    reason='build123d kurulu değil (gerekçe DOĞRULANDI: find_spec)')


# ---------------------------------------------------------------------------
# P9B2-03 — çizilen grain Ø96 ⟷ çözücü Ø100
# ---------------------------------------------------------------------------
@_b123d
class TestP9B2_03GrainDisCapi:
    """Grain dış çapı ÇÖZÜCÜDEN gelir; üreteç 'liner' kuralından DEĞİL.

    ÖLÇÜM (once.json): çözücü ``grain_design.outer_diameter_mm = 100,000``
    derken ``fuel_grain.step`` sınır kutusu **Ø96,000 mm** — itici hacmi
    -%8,62, web -%5,71 ve hiçbir çıktı bu kırpmayı beyan etmiyordu.
    (sonra.json: Ø100,000 mm, çözücüyle BİREBİR.)
    """

    def test_cizilen_dis_cap_cozucunun_capidir(self, solid, tmp_path):
        from hrma.export.step_export import generate_step_assembly
        beklenen = solid['grain_design']['outer_diameter_mm']
        files = _sessiz(generate_step_assembly, solid,
                        out_dir=str(tmp_path), motor_type='solid')
        bb = _bbox(files['fuel_grain'])
        cizilen = max(bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
        assert cizilen == pytest.approx(beklenen, abs=0.05), (
            f'çizilen grain Ø{cizilen:.3f} mm, çözücü Ø{beklenen:.3f} mm — '
            'üreteç liner kuralı geri gelmiş olabilir')

    def test_dis_cap_parca_adinda_beyan_edilir(self, solid, tmp_path):
        from hrma.export.step_export import generate_step_assembly
        files = _sessiz(generate_step_assembly, solid,
                        out_dir=str(tmp_path), motor_type='solid')
        metin = _step_metni(files['fuel_grain'])
        assert 'outer diameter' in metin, (
            'grain parça adı dış çapın nereden geldiğini söylemiyor')
        assert 'grain_design' in metin, (
            'dış çapın KAYNAK alanı parça adında yok')

    def test_cozucu_cap_yayimlamazsa_grain_cizilmez(self, solid, tmp_path):
        """FAIL-CLOSED: çap yoksa uydurma liner ile çizilmez."""
        from hrma.export.step_export import generate_step_assembly
        md = json.loads(json.dumps(solid))
        for blok in (md.get('grain_design') or {},
                     (md.get('motor_geometry') or {}).get('grain_design') or {}):
            blok.pop('outer_diameter_mm', None)
            blok.pop('grain_outer_diameter_mm', None)
        files = _sessiz(generate_step_assembly, md, out_dir=str(tmp_path),
                        motor_type='solid')
        assert 'fuel_grain' not in files, (
            'dış çap yokken grain yine çizilmiş — üreteç yedeği geri gelmiş')
        metin = _step_metni(files['assembly'])
        assert 'fuel grain NOT modelled' in metin, (
            'çizilmeyen grain montaj künyesinde beyan edilmiyor')


# ---------------------------------------------------------------------------
# P9B2-12 — STEP 368 mm ⟷ DXF 900 mm (sessiz kırpma)
# ---------------------------------------------------------------------------
class TestP9B2_12SessizKirpma:
    """Zarfı aşan grain SESSİZCE kırpılmaz; reddedilir.

    ÖLÇÜM (once.json, ``gate2_grain900``): ``grain_length_mm = 900``, kamara
    400 mm -> STEP ``fuel_grain`` **368,000 mm**, aynı isteğin DXF'i
    ``grain 900.0 mm`` — **2,446 kat** fark, hiçbir çıktı kırpmayı beyan
    etmiyor.
    """

    @staticmethod
    def _uzun_grain(solid):
        md = json.loads(json.dumps(solid))
        md['motor_name'] = 'GATE2'
        for blok in (md.setdefault('grain_design', {}),
                     md.setdefault('motor_geometry', {})
                       .setdefault('grain_design', {})):
            blok['grain_length_mm'] = 900.0
        md['chamber_length'] = 400.0
        md['grain_length'] = 900.0
        return md

    @_b123d
    def test_kamaradan_uzun_grain_step_uretmez(self, solid, tmp_path):
        from hrma.export.step_export import generate_step_assembly
        md = self._uzun_grain(solid)
        with pytest.raises(ValueError, match='does not fit inside the case'):
            _sessiz(generate_step_assembly, md, out_dir=str(tmp_path),
                    motor_type='solid')

    def test_rota_kapisi_422_ve_alan_adi_verir(self, solid):
        from hrma.app import _export_geometry_problem
        problem = _export_geometry_problem(self._uzun_grain(solid))
        assert problem is not None, 'kamaradan uzun grain kapıdan geçiyor'
        assert problem['error'] == 'inconsistent_export_geometry'
        nedenler = {f['reason'] for f in problem['inconsistent_fields']}
        assert 'grain_longer_than_chamber' in nedenler

    @pytest.mark.parametrize('uc', ('/api/export-dxf', '/api/export-step',
                                    '/api/export-drawings-pdf'))
    def test_uclar_gercek_govdede_de_reddeder(self, solid, uc):
        """Kapı, ÜRETİCİNİN okuduğu grain boyuna bakmalıdır.

        Ölçüldü (31 Ağustos 2026): kapı yalnız üst düzey ``grain_length``e
        bakarken GERÇEK katı motor gövdesi (grain boyu
        ``motor_geometry.grain_design.grain_length_mm``de) kapıdan geçiyor ve
        üç uç da HTTP 200 veriyordu — oysa ``resolve_grain_m`` (STEP ve DXF
        üreticilerinin okuduğu yer) 900 mm diyordu.
        """
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.app import app
        app.config['TESTING'] = True
        cevap = _sessiz(app.test_client().post, uc,
                        json={'motor_data': self._uzun_grain(solid)})
        assert cevap.status_code == 422, (
            f'{uc}: kamaradan 2,25 kat uzun grain için imalat dosyası verdi')
        assert (cevap.get_json() or {}).get('error') == (
            'inconsistent_export_geometry')

    @_b123d
    def test_sigan_grain_KIRPILMADAN_cizilir(self, hybrid, tmp_path):
        """Hibrit fikstürü kamaranın %96,5'ini dolduruyor: kırpılmamalı.

        Eski ``0,92 x L`` kuralı bu SAĞLIKLI vakayı da ısırıyordu (3387,38 ->
        3228,65 mm, -%4,7) ve bunu hiçbir yerde söylemiyordu.
        """
        from hrma.export.motor_geometry import (normalise_export_geometry,
                                                resolve_grain_m)
        from hrma.export.step_export import generate_step_assembly
        md, _ = normalise_export_geometry(hybrid)
        grain, _r = resolve_grain_m(md)
        istenen_mm = grain['length'] * 1000.0
        oda_mm = float(md['chamber_length']) * 1000.0
        assert istenen_mm / oda_mm > 0.92, (
            'fikstür artık 0,92 zarfını aşmıyor — bekçi anlamsızlaştı')
        files = _sessiz(generate_step_assembly, hybrid, out_dir=str(tmp_path),
                        motor_type='hybrid')
        bb = _bbox(files['fuel_grain'])
        assert (bb.max.X - bb.min.X) == pytest.approx(istenen_mm, rel=1e-4), (
            'sığan grain kırpılmış — 0,92 kelepçesi geri gelmiş olabilir')


# ---------------------------------------------------------------------------
# P9B2-11 — imkânsız geometri 200 ile imalat paketi veriyordu
# ---------------------------------------------------------------------------
class TestP9B2_11TutarlilikKapisi:
    """Ölçüler ARASI çelişki fail-closed reddedilir (422 + alan adı).

    ÖLÇÜM (once.json): ``chamber_diameter = 100 mm`` + ``throat_diameter =
    120 mm`` gövdesi ``/api/export-dxf``ten **200** + 42 926 B,
    ``/api/export-drawings-pdf``ten **200** + 122 157 B alıyordu; kapının
    hükmü ``None`` idi.
    """

    IMKANSIZ = {'motor_name': 'GATE', 'chamber_diameter': 0.100,
                'throat_diameter': 0.120, 'exit_diameter': 0.200,
                'chamber_length': 0.400, 'nozzle_length': 0.225,
                'wall_thickness': 0.0024, 'expansion_ratio': 2.78}
    TERS_LULE = {'motor_name': 'GATE3', 'chamber_diameter': 0.100,
                 'throat_diameter': 0.050, 'exit_diameter': 0.030,
                 'chamber_length': 0.400, 'nozzle_length': 0.225,
                 'wall_thickness': 0.0024, 'expansion_ratio': 0.36}
    TUTARLI_REFERANS = {'motor_name': 'OK', 'chamber_diameter': 0.100,
                'throat_diameter': 0.0366, 'exit_diameter': 0.0891,
                'chamber_length': 0.400, 'nozzle_length': 0.225,
                'wall_thickness': 0.0024, 'expansion_ratio': 5.93}

    def test_bogaz_odadan_buyukse_reddedilir(self):
        from hrma.app import _export_geometry_problem
        problem = _export_geometry_problem(self.IMKANSIZ)
        assert problem is not None, 'boğaz > oda kapıdan geçiyor'
        assert problem['error'] == 'inconsistent_export_geometry'
        alan = problem['inconsistent_fields'][0]
        assert alan['reason'] == 'throat_not_smaller_than_chamber'
        assert alan['field'] == 'throat_diameter'
        assert alan['compared_with'] == 'chamber_diameter'

    def test_cikis_bogazdan_kucukse_reddedilir(self):
        from hrma.app import _export_geometry_problem
        problem = _export_geometry_problem(self.TERS_LULE)
        assert problem is not None, 'ters lüle kapıdan geçiyor'
        nedenler = {f['reason'] for f in problem['inconsistent_fields']}
        assert 'exit_smaller_than_throat' in nedenler

    def test_saglikli_geometri_gecer(self):
        from hrma.app import _export_geometry_problem
        assert _export_geometry_problem(self.TUTARLI_REFERANS) is None

    @pytest.mark.parametrize('ad', ('solid', 'liquid', 'hybrid'))
    def test_uc_gercek_motor_da_gecer(self, ad):
        """ÖK-22: sağlıklı envanter GEVŞEMEZ ve SIKILAŞMAZ."""
        from hrma.app import _export_geometry_problem
        assert _export_geometry_problem(_fixture(ad)) is None, (
            f'{ad} fikstürü yeni kapıya takılıyor — yanlış ret')

    @pytest.mark.parametrize('uc', ('/api/export-dxf', '/api/export-step',
                                    '/api/export-stl',
                                    '/api/export-drawings-pdf'))
    def test_imalat_uclari_imkansiz_motoru_indirtmez(self, uc):
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.app import app
        app.config['TESTING'] = True
        cevap = _sessiz(app.test_client().post, uc,
                        json={'motor_data': dict(self.IMKANSIZ)})
        assert cevap.status_code != 200, (
            f'{uc} boğazı odasından büyük motor için imalat dosyası verdi')

    def test_karisik_birimli_govde_yanlis_reddedilmez(self):
        """Kapı METRE cinsinden kıyaslar: mm/m karışık gövde ret ALMAZ.

        Ölçüldü: P09 sıvı fikstüründe ``chamber_diameter = 61,53`` **mm** ile
        ``throat_diameter = 0,0308`` **m** aynı sözlükte duruyor; ham oran
        kıyası bu sağlıklı motoru reddederdi.
        """
        from hrma.app import _export_geometry_problem
        karisik = {'chamber_diameter': 61.53496638537138,
                   'throat_diameter': 0.030767483192685692,
                   'exit_diameter': 0.21755896005591183,
                   'chamber_length': 300.0}
        assert _export_geometry_problem(karisik) is None


# ---------------------------------------------------------------------------
# P9B2-06 — HRMA'nın STEP'ini HRMA'nın içe aktarıcısı yanlış okuyordu
# ---------------------------------------------------------------------------
@_b123d
class TestP9B2_06RoundTrip:
    """Montaj STEP'i geri okununca ODA çözümlenir, en büyük hacim DEĞİL.

    ÖLÇÜM (once.json): ``chamber_diameter_mm = 35,0`` (gerçek 100,0, -%65,0),
    ``chamber_length_mm = 300,0`` (gerçek 400,0), ``wall_thickness_mm = 30,5``
    (gerçek 2,4, +%1171) — ÜÇÜ DE "high" güven rozetiyle. Kök neden: seçim
    ``argmax(volumes)`` ile yapılıyor, dosyadaki PARÇA ADLARI okunuyor ama
    seçimde kullanılmıyordu (grain 1 882 835 mm3 > kamara 377 840 mm3).
    """

    @pytest.fixture(scope='class')
    def rapor(self, tmp_path_factory):
        from hrma.export.step_export import generate_step_assembly
        from hrma.importers.step_import import analyze_step
        out = tmp_path_factory.mktemp('d15a2_rt')
        files = _sessiz(generate_step_assembly, _fixture('solid'),
                        out_dir=str(out), motor_type='solid')
        return _sessiz(analyze_step, files['assembly'])

    def test_oda_katisi_secilir(self, rapor):
        secim = rapor['solid_selection']
        assert secim['identified_as_chamber'] is True
        assert secim['matched_name'].startswith('chamber')

    @pytest.mark.parametrize('alan,beklenen', [
        ('chamber_diameter_mm', 100.0),
        ('chamber_length_mm', 400.0),
        ('wall_thickness_mm', 2.4),
    ])
    def test_oneriler_gercek_degerlerdir(self, rapor, alan, beklenen):
        oneri = rapor['suggestions'][alan]
        assert oneri['value'] == pytest.approx(beklenen, rel=1e-3), (
            f'{alan}: {oneri["value"]} onerildi, gerçek {beklenen} — '
            'seçim yine hacme düşmüş olabilir')

    def test_tek_parca_dosya_ile_montaj_ayni_sonucu_verir(self,
                                                          tmp_path_factory):
        """Kusur sayısal sadakatte değil KATI SEÇİMİNDEYDİ: ikisi eşit olmalı."""
        from hrma.export.step_export import generate_step_assembly
        from hrma.importers.step_import import analyze_step
        out = tmp_path_factory.mktemp('d15a2_rt2')
        files = _sessiz(generate_step_assembly, _fixture('solid'),
                        out_dir=str(out), motor_type='solid')
        montaj = _sessiz(analyze_step, files['assembly'])['suggestions']
        tek = _sessiz(analyze_step, files['chamber'])['suggestions']
        for alan in ('chamber_diameter_mm', 'chamber_length_mm',
                     'wall_thickness_mm'):
            assert montaj[alan]['value'] == pytest.approx(
                tek[alan]['value'], rel=1e-6), (
                f'{alan}: montaj {montaj[alan]["value"]} ⟷ tek parça '
                f'{tek[alan]["value"]}')

    def test_adsiz_montajda_guven_dusurulur(self, tmp_path):
        """Oda tanınmıyorsa 'high' rozeti verilmez (fail-closed yarısı)."""
        from hrma.importers.step_import import (_choose_solid,
                                                _demote_chamber_confidence)
        adsiz = [{'index': 0, 'name': 'COMPOUND', 'volume_mm3': 10.0},
                 {'index': 1, 'name': 'COMPOUND', 'volume_mm3': 99.0}]
        index, secim = _choose_solid(adsiz)
        assert index == 1 and secim['identified_as_chamber'] is False
        oneriler = {'chamber_diameter_mm': {'value': 1.0,
                                            'confidence': 'high'},
                    'wall_thickness_mm': {'value': 2.0, 'confidence': 'high'},
                    'throat_diameter_mm': {'value': 3.0,
                                           'confidence': 'high'}}
        uyarilar = []
        _demote_chamber_confidence(oneriler, uyarilar)
        assert oneriler['chamber_diameter_mm']['confidence'] == 'low'
        assert oneriler['wall_thickness_mm']['confidence'] == 'low'
        # Boğaz ölçüsü katı seçiminden BAĞIMSIZ olarak sadıktır — düşürülmez.
        assert oneriler['throat_diameter_mm']['confidence'] == 'high'
        assert uyarilar, 'güven düşürme gerekçesi yayımlanmıyor'

    def test_grain_ve_lule_oda_sanilmaz(self):
        from hrma.importers.step_import import _chamber_name_rank
        assert _chamber_name_rank('fuel_grain (axial position ...)') is None
        assert _chamber_name_rank('nozzle (wall 3.66 mm ...)') is None
        assert _chamber_name_rank('injector (oxidizer circuit ...)') is None
        assert _chamber_name_rank('chamber (wall 2.40 mm ...)') == 0


# ---------------------------------------------------------------------------
# P9B2-15 / P9B2-16 — tank STEP dolu kütük, STL açık boru
# ---------------------------------------------------------------------------
class TestP9B2_15_16Tank:
    """Tank bir KABUKTUR ve STL'i STEP'le aynı tankı anlatır, su geçirmezdir.

    ÖLÇÜM (once.json, Ø743,7556 / gövde 1859,3891 mm, Al 2024-T3):
    STEP hacmi 1 023 252 929 mm3 -> **2844,64 kg**, yayımlanan **47,62 kg**
    (**59,74 kat**). STL boyu 1859,39 mm ⟷ STEP boyu 2603,14 mm (%40) ve
    ``V - E + F = 30`` (kapalı katı için 2 olmalı).
    """

    OX = {'diameter': 743.7556, 'length': 1859.3891, 'wall_thickness': 3.0}
    RHO = 2780.0

    @_b123d
    def test_step_kabuktur_dolu_kutuk_degil(self, tmp_path):
        """ÖH V3 CAD A2 · H4 — ÇEVRİLDİ (12 Eki 2026, ana model izni, dört
        koşul; rapor ``docs/scofield/raw/OH/V3/cad-duzeltme/rapor.md``
        "Bölüm T"). Beklenen hacim eskiden YARIKÜRE başlıklı, D'yi dış çap
        sayan kabuktan kuruluyordu. Karar §28-21 (b): CAD, boyutlandırmanın
        düz uçlu modelini çizer — boşluk Ø D × L (boyutlandırma
        ``V = π·D²·L/4``), cidar t gövdeye ve iki düz kapağa DIŞARIDAN
        eklenir. Kâhin bu tanım ve girdinin D, L, t'sidir:
        V_kabuk = π·(r + t)²·(L + 2t) − π·r²·L, r = D/2.
        """
        from hrma.export.step_export import generate_tank_step
        files = _sessiz(generate_tank_step,
                        {'oxidizer_tank': dict(self.OX),
                         'fuel_tank': dict(self.OX)}, out_dir=str(tmp_path))
        from build123d import import_step
        hacim = _sessiz(import_step, files['oxidizer_tank']).volume
        D, L, t = self.OX['diameter'], self.OX['length'], self.OX[
            'wall_thickness']
        r_i = D / 2
        r_o = r_i + t
        beklenen = (math.pi * r_o ** 2 * (L + 2 * t)
                    - math.pi * r_i ** 2 * L)
        assert hacim == pytest.approx(beklenen, rel=2e-3), (
            f'çizilen hacim {hacim:.0f} mm3, kabuk hacmi {beklenen:.0f} mm3 '
            '— oyma (boolean cut) düşmüş olabilir')
        kutle = hacim * 1e-9 * self.RHO
        assert kutle < 100.0, (
            f'tank katısı {kutle:.1f} kg — içi dolu kütük geri gelmiş')

    @_b123d
    def test_cidarsiz_girdi_reddedilir(self, tmp_path):
        from hrma.export.step_export import generate_tank_step
        with pytest.raises(ValueError, match='SOLID BILLET'):
            _sessiz(generate_tank_step,
                    {'oxidizer_tank': {'diameter': 743.7556,
                                       'length': 1859.3891},
                     'fuel_tank': {'diameter': 500.0, 'length': 1200.0}},
                    out_dir=str(tmp_path))

    def _stl_mesleri(self, tmp_path):
        """Paketin GERÇEKTEN yazdığı tank STL'leri, trimesh ile geri okunur.

        ÖH V3 CAD A2 · H9: eskiden sınanan ``_generate_tank_mesh`` (yarıküreli,
        içi DOLU, +Z) kaldırıldı; STL artık ``_generate_simple_stl``in
        yazdığı dosyadır (STEP'in döndürdüğü profil, +X).
        """
        import trimesh

        from hrma.export.cad_export import TankCADGenerator
        tank = {'dimensions': dict(self.OX)}
        yollar = _sessiz(TankCADGenerator()._generate_simple_stl,
                         {'oxidizer_tank': tank, 'fuel_tank': tank},
                         str(tmp_path))
        assert len(yollar) == 2, yollar
        return [(os.path.basename(y), trimesh.load(y, force='mesh'))
                for y in yollar]

    def test_stl_su_gecirmezdir(self, tmp_path):
        """ÖH V3 CAD A2 · H9 — ÇEVRİLDİ (12 Eki 2026, ana model izni, dört
        koşul; rapor ``docs/scofield/raw/OH/V3/cad-duzeltme/rapor.md``
        "Bölüm T"). Eski düğüm kaldırılan ``_generate_tank_mesh``in içi
        DOLU yarıküreli zarfını (tek kapalı yüzey, V − E + F = 2) sınıyordu.
        Karar §28-21 (b) + H9: tank STL'si dolu katı DEĞİL kabuktur. Kâhin
        topolojidir (Euler–Poincaré): içinde tek boşluk olan katının sınırı
        iki kapalı, cinsi 0 yüzeydir (dış yüzey + boşluk yüzeyi), her biri
        χ = 2 → V − E + F = 4. Niyet aynen: su geçirmez, her kenar tam iki
        üçgende.
        """
        for ad, mesh in self._stl_mesleri(tmp_path):
            kenarlar = {}
            for yuz in mesh.faces.tolist():
                for a, b in ((0, 1), (1, 2), (2, 0)):
                    anahtar = tuple(sorted((yuz[a], yuz[b])))
                    kenarlar[anahtar] = kenarlar.get(anahtar, 0) + 1
            euler = len(mesh.vertices) - len(kenarlar) + len(mesh.faces)
            assert euler == 4, (
                f'{ad}: V - E + F = {euler} (dış yüzey + boşluk yüzeyi için 4 '
                'olmalı; 2 = içi dolu zarf geri gelmiş)')
            assert set(kenarlar.values()) == {2}, (
                f'{ad}: manifold değil — bir kenar 2 üçgen dışında bir sayıda '
                'kullanılmış')
            assert mesh.is_watertight and mesh.is_volume, (
                f'{ad}: su geçirmez kapalı hacim değil, dilimleyiciye '
                'verilemez')
            assert len(mesh.split(only_watertight=False)) == 2, (
                f'{ad}: dış yüzey ve boşluk yüzeyi iki ayrı kapalı kabuk '
                'olmalı')

    def test_stl_ve_step_ayni_boyu_anlatir(self, tmp_path):
        """ÖH V3 CAD A2 · H4/H9 — ÇEVRİLDİ (12 Eki 2026, ana model izni,
        dört koşul; rapor ``docs/scofield/raw/OH/V3/cad-duzeltme/rapor.md``
        "Bölüm T"). Eski düğüm kaldırılan mesh'in Z boyunu yarıküreli STEP
        zarfıyla (L + D) kıyaslıyordu. Karar §28-21 (b): iki dosya da
        boyutlandırmanın düz uçlu modelini çizer; STEP zarfı L + 2t (iki düz
        kapak dışarıda) ve eksen +X (paket sözleşmesi). Kâhin bu tanım ve
        girdinin L, t'sidir.
        """
        step_boy = self.OX['length'] + 2 * self.OX['wall_thickness']
        for ad, mesh in self._stl_mesleri(tmp_path):
            stl_boy = float(mesh.extents[0])
            assert stl_boy == pytest.approx(step_boy, rel=1e-9), (
                f'{ad}: STL X boyu {stl_boy:.4f} mm ⟷ STEP {step_boy:.4f} mm '
                '— iki dosya aynı tankı farklı boyda ya da farklı eksende '
                'anlatıyor')

    def test_adaptor_cidari_gecirir(self):
        """``cad_export`` -> ``generate_tank_step`` çağrısı cidarı TAŞIR."""
        from pathlib import Path

        import hrma.export.cad_export as cad_export
        src = Path(cad_export.__file__).read_text(encoding='utf-8')
        bas = src.find('generate_tank_step({')
        assert bas != -1
        govde = src[bas:bas + 1400]
        assert govde.count("'wall_thickness'") >= 2, (
            'adaptör iki tankın da cidarını geçirmiyor — STEP yine içi dolu '
            'çizilir')


# ---------------------------------------------------------------------------
# P9B2-09 — bell_80 künyesi yalnız "div 30.0 deg"
# ---------------------------------------------------------------------------
class TestP9B2_09CanLuleCikisAcisi:
    """Çan lülede ÇIKIŞ açısı imalat çiziminde ADIYLA basılır.

    ÖLÇÜM (once.json, sıvı fikstürü, ``bell_80``): çizim satırı
    ``bell_80; conv 30.0 deg, div 30.0 deg`` — 30 derece BOĞAZ açısıdır;
    yayımlanan Isp ise ``exit_angle_deg = 8,5``e demirli
    (``divergence_efficiency = 0,9945079316809584``; özdeşlik
    ``(1 + cos 8,5)/2``). Çıkış açısı çizimde HİÇ geçmiyordu.
    """

    @staticmethod
    def _satirlar(md):
        from hrma.export.drawing_generator import _prepare, _schedule_rows
        nmd, d = _sessiz(_prepare, md)
        return dict(_sessiz(_schedule_rows, nmd, d))

    def test_cozucunun_cikis_acisi_okunur(self, liquid):
        from hrma.export.cad_visualization import _nozzle_exit_angle_deg
        assert _nozzle_exit_angle_deg(liquid) == pytest.approx(8.5)

    def test_cikis_acisi_isp_verimiyle_ozdes(self, liquid):
        """Sayının neden önemli olduğunu kilitler: Isp ona demirli."""
        from hrma.export.cad_visualization import _nozzle_exit_angle_deg
        acilar = liquid.get('nozzle_angles') or {}
        verim = acilar.get('divergence_efficiency')
        if verim is None:
            pytest.skip('fikstür divergence_efficiency yayımlamıyor '
                        '(gerekçe DOĞRULANDI: alan okundu, None)')
        theta = _nozzle_exit_angle_deg(liquid)
        assert (1 + math.cos(math.radians(theta))) / 2 == pytest.approx(
            verim, rel=1e-9)

    def test_cizimde_cikis_acisi_satiri_var(self, liquid):
        satirlar = self._satirlar(liquid)
        assert 'Nozzle exit half angle' in satirlar, (
            'imalat çizimi çıkış açısını hiç basmıyor')
        assert '8.5 deg' in satirlar['Nozzle exit half angle']

    def test_div_sutunu_ne_anlama_geldigini_soyler(self, liquid):
        satir = self._satirlar(liquid)['Nozzle exit half angle']
        assert 'throat angle' in satir, (
            'çan lülede div sütununun BOĞAZ açısı olduğu söylenmiyor')

    def test_konik_lulede_sabit_aci_denir(self, solid):
        satir = self._satirlar(solid)['Nozzle exit half angle']
        assert 'constant half angle' in satir
        assert 'same as the divergence half angle' in satir

    def test_aci_satiri_YAPRAK_DAGILIMINI_kaydirmaz(self, solid):
        """Beyan satırı TABLONUN SONUNDA yaşar (Z5S yaprak kuralı).

        Ölçüldü: satır araya konduğunda kendisinden sonraki satırların yaprak
        dağılımı kaydı ve enjektör satırını 3. yaprakta arayan kardeş bekçi
        (``test_export_real_data::test_drawing_pdf_uses_solver_injector``)
        başka yaprağa baktı.
        """
        satirlar = list(self._satirlar(solid))
        assert satirlar.index('Nozzle exit half angle') > satirlar.index(
            'Injector orifices'), (
            'çıkış açısı satırı enjektör satırının ÖNÜNE girmiş — yaprak '
            'dağılımı kayar')


# ---------------------------------------------------------------------------
# P9B1-18 — lüle kütlesi "AUTHORITATIVE" ama cidar/malzeme üreteç varsayımı
# ---------------------------------------------------------------------------
class TestP9B1_18LuleKunyesi:
    """Lüle kütlesinin İKİ girdisi de kaynağıyla birlikte yayımlanır.

    ÖLÇÜM (once.json): katı ve sıvı sonuçlarında ``nozzle_geometry`` BOŞ,
    ``nozzle_material`` YOK -> cidar üreteç kuralından (katı **3,659** mm,
    sıvı **3,077** mm), yoğunluk sessizce grafitten (1800 kg/m3). Künye ise
    "AUTHORITATIVE ... same contour, wall and material as the STEP/STL parts"
    diyordu ve varsayımdan HİÇ söz etmiyordu.
    """

    @staticmethod
    def _ozet(md):
        """Tam ``performance_summary``.

        ÖH D29 (defter P15B4-12): lülenin cidarı ``geometry_summary``,
        yoğunluğu ``material_summary`` sözlüğünde durur; ``mass_breakdown``
        yalnız kütle taşır. Bekçi alanı YENİ adresinde arar — taşıma
        sessizce kayba dönüşemez.
        """
        from hrma.export.cad_visualization import MotorCADDesigner
        cad = _sessiz(MotorCADDesigner().generate_3d_motor_assembly, dict(md))
        return cad['performance_summary'] or {}

    @classmethod
    def _kutle_dokumu(cls, md):
        return cls._ozet(md)['mass_breakdown']

    @pytest.mark.parametrize('ad,cidar_mm', [('solid', 3.6593543550787127),
                                             ('liquid', 3.076748319268569)])
    def test_uretec_kurali_beyan_edilir(self, ad, cidar_mm):
        ozet = self._ozet(_fixture(ad))
        geo, d = ozet['geometry_summary'], ozet['mass_breakdown']
        assert geo['nozzle_wall_thickness_mm'] == pytest.approx(cidar_mm,
                                                                rel=1e-9)
        kaynak = geo['nozzle_wall_thickness_source']
        assert 'ASSUMED generator rule' in kaynak
        assert 'NO structural or thermal analysis' in kaynak
        assert 'ASSUMED' in d['nozzle_mass_basis'] or (
            kaynak in d['nozzle_mass_basis'])

    @pytest.mark.parametrize('ad', ('solid', 'liquid'))
    def test_yogunluk_yedegi_adiyla_soylenir(self, ad):
        kaynak = self._ozet(_fixture(ad))['material_summary'][
            'nozzle_mass_density_source']
        assert 'NAMED generator fallback graphite' in kaynak
        assert 'NOT a material this run selected' in kaynak

    def test_yayimlanan_cidar_varsa_oyle_soylenir(self, hybrid):
        ozet = self._ozet(hybrid)
        assert ozet['geometry_summary'][
            'nozzle_wall_thickness_source'].startswith(
            'nozzle_geometry.wall_thickness published by this run')
        assert 'as selected by this run' in ozet['material_summary'][
            'nozzle_mass_density_source']

    def test_kutle_degeri_DEGISMEDI(self, solid, liquid):
        """Onarım künyeyi düzeltti, SAYIYI değil (P09 ölçümüyle birebir)."""
        assert self._kutle_dokumu(solid)['nozzle_mass'] == pytest.approx(
            0.2175, abs=5e-5)
        assert self._kutle_dokumu(liquid)['nozzle_mass'] == pytest.approx(
            0.7343, abs=5e-5)

    def test_cidar_kurali_TEK_YERDE_tanimli(self):
        """``cad_visualization`` kuralı ``step_export``ten ithal eder."""
        from pathlib import Path

        import hrma.export.cad_visualization as cv
        src = Path(cv.__file__).read_text(encoding='utf-8')
        assert 'max(0.003, 0.1 *' not in src, (
            'lüle cidar kuralı yine literal olarak kopyalanmış (TEK KAYNAK)')
        assert 'NOZZLE_WALL_THROAT_FRACTION' in src


# ---------------------------------------------------------------------------
# P9B2-24 — yayımlanan boy ⟷ STEP montaj boyu
# ---------------------------------------------------------------------------
@_b123d
class TestP9B2_24MontajBoyu:
    """İmalat montajı KENDİ boyunu ve yayımlanan boyla farkını söyler.

    ÖLÇÜM (once.json): sıvıda yayımlanan 578,846 mm ⟷ STEP montaj
    **613,492 mm** (+34,646 = kapak 8,000 + yakınsak 26,645); katıda
    552,935 ⟷ **561,855** (+8,920 = kapak 8,000 + lüle ucu 0,920).
    Hiçbir çıktı bu iki sayıyı uzlaştırmıyordu.
    """

    @pytest.mark.parametrize('ad,tip', [('solid', 'solid'),
                                        ('liquid', 'liquid')])
    def test_montaj_adi_olculen_ve_yayimlanan_boyu_tasir(self, ad, tip,
                                                         tmp_path):
        from hrma.export.step_export import generate_step_assembly
        files = _sessiz(generate_step_assembly, _fixture(ad),
                        out_dir=str(tmp_path), motor_type=tip)
        metin = _step_metni(files['assembly'])
        assert 'as-built overall length' in metin
        assert 'the analysis publishes' in metin
        assert 'a difference of' in metin

    def test_olculen_boy_gercek_zarfla_ayni(self, liquid, tmp_path):
        from hrma.export.step_export import generate_step_assembly
        files = _sessiz(generate_step_assembly, liquid,
                        out_dir=str(tmp_path), motor_type='liquid')
        bb = _bbox(files['assembly'])
        olculen = bb.max.X - bb.min.X
        metin = _step_metni(files['assembly'])
        # Künyedeki sayı, dosyanın GERÇEK zarfıyla aynı olmalı
        assert f'as-built overall length {olculen:.2f} mm' in metin, (
            f'künye ile ölçülen zarf ({olculen:.2f} mm) ayrışıyor')

    def test_yayimlanan_boyun_neyi_saymadigi_yazilir(self, liquid, tmp_path):
        from hrma.export.step_export import generate_step_assembly
        files = _sessiz(generate_step_assembly, liquid,
                        out_dir=str(tmp_path), motor_type='liquid')
        metin = _step_metni(files['assembly'])
        assert 'does not include' in metin
        assert 'closure head' in metin and 'convergent cone' in metin


# ---------------------------------------------------------------------------
# P9B2-08 — ÇÜRÜTÜLDÜ (a1/P9B1-14 kapattı); kapı bir daha açılmasın
# ---------------------------------------------------------------------------
class TestP9B2_08MalzemeCurutuldu:
    """İmalat çiziminde kamara malzemesi 'NOT AVAILABLE' YAZMAZ.

    Kalem ÇÜRÜTÜLDÜ: ölçüldü (once.json), üç motorda da malzeme çözülüyor —
    katı ``Carbon steel (generic, A36-class)``, sıvı ``Inconel 718 (aged)``,
    hibrit ``AISI 4130 low-alloy steel (normalized)``. P09 devrindeki
    "NOT AVAILABLE - not produced by this analysis run" beyanı (ki ölçülebilir
    biçimde YANLIŞTI: üretiliyordu, okunmuyordu) ÖH D15 a1'in P9B1-14
    onarımıyla kapandı. Bekçi yine yazılır: kapı bir daha açılmasın.
    """

    @pytest.mark.parametrize('ad,beklenen', [
        ('solid', 'Carbon steel'),
        ('liquid', 'Inconel 718'),
        ('hybrid', 'AISI 4130'),
    ])
    def test_uc_semada_da_malzeme_cozulur(self, ad, beklenen):
        from hrma.export.cad_visualization import _chamber_material
        _key, isim, rho = _chamber_material(_fixture(ad))
        assert isim and beklenen in isim, (
            f'{ad}: malzeme "{isim}" — çözümleyici yine yalnız hibrit '
            'şemasını tanıyor olabilir')
        assert rho and rho > 0

    @pytest.mark.parametrize('ad', ('solid', 'liquid', 'hybrid'))
    def test_cizim_satirinda_NOT_AVAILABLE_yok(self, ad):
        from hrma.export.drawing_generator import _prepare, _schedule_rows
        nmd, d = _sessiz(_prepare, _fixture(ad))
        satirlar = dict(_sessiz(_schedule_rows, nmd, d))
        assert 'NOT AVAILABLE' not in satirlar['Chamber material'], (
            f'{ad}: imalat çizimi kamara malzemesini bilmediğini söylüyor')


# ---------------------------------------------------------------------------
# P9B2-02 — KISMEN: kapak beyanlı ama solid/liquid'de hâlâ üreteç sabiti
# ---------------------------------------------------------------------------
class TestP9B2_02BasKapagi:
    """Baş kapağı: analiz varsa ONDAN, yoksa 8,00 mm ve ADIYLA beyanlı.

    ÖLÇÜM (once.json): hibritte kapak yapısal analizden geliyor
    (``flat_mm = 13,6406``); katı ve sıvıda ``end_cap_analysis`` YOK ve
    kalınlık **8,00 mm** üreteç sabiti — beyanı ÖH Z5S'te eklenmiş
    (``ASSUMED closure head ...``). Kalemin "beyanı da yok" yarısı KAPALI;
    "hiçbir analizden gelmiyor" yarısı katı/sıvıda CANLI ve çözümü yapısal
    analiz kulvarındadır (kapak hesabı ``engines/`` sahasında üretilir).
    Bekçi bugünkü hâli kilitler ki sessiz sabite geri dönülmesin.
    """

    def test_analiz_varsa_kapak_ondan_gelir(self, hybrid):
        from hrma.export.cad_visualization import _front_cap_design
        from hrma.export.motor_geometry import normalise_export_geometry
        md, _ = normalise_export_geometry(hybrid)
        rc = float(md['chamber_diameter']) * 1000.0 / 2
        cap = _front_cap_design(md, wall_mm=2.4, bore_radius_mm=rc)
        assert cap['flat_mm'] is not None
        assert 'structural analysis' in cap['source']

    @pytest.mark.parametrize('ad', ('solid', 'liquid'))
    def test_analiz_yoksa_sabit_ADIYLA_beyan_edilir(self, ad):
        from hrma.export.cad_visualization import _front_cap_design
        from hrma.export.motor_geometry import normalise_export_geometry
        md, _ = normalise_export_geometry(_fixture(ad))
        rc = float(md['chamber_diameter']) * 1000.0 / 2
        cap = _front_cap_design(md, wall_mm=2.4, bore_radius_mm=rc)
        assert cap['flat_mm'] is None
        assert cap['thickness_mm'] == pytest.approx(8.0)
        assert 'ASSUMED closure head' in cap['source']
        assert 'NOT a pressure-vessel head calculation' in cap['source']

    @_b123d
    def test_kapak_beyani_STEP_parca_adinda_tasinir(self, solid, tmp_path):
        from hrma.export.step_export import generate_step_assembly
        files = _sessiz(generate_step_assembly, solid,
                        out_dir=str(tmp_path), motor_type='solid')
        metin = _step_metni(files['chamber'])
        assert 'closure head' in metin
        assert 'ASSUMED closure head' in metin
