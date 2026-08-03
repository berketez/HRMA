"""Tarayıcı denetim iskelesi — sürüm başına GÖRSEL kapı.

Faz 6'da ``/hybrid``, ``/solid`` ve ``/liquid`` sayfaları Playwright ile ELLE
gezildi; bulunan kusurların büyüğü (boş kalan 3B tuval, çizilmeyen egzoz,
ekrana sızan ``[object Object]``) hiçbir birim testinin GÖRMEDİĞİ yerdeydi.
Bu paket o gezintiyi depoya kalıcı bir araca çevirir: aynı adımlar her
sürümde makinece koşar, hüküm JSON rapora yazılır.

Modüller
--------
``esikler``    Sayısal eşiklerin TEK kaynağı (hardcode çoğaltma yasak).
``sayfalar``   Hangi sayfada hangi düğmeye basılacağı, ne bekleneceği.
``denetimler`` Ölçümden HÜKME geçen saf fonksiyonlar — tarayıcı gerektirmez,
               bu yüzden ``tests/test_browser_harness.py`` hepsini sınar.
``sunucu``     ``python -m hrma.run`` alt sürecinin ömrü (mutlaka öldürülür).
``tur``        Playwright etkileşimi: yalnız ÖLÇER, hüküm vermez.
``run_tour``   Komut satırı arayüzü + rapor yazımı.

Ayrım bilinçli: ölçüm (tarayıcı) ile hüküm (saf fonksiyon) ayrı durduğu için
eşikler tarayıcı açmadan sınanabilir ve raporun her sayısı ``dayanak``
alanıyla nereden geldiğini söyler.
"""
