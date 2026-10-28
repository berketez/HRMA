"""Bebek-Scofield sıvı motor bekçileri (A2 — F1-1, F1-2, F5-3, F5-4).

Bulgu sicili: docs/scofield-bebek-2026-08-17.md. Dört kusur da aynı
sınıftandı: iki parça tek başına doğru, aralarındaki sözleşme yanlış.

Ölçülen kusurlar (öncesi → sonrası):

* F1-2 — tank basıncı marjı YALNIZ oksitleyici basma basıncına bakıyordu;
  rejeneratif ΔP taşıyan yakıt gereksinimi bağlayıcıyken işaret ters
  dönüyordu. Ölçüm (25 kN LOX/RP-1, Pc=70 bar, pressure_fed, tank 95 bar):
  yayımlanan +4,402 bar ⟷ çevrim çözücüsü −3,576 bar + critical
  ``warn.cycle.pressure_fed_infeasible``. Sonrası: marj çevrim çözümünün
  KENDİSİNDEN okunur (tek kaynak), motor kapısı da aynı marjdan ateşler.

* F1-1 — ``_apply_cycle_accounting`` ölü koddu: başlık Isp'si (277,449 s)
  ile yakınsamış çevrim çözümünün motor Isp'si (274,034 s; kayıp 3,415 s)
  aynı yanıtta beyansız çelişiyordu. Sonrası: ilişki
  ``cycle_isp_accounting`` bloğunda adıyla ve ölçülen farkla yayımlanır;
  blok motorun GERÇEK ``_cycle_isp_applied`` durumundan türediği için beyan
  davranıştan kopamaz.

* F5-3 — aynı turbopompanın türbin gücü iki değerle yayımlanıyordu:
  kullanıcıya 169,55 kW (= 110,21/0,65 — pompa mil gücü türbin verimine
  BÖLÜNMÜŞ), çevrim kapanışında 110,21 kW. Mil dengesinde türbin mil gücü
  pompa mil gücüne EŞİTTİR (çevrim çözücüsünün kapattığı özdeşlik; verim
  gaz debisi boyutlandırmasına girer, mil gücünü büyütmez). Sonrası: tek
  değer, her yayın noktasında aynı.

* F5-4 — aynı kanal devresi için iki çelişen çıktı kümesi (toplu Bartz
  zinciri 52,15 MW/m² / çıkış 820,0 K ⟷ istasyon marşı 10,95 MW/m² /
  421,9 K) beyansız yan yana duruyordu. Sonrası: fark
  ``channel_circuit_reconciliation`` bloğunda adıyla ölçülür; hangi kümenin
  fiziksel denge olduğu ENERJİ DENGESİYLE karara bağlanır (marşın kendi
  kapanışı ṁ·c̄p·ΔT = ∮q dA ölçülü; tasarım-cidar akısı için gereken film
  ΔT'si kanalların verebileceğiyle kıyaslanır).

Motor koşuları pahalıdır (~3-5 s); iki koşu modül kapsamında paylaşılır.
"""

import pytest

# Form varsayılanları ve koşucu TEK kaynaktan (deponun kendi deseni:
# tests.test_cfd_alan_koprusu -> test_cfd_endpoint ithali gibi).
from tests.test_liquid_real_inputs import FORM_DEFAULTS, run_engine


# ---------------------------------------------------------------------------
# Paylaşılan koşular
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def gg():
    """Gaz jeneratörü çevrimi (RP-1/LOX, rejeneratif): F1-1, F5-3, F5-4."""
    return run_engine(dict(FORM_DEFAULTS))


#: F5-4 senaryosunda kullanılan cidar kalınlığı [mm]. Form varsayılanı 5 mm
#: ve o değer 1B istasyon marşının İNCE-CİDAR ZARFININ DIŞINDA kalıyor
#: (aşağıdaki ``gg_zarf`` gerekçesi); 3 mm zarfın içindedir.
F54_CIDAR_MM = 3


@pytest.fixture(scope='module')
def gg_zarf():
    """``gg``ın ince-cidar ZARFI İÇİNDEKİ kardeşi (F5-4 senaryosu).

    ÇEVRİLDİ — ÖH D15 birleşme etkileşimi (1 Eylül 2026)
    ----------------------------------------------------
    Termo-uçuş kulvarının **P4B2-09** onarımı ``RegenCooling``e model zarfı
    kapısı koydu: modül künyesinde "thin flat-plate radial conduction" diyor,
    bu yüzden düz-levha iletim direnci (``t_w/k``) ile silindirik çözümün
    (``r1·ln(r2/r1)/k``) bağıl farkı %10'u aşarsa cidar sıcaklığı YAYIMLANMAZ
    (``ValueError``). Bu FAIL-CLOSED hüküm kazanır ve korunur.

    ÖLÇÜLDÜ (1 Eylül 2026, birleşik ana ağaç, ``FORM_DEFAULTS``): boğaz
    yarıçapı 15,4 mm, cidar 5 mm -> fark **%13,4** -> marş reddediliyor,
    ``station_march`` ve ``channel_circuit_reconciliation`` blokları yanıtta
    HİÇ YOK. 4 mm de reddediliyor; **3 mm zarfın içinde** ve marş koşuyor
    (ölçülen mutabakat: tepe akı 80,4285 ⟷ 8,4432 MW/m², çıkış 1254,9505 ⟷
    486,5416 K, ΔP 0,3600 ⟷ 0,2252 bar; marşın enerji dengesi bağıl açığı
    1,16e-16).

    F5-4 bekçileri devrenin İKİ çözümünün mutabakatını ölçer; o mutabakat
    ancak marşın koştuğu bir senaryoda ölçülebilir. Senaryo zarfın içine
    taşındı, İDDİALARIN HİÇBİRİ GEVŞETİLMEDİ. Zarf DIŞINDAKİ davranış
    (varsayılan 5 mm) ayrıca ve ilk kez kilitlendi:
    ``test_zarf_disinda_mars_reddi_beyanli_ve_sizintisiz``.
    """
    return run_engine(dict(FORM_DEFAULTS,
                           chamber_wall_thickness=F54_CIDAR_MM))


@pytest.fixture(scope='module')
def exp_kapanmayan():
    """Expander + RP-1: çevrim KAPANMAZ (not_converged) — türbin kartının
    yedek (çevrimsiz) yolunu görünür kılar. Converged yolda kart çevrim
    kapanışıyla ezildiği için F5-3'ün ikinci ``/η`` kopyası ancak burada
    ısırılabilir (ölçüldü: mutasyonla 64,15 kW → 98,69 kW)."""
    return run_engine(dict(FORM_DEFAULTS, engine_cycle='expander'))


@pytest.fixture(scope='module')
def pf():
    """Basınç beslemeli, yakıt tarafı bağlayıcı senaryo (F1-2 ölçüm vakası).

    Pc=70 bar + 20 bar enjektör ΔP + rejeneratif ceket ΔP'siyle yakıt
    gereksinimi oksitleyicininkini aşar; tank basıncı tam ikisinin
    ARASINDADIR — eski formülün işareti burada ters dönüyordu.

    ÖH D15 sıvı a2 (P3B3-04): tank basıncı 95 -> 92 bar. Bekçinin ÖN KOŞULU
    (req_ox < tank < req_fuel) kırıldığı için değil, kırıldığını KENDİSİ
    söylediği için güncellendi ("bekçi senaryosunu güncelle"). Besleme hattı
    çapı artık hız bandına göre seçildiğinden yakıt hattı 25 -> 50 mm'ye
    çıktı, hat kaybı düştü ve gereken yakıt tankı basıncı 98,6 -> 94,66 bara
    indi; 95 bar artık aralığın ÜSTÜNDE kalıyordu. Ölçülen yeni aralık:
    req_ox 91,135 / req_fuel 94,663 bar. İDDİALARIN HİÇBİRİ gevşetilmedi;
    marj hâlâ NEGATİF (-2,6634 bar) ve infeasible uyarısı hâlâ çıkıyor.
    """
    return run_engine(dict(FORM_DEFAULTS, engine_cycle='pressure_fed',
                           feed_pressure=92),
                      thrust=25000, chamber_pressure=70, mixture_ratio=2.3)


def _cyc(result):
    return result['detailed_feed_system']['engine_cycle_solution']


# ---------------------------------------------------------------------------
# F1-2 — tank basıncı marjı tek kaynaktan ve doğru taraftan
# ---------------------------------------------------------------------------

class TestF12TankMarji:
    def test_marj_cevrim_cozumunun_kendisidir(self, pf):
        """Yayımlanan marj = çevrim çözücüsünün marjı (bit düzeyinde)."""
        _, res = pf
        dfs = res['detailed_feed_system']
        cyc = _cyc(res)
        assert cyc.get('tank_pressure_margin_bar') is not None, (
            'senaryo ön koşulu: çevrim çözümü marj yayımlamalı')
        assert dfs['tank_pressure_margin_bar'] == \
            cyc['tank_pressure_margin_bar']
        assert 'single source' in dfs['tank_pressure_margin_basis']

    def test_marj_yakit_tarafini_gorur_ve_isaret_dogru(self, pf):
        """Kusurun kendisi: yakıt bağlayıcıyken eski formül + verirdi.

        Mutasyon kanıtı: marj ``tank − ox basma basıncı``na geri dönerse
        (eski satır) burada +4,4 bar civarı POZİTİF çıkar ve iki assert
        birden kırılır.
        """
        _, res = pf
        dfs = res['detailed_feed_system']
        cyc = _cyc(res)
        req_ox = cyc['required_tank_pressure_ox_bar']
        req_fuel = cyc['required_tank_pressure_fuel_bar']
        tank = dfs['tank_pressure_bar']
        # Senaryo ön koşulları — bunlar kırılırsa bekçi kör kalır, sessiz
        # geçmek yerine adıyla söylenir.
        assert req_fuel > req_ox, (
            'senaryo ön koşulu bozuldu: yakıt gereksinimi artık bağlayıcı '
            f'değil (req_fuel={req_fuel:.2f} <= req_ox={req_ox:.2f}); '
            'bekçi senaryosunu güncelle')
        assert req_ox < tank < req_fuel, (
            'senaryo ön koşulu bozuldu: tank basıncı iki gereksinimin '
            f'arasında değil (req_ox={req_ox:.2f}, tank={tank}, '
            f'req_fuel={req_fuel:.2f}); bekçi senaryosunu güncelle')
        marj = dfs['tank_pressure_margin_bar']
        # Doğru tanım: tank − max(req_ox, req_fuel); bu vakada NEGATİF.
        assert marj == pytest.approx(tank - max(req_ox, req_fuel),
                                     rel=1e-12)
        assert marj < 0.0
        # Eski (yanlış taraf) formülün değeri farklı ve POZİTİF olurdu.
        assert marj != pytest.approx(tank - req_ox, abs=1e-6)

    def test_marj_negatifse_motor_da_uyarir(self, pf):
        """Kapı da tek kaynaktan: çözücü critical derken motor susamaz."""
        _, res = pf
        cyc_codes = [w.get('code') for w in (_cyc(res).get('warnings') or [])
                     if isinstance(w, dict)]
        assert 'warn.cycle.pressure_fed_infeasible' in cyc_codes
        eng_warns = [w for w in res['input_warnings']
                     if isinstance(w, dict)
                     and w.get('code') == 'warn.liquid.pressure_fed_tank_too_low']
        assert eng_warns, (
            'çevrim çözücüsü critical infeasible derken motor seviyesinde '
            'pressure_fed_tank_too_low uyarısı yok — eski kapı yalnız '
            'oksitleyiciye bakıyordu, bu kusurun ta kendisi')
        # Uyarının bildirdiği gereksinim bağlayıcı (yakıt) taraf olmalı.
        req_fuel = _cyc(res)['required_tank_pressure_fuel_bar']
        assert eng_warns[0]['params']['required_bar'] == \
            pytest.approx(round(req_fuel, 1))


# ---------------------------------------------------------------------------
# F5-3 — türbin gücü tek değer, mil dengesiyle
# ---------------------------------------------------------------------------

class TestF53TurbinGucu:
    def test_turbin_gucu_her_yayin_noktasinda_ayni(self, gg):
        """169,55 ⟷ 110,21 çelişkisi: artık TEK değer."""
        _, res = gg
        cyc = _cyc(res)
        assert cyc.get('status') == 'converged', 'senaryo ön koşulu'
        cyc_kw = cyc['turbine_power_total_W'] / 1e3
        yayinlar = {
            'turbopump_system.turbine_power':
                res['turbopump_system']['turbine_power'],
            'detailed_feed_system.turbopump_analysis.turbine.power_output':
                res['detailed_feed_system']['turbopump_analysis'][
                    'turbine']['power_output'],
            'feed_system.turbopump.turbine.power':
                res['feed_system']['turbopump']['turbine']['power'],
        }
        for ad, deger in yayinlar.items():
            assert deger == pytest.approx(cyc_kw, rel=1e-9), (
                f'{ad} = {deger} != çevrim kapanışı {cyc_kw} — aynı '
                'turbopompa yine iki sayıyla anlatılıyor')

    def test_mil_dengesi_ozdesligi(self, gg):
        """Enerji dengesi: türbin mil gücü ≡ pompa mil gücü.

        Mutasyon kanıtı: ``/ eta_turbine`` geri gelirse yayımlanan güç
        pompa toplamının 1/0,65 katına çıkar ve burada kırılır.
        """
        _, res = gg
        cyc = _cyc(res)
        # Çözücünün kendi kapanışı (özdeşliğin kaynağı).
        assert cyc['turbine_power_total_W'] == \
            pytest.approx(cyc['pump_power_total_W'], rel=1e-9)
        # Yayımlanan türbin gücü pompa toplamına eşit — verime bölünmemiş.
        tps = res['turbopump_system']
        pompa_toplam = tps['total_pump_power']
        assert tps['turbine_power'] == pytest.approx(pompa_toplam, rel=1e-9)
        # Verim hâlâ yayımlanıyor (gaz debisi boyutlandırması için) ama mil
        # gücünü şişirmiyor.
        turb = res['detailed_feed_system']['turbopump_analysis']['turbine']
        assert 'shaft power balance' in turb['power_output_basis']

    def test_cevrim_kapanmayinca_da_mil_dengesi(self, exp_kapanmayan):
        """İkinci ``/η`` kopyasının bekçisi: çevrimsiz yedek yol.

        Converged yolda türbin kartı çevrim kapanışıyla ezilir; kopya kusur
        ancak çevrim KAPANMADIĞINDA görünür. Ölçülen (expander+RP-1,
        not_converged): pompalar 64,15 kW iken mutasyonlu kart 98,69 kW
        (=64,15/0,65) yayımlıyordu.
        """
        _, res = exp_kapanmayan
        cyc = _cyc(res)
        assert cyc.get('status') != 'converged', (
            'senaryo ön koşulu bozuldu: expander+RP-1 çevrimi artık '
            'kapanıyor; bekçiye yeni bir kapanmayan senaryo gerek')
        ta = res['detailed_feed_system']['turbopump_analysis']
        pompa_toplam = (ta['oxidizer_pump']['design_power']
                        + ta['fuel_pump']['design_power'])
        turb = ta['turbine']
        assert turb['power_output'] == pytest.approx(pompa_toplam, rel=1e-9)
        # Gaz debisi boyutlandırması: ṁ = P_mil/(Δh·η) — verim TAM BİR kez.
        # ÖH D15 sıvı a2 (P3B3-02): burada '/100.0' YAZILIYDI, yani bekçi bu
        # alanın YÜZDE olduğunu SÖZLEŞME yapıyordu. Oysa kardeş kart
        # (feed_system.turbopump.turbine) aynı adla KESİR yayımlıyordu ve
        # ölçülen kusur tam buydu: bir yanıt, bir alan adı, iki birim. Alan
        # artık iki kartta da kesirdir; bekçi sabiti kodlamak yerine KARTIN
        # KENDİ birim beyanını okur, böylece birim yeniden kayarsa görür.
        assert turb['efficiency_unit'] == 'fraction'
        eta = float(turb['efficiency'])
        assert 0.0 < eta <= 1.0, f'verim kesir değil: {eta}'
        assert turb['mass_flow_rate'] == pytest.approx(
            turb['power_output'] * 1e3 / (turb['specific_work_J_kg'] * eta),
            rel=1e-9)


# ---------------------------------------------------------------------------
# F1-1 — başlık Isp'si ↔ çevrim çözümü ilişkisi beyanlı
# ---------------------------------------------------------------------------

class TestF11CevrimIspBeyani:
    def test_beyan_blogu_var_ve_olculu(self, gg):
        _, res = gg
        acc = res.get('cycle_isp_accounting')
        assert isinstance(acc, dict), (
            'cycle_isp_accounting bloğu yok — başlık Isp\'si ile çevrim '
            'çözümü yine beyansız çelişiyor (F1-1)')
        cyc = _cyc(res)
        assert cyc.get('status') == 'converged', 'senaryo ön koşulu'
        assert acc['status'] == 'reconciled'
        assert acc['engine_isp_sl_s'] == cyc['isp_engine_sl_s']
        assert acc['isp_loss_sl_s'] == cyc['isp_loss_sl_s']
        assert acc['headline_minus_engine_sl_s'] == pytest.approx(
            acc['headline_isp_sl_s'] - acc['engine_isp_sl_s'], rel=1e-12)
        # Açık çevrimde kayıp gerçek ve pozitif olmalı (ölçülen ~3,4 s).
        assert acc['isp_loss_sl_s'] > 0.0

    def test_beyan_davranistan_kopamaz(self, gg):
        """Kaybı sessizce uygulamak da, beyanı çürütmek de kırmızıdır.

        Blok ``_cycle_isp_applied`` durumundan türediği için üç hâl de
        kilitli: (a) uygulanmadıysa başlık ANA ODA Isp'sinin ta kendisidir;
        (b) uygulandıysa başlık motor Isp'sidir; (c) motor nesnesinin
        durumu ile bloğun beyanı aynıdır.
        """
        engine, res = gg
        acc = res['cycle_isp_accounting']
        cyc = _cyc(res)
        assert acc['applied'] == bool(getattr(engine, '_cycle_isp_applied',
                                              False))
        assert acc['headline_isp_sl_s'] == pytest.approx(
            res['isp_sea_level'], rel=1e-12)
        if not acc['applied']:
            # Başlık, beyan edilen kaynağın (ana oda zinciri) KENDİSİ olmalı.
            assert res['isp_sea_level'] == pytest.approx(
                cyc['isp_main_sl_s'], rel=1e-12), (
                'başlık Isp\'si ne ana oda değeri ne motor değeri — kayıp '
                'sessizce/yarım uygulanmış (F1-1 geri geldi)')
            assert 'NOT subtracted' in acc['headline_isp_basis']
        else:
            assert res['isp_sea_level'] == pytest.approx(
                cyc['isp_engine_sl_s'], rel=1e-3), (
                'blok applied=True diyor ama başlık motor Isp\'si değil')

    def test_kapali_cevrimde_kayip_sifir_beyani(self, pf):
        """Basınç beslemeli: kayıp tanım gereği 0 ve blok bunu söyler."""
        _, res = pf
        acc = res.get('cycle_isp_accounting')
        assert isinstance(acc, dict)
        if acc['status'] == 'reconciled':
            assert acc['isp_loss_sl_s'] == 0.0


# ---------------------------------------------------------------------------
# F5-4 — aynı kanal devresi: fark adıyla, hüküm enerji dengesiyle
# ---------------------------------------------------------------------------

class TestF54KanalDevresi:
    def test_mutabakat_blogu_iki_kumeyi_adiyla_yayimlar(self, gg_zarf):
        _, res = gg_zarf
        tp = res['thermal_protection']
        assert 'station_march' in tp, 'senaryo ön koşulu: RP-1 marşı koşmalı'
        rec = tp.get('channel_circuit_reconciliation')
        assert isinstance(rec, dict), (
            'channel_circuit_reconciliation yok — aynı devrenin iki çıktı '
            'kümesi yine beyansız yan yana (F5-4)')
        bulk, march = rec['bulk_chain'], rec['station_march']
        # Kimlik: blok, başlıktaki sayıların TA KENDİSİNİ mutabık kılar.
        assert bulk['peak_heat_flux_MW_m2'] == \
            pytest.approx(tp['heat_flux'], rel=1e-12)
        # BİLİNÇLİ KİLİT (ÖH defteri P15B1-06 / ÖK-14, 2026-08-27).
        # İddia DOĞRUDUR ve KALIR — blok, başlıktaki sayının ta kendisini
        # mutabık kılmalı. Ama bu satır aynı zamanda bir KUSURU kilitliyor:
        # ``tp['coolant_exit_temperature']`` takma adı bugün YALNIZ toplu
        # Bartz zincirinin sayısını taşır; aynı devrenin istasyon marşı
        # çözümü üst katmanda hiç yayımlanmaz. O yüzden kilidin gerekçesi
        # ve onarım günündeki GÜNCELLEME REÇETESİ mesajda yazılıdır; borcun
        # kendisi aşağıda ters yönde imliydi
        # (test_ust_katman_mars_karsiligini_yayimlamiyor).
        #
        # 27 Ağustos 2026 (Z5S/PK1) — KAPANIŞ ÜÇÜNCÜ YOLDAN GELDİ: aşağıdaki
        # mesajın (1) ve (2) hâllerinin İKİSİ DE gerçekleşmedi. Marş karşılığı
        # takma adın YERİNE geçmedi, YANINA çıktı (üst katmanda ayrı ad + ayrı
        # künye). Takma ad hâlâ bulk_chain'i taşır, dolayısıyla bu KİLİT
        # AYNEN GEÇERLİDİR ve kaldırılmaz; yalnız ters yön borç imi söküldü.
        # L-B (v3.0.1, SV-05 karar 5) — REÇETENİN (2) HÂLİ UYGULANDI:
        # kullanıcıya tek "coolant exit temperature" yayımlanır, marş
        # koştuysa marşınki. Takma adın YENİ kaynağı istasyon marşıdır; toplu
        # kestirim temeli yazılı ayrı tanı alanına indi
        # (coolant_exit_temperature_bulk_estimate_K). Kimlik iki yönde de
        # kilitli: takma ad = marş, tanı alanı = bulk_chain.
        assert march['coolant_exit_temperature_K'] == \
            pytest.approx(tp['coolant_exit_temperature'], rel=1e-12)
        assert bulk['coolant_exit_temperature_K'] == pytest.approx(
            tp['coolant_exit_temperature_bulk_estimate_K'], rel=1e-12)
        assert 'station march' in tp['coolant_exit_temperature_basis']
        assert march['coolant_exit_temperature_K'] == \
            pytest.approx(tp['coolant_exit_temperature'], rel=1e-12), (
            'takma ad ⟷ bulk_chain kimliği koptu (üst katman %r, bulk %r).\n'
            'BU BEKÇİ BİLİNÇLİ KİLİTTİR (ÖH defteri P15B1-06 / ÖK-14): '
            'takma ad bugün bulk_chain\'e BAĞLIDIR ve bu satır o bağı '
            'kilitler. Kırmızıysa iki hâlden biridir:\n'
            '  (1) kimlik bozuldu — mutabakat bloğu artık başlıktaki sayıyı '
            'mutabık kılmıyor; bu bir GERİLEMEDİR, blok düzeltilir.\n'
            '  (2) onarım geldi — takma ad artık istasyon marşına ya da tek '
            'bir kaynağa bağlı. O gün bu bekçi SİLİNMEZ, ŞÖYLE GÜNCELLENİR: '
            'kimlik iddiasının sağ tarafı takma adın YENİ kaynağına çevrilir '
            '(``rec[\'station_march\'][\'coolant_exit_temperature_K\']`` ya da '
            '``tp[\'coolant_exit_temperature_basis\']``in adıyla işaret ettiği '
            'küme — beyan alanı zaten hangi kapanış olduğunu yazıyor) ve '
            'aynı commit\'te aşağıdaki ters yön borç imi '
            '(test_ust_katman_mars_karsiligini_yayimlamiyor) xfail\'den '
            'çıkarılır. Kilidin "geri al" demesine izin yok: iki bekçi '
            'birbirini tutuyor.'
            % (tp['coolant_exit_temperature'],
               bulk['coolant_exit_temperature_K']))
        # Sıcaklık artışı çıkışla çifttir (çıkış = giriş + artış): o da marşa
        # geçti, toplu artış tanı alanında.
        assert march['temperature_rise_K'] == \
            pytest.approx(tp['temperature_rise'], rel=1e-9)
        assert bulk['temperature_rise_K'] == pytest.approx(
            tp['temperature_rise_bulk_estimate_K'], rel=1e-12)
        assert bulk['pressure_drop_bar'] == \
            pytest.approx(tp['pressure_drop'], rel=1e-12)
        sm = tp['station_march']
        assert march['peak_heat_flux_MW_m2'] == \
            pytest.approx(sm['peak_heat_flux_MW_m2'], rel=1e-12)
        assert march['coolant_exit_temperature_K'] == \
            pytest.approx(sm['coolant_exit_temperature_K'], rel=1e-12)
        assert march['pressure_drop_bar'] == \
            pytest.approx(sm['coolant_pressure_drop_bar'], rel=1e-12)
        # Oran, bloğun kendi satırlarından türetilmiş olmalı (kimlik).
        assert rec['peak_flux_ratio_bulk_over_march'] == pytest.approx(
            bulk['peak_heat_flux_MW_m2'] / march['peak_heat_flux_MW_m2'],
            rel=1e-12)

    # -- ÖK-14: takma adın kapsamı ölçülü, borcu ters yönde imli -----------
    #
    # P15B1-06 (orta, "yanlış-değeri-kilitliyor") şunu ölçtü: yukarıdaki
    # kimlik iddiaları takma adı ``bulk_chain``'e BAĞLAR ve takma adı tek
    # kaynağa çekecek onarımı kıracak tek satır odur. ÖK-14 bu yüzden
    # onarımın SIRA KİLİDİDİR: kilit önce bilinçli-kilitleyen protokole
    # çevrilir (yukarıdaki mesaj), sonra kusurun kendisi ters yönde imlenir.
    # İkisi birlikte şunu söyledi: "bu bağ bilinçli, ölçülü ve GEÇİCİ".
    # Z5S/PK1 (27 Ağustos 2026) borcu üçüncü yoldan kapattı — marş karşılığı
    # üst katmana AYRI ADLA çıktı, ters yön imi söküldü; takma ad hâlâ
    # bulk_chain'e bağlı olduğu için aşağıdaki ölçüm bekçisi de yeşil kalır.

    #: Üst katmandaki çıplak alan ⟷ aynı devrenin istasyon marşı karşılığı.
    #: (Dördüncü takma ad ``temperature_rise``'ın marş karşılığı ayrı bir
    #: adla değil ``coolant_exit_temperature_K − inlet`` olarak türer; o
    #: yüzden doğrudan eşleşen üçlü kilitlenir.)
    #: L-B (v3.0.1, SV-05 karar 5): ``coolant_exit_temperature`` bu listeden
    #: ÇIKTI — takma ad artık marşı taşır (bkz. yukarıdaki kimlik ve
    #: ``test_cikis_takma_adi_marsa_bagli``). Akı ve ΔP hâlâ bulk_chain'dir.
    TAKMA_AD_CIFTLERI = (
        ('heat_flux', 'peak_heat_flux_MW_m2'),
        ('pressure_drop', 'coolant_pressure_drop_bar'),
    )

    def test_cikis_takma_adi_marsa_bagli(self, gg_zarf):
        """L-B (v3.0.1, SV-05 karar 5): tek yayımlanan çıkış sıcaklığı marşınki.

        Ters mutasyon (L-B RAPOR.md): ``_resolve_wall_temperature`` içinde
        takma ad ataması kaldırılırsa burası kırmızıdır (toplu 1283 K ⟷
        marş 459 K mertebesi).
        """
        _, res = gg_zarf
        tp = res['thermal_protection']
        cs = res['cooling_system']
        sm = tp['station_march']
        assert tp['coolant_exit_temperature'] == pytest.approx(
            sm['coolant_exit_temperature_K'], rel=1e-12)
        assert cs['coolant_exit_temperature'] == pytest.approx(
            sm['coolant_exit_temperature_K'], rel=1e-12)
        assert cs['coolant_exit_temperature_bulk_estimate_K'] == \
            pytest.approx(tp['channel_circuit_reconciliation']['bulk_chain'][
                'coolant_exit_temperature_K'], rel=1e-12)
        assert 'DIAGNOSTIC' in cs['coolant_exit_temperature_bulk_estimate_basis']

    @staticmethod
    def _ust_katman_skalerleri(tp):
        """``thermal_protection``'ın ÇIPLAK (iç blok olmayan) sayı alanları."""
        return {k: v for k, v in tp.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)}

    def test_takma_adin_kapsami_bulk_chain_ile_sinirli_olculdu(self, gg_zarf):
        """Kilidin ÖLÇÜLEN gerekçesi: üç takma ad da bulk, marş DEĞİL.

        Bu bekçi bugünkü kusuru KAYDEDER (korumaz): iki kümenin gerçekten
        AYRIŞTIĞINI sayıyla gösterir. Ayrışma kapanırsa (iki zincir tek
        kaynağa indiyse) burası kırmızıya döner ve o gün ters yön borç imi
        de düşer — yani bu satırlar onarımı görmeden geçemez.

        ÖLÇÜLDÜ (2026-08-27, gg senaryosu): akı 80,4285 ⟷ 6,3380 MW/m²
        (12,69×), çıkış 1283,4599 ⟷ 459,0098 K, ΔP 0,3695 ⟷ 0,2257 bar.
        (P15'in kendi ölçümü 746,2323 ⟷ 449,8854 K idi; senaryo farklı,
        kusur aynı — takma ad her iki koşuda da yalnız bulk'ı taşıyor.)
        """
        _, res = gg_zarf
        tp = res['thermal_protection']
        sm = tp['station_march']
        rec = tp['channel_circuit_reconciliation']
        for ust, mars in self.TAKMA_AD_CIFTLERI:
            assert tp[ust] == pytest.approx(
                rec['bulk_chain'][{'heat_flux': 'peak_heat_flux_MW_m2',
                                   'coolant_exit_temperature':
                                       'coolant_exit_temperature_K',
                                   'pressure_drop': 'pressure_drop_bar'}[ust]],
                rel=1e-12), (
                '%s takma adı artık bulk_chain\'i taşımıyor — ÖK-14 onarımı '
                'gelmiş olabilir: bilinçli kilidin reçetesini uygulayın '
                '(yukarıdaki mesaj) ve ters yön imini kaldırın' % ust)
            assert tp[ust] != pytest.approx(sm[mars], rel=1e-6), (
                '%s: iki zincir artık aynı sayıyı veriyor (%r ⟷ %r). Bu İYİ '
                'haber olabilir (devre tek kaynağa indi) ama sessiz kalamaz: '
                'ÖK-14/P15B1-06 borcunun gerekçesi ortadan kalkmıştır, '
                'aşağıdaki xfail imi kaldırılmalı ve bu bekçi yeni sözleşmeye '
                'göre yeniden yazılmalıdır.' % (ust, tp[ust], sm[mars]))

    # ÖH defter P15B1-06 — Z5S/PK1 onarımıyla yeşile döndü, ters yön borç imi
    # (xfail strict) 27 Ağustos 2026'da söküldü. Kapanış ÜÇÜNCÜ yoldan geldi:
    # marş karşılığı takma adın YERİNE geçmedi, YANINA çıktı (üst katmanda
    # heat_flux_station_march_MW_m2 / coolant_exit_temperature_station_march_K
    # / pressure_drop_station_march_bar + station_march_scalars_basis). Bu
    # yüzden yukarıdaki BİLİNÇLİ KİLİT (:293-321) AYNEN DURUYOR: takma adlar
    # hâlâ bulk_chain'e bağlıdır ve o bağ hâlâ kilitlidir.
    def test_ust_katman_mars_karsiligini_yayimlamiyor(self, gg_zarf):
        """Marş karşılığı üst katmanda VAR (eski ters yön borç imi).

        ÖH defteri **P15B1-06** (orta, yanlış-değeri-kilitliyor): aynı
        soğutma devresinin iki çözümünden yalnız biri (toplu Bartz zinciri)
        ``thermal_protection``'ın çıplak alanlarına çıkar; kuple çözülmüş
        istasyon marşı yalnız ``station_march`` alt bloğunda kalır. Çıplak
        alanı okuyan her tüketici (panel, PDF/ihracat, AI belgesi) bu yüzden
        tek kümeyi görür.

        Bu test kilitlenen sözleşmeyi yazar: üst katmanda marş karşılığını
        taşıyan bir alan BULUNMALI. Ad ARANMAZ — onarım alanı istediği adla
        açabilir (``coolant_exit_temperature_station_march_K``, ``..._solved``
        vb.); ölçüt DEĞERİN üst katmanda görünmesidir. Onarım (Z5S/PK1) tam
        bunu yaptı, o yüzden bekçi artık ileri yönde yeşil koşuyor: marş
        karşılığı üst katmandan SİLİNİRSE burası yeniden kırmızıya döner.
        """
        _, res = gg_zarf
        tp = res['thermal_protection']
        sm = tp['station_march']
        skalerler = self._ust_katman_skalerleri(tp)
        eksik = []
        for ust, mars in self.TAKMA_AD_CIFTLERI:
            hedef = sm[mars]
            tasiyan = [k for k, v in skalerler.items()
                       if k != ust and hedef == pytest.approx(v, rel=1e-9)]
            if not tasiyan:
                eksik.append('%s: marş karşılığı %r üst katmanda yok '
                             '(çıplak alan %r taşıyor)'
                             % (ust, hedef, tp[ust]))
        assert not eksik, (
            'thermal_protection üst katmanı istasyon marşı karşılıklarını '
            'yayımlamıyor (P15B1-06):\n  %s\nÜst katman alanları: %s'
            % ('\n  '.join(eksik), sorted(skalerler)))

    def test_enerji_dengesi_olculu_ve_hukum_tutarli(self, gg_zarf):
        """Hüküm ölçümden: marş kendi dengesini kapatır, hüküm ondan türer."""
        _, res = gg_zarf
        rec = res['thermal_protection']['channel_circuit_reconciliation']
        eb = rec['march_energy_balance']
        # Marşın kendi enerji dengesi ÖLÇÜLÜ kapalı: ṁ·c̄p·ΔT = ∮q dA.
        assert eb['relative_gap'] is not None and eb['relative_gap'] < 1e-6
        assert eb['mdot_cp_dT_kW'] == pytest.approx(
            eb['integral_q_dA_kW'], rel=1e-6)
        # Taşınabilirlik hükmü kendi sayılarıyla tutarlı olmalı.
        gereken = rec['design_flux_film_dt_required_K']
        mevcut = rec['design_film_dt_available_K']
        assert rec['design_flux_supportable_by_channels'] == (
            gereken is not None and gereken <= mevcut)
        if not rec['design_flux_supportable_by_channels']:
            assert 'station_march' in rec['verdict']

    #: Başlık sayılarının künye alanları (dördü de aynı metni taşır).
    KUNYE_ALANLARI = ('heat_flux_basis', 'temperature_rise_basis',
                      'coolant_exit_temperature_basis', 'pressure_drop_basis')

    def test_baslik_alanlari_model_adini_soyler(self, gg_zarf):
        """Çıplak akı/ΔT/çıkış sayıları hangi cidar kapanışından, yazmalı."""
        _, res = gg_zarf
        tp = res['thermal_protection']
        for alan in self.KUNYE_ALANLARI:
            assert alan in tp, f'{alan} yok — sayı yine beyansız'
            assert ('design wall temperature' in tp[alan]
                    or 'station march' in tp[alan]), tp[alan]
        # RP-1 çözülmemiş zincirde beyan mutabakat bloğuna işaret etmeli.
        if 'design wall temperature' in tp['heat_flux_basis']:
            assert 'channel_circuit_reconciliation' in tp['heat_flux_basis']

    # -- ÖH D15 birleşme etkileşimi: zarf DIŞI dal ilk kez kilitlendi ------
    def test_zarf_disinda_mars_reddi_beyanli_ve_sizintisiz(self, gg):
        """Marş model zarfının dışında REDDEDİLİYORSA fail-closed olmalı.

        Termo-uçuş **P4B2-09** kapısının tüketici tarafındaki karşılığı.
        ``gg`` (form varsayılanları, cidar 5 mm) o kapının DIŞINDA kalır —
        ölçüldü: düz-levha ⟷ silindirik iletim direnci farkı %13,4 > %10.

        Üç şart birlikte: (1) red BEYANLI (``station_march_status`` reddin
        alanını ve zarfı adıyla söyler), (2) marş türevi HİÇBİR sayı üst
        katmana SIZMAZ, (3) başlık künyeleri var olmayan bloklara İŞARET
        ETMEZ. (3) birleşmede kırılmıştı: künye hâlâ "the solved equilibrium
        is the station_march block ... published in
        channel_circuit_reconciliation" diyordu, oysa iki blok da yanıtta
        yoktu — ürün onarıldı (künye marş kararından SONRA kesinleşiyor).
        """
        _, res = gg
        tp = res['thermal_protection']
        if 'station_march' in tp:
            pytest.skip('senaryo artık zarfın içinde — bu dal ölçülemiyor')
        # (1) Red beyanlı ve gerekçesi adıyla.
        durum = str(tp.get('station_march_status') or '')
        assert durum, 'marş yok ve sebebi de yok — sessiz eksiklik'
        assert 'wall_thickness' in durum and 'envelope' in durum, durum
        # (2) Marş türevi sayı sızıntısı yok.
        sizanlar = [k for k, v in tp.items()
                    if 'station_march' in k and isinstance(v, (int, float))
                    and not isinstance(v, bool)]
        assert not sizanlar, (
            f'marş reddedildi ama marş türevi sayı yayımlanıyor: {sizanlar}')
        assert 'channel_circuit_reconciliation' not in tp
        # (3) Künye var olmayan bloğa yollamıyor.
        for alan in self.KUNYE_ALANLARI:
            kunye = str(tp[alan])
            assert 'channel_circuit_reconciliation' not in kunye, (
                f'{alan} var olmayan mutabakat bloğuna işaret ediyor:\n'
                f'{kunye}')
            assert 'station_march_status' in kunye, (
                f'{alan} reddin nerede yazdığını söylemiyor:\n{kunye}')
