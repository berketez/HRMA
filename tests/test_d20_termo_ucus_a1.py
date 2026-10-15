# -*- coding: utf-8 -*-
"""ÖH Dalga-20 / termo-ucus a1 — bekçiler.

Her sınıf bir defter kalemine bağlıdır; her iddia
``docs/scofield/raw/OH/D20/termo-ucus/a1/`` altındaki ölçüm dosyasından
gelen SAYIYI kilitler. Ters-mutasyon kanıtları ``mutasyon.json``dadır.
"""
import contextlib
import io
import json
import os
import re

import numpy as np
# ÖH D26 / OH-D25-14: ``np.trapz`` NumPy 2.0'da ad alanından
# KALDIRILDI (np.trapezoid); ad TEK YERDE çözülür.
from hrma.utils.numeric_compat import trapezoid as _trapezoid
import pytest

from hrma.analysis.heat_transfer_analysis import (
    DEFAULT_X_CO2, DEFAULT_X_H2O, RADIATION_COMPOSITION_SOURCE_CALLER,
    RADIATION_COMPOSITION_SOURCE_DEFAULT)
from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
from tests.support.kanit import kanit_gerekli

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(client, yol, yuk):
    r = _sessiz(client.post, yol, json=yuk)
    return r.status_code, r.get_json()


# ============================================================== OH-D19-07
#: Işıma kompozisyonu ölçümü — modül varsayılanından UZAK bir çift.
_X_CAGIRAN = {'x_H2O': 0.45, 'x_CO2': 0.05}

#: ``once_ohd19_07.json`` U1/U4 ile aynı motor.
_MOTOR_ISI = {
    'chamber_pressure': 40.0, 'chamber_temperature': 3200.0,
    'chamber_diameter': 0.1, 'chamber_length': 0.4,
    'burn_time': 10.0, 'mdot_total': 1.0,
    'throat_diameter': 0.02, 'expansion_ratio': 8.0,
}

#: ÖLÇÜLDÜ (``sonra_ohd19_07.json`` U4, modül doğrudan çağrıldığında):
#: aynı motorda yalnız kompozisyon değişince hazne akısı bu iki değeri alır.
_Q_HAZNE_VARSAYILAN = 2442956.3570863595   # W/m², x = (0,25 / 0,15)
_Q_HAZNE_CAGIRAN = 2814769.015191563       # W/m², x = (0,45 / 0,05)


class TestOHD1907IsimaKompozisyonuUctanGecer:
    """app.py'nin üç ısı ucu ``x_H2O``/``x_CO2``yi modüle GEÇİRİR.

    ÖLÇÜLDÜ (``once_ohd19_07.json``, taban 14acd1d): üç uçta da kesirleri
    gönderen istek ile göndermeyen istek BİT-AYNI gövde döndürüyordu
    (``sha_esit: true``) — çünkü uçlar kendi ``motor_data``larını sabit bir
    anahtar listesiyle kuruyor ve bu iki anahtar listede yoktu.
    ``/analyze_thermal_safety`` üstelik kullanıcıya "no x_H2O/x_CO2 was
    supplied with the motor data" diyordu: kullanıcı kesirleri gönderdiği
    hâlde. Modül doğrudan çağrıldığında (U4) aynı değişiklik hazne akısını
    2 442 956 -> 2 814 769 W/m² (+%15,2) kaydırıyordu, yani düşürülen girdi
    ETKİSİZ değil GÖRÜNMEZDİ.
    """

    def test_ileri_analiz_kesirleri_gecirir(self, client):
        temiz = dict(_MOTOR_ISI)
        zengin = dict(_MOTOR_ISI, **_X_CAGIRAN)
        _, j1 = _post(client, '/api/advanced-analysis', {
            'motor_data': temiz, 'analysis_types': ['heat_transfer'],
            'wall_thickness': 0.005})
        _, j2 = _post(client, '/api/advanced-analysis', {
            'motor_data': zengin, 'analysis_types': ['heat_transfer'],
            'wall_thickness': 0.005})
        g1 = j1['results']['heat_analysis']['gas_side_analysis']
        g2 = j2['results']['heat_analysis']['gas_side_analysis']
        # Kesirler gerçekten modüle gitti
        assert g2['radiation_x_H2O'] == pytest.approx(_X_CAGIRAN['x_H2O'])
        assert g2['radiation_x_CO2'] == pytest.approx(_X_CAGIRAN['x_CO2'])
        assert g2['radiation_composition_source'] == \
            RADIATION_COMPOSITION_SOURCE_CALLER
        # Sağlıklı yol (kesirsiz) BİT-AYNI kaldı — regresyon kilidi
        assert g1['radiation_x_H2O'] == pytest.approx(DEFAULT_X_H2O)
        assert g1['radiation_x_CO2'] == pytest.approx(DEFAULT_X_CO2)
        assert g1['radiation_composition_source'] == \
            RADIATION_COMPOSITION_SOURCE_DEFAULT
        # ...ve SAYI kaydı: kompozisyon hükmü değiştirdi
        assert g1['chamber_heat_flux'] == pytest.approx(_Q_HAZNE_VARSAYILAN,
                                                        rel=1e-9)
        assert g2['chamber_heat_flux'] == pytest.approx(_Q_HAZNE_CAGIRAN,
                                                        rel=1e-9)

    def test_termal_guvenlik_kokeni_dogru_soyler(self, client):
        taban = dict(_MOTOR_ISI, wall_thickness=0.005, material='steel',
                     cooling_type='natural')
        _, j1 = _post(client, '/analyze_thermal_safety', dict(taban))
        _, j2 = _post(client, '/analyze_thermal_safety',
                      dict(taban, **_X_CAGIRAN))
        g1 = j1['thermal_analysis']['gas_side_analysis']
        g2 = j2['thermal_analysis']['gas_side_analysis']
        assert g1['radiation_composition_source'] == \
            RADIATION_COMPOSITION_SOURCE_DEFAULT
        # Kullanıcı kesirleri VERDİYSE uç "vermedin" diyemez
        assert g2['radiation_composition_source'] == \
            RADIATION_COMPOSITION_SOURCE_CALLER
        assert g2['radiation_x_H2O'] == pytest.approx(_X_CAGIRAN['x_H2O'])
        assert g1['chamber_heat_flux'] == pytest.approx(_Q_HAZNE_VARSAYILAN,
                                                        rel=1e-9)
        assert g2['chamber_heat_flux'] == pytest.approx(_Q_HAZNE_CAGIRAN,
                                                        rel=1e-9)

    def test_duvar_profili_kesirleri_gecirir(self, client):
        taban = dict(_MOTOR_ISI, wall_thickness=0.005, material='steel')
        _, j1 = _post(client, '/api/analysis/wall-profile', dict(taban))
        _, j2 = _post(client, '/api/analysis/wall-profile',
                      dict(taban, **_X_CAGIRAN))
        q1 = [v for v in j1['wall_profile']['q_MW'] if v is not None]
        q2 = [v for v in j2['wall_profile']['q_MW'] if v is not None]
        assert q1 and q2
        # ÖLÇÜLDÜ (once/sonra_ohd19_07.json U3): tepe 28,520400 -> 28,548295
        assert max(q1) == pytest.approx(28.520399514787695, rel=1e-9)
        assert max(q2) == pytest.approx(28.548294634535793, rel=1e-9)
        # Köken alanı profile KONMAZ — D17 hükmü (ters-yön borcu büyümesin);
        # tests/test_d17_termo_ucus_a1.py aynı iddiayı modül tarafında tutar.
        assert 'radiation_composition_source' not in j1['wall_profile']

    def test_x_CO2_sifiri_dusurulmez(self, client):
        """``x_CO2 = 0`` FİZİKSEL bir girdidir, "verilmedi" değildir.

        ``/api/analysis/wall-profile`` isteğe bağlı sayıları
        ``optional_numeric`` döngüsüyle okur ve o döngü ``0``/``'0'``
        değerini "kullanma" sayar. Işıyan tür kesirleri o listeye konsaydı
        CO2 üretmeyen bir sistemin ``x_CO2 = 0`` girdisi sessizce düşer,
        modül 0,15'e çıkardı. ÖLÇÜLDÜ (aynı motor, q_MW tepe): kesirsiz
        28,520400 | x = (0,60 / 0,00) 28,560793 | x_CO2 düşürülmüş hâl
        (0,60 / 0,15) 28,607742 MW/m² — üç ayrı sayı.
        """
        taban = dict(_MOTOR_ISI, wall_thickness=0.005, material='steel')

        def _tepe(ek):
            _, j = _post(client, '/api/analysis/wall-profile',
                         dict(taban, **ek))
            return max(v for v in j['wall_profile']['q_MW'] if v is not None)

        assert _tepe({}) == pytest.approx(28.520399514787695, rel=1e-9)
        assert _tepe({'x_H2O': 0.60, 'x_CO2': 0.0}) == pytest.approx(
            28.56079323082785, rel=1e-9)
        # x_CO2 düşürülseydi bu sayı çıkardı — bekçinin ayırt ettiği hâl
        assert _tepe({'x_H2O': 0.60}) == pytest.approx(
            28.607741513103708, rel=1e-9)

    def test_termal_guvenlik_x_CO2_sifirini_kabul_eder(self, client):
        """Kardeş uçta da ``x_CO2 = 0`` çağıran girdisidir."""
        taban = dict(_MOTOR_ISI, wall_thickness=0.005, material='steel',
                     cooling_type='natural')
        _, j = _post(client, '/analyze_thermal_safety',
                     dict(taban, x_H2O=0.60, x_CO2=0.0))
        g = j['thermal_analysis']['gas_side_analysis']
        assert g['radiation_x_CO2'] == pytest.approx(0.0)
        assert g['radiation_x_H2O'] == pytest.approx(0.60)
        assert g['radiation_composition_source'] == \
            RADIATION_COMPOSITION_SOURCE_CALLER


# ============================================================== OH-D17-27
_EGRI = {'time': [0.0, 1.0, 2.0, 4.0, 8.0],
         'thrust': [12000.0, 12000.0, 4000.0, 2000.0, 1000.0]}
_EGRI_IMPULS = 32000.0        # N·s (trapez)
_EGRI_ORTALAMA = 4000.0       # N
_M_KURU, _M_YAKIT, _T_YANMA = 35.0, 15.0, 8.0


def _impuls_kadar(t_hedef):
    """∫_0^t F dt — bekçinin BAĞIMSIZ referansı (çözücüden okunmaz)."""
    t = np.asarray(_EGRI['time'], dtype=float)
    F = np.asarray(_EGRI['thrust'], dtype=float)
    if t_hedef <= t[0]:
        return 0.0
    t_kes = t[t < t_hedef]
    F_kes = F[:len(t_kes)]
    t_tam = np.append(t_kes, float(t_hedef))
    F_tam = np.append(F_kes, float(np.interp(t_hedef, t, F)))
    return float(_trapezoid(F_tam, t_tam))


class TestOHD1727KutleYorungesiEgriyeBagli:
    """ṁ(t) = m_p·F(t)/I doktrini kütle YÖRÜNGESİYLE kilitlenir.

    ÖLÇÜLDÜ (``once_ohd1727.json``, taban 14acd1d): eğri-orantılı ṁ ile
    sabit ṁ = m_p/t_b modelleri yanma SONUNDA aynı kütleye oturuyor
    (35,000 kg — mevcut bekçi ailesinin kilitlediği tek sayı), ama ARADA
    ayrışıyor: t = 2,004 s'de 40,6175 kg ⟷ 46,2425 kg, fark 5,625 kg
    (+%13,85). Yani "yakıt itkiyle orantılı harcanır" hükmü, sabit debiye
    dönen bir mutasyonda da yeşil kalıyordu (OH-D17-27). Bu bekçi kütleyi
    ARA ZAMANLARDA analitik ∫F dt referansına bağlar.
    """

    @staticmethod
    def _powered(egri_ile):
        c = TrajectoryAnalyzer()
        c.set_vehicle_parameters(mass_dry=_M_KURU, diameter=0.1128,
                                 drag_coefficient=0.5)
        c.set_thrust_curve(_EGRI)
        return _sessiz(
            c._calculate_powered_flight,
            _EGRI_ORTALAMA, _T_YANMA, _M_KURU + _M_YAKIT, _M_YAKIT,
            np.radians(85.0), 0.0, 0.01, (0.0, 0.0),
            thrust_curve=(c._thrust_curve if egri_ile else None))

    @pytest.mark.parametrize('t_ornek', [0.5, 1.0, 2.004, 4.0, 6.0])
    def test_kutle_t_analitik_impuls_kesrini_izler(self, t_ornek):
        pf = self._powered(True)
        t = np.asarray(pf['time'], dtype=float)
        m = np.asarray(pf['mass'], dtype=float)
        olculen = float(np.interp(t_ornek, t, m))
        beklenen = (_M_KURU + _M_YAKIT) - _M_YAKIT * (
            _impuls_kadar(t_ornek) / _EGRI_IMPULS)
        assert olculen == pytest.approx(beklenen, abs=2e-3), (
            f't = {t_ornek} s: kütle {olculen:.6f} kg, ṁ = m_p·F(t)/I '
            f'doktrini {beklenen:.6f} kg gerektiriyor')

    def test_sabit_debi_modeli_ayirt_edilir(self):
        """Aynı ara zamanda sabit-debi modeli ÖLÇÜLEBİLİR biçimde ayrışır.

        Bu iddia olmadan yukarıdaki bekçi "tolerans yeterince gevşek mi?"
        sorusuna cevap veremez: 5,625 kg'lık ayrışma 2e-3 kg'lık toleransın
        2800 katıdır.
        """
        t_ornek = 2.004
        m_egri = float(np.interp(
            t_ornek, np.asarray(self._powered(True)['time'], dtype=float),
            np.asarray(self._powered(True)['mass'], dtype=float)))
        pf_s = self._powered(False)
        m_sabit = float(np.interp(t_ornek,
                                  np.asarray(pf_s['time'], dtype=float),
                                  np.asarray(pf_s['mass'], dtype=float)))
        assert m_egri == pytest.approx(40.6175, abs=1e-3)
        assert m_sabit == pytest.approx(46.2425, abs=1e-3)
        assert abs(m_sabit - m_egri) > 5.0

    def test_yanma_sonu_kutlesi_iki_modelde_de_ayni(self):
        """Mevcut bekçinin kilitlediği eşitlik — neden yetmediğinin kanıtı."""
        assert self._powered(True)['final_state'][4] == pytest.approx(
            _M_KURU, abs=1e-3)
        assert self._powered(False)['final_state'][4] == pytest.approx(
            _M_KURU, abs=1e-3)


# ====================================================== ŞART (Fable-D17)
class TestFableD17SartlariHizali:
    """Fable-D17'nin iki ŞARTı: kod kendi hakkında doğru konuşur.

    Bunlar SAYISAL değil BEYAN kalemleridir (Fable: "kod/test değişikliği
    gerekmez"); bekçi yalnız beyanın ölçümle hizalı kaldığını kilitler ki
    aynı kayma sessizce geri gelmesin.
    """

    def test_p4b315_yorum_sayilari_olcumle_ayni(self):
        yol = os.path.join(_KOK, 'hrma', 'analysis', 'trajectory_analysis.py')
        with open(yol, encoding='utf-8') as f:
            kaynak = f.read()
        blok = kaynak.split('ORTALAMA İNİŞ HIZININ DATUMU')[1][:1200]
        # D17 once.json K7 (1500 m sahası) — beyan bu sayıları taşımalı
        assert '16,836785' in blok
        assert '13,117193' in blok
        assert '28,36' in blok
        # Fable'ın RET ettiği eski (ölçümde olmayan) sayılar geri gelmesin
        assert '17,2774' not in blok
        assert '15,1680' not in blok

    def test_p4b315_sayilar_gercekten_olcum_dosyasindan(self):
        yol = os.path.join(_KOK, 'docs', 'scofield', 'raw', 'OH', 'D17',
                           'termo-ucus', 'a1', 'once.json')
        with open(kanit_gerekli(yol), encoding='utf-8') as f:
            k7 = json.load(f)['K7_P4B3_15_inis']
        assert round(k7['1500.0']['mean_descent_rate_m_s'], 6) == 16.836785
        assert round(k7['1500.0']['el_hesabi_saha_datumu'], 6) == 13.117193
        assert round(k7['_bagil_sapma_yuzde'], 2) == 28.36

    def test_p15b409_yorumu_yapmadigi_isi_iddia_etmez(self):
        yol = os.path.join(_KOK, 'hrma', 'analysis', 'nozzle_flow_1d.py')
        with open(yol, encoding='utf-8') as f:
            kaynak = f.read()
        blok = kaynak.split('İKİ UÇ AYNI SORUYA TERS CEVAP VEREMEZ')[1][:2600]
        assert 'BİR iş yapılır' in blok
        assert 'İki iş yapılır' not in blok
        # Kaldırılan madde TARİHÇE olarak duruyor, iş listesi olarak değil
        assert 'GERİ ALINDI' in blok
        # İş listesinde ikinci bir numaralı madde kalmadı
        is_listesi = blok.split('TARİHÇE')[0]
        assert not re.search(r'^\s*#\s+\(2\)', is_listesi, re.M)


# ============================================================== P4B4-18
class TestP4B418ChugTekSayisalTanim:
    """Chug tasarım kuralının 0,20'si İKİ yerde yazılamaz.

    ÖLÇÜLDÜ (``once_p4b418.json`` A, taban 14acd1d): mevcut tek-kaynak
    bekçisi yalnız ADINDA CHUG+(DP|RATIO) geçen sabitleri arıyordu, bu
    yüzden ``cycle_power_balance.INJECTOR_DP_FRAC_LIQUID_DEFAULT = 0.20``
    (yorumu "chug kararlılığı için 0.15-0.20" diyor) taramaya HİÇ
    girmiyordu ve künye kullanıcıya "bu çift HRMA'daki TEK sayısal
    tanımdır" demeye devam ediyordu. Bu bekçi ADA değil KİMLİĞE bakar.
    """

    def test_cevrim_varsayilani_tanim_noktasindan_gelir(self):
        from hrma.analysis.acoustic_modes import CHUG_DP_RATIO_RECOMMENDED
        from hrma.engines import cycle_power_balance as cpb
        assert cpb.INJECTOR_DP_FRAC_LIQUID_DEFAULT is \
            CHUG_DP_RATIO_RECOMMENDED, (
                'sıvı enjektör ΔP varsayılanı chug kuralının TANIM '
                'noktasından okunmalı, kendi literali olmamalı')

    def test_cevrim_dosyasinda_chug_literali_kalmadi(self):
        """AST: dosyada 0,20 literali chug bağlamında yeniden yazılmasın."""
        import ast as _ast
        yol = os.path.join(_KOK, 'hrma', 'engines', 'cycle_power_balance.py')
        with open(yol, encoding='utf-8') as f:
            kaynak = f.read()
        agac = _ast.parse(kaynak)
        satirlar = kaynak.splitlines()
        baglam = re.compile(r'chug', re.I)
        suclu = []
        for d in _ast.walk(agac):
            if not isinstance(d, _ast.Constant):
                continue
            if not isinstance(d.value, float) or d.value != 0.20:
                continue
            n = d.lineno
            if baglam.search('\n'.join(satirlar[max(0, n - 4):n + 2])):
                suclu.append((n, satirlar[n - 1].strip()))
        assert suclu == [], f'chug bağlamında 0,20 literali: {suclu}'

    def test_geri_cekilen_sp8089_atfi_dayanak_yapilmaz(self):
        """SP-8089 bandın DAYANAĞI olmaktan geri çekildi; kopyası kalmasın.

        ``acoustic_modes.CHUG_THRESHOLD_SOURCE`` atfı açıkça geri çekiyor;
        çevrim dosyası aynı atfı dayanak gibi kullanıyordu.
        """
        yol = os.path.join(_KOK, 'hrma', 'engines', 'cycle_power_balance.py')
        with open(yol, encoding='utf-8') as f:
            metin = f.read()
        blok = metin.split('Enjektör ΔP oranları')[1][:2200]
        assert 'SP-8089 alt bandı' not in blok
        assert 'chug kararlılığı için 0.15-0.20' not in blok
