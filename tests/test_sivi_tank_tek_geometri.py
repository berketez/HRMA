"""A11 — sıvı motor tank TEK-GEOMETRİ bekçileri (2.7 kapı ölçütü #4).

Bu deponun en pahalı kusur sınıfı: "aynı kavram, aynı yanıtta birden fazla
sayı". 2026-08-15 teşhisi (25 kN LOX/RP-1 örneği, POST /calculate_liquid)
tank geometrisinin durumunu ÖLÇTÜ:

TEŞHİS TABLOSU (düzeltme öncesi):

  Kavram                | Yol 1                        | Yol 2                          | Fark
  ----------------------|------------------------------|--------------------------------|------
  Tank hacmi (oks/yakıt)| feed_system 2.0383/1.2483 m³ | tank kartı 2038.26/1248.34 L   | %0 ✓
  Tank basıncı (turbo)  | besleme zinciri 3.0 bar      | tank kartı 300000 Pa LİTERALİ  | %0*
  Tank basıncı (p-fed)  | besleme kartı 105 bar (girdi)| tank kartı (P_c+5)x1.2 = 90 bar| %16.7
  Toplam itici kütlesi  | design_summary 2756.50 kg    | tank kartı 3169.97 kg          | %15**
  Cidar (turbo)         | dimensions 3.0 mm (beyansız) | basınçtan 1.087 mm (görünmez)  | 2.8x**
  Autogenous basıncı    | _tank kartı zinciri          | 3.0e5 Pa LİTERALİ              | %0*

  *  bugün aynı sayı; sabit değişse SESSİZCE ayrışırlardı (tanım noktası ayrı).
  ** aynı adla değil ama beyansız: rezerv payı / imalat tabanı hükmü çıktıda
     görünmüyordu.

Tek kaynak seçimi: tank hacmi/çap/boy zaten _size_tank + TANK_LD_RATIO
üstünden tekti; basınç için merkez, NPSH tek-kaynak reformunun (B5, 5bb6ed0)
kutsadığı besleme zinciri mantığıdır — artık _tank_pressure_bar() adlı TEK
fonksiyondadır ve besleme kartı, pompa zinciri, çevrim çözücüsü, ayrıntılı
tank kartı ile autogenous bloğu hepsi oradan okur. Gerekçe: basınç beslemeli
çevrimde tankı BASINÇLANDIRAN şey kullanıcının feed_pressure girdisidir;
(P_c+5)x1.2 türetilmiş tahmini kullanıcının gerçek girdisini yok sayıyordu
(gereksinim kavramı zaten ayrı adla yayımlanıyor:
injection_system.required_*_tank_pressure).

MUTASYON DÜŞÜNCELERİ (bu dosya neyi kilitliyor):
  * _design_propellant_tanks'a `tank_pressure = 300000` literal'i veya
    `(P_c+5e5)*1.2` tahmini geri gelirse: basınç-beslemeli fikstürde kart
    90 bar der, besleme kartı 105 bar der -> test_basinc_beslemeli_* düşer;
    kaynak taraması test_kaynak_kodda_literal_yok da düşer.
  * autogenous'a `3.0e5` literal'i geri gelirse: kaynak taraması düşer.
  * Tank kütlesi rezervi beyansız kalırsa (mass_basis/mass_nominal silinirse)
    test_kutle_rezervi_beyanli düşer; 2756 vs 3170 çelişkisi geri gelir.
  * Cidar imalat tabanı hükmü sessizleşirse (governed_by/psized silinirse)
    test_cidar_beyani düşer.
  * Herhangi bir blok kendi tank hacmi/çapı/boyunu AYRI hesaplamaya
    başlarsa yapraklar tek kaynak kümesinden sapar -> yapısal tarama düşer.
"""

import contextlib
import inspect
import io

import numpy as np
import pytest

import hrma.analysis.pressurant_sizing as pressurant_sizing
from hrma.engines.liquid_rocket_engine import (
    LiquidRocketEngine,
    PUMP_TANK_PRESSURE_DEFAULT_BAR,
    TANK_LD_RATIO,
    TANK_PROPELLANT_RESERVE_FACTOR,
    TANK_ULLAGE_FRACTION,
    TANK_WALL_MIN_THICKNESS_M,
)

# Çevrimdışı itici verisi — TEK tanım noktası (CLAUDE.md kural 11):
# test_liquid_real_inputs ile aynı sözlük, kopyalanmaz.
from tests.test_liquid_real_inputs import PROPELLANT_DATA  # noqa: E402

#: 25 kN örneğinin oranları (examples/Example Liquid LOX-RP1 25kN.hrma).
TABAN = dict(thrust=25000, chamber_pressure=70, mixture_ratio=2.3,
             fuel_type='rp1', oxidizer_type='lox',
             propellant_data=PROPELLANT_DATA)


def _cift(overrides=None, **kwargs):
    kw = dict(TABAN)
    kw.update(kwargs)
    with contextlib.redirect_stdout(io.StringIO()):
        engine = LiquidRocketEngine(overrides=dict(overrides or {}), **kw)
        return engine, engine.calculate_performance()


# Çözüm pahalıdır; senaryo başına BİR koşu, modül boyunca paylaşılır.
@pytest.fixture(scope='module')
def turbo():
    """Turbopompalı (gaz jeneratörü) koşu — teşhisin taban senaryosu."""
    return _cift(overrides={'engine_cycle': 'gas_generator',
                            'feed_pressure': 105})


@pytest.fixture(scope='module')
def basincli():
    """Basınç beslemeli koşu — teşhiste %16.7'lik uyuşmazlığın senaryosu."""
    return _cift(overrides={'engine_cycle': 'pressure_fed',
                            'feed_pressure': 105})


def _tank(sonuc, ad):
    return sonuc['propellant_tanks'][ad]


def _yaprak_gez(node, yol=()):
    """Yanıt ağacındaki (yol, değer) sayısal yapraklarını üretir."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _yaprak_gez(v, yol + (str(k),))
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            yield from _yaprak_gez(v, yol + (f'[{i}]',))
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        yield yol, float(node)


def _ebeveyn(sonuc, yol):
    """Yaprağın ebeveyn sözlüğünü döndürür."""
    node = sonuc
    for adim in yol[:-1]:
        if adim.startswith('['):
            node = node[int(adim[1:-1])]
        else:
            node = node[adim]
    return node


def _beyanli(blok):
    """Blok kendi büyüklüğünün kaynağını/temelini beyan ediyor mu?

    Tek-kaynak sözleşmesinin ikinci kolu: tek kaynaktan OKUYAMAYAN bir
    büyüklük ancak kendi 'basis/source' beyanıyla (veya 'INDEPENDENT
    ESTIMATES' deseniyle) yaşayabilir.
    """
    if not isinstance(blok, dict):
        return False
    for k, v in blok.items():
        if ('basis' in k or 'source' in k) and isinstance(v, str) and v:
            return True
        if isinstance(v, str) and 'INDEPENDENT' in v.upper():
            return True
    return False


# ===========================================================================
# 1 — Yapısal tarama: her tank hacim/çap/boy yaprağı ya tek kaynak
#     değerine eşit ya beyan taşıyor (İSTİSNASIZ)
# ===========================================================================

class TestYapisalTarama:

    YAPRAK_ADLARI = ('volume', 'diameter', 'length', 'total_volume',
                     'tank_volume', 'tank_diameter', 'tank_length')

    @pytest.mark.parametrize('senaryo', ['turbo', 'basincli'])
    def test_tank_geometri_yapraklari_tek_kaynak(self, senaryo, request):
        """Yanıt ağacı gezilir; 'tank' bağlamındaki her hacim/çap/boy
        yaprağı tek kaynak kümesiyle (m³/L ve m/mm birim köprüleriyle)
        eşleşmeli, eşleşmeyen yaprak kendi basis/source beyanını taşımalı.

        Mutasyon: herhangi bir blok tank hacmini/çapını kendi başına yeniden
        hesaplamaya dönerse (eski 1.20-çarpanlı besleme hacmi gibi) yaprak
        kümeden sapar ve yol adıyla burada yakalanır.
        """
        _, sonuc = request.getfixturevalue(senaryo)

        # Tek kaynak kümesi (kanonik birimler: L ve mm) tank kartından.
        ox = _tank(sonuc, 'oxidizer_tank')['dimensions']
        fuel = _tank(sonuc, 'fuel_tank')['dimensions']
        kume = {
            ox['volume'], fuel['volume'], ox['volume'] + fuel['volume'],
            ox['diameter'], fuel['diameter'],
            ox['length'], fuel['length'],
        }

        def eslesir(deger):
            for s in kume:
                for olcek in (1.0, 1000.0):  # m³->L, m->mm köprüsü
                    if s != 0 and abs(deger * olcek - s) <= 1e-9 * abs(s):
                        return True
            return False

        yakalanan, sapan = [], []
        for yol, deger in _yaprak_gez(sonuc):
            if yol[-1] not in self.YAPRAK_ADLARI:
                continue
            if not any('tank' in adim.lower() for adim in yol):
                continue
            yakalanan.append(yol)
            if eslesir(deger):
                continue
            if _beyanli(_ebeveyn(sonuc, yol)):
                continue
            sapan.append(('.'.join(yol), deger))

        assert not sapan, (
            'Tek kaynak kümesine uymayan ve beyansız tank geometri '
            f'yaprakları: {sapan}')
        # Tarama boş dönerse bekçi kör demektir: bilinen çekirdek yaprak
        # sayısı (2 besleme hacmi + 2x3 boyut + toplam) altına inmemeli.
        assert len(yakalanan) >= 9, (
            f'Tarama yalnız {len(yakalanan)} yaprak yakaladı — yürüyüş '
            'köreldi (şema mı değişti?)')

    @pytest.mark.parametrize('senaryo', ['turbo', 'basincli'])
    def test_hacim_zinciri_beyan_edilen_modelden(self, senaryo, request):
        """V = m_nominal x rezerv / rho / (1-ullage); D = (4V/(pi L/D))^(1/3);
        L = D x L/D — kartın sayıları kartın BEYAN ETTİĞİ modeli yeniden
        üretmeli (sayı ile beyanın ayrışması bu sınıfın öteki yüzüdür)."""
        _, sonuc = request.getfixturevalue(senaryo)
        for ad in ('oxidizer_tank', 'fuel_tank'):
            tank = _tank(sonuc, ad)
            dims, pd = tank['dimensions'], tank['propellant_data']
            v_sivi = (pd['mass_nominal'] * TANK_PROPELLANT_RESERVE_FACTOR
                      / pd['density'])                       # m³
            v_tank = v_sivi / (1.0 - TANK_ULLAGE_FRACTION)   # m³
            assert dims['volume'] == pytest.approx(v_tank * 1000, rel=1e-9)
            assert pd['volume_required'] == pytest.approx(
                v_sivi * 1000, rel=1e-9)
            assert pd['ullage_volume'] == pytest.approx(
                (v_tank - v_sivi) * 1000, rel=1e-9)
            cap = (4 * v_tank / (np.pi * TANK_LD_RATIO)) ** (1 / 3)  # m
            assert dims['diameter'] == pytest.approx(cap * 1000, rel=1e-9)
            assert dims['length'] == pytest.approx(
                cap * TANK_LD_RATIO * 1000, rel=1e-9)
            # Besleme kartı aynı hacmi m³ cinsinden gösterir.
            besleme = sonuc['feed_system']['tanks'][
                'oxidizer_tank' if ad == 'oxidizer_tank' else 'fuel_tank']
            assert besleme['volume'] == pytest.approx(v_tank, rel=1e-9)


# ===========================================================================
# 2 — Tank basıncı: NPSH zinciriyle TEK kaynak
# ===========================================================================

class TestTankBasinciTekKaynak:

    def test_turbopompali_zincir_tek_deger(self, turbo):
        """Turbopompalı koşuda besleme kartı, ayrıntılı besleme, pompa
        NPSH girdisi, tank kartı ve basınçlı kap MEOP'u aynı sayı: hepsi
        PUMP_TANK_PRESSURE_DEFAULT_BAR.

        Mutasyon: _design_propellant_tanks'a `300000` Pa literal'i geri
        gelir ve sabit değişirse kart ile zincir ayrışır -> bu test düşer.
        """
        _, sonuc = turbo
        beklenen = PUMP_TANK_PRESSURE_DEFAULT_BAR
        assert sonuc['feed_system']['tank_pressure_bar'] == beklenen
        assert sonuc['detailed_feed_system']['tank_pressure_bar'] == beklenen
        for pompa in ('oxidizer_pump', 'fuel_pump'):
            tps = sonuc['detailed_feed_system']['turbopump_sizing'][pompa]
            # Çevrimdışı koşuda modül 'not_modelled' dönebilir; sayı
            # taşıyorsa AYNI sayı olmak zorunda (NPSH tek-kaynak köprüsü).
            if 'tank_pressure_bar' in tps:
                assert tps['tank_pressure_bar'] == pytest.approx(beklenen)
        for ad in ('oxidizer_tank', 'fuel_tank'):
            tank = _tank(sonuc, ad)
            assert tank['structural']['pressure_rating'] == pytest.approx(
                beklenen, rel=1e-12)
            assert tank['pressure_vessel']['inputs']['meop_bar'] == \
                pytest.approx(beklenen, rel=1e-12)

    def test_basinc_beslemeli_kart_kullanici_girdisini_gorur(self, basincli):
        """Basınç beslemeli çevrimde tank kartı kullanıcının feed_pressure
        girdisini (105 bar) görmeli — besleme kartıyla AYNI sayı.

        Mutasyon (teşhisin %16.7 uyuşmazlığı): eski `(P_c+5 bar) x 1.2`
        tahmini geri gelirse bu fikstürde kart 90.0 bar der ve düşer;
        cidar/kütle/MEOP/vana ayarı da o yanlış sayıdan türerdi.
        """
        _, sonuc = basincli
        assert sonuc['feed_system']['tank_pressure_bar'] == 105.0
        for ad in ('oxidizer_tank', 'fuel_tank'):
            tank = _tank(sonuc, ad)
            assert tank['structural']['pressure_rating'] == pytest.approx(
                105.0, rel=1e-12), (
                f'{ad}: kart besleme kartından ayrıştı — eski türetilmiş '
                'tahmin (90 bar) geri mi geldi?')
            assert tank['pressure_vessel']['inputs']['meop_bar'] == \
                pytest.approx(105.0, rel=1e-12)

    @pytest.mark.parametrize('senaryo', ['turbo', 'basincli'])
    def test_vana_ayari_tek_kaynaktan(self, senaryo, request):
        """Emniyet vanası ayarı = 1.1 x TEK kaynak basıncı (bloklar arası)."""
        _, sonuc = request.getfixturevalue(senaryo)
        kaynak = sonuc['feed_system']['tank_pressure_bar']
        for ad in ('oxidizer_tank', 'fuel_tank'):
            vana = _tank(sonuc, ad)['internal_structures'][
                'instrumentation']['relief_valve']
            assert vana['set_pressure'] == pytest.approx(
                1.1 * kaynak, rel=1e-9)

    @pytest.mark.parametrize('senaryo,anahtar', [
        ('turbo', 'PUMP_TANK_PRESSURE_DEFAULT_BAR'),
        ('basincli', 'user feed pressure'),
    ])
    def test_basinc_kaynak_beyani(self, senaryo, anahtar, request):
        """Kartta basıncın KAYNAĞI yazmalı (beyansız sayı yasak)."""
        _, sonuc = request.getfixturevalue(senaryo)
        assert anahtar in sonuc['feed_system']['tank_pressure_source']
        for ad in ('oxidizer_tank', 'fuel_tank'):
            assert anahtar in _tank(sonuc, ad)['structural'][
                'pressure_rating_source']

    def test_kaynak_kodda_literal_yok(self):
        """Kusuru kilitleyen bekçi: tank kartı ve autogenous bloğu tank
        basıncını _tank_pressure_bar'dan OKUMALI; eski literaller
        (300000 / 3.0e5 / x1.2 tahmini) kaynak koda geri dönemez."""
        kart = inspect.getsource(
            LiquidRocketEngine._design_propellant_tanks)
        assert '_tank_pressure_bar' in kart
        assert '300000' not in kart, (
            'tank kartına 300000 Pa satır içi literali geri geldi')
        assert '* 1.2' not in kart, (
            'tank kartına (P_c+5)x1.2 türetilmiş tahmini geri geldi')
        auto = inspect.getsource(
            LiquidRocketEngine._autogenous_pressurization_summary)
        assert '_tank_pressure_bar' in auto
        assert '3.0e5' not in auto, (
            'autogenous bloğuna 3.0e5 Pa literali geri geldi')


# ===========================================================================
# 3 — Kütle: rezerv payı beyanlı, nominal ayrı adla
# ===========================================================================

class TestKutleBeyani:

    def test_kutle_rezervi_beyanli(self, turbo):
        """Tank kütlesi = nominal x 1.15 ve bunu KENDİ söylüyor.

        Mutasyon (teşhisin %15 uyuşmazlığı): design_summary 2756.5 kg
        derken tank kartı beyansız 3169.97 kg diyordu — mass_nominal /
        mass_basis silinirse veya oran rezerv sabitinden saparsa düşer.
        """
        _, sonuc = turbo
        for ad in ('oxidizer_tank', 'fuel_tank'):
            pd = _tank(sonuc, ad)['propellant_data']
            assert pd['mass'] == pytest.approx(
                pd['mass_nominal'] * TANK_PROPELLANT_RESERVE_FACTOR,
                rel=1e-12)
            assert f'{TANK_PROPELLANT_RESERVE_FACTOR:g}' in pd['mass_basis']
            assert 'separate names' in pd['mass_basis']

    def test_toplam_kutle_design_summary_ile_baglanir(self, turbo):
        """system_summary nominali design_summary'nin sayısının TA KENDİSİ;
        rezervli toplam da nominalin 1.15 katı — iki blok tek modelde."""
        _, sonuc = turbo
        ss = sonuc['propellant_tanks']['system_summary']
        ds = sonuc['design_summary']['masses']
        assert ss['total_propellant_mass_nominal'] == pytest.approx(
            ds['propellant_mass_kg'], rel=1e-9)
        assert ss['total_propellant_mass'] == pytest.approx(
            ss['total_propellant_mass_nominal']
            * TANK_PROPELLANT_RESERVE_FACTOR, rel=1e-12)
        assert 'reserve' in ss['total_propellant_mass_basis']
        assert 'reserve' in ds['propellant_mass_basis']


# ===========================================================================
# 4 — Ullaj / L-D / cidar beyan alanları
# ===========================================================================

class TestBeyanAlanlari:

    @pytest.mark.parametrize('senaryo', ['turbo', 'basincli'])
    def test_ullaj_ve_ld_beyani(self, senaryo, request):
        _, sonuc = request.getfixturevalue(senaryo)
        ss = sonuc['propellant_tanks']['system_summary']
        assert ss['ullage_fraction'] == pytest.approx(
            TANK_ULLAGE_FRACTION * 100)
        assert 'ullage' in ss['ullage_fraction_basis']
        for ad in ('oxidizer_tank', 'fuel_tank'):
            tank = _tank(sonuc, ad)
            assert tank['dimensions']['ld_ratio'] == TANK_LD_RATIO
            assert 'design choice' in tank['dimensions']['ld_ratio_basis']
            assert 'ullage' in tank['propellant_data'][
                'ullage_fraction_basis']

    @pytest.mark.parametrize('senaryo,beklenen_hukum', [
        ('turbo', 'minimum manufacturing gauge'),
        ('basincli', 'pressure sizing'),
    ])
    def test_cidar_beyani(self, senaryo, beklenen_hukum, request):
        """Cidar = max(basınç boyutlandırması, 3 mm taban) ve HÜKÜM beyanlı.

        Ölçülen: turbopompada basınçtan 1.087 mm çıkar, 3 mm taban yönetir;
        basınç beslemelide (105 bar) 38.06 mm çıkar, basınç yönetir. Eski
        çıktı 3.0 mm'yi hangi hükmün ürettiğini söylemiyordu; basınçtan
        gelen değer artık AYRI adla yayımlanır (bir kavram = bir ad).
        """
        _, sonuc = request.getfixturevalue(senaryo)
        for ad in ('oxidizer_tank', 'fuel_tank'):
            dims = _tank(sonuc, ad)['dimensions']
            psized = dims['wall_thickness_pressure_sized_mm']
            assert dims['wall_thickness'] == pytest.approx(
                max(psized, TANK_WALL_MIN_THICKNESS_M * 1000), rel=1e-12)
            assert dims['wall_thickness_governed_by'] == beklenen_hukum
            assert 'minimum manufacturing gauge' in \
                dims['wall_thickness_basis']
            # Basınçlı kap analizi de aynı cidarı kullanmalı (A3 köprüsü).
            vessel = _tank(sonuc, ad)['pressure_vessel']
            assert vessel['inputs']['wall_thickness_mm'] == pytest.approx(
                dims['wall_thickness'], rel=1e-9)


# ===========================================================================
# 5 — Autogenous/pressurant hacmi == geometri hacmi
# ===========================================================================

class TestPressurantHacmi:

    def test_autogenous_hacim_ve_basinc_geometriyle_ayni(self, monkeypatch):
        """pressurant_sizing'e giden boşalan hacimler _size_tank'ın sıvı
        hacimlerinin TA KENDİSİ, basınç da _tank_pressure_bar'ın değeri
        olmalı (metan/LOX — autogenous'un modellendiği konfigürasyon).

        Mutasyon: autogenous bloğu kendi hacmini/basıncını türetmeye
        dönerse (eski 3.0e5 literali gibi) yakalanan çağrı argümanları
        geometriden sapar ve düşer.
        """
        cagrilar = []
        gercek = pressurant_sizing.autogenous_pressurant

        def yakala(hacim, basinc, itici, **kw):
            cagrilar.append((float(hacim), float(basinc), itici))
            return gercek(hacim, basinc, itici, **kw)

        monkeypatch.setattr(pressurant_sizing, 'autogenous_pressurant',
                            yakala)
        with contextlib.redirect_stdout(io.StringIO()):
            motor = LiquidRocketEngine(
                thrust=25000, chamber_pressure=70, mixture_ratio=3.0,
                fuel_type='methane', oxidizer_type='lox',
                propellant_data=PROPELLANT_DATA)
            blok = motor._autogenous_pressurization_summary()
        assert blok['status'] == 'ok'
        assert len(cagrilar) == 2

        yanma, _ = motor._burn_time()
        _, ox_sivi, _, _ = motor._size_tank(
            motor.mdot_ox * yanma, 'oxidizer')
        _, yakit_sivi, _, _ = motor._size_tank(
            motor.mdot_fuel * yanma, 'fuel')
        beklenen_basinc = motor._tank_pressure_bar()[0] * 1e5  # Pa
        (v_ox, p_ox, g_ox), (v_f, p_f, g_f) = cagrilar
        assert g_ox == 'oxygen' and g_f == 'methane'
        assert v_ox == pytest.approx(ox_sivi, rel=1e-12)
        assert v_f == pytest.approx(yakit_sivi, rel=1e-12)
        assert p_ox == pytest.approx(beklenen_basinc, rel=1e-12)
        assert p_f == pytest.approx(beklenen_basinc, rel=1e-12)
