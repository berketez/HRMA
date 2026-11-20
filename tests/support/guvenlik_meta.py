# -*- coding: utf-8 -*-
"""V307/KÜÇÜKLER (kalem 6): GÜVENLİK panelinin zorunlu alan kümesi — GERÇEK
şablonun (sıvı sayfası) bastığı ``<meta name="hrma-safety-required">``
içeriği. Node düzenekleri bunu ``HRMA_SAFETY_META`` ortam değişkeniyle
``tests/support/meta_guvenlik.js`` taşıyıcısına verir."""
import functools
import html
import re

TASIYICI = 'tests/support/meta_guvenlik.js'
KALIP = r"""<meta name="hrma-safety-required" content='([^']*)'>"""


@functools.lru_cache(maxsize=1)
def guvenlik_metasi():
    from hrma.app import app
    r = app.test_client().get('/liquid', headers={'Host': '127.0.0.1:8080'})
    assert r.status_code == 200
    m = re.search(KALIP, r.get_data(as_text=True))
    assert m, 'sıvı sayfası hrma-safety-required etiketini basmıyor'
    return html.unescape(m.group(1))


def ortam(taban=None):
    """``taban`` (yoksa os.environ) + HRMA_SAFETY_META."""
    import os
    o = dict(os.environ if taban is None else taban)
    o['HRMA_SAFETY_META'] = guvenlik_metasi()
    return o
