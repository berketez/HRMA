"""ÖH Z5S / PK1 — sıvı motorda AYNI büyüklüğün TEK tanım noktası.

Bu dosya, ÖH defterinin yedi "bekçi-kırmızı" sıvı kalemi onarıldıktan sonra
onarımın KENDİSİNİ kilitler. Kardeş dosyalar (``test_sivi_tank_tek_geometri``,
``test_sivi_baglama_beyan``, ``test_scofield_sivi``) kusurları
``xfail(strict=True)`` borç imleriyle tescil etmişti; onarım o imleri XPASS'e
çevirir. Buradaki bekçiler ise onarımın GERİ ALINMASINI yakalar.

Kilitlenen sözleşmeler (defter kimlikleriyle)
--------------------------------------------
* **P3B2-01** — GEREKEN yakıt tank basıncı soğutma ceketi ΔP'sini görür.
  Ölçüm düzeneği: aynı motorun rejeneratif ve ablatif kardeşi YALNIZ soğutma
  tipinde ayrılır; talep farkı ceket ΔP farkının ta kendisi olmalıdır.
* **P3B3-13** — çevrim güç dengesi çözücüsü pompa emme basıncını A11'in tek
  tanım noktasından (``_tank_pressure_bar``) okur, sabitten değil. Tek
  KAYNAKLILIK ancak kaynak oynatılarak ölçülür (bellekte yamalı alt sınıf).
* **P3B3-11** — basınçlı kap nitelendirmesi kendi emniyet vanası ayarının
  ALTINDA kalamaz; işletme basıncı ayrı adla ve tek kaynağa bağlı durur.
* **P3B1-14** — A3 kapanışının yasakladığı yer tutucular (c* = 1650 m/s,
  Isp = 300 s) çalışan kodda YOKTUR; AST taraması ``G_0`` yazımını da kapsar.
* **P3B4-02** — aynı türbin için tek çevre hızı, tek ortalama çap, tek kademe
  sayısı. Kartın kendi tek kademeli kestirimi silinmez; AYRI adla ve künyeyle
  durur (sessiz ikame yok).
* **P3B4-09** — "cidar aktif soğutuluyor, ısıl koruma çözümü budur" hükmü
  ancak TANINAN bir aktif soğutma şemasında verilir; tanınmayan değer kendi
  gerekçesiyle NOT_MODELLED olur ve girdi uyarısı üretir.
* **P15B1-06** — aynı soğutma devresinin İKİ çözümünden ikisi de üst katmana
  çıkar (ayrı ad, ayrı künye); takma adların ``bulk_chain`` bağı bilinçli
  kilittir ve bu dosya onu da doğrular.

Bekçi disiplini: iddialar İLİŞKİ ve KÜNYE kilitler, kesin ondalık ÇAPALAMAZ
(eşzamanlı onarımlar değer kaydırabilir). Ölçülen sayılar
``docs/scofield/raw/OH/Z5S/pk1/`` altındaki kanıt dosyalarındadır.
"""

import ast
import contextlib
import inspect
import io
import math
import os
import pathlib
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from hrma.engines.liquid_rocket_engine import (             # noqa: E402
    BURN_TIME_DEFAULT_S,
    COOLING_TYPES_ACTIVE,
    COOLING_TYPES_PASSIVE,
    COOLING_TYPES_RECOGNISED,
    INJECTOR_FEED_MARGIN_BAR,
    PUMP_TANK_PRESSURE_DEFAULT_BAR,
    RELIEF_VALVE_SET_PRESSURE_FACTOR,
    LiquidRocketEngine,
)


# ---------------------------------------------------------------------------
# ÖH D31 fix-34b — ÜRÜN KAYNAĞI DOSYADAN OKUNUR (``inspect.getsource`` DEĞİL)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (``docs/scofield/raw/OH/D31/fix34/b/olcum_getsource_kaymasi.json``):
# taban kaydı-14 süiti PAYLAŞILAN ``main`` çalışma ağacında 64 dakika koştu;
# koşum sürerken D31 kulvar birleşmeleri main'e indi ve
# ``hrma/engines/liquid_rocket_engine.py`` DİSKTE DEĞİŞTİ (``_stream``
# 5938 -> 6015, ``_calculate_feed_system_pressure_drops`` 8933 -> 9014).
# Kod nesneleri içe aktarma anındaki satır numaralarını taşıyordu;
# ``inspect.getsource`` ise ``linecache`` üzerinden DEĞİŞMİŞ dosyayı okudu ve
# ``inspect.findsource`` geriye doğru ilk ``def``i bularak KOMŞU gövdeyi
# döndürdü: ``calculate_injector_design`` yerine ``_stream``,
# ``_solve_cycle_balance`` yerine ``_calculate_feed_system_pressure_drops``.
# Kırmızı ürün kusuru değil, DEĞİŞEN AĞAÇ ÜZERİNDE ÖLÇÜM artefaktıydı — aynı
# kayma ters yönde SAHTE YEŞİL de üretebilirdi.
#
# Kapı gevşetilmedi, ÖLÇÜM SAĞLAMLAŞTIRILDI: aranan şey zaten ürünün KAYNAK
# METNİdir, o yüzden metin çalışma-anı nesnesinden değil DOSYADAN alınır ve
# hedef gövde AST ile ADIYLA bulunur.
def _urun_kaynagi(nesne, *ad_yolu):
    """``nesne``nin tanımlandığı dosyadaki ``ad_yolu`` gövdesinin metni."""
    yol = pathlib.Path(inspect.getsourcefile(nesne) or '')
    assert yol.is_file(), 'kaynak dosya bulunamadı: %r' % (yol,)
    metin = yol.read_text(encoding='utf-8')
    govde = ast.parse(metin).body
    dugum = None
    for ad in ad_yolu:
        dugum = next((d for d in govde
                      if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef,
                                        ast.ClassDef)) and d.name == ad), None)
        assert dugum is not None, (
            '%s içinde %r tanımı yok (aranan yol: %s)'
            % (yol.name, ad, '.'.join(ad_yolu)))
        govde = dugum.body
    parca = ast.get_source_segment(metin, dugum)
    assert parca, 'kaynak parçası çıkarılamadı: %s' % '.'.join(ad_yolu)
    return parca

# Çevrimdışı itici verisi — TEK tanım noktası (CLAUDE.md kural 11): kardeş
# bekçi dosyalarıyla aynı sözlük, kopyalanmaz.
from tests.test_liquid_real_inputs import PROPELLANT_DATA   # noqa: E402

#: 25 kN LOX/RP-1 örneği — tank/basınç kalemlerinin ölçüm tabanı.
TABAN_25KN = dict(thrust=25000, chamber_pressure=70, mixture_ratio=2.3,
                  fuel_type='rp1', oxidizer_type='lox',
                  propellant_data=PROPELLANT_DATA)
#: 10 kN / Pc=100 — türbin ve ısıl koruma kalemlerinin ölçüm tabanı.
TABAN_10KN = dict(thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
                  fuel_type='rp1', oxidizer_type='lox',
                  cooling_type='regenerative', injector_type='impinging',
                  propellant_data=PROPELLANT_DATA)

#: ÖH D36 / LU-1 (ÇEVRİLEN BEKÇİ, onemli2-sivi a2): motor yanma süresini
#: ARTIK VARSAYMAZ; süre verilmezse ``propellant_tanks`` ``not_modelled`` ve
#: pasif ısıl koruma ``NOT_MODELLED`` (eksik: burn_time) döner. ``turbo``,
#: ``basincli`` ve ``turbo_ablatif`` senaryolarının ölçtüğü tank kapları
#: (P3B3 kap nitelendirmesi) ve ablatif astar boyutu (P3B4) SÜRESİ VERİLMİŞ
#: bir tasarımdır; süre motorun kendi sabitinden AÇIKÇA verilir (sayı burada
#: yazılmaz), sayılar LU-1 öncesindeki sessiz varsayımla birebir aynıdır.
SURE = {'max_burn_duration': BURN_TIME_DEFAULT_S}

#: P3B4-09 ölçümünün üç tanınmayan değeri (defterde adıyla geçen üçlü).
TANINMAYAN_SOGUTMA = ('banana', 'none', '')


def _kos(taban, overrides=None, **kwargs):
    kw = dict(taban)
    kw.update(kwargs)
    with contextlib.redirect_stdout(io.StringIO()):
        engine = LiquidRocketEngine(overrides=dict(overrides or {}), **kw)
        return engine, engine.calculate_performance()


# Çözüm pahalıdır; senaryo başına BİR koşu, modül boyunca paylaşılır.
@pytest.fixture(scope='module')
def turbo():
    return _kos(TABAN_25KN, dict(SURE, engine_cycle='gas_generator',
                                 feed_pressure=105))


@pytest.fixture(scope='module')
def turbo_ablatif():
    """``turbo``nun ABLATİF kardeşi — ceket ΔP'si tanım gereği sıfırdır."""
    return _kos(TABAN_25KN, dict(SURE, engine_cycle='gas_generator',
                                 feed_pressure=105),
                cooling_type='ablative')


@pytest.fixture(scope='module')
def basincli():
    return _kos(TABAN_25KN, dict(SURE, engine_cycle='pressure_fed',
                                 feed_pressure=105))


@pytest.fixture(scope='module')
def tek_tanim_yamali():
    """``_tank_pressure_bar()`` bellekte 12,0 bara alınmış turbo koşu.

    Ürün dosyasına DOKUNULMAZ; alt sınıf yalnız bu testin belleğinde yaşar.
    Tek tanım noktasını okuyan her tüketici 12,0 bara gitmek zorundadır.
    """
    class _Yamali(LiquidRocketEngine):
        def _tank_pressure_bar(self):
            return 12.0, 'Z5S/PK1 bekçisi: tek tanım noktası oynatıldı'

    with contextlib.redirect_stdout(io.StringIO()):
        engine = _Yamali(overrides={'engine_cycle': 'gas_generator',
                                    'feed_pressure': 105}, **TABAN_25KN)
        return engine, engine.calculate_performance()


@pytest.fixture(scope='module')
def gg10():
    return _kos(TABAN_10KN)


@pytest.fixture(scope='module')
def taninmayan():
    """Üç tanınmayan soğutma tipinin sonuçları (değer -> sonuç)."""
    return {ct: _kos(TABAN_10KN, cooling_type=ct)[1]
            for ct in TANINMAYAN_SOGUTMA}


def _tank(sonuc, ad):
    return sonuc['propellant_tanks'][ad]


def _sayi_var_mi(nesne):
    """Ağaçta bool olmayan bir sayı var mı? (fail-closed denetimi)"""
    if isinstance(nesne, bool):
        return False
    if isinstance(nesne, (int, float)):
        return True
    if isinstance(nesne, dict):
        return any(_sayi_var_mi(v) for v in nesne.values())
    if isinstance(nesne, (list, tuple)):
        return any(_sayi_var_mi(v) for v in nesne)
    return False


# ===========================================================================
# P3B2-01 — GEREKEN tank basıncı soğutma ceketini görüyor
# ===========================================================================
class TestP3B2GerekenBasincCeketiGoruyor:

    def test_talep_farki_ceket_dp_farkina_esit(self, turbo, turbo_ablatif):
        """İki koşu YALNIZ soğutma tipinde ayrılır; yakıt tarafındaki talep
        farkı ceket ΔP farkının ta kendisi olmalıdır.

        Mutasyon (ölçüldü): ceket terimi formülden çıkarılırsa talep farkı
        0,0000 bara döner (rejeneratif ve ablatif koşuda AYNI sayı) ve bu
        bekçi düşer.
        """
        _, regen = turbo
        _, abl = turbo_ablatif
        r_dp = float(regen['cooling_system']['cooling_pressure_drop'])
        a_dp = float(abl['cooling_system']['cooling_pressure_drop'])
        assert r_dp > 0.0 and a_dp == 0.0, (
            f'düzenek bozuldu: rejeneratif ΔP={r_dp}, ablatif ΔP={a_dp}')

        r_inj, a_inj = regen['injection_system'], abl['injection_system']
        assert a_inj['fuel_pressure_drop'] == pytest.approx(
            r_inj['fuel_pressure_drop'], rel=1e-12), (
            'enjektör ΔP\'si iki koşuda ayrıştı — karşılaştırma tabanı yok')
        assert (r_inj['required_fuel_tank_pressure']
                - a_inj['required_fuel_tank_pressure']) == pytest.approx(
            r_dp - a_dp, rel=1e-9), (
            'gereken yakıt tank basıncı soğutma ceketi ΔP\'sini görmüyor')

    def test_oksitleyici_tarafi_ceketten_etkilenmez(self, turbo,
                                                    turbo_ablatif):
        """Oksitleyici ceketten geçmez; o taraf hareket ETMEMELİDİR."""
        _, regen = turbo
        _, abl = turbo_ablatif
        assert abl['injection_system']['required_ox_tank_pressure'] == \
            pytest.approx(regen['injection_system'][
                'required_ox_tank_pressure'], rel=1e-12)

    @pytest.mark.parametrize('senaryo', ['turbo', 'turbo_ablatif'])
    def test_talep_kendi_dokumunden_yeniden_uretilir(self, senaryo, request):
        """Yayımlanan sayı, yayımlanan dökümün TOPLAMI olmalı (kimlik).

        Beyan ile sayının ayrışması bu sınıfın öteki yüzüdür: döküm bloğu
        süslü bir metin değil, sayının kendisidir.
        """
        _, sonuc = request.getfixturevalue(senaryo)
        inj = sonuc['injection_system']
        d = inj['required_fuel_tank_pressure_terms']
        assert d['chamber_pressure_bar'] + d['injector_pressure_drop_bar'] \
            + d['cooling_jacket_pressure_drop_bar'] + d['declared_margin_bar'] \
            == pytest.approx(inj['required_fuel_tank_pressure'], rel=1e-12)
        assert d['declared_margin_bar'] == pytest.approx(
            INJECTOR_FEED_MARGIN_BAR), (
            'pay tek tanım noktasından (INJECTOR_FEED_MARGIN_BAR) gelmiyor')
        assert d['cooling_jacket_pressure_drop_bar'] == pytest.approx(
            sonuc['cooling_system']['cooling_pressure_drop'], rel=1e-12), (
            'döküm, aynı yanıtın yayımladığı ceket ΔP\'sinden başka bir '
            'sayı taşıyor — iki ceket ΔP\'si olamaz')

    def test_beyan_ceket_terimini_adiyla_soyluyor(self, turbo):
        """Sayının yanında künyesi olacak: hangi kalemlerden kuruldu?"""
        inj = turbo[1]['injection_system']
        yakit = inj['required_fuel_tank_pressure_basis']
        oks = inj['required_ox_tank_pressure_basis']
        assert 'jacket' in yakit.lower()
        assert 'cooling_system.cooling_pressure_drop' in yakit
        assert 'no jacket term' in oks.lower(), (
            'oksitleyici künyesi ceketin NEDEN yok olduğunu söylemeli')

    def test_kodda_ciplak_pay_literali_yok(self):
        """Kusuru kilitleyen bekçi: 8 bar payı tek tanım noktasından okunur;
        formüle çıplak ``+ 8`` geri dönemez."""
        kaynak = _urun_kaynagi(LiquidRocketEngine, 'LiquidRocketEngine',
                               'calculate_injector_design')
        assert 'INJECTOR_FEED_MARGIN_BAR' in kaynak
        assert 'delta_P_fuel + 8' not in kaynak
        assert 'delta_P_ox + 8' not in kaynak


# ===========================================================================
# P3B3-13 — çevrim çözücüsü tank basıncını TEK tanım noktasından okur
# ===========================================================================
class TestP3B3CevrimCozucusuTekTanim:

    def test_pompa_emme_basinci_kaynagi_izler(self, tek_tanim_yamali):
        """Tek tanım noktası oynatılınca çözücünün pompa girişleri de gider.

        Mutasyon (ölçüldü): emme basıncı yine
        ``PUMP_TANK_PRESSURE_DEFAULT_BAR`` sabitinden okunursa besleme kartı
        12,0 bara giderken pompa girişleri 3,0 barda kalır ve bu düşer.
        """
        motor, sonuc = tek_tanim_yamali
        beklenen = motor._tank_pressure_bar()[0]
        assert beklenen == 12.0, 'yama tutmadı — düzenek bozuk'
        assert beklenen != PUMP_TANK_PRESSURE_DEFAULT_BAR, (
            'yama sabitin kendisine eşit — ayrışma ölçülemez')
        assert sonuc['feed_system']['tank_pressure_bar'] == pytest.approx(
            beklenen, rel=1e-12)

        cyc = sonuc['detailed_feed_system']['engine_cycle_solution']
        assert isinstance(cyc, dict) and cyc.get('shafts'), (
            'çevrim çözümü koşmadı — düzenek bozuk')
        kayit = [(s.get('name'), p.get('propellant'),
                  p.get('inlet_pressure_bar'))
                 for s in cyc['shafts'] for p in s.get('pumps', ())]
        assert kayit, 'çevrim çözümünde pompa kaydı yok — düzenek bozuk'
        for _, itici, basinc in kayit:
            assert basinc == pytest.approx(beklenen, rel=1e-12), (
                f'{itici} pompası emme basıncını tek tanım noktasından '
                f'okumuyor: {basinc} bar (beklenen {beklenen} bar); '
                f'ölçülen tüm kayıtlar: {kayit}')

    def test_cozucu_govdesinde_sabit_dogrudan_okunmuyor(self):
        """AST: ``_solve_cycle_balance`` içinde pompa emme argümanlarına
        sabit ADI doğrudan bağlanamaz — tek tanım noktası çağrılmalıdır."""
        kaynak = _urun_kaynagi(LiquidRocketEngine, 'LiquidRocketEngine',
                               '_solve_cycle_balance')
        agac = ast.parse(kaynak.lstrip())
        suclu = []
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.keyword):
                continue
            if dugum.arg not in ('pump_inlet_ox_bar', 'pump_inlet_fuel_bar'):
                continue
            if isinstance(dugum.value, ast.Name) and \
                    dugum.value.id == 'PUMP_TANK_PRESSURE_DEFAULT_BAR':
                suclu.append(dugum.arg)
        assert not suclu, (
            'çevrim çözücüsü pompa emme basıncını yine sabitten okuyor '
            f'({suclu}) — tek tanım noktası _tank_pressure_bar()')
        assert '_tank_pressure_bar()' in kaynak

    def test_turbopompali_koşuda_zincir_hala_tek_deger(self, turbo):
        """Çevrim çözücüsünün pompa girişleri tek tanım noktasını izler.

        ÖH D18 fizik-a2 (F3) ÇEVİRİSİ: bu bekçi eskiden çapayı
        ``PUMP_TANK_PRESSURE_DEFAULT_BAR`` SABİTİNE atıyor ve "onarım
        bugünkü sayıyı DEĞİŞTİRMEZ" diyordu. O bit-aynılık iddiası artık
        geçersiz: tank basıncı pompaların NPSH gereksiniminden
        boyutlandırılıyor (SP-8109 §3.2.1.2 + SP-125 eş. 6-8 tersi), yani
        motora göre değişiyor. Bu testin GERÇEK iddiası zaten sabitin
        değeri değil, ZİNCİRİN TEK DEĞER taşımasıydı — çapa oraya taşındı;
        ayrıca sayının sabite eşit OLMADIĞI sınanır ki sabite geri dönüş
        bu testi de kırsın.
        """
        _, sonuc = turbo
        beklenen = sonuc['feed_system']['tank_pressure_bar']
        assert beklenen != PUMP_TANK_PRESSURE_DEFAULT_BAR, (
            'tank basıncı NPSH gereksiniminden türetilmeli, sabit olmamalı')
        cyc = sonuc['detailed_feed_system']['engine_cycle_solution']
        for s in cyc.get('shafts') or []:
            for p in s.get('pumps', ()):
                assert p.get('inlet_pressure_bar') == pytest.approx(
                    beklenen, rel=1e-12)


# ===========================================================================
# P3B3-11 — kap nitelendirmesi kendi emniyet vanasının altına düşemez
# ===========================================================================
class TestP3B3KapNitelendirmesi:

    @pytest.mark.parametrize('senaryo', ['turbo', 'basincli'])
    def test_meop_vana_ayarinin_altina_dusemez(self, senaryo, request):
        """MEOP tanım gereği emniyet vanasının açma basıncından küçük olamaz.

        Mutasyon (ölçüldü): nitelendirme yine İŞLETME basıncında yapılırsa
        turbopompalı koşuda 3,0000 ⟷ 3,3000 ve basınç beslemelide
        105,0000 ⟷ 115,5000 çıkar; bu bekçi düşer.
        """
        _, sonuc = request.getfixturevalue(senaryo)
        for ad in ('oxidizer_tank', 'fuel_tank'):
            tank = _tank(sonuc, ad)
            meop = tank['pressure_vessel']['inputs']['meop_bar']
            vana = tank['internal_structures']['instrumentation'][
                'relief_valve']['set_pressure']
            assert vana > 0
            assert meop >= vana * (1.0 - 1e-9), (
                f'{ad}: kap {meop:.4f} bar ile nitelendirilirken emniyet '
                f'vanası {vana:.4f} barda açıyor')

    @pytest.mark.parametrize('senaryo', ['turbo', 'basincli'])
    def test_isletme_basinci_ayri_adla_ve_tek_kaynaktan(self, senaryo,
                                                        request):
        """Nitelendirme basıncı işletme basıncını EZMEZ: işletme basıncı
        kendi adıyla durur ve tank kartıyla AYNI tek kaynaktan gelir."""
        _, sonuc = request.getfixturevalue(senaryo)
        kaynak = sonuc['feed_system']['tank_pressure_bar']
        for ad in ('oxidizer_tank', 'fuel_tank'):
            tank = _tank(sonuc, ad)
            kap = tank['pressure_vessel']
            assert kap['operating_pressure_bar'] == pytest.approx(
                kaynak, rel=1e-9), (
                f'{ad}: kap kartındaki işletme basıncı besleme zincirinden '
                'ayrıştı — tek kaynak koptu')
            assert kap['operating_pressure_bar'] == pytest.approx(
                tank['structural']['pressure_rating'], rel=1e-9)
            assert kap['inputs']['meop_bar'] == pytest.approx(
                kap['operating_pressure_bar']
                * RELIEF_VALVE_SET_PRESSURE_FACTOR, rel=1e-9), (
                'nitelendirme basıncı vana ayarı çarpanından türemiyor')

    def test_kunye_carpani_ve_gerekcesini_yaziyor(self, turbo):
        """Beyansız sayı yasak: nitelendirme basıncının künyesi hangi
        basınç olduğunu ve neden o olduğunu söylemeli."""
        kap = _tank(turbo[1], 'fuel_tank')['pressure_vessel']
        kunye = kap['meop_basis']
        assert 'RELIEF_VALVE_SET_PRESSURE_FACTOR' in kunye
        assert 'operating_pressure_bar' in kunye
        assert 'relief' in kunye.lower()


# ===========================================================================
# P3B1-14 — A3'ün yasakladığı yer tutucular çalışan kodda yok
# ===========================================================================
class TestP3B1YerTutucular:

    def test_a3_yer_tutuculari_kodda_yok(self):
        """AST taraması: c* = 1650 m/s ve Isp = 300 s yer tutucuları.

        Kardeş bekçi (``test_sivi_tank_tek_geometri``) yalnız
        ``300 * self.g0`` yazımını arıyordu; ``300 * G_0`` kopyası taramadan
        kaçıyordu (ölçüldü: :8646). Bu tarama İKİ yazımı da kapsar.
        Docstring/yorum içindeki ANMA serbesttir — yasak olan çalışan koddaki
        sayıdır.
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
                    if not _sayi(a, 300.0):
                        continue
                    if isinstance(b, ast.Attribute) and b.attr == 'g0':
                        bulunan.append((dugum.lineno,
                                        'Isp = 300 s (300 * self.g0)'))
                    if isinstance(b, ast.Name) and b.id == 'G_0':
                        bulunan.append((dugum.lineno,
                                        'Isp = 300 s (300 * G_0)'))
        assert not bulunan, (
            'A3 kapanışında yasaklanan yer tutucular çalışan kodda duruyor: '
            + '; '.join(f'{satir}: {ad}' for satir, ad in sorted(bulunan)))

    def test_c_star_yedegi_sessiz_degil_kapali(self):
        """c* çözülmemişse hesap DURUR (fail-closed); yedek sayı konmaz.

        Tarama AST üzerindedir: yorumda/docstring'te kusurun ANILMASI
        serbesttir (yukarıdaki blok kusuru anlatıyor), yasak olan ÇALIŞAN
        koddaki ``getattr(self, 'c_star', <yedek>)`` çağrısıdır.
        """
        kaynak = _urun_kaynagi(LiquidRocketEngine, 'LiquidRocketEngine',
                               '__init__')
        agac = ast.parse(kaynak.lstrip())
        suclu = []
        for dugum in ast.walk(agac):
            if not (isinstance(dugum, ast.Call)
                    and isinstance(dugum.func, ast.Name)
                    and dugum.func.id == 'getattr'
                    and len(dugum.args) >= 3):
                continue
            ad = dugum.args[1]
            if isinstance(ad, ast.Constant) and ad.value == 'c_star':
                suclu.append(dugum.lineno)
        assert not suclu, (
            f'c* için getattr yedeği çalışan koda geri geldi (satır {suclu})')
        assert 'UnsupportedPropellantPairError' in kaynak


# ===========================================================================
# P3B4-02 — aynı türbinin TEK geometrisi
# ===========================================================================
class TestP3B4TurbinTekGeometri:

    @staticmethod
    def _bloklar(sonuc):
        besleme = sonuc['detailed_feed_system']
        return (besleme['turbopump_analysis']['turbine'],
                besleme['turbopump_sizing']['turbine'])

    def test_iki_blok_ayni_capi_veriyor(self, gg10):
        """İki blok ortalama çap için AYNI hükmü verir: ya aynı SAYI ya aynı
        "geri çekildi".

        Mutasyon (ölçüldü): mutabakat kapatılırsa kart 615,4852 m/s ile
        D = 0,32418 m ima eder, boyutlandırma 0,06719 m der (4,824x).

        ÇEVRİLDİ — ÖH D15 birleşme etkileşimi (1 Eylül 2026)
        ----------------------------------------------------
        Yapısal-sistem kulvarının **P5B3-04** onarımı kademe tavanında
        ``mean_diameter_m``i GERİ ÇEKİYOR (``None``): kırpma varken
        ``u_pitch = u_env`` olduğundan ``D = 60·U/(pi·N)`` yalnız dışarıdan
        gelen zarfı tekrar eder (ölçüldü: üç motorda da pompa çark çapına
        bağıl fark 0,0). Bu FAIL-CLOSED hüküm kazanır ve korunur.

        Eski satır çapın SAYI olmasını şart koşuyordu, yani P5B3-04'ün
        kapattığı kusurun geri gelmesini talep ediyordu. Birleşik ağaçta
        ölçülen sonuç: kart ``not_sized`` dalına düşüp 747,9283 m/s'lik tek
        kademeli kestirimi ``blade_tip_speed`` diye yayımlıyordu, boyutlandırma
        ise 3 kademe · 127,5766 m/s diyordu — P3B4-02'nin kusuru geri gelmişti.
        Ürün onarıldı (``_reconcile_turbine_geometry``: kademe/pitch KARAR,
        çap TÜREV) ve bu bekçi iki dallı sözleşmeye çevrildi. GEVŞEME YOK:
        geri çekme dalında kartın gerekçesinin modülün KENDİ kaydıyla
        bayt-aynı olması ve yayımlanan hızın tek kademeli kestirim OLMAMASI
        ayrıca kilitlenir.
        """
        kart, boyut = self._bloklar(gg10[1])
        assert boyut['shaft_speed_rpm'] == pytest.approx(
            kart['rotational_speed'], rel=1e-9), (
            'iki blok farklı devirde — karşılaştırma tabanı yok')
        d_boyut = boyut['mean_diameter_m']
        if d_boyut is None:
            # (a) GERİ ÇEKME dalı — iki blok aynı hükmü verir.
            assert boyut['mean_diameter_is_degenerate'] is True, (
                'boyutlandırma çapı geri çekti ama dejenerasyonu beyan '
                'etmiyor (P5B3-04 kanalı kopuk)')
            assert kart['mean_diameter_m'] is None, (
                'boyutlandırma çapı geri çekerken kart kendi çapını '
                'yayımlıyor — aynı türbin için ikinci bir çap')
            assert kart['mean_diameter_status'] == 'withheld_by_sizing'
            gerekce = [k.get('message') for k in (boyut.get('validity') or [])
                       if k.get('field') == 'turbine_mean_diameter']
            assert gerekce, 'boyutlandırma geri çekme gerekçesini yazmıyor'
            assert kart['mean_diameter_basis'] == gerekce[0], (
                'kart geri çekme için İKİNCİ bir gerekçe metni yazıyor; '
                'gerekçe tek kaynaktan (modülün validity kaydından) gelmeli')
            # Kartın hızı hâlâ boyutlandırmanın kararıdır: tek kademeli
            # kestirim yayımlanan hızın yerine GEÇMEMİŞTİR (birleşme kusuru).
            assert float(kart['blade_tip_speed']) == pytest.approx(
                float(boyut['pitch_speed_m_s']), rel=1e-12)
            assert float(kart['blade_tip_speed']) != pytest.approx(
                float(kart['blade_speed_single_stage_optimum_m_s']),
                rel=1e-9), (
                'yayımlanan çevre hızı kartın tek kademeli kestirimine geri '
                'döndü — boyutlandırma kararı atılmış demektir')
        else:
            # (b) YAYIMLAMA dalı — iki blok aynı sayıyı verir.
            n = float(kart['rotational_speed'])
            d_karttan = 60.0 * float(kart['blade_tip_speed']) / (math.pi * n)
            assert float(d_boyut) == pytest.approx(d_karttan, rel=1e-9)
            assert float(kart['mean_diameter_m']) == pytest.approx(
                float(d_boyut), rel=1e-12), (
                'kart kendi ortalama çapını yayımlıyor ama '
                'boyutlandırmanınkiyle aynı değil')
            assert kart['mean_diameter_status'] == 'published'

    def test_kademe_sayisi_ve_tip_tek_karar(self, gg10):
        """Kademe sayısı bir TASARIM KARARIDIR; iki blok iki karar veremez."""
        kart, boyut = self._bloklar(gg10[1])
        kademe = int(boyut['stage_count'])
        assert int(kart['stage_count']) == kademe
        tip = str(kart['type']).lower()
        if kademe == 1:
            assert 'single' in tip
        else:
            assert 'single' not in tip, (
                f"kart '{kart['type']}' diyor, boyutlandırma {kademe} kademe "
                'yayımlıyor')
            assert str(kademe) in tip

    def test_tek_kademeli_kestirim_silinmedi_kunyesiyle_duruyor(self, gg10):
        """Kartın kendi kestirimi kaybolmaz: AYRI ad, AYRI künye.

        Sessiz ikame yasağı: bir sayı başka bir sayının yerine geçerse
        kullanıcı hangi modeli okuduğunu bilemez.
        """
        kart, _ = self._bloklar(gg10[1])
        tek = float(kart['blade_speed_single_stage_optimum_m_s'])
        assert tek > 0
        assert 'C0' in kart['blade_speed_single_stage_optimum_basis']
        assert kart['blade_tip_speed_basis']
        assert 'turbopump_sizing' in kart['geometry_source']

    def test_yayimlanan_hiz_boyutlandirmanin_pitch_hizidir(self, gg10):
        kart, boyut = self._bloklar(gg10[1])
        assert float(kart['blade_tip_speed']) == pytest.approx(
            float(boyut['pitch_speed_m_s']), rel=1e-12)


# ===========================================================================
# P3B4-09 — tanınmayan soğutma tipine aktif soğutma hükmü verilmez
# ===========================================================================
class TestP3B4SogutmaTipiKapisi:

    @staticmethod
    def _pasif(sonuc):
        return sonuc['thermal_protection']['passive_thermal_protection']

    def test_tanim_kumeleri_tek_kaynaktan_turuyor(self):
        """Tanınan kümeler cidar sıcaklığı tablosundan TÜRETİLİR; iki liste
        ayrışamaz (CLAUDE.md kural 11)."""
        assert set(COOLING_TYPES_RECOGNISED) == (
            set(COOLING_TYPES_ACTIVE) | set(COOLING_TYPES_PASSIVE))
        assert set(COOLING_TYPES_ACTIVE) & set(COOLING_TYPES_PASSIVE) == set()
        assert 'regenerative' in COOLING_TYPES_ACTIVE
        assert 'ablative' in COOLING_TYPES_PASSIVE

    @pytest.mark.parametrize('cooling_type', TANINMAYAN_SOGUTMA)
    def test_taninmayan_deger_aktif_sogutma_hukmu_almaz(self, taninmayan,
                                                        cooling_type):
        """Ölçülen kusur: 'banana' / 'none' / '' üçü de "the wall is actively
        cooled" hükmüne düşüyordu ve o koşularda kanal 0, hız 0,0 m/s idi."""
        blok = self._pasif(taninmayan[cooling_type])
        assert blok['status'] == 'NOT_MODELLED'
        assert blok['cooling_type_recognised'] is False
        assert 'actively cooled' not in str(blok.get('reason') or ''), (
            'tanınmayan soğutma tipine hâlâ aktif soğutma hükmü veriliyor')
        assert str(cooling_type) in str(blok['cooling_type_supplied'])
        assert set(blok['cooling_type_options']) == set(
            COOLING_TYPES_RECOGNISED)

    @pytest.mark.parametrize('cooling_type', TANINMAYAN_SOGUTMA)
    def test_taninmayan_deger_sayi_uretmez(self, taninmayan, cooling_type):
        """Fail-closed: hüküm verilemiyorsa uydurma sayı da yayımlanmaz."""
        blok = dict(self._pasif(taninmayan[cooling_type]))
        blok.pop('status', None)
        blok.pop('cooling_type_recognised', None)
        assert not _sayi_var_mi(blok), (
            'tanınmayan soğutma tipinde pasif ısıl koruma bloğu sayı '
            f'yayımlıyor: {blok}')

    @pytest.mark.parametrize('cooling_type', TANINMAYAN_SOGUTMA)
    def test_taninmayan_deger_girdi_uyarisi_uretir(self, taninmayan,
                                                   cooling_type):
        """Sessiz varsayım yasağı: kullanıcı seçiminin tanınmadığını
        uyarı kanalından da görmeli."""
        uyarilar = taninmayan[cooling_type].get('input_warnings') or []
        kodlar = [u.get('code') for u in uyarilar if isinstance(u, dict)]
        alanlar = [(u.get('params') or {}).get('field')
                   for u in uyarilar if isinstance(u, dict)]
        assert 'warn.liquid.option_not_recognised' in kodlar
        assert 'cooling_type' in alanlar

    def test_mesru_aktif_dalda_hukum_hala_veriliyor(self, gg10):
        """Onarım meşru dalı köreltmemeli: rejeneratif koşuda hüküm DOĞRU
        ve fiilî soğutma (kanal + hız) vardır."""
        _, sonuc = gg10
        blok = self._pasif(sonuc)
        assert blok['status'] == 'NOT_APPLICABLE'
        assert blok['cooling_type_recognised'] is True
        assert 'actively cooled' in blok['reason']
        assert float(sonuc['cooling_system']['cooling_channels']) > 0
        assert float(sonuc['cooling_system']['coolant_velocity']) > 0

    def test_pasif_dalda_boyutlandirma_hala_kosuyor(self, turbo_ablatif):
        """Ablatif dal kapıdan geçmeye devam etmeli (kapsam daralmadı)."""
        blok = self._pasif(turbo_ablatif[1])
        assert blok['status'] == 'modelled'
        assert 'chamber_liner' in blok


# ===========================================================================
# P15B1-06 — aynı devrenin İKİ çözümü de üst katmanda
# ===========================================================================
class TestP15B1MarsKarsiligi:

    #: (çıplak takma ad, üst katman marş alanı, station_march alanı)
    MARS_UCLULERI = (
        ('heat_flux', 'heat_flux_station_march_MW_m2',
         'peak_heat_flux_MW_m2'),
        ('coolant_exit_temperature',
         'coolant_exit_temperature_station_march_K',
         'coolant_exit_temperature_K'),
        ('pressure_drop', 'pressure_drop_station_march_bar',
         'coolant_pressure_drop_bar'),
    )

    def test_mars_karsiligi_ust_katmanda_ve_kimlikli(self, gg10):
        """Marş çözümünün üç büyüklüğü üst katmanda, alt bloktaki sayının
        TA KENDİSİ olarak durur.

        Mutasyon (ölçüldü): yayın satırları kaldırılırsa üst katmanda marş
        karşılığını taşıyan alan kalmaz (ölçülen çift: akı 79,8703 ⟷ 11,6788
        MW/m², çıkış 796,0493 ⟷ 453,7269 K, ΔP 1,4780 ⟷ 1,2348 bar).
        """
        _, sonuc = gg10
        tp = sonuc['thermal_protection']
        sm = tp['station_march']
        for _, ust_ad, mars_ad in self.MARS_UCLULERI:
            assert ust_ad in tp, (
                f'{ust_ad} yok — marş karşılığı yine yalnız alt blokta')
            assert tp[ust_ad] == pytest.approx(sm[mars_ad], rel=1e-12)

    def test_takma_adlar_bulk_zincirinde_kaldi(self, gg10):
        """BİLİNÇLİ KİLİT (ÖK-14): çıplak takma adlar bugün toplu Bartz
        zincirini taşır; marş karşılığı onların yerine SESSİZCE geçmedi."""
        _, sonuc = gg10
        tp = sonuc['thermal_protection']
        bulk = tp['channel_circuit_reconciliation']['bulk_chain']
        assert tp['heat_flux'] == pytest.approx(
            bulk['peak_heat_flux_MW_m2'], rel=1e-12)
        assert tp['coolant_exit_temperature'] == pytest.approx(
            bulk['coolant_exit_temperature_K'], rel=1e-12)
        assert tp['pressure_drop'] == pytest.approx(
            bulk['pressure_drop_bar'], rel=1e-12)

    def test_iki_kume_ayri_adla_yasiyor(self, gg10):
        """İki çözüm aynı adı paylaşmaz; ayrıştıkları ölçülebilir olmalı."""
        _, sonuc = gg10
        tp = sonuc['thermal_protection']
        for cıplak, ust_ad, _ in self.MARS_UCLULERI:
            assert cıplak != ust_ad
            assert tp[cıplak] != pytest.approx(tp[ust_ad], rel=1e-6), (
                f'{cıplak} ile {ust_ad} aynı sayıya indi — iki zincir tek '
                'kaynağa mı düştü? O gün bu bekçi yeni sözleşmeye göre '
                'güncellenir (ÖK-14 protokolü)')

    def test_mars_skalerleri_kunyeli(self, gg10):
        """Beyansız sayı yasak."""
        tp = gg10[1]['thermal_protection']
        kunye = tp['station_march_scalars_basis']
        assert 'station march' in kunye.lower()
        assert 'channel_circuit_reconciliation' in kunye

    def test_sicaklik_artisi_kendi_giris_sicakligindan_turer(self, gg10):
        """Marş ΔT'si kendi çıkış sıcaklığından türetilir (kimlik)."""
        tp = gg10[1]['thermal_protection']
        assert tp['temperature_rise_station_march_K'] == pytest.approx(
            tp['coolant_exit_temperature_station_march_K']
            - tp['coolant_inlet_temperature'], rel=1e-12)
