# -*- coding: utf-8 -*-
"""ÖH D15 (ana model, 1 Eyl 2026) — /api/user-guide/open başsız koruma bekçisi.

Ölçüldü: 12-kulvar tam süiti koşarken bu uç test istemcisinden çağrılınca
sunucu makinesinde ``open <pdf>`` çalışıp Preview'da kılavuzu açtı (Berke'nin
ekran görüntüsü, 10:48). Test/başsız kipte GUI başlatılmamalı; yanıt bunu
adıyla söylemeli. Ters-mutasyon: koruma dalı silinince ``Popen`` ÇAĞRILIR.
"""
import os
import subprocess

import pytest


@pytest.fixture()
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _kilavuz_var():
    from hrma.app import _user_guide_path
    return bool(_user_guide_path('en'))


def test_testing_kipinde_gui_baslatilmaz(istemci, monkeypatch):
    cagri = []
    monkeypatch.setattr(subprocess, 'Popen',
                        lambda *a, **k: cagri.append(a) or None)
    r = istemci.post('/api/user-guide/open?lang=en')
    assert r.status_code == 200
    g = r.get_json()
    assert cagri == [], 'TESTING kipinde masaüstü görüntüleyici başlatıldı'
    assert g['opened'] is False
    if _kilavuz_var():
        assert g.get('reason') == 'headless'
        assert g.get('path')
    else:
        assert g.get('url')


def test_hrma_headless_ortami_da_korur(monkeypatch):
    from hrma.app import app
    monkeypatch.setitem(app.config, 'TESTING', False)
    monkeypatch.setenv('HRMA_HEADLESS', '1')
    cagri = []
    monkeypatch.setattr(subprocess, 'Popen',
                        lambda *a, **k: cagri.append(a) or None)
    r = app.test_client().post('/api/user-guide/open?lang=tr')
    assert r.status_code == 200
    assert cagri == []
    assert r.get_json()['opened'] is False
