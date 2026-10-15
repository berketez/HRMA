"""ÖH Dalga-27 · sivi · aşama 1 — onarım bekçileri.

BAĞLANAN DEFTER KALEMLERİ
-------------------------
OH-D26-07  ΔP/Pc BAĞLAM VARSAYILANLARI TEK KAYNAĞA.
    ÖLÇÜLDÜ (``docs/scofield/raw/OH/D27/sivi/a1/once.json``): 0,20/0,15
    çifti ürün kodunda ΔP/Pc bağlamında BEŞ sitede daha SAYI olarak
    yazılıydı (cycle_power_balance ×2, injector_design ×2,
    liquid_rocket_engine ×1). Dördü tanım noktasına bağlandı, kalan ikizi
    tek tanıma indirildi; envanter 5 -> 0.

OH-D26-09  NPSH DEVİR SEÇİMİNİN BAĞLAYICI KISITI ADIYLA YAYIMLANIR.
    ÖLÇÜLDÜ (25 kN LOX/RP-1, Pc = 60 bar): mil devri emme sınırının 0,90
    katıdır; omega_ss = 8 -> 21 864 US, indüsersiz tavanın (11 000 US) İKİ
    KATI, yani tasarım İNDÜSER İSTER — ama ``inducer_required`` alanı
    ``None`` yayımlanıyordu. Özgül devir ölçüldü: yakıt 922,8 US (radyal
    bandın ortası), oksitleyici 407,4 US (bandın ALTINDA). Kalemin sorduğu
    "yönü mü yanlış, tavanı mı bayat" sorusunun ölçülmüş yanıtı: yakıt
    devrinin YÖNÜ bandın dışına çıkmıyor (Ns bandın ortasında, çevresel hız
    129 m/s), 60 000 rpm tavanı bir SAYI çapasıydı. Bağlayıcı kısıt indüser
    gerekliliği ve oksitleyici tarafındaki kademe sorusudur.

OH-D26-12  TANK BASINCI KAPISININ ÖNERMESİ ÇEVRİME BAĞLANDI.
    ÖLÇÜLDÜ (10 kN RP-1/LOX, Pc = 30 bar, çevrim belirtilmemiş =
    turbopompalı): ``tank_pressure=3`` -> 400 "must be greater than chamber
    pressure" (turbopompalı tankta 3 bar NORMALDİR; çözücü aynı yanıtta
    2,768 bar yayımlıyor), ``tank_pressure=200`` -> 200 ve hiçbir yaprağı
    oynatmıyor (sessiz yutma). Onarım: turbopompalı çevrimde alan ADIYLA
    reddedilir (422 + use_instead), basınç beslemeli çevrimde ΔP kapısı
    aynen kalır. Hiçbir vaka 400 -> 200'e geçmedi (ÖK-22).

P4B4-07    SU KOÇU BESLEME AKIŞKAN HARİTASI — VERİ BORCU (ENGELLİ).
    Ürün fail-closed; kapanması altı itici için kaynak künyeli K/rho/p_v
    kaydı ister ve bu dalgada o veri kazanılamadı. Aşağıdaki bekçiler
    borcun ÇÜRÜMESİNİ engeller: fail-closed sözleşmesi ile haritanın
    merkezî itici tablosuyla AYNI yoğunluğu taşıma şartı kilitlenir.
"""

import ast
import io
import contextlib
import os
import re
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

SIVI = {'motor_name': 'D27-SIVI', 'thrust': 10000.0, 'burn_time': 30.0,
        'chamber_pressure': 30.0, 'mixture_ratio': 2.2,
        'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'expansion_ratio': 12.0}


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _gonder(client, ek):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = client.post('/calculate_liquid', json=dict(SIVI, **ek))
    try:
        return r.status_code, (r.get_json() or {})
    except Exception:                                      # pragma: no cover
        return r.status_code, {}


# ===========================================================================
# OH-D26-07 — ΔP/Pc bağlam varsayılanları tek kaynaktan
# ===========================================================================
class TestOHD2607BaglamVarsayilanlariTekKaynak:
    """Mutasyon hedefi: bir bağlam varsayılanının yeniden SAYI olması."""

    def test_enjektor_tipi_varsayilani_tanim_noktasindan_gelir(self):
        """``INJECTOR_TYPE_DP_FRACTION_DEFAULT`` merkezle AYNI NESNE.

        Değer eşitliği YETMEZ: 0,20 tesadüfen de eşit olabilir. Bekçi
        merkezin kaydırılmasının bu adı da kaydırdığını ister.
        """
        from hrma.analysis import acoustic_modes
        from hrma.engines import liquid_rocket_engine as lre

        assert (lre.INJECTOR_TYPE_DP_FRACTION_DEFAULT
                == acoustic_modes.CHUG_DP_RATIO_RECOMMENDED)
        kaynak = _modul_kaynagi(lre)
        assert not re.search(
            r'^INJECTOR_TYPE_DP_FRACTION_DEFAULT\s*=\s*0\.',
            kaynak, re.M), (
            'tip varsayılanı yeniden SAYI olarak yazılmış — ikinci tanım '
            'noktası geri geldi')

    def test_enjektor_tasarimi_cagri_varsayilani_merkezden_gelir(self):
        """``dp_ratio_ox`` / ``dp_ratio_fuel`` çıplak 0,20'ye düşmez."""
        from hrma.engines import injector_design as idm

        kaynak = _modul_kaynagi(idm)
        for ad in ('dp_ratio_ox', 'dp_ratio_fuel'):
            assert not re.search(
                r"spec\.get\('%s',\s*0\.\d+\)" % ad, kaynak), (
                f'{ad} çağrı varsayılanı yine çıplak sayı')
        assert "spec.get('dp_ratio_ox', CHUG_DP_RATIO_RECOMMENDED)" in kaynak

    def test_sicak_gaz_ikizi_TEK_tanima_indi(self):
        """Gaz + ön yakıcı varsayılanı aynı tek tanımın takma adıdır."""
        from hrma.engines import cycle_power_balance as cpb

        assert (cpb.INJECTOR_DP_FRAC_GAS_DEFAULT
                is cpb.INJECTOR_DP_FRAC_HOT_GAS_BAND_LOW)
        assert (cpb.INJECTOR_DP_FRAC_PREBURNER_DEFAULT
                is cpb.INJECTOR_DP_FRAC_HOT_GAS_BAND_LOW)
        # Ayrım korunur: bu sayı chug kuralına BAĞLANMADI.
        assert 'not the same quantity' in (
            cpb.INJECTOR_DP_FRAC_HOT_GAS_BAND_LOW_SOURCE)

    def test_envanter_BOSALDI_ve_yeniden_dolarsa_kirmizi(self):
        """AST taraması: ΔP/Pc bağlamında kalan borç sitesi YOK.

        Tarama ``test_stability_sivi``den İTHAL EDİLMEZ; deseni burada
        yeniden kurulur ki iki bekçi birbirini kör etmesin.
        """
        borclu = _dp_orani_siteleri()
        muaf = {
            ('hrma/engines/liquid_rocket_engine.py',
             'injector_pressure_drop'),
            ('hrma/engines/solid_rocket_engine.py',
             'pressure_fraction_default'),
            ('hrma/utils/injector_design.py', 'INJECTOR_PLATE_MIN_LIGAMENT'),
            ('hrma/engines/cycle_power_balance.py',
             'INJECTOR_DP_FRAC_HOT_GAS_BAND_LOW'),
        }
        kalan = sorted(set(borclu) - muaf)
        assert not kalan, (
            f'ΔP/Pc bağlam varsayılanı borcu yeniden doğdu: {kalan}')


def _modul_kaynagi(modul):
    with open(modul.__file__, encoding='utf-8') as f:
        return f.read()


def _dp_orani_siteleri():
    """(dosya, sahip) çiftleri — 0,20/0,15 ΔP/Pc bağlamında."""
    baglam = re.compile(r'(?i)dp|delta_p|pressure_drop|p_c|chamber_pressure|inj')
    ciftler = set()
    for kok, _d, dosyalar in os.walk(os.path.join(REPO_ROOT, 'hrma')):
        if '__pycache__' in kok:
            continue
        for dosya in sorted(dosyalar):
            if not dosya.endswith('.py'):
                continue
            tam = os.path.join(kok, dosya)
            bagil = os.path.relpath(tam, REPO_ROOT).replace(os.sep, '/')
            if bagil == 'hrma/analysis/acoustic_modes.py':
                continue
            with open(tam, encoding='utf-8') as f:
                kaynak = f.read()
            satirlar = kaynak.splitlines()
            agac = ast.parse(kaynak, filename=tam)
            ebeveyn = {}
            for ust in ast.walk(agac):
                for cocuk in ast.iter_child_nodes(ust):
                    ebeveyn[cocuk] = ust
            for dugum in ast.walk(agac):
                if not isinstance(dugum, ast.Constant):
                    continue
                if not isinstance(dugum.value, float):
                    continue
                if dugum.value not in (0.20, 0.15):
                    continue
                if not baglam.search(satirlar[dugum.lineno - 1]):
                    continue
                ciftler.add((bagil, _sahip(dugum, ebeveyn)))
    return ciftler


def _sahip(dugum, ebeveyn):
    n = dugum
    while n in ebeveyn:
        ust = ebeveyn[n]
        if isinstance(ust, ast.Assign):
            for hedef in ust.targets:
                if isinstance(hedef, ast.Name):
                    return hedef.id
                if isinstance(hedef, ast.Attribute):
                    return hedef.attr
            return None
        if isinstance(ust, ast.Dict):
            for anahtar, deger in zip(ust.keys, ust.values):
                if deger is n and isinstance(anahtar, ast.Constant):
                    return str(anahtar.value)
            return None
        if isinstance(ust, ast.Call):
            for arg in ust.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    return arg.value
            return None
        if isinstance(ust, ast.keyword):
            return ust.arg
        if isinstance(ust, ast.Compare):
            sol = ust.left
            if isinstance(sol, ast.Attribute):
                return sol.attr
            if isinstance(sol, ast.Name):
                return sol.id
            return None
        n = ust
    return None


# ===========================================================================
# OH-D26-12 — kapının önermesi ÇEVRİME bağlı
# ===========================================================================
class TestOHD2612CevrimEksenliTankKapisi:
    """Mutasyon hedefleri: (1) kapı yine çevrimden bağımsız hüküm veriyor,
    (2) turbopompalı çevrimde alan sessizce yutuluyor, (3) basınç beslemeli
    çevrimde ΔP kapısı susuyor."""

    @pytest.mark.parametrize('deger', [3, 29, 45, 200])
    def test_turbopompali_cevrimde_alan_ADIYLA_reddedilir(self, client, deger):
        kod, govde = _gonder(client, {'tank_pressure': deger})
        assert kod == 422, (
            f'tank_pressure={deger} turbopompalı çevrimde okunmuyor; '
            f'adıyla reddedilmeliydi. HTTP {kod}')
        assert govde.get('error') == (
            'tank_pressure_not_read_in_turbopump_cycle'), govde
        alan = (govde.get('invalid_fields') or [{}])[0]
        assert alan.get('field') == 'tank_pressure', alan
        assert alan.get('use_instead') == 'feed_pressure', alan
        # FAIL-CLOSED: ret gövdesinde tasarım YOK.
        for anahtar in ('motor_geometry', 'performance', 'plots',
                        'detailed_feed_system'):
            assert anahtar not in govde, f'reddedilen istekte {anahtar} var'

    def test_basinc_beslemeli_cevrimde_dP_kapisi_AYNEN(self, client):
        """Kapsam daralmadı: tank enjektörü besliyorsa eski hüküm sürüyor."""
        kod_dusuk, govde = _gonder(
            client, {'engine_cycle': 'pressure_fed', 'tank_pressure': 29})
        assert kod_dusuk == 400, f'ΔP kapısı susmuş; HTTP {kod_dusuk}'
        alan = (govde.get('invalid_fields') or [{}])[0]
        assert alan.get('reason') == 'insufficient_injector_pressure_drop', alan
        kod_saglikli, _ = _gonder(
            client, {'engine_cycle': 'pressure_fed', 'tank_pressure': 45})
        assert kod_saglikli == 200, (
            f'sağlıklı basınç beslemeli tank reddedildi; HTTP {kod_saglikli}')

    def test_alan_gonderilmezse_HICBIR_SEY_degismez(self, client):
        """Çözücünün kendi tank çözümü dokunulmadan kalır."""
        kod, govde = _gonder(client, {})
        assert kod == 200, f'sağlıklı gövde bozuldu; HTTP {kod}'
        tank = (govde.get('detailed_feed_system') or {}).get(
            'tank_pressure_bar')
        assert tank is not None and float(tank) > 0.0, (
            'çözücü kendi tank basıncını yayımlamıyor')

    def test_feed_pressure_kapisi_HER_CEVRIMDE_isirir(self, client):
        """``feed_pressure`` iki çevrimde de enjektörü besleyen basınçtır."""
        for ek in ({}, {'engine_cycle': 'pressure_fed'}):
            kod, _ = _gonder(client, dict(ek, feed_pressure=3))
            assert kod == 400, (
                f'{ek or "turbopompalı"}: 3 bar besleme 30 bar hazneye '
                f'akamaz; HTTP {kod}')

    def test_cevrim_ayrimi_TEK_KAYNAKTAN(self):
        """Uç katmanı çevrim kuralını yeniden yazmaz; motordan okur."""
        from hrma.engines.liquid_rocket_engine import tank_feeds_injector

        assert tank_feeds_injector({'engine_cycle': 'pressure_fed'}) is True
        # Tanınmayan / eksik çevrim FAIL-CLOSED tarafa düşer (turbopompa).
        for govde in ({}, {'engine_cycle': 'gas_generator'},
                      {'engine_cycle': 'banana'}, {'engine_cycle': None},
                      {'engine_cycle': 3}, 'sozluk-degil'):
            assert tank_feeds_injector(govde) is False, govde
        # Uç katmanında ikinci bir çevrim kuralı YAZILMAMIŞ olmalı.
        with open(os.path.join(REPO_ROOT, 'hrma', 'app.py'),
                  encoding='utf-8') as f:
            app_kaynak = f.read()
        assert app_kaynak.count("== 'pressure_fed'") == 0, (
            'uç katmanı çevrim kuralını kendi literaliyle yeniden yazıyor')


# ===========================================================================
# OH-D26-09 — devir seçiminin bağlayıcı kısıtı ADIYLA yayımlanır
# ===========================================================================
@pytest.fixture(scope='module')
def besleme_25kn():
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        eng = LiquidRocketEngine(thrust=25000, chamber_pressure=60,
                                 mixture_ratio=2.3, fuel_type='rp1',
                                 oxidizer_type='lox')
        res = eng.calculate_performance()
    return res['detailed_feed_system']['turbopump_analysis']


class TestOHD2609DevirBandiTuretimli:
    """Mutasyon hedefleri: (1) ``inducer_required`` yine ``None``,
    (2) bant sınırı kartta ikinci kez yazılıyor, (3) özgül devir sınıfı
    ölçümle çelişiyor."""

    @pytest.mark.parametrize('ad', ['oxidizer_pump', 'fuel_pump'])
    def test_induser_gerekliligi_YAPISAL_ve_turetimli(self, besleme_25kn, ad):
        from hrma.analysis.turbopump_sizing import NSS_NO_INDUCER_MAX_US

        p = besleme_25kn[ad]
        nss = float(p['suction_specific_speed_us'])
        assert isinstance(p['inducer_required'], bool), (
            'indüser gerekliliği hâlâ yapısal bir alan değil: '
            f'{p["inducer_required"]!r}')
        assert p['inducer_required'] is (nss > NSS_NO_INDUCER_MAX_US), (
            f'{ad}: Nss = {nss:.0f} US, indüsersiz tavan '
            f'{NSS_NO_INDUCER_MAX_US:.0f} US — yayımlanan hüküm '
            f'{p["inducer_required"]} ile çelişiyor')

    @pytest.mark.parametrize('ad', ['oxidizer_pump', 'fuel_pump'])
    def test_ozgul_devir_KENDI_kartindan_turetilebilir(self, besleme_25kn, ad):
        """Ns, kartın KENDİ devri/debisi/basma yüksekliğinden yeniden kurulur.

        Sayı çapası değil İLİŞKİ: kart hangi devri yayımlarsa yayımlasın,
        yayımladığı özgül devir o üçlüden çıkmak ZORUNDADIR.
        """
        from hrma.analysis.turbopump_sizing import (
            NS_CENTRIFUGAL_MAX_US, NS_CENTRIFUGAL_MIN_US, m3s_to_gpm, m_to_ft)

        p = besleme_25kn[ad]
        ns = float(p['specific_speed_us'])
        beklenen = (float(p['rotational_speed'])
                    * m3s_to_gpm(float(p['volumetric_flow_m3_s'])) ** 0.5
                    / m_to_ft(float(p['total_head_m'])) ** 0.75)
        assert ns == pytest.approx(beklenen, rel=1e-9), (
            f'{ad}: yayımlanan Ns {ns:.1f}, kartın kendi üçlüsünden '
            f'türetilen {beklenen:.1f} — ayrışmış')
        sinif = p['specific_speed_band_status']
        beklenen_sinif = ('below_centrifugal_band' if ns < NS_CENTRIFUGAL_MIN_US
                          else 'above_centrifugal_band'
                          if ns > NS_CENTRIFUGAL_MAX_US
                          else 'in_centrifugal_band')
        assert sinif == beklenen_sinif, (
            f'{ad}: Ns {ns:.1f} US için sınıf {sinif}, band '
            f'{NS_CENTRIFUGAL_MIN_US:g}-{NS_CENTRIFUGAL_MAX_US:g}')

    def test_devir_emme_sinirinin_derate_kati(self, besleme_25kn):
        """Devrin kaynağı ADIYLA doğrulanır: sınır × SPEED_DERATE_DEFAULT.

        ÖLÇÜLDÜ: yakıt 52 711 rpm / emme sınırı 58 568 rpm = 0,900.
        Bu ilişki bekçisi, eski 60 000 rpm SAYI tavanının yerine geçer:
        devir bandı modelle birlikte kayabilir, ama devrin NEREDEN geldiği
        kaymamalıdır.
        """
        from hrma.analysis.turbopump_sizing import G_0, SPEED_DERATE_DEFAULT
        import math

        for ad in ('oxidizer_pump', 'fuel_pump'):
            p = besleme_25kn[ad]
            npsh_a = float(p['npsh_available'])
            assert npsh_a > 0.0, f'{ad}: NPSH_a <= 0, devir seçimi anlamsız'
            omega_ss = float(p['suction_specific_speed_dimensionless'])
            q = float(p['volumetric_flow_m3_s'])
            omega_limit = omega_ss * (npsh_a * G_0) ** 0.75 / q ** 0.5
            rpm_limit = omega_limit * 60.0 / (2.0 * math.pi)
            assert float(p['rotational_speed']) == pytest.approx(
                rpm_limit * SPEED_DERATE_DEFAULT, rel=1e-3), (
                f'{ad}: devir {p["rotational_speed"]:.0f} rpm, emme sınırı '
                f'{rpm_limit:.0f} rpm × {SPEED_DERATE_DEFAULT:g} = '
                f'{rpm_limit * SPEED_DERATE_DEFAULT:.0f} rpm — devrin '
                'kaynağı ayrışmış')


# ===========================================================================
# P4B4-07 — VERİ BORCU (engelli): sözleşme çürümesin
# ===========================================================================
class TestP4B407VeriBorcuCurumesin:
    """Borç kapanmadı; kapanış ŞARTLARI kilitlenir.

    D27'de altı itici (lh2, methane, mmh, udmh, h2o2, n2o4) için kaynak
    künyeli kayıt KAZANILAMAMIŞTI, sayı uydurulmadı ve harita büyütülmedi.
    Borcun sessizce çürümemesi için iki ayak kilitlendi: (a) haritasız itici
    için ürün su koçu bağlamasını HİÇ üretmemeli, (b) haritaya bir itici
    EKLENDİĞİNDE onun yoğunluğu merkezî itici tablosuyla AYNI olmalı ve
    künyesi dolu olmalı.

    ÖH D31 · P4B4-07 / OH-D27-08 — BORCUN BÜYÜK KISMI ÖDENDİ (bekçi
    ÇEVRİLDİ, GEVŞETİLMEDİ). Beş itici (lh2, methane, mmh, udmh, n2o4)
    birincil kaynaklı kayıtla haritaya girdi; harita kapsaması ÖLÇÜLDÜ:
    2/9 -> 7/9, üretilen su koçu bloğu 2 -> 7. (a) ayağının listesi bu
    yüzden KALAN iki iticiye indi: ``h2o2`` (buhar basıncı kaynağı
    kazanılamadı -> fail-closed) ve ``n2o`` (kaydı kanona taşındı ama
    haritaya alınması ürün kapsamı kararı). (b) ayağı GEVŞEMEDİ, tersine
    artık iki değil YEDİ itici ölçüyor ve n2o'nun 785 ⟷ 745 kg/m³
    ayrışması D31'de kapandığı için o ayrışmayı geri getirecek her
    değişiklik kırmızıya düşer.
    """

    #: (a) ayağının KALAN kapsamı — bu liste yalnız borç ödendikçe KISALIR;
    #: buraya bir itici GERİ eklemek borcu yeniden açmak demektir.
    HARITASIZ_KALAN = ('h2o2', 'n2o')

    def test_haritasiz_itici_icin_baglama_URETILMEZ(self):
        from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

        for itici in self.HARITASIZ_KALAN:
            anahtar, kayit = LiquidRocketEngine._feed_fluid_record(itici)
            assert anahtar is None and kayit is None, (
                f'{itici} haritaya girmiş: kaydın künyesi ve merkezî tabloyla '
                'tutarlılığı ayrıca sınanmalı (aşağıdaki bekçi)')

    def test_odenen_borc_GERI_ALINAMAZ(self):
        """D31'de haritaya giren beş itici bir daha haritadan düşemez.

        Ters yön kilidi: yukarıdaki (a) ayağı yalnız KALAN boşluğu ölçer;
        ödenen kısmı hiçbir şey tutmazsa harita sessizce küçülebilir ve
        kullanıcı su koçu bloğunu kaybeder. Bu bekçi onu tutar.
        """
        from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

        for itici in ('lh2', 'methane', 'mmh', 'udmh', 'n2o4'):
            anahtar, kayit = LiquidRocketEngine._feed_fluid_record(itici)
            assert anahtar == itici and kayit is not None, (
                f'{itici} haritadan düşmüş: D31/P4B4-07 ile ödenen veri '
                'borcu geri alınamaz')

    def test_haritadaki_her_itici_KUNYELI_ve_merkezle_TUTARLI(self):
        from hrma.analysis.water_hammer import FLUID_PROPERTIES
        from hrma.data.propellant_database import PropellantDatabase
        from hrma.engines.liquid_rocket_engine import (
            LiquidRocketEngine, WATER_HAMMER_FLUID_KEY)

        db = PropellantDatabase()
        iticiler = (db.get_propellant_list('liquid_fuels')
                    + db.get_propellant_list('oxidizers'))
        assert WATER_HAMMER_FLUID_KEY, 'harita boşalmış'
        for itici in iticiler:
            _anahtar, kayit = LiquidRocketEngine._feed_fluid_record(itici)
            if kayit is None:
                continue
            for alan in ('bulk_modulus_Pa', 'density_kg_m3',
                         'vapor_pressure_Pa', 'source',
                         'vapor_pressure_source'):
                assert kayit.get(alan), (
                    f'{itici}: su koçu kaydında {alan} yok — kaynak künyesiz '
                    'sayı haritaya giremez (P4B4-07 veri borcu)')
            rho_merkez = float(db.get_propellant_properties(itici)['density'])
            assert float(kayit['density_kg_m3']) == pytest.approx(
                rho_merkez, rel=1e-9), (
                f'{itici}: su koçu tablosu {kayit["density_kg_m3"]} kg/m³, '
                f'merkezî itici tablosu {rho_merkez} kg/m³ — iki kaynak '
                'ayrışmış (n2o kanon-T kararı bu ayrışmanın adıdır)')
        # Tablo anahtarları ile haritanın hedefleri ayrışamaz.
        for hedef in set(WATER_HAMMER_FLUID_KEY.values()):
            assert hedef in FLUID_PROPERTIES, (
                f'harita {hedef!r} diyor ama tabloda böyle bir kayıt yok')
