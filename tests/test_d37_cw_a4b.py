"""ÖH D37 · CW-A4b — hibrit formu ``target_velocity`` için sessiz 30 m/s YAZMAZ.

ÖLÇÜLDÜ (24 Eyl 2026, main 718df0f2): ``advanced.html`` ``getFormData``
sonunda ``data.target_velocity = data.target_velocity || 30;`` vardı. Alan
boşken istemci 30 gönderiyor, uç (``app.py`` ``_uc_yedegi``) onu kullanıcının
değeri sandığı için ``defaults_applied`` künyesi çıkmıyordu (Cowork A-4 ek).
Ucun kendisi doğruydu: alan yok ya da ``''`` → 30 m/s künyeli
(``docs/scofield/raw/OH/D37/defter-h25/cw_a4b.json``; sunucu ayağının
bekçisi ``tests/test_d32_app_api_uc_a1.py``).

Bu dosya İSTEMCİ ayağını davranışla sınar: şablonun gerçek ``getFormData``
işlevi node'da, şablondan türetilmiş DOM ikiziyle koşturulur
(``tests/test_d36_hibrit_a1.py`` düzeneği aynen kullanılır).
"""
from __future__ import annotations

import pytest

from tests.test_d36_hibrit_a1 import NODE, _govde


@pytest.mark.skipif(NODE is None, reason='node yok')
class TestCwA4bIstemci:
    def test_bos_alan_govdeye_girmez(self):
        """Şablondaki boş ``target_velocity`` gövdeye hiç girmez; uç
        varsayılanını adıyla beyan edebilsin diye."""
        govde = _govde()
        assert 'target_velocity' not in govde, (
            'istemci boş target_velocity için değer yazdı: %r'
            % govde.get('target_velocity'))

    def test_kullanici_degeri_aynen_gider(self):
        """Kullanıcının girdiği değer değişmeden gider (kapı yalnız boşu
        düşürür, sayıyı ezmez)."""
        govde = _govde(deger={'target_velocity': 45})
        assert govde.get('target_velocity') == 45

    def test_sifir_verilmedi_sayilmaz(self):
        """``0`` geçerli bir girdidir; ``|| 30`` deseni onu 30'a çevirirdi.
        Uç 0'ı kendi bant kapısıyla değerlendirir, istemci ezmez."""
        govde = _govde(deger={'target_velocity': 0})
        assert govde.get('target_velocity') == 0
