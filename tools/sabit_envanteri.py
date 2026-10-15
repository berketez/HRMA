#!/usr/bin/env python3
"""KAYNAK seviyesi sabit envanteri — merkezî sabitlerin çıplak ikizlerini bulur.

Neden ayrı bir araç (P10B4-15). Depoda ``tools/sabit_tarayici.py`` var, ama o
ÇALIŞMA ZAMANI aracıdır: uca yük gönderip kıpırdamayan ÇIKTI yapraklarını
listeler. Kaynak metnindeki ``9.81`` ile ``hrma/constants.py``deki
``G_0 = 9.80665`` arasındaki çelişkiyi göremez, çünkü ikisi de çıktıyı
oynatır — kusur "sabit yaprak" değil "ikinci tanım"dır. Ölçüldüğünde
(``docs/scofield/raw/OH/D20/altyapi/a1/once.json``) depoda kaynak seviyesinde
sabit envanteri çıkaran HİÇBİR araç yoktu; ``hrma/constants.py``nin kendi
başlığında örnek diye verdiği çelişki (9.81 ⟷ 9.80665) ürünün ön yüzünde
canlıydı ve hiçbir bekçi onu görmüyordu.

İki kusur türü ayrılır:

``ikiz``
    Literal merkezî değerle BİT-AYNI. Sayı doğru, tek kaynak yok. Sessiz
    kusur: değer merkezde değişirse ikiz geride kalır.
``yakin_iska``
    Literal merkezî değere yakın ama AYNI DEĞİL (``9.81`` ⟷ ``9.80665``).
    Gürültülü kusur: iki farklı sayı aynı fiziksel sabiti temsil ediyor,
    yani ürün kendi içinde tutarsız.

KÖR BAND KAPALI — ``ast.Assign`` yetmez. Bir sabitin ikizi çoğu zaman
atama olarak değil hesabın ORTASINDA durur (``8314.462618 / mw``,
``f(g0=9.80665)``, ``x * 9.81``). Yalnız ``Assign`` düğümüne bakan bir
tarayıcı bu depoda çıplak kullanımların ezici çoğunluğunu KAÇIRIR; ölçüldü:
``Assign`` biçimli isabet 0, ``BinOp``/``keyword``/``Call`` biçimli isabet
onlarca. Bu yüzden burada TÜM ``ast.Constant`` düğümleri gezilir ve her
isabetin BİÇİMİ (ana düğüm sınıfı) künyeye yazılır.

Python dışı yüzey de taranır: ürünün ön yüzü (``.js``) sunucudan bağımsız
kendi sabitini taşıyabilir; ``app.js``teki itki/ağırlık oranı bunun canlı
örneğidir.

Kullanım:
    PYTHONPATH=. python3 tools/sabit_envanteri.py
    PYTHONPATH=. python3 tools/sabit_envanteri.py --json
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys

KOK = pathlib.Path(__file__).resolve().parents[1]

#: Merkezî sabit kaynağı — TEK tanım noktası. Değerler buraya KOPYALANMAZ,
#: dosyadan AST ile okunur (kopyalamak aracın kendisini ikinci tanım yapardı).
MERKEZ_SABIT_DOSYASI = 'hrma/constants.py'

#: Taranan ürün yüzeyi. ``tests/``, ``docs/``, ``tools/`` dışarıdadır: test
#: ve araç kodunun sabiti bilerek yazması meşrudur (bekçi karşılaştırma için
#: değeri elinde tutmak zorundadır).
TARANAN_KOKLER = ('hrma',)
PY_UZANTI = ('.py',)
JS_UZANTI = ('.js',)

#: Bu dizinler üretilmiş/dış kaynaklı: ikiz araması anlamsız.
ATLANAN_PARCALAR = ('/node_modules/', '/__pycache__/', '/static/lib/',
                    '/static/vendor/', '/.venv/', '/build/', '/dist/')

#: Yakın-ıska bandı. ``9.81`` ⟷ ``9.80665`` bağıl farkı 3,4e-4;
#: ``8314.5`` ⟷ ``8314.462618`` bağıl farkı 4,5e-6. Band bu iki ölçülmüş
#: vakayı kapsayacak, ilgisiz sayıları kapsamayacak biçimde seçildi.
YAKIN_ISKA_BANDI = 5e-3

#: MEŞRU isabetler — değeri merkezî bir sabite yakın ama AYNI FİZİKSEL
#: BÜYÜKLÜK OLMAYAN literaller. Boş bırakmak aracı gürültüye boğar, sessizce
#: elemek ise kör band açar; bu yüzden her muafiyet dosya+sabit+DEĞER üçlüsüyle
#: ve GEREKÇESİYLE yazılır (satır numarası kullanılmaz: kayar).
#: Muafiyet ancak ölçülmüş bir gerekçeyle eklenir — "gürültü" gerekçe değildir.
MESRU = (
    {'dosya': 'hrma/analysis/launch_site.py', 'sabit': 'G_0',
     'deger': 9.7803253359,
     'gerekce': 'WGS84_GAMMA_E — WGS-84 elipsoidinde EKVATORDAKİ normal '
                'yerçekimi (NIMA TR8350.2 Tablo 3.4). g₀ değil; Somigliana '
                'formülünün tanımlayıcı girdisi.'},
    {'dosya': 'hrma/analysis/launch_site.py', 'sabit': 'G_0',
     'deger': 9.8321849378,
     'gerekce': 'WGS84_GAMMA_P — WGS-84 elipsoidinde KUTUPTAKİ normal '
                'yerçekimi (NIMA TR8350.2 Tablo 3.4). g₀ değil.'},
    {'dosya': 'hrma/engines/liquid_rocket_engine.py', 'sabit': 'M_AIR',
     'deger': 0.0289,
     'gerekce': "``gamma_coeffs`` polinom katsayısı (üçüncü terim); boyutsuz. "
                "Havanın molar kütlesiyle (kg/mol) ilgisi yok, sayısal "
                "yakınlık rastlantı."},
    # ÖH D30 / fix-29a — ``ast.Pow`` kör bandı kapanınca PA_PER_PSI envantere
    # girdi ve bu isabet ilk kez göründü. İkisi de gerçek: aşağıdaki sayı bir
    # BASINÇ değil, ölçülmüş bir YİNELEME SAYISIdır.
    {'dosya': 'hrma/cfd/steady.py', 'sabit': 'PA_PER_PSI',
     'deger': 6897.0,
     'gerekce': '``IMPLICIT_CALIBRATION[\'muscl_explicit_iters\']`` — ÖH D26 '
                'fea-cfd a3 kalibrasyonunda ölçülen açık MUSCL yineleme '
                'sayısı (birimsiz sayaç, 2026-09-07 M4 Max koşumu). Basınç '
                'birimiyle ilgisi yok; 6894,757 Pa/psi ile 3,2e-4 bağıl '
                'yakınlık rastlantıdır ve sayı bir ÖLÇÜM sonucudur, '
                'merkezden okunamaz.'},
)


def _mesru_mu(dosya, sabit, deger):
    return any(m['dosya'] == dosya and m['sabit'] == sabit
               and m['deger'] == deger for m in MESRU)


def hayalet_muafiyet(sonuc: dict, kok: pathlib.Path | str = KOK) -> list:
    """HİÇBİR gerçek isabete uymayan muafiyet satırları.

    ÖH D26 / OH-D25-01(b). Muafiyet kapısı bugüne kadar yalnız gerekçenin
    UZUNLUĞUNU ölçüyordu (``len(gerekce) >= 40``); gerekçenin bir GERÇEĞE
    karşılık gelip gelmediği hiç sınanmıyordu. İki sessiz kaçış doğuyordu:

    1. Uydurma adres — var olmayan bir (dosya, sabit, değer) üçlüsüne
       muafiyet yazmak. Kimse görmez, envanter küçülmez ama tablo şişer ve
       bir sonraki okuyucu "burası ölçülmüş" sanır.
    2. Bayat muafiyet — kalem onarıldıktan (literal silindikten) sonra
       muafiyet satırı yerinde kalır. Aynı değer ileride BAŞKA bir bağlamda
       geri gelirse muafiyet onu da sessizce yutar: kör band, üstelik
       gerekçeli görünen bir kör band.

    Envanter mandalının (``KILITLI_ENVANTER``) ``<=`` karşılaştırması bunu
    yakalayamaz: muafiyet eklemek ihlali ``mesru_isabetler``e taşır, envanter
    KÜÇÜLÜR ve mandal yeşil kalır. Yani muafiyet, mandalın etrafından dolaşan
    bir kapıdır — bu işlev o kapıyı ölçülebilir kılar.

    Kapsam sınırı BEYAN EDİLİR: muafiyetin dosyası taranan ağaçta YOKSA satır
    hayalet sayılmaz — sentetik/kısmi bir ağaçta koşan araç, ilgisiz bir
    ağacın eksikliğini kusur diye raporlayamaz (yalancı kırmızı da bir kör
    banddır: susturulan bekçi hiçbir şey korumaz).
    """
    kok = pathlib.Path(kok).resolve()
    isabetler = {(i['dosya'], i['sabit'], i['deger'])
                 for i in sonuc['ihlaller'] + sonuc['mesru_isabetler']}
    return [m for m in MESRU
            if (kok / m['dosya']).is_file()
            and (m['dosya'], m['sabit'], m['deger']) not in isabetler]


#: ``bekci_kapsami`` hangi bekçi dosyalarına bakar — D20 ölçümünün baktığı
#: iki dosyanın AYNISI (kıyas anlamlı kalsın diye). Liste büyürse kapsam da
#: büyür; "bekçili" TANIMI değişmez.
BEKCI_DOSYALARI = ('tests/test_sabit_tek_kaynak.py',
                   'tests/test_d20_altyapi_a1.py')


def merkez_ad_listesi(kok: pathlib.Path | str = KOK) -> list:
    """``hrma/constants.py``de modül düzeyinde atanan TÜM adlar (AST).

    ``merkez_sabitleri`` yalnız SAYISAL sabitleri döner; kapsam sorusu ise
    tablo/demet sabitlerini de (``ISA_LAYERS``, ``MOTOR_TYPES``) kapsar.
    """
    kok = pathlib.Path(kok).resolve()
    src = (kok / MERKEZ_SABIT_DOSYASI).read_text(encoding='utf-8')
    adlar = []
    for dugum in ast.parse(src).body:
        if isinstance(dugum, ast.Assign):
            adlar += [t.id for t in dugum.targets if isinstance(t, ast.Name)]
        elif isinstance(dugum, ast.AnnAssign) and isinstance(dugum.target, ast.Name):
            adlar.append(dugum.target.id)
    return adlar


def _test_govdesi_adlari(kaynak: str) -> set:
    """Test GÖVDELERİNDE geçen adlar — dinamik iddia yüzeyi.

    Modül düzeyindeki veri literalleri (muafiyet/kilit listeleri) BİLEREK
    dışarıda bırakılır: bir ada muafiyet listesinde rastlamak, o adın
    sınandığı değil KAPSAM DIŞI İLAN EDİLDİĞİ anlamına gelir.
    """
    adlar = set()
    for dugum in ast.walk(ast.parse(kaynak)):
        if not isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for alt in ast.walk(dugum):
            if isinstance(alt, ast.Name):
                adlar.add(alt.id)
            elif isinstance(alt, ast.Attribute):
                adlar.add(alt.attr)
            elif isinstance(alt, ast.Constant) and isinstance(alt.value, str):
                adlar.update(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', alt.value))
    return adlar


def _modul_literal_dizgeleri(kaynak: str) -> set:
    """Modül düzeyi VERİ literallerindeki dizgeler (muafiyet/kilit listeleri)."""
    adlar = set()
    for d in ast.parse(kaynak).body:
        if not isinstance(d, (ast.Assign, ast.AnnAssign)):
            continue
        for alt in ast.walk(d):
            if isinstance(alt, ast.Constant) and isinstance(alt.value, str):
                adlar.add(alt.value)
    return adlar


def bekci_kapsami(kok: pathlib.Path | str = KOK) -> dict:
    """Merkezî sabitlerin bekçi kapsamı — AD GEÇİŞİ DEĞİL, İDDİA.

    ÖH D27 / OH-D25-01(c). D20 raporu "bekçili 3 → 22" diyor; o sayıyı
    üreten ölçüm (``docs/scofield/raw/OH/D20/altyapi/a1/olcum.py:75-79``)
    bir sabiti "bekçili" sayıyordu çünkü ADI iki bekçi dosyasının birinde
    ``\\bad\\b`` olarak geçiyordu — metnin NERESİNDE geçtiğine bakmadan.
    Muafiyet/kilit listesine yazılmış bir ad da böylece "bekçili" görünür;
    oysa o listeye girmek KAPSAM DIŞI İLAN EDİLMEKTİR, tam tersi.

    ÖLÇÜLDÜ (``docs/scofield/raw/OH/D27/altyapi/a1/once_metrik.json``,
    taban ağacı 709a235e): 30 adın sığ tanımla 23'ü "bekçili" görünüyor;
    bunların **7'si** (``H_TROPOPAUSE``, ``LAMBDA_CONICAL_15DEG``,
    ``LAMBDA_CONICAL_20DEG``, ``P_SEA_LEVEL_PA``, ``P_TROPOPAUSE``,
    ``R_STAR_ICAO``, ``T_TROPOPAUSE``) YALNIZ ``KILITLI_OLU_SABITLER``
    literalinde geçtiği için sayılıyor. Test gövdesinde adı geçen sabit
    sayısı 16; şişme 7.

    Sayı üç kümeye bölünür ve hiçbiri diğerinin yerine sayılmaz:

    ``govde``    adı bir test gövdesinde geçen sabitler (adıyla sınananlar),
    ``mandal``   aracın kapsam mandalındaki sabitler (ayırt edici tarama +
                 beyanlı ``belirsiz_deger``): adıyla anılmasa da her biri
                 dinamik bir KÜMEDE sınanır,
    ``bekcisiz`` ikisinde de olmayanlar — gerçek boşluk budur.

    ``yalniz_muafiyet_literalinde`` bir kapsam ölçüsü DEĞİLDİR; sığ tanımın
    şişme kaynağının adıdır.
    """
    kok = pathlib.Path(kok).resolve()
    ayirt, belirsiz = merkez_sabitleri(kok)
    adlar = merkez_ad_listesi(kok)
    govde, literal, sig = set(), set(), set()
    for bagil in BEKCI_DOSYALARI:
        yol = kok / bagil
        if not yol.is_file():
            continue
        kaynak = yol.read_text(encoding='utf-8')
        govde |= _test_govdesi_adlari(kaynak)
        literal |= _modul_literal_dizgeleri(kaynak)
        sig |= {ad for ad in adlar
                if re.search(r'\b%s\b' % re.escape(ad), kaynak)}
    mandal = set(ayirt) | set(belirsiz)
    govde_ad = {ad for ad in adlar if ad in govde}
    mandal_ad = {ad for ad in adlar if ad in mandal}
    return {
        'sabit_sayisi': len(adlar),
        'govde': sorted(govde_ad),
        'mandal': sorted(mandal_ad),
        'kapsam': sorted(govde_ad | mandal_ad),
        'bekcisiz': sorted(set(adlar) - govde_ad - mandal_ad),
        'sig_tanim': sorted(sig),
        'yalniz_muafiyet_literalinde': sorted(
            ad for ad in sig if ad not in govde_ad and ad in literal),
    }


#: Ayırt edicilik eşiği: anlamlı basamak sayısı. ``100000.0`` (PA_PER_BAR)
#: tek anlamlı basamaklıdır ve depoda yineleme sayısı/ölçek olarak da geçer;
#: onu "ikiz" saymak gürültü üretir. Böyle sabitler DIŞLANMAZ, ayrı bir
#: listede ``belirsiz_deger`` diye BEYAN EDİLİR — aracın kendi kapsam sınırı
#: sessizce saklanmaz.
ANLAMLI_BASAMAK_ESIGI = 4


def _anlamli_basamak(deger: float) -> int:
    """Bir sayının anlamlı basamak sayısı (kuyruk sıfırları sayılmaz)."""
    m = re.sub(r'[^0-9]', '', repr(float(deger)).split('e')[0])
    return len(m.strip('0')) or 1


def _turetilmis_deger(dugum, ham: dict):
    """Çözülmüş adlara dayanan basit sayısal ifadeyi hesaplar.

    Kapsam BİLEREK dar: ad, sayı, tekil eksi, dört işlem ve ÜS. Merkez
    dosyasında sabit tanımı bundan karmaşıksa (fonksiyon çağrısı, koşul)
    araç onu çözmeye ÇALIŞMAZ — ``None`` döner ve çağıran atlar; yanlış
    değer üretmektense görmemek yeğdir (fail-closed).

    ÖH D30 / fix-29a — ``ast.Pow`` ayağı EKSİKTİ ve bu, P10B3-10'da
    ``BinOp`` için, P15B2-06'da ``Subscript`` için kapatılan kör bandın
    ÜÇÜNCÜ ayağıydı. ÖLÇÜLDÜ (taban ab7cf68b): ``PA_PER_PSI = LB_KG * G_0 /
    (IN_M ** 2)`` çözülemediği için ``PA_PER_PSI`` ve ondan türeyen
    ``PSIA_PER_BAR`` envantere HİÇ girmiyordu; ikisi de "bekçisiz merkezî
    sabit" olarak raporlanıyor (``bekci_kapsami``) ve DEĞERLERİ ikiz
    taramasının dışında kalıyordu — yani 6894,757293168361'in çıplak bir
    ikizi üründe doğsa araç onu göremezdi. Üs, birim tanımlarının doğal
    biçimidir (lbf/in^2); onu görmemek tam da bu ailenin kör noktasıydı.
    """
    if isinstance(dugum, ast.Name):
        return ham.get(dugum.id)
    if isinstance(dugum, ast.Constant):
        d = dugum.value
        return None if isinstance(d, bool) or not isinstance(
            d, (int, float)) else float(d)
    if isinstance(dugum, ast.UnaryOp) and isinstance(dugum.op, (ast.UAdd,
                                                                ast.USub)):
        i = _turetilmis_deger(dugum.operand, ham)
        return None if i is None else (i if isinstance(dugum.op, ast.UAdd)
                                       else -i)
    if isinstance(dugum, ast.BinOp):
        sol = _turetilmis_deger(dugum.left, ham)
        sag = _turetilmis_deger(dugum.right, ham)
        if sol is None or sag is None:
            return None
        try:
            if isinstance(dugum.op, ast.Add):
                return sol + sag
            if isinstance(dugum.op, ast.Sub):
                return sol - sag
            if isinstance(dugum.op, ast.Mult):
                return sol * sag
            if isinstance(dugum.op, ast.Div):
                return sol / sag
            if isinstance(dugum.op, ast.Pow):
                # Üs BİLEREK sınırlı: yalnız küçük, sonlu tamsayı üsler.
                # Merkezî bir birim tanımı ``IN_M ** 2`` biçimindedir;
                # ``2 ** 10000`` gibi bir ifade aracı kilitleyebilir, o
                # yüzden kapsam dışıdır (fail-closed: None).
                if sag != int(sag) or not (-8 <= sag <= 8):
                    return None
                return sol ** sag
        except (ZeroDivisionError, OverflowError, ValueError):
            return None
    return None


def _yapi_ogesi(dugum, yapilar: dict):
    """``ISA_LAYERS[0][3]`` gibi TABLODAN OKUMA ile tanımlı sabitin değeri.

    ÖH D26 / defter P15B2-06. ``_turetilmis_deger`` ad / sayı / dört işlem
    görür; merkezdeki bir sabit KENDİ TABLOSUNUN bir gözünden okunuyorsa
    (tek-kaynak kuralının en dar biçimi — sayı tabloda bir kez yazılır,
    ikinci kez yazılmaz) araç onu göremiyordu ve sabit envantere hiç
    girmiyordu. P10B3-10'da türetilmiş (``BinOp``) sabitler için kapatılan
    kör bandın aynısı; burada ``Subscript`` ayağı kapanır.

    Kapsam BİLEREK dar: yalnız merkez dosyasında ``literal_eval`` ile
    çözülmüş bir dizi/demet ve TAM SAYI indis. Dilim, negatif olmayan
    değişken indis, çağrı vb. çözülmez -> ``None`` (fail-closed).
    """
    if isinstance(dugum, ast.Name):
        return yapilar.get(dugum.id)
    if not isinstance(dugum, ast.Subscript):
        return None
    taban = _yapi_ogesi(dugum.value, yapilar)
    if not isinstance(taban, (list, tuple)):
        return None
    try:
        indis = ast.literal_eval(dugum.slice)
    except Exception:
        return None
    if isinstance(indis, bool) or not isinstance(indis, int):
        return None
    try:
        return taban[indis]
    except IndexError:
        return None


def merkez_sabitleri(kok: pathlib.Path) -> tuple[dict, dict]:
    """``hrma/constants.py``deki sayısal sabitler — AST ile, kopyasız.

    Döner: ``(ayirt_edici, belirsiz)``; ikisi de ``{ad: deger}``.
    """
    src = (kok / MERKEZ_SABIT_DOSYASI).read_text(encoding='utf-8')
    agac = ast.parse(src)
    ham: dict[str, float] = {}
    #: Sayısal OLMAYAN ama literal olarak çözülen merkez adları (tablolar).
    #: ``_yapi_ogesi`` bunların gözlerinden okunan sabitleri çözer.
    yapilar: dict[str, object] = {}
    for dugum in agac.body:
        hedefler = []
        if isinstance(dugum, ast.Assign):
            hedefler = [t.id for t in dugum.targets if isinstance(t, ast.Name)]
            deger_dugumu = dugum.value
        elif isinstance(dugum, ast.AnnAssign) and isinstance(dugum.target, ast.Name):
            hedefler = [dugum.target.id]
            deger_dugumu = dugum.value
        else:
            continue
        if deger_dugumu is None:
            continue
        try:
            deger = ast.literal_eval(deger_dugumu)
        except Exception:
            # Takma ad (``g_0 = G_0``) veya TÜRETME (``R_MOLAR =
            # R_UNIVERSAL / 1000.0``) — ikisi de zaten çözülmüş adlara
            # dayanır. ÖH D24 / P10B3-10: türetilen sabit burada
            # SESSİZCE DÜŞÜYORDU (``literal_eval`` BinOp'u çözemez, Name
            # dalı da yakalamaz), dolayısıyla merkezde tanımlı olduğu
            # hâlde envantere hiç girmiyor ve "bekçi kapsamı dışında"
            # kalıyordu. Türetme, tek-kaynak kuralının TERCİH EDİLEN
            # biçimidir (sayı iki kez yazılmaz); aracın onu görmemesi
            # kendi kapsam boşluğuydu.
            deger = _turetilmis_deger(deger_dugumu, ham)
            if deger is None:
                # ÖH D26 / P15B2-06: TABLODAN OKUMA ayağı
                # (``P_SEA_LEVEL_PA = ISA_LAYERS[0][3]``).
                deger = _yapi_ogesi(deger_dugumu, yapilar)
            if deger is None:
                continue
        if isinstance(deger, bool) or not isinstance(deger, (int, float)):
            # ÖH D26 / P15B2-06: sayısal olmayan literal (ISA katman
            # tablosu gibi) DÜŞÜRÜLMEZ; ``Subscript`` ile ondan okunan
            # sabitlerin çözülebilmesi için ayrı sözlükte tutulur.
            if isinstance(deger, (list, tuple)):
                for ad in hedefler:
                    yapilar[ad] = deger
            continue
        for ad in hedefler:
            ham[ad] = float(deger)

    ayirt, belirsiz = {}, {}
    for ad, deger in ham.items():
        if deger == 0:
            belirsiz[ad] = deger
        elif _anlamli_basamak(deger) >= ANLAMLI_BASAMAK_ESIGI:
            ayirt[ad] = deger
        else:
            belirsiz[ad] = deger
    return ayirt, belirsiz


def _kaynak_dosyalari(kok: pathlib.Path):
    for parca in TARANAN_KOKLER:
        taban = kok / parca
        if not taban.is_dir():
            continue
        for yol in sorted(taban.rglob('*')):
            if not yol.is_file():
                continue
            bagil = '/' + str(yol.relative_to(kok))
            if any(a in bagil for a in ATLANAN_PARCALAR):
                continue
            if yol.suffix in PY_UZANTI or yol.suffix in JS_UZANTI:
                if str(yol.relative_to(kok)) == MERKEZ_SABIT_DOSYASI:
                    continue  # merkezin kendisi ikiz değildir
                yield yol


def _py_literalleri(metin: str):
    """(satır, değer, biçim) — TÜM sabit düğümleri, yalnız ``Assign`` değil."""
    try:
        agac = ast.parse(metin)
    except SyntaxError:
        return
    ana: dict[int, str] = {}
    for dugum in ast.walk(agac):
        for cocuk in ast.iter_child_nodes(dugum):
            ana[id(cocuk)] = type(dugum).__name__
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.Constant):
            continue
        deger = dugum.value
        if isinstance(deger, bool) or not isinstance(deger, (int, float)):
            continue
        yield dugum.lineno, float(deger), ana.get(id(dugum), 'Module')


#: JS yorum ve dizgilerini eleyen kaba süzgeç. Amaç kesinlik değil, yorum
#: içindeki ``9.81``i kusur saymamak.
_JS_YORUM = re.compile(r'/\*.*?\*/|//[^\n]*', re.S)
_JS_DIZGI = re.compile(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`", re.S)
_JS_SAYI = re.compile(r'(?<![\w.$])(\d+\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)(?![\w.])')


def _js_literalleri(metin: str):
    def _bosalt(m):
        return re.sub(r'[^\n]', ' ', m.group(0))
    temiz = _JS_DIZGI.sub(_bosalt, _JS_YORUM.sub(_bosalt, metin))
    for m in _JS_SAYI.finditer(temiz):
        satir = temiz.count('\n', 0, m.start()) + 1
        try:
            yield satir, float(m.group(1)), 'JS'
        except ValueError:
            continue


def envanter(kok: pathlib.Path | str = KOK) -> dict:
    """Envanteri çıkarır. FAIL-CLOSED: merkez okunamazsa yükseltir."""
    kok = pathlib.Path(kok).resolve()
    ayirt, belirsiz = merkez_sabitleri(kok)
    ihlaller = []
    mesru_isabetler = []
    taranan = 0
    for yol in _kaynak_dosyalari(kok):
        try:
            metin = yol.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        taranan += 1
        bagil = str(yol.relative_to(kok))
        uretici = _py_literalleri if yol.suffix in PY_UZANTI else _js_literalleri
        for satir, deger, bicim in uretici(metin):
            for ad, merkez_deger in ayirt.items():
                if deger == merkez_deger:
                    tur = 'ikiz'
                elif abs(deger - merkez_deger) <= YAKIN_ISKA_BANDI * abs(merkez_deger):
                    tur = 'yakin_iska'
                else:
                    continue
                kayit = {'sabit': ad, 'dosya': bagil, 'satir': satir,
                         'deger': deger, 'bicim': bicim, 'tur': tur}
                (mesru_isabetler if _mesru_mu(bagil, ad, deger)
                 else ihlaller).append(kayit)
                break
    anahtar = lambda i: (i['dosya'], i['satir'], i['sabit'])
    ihlaller.sort(key=anahtar)
    mesru_isabetler.sort(key=anahtar)
    return {
        'taranan_dosya': taranan,
        'sabitler': ayirt,
        'belirsiz_deger': belirsiz,
        'ihlaller': ihlaller,
        'mesru_isabetler': mesru_isabetler,
        'ikiz': sum(1 for i in ihlaller if i['tur'] == 'ikiz'),
        'yakin_iska': sum(1 for i in ihlaller if i['tur'] == 'yakin_iska'),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kok', default=str(KOK))
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)

    sonuc = envanter(args.kok)
    if args.json:
        print(json.dumps(sonuc, ensure_ascii=False, indent=2))
        return 0

    print('KAYNAK SABİT ENVANTERİ')
    print(f"  merkez        : {MERKEZ_SABIT_DOSYASI} "
          f"({len(sonuc['sabitler'])} ayırt edici, "
          f"{len(sonuc['belirsiz_deger'])} belirsiz değerli)")
    print(f"  taranan dosya : {sonuc['taranan_dosya']}")
    print(f"  ikiz          : {sonuc['ikiz']}")
    print(f"  meşru muafiyet: {len(sonuc['mesru_isabetler'])}")
    print(f"  yakın-ıska    : {sonuc['yakin_iska']}")
    if sonuc['belirsiz_deger']:
        print('  KAPSAM SINIRI — ayırt edici olmayan (az anlamlı basamaklı) '
              'sabitler ikiz taramasına GİRMEZ: '
              + ', '.join(sorted(sonuc['belirsiz_deger'])))
    for i in sonuc['ihlaller']:
        print(f"  {i['tur']:11s} {i['sabit']:28s} {i['dosya']}:{i['satir']} "
              f"= {i['deger']!r}  [{i['bicim']}]")

    # --- ÖH D26 / OH-D25-01 -------------------------------------------------
    # (a) ÇIKIŞ KODU İKİZLERİ DE SAYAR. Eski hâli ``1 if yakin_iska else 0``
    #     idi: ikiz ihlalleri ekrana basılıyor ama çıkış kodu 0 dönüyordu,
    #     yani aracı bir kapıda koşan her betik "temiz" hükmü alıyordu.
    #     Gerçek depoda kusur GİZLİYDİ (bugün 5 yakın-ıska var, kod zaten 1);
    #     ölçüm sentetik ağaçla yapıldı (2 ikiz / 0 yakın-ıska -> çıkış 0,
    #     docs/scofield/raw/OH/D26/altyapi/a1/once_nsi_envanter.json
    #     ``sentetik_sadece_ikiz``). İkiz sessiz bir kusurdur (sayı doğru,
    #     kaynak ikiye bölünmüş) — sessizliği çıkış koduna taşımak kusurun
    #     kendisini gizler.
    # (b) HAYALET MUAFİYET de kırmızıdır: muafiyet tablosu ancak GERÇEK bir
    #     isabete karşılık geliyorsa gerekçelidir.
    hayalet = hayalet_muafiyet(sonuc, args.kok)
    for m in hayalet:
        print(f"  HAYALET MUAFİYET  {m['sabit']:26s} {m['dosya']} "
              f"= {m['deger']!r} — hiçbir gerçek isabete uymuyor")
    if hayalet:
        print(f"  hayalet muafiyet: {len(hayalet)} (tabloda yazılı ama "
              'kaynakta karşılığı yok)')

    # --- ÖH D27 / OH-D25-01(c) ---------------------------------------------
    # "Bekçili" AD GEÇİŞİYLE sayılamaz: muafiyet listesinde adı geçen sabit
    # bekçili DEĞİL, kapsam dışı ilan edilmiştir. Kapsam üç kümeye bölünür,
    # gerçek boşluk (``bekcisiz``) çıkış koduna girer.
    kapsam = bekci_kapsami(args.kok)
    print(f"  bekçi kapsamı : {len(kapsam['kapsam'])}/{kapsam['sabit_sayisi']} "
          f"(adıyla sınanan {len(kapsam['govde'])}, "
          f"kapsam mandalında {len(kapsam['mandal'])})")
    if kapsam['yalniz_muafiyet_literalinde']:
        print('  ŞİŞME UYARISI — yalnız muafiyet/kilit listesinde adı geçtiği '
              'için "bekçili" görünen sabit: '
              + ', '.join(kapsam['yalniz_muafiyet_literalinde']))
    for ad in kapsam['bekcisiz']:
        print(f"  BEKÇİSİZ SABİT    {ad} — ne adıyla sınanıyor ne kapsam "
              'mandalında')
    return 1 if (sonuc['ihlaller'] or hayalet or kapsam['bekcisiz']) else 0


if __name__ == '__main__':
    sys.exit(main())
