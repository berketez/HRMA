"""Örnek ``.hrma`` dosyasının alanlarını sayfanın GÖNDERDİĞİ biçime indirir.

NEDEN (V301/T-ÇAPA-D, 28 Eki): V301/ÖRNEK kulvarı örnekleri gerçek sayfa
gövdesiyle yeniden üretti (5fa435893, 91dc5b780). Dosya artık sayfanın BÜTÜN
alanlarını taşıyor; kullanıcının boş bıraktığı isteğe bağlı alanlar dosyada
boş dizge (``''``) olarak duruyor (hibrit örnekte 15 alan, ör.
``contraction_ratio``). Sayfa bu alanları Hesapla gövdesine KOYMAZ —
ölçüldü: ``tests/support/kabul_sayfa_yukleri.py`` (gerçek tarayıcı hasadı,
27 Eki) hibrit ve sıvı gövdelerinde dosyada boş olan alanların HİÇBİRİ yok.
Dosyanın alan sözlüğünü olduğu gibi POST eden testler ``''``yi sayı alanına
gönderiyor ve uç (doğru olarak) ``invalid_input / not_a_json_number`` ile
400 veriyordu. Bu yardımcı sayfanın davranışını yineler: boş dizge alanı
gövdeye girmez. Sayı ya da seçim taşıyan alanlara dokunulmaz.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict


def sayfa_gibi(alanlar: Dict[str, Any]) -> Dict[str, Any]:
    """Boş dizge (``''``) alanları çıkarılmış KOPYA (sayfa boş alanı göndermez)."""
    return {k: v for k, v in alanlar.items() if v != ''}


def ornek_alanlari(yol: pathlib.Path) -> Dict[str, Any]:
    """Örnek dosyanın ``inputs.fields`` sözlüğü, sayfanın gönderdiği biçimde."""
    d = json.loads(pathlib.Path(yol).read_text(encoding='utf-8'))
    return sayfa_gibi(dict(d['inputs']['fields']))
