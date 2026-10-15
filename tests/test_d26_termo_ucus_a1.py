"""ÖH Dalga-26 · termo-ucus · aşama 1 bekçileri.

Dört kalem:

OH-D25-14  ``np.trapz`` NumPy 2.0'da ad alanından kaldırıldı; ürün kodu
           (30 site / 11 dosya) ve ÖH D20 bekçisi (1 site) o gün kırılırdı.
OH-B1-03   Yayımlanan chug künyesi "depodaki TEK sayısal tanım" diyordu;
           ölçülen borç 7 site / 4 dosyaydı (borç imi kalktı).
P4B4-14    "En düşük N mod" listesi havuz kırpması yüzünden gerçek modları
           düşürüyordu (borç imi kalktı).
P4B4-16    Chug oranının üst sınırı yoktu; bandın 48 katı temiz OK alıyordu
           (borç imi kalktı).

Ölçüm dosyaları: docs/scofield/raw/OH/D26/termo-ucus/a1/{once,sonra}.json
Ters-mutasyon:   docs/scofield/raw/OH/D26/termo-ucus/a1/mutasyon.json
"""

import ast
import math
import os
import re
import sys

import numpy as np
import pytest

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _KOK not in sys.path:
    sys.path.insert(0, _KOK)

from hrma.analysis import acoustic_modes                          # noqa: E402
from hrma.analysis.acoustic_modes import (                        # noqa: E402
    AcousticModeAnalyzer,
    CHUG_DP_RATIO_BAND_MAX,
    CHUG_DP_RATIO_MINIMUM,
    CHUG_DP_RATIO_RECOMMENDED,
    CHUG_THRESHOLD_DEFINITION_POINT,
    CHUG_THRESHOLD_SOURCE,
    FREQ_BAND_BUZZ_MAX_HZ,
    longitudinal_frequency,
    sound_speed,
)

# ===========================================================================
# Ortak fikstürler — sayılar BURADA yazılıdır, üründen türetilmez.
# ===========================================================================
#: Katı motor orantısı (uzun/ince kavite). P4B4-14 defter vakası birebir.
KATI_KAVITESI = dict(chamber_temperature=2000.0, gamma=1.2,
                     gas_constant=300.0, chamber_diameter=0.20,
                     chamber_length=2.5)
#: L/D ~ 4 kamara — kırpmanın GÖRÜNMEDİĞİ negatif kontrol.
LD4_KAMARA = dict(chamber_temperature=3000.0, gamma=1.2, gas_constant=360.0,
                  chamber_diameter=0.10, chamber_length=0.40)
#: Yayımlanmış klasik chug tasarım bandı (Sutton & Biblarz RPE 9. baskı,
#: Böl. 8): dP_inj / P_c = %15-25. Testte YAZILIDIR; üründen okunursa
#: bekçi ürünün kendi bandını aşmasını göremez.
CHUG_BANDI_YAYIMLANMIS = (0.15, 0.25)


def _analiz(**ek):
    args = dict(LD4_KAMARA, n_modes=10)
    args.update(ek)
    return AcousticModeAnalyzer().analyze(**args)


def _eksik_boyuna(res, a, L):
    """Tablonun kendi en yüksek frekansının altında kalan ama tabloda
    BULUNMAYAN gerçek boyuna modlar (üyelik ölçümü, kapalı form)."""
    fmax = max(m['frequency_hz'] for m in res['modes'])
    listede = {m['label'] for m in res['modes']}
    eksik, q = [], 1
    while True:
        f = longitudinal_frequency(a, L, q)
        if f > fmax * (1.0 + 1e-12):
            return fmax, eksik
        if f'{q}L' not in listede:
            eksik.append((f'{q}L', f))
        q += 1
        if q > 20000:
            return fmax, eksik


def _trapz_siteleri(dizin):
    """``np.trapz`` / ``numpy.trapz`` ÇAĞRI siteleri (yorum değil, AST)."""
    siteler = []
    for kok, dizinler, dosyalar in os.walk(dizin):
        dizinler[:] = [d for d in dizinler if d != '__pycache__']
        for dosya in sorted(dosyalar):
            if not dosya.endswith('.py'):
                continue
            tam = os.path.join(kok, dosya)
            bagil = os.path.relpath(tam, _KOK).replace(os.sep, '/')
            try:
                agac = ast.parse(open(tam, encoding='utf-8').read(),
                                 filename=tam)
            except (SyntaxError, UnicodeDecodeError):
                continue
            for dugum in ast.walk(agac):
                if (isinstance(dugum, ast.Attribute) and dugum.attr == 'trapz'
                        and isinstance(dugum.value, ast.Name)
                        and dugum.value.id in ('np', 'numpy')):
                    siteler.append((bagil, dugum.lineno))
    return siteler


# ===========================================================================
# OH-D25-14 — NumPy 2 uyumu
# ===========================================================================
#: Adın ÇÖZÜLDÜĞÜ tek yer. Başka hiçbir ürün dosyası ``np.trapz`` yazamaz.
TRAPEZOID_TEK_KAYNAK = 'hrma/utils/numeric_compat.py'

#: Adı GÜVENLİ biçimde çözen (yani NumPy 2'de de koşan) bekçi dosyaları:
#: ``getattr(np, 'trapezoid', None) or np.trapz`` deseni. Bunlar borç
#: değildir; adı anmaları zorunludur.
TRAPZ_ADINI_GUVENLI_COZENLER = {
    'tests/test_d26_termo_ucus_a1.py',      # bu dosya (NumPy 2 taklidi)
    'tests/test_grain_types.py',            # zaten güvenli desen
}

#: BORÇ KAPANDI (ÖH D27, OH-D26-08, bekci-cevirisi a1). D26'da ölçülen
#: 24 site / 14 dosya TEK KAYNAK'a çevrildi; kanıt
#: docs/scofield/raw/OH/D27/bekci-cevirisi/a1/{once_taban,sonra}.json ve
#: k1_cevir.py (dosya başına AST sayımı + ``count`` doğrulamalı çevrim).
#: Serbest nüfusun tavanı artık SIFIR: güvenli çözücüler ile aşağıdaki
#: ADLI muafiyet dışında tests/ altında ``np.trapz`` yazılamaz.
TESTS_TRAPZ_TAVANI = 0

#: ADLI + TARİHLİ tek muafiyet — kardeş dal ölçümü (ÖH D27, 8 Eylül 2026):
#: ``tests/test_d26_fea_cfd_a2.py`` o sırada fea-cfd / fix-26 kulvarının
#: elindeydi (aynı dosyada aktif değişiklik), bu yüzden bekci-cevirisi
#: oradaki TEK siteye dokunmadı. Muafiyet borcu GİZLEMEZ: aşağıdaki
#: toplam tavan onu da sayar. Borç ödendiğinde küme boşalır ve
#: ``TRAPZ_TOPLAM_TAVANI`` 0'a çekilir.
TRAPZ_BASKA_KULVAR_MUAFIYETI = {
    'tests/test_d26_fea_cfd_a2.py',         # fea-cfd / fix-26, ÖH D27
}

#: Muafiyet DAHİL toplam borç tavanı. TEK YÖNLÜ: büyürse kırmızı,
#: küçülürse yeşil — başka kulvarın onarımı bu bekçiyi kırmasın diye.
TRAPZ_TOPLAM_TAVANI = 1


class TestOHD2514NumpyIkiUyumu:
    """ÖLÇÜLEN KUSUR (once.json, K1): ürün kodunda 30 çağrı sitesi / 11
    dosya + D20 bekçisinde 1 site ``np.trapz`` adını çalışma anında
    çözüyordu. NumPy 2.0 bu adı ad alanından KALDIRDI (np.trapezoid);
    NumPy 2 taklidi altında ölçüm ``AttributeError: module 'numpy' has no
    attribute 'trapz'`` verdi — yani toplam impuls / sürtünme direnci /
    basınç integrali ürün yolları kırılırdı."""

    def test_urun_kodunda_np_trapz_adi_KALMADI(self):
        siteler = [s for s in _trapz_siteleri(os.path.join(_KOK, 'hrma'))
                   if s[0] != TRAPEZOID_TEK_KAYNAK]
        assert siteler == [], (
            'ürün kodunda np.trapz çağrısı kaldı (NumPy 2.0 bu adı '
            f'kaldırdı): {siteler}. Adı {TRAPEZOID_TEK_KAYNAK} üzerinden '
            'ithal et.')

    def test_tek_kaynak_gercekten_ADI_cozuyor(self):
        from hrma.utils.numeric_compat import trapezoid
        # Ad tek yerde çözülür ve iki NumPy sürümünde de aynı kuralı verir.
        assert callable(trapezoid)
        beklenen = getattr(np, 'trapezoid', None) or np.trapz
        assert trapezoid is beklenen
        # Sayısal çapa: yamuk kuralı el hesabıyla.
        assert float(trapezoid([0.0, 2.0, 4.0], [0.0, 1.0, 2.0])) == (
            pytest.approx(4.0, rel=1e-12))

    def test_D20_bekcisi_de_numpy2_altinda_kosuyor(self):
        siteler = _trapz_siteleri(os.path.join(_KOK, 'tests'))
        d20 = [s for s in siteler
               if s[0] == 'tests/test_d20_termo_ucus_a1.py']
        assert d20 == [], f'D20 termo-ucus bekçisinde np.trapz kaldı: {d20}'

    def test_kalan_bekci_borcu_BUYUMUYOR(self):
        """tests/ altındaki kalan borç envanterli ve tavanı yükselemez.

        ÖH D27 (OH-D26-08): serbest nüfus tavanı 24 -> 0 indirildi.
        ``TRAPZ_BASKA_KULVAR_MUAFIYETI`` yalnız kardeş dal çakışması
        yüzünden dokunulmayan dosyaları taşır ve toplam tavana SAYILIR.
        """
        hepsi = [s for s in _trapz_siteleri(os.path.join(_KOK, 'tests'))
                 if s[0] not in TRAPZ_ADINI_GUVENLI_COZENLER]
        serbest = [s for s in hepsi
                   if s[0] not in TRAPZ_BASKA_KULVAR_MUAFIYETI]
        assert len(serbest) <= TESTS_TRAPZ_TAVANI, (
            f'tests/ altında muafiyetsiz np.trapz sitesi {len(serbest)}, '
            f'tavan {TESTS_TRAPZ_TAVANI} — tavanı yükseltmek borcu '
            f'gizlemektir. Kalan: {sorted({s[0] for s in serbest})}. '
            'Adı hrma/utils/numeric_compat.trapezoid üzerinden ithal et.')
        assert len(hepsi) <= TRAPZ_TOPLAM_TAVANI, (
            f'muafiyet DAHİL toplam np.trapz sitesi {len(hepsi)}, tavan '
            f'{TRAPZ_TOPLAM_TAVANI} — muafiyet kümesi büyüyemez. '
            f'Kalan: {sorted({s[0] for s in hepsi})}')

    def test_numpy2_TAKLIDI_altinda_urun_yolu_kosuyor(self):
        """NumPy 2 ad alanı taklidi: ``trapz`` YOK, ``trapezoid`` VAR.

        Kusur bu koşulda ölçülmüştü (once.json K1: ``AttributeError:
        module 'numpy' has no attribute 'trapz'``). Taklit NumPy 2.0 ad
        alanını birebir kurar: ``np.trapz`` silinir, ``np.trapezoid``
        eklenir (2.0'da yalnız YENİDEN ADLANDIRMA yapıldı). Ad geri yazımı
        ``finally`` içindedir — süreç kirletilmez, ``git checkout`` yok.
        """
        import importlib
        trapz_vardi = hasattr(np, 'trapz')
        trapz_yedek = getattr(np, 'trapz', None)
        trapezoid_vardi = hasattr(np, 'trapezoid')
        trapezoid_yedek = getattr(np, 'trapezoid', None)
        try:
            if not trapezoid_vardi:
                setattr(np, 'trapezoid', trapz_yedek)   # NumPy 2 adı
            if trapz_vardi:
                delattr(np, 'trapz')                    # NumPy 2'de YOK
            # Ön koşul: eski çağrı biçimi (``np.trapz(...)``) artık düşer.
            with pytest.raises(AttributeError):
                np.trapz([0.0, 1.0], [0.0, 1.0])
            # Tek kaynak bu ad alanında YENİDEN çözülebiliyor.
            mc = importlib.reload(
                importlib.import_module('hrma.utils.numeric_compat'))
            assert mc.trapezoid is np.trapezoid
            assert float(mc.trapezoid([0.0, 2.0, 4.0],
                                      [0.0, 1.0, 2.0])) == pytest.approx(4.0)
            # Ürün modülü adı ÇAĞRI ANINDA aramıyor: alias ithal anında
            # bağlanmıştır, dolayısıyla ad alanı değişse de yol koşar.
            from hrma.analysis import trajectory_analysis as ta
            assert float(ta._trapezoid([0.0, 2.0, 4.0],
                                       [0.0, 1.0, 2.0])) == pytest.approx(4.0)
        finally:
            if trapz_vardi:
                setattr(np, 'trapz', trapz_yedek)
            if not trapezoid_vardi and hasattr(np, 'trapezoid'):
                delattr(np, 'trapezoid')
            importlib.reload(
                importlib.import_module('hrma.utils.numeric_compat'))
        # Ortam geri yazıldı ve tek kaynak yine bu sürümün adını çözüyor.
        from hrma.utils.numeric_compat import trapezoid as _geri
        assert _geri is (getattr(np, 'trapezoid', None) or np.trapz)


# ===========================================================================
# OH-B1-03 — yayımlanan künye "TEK tanım" diye yalan söylemiyor
# ===========================================================================
class TestOHB103KunyeMunhasirlikIddiaEtmiyor:
    """ÖLÇÜLEN KUSUR (once.json, K2): ``_chug_report()['threshold_source']``
    kullanıcıya "This pair (0.20 / 0.15) is the ONLY numeric definition of
    the chug design rule in HRMA" diyordu; aynı anda ölçülen borç 7 site /
    4 dosyaydı (hepsi ``hrma/engines/`` altında)."""

    def test_yayimlanan_kunyede_munhasirlik_iddiasi_YOK(self):
        chug = _analiz(injector_dp_ratio=0.20)['stability_report']['chug']
        for yasak in ('ONLY numeric definition', 'only numeric definition'):
            assert yasak not in chug['threshold_source']
        assert yasak not in CHUG_THRESHOLD_SOURCE

    def test_tanim_noktasi_YAPISAL_olarak_yayimlaniyor(self):
        """Düzyazı iddia yerine doğrulanabilir kayıt: modül + sembol."""
        chug = _analiz(injector_dp_ratio=0.20)['stability_report']['chug']
        tanim = chug['threshold_definition_point']
        assert tanim['module'] == 'hrma.analysis.acoustic_modes'
        assert tanim['exclusive_in_repository'] is False
        assert set(tanim['symbols']) == {
            'CHUG_DP_RATIO_MINIMUM', 'CHUG_DP_RATIO_RECOMMENDED',
            'CHUG_DP_RATIO_BAND_MAX'}
        for sembol in tanim['symbols']:
            assert isinstance(getattr(acoustic_modes, sembol), float)
        # Kaynak sözlüğü mutasyona kapalı: yayımlanan kopya olmalı.
        tanim['module'] = 'BOZULDU'
        assert CHUG_THRESHOLD_DEFINITION_POINT['module'] == (
            'hrma.analysis.acoustic_modes')

    def test_kunyenin_kanit_omurgasi_KORUNDU(self):
        """Yalan sökülürken künyenin gerçek dayanakları düşmemeli."""
        for parca in ('Sutton & Biblarz', 'SP-194', 'not attributed to it'):
            assert parca in CHUG_THRESHOLD_SOURCE, parca
        assert re.search(r'15\s*-\s*25\s*%', CHUG_THRESHOLD_SOURCE)


# ===========================================================================
# P4B4-14 — mod havuzu kırpması
# ===========================================================================
class TestP4B414HavuzKirpmasi:
    """ÖLÇÜLEN KUSUR (once.json, K3): havuz ``MAX_LONGITUDINAL_INDEX = 6``
    ile sabit kırpılıyordu. Katı motor orantısında (a = 848,53 m/s,
    n_modes = 10) tablonun kendi en yüksek frekansı 2538,06 Hz iken
    7L..14L (1187,9-2375,9 Hz) SEKİZ gerçek boyuna mod listeye giremiyordu;
    n_modes = 200 istendiğinde havuz 83 adayda tükeniyor, kayıp 84 moda
    çıkıyordu. Kırpma n_modes ile aşılamıyordu."""

    @pytest.mark.parametrize('n_modes', [10, 59, 200])
    def test_tablo_kendi_bandinda_EKSIKSIZ(self, n_modes):
        res = AcousticModeAnalyzer().analyze(n_modes=n_modes, **KATI_KAVITESI)
        a = sound_speed(KATI_KAVITESI['gamma'], KATI_KAVITESI['gas_constant'],
                        KATI_KAVITESI['chamber_temperature'])
        fmax, eksik = _eksik_boyuna(res, a, KATI_KAVITESI['chamber_length'])
        assert len(res['modes']) == n_modes
        assert not eksik, (
            f'{fmax:.1f} Hz altında {len(eksik)} gerçek boyuna mod tabloya '
            f'giremedi: {[(k, round(v, 1)) for k, v in eksik]}')

    def test_defter_vakasi_7L_14L_ARTIK_LISTEDE(self):
        """Kusurun birebir vakası: sekiz mod geri geldi."""
        res = AcousticModeAnalyzer().analyze(n_modes=10, **KATI_KAVITESI)
        etiketler = [m['label'] for m in res['modes']]
        assert etiketler == [f'{q}L' for q in range(1, 11)]
        a = sound_speed(KATI_KAVITESI['gamma'], KATI_KAVITESI['gas_constant'],
                        KATI_KAVITESI['chamber_temperature'])
        # Kapalı form çapası: f_qL = q*a/(2L), testin içinde kurulur.
        for m in res['modes']:
            q = int(m['label'].rstrip('L'))
            assert m['frequency_hz'] == pytest.approx(
                q * a / (2.0 * KATI_KAVITESI['chamber_length']), rel=1e-12)

    def test_havuz_sinirlari_ve_eksiksizlik_YAYIMLANIYOR(self):
        res = AcousticModeAnalyzer().analyze(n_modes=10, **KATI_KAVITESI)
        havuz = res['mode_pool']
        assert havuz['truncated'] is False
        assert havuz['complete_below_hz'] == pytest.approx(
            max(m['frequency_hz'] for m in res['modes']), rel=1e-12)
        assert havuz['returned_n_modes'] == 10
        assert havuz['requested_n_modes'] == 10
        assert havuz['candidate_count'] > 83     # eski havuz 83'te tükeniyordu
        # Büyütme tohumdan başlar ve tohumun ALTINA inmez.
        tohum = havuz['seed_bounds']
        assert havuz['longitudinal_max_q'] > tohum['longitudinal_max_q']
        assert havuz['tangential_max_m'] >= tohum['tangential_max_m']
        assert havuz['radial_max_n'] >= tohum['radial_max_n']
        assert 'pool' in res['mode_table_basis'].lower()

    def test_screech_hukmu_EKSIKSIZ_havuzdan_turuyor(self):
        res = AcousticModeAnalyzer().analyze(n_modes=10, **KATI_KAVITESI)
        hf = res['stability_report']['high_frequency']
        assert hf['mode_pool_truncated'] is False
        assert set(hf['modes_in_screech_band']) == {
            m['label'] for m in res['modes']
            if m['band'] == 'screech_range'}
        # Kusur vakası: 1000 Hz üstündeki 7L..10L artık hükmün içinde.
        assert {f'{q}L' for q in range(7, 11)} <= set(
            hf['modes_in_screech_band'])
        assert hf['mode_pool_complete_below_hz'] >= FREQ_BAND_BUZZ_MAX_HZ

    def test_enine_aday_LISTEYE_GIRMESE_DE_adiyla_yayimlaniyor(self):
        """Yan etkinin fail-closed karşılığı: 1T yok olmaz."""
        res = AcousticModeAnalyzer().analyze(n_modes=10, **KATI_KAVITESI)
        en_dusuk = res['stability_report']['high_frequency'][
            'lowest_transverse_mode']
        assert en_dusuk is not None
        assert en_dusuk['label'] == '1T'
        assert en_dusuk['in_mode_table'] is False
        a = sound_speed(KATI_KAVITESI['gamma'], KATI_KAVITESI['gas_constant'],
                        KATI_KAVITESI['chamber_temperature'])
        # f_1T = a*alpha_11/(pi*D), alpha_11 = 1.8412 (A&S Tablo 9.5)
        assert en_dusuk['frequency_hz'] == pytest.approx(
            a * 1.8412 / (math.pi * KATI_KAVITESI['chamber_diameter']),
            rel=5e-4)

    def test_KISA_kamarada_havuz_DEGISMEDI(self):
        """Negatif kontrol: kırpmanın görünmediği L/D~4 kamarada onarım
        havuzu büyütmez (gereksiz churn yok, çapa sapmaz)."""
        res = _analiz()
        havuz = res['mode_pool']
        assert (havuz['tangential_max_m'], havuz['radial_max_n'],
                havuz['longitudinal_max_q']) == (
            AcousticModeAnalyzer.MAX_TANGENTIAL_INDEX,
            AcousticModeAnalyzer.MAX_RADIAL_INDEX,
            AcousticModeAnalyzer.MAX_LONGITUDINAL_INDEX)
        assert havuz['candidate_count'] == 83
        a = sound_speed(LD4_KAMARA['gamma'], LD4_KAMARA['gas_constant'],
                        LD4_KAMARA['chamber_temperature'])
        _, eksik = _eksik_boyuna(res, a, LD4_KAMARA['chamber_length'])
        assert not eksik


# ===========================================================================
# P4B4-16 — chug oranının üst sınırı
# ===========================================================================
class TestP4B416ChugUstSiniri:
    """ÖLÇÜLEN KUSUR (once.json, K4): 0,30 / 0,50 / 1,00 / 1,527 / 12,0
    oranlarının BEŞİ de "... meets the recommended >= 0.20 design rule"
    cümlesiyle temiz ``STATUS_OK`` alıyordu; modülün kendi künyesi bandı
    %15-25 ilan ederken üst uçta hiçbir kademe yoktu."""

    def test_band_ust_ucu_YAYIMLANIYOR_ve_ilan_edilen_bandla_ayni(self):
        alt, ust = CHUG_BANDI_YAYIMLANMIS
        assert CHUG_DP_RATIO_BAND_MAX == pytest.approx(ust, rel=1e-12)
        assert CHUG_DP_RATIO_MINIMUM == pytest.approx(alt, rel=1e-12)
        assert alt <= CHUG_DP_RATIO_RECOMMENDED <= ust
        chug = _analiz(injector_dp_ratio=0.20)['stability_report']['chug']
        assert chug['design_band_min_ratio'] == pytest.approx(alt, rel=1e-12)
        assert chug['design_band_max_ratio'] == pytest.approx(ust, rel=1e-12)

    @pytest.mark.parametrize('oran', [0.30, 0.5, 1.0, 1.527, 12.0])
    def test_bandin_USTUNDEKI_oran_temiz_OK_alamaz(self, oran):
        chug = _analiz(injector_dp_ratio=oran)['stability_report']['chug']
        _, ust = CHUG_BANDI_YAYIMLANMIS
        assert oran > ust                        # ön koşul
        temiz_ok = (chug['status'] == AcousticModeAnalyzer.STATUS_OK
                    and 'meets the recommended' in chug['note']
                    and not re.search(r'exceed|above the|upper', chug['note'],
                                      re.IGNORECASE))
        assert not temiz_ok, chug['note'][:160]
        assert chug['above_design_band'] is True
        assert chug['design_band_excess_factor'] == pytest.approx(
            oran / ust, rel=1e-12)
        # Hüküm AYRIMI korunur: chug mekanizması için OK doğrudur.
        assert chug['status'] == AcousticModeAnalyzer.STATUS_OK

    @pytest.mark.parametrize('oran,beklenen', [
        (0.10, AcousticModeAnalyzer.STATUS_AT_RISK),
        (0.15, AcousticModeAnalyzer.STATUS_MARGINAL),
        (0.17, AcousticModeAnalyzer.STATUS_MARGINAL),
        (0.20, AcousticModeAnalyzer.STATUS_OK),
        (0.25, AcousticModeAnalyzer.STATUS_OK),
    ])
    def test_band_ICINDE_hukum_ve_beyan_DEGISMEDI(self, oran, beklenen):
        """Sınır tam 0,25'te üst uyarı TETİKLENMEZ (yanlış alarm yok)."""
        chug = _analiz(injector_dp_ratio=oran)['stability_report']['chug']
        assert chug['status'] == beklenen
        assert chug['above_design_band'] is False
        assert chug['design_band_excess_factor'] is None
        assert not re.search(r'EXCEEDS the upper bound', chug['note'])

    def test_girdisiz_hukumde_ust_sinir_alanlari_UYDURULMUYOR(self):
        chug = _analiz()['stability_report']['chug']
        assert chug['evaluated'] is False
        assert chug['above_design_band'] is False
        assert chug['design_band_excess_factor'] is None
