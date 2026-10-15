"""ÖH D36 · kabuk sayfaları piksel turu bekçileri (OH-K-01..04, ana model, 22 Eyl 2026).

Ölçülen kusurlar (Playwright, birleşik main 06718d43, TR ve EN, 1440 ve 390 px):
- OH-K-01 /uzaytek: gizli tooltip'ler (visibility:hidden, 300 px, mutlak) yerleşimde
  yer tutuyordu → scrollWidth 1471 (1440 px'te), 463 (390 px'te); yatay kaydırma.
- OH-K-02 /simple: köken notu satır içi <span>; 390 px'te "Mixed" sağda tek başına,
  gerisi solda (x=43'e dönüyor).
- OH-K-03 /formulas: 390 px'te menü tek satır (954 px), satır içi MathJax 413 px,
  değişken tablosu 368 px → scrollWidth 722.
- OH-K-04 /launch-site: TR'de "0.0 s", "28.608°N" (noktalı okuma).

Bekçiler kaynağı DOSYADAN okur (inspect.getsource yok); OH-K-04 için yardımcı
node ile gerçekten koşturulur.

OH-K-01 ve OH-K-02 bekçileri emekli: iki sayfa ÖH D36'da söküldü (Berke,
23 Eyl 2026, dalga36/sokum); geri dönüş bekçisi tests/test_d36_sokum_a1.py.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
SABLON = KOK / 'hrma' / 'templates'


def _oku(ad: str) -> str:
    return (SABLON / ad).read_text(encoding='utf-8')


def _blok(metin: str, secici: str) -> str:
    """`secici {` ile başlayan ilk CSS bloğunun gövdesi."""
    m = re.search(re.escape(secici) + r'\s*\{([^}]*)\}', metin)
    assert m, f'{secici!r} bloğu yok'
    return m.group(1)


# OH-K-01 (/uzaytek tooltip, 3 düğüm) + OH-K-02 (/simple köken notu, 2 düğüm) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum


class TestOHK03FormulasDarEkran:
    def test_menu_sarar(self):
        metin = _oku('formulas.html')
        m = re.search(r'@media \(max-width: 768px\)\s*\{(.*?)</style>', metin, re.S)
        assert m, '768 px medya bloğu yok'
        assert re.search(r'\.nav-links\s*\{[^}]*flex-wrap: wrap', m.group(1))
        assert re.search(r'\.variable-table\s*\{[^}]*overflow-x: auto', m.group(1))

    def test_formul_kutusu_kendi_icinde_kayar(self):
        metin = _oku('formulas.html')
        assert 'overflow-x: auto' in _blok(metin, '.formula-box')
        assert re.search(r'\.formula-box mjx-container\s*\{[^}]*display: inline-block;[^}]*overflow-x: auto', metin)


class TestOHK04LaunchSiteSayiBicimi:
    def test_metin_okumalarinda_toFixed_kalmadi(self):
        metin = _oku('launch_site.html')
        kalan = [s for s in metin.splitlines()
                 if re.search(r'(textContent|innerText)\s*=.*\.toFixed\(', s)]
        assert kalan == [], f'metne doğrudan toFixed basan satır kaldı: {kalan}'
        for ad in ('fmtLat', 'fmtLon', 'fmtKmM', 'fmtDist'):
            govde = re.search(r'function ' + ad + r'\([^)]*\)\s*\{(.*?)\n\s*\}', metin, re.S)
            assert govde and 'fmtNum_' in govde.group(0), f'{ad} fmtNum_ kullanmıyor'
        assert "e.textContent = fmtNum_(0, 1) + ' s'" in metin

    @pytest.mark.skipif(shutil.which('node') is None, reason='node yok')
    def test_yardimci_tr_de_virgul_en_de_nokta(self):
        metin = _oku('launch_site.html')
        m = re.search(r'function fmtNum_\(v, digits\)\s*\{(.*?)\n    \}', metin, re.S)
        assert m
        js = ('var I18N = { number: function (v, d) { return v.toFixed(d).replace(".", ","); } };'
              'var window = { I18N: I18N };'
              'function fmtNum_(v, digits) {' + m.group(1) + '\n}'
              'var tr = fmtNum_(0, 1) + " s";'
              'window.I18N = undefined; var en = fmtNum_(28.6084, 3);'
              'console.log(JSON.stringify({tr: tr, en: en}));')
        out = subprocess.run(['node'], input=js, capture_output=True, text=True,
                             check=True).stdout
        sonuc = json.loads(out)
        assert sonuc == {'tr': '0,0 s', 'en': '28.608'}


class TestOHK05SozlukIsaretlemesi:
    """OH-K-05: sözlük değeri HTML etiketi taşıyan her `data-i18n` anahtarı,
    şablonda `data-i18n-html` ile işaretli bir düğümde olmalı; uygulayıcı bu
    işaretle innerHTML, aksi hâlde textContent basmalı (ölçüldü: 64 harfiyen
    etiket, iki dilde de)."""

    ETIKET = re.compile(r'<(em|strong|code|sup|sub|br|i|b|span|a)\b[^>]*>')

    def _html_anahtarlar(self):
        anahtar = set()
        for f in (KOK / 'hrma' / 'static' / 'js').glob('i18n_*.js'):
            for m in re.finditer(r"""(['"])([a-zA-Z0-9_.]+)\1:\s*(['"])((?:[^'"\\]|\\.|(?!\3)['"])*)\3""",
                                 f.read_text(encoding='utf-8')):
                if self.ETIKET.search(m.group(4)):
                    anahtar.add(m.group(2))
        return anahtar

    def test_uygulayici_html_dalini_yalniz_isaretle_acar(self):
        js = (KOK / 'hrma' / 'static' / 'js' / 'i18n.js').read_text(encoding='utf-8')
        assert "(el.getAttribute('data-i18n-html') != null) && !params" in js
        assert 'if (html) el.innerHTML = text; else el.textContent = text;' in js

    def test_html_tasiyan_anahtarlar_sablonda_isaretli(self):
        anahtar = self._html_anahtarlar()
        assert anahtar, 'tarama boş — regex kırıldı'
        eksik = []
        for sablon in SABLON.glob('*.html'):
            s = sablon.read_text(encoding='utf-8')
            for m in re.finditer(r'<[a-z0-9]+\b([^>]*)\bdata-i18n="([^"]+)"([^>]*)>', s):
                if m.group(2) in anahtar and 'data-i18n-html' not in (m.group(1) + m.group(3)):
                    eksik.append(f'{sablon.name}: {m.group(2)}')
        assert eksik == [], 'HTML taşıyan anahtar işaretsiz düğümde: ' + ', '.join(eksik)

    def test_formulas_bes_not_isaretli(self):
        s = _oku('formulas.html')
        assert len(re.findall(r'data-i18n="fx\.[a-z0-9_.]+" data-i18n-html>', s)) >= 5


class TestOHK06MotorSayfalariDarEkranMenu:
    """OH-K-06: 390 px'te /hybrid, /solid, /liquid menüsü 924 px'e uzuyor,
    sayfa 944 px'e genişliyordu; ortak theme.css'te sarma kuralı."""

    def test_theme_css_dar_ekranda_menu_sarar(self):
        css = (KOK / 'hrma' / 'static' / 'css' / 'theme.css').read_text(encoding='utf-8')
        m = re.search(r'@media \(max-width: 768px\)\s*\{(.*?)\n\}', css, re.S)
        assert m, 'theme.css 768 px medya bloğu yok'
        assert re.search(r'\.nav-links\s*\{[^}]*flex-wrap: wrap', m.group(1))
        assert re.search(r'\.navbar\s*\{[^}]*flex-wrap: wrap', m.group(1))
