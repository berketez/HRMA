"""İstek gövdesi bayt tavanının TEK KAYNAĞI (V3 SG-2 bölüm C, SG-07 c).

``hrma/app.py`` bu sayıyı ``app.config['MAX_CONTENT_LENGTH']`` olarak
kurar; gövde kapıları (:mod:`hrma.security.limits`) tavanı oradan okur.
STEP yükleme ucu (``hrma/importers/step_api.py::MAX_UPLOAD_BYTES``) da
AYNI sayıyı buradan alır.

KUSUR (beyan ⟷ gerçek): ``step_api.MAX_UPLOAD_BYTES`` 50 MiB beyan
ediyordu ("büyük montaj STEP'leri"), oysa genel tavan 32 MiB ve her istekte
ÖNCE çalışır (``app.py::_reject_oversized_body``). 32 MiB üstündeki STEP
yüklemesi genel 413'ü alır; STEP ucunun kendi "limit 50 MB" kapısı hiçbir
istekte ateşlenemez, kullanıcıya söylenen sınır yanlıştı.

GEÇERLİ DEĞER 32 MiB, gerekçe:

* Genel tavan bir GÜVENLİK bütçesidir (v2.6.2): her uç için bellekte
  okunabilecek en büyük gövdeyi sınırlar. STEP için yükseltmek bütün
  uçların saldırı yüzeyini büyütürdü; ucun kendi beyanını gerçeğe çekmek
  hiçbir şeyi gevşetmez.
* Meşru STEP boyutu bunun çok altında: depodaki en büyük STEP çıktısı
  0,40 MB (sıvı örnek motorun ``*_assembly.step`` montajı, 396 711 bayt); ``step_api``'nin
  kendi gerekçesi "büyük montaj STEP'leri dahi metin olarak genelde 10-20
  MB" diyor. 32 MiB bu üst ucun 1,6 katıdır.
* Diğer yükleme uçlarının tavanları zaten genel tavanın altında (ork 20 MiB,
  motor dosyası 2 MiB; ``hrma/importers/api.py``).
"""

#: Bütün uçlarda istek gövdesinin üst sınırı [bayt] (32 MiB). Tek kaynak;
#: ``app.config['MAX_CONTENT_LENGTH']`` ve ``step_api.MAX_UPLOAD_BYTES``
#: bu adı kullanır, sayıyı kopyalamaz.
REQUEST_BODY_MAX_BYTES = 32 * 1024 * 1024


#: Waitress eşzamanlı bağlantı tavanı (waitress varsayılanı 100). Waitress her
#: bağlantının gövdesini köken kapısından ÖNCE ``REQUEST_BODY_MAX_BYTES``'a
#: kadar tamponlar; yabancı bir yerel sayfanın açabileceği geçici tampon
#: bağlantı sayısıyla çarpılır (1000 bağlantıda ~32 GiB, 100'de ~3,2 GiB).
#: run_windows.py eskiden gerekçesiz 1000 veriyordu (SG-2 waitress turu, devir;
#: ana model 14 Eki). Yerel tek kullanıcılı uygulama için 100 fazlasıyla yeter.
WAITRESS_CONNECTION_LIMIT = 100
