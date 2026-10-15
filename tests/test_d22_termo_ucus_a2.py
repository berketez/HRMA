"""ÖH D22 — kulvar ``termo-ucus``, aşama 2/2 bekçileri.

Tek konu: **OH-D18-05 + OH-Z5-02** — paraşüt (kurtarma sistemi) girdisi
verilmediğinde iniş hükmünün yayımlanması.

KUSUR (ölçüldü, ``docs/scofield/raw/OH/D22/termo-ucus/a2/once.json``):
``launch_params['parachute_area']`` gönderilmediğinde çözücü
``DEFAULT_PARACHUTE_AREA_M2 = 2,0 m²`` uyduruyor, o kanopiyle iniş fazını
entegre ediyor ve **14 sayı** yayımlıyordu — iniş hızı, iniş anı, iniş
noktası, toplam uçuş süresi, menzil, iniş süresi, ortalama iniş hızı…
Bir ``parachute_area_assumed`` bayrağı ve bir uyarı bunu dürüstçe
söylüyordu, ama beyan çözüm değildir: sayı kazanılmamıştı.

KANIT: kullanıcının BÜTÜN girdileri sabit tutulup yalnız modül sabiti
1,0 → 2,0 → 4,0 m² yapıldığında yanıt ağacında **15 yaprak** oynuyordu.
Yani yayımlanan iniş hükmü kullanıcının hiçbir girdisinin değil, araçla
ilgisi olmayan bir modül sabitinin fonksiyonuydu. Onarımdan sonra aynı
sarsım **0 yaprak** oynatıyor.

OH-Z5-02 bağı: o 15 yaprağın biri
``trajectory.warnings[2].params.area``tı ve Katman B'nin
``test_no_fabricated_constant_outputs`` sayımında "sabit yaprak" olarak
duruyordu (alan verilince uyarının KENDİSİ kaybolduğu için hiçbir sarsımda
'değişti' sayılmıyordu). Ölçüldü: sabit yaprak sayımı **15 → 14**, düşen
tek yaprak ADIYLA o yapraktır.
"""

import json
import math

import numpy as np
import pytest
from tests.support.platform_capa import capa_rel

import hrma.analysis.trajectory_analysis as TA
from hrma.analysis.trajectory_analysis import (
    DEFAULT_PARACHUTE_AREA_M2, LANDING_WITHHELD_NO_PARACHUTE,
    TrajectoryAnalyzer, TrajectoryInputError)


MOTOR = {
    'thrust': 5000.0,
    'burn_time': 10.0,
    'propellant_mass_total': 12.0,
    'total_impulse': 50000.0,
    'specific_impulse': 220.0,
}


def _kos(parachute_area=None, **ek):
    ta = TrajectoryAnalyzer()
    ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15,
                              drag_coefficient=0.5, length=2.0)
    params = {'launch_angle': 85.0, 'launch_altitude': 0.0,
              'wind_speed': 0.0, 'wind_direction': 0.0}
    if parachute_area is not None:
        params['parachute_area'] = parachute_area
    params.update(ek)
    return ta.calculate_trajectory(dict(MOTOR), params)


#: İniş HÜKMÜNÜ taşıyan yapraklar — "araç şu hızla, şu anda, şu noktaya
#: indi" diye okunan sayılar. Paraşüt yoksa hiçbiri yayımlanmaz.
INIS_HUKMU = (
    ('performance', 'trajectory_metrics', 'landing_velocity'),
    ('performance', 'trajectory_metrics', 'total_flight_time'),
    ('performance', 'trajectory_metrics', 'range_distance'),
    ('performance', 'trajectory_metrics', 'parachute_area_m2'),
    ('performance', 'trajectory_metrics', 'parachute_cd'),
    ('performance', 'phase_breakdown', 'descent_time'),
    ('trajectory', 'phases', 'descent', 'landing_time'),
    ('trajectory', 'phases', 'descent', 'landing_velocity'),
    ('trajectory', 'phases', 'descent', 'landing_position_x'),
    ('trajectory', 'phases', 'descent', 'parachute_area_m2'),
    ('recovery', 'landing_velocity_m_s'),
    ('recovery', 'descent_duration_s'),
    ('recovery', 'mean_descent_rate_m_s'),
    ('recovery', 'descent_height_m'),
    ('recovery', 'parachute_area_m2'),
)


def _al(sonuc, yol):
    dugum = sonuc
    for parca in yol:
        dugum = dugum[parca]
    return dugum


class TestOHD1805InisHukmuFailClosed:
    """Paraşüt verilmediğinde iniş hükmü YAYIMLANMAZ."""

    def test_paracutsuz_kosumda_tek_bir_inis_sayisi_bile_yayimlanmaz(self):
        r = _kos()
        yayimlanan = [yol for yol in INIS_HUKMU
                      if _al(r, yol) is not None]
        assert yayimlanan == [], (
            'paraşüt verilmediği hâlde iniş hükmü yayımlandı: %s'
            % (yayimlanan,))

    def test_ucus_hukmu_inisi_bilinmiyor_ilan_eder(self):
        r = _kos()
        fs = r['flight_status']
        assert fs['landing_unknown'] is True
        assert fs['landed'] is False
        assert fs['phase_end_reasons']['descent'] == 'not_modelled'
        # Çözücü BAŞARISIZ olmadı, hiç ÇAĞRILMADI: eksik girdi bir çözücü
        # hatası değildir, uçuş hükmü geçerli kalır ve 'solver_no_event'
        # hata uyarısı basılmaz.
        assert fs['valid'] is True
        assert fs['landing_withheld_because'] == LANDING_WITHHELD_NO_PARACHUTE
        kodlar = {w['code'] for w in r.get('warnings', [])}
        assert 'warn.trajectory.solver_no_event' not in kodlar

    def test_gerekce_alan_adiyla_ve_tek_kaynaktan_gelir(self):
        r = _kos()
        rec = r['recovery']
        assert rec['deployed'] is False
        assert rec['descent_model'] == 'NOT_MODELLED'
        assert rec['reason'] == 'recovery_not_supplied'
        # Gerekçe EKSİK ALANI ADIYLA söyler (sayı uydurmadan).
        assert 'parachute_area' in rec['landing_withheld_because']
        assert rec['basis'] == rec['landing_withheld_because']
        # TEK KAYNAK: faz sözlüğü ile üst düzey özet aynı metni taşır.
        assert (r['trajectory']['phases']['descent']
                ['landing_withheld_because']) == LANDING_WITHHELD_NO_PARACHUTE

    def test_uydurma_alani_anlatan_uyari_artik_uretilmez(self):
        """Beyan doğruyu söylemek zorundadır; anlattığı şey kalkınca gider.

        ``warn.trajectory.parachute_area_assumed`` metni "paraşüt alanı
        {area} m² ve Cd {cd} birer varsayımdır… iniş hızı doğrudan
        bunlarla ölçeklenir" diyordu. Alan artık hiç kullanılmadığı için
        bu cümle YANLIŞ olurdu.
        """
        kodlar = {w['code'] for w in _kos().get('warnings', [])}
        assert 'warn.trajectory.parachute_area_assumed' not in kodlar

    def test_sozlesme_sekli_iki_dalda_da_ayni(self):
        """Hüküm geri çekilince ALAN KAYBOLMAZ, değeri None olur.

        Aksi hâlde ``rec['landing_velocity_m_s']`` okuyan tüketici
        KeyError alır ve "sayı yok" ile "alan yok" birbirine karışır.
        """
        yok = _kos()['recovery']
        var = _kos(parachute_area=9.0)['recovery']
        # Sayısal/veri anahtarlarının TAMAMI iki dalda da bulunmalı. Yalnız
        # var olmayan bir SAYIYI anlatan künye metni (``mean_descent_rate_
        # basis``) düşer — anlatacağı sayı yokken cümle kurmak beyanı
        # yalancı yapardı.
        kunye = {'mean_descent_rate_basis'}
        eksik = sorted((set(var) - set(yok)) - kunye)
        assert eksik == [], 'geri çekilen dalda eksik anahtar: %s' % (eksik,)
        for anahtar in ('landing_velocity_m_s', 'descent_duration_s',
                        'mean_descent_rate_m_s', 'parachute_area_m2'):
            assert anahtar in yok and yok[anahtar] is None, anahtar

    def test_gecersiz_alan_sessizce_varsayima_dusmez(self):
        """Negatif/sıfır alan varsayıma DÜŞMEZ, hüküm geri çekilir."""
        for kotu in (-1.0, 0.0):
            r = _kos(parachute_area=kotu)
            tm = r['performance']['trajectory_metrics']
            assert tm['parachute_area_m2'] is None, kotu
            assert tm['landing_velocity'] is None, kotu
            assert r['recovery']['descent_model'] == 'NOT_MODELLED', kotu

    def test_sonlu_olmayan_alan_daha_ust_kapida_reddedilir(self):
        """NaN/sonsuz alan ``_guard_solver_inputs`` kapısında düşer.

        Bu da fail-closed'dır ve daha erkendir: sayı hiç çözücüye girmez.
        Bekçi iki kapının BİRLİKTE durduğunu kilitler — üsttekinin
        kaldırılması alttakini sessizce ``None`` yoluna sokardı.
        """
        for kotu in (float('nan'), float('inf')):
            with pytest.raises(TrajectoryInputError) as hata:
                _kos(parachute_area=kotu)
            assert 'parachute_area' in str(hata.value), kotu

    def test_cozucu_kendi_on_kosulunu_korur(self):
        """Kapı iki yerdedir: ileride eklenecek ikinci bir çağıran da
        uydurmayı sessizce geri getiremesin."""
        ta = TrajectoryAnalyzer()
        ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15)
        with pytest.raises(TrajectoryInputError) as hata:
            ta._calculate_descent_flight([0.0, 1000.0, 10.0, 0.0, 20.0],
                                         0.0177, (0.0, 0.0))
        assert hata.value.problems[0]['field'] == \
            'launch_params.parachute_area'


class TestOHD1805ModulSabitiArtikSonucaGirmiyor:
    """ASIL ÖLÇÜM: yayımlanan hiçbir sayı modül sabitine bağlı değil."""

    @staticmethod
    def _yapraklar(nesne, onek=''):
        cikti = {}
        if isinstance(nesne, dict):
            for k, v in nesne.items():
                cikti.update(TestOHD1805ModulSabitiArtikSonucaGirmiyor
                             ._yapraklar(v, '%s.%s' % (onek, k)))
        elif isinstance(nesne, (list, tuple)):
            for i, v in enumerate(nesne):
                cikti.update(TestOHD1805ModulSabitiArtikSonucaGirmiyor
                             ._yapraklar(v, '%s[%d]' % (onek, i)))
        elif isinstance(nesne, np.ndarray):
            pass
        elif isinstance(nesne, (int, float)) and not isinstance(nesne, bool):
            cikti[onek] = float(nesne)
        return cikti

    def test_varsayilan_alan_sarsimi_hicbir_yapragi_oynatmaz(self, monkeypatch):
        """Kullanıcı girdisi SABİT; yalnız modül sabiti oynuyor.

        ÖLÇÜLDÜ (once.json B): onarımdan önce 15 yaprak oynuyordu —
        ``.performance.trajectory_metrics.landing_velocity``,
        ``.total_flight_time``, ``.range_distance``,
        ``.recovery.mean_descent_rate_m_s``,
        ``.trajectory.warnings[2].params.area`` dâhil. Şimdi 0.
        """
        goruntuler = []
        for alan in (1.0, 2.0, 4.0):
            monkeypatch.setattr(TA, 'DEFAULT_PARACHUTE_AREA_M2', alan)
            goruntuler.append(self._yapraklar(_kos()))
        ortak = set(goruntuler[0]) & set(goruntuler[1]) & set(goruntuler[2])
        oynayan = sorted(y for y in ortak
                         if not (goruntuler[0][y] == goruntuler[1][y]
                                 == goruntuler[2][y]))
        assert oynayan == [], (
            'yayımlanan yapraklar hâlâ modül sabitine bağlı: %s' % (oynayan,))

    def test_ohz502_uydurma_alan_yapragi_kalmadi(self):
        """OH-Z5-02: hiçbir uyarı uydurma bir ``params.area`` taşımaz.

        Katman B sayımında bu yaprak "sabit çıktı" olarak duruyordu ve
        imlenmemişti (alan verilince uyarının kendisi kaybolduğu için
        hiçbir sarsımda 'değişti' sayılmıyordu). Sayım 15 → 14; düşen tek
        yaprak budur.
        """
        for kosum in (_kos(), _kos(parachute_area=9.0)):
            for w in kosum.get('warnings', []):
                params = w.get('params') or {}
                assert 'area' not in params, (w['code'], params)


class TestOHD1805MesruYolBozulmadi:
    """Paraşüt VERİLEN yol bit-aynı kalır — onarım kanalı kapatmaz."""

    def test_verilen_alanla_inis_hukmu_yayimlanir(self):
        r = _kos(parachute_area=9.0)
        eksik = [yol for yol in INIS_HUKMU if _al(r, yol) is None]
        assert eksik == [], eksik
        assert r['flight_status']['landing_unknown'] is False
        assert r['recovery']['descent_model'] == 'parachute'
        assert r['recovery']['assumed']['area'] is False

    #: ÖH D22 çapası — OH-D18-05 onarımı yayımlandığında ölçülen iniş hızı
    #: [m/s]. O gün ``_atm_full`` deniz seviyesi ALTINDAKİ her irtifayı 0 m'ye
    #: yapıştırıyordu.
    D22_CAPASI = 10.697066699014087

    #: ÖH D25 fix-23 çapası — AYNI kurulum, AYNI paraşüt alanı, YENİ atmosfer
    #: tabanı. Kayma ÖLÇÜLDÜ: 8,87e-09 bağıl (dokuzuncu basamak).
    D25_CAPASI = 10.697066604180101

    def test_eski_sayi_alan_acikca_istenince_bit_ayni_uretilir(self,
                                                               monkeypatch):
        """Regresyon kilidi: 2,0 m² İSTENİRSE iniş hızı çapadan sapmaz.

        Onarım (OH-D18-05) sayıyı değiştirmedi, sessizce üretilmesini
        durdurdu.

        ÖH D25 fix-23 — TÜRETİMLİ YENİDEN ÇAPALAMA (gerekçe ölçüldü).
        Çapa ``10.697066699014087`` idi; D24 birleşince ``10.697066604180101``
        okundu. KAYNAK ADIYLA: ÖH D24 termo-ucus a2 (``fecab6f`` ürün,
        ``d386a4a`` kapanış) OH-D23-07'yi onardı — ``_atm_full`` artık 0 m
        altını deniz seviyesine KIRPMIYOR, ISA tablosunun kendi tabanına
        (``ISA_TABLE_BOTTOM_M`` = −5000 m) kırpıyor. İniş fazında
        ``solve_ivp`` yerin biraz altında türev denediği için o deneme
        adımları artık gerçek (daha yoğun) havayı görüyor; iniş olayının
        kökü dokuzuncu basamakta kayıyor.

        Bu bir ürün gerilemesi DEĞİL fizik kaymasıdır ve iddia bunu VARSAYMAZ,
        ÖLÇER: aşağıdaki ikinci koşum eski kırpmayı geri koyar
        (``ISA_TABLE_BOTTOM_M = 0.0``, ``_atm_full``in okuduğu tek yer) ve
        D22 çapasını BİT-AYNI üretmesini şart koşar. Yani sayı ancak
        atmosfer tabanı değişirse oynayabilir; paraşüt yolunda gerçek bir
        gerileme olsaydı eski-kırpma koşumu da çapadan sapardı ve bu test
        yine kırmızı verirdi. İddia eski hâlinden GÜÇLÜDÜR: tek sayı yerine
        bir sayı ÇİFTİ ve aralarındaki farkın kaynağı kilitleniyor.
        """
        v = _kos(parachute_area=DEFAULT_PARACHUTE_AREA_M2)[
            'performance']['trajectory_metrics']['landing_velocity']
        # v3.0.0 (15 Eki) — çapa darwin/arm64'te ölçüldü; CI linux/x86_64'te
        # AYNI kod 1,3e-7 (ODE, uyarlamalı adım) bağıl sapma verdi (koşum 38770162288). Tolerans
        # referans platformda aynen; başkasında 1e-6 (tests/support/platform_capa.py).
        assert v == pytest.approx(self.D25_CAPASI, rel=capa_rel(1e-9, 1e-6))

        # Kaymanın KAYNAĞI: OH-D23-07 öncesi kırpma geri konunca D22 çapası
        # birebir geri gelmeli (bit-aynı: rel=0).
        monkeypatch.setattr(TA, 'ISA_TABLE_BOTTOM_M', 0.0)
        eski = _kos(parachute_area=DEFAULT_PARACHUTE_AREA_M2)[
            'performance']['trajectory_metrics']['landing_velocity']
        assert eski == self.D22_CAPASI, (
            'eski 0 m kırpmasıyla D22 çapası geri gelmedi (%r != %r) — kayma '
            'OH-D23-07 atmosfer tabanından DEĞİL, paraşüt yolundaki gerçek '
            'bir gerilemeden geliyor' % (eski, self.D22_CAPASI))
        # Kayma yalnız dokuzuncu basamakta: fizik kayması, model değişimi
        # değil. (Ölçülen: 8,87e-09)
        assert abs(v - eski) / eski < 1e-7, (
            'atmosfer tabanı değişiminin iniş hızına etkisi ölçülenden '
            'BÜYÜK: %r' % (abs(v - eski) / eski,))

    def test_kullanicinin_alani_sonucu_gercekten_degistirir(self):
        kucuk = _kos(parachute_area=4.0)['recovery']['landing_velocity_m_s']
        buyuk = _kos(parachute_area=9.0)['recovery']['landing_velocity_m_s']
        assert kucuk > buyuk > 0
        assert (kucuk - buyuk) / buyuk > 0.1


class TestOHD1805GrafikOlmayanInisiIsaretlemez:
    """Uydurma veri grafikte de uydurmadır."""

    def test_parasutsuz_kosumda_inis_isaretcisi_cizilmez(self):
        ta = TrajectoryAnalyzer()
        ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15,
                                  drag_coefficient=0.5, length=2.0)
        r = ta.calculate_trajectory(dict(MOTOR),
                                    {'launch_angle': 85.0,
                                     'launch_altitude': 0.0,
                                     'wind_speed': 0.0,
                                     'wind_direction': 0.0})
        figur = json.loads(ta.create_trajectory_plots(r))
        izler = {t.get('name'): t for t in figur['data'] if t.get('name')}
        assert 'Parachute deploy' not in izler, sorted(izler)
        etiketler = izler['Flight Phases']['text']
        assert 'Landing' not in etiketler, etiketler
        assert 'Landing under parachute' not in etiketler, etiketler
        # İniş fazı hiç koşmadığı için seri apojede biter; dördüncü nokta
        # apojenin kopyası olarak çizilmez.
        assert etiketler[-1] == 'Apogee', etiketler

    def test_parasut_verilince_isaretci_geri_gelir(self):
        ta = TrajectoryAnalyzer()
        ta.set_vehicle_parameters(mass_dry=20.0, diameter=0.15,
                                  drag_coefficient=0.5, length=2.0)
        r = ta.calculate_trajectory(dict(MOTOR),
                                    {'launch_angle': 85.0,
                                     'launch_altitude': 0.0,
                                     'wind_speed': 0.0, 'wind_direction': 0.0,
                                     'parachute_area': 2.0})
        figur = json.loads(ta.create_trajectory_plots(r))
        izler = {t.get('name'): t for t in figur['data'] if t.get('name')}
        assert 'Parachute deploy' in izler, sorted(izler)
        assert izler['Flight Phases']['text'][-1] == 'Landing under parachute'
