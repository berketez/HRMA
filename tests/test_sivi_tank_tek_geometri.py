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

ÖH FAZ B (27 Ağustos 2026) — TAŞINAN BEKÇİLER, Z5S/PK1'de KAPANDI
------------------------------------------------------------------
Kampanya bu dosyanın üç düğümünü "kusuru koruyan bekçi" saydı: ölçtükleri
şey TEK-DEĞERLİLİK (aynı değişkeni okuyan beş yer aynı sayıyı veriyor) iken
kilitlenmesi gereken şey TEK-KAYNAKLILIK ve gereksinimle KARŞILAŞTIRMAdır.
Taşınan iddialar bir gün ``xfail(strict=True)`` + defter kimliğiyle durdu;
Z5S/PK1 onarım dalgası (aynı gün) dördünü de yeşile döndürdü ve imler
söküldü. Kilitlenen sözleşmeler:

  * ``P3B2-01`` — gereken tank basıncı soğutma ceketi ΔP'sini GÖRÜR
    (``calculate_injector_design`` soğutma çözümünü argümanla alır).
  * ``P3B3-13`` — çevrim çözücüsü tank basıncını A11'in tek tanım
    noktasından (``_tank_pressure_bar``) okur, sabitten değil.
  * ``P3B3-11`` — basınçlı kap EMNİYET VANASI AYARINDA nitelendirilir
    (``meop_bar = operating_pressure_bar x RELIEF_VALVE_SET_PRESSURE_FACTOR``,
    ASME VIII Div.1 UG-134 mantığı); işletme basıncı ayrı adla
    (``operating_pressure_bar``) yanında durur ve tek kaynağı O taşır.
    Bu yüzden bu dosyanın iki tek-kaynak bekçisi (``:test_turbopompali_
    zincir_tek_deger``, ``:test_basinc_beslemeli_kart_kullanici_girdisini_
    gorur``) MEOP'u artık çarpanla karşılaştırır — tek-kaynak iddiası
    ``operating_pressure_bar`` satırında yaşamaya devam eder.
  * ``P3B1-14`` — A3 kapanışında yasaklanan yer tutucular (c* = 1650 m/s,
    Isp = 300 s) çalışan kodda YOK; ``test_kaynak_kodda_literal_yok``
    deseni onlara da uygulandı (fail-closed karşılığı kondu).
"""

import ast
import contextlib
import inspect
import io
import pathlib

import numpy as np
import pytest

import hrma.analysis.pressurant_sizing as pressurant_sizing
from hrma.engines.liquid_rocket_engine import (
    BURN_TIME_DEFAULT_S,
    LiquidRocketEngine,
    PUMP_TANK_PRESSURE_DEFAULT_BAR,
    RELIEF_VALVE_SET_PRESSURE_FACTOR,
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


#: ÖH D36 / LU-1 (ÇEVRİLEN BEKÇİ): motor yanma süresini ARTIK VARSAYMAZ;
#: süre yoksa tank kartı ``not_modelled`` döner ve besleme hacimleri None
#: olur. Bu dosyanın iddiaları (tek geometri, tek basınç, beyanlar) SÜRESİ
#: VERİLMİŞ bir tasarım üzerinedir; eski sessiz varsayımla aynı sayılar
#: çıksın diye süre açıkça, motorun kendi sabitinden verilir (sayı burada
#: yazılmaz). Süre yokken kartın fail-closed hâli tests/test_d36_sivi_a1.py'de.
SURE = {'max_burn_duration': BURN_TIME_DEFAULT_S}


def _cift(overrides=None, **kwargs):
    kw = dict(TABAN)
    kw.update(kwargs)
    ov = dict(SURE)
    ov.update(overrides or {})
    with contextlib.redirect_stdout(io.StringIO()):
        engine = LiquidRocketEngine(overrides=ov, **kw)
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


@pytest.fixture(scope='module')
def turbo_ablatif():
    """``turbo``nun ABLATİF kardeşi: soğutma ceketi ΔP'si SIFIRDIR.

    P3B2-01'in ölçüm düzeneği. İki koşu yalnız soğutma tipinde ayrılır
    (aynı itki, aynı Pc, aynı çevrim, aynı besleme basıncı), dolayısıyla
    gereken YAKIT tank basıncındaki fark ceket ΔP farkının ta kendisi olmak
    zorundadır — yakıt ceketten geçen soğutucudur.
    """
    return _cift(overrides={'engine_cycle': 'gas_generator',
                            'feed_pressure': 105},
                 cooling_type='ablative')


@pytest.fixture(scope='module')
def turbo_tek_tanim_yamali():
    """``_tank_pressure_bar()`` bellekte 12,0 bara alınmış turbo koşu.

    P3B3-13'ün parti raporundaki mutasyonun aynısı; ürün dosyasına
    DOKUNULMAZ, alt sınıf yalnız bu testin belleğinde yaşar. Tek tanım
    noktasını okuyan her tüketici 12,0 bara gitmek zorundadır.
    """
    class _TekTanimYamali(LiquidRocketEngine):
        def _tank_pressure_bar(self):
            return 12.0, 'MUTASYON (ÖH bekçisi): tek tanım noktası'

    with contextlib.redirect_stdout(io.StringIO()):
        engine = _TekTanimYamali(
            overrides=dict(SURE, engine_cycle='gas_generator',
                           feed_pressure=105),
            **TABAN)
        return engine, engine.calculate_performance()


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
        NPSH girdisi, tank kartı ve basınçlı kabın İŞLETME basıncı aynı
        sayı: hepsi PUMP_TANK_PRESSURE_DEFAULT_BAR.

        Mutasyon: _design_propellant_tanks'a `300000` Pa literal'i geri
        gelir ve sabit değişirse kart ile zincir ayrışır -> bu test düşer.

        Z5S/PK1 (P3B3-11) ÇEVİRİSİ: kap artık İŞLETME basıncında değil
        EMNİYET VANASI AYARINDA nitelendiriliyor, yani ``meop_bar`` tek
        kaynağın ta kendisi değil onun
        ``RELIEF_VALVE_SET_PRESSURE_FACTOR`` katıdır. Tek-kaynak iddiası
        zayıflamadı, ADRES değiştirdi: aynı zincir artık
        ``pressure_vessel['operating_pressure_bar']`` satırında kilitli ve
        MEOP o sayıdan çarpanla TÜREDİĞİ için ayrıca kilitli — kap kartı
        beslemeden ayrışırsa iki satır da düşer.

        ÖH D18 fizik-a2 (F3) ÇEVİRİSİ: bu bekçi eskiden tek kaynağı
        ``PUMP_TANK_PRESSURE_DEFAULT_BAR`` SABİTİNE bağlıyordu; bu, tank
        basıncının NPSH gereksiniminden boyutlandırılmasını KİLİTLEYEN bir
        iddiaydı (kusuru koruyan bekçi). Tek-kaynak iddiası zayıflamadı,
        ÇAPASI değişti: sayı artık türetilir, ama HER blok AYNI türetilmiş
        sayıyı taşımak zorundadır. Sayının sabite EŞİT OLMADIĞI da sınanır,
        yani sabite geri dönülürse bu test yine düşer.
        """
        _, sonuc = turbo
        beklenen = sonuc['feed_system']['tank_pressure_bar']
        assert beklenen != PUMP_TANK_PRESSURE_DEFAULT_BAR, (
            'tank basıncı NPSH gereksiniminden türetilmeli, sabit olmamalı')
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
            # Tek kaynak: kap kartının İŞLETME basıncı zincirin ta kendisi.
            assert tank['pressure_vessel']['operating_pressure_bar'] == \
                pytest.approx(beklenen, rel=1e-12)
            # Nitelendirme basıncı ondan çarpanla türer (P3B3-11 sözleşmesi).
            assert tank['pressure_vessel']['inputs']['meop_bar'] == \
                pytest.approx(beklenen * RELIEF_VALVE_SET_PRESSURE_FACTOR,
                              rel=1e-12)

    # ÖH defter P3B2-01 — Z5S/PK1 onarımıyla yeşile döndü, xfail(strict) imi
    # 27 Ağustos 2026'da söküldü. Kusur: gereken tank basıncı
    # P_c + ΔP_enjektör + 8 bar çıplak paydı, soğutma ceketi ΔP'si formüle
    # HİÇ girmiyordu (ölçüldü: rejeneratif 3,7685 bar / ablatif 0,0000 bar
    # iken required_fuel_tank_pressure İKİSİNDE DE 93,4000 bar).
    def test_gereken_tank_basinci_ceket_dp_sini_goruyor(self, turbo,
                                                        turbo_ablatif):
        """TAŞINAN BEKÇİ (P3B2-01): kardeş düğüm ``:233`` beş alanın AYNI
        sayı olduğunu doğruluyordu; beşi de ``_tank_pressure_bar()``'ı okuduğu
        için bu iddia yapı gereği doğrudur. Kilitlenmesi gereken şey teslim
        edilen basıncın değil, GEREKEN basıncın modelidir.

        İki koşu yalnız soğutma tipinde ayrılır; talep farkı ceket ΔP farkına
        eşit olmalıdır. Mutasyon yönü: ceket terimi formüle eklenirse bu
        bekçi yeşile döner (xfail kalkar), çıkarılırsa kırmızı kalır.
        """
        _, regen = turbo
        _, abl = turbo_ablatif
        r_inj, a_inj = regen['injection_system'], abl['injection_system']
        r_dp = float(regen['cooling_system']['cooling_pressure_drop'])
        a_dp = float(abl['cooling_system']['cooling_pressure_drop'])

        # Kontrol: düzenek gerçekten YALNIZ ceket ΔP'sinde ayrışıyor.
        assert r_dp > 0.0 and a_dp == 0.0, (
            f'düzenek bozuldu: rejeneratif ΔP={r_dp}, ablatif ΔP={a_dp}')
        assert a_inj['fuel_pressure_drop'] == pytest.approx(
            r_inj['fuel_pressure_drop'], rel=1e-12)
        assert a_inj['required_ox_tank_pressure'] == pytest.approx(
            r_inj['required_ox_tank_pressure'], rel=1e-12), (
            'oksitleyici ceketten geçmiyor; o taraf hareket etmemeli')

        # Asıl iddia: talep, ceketin kendi yayımladığı ΔP kadar yükselmeli.
        assert (r_inj['required_fuel_tank_pressure']
                - a_inj['required_fuel_tank_pressure']) == pytest.approx(
            r_dp - a_dp, rel=1e-6), (
            'gereken yakıt tank basıncı soğutma ceketi ΔP\'sini görmüyor: '
            f"rejeneratif {r_inj['required_fuel_tank_pressure']:.4f} bar, "
            f"ablatif {a_inj['required_fuel_tank_pressure']:.4f} bar, "
            f'ceket ΔP farkı {r_dp - a_dp:.4f} bar')

    # ÖH defter P3B3-13 — Z5S/PK1 onarımıyla yeşile döndü, xfail(strict) imi
    # 27 Ağustos 2026'da söküldü. Kusur: _solve_cycle_balance pompa emme
    # basıncını PUMP_TANK_PRESSURE_DEFAULT_BAR sabitinden DOĞRUDAN okuyordu;
    # tek tanım noktası 12,0 bara alınınca besleme kartı gidiyor ama
    # inlet_pressure_bar 3,0 barda KALIYORDU (beyan :5570-5572 yanlıştı).
    def test_cevrim_cozucusu_tank_basincini_tek_tanim_noktasindan_okur(
            self, turbo_tek_tanim_yamali):
        """TAŞINAN BEKÇİ (P3B3-13): ``:233`` tek-DEĞERLİLİĞİ ölçüyor, sabiti
        doğrudan okuyan bir yol o iddiayı tanım gereği geçiyor. Tek-KAYNAKLILIK
        ancak kaynak oynatılarak ölçülür.
        """
        motor, sonuc = turbo_tek_tanim_yamali
        beklenen = motor._tank_pressure_bar()[0]
        assert beklenen == 12.0, 'yama tutmadı — düzenek bozuk'
        # Kontrol: tek tanım noktasını GERÇEKTEN okuyan tüketici onu izliyor.
        assert sonuc['feed_system']['tank_pressure_bar'] == pytest.approx(
            beklenen, rel=1e-12)

        cyc = sonuc['detailed_feed_system']['engine_cycle_solution']
        assert isinstance(cyc, dict) and cyc.get('shafts'), (
            'çevrim çözümü koşmadı — düzenek bozuk')
        emme = [(s.get('name'), p.get('propellant'),
                 p.get('inlet_pressure_bar'))
                for s in cyc['shafts'] for p in s.get('pumps', ())]
        assert emme, 'çevrim çözümünde pompa kaydı yok — düzenek bozuk'
        for _, itici, basinc in emme:
            assert basinc == pytest.approx(beklenen, rel=1e-12), (
                f'{itici} pompası emme basıncını tek tanım noktasından '
                f'okumuyor: {basinc} bar (beklenen {beklenen} bar) — '
                f'ölçülen tüm kayıtlar: {emme}')

    # ÖH defter P3B3-11 — Z5S/PK1 onarımıyla yeşile döndü, xfail(strict) imi
    # 27 Ağustos 2026'da söküldü. Kusur: MEOP olarak İŞLETME basıncı
    # veriliyordu, emniyet vanası ise onun 1,10 katına ayarlıydı ve iki alan
    # arasında çapraz denetim yoktu (ölçüldü: turbo 3,0000 / 3,3000; basınç
    # beslemeli 105,0000 / 115,5000 — status=PASS hükmü %10 düşük zeminde).
    # Aynı onarım bu sınıfın iki tek-kaynak bekçisini de çevirdi: MEOP artık
    # çarpanlı, tek kaynak operating_pressure_bar satırında yaşıyor.
    @pytest.mark.parametrize('senaryo', ['turbo', 'basincli'])
    def test_meop_kendi_vana_ayarinin_altina_dusemez(self, senaryo, request):
        """TAŞINAN BEKÇİ (P3B3-11): bu sınıf MEOP'un besleme zinciriyle AYNI
        sayı olmasını şart koşuyordu — kusur tam olarak o eşitlikti. MEOP
        tanım gereği emniyet vanasının açma basıncından küçük olamaz;
        aksi hâlde kap, kendi vanası açılmadan önce ulaşacağı basınca göre
        nitelendirilmemiş demektir.
        """
        _, sonuc = request.getfixturevalue(senaryo)
        for ad in ('oxidizer_tank', 'fuel_tank'):
            tank = _tank(sonuc, ad)
            meop = tank['pressure_vessel']['inputs']['meop_bar']
            vana = tank['internal_structures']['instrumentation'][
                'relief_valve']['set_pressure']
            # Kontrol: vana ayarı gerçekten kaynağın 1,1 katı (kardeş bekçi).
            assert vana > 0
            assert meop >= vana - 1e-9, (
                f'{ad}: kap {meop:.4f} bar MEOP ile nitelendirilirken emniyet '
                f'vanası {vana:.4f} barda açıyor — nitelendirme sistemin '
                'ulaşabileceği basıncın altında kuruldu')

    def test_basinc_beslemeli_kart_kullanici_girdisini_gorur(self, basincli):
        """Basınç beslemeli çevrimde tank kartı kullanıcının feed_pressure
        girdisini (105 bar) görmeli — besleme kartıyla AYNI sayı.

        Mutasyon (teşhisin %16.7 uyuşmazlığı): eski `(P_c+5 bar) x 1.2`
        tahmini geri gelirse bu fikstürde kart 90.0 bar der ve düşer;
        cidar/kütle/MEOP/vana ayarı da o yanlış sayıdan türerdi.

        Z5S/PK1 (P3B3-11) ÇEVİRİSİ: kullanıcı girdisinin görüldüğü iddiası
        kap kartında artık ``operating_pressure_bar`` satırındadır (105,0);
        ``meop_bar`` ondan ``RELIEF_VALVE_SET_PRESSURE_FACTOR`` katıyla
        türer (115,5). Eski 90 bar tahmini geri gelirse İKİ satır da düşer.
        """
        _, sonuc = basincli
        assert sonuc['feed_system']['tank_pressure_bar'] == 105.0
        for ad in ('oxidizer_tank', 'fuel_tank'):
            tank = _tank(sonuc, ad)
            assert tank['structural']['pressure_rating'] == pytest.approx(
                105.0, rel=1e-12), (
                f'{ad}: kart besleme kartından ayrıştı — eski türetilmiş '
                'tahmin (90 bar) geri mi geldi?')
            assert tank['pressure_vessel']['operating_pressure_bar'] == \
                pytest.approx(105.0, rel=1e-12), (
                f'{ad}: kap kartının işletme basıncı kullanıcı girdisinden '
                'ayrıştı — tek kaynak koptu')
            assert tank['pressure_vessel']['inputs']['meop_bar'] == \
                pytest.approx(105.0 * RELIEF_VALVE_SET_PRESSURE_FACTOR,
                              rel=1e-12)

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

    # ÖH D18 fizik-a2 (F3): turbopompalı dalda künye artık sabitin ADINI
    # değil, basıncın NASIL boyutlandığını söyler.
    @pytest.mark.parametrize('senaryo,anahtar', [
        ('turbo', 'NPSH requirement'),
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

    # ÖH defter P3B1-14 — Z5S/PK1 onarımıyla yeşile döndü, xfail(strict) imi
    # 27 Ağustos 2026'da söküldü. Kusur: A3'ün yasakladığı yer tutucular
    # çalışan kodda duruyordu (:1138 getattr(self,'c_star',1650.0), :2082
    # F/(300*g0) ve deftere hiç girmemiş :8646 kardeşi F/(300*G_0)); üçü de
    # erişilemez yollardaydı ama kurucu sırası değişirse SESSİZCE canlanırdı.
    # Onarım fail-closed koydu (UnsupportedPropellantPairError). NOT: aşağıdaki
    # tarama 'G_0' yazımını GÖRMEZ (yalnız ast.Attribute 'g0'); iki yazımı da
    # kapsayan bekçi tests/test_z5s_sivi_tek_tanim.py::TestP3B1YerTutucular.
    def test_a3_yer_tutucu_sabitleri_kaynak_kodda_kalmadi(self):
        """Aynı kaynak-tarama deseni (yukarıdaki kardeş), A3'ün yasakladığı
        yedek sabitlere uygulanır.

        Tarama AST üzerindedir: docstring ve yorum içindeki ANMA serbesttir
        (:104 ve :2427 kusurun kendisini anlatıyor), yasak olan yalnız
        ÇALIŞAN koddaki sayıdır.
        """
        yol = pathlib.Path(inspect.getsourcefile(LiquidRocketEngine))
        agac = ast.parse(yol.read_text(encoding='utf-8'))

        def _sayi(dugum, deger):
            return (isinstance(dugum, ast.Constant)
                    and not isinstance(dugum.value, bool)
                    and isinstance(dugum.value, (int, float))
                    and float(dugum.value) == deger)

        bulunan = []
        for dugum in ast.walk(agac):
            if _sayi(dugum, 1650.0):
                bulunan.append((dugum.lineno, 'c* = 1650 m/s yer tutucusu'))
            if isinstance(dugum, ast.BinOp) and isinstance(dugum.op, ast.Mult):
                for a, b in ((dugum.left, dugum.right),
                             (dugum.right, dugum.left)):
                    if _sayi(a, 300.0) and isinstance(b, ast.Attribute) \
                            and b.attr == 'g0':
                        bulunan.append(
                            (dugum.lineno, 'Isp = 300 s yer tutucusu '
                                           '(F / (300 * g0))'))
        assert not bulunan, (
            'A3 kapanışında yasaklanan yer tutucular çalışan kodda duruyor '
            f'({yol.name}): '
            + '; '.join(f'{satir}: {ad}' for satir, ad in sorted(bulunan)))


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
                propellant_data=PROPELLANT_DATA, overrides=dict(SURE))
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
