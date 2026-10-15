# -*- coding: utf-8 -*-
"""ÖH fix-13 — başsız kipte indirilen kurucu (.dmg/.exe) masaüstüne AÇILMAZ.

Ölçüldü (1 ve 3 Eyl 2026): bir test koşumu ``update_checker._open_installer``
üzerinden sahte bir ``.dmg``'yi ``open`` ile Finder'a verince Berke'nin
masaüstünde "disk görüntüsü bozulmuş" uyarısı çıktı. ``/api/user-guide/open``
aynı korumayı taşıyordu (6d1426c), kurucu açıcı taşımıyordu. Karar tek yerde:
``_headless()`` — HRMA_HEADLESS / PYTEST_CURRENT_TEST / HRMA_TESTING.
Ters mutasyon: ``_headless`` gövdesi ``return False`` yapılırsa
``test_basliksiz_kipte_popen_cagrilmaz`` KIRMIZI (Popen çağrılır).
"""
import os

import pytest

from hrma.utils import update_checker as uc


def test_pytest_altinda_basliksiz_sayilir():
    assert os.environ.get("PYTEST_CURRENT_TEST")
    assert uc._headless() is True


def test_basliksiz_kipte_popen_cagrilmaz(monkeypatch, tmp_path):
    cagri = []
    import subprocess

    def _yakala(*a, **k):
        cagri.append(a)
        raise AssertionError("başsız kipte masaüstü açılışı olmamalı")
    monkeypatch.setattr(subprocess, "Popen", _yakala)
    sahte = tmp_path / "HRMA-Setup-sahte.dmg"
    sahte.write_bytes(b"bu bir disk goruntusu degildir")
    sonuc = uc._open_installer(str(sahte))
    assert cagri == []
    assert sonuc == {"opened": False, "reason": "headless", "path": str(sahte)}


def test_manuel_kurulum_yaniti_acilmadigini_soyler(monkeypatch, tmp_path):
    """start_install manuel dalı: başsız kipte opened=False, open_reason='headless'; started (teslim) True."""
    sahte = tmp_path / "HRMA-Setup-sahte.dmg"
    sahte.write_bytes(b"x" * 64)
    with uc._download_lock:
        uc._download.update(state="done", pct=100, path=str(sahte), error="")
    from hrma.utils import self_install
    monkeypatch.setattr(self_install, "plan_install",
                        lambda path, installer_size=0: {"mode": "manual", "reason": "test"})
    sonuc = uc.start_install()
    assert sonuc["mode"] == "manual"
    assert sonuc["opened"] is False and sonuc["open_reason"] == "headless"
    assert sonuc["started"] is True
