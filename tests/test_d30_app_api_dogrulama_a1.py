# -*- coding: utf-8 -*-
"""ÖH D30 / app-api-dogrulama a1 — onarım bekçileri.

Kalemler: OH-D28-12 + P10B2-16 (ÇİFT), OH-D29-11 + P11B5-21 (ÇİFT),
OH-D29-07, P12bB1-12, P10B1-05, P15B2-01.

Her bekçi TERS MUTASYONLA sınandı (kanıt:
``docs/scofield/raw/OH/D30/app-api-dogrulama/a1/mutasyon.json``).
"""
import ast
import contextlib
import io
import json
import os
import re

import pytest
from tests.support.kanit import kanit_gerekli

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _oku(bagil):
    with open(os.path.join(KOK, bagil), encoding='utf-8') as f:
        return f.read()


# ===========================================================================
# OH-D28-12 + P10B2-16 — bağıl fark KANONU: payda ÖLÇÜM
# ===========================================================================

def test_ohd2812_kanon_payda_olcumdur():
    """Paketin yayımlanan iki yüzdesi AYNI paydayı kullanır.

    ÖLÇÜLDÜ (``once.json`` -> ``OH-D28-12+P10B2-16``, taban ``ab7cf68b``):
    aynı çift (ölçülen 1000, tahmin 1100) ``correlation_runner``da
    ``+10,0000 %``, ``user_data_validation``da ``-9,0909 %`` veriyordu —
    işaret ZIT. Kanon ASME V&V 20-2009'dur: payda deneysel veridir.
    """
    from hrma.validation import _relative as rel
    from hrma.validation import correlation_runner as cr
    from hrma.validation import user_data_validation as udv
    assert rel.CANONICAL_REFERENCE == rel.REFERENCE_MEASUREMENT
    assert cr.SCORE_ERROR_REFERENCE == rel.CANONICAL_REFERENCE
    assert udv.PCT_DIFF_REFERENCE == rel.CANONICAL_REFERENCE, (
        'yayımlanan yüzde kanondan koptu: '
        f'{udv.PCT_DIFF_REFERENCE!r} != {rel.CANONICAL_REFERENCE!r}')


def test_ohd2812_iki_modul_ayni_cifte_ayni_sayiyi_verir():
    """Aynı iki sayı, aynı paketten, TEK cevap (işaret dâhil)."""
    from hrma.validation import correlation_runner as cr
    from hrma.validation import user_data_validation as udv
    olculen, tahmin = 1000.0, 1100.0
    kosucu = cr._score_adapter_result({
        'measured_si': {'thrust': olculen},
        'predictions': {'thrust': tahmin},
    })['thrust']['error_pct']
    assert udv._pct_diff(olculen, tahmin) == pytest.approx(kosucu), (
        'iki modül aynı çifte hâlâ farklı yüzde veriyor')
    assert kosucu > 0, 'tahmin ölçümden büyükken işaret pozitif olmalı'


def test_p10b2_16_yayimlanan_govde_kanonu_soyler():
    """Tüketici paydayı KODDAN değil VERİDEN okur — ve payda ölçümdür."""
    from hrma.validation.user_data_validation import compare
    t = [0.0, 1.0, 2.0]
    olculen = {'time': t, 'thrust': [0.0, 1000.0, 0.0]}
    tahmin = {'time': t, 'thrust': [0.0, 1100.0, 0.0]}
    with contextlib.redirect_stdout(io.StringIO()):
        out = compare(olculen, tahmin)
    assert out['diff_pct_reference'] == 'measurement', (
        f"payda künyesi kanonu söylemiyor: {out.get('diff_pct_reference')!r}")
    assert out['metrics']['peak_thrust_diff_pct'] == pytest.approx(10.0), (
        'tepe itki farkı ÖLÇÜME bölünmüyor')


def test_ohd2812_ikinci_sozlesme_yayimlanan_yolda_kullanilmiyor():
    """``REFERENCE_PREDICTION`` yalnız ADIYLA istenirse geçer.

    Paket içindeki yayımlanan yollarda ikinci payda sözleşmesi çağrılmaz;
    çağıran olsaydı iki sözleşme yeniden yan yana dururdu.
    """
    kullananlar = []
    kok = os.path.join(KOK, 'hrma', 'validation')
    for ad in sorted(os.listdir(kok)):
        if not ad.endswith('.py') or ad == '_relative.py':
            continue
        if 'REFERENCE_PREDICTION' in _oku(os.path.join('hrma/validation', ad)):
            kullananlar.append(ad)
    assert kullananlar == [], (
        f'ikinci payda sözleşmesi yayımlanan yolda geri geldi: {kullananlar}')


# ===========================================================================
# OH-D29-11 + P11B5-21 — yalan '_tr' alanı + panelin ham HTML basımı
# ===========================================================================

_INJ_TIPLERI = ('showerhead', 'impinging_doublet', 'pintle', 'swirl',
                'gas_gas_coaxial')


def _inj_spec(tip):
    spec = {'motor_type': 'liquid', 'injector_type': tip,
            'mdot_ox': 2.97, 'mdot_fuel': 1.29, 'Pc_bar': 30.0,
            'T_c_K': 3400.0, 'mw_gas': 22.0,
            'rho_ox': 1141.0, 'rho_fuel': 810.0,
            'oxidizer_type': 'lox', 'fuel_type': 'rp1'}
    if tip == 'gas_gas_coaxial':
        spec['gas_ox'] = {'T0_K': 700.0, 'P0_bar': 45.0, 'gamma': 1.4,
                          'MW': 32.0}
        spec['gas_fuel'] = {'T0_K': 300.0, 'P0_bar': 45.0, 'gamma': 1.4,
                            'MW': 2.0}
    return spec


@pytest.mark.parametrize('tip', _INJ_TIPLERI)
def test_ohd2911_yalan_tr_alani_yayimlanmaz(tip):
    """``description_tr`` adı Türkçe VAAT EDİYOR, içerik İngilizceydi.

    ÖLÇÜLDÜ (``once.json`` -> ``OH-D29-11+P11B5-21``): dört enjektör
    tipinin dördünde de ``description_tr == description`` (bit-aynı
    İngilizce). Yalan künye yayımlanmaz (Doktrin 1).
    """
    from hrma.engines.injector_design import design_injector
    with contextlib.redirect_stdout(io.StringIO()):
        d = design_injector(_inj_spec(tip))
    desen = d['pattern']
    assert 'description_tr' not in desen, (
        f'{tip}: yalan "_tr" alanı geri geldi -> '
        f'{desen.get("description_tr")!r}')
    assert desen.get('description'), f'{tip}: açıklama boş'


def test_p11b5_21_panel_metni_ham_html_basmaz():
    """Panel açıklamayı ``description``dan ve KAÇIRARAK basar."""
    panel = _oku('hrma/static/js/injector_panel.js')
    assert 'pattern.description_tr' not in panel, (
        'panel hâlâ yalan "_tr" anahtarını okuyor')
    assert not re.search(r'\$\{dz\.pattern\.description\}', panel), (
        'uçtan gelen metin şablona HAM giriyor (kaçış yok)')
    assert re.search(r'\$\{escText\(dz\.pattern\.description\)\}', panel), (
        'açıklama escText süzgecinden geçmiyor')
    assert re.search(r'function\s+escText', panel), 'escText tanımı yok'


# ===========================================================================
# OH-D29-07 — "bu bir JSON sayısı mı" TEK kural
# ===========================================================================

def test_ohd2907_json_sayi_kurali_merkezde():
    from hrma.utils.input_guard import is_json_number
    assert is_json_number(293.15) is True
    assert is_json_number(20) is True
    assert is_json_number('293.15') is False, 'sayı-benzeri dize JSON sayısı DEĞİL'
    assert is_json_number(True) is False, 'bool sayı değildir'
    assert is_json_number(None) is False


def test_ohd2907_dogrulayici_kurali_merkezden_okur():
    """Kural motor_validation'da ÜÇÜNCÜ kez YAZILMAZ, merkezden okunur."""
    kaynak = _oku('hrma/validation/motor_validation.py')
    assert 'from hrma.utils.input_guard import finite_number, is_json_number' \
        in kaynak, 'merkez kuralı içe aktarılmıyor'
    agac = ast.parse(kaynak)
    yerel = [d for d in ast.walk(agac)
             if isinstance(d, ast.FunctionDef) and d.name == 'is_json_number']
    assert yerel == [], 'kuralın yerel kopyası yeniden doğdu'
    # Kural HER İKİ kapıda da merkezden okunmalı; birinin literale geri
    # dönmesi ötekinin varlığıyla gizlenemez (bu yüzden gövde gövde bakılır).
    for ad in ('_bant_sorunlari', '_bandsiz_sayisal_sorun'):
        dugum = [d for d in ast.walk(agac)
                 if isinstance(d, ast.FunctionDef) and d.name == ad]
        assert dugum, f'{ad} kayboldu'
        govde = ast.get_source_segment(kaynak, dugum[0])
        # Yorum satırları ELENİR: kusurun künyesi gövdede ADIYLA anlatılıyor
        # ve o metin kodun kendisiyle karıştırılamaz.
        kod = '\n'.join(satir for satir in govde.splitlines()
                        if not satir.strip().startswith('#'))
        assert 'is_json_number(' in kod, (
            f'{ad} tip kuralını merkezden okumuyor')
        assert 'isinstance(value, (int, float))' not in kod, (
            f'{ad} içinde kuralın literal kopyası geri geldi')


def test_ohd2907_dize_ucun_kapisinda_reddedilir():
    """``oxidizer_temp='293.15'`` artık kardeş uçlarla AYNI hükmü alır.

    ÖLÇÜLDÜ (``once.json`` -> ``OH-D29-07``): aynı biçimdeki dize
    ``/calculate``ta HTTP 200, ``/calculate_solid`` ve
    ``/calculate_liquid``ta HTTP 400 alıyordu.
    """
    from hrma.validation.motor_validation import MotorDataValidator
    v = MotorDataValidator()
    govde = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
             'chamber_pressure': 20.0, 'fuel_type': 'htpb',
             'oxidizer_type': 'n2o'}
    with contextlib.redirect_stdout(io.StringIO()):
        temiz = v.validate_motor_data_detailed(dict(govde), 'hybrid')
        dizeli = v.validate_motor_data_detailed(
            dict(govde, oxidizer_temp='293.15'), 'hybrid')
        sayili = v.validate_motor_data_detailed(
            dict(govde, oxidizer_temp=293.15), 'hybrid')
    assert temiz[0] is True, f'geçerli gövde reddedildi: {temiz[1]}'
    assert sayili[0] is True, f'sayı reddedildi: {sayili[1]}'
    assert dizeli[0] is False, 'sayı-benzeri dize hâlâ kabul ediliyor'
    assert any('oxidizer_temp must be numeric' in m for m in dizeli[1]), \
        dizeli[1]


# ===========================================================================
# P12bB1-12 — bandı olmayan alan: kapı VAR, bant UYDURULMAZ
# ===========================================================================

_BANDSIZ_BES = ('stoichiometric_of', 'initial_mass', 'final_mass',
                'drag_coefficient', 'reference_area')


@pytest.mark.parametrize('alan', _BANDSIZ_BES)
def test_p12bb1_12_bant_yok_beyani(alan):
    """Bant yoksa künye "band yok" DER; sayı uydurmaz (Doktrin 4 + 6)."""
    from hrma.validation.motor_validation import accepted_range_kunyesi
    k = accepted_range_kunyesi(alan)
    assert k['band_yok'] is True
    assert k['accepted_range'] is None, f'{alan}: bant UYDURULMUŞ: {k}'
    assert k['basis'] == 'physical_only'
    assert 'finite' in k['limits'] and '> 0' in k['limits']
    assert k['reason'], 'kısıtın gerekçesi yazılmamış'


def test_p12bb1_12_traj_burn_time_kanonik_banda_baglidir():
    """Altı alanın YALNIZ beşi bandsız: ``burn_time``ın kanonik bandı var."""
    from hrma.validation.motor_validation import (
        accepted_range_kunyesi, CANONICAL_LIMITS, NUMERIC_ONLY_FIELDS)
    k = accepted_range_kunyesi('burn_time')
    assert k['band_yok'] is False and k['basis'] == 'canonical_band'
    assert k['accepted_range'] == [CANONICAL_LIMITS['burn_time']['min'],
                                   CANONICAL_LIMITS['burn_time']['max']]
    assert 'burn_time' not in NUMERIC_ONLY_FIELDS, (
        'kanonik bandı olan alan "bant yok" diye yazılmış')


def test_p12bb1_12_kunye_bandi_KOPYALAMAZ_tek_kaynaktan_okur():
    """Künye sayıyı kendi tutmaz: kaynak tablolar değişince künye değişir."""
    from hrma.validation import motor_validation as mv
    for alan in ('chamber_pressure', 'thrust', 'of_ratio'):
        k = mv.accepted_range_kunyesi(alan)
        band = mv.CANONICAL_LIMITS[alan]
        assert k['accepted_range'] == [band['min'], band['max']]
    k = mv.accepted_range_kunyesi('chamber_pressure', form='solid')
    assert k['basis'] == 'form_band'
    assert k['accepted_range'] == list(
        mv.FORM_LIMITS['solid']['chamber_pressure'][:2])


@pytest.mark.parametrize('deger,sebep', [(-2.0, 'not_positive'),
                                         (0.0, 'not_positive'),
                                         (float('nan'), 'not_finite')])
def test_p12bb1_12_fiziksel_kapi_uygulanir(deger, sebep):
    """Bant yok ama FİZİK var: sonsuz/negatif/sıfır alan geçemez."""
    from hrma.validation.motor_validation import _bandsiz_sayisal_sorun
    mesaj, kayit = _bandsiz_sayisal_sorun('reference_area', deger)
    assert mesaj is not None, f'{deger} sessizce geçti'
    assert kayit['reason'] == sebep
    assert kayit['accepted_range'] is None and kayit['band_yok'] is True
    # mesaj BİÇİMİ mevcut i18n süzgeciyle eşleşmeli (yeni çeviri borcu YOK)
    assert re.match(r'^(.+) = (.+) is outside valid range \[(.+)\] (.*)$',
                    mesaj), mesaj


def test_p12bb1_12_gecerli_deger_gecer():
    from hrma.validation.motor_validation import _bandsiz_sayisal_sorun
    assert _bandsiz_sayisal_sorun('reference_area', 0.05) == (None, None)
    assert _bandsiz_sayisal_sorun('bilinmeyen_alan', -1.0) == (None, None)


# ===========================================================================
# P10B1-05 — ölü yol PAKET yüzeyinden çıktı
# ===========================================================================

def test_p10b1_05_olu_yol_paket_yuzeyinde_degil():
    """``hrma.utils.of_optimizer.find_optimum_hybrid`` artık ERİŞİLEMEZ.

    ÖLÇÜLDÜ (``once.json`` -> ``P10B1-05``): ürün çağrısı 0, bekçi çağrısı
    14; buna rağmen paket yüzeyinden herkese açıktı.

    Ana model (14 Eyl 2026, fix-29 birleşmesi sonrası): paket yüzeyi TEMİZ bir
    yorumlayıcıda ölçülür (alt süreç). Aynı süreçte başka bir test
    ``hrma.data.external_data_fetcher``'ı önce yüklerse ``hrma.utils`` ile
    dairesel içe aktarma ``IMPORT_ERRORS``'a düşüyor (tabanda da var) — o kusur
    bu iddianın değil, aşağıdaki borç iminin konusudur (OH-D30 dairesel içe
    aktarma kalemi).
    """
    import json as _json
    import subprocess as _sp
    import sys as _sys
    # ÖH D32 / OH-D31-06 — ``_load_exports()`` ÇAĞRISI EKLENDİ.
    # Paket yüzeyi artık GECİKMELİ çözülüyor (PEP 562 ``__getattr__``):
    # ``import hrma.utils`` tek başına hiçbir adı denemez, dolayısıyla
    # ``IMPORT_ERRORS`` boş olur ve bu iddia ÖLÇMEDEN geçerdi (sahte
    # yeşil). Çağrı yüzeyin TAMAMINI çözdürür; iddia yine CANLI yolu
    # ölçer. (D31 dersi 23: bekçi ölü kopyayı değil canlı yolu ölçer.)
    betik = (
        "import json, hrma.utils as hu; hu._load_exports(); "
        "print(json.dumps({'yuzey': [a for a in ('of_optimizer', 'OptimumOFRatioFinder') if hasattr(hu, a)], "
        "'hatalar': sorted(hu.IMPORT_ERRORS)}))"
    )
    cikti = _sp.run([_sys.executable, '-c', betik], capture_output=True, text=True,
                    timeout=120, cwd=str(KOK))
    assert cikti.returncode == 0, cikti.stderr[-800:]
    olcum = _json.loads(cikti.stdout.strip().splitlines()[-1])
    assert olcum['yuzey'] == [], (
        f"ölü tablo okuyucusu paket yüzeyine geri geldi: hrma.utils.{olcum['yuzey']}")
    assert olcum['hatalar'] == [], olcum['hatalar']


# ÖH D31 / app-api-dogrulama a1 — BORÇ İMİ ÖDENDİ (OH-D30-01).
# Buradaki ``@pytest.mark.xfail(strict=True)`` imi D30'da kusuru ADIYLA
# tutuyordu: ``hrma.data.external_data_fetcher`` önce yüklenen süreçte
# ``hrma.utils.injector_design -> external_data_fetcher`` dairesel içe
# aktarması ``InjectorDesign``ı ``IMPORT_ERRORS``a düşürüyordu. D31'de
# ``hrma/utils/injector_design.py``teki iki modül düzeyi içe aktarma işlev
# içine alındı (eski adlar PEP 562 modül ``__getattr__`` ile korunuyor), im
# XPASS'a döndü ve KALDIRILDI. Test artık düpedüz YEŞİL bir bekçidir:
# içe aktarmalar modül düzeyine geri konursa kırmızıya döner
# (ters-mutasyon kanıtı: ``mutasyon_ohd3001.json``).
def test_ohd30_dairesel_ice_aktarma_borcu():
    """Ters sırada yükleme ``hrma.utils.InjectorDesign``'ı kullanılamaz bırakmamalı."""
    import json as _json
    import subprocess as _sp
    import sys as _sys
    # ÖH D32 / OH-D31-06 — ``_load_exports()`` ÇAĞRISI EKLENDİ.
    # Paket yüzeyi artık GECİKMELİ çözülüyor (PEP 562 ``__getattr__``):
    # ``import hrma.utils`` tek başına hiçbir adı denemez, dolayısıyla
    # ``IMPORT_ERRORS`` boş olur ve bu iddia ÖLÇMEDEN geçerdi (sahte
    # yeşil). Çağrı yüzeyin TAMAMINI çözdürür; iddia yine CANLI yolu
    # ölçer. (D31 dersi 23: bekçi ölü kopyayı değil canlı yolu ölçer.)
    betik = (
        "import json, hrma.data.external_data_fetcher, hrma.utils as hu; "
        "hu._load_exports(); "
        "print(json.dumps(sorted(hu.IMPORT_ERRORS)))"
    )
    cikti = _sp.run([_sys.executable, '-c', betik], capture_output=True, text=True,
                    timeout=120, cwd=str(KOK))
    assert cikti.returncode == 0, cikti.stderr[-800:]
    assert _json.loads(cikti.stdout.strip().splitlines()[-1]) == []


def test_p10b1_05_modul_yolu_ve_urun_ucu_calisiyor():
    """Daralan yalnız PAKET yüzeyidir; modül ve ürün ucu bozulmaz."""
    from hrma.utils.optimum_of_ratio import of_optimizer
    with contextlib.redirect_stdout(io.StringIO()):
        oneri = of_optimizer.get_recommendation('hybrid', 'n2o', 'htpb')
    assert oneri
    assert 'from hrma.utils.optimum_of_ratio import of_optimizer' in \
        _oku('hrma/app.py'), 'ürün ucu paket özniteliğine kaymış'


# ===========================================================================
# P15B2-01 — kalan 45 tanımın ADLI dağıtımı
# ===========================================================================

def test_p15b2_01_dagitim_dosyasi_envanteri_tasiyor():
    """Kalan borç ADIYLA dağıtıldı: id / dosya / kulvar / odendi."""
    yol = 'docs/scofield/raw/OH/D30/ana_model/p15b201_dagitim.json'
    veri = json.loads(_oku(kanit_gerekli(yol)))
    dagitim = veri['dagitim']
    assert len(dagitim) >= 45, f'envanter küçülmüş: {len(dagitim)}'
    for kayit in dagitim:
        assert set(('id', 'dosya', 'kulvar', 'odendi')) <= set(kayit)
        assert '::' in kayit['id']
        assert os.path.exists(os.path.join(KOK, kayit['dosya'])), kayit
    # sahibi belirsiz kalan kalemler GEREKÇELİ olmalı (sessiz '?' yok)
    for kayit in dagitim:
        if kayit['kulvar'] == '?':
            assert kayit.get('gerekce'), f'gerekçesiz "?" kalem: {kayit["id"]}'


def test_p15b2_01_kendi_saham_merkeze_bagli():
    """Kulvarın kendi sahasında merkeze BAĞSIZ değer kapısı kalmadı."""
    veri = json.loads(_oku(
        kanit_gerekli('docs/scofield/raw/OH/D30/ana_model/p15b201_dagitim.json')))
    acik = [k['id'] for k in veri['dagitim']
            if k['kulvar'] == 'app-api-dogrulama' and k['durum'] == 'acik']
    assert acik == [], f'kendi sahamda ödenmemiş kapı: {acik}'
