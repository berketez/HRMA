"""Depo geneli ölçüm eşikleri — **TEK TANIM YERİ**.

ÖH D20 · defter **P13B3-07**. Kusur şuydu: platform gürültü tabanı
``1e-12`` diye İLAN EDİLMİŞTİ ama sabit yalnız onu yazan dosyada
(``tests/test_sivi_akustik_gocu.py``) duruyordu; yani "kural" depo geneli
bir sözleşme değil, tek dosyalık bir yerel âdetti. Ölçüldü (ÖH D20,
``once_gurultu.json``): tabanın ALTINDA bant ilan eden 60 karşılaştırma
var ve hiçbiri bu sabiti okumuyordu — okuyamazdı da, çünkü paylaşılmıyordu.

Sabit buraya taşındı; ilan eden dosya da artık BURADAN okur.

Kaynak ölçüm (metin, ``test_sivi_akustik_gocu.py``'den taşındı)
-----------------------------------------------------------------
``ESKI_YEREL`` anlık görüntüsü arm64/Darwin'de ölçüldü (HEAD 9946c70); CI
x86_64/Linux'ta aynı ifadeler libm/FMA/BLAS son-bit farkıyla değişik
yuvarlanıyor. Ölçülen en büyük sapma **3,1e-13 bağıl** (CI koşumu
32003781095: 6398,1396323450135 -> ...347029). Eşik o gürültünün ~3 katı;
gerçek bir göç kaçağı (>=1e-6 sınıfı: çap kaynağı, ses hızı, formül
değişimi) ise 6 dekad üstündedir, yani bekçi ısırmaya devam eder
(mutasyonla ölçüldü: 1,6e-5'lik oynama 2 testi kırmızı yakıyor).
``repr()`` tam eşitliği yalnız AYNI makinede anlamlıdır; platformlar arası
sözleşme bu taban üzerinden kurulur.

Tabanın altına inmenin İKİ anlamı var — yalnız biri kusurdur
------------------------------------------------------------
**KİMLİK** (meşru): karşılaştırmanın iki yanı da İFADE — aynı cebrin iki
yazımı, aynı platform, yinelemeli çözücü yok. ``1e-15`` bandı burada bir
platform iddiası değil, "bu iki ifade aynı sayıyı üretir" iddiasıdır.
Ölçüldü: 60 taban-altı karşılaştırmanın **54'ü** bu sınıftadır.

**ÇAPA** (kusur): bir yanı ÇIPLAK SAYI LİTERALİ. Tabanın altında çapa
kurmak, "bu literalin son basamakları her platformda aynı çıkar" demektir;
bu ölçülmemiş bir iddiadır ve ÖH defterinde P13B3-08 tam olarak budur
(belge 4 basamak yazarken bekçi 16 basamak kilitliyordu).
"""

#: Platformlar arası "değişmedi" sözleşmesinin bağıl tabanı.
PLATFORM_GURULTU_TABANI_REL = 1e-12

#: Aynı platformda, aynı cebrin iki yazımı arasındaki kimlik bandı. Taban
#: ALTINDADIR ve bilinçlidir: burada iddia platform taşınabilirliği değil,
#: cebirsel özdeşliktir (birkaç ULP'lik toplama sırası farkı beklenir).
CEBIRSEL_KIMLIK_REL = 1e-14
