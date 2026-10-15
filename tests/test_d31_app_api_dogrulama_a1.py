# -*- coding: utf-8 -*-
"""ÖH D31 / app-api-dogrulama a1 — onarım bekçileri.

Kalemler: P7B1-06 (ÖK-16 birim sözleşmesi tek kaynağa), OH-D30-01 (dairesel
içe aktarma hrma.utils ⟷ hrma.data.external_data_fetcher).

Her bekçi TERS MUTASYONLA sınandı (kanıt:
``docs/scofield/raw/OH/D31/app-api-dogrulama/a1/mutasyon.json``).
"""
import ast
import json
import os
import subprocess
import sys

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _oku(bagil):
    with open(os.path.join(KOK, bagil), encoding='utf-8') as f:
        return f.read()


def _alt_surec(betik, sure=240):
    """Süreç DURUMU ölçen bekçiler ALT SÜREÇTE koşar (D30 dersi 20).

    ``IMPORT_ERRORS`` ve modül yüzeyi, başka testlerin içe aktarma SIRASINA
    bağlıdır; aynı yorumlayıcıda ölçmek sahte yeşil/sahte kırmızı üretir.
    """
    ortam = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', HRMA_HEADLESS='1')
    c = subprocess.run([sys.executable, '-c', betik], capture_output=True,
                       text=True, timeout=sure, cwd=KOK, env=ortam)
    assert c.returncode == 0, c.stderr[-1200:]
    return json.loads(c.stdout.strip().splitlines()[-1])


# ===========================================================================
# P7B1-06 (ÖK-16) — birim çıkarım tavanı KANONDAN türer, elle yazılmaz
# ===========================================================================

def test_p7b106_cap_tavani_elle_yazili_degil():
    """``DIAMETER_SI_MAX_M`` bir SAYI LİTERALİNE atanmış olamaz.

    ÖLÇÜLDÜ (``once.json`` B4): tavan ``hrma/export/motor_geometry.py``
    içinde ``DIAMETER_SI_MAX_M = 1.0`` diye elle yazılıydı ve doğrulayıcının
    kanonik ``chamber_diameter`` bandının üst ucuyla (5,0 m) çelişiyordu —
    aynı fiziksel büyüklüğün İKİ zarfı (CLAUDE.md kural 11 / Doktrin 4).
    """
    agac = ast.parse(_oku('hrma/export/motor_geometry.py'))
    atamalar = [d for d in agac.body
                if isinstance(d, ast.Assign)
                and any(isinstance(h, ast.Name) and h.id == 'DIAMETER_SI_MAX_M'
                        for h in d.targets)]
    assert len(atamalar) == 1, f'tek atama beklenir, bulunan: {len(atamalar)}'
    deger = atamalar[0].value
    assert not isinstance(deger, ast.Constant), (
        'çap tavanı yeniden SAYIYLA yazılmış: '
        f'{getattr(deger, "value", None)!r} — kanondan türetilmeli '
        '(hrma.validation.motor_validation.DIAMETER_UNIT_INFERENCE_MAX_M)')
    assert isinstance(deger, ast.Name), ast.dump(deger)


def test_p7b106_tavan_kanonik_bantlarin_en_genisi():
    """Tavan = çap alanlarının kanonik üst uçlarının en büyüğü."""
    from hrma.validation.motor_validation import (
        CANONICAL_LIMITS, DIAMETER_CANONICAL_FIELDS,
        DIAMETER_UNIT_INFERENCE_MAX_M, canonical_band_m)
    import hrma.export.motor_geometry as MG

    beklenen = max(CANONICAL_LIMITS[a]['max'] for a in DIAMETER_CANONICAL_FIELDS)
    assert DIAMETER_UNIT_INFERENCE_MAX_M == beklenen
    assert MG.DIAMETER_SI_MAX_M == DIAMETER_UNIT_INFERENCE_MAX_M, (
        'dışa aktarım tavanı kanondan koptu: '
        f'{MG.DIAMETER_SI_MAX_M} != {DIAMETER_UNIT_INFERENCE_MAX_M}')
    # Kanon okuyucusu yalnız METRE bandı yayımlar (bar/K/N satırları hayır).
    assert canonical_band_m('chamber_diameter') == (
        CANONICAL_LIMITS['chamber_diameter']['min'],
        CANONICAL_LIMITS['chamber_diameter']['max'])
    assert canonical_band_m('chamber_pressure') is None
    assert canonical_band_m('boyle_bir_alan_yok') is None


def test_p7b106_kanon_ici_kasa_capi_milimetre_sayilmiyor():
    """CANLI kusur: bandı OLMAYAN çap alanı tek-eşikli yolda kalır.

    ÖLÇÜLDÜ (``once.json`` B2): ``case_outer_diameter = 1,5`` — kanonik
    ``chamber_diameter`` bandının ([0,01; 5,0] m) İÇİNDE, yani meşru bir
    kasa — ``0,0015 m`` olarak okunuyordu (1000 kat). ``.eng`` başlığının
    ikinci alanı imalata bu sayıyla gidiyordu.
    """
    import hrma.export.motor_geometry as MG
    from hrma.validation.motor_validation import canonical_band_m

    alt, ust = canonical_band_m('chamber_diameter')
    for girdi in (1.5, 2.5, 4.9):
        assert alt <= girdi <= ust, 'ölçüm girdisi kanon dışına kaymış'
        metre, kaynak = MG.length_in_meters(girdi, MG.DIAMETER_SI_MAX_M)
        assert (metre, kaynak) == (girdi, 'si'), (
            f'kanon içi kasa çapı {girdi} m yeniden yorumlandı: '
            f'{metre} ({kaynak})')
    # Kanon DIŞI değer hâlâ milimetre okunur — çıkarım kaldırılmadı.
    assert MG.length_in_meters(100.0, MG.DIAMETER_SI_MAX_M) == (0.1, 'mm')


def test_p7b106_bantli_alanlar_birlesim_kuralinda_kaldi():
    """Bandı OLAN alanlar tavandan etkilenmez (iki-okuma birleşimi sürer)."""
    import hrma.export.motor_geometry as MG
    ç = MG.length_in_meters_banded
    # chamber [0,01;5,0]: 1,5 m makul, 1,5 mm değil -> METRE
    assert ç(1.5, 'chamber_diameter', MG.DIAMETER_SI_MAX_M) == (1.5, 'si')
    # throat [0,001;2,0]: 1,5 m de 1,5 mm de makul -> KAZANILMADI
    assert ç(1.5, 'throat_diameter', MG.DIAMETER_SI_MAX_M) == (None, 'ambiguous')
    # port [0,005;1,0]: 1,5 m imkânsız, 1,5 mm de imkânsız -> BANT DIŞI
    assert ç(1.5, 'port_diameter_initial',
             MG.DIAMETER_SI_MAX_M) == (None, 'out_of_band')


# ===========================================================================
# OH-D30-01 — dairesel içe aktarma söküldü
# ===========================================================================

def test_ohd3001_modul_duzeyinde_dairesel_ice_aktarma_yok():
    """``hrma/utils/injector_design.py`` modül YÜKÜNDE halkayı kapatmamalı.

    Halka (ölçüldü, ``once.json`` bölüm A):
    ``external_data_fetcher -> tank_blowdown -> ... -> trajectory_analysis
    -> hrma.utils.numeric_compat -> hrma/utils/__init__ ->
    hrma.utils.injector_design -> external_data_fetcher (YARIM)``.
    """
    agac = ast.parse(_oku('hrma/utils/injector_design.py'))
    yasak = ('hrma.data.external_data_fetcher', 'hrma.analysis.tank_blowdown')
    bulunan = []
    for dugum in agac.body:                      # YALNIZ modül düzeyi
        if isinstance(dugum, ast.ImportFrom) and dugum.module in yasak:
            bulunan.append(dugum.module)
        elif isinstance(dugum, ast.Import):
            bulunan += [a.name for a in dugum.names if a.name in yasak]
    assert bulunan == [], (
        f'dairesel halka modül düzeyine geri kondu: {bulunan}')


def test_ohd3001_ters_sirada_paket_yuzeyi_saglam():
    """``external_data_fetcher`` ÖNCE yüklense de ``hrma.utils`` tam olmalı."""
    # ÖH D32 / OH-D31-06 — ``_load_exports()`` ÇAĞRISI EKLENDİ.
    # Paket yüzeyi artık GECİKMELİ çözülüyor (PEP 562 ``__getattr__``):
    # ``import hrma.utils`` tek başına hiçbir adı denemez, dolayısıyla
    # ``IMPORT_ERRORS`` boş olur ve bu iddia ÖLÇMEDEN geçerdi (sahte
    # yeşil). Çağrı yüzeyin TAMAMINI çözdürür; iddia yine CANLI yolu
    # ölçer. (D31 dersi 23: bekçi ölü kopyayı değil canlı yolu ölçer.)
    olcum = _alt_surec(
        "import json, hrma.data.external_data_fetcher, hrma.utils as hu; "
        "hu._load_exports(); "
        "print(json.dumps(sorted(hu.IMPORT_ERRORS)))")
    assert olcum == [], f'ters sırada yükleme yüzeyi kırdı: {olcum}'


def test_ohd3001_ters_sirada_urun_yolu_calisiyor():
    """Ürün yolu: ters sırada ``InjectorDesign`` örneği KURULABİLMELİ.

    ÖLÇÜLDÜ (``once.json`` ``urun_yolu_ters_sira``): önce
    ``ImportError: hrma.utils.InjectorDesign is unavailable ...``.
    """
    olcum = _alt_surec(
        "import json, hrma.data.external_data_fetcher\n"
        "sonuc = {}\n"
        "try:\n"
        "    from hrma.utils import InjectorDesign\n"
        "    d = InjectorDesign(mdot_ox=0.5, chamber_pressure=20)\n"
        "    sonuc['ornek'] = 'kuruldu'\n"
        "    sonuc['p_vapor_bar'] = getattr(d, 'p_vapor_bar', None)\n"
        "except Exception as e:\n"
        "    sonuc['ornek'] = f'{type(e).__name__}: {e}'[:300]\n"
        "print(json.dumps(sonuc))\n")
    assert olcum['ornek'] == 'kuruldu', olcum['ornek']
    assert olcum['p_vapor_bar'] is not None, 'doyma tablosu gecikmeli kuruluma takıldı'


def test_ohd3001_eski_adlar_bozulmadi():
    """Gecikmeli çözüm ESKİ ``from ... import`` kullanımlarını kırmamalı."""
    from hrma.utils.injector_design import (
        LOCAL_DENSITY_FALLBACK, OxidizerStateError, OXIDIZER_STATE_TOLERANCE,
        N2OSaturation, data_fetcher, oxidizer_reference_density)
    import hrma.utils.injector_design as ui

    assert LOCAL_DENSITY_FALLBACK == pytest.approx(
        oxidizer_reference_density('n2o')['density'])
    assert issubclass(OxidizerStateError, Exception)
    assert float(OXIDIZER_STATE_TOLERANCE) > 0
    assert data_fetcher is not None
    # Paylaşılan doyma örneği TEK kalır (eski modül düzeyi örnekle aynı).
    assert ui._SAT_N2O is ui._SAT_N2O
    assert isinstance(ui._SAT_N2O, N2OSaturation)
    with pytest.raises(AttributeError):
        ui.boyle_bir_ad_yok
