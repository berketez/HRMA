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


def _dicts():
    """i18n_common.js içindeki en/tr bloklarını {kod: metin} olarak döndürür."""
    js = (ROOT / I18N_FILE).read_text(encoding='utf-8')
    en_start, tr_start = js.index('        en: {'), js.index('        tr: {')
    assert en_start < tr_start, 'i18n_common.js blok sırası beklenmedik'
    return (
        dict(KEY_RE.findall(js[en_start:tr_start])),
        dict(KEY_RE.findall(js[tr_start:])),
    )


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
    missing = sorted(codes - set(table))
    assert not missing, f'{lang} sözlüğünde eksik motor uyarı kodu: {missing}'


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
