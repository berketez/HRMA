"""v3.0.1 N-girdi-1 bekçisi — her güverte girdisinin yanında açıklama.

Berke (26 Eki 2026): "Her bir inputun yanında açıklaması olmalı, istisnasız."

Bu dosya üç şeyi ölçer:
  (a) analiz güvertesinin BÜTÜN alan tanımları (panels/*.js alan dizileri,
      feed panelinin sekme alanları) 6. eleman olarak bir ipucu anahtarı
      taşır, panellerin kendi girdileri (comparative / uncertainty /
      validation) ipucu basar; her anahtar i18n_common.js EN ve TR
      bloklarında tanımlı ve boş değil;
  (b) ``fieldHtml`` ipucu ikonunu ortak bileşenle (field_help.js →
      HRMAHelp) gerçekten basar (node altında, ürün kodu yalıtılıp koşar);
  (c) balon CSS'i tek kaynakta ve gizliyken sayfa genişliğine katılmaz
      (statik kural) + kayıtlı Chromium ölçümü (kanıt dizini).

Kanıt: docs/scofield/raw/OH/V301/girdi-aciklama/ (RAPOR.md, olcum.py,
balon.py, önce/sonra json). Ters mutasyon: bir alanın anahtarı silinince
(a) KIRMIZI — RAPOR.md'de kayıtlı.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from tests.support.kanit import kanit_gerekli

ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = ROOT / 'hrma' / 'static' / 'js'
PANELS = JS / 'panels'
TEMA = ROOT / 'hrma' / 'static' / 'css' / 'theme.css'
IPUCU_SABLONLARI = [ROOT / 'hrma' / 'templates' / a for a in ('liquid.html', 'solid.html', 'advanced.html')]
# T-ÇAPA-C2 (27 Eki): ölçüm dosyaları büyük (0,8 MB) — docs'ta kalır, okuma
# kanit_gerekli kapısından. Kanıt tarayıcısı ``kanit_yolu('docs/…')`` dize
# tohumunu kapı dışı okuma sayıyor (test_harita_k4 deseni): yol parçalarla
# kurulur, okumadan hemen önce kapıdan geçer.
KANIT = (pathlib.Path(__file__).resolve().parents[1] / 'docs' / 'scofield'
         / 'raw' / 'OH' / 'V301' / 'girdi-aciklama')
NODE = shutil.which('node')

#: Alan dizisi taşıyan güverte panelleri ve dizi başlangıç desenleri.
DOCK_PANELLERI = {
    'structural_panel.js': [r'\n        fields: \['],
    'thermal_panel.js': [r'\n        fields: \['],
    'safety_panel.js': [r'const FIELDS = \['],
    'performance_panel.js': [r'const PERF_FIELDS = \[', r"fields: \[(?=\['analysis_type')"],
    'vessel_panel.js': [r'\n        fields: \['],
    'protection_panel.js': [r'\n        fields: \['],
    'joint_panel.js': [r'\n        fields: \['],
    'flow_panel.js': [r'\n        fields: \['],
    'cooling_panel.js': [r'\n        fields: \['],
    'feed_panel.js': [r'\n            fields: \['],
}

#: Panellerin kendi işaretlemesindeki girdiler ⟷ ipucu anahtarı.
KENDI_GIRDILER = {
    'comparative_panel.js': {'cmp_name': 'panel.comparative.help.name',
                             'cmp_ov_a': 'panel.comparative.help.overlayA',
                             'cmp_ov_b': 'panel.comparative.help.overlayB'},
    'uncertainty_panel.js': {'uq_level': 'panel.uncertainty.help.level',
                             'uq_seed': 'panel.uncertainty.help.seed'},
    'validation_panel.js': {'vp_csv_text': 'panel.validation.help.csv'},
}

ANAHTAR = re.compile(r"^panel\.[A-Za-z]+\.help\.[A-Za-z0-9_.]+$")


def _esle(s, i):
    """s[i] == '['; eşleşen ']' indeksini döndürür (dize/yorum atlanır)."""
    d = 0
    j = i
    while j < len(s):
        c = s[j]
        if c in '\'"`':
            q = c
            j += 1
            while s[j] != q:
                if s[j] == '\\':
                    j += 1
                j += 1
        elif s.startswith('//', j):
            j = s.index('\n', j)
        elif s.startswith('/*', j):
            j = s.index('*/', j) + 1
        elif c == '[':
            d += 1
        elif c == ']':
            d -= 1
            if d == 0:
                return j
        j += 1
    raise AssertionError('kapanmayan dizi')


def _ust_elemanlar(s, a, b):
    out = []
    j = a + 1
    while j < b:
        c = s[j]
        if c in '\'"`':
            q = c
            j += 1
            while s[j] != q:
                if s[j] == '\\':
                    j += 1
                j += 1
        elif s.startswith('//', j):
            j = s.index('\n', j)
        elif s.startswith('/*', j):
            j = s.index('*/', j) + 1
        elif c == '[':
            e = _esle(s, j)
            out.append(s[j:e + 1])
            j = e
        j += 1
    return out


def alan_tanimlari():
    """[(dosya, alan_id, ipucu_anahtari|None)] — ürün kaynağından."""
    sonuc = []
    for dosya, desenler in DOCK_PANELLERI.items():
        s = (PANELS / dosya).read_text(encoding='utf-8')
        bulunan = 0
        for desen in desenler:
            for m in re.finditer(desen, s):
                a = m.end() - 1
                for el in _ust_elemanlar(s, a, _esle(s, a)):
                    fid = re.match(r"\[\s*'([^']+)'", el).group(1)
                    dizeler = re.findall(r"'((?:[^'\\]|\\.)*)'", el)
                    son = dizeler[-1] if dizeler else None
                    sonuc.append((dosya, fid, son if son and ANAHTAR.match(son) else None))
                    bulunan += 1
        assert bulunan, '%s: alan dizisi bulunamadı (desen kaydı bayat)' % dosya
    return sonuc


@pytest.fixture(scope='module')
def sozluk():
    if NODE is None:
        pytest.skip('node kurulu değil')
    betik = ("global.window = global; require(%s);"
             "process.stdout.write(JSON.stringify(global.__I18N_PENDING[0]));"
             % json.dumps(str(JS / 'i18n_common.js')))
    # V3.0.5 T-ÇAPA-C1: betik stdin ile (tests/test_node_cagri_sozlesmesi.py).
    r = subprocess.run([NODE], input=betik, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


# --- (a) alan tanımları + sözlük ------------------------------------------

def test_alan_dizisi_sayisi_daralmadi():
    """Ayrıştırıcı körleşirse (0 alan) bekçi sahte yeşil verir — taban sayı."""
    tanimlar = alan_tanimlari()
    # 26 Eki ölçümü: 9 güverte paneli 123 alan tanımı (performans iki
    # kaydı tek dizi + katı seçicisi) → kaynakta 111 + feed 26 = 137 öğe.
    assert len(tanimlar) >= 137, len(tanimlar)


def test_her_guverte_alaninda_ipucu_anahtari_var():
    eksik = ['%s:%s' % (d, f) for d, f, k in alan_tanimlari() if not k]
    assert not eksik, ('ipucu anahtarı (alan tanımının 6. elemanı) olmayan '
                       'güverte alanları: %s' % eksik)


def test_ipucu_anahtarlari_en_ve_tr_sozlukte(sozluk):
    anahtarlar = {k for _, _, k in alan_tanimlari() if k}
    for d in KENDI_GIRDILER.values():
        anahtarlar.update(d.values())
    for dil in ('en', 'tr'):
        eksik = sorted(k for k in anahtarlar if not (sozluk[dil].get(k) or '').strip())
        assert not eksik, '%s sözlüğünde yok/boş: %s' % (dil, eksik)


def test_tr_ipucu_ingilizce_kopya_degil(sozluk):
    anahtarlar = [k for k in sozluk['en'] if '.help.' in k and k.startswith('panel.')]
    assert len(anahtarlar) >= 143, len(anahtarlar)
    ayni = [k for k in anahtarlar if sozluk['en'][k] == sozluk['tr'][k]]
    assert not ayni, ayni
    turkce = re.compile('[çğıİöşüÇĞÖŞÜ]')
    harfsiz = [k for k in anahtarlar if not turkce.search(sozluk['tr'][k])]
    assert not harfsiz, ('TR ipucunda hiç Türkçe harf yok (ASCII kaçışı?): %s' % harfsiz)


def test_panellerin_kendi_girdileri_ipucu_basar():
    for dosya, girdiler in KENDI_GIRDILER.items():
        s = (PANELS / dosya).read_text(encoding='utf-8')
        for gid, anahtar in girdiler.items():
            i = s.index('id="%s"' % gid)
            # girdinin bulunduğu .form-group bloğu: önceki '<div class="form-group' ile
            bas = s.rindex('class="form-group', 0, i)
            assert "helpHtml('%s')" % anahtar in s[bas:i], (
                '%s: %s girdisinin form grubunda %s ipucu yok' % (dosya, gid, anahtar))


def test_feed_fieldHtml_ipucu_basar():
    s = (PANELS / 'feed_panel.js').read_text(encoding='utf-8')
    govde = s[s.index('function fieldHtml(tabKey, f)'):]
    govde = govde[:govde.index('\n    }\n') + 6]
    assert 'helpHtml(f[5])' in govde and govde.count('+ head') == 2, govde


# --- (b) fieldHtml ikonu basar (node) -------------------------------------

def _govde(src, ad):
    m = re.search(r'function\s+%s\s*\(' % re.escape(ad), src)
    i = src.index('{', m.end() - 1)
    d = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            d += 1
        elif src[j] == '}':
            d -= 1
            if d == 0:
                return src[m.start():j + 1]
    raise AssertionError(ad)


def test_fieldHtml_ipucu_ikonunu_ortak_bilesenle_basar():
    if NODE is None:
        pytest.skip('node kurulu değil')
    dock = (JS / 'analysis_dock.js').read_text(encoding='utf-8')
    betik = """
'use strict';
global.window = global;
require(%s);
function i18nAttr(k) { return k ? ' data-i18n="' + k + '"' : ''; }
function T(k, fb) { return k === 'panel.x.help.pc' ? 'Basınç <b>"açıklama"</b>' : fb; }
function escAttr(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function fieldDomId(p, f) { return 'ad_f_' + p + '_' + f; }
function fieldSourceSlotId(p, f) { return 'ad_src_' + p + '_' + f; }
%s
var ile = fieldHtml('x', ['pc', 'Pc', 20, 0.1, 'common.f.pc', 'panel.x.help.pc']);
var sec = fieldHtml('x', ['m', 'M', 'a', [['a', 'A', null]], null, 'panel.x.help.pc']);
var siz = fieldHtml('x', ['pc', 'Pc', 20, 0.1, 'common.f.pc']);
process.stdout.write(JSON.stringify({ile: ile, sec: sec, siz: siz}));
""" % (json.dumps(str(JS / 'field_help.js')), _govde(dock, 'fieldHtml'))
    r = subprocess.run([NODE, '-'], input=betik, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout)
    for ad in ('ile', 'sec'):
        h = out[ad]
        assert 'class="tooltip-icon" tabindex="0"' in h, h
        assert 'class="tooltip-text" role="tooltip" data-i18n="panel.x.help.pc"' in h, h
        # metin kaçışlı basılır (HTML enjeksiyonu yok)
        assert '&lt;b&gt;&quot;açıklama&quot;&lt;/b&gt;' in h, h
        # ikon etiketin ARDINDA, kaynak çipi yuvasından ÖNCE
        assert h.index('</label>') < h.index('tooltip-icon') < h.index('ad-src-slot'), h
    assert 'tooltip' not in out['siz'], 'anahtarsız alana ipucu uydurulmamalı'


# --- (c) balon CSS'i tek kaynakta, gizliyken taşmaz ------------------------

def _kural(metin, secici):
    i = metin.index(secici + ' {')
    return metin[i:metin.index('}', i)]


def test_balon_css_tek_kaynakta_ve_gizliyken_boyutsuz():
    tema = TEMA.read_text(encoding='utf-8')
    bolum = tema[tema.index('/* ---------------- Alan ipucu (ortak bileşen)'):]
    gizli = _kural(bolum, '.tooltip-text')
    assert 'visibility: hidden;' in gizli and 'transform: scale(0);' in gizli, gizli
    acik = bolum[bolum.index('.tooltip:hover .tooltip-text,'):]
    acik = acik[:acik.index('}')]
    assert '.tooltip:focus-within .tooltip-text' in acik, 'klavyeyle açılmıyor'
    assert 'transform: scale(1);' in acik and 'visibility: visible;' in acik, acik
    for sablon in IPUCU_SABLONLARI:
        s = sablon.read_text(encoding='utf-8')
        stil = s[s.index('<style>'):s.index('</style>')]
        assert not re.search(r'^\s*\.tooltip-text\s*\{', stil, re.M), (
            '%s: ipucu CSS kopyası geri gelmiş (tek kaynak theme.css)' % sablon.name)
        assert s.index('/static/js/field_help.js') < s.index('/static/js/analysis_dock.js'), (
            '%s: field_help.js güverteden ÖNCE yüklenmeli' % sablon.name)


def test_field_help_acik_balonu_ekran_icine_hizalar():
    s = (JS / 'field_help.js').read_text(encoding='utf-8')
    place = _govde(s, 'place')
    assert "balon.style.position = 'fixed'" in place
    assert 'Math.max(orta - w / 2, KENAR)' in place and 'vw - w - KENAR' in place, (
        'sol ve sağ kenar kıskacı yok')


# --- (d) kayıtlı Chromium ölçümü --------------------------------------------

@pytest.mark.parametrize('dil', ['tr', 'en'])
def test_kayitli_olcum_kapsamda_aciklamasiz_yok_ve_tasma_yok(dil):
    yol = kanit_gerekli(KANIT / ('sonra_olcum_%s.json' % dil))
    d = json.loads(pathlib.Path(yol).read_text(encoding='utf-8'))
    for ad, dd in d['sayfalar'].items():
        for an in ('once', 'sonra'):
            g = dd[an]['girdi']
            kapsam = [x for x in g if (x['id'] or '').startswith('ad_f_')
                      or (x['panel'] or '').startswith('ad_sec_')]
            assert kapsam, (ad, an)
            acik = [x['id'] for x in kapsam if not (x['tooltip'] or x['title'] or x['help'])]
            assert not acik, (dil, ad, an, acik)
            tas = {w: v['tasma'] for w, v in dd[an]['tasma'].items()}
            assert set(tas) == {'1024', '1280', '1366', '1440', '1920'}
            assert all(t == 0 for t in tas.values()), (dil, ad, an, tas)


@pytest.mark.parametrize('dil', ['tr', 'en'])
def test_kayitli_olcum_acik_balon_iki_kenarda_da_ekran_icinde(dil):
    yol = kanit_gerekli(KANIT / ('balon_son_%s.json' % dil))
    d = json.loads(pathlib.Path(yol).read_text(encoding='utf-8'))
    for ad, dd in d['sayfalar'].items():
        for an, v in dd.items():
            if not isinstance(v, dict):
                continue
            for w, x in v.items():
                assert x['ortak'] and x['sayi'] > 0, (ad, an, w)
                for k in ('sol_tasan_sayi', 'sag_tasan_sayi', 'ust_tasan_sayi', 'ortulen_sayi'):
                    assert x[k] == 0, (dil, ad, an, w, k, x[k])
