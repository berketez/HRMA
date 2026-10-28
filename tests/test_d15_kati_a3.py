"""ÖH Dalga-15 · kulvar 'kati' · aşama 3 — onarım bekçileri.

Sekiz kalem: P2B1-07, P2B1-11, P2B2-03, P2B2-04, P2B2-05, P2B2-07,
P2B2-10, P2B2-11.

Her sınıf, onarım geçici olarak geri alındığında KIRMIZI olacak biçimde
yazılmıştır (ters-mutasyon kanıtı: docs/scofield/raw/OH/D15/kati/a3/
mutasyon.py + mutasyon_sonuc.json). Sayıların hepsi
docs/scofield/raw/OH/D15/kati/a3/once.json ⟷ sonra.json'dan gelir.
"""
import contextlib
import io

import numpy as np
import pytest

from hrma.constants import ISA_TABLE_TOP_M, isa_pressure, isa_temperature
from hrma.engines.solid_rocket_engine import (
    AL_TO_AL2O3_MASS_RATIO,
    SOLID_CONDENSED_MASS_FRACTION,
    SOLID_DEFAULT_GEOMETRY_MM,
    SolidGeometryError,
    SolidRocketEngine,
    _condensed_mass_fraction,
)


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _motor(**kw):
    ov = kw.pop('overrides', None)
    # V301/K-A (22 Eki): eski çapa A_p/A_t = 0,947'lik boğulan portlu
    # varsayılan motoru kilitliyordu (çekirdek 30 mm); örnek motorun TEK
    # tanımı okunur.
    p = dict(grain_type='bates', propellant_type='apcp',
             chamber_diameter=100, grain_length=500,
             core_diameter=SOLID_DEFAULT_GEOMETRY_MM['core_diameter'],
             chamber_pressure=40)
    p.update(kw)
    if ov is not None:
        p['overrides'] = dict(ov)
    return SolidRocketEngine(**p)


def _geopotansiyel(alt_m):
    """Geometrik -> geopotansiyel irtifa (US Std Atm 1976)."""
    return alt_m * 6356766.0 / (6356766.0 + alt_m)


# ===========================================================================
# P2B1-07 — kurucuda FAIL-CLOSED geometri/basınç kapısı
# ===========================================================================
class TestP2B1_07KurucuKapisi:
    """Fiziksel olarak imkânsız girdi kurucuda reddedilir, sonuç yayımlanmaz.

    Ölçüm (once.json): kapı yokken core_diameter = -30 mm (kasa 100 mm)
    64 anahtarlı TAM sonuç veriyordu — Isp 27,9941 s ⟷ aynı yanıtta
    isp_vacuum 267,8985 s (9,570 kat iç çelişki).
    """

    KOTU = [
        ('core_diameter', dict(core_diameter=-30), 'negative_core'),
        ('core_diameter', dict(core_diameter=120), 'core_not_inside_case'),
        ('core_diameter', dict(core_diameter=100), 'core_not_inside_case'),
        ('chamber_diameter', dict(chamber_diameter=0), 'not_positive'),
        ('chamber_pressure', dict(chamber_pressure=0), 'not_positive'),
        ('chamber_pressure', dict(chamber_pressure=-40), 'not_positive'),
        ('grain_length', dict(grain_length=0), 'not_positive'),
        ('grain_length', dict(grain_length=-500), 'not_positive'),
        ('burn_rate_a', dict(burn_rate_a=0.0), 'not_positive'),
        ('burn_rate_a', dict(burn_rate_a=-0.002), 'not_positive'),
    ]

    @pytest.mark.parametrize('alan,kw,gerekce', KOTU)
    def test_fiziksel_olmayan_girdi_kurucuda_reddedilir(self, alan, kw,
                                                        gerekce):
        with pytest.raises(SolidGeometryError) as exc:
            _motor(**kw)
        kunye = exc.value.kunye
        assert kunye['field'] == alan
        assert kunye['reason'] == gerekce
        assert kunye['motor_form'] == 'solid'

    def test_bool_sayi_yerine_gecmez(self):
        with pytest.raises(SolidGeometryError) as exc:
            _motor(chamber_pressure=True)
        assert exc.value.kunye['reason'] == 'boolean_is_not_a_number'

    def test_sonsuz_deger_reddedilir(self):
        with pytest.raises(SolidGeometryError) as exc:
            _motor(grain_length=float('inf'))
        assert exc.value.kunye['reason'] == 'not_finite'

    def test_saglikli_motor_kapiya_takilmaz(self):
        """ÖK-22: kapı sağlıklı envanteri daraltmaz."""
        for gt in ('bates', 'star', 'wagon_wheel', 'finocyl', 'slotted',
                   'end_burner'):
            r = _sessiz(_motor(grain_type=gt).calculate_performance)
            assert not r.get('error'), gt
        # end_burner'da port yoktur: çekirdek kasadan büyük olabilir
        assert _motor(grain_type='end_burner', core_diameter=100) is not None

    def test_monte_carlo_ucu_ayni_girdiyi_reddeder(self):
        """/api/solid-monte-carlo ⟷ /calculate_solid asimetrisi kapandı.

        Ölçüm (once.json): MC ucu HTTP 200 + n_failed_runs = 0 + 100 mm
        kasada throat_diameter_mm = 87,258 döndürüyordu; kardeş uç aynı
        girdiyi 400 ile reddediyordu.

        ÖH D15 birleştirme (1 Eyl 2026): app-api kulvarı aynı uca KENDİ
        ön kapısını koydu (P7B2-06 + cidar payı bandı) ve ``core=-30``
        artık oraya takılıyor; kurucunun ``solid_input_rejected``
        çevirisine bu gövdeyle inilmiyor. İki kapı da FAIL-CLOSED, ikisi
        de 422 + ``invalid_fields`` veriyor; ÖNCE ateşlenen kapı DAHA
        ZENGİN gövde yayımlıyor (``accepted_range`` + birim), o yüzden
        kazanır. Bu bekçinin iddiası ada değil REDDE bağlı: uç kardeşiyle
        aynı girdiyi reddediyor mu, ve kurucunun kapısı hâlâ uca bağlı mı.
        İkincisi ayrı bir kolla (``burn_rate_a``, ön kapının SAYMADIĞI
        alan) ölçülür, böylece çeviri dalı ölü kalmaz.
        """
        from hrma.app import app
        from hrma.engines.solid_rocket_engine import SolidGeometryError
        app.config['TESTING'] = True
        govde = dict(grain_type='bates', propellant_type='apcp',
                     chamber_diameter=100, grain_length=500,
                     core_diameter=-30, chamber_pressure=40, n_samples=20)
        with app.test_client() as c:
            resp = _sessiz(c.post, '/api/solid-monte-carlo', json=govde)
            assert resp.status_code == 422, resp.status_code
            j = resp.get_json()
            assert j['error'] in ('solid_input_rejected',
                                  'invalid_solid_monte_carlo_input'), j
            assert j['invalid_fields'][0]['field'] == 'core_diameter'
            assert 'n_failed_runs' not in j and 'throat_diameter_mm' not in j

            # KURUCUNUN kapısı hâlâ uca bağlı: ön kapının saymadığı bir
            # alanla (burn_rate_a) reddin ta kendisi ölçülür.
            kurucu = _sessiz(c.post, '/api/solid-monte-carlo',
                             json=dict(govde, core_diameter=30,
                                       burn_rate_a=-0.002))
            assert kurucu.status_code == 422, kurucu.status_code
            k = kurucu.get_json()
            # ÖH D18 / OH-D16-10 — BEKÇİ ÇEVRİLDİ. Bu satır KUSURU
            # KORUYORDU: aynı uç, aynı ret sınıfı için iki ad
            # (``solid_input_rejected`` ⟷ ``invalid_solid_monte_carlo_input``)
            # döndürmesini şart koşuyordu. Uç artık TEK ad yayımlıyor
            # (``SOLID_MC_REJECT_ERROR``); bekçinin GERÇEK iddiası —
            # "kurucunun kapısı hâlâ uca bağlı" — ``rejected_by`` ile
            # ölçülür, yani dal ölü kalmaz.
            assert k['error'] == 'invalid_solid_monte_carlo_input', k
            assert k['rejected_by'] == 'solid_engine_constructor', k
            assert k['error_type'] == 'SolidGeometryError', k
            assert k['invalid_fields'][0]['field'] == 'burn_rate_a', k
            assert k['invalid_fields'][0]['reason'] == 'not_positive', k
            # kardeş uç aynı girdiyi reddetmeye devam ediyor
            kardes = _sessiz(c.post, '/calculate_solid',
                             json=dict(govde, n_samples=None))
            assert kardes.status_code >= 400
            # sağlıklı girdi İKİ uçta da geçmeye devam ediyor
            for yol in ('/api/solid-monte-carlo', '/calculate_solid'):
                # V301/K-A: eski çapa A_p/A_t = 0,947'lik boğulan portlu varsayılan motoru kilitliyordu;
                # sağlıklı girdi örnek motorun geçerli çekirdeğidir.
                iyi = _sessiz(c.post, yol, json=dict(
                    govde,
                    core_diameter=SOLID_DEFAULT_GEOMETRY_MM['core_diameter']))
                assert iyi.status_code == 200, yol


# ===========================================================================
# P2B1-11 — yoğuşmuş faz kesri kaydın KENDİ formülasyonundan
# ===========================================================================
class TestP2B1_11YogusmusFazKesri:
    """Metalsiz kompozit, alüminyumlu APCP'nin X_p'sini devralmaz."""

    def test_metalsiz_kompozit_sifir_yogusmus_faz(self):
        for k in ('apcp_nonaluminized', 'blue_thunder'):
            x, kaynak, kunye = _condensed_mass_fraction(k)
            assert x == 0.0, f'{k}: X_p = {x}'
            assert 'derived from' in kunye
            assert kaynak != 'apcp', f'{k}: hâlâ apcp devralınıyor'
            assert kaynak == k

    def test_metal_yuzdesi_kaydin_kendisinden(self):
        """pban_ap_al %16 Al -> 0,16 x 1,88955 = 0,302328 (0,340119 DEĞİL)."""
        x, kaynak, kunye = _condensed_mass_fraction('pban_ap_al')
        assert '16% metal fuel' in kunye
        assert x == pytest.approx(0.16 * AL_TO_AL2O3_MASS_RATIO, rel=1e-12)
        assert x != pytest.approx(
            SOLID_CONDENSED_MASS_FRACTION['apcp'], rel=1e-9)
        assert kaynak == 'pban_ap_al'

    def test_tablo_satiri_ile_turetim_ayrismiyor(self):
        """%18 Al'li kayıttan türetilen kesir tablo 'apcp' satırına eşit."""
        x, _kaynak, _kunye = _condensed_mass_fraction('htpb_ap_al')
        assert x == pytest.approx(SOLID_CONDENSED_MASS_FRACTION['apcp'],
                                  rel=1e-12)

    def test_yayimlanan_iki_fazli_kayip_metalsizde_sifir(self):
        """Ölçüm: %4,08142 -> %0,0; particle_diameter_um artık yok."""
        r = _sessiz(_motor(
            propellant_type='apcp_nonaluminized').calculate_performance)
        tv = r['detailed_analysis']['performance_metrics'][
            'theoretical_vs_actual_isp']
        assert tv['two_phase_losses'] == 0.0
        assert 'inherited' not in tv['two_phase_losses_basis']
        assert 'X_p = 0.000' in tv['two_phase_losses_basis']
        assert r['two_phase_loss']['particle_diameter_um'] is None

    def test_metalli_kayitlar_bozulmadi(self):
        """apcp ve şeker ailesi tablodan okumaya devam ediyor."""
        for k in ('apcp', 'kndx', 'knsu', 'double_base'):
            x, kaynak, kunye = _condensed_mass_fraction(k)
            assert kaynak == k
            assert x == SOLID_CONDENSED_MASS_FRACTION[k]
            assert 'SOLID_CONDENSED_MASS_FRACTION' in kunye


# ===========================================================================
# P2B2-03 — combustion_smoothness kırpılır ve kırpması BEYAN EDİLİR
# ===========================================================================
class TestP2B2_03YanmaDuzgunlugu:
    """Negatif yüzde yayımlanmaz; sözleşme kardeş alanla birebir aynı.

    Ölçülen negatif üreten girdiler (slotted, D_kasa = 100, D_çekirdek = 30,
    APCP): L/P = 1500/70 -> -5,218 · 2000/70 -> -7,098 · 2500/70 -> -8,820 ·
    1500/40 -> -0,614 · 2000/40 -> -2,284 · 2500/40 -> -3,562.
    """

    #: (grain_length mm, chamber_pressure bar) — slotted + slot_count = 8.
    #: Ölçülen ham (kırpılmamış) 100 - osc değerleri sırasıyla
    #: -5,218 · -7,098 · -8,820 · -0,614 · -2,284 · -3,562.
    NEGATIF_SMOOTHNESS_GIRDILERI = [(1500, 70), (2000, 70), (2500, 70),
                                    (1500, 40), (2000, 40), (2500, 40)]
    SLOT = {'slot_count': 8}

    # V301/K-A (22 Eki) — TERS KAPIYA ÇEVRİLDİ. Negatif ham düzgünlük
    # yalnız portu BOĞULAN geometrilerde ölçülüyordu (çekirdek 30 mm, uzun
    # slotted tane: A_p/A_t < 1). Geçerli portlu geometrilerde ham değer
    # pozitif kalıyor (ölçüldü: L 1000-2500 mm, çekirdek 70-80 mm, 10-47).
    # Bu girdiler artık YAYIMLANMAZ: port boğazdan küçük (KT-23) -> RET.
    @pytest.mark.parametrize('L,P', NEGATIF_SMOOTHNESS_GIRDILERI)
    def test_negatif_yuzde_yayimlanmaz(self, L, P):
        from hrma.engines.solid_rocket_engine import SolidDesignRejected
        with pytest.raises(SolidDesignRejected) as exc:
            _sessiz(_motor(grain_type='slotted', grain_length=L,
                           chamber_pressure=P, core_diameter=30,
                           overrides=self.SLOT).calculate_performance)
        assert exc.value.code == 'port_smaller_than_throat', (L, P)

    @pytest.mark.parametrize('L,P', NEGATIF_SMOOTHNESS_GIRDILERI)
    def test_kirpma_beyan_edilir_ve_ham_buyukluk_yaninda_durur(self, L, P):
        from hrma.engines.solid_rocket_engine import SolidDesignRejected
        with pytest.raises(SolidDesignRejected) as exc:
            _sessiz(_motor(grain_type='slotted', grain_length=L,
                           chamber_pressure=P, core_diameter=30,
                           overrides=self.SLOT).calculate_performance)
        kunye = exc.value.invalid_fields[0]
        assert kunye['port_to_throat_area_ratio'] <= 1.0, (L, P)
        assert kunye['field'] == 'core_diameter'

    def test_kirpilmayan_girdide_bayrak_yanlis_ve_ozdeslik_tutuyor(self):
        r = _sessiz(_motor().calculate_performance)
        tp = r['detailed_analysis']['thrust_profile_analysis']
        assert tp['combustion_smoothness_was_clamped'] is False
        assert tp['combustion_smoothness'] == pytest.approx(
            100.0 - tp['pressure_oscillations_percent'], rel=1e-12)

    def test_kardes_alanin_sozlesmesi_bozulmadi(self):
        """thrust_stability ikizi (B2-2) aynı desende kalmalı."""
        r = _sessiz(_motor().calculate_performance)
        tp = r['detailed_analysis']['thrust_profile_analysis']
        for alan in ('thrust_stability', 'thrust_stability_was_clamped',
                     'thrust_variation_coefficient_percent',
                     'thrust_stability_basis'):
            assert alan in tp, alan


# ===========================================================================
# P2B2-04 — web kullanımının paydası FİZİKSEL web'dir
# ===========================================================================
class TestP2B2_04WebKullanimi:
    """Tükenmiş grain %100'e yakın okur; payda tarama sınırı değildir."""

    #: (grain, yayımlanan önce, fiziksel taban) — once.json
    ONCE_YAYIMLANAN_KULLANIM = {'star': 56.0849, 'wagon_wheel': 46.2111,
            'finocyl': 69.9998, 'slotted': 45.6724}

    @pytest.mark.parametrize('gt', sorted(ONCE_YAYIMLANAN_KULLANIM))
    def test_payda_fiziksel_tuketilebilir_web(self, gt):
        """ÖH D17 (P2B2-04 ŞART) — ÇEVRİLDİ.

        Bu bekçi paydanın TAM OLARAK (D_kasa - D_çekirdek)/2 olmasını şart
        koşuyordu ve poligon tiplerde kusuru kilitliyordu: yakıt fiilen
        bittiği hâlde (Ab(w_tük)/Ab(0) = 0,034/0,038/0,025) kullanım
        %65-80 okunuyordu. Payda artık ÇÖZÜCÜNÜN KENDİ tükeniş webi; iddia
        "payda şu formüldür"den "payda çözücünün tükeniş tanımıyla birebir
        ve radyal eti aşmaz"a çevrildi — gevşetme değil, ölçülebilirlik.
        """
        e = _motor(grain_type=gt)
        c = _sessiz(e.calculate_thrust_curve)
        tuketilen = e._consumed_web(c)
        radyal = (e.D_chamber - e.D_core) / 2.0
        payda = e._available_web_thickness()
        assert 0.0 < payda <= radyal + 1e-12, (gt, payda, radyal)
        if gt in ('star', 'wagon_wheel', 'slotted', 'finocyl'):
            assert payda == pytest.approx(e._geometric_burnout_web(),
                                          rel=1e-12), gt
        r = _sessiz(e.calculate_performance)
        yayin = r['detailed_analysis']['grain_regression_analysis'][
            'web_thickness_utilization']
        assert yayin == pytest.approx(
            min(100.0, 100.0 * tuketilen / payda), rel=1e-9)
        # ESKİ (kusurlu) taban ile ölçülebilir biçimde AYRIŞMALI:
        # _max_web_thickness shapely'li tiplerde kasa YARIÇAPIDIR.
        assert yayin > self.ONCE_YAYIMLANAN_KULLANIM[gt] + 1.0, (
            f'{gt}: {yayin} hâlâ tarama sınırı tabanına yakın')

    @pytest.mark.parametrize('gt', sorted(ONCE_YAYIMLANAN_KULLANIM))
    def test_tukenmis_grain_tam_kullanim_gosterir(self, gt):
        """Yanma alanı sıfıra inen grain eksik kullanılmış görünemez.

        ÖH D17 (P2B2-04 ŞART) — ÇEVRİLDİ. Eşik >60 idi ve tam tükenmiş
        poligon grainlerin %65-80 okumasını KİLİTLİYORDU: ölçüldü
        (docs/scofield/raw/OH/D17/kati/a1/once.json) star %80,121 /
        wagon_wheel %66,016 / slotted %65,246 yayımlanırken aynı koşuda
        Ab(w_tüketilen)/Ab(0) sırasıyla 0,0335 / 0,0375 / 0,0254, yani grain
        BİTMİŞTİ. Payda çözücünün kendi tükeniş webine alındıktan sonra
        ölçülen kullanım: star %98,999 / wagon_wheel %98,391 /
        slotted %98,273 / finocyl %100,000 (sonra.json). Eşik bu yüzden
        60 -> 98 olarak SIKILAŞTIRILDI (gevşetme değil daraltma).

        Kalan ~%1-1,7 payda değil ÇÖZÜCÜ artığıdır ve BEYANLIDIR: itki
        eğrisi star'da t=4,79 s'de termination=None ile duruyor ve son
        saklanan web 28,042 mm iken geometrik tükeniş 28,326 mm'de
        (Ab(28,042 mm)/Ab(0) = 0,0335). Yani son ~0,28 mm integrale hiç
        girmiyor. Bu, ayrı bir çözücü sonlandırma kalemidir (ÖH D17 kati a1
        raporunda yeni bulgu olarak bildirildi); %99'luk eşik onu buraya
        borç yazardı, %98 ise paydanın onarımını kilitler.
        """
        # V301/K-A: eski çapa A_p/A_t = 0,947'lik boğulan portlu varsayılan motoru kilitliyordu (wagon_wheel
        # çekirdek 30 mm'de A_p/A_t < 1, reddediliyor). Ölçüm çekirdeği
        # 36 mm: dört tipte de port geçerli; wagon_wheel 48 mm'de %97,93
        # okuyor (eşiğin altındaki sonlandırma kalemi, bkz. yukarıdaki not).
        e = _motor(grain_type=gt, core_diameter=36)
        r = _sessiz(e.calculate_performance)
        yayin = r['detailed_analysis']['grain_regression_analysis'][
            'web_thickness_utilization']
        assert yayin >= 98.0, f'{gt}: {yayin}'

    @pytest.mark.parametrize('gt', ('star', 'wagon_wheel', 'slotted',
                                    'finocyl'))
    def test_payda_cozucunun_kendi_tukenis_webi(self, gt):
        """ÖH D17 (P2B2-04): poligon paydası Ab -> 0 webidir, (D-d)/2 değil.

        Ters mutasyon (payda yeniden (D_kasa - D_çekirdek)/2) bu iddiayı
        kırar; ayrıca paydanın çözücünün kendi tükeniş tanımıyla (Ab(w) = 0)
        birebir olduğunu sınar.
        """
        e = _motor(grain_type=gt)
        payda = e._available_web_thickness()
        radyal = (e.D_chamber - e.D_core) / 2.0
        tukenis = e._geometric_burnout_web()
        assert tukenis is not None, gt
        assert payda == pytest.approx(tukenis, rel=1e-12), gt
        assert payda <= radyal + 1e-12, gt
        # Paydada yanma alanı gerçekten sönmüş olmalı.
        assert _sessiz(e.calculate_burn_area, payda * (1.0 + 1e-6)) <= 0.0
        assert _sessiz(e.calculate_burn_area, payda * (1.0 - 1e-3)) > 0.0

    def test_end_burner_ve_bates_bozulmadi(self):
        for gt, beklenen in (('bates', 99.94), ('end_burner', 100.0)):
            e = _motor(grain_type=gt)
            r = _sessiz(e.calculate_performance)
            yayin = r['detailed_analysis']['grain_regression_analysis'][
                'web_thickness_utilization']
            assert yayin == pytest.approx(beklenen, abs=0.1), gt

    def test_payda_kunyesi_yayimlanir_ve_tarama_sinirini_disliyor(self):
        r = _sessiz(_motor(grain_type='star').calculate_performance)
        k = r['detailed_analysis']['grain_regression_analysis'][
            'web_thickness_utilization_basis']
        assert 'consumable web' in k
        assert 'NOT the solver scan bound' in k

    def test_tarama_siniri_ayri_bir_buyukluk_olarak_duruyor(self):
        """_max_web_thickness kaldırılmadı; iki büyüklük ayrı ve farklı."""
        e = _motor(grain_type='star')
        assert e._max_web_thickness() == pytest.approx(e.D_chamber / 2)
        assert e._max_web_thickness() != pytest.approx(
            e._available_web_thickness())


# ===========================================================================
# P2B2-05 — uyarı bloğu ÇÖZÜCÜNÜN port kesitini okur
# ===========================================================================
class TestP2B2_05PortKesitiTekTanim:
    """Aynı yanıtta iki farklı başlangıç kütle akısı olamaz.

    Ölçüm (once.json) uyarı / çözücü: slotted 1,8501x · star 1,9095x ·
    wagon_wheel 1,7497x · bates 1,0001x.
    """

    #: Uyarının DOĞRU akıyla hâlâ çıktığı tipler.
    AKI_TIPLERI = ['slotted', 'wagon_wheel', 'bates']

    @staticmethod
    def _uyari_akisi(r):
        for w in (r.get('design_warnings') or []) + (r.get('warnings') or []):
            if isinstance(w, dict) and w.get(
                    'code') == 'warn.solid.initial_mass_flux_high':
                return (w.get('params') or w).get('mass_flux_kg_m2s')
        return None

    #: V301/K-A: eski çapa A_p/A_t = 0,947'lik boğulan portlu varsayılan motoru kilitliyordu. Akı ve
    #: port/boğaz uyarısının ÜÇ tipte de çıktığı geçerli portlu çekirdek
    #: 36 mm (ölçüldü: bates/slotted/wagon_wheel ikisi de var; 38 mm'de
    #: wagon_wheel akı uyarısı düşüyor).
    UYARILI_CEKIRDEK_MM = 36

    @pytest.mark.parametrize('gt', AKI_TIPLERI)
    def test_uyari_metnindeki_akis_cozucununkiyle_ayni(self, gt):
        r = _sessiz(_motor(grain_type=gt,
                           core_diameter=self.UYARILI_CEKIRDEK_MM
                           ).calculate_performance)
        cozucu = r['detailed_analysis']['grain_regression_analysis'][
            'erosive_burning_effects']['mass_flux_kg_m2s']
        uyari = self._uyari_akisi(r)
        assert uyari is not None, f'{gt}: uyarı çıkmadı'
        # uyarı gövdesi round(G_0) ile yayımlanır -> 1 kg/m2s tolerans
        assert abs(float(uyari) - float(cozucu)) <= 1.0, (
            f'{gt}: uyarı {uyari} ⟷ çözücü {cozucu}')

    @pytest.mark.parametrize('gt', AKI_TIPLERI)
    def test_uyari_bloğu_kendi_port_alanini_kurmuyor(self, gt):
        """Kullanılan kesit _port_flow_area(0) olmalı, π(D_core/2)² değil."""
        e = _motor(grain_type=gt, core_diameter=self.UYARILI_CEKIRDEK_MM)
        c = _sessiz(e.calculate_thrust_curve)
        gercek = float(e._port_flow_area(0.0))
        dairesel = float(np.pi * (e.D_core / 2.0) ** 2)
        r = _sessiz(e.calculate_performance)
        uyari = self._uyari_akisi(r)
        assert uyari is not None, gt
        m_dot0 = float(c['mass_flow'][0])
        assert abs(float(uyari) - m_dot0 / gercek) <= 1.0, gt
        if gt != 'bates':
            assert gercek != pytest.approx(dairesel, rel=1e-6), (
                f'{gt}: iki alan zaten aynı, bekçi ayrımı göremez')
            assert abs(float(uyari) - m_dot0 / dairesel) > 1.0, (
                f'{gt}: uyarı hâlâ dairesel kesitten okuyor')

    def test_star_yanlis_alarmi_kalkti(self):
        """star'da uyarı ŞİŞMİŞ sayıdan ateşleniyordu: 1985 ⟷ 1039,53.

        Doğru akı eşiğin (1400 kg/m2s) ALTINDA olduğu için uyarı artık
        çıkmıyor — susturma değil, yanlış alarmın kalkması.
        """
        # V301/K-A: star çekirdek 30 mm'de port geçerli (kapıdan geçer);
        # ölçümün kendi geometrisi açıkça verilir.
        e = _motor(grain_type='star', core_diameter=30)
        r = _sessiz(e.calculate_performance)
        cozucu = r['detailed_analysis']['grain_regression_analysis'][
            'erosive_burning_effects']['mass_flux_kg_m2s']
        assert cozucu == pytest.approx(1039.53, abs=1.0)
        assert self._uyari_akisi(r) is None, 'star hâlâ şişmiş akıyla uyarıyor'
        # dairesel (kusurlu) kesitten okunsaydı eşiği AŞARDI:
        c = _sessiz(e.calculate_thrust_curve)
        dairesel = float(np.pi * (e.D_core / 2.0) ** 2)
        assert float(c['mass_flow'][0]) / dairesel > 1400.0

    def test_saglikli_uyari_sozlesmesi_bozulmadi(self):
        """Uyarılı geometride uyarı yine çıkmalı (uyarı susturulmadı).

        V301/K-A: varsayılan motor artık geçerli portlu (A_p/A_t >= 2) ve
        bu uyarıları BİLEREK basmıyor (KT-20); sözleşme uyarılı geçerli
        geometride (çekirdek 36 mm) ölçülür.
        """
        r = _sessiz(_motor(core_diameter=self.UYARILI_CEKIRDEK_MM
                           ).calculate_performance)
        kodlar = [w.get('code') for w in (r.get('design_warnings') or [])]
        assert 'warn.solid.initial_mass_flux_high' in kodlar
        assert 'warn.solid.port_to_throat_low' in kodlar


# ===========================================================================
# P2B2-07 — star girdilerinin kırpması/varsayılanı BEYAN EDİLİR
# ===========================================================================
class TestP2B2_07StarBeyani:
    """a2'de (P2B1-06) onarıldı; a3 ölçtü ve bekçiyle bağladı.

    Ölçüm (once.json): star_radius = 30/45/60 mm girdilerinin üçü de
    28,000 mm'ye kırpılıyor ve clipped_inputs = ['star_radius'] ile
    beyan ediliyor; girdi yokken assumed_defaults = ['star_points',
    'star_radius'].
    """

    @pytest.mark.parametrize('sr', [30, 45, 60])
    def test_kirpma_beyan_ediliyor(self, sr):
        # V301/K-A: kırpma sınırı (28 mm) çekirdeğe bağlı; ölçümün kendi
        # geometrisi (çekirdek 30 mm, star portu geçerli) açıkça verilir.
        e = _motor(grain_type='star', core_diameter=30,
                   overrides={'star_radius': sr, 'star_points': 8})
        r = _sessiz(e.calculate_performance)
        gd = r['grain_design']
        assert 'star_radius' in (gd.get('clipped_inputs') or []), sr
        # kırpılan DEĞER de kullanılan değerdir (rapor ⟷ model tek kaynak)
        assert e._star_params()[1] * 1000.0 == pytest.approx(28.0, abs=1e-6)

    @pytest.mark.parametrize('sr', [15, 28])
    def test_kirpilmayan_girdide_beyan_yok(self, sr):
        gd = _sessiz(_motor(
            grain_type='star', core_diameter=30,
            overrides={'star_radius': sr,
                       'star_points': 8}).calculate_performance)['grain_design']
        assert 'star_radius' not in (gd.get('clipped_inputs') or []), sr

    def test_varsayilana_dusus_beyan_ediliyor(self):
        gd = _sessiz(_motor(
            grain_type='star').calculate_performance)['grain_design']
        varsayilan = gd.get('assumed_defaults') or []
        assert 'star_points' in varsayilan
        assert 'star_radius' in varsayilan

    def test_kardes_tiplerle_ayni_sozlesme(self):
        """Star, finocyl/slotted ile AYNI kanalları yayımlıyor."""
        anahtarlar = set()
        for gt, ov in (('star', {'star_radius': 45}),
                       ('finocyl', {'fin_length': 90}),
                       ('slotted', {'slot_depth': 90})):
            gd = _sessiz(_motor(grain_type=gt,
                                overrides=ov).calculate_performance)[
                                    'grain_design']
            assert gd.get('clipped_inputs') is not None, gt
            assert gd.get('assumed_defaults') is not None, gt
            anahtarlar.add(gt)
        assert anahtarlar == {'star', 'finocyl', 'slotted'}


# ===========================================================================
# P2B2-10 — bulk_mode künyesi GERÇEĞİ söylüyor
# ===========================================================================
class TestP2B2_10BulkModeKunyesi:
    """Kapı üstel değil YAKINSAMA kapısıdır; künye bunu söyler.

    Ölçüm (once.json): a = 0,0005 & n = 1,30 -> 64 anahtarlı TAM sonuç,
    ortalama itki 23524,77 N; a = 0,0005 & n ∈ {1,00; 1,05} -> fail-closed;
    a = 0,005 & n ∈ {1,05; 1,30} -> yayımlanıyor (43394,82 N).
    """

    #: V301/K-A: eski çapa A_p/A_t = 0,947'lik boğulan portlu varsayılan motoru kilitliyordu; a = 0,005 /
    #: n > 1 ile Ø100/500 tanede port boğaza HİÇ yetişmiyor (A_p/A_t 0,19-0,86).
    #: Aynı üç davranışın (yayımlanan n > 1, fail-closed n >= 1 yakınsamaz,
    #: n = 0,35) ölçüldüğü geçerli portlu kısa tane: L 150, çekirdek 70 mm.
    GEOMETRI = {'grain_length': 150, 'core_diameter': 70}

    @classmethod
    def _kapi(cls, a, n):
        r = _sessiz(_motor(burn_rate_a=a, burn_rate_n=n,
                           **cls.GEOMETRI).calculate_performance)
        return r, (r.get('combustion_stability') or {}).get('bulk_mode') or {}

    @pytest.mark.parametrize('a,n', [(0.0005, 1.30), (0.005, 1.05),
                                     (0.005, 1.30)])
    def test_n_bir_ustunde_yayimlanan_kosu_var(self, a, n):
        r, bulk = self._kapi(a, n)
        assert not r.get('error'), f'a={a} n={n}'
        assert len(r) > 50
        assert bulk['verdict'] == 'unstable'

    @pytest.mark.parametrize('a,n', [(0.0005, 1.30), (0.005, 1.05),
                                     (0.005, 1.30)])
    def test_kunye_asla_yayimlanmaz_demiyor(self, a, n):
        _r, bulk = self._kapi(a, n)
        k = bulk['solver_gate_consistency']['basis']
        assert 'already fails closed for n >= 1' not in k
        assert 'never gets published' not in k
        assert 'CONVERGENCE gate, not an exponent gate' in k

    @pytest.mark.parametrize('a,n', [(0.0005, 1.30), (0.005, 1.30),
                                     (0.0022334, 0.35)])
    def test_kunyenin_iddiasi_ayni_sozlukten_dogrulanabilir(self, a, n):
        _r, bulk = self._kapi(a, n)
        sgc = bulk['solver_gate_consistency']
        assert sgc['burn_rate_exponent'] == pytest.approx(n)
        assert sgc['published_with_criterion_met'] is (n >= 1.0)
        assert sgc['consistent'] is True

    def test_fail_closed_bandi_hala_kapali(self):
        """Yakınsamayan koşu yayımlanmamaya devam ediyor (ÖK-22 tersi)."""
        for a, n in ((0.0005, 1.05), (0.0005, 1.00)):
            r = _sessiz(_motor(burn_rate_a=a, burn_rate_n=n,
                               **self.GEOMETRI).calculate_performance)
            assert r.get('error'), f'a={a} n={n} yayımlanmamalıydı'
            assert 'combustion_stability' not in r


# ===========================================================================
# P2B2-11 — ISA yardımcıları GEOPOTANSİYEL irtifayla çağrılır
# ===========================================================================
class TestP2B2_11IsaIrtifasi:
    """Tablo tepesinde sıçrama yok; mutlak sapma kapandı.

    Ölçüm (once.json): 84850 -> 84853 m arasında ΔP = -%18,419 ve
    ΔT = -2,2393 K; yayımlanan/doğru oranı 90 km 0,7948 · 100 km 0,7535 ·
    120 km 0,6661.
    """

    @staticmethod
    def _satirlar(irtifalar):
        return {int(d['altitude']): d
                for d in _sessiz(_motor().calculate_altitude_performance,
                                 irtifalar)}

    #: İki dalın GERÇEK ayrım noktası: H = ISA_TABLE_TOP_M'ye karşılık gelen
    #: geometrik irtifa (85999,95 m). Kusurlu kodda karşılaştırma geometrik
    #: ``alt`` ile yapıldığı için ayrım 84852 m'ye kaymıştı ve tam orada
    #: ÖLÇÜLEN sıçrama vardı (84850 -> 84853 m arası ΔP = -%18,419,
    #: ΔT = -2,2393 K).
    GECIS_M = 85999.95290624202

    def test_eski_ayrim_noktasinda_sicrama_kalmadi(self):
        """84850 -> 84853 m: ÖLÇÜLEN -%18,419 / -2,2393 K sıçrama kapandı."""
        s = self._satirlar([84850, 84853])
        p1, p2 = s[84850]['pressure'], s[84853]['pressure']
        t1, t2 = s[84850]['temperature'], s[84853]['temperature']
        dp = 100.0 * (p2 - p1) / p1
        # 3 metrelik FİZİKSEL düşüş bu irtifada ~%0,053'tür; kusurlu kodda
        # okunan %18,419 idi. Bant fiziksel düşüşün iki katı.
        assert abs(dp) < 0.11, f'3 metrede %{dp:.3f} basınç sıçraması'
        assert abs(t2 - t1) < 0.01, f'3 metrede {t2 - t1:.4f} K sıçrama'
        assert s[84850]['atmosphere_basis'] == s[84853]['atmosphere_basis'], (
            'iki satır hâlâ FARKLI ISA dalından geliyor')

    def test_gercek_gecis_noktasinda_iki_dal_ayni_seyi_veriyor(self):
        """Dal değişimi ek bir süreksizlik EKLEMİYOR (tek tanım, tek H)."""
        alt_alt, alt_ust = self.GECIS_M - 1.0, self.GECIS_M + 1.0
        s = self._satirlar([alt_alt, alt_ust])
        d_alt, d_ust = s[int(alt_alt)], s[int(alt_ust)]
        assert 'isothermal extension' not in d_alt['atmosphere_basis']
        assert 'isothermal extension' in d_ust['atmosphere_basis']
        # iki dal da AYNI analitik fonksiyonla (aynı H ile) örtüşüyor
        for d, a in ((d_alt, alt_alt), (d_ust, alt_ust)):
            H = _geopotansiyel(a)
            assert d['pressure'] == pytest.approx(isa_pressure(H) / 1e5,
                                                  rel=1e-9)
            assert d['temperature'] == pytest.approx(isa_temperature(H),
                                                     rel=1e-9)
        # geçişteki düşüş, hemen ALTINDAKİ aynı genişlikli düşüşle uyumlu
        ref = self._satirlar([alt_alt - 2.0, alt_alt])
        d_gecis = abs(d_ust['pressure'] / d_alt['pressure'] - 1.0)
        d_ref = abs(ref[int(alt_alt)]['pressure']
                    / ref[int(alt_alt - 2.0)]['pressure'] - 1.0)
        assert d_gecis == pytest.approx(d_ref, rel=0.05), (
            f'geçişte fazladan sıçrama: {d_gecis:.3e} ⟷ {d_ref:.3e}')

    @pytest.mark.parametrize('alt', [90000, 100000, 120000])
    def test_tablo_ustu_geopotansiyel_dogruyu_veriyor(self, alt):
        d = self._satirlar([alt])[alt]
        H = _geopotansiyel(alt)
        assert d['pressure'] == pytest.approx(isa_pressure(H) / 1e5,
                                              rel=1e-12)
        assert d['temperature'] == pytest.approx(isa_temperature(H),
                                                 rel=1e-12)
        # GEOMETRİK irtifayla çağrı ölçülebilir biçimde AYRI bir sayıdır
        assert d['pressure'] != pytest.approx(isa_pressure(alt) / 1e5,
                                              rel=1e-6)

    @pytest.mark.parametrize('alt', [0, 10000, 50000, 84000])
    def test_tablo_ici_satirlar_bozulmadi(self, alt):
        d = self._satirlar([alt])[alt]
        H = _geopotansiyel(alt)
        assert d['pressure'] == pytest.approx(isa_pressure(H) / 1e5,
                                              rel=1e-9)

    def test_sinir_karsilastirmasi_geopotansiyel_uzerinden(self):
        """ISA_TABLE_TOP_M geopotansiyel bir sınırdır; dal onu H ile seçer.

        85000 m GEOMETRİK olarak tablo tepesinin üstündedir ama
        GEOPOTANSİYEL olarak (83920 m) altındadır. Kusurlu kod bu satırı
        izotermal uzantı dalına düşürüyordu; doğrusu tablo dalıdır.
        """
        alt = 85000
        assert alt > ISA_TABLE_TOP_M
        assert _geopotansiyel(alt) < ISA_TABLE_TOP_M
        d = self._satirlar([alt])[alt]
        assert 'isothermal extension' not in d['atmosphere_basis']
        assert d['pressure'] == pytest.approx(
            isa_pressure(_geopotansiyel(alt)) / 1e5, rel=1e-9)
        # izotermal uzantı bu satırda FARKLI bir sayı verirdi (eski davranış)
        assert d['temperature'] > isa_temperature(ISA_TABLE_TOP_M) + 1.0
