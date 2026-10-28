"""ÖH Z5S / P09-B — İmalat paketi (STEP + DXF) bekçileri.

Bu dosya sekiz defter kalemini kilitler. Ortak kusur sınıfı tekti: **imalata
giden dosyanın sayısı çözücünün sayısı değil, üreteç sezgisiydi ve hiçbir
alan farkı beyan etmiyordu.**

===========  =============================================================
kalem        kilitlenen davranış
===========  =============================================================
P9B2-01      KRİTİK. Enjektör plakası HER devreyi deler; delemediği devreyi
             parça adında BEYAN eder. Eski hâl: sıvı motorda yalnız yakıt
             devresi deliniyordu, oksitleyici plakaya %0 iniyordu.
P9B2-29      Lüle et kalınlığı bir ÜRETEÇ kuralıdır — parça adında beyan
             edilir; DXF "WALL THICKNESS" ölçüsünün kamaraya ait olduğunu
             ve lüle dış profilinin çizilmediğini söyler.
P9B2-22      Grain'in eksenel konumu üreteç yerleşimidir — STEP parça adı,
             DXF metni ve ölçü tablosu bunu yazar.
P9B2-20      STEP paketinin parça listesi ARŞİVDEKİ dosyalardan okunur;
             koşuldan bağımsız dört parça sayılmaz.
P9B2-28      Eksen sözleşmesi (katılar +X, STL mesh'leri +Z) montaj adında,
             README'de ve DXF'te yazılıdır.
P9B2-05      Tek parça STEP dosyaları kendi adlarını taşır; CAD ağacında
             "COMPOUND" görünmez.
P9B2-10      Lüle açılarının kaynağı (çözücünün ``angles_source`` beyanı)
             düşürülmez.
P9B2-30      Katı motorun çizim PDF'inde "INJECTOR FACE PATTERN" yaprağı
             HİÇ basılmaz — katı motorda enjektör yoktur.
===========  =============================================================

Bekçi katmanı bilinçlidir: kalemlerin çoğu ``build123d`` / ``ezdxf`` /
``reportlab`` kurulu OLMADAN da koşan bir katmanda (plan çözücüsü, künye
metni, tablo satırı) sınanır. Paket notundaki şart buydu — eski bekçiler
``importorskip`` kapısının arkasında saklanıp CI'da sessizce kayboluyordu.
"""

import contextlib
import io
import os

import pytest

from hrma.export import drawing_generator, step_export
from tests.bagimlilik_kapisi import kurulu_mu

# V301/T-ÇAPA-A: katı örnek motor geometrisi tek tanımdan (çekirdek
# 30 -> 48 mm). Eski Ø100/500/30 @ 40 bar BATES portu boğuluyordu
# (A_p/A_t 0,947) ve K-A port kapısından 422 alıyor; bu dosyadaki
# düğümlerin konusu boğulan port değil (K-A RAPOR §6, kural 1).
from hrma.engines.solid_rocket_engine import SOLID_DEFAULT_GEOMETRY_MM  # noqa: E402
_CEKIRDEK_MM = SOLID_DEFAULT_GEOMETRY_MM['core_diameter']


_B123D = kurulu_mu('build123d')
_EZDXF = kurulu_mu('ezdxf')
_REPORTLAB = kurulu_mu('reportlab')

_kati_gerekli = pytest.mark.skipif(
    not _B123D, reason='build123d kurulu değil (gerekçe DOĞRULANDI: find_spec)')
_dxf_gerekli = pytest.mark.skipif(
    not _EZDXF, reason='ezdxf kurulu değil (gerekçe DOĞRULANDI: find_spec)')
_pdf_gerekli = pytest.mark.skipif(
    not (_REPORTLAB and kurulu_mu('pypdf')),
    reason='reportlab/pypdf kurulu değil (gerekçe DOĞRULANDI: find_spec)')


def _quiet(fn, *args, **kwargs):
    """Çözücülerin print gürültüsünü yutar."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


#: Enjektör panelinin TASARLANAN plaka kalınlığı [mm]. Ürün yolunda bu sayı
#: kullanıcıdan gelir (``injector_design.injector_plate_structural``
#: kalınlığı çağırandan alır ve ``plate_thickness_earned`` ile künyeler);
#: HRMA onu TÜRETMEZ.
Z5S_PANEL_PLAKA_MM = 6.0


def _panel_plakali(sonuc, t_mm=Z5S_PANEL_PLAKA_MM):
    """Sonuca enjektör panelinin tasarlanan plakasını ekler.

    ÖH D32 / OH-D31-16. Bu dosyadaki enjektör bekçileri plakanın İÇERİĞİNİ
    ölçer (iki devrenin delikleri, devre adları, 'ASSUMED' halka beyanı) ve
    bunun için plakanın ÇİZİLMİŞ olmasını gerektirir. Plaka kalınlığı ise
    çözücüden değil kullanıcının enjektör panelinden gelir; ham motor
    koşumu onu yayımlamaz. Ölçüldü (taban dd1dcddc): ham koşumda
    ``cad_visualization._injector_plate_design(...)['thickness_m'] is None``,
    dolayısıyla STL plakayı çizmiyor, STEP ise kamaranın ÖN KAPAK
    kalınlığını plaka yerine koyarak çiziyordu — aynı pakette iki farklı
    motor (``/api/export-complete-zip`` bunu 422 ile reddediyordu).

    D32'de STEP de kardeşinin TEK çözümleyicisine bağlandı: kalınlık yoksa
    plaka çizilmez. Bu yardımcı, kalınlığın KAZANILDIĞI koşuyu kurar —
    böylece aşağıdaki bekçiler asıl niyetlerini (plakanın içeriği) ölçmeye
    devam eder. Kalınlığın YOKLUĞUNDA parçanın çizilmediği
    ``tests/test_d32_ihracat_a1.py``de ayrıca sınanır.
    """
    r = dict(sonuc)
    r['injector_results'] = {
        'plate_structural': {
            'status': 'analyzed',
            'plate_thickness_mm': float(t_mm),
            'material': 'stainless_steel_316',
        },
    }
    return r


# ---------------------------------------------------------------------------
# Gerçek çözümler — uydurma sözlük yok
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def sivi_sonuc():
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    from hrma.export.motor_geometry import liquid_results_to_motor_geometry
    r = _quiet(LiquidRocketEngine(thrust=10000, chamber_pressure=100,
                                  mixture_ratio=2.5).calculate_performance)
    r['motor_name'] = 'Z5S_SIVI'
    r['motor_geometry'] = liquid_results_to_motor_geometry(r)
    return r


@pytest.fixture(scope='module')
def kati_sonuc():
    from hrma.engines.solid_rocket_engine import SolidRocketEngine
    from hrma.export.motor_geometry import solid_results_to_motor_geometry
    r = _quiet(SolidRocketEngine(chamber_diameter=100, grain_length=500,
                                 core_diameter=_CEKIRDEK_MM,
                                 chamber_pressure=40).calculate_performance)
    r['motor_name'] = 'Z5S_KATI'
    r['motor_geometry'] = solid_results_to_motor_geometry(r)
    return r


@pytest.fixture(scope='module')
def hibrit_sonuc():
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    r = _quiet(HybridRocketEngine(thrust=2000, burn_time=10, of_ratio=6.0,
                                  chamber_pressure=20, fuel_type='htpb',
                                  oxidizer_type='n2o').calculate)
    r['motor_name'] = 'Z5S_HIBRIT'
    return r


def _step_parca_adlari(path):
    """STEP dosyasındaki PRODUCT adları (boşluklar sıkıştırılmış)."""
    import re
    compact = ''.join(open(path, encoding='utf-8', errors='ignore').read()
                      .split())
    return re.findall(r"PRODUCT\('([^']*)'", compact)


def _dxf_metinleri(path):
    import ezdxf
    return [e.dxf.text for e in ezdxf.readfile(path).modelspace()
            if e.dxftype() == 'TEXT']


def _tablo(motor_results):
    md, dims = drawing_generator._prepare(motor_results)
    return dict(drawing_generator._schedule_rows(md, dims))


# ---------------------------------------------------------------------------
# P9B2-01 (KRİTİK) — enjektör plakasında İKİ DEVRE
# ---------------------------------------------------------------------------

class TestP9B201EnjektorDevreleri:
    """Ölçüldü (27 Ağustos 2026, 10 kN sıvı motor, Pc=100 bar, MR=2,5):

    çözücü ``number_of_elements = 5``, ``fuel_orifice_diameter_mm = 2,3073``
    **ve** ``oxidizer_orifice_diameter_mm = 2,4994`` yayımlarken üretilen
    plakada 5 delik vardı — hepsi YAKIT devresi. Oksitleyici plakaya %0
    iniyordu; böyle bir enjektör hiç püskürtemez.
    """

    def test_sivi_sonucta_iki_devre_de_cozulur(self, sivi_sonuc):
        """Kapı artık her devrenin sayısını VE çapını ayrı çözer."""
        plan = step_export.resolve_injector_plan(sivi_sonuc,
                                                 motor_type='liquid')
        adlar = [c['name'] for c in plan['circuits']]
        assert adlar == ['oxidizer', 'fuel'], (
            f'sıvı motorda çözülen devreler {adlar} — oksitleyici devresi '
            'yine plakaya inmiyor')
        cap = {c['name']: c['d_mm'] for c in plan['circuits']}
        kaynak = sivi_sonuc['injector_design']
        assert cap['oxidizer'] == pytest.approx(
            kaynak['oxidizer_orifice_diameter_mm'])
        assert cap['fuel'] == pytest.approx(
            kaynak['fuel_orifice_diameter_mm'])
        # İki devre GERÇEKTEN farklı çaplar taşıyor: aynı sayı olsaydı
        # bekçi "hangisi çizildi" sorusunu ölçemezdi.
        assert cap['oxidizer'] != cap['fuel']

    def test_devre_sayilari_cozucunun_alanlarindan_gelir(self, sivi_sonuc):
        """Künye, sayının HANGİ alandan geldiğini adıyla taşır."""
        plan = step_export.resolve_injector_plan(sivi_sonuc,
                                                 motor_type='liquid')
        for circuit in plan['circuits']:
            assert circuit['count_field'], 'delik sayısının alan adı yok'
            assert circuit['diameter_field'], 'çapın alan adı yok'
            assert circuit['n'] == int(round(
                sivi_sonuc['injector_design']['number_of_elements']))

    def test_eksik_devre_beyan_edilir(self):
        """Yalnız bir devre yayımlanmışsa diğeri ADIYLA beyan edilir."""
        payload = {'injector_design': {'number_of_elements': 8,
                                       'fuel_orifice_diameter_mm': 1.2}}
        plan = step_export.resolve_injector_plan(payload, motor_type='liquid')
        assert [c['name'] for c in plan['circuits']] == ['fuel']
        beyan = ' | '.join(plan['missing'])
        assert 'oxidizer circuit NOT drilled' in beyan, (
            f'çizilmeyen oksitleyici devresi beyan edilmiyor: {beyan!r}')

    def test_hibritte_yakit_devresi_uygulanamaz_diye_yazilir(self,
                                                             hibrit_sonuc):
        """Hibritte yakıt katı grain'dir; "eksik devre" demek YANLIŞ olur."""
        plan = step_export.resolve_injector_plan(hibrit_sonuc,
                                                 motor_type='hybrid')
        assert [c['name'] for c in plan['circuits']] == ['oxidizer']
        assert any('solid grain' in m for m in plan['missing']), plan['missing']

    def test_enjektor_iddiasi_yoksa_parca_iddia_edilmez(self, kati_sonuc):
        """Katı motor sonucunda enjektör bloğu yok — plan 'claimed' demez."""
        plan = step_export.resolve_injector_plan(kati_sonuc,
                                                 motor_type='solid')
        assert plan['claimed'] is False
        assert plan['circuits'] == []

    @_kati_gerekli
    def test_uretilen_plaka_iki_devrenin_deliklerini_tasir(self, sivi_sonuc,
                                                          tmp_path):
        """İmalata giden DOSYADA delik sayısı ölçülür (sözlükte değil).

        Plaka silindiri + (ox delikleri) + (yakıt delikleri) kadar silindirik
        yüzey olmalı. Eski hâlde 1 + 5 = 6 vardı; oksitleyici devresi hiç
        delinmiyordu.
        """
        files = _quiet(step_export.generate_step_assembly,
                       _panel_plakali(sivi_sonuc),
                       out_dir=str(tmp_path), motor_type='liquid')
        plan = step_export.resolve_injector_plan(sivi_sonuc,
                                                 motor_type='liquid')
        beklenen = 1 + sum(c['n'] for c in plan['circuits'])
        metin = open(files['injector'], encoding='utf-8',
                     errors='ignore').read()
        assert metin.count('CYLINDRICAL_SURFACE') == beklenen, (
            f"plakada {metin.count('CYLINDRICAL_SURFACE')} silindirik yüzey "
            f'var, {beklenen} bekleniyordu (1 plaka + '
            f"{[c['n'] for c in plan['circuits']]} delik)")

    @_kati_gerekli
    def test_parca_adi_her_devreyi_adiyla_yazar(self, sivi_sonuc, tmp_path):
        """Beyan STEP dosyasının İÇİNDE taşınır — imalatçıya giden şey odur."""
        files = _quiet(step_export.generate_step_assembly,
                       _panel_plakali(sivi_sonuc),
                       out_dir=str(tmp_path), motor_type='liquid')
        ad = ''.join(_step_parca_adlari(files['injector'])[:1])
        assert 'oxidizercircuit' in ad and 'fuelcircuit' in ad, (
            f'enjektör parça adı devreleri saymıyor: {ad[:200]!r}')
        assert 'ASSUMED' in ad, 'halka yarıçapı varsayımı beyanı düştü'

    @_kati_gerekli
    def test_delinmeyen_devre_STEP_DOSYASINDA_beyan_edilir(self, sivi_sonuc,
                                                           tmp_path):
        """Eksik devrenin beyanı sözlükte DEĞİL, imalat dosyasında olmalı.

        Mutasyon ölçümü (27 Ağustos 2026): ``inj_notes.extend(plan['missing'])``
        satırı susturulduğunda kardeş bekçiler YEŞİL kaldı — çünkü hepsi iki
        devresi de çözülen bir koşumu ölçüyordu ve o koşumda ``missing`` boş.
        Bu bekçi devreyi bilerek EKSİLTİR: oksitleyici çapı sonuçtan
        çıkarılınca plakada ox deliği kalmaz ve bunu SÖYLEMEK zorunludur.
        """
        import copy
        r = copy.deepcopy(sivi_sonuc)
        for blok in (r, r.get('injector_design') or {}):
            for anahtar in ('oxidizer_orifice_diameter_mm',
                            'ox_orifice_diameter_mm', 'ox_orifice_diameter'):
                blok.pop(anahtar, None)
        plan = step_export.resolve_injector_plan(r, motor_type='liquid')
        assert [c['name'] for c in plan['circuits']] == ['fuel'], (
            'fikstür kurulamadı: oksitleyici devresi hâlâ çözülüyor')
        files = _quiet(step_export.generate_step_assembly,
                       _panel_plakali(r),
                       out_dir=str(tmp_path), motor_type='liquid')
        ad = ''.join(_step_parca_adlari(files['injector'])[:1])
        assert 'oxidizercircuitNOTdrilled' in ad, (
            'plakada oksitleyici deliği YOK ama STEP dosyası bunu '
            f'söylemiyor: {ad[:240]!r}')

    @_kati_gerekli
    def test_hibrit_plakasi_yakit_devresinin_yoklugunu_yazar(self,
                                                             hibrit_sonuc,
                                                             tmp_path):
        """Hibritte de "çizilmeyen devre" beyanı dosyaya iner."""
        files = _quiet(step_export.generate_step_assembly,
                       _panel_plakali(hibrit_sonuc),
                       out_dir=str(tmp_path))
        ad = ''.join(_step_parca_adlari(files['injector'])[:1])
        assert 'fuelcircuitNOTdrilled' in ad, (
            f'hibrit plakasında yakıt devresi beyanı yok: {ad[:240]!r}')
        assert 'solidgrain' in ad, 'gerekçe (katı grain) yazılmıyor'


# ---------------------------------------------------------------------------
# P9B2-29 — lüle et kalınlığı: üreteç kuralı, beyanı yok
# ---------------------------------------------------------------------------

class TestP9B229LuleCidari:
    def test_ureteç_kurali_adlandirilmis_sabitlerde(self):
        """Sayı DEĞİŞMEDİ; sihirli sayı olmaktan çıktı (CLAUDE.md kural 11)."""
        assert step_export.NOZZLE_WALL_MIN_MM == 3.0
        assert step_export.NOZZLE_WALL_THROAT_FRACTION == 0.1
        assert step_export.NOZZLE_WALL_THROAT_FALLBACK_M == 0.02

    @_kati_gerekli
    def test_lule_parca_adi_kurali_beyan_eder(self, hibrit_sonuc, kati_sonuc,
                                              tmp_path):
        """Lüle etinin künyesi KAYNAĞINI söyler; kaynak uydurulmaz.

        ÖH V3 CAD A1 · H2 — ÇEVRİLDİ (12 Eki 2026, ana model izni, dört
        koşul; rapor ``docs/scofield/raw/OH/V3/cad-duzeltme/rapor.md``
        "Bölüm T"). Bu düğüm hibrit fikstürde "ASSUMED generator rule ... NOT
        from a structural or thermal analysis" künyesini arıyordu; oysa hibrit
        çözücü ``nozzle_geometry.wall_thickness`` YAYIMLIYOR (thin_wall_hoop)
        ve eski STEP onu okumadan 3 mm kural eti çizip bu YANLIŞ künyeyi
        basıyordu (7 Eki CAD kontrolü H2). Kâhin dışa aktarım kod yolu
        DEĞİL, çözücünün kendi yayımladığı et ve dayanağıdır
        (``nozzle_geometry.wall_thickness`` / ``wall_thickness_basis``).
        Niyetin öbür yarısı (et yayımlanmadığında kural adıyla beyan edilir)
        ``nozzle_geometry`` yayımlamayan katı fikstürde aynen sınanır.
        """
        geo = hibrit_sonuc['nozzle_geometry']
        et_mm = geo['wall_thickness']
        dayanak = ''.join(str(geo['wall_thickness_basis']).split())
        files = _quiet(step_export.generate_step_assembly, hibrit_sonuc,
                       out_dir=str(tmp_path / 'hibrit'))
        ad = ''.join(_step_parca_adlari(files['nozzle'])[:1])
        assert f'wall{et_mm:.2f}mm' in ad, (
            f'lüle eti çözücünün yayımladığı {et_mm:.3f} mm değil: {ad!r}')
        assert 'nozzle_geometry.wall_thicknesspublishedbythisrun' in ad, (
            f'etin kaynağı (çözücü alanı) söylenmiyor: {ad!r}')
        assert dayanak in ad, (
            f'çözücünün dayanağı ({dayanak}) künyede yok: {ad!r}')
        assert 'ASSUMEDgeneratorrule' not in ad, (
            f'yayımlanan et varken üreteç kuralı beyan ediliyor: {ad!r}')
        assert 'NOTfromastructuralorthermalanalysis' not in ad, (
            f'analizden GELEN et "analizden değil" diye etiketleniyor: {ad!r}')

        assert not (kati_sonuc.get('nozzle_geometry') or {}).get(
            'wall_thickness'), 'katı fikstür artık lüle eti yayımlıyor'
        files = _quiet(step_export.generate_step_assembly, kati_sonuc,
                       out_dir=str(tmp_path / 'kati'))
        ad = ''.join(_step_parca_adlari(files['nozzle'])[:1])
        assert 'ASSUMEDgeneratorrule' in ad, (
            f'lüle cidarı hâlâ beyansız: {ad!r}')
        assert 'NOTfromastructuralorthermalanalysis' in ad, (
            'cidarın analizden GELMEDİĞİ söylenmiyor')

    @_dxf_gerekli
    def test_dxf_wall_thickness_olcusunun_kapsamini_soyler(self, hibrit_sonuc,
                                                          tmp_path):
        """DXF lülenin dış profilini çizmiyor ama "WALL THICKNESS" basıyordu.

        V301 CAD-2 kalem 6: DXF artık lüle dış duvarını çiziyor
        (``nozzle_wall_profile``). Kapsam beyanı kalır: "WALL THICKNESS"
        ölçüsü kamaraya aittir; lüle satırı çizilen duvarı anlatır (eski
        beklenti 'NOT drawn' bugünkü çizimsiz çıktıyı kilitliyordu).
        """
        path = _quiet(drawing_generator.generate_dxf, hibrit_sonuc,
                      out_path=str(tmp_path / 'n.dxf'))
        metinler = _dxf_metinleri(path)
        assert any(t.startswith('NOZZLE WALL:') for t in metinler), (
            f'lüle cidarı için kapsam beyanı yok: {metinler}')
        lule = next(t for t in metinler if t.startswith('NOZZLE WALL:'))
        assert 'DRAWN in this view' in lule and 'chamber only' in lule

    @_dxf_gerekli
    def test_kardes_bekci_cidar_olcusunu_hala_okuyabilir(self, hibrit_sonuc,
                                                        tmp_path):
        """Yeni satırlar "WALL THICKNESS" ÖNEKİNİ çalmamalı.

        Kardeş bekçi (``test_faz4_export_geometri``) kamara cidarını bu
        önekle arıyor; araya giren bir satır ölçüyü kaçırtırdı.
        """
        path = _quiet(drawing_generator.generate_dxf, hibrit_sonuc,
                      out_path=str(tmp_path / 'n2.dxf'))
        onekli = [t for t in _dxf_metinleri(path)
                  if t.startswith('WALL THICKNESS')]
        assert len(onekli) == 1, (
            f'"WALL THICKNESS" ile başlayan {len(onekli)} satır var: {onekli}')
        assert 'mm' in onekli[0]


# ---------------------------------------------------------------------------
# P9B2-22 — grain'in eksenel konumu
# ---------------------------------------------------------------------------

class TestP9B222GrainEksenelKonumu:
    def test_kural_iki_uretecte_de_ayni_sabitten(self):
        """STEP ile DXF aynı yeri çizsin: kesir tek bir sayı olarak adlı."""
        assert (step_export.GRAIN_AXIAL_POSITION_FRACTION
                == drawing_generator.GRAIN_AXIAL_POSITION_FRACTION == 0.35)
        assert (step_export.GRAIN_AXIAL_MIN_SLACK_MM
                == drawing_generator.GRAIN_AXIAL_MIN_SLACK_MM == 4.0)

    @_kati_gerekli
    def test_grain_parca_adi_konumu_beyan_eder(self, kati_sonuc, tmp_path):
        files = _quiet(step_export.generate_step_assembly, kati_sonuc,
                       out_dir=str(tmp_path), motor_type='solid')
        ad = ''.join(_step_parca_adlari(files['fuel_grain'])[:1])
        assert 'axialpositionASSUMED' in ad, (
            f'grain eksenel konumu beyansız: {ad!r}')
        assert 'NOsolverpublishes' in ad

    @_dxf_gerekli
    def test_dxf_grain_konumunu_yazar(self, kati_sonuc, tmp_path):
        path = _quiet(drawing_generator.generate_dxf, kati_sonuc,
                      out_path=str(tmp_path / 'g.dxf'))
        satir = [t for t in _dxf_metinleri(path)
                 if t.startswith('GRAIN AXIAL POSITION:')]
        assert satir, 'çizimde grain eksenel konumu beyanı yok'
        assert 'ASSUMED' in satir[0]

    def test_tablo_grain_konumunu_yazar(self, kati_sonuc):
        tablo = _tablo(kati_sonuc)
        assert 'Grain axial position' in tablo
        assert 'ASSUMED' in tablo['Grain axial position']

    def test_grainsiz_motorda_satir_uydurulmaz(self, sivi_sonuc):
        """Sıvı motorda grain yok — konum satırı da olmamalı (fail-closed)."""
        assert 'Grain axial position' not in _tablo(sivi_sonuc)


# ---------------------------------------------------------------------------
# P9B2-20 — README parça listesi ARŞİVDEN okunur
# ---------------------------------------------------------------------------

class TestP9B220ReadmeParcaListesi:
    """Eski metin her koşuda dört parçayı sayıyordu: katı motor paketinde
    "injector plate (drilled orifices)", sıvı motor paketinde "fuel grain" —
    o parçalar pakette YOKKEN.
    """

    def test_kati_paketinde_enjektor_plakasi_sayilmaz(self, tmp_path):
        yollar = []
        for ad in ('chamber', 'nozzle', 'fuel_grain', 'assembly'):
            p = tmp_path / f'M_{ad}.step'
            p.write_text('ISO-10303-21;', encoding='utf-8')
            yollar.append(str(p))
        metin = step_export.step_package_readme(yollar)
        assert 'fuel grain' in metin
        assert 'injector plate' not in metin, (
            f'katı motor paketinde olmayan plaka sayılıyor:\n{metin}')

    def test_sivi_paketinde_grain_sayilmaz(self, tmp_path):
        yollar = []
        for ad in ('chamber', 'nozzle', 'injector', 'assembly'):
            p = tmp_path / f'M_{ad}.step'
            p.write_text('ISO-10303-21;', encoding='utf-8')
            yollar.append(str(p))
        metin = step_export.step_package_readme(yollar)
        assert 'injector plate' in metin
        assert 'fuel grain' not in metin, (
            f'sıvı motor paketinde olmayan grain sayılıyor:\n{metin}')

    def test_var_olmayan_dosya_parca_diye_sayilmaz(self, tmp_path):
        """Yol verilmiş ama dosya üretilememişse parça YAZILMAZ."""
        gercek = tmp_path / 'M_chamber.step'
        gercek.write_text('ISO-10303-21;', encoding='utf-8')
        metin = step_export.step_package_readme(
            [str(gercek), str(tmp_path / 'M_injector.step')])
        assert 'chamber' in metin
        assert 'injector plate' not in metin


# ---------------------------------------------------------------------------
# P9B2-28 — eksen sözleşmesi
# ---------------------------------------------------------------------------

class TestP9B228EksenSozlesmesi:
    def test_sozlesme_metni_tek_ekseni_adlandirir(self):
        """Paketin TEK eksen sözleşmesi künyede adıyla yazar.

        ÖH D26 / defter P15B4-01 — BU İDDİA ÇEVRİLDİ. Eski hâli
        ``'+X' in note and '+Z' in note and '90 deg' in note`` idi; yani
        künyenin STEP ile STL'in AYRI eksende olduğunu ve kullanıcının
        dosyaları elle 90° döndürmesi gerektiğini söylemesini ŞART
        koşuyordu — kusuru koruyan bekçiydi (P9B2-28 o gün ayrışmayı yalnız
        BEYAN etmişti; beyan çözüm değildir). Ayrışma ölçülüp kapatıldı
        (``raw/OH/D26/ihracat/a1``: 3 motor / 5 parça, ayrışan 5 -> 0), bu
        yüzden künye artık tek sözleşme yazar ve iddia onu sınar.
        """
        note = step_export.STEP_AXIS_NOTE
        assert '+X' in note, note
        # Kullanıcıdan artık HİÇBİR düzeltme dönüşü istenmiyor.
        assert '90 deg' not in note, note
        assert 'STEP' in note and 'STL' in note, note

    def test_sozlesme_tek_kaynaktan_okunur(self):
        """Künye iki dosyada ayrı ayrı yazılmaz (CLAUDE.md kural 11)."""
        from hrma.export.motor_geometry import EXPORT_AXIS_NOTE
        assert step_export.STEP_AXIS_NOTE is EXPORT_AXIS_NOTE

    @_kati_gerekli
    def test_montaj_adi_sozlesmeyi_tasir(self, hibrit_sonuc, tmp_path):
        files = _quiet(step_export.generate_step_assembly, hibrit_sonuc,
                       out_dir=str(tmp_path))
        ad = ''.join(_step_parca_adlari(files['assembly'])[:1])
        assert 'axisconvention' in ad, (
            f'montaj adı eksen sözleşmesini taşımıyor: {ad!r}')

    def test_readme_sozlesmeyi_tasir(self, tmp_path):
        p = tmp_path / 'M_chamber.step'
        p.write_text('ISO-10303-21;', encoding='utf-8')
        assert 'axis convention' in step_export.step_package_readme(
            [str(p)]).lower()

    @_dxf_gerekli
    def test_dxf_sozlesmeyi_yazar(self, hibrit_sonuc, tmp_path):
        path = _quiet(drawing_generator.generate_dxf, hibrit_sonuc,
                      out_path=str(tmp_path / 'a.dxf'))
        assert any(t.startswith('AXIS CONVENTION:')
                   for t in _dxf_metinleri(path))

    def test_tablo_sozlesmeyi_yazar(self, hibrit_sonuc):
        tablo = _tablo(hibrit_sonuc)
        assert 'Axis convention' in tablo
        assert '+Z' in tablo['Axis convention']


# ---------------------------------------------------------------------------
# P9B2-05 — tek parça STEP dosyalarında "COMPOUND"
# ---------------------------------------------------------------------------

@_kati_gerekli
class TestP9B205ParcaAdlari:
    """Kod tam bu kusuru düzelttiğini yazıyordu ("SolidWorks/Fusion COMPOUND
    ×5 sorunu"), ama ``label`` ihraçtan SONRA atandığı için düzeltme yalnız
    montaj dosyasında işliyordu.
    """

    def test_hicbir_tek_parca_dosyasi_compound_demez(self, hibrit_sonuc,
                                                     tmp_path):
        files = _quiet(step_export.generate_step_assembly, hibrit_sonuc,
                       out_dir=str(tmp_path))
        kirli = {k: _step_parca_adlari(p)
                 for k, p in files.items()
                 if any(ad == 'COMPOUND' for ad in _step_parca_adlari(p))}
        assert not kirli, (
            f'CAD ağacında hâlâ "COMPOUND" görünen dosyalar: {sorted(kirli)}')

    def test_her_dosya_kendi_adini_tasir(self, hibrit_sonuc, tmp_path):
        files = _quiet(step_export.generate_step_assembly,
                       _panel_plakali(hibrit_sonuc),
                       out_dir=str(tmp_path))
        for anahtar in ('chamber', 'nozzle', 'fuel_grain', 'injector'):
            adlar = ''.join(_step_parca_adlari(files[anahtar]))
            assert anahtar.replace('_', '') in adlar.replace('_', ''), (
                f'{anahtar}.step parça adı {adlar[:60]!r} — kendi adını '
                'taşımıyor')


# ---------------------------------------------------------------------------
# P9B2-10 — lüle açılarının kaynağı
# ---------------------------------------------------------------------------

class TestP9B210AciKaynagi:
    def test_cozucunun_varsayilan_beyani_dusurulmez(self, kati_sonuc):
        """Katı çözücü ``angles_source='conical_default_30_15'`` yayımlıyor."""
        assert (kati_sonuc['nozzle_angles']['angles_source']
                == 'conical_default_30_15')
        tablo = _tablo(kati_sonuc)
        satir = tablo['Nozzle type / half angles']
        assert 'GENERATOR DEFAULT' in satir, (
            f'açı satırı varsayılan künyesini düşürüyor: {satir!r}')
        assert 'conical_default_30_15' in tablo['Nozzle angle source']

    def test_kullanici_girdisi_varsayilan_gibi_etiketlenmez(self, kati_sonuc):
        """Aynı motor "user_input" beyan ederse künye DEĞİŞMELİ.

        Ölçüm çapası: iki koşum bugüne kadar BİREBİR aynı satırı basıyordu.
        """
        import copy
        r = copy.deepcopy(kati_sonuc)
        r['nozzle_angles']['angles_source'] = 'user_input'
        varsayilan = _tablo(kati_sonuc)['Nozzle type / half angles']
        girdi = _tablo(r)['Nozzle type / half angles']
        assert varsayilan != girdi, (
            'varsayılan açı ile kullanıcı girdisi aynı künyeyi basıyor')
        assert 'GENERATOR DEFAULT' not in girdi

    def test_beyan_yoksa_kullanici_girdisi_iddia_edilmez(self, sivi_sonuc):
        """Sıvı çözücü ``angles_source`` yayımlamıyor — fail-closed."""
        assert 'angles_source' not in (sivi_sonuc.get('nozzle_angles') or {})
        assert 'NOT STATED' in _tablo(sivi_sonuc)['Nozzle angle source']

    @_dxf_gerekli
    def test_dxf_aci_kaynagini_yazar(self, kati_sonuc, tmp_path):
        path = _quiet(drawing_generator.generate_dxf, kati_sonuc,
                      out_path=str(tmp_path / 'ang.dxf'))
        satir = [t for t in _dxf_metinleri(path)
                 if t.startswith('NOZZLE HALF ANGLES:')]
        assert satir, 'çizimde açı kaynağı beyanı yok'
        assert 'GENERATOR DEFAULT' in satir[0]


# ---------------------------------------------------------------------------
# P9B2-30 — katı motorda boş "INJECTOR FACE PATTERN" yaprağı
# ---------------------------------------------------------------------------

class TestP9B230OlmayanParcaninYapragi:
    def test_kati_motor_enjektor_iddia_etmez(self, kati_sonuc):
        assert drawing_generator._motor_claims_injector(kati_sonuc) is False

    def test_sivi_ve_hibrit_enjektor_iddia_eder(self, sivi_sonuc,
                                                hibrit_sonuc):
        assert drawing_generator._motor_claims_injector(sivi_sonuc) is True
        assert drawing_generator._motor_claims_injector(hibrit_sonuc) is True

    @_pdf_gerekli
    def test_kati_pdf_enjektor_yapragi_basmaz(self, kati_sonuc, tmp_path):
        """Ölçüldü: yaprak "Injector render failed: ... (injector_design
        missing)" yazıyordu. Bu bir HATA değil, olmayan bir parçadır."""
        import pypdf
        path = _quiet(drawing_generator.generate_drawing_pdf, kati_sonuc,
                      out_path=str(tmp_path / 'k.pdf'))
        sayfalar = [p.extract_text() or ''
                    for p in pypdf.PdfReader(path).pages]
        birlesik = '\n'.join(sayfalar)
        assert 'INJECTOR FACE PATTERN' not in birlesik, (
            'katı motorun çizim paketinde hâlâ enjektör yaprağı var')
        assert 'Injector render failed' not in birlesik

    @_pdf_gerekli
    def test_yaprak_numaralari_tutarli(self, kati_sonuc, tmp_path):
        """Yaprak düşünce "SHEET x/y" da düzelmeli (sayı boşta kalmasın)."""
        import pypdf
        path = _quiet(drawing_generator.generate_drawing_pdf, kati_sonuc,
                      out_path=str(tmp_path / 'k2.pdf'))
        sayfalar = [p.extract_text() or ''
                    for p in pypdf.PdfReader(path).pages]
        toplam = len(sayfalar)
        for index, metin in enumerate(sayfalar):
            assert f'SHEET {index + 1}/{toplam}' in metin, (
                f'{index + 1}. yaprağın anteti yanlış: '
                f'SHEET {index + 1}/{toplam} bekleniyordu')

    @_pdf_gerekli
    def test_enjektoru_olan_motorda_yaprak_durur(self, hibrit_sonuc,
                                                 tmp_path):
        """Aşırı düzeltme bekçisi: hibritte yaprak DÜŞMEMELİ."""
        import pypdf
        path = _quiet(drawing_generator.generate_drawing_pdf, hibrit_sonuc,
                      out_path=str(tmp_path / 'h.pdf'))
        birlesik = '\n'.join(p.extract_text() or ''
                             for p in pypdf.PdfReader(path).pages)
        assert 'INJECTOR FACE PATTERN' in birlesik


# ---------------------------------------------------------------------------
# Sağlıklı yol: onarım hiçbir ölçüyü DEĞİŞTİRMEDİ
# ---------------------------------------------------------------------------

@_kati_gerekli
def test_tek_devreli_motorda_delik_sayisi_degismedi(hibrit_sonuc, tmp_path):
    """Hibrit plakası ONARIM ÖNCESİYLE aynı sayıda delik taşır.

    Çapa ölçümü (docs/scofield/raw/OH/Z5S/p09b): hibrit enjektörünün
    geometri parmak izi onarım öncesi ve sonrası BİT-AYNI (md5 ab1367ec70);
    burada aynı şey ürün düzeyinde tekrar ölçülür.
    """
    files = _quiet(step_export.generate_step_assembly,
                   _panel_plakali(hibrit_sonuc),
                   out_dir=str(tmp_path))
    plan = step_export.resolve_injector_plan(hibrit_sonuc,
                                             motor_type='hybrid')
    assert len(plan['circuits']) == 1
    metin = open(files['injector'], encoding='utf-8', errors='ignore').read()
    assert metin.count('CYLINDRICAL_SURFACE') == 1 + plan['circuits'][0]['n']


@_kati_gerekli
def test_cozulemeyen_plan_hala_reddedilir(tmp_path):
    """Dürüstlük kapısı DURUYOR: boş enjektör bloğundan plaka çıkmaz."""
    payload = {
        'motor_name': 'Z5S_RET', 'length_units': 'm',
        'chamber_diameter': 0.1, 'chamber_length': 0.3,
        'throat_diameter': 0.03, 'exit_diameter': 0.09,
        'nozzle_angles': {'nozzle_type': 'conical'},
        'structural_analysis': {'chamber_structure': {'wall_thickness': 3.0}},
        'injector_design': {},
    }
    with pytest.raises(ValueError, match='injector orifice'):
        _quiet(step_export.generate_step_assembly, payload,
               out_dir=str(tmp_path), motor_type='liquid')
    assert not [p for p in os.listdir(tmp_path) if p.endswith('.step')], (
        'ret sonrası yarım dosya kaldı')
