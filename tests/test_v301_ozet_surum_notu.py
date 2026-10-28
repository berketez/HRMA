"""v3.0.1 (26 Eki 2026) — proje listesindeki özet hangi sürümle hesaplandığını
söyler (NK-26).

Son kullanıcı testi: ana sayfa "Son Projeler" ve "Proje Aç" listesinde katı
örnek "Fpk 1642 N · Isp 140,1 s · It 3307 N·s" görünüyordu; açıp hesaplayınca
1499,7 N · 125,4 s · 3,0 kN·s çıktı. Özet eski bir sürümün koşusundan
geliyordu ve bu hiçbir yerde söylenmiyordu. (Eski örnek kopyalarının kendisi
ana modelin c2f98c91a tazelemesiyle düzeldi; bu bekçi kullanıcının KENDİ eski
projelerindeki özetin etiketini tutar.)
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
BAR = KOK / 'hrma' / 'static' / 'js' / 'project_bar.js'
NODE = shutil.which('node')


def _fonksiyon(src, ad):
    a = src.index('function ' + ad + '(')
    # gövdeyi süslü parantez sayarak çıkar
    i = src.index('{', a); d = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            d += 1
        elif src[j] == '}':
            d -= 1
            if d == 0:
                return src[a:j + 1]
    raise AssertionError(ad)


@pytest.mark.skipif(NODE is None, reason='node yok')
@pytest.mark.parametrize('simdi,ozet_surum,beklenen_ek', [
    ('3.0.1', '3.0.0', 'computed with v3.0.0'),
    ('3.0.1', None, 'computed with an older version'),
    ('3.0.1', '3.0.1', None),
    (None, '3.0.0', None),          # güncel sürüm bilinmiyorsa kıyas yok
])
def test_ozet_surum_notu(simdi, ozet_surum, beklenen_ek):
    src = BAR.read_text(encoding='utf-8')
    govde = '\n'.join(_fonksiyon(src, ad) for ad in ('nf', 'summaryMini'))
    ozet = {'peak_thrust_N': 1642.0, 'isp_s': 140.1, 'total_impulse_Ns': 3307.0}
    if ozet_surum:
        ozet['computed_with_version'] = ozet_surum
    betik = """
const window = { HRMA_APP_VERSION: %s };
function T(k, fb) { return fb; }
function TF(k, p, fb) { return fb.replace(/\\{(\\w+)\\}/g, (m, a) => p[a]); }
%s
process.stdout.write(JSON.stringify(summaryMini(%s)));
""" % (json.dumps(simdi), govde, json.dumps(ozet))
    # V3.0.5 T-ÇAPA-C1: betik stdin ile (tests/test_node_cagri_sozlesmesi.py).
    r = subprocess.run([NODE], input=betik, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-600:]
    metin = json.loads(r.stdout)
    assert metin.startswith('Fpk 1642 N · Isp 140.1 s · It 3307 N·s')
    if beklenen_ek:
        assert metin.endswith(' · ' + beklenen_ek)
    else:
        assert 'computed with' not in metin


def test_iki_dilde_sozlukte():
    js = (KOK / 'hrma' / 'static' / 'js' / 'i18n_common.js').read_text(encoding='utf-8')
    for k in ('proj.summaryOldVersion', 'proj.summaryVersionUnknown'):
        assert js.count("'" + k + "':") == 2, k
    tr = re.findall(r"'proj\.summaryOldVersion': '([^']*)'", js)[1]
    assert '{version}' in tr and 'hesaplandı' in tr
