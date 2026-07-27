"""D-track uyarı sözleşmesi bekçisi (v2.6.2).

Arka plan — bu testin var olma sebebi:
v2.6.2'de analiz modülleri uyarı/öneri metinlerini düz İngilizce string yerine
``{code, params, severity}`` sözlüğüne çevirdi. Backend dönüşümü yapıldı ama
frontend güncellenmedi; sonuçta katı motor uyarı paneli ve emniyet/yapısal
öneri listeleri ekrana ``[object Object]`` bastı. Etkilenen uyarılar arasında
``warn.solid.burn_rate_exponent_ge_one`` (severity=critical, n>=1'de basınç
kaçağı) ve ``warn.safety.do_not_proceed`` ("KRİTİK: Devam etmeyin") vardı —
yani sessizce kaybolan şey tam olarak en kritik uyarılardı.

Bu dosya sözleşmenin üç ayağını da kilitler:
  1. Backend'in ürettiği HER kodun EN ve TR karşılığı vardır.
  2. Parametreli kodların yer tutucuları iki dilde de eksiksizdir.
  3. Frontend tüketicileri sözlüğü ham basmaz (kod yolunu tanır).
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Uyarı kodu üreten backend modülleri. Yeni modül eklenirse buraya da eklenir;
# aksi hâlde kodları çevrilmeden kalır ve kullanıcı ham anahtar görür.
BACKEND_SOURCES = [
    'hrma/analysis/safety_analysis.py',
    'hrma/analysis/structural_analysis.py',
    'hrma/analysis/heat_transfer_analysis.py',
    # v2.6.25: 'warn.kinetic.' öneki ANALYSIS_PREFIXES içinde sahipleniliyordu
    # ama onu ÜRETEN dosya bu listede yoktu. Sonuç: kinetik uyarılarının
    # çevirisi yazıldığı anda hepsi "yetim anahtar" görünüp bu bekçiyi
    # kırıyordu — sahiplenilen önek ile taranan kaynak kümesi ayrışmıştı.
    'hrma/analysis/kinetic_analysis.py',
]

I18N_FILE = 'hrma/static/js/i18n_common.js'

# Bu bekçinin SAHİPLENDİĞİ kod önekleri.
#
# Motor kodları (warn.solid/liquid/hybrid/injector/cycle/combustion) v2.6.2'de
# eklendi ve tests/test_engine_warning_i18n.py tarafından kilitleniyor. İki
# bekçi AYNI sözlük dosyasını okuduğu için, buradaki "yetim anahtar" kontrolü
# önekle sınırlanmalı; aksi hâlde motor anahtarları burada yetim, analiz
# anahtarları orada yetim görünür ve iki test birbirini kırar.
ANALYSIS_PREFIXES = (
    'warn.safety.',
    'warn.structural.',
    'warn.thermal.',
    'warn.kinetic.',
)

CODE_RE = re.compile(r"'(warn\.[a-z0-9_.]+)'")
KEY_RE = re.compile(r"'(warn\.[a-z0-9_.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'")
PLACEHOLDER_RE = re.compile(r'\{(\w+)\}')


def _backend_codes():
    codes = set()
    for rel in BACKEND_SOURCES:
        codes |= set(CODE_RE.findall((ROOT / rel).read_text(encoding='utf-8')))
    return codes


def _dicts():
    """i18n_common.js içindeki en/tr bloklarını {kod: metin} olarak döndürür."""
    js = (ROOT / I18N_FILE).read_text(encoding='utf-8')
    en_start, tr_start = js.index('        en: {'), js.index('        tr: {')
    assert en_start < tr_start, 'i18n_common.js blok sırası beklenmedik'
    return (
        dict(KEY_RE.findall(js[en_start:tr_start])),
        dict(KEY_RE.findall(js[tr_start:])),
    )


def test_backend_emits_codes_at_all():
    """Sözleşme yürürlükte mi — kod üretimi tümden kaybolduysa bu test uyarır."""
    codes = _backend_codes()
    assert len(codes) >= 40, f'Beklenenden az uyarı kodu bulundu: {len(codes)}'


@pytest.mark.parametrize('lang_index,lang', [(0, 'EN'), (1, 'TR')])
def test_every_backend_code_has_translation(lang_index, lang):
    """Her backend kodunun karşılığı olmalı; yoksa kullanıcı ham anahtar görür."""
    codes = _backend_codes()
    table = _dicts()[lang_index]
    missing = sorted(codes - set(table))
    assert not missing, f'{lang} sözlüğünde eksik uyarı kodu: {missing}'


def test_no_orphan_translation_keys():
    """Backend'de karşılığı olmayan çeviri anahtarı ölü ağırlıktır."""
    codes = _backend_codes()
    en, tr = _dicts()

    def owned(table):
        return {k for k in table if k.startswith(ANALYSIS_PREFIXES)}

    orphan_en = sorted(owned(en) - codes)
    orphan_tr = sorted(owned(tr) - codes)
    assert not orphan_en, f'EN sözlüğünde yetim anahtar: {orphan_en}'
    assert not orphan_tr, f'TR sözlüğünde yetim anahtar: {orphan_tr}'


def test_placeholders_match_between_languages():
    """{T_wall} gibi yer tutucular iki dilde de aynı olmalı.

    Eksik yer tutucu sessiz veri kaybıdır: TR kullanıcısı sıcaklık değerini
    hiç görmeden 'cidar sıcaklığı sınırı aşıyor' uyarısı okur.
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
    """_mk_warning'e verilen her parametre metinde yer tutucu olarak geçmeli.

    Geçmiyorsa ya parametre boşuna hesaplanıyor ya da metin eksik yazılmış.
    """
    import ast

    en, _tr = _dicts()
    # Regex yerine AST: metin içinde geçen matematiksel değişken adlarını
    # (sigma_a, S_e ...) yanlışlıkla "parametre" saymamak için.
    calls = {}
    for rel in BACKEND_SOURCES:
        tree = ast.parse((ROOT / rel).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, 'id', None) or getattr(fn, 'attr', None)
            if name != '_mk_warning' or not node.args:
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Constant)
                    and isinstance(first.value, str)
                    and first.value.startswith('warn.')):
                continue
            kw = {k.arg for k in node.keywords if k.arg}
            calls.setdefault(first.value, set()).update(kw)

    problems = []
    for code, params in sorted(calls.items()):
        if not params or code not in en:
            continue
        unused = params - set(PLACEHOLDER_RE.findall(en[code]))
        if unused:
            problems.append(f'{code}: metinde kullanılmayan parametre {sorted(unused)}')
    assert not problems, '\n'.join(problems)


def test_frontend_consumers_handle_code_dicts():
    """Sözlüğü ham basan tüketici kalmamalı — '[object Object]' regresyonu.

    Her tüketicinin ``code`` alanını tanıyıp çeviri fonksiyonundan geçirdiğini
    doğrular. Yeni bir panel uyarı listesi tüketmeye başlarsa buraya eklenir.
    """
    checks = [
        # (dosya, sözlüğü çeviren ifadeyi içermesi beklenen işaret)
        ('hrma/static/js/analysis_dock.js', 'function warnText'),
        ('hrma/static/js/analysis_dock.js', 'warnText: warnText'),
        ('hrma/static/js/panels/safety_panel.js', '.map(U.warnText)'),
        ('hrma/templates/solid.html', 'function localizeWarning'),
    ]
    for rel, needle in checks:
        text = (ROOT / rel).read_text(encoding='utf-8')
        assert needle in text, f'{rel} içinde beklenen tüketici kodu yok: {needle!r}'


def test_frontend_translates_nested_warning_records():
    """İç içe uyarı kayıtları da çevrilmeli — özyineleme bekçisi.

    Bazı uyarıların parametresi kendisi bir uyarı kaydı ya da kayıt LİSTESİDİR:
    ``warn.solid.bates_envelope`` ``params['options']`` alanında kendi
    ``warn.solid.opt_*`` kodlarını taşır. ``I18N.tf`` sayı olmayan parametreyi
    ``String(v)`` ile bastığı için, çeviri özyinelemeli değilse bu alanlar
    kullanıcıya "[object Object]" olarak görünür — dış metin doğru çevrilmiş
    olsa bile.
    """
    for rel in ('hrma/static/js/analysis_dock.js', 'hrma/templates/solid.html'):
        text = (ROOT / rel).read_text(encoding='utf-8')
        assert 'Array.isArray(' in text, (
            f'{rel}: uyarı listesi (options) çevirisi yok')
        assert 'depth' in text, (
            f'{rel}: özyineleme derinlik koruması yok')


def test_nested_warning_producer_contract_holds():
    """Backend gerçekten iç içe kayıt üretiyor mu — sözleşmenin diğer ucu.

    Üretici tarafı sadeleşip düz metne dönerse yukarıdaki frontend özyinelemesi
    ölü kod olur; bu test iki ucu birbirine bağlar.
    """
    src = (ROOT / 'hrma/engines/solid_rocket_engine.py').read_text(encoding='utf-8')
    assert 'options=options' in src, (
        'bates_envelope artık iç içe kayıt üretmiyor; frontend özyinelemesi '
        'gözden geçirilmeli')
    assert "_w('warn.solid.opt_" in src, 'iç içe seçenek kodları kaybolmuş'


def test_no_raw_object_join_on_warning_lists():
    """Uyarı listelerinde ham .join() kalmamalı ('[object Object] · ...')."""
    text = (ROOT / 'hrma/static/js/panels/safety_panel.js').read_text(encoding='utf-8')
    assert "safety_devices_required.join(" not in text, (
        'safety_devices_required ham join() ile basılıyor — sözlük listesi '
        '"[object Object]" üretir; .map(U.warnText) kullanılmalı.'
    )
