"""İçerik Güvenliği Politikası (CSP) — tek kaynak (V3 SG-2 Bölüm B / SG-04).

``hrma/app.py::_add_security_headers`` bu değeri her yanıta
``Content-Security-Policy`` olarak koyar; başka bir yerde ikinci kopya
YOKTUR.

ÖNCE (SG-0, ``docs/scofield/raw/OH/V3/guvenlik/SG0_saldiri_yuzeyi.md``
SG-04): politika yalnız ``frame-ancestors 'none'`` idi; bir DOM-XSS olursa
(SG-05) CSP onu durdurmazdı.

BU TURDA EKLENEN İKİ YÖNERGE (arayüzü bozmadığı gerçek tarayıcıda
ölçüldü: ``docs/scofield/raw/OH/V3/guvenlik/sg2b/sonuc/csp_*.json``):

* ``object-src 'none'`` — ``<object>`` / ``<embed>`` ile eklenti yüklemesi
  yok. Ürün bu öğeleri hiç kullanmıyor (şablon ve JS taraması: 0); PDF'ler
  ek olarak indirilir, sayfaya gömülmez.
* ``base-uri 'none'`` — enjekte edilmiş bir ``<base href>`` göreli betik
  ve form adreslerini başka kökene çeviremez. Ürün ``<base>`` kullanmıyor.

BİLEREK EKLENMEYEN: ``script-src``. Şablonlarda satır içi ``<script>``
blokları ve ``onclick=`` gibi satır içi olay nitelikleri var; ``'self'``
bunları keser. Nonce'a ya da dış dosyaya taşıma v3.1 kartıdır (envanter
ve ölçüm: ``docs/scofield/raw/OH/V3/guvenlik/SG2_rapor.md`` Bölüm B).
``'unsafe-inline'`` ile bir ``script-src`` koymak koruma vermeden koruma
varmış gibi görünür; o yüzden hiç konmadı.
"""

#: Sayfa başka bir sayfanın çerçevesine gömülemez (tıklama hırsızlığı).
FRAME_ANCESTORS = "frame-ancestors 'none'"

#: Eklenti / ``<object>`` / ``<embed>`` yüklemesi yok.
OBJECT_SRC = "object-src 'none'"

#: ``<base>`` etiketiyle göreli adres kaçırma yok.
BASE_URI = "base-uri 'none'"

#: Yanıtlara konan tam politika (yönergeler ``; `` ile birleşir).
CONTENT_SECURITY_POLICY = '; '.join((FRAME_ANCESTORS, OBJECT_SRC, BASE_URI))
