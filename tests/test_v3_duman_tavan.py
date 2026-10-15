"""Yayın kapısı duman sunucularının gövde ve bağlantı tavanı bekçisi.

ÖH V3 yayın (REL D-3, 15 Eki 2026). Gövde, yayın kulvarının kanıt betiğinden
(``docs/scofield/raw/OH/V3/yayin/kanit/duman_tavan_bekcisi.py``) CI'a taşındı;
o betik docs/ altında olduğu için yayın dalında yoktur, bu dosya kanıt
dizinine bağlı DEĞİLDİR (yalnız ``packaging/`` ve ``.github/`` okur, ikisi de
yayın dalında durur).

``packaging/release_gate.sh`` ve ``.github/workflows/release.yml`` içindeki
duman sunucusu ``serve(...)`` çağrısı ürünle (``hrma/run.py``,
``run_windows.py``) AYNI tavanları vermeli:
``max_request_body_size = REQUEST_BODY_MAX_BYTES + 1`` ve
``connection_limit = WAITRESS_CONNECTION_LIMIT`` (tek kaynak
``hrma/security/body_limit.py``). Tavansız bir duman sunucusu, kapının
ölçtüğü davranışı ürünün davranışından ayırır.

İki ölçüm:
  A. AST: gömülü Python betiği (heredoc) ayrıştırılır; her ``serve`` çağrısı
     iki anahtarı tek kaynağın ADIYLA taşır; ``body_limit`` içe aktarması
     modül düzeyinde, ``try`` DIŞINDA (başarısızsa 'waitress yok' dalına
     düşüp tavansız sunucu kalkmaz).
  B. Sonda: betik GERÇEKTEN koşturulur. ``waitress`` yerine, aldığı anahtar
     argümanları JSON'a yazıp dönen bir sonda modülü ``PYTHONPATH``'in başına
     konur (ürün kodu taklit edilmez; yalnız sunucu çağrısının argümanları
     yakalanır). Yakalanan değerler tek kaynağın değerleriyle karşılaştırılır.
"""
import ast
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from hrma.security.body_limit import (REQUEST_BODY_MAX_BYTES,
                                      WAITRESS_CONNECTION_LIMIT)

KOK = Path(__file__).resolve().parents[1]

#: Duman sunucusu heredoc'unun başladığı satır (dosya başına tek).
DUMAN_BETIK_YERLERI = {
    'packaging/release_gate.sh': '"$PY" - "$PORT" <<\'PY\' &',
    '.github/workflows/release.yml':
        'python3 - "$PORT" > /tmp/duman_sunucu.log 2>&1 <<\'PY\' &',
}

#: Sonda koşusunun üst süresi (s). Sonda ``serve``i hemen döndürür; süre
#: yalnız ``hrma.app`` içe aktarmasına harcanır. Aşılırsa süreç öldürülür
#: (sonda tutmayıp Flask sunucusu kalkarsa test asılı kalmaz).
SONDA_SURE_TAVANI_S = 180

WAITRESS_SONDA_MODULU = '''
import json, os
def serve(app, **kw):
    kw.pop('_quiet', None)
    with open(os.environ['DUMAN_SONDA_CIKTI'], 'w') as f:
        json.dump({k: v for k, v in kw.items()
                   if isinstance(v, (int, str, float))}, f)
'''


def _betik(yol, baslangic):
    satirlar = (KOK / yol).read_text(encoding='utf-8').splitlines()
    i = [n for n, s in enumerate(satirlar) if s.strip() == baslangic]
    assert len(i) == 1, (
        '%s: duman sunucusu heredoc başlangıcı %d kez bulundu (beklenen 1): %r'
        % (yol, len(i), baslangic))
    j = next(n for n in range(i[0] + 1, len(satirlar))
             if satirlar[n].strip() == 'PY')
    return textwrap.dedent('\n'.join(satirlar[i[0] + 1:j])) + '\n'


def _adlar(dugum):
    return {n.id for n in ast.walk(dugum) if isinstance(n, ast.Name)}


@pytest.mark.parametrize('yol', sorted(DUMAN_BETIK_YERLERI))
def test_serve_tavanlari_tek_kaynaktan_ast(yol):
    agac = ast.parse(_betik(yol, DUMAN_BETIK_YERLERI[yol]))
    cagrilar = [n for n in ast.walk(agac) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == 'serve']
    assert cagrilar, '%s: duman betiğinde serve çağrısı yok' % yol
    for c in cagrilar:
        kw = {k.arg: k.value for k in c.keywords}
        assert 'REQUEST_BODY_MAX_BYTES' in _adlar(
            kw.get('max_request_body_size', ast.Constant(None))), (
            '%s: serve max_request_body_size tek kaynaktan değil (betik '
            'satırı %d)' % (yol, c.lineno))
        assert 'WAITRESS_CONNECTION_LIMIT' in _adlar(
            kw.get('connection_limit', ast.Constant(None))), (
            '%s: serve connection_limit tek kaynaktan değil (betik satırı %d)'
            % (yol, c.lineno))
    ust = [n for n in agac.body if isinstance(n, ast.ImportFrom)
           and n.module == 'hrma.security.body_limit']
    assert ust, ('%s: body_limit içe aktarması modül düzeyinde (try dışında) '
                 'değil; başarısızsa tavansız sunucu kalkar' % yol)


@pytest.mark.parametrize('yol', sorted(DUMAN_BETIK_YERLERI))
def test_serve_tavanlari_gercek_kosuda(yol, tmp_path):
    (tmp_path / 'waitress.py').write_text(WAITRESS_SONDA_MODULU,
                                          encoding='utf-8')
    cikti = tmp_path / 'kw.json'
    projeler = tmp_path / 'projeler'
    projeler.mkdir()
    env = dict(os.environ,
               PYTHONPATH=str(tmp_path) + os.pathsep + str(KOK),
               DUMAN_SONDA_CIKTI=str(cikti),
               HRMA_PROJECTS_DIR=str(projeler),
               BROWSER='echo')
    r = subprocess.run([sys.executable, '-', '0'],
                       input=_betik(yol, DUMAN_BETIK_YERLERI[yol]), text=True,
                       cwd=str(KOK), env=env, capture_output=True,
                       timeout=SONDA_SURE_TAVANI_S)
    assert cikti.exists(), ('%s: duman betiği serve çağırmadı (çıkış %d): %s'
                            % (yol, r.returncode, r.stderr[-600:]))
    kw = json.loads(cikti.read_text(encoding='utf-8'))
    assert kw.get('max_request_body_size') == REQUEST_BODY_MAX_BYTES + 1, (
        '%s: max_request_body_size=%r, beklenen %d'
        % (yol, kw.get('max_request_body_size'), REQUEST_BODY_MAX_BYTES + 1))
    assert kw.get('connection_limit') == WAITRESS_CONNECTION_LIMIT, (
        '%s: connection_limit=%r, beklenen %d'
        % (yol, kw.get('connection_limit'), WAITRESS_CONNECTION_LIMIT))
