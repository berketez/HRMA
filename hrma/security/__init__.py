"""HRMA güvenlik kapıları (V3 SG-2).

Neden ayrı bir paket: karar §28-33 (Berke, 12 Eki) güvenlik ve kararlılığı
HRMA'nın TEMEL İLKESİ sayar; SG kulvarlarının bulduğu açıklar özellik
eksiği değil kusurdur. Aynı gün ``hrma/app.py``'ye başka v3.0 kulvarları da
dokunuyor (CAD dışa aktarım kapısı, CFDS runtime_basis, termal/hibrit
yamaları). Çakışmayı en aza indirmek için güvenlik mantığı burada yaşar;
``app.py`` yalnız çağırır.

Modüller:

* ``origin_gate`` — köken kapısı: durum değiştiren isteklerde ve yan etkili
  GET uçlarında ``Origin`` / ``Sec-Fetch-Site`` denetimi; sunucunun gerçek
  portunun tek kayıt noktası (SG-02, SG-06).
* ``limits`` — istek başına kalem sayısı tavanları (SG-03) ve gövde bayt
  tavanının her uçta JSON 413 beyanı (SG-07); ikisi de 413.
* ``csp`` — İçerik Güvenliği Politikası değerinin tek kaynağı (SG-04).

Bu paket Flask'a bağımlı DEĞİLDİR: fonksiyonlar düz değer alır (yöntem,
uç adı, başlık eşlemesi, port), böylece kapı ``test_client`` olmadan da
birim düzeyinde ölçülebilir.
"""
