"""3.0.6 (9 Kas, ana model) — enjektör Cd dayanağı TR ekranda İngilizce kalmaz.

Kusur (yerel tam süpürme, rc.1): hibrit örneğin TR ekranında enjektör
tablosunun 'Boşaltma Katsayısı Dayanağı' satırı sunucunun İngilizce
cümlesini AYNEN basıyordu (test_v301_dil_ekran::test_tr_ekranda_sizinti_yok
[ingilizce-hybrid]; L/D 1,23 → 'sharp inlet, reattaching ...'). Onarım:
satır, yanındaki 'Basınç Düşümü Dayanağı' gibi sunucu çeviri kanalından
(SRV → I18N.serverText) geçer; çeviri MSG_PATTERNS'teki tek desenle yapılır.

Bekçiler ürün kodunu koşar: girdiler ürünün KENDİ ``discharge_coefficient``
çıktısıdır (CD_TABLE'ın her satırı + tablo dışı iki uç), çeviri ürünün
i18n_charts.js dosyasından node altında yalıtılıp koşar. Fail-closed:
tanınmayan gerekçe ya da künye çevrilmez (metin AYNEN kalır).
"""
import json
import pathlib
import shutil
import subprocess

import pytest

from hrma.engines.injector_design import CD_TABLE, discharge_coefficient

KOK = pathlib.Path(__file__).resolve().parents[1]

# Betik node'a STDIN'den gider (argv'den değil: tests/test_node_cagri_sozlesmesi
# argv tavanı kuralı); girdi betiğin başına JSON olarak gömülür.
_KOSUM = r"""
const fs = require('fs'), vm = require('vm'), path = require('path');
const src = fs.readFileSync(path.join(girdi.kok, 'hrma/static/js/i18n_charts.js'), 'utf8');
const sb = { console: { log() {}, warn() {}, error() {} } };
sb.window = sb;
sb.I18N = { lang: 'tr', decimalText: (x) => String(x).replace('.', ',') };
vm.createContext(sb);
vm.runInContext(src, sb);
const out = { tr: [], en: [] };
for (const m of girdi.metinler) out.tr.push(sb.I18N.serverText(m));
sb.I18N.lang = 'en';
for (const m of girdi.metinler) out.en.push(sb.I18N.serverText(m));
process.stdout.write(JSON.stringify(out));
"""


def _cevir(metinler):
    node = shutil.which('node')
    if node is None:
        pytest.skip('node yok: i18n_charts.js koşamaz (gerekçeli atlama)')
    betik = ('const girdi = %s;\n' % json.dumps(
        {'kok': str(KOK), 'metinler': metinler}, ensure_ascii=False)) + _KOSUM
    p = subprocess.run([node], input=betik, capture_output=True,
                       text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


def _urun_dayanaklari():
    """Ürünün yayımladığı her Cd dayanak biçimi (tablo satırları + uçlar)."""
    out = []
    for tip, lo, hi, _cd, _neden in CD_TABLE:
        out.append(discharge_coefficient(tip, lo + 0.5 * (min(hi, lo + 2.0) - lo))[1])
    out.append(discharge_coefficient('sharp', 1.23093)[1])   # hibrit örnek
    out.append(discharge_coefficient('sharp', 150.0)[1])     # tablo dışı uç
    out.append(discharge_coefficient('radiused', 150.0)[1])
    return out


def test_her_cd_dayanagi_tr_ekranda_cevrilir():
    metinler = _urun_dayanaklari()
    s = _cevir(metinler)
    for eski, tr in zip(metinler, s['tr']):
        assert tr != eski, f'çevrilmedi: {eski}'
        assert 'giriş' in tr and ' → Cd=' in tr, tr
        for en in ('sharp inlet', 'radiused inlet', 'table value',
                   'outside table', 'Fig. ', '2nd ed.'):
            assert en not in tr, (en, tr)


def test_hibrit_ornek_dayanagi_sayilari_ondalik_kanonundan():
    s = _cevir([discharge_coefficient('sharp', 1.23093)[1]])
    assert 'L/D=1,23093 → Cd=0,78' in s['tr'][0], s['tr'][0]
    assert 'yeniden tutunan akış (L/D 1-5)' in s['tr'][0]


def test_en_dilinde_metin_aynen_kalir():
    metinler = _urun_dayanaklari()
    assert _cevir(metinler)['en'] == metinler


def test_taninmayan_gerekce_ya_da_kunye_cevrilmez():
    """Fail-closed: tablo dışı bir gerekçe/künye uydurma çeviri almaz."""
    bilinmeyen = [
        'sharp inlet, invented regime; L/D=2 -> Cd=0.7 (NASA SP-8089 (Gill & '
        'Nurick 1976) Fig. 13 p. 38 and Fig. 15 p. 43; Lefebvre & McDonell, '
        'Atomization and Sprays, 2nd ed., Ch. 5)',
        'radiused inlet (r/d >= 0.15): stable Cd; L/D=3 -> Cd=0.92 (some other '
        'source)',
    ]
    assert _cevir(bilinmeyen)['tr'] == bilinmeyen


def test_enjektor_tablosu_dayanagi_ceviri_kanalindan_basar():
    """Hibrit enjektör tablosunun dayanak satırı SRV'den geçer (ham String
    değil) — 'Pressure Drop Basis' satırıyla aynı kanal."""
    app = (KOK / 'hrma' / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')
    i = app.index("T('app.rep.cdBasis', 'Discharge Coefficient Basis')")
    satir = app[i:i + 200]
    assert 'SRV(String(injectorData.discharge_coefficient_basis))' in satir, satir
