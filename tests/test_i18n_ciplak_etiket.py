"""Çıplak Isp/akı etiketlerinin geri dönmemesi (parti 33, 2026-08-18).

Defter borcu "ortak sözlükteki son çıplak Isp/akı etiketleri" beş anahtarı
sayıyordu: app.metric.isp, app.rep.ispLong, panel.thermal.cardQThroat,
panel.thermal.heatFluxSeries, panel.regen.cardPeakFlux. Parti 33 ölçümü:
beşi de HEM sözlüklerden HEM kullanımdan çoktan kalkmış (grep 0/0) ve
nitelikli ikizleri (ispDesign / *RefWall / *Balance) EN+TR mevcut —
satır eskimişti. Bu dosya kapanış kuralının bekçisidir: çıplak anahtar
geri gelirse ya da nitelikli ikizlerden biri silinirse kırmızı.

(Niteliğin NEDENİ: aynı panelde iki farklı fiziksel büyüklük aynı çıplak
adla basılıyordu — referans-cidar Bartz tasarım yükü ile denge-cidar
akısı, tasarım Isp'si ile teslim Isp'si. Ad, hangi büyüklük olduğunu
taşımak zorunda.)
"""

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
JS_DIR = REPO_ROOT / 'hrma' / 'static' / 'js'
TPL_DIR = REPO_ROOT / 'hrma' / 'templates'

CIPLAK = (
    'app.metric.isp',
    'app.rep.ispLong',
    'panel.thermal.cardQThroat',
    'panel.thermal.heatFluxSeries',
    'panel.regen.cardPeakFlux',
)

# Nitelikli halefler — silinirlerse çıplak ada dönüş baskısı doğar
NITELIKLI = (
    'app.metric.ispDesign',
    'panel.thermal.heatFluxSeriesRefWall',
    'panel.thermal.cardQThroatRefWall',
    'panel.regen.heatFluxSeriesBalance',
    'panel.regen.cardPeakFluxBalance',
)


def _dosyalar():
    out = list(JS_DIR.glob('*.js')) + list((JS_DIR / 'panels').glob('*.js'))
    out += list(TPL_DIR.glob('*.html'))
    assert len(out) > 20, 'tarama yüzeyi beklenenden küçük'
    return out


def test_ciplak_anahtarlar_geri_gelmedi():
    """Beş çıplak anahtar ne sözlük tanımı ne kullanım olarak var.

    Kelime sınırıyla aranır: nitelikli halefler (ör. app.metric.ispDesign)
    çıplak adın öneki olduğu için düz substring yanlış pozitif verirdi.
    """
    ihlaller = []
    for f in _dosyalar():
        icerik = f.read_text(encoding='utf-8', errors='replace')
        for anahtar in CIPLAK:
            for m in re.finditer(re.escape(anahtar), icerik):
                son = icerik[m.end():m.end() + 1]
                if re.match(r'[A-Za-z0-9_]', son or ''):
                    continue          # nitelikli halefin öneki
                satir = icerik.count('\n', 0, m.start()) + 1
                ihlaller.append('%s:%d %s' % (f.name, satir, anahtar))
    assert not ihlaller, (
        'çıplak Isp/akı anahtarı geri gelmiş (defter borcu yeniden '
        'açılır): %s' % ihlaller)


def test_nitelikli_ikizler_iki_dilde_de_duruyor():
    src = (JS_DIR / 'i18n_common.js').read_text(encoding='utf-8')
    for anahtar in NITELIKLI:
        n = len(re.findall(r"'%s':" % re.escape(anahtar), src))
        assert n >= 2, (
            'nitelikli anahtar %r iki dilde tanımlı değil (bulunan: %d) — '
            'silinirse çıplak ada dönüş baskısı doğar' % (anahtar, n))
