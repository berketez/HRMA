"""Motor (engines) uyarı kodu i18n bekçisi (v2.6.2).

Arka plan — bu testin var olma sebebi:
v2.6.2'de ``hrma/engines/*.py`` modülleri kullanıcıya görünen uyarı ve
varsayım metinlerini düz string yerine ``{code, params, severity}`` sözlüğüne
çevirdi. Analiz tarafı (safety/structural/thermal) için parite bekçisi
``tests/test_warning_contract.py`` ile kilitlendi, ama motor kodlarının
(``warn.solid.*``, ``warn.liquid.*``, ``warn.injector.*``, ``warn.cycle.*``,
``warn.combustion.*``) HİÇBİRİNİN sözlük karşılığı yoktu: kullanıcı panelde
çevrilmiş metin yerine ham anahtar görüyordu (ör. "warn.cycle.ox_density_nbp").
Kaybolanlar arasında ``warn.solid.burn_rate_exponent_ge_one`` (n>=1'de basınç
kaçağı) ve ``warn.cycle.staged_power_balance_infeasible`` gibi KRİTİK kayıtlar
vardı — yani en çok okunması gereken uyarılar okunamaz haldeydi.

Bu dosya sözleşmenin dört ayağını kilitler:
  1. Motor modüllerinin ürettiği HER kodun EN ve TR karşılığı vardır.
  2. Motor öneki taşıyan yetim (backend'de karşılığı olmayan) anahtar yoktur.
  3. Yer tutucular ({tit}, {pr} ...) iki dilde birebir aynıdır.
  4. ``_w()`` / ``_warn()`` çağrısına verilen HER parametre metinde kullanılır
     (kullanılmayan parametre ya boşuna hesaplanmıştır ya metin eksiktir).

Not: kod kümesi dosyalardan DİNAMİK okunur. Motor dosyasına yeni bir uyarı
kodu eklenip sözlüğe girilmezse bu test kırmızıya döner — istenen davranış
budur, çünkü alternatifi kullanıcının ham anahtar görmesidir.
"""

import ast
import glob
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Uyarı kodu üreten motor modülleri. Glob kullanılıyor: yeni bir motor dosyası
# eklendiğinde listeyi güncellemek unutulmasın diye.
BACKEND_GLOB = 'hrma/engines/*.py'

I18N_FILE = 'hrma/static/js/i18n_common.js'

# Bu testin sahiplendiği kod önekleri. Analiz tarafı (warn.safety/structural/
# thermal/kinetic) test_warning_contract.py'nin kapsamındadır; yetim kontrolü
# yalnız bu öneklerde yapılır ki iki bekçi birbirini yanlışlıkla kırmasın.
ENGINE_PREFIXES = (
    'warn.combustion.',
    'warn.cycle.',
    'warn.hybrid.',
    'warn.injector.',
    'warn.liquid.',
    'warn.nozzle.',
    'warn.solid.',
)

# Uyarı kaydı üreten yardımcıların adları (dosya-yerel tanımlar).
WARN_HELPERS = ('_w', '_warn', '_mk_warning')

# --- ZİNCİR BORCU (ÖH D30 · katı a1 · OH-D29-05 / OH-D28-05) --------------
# Bir uyarı kodunun SÖZLÜK karşılığını, kodu yayımlayan kulvar ekleyemez:
# ``i18n_common.js``in sahibi arayuz-i18n kulvarıdır ve D29 hüküm-18 zinciri
# "motor kodu -> i18n anahtarı -> panel satırı" sırasını şart koşar (kod
# yokken anahtar yazmak olmayan bir uyarıyı varmış gibi göstermek olurdu).
# Zincirin iki ayağı ayrı dalgalara düştüğünde arada bir dalga boyu
# anahtarsız kod bulunur.
#
# Bu listenin GEVŞETME OLMAMASININ sebebi, testin gerekçesinin ("yoksa
# kullanıcı ham anahtar görür") o kodlar için geçerli OLMAMASIDIR: kayıt
# İngilizce metnini ``fallback`` alanında taşır ve ekran katmanı
# (``templates/solid.html`` ``displaySolidWarnings``, ``static/js/app.js``
# ``warnToText``) ``w.fallback || w.code`` ile onu basar — kullanıcı ham
# anahtar değil İngilizce cümle görür. Liste bir BORÇ İMİdir ve iki ayrı
# bekçiyle kendini temizler:
#   * girmek KAZANILIR: kodun her yayım yerinde ``fallback`` bulunmalıdır
#     (test_zincir_borcu_kodlari_ingilizce_yedek_tasiyor),
#   * anahtar eklendiği anda kod buradan ÇIKMAK zorundadır
#     (test_zincir_borcu_odendiyse_liste_temizlenir).
# Küme kalıcıdır: zincirin iki ayağı (motor kodu -> i18n anahtarı) ayrı
# dalgalara düştüğünde yeni kod buraya gerekçesiyle yazılır. `set()` /
# `{...}` küme yazılır, boş SÖZLÜK DEĞİL: ikincisi küme farkı alan üç
# kullanım yerinde TypeError verirdi (ölçüldü).
#
# ÖH D30 · fix-31: ``warn.solid.erosion_exponent_extrapolated`` EN+TR
# karşılığını aldı ve test_zincir_borcu_odendiyse_liste_temizlenir uyarınca
# buradan ÇIKARILDI.
#
# ÖH D32 · kati a1 (OH-D31-17): ``warn.solid.two_phase_correction_unverified``
# eklendi. Berke/Astra hükmü (15 Eyl) "iki-faz düzeltmesi doğrulanmamış"
# durumunun PDF'e taşınmasını ŞART koşuyor ve PDF katmanı yalnız
# ``design_warnings`` kayıtlarını okuyor (pdf_generator.WARNING_SOURCES) —
# yani kodun bu dalgada yayımlanması zorunluydu. ``i18n_common.js`` ise
# arayuz-i18n kulvarının sahasıdır ve D29 hüküm-18 zinciri "önce motor
# kodu, sonra i18n anahtarı" sırasını şart koşar. Kayıt İngilizce metnini
# ``fallback`` alanında taşıyor (test_zincir_borcu_kodlari_ingilizce_yedek_
# tasiyor bunu kilitliyor), bu yüzden kullanıcı ham anahtar GÖRMÜYOR.
# Borç, arayuz-i18n kulvarı EN+TR anahtarını eklediğinde kapanır.
#
# ÖH D33 · motorlar a1 (OH-UC-05): ``warn.liquid.vacuum_isp_improvement_
# out_of_band`` eklendi. Hüküm ZATEN VARDI ama yalnız ``print()`` ile
# stdout'a basılıyordu (ÖLÇÜLDÜ, docs/scofield/raw/OH/D33/motorlar/a1/
# once.json · K1: stdout'ta "Vakum Isp iyileştirmesi anormal: %0.0" satırı
# VAR, yanıttaki eşleşen ``design_warnings`` kaydı 0) — yani kullanıcı
# hükmü HİÇ görmüyordu. Kanalın onarımı bu dalganın kalemidir;
# ``i18n_common.js`` ise arayuz-i18n kulvarının sahasıdır ve D33-KOLAY'da
# o kulvar AÇILMADI. Kayıt İngilizce metnini ``fallback`` alanında taşıyor
# (``test_zincir_borcu_kodlari_ingilizce_yedek_tasiyor`` kilitliyor) ve
# ekran katmanı (``static/js/app.js`` ``warnToText``, ``analysis_dock.js``
# ``warnText``) ``TF(code, params, w.fallback || w.code)`` ile onu basıyor;
# ``I18N.tf`` yer tutucuları YEDEK METİNDE de yerine koyar (i18n.js:282),
# yani kullanıcı ham anahtar değil sayılı İngilizce cümle görür. Borç,
# arayuz-i18n kulvarı EN+TR anahtarını eklediğinde kapanır.
ZINCIR_BORCU = set()  # fix-35e (15 Eyl): warn.solid.two_phase_correction_unverified ödendi; fix-36a (15 Eyl 23:2x, ana model): warn.liquid.vacuum_isp_improvement_out_of_band (D33 motorlar a1 · OH-UC-05) EN+TR sözlüğe girdi, borç ödendi ve listeden çıktı — küme BOŞ

CODE_RE = re.compile(r"['\"](warn\.[a-z0-9_.]+)['\"]")
KEY_RE = re.compile(r"'(warn\.[a-z0-9_.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'")
PLACEHOLDER_RE = re.compile(r'\{(\w+)\}')


def _engine_files():
    files = sorted(glob.glob(str(ROOT / BACKEND_GLOB)))
    assert files, f'{BACKEND_GLOB} hiçbir dosya eşleşmedi'
    return [Path(f) for f in files]


def _backend_codes():
    """Motor dosyalarında geçen tüm warn.* kodları.

    Regex kullanılır (AST değil) çünkü kodların bir kısmı koşullu ifadeyle
    (``'...._ox' if stream == 'ox' else '..._fuel'``) veya doğrudan sözlük
    literaliyle (``{'code': ...}``) üretiliyor; ikisi de kullanıcıya aynı
    şekilde ulaşır, dolayısıyla ikisi de çevrilmek zorundadır.
    """
    codes = set()
    for path in _engine_files():
        codes |= set(CODE_RE.findall(path.read_text(encoding='utf-8')))
    return codes


def _all_backend_codes():
    """Tüm backend (hrma/**/*.py) warn.* kodları — yetim kontrolü için.

    Yetim kontrolünde motor dosyalarıyla yetinmek TUZAKTIR: ``warn.hybrid.*``
    kodlarının bir bölümü ``hrma/analysis/regression_analysis.py`` içinde
    üretiliyor. Yalnız motor dosyalarına bakılsaydı, oraya ait bir çeviri
    eklendiği anda bu test onu haksız yere "yetim" ilan ederdi.
    """
    codes = set()
    for path in sorted((ROOT / 'hrma').glob('**/*.py')):
        codes |= set(CODE_RE.findall(path.read_text(encoding='utf-8')))
    return codes


def _declared_params():
    """{kod: {parametre adları}} — _w()/_warn() çağrılarından AST ile.

    Regex yerine AST: metin içinde geçen matematiksel değişken adlarını
    (K_c, r_s ...) yanlışlıkla "parametre" saymamak için. Koşullu ilk argüman
    (IfExp) iki dala da açılır — gaz postu / hidrolik flip kodları böyle
    üretiliyor ve parametreleri ortaktır.
    """
    def codes_of(node):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and node.value.startswith('warn.')):
            return [node.value]
        if isinstance(node, ast.IfExp):
            return codes_of(node.body) + codes_of(node.orelse)
        return []

    calls = {}
    for path in _engine_files():
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            fn = node.func
            name = getattr(fn, 'id', None) or getattr(fn, 'attr', None)
            if name not in WARN_HELPERS:
                continue
            kw = {k.arg for k in node.keywords if k.arg}
            for code in codes_of(node.args[0]):
                calls.setdefault(code, set()).update(kw)
    return calls


# ---------------------------------------------------------------------------
# ÖH D24 · OH-D23-22 — SÖZLÜK KESİTİ, DENGELİ PARANTEZLE ÇIKARILIR
#
# Eski ``_dicts`` EN bloğunu ``js[en_start:tr_start]``, TR bloğunu
# ``js[tr_start:]`` diye DİLİMLİYORDU. İki kusur:
#
#   1. EN kesiti ``tr: {`` işaretinde biter; dosyanın SONUNA eklenen bir
#      anahtar EN tarafında GÖRÜNMEZ. (Dalga briefinin "electron/sivi
#      anahtarı dosya sonuna blok olarak eklenebilir" istisnası tam bu
#      yüzden kaldırıldı — ÖH D23 sıvı kulvarı ölçtü.)
#   2. TR kesiti DOSYA SONUNA kadar gider; sözlük nesnesi ``};`` ile
#      kapandıktan SONRA gelen her şeyi de TR çevirisi sayar. Oysa orası
#      ``I18N.register`` çağrısıdır: oraya yazılan anahtar tarayıcıya HİÇ
#      ulaşmaz. Yani bekçi, hiç yüklenmeyen bir anahtarı "TR çevirisi var"
#      diye kabul ediyordu — fail-open.
#
# Kesit artık dengeli parantezle çıkarılır ve iki bloğun DIŞINDA kalan
# ``warn.*`` anahtarları ADIYLA raporlanır (``_blok_disi_anahtarlar``).
# ---------------------------------------------------------------------------

def _blok_araligi(js, bas_imi):
    """``bas_imi`` satırından, aynı girintideki kapanış satırına kadar.

    Karakter düzeyinde parantez saymak bu dosyada GÜVENİLMEZ: metinler
    kesme işareti ve süslü yer tutucu ("{shown}", "don't") taşıyor, JS
    yorumları da öyle. Ölçüldü (ÖH D24): karakter tarayıcısı EN bloğunu
    2516-450570 aralığında "kapatıyor", yani TR bloğunu da yutuyordu ve
    iki sözlük birebir aynı çıkıyordu (``test_turkish_block_is_actually_
    turkish`` kırmızıya düştü).

    Bu dosyanın biçimi kesindir ve ADIYLA sınanır: blok ``        en: {``
    satırıyla açılır, ``        }`` / ``        },`` satırıyla kapanır.
    Biçim değişirse fonksiyon SESSİZ KALMAZ, hata yükseltir.
    """
    satirlar = js.split('\n')
    girinti = bas_imi[:len(bas_imi) - len(bas_imi.lstrip())]
    bas_no = None
    for i, satir in enumerate(satirlar):
        if satir.rstrip() == bas_imi.rstrip():
            bas_no = i
            break
    assert bas_no is not None, '%r satırı yok' % bas_imi
    kapanis = re.compile(r'^%s\}[,;]?\s*$' % re.escape(girinti))
    for j in range(bas_no + 1, len(satirlar)):
        if kapanis.match(satirlar[j]):
            bas_ofs = sum(len(x) + 1 for x in satirlar[:bas_no])
            son_ofs = sum(len(x) + 1 for x in satirlar[:j + 1])
            return (bas_ofs, son_ofs), '\n'.join(satirlar[bas_no:j + 1])
    raise AssertionError('%r bloğu kapanmıyor (biçim değişmiş)' % bas_imi)


def _blok_araliklari():
    js = (ROOT / I18N_FILE).read_text(encoding='utf-8')
    en_ara, en_metin = _blok_araligi(js, '        en: {')
    tr_ara, tr_metin = _blok_araligi(js, '        tr: {')
    assert en_ara[0] < tr_ara[0], 'i18n_common.js blok sırası beklenmedik'
    return js, (en_ara, en_metin), (tr_ara, tr_metin)


def _dicts():
    """i18n_common.js içindeki en/tr bloklarını {kod: metin} olarak döndürür."""
    _, (_, en_metin), (_, tr_metin) = _blok_araliklari()
    return dict(KEY_RE.findall(en_metin)), dict(KEY_RE.findall(tr_metin))


def _blok_disi_anahtarlar():
    """``en``/``tr`` bloklarının DIŞINDA duran ``warn.*`` anahtarları.

    Böyle bir anahtar ya hiç yüklenmez (sözlük nesnesi kapandıktan sonra)
    ya da yanlış dile yazılır. Sessizce saymak yerine ADIYLA bildirilir.
    """
    js, (en_ara, _), (tr_ara, _) = _blok_araliklari()
    disarida = []
    for m in KEY_RE.finditer(js):
        i = m.start()
        icinde = (en_ara[0] <= i < en_ara[1]) or (tr_ara[0] <= i < tr_ara[1])
        if not icinde:
            satir = js.count('\n', 0, i) + 1
            disarida.append('%s:%d %s' % (I18N_FILE, satir, m.group(1)))
    return disarida


def _engine_keys(table):
    return {k for k in table if k.startswith(ENGINE_PREFIXES)}


def test_backend_emits_engine_codes_at_all():
    """Sözleşme yürürlükte mi — kod üretimi tümden kaybolduysa bu test uyarır."""
    codes = _backend_codes()
    assert len(codes) >= 120, f'Beklenenden az motor uyarı kodu bulundu: {len(codes)}'


def test_all_engine_codes_carry_known_prefix():
    """Yeni bir alt sistem öneki eklenirse bekçi kapsamı dışında kalmasın."""
    unknown = sorted(c for c in _backend_codes()
                     if not c.startswith(ENGINE_PREFIXES))
    assert not unknown, (
        f'Tanınmayan önekli motor uyarı kodu: {unknown}. '
        f'ENGINE_PREFIXES listesine ekleyin, aksi hâlde yetim kontrolü '
        f'bu kodları görmez.')


@pytest.mark.parametrize('lang_index,lang', [(0, 'EN'), (1, 'TR')])
def test_every_engine_code_has_translation(lang_index, lang):
    """Her motor kodunun karşılığı olmalı; yoksa kullanıcı ham anahtar görür."""
    codes = _backend_codes()
    table = _dicts()[lang_index]
    missing = sorted(codes - set(table) - ZINCIR_BORCU)
    assert not missing, f'{lang} sözlüğünde eksik motor uyarı kodu: {missing}'


def _yayim_yerleri(code):
    """``code``u yayımlayan çağrı düğümleri (AST) — dosya adıyla birlikte."""
    bulunan = []
    for path in _engine_files():
        agac = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(agac):
            if not isinstance(node, ast.Call):
                continue
            sabitler = [c.value for c in ast.walk(node)
                        if isinstance(c, ast.Constant)
                        and isinstance(c.value, str)]
            if code in sabitler:
                bulunan.append((path.name, node))
    return bulunan


def test_zincir_borcu_kodlari_ingilizce_yedek_tasiyor():
    """Borç imi KAZANILIR: anahtarsız kod İngilizce metnini taşımalı.

    Aksi hâlde liste gerçekten bir gevşetme olurdu — kullanıcı ham anahtar
    görürken bekçi yeşil kalırdı.
    """
    eksik = []
    for code in sorted(ZINCIR_BORCU):
        yerler = _yayim_yerleri(code)
        assert yerler, f'{code} hiçbir motor dosyasında yayımlanmıyor'
        # En dış çağrı (``dict(_w(...), fallback=...)``) yedek metni taşır.
        yedekli = [
            (ad, n) for ad, n in yerler
            if any(kw.arg == 'fallback'
                   and isinstance(kw.value, ast.Constant)
                   and isinstance(kw.value.value, str)
                   and kw.value.value.strip()
                   for kw in n.keywords)
        ]
        if not yedekli:
            eksik.append('%s (%s)' % (code, sorted({a for a, _ in yerler})))
    assert not eksik, (
        'zincir borcundaki kod İngilizce yedek metin taşımıyor: %s' % eksik)


def test_zincir_borcu_odendiyse_liste_temizlenir():
    """Anahtar geldiyse borç imi KALMAZ (XPASS'ın sözlük karşılığı)."""
    en, tr = _dicts()
    odenmis = sorted(c for c in ZINCIR_BORCU if c in en and c in tr)
    assert not odenmis, (
        'bu kodların EN+TR anahtarı eklenmiş; ZINCIR_BORCU listesinden '
        'çıkarın: %s' % odenmis)


def test_no_orphan_engine_translation_keys():
    """Backend'de karşılığı olmayan çeviri anahtarı ölü ağırlıktır."""
    codes = _all_backend_codes()
    en, tr = _dicts()
    orphan_en = sorted(_engine_keys(en) - codes)
    orphan_tr = sorted(_engine_keys(tr) - codes)
    assert not orphan_en, f'EN sözlüğünde yetim motor anahtarı: {orphan_en}'
    assert not orphan_tr, f'TR sözlüğünde yetim motor anahtarı: {orphan_tr}'


def test_placeholders_match_between_languages():
    """{tit} gibi yer tutucular iki dilde de aynı olmalı.

    Eksik yer tutucu sessiz veri kaybıdır: TR kullanıcısı sıcaklık değerini
    hiç görmeden "türbin giriş sıcaklığı sınırı aşıyor" uyarısı okur.
    """
    codes = _backend_codes()
    en, tr = _dicts()
    problems = []
    for code in sorted(codes):
        if code not in en or code not in tr:
            continue  # ayrı test kapsıyor
        p_en = set(PLACEHOLDER_RE.findall(en[code]))
        p_tr = set(PLACEHOLDER_RE.findall(tr[code]))
        if p_en != p_tr:
            problems.append(f'{code}: EN={sorted(p_en)} TR={sorted(p_tr)}')
    assert not problems, 'Yer tutucu uyuşmazlığı:\n' + '\n'.join(problems)


def test_declared_params_are_used_in_text():
    """_w()'ye verilen her parametre metinde yer tutucu olarak geçmeli.

    Geçmiyorsa ya parametre boşuna hesaplanıyor ya da metin eksik yazılmış.
    Kontrol iki dilde de yapılır — TR metni EN'in parametre kümesini
    kaybederse (ör. sayıyı cümleden düşürürse) burada yakalanır.
    """
    en, tr = _dicts()
    problems = []
    for code, params in sorted(_declared_params().items()):
        if not params:
            continue
        for lang, table in (('EN', en), ('TR', tr)):
            if code not in table:
                continue  # ayrı test kapsıyor
            unused = params - set(PLACEHOLDER_RE.findall(table[code]))
            if unused:
                problems.append(
                    f'{code} [{lang}]: metinde kullanılmayan parametre '
                    f'{sorted(unused)}')
    assert not problems, '\n'.join(problems)


def test_no_undeclared_placeholders_in_text():
    """Metindeki her yer tutucunun backend karşılığı olmalı.

    Backend'in göndermediği {foo}, tf() tarafından OLDUĞU GİBİ bırakılır ve
    kullanıcı ekranda süslü parantezli ham anahtar görür.
    """
    en, tr = _dicts()
    declared = _declared_params()
    problems = []
    for code, params in sorted(declared.items()):
        for lang, table in (('EN', en), ('TR', tr)):
            if code not in table:
                continue
            extra = set(PLACEHOLDER_RE.findall(table[code])) - params
            if extra:
                problems.append(
                    f'{code} [{lang}]: backend göndermeyen yer tutucu '
                    f'{sorted(extra)}')
    assert not problems, '\n'.join(problems)


def test_translations_are_not_placeholder_stubs():
    """Metin, kodun kendisi ya da boş olmamalı (kopyala-yapıştır kazası)."""
    codes = _backend_codes()
    en, tr = _dicts()
    problems = []
    for code in sorted(codes):
        for lang, table in (('EN', en), ('TR', tr)):
            text = table.get(code)
            if text is None:
                continue
            if not text.strip() or text.strip() == code:
                problems.append(f'{code} [{lang}]: metin boş veya kodun kopyası')
    assert not problems, '\n'.join(problems)


def test_turkish_block_is_actually_turkish():
    """TR metinleri EN ile birebir aynı olmamalı (çeviri unutulmuş kalıntı).

    Kısa özel adlar (birim, kısaltma) doğal olarak aynı kalabilir; bu yüzden
    yalnız 40 karakterden uzun metinlerde birebir eşitlik hata sayılır.
    """
    codes = _backend_codes()
    en, tr = _dicts()
    same = sorted(c for c in codes
                  if c in en and c in tr and len(en[c]) > 40 and en[c] == tr[c])
    assert not same, f'TR karşılığı İngilizce metinle aynı kalmış: {same}'
