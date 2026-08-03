"""Faz 6 / G5 — sıvı motor tarafında kalan kalemlerin bekçi testleri.

Tarayıcı denetiminin sıvı sayfasında AÇIK bıraktığı kalemleri KİLİTLER.
Her test kusuru YENİDEN ÜRETİR: düzeltme geri alınırsa test kırılır. Her
bekçinin kusuru gerçekten yakaladığı, düzeltme geri alınarak ÖLÇÜLDÜ
(3 Ağustos 2026) — sonuçlar ilgili sınıfın notunda.

Kapsanan kalemler
-----------------
T13 (manşet)
    ``/liquid`` 3B tank görünümü girdap önleyicinin çap/yüksekliğini
    MİLİMETRE sanıp 2000'e ve 1000'e bölüyordu; oysa çözücü bu iki alanı
    METRE yayımlar. 258,91 mm çaplı düzenek 0,2589 mm çizildi — gözle
    görünmezdi (ölçüldü: mesh3d x uzanımı ±0,00012946 m).
T13 (kök neden)
    Çözücü AYNI sözlükte iki birim yayımlıyordu ('diameter'/'height'
    metre, 'vane_radial_length_mm'/'vane_thickness' milimetre) ve hiçbir
    yerde birim BEYAN etmiyordu; her tüketici tahmin etmek zorundaydı ve
    iki bağımsız tüketici de yanlış tahmin etti.
EK-GÖZLEM-1
    İndirilen CAD paketi yalnız 4 dosya içeriyordu. ``_generate_simple_stl``,
    ``_generate_drawings`` ve ``_generate_manufacturing_specs`` dosyalarını
    diske GERÇEKTEN yazıyor ama hiçbiri paket listesine eklenmediği için
    ZIP'e girmiyordu. Arayüzün başarı mesajı ise 'STL files' ve
    'Engineering drawings' indiğini SÖYLÜYORDU: iddia ile gerçek çelişiyordu.
EK-GÖZLEM-2
    Kütle modeli ile katı model aynı kanadı anlatmıyordu: çözücü radyal
    uzunluğu ``D/2`` alıp kütleyi ona göre hesaplıyor, katı model ise
    ``0,3·D`` kuruyordu — %40 sapma.
T47
    Enjektör paneli İngilizce modda Türkçe metin basıyordu ('6 çift unlike
    doublet', 'Böl. 8-9', '(kavitasyon/flip)' …). Metin istemcide
    üretilmiyor; çözücü dizeleri hazır karışık dilde gönderiyordu.

Yöntem
------
Şablonun JS'i "yazılmış mı" diye TARANMAZ. İlgili fonksiyonlar
``liquid.html``'den kesilip GERÇEK node içinde, GERÇEK çözücü çıktısıyla
çalıştırılır ve ÜRETTİKLERİ ölçülür — böylece bekçi çağrı yerini de kapsar,
yalnız yardımcı fonksiyonu değil. Python tarafı gerçek paketi üretip açar.
"""

import json
import pathlib
import re
import shutil
import subprocess
import zipfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIQUID_HTML = REPO_ROOT / 'hrma' / 'templates' / 'liquid.html'

NODE = shutil.which('node')

#: Ölçüm koşumunun tank ölçüleri (mm) — tarayıcıda ölçülen varsayılan koşum.
OX_TANK_D_MM, OX_TANK_L_MM = 863.0350452502258, 2157.5876131255644
FUEL_TANK_D_MM, FUEL_TANK_L_MM = 383.11, 701.72


# ===========================================================================
# Ortak: şablondan JS kesme (test_faz6_f2a_sivi.py ile aynı sözleşme)
# ===========================================================================

def js_function(name, src=None):
    """``liquid.html``'deki üst düzey bir fonksiyonun kaynağını döndürür.

    Şablonda üst düzey fonksiyonlar 8 boşluk girintili ve kapanış süslü
    ayracı kendi satırında; kesme sınırı budur.
    """
    src = src if src is not None else LIQUID_HTML.read_text(encoding='utf-8')
    start = src.find('\n        function %s(' % name)
    assert start != -1, 'liquid.html içinde %s() yok' % name
    end = src.find('\n        }\n', start)
    assert end != -1, '%s() kapanışı bulunamadı' % name
    return src[start:end + len('\n        }\n')]


#: Şablondan kesilecek fonksiyonlar (bağımlılık sırasıyla).
JS_FUNCS = ['antiVortexMm', 'createCylinderTrace', 'createRingTrace',
            'createTankVisualization']

JS_PRELUDE = r"""
'use strict';
const fs = require('fs');

// --- şablonun beklediği en küçük ortam ---------------------------------
const T = (k, d) => (d !== undefined ? d : k);
const TF = (k, p, d) => String(d !== undefined ? d : k)
    .replace(/\{(\w+)\}/g, (_, n) => (p && p[n] !== undefined ? p[n] : ''));

let YAKALANAN = null;
function liquidPlot(target, data, layout) { YAKALANAN = { data, layout }; }
function createChartDiv() { throw new Error('kap zaten var olmalıydı'); }

const document = {
    getElementById: (id) => ({ id: id, style: {} })
};
const UYARILAR = [];
const console = { warn: (...a) => UYARILAR.push(a.map(String).join(' ')),
                  log: () => {}, error: () => {} };
"""

JS_EPILOGUE = r"""
const inp = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
createTankVisualization(inp.tankData);

const uzanim = (tr) => {
    if (!tr) return null;
    const xs = (tr.x || []).filter(v => typeof v === 'number');
    const zs = (tr.z || []).filter(v => typeof v === 'number');
    return {
        cap_mm: (Math.max(...xs) - Math.min(...xs)) * 1000,
        yukseklik_mm: (Math.max(...zs) - Math.min(...zs)) * 1000
    };
};
const bul = (re) => (YAKALANAN.data || []).find(t => re.test(t.name || ''));
process.stdout.write(JSON.stringify({
    izAdlari: (YAKALANAN.data || []).map(t => t.name),
    antiVortex: uzanim(bul(/Anti-Vortex/)),
    oxTank: uzanim(bul(/Oxidizer Tank/)),
    uyarilar: UYARILAR
}));
"""


def run_tank_js(tmp_path, tank_data):
    """``createTankVisualization``'ı node içinde koşturur, izleri ölçer."""
    src = LIQUID_HTML.read_text(encoding='utf-8')
    parts = [JS_PRELUDE] + [js_function(n, src) for n in JS_FUNCS]
    parts.append(JS_EPILOGUE)
    harness = tmp_path / 'kosum.js'
    harness.write_text('\n'.join(parts), encoding='utf-8')
    inp = tmp_path / 'girdi.json'
    inp.write_text(json.dumps({'tankData': tank_data}), encoding='utf-8')
    proc = subprocess.run([NODE, str(harness), str(inp)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, 'node hatası:\n%s' % proc.stderr[-2000:]
    return json.loads(proc.stdout)


# ===========================================================================
# Ortak veri — çözücünün GERÇEK çıktısı (elle yazılmış sözlük değil)
# ===========================================================================

@pytest.fixture(scope='module')
def solver_internals():
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    eng = LiquidRocketEngine(thrust=10000.0, chamber_pressure=30.0,
                             mixture_ratio=2.3, fuel_type='rp1',
                             oxidizer_type='lox')
    return {
        'oxidizer': eng._design_tank_internals(
            OX_TANK_D_MM / 1000.0, OX_TANK_L_MM / 1000.0, 'oxidizer',
            tank_pressure_pa=3.0e6, mdot=2.5),
        'fuel': eng._design_tank_internals(
            FUEL_TANK_D_MM / 1000.0, FUEL_TANK_L_MM / 1000.0, 'fuel',
            tank_pressure_pa=3.0e6, mdot=1.0),
    }


def _structural():
    return {'material': 'Aluminum 2024-T3', 'material_key': 'al_2024_t3',
            'yield_strength_mpa': 345.0, 'density_kg_m3': 2780.0,
            'pressure_rating': 42.0}


@pytest.fixture(scope='module')
def tank_data(solver_internals):
    """Tarayıcının 3B görünüme ve ``/export_tank_cad`` ucuna verdiği gövde."""
    return {
        'oxidizer_tank': {
            'propellant_type': 'LOX',
            'dimensions': {'diameter': OX_TANK_D_MM, 'length': OX_TANK_L_MM,
                           'wall_thickness': 3.0},
            'structural': _structural(),
            'internal_structures': solver_internals['oxidizer'],
        },
        'fuel_tank': {
            'propellant_type': 'RP1',
            'dimensions': {'diameter': FUEL_TANK_D_MM,
                           'length': FUEL_TANK_L_MM, 'wall_thickness': 3.0},
            'structural': _structural(),
            'internal_structures': solver_internals['fuel'],
        },
    }


# ===========================================================================
# T13 (kök neden) — çözücü birimini artık BEYAN ediyor
# ===========================================================================

class TestT13CozucuBirimBeyani:
    """Kusurun önkoşulu: aynı sözlükte iki birim, hiç beyan yok.

    Beyan alanları silinirse bu sınıf kırılır ve tüketiciler yeniden tahmin
    etmek zorunda kalacağı için o gün bu not okunur.
    """

    @pytest.mark.parametrize('kind, tank_d_mm',
                             [('oxidizer', OX_TANK_D_MM),
                              ('fuel', FUEL_TANK_D_MM)])
    def test_units_field_declares_the_metre_fields(self, solver_internals,
                                                   kind, tank_d_mm):
        av = solver_internals[kind]['anti_vortex_device']
        assert av.get('units') == 'm', (
            "'diameter'/'height' alanlarının birimi BEYAN edilmeli; beyan "
            'yoksa her tüketici tahmin eder (T13 hatasının kök nedeni)')

    @pytest.mark.parametrize('kind, tank_d_mm',
                             [('oxidizer', OX_TANK_D_MM),
                              ('fuel', FUEL_TANK_D_MM)])
    def test_millimetre_fields_agree_with_the_metre_fields(
            self, solver_internals, kind, tank_d_mm):
        """mm alanları metre alanlarının tam 1000 katı olmalı."""
        av = solver_internals[kind]['anti_vortex_device']
        assert av['diameter_mm'] == pytest.approx(av['diameter'] * 1000.0,
                                                  rel=1e-12)
        assert av['height_mm'] == pytest.approx(av['height'] * 1000.0,
                                                rel=1e-12)

    @pytest.mark.parametrize('kind, tank_d_mm',
                             [('oxidizer', OX_TANK_D_MM),
                              ('fuel', FUEL_TANK_D_MM)])
    def test_millimetre_fields_match_the_geometric_proportioning(
            self, solver_internals, kind, tank_d_mm):
        """Beyan edilen mm değeri tank çapının oranı olmalı (0,3 ve 0,1)."""
        from hrma.engines.liquid_rocket_engine import (
            TANK_ANTIVORTEX_D_RATIO, TANK_ANTIVORTEX_H_RATIO)
        av = solver_internals[kind]['anti_vortex_device']
        assert av['diameter_mm'] == pytest.approx(
            tank_d_mm * TANK_ANTIVORTEX_D_RATIO, rel=1e-9)
        assert av['height_mm'] == pytest.approx(
            tank_d_mm * TANK_ANTIVORTEX_H_RATIO, rel=1e-9)


# ===========================================================================
# T13 (manşet) — 3B görünümde düzenek GÖRÜNÜR boyutta
# ===========================================================================

@pytest.mark.skipif(NODE is None, reason='node yok')
class TestT13UcBoyutluGorunum:
    """ASIL BEKÇİ: çağrı yerini de kapsar, yalnız yardımcıyı değil.

    Düzeltme geri alma ölçümü (3 Ağustos 2026): çağrı yerindeki bölenler
    ``/2000`` ve ``/1000``'e döndürüldüğünde ölçülen çap 258,91 mm yerine
    0,2589 mm çıktı ve ``test_device_diameter_is_visible_size`` kırıldı.
    Yani bekçi kusuru GERÇEKTEN yakalıyor.
    """

    @pytest.fixture(scope='class')
    def olcum(self, tmp_path_factory, tank_data):
        return run_tank_js(tmp_path_factory.mktemp('t13'), tank_data)

    def test_device_is_actually_drawn(self, olcum):
        assert olcum['antiVortex'] is not None, (
            'girdap önleyici izi hiç çizilmemiş; birim çözülemedi mi? '
            'uyarılar: %s' % olcum['uyarilar'])

    def test_device_diameter_is_visible_size(self, olcum):
        """Çap tank çapının 0,3 katı olmalı — 1000 kat küçüğü DEĞİL."""
        from hrma.engines.liquid_rocket_engine import TANK_ANTIVORTEX_D_RATIO
        beklenen = OX_TANK_D_MM * TANK_ANTIVORTEX_D_RATIO
        assert olcum['antiVortex']['cap_mm'] == pytest.approx(beklenen,
                                                              rel=1e-6), (
            'düzenek %g mm çizilmiş, beklenen %g mm — çap alanı metre gelirken '
            'mm sanılıp bölünmüş olabilir (T13)'
            % (olcum['antiVortex']['cap_mm'], beklenen))

    def test_device_height_is_visible_size(self, olcum):
        from hrma.engines.liquid_rocket_engine import TANK_ANTIVORTEX_H_RATIO
        beklenen = OX_TANK_D_MM * TANK_ANTIVORTEX_H_RATIO
        assert olcum['antiVortex']['yukseklik_mm'] == pytest.approx(
            beklenen, rel=1e-6)

    def test_device_fits_inside_the_tank(self, olcum):
        """Düzenek tanktan büyük çizilmemeli (ters yöne kaçış bekçisi).

        Yalnız 'çok küçük değil' demek yetmez: ölçek düzeltmesi yanlış yöne
        uygulanırsa (mm alanı 1000 ile ÇARPILIRSA) çap tankı aşardı.
        """
        assert 0 < olcum['antiVortex']['cap_mm'] < olcum['oxTank']['cap_mm']

    def test_tank_itself_is_unchanged(self, olcum):
        """Komşu izler bozulmamalı — tank hâlâ mm/1000 sözleşmesinde."""
        assert olcum['oxTank']['cap_mm'] == pytest.approx(OX_TANK_D_MM,
                                                          rel=1e-6)


@pytest.mark.skipif(NODE is None, reason='node yok')
class TestT13BirimCozulemezse:
    """Birim çözülemiyorsa değer UYDURULMAZ: iz hiç çizilmez."""

    def test_unresolvable_unit_draws_nothing(self, tmp_path, tank_data):
        import copy
        bozuk = copy.deepcopy(tank_data)
        av = bozuk['oxidizer_tank']['internal_structures'][
            'anti_vortex_device']
        # Hem beyanı hem de mm demirini kaldır -> hiçbir ölçüt kalmasın.
        for anahtar in ('units', 'diameter_mm', 'height_mm',
                        'vane_radial_length_mm'):
            av.pop(anahtar, None)
        olcum = run_tank_js(tmp_path, bozuk)
        assert olcum['antiVortex'] is None, (
            'birim çözülemezken düzenek yine de çizilmiş — yanlış ölçekli bir '
            'cisim çizmektense hiç çizmemek gerekir')
        # Konsol metni İngilizce (alt sayfalar tek dilli — test_i18n.py).
        assert any('unit could not be resolved' in u
                   for u in olcum['uyarilar']), (
            'sessizce düşürülmemeli, konsola not düşmeli')

    def test_tank_still_drawn_when_device_is_dropped(self, tmp_path,
                                                     tank_data):
        """Düzenek düşse bile grafiğin geri kalanı çizilmeye devam etmeli."""
        import copy
        bozuk = copy.deepcopy(tank_data)
        av = bozuk['oxidizer_tank']['internal_structures'][
            'anti_vortex_device']
        for anahtar in ('units', 'diameter_mm', 'height_mm',
                        'vane_radial_length_mm'):
            av.pop(anahtar, None)
        olcum = run_tank_js(tmp_path, bozuk)
        assert olcum['oxTank'] is not None
        assert any('Baffle' in (a or '') for a in olcum['izAdlari'])


# ===========================================================================
# EK-GÖZLEM-1 — indirilen paket, mesajın SÖYLEDİĞİ dosyaları içeriyor
# ===========================================================================

@pytest.fixture(scope='module')
def paket_adlari(tank_data):
    """Kullanıcının indirdiği ZIP'in gerçek dosya listesi."""
    from hrma.export.cad_export import cad_generator
    zip_path = cad_generator.generate_tank_cad(tank_data)
    with zipfile.ZipFile(zip_path) as zf:
        return sorted(zf.namelist())


class TestEkGozlem1PaketIcerigi:
    """Arayüzün başarı mesajı ile paketin gerçeği ÇELİŞMEMELİ.

    Düzeltme geri alma ölçümü (3 Ağustos 2026): üç üreticinin dönüş değeri
    ``exported_files``'a eklenmediğinde paket 8 yerine 4 dosyaya düştü ve
    aşağıdaki dört test birden kırıldı.
    """

    #: Mesajın indiğini SÖYLEDİĞİ kalemler -> paketteki karşılıkları.
    #: (liquid.html::exportTankCAD başarı metni)
    @pytest.mark.parametrize('iddia, dosya', [
        ('STL files (3D printing ready)', 'oxidizer_tank.stl'),
        ('STL files (3D printing ready)', 'fuel_tank.stl'),
        ('Engineering drawings (JSON format)', 'engineering_drawings.json'),
        ('Manufacturing specifications',
         'manufacturing_checklist_TEMPLATE.json'),
        ('Geometry definitions', 'oxidizer_tank_geometry.json'),
        ('Geometry definitions', 'fuel_tank_geometry.json'),
        ('STEP files (CATIA/SolidWorks compatible)', 'oxidizer_tank.step'),
        ('STEP files (CATIA/SolidWorks compatible)', 'fuel_tank.step'),
    ])
    def test_claimed_file_is_actually_in_the_package(self, paket_adlari,
                                                     iddia, dosya):
        assert dosya in paket_adlari, (
            'arayüz "%s" indiğini söylüyor ama pakette %s yok; paket: %s'
            % (iddia, dosya, paket_adlari))

    def test_written_files_are_not_silently_dropped(self, paket_adlari):
        """Diske yazılan her dosya pakete girmeli (sessiz düşme bekçisi)."""
        assert len(paket_adlari) >= 8, (
            'paket %d dosya içeriyor; üreticilerin yazdığı dosyalardan '
            'bazıları listeye eklenmemiş olabilir: %s'
            % (len(paket_adlari), paket_adlari))

    def test_stl_files_are_not_empty(self, tank_data, tmp_path):
        """Dosya adı pakette görünüyor diye içi dolu sayılmaz."""
        from hrma.export.cad_export import cad_generator
        zip_path = cad_generator.generate_tank_cad(tank_data)
        with zipfile.ZipFile(zip_path) as zf:
            for ad in ('oxidizer_tank.stl', 'fuel_tank.stl'):
                icerik = zf.read(ad).decode('utf-8', 'replace')
                assert icerik.startswith('solid '), '%s STL değil' % ad
                assert 'facet normal' in icerik, '%s boş üçgen listesi' % ad

    def test_generators_return_the_paths_they_wrote(self, tank_data,
                                                    tmp_path):
        """Kök neden bekçisi: üreticiler yol DÖNDÜRMELİ.

        Dönüş değeri yoksa çağıran paket listesine ekleyemez — hatanın
        mekanizması buydu.
        """
        from hrma.export.cad_export import cad_generator
        d = str(tmp_path)
        stl = cad_generator._generate_simple_stl(tank_data, d)
        ciz = cad_generator._generate_drawings(tank_data, d)
        spec = cad_generator._generate_manufacturing_specs(tank_data, d)
        assert isinstance(stl, list) and len(stl) == 2
        for yol in list(stl) + [ciz, spec]:
            assert yol, 'üretici yol döndürmedi'
            assert pathlib.Path(yol).is_file(), '%s diske yazılmamış' % yol


# ===========================================================================
# EK-GÖZLEM-2 — katı model ile kütle modeli AYNI kanadı anlatıyor
# ===========================================================================

class TestEkGozlem2KanatGeometrisi:
    """Aynı nesnenin iki geometrisi olmamalı.

    Düzeltme geri alma ölçümü (3 Ağustos 2026): radyal uzunluk yeniden
    ``(D/2) - 0,2·D`` olarak türetildiğinde 70,686 mm yerine 42,412 mm
    çıktı (-%40) ve ilk iki test kırıldı.
    """

    @pytest.fixture(scope='class')
    def geom(self, solver_internals):
        from hrma.export.cad_export import (TankCADGenerator,
                                            normalize_anti_vortex_mm)
        av = normalize_anti_vortex_mm(
            solver_internals['oxidizer']['anti_vortex_device'], OX_TANK_D_MM)
        return TankCADGenerator.anti_vortex_vane_geometry(av), av

    def test_solid_vane_length_equals_the_published_field(self, geom):
        g, av = geom
        assert g['vane_length_mm'] == pytest.approx(
            av['vane_radial_length_mm'], rel=1e-12), (
            'katı modelin kanadı, kütlenin dayandığı uzunluktan farklı — '
            'STEP dosyasını ölçen kullanıcı arayüzdeki kütleyi doğrulayamaz')

    def test_solid_vane_length_is_not_the_old_hub_derivation(self, geom):
        """Eski türetme (0,3·D) geri gelirse bu test kırılır."""
        g, av = geom
        eski = 0.3 * av['diameter']
        assert abs(g['vane_length_mm'] - eski) > 1e-6, (
            'kanat uzunluğu yeniden göbek oranından türetilmiş görünüyor '
            '(%g mm), oysa yayımlanan alan %g mm'
            % (eski, av['vane_radial_length_mm']))

    def test_vane_reaches_the_outer_diameter(self, geom):
        """Kanat dış çapta bitmeli: başlangıç + uzunluk = D/2."""
        g, av = geom
        assert (g['vane_start_radius_mm'] + g['vane_length_mm']
                == pytest.approx(av['diameter'] / 2.0, rel=1e-12))

    def test_hub_is_not_modelled_because_the_mass_model_has_none(self, geom):
        """Kütle modelinde olmayan bir kütle katıya konmamalı."""
        g, _ = geom
        assert g['hub_modelled'] is False

    def test_solid_matches_the_published_mass(self, solver_internals):
        """Sayısal uzlaşma: katının hacminden çıkan kütle == yayımlanan kütle.

        Çözücü kütlesi ``N x h x (D/2) x t x rho``. Katı da aynı N plakadan
        kuruluyorsa hacim çarpımı birebir tutmalı.
        """
        from hrma.export.cad_export import (TankCADGenerator,
                                            normalize_anti_vortex_mm)
        internals = solver_internals['oxidizer']
        av = normalize_anti_vortex_mm(internals['anti_vortex_device'],
                                      OX_TANK_D_MM)
        g = TankCADGenerator.anti_vortex_vane_geometry(av)
        # mm -> m
        hacim_m3 = (g['vane_count'] * g['vane_height_mm']
                    * g['vane_length_mm'] * g['vane_width_mm']) * 1e-9
        from hrma.engines.liquid_rocket_engine import TANK_INTERNALS_MATERIAL
        from hrma.data.materials_db import get_material_safe
        rho = float(get_material_safe(TANK_INTERNALS_MATERIAL)[0]['density'])
        yayimlanan = internals['mass_breakdown']['anti_vortex']
        assert hacim_m3 * rho == pytest.approx(yayimlanan, rel=1e-9), (
            'katı modelin kütlesi yayımlanan kütleden farklı')


# ===========================================================================
# T47 — enjektör çıktısı dil-karışık DEĞİL
# ===========================================================================

#: Türkçeye özgü harfler. Kaynak künyelerindeki 'N₂O' gibi simgeler dokunulmaz.
TR_HARFLER = re.compile(r'[çğıİöşüÇĞÖŞÜ]')

#: Türkçe sözcükler (aksansız yazılmış olsalar bile yakalanır).
TR_SOZCUKLER = re.compile(
    r'\b(adet|cift|çift|delikli|baski|baskı|Bol\.|Böl\.|pratigi|pratiği|'
    r'kavitasyon|karisim|karışım|kriteri|teorisi|izolasyonu|serbest|riski|'
    r'eksenel|paralel|jetler|radyal|delik|anulus|anülüs|merkezli|basinc|'
    r'basınç|Koaksiyel|ve ark|ayni|aynı|akiskan|akışkan|ciftleri|çiftleri|'
    r'izentropik|orifis|kararlilik|kararlılık|koaksiyel|yanma|calismalari|'
    r'çalışmaları|yakit|yakıt|dis|dış|orta)\b', re.I)


def _tr_kalintisi(metin):
    return bool(TR_HARFLER.search(metin) or TR_SOZCUKLER.search(metin))


def _spec(inj_type):
    ortak = {'motor_type': 'liquid', 'injector_type': inj_type,
             'mdot_ox': 2.97, 'mdot_fuel': 1.29, 'Pc_bar': 30.0,
             'T_c_K': 3400.0, 'mw_gas': 22.0,
             'rho_ox': 1141.0, 'rho_fuel': 810.0,
             'oxidizer_type': 'lox', 'fuel_type': 'rp1'}
    if inj_type == 'gas_gas_coaxial':
        ortak['gas_ox'] = {'T0_K': 700.0, 'P0_bar': 45.0, 'gamma': 1.4,
                           'MW': 32.0}
        ortak['gas_fuel'] = {'T0_K': 300.0, 'P0_bar': 45.0, 'gamma': 1.4,
                             'MW': 2.0}
    return ortak


INJ_TIPLERI = ['showerhead', 'impinging_doublet', 'impinging_triplet',
               'like_impinging', 'pintle', 'swirl', 'coax_swirl',
               'gas_gas_coaxial']


class TestT47EnjektorDili:
    """Panel bu metinleri DİLDEN BAĞIMSIZ basıyor; karışık dil olamaz.

    Düzeltme geri alma ölçümü (3 Ağustos 2026): ``desc`` dizeleri ve
    ``REFERENCES`` kalemleri eski Türkçe hâllerine döndürüldüğünde 8 tipin
    tamamında ``test_pattern_description_is_single_language`` ve
    ``test_reference_entries_are_single_language`` kırıldı (ölçülen kalıntı:
    desc'te 8, künyelerde 7 kalem).
    """

    @pytest.fixture(scope='class')
    def tasarimlar(self):
        from hrma.engines.injector_design import design_injector
        out = {}
        for tip in INJ_TIPLERI:
            d = design_injector(_spec(tip))
            assert d.get('status') == 'success', (
                '%s tasarımı üretilemedi: %s' % (tip, d.get('error')))
            out[tip] = d
        return out

    @pytest.mark.parametrize('tip', INJ_TIPLERI)
    def test_pattern_description_is_single_language(self, tasarimlar, tip):
        desc = tasarimlar[tip]['pattern']['description']
        assert desc, '%s: desen açıklaması boş' % tip
        assert not _tr_kalintisi(desc), (
            '%s: panel bu metni İngilizce modda da basıyor, Türkçe kalıntı '
            'var -> %r' % (tip, desc))

    @pytest.mark.parametrize('tip', INJ_TIPLERI)
    def test_legacy_key_still_present_for_the_panel(self, tasarimlar, tip):
        """``injector_panel.js:348`` hâlâ ``description_tr`` okuyor.

        Anahtar tüketici geçmeden kaldırılırsa panel açıklamayı hiç
        göstermez; bekçi o sessiz kaybı yakalar.
        """
        pat = tasarimlar[tip]['pattern']
        assert pat.get('description_tr') == pat.get('description')

    @pytest.mark.parametrize('tip', INJ_TIPLERI)
    def test_reference_entries_are_single_language(self, tasarimlar, tip):
        refs = tasarimlar[tip].get('references') or []
        assert refs, '%s: kaynak listesi boş' % tip
        kirli = [r for r in refs if _tr_kalintisi(r)]
        assert not kirli, (
            '%s: kaynak künyelerinde Türkçe kalıntı -> %s' % (tip, kirli))

    def test_reference_lists_themselves_are_clean(self):
        """Modül düzeyindeki listeler (tek doğruluk kaynağı) temiz olmalı."""
        from hrma.engines.injector_design import (REFERENCES,
                                                  GAS_GAS_REFERENCES)
        for ad, liste in (('REFERENCES', REFERENCES),
                          ('GAS_GAS_REFERENCES', GAS_GAS_REFERENCES)):
            kirli = [r for r in liste if _tr_kalintisi(r)]
            assert not kirli, '%s içinde Türkçe kalıntı -> %s' % (ad, kirli)

    def test_citation_bodies_are_preserved(self):
        """Çeviri künyeyi BOZMAMALI: yazar/kaynak adları yerinde kalmalı."""
        from hrma.engines.injector_design import REFERENCES
        birlesik = ' | '.join(REFERENCES)
        for parca in ('NASA SP-8089', 'Sutton & Biblarz', 'Huzel & Huang',
                      'Lefebvre & McDonell', 'AIAA 2007-5702',
                      'ASME J. Fluids Eng. 1976', 'JPL 20-195',
                      'Elkotb, PECS 1982', 'Giffen & Muraszew',
                      'NASA NTRS 20190001326'):
            assert parca in birlesik, 'künye kaybolmuş: %s' % parca
