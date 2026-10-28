"""ÖH Dalga-15 · hibrit kulvarı · aşama 1 — beş kusurun bekçileri.

Her bekçi TERS-MUTASYONLA sınandı (onarımı geçici geri al -> test KIRMIZI ->
geri koy -> YEŞİL). Ölçüm dosyaları:
``docs/scofield/raw/OH/D15/hibrit/a1/once.json`` ve ``sonra.json``.

KİLİTLENEN KUSURLAR

P10B3-08 — /hybrid yanıtında kamara malzemesi İKİ ADLA dolaşıyordu:
    ``structural_analysis.design_parameters.material = 'steel_304'``
    (arayüzün gönderdiği TAKMA ad) ⟷
    ``heat_transfer_analysis.design_parameters.material = 'ss_304'``
    (kanonik ad). Panel malzemeyi birinci yoldan okuyor
    (analysis_dock.js:1068) ve select'inin seçenek listesi kanonik adlardan
    kurulu (structural_panel.js:23). Listede olmayan değer atanınca select
    sessizce ilk seçenekte (steel_4130) kalıyor: aynı oda için SF 0,2841
    (ss_304) yerine 0,9593 (4130) — 3,3768 kat İYİMSER, üstelik 0,67
    GÜVENSİZ yerine "güvenli" gösteren yönde.

P1B2-01 — kırpılmış yanmada ``design_summary.performance`` İSTENEN süreyi
    ve impulsu yayımlıyordu: üst düzey 2,8000 s / 8391,73 Ns ⟷ özet
    40,0000 s / 120000,0 Ns (+%1328,57 / +%1329,98 = 14,3 kat). Aynı yanıt
    status = TARGET_NOT_MET diyordu ve blokta tek *_basis alanı yoktu.

P1B1-03 — enjektör zinciri kullanıcının tank sıcaklığını HİÇ okumuyordu:
    tank_temperature = None/280/293,15/305 K'nin dördünde de yoğunluk
    742,933 kg/m³ idi (ayrık değer sayısı = 1), oysa AYNI yanıttaki tank
    blowdown bloğu 785,10 / 870,44 / 785,10 / 661,16 kg/m³ yayımlıyordu.

P1B1-04 — tıkanmamış boğaz rejiminde (Pc/Pa < ((γ+1)/2)^(γ/(γ−1))) tam bir
    tasarım yayımlanıyordu: Pa = 1,0 bar / Pc = 1,0 bar'da ε tavana
    (250,000) dayanıyor, 1 kN'luk motora d_e = 4313 mm çıkış çapı
    yazılıyordu ve TEK uyarı yoktu. ε(Pc) monoton bile değildi.

P1B2-02 — yayımlanan ıraksak lüle boyu ÇİZİLEN/İHRAÇ EDİLEN konturdan
    uzundu: bell 141,1969 ⟷ 84,3150 mm (+%67,46), parabolik 141,9794 ⟷
    87,5476 mm (+%62,17). Kök, bell konturunda var olmayan bir "yarı
    açı"dan (sabit 11,0°) boy türetmekti.
"""

import numpy as np
import pytest

from hrma.analysis.tank_blowdown import N2OSaturation
from hrma.data.materials_db import MATERIALS
from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from tests.bagimlilik_kapisi import kapi


def _motor(**kw):
    taban = dict(thrust=3000.0, burn_time=10.0, of_ratio=6.0,
                 chamber_pressure=30.0, atmospheric_pressure=1.0,
                 fuel_type='htpb', oxidizer_type='n2o',
                 track_performance=True)
    taban.update(kw)
    return HybridRocketEngine(**taban)


@pytest.fixture(scope='module')
def sonuc_ss304():
    m = _motor(chamber_material='steel_304')
    return m, m.calculate()


@pytest.fixture(scope='module')
def sonuc_kirpilmis():
    """ESKİ kırpılan koşu — v3.0.1 kulvar P'de reddedilir; fikstür artık
    AYNI görevin zarfa sığan en küçük kamarasıyla koşar.

    Eski girdi (40 s, D_ilk 50 mm, kamara 70 mm) kaynaksız 0,8·D_ch
    kırpmasıyla 2,8 s'te kesilip TARGET_NOT_MET yayımlanıyordu. Ana model
    kararıyla kırpma söküldü: zarfı aşan istek ``GrainEnvelopeError`` ile
    adıyla reddedilir ve ret gereken en küçük kamara çapını söyler. Özet ⟷
    manşet sözleşmesi (P1B2-01) o çapla koşan GEÇERLİ tasarımda sınanır.
    """
    from hrma.engines.hybrid_rocket_engine import GrainEnvelopeError
    kw = dict(burn_time=40.0, initial_port_diameter=0.050,
              expansion_ratio=4.0, l_star=1.0)
    with pytest.raises(GrainEnvelopeError) as e:
        _motor(chamber_diameter_input=70.0, **kw).calculate()
    gereken = e.value.invalid_fields[0]['required_min']
    m = _motor(chamber_diameter_input=gereken, **kw)
    return m, m.calculate()


@pytest.fixture(scope='module')
def sonuc_bell():
    m = _motor(nozzle_type='bell', expansion_ratio=8.0)
    return m, m.calculate()


class TestP10B308KanonikMalzemeAdi:
    """Kamara malzemesi TEK ve KANONİK adla yayımlanır."""

    def test_takma_ad_kanonige_cozulur(self, sonuc_ss304):
        m, r = sonuc_ss304
        assert m.chamber_material == 'ss_304', (
            "arayüzün 'steel_304' takma adı kanonik materials_db anahtarına "
            f"çözülmeliydi; motor {m.chamber_material!r} tutuyor")
        assert r['chamber_material'] == 'ss_304'
        cozum = r['chamber_material_resolution']
        assert cozum['requested'] == 'steel_304'
        assert cozum['resolved_to'] == 'ss_304'
        assert cozum['resolution'] == 'alias'

    def test_yapisal_ve_termal_ayni_adi_yayimlar(self, sonuc_ss304):
        """İki tüketici zinciri aynı motorun malzemesini aynı adla görür."""
        _m, r = sonuc_ss304
        yapisal = r['structural_analysis']['design_parameters']['material']
        termal = r['heat_transfer_analysis']['design_parameters']['material']
        assert yapisal == termal == 'ss_304', (
            'aynı yanıtta iki malzeme adı: yapısal=%r termal=%r' %
            (yapisal, termal))

    def test_yayimlanan_ad_panel_listesinde_bulunabilir(self, sonuc_ss304):
        """Panel select'i KANONİK adlarla kurulu; yayımlanan ad orada olmalı.

        Bu, kusurun ürün yüzündeki kanadıdır: listede olmayan bir değer
        atanınca select sessizce ilk seçenekte (steel_4130) kalıyordu.
        """
        _m, r = sonuc_ss304
        ad = r['structural_analysis']['design_parameters']['material']
        assert ad in MATERIALS, (
            f'{ad!r} materials_db KANONİK anahtarı değil (takma ad olabilir); '
            'panel seçenek listesi kanonik adlardan kuruluyor, listede '
            'olmayan değer sessizce steel_4130 gösterir')

    def test_ss304_ve_4130_gercekten_ayrisiyor(self):
        """Kusurun ŞİDDET çapası: yanlış malzeme 3,4 kat iyimser SF verir."""
        r304 = _motor(chamber_material='steel_304').calculate()
        r4130 = _motor(chamber_material='steel_4130').calculate()
        sf304 = r304['structural_analysis']['safety_factor']
        sf4130 = r4130['structural_analysis']['safety_factor']
        assert sf4130 / sf304 > 3.0, (
            'iki malzemenin emniyet katsayısı ayrışmıyorsa bu bekçi kusuru '
            f'göremez (sf4130={sf4130!r}, sf304={sf304!r})')


class TestP1B201OzetManseteBagli:
    """design_summary.performance manşetle AYNI sayıyı yayımlar."""

    def test_kirpma_yolu_kapandi_gereken_capla_tam_sure(self, sonuc_kirpilmis):
        # v3.0.1 kulvar P: kırpma yolu kapandı (fikstür ret + en küçük
        # çapla koşu). Gereken çapla tasarım TAM süreyle yayımlanır.
        _m, r = sonuc_kirpilmis
        assert r['burn_time_clipped'] is False
        assert r['design_summary']['status'] != 'TARGET_NOT_MET'

    def test_ozet_suresi_manset_suresiyle_ayni(self, sonuc_kirpilmis):
        _m, r = sonuc_kirpilmis
        ust = float(r['burn_time'])
        ozet = float(r['design_summary']['performance']['burn_time_s'])
        assert ozet == pytest.approx(ust, rel=1e-12), (
            f'özet {ozet:.4f} s ⟷ manşet {ust:.4f} s '
            f'(%{100.0 * (ozet / ust - 1.0):.2f})')

    def test_ozet_impulsu_manset_impulsuyla_ayni(self, sonuc_kirpilmis):
        _m, r = sonuc_kirpilmis
        ust = float(r['total_impulse'])
        ozet = float(r['design_summary']['performance']['total_impulse_Ns'])
        assert ozet == pytest.approx(ust, rel=1e-12), (
            f'özet {ozet:.1f} Ns ⟷ manşet {ust:.1f} Ns '
            f'(%{100.0 * (ozet / ust - 1.0):.2f})')

    def test_istenen_deger_kaybolmaz_ve_kunye_var(self, sonuc_kirpilmis):
        """Teslim edileni yayımlamak, isteneni gizlemek demek değildir."""
        _m, r = sonuc_kirpilmis
        perf = r['design_summary']['performance']
        assert perf['burn_time_requested_s'] == pytest.approx(40.0)
        assert perf['total_impulse_requested_Ns'] == pytest.approx(
            float(r['total_impulse_requested_Ns']))
        assert perf['burn_time_clipped'] is False      # v3.0.1: kırpma yok
        assert 'burn_time_basis' in perf and perf['burn_time_basis']
        assert 'total_impulse_basis' in perf and perf['total_impulse_basis']

    def test_kirpilmayan_kosuda_sayilar_degismez(self):
        """Sözleşme: kırpılma yoksa özet = istenen = teslim edilen."""
        r = _motor().calculate()
        assert r['burn_time_clipped'] is False
        perf = r['design_summary']['performance']
        assert perf['burn_time_s'] == pytest.approx(10.0)
        assert perf['total_impulse_Ns'] == pytest.approx(
            float(r['total_impulse']), rel=1e-12)


class TestP1B103TankSicakligiEnjektore:
    """Enjektör yoğunluğu kullanıcının tank sıcaklığından gelir."""

    SICAKLIKLAR = (280.0, 293.15, 305.0)

    def test_farkli_sicaklik_farkli_yogunluk(self):
        rho = {}
        for T in self.SICAKLIKLAR:
            m = _motor(tank_temperature=T)
            m.calculate()
            rho[T] = float(m._inj_rho_ox)
        ayrik = {round(v, 6) for v in rho.values()}
        assert len(ayrik) == len(self.SICAKLIKLAR), (
            f'tank sıcaklığı enjektör yoğunluğunu değiştirmiyor: {rho}')
        # Yoğunluk sıcaklıkla AZALIR (doygun sıvı N2O).
        assert rho[280.0] > rho[293.15] > rho[305.0]

    def test_enjektor_ve_tank_blogu_ayni_yogunlugu_gorur(self):
        """Tek kaynak: aynı yanıtta iki N2O yoğunluğu olamaz."""
        for T in self.SICAKLIKLAR:
            m = _motor(tank_temperature=T)
            r = m.calculate()
            blok = r.get('oxidizer_tank_slosh') or {}
            tank_rho = blok.get('liquid_density_kg_m3')
            if tank_rho is None:
                pytest.skip(
                    'tank blowdown bloğu bu koşuda çözülmedi; karşılaştırma '
                    'için ikinci yoğunluk yok (kurulum sorusu değil, bu '
                    'tasarımda blok NOT_MODELLED)')
            assert float(m._inj_rho_ox) == pytest.approx(
                float(tank_rho), rel=1e-9), (
                f'T={T} K: enjektör {m._inj_rho_ox:.4f} ⟷ tank '
                f'{float(tank_rho):.4f} kg/m³')

    def test_varsayilan_sicaklik_modul_kunyesiyle_ayni(self):
        """Sıcaklık verilmezse künyedeki 293,15 K kullanılır."""
        m = _motor()
        m.calculate()
        assert float(m._inj_rho_ox) == pytest.approx(
            float(N2OSaturation().rho_l(293.15)), rel=1e-9)

    def test_doyma_zarfi_disinda_sayi_uretilmez(self):
        """Kritik nokta üstünde doygun sıvı yoktur — fail-closed."""
        with pytest.raises(ValueError, match=r'saturated-liquid envelope'):
            _motor(tank_temperature=320.0).calculate()


class TestP1B104TikanmamisBogaz:
    """Boğaz tıkanmıyorsa süpersonik lüle boyutlandırılmaz."""

    def test_tikanmamis_rejim_reddedilir(self):
        with pytest.raises(ValueError, match=r'not choked'):
            _motor(thrust=1000.0, chamber_pressure=1.0,
                   atmospheric_pressure=1.0).calculate()

    def test_hata_mesaji_alanlari_ve_esigi_soyler(self):
        with pytest.raises(ValueError) as exc:
            _motor(thrust=1000.0, chamber_pressure=1.2,
                   atmospheric_pressure=1.0).calculate()
        mesaj = str(exc.value)
        assert 'chamber_pressure' in mesaj
        assert 'atmospheric_pressure' in mesaj
        assert 'pressure ratio' in mesaj

    def test_tikanik_rejim_gecer_ve_esik_yayimlanir(self):
        m = _motor(thrust=1000.0, chamber_pressure=5.0,
                   atmospheric_pressure=1.0)
        m.calculate()
        assert m.throat_choked is True
        assert m.choked_pressure_ratio == pytest.approx(5.0)
        assert 1.0 < m.choked_pressure_ratio_required < 2.5

    def test_epsilon_pc_ile_monoton_artar(self):
        """Eşlenik genişleme oranı Pc/Pa ile monoton artmak ZORUNDADIR."""
        eps = []
        for pc in (2.0, 3.0, 5.0, 10.0):
            r = _motor(thrust=1000.0, chamber_pressure=pc,
                       atmospheric_pressure=1.0).calculate()
            eps.append(float(r['expansion_ratio']))
        assert all(eps[i + 1] > eps[i] for i in range(len(eps) - 1)), eps

    def test_vakumda_kapi_kapanmaz(self):
        """Pa = 0: oran sonsuz, boğaz her zaman tıkanık — kapı susmalı.

        ÖH D24 / OH-D23-01: gövde İDDİASIZDI. "Patlamamalı" yorumu tek
        başına bir iddia değil: kapı sessizce bir uyarı üretmeye başlasa
        ya da P_a'yı kendi kendine değiştirse test yine yeşil kalırdı.
        Kapının SUSTUĞU artık ölçülüyor.
        """
        m = _motor(thrust=1000.0, chamber_pressure=20.0,
                   atmospheric_pressure=0.0)
        m._gate_choked_throat()  # gamma yokken bile patlamamalı
        assert m.P_a == 0.0, 'kapı vakum basıncını değiştirdi'
        m.gamma = 1.2
        m.P_a = 0.0
        onceki = list(getattr(m, 'warnings', []) or [])
        m._gate_choked_throat()
        sonraki = list(getattr(m, 'warnings', []) or [])
        assert sonraki == onceki, (
            'vakumda (P_a=0) boğaz her zaman tıkanıktır; kapı yine de '
            'uyarı üretti: %s' % (sonraki[len(onceki):],))
        assert m.gamma == 1.2 and m.P_a == 0.0, (
            'kapı girdileri sessizce değiştirdi')


class TestP1B202IraksakBoyTekKaynak:
    """Yayımlanan ıraksak boy, çizilen konturun boyudur."""

    @pytest.mark.parametrize('tip', ['conical', 'bell', 'parabolic'])
    def test_ozet_boyu_kontur_boyuyla_ayni(self, tip):
        r = _motor(nozzle_type=tip, expansion_ratio=8.0).calculate()
        ozet = float(r['design_summary']['nozzle']['divergent_length_mm'])
        kontur = float(r['nozzle_contour']['divergent']['length'])
        assert ozet == pytest.approx(kontur, rel=1e-9), (
            f'{tip}: özet {ozet:.4f} ⟷ kontur {kontur:.4f} mm '
            f'(%{100.0 * (ozet / kontur - 1.0):.2f})')

    def test_boyun_kaynagi_adiyla_yayimlanir(self, sonuc_bell):
        _m, r = sonuc_bell
        kaynak = r['design_summary']['nozzle']['divergent_length_source']
        assert kaynak.startswith('solver ('), kaynak

    def test_toplam_motor_boyu_kamara_arti_lule(self, sonuc_bell):
        """Toplam boy, çizilen lülenin boyuyla kapanmalı."""
        m, r = sonuc_bell
        kd = r['design_summary']['key_dimensions']
        noz = r['design_summary']['nozzle']
        toplam = float(kd['total_motor_length_mm'])
        beklenen = (float(m.L) * 1000.0
                    + float(noz['convergent_length_mm'])
                    + float(noz['divergent_length_mm']))
        assert toplam == pytest.approx(beklenen, rel=1e-9)

    def test_bell_boyu_11_derece_koni_bagintisindan_gelmiyor(self, sonuc_bell):
        """Kusurun İMZASI: eski değer (re-rt)/tan(11°) idi."""
        m, r = sonuc_bell
        eski = ((m.d_e / 2.0 - m.d_t / 2.0)
                / np.tan(np.radians(11.0))) * 1000.0
        ozet = float(r['design_summary']['nozzle']['divergent_length_mm'])
        assert abs(ozet / eski - 1.0) > 0.10, (
            f'yayımlanan boy hâlâ 11° koni bağıntısının değeri: '
            f'{ozet:.4f} ⟷ {eski:.4f} mm')


# ===========================================================================
# DEVRALMA AJANININ ÜÇ KALEMİ (31 Ağu 2026) — P1B3-03, P1B3-04, P1B4-01
#
# Ölçüm dosyaları: ``docs/scofield/raw/OH/D15/hibrit/a1/once2.json`` ve
# ``sonra2.json`` (betik: ``olcum2.py``).
#
# P1B3-03 — LOX'un kriyojenik entalpisi düşülmüyordu: `hf_ox = 0.0`, yani
#     SIVI oksijen 298,15 K'deki GAZ O2 referansıyla yakılıyordu. CEA'nın
#     kendi LOX kartı (O2(L), h,cal=-3102, t(k)=90.18) −405,60 kJ/kg diyor.
#     Ölçülen: htpb/lox O/F 2,1 Pc 30 -> T_c 3601,86 K (CEA sözleşmeli
#     3554,84 K, +47,02 K); c* 1814,63 ⟷ 1795,29 m/s (+%1,08). Dört LOX
#     çiftinin dördünde de sapma İYİMSER yöndeydi; N2O kontrolü +0,00 K.
#
# P1B3-04 — `ethanol` anahtarı SAF etanol kartına (C2H5OH) eşleniyordu,
#     oysa HRMA tablosundaki adı ve yakıt yoğunluğu %75 etanol/%25 su
#     karışımınındır. Ölçülen (LOX, Pc = 100 bar, MR = 1,524): saf kart
#     c* 1739,74 m/s ⟷ tablo 1678,30 (+%3,66); mw 22,621 ⟷ 24,23 (−%6,64).
#
# P1B4-01 — NHNE devresinde alan İKİ FAZLI kütle akısından çözülürken hız
#     TEK FAZLI SPI bağıntısından yayımlanıyordu: velocity_m_s 56,4263 m/s
#     ⟷ aynı yanıttan ṁ/(ρ·A) 42,6908 m/s (oran 1,32174). SPI kontrolünde
#     oran tam 1,000000 idi. Hız SMD'ye giriyor (SMD ∝ v^(−2/3)): pintle
#     SMD 30,7413 µm yayımlanıyordu, sürekliliğe göre 37,0244 µm.
# ===========================================================================

# CEA LOX kartı: -3102 cal/mol x 4,184 J/cal / 1000 = -12,978768 kJ/mol
LOX_HF_CEA_KJ_MOL = -3102.0 * 4.184 / 1000.0
LOX_MW_G_MOL = 31.9988
LOX_HF_CEA_J_KG = LOX_HF_CEA_KJ_MOL * 1e6 / LOX_MW_G_MOL


@pytest.fixture(scope='module')
def yanma():
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    return CombustionAnalyzer()


@pytest.fixture(scope='module')
def yanma_htpb_lox(yanma):
    return yanma.analyze_combustion(fuel_composition={'htpb': 100.0},
                                    oxidizer_type='lox', of_ratio=2.1,
                                    chamber_pressure=30.0)


@pytest.fixture(scope='module')
def yanma_htpb_n2o(yanma):
    return yanma.analyze_combustion(fuel_composition={'htpb': 100.0},
                                    oxidizer_type='n2o', of_ratio=6.0,
                                    chamber_pressure=20.0)


class TestP1B303LoxKriyojenikEntalpi:
    """Sıvı oksijen gaz O2 referansıyla yakılamaz."""

    def test_sabit_cea_kartindan_ve_tek_kaynakta(self, yanma):
        """Entalpi TEK yerde (propellant_specs) ve CEA kartının değeri."""
        spec = yanma.propellant_specs['lox']
        assert spec['enthalpy_formation'] == pytest.approx(
            LOX_HF_CEA_KJ_MOL, rel=1e-12)
        assert spec['molecular_weight'] == pytest.approx(LOX_MW_G_MOL,
                                                         rel=1e-12)
        # Kütle bazı: CEA'nın -405,6 kJ/kg'ı.
        kj_kg = spec['enthalpy_formation'] * 1e6 / spec['molecular_weight'] / 1e3
        assert kj_kg == pytest.approx(-405.6017, abs=1e-3)

    def test_reaktan_entalpisi_sifir_degil(self, yanma):
        """O/F -> sonsuzda kalan pay TAM oksitleyici entalpisidir."""
        h = yanma._calculate_reactant_enthalpy({'htpb': 100.0}, 'lox', 1e12)
        assert h is not None
        assert h == pytest.approx(LOX_HF_CEA_J_KG, rel=1e-6)
        # Kusurun imzası: burası eskiden 0,0 idi.
        assert h < -4.0e5

    def test_tc_cea_sozlesmeli_cozumle_ayni(self, yanma_htpb_lox):
        """Ölçülen CEA sözleşmeli değer 3554,84 K; kusurlu değer 3601,86 K."""
        t_c = float(yanma_htpb_lox['conditions']['chamber']['T'])
        # ÇAPA TÜRETİMLİ YENİLENDİ — ÖH D19 hibrit-a1 (kalem B3-12).
        # Eski sayı, elemental ayrıştırmanın KÜTLE KORUMADIĞI koddan
        # geliyordu: pay (atom kütleleri) ile payda (molekül ağırlığı)
        # ayrı ayrı elle yazılıydı, HTPB'de Σ(kütle kesri)=1,001851852
        # (+%0,1852) ve kullanıcının 6,0 dediği O/F dengeye 5,990270
        # olarak giriyordu. D19'da molekül ağırlığı formülden ve
        # _ATOMIC_MASS (IUPAC 2021) tablosundan TÜRETİLDİ; Σ=1,0 ve
        # efektif O/F = istenen O/F oldu. Yeni sayı bu DOĞRU girdiden
        # gelir; yön fiziksel olarak beklenendir (yakıt payı %0,185
        # şişkinken karışım daha zengin görünüyordu, düzeltilince
        # stokiyometriye yaklaşıp alev sıcaklığı yükseldi).
        # Ölçüm: docs/scofield/raw/OH/D19/hibrit/a1/capa_yenileme.json
        # Eski çapa 3554,84 K -> yeni 3557,028375856765 K (+2,188 K,
        # +%0,062). Kusur imzası denetimi (t_c < 3580) DEĞİŞMEDİ ve hâlâ
        # geçiyor: kriyojenik entalpisi düşülmemiş değer 3601,86 K idi.
        # Aynı fixture'ın c* çapası (1795,29 ± 1,0) yenilenmedi: yeni değer
        # 1795,242865911794, bant içinde kaldı.
        assert t_c == pytest.approx(3557.028375856765, abs=1.0)
        assert t_c < 3580.0, (
            f'T_c hâlâ kriyojenik entalpisi düşülmemiş değere yakın: {t_c:.2f} K')

    def test_c_star_iyimser_degil(self, yanma_htpb_lox):
        c = float(yanma_htpb_lox['performance']['c_star'])
        assert c == pytest.approx(1795.29, abs=1.0)
        assert c < 1808.0, f'c* hâlâ iyimser: {c:.2f} m/s'

    def test_n2o_kontrolu_degismedi(self, yanma_htpb_n2o):
        """Sapmanın kaynağı LOX dalıdır; N2O yolu DOKUNULMAMIŞ kalmalı.

        c* ÇAPASI TÜRETİMLİ YENİLENDİ — ÖH D18 fizik-a1 / F1 (B3-05).
        Eski çapa 1619,5970602689638 m/s tek-γ KAPALI FORMUNDAN geliyordu:
        c* = sqrt(R_c·T_c/γ)/((2/(γ+1))^((γ+1)/(2(γ−1)))). F1'den sonra c*
        çözülen kayan-denge BOĞAZ istasyonundan gelir:
        c* = P_c/(ρ_t·v_t) (NASA RP-1311 Part I eş. 6.11).
        Yeni/eski = 1618,3463221682769/1619,5970602689638 = 0,99922776
        (−%0,0772). Bu oran P01'in bağımsız ölçümüyle birebir aynıdır:
        o rapor yayımlanan c*'ı kayan-denge referansına göre +%0,077
        buluyordu (docs/scofield/raw/P01/B3-yanma-cea.md §B3-05:
        "yayımlanan=1619,597 | kayan-denge=1618,346"). Yani yeni çapa,
        P01'in ölçtüğü DOĞRU değerin ta kendisidir.
        Oda sıcaklığı çapası DEĞİŞMEDİ — LOX dalı denetimi bozulmadı.
        Tek-γ değeri silinmedi, ``c_star_single_gamma`` altında yayımlanır.
        """
        # ÇAPA TÜRETİMLİ YENİLENDİ — ÖH D19 hibrit-a1 (kalem B3-12).
        # Eski sayı, elemental ayrıştırmanın KÜTLE KORUMADIĞI koddan
        # geliyordu: pay (atom kütleleri) ile payda (molekül ağırlığı)
        # ayrı ayrı elle yazılıydı, HTPB'de Σ(kütle kesri)=1,001851852
        # (+%0,1852) ve kullanıcının 6,0 dediği O/F dengeye 5,990270
        # olarak giriyordu. D19'da molekül ağırlığı formülden ve
        # _ATOMIC_MASS (IUPAC 2021) tablosundan TÜRETİLDİ; Σ=1,0 ve
        # efektif O/F = istenen O/F oldu. Yeni sayı bu DOĞRU girdiden
        # gelir; yön fiziksel olarak beklenendir (yakıt payı %0,185
        # şişkinken karışım daha zengin görünüyordu, düzeltilince
        # stokiyometriye yaklaşıp alev sıcaklığı yükseldi).
        # Ölçüm: docs/scofield/raw/OH/D19/hibrit/a1/capa_yenileme.json
        # Eski -> yeni (üçü de aynı kökten, B3-12):
        #   T_c   3307,1286052735204 -> 3308,150759944153   (+1,022 K)
        #   c*    1618,3463221682769 -> 1618,2075165893289  (-%0,0086)
        #   c*_1g 1619,5970602689638 -> 1619,420823155716   (-%0,0109)
        # D18/F1'in kayan-denge c* sözleşmesi KORUNDU: c* < c*_tek-γ ilişkisi
        # ve aradaki -%0,075 mertebesindeki fark aynen duruyor.
        # ÇAPA YENİLENDİ — kitap p1a B16 (karar §28-18 (a), ana model izni).
        # N₂O artık 293,15 K doymuş SIVI giriş entalpisiyle (70,8212 kJ/mol;
        # RP-1311 §4.1) yakılıyor; eski sayılar 298,15 K ideal GAZ
        # (82,05 kJ/mol) referansındandı. Bu bekçinin LOX dalına karşı
        # kontrol rolü aynen duruyor: N₂O yolu LOX düzeltmesinden etkilenmez.
        # Eski -> yeni (tolerans rel 1e-9 DEĞİŞMEDİ):
        #   T_c   3308,150759944153  -> 3245,6920966427515
        #   c*    1618,2075165893289 -> 1595,8688364555653
        #   c*_1g 1619,420823155716  -> 1597,8986556899304
        # Kâhin: NASA CEA kök denetimi (docs/scofield/raw/OH/KITAP/p1a/
        # kanit/tur2b/kahin_cea.json; sıvı kartla HRMA ⟷ CEA farkı gaz
        # tabanının 0,5 puan içinde) + önce/sonra satırı (p1a rapor §12).
        # 'gas' fazında eski üç sayı BİT-AYNI çıkıyor (ölçüldü).
        assert float(yanma_htpb_n2o['conditions']['chamber']['T']) == \
            pytest.approx(3245.6920966427515, rel=1e-9)
        assert float(yanma_htpb_n2o['performance']['c_star']) == \
            pytest.approx(1595.8688364555653, rel=1e-9)
        assert float(yanma_htpb_n2o['performance']['c_star_single_gamma']) \
            == pytest.approx(1597.8986556899304, rel=1e-9)

    def test_gox_hala_sifir(self, yanma):
        """Gaz O2 için Hf = 0 DOĞRUDUR; onarım o dalı bozmamalı."""
        h_gox = yanma._calculate_reactant_enthalpy({'htpb': 100.0}, 'gox',
                                                   1e12)
        assert h_gox is not None
        assert abs(h_gox) < 1.0


class TestP1B304EtanolKimligi:
    """Bir motorun kimliği tektir: ad, yoğunluk ve termokimya aynı iticinin."""

    def test_ethanol_karisim_kartina_eslenir(self):
        from hrma.engines.cea_bridge import map_propellants
        assert map_propellants('ethanol', 'lox') == ('ETHANOL75', 'LOX')

    def test_saf_etanol_ayri_anahtarda_erisilebilir(self):
        from hrma.engines.cea_bridge import map_propellants
        assert map_propellants('c2h5oh', 'lox') == ('C2H5OH', 'LOX')
        assert map_propellants('ethanol_pure', 'lox') == ('C2H5OH', 'LOX')

    def test_ozel_kart_rocketcea_kendi_bilesenlerinden(self):
        """Kart satırları uydurulmadı: RocketCEA'nın C2H5OH ve H2O kartları."""
        from hrma.engines.cea_bridge import CUSTOM_FUEL_CARDS
        kart = CUSTOM_FUEL_CARDS['ETHANOL75']
        assert '-66370' in kart          # C2H5OH(L) h,cal
        assert '-68308' in kart          # water h,cal
        assert 'wt%=75.00' in kart
        assert 'wt%=25.00' in kart

    def test_karisim_karti_hrma_tablosuna_saf_etanoldan_yakin(self):
        """Kimlik ölçütü: kartın c*/mw'si tablonun karışımına yakınsamalı."""
        from hrma.engines import cea_bridge
        # ÖH D15 birleştirme (1 Eyl 2026): eski hâli
        # ``pytest.skip('RocketCEA kurulu değil')`` idi ve kurulum sorusunu
        # HİÇ sormuyordu — rocketcea KURULUYKEN ithal/veri yolu bozulursa da
        # atlıyor, ürün kusuru sessizleşiyordu. Karar tek kaynağa
        # (``tests/bagimlilik_kapisi.kapi``) verildi: kurulu değilse ATLA,
        # kurulu ama yol kapalıysa KIRMIZI. Kardeş desen:
        # ``tests/test_cea_bridge.py``.
        kapi('rocketcea', cea_bridge.is_rocketcea_available(),
             'rocketcea ithal edilebiliyor ama '
             'cea_bridge.is_rocketcea_available() False — CEA veri dizini '
             'ya da özel kart kurulumu bozuk')
        from rocketcea.cea_obj import CEA_Obj
        cea_bridge.ensure_isolated_cea_data_dir()
        cea_bridge.ensure_custom_cards()
        pc_psi = 100.0 * 14.5037738
        TABLO_CSTAR, TABLO_MW = 1678.3, 24.23

        def _olc(kart):
            o = CEA_Obj(oxName='LOX', fuelName=kart)
            c = float(o.get_Cstar(Pc=pc_psi, MR=1.524)) * 0.3048
            mw = float(o.get_Chamber_MolWt_gamma(
                Pc=pc_psi, MR=1.524, eps=200.0)[0])
            return c, mw

        c_kar, mw_kar = _olc('ETHANOL75')
        c_saf, mw_saf = _olc('C2H5OH')
        assert abs(c_kar - TABLO_CSTAR) < abs(c_saf - TABLO_CSTAR)
        assert abs(mw_kar - TABLO_MW) < abs(mw_saf - TABLO_MW)
        # Kusurun imzası: saf kart tabloyu %3'ten fazla aşıyordu.
        assert abs(c_kar / TABLO_CSTAR - 1.0) < 0.02


def _ox_devresi(m, r):
    det = r['injector_design_detail']
    ox = det['ox_circuit']
    v_sur = (float(ox['mdot_kg_s'])
             / (float(m._inj_rho_ox) * float(ox['total_area_mm2']) * 1e-6))
    return det, ox, v_sur


@pytest.fixture(scope='module')
def enj_n2o():
    m = _motor(thrust=5000.0, nozzle_type='bell')
    return m, m.calculate()


@pytest.fixture(scope='module')
def enj_n2o_pintle():
    m = _motor(thrust=5000.0, nozzle_type='bell', injector_type='pintle')
    return m, m.calculate()


@pytest.fixture(scope='module')
def enj_lox_spi():
    m = _motor(thrust=5000.0, nozzle_type='bell', oxidizer_type='lox',
               of_ratio=2.1)
    return m, m.calculate()


class TestP1B401EnjeksiyonHiziSureklilikten:
    """Yayımlanan hız, aynı yanıttaki ṁ, ρ ve A ile kapanmalı."""

    def test_nhne_devresi_sureklilikle_kapaniyor(self, enj_n2o):
        m, r = enj_n2o
        det, ox, v_sur = _ox_devresi(m, r)
        assert ox['flow_model'] == 'NHNE'
        assert float(ox['velocity_m_s']) == pytest.approx(v_sur, rel=1e-12)

    def test_spi_kontrolu_de_kapali(self, enj_lox_spi):
        """SPI dalı ZATEN kapalıydı; genelleştirme onu bozmamalı."""
        m, r = enj_lox_spi
        det, ox, v_sur = _ox_devresi(m, r)
        assert ox['flow_model'] == 'SPI'
        assert float(ox['velocity_m_s']) == pytest.approx(v_sur, rel=1e-12)

    def test_urun_yuzunde_yayimlanan_hiz_ayni(self, enj_n2o):
        m, r = enj_n2o
        det, ox, v_sur = _ox_devresi(m, r)
        assert float(r['injector_design']['injection_velocity_m_s']) == \
            pytest.approx(v_sur, rel=1e-12)

    def test_kusurun_imzasi_spi_bagintisi_degil(self, enj_n2o):
        """Eski değer cd·sqrt(2Δp/ρ) idi; NHNE'de bu %30'dan fazla yüksek."""
        m, r = enj_n2o
        det, ox, v_sur = _ox_devresi(m, r)
        eski = float(ox['cd']) * np.sqrt(
            2.0 * float(ox['delta_p_bar']) * 1e5 / float(m._inj_rho_ox))
        assert eski / v_sur > 1.20, 'ölçüm kurulumu kusuru üretmiyor'
        assert abs(float(ox['velocity_m_s']) / eski - 1.0) > 0.10, (
            f"yayımlanan hız hâlâ SPI bağıntısının değeri: "
            f"{ox['velocity_m_s']:.4f} ⟷ {eski:.4f} m/s")

    def test_smd_sureklilik_hizindan_gelir(self, enj_n2o_pintle):
        """SMD ∝ v^(−2/3): iyimser hız, olduğundan küçük damlacık demekti.

        ÖH D20 / B4-11 — ÇAPA GÜNCELLENDİ (37,02 → 37,792 µm, +%2,08).
        Sayıyı SMD bağıntısı değil PINTLE GEOMETRİSİ oynattı:
        ``pintle_tip_geometry`` D_p'yi ince-anülüs yaklaşımının tersinden
        (``D_p = √(A_ann/(πk))``), anülüs boşluğu t'yi ise TAM ifadeden
        (``A_ann = π(D_p+t)t``) çözüyordu; iki model yan yana durunca
        yayımlanan ``t/D_p`` 0,047723 çıkıyordu — fonksiyonun kendi künyesinin
        söz verdiği 0,05'ten %4,555 sapma (ölçüm:
        ``docs/scofield/raw/OH/D20/hibrit/a1/once.json`` ``B4_11``).
        D20'de tek modele indirildi (``D_p = √(A_ann/(πk(1+k)))``), t/D_p artık
        tam 0,05 ve ``π(D_p+t)t`` anülüs alanını 1e−12 içinde geri veriyor.
        37,02 bu ağaçta ancak B4-11 GERİ ALINARAK üretilebiliyor (ölçüldü:
        onarım geri alınınca bu sınıf 6/6 yeşil) — yani eski çapa kusuru
        KORUYAN bir bekçiydi. Kalemin ASIL iddiası (SMD süreklilik hızından
        gelir, iyimser SPI hızından değil) DEĞİŞMEDİ ve aşağıdaki alt sınır
        testiyle korunuyor.
        """
        m, r = enj_n2o_pintle
        det, ox, v_sur = _ox_devresi(m, r)
        smd = float(det['atomization']['smd_ox_um'])
        assert smd == pytest.approx(37.792, abs=0.5)
        assert smd > 34.0, f'SMD hâlâ iyimser (küçük): {smd:.4f} µm'

    def test_manifold_beyani_gercegi_soyluyor(self, enj_n2o):
        """Oran artık iki dalda da özdeşliktir; künye bunu söylemeli."""
        m, r = enj_n2o
        det, ox, _ = _ox_devresi(m, r)
        man = ox['manifold']
        assert man['v_ratio_is_tautological'] is True
        assert 'continuity' in man['v_ratio_basis']
        assert man['v_ratio'] == pytest.approx(man['v_ratio_target'],
                                               rel=1e-9)
