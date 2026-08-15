# -*- coding: utf-8 -*-
"""Parça-kopya bekçisi — sözlük girdisi, kodun tam fallback'inin ÖN EKİ olamaz.

NEDEN (2.6.27 yirminci parti, 15 Ağustos 2026 — ölçüldü):
fea_panel.js'teki uzun İngilizce fallback'ler kaynakta çok parçalı dize
birleştirmesiyle yazılır::

    T('fea.busy', 'Running — the solver refines the mesh until the '
        + 'peak stress stops changing; ...')

Anahtarlar sözlüğe taşınırken birleştirmenin YALNIZ İLK dizesi kopyalanmış;
sözlük girdisi fallback'i ezdiği için üründe 10 ayrı metin cümle ortasında
kesik basılıyordu ('fea.intro', 'fea.busy', 'fea.gaussNote', ... — tamamı bu
dosyanın taramasıyla bulundu ve onarıldı). Türkçe girdiler elle yazıldığı
için tamdı; kusur yalnız EN tarafındaydı ve hiçbir bekçi görmüyordu: ölü
çeviri bekçisi anahtarın VARLIĞINA bakar, içeriğine bakmaz.

KURAL: kod içinde T('anahtar', '<tam fallback>') olarak yaşayan her anahtar
için, EN sözlük değeri fallback'in KESİN ÖN EKİ (daha kısa hâli) olamaz.
Farklı olması serbesttir (sözlük metni bilinçli sadeleştirilmiş olabilir);
yasak olan tek şey "kopyala derken yarıda kesilmiş" imzasıdır.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STATIC_JS = REPO / 'hrma' / 'static' / 'js'

#: Fallback taşıyan kaynaklar. Yeni panel dosyası eklendiğinde buraya da
#: eklenmelidir (test_i18n_common.py MODULE_FILES ile aynı disiplin).
FALLBACK_SOURCES = [
    STATIC_JS / 'fea_panel.js',
    STATIC_JS / 'thermal_fea_panel.js',
    REPO / 'hrma' / 'templates' / 'solid.html',
    REPO / 'hrma' / 'templates' / 'advanced.html',
    REPO / 'hrma' / 'templates' / 'liquid.html',
]

DICTS = [
    STATIC_JS / 'i18n_common.js',
    STATIC_JS / 'i18n_pages.js',
    STATIC_JS / 'i18n_advanced.js',
]


def _string_literal(s, i):
    """s[i] tırnak: literalin (değer, sonraki_indeks) çifti."""
    q = s[i]
    out = []
    i += 1
    while i < len(s):
        c = s[i]
        if c == '\\':
            nxt = s[i + 1]
            out.append({'n': '\n', 't': '\t', "'": "'", '"': '"',
                        '\\': '\\'}.get(nxt, nxt))
            i += 2
            continue
        if c == q:
            return ''.join(out), i + 1
        out.append(c)
        i += 1
    raise AssertionError('kapanmayan dize: %d' % i)


def _concat_from(s, i):
    """i'deki dize literalinden başlayıp ' + ' zincirini birleştirir."""
    parts = []
    while True:
        while i < len(s) and s[i] in ' \t\n':
            i += 1
        if i >= len(s) or s[i] not in '\'"':
            break
        val, i = _string_literal(s, i)
        parts.append(val)
        j = i
        while j < len(s) and s[j] in ' \t\n':
            j += 1
        if j < len(s) and s[j] == '+':
            i = j + 1
            continue
        break
    return ''.join(parts), i


def _skip_arg(s, i):
    """Dize olmayan bir argümanı (nesne literali / tanımlayıcı) atlar."""
    if i < len(s) and s[i] == '{':
        depth = 0
        while i < len(s):
            if s[i] == '{':
                depth += 1
            elif s[i] == '}':
                depth -= 1
                if depth == 0:
                    return i + 1
            elif s[i] in '\'"':
                _, i = _string_literal(s, i)
                continue
            i += 1
        return i
    while i < len(s) and re.match(r'[\w$.\[\]()]', s[i]):
        i += 1
    return i


def harvest_fallbacks(path):
    """T('k', str) / TF('k', <arg>, str) çağrılarından anahtar→tam fallback.

    Aynı anahtar birden çok yerde geçerse en UZUN fallback esas alınır
    (kısa bağlam kopyaları uzun metni yanlışlamasın)."""
    s = path.read_text(encoding='utf-8')
    out = {}
    for m in re.finditer(r"\bTF?\(\s*['\"]([\w.\-]+)['\"]\s*,", s):
        key, i = m.group(1), m.end()
        for _ in range(3):          # en fazla 2 ara argüman
            while i < len(s) and s[i] in ' \t\n':
                i += 1
            if i >= len(s):
                break
            if s[i] in '\'"':
                val, _son = _concat_from(s, i)
                if key not in out or len(val) > len(out[key]):
                    out[key] = val
                break
            yeni = _skip_arg(s, i)
            if yeni == i:
                break
            i = yeni
            while i < len(s) and s[i] in ' \t\n':
                i += 1
            if i < len(s) and s[i] == ',':
                i += 1
            else:
                break
    return out


def dict_entries(path):
    """Sözlük dosyasının YALNIZ EN bölümündeki girdiler.

    TR bölümü bilinçli dışarıda: çeviri, fallback'in ön eki olabilir ve bu
    kusur değildir (ölçülen örnek: TR 'Kerosen', EN fallback 'Kerosene'nin
    ön ekidir — doğru Türkçe kelimedir). Kesik-kopya hastalığı yalnız EN
    girdisi fallback'ten kopyalanırken oluşur."""
    s = path.read_text(encoding='utf-8')
    en_m = re.search(r'^\s*en:\s*\{', s, re.M)
    tr_m = re.search(r'^\s*tr:\s*\{', s, re.M)
    assert en_m and tr_m and en_m.start() < tr_m.start(), (
        '%s: en:/tr: bölüm yapısı beklenen düzende değil' % path.name)
    bas, son = en_m.end(), tr_m.start()
    out = []
    for m in re.finditer(r"['\"]([\w.\-]+)['\"]\s*:\s*(?=['\"])", s):
        if not (bas <= m.start() < son):
            continue
        val, _ = _concat_from(s, m.end())
        line = s.count('\n', 0, m.start()) + 1
        out.append((m.group(1), val, line))
    return out


def test_sozluk_girdisi_fallback_on_eki_degil():
    fallbacks = {}
    for p in FALLBACK_SOURCES:
        assert p.exists(), 'fallback kaynağı kayıp: %s' % p
        fallbacks.update(harvest_fallbacks(p))
    assert len(fallbacks) > 100, (
        'fallback hasadı beklenenden küçük (%d) — tarayıcı desenleri '
        'kaynaklarla uyumsuz olabilir' % len(fallbacks))
    kusur = []
    for dpath in DICTS:
        for key, val, line in dict_entries(dpath):
            fb = fallbacks.get(key)
            if fb is None or val == fb:
                continue
            if fb.startswith(val) and len(val) < len(fb):
                kusur.append('%s:%d  %s\n    sözlük: %r\n    tam   : %r' %
                             (dpath.name, line, key, val[:60], fb[:60]))
    assert not kusur, (
        'Parça-kopya kusuru: sözlük girdisi, kodun tam fallback metninin '
        'kesik ön eki (%d girdi). Girdiyi tam metinle değiştirin:\n%s'
        % (len(kusur), '\n'.join(kusur[:10])))


def test_bekci_kendini_yakalar():
    """Tautoloji karşıtı kanıt: hasat mekanizması bilinen bir tam fallback'i
    gerçekten çıkarabiliyor ve ön-ek karşılaştırması gerçekten çalışıyor.

    (Onarılmış vakanın ta kendisi: fea.busy'nin fallback'i çok parçalıdır;
    ilk parçası sözlükte dursaydı bu bekçi kırmızıya düşerdi.)"""
    fb = harvest_fallbacks(STATIC_JS / 'fea_panel.js')
    assert 'fea.busy' in fb
    tam = fb['fea.busy']
    ilk_parca = 'Running — the solver refines the mesh until the '
    assert tam.startswith(ilk_parca) and len(tam) > len(ilk_parca), (
        'fea.busy fallback birleştirmesi artık farklı — bekçinin kanıt '
        'vakasını güncelleyin')
