# -*- coding: utf-8 -*-
"""ÖH D29 / app-api-dogrulama a1 — onarım bekçileri.

Kapsanan defter kalemleri:
  P15B2-10  psi çevriminin ondalık kopyaları -> merkez (hrma.constants)
  P15B2-01  değer katmanı kapılarının merkezi (input_guard) kulvar sahasında
  P10B2-11  'unconverted' iki sebebi tek isimde topluyordu
  P10B2-12  döngüsellik bekçisi HAM anahtar karşılaştırıyordu
  P10B2-16  aynı pakette iki yüzde sözleşmesi (referans artık ADIYLA verilir)
  P10B1-05  find_optimum_* ürün yüzeyi değişmezi (ölü yol sessizce bağlanamaz)
  P10B1-06  plaka hükmünün ΔP'si ile yayımlanan ΔP tek kaynak (ÇÜRÜTME kilidi)

Her bekçi ters-mutasyonla sınandı: docs/scofield/raw/OH/D29/
app-api-dogrulama/a1/mutasyon.json.
"""
import ast
import io
import math
import contextlib
import os

import numpy as np
import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _oku(bagil):
    with open(os.path.join(KOK, bagil), encoding='utf-8') as f:
        return f.read()


# ===========================================================================
# P15B2-10 — psi çevrimi TEK KAYNAK
# ===========================================================================
#: Ölçümde (once.json) ondalık kopya taşıyan dosyalar.
PSI_TUKETICILERI = (
    'hrma/analysis/two_phase_loss.py',
    'hrma/engines/cycle_power_balance.py',
    'hrma/engines/cea_bridge.py',
    'hrma/data/external_data_fetcher.py',
    'hrma/validation/record_adapters.py',
    'hrma/analysis/valve_feedline.py',
)


def test_p15b2_10_psi_kanonu_kesin_tanimlardan_turetilir():
    """Merkezdeki sayı literal DEĞİL, kesin birim tanımlarından türetilir."""
    from hrma.constants import G_0, IN_M, LB_KG, PA_PER_BAR, PA_PER_PSI, \
        PSIA_PER_BAR
    assert IN_M == 0.0254                     # uluslararası inch (TAM)
    assert LB_KG == 0.45359237                # avoirdupois pound (TAM)
    assert PA_PER_PSI == LB_KG * G_0 / (IN_M ** 2)
    assert PSIA_PER_BAR == PA_PER_BAR / PA_PER_PSI
    # NIST SP 811 yuvarlaması ile uyum (bağıl 1e-12 altı).
    assert abs(PA_PER_PSI - 6894.757293168) / 6894.757293168 < 1e-12
    assert abs(PSIA_PER_BAR - 14.503773773) / 14.503773773 < 1e-11


def test_p15b2_10_tuketicilerde_ondalik_kopya_kalmadi():
    """Beş tüketici dosyada psi/bar-psia ondalık literali BULUNMAZ."""
    from hrma.constants import PA_PER_PSI, PSIA_PER_BAR
    suclu = {}
    for bagil in PSI_TUKETICILERI:
        metin = _oku(bagil)
        agac = ast.parse(metin)
        for dugum in ast.walk(agac):
            if not (isinstance(dugum, ast.Constant)
                    and isinstance(dugum.value, float)):
                continue
            v = dugum.value
            yakin_psi = abs(v - PA_PER_PSI) / PA_PER_PSI < 1e-3
            yakin_bar = abs(v - PSIA_PER_BAR) / PSIA_PER_BAR < 1e-3
            if yakin_psi or yakin_bar:
                suclu.setdefault(bagil, []).append((dugum.lineno, v))
    assert suclu == {}, (
        f'psi çevriminin ondalık kopyası geri geldi: {suclu}. Sabit '
        f'hrma.constants.PA_PER_PSI / PSIA_PER_BAR üzerinden okunur '
        f'(defter P15B2-10).')


def test_p15b2_10_tuketiciler_ayni_sayiyi_okur():
    """Dört tüketicinin çevirici değeri BİT-AYNI olmalı."""
    from hrma.constants import PA_PER_PSI, PSIA_PER_BAR
    from hrma.analysis.two_phase_loss import _BAR_TO_PSIA as a
    from hrma.engines.cycle_power_balance import _BAR_TO_PSIA as b
    from hrma.engines.cea_bridge import BAR_TO_PSIA as c
    from hrma.analysis.valve_feedline import PSI_PA
    from hrma.validation.record_adapters import UNIT_TO_SI
    assert a == b == c == PSIA_PER_BAR
    assert PSI_PA == PA_PER_PSI
    assert UNIT_TO_SI['psi'] == UNIT_TO_SI['psia'] == PA_PER_PSI


# ===========================================================================
# P15B2-01 — değer katmanı merkezinin kulvar sahasındaki kapsamı
# ===========================================================================
#: Kulvarın sahası (D29 kulvar bölmesi). Bu dosyalarda YEREL değer kapısı
#: tanımı kalmaz; kural hrma.utils.input_guard'dadır.
SAHA_DOSYALARI = (
    'hrma/validation/motor_validation.py',
    'hrma/validation/validation_system.py',
    'hrma/validation/record_adapters.py',
    'hrma/validation/user_data_validation.py',
    'hrma/validation/correlation_runner.py',
    'hrma/validation/experiment_db.py',
    'hrma/analysis/uq_adapters.py',
)


def test_p15b2_01_saha_kapilari_merkeze_bagli():
    """Sahadaki değer kapıları merkezin gövdesini KOPYALAMAZ, ÇAĞIRIR."""
    kopya = []
    for bagil in SAHA_DOSYALARI:
        metin = _oku(bagil)
        agac = ast.parse(metin)
        for dugum in ast.walk(agac):
            if not isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            govde = ast.get_source_segment(metin, dugum) or ''
            # ÇEVRİLDİ — ÖH D30 / OH-D29-07. Tarama bir DESEN eşlemesidir
            # ('isfinite' + 'float(' + 'bool'); merkezi ÇAĞIRAN bir gövde de
            # bu deseni taşıyabilir (``motor_validation._bandsiz_sayisal_
            # sorun`` tip kuralını ``is_json_number``dan okur ama bool'u
            # ADIYLA anar). Kopya ölçüsü artık ilişkiseldir: merkezin adını
            # çağıran gövde kopya DEĞİLDİR. Eski hâli, merkeze bağlanan yeni
            # kapıyı 'yerel kopya' diye kırmızıya düşürüyordu.
            if ('isfinite' in govde and 'float(' in govde
                    and 'bool' in govde and len(govde) < 2500
                    and 'input_guard' not in govde
                    and 'finite_number' not in govde
                    and 'finite_positive' not in govde
                    and 'is_json_number' not in govde):
                kopya.append(f'{bagil}::{dugum.name}')
    assert kopya == [], (
        f'değer katmanı kapısı yerel olarak yeniden yazılmış: {kopya}. '
        f'Kural hrma.utils.input_guard.finite_number / finite_positive '
        f'içindedir (defter P15B2-01).')


def test_p15b2_01_numpy_bool_ve_float32_merkez_sozlesmesi():
    """Yerel kopyaların iki ayrışması: np.bool_ sızıyordu, np.float32 düşüyordu."""
    from hrma.validation.motor_validation import _num
    from hrma.validation.validation_system import _finite_positive
    from hrma.analysis.uq_adapters import _finite_float
    # np.bool_ Python bool'un ALT SINIFI DEĞİLDİR; float(np.bool_(True)) = 1.0
    assert not isinstance(np.bool_(True), bool)
    assert _num(np.bool_(True)) is None
    assert _finite_positive(np.bool_(True)) is None
    assert _finite_float(np.bool_(True)) is None
    # np.float32 (int, float) örneği DEĞİLDİR ama MEŞRU bir ölçüdür
    assert not isinstance(np.float32(3.5), (int, float))
    assert _finite_float(np.float32(3.5)) == pytest.approx(3.5)
    assert _num(np.float32(3.5)) == pytest.approx(3.5)
    # sözleşmenin geri kalanı korunur
    assert _num(float('nan')) is None and _num(float('inf')) is None
    assert _finite_positive(0) is None and _finite_positive(-1.0) is None


# ===========================================================================
# P10B2-11 — iki sebep, iki ad
# ===========================================================================
def test_p10b2_11_cakisan_taban_unknown_unit_degildir():
    from hrma.validation.record_adapters import convert_block
    blok = {
        'combustion_temperature_f': 5000.0,   # birim ÇÖZÜLEMEZ
        'chamber_pressure_bar': 30.0,         # taban: chamber_pressure
        'chamber_pressure_psia': 435.1,       # AYNI taban, ikinci kez
    }
    cev = convert_block(blok)
    assert cev['unconverted'] == ['combustion_temperature_f'], (
        f"'unconverted' YALNIZ birimi çözülemeyen anahtarı taşır; "
        f"bulunan: {cev['unconverted']}")
    assert cev['duplicate_base'] == ['chamber_pressure_psia'], (
        f"taban adı çakışan anahtar 'duplicate_base'e gider; "
        f"bulunan: {cev.get('duplicate_base')}")
    assert 'chamber_pressure' in cev['si']


def test_p10b2_11_kosucu_iki_durumu_ayirir():
    from hrma.validation.record_adapters import adapt_record
    from hrma.validation.correlation_runner import _score_adapter_result
    kayit = {
        'record_id': 'p10b2-11', 'motor_type': 'hybrid',
        'source': {'citation': 'ölçüm'},
        'inputs': {},
        'measured': {
            'combustion_temperature_f': 5000.0,
            'chamber_pressure_bar': 30.0,
            'chamber_pressure_psia': 435.1,
        },
    }
    with contextlib.redirect_stdout(io.StringIO()):
        ad = adapt_record(kayit)
    assert ad['measured_unconverted'] == ['combustion_temperature_f']
    assert ad['measured_duplicate_base'] == ['chamber_pressure_psia']
    with contextlib.redirect_stdout(io.StringIO()):
        skor = _score_adapter_result(ad)
    durumlar = {k: v.get('status') for k, v in skor.items()}
    assert durumlar.get('combustion_temperature_f') == 'unknown_unit'
    assert durumlar.get('chamber_pressure_psia') == 'duplicate_base', (
        f'birimi BİLİNEN ama tabanı dolu olan anahtar "unknown_unit" diye '
        f'raporlanıyor: {durumlar}')


# ===========================================================================
# P10B2-12 — döngüsellik bekçisi kanonik taban ada bakar
# ===========================================================================
def _kayit(inputs, measured):
    return {'schema_version': 'hrma-exp-1', 'record_id': 'p10b2-12',
            'source': {'citation': 'ölçüm'}, 'motor_type': 'hybrid',
            'inputs': inputs, 'measured': measured}


@pytest.mark.parametrize('inputs,measured,taban', [
    ({'chamber_pressure_bar': 30.0}, {'chamber_pressure_psia': 435.1},
     'chamber_pressure'),                              # birim varyantı
    ({'mixture_ratio': 5.0}, {'of_ratio': 5.0}, 'of_ratio'),        # takma ad
    ({'average_thrust': 1000.0}, {'thrust_mean': 1000.0}, 'thrust_mean'),
    ({'thrust_n': 1000.0}, {'thrust_n': 1000.0}, 'thrust'),         # birebir
])
def test_p10b2_12_dongusellik_kanonik_tabanda_yakalanir(inputs, measured,
                                                        taban):
    from hrma.validation.experiment_db import validate_record
    hatalar = [h for h in validate_record(_kayit(inputs, measured))
               if 'döngüsellik' in h]
    assert hatalar, (
        f'aynı kanonik büyüklük ({taban}) hem inputs hem measured içinde '
        f'ama bekçi susuyor: inputs={inputs} measured={measured}')
    assert taban in hatalar[0]


def test_p10b2_12_farkli_buyuklukler_serbest():
    """Yanlış pozitif olmamalı: ayrı büyüklükler döngüsel DEĞİLDİR."""
    from hrma.validation.experiment_db import validate_record
    hatalar = [h for h in validate_record(
        _kayit({'chamber_pressure_bar': 30.0}, {'thrust_n': 1000.0}))
        if 'döngüsellik' in h]
    assert hatalar == []


# ===========================================================================
# P10B2-16 — yüzde sözleşmesi merkezden, referans ADIYLA
# ===========================================================================
def test_p10b2_16_iki_modul_de_merkezi_cagirir():
    from hrma.validation import _relative
    from hrma.validation import correlation_runner as cr
    from hrma.validation import user_data_validation as udv
    assert cr.SCORE_ERROR_REFERENCE == _relative.REFERENCE_MEASUREMENT
    # ÇEVRİLDİ — ÖH D30 / OH-D28-12 + P10B2-16 (ana model hükmü,
    # 9 Eylül 2026): D29'da iki payda BİLEREK yan yana bırakılmıştı
    # ('referans seçimi ürün kararıdır'). Karar verildi: KANON
    # ÖLÇÜMdür (ASME V&V 20-2009). Bekçi artık kanonun TEKliğini
    # sınar; eski satır kusuru (iki ayrı payda) mandallıyordu.
    assert udv.PCT_DIFF_REFERENCE == _relative.CANONICAL_REFERENCE
    assert _relative.CANONICAL_REFERENCE == _relative.REFERENCE_MEASUREMENT
    # Metin araması YETMEZ (içe aktarma satırı dosyada kalabilir): iki
    # üreticinin GÖVDESİ merkezi ÇAĞIRMALI.
    for bagil, fn_adi in (('hrma/validation/correlation_runner.py',
                           '_score_adapter_result'),
                          ('hrma/validation/user_data_validation.py',
                           '_pct_diff')):
        metin = _oku(bagil)
        agac = ast.parse(metin)
        hedef = [d for d in ast.walk(agac)
                 if isinstance(d, ast.FunctionDef) and d.name == fn_adi]
        assert hedef, f'{bagil}::{fn_adi} bulunamadı'
        cagri = [d for d in ast.walk(hedef[0])
                 if isinstance(d, ast.Call)
                 and getattr(d.func, 'id', getattr(d.func, 'attr', None))
                 == 'relative_difference_pct']
        assert cagri, (
            f'{bagil}::{fn_adi} yüzde farkını KENDİ içinde hesaplıyor; '
            f'formül hrma.validation._relative.relative_difference_pct '
            f'içindedir (defter P10B2-16)')
        # ...ve payda rolü ANAHTAR SÖZCÜKLE verilmiş olmalı
        assert any(k.arg == 'reference' for k in cagri[0].keywords), (
            f'{bagil}::{fn_adi} payda rolünü adıyla vermiyor')


def test_p10b2_16_referans_rolu_zorunlu_ve_sifir_payda_fail_closed():
    from hrma.validation._relative import relative_difference_pct
    with pytest.raises(TypeError):
        relative_difference_pct(1.0, 2.0)          # reference= zorunlu
    with pytest.raises(ValueError):
        relative_difference_pct(1.0, 2.0, reference='keyfi')
    with pytest.raises(ValueError):
        relative_difference_pct(1.0, 0.0, reference='measurement')
    assert relative_difference_pct(1100.0, 1000.0,
                                   reference='measurement') == 10.0


def test_p10b2_16_yayimlanan_govde_paydayi_soyler():
    """Tüketici hangi sözleşmeyi okuduğunu KODDAN değil VERİDEN bilir."""
    from hrma.validation.user_data_validation import compare
    t = [0.0, 1.0, 2.0]
    kullanici = {'time': t, 'thrust': [0.0, 100.0, 0.0]}
    tahmin = {'time': t, 'thrust': [0.0, 90.0, 0.0]}
    with contextlib.redirect_stdout(io.StringIO()):
        out = compare(kullanici, tahmin)
    # ÇEVRİLDİ — ÖH D30 / OH-D28-12: künye artık KANONU söyler.
    assert out.get('diff_pct_reference') == 'measurement', (
        f"'*_diff_pct' alanlarının paydası yayımlanmıyor: {sorted(out)}")


# ===========================================================================
# P10B1-05 — ürün yüzeyi değişmezi
# ===========================================================================
OLU_YOLLAR = ('find_optimum_hybrid', 'find_optimum_liquid')


def test_p10b1_05_olu_yol_urunden_cagrilmaz():
    """Tablo geri okuyucusu ürün akışına SESSİZCE bağlanamaz.

    ``find_optimum_*`` bir denge çözümü DEĞİLDİR (modül künyesi, P10B1-04):
    çan eğrisinin tepesi referans tablo değerine konur. Ürün ucu
    (``/api/find-optimum-of``) gerçek taramayı
    ``CombustionAnalyzer.find_optimum_of_ratio`` ile yapar. Bu bekçi, ölü
    yolun bir gün ürüne bağlanıp tablo sayısını "optimum" diye
    yayımlamasını engeller; bağlamak isteyen önce bu bekçiyi ve künye
    kararını karşısında bulur.
    """
    cagrilar = []
    for taban, _dizinler, dosyalar in os.walk(os.path.join(KOK, 'hrma')):
        for d in dosyalar:
            if not d.endswith('.py'):
                continue
            yol = os.path.join(taban, d)
            bagil = os.path.relpath(yol, KOK)
            if bagil == os.path.join('hrma', 'utils', 'optimum_of_ratio.py'):
                continue
            with open(yol, encoding='utf-8') as f:
                metin = f.read()
            try:
                agac = ast.parse(metin)
            except SyntaxError:
                continue
            for dugum in ast.walk(agac):
                if (isinstance(dugum, ast.Call)
                        and isinstance(dugum.func, ast.Attribute)
                        and dugum.func.attr in OLU_YOLLAR):
                    cagrilar.append(f'{bagil}:{dugum.lineno}')
    assert cagrilar == [], (
        f'referans tablo geri okuyucusu ürün akışına bağlanmış: {cagrilar}. '
        f'Bu yol denge çözümü değildir (defter P10B1-04/P10B1-05).')


def test_p10b1_05_kunye_donen_sozlukte_durur():
    """Ölü yol yine de kendi kimliğini SÖYLER (bağlanırsa yalan söylemesin)."""
    from hrma.utils.optimum_of_ratio import of_optimizer
    with contextlib.redirect_stdout(io.StringIO()):
        d = of_optimizer.find_optimum_hybrid('n2o', 'htpb')
    assert d['is_equilibrium_search'] is False
    assert d['chamber_pressure_affects_optimum'] is False
    assert 'not a searched optimum' in d['optimum_of_ratio_basis']


# ===========================================================================
# P10B1-06 — ÇÜRÜTME KİLİDİ: plaka hükmü ile panel AYNI ΔP'yi okur
# ===========================================================================
def test_p10b1_06_yayimlanan_dp_ile_plaka_dp_tek_kaynak():
    """Bulucunun iddiası (3,4x sapma) HEAD'de ÇÜRÜK; kilit burada.

    ÖLÇÜLDÜ (once.json -> P10B1-06): çözücünün kullandığı ``delta_P_inj``
    ile yayımlanan ``pressure_drop`` / ``pressure_drop_bar`` BİREBİR
    aynıdır; ``app.py`` plaka hükmünü de ``injector_results['pressure_drop']``
    ile kurar. Bu bekçi ayrışmanın geri gelmesini engeller.
    """
    from hrma.utils.injector_design import InjectorDesign
    with contextlib.redirect_stdout(io.StringIO()):
        tas = InjectorDesign(mdot_ox=2.0, chamber_pressure=30.0,
                             tank_pressure=50.0, pressure_drop=6.0,
                             oxidizer_type='n2o')
        sonuc = tas.calculate()
    assert sonuc['pressure_drop'] == sonuc['pressure_drop_bar'] == \
        tas.delta_P_inj == pytest.approx(6.0)
    # app.py plaka hükmünü AYNI yayımlanan alandan kurar (kaynak kilidi).
    metin = _oku('hrma/app.py')
    assert "injector_results.get('pressure_drop')" in metin, (
        'plaka yapısal hükmü artık yayımlanan enjektör ΔP alanından '
        'okumuyor — panel ile hüküm ayrışabilir (defter P10B1-06)')
