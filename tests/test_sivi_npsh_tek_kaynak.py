"""B5 (v2.6.27) — sıvı motor NPSH zinciri TEK KAYNAK bekçileri.

ÖLÇÜLEN KUSUR (25 kN LOX/RP-1 örneği, 2026-08-14/15 teşhisi, HEAD 9e1410b):
aynı yanıt NPSH hakkında üç farklı ve üçü de yanlış şey söylüyordu.

1. ``performance_margins.npsh_margin = 2e-14`` — devir doğrudan kavitasyon
   sınırından seçildiği için NPSH_gerekli ≡ NPSH_mevcut idi; kendi basis
   metni bunu "equals by construction" diye İTİRAF ediyordu. Totolojik ölü
   metrik; ``npsh_insufficient`` uyarısı cebirsel olarak ULAŞILAMAZDI.
2. ``turbopump_analysis.fuel_pump.npsh_available = 25,01 m`` — RP-1'e SABİT
   1,013 bar buhar basıncı (gerçek ~0,007 bar) uygulanmış ve hat kaybı HİÇ
   düşülmemişti: NPSH şişkin, yakıt pompası 78 607 rpm'e fırlamıştı.
3. ``turbopump_sizing.fuel_pump`` modül tarafı aynı pompaya NPSH_a = -14,4 m
   diyordu, çünkü hattın TAMAMI (ana vana + 2,5 m dirsekli koşu dahil)
   emmeden düşülüyordu — ana vana ve dirsekli koşu pompanın BASMASINDADIR.

DÜZELTME SÖZLEŞMESİ (bu dosyanın kilitlediği):

* NPSH_a TEK kaynaktan: motorun ``_design_pump``'ı da modül bağlaması da
  ``turbopump_sizing.npsh_available_m`` (Eş. 1) üzerinden, GERÇEK buhar
  basıncı kaydı ve YALNIZ EMME tarafı hat kaybıyla hesaplar. İki değer
  birbirine 1e-9 bağıl hatayla eşittir.
* Devir emme sınırının SPEED_DERATE_DEFAULT (0,90; modülden İTHAL, ikinci
  bir 0,9 tanımı yok) katıdır; marj tavansız noktada derate^(-4/3)-1 ≈ %15
  olur — artık totolojik değil.
* NPSH_a ≤ 0 vakası GÖRÜNÜRDÜR: critical
  ``warn.liquid.npsh_pressurization_insufficient`` ateşler.
* Buhar basıncı kaydı olmayan itici için NBP yedeği SESSİZ DEĞİLDİR:
  ``warn.liquid.npsh_vapor_pressure_assumed`` + basis beyanı.
* Eski devir sınıfı (yakıt 78 607 / oks 49 479 rpm) geri gelmez; ölçülen
  yeni sınıf (her iki pompa ~35-36 bin rpm) bant olarak kilitlenir.

Her test mutasyon hedefini docstring'inde söyler: hangi geri dönüş bu
bekçiyi kırar. Sayılar bu depoda ÖLÇÜLDÜ (2026-08-15); testler ölçümün
kendisini değil, ölçümün gösterdiği doğru sözleşmeyi korur.
"""

import contextlib
import io
import json
import math
import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from hrma.constants import G_0, PA_PER_BAR                # noqa: E402
from hrma.analysis.turbopump_sizing import (              # noqa: E402
    NSS_INDUCER_DESIGN_US,
    NSS_NO_INDUCER_MAX_US,
    SPEED_DERATE_DEFAULT,
)
from hrma.analysis.water_hammer import FLUID_PROPERTIES   # noqa: E402
from hrma.engines.liquid_rocket_engine import (           # noqa: E402
    FEED_K_FILTER,
    FEED_K_TANK_OUTLET,
    FEED_SUCTION_LINE_LENGTH_M,
    LiquidRocketEngine,
    PUMP_NPSH_VAPOR_PRESSURE_BAR,
    PUMP_SUCTION_SPECIFIC_SPEED,
    PUMP_SUCTION_SPECIFIC_SPEED_US,
)

#: Ağ yok: motora boş ama VAR olan itici verisi enjekte edilir
#: (test_liquid_real_inputs ile aynı çevrimdışı desen).
OFFLINE_PROPELLANTS = {'rp1': {}, 'lox': {}}

#: Teşhisin yapıldığı örnek — alanlar dosyadan okunur ki test ile örnek
#: sessizce ayrışamasın (parametre tutarlılığı kuralı: ikinci kopya yok).
ORNEK_DOSYA = os.path.join(REPO_ROOT, 'examples',
                           'Example Liquid LOX-RP1 25kN.hrma')

#: /calculate_liquid uç noktasının kurucuya taşıdığı alanlar; gerisi
#: overrides sözlüğünden okunur (test_liquid_declarations ile aynı harita).
CTOR_ALANLARI = ('thrust', 'chamber_pressure', 'mixture_ratio', 'fuel_type',
                 'oxidizer_type', 'cooling_type', 'injector_type')


def _ornek_alanlari():
    with open(ORNEK_DOSYA, encoding='utf-8') as f:
        return json.load(f)['inputs']['fields']


@pytest.fixture(scope='module')
def cift_25kn():
    """(motor, sonuç) — 25 kN LOX/RP-1 örneği, teşhisle aynı girdi."""
    fields = _ornek_alanlari()
    ctor = {k: fields[k] for k in CTOR_ALANLARI if k in fields}
    ctor['propellant_data'] = OFFLINE_PROPELLANTS
    overrides = {k: v for k, v in fields.items() if k not in CTOR_ALANLARI}
    with contextlib.redirect_stdout(io.StringIO()):
        engine = LiquidRocketEngine(overrides=overrides, **ctor)
        return engine, engine.calculate_performance()


@pytest.fixture(scope='module')
def besleme(cift_25kn):
    return cift_25kn[1]['detailed_feed_system']


def _birim_motor():
    """Ucuz motor örneği — yalnız ``_design_pump``'ı doğrudan çağırmak için."""
    return LiquidRocketEngine(thrust=10000, chamber_pressure=100,
                              mixture_ratio=2.5, fuel_type='rp1',
                              oxidizer_type='lox',
                              propellant_data=OFFLINE_PROPELLANTS,
                              overrides={})


#: _design_pump'ın hattan okuduğu üç alanla sentetik emme hattı. 8 m/s tavan
#: hızında dinamik basınç 0,259 bar; K=10 süzgeç baskın kalemdir.
SENTETIK_HAT = {'line_velocity_m_s': 8.0, 'line_diameter_mm': 25.0,
                'friction_factor': 0.02}


def _emme_kaybi_bar(line, rho):
    """Beklenen emme kaybı — sözleşmenin BAĞIMSIZ yeniden hesabı [bar].

    Emme kümesi: tank çıkışı K + süzgeç K + FEED_SUCTION_LINE_LENGTH_M
    üzerinden Darcy. Ana vana ve dirsekli 2,5 m koşu BASMA tarafıdır ve
    burada YOKTUR — tam-hat düşümüne dönüş bu yardımcıyla eşitliği bozar.
    """
    dyn = 0.5 * rho * float(line['line_velocity_m_s']) ** 2
    d = float(line['line_diameter_mm']) / 1000.0
    k_toplam = (FEED_K_TANK_OUTLET + FEED_K_FILTER
                + float(line['friction_factor'])
                * FEED_SUCTION_LINE_LENGTH_M / d)
    return k_toplam * dyn / PA_PER_BAR


# ---------------------------------------------------------------------------
# 1) Buhar basıncı: gerçek kayıt, sabit değil
# ---------------------------------------------------------------------------
class TestBuharBasinci:

    def test_rp1_npsh_gercek_buhar_basinciyla(self, cift_25kn, besleme):
        """RP-1 NPSH'ı 700 Pa kayıtla kurulmalı, 1,013 bar sabitiyle DEĞİL.

        Mutasyon hedefi: ``_design_pump`` PUMP_NPSH_VAPOR_PRESSURE_BAR
        sabitine geri dönerse ``vapor_pressure_Pa`` 101325 olur ve NPSH_a
        ~12,7 m şişer — iki iddia da kırılır.
        """
        motor, _ = cift_25kn
        yakit = besleme['turbopump_analysis']['fuel_pump']
        kayit = FLUID_PROPERTIES['rp1']
        assert yakit['vapor_pressure_Pa'] == kayit['vapor_pressure_Pa'], (
            'Yakıt pompası NPSH buhar basıncı su koçu tablosunun RP-1 '
            'kaydından gelmeli (tek kaynak)')
        assert yakit['vapor_pressure_source'] == kayit['vapor_pressure_source']
        # NPSH_a bağımsız yeniden hesap: (p_tank - dp_emme - p_v)/(rho*g).
        tank_pa = besleme['tank_pressure_bar'] * PA_PER_BAR
        beklenen = ((tank_pa - yakit['suction_line_dp_bar'] * PA_PER_BAR
                     - kayit['vapor_pressure_Pa'])
                    / (motor.rho_fuel * G_0))
        assert yakit['npsh_available'] == pytest.approx(beklenen, rel=1e-9)
        # Sabitle kurulmuş NPSH bariz farklı olurdu (RP-1'de ~12,7 m fark).
        sabitle = ((tank_pa - yakit['suction_line_dp_bar'] * PA_PER_BAR
                    - PUMP_NPSH_VAPOR_PRESSURE_BAR * PA_PER_BAR)
                   / (motor.rho_fuel * G_0))
        assert abs(yakit['npsh_available'] - sabitle) > 5.0, (
            'Gerçek kayıtla sabit varsayım ayırt edilemiyorsa bekçi kördür')

    def test_kayitsiz_iticide_yedek_yuksek_sesle(self):
        """Tablosuz itici: NBP yedeği uygulanır ama SESSİZ DEĞİLDİR.

        Mutasyon hedefi: yedek düşüşü uyarısız/beyansız yapılırsa (eski
        davranış) uyarı kaydı ve basis metni kaybolur — ikisi de aranır.
        """
        # ÖH D31 · P4B4-07: örnek itici METAN'dan ETHANOL'e taşındı — metan
        # artık su koçu / besleme tablosunda kayıtlıdır (birincil kaynaklı
        # NIST WebBook girdisi), dolayısıyla 'kayıtsız itici' örneği olamaz.
        # Motorun desteklediği çiftler arasında kaydı olmayan tek itici
        # ethanol'dür. İddia değişmedi: yedek düşüşü SESSİZ olamaz.
        motor = _birim_motor()
        sonuc = motor._design_pump(2.0, 420.0, 100.0, 30.0,
                                   propellant='ethanol', line=SENTETIK_HAT)
        assert sonuc['vapor_pressure_Pa'] == pytest.approx(
            PUMP_NPSH_VAPOR_PRESSURE_BAR * PA_PER_BAR)
        assert 'record missing' in sonuc['vapor_pressure_source']
        kodlar = {(w['code'], w['severity']) for w in motor.design_warnings}
        assert ('warn.liquid.npsh_vapor_pressure_assumed',
                'warning') in kodlar, (
            'NBP yedeğine sessiz düşüş yasak: uyarı üretilmeli')


# ---------------------------------------------------------------------------
# 2) Emme / basma ayrımı
# ---------------------------------------------------------------------------
class TestEmmeBasmaAyrimi:

    def test_ana_vana_npshtan_dusulmuyor(self, cift_25kn, besleme):
        """NPSH kaybı yalnız emme kalemleri; ana vana + dirsekli koşu hariç.

        Mutasyon hedefi: tam-hat düşümüne (tank_outlet + main_valve +
        filters + feed_lines) dönüş, yayımlanan emme kaybını bağımsız
        yeniden hesaptan koparır — teşhisteki -14,4 m NPSH bu yoldan
        geliyordu.
        """
        motor, _ = cift_25kn
        drops = motor._calculate_feed_system_pressure_drops()
        for ad, hat_adi, rho in (('oxidizer_pump', 'oxidizer_line',
                                  motor.rho_ox),
                                 ('fuel_pump', 'fuel_line',
                                  motor.rho_fuel)):
            pompa = besleme['turbopump_analysis'][ad]
            hat = drops[hat_adi]
            beklenen = _emme_kaybi_bar(hat, rho)
            assert pompa['suction_line_dp_bar'] == pytest.approx(
                beklenen, rel=1e-9), f'{ad}: emme kümesi sözleşme dışı'
            tam_hat = sum(hat[k] for k in ('tank_outlet', 'main_valve',
                                           'filters', 'feed_lines'))
            assert pompa['suction_line_dp_bar'] < tam_hat, (
                f'{ad}: emme kaybı tam hat kaybından KÜÇÜK olmalı '
                '(ana vana ve dirsekli koşu basmadadır)')
            # Modül bağlaması AYNI emme kümesini okumalı (iki yer tek sabit).
            modul = besleme['turbopump_sizing'][ad]
            assert modul['line_pressure_drop_bar'] == pytest.approx(
                pompa['suction_line_dp_bar'], rel=1e-12), (
                f'{ad}: motor ve modül farklı hat kaybı görüyor')

    def test_emme_dokumu_yayimlanir(self, besleme):
        """Döküm (tank çıkışı / süzgeç / emme borusu) beyanla çıktıdadır."""
        pompa = besleme['turbopump_analysis']['fuel_pump']
        dokum = pompa['suction_loss_breakdown_bar']
        assert set(dokum) == {'tank_outlet', 'filters', 'suction_line',
                              'total'}
        assert dokum['total'] == pytest.approx(
            dokum['tank_outlet'] + dokum['filters'] + dokum['suction_line'])
        # K=10 süzgeç tahmini baskın kalemdir ve basis bunu beyan eder.
        assert 'clean-element estimate' in pompa['npsh_available_basis']
        assert 'main valve' in pompa['npsh_available_basis'].lower() or \
            'MAIN VALVE' in pompa['npsh_available_basis'].upper()


# ---------------------------------------------------------------------------
# 3) Tek kaynak: motor NPSH'ı == modül NPSH'ı
# ---------------------------------------------------------------------------
class TestTekKaynak:

    def test_motor_ve_modul_ayni_npsh(self, besleme):
        """Aynı yanıtta iki farklı NPSH gerçeği olamaz (rel 1e-9).

        Mutasyon hedefi: motorun kendi NPSH formülüne dönüşü (eski sabit
        buharlı, hat kayıpsız satır) iki değeri ayırır — teşhiste fark
        25,01 m'ye karşı -14,4 m idi.
        """
        for ad in ('oxidizer_pump', 'fuel_pump'):
            motor_p = besleme['turbopump_analysis'][ad]
            modul_p = besleme['turbopump_sizing'][ad]
            assert modul_p['status'] == 'modelled'
            assert motor_p['npsh_available'] == pytest.approx(
                modul_p['npsh']['available_m'], rel=1e-9), f'{ad} NPSH_a'
            assert motor_p['npsh_required'] == pytest.approx(
                modul_p['npsh']['required_m'], rel=1e-9), f'{ad} NPSH_r'

    def test_emme_kabiliyeti_tek_tanimdan(self, besleme):
        """Modül hedef Nss'i motorun Ω_ss=8 köprüsünden alır (30000 değil).

        Motorun boyutsuz 8,0 değeri kesin birim köprüsüyle ~21 864 US eder:
        indüsersiz tavanın (11 000) ÜSTÜNDE, indüserli tasarım varsayılanının
        (30 000) ALTINDA — indüserli sınıf. Mutasyon hedefi: modülün 30 000
        varsayılanına dönüş hem hedefi hem NPSH_req'i kaydırır.
        """
        assert NSS_NO_INDUCER_MAX_US < PUMP_SUCTION_SPECIFIC_SPEED_US \
            < NSS_INDUCER_DESIGN_US
        for ad in ('oxidizer_pump', 'fuel_pump'):
            modul_p = besleme['turbopump_sizing'][ad]
            assert modul_p['npsh'][
                'suction_specific_speed_capability_us'] == pytest.approx(
                    PUMP_SUCTION_SPECIFIC_SPEED_US, rel=1e-12)

    def test_devir_emme_sinirinin_derate_katidir(self, besleme):
        """Motor devri = SPEED_DERATE_DEFAULT x modülün emme sınırı devri.

        Modül üst devri kendi ABD-birim zinciriyle, motor kendi boyutsuz
        zinciriyle hesaplar; ikisi ancak TEK NPSH + TEK Ω_ss + TEK derate
        varsa üst üste düşer. Mutasyon hedefi: ikinci bir 0,9 literali,
        farklı Nss ya da farklı NPSH bu eşitliği bozar.
        """
        for ad in ('oxidizer_pump', 'fuel_pump'):
            motor_p = besleme['turbopump_analysis'][ad]
            modul_p = besleme['turbopump_sizing'][ad]
            assert 'SPEED_DERATE_DEFAULT' in motor_p['speed_source'], (
                f'{ad}: bu test tavansız tasarım noktası ister')
            assert motor_p['rotational_speed'] == pytest.approx(
                SPEED_DERATE_DEFAULT
                * modul_p['shaft_speed']['suction_limited_max_rpm'],
                rel=1e-9), f'{ad}: derate tek kaynak değil'


# ---------------------------------------------------------------------------
# 4) Marj artık totolojik değil
# ---------------------------------------------------------------------------
class TestGercekMarj:

    def test_marj_derate_orani_kadar(self, besleme):
        """Tavansız tasarım noktasında marj = derate^(-4/3)-1 ≈ %15,1 > %5.

        Mutasyon hedefi: devrin tam kavitasyon sınırından seçilmesine dönüş
        marjı ~1e-14'e düşürür (teşhisteki ölü metrik).
        """
        marj = besleme['performance_margins']['npsh_margin']
        beklenen = (SPEED_DERATE_DEFAULT ** (-4.0 / 3.0) - 1.0) * 100.0
        assert marj == pytest.approx(beklenen, abs=0.5)
        assert marj > 5.0
        assert marj != pytest.approx(0.0, abs=1e-9), 'Totolojik marj döndü'

    def test_marj_beyani_yeni_sozlesmeyi_anlatir(self, besleme):
        """'by construction' itirafı tarihe karıştı; beyan derate'i söyler."""
        basis = besleme['performance_margins']['npsh_margin_basis']
        assert 'by construction' not in basis or \
            'zero-by-construction' in basis, (
            'Eski totoloji beyanı geri gelmiş olabilir')
        assert 'SPEED_DERATE_DEFAULT' in basis
        assert 'binding (worst) pump' in basis, (
            'Marj iki pompanın KÖTÜSÜNÜ raporlamalı (eski kod yalnız '
            'oksitleyiciye bakıyordu)')

    def test_npsh_required_basis_derate_iliskisini_soyler(self, besleme):
        for ad in ('oxidizer_pump', 'fuel_pump'):
            basis = besleme['turbopump_analysis'][ad]['npsh_required_basis']
            assert 'no longer equal by construction' in basis
            assert 'SPEED_DERATE_DEFAULT' in basis


# ---------------------------------------------------------------------------
# 5) Uyarılar ULAŞILABİLİR
# ---------------------------------------------------------------------------
class TestKavitasyonUyarisi:

    def test_dusuk_tank_basincinda_critical_ateslenir(self):
        """1 bar tanklı RP-1 pompası: NPSH_a ≤ 0 GÖRÜNÜR olmalı.

        Emme kaybı (~2,8 bar; K=10 süzgeç baskın) 1 bar tankı aşar. Eski
        kod bu vakada NPSH'ı 1e3 Pa tabanına SESSİZCE kırpıp tasarıma devam
        ediyordu; teşhisteki -14,4 m vaka hiçbir uyarı üretmemişti.
        Mutasyon hedefi: uyarının kaldırılması ya da NPSH'ın pozitif tabana
        kırpılıp RAPORLANMASI iki iddiadan birini kırar.
        """
        motor = _birim_motor()
        sonuc = motor._design_pump(5.0, 810.0, 100.0, 1.0,
                                   propellant='rp1', line=SENTETIK_HAT)
        assert sonuc['npsh_available'] < 0.0, (
            'Gerçek (negatif) NPSH raporlanmalı; pozitif taban uydurmadır')
        kodlar = {(w['code'], w['severity']) for w in motor.design_warnings}
        assert ('warn.liquid.npsh_pressurization_insufficient',
                'critical') in kodlar
        assert ('warn.liquid.npsh_insufficient', 'critical') in kodlar, (
            'npsh_insufficient artık ulaşılabilir olmalı '
            '(eskiden cebirsel olarak imkânsızdı)')
        assert 'NOT feasible' in sonuc['speed_source']

    def test_saglikli_tasarimda_critical_yok(self, cift_25kn):
        """25 kN örneği sağlıklıdır: kavitasyon uyarısı YANLIŞ ateşlenmez."""
        motor, _ = cift_25kn
        kodlar = {w['code'] for w in motor.design_warnings}
        assert 'warn.liquid.npsh_pressurization_insufficient' not in kodlar
        assert 'warn.liquid.npsh_insufficient' not in kodlar


# ---------------------------------------------------------------------------
# 6) Devir sınıfı ve mil mimarisi
# ---------------------------------------------------------------------------
class TestDevirVeMil:

    def test_eski_devir_sinifi_geri_gelmedi(self, besleme):
        """Şişkin NPSH devirleri (yakıt 78 607 / oks 49 479) tarihe karıştı.

        ASIL İDDİA (hiç gevşemedi): ESKİ sınıfa dönüş — yakıt > 60 000,
        oks > 45 000 rpm — kırar. Bu iki tavan 2026-08-15'ten beri AYNI.

        ÇAPA YENİLENDİ (ÖH D26 / fix-25b). Eski çapa 2026-08-15 ölçümüydü
        (oks 35 855 / yakıt 36 146, ±%20). O tarihten SONRA besleme-NPSH
        zinciri BEŞ ayrı kulvarda bilinçli olarak değişti; çapa bayatladı:
          * D15 sıvı a2 (23784aa, 31 Ağu) — P3B3-04: hat çapı artık HIZ
            BANDINA göre seçiliyor; oks hattındaki 11,03 m/s tavan ihlali
            kalktı. BASKIN SEBEP BUDUR.
          * D18 fizik-a2 (94c96e5, 2 Eyl) — tank basıncı NPSH'e bağlandı.
          * D18 sıvı a1 (b3fb65e, 2 Eyl) — P3B3-09 hat cinsi argümanı.
          * D20 sıvı a1 (ef571cb, 3 Eyl) — hat çapı seçimi.
          * D21 sıvı a1 (c4891b3, 4 Eyl) — OH-D20-09 TEK MARJ sözleşmesi
            (SP-8107 1,25 çarpanı SP-8109 hız-yükü kuralının ÜSTÜNE
            yığılmıyor) + P3B4-10 dejenere NPSH marjı.

        DEĞİŞİM TÜRETİLDİ, "sayı oynatılmadı". Zincir:
        NPSH_a = k_v·c_m²/(2g) (SP-8109 §3.2.1.2) ve
        ω = ω_ss·(NPSH·g)^(3/4)/√Q  ⇒  devir ∝ c_m^1,5 (sabit Q'da).
        Oks giriş hızı 11,03 → 5,717 m/s olunca beklenen devir
        35 855·(5,717/11,03)^1,5 = 13 379 rpm; ÖLÇÜLEN 14 103,9 rpm
        (sapma +%5,4 — kalanı tek-marj sözleşmesi ve Q değişimi).
        Yani düşüş, bandın kendisinin onarımının DOĞRUDAN sonucudur.

        YENİ ÇAPA (bu depo, D26 fix-25b): oks 14 103,9 / yakıt 51 380,2
        rpm, aynı ±%20 payla (pay BÜYÜTÜLMEDİ). Oks artık yöneten pompa:
        NPSH_a'sı hız-yükü tabanına oturuyor, yakıtta artı NPSH kalıyor.

        UYARI (D26 sıvı kulvarına): yakıt devri çapadan +%42 yükseldi
        (36 146 → 51 380) ve ESKİ sınıf tavanının (60 000) %86'sına
        geldi. Kırmızı değil ama yön eski sınıfa DOĞRU; bir sonraki
        besleme değişikliği bu tavanı zorlarsa bekçi kıracaktır.
        """
        oks = besleme['turbopump_analysis']['oxidizer_pump']
        yakit = besleme['turbopump_analysis']['fuel_pump']
        # 1) ASIL İDDİA — eski şişkin sınıfa dönüş yok (tavanlar sabit).
        assert oks['rotational_speed'] < 45000, (
            f"Oks devri {oks['rotational_speed']:.0f} rpm ESKİ şişkin "
            'sınıfa (>45 000) döndü')
        assert yakit['rotational_speed'] < 60000, (
            f"Yakıt devri {yakit['rotational_speed']:.0f} rpm ESKİ şişkin "
            'sınıfa (>60 000) döndü')
        # 2) YENİLENEN ÇAPA — ölçülen sınıf ±%20 (pay büyütülmedi).
        assert 11283 < oks['rotational_speed'] < 16925, (
            f"Oks devri {oks['rotational_speed']:.0f} rpm yenilenen "
            'çapanın (14 103,9 ±%20) dışında')
        assert 41104 < yakit['rotational_speed'] < 61656, (
            f"Yakıt devri {yakit['rotational_speed']:.0f} rpm yenilenen "
            'çapanın (51 380,2 ±%20) dışında')
        # Türbin oks miline boyutlanır.
        turbin = besleme['turbopump_analysis']['turbine']
        assert turbin['rotational_speed'] == pytest.approx(
            oks['rotational_speed'])

    def test_devir_kendi_yayimladigi_tabandan_turetilebiliyor(self, besleme):
        """Devir, kartın KENDİ yayımladığı NPSH ve debiden yeniden kurulur.

        ÇAPA YENİLEMESİNİN BEKÇİSİ (ÖH D26 / fix-25b): yukarıdaki bant bir
        SAYI çapasıdır ve model geliştikçe yine kayabilir. Bu test sayıyı
        değil İLİŞKİYİ kilitler — kart hangi devri yayımlarsa yayımlasın,
        o devir kendi künyesindeki tanımı sağlamak ZORUNDADIR:

            NPSH_req = (ω·√Q / ω_ss)^(4/3) / g   (kartın npsh_required_basis
            cümlesinin birebir kendisi)  ⇒  ω = ω_ss·(NPSH_req·g)^(3/4)/√Q

        Böylece devir ile NPSH sessizce ayrışamaz (biri elle oynatılırsa
        kırar) ve bant kayması bir daha "ölçülmemiş sayı" olarak geçmez.
        """
        for ad in ('oxidizer_pump', 'fuel_pump'):
            p = besleme['turbopump_analysis'][ad]
            omega_ss = float(p['suction_specific_speed_dimensionless'])
            npsh_req = float(p['npsh_required'])
            q = float(p['volumetric_flow_m3_s'])
            omega = omega_ss * (npsh_req * G_0) ** 0.75 / q ** 0.5
            rpm_turetilmis = omega * 60.0 / (2.0 * math.pi)
            assert p['rotational_speed'] == pytest.approx(
                rpm_turetilmis, rel=1e-3), (
                f'{ad}: yayımlanan devir {p["rotational_speed"]:.1f} rpm, '
                f'kendi NPSH/debi künyesinden türetilen {rpm_turetilmis:.1f} '
                'rpm — devir ile NPSH ayrışmış')

    def test_mil_mimarisi_beyani_yayimlanir(self, besleme):
        """Devirler farklıysa dişli/çift-mil varsayımı SÖYLENMELİDİR."""
        not_metni = besleme['turbopump_analysis']['shaft_architecture_note']
        assert isinstance(not_metni, str) and not_metni
        assert ('single-shaft' in not_metni
                or 'OXIDIZER pump shaft' in not_metni)

    def test_mil_beyani_dallari(self):
        """Yardımcının iki dalı: eşit devir tek mil, farklı devir dişli."""
        esit = LiquidRocketEngine._shaft_architecture_note(
            {'rotational_speed': 36000.0}, {'rotational_speed': 36100.0})
        assert 'single-shaft' in esit
        farkli = LiquidRocketEngine._shaft_architecture_note(
            {'rotational_speed': 36000.0}, {'rotational_speed': 120000.0})
        assert 'OXIDIZER pump shaft' in farkli
        assert 'gearbox' in farkli

    def test_omega_ss_tek_tanim(self):
        """Ω_ss=8 ile US köprüsü tutarlı: ~2733 çarpanı bağımsız doğrulanır.

        Mutasyon hedefi: köprü katsayısının elle yazılmış İKİNCİ bir 2733
        literaline ya da farklı bir Ω_ss'e ayrışması.
        """
        assert PUMP_SUCTION_SPECIFIC_SPEED == pytest.approx(8.0)
        # Bağımsız türetme: Nss_US/Ω_ss = (60/2π)·g^0.75·√(1/gpm)·ft^0.75.
        m3s_per_gpm = 231.0 * 0.0254 ** 3 / 60.0
        carpan = ((60.0 / (2.0 * 3.141592653589793)) * G_0 ** 0.75
                  / m3s_per_gpm ** 0.5 * 0.3048 ** 0.75)
        assert PUMP_SUCTION_SPECIFIC_SPEED_US == pytest.approx(
            PUMP_SUCTION_SPECIFIC_SPEED * carpan, rel=1e-12)
