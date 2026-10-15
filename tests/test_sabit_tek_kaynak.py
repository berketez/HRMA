"""Sabitlerin ve alan sözlüklerinin tek-tanım-noktası bekçisi (v2.6.27).

BULGU (15 Ağustos 2026, mimari tarama): Stefan-Boltzmann sabiti 6 ayrı
dosyada ayrı ayrı tanımlıydı (thermal_protection, heat_transfer_analysis,
solid_rocket_engine SOLID_THERMAL, safety_analysis, structural_analysis,
fea/thermal_axisym). Değerler aynıydı — yani kusur değil, kural ihlaliydi:
parametre tutarlılığı kuralı "bir kavram, bir tanım noktası" der; altı kopya,
birinin sessizce farklılaşmasına açık kapıdır.

Bu dosya iki şeyi kilitler: (1) depoda merkez dışında literal tanım yok,
(2) tüketicilerin gördüğü değer merkezle bire bir aynı.
"""

import ast
import re
import subprocess
from pathlib import Path

from hrma.constants import MOTOR_TYPES as _MERKEZ_MOTOR_TYPES

ROOT = Path(__file__).resolve().parents[1]


def test_stefan_boltzmann_tek_tanim_noktasi():
    """Literal 5.670374419e-8 yalnız hrma/constants.py'de yazılabilir.

    Yeni bir dosyaya yerel kopya eklenirse bu test kırılır; doğru hamle
    `from hrma.constants import STEFAN_BOLTZMANN` satırıdır.
    """
    sonuc = subprocess.run(
        ['git', 'grep', '-l', '5.670374419e-8', '--', 'hrma/*.py',
         'hrma/**/*.py'],
        cwd=ROOT, capture_output=True, text=True)
    dosyalar = [s for s in sonuc.stdout.splitlines() if s.strip()]
    assert dosyalar == ['hrma/constants.py'], (
        'Stefan-Boltzmann literali merkez dışında da tanımlı: %s — yerel '
        'kopya yasak, hrma.constants.STEFAN_BOLTZMANN import edilmeli.'
        % dosyalar)


def test_tuketiciler_merkezle_ayni_nesne():
    """Altı eski tanım yerinin tamamı merkez değeri görmeli."""
    from hrma.constants import STEFAN_BOLTZMANN as merkez
    import hrma.analysis.thermal_protection as tp
    import hrma.analysis.safety_analysis as sa
    import hrma.analysis.heat_transfer_analysis as ht
    import hrma.analysis.structural_analysis as st  # import hatasını yakalar
    import hrma.fea.thermal_axisym as fea
    import hrma.engines.solid_rocket_engine as se

    assert merkez == 5.670374419e-8  # CODATA 2018 — değer de kilitli
    assert tp.STEFAN_BOLTZMANN is merkez
    assert sa.SAFETY_MODEL['stefan_boltzmann'] is merkez
    assert ht.HeatTransferAnalyzer().stefan_boltzmann is merkez
    assert fea.STEFAN_BOLTZMANN_W_M2K4 is merkez
    assert se.SOLID_THERMAL['stefan_boltzmann'] is merkez


# ===========================================================================
# TABLO/BANT SABİTLERİ — adıyla sınanır (ÖH D30 fix-29a)
# ===========================================================================
# Bu üç bekçi, ``test_d20_altyapi_a1::test_TUM_sabitler_bekci_kapsaminda``
# içinde ELLE YAZILI bir muafiyet kümesi olarak duran adları GERÇEK iddiaya
# bağlar. Eski hâlinde o küme kendi kendini onaylıyordu: adı listede geçen
# sabit "bekçiye tanıtılmış" sayılıyordu, oysa hakkında tek bir iddia
# yoktu (OH-D25-01(c)'nin kapattığı yanılsamanın gövde-içi biçimi).

def test_isa_tablosu_turetilen_sabitlerle_AYRISMIYOR():
    """ISA katman tablosu ile ondan okunan/yanı sıra yazılan sabitler."""
    from hrma.constants import (H_TROPOPAUSE, ISA_LAYERS, ISA_TABLE_BOTTOM_M,
                                ISA_TABLE_TOP_M, P_SEA_LEVEL_PA,
                                P_TROPOPAUSE, T_TROPOPAUSE)
    # Deniz seviyesi basıncı tablodan OKUNUR (ikinci kez yazılmaz).
    assert P_SEA_LEVEL_PA is ISA_LAYERS[0][3]
    # Tropopoz üçlüsü ayrı ayrı yazılıdır; tabloyla AYRIŞAMAZ.
    h, t, lapse, pa = ISA_LAYERS[1]
    assert (h, t, pa) == (H_TROPOPAUSE, T_TROPOPAUSE, P_TROPOPAUSE), (
        'tropopoz sabitleri ISA tablosunun 2. satırından ayrışmış: '
        'tablo %r, sabitler %r'
        % ((h, t, pa), (H_TROPOPAUSE, T_TROPOPAUSE, P_TROPOPAUSE)))
    assert lapse == 0.0, 'tropopoz katmanı izotermal olmalı'
    # Tablo sınırları tabloyu KAPSAR (fail-closed: dışı ekstrapolasyon).
    assert ISA_TABLE_BOTTOM_M < ISA_LAYERS[0][0]
    assert ISA_TABLE_TOP_M > ISA_LAYERS[-1][0]
    yukseklikler = [k[0] for k in ISA_LAYERS]
    assert yukseklikler == sorted(yukseklikler), 'katmanlar artan değil'


def test_c_star_bantlari_tek_kaynak_ve_TUTARLI():
    """c* bandı sözlüğü ve bilinmeyen oksitleyici yedeği."""
    from hrma.constants import (C_STAR_BAND_DEFAULT_MPS,
                                C_STAR_PLAUSIBLE_BAND_MPS)
    import hrma.engines.hybrid_rocket_engine as hre

    assert hre.C_STAR_PLAUSIBLE_BAND_MPS is C_STAR_PLAUSIBLE_BAND_MPS
    assert hre.C_STAR_BAND_DEFAULT_MPS is C_STAR_BAND_DEFAULT_MPS
    bantlar = dict(C_STAR_PLAUSIBLE_BAND_MPS)
    bantlar['(bilinmeyen)'] = C_STAR_BAND_DEFAULT_MPS
    for ad, bant in bantlar.items():
        assert isinstance(bant, tuple) and len(bant) == 2, (ad, bant)
        alt, ust = bant
        assert 0 < alt < ust, '%s bandı artan değil: %r' % (ad, bant)
    # Anahtarlar küçük harf: engine ``str(ox).lower()`` ile arıyor.
    assert all(a == a.lower() for a in C_STAR_PLAUSIBLE_BAND_MPS)


def test_l_star_bandi_kunyesiyle_AYNI_araligi_soyluyor():
    """Genel L* bandı, varsayılanı ve künyesi birbirini tutuyor mu?"""
    from hrma.constants import (L_STAR_DEFAULT_M, L_STAR_GENERIC_BAND_M,
                                L_STAR_GENERIC_BAND_SOURCE)
    alt, ust = L_STAR_GENERIC_BAND_M
    assert alt < L_STAR_DEFAULT_M < ust, (
        'varsayılan L* genel bandın dışında: %s / %r'
        % (L_STAR_DEFAULT_M, L_STAR_GENERIC_BAND_M))
    # Künye süs değil: andığı metre aralığı bandın TA KENDİSİ olmalı.
    metreler = re.search(r'\((\d+\.\d+)-(\d+\.\d+)\s*m\)',
                         L_STAR_GENERIC_BAND_SOURCE)
    assert metreler, (
        'künye metre aralığını anmıyor: %r' % L_STAR_GENERIC_BAND_SOURCE)
    assert (float(metreler.group(1)), float(metreler.group(2))) == (alt, ust), (
        'künyedeki aralık bantla ayrışmış: künye %s, bant %r'
        % (metreler.groups(), L_STAR_GENERIC_BAND_M))


def test_orifis_cap_bandi_kunyesiyle_AYNI_araligi_soyluyor():
    """Enjektör orifis çapı bandı, künyesi ve tüketicisi birbirini tutuyor mu?

    ÖH D37 A2 hibrit · F-10 (= CW-A5). Bu bekçi ``tests/test_d37_hibrit_f1.py``
    T2'den buraya TAŞINDI (denetçi-3 Ş-1, ana model kararı (ii), 29 Eyl):
    ``tools/sabit_envanteri.BEKCI_DOSYALARI`` yalnız bu dosyayı ve
    ``test_d20_altyapi_a1.py``yi tarar; kulvar dosyasını listeye eklemek
    (T7 yaması, geri alındı) ``test_d27_altyapi_a1::
    test_kapsam_sayilari_OLCUMLE_uyusuyor`` çapasını kırıyordu — o test
    listedeki her dosyayı D27 taban ağacından (709a235e) ``git show`` ile
    okur ve kulvar dosyası orada yoktur. Adlar burada bir test GÖVDESİNDE
    sınanır; kapsam aracı onları görür, liste değişmez.
    """
    from hrma.constants import ORIFICE_D_BAND_MM, ORIFICE_D_BAND_SOURCE
    import hrma.engines.injector_design as eid
    assert isinstance(ORIFICE_D_BAND_MM, tuple) and len(ORIFICE_D_BAND_MM) == 2
    alt, ust = ORIFICE_D_BAND_MM
    assert 0 < alt < ust, 'orifis bandı artan değil: %r' % (ORIFICE_D_BAND_MM,)
    # Künye süs değil: andığı milimetre aralığı bandın TA KENDİSİ olmalı.
    mm = re.search(r'\((\d+\.\d+)-(\d+\.\d+)\s*mm\)', ORIFICE_D_BAND_SOURCE)
    assert mm, 'künye mm aralığını anmıyor: %r' % ORIFICE_D_BAND_SOURCE
    assert (float(mm.group(1)), float(mm.group(2))) == (alt, ust), (
        'künyedeki aralık bantla ayrışmış: künye %s, bant %r'
        % (mm.groups(), ORIFICE_D_BAND_MM))
    # İki bağımsız kitap, adıyla ve sayfasıyla (Sutton & Biblarz 9. bs.
    # §8.9 s. 337; Mishra 2017 Böl. 10 s. 348 — birincil metinden okundu).
    assert 'Sutton' in ORIFICE_D_BAND_SOURCE and 'p. 337' in ORIFICE_D_BAND_SOURCE
    assert 'Mishra' in ORIFICE_D_BAND_SOURCE and 'p. 348' in ORIFICE_D_BAND_SOURCE
    # Tüketici merkezin AYNI nesnesini görür (kopya değil KİMLİK).
    assert eid.ORIFICE_D_PREF_MM is ORIFICE_D_BAND_MM
    assert eid.DEFAULT_CONSTRAINTS['d_min_mm'] is ORIFICE_D_BAND_MM[0]
    assert eid.DEFAULT_CONSTRAINTS['d_max_mm'] is ORIFICE_D_BAND_MM[1]


# ===========================================================================
# ORTAM SICAKLIĞI ZARFI — bant ve KÜNYESİ (ÖH D29 P16B1-44, bekçi D30 fix-29a)
# ===========================================================================

def test_ortam_sicakligi_bandi_tek_tanim_noktasi():
    """Bandı okuyan iki yer de merkezin AYNI nesnesini görür.

    Bant D29'da merkeze alındı ama hiçbir bekçi onu ADIYLA sınamıyordu:
    ``sabit_envanteri.bekci_kapsami`` iki adı da "bekçisiz merkezî sabit"
    diye raporluyordu (ölçüldü, taban ab7cf68b). Kopya değil KİMLİK
    sınanır — sayı ikinci kez yazılırsa ``is`` kırılır.
    """
    from hrma.constants import AMBIENT_TEMPERATURE_BAND_K
    from hrma.validation.motor_validation import CANONICAL_LIMITS
    import hrma.engines.hybrid_rocket_engine as hre

    band = CANONICAL_LIMITS['ambient_temperature']
    assert band['min'] is AMBIENT_TEMPERATURE_BAND_K[0]
    assert band['max'] is AMBIENT_TEMPERATURE_BAND_K[1]
    assert band['unit'] == 'K'
    # Motor zarfı da aynı demeti ithal eder (ikinci literal yok).
    assert hre.AMBIENT_TEMPERATURE_BAND_K is AMBIENT_TEMPERATURE_BAND_K
    assert AMBIENT_TEMPERATURE_BAND_K[0] < AMBIENT_TEMPERATURE_BAND_K[1]


def test_ortam_sicakligi_kunyesi_bandi_GERCEKTEN_kapsiyor():
    """``AMBIENT_TEMPERATURE_BAND_SOURCE`` süs değil, yük taşır.

    Künyenin gerekçesi "WMO onaylı uçların cömert üst kümesi"dir. Bu
    iddia ÖLÇÜLEBİLİR: künyede ADI GEÇEN kelvin değerlerinin tamamı
    bandın İÇİNDE olmalı. Bant daraltılır ya da künye başka bir kaynağa
    çevrilirse ikisi ayrışır ve bu test kırmızı yanar — yani künye
    bayatlayamaz.
    """
    from hrma.constants import (AMBIENT_TEMPERATURE_BAND_K,
                                AMBIENT_TEMPERATURE_BAND_SOURCE)
    alt, ust = AMBIENT_TEMPERATURE_BAND_K
    kunye = AMBIENT_TEMPERATURE_BAND_SOURCE
    assert isinstance(kunye, str) and len(kunye) >= 40
    kelvinler = [float(x) for x in
                 re.findall(r'(\d+(?:\.\d+)?)\s*K\b', kunye)]
    assert len(kelvinler) >= 2, (
        'künye hiçbir kelvin ucu anmıyor: %r' % kunye)
    disarida = [k for k in kelvinler if not alt <= k <= ust]
    assert not disarida, (
        'künyenin andığı uç bandın DIŞINDA (%s), yani bant künyesinin '
        'söylediği zarfı kapsamıyor: bant (%s, %s)'
        % (disarida, alt, ust))


def test_ortam_sicakligi_kunyesi_urun_tablosunda_ANILIYOR():
    """Künye, belgelediği tablonun yanında ADIYLA duruyor mu?

    ``test_d20_altyapi_a1::test_olu_merkezi_sabit_listesi_BUYUMEZ``in
    künye eşlikçisi muafiyeti tam olarak bu bağa dayanır; bağ koparsa
    muafiyet anonimleşir.
    """
    metin = (ROOT / 'hrma' / 'validation'
             / 'motor_validation.py').read_text(encoding='utf-8')
    assert 'AMBIENT_TEMPERATURE_BAND_SOURCE' in metin, (
        'bandı taşıyan ürün tablosu künyeye adıyla atıf yapmıyor')


# ===========================================================================
# MOTOR_TYPES — alan sözlüğünün tek-tanım-noktası (v2.6.27, otuz ikinci parti)
# ===========================================================================
#
# BULGU (defter): ('hybrid','solid','liquid') üçlüsü üç dosyada ayrı ayrı
# TANIMLIYDI — hrma/utils/projects.py (frozenset), hrma/validation/
# experiment_db.py (demet, __all__ ile yayımlanıyor), tests/
# test_panel_units_v2626.py (demet). Değerler aynıydı; kusur, dördüncü bir
# motor türü eklendiğinde üç yerin ikisinin güncellenip birinin unutulmasına
# açık olmasıydı. Tek kaynak hrma/constants.py'dedir ve SIRALI demettir
# (experiment_db klasörleri bu sırayla gezer).

#: Aranan üyelik MERKEZDEN okunur — bu dosya kendi literal kopyasını yazarsa
#: kendi bekçisine takılır (ölçüldü: yazdım, test kırmızı oldu). Değerin ve
#: sıranın kilidi ayrı testtedir; merkez bir gün genişlerse tarayıcının hedefi
#: onunla birlikte kayar ve ikiz kümesi YENİDEN ÖLÇÜLMEK zorundadır.
_MOTOR_TYPE_SET = set(_MERKEZ_MOTOR_TYPES)

#: Tek kaynağın kendisi (tanım burada OLMALI).
_KAYNAK = ('hrma/constants.py', 'MOTOR_TYPES')

#: BUGÜN ÖLÇÜLEN ikizler — İKİ YÖNLÜ EŞİK (KAPISIZ_BILINEN deseni,
#: tests/test_stability_hibrit_chug.py:388). Bu küme BÜYÜYEMEZ (yeni yerel
#: tanım = kırmızı) ve satır SİLİNMEDEN ikiz kapatılamaz (kapatıldıysa satır
#: da silinmeli, yoksa test kırmızı). Hiçbiri "meşru" damgası DEĞİLDİR:
#: dördü de aynı sınıf borçtur, yalnızca bu partinin dosya kapsamı dışında
#: kaldıkları için duruyorlar.
_MOTOR_TYPE_IKIZLERI = {
    # Belirsizlik (UQ) ucunun kendi özel kopyası; ad özel (_UQ_ öneki), değer
    # aynı. app.py bu partide yalnız ambient_temp bölgesi için açıktı.
    ('hrma/app.py', '_UQ_MOTOR_TYPES'),
    # Uçuş aracı çözücüsünün özel kopyası (motor_type doğrulaması).
    ('hrma/analysis/flight_vehicle.py', '_MOTOR_TYPES'),
    # AYNI ÜYELİK, BAŞKA SIRA ve başka ad: FEA köprüsünün 'motor yerleşimi'
    # kavramı. Kavram adı farklı olduğu için birebir aynı sözlük müdür yoksa
    # ayrı bir alan sözlüğü müdür — ÖLÇÜLMEDİ, uydurma gerekçe yazılmıyor.
    ('hrma/fea/bridge.py', 'ENGINE_LAYOUTS'),
    # ÖH D21 / altyapi — İKİZ KAPANDI. Tarayıcı turunun gezinme sırası artık
    # üçlüyü literal olarak yazmıyor: `HESAPLI_SIRA` sayfa tanımlarından
    # türetiliyor (`hesap_var` olanlar) ve `VARSAYILAN_SIRA` ona üç statik
    # sayfa ekliyor — yani ikisi de motor türü üçlüsünün kopyası değil.
}


def _literal_kume(node):
    """Düğüm bir dizi/küme literali ise eleman kümesini, değilse None."""
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        elemanlar = node.elts
    elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
          and node.func.id in ('frozenset', 'set', 'tuple', 'list')
          and len(node.args) == 1):
        return _literal_kume(node.args[0])
    else:
        return None
    degerler = [e.value for e in elemanlar
                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    if not degerler or len(degerler) != len(elemanlar):
        return None
    return set(degerler)


def _adlandirilmis_tanimlar():
    """(dosya, ad) -> motor türü üçlüsünü LİTERAL olarak tanımlayan atamalar.

    Satır içi kullanımlar (``for mt in ('hybrid','solid','liquid')``,
    parametrize listeleri) BİLEREK kapsam dışıdır: onlar bir kavramın tanım
    noktası değil, tek seferlik ölçüm kümeleridir (depoda 20+ tane var ve
    hepsini dondurmak bekçiyi gürültüye boğardı). Bu bekçi ADLANDIRILMIŞ
    tanımı — yani ileride "tek kaynak" gibi kullanılabilecek olanı — yakalar.
    """
    bulunan = set()
    for desen in ('hrma/**/*.py', 'tests/**/*.py', 'tools/**/*.py'):
        for yol in sorted(ROOT.glob(desen)):
            try:
                agac = ast.parse(yol.read_text(encoding='utf-8'))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for dugum in ast.walk(agac):
                if isinstance(dugum, ast.Assign):
                    hedefler = dugum.targets
                elif isinstance(dugum, ast.AnnAssign):
                    hedefler = [dugum.target]
                else:
                    continue
                if dugum.value is None:
                    continue
                if _literal_kume(dugum.value) != _MOTOR_TYPE_SET:
                    continue
                for hedef in hedefler:
                    if isinstance(hedef, ast.Name):
                        bulunan.add(
                            (yol.relative_to(ROOT).as_posix(), hedef.id))
    return bulunan


def test_motor_types_tek_tanim_noktasi():
    """Üçlünün adlandırılmış tanımı yalnız hrma/constants.py'de olabilir."""
    bulunan = _adlandirilmis_tanimlar()
    assert _KAYNAK in bulunan, (
        'Tek kaynak kayboldu: %s içinde MOTOR_TYPES literali yok. Tarayıcı '
        'körelmiş olabilir (negatif kontrol).' % (_KAYNAK[0],))
    ikizler = bulunan - {_KAYNAK}
    assert ikizler == _MOTOR_TYPE_IKIZLERI, (
        'Motor türü ikiz kümesi değişti.\n  YENİ yerel tanım: %s — '
        'hrma.constants.MOTOR_TYPES import edilmeli.\n  KAPANAN ikiz: %s — '
        '_MOTOR_TYPE_IKIZLERI satırını silin.'
        % (sorted(ikizler - _MOTOR_TYPE_IKIZLERI),
           sorted(_MOTOR_TYPE_IKIZLERI - ikizler)))


def test_motor_types_tuketiciler_merkezle_ayni_nesne():
    """Üç eski tanım yeri de merkezin NESNESİNİ görmeli (kimlik denetimi)."""
    from hrma.constants import MOTOR_TYPES, MOTOR_TYPE_SET
    from hrma.utils import projects
    from hrma.validation import experiment_db

    # Değer ve SIRA kilitli: experiment_db klasörleri bu sırayla gezer.
    assert MOTOR_TYPES == ('hybrid', 'solid', 'liquid')
    assert MOTOR_TYPE_SET == set(MOTOR_TYPES)
    # Küme biçimi TÜRETİLİR, ikinci bir literal değildir.
    assert experiment_db.MOTOR_TYPES is MOTOR_TYPES
    assert projects.MOTOR_TYPES is MOTOR_TYPE_SET
    # __all__ yayını korunmalı: dış tüketici eski yolundan okumaya devam eder.
    assert 'MOTOR_TYPES' in experiment_db.__all__


def test_panel_testi_uclu_kaynagi_import_ediyor():
    """tests/test_panel_units_v2626.py yerel kopya yerine import etmeli.

    Modülü içe aktarmak yerine AST ile import KAYNAĞI denetlenir: o test
    dosyası ağır (node köprüsü, örnek projeler) ve buradan yüklenmesi bu
    bekçiyi yavaşlatır — ayrıca ölçmek istediğimiz şey davranış değil,
    ithalatın hangi modülden yapıldığıdır.
    """
    yol = ROOT / 'tests/test_panel_units_v2626.py'
    agac = ast.parse(yol.read_text(encoding='utf-8'))
    kaynaklar = {
        dugum.module for dugum in ast.walk(agac)
        if isinstance(dugum, ast.ImportFrom)
        and any(ad.name == 'MOTOR_TYPES' and ad.asname is None
                for ad in dugum.names)}
    assert kaynaklar == {'hrma.constants'}, (
        'test_panel_units_v2626.py MOTOR_TYPES sabitini %s kaynağından '
        'alıyor; beklenen hrma.constants.' % (sorted(kaynaklar) or 'HİÇBİR'))
