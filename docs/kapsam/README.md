# HRMA — Kapsam Belgeleri

**Son güncelleme: 2026-08-14**
**Kapsam:** Bu dizin, HRMA'nın *ne yaptığını, ne yapmadığını, nerede geçerli
olduğunu ve nerede kullanılmaması gerektiğini* tanımlar. Kurulum, mimari ve
geliştirme süreci başka belgelerin konusudur.

**Ölçüm tabanı:** Bu dizindeki her sayı ve her iddia, `2e2375d` commit'indeki
çalışma ağacı üzerinde ölçülmüştür. Ölçülemeyen hiçbir yetenek burada
yazılmamıştır; yazılan her yetenek `dosya:satır` referansı taşır.

---

## Tek cümlelik kapsam

HRMA; katı, sıvı ve hibrit roket motorları için **ön tasarım ve eğitim
amaçlı** bir analiz platformudur. Uçuş kalifikasyonu, sertifikasyon,
uygunluk denetimi veya işletme emniyeti hükmü **vermez** ve veremez.

---

## Belgeler

| Belge | Neyi cevaplar |
|---|---|
| [ne-yapar.md](ne-yapar.md) | Hangi motor tipi, hangi analiz modülü, hangi çıktı biçimi gerçekten var? Ölçülmüş envanter. |
| [ne-yapmaz.md](ne-yapmaz.md) | Yazılımın kapsamı dışında olan şeyler, her biri kodda nerede beyan edildiğiyle birlikte. |
| [gecerlilik-zarfi.md](gecerlilik-zarfi.md) | Her modelin geçerli olduğu aralık; zarf dışına çıkıldığında yazılımın ne yaptığı (`NOT_MODELLED` disiplini). |
| [kullanim-alanlari.md](kullanim-alanlari.md) | Kimler, hangi amaçla kullanır; hangi amaçla kullanmaz. |
| [yasaklar-ve-sorumluluk.md](yasaklar-ve-sorumluluk.md) | Kullanım yasakları, güvenlik uyarıları, lisans ve sorumluluk reddi. |

## İlgili belgeler (bu dizinin dışında)

| Belge | İçerik |
|---|---|
| [`docs/VALIDATION_STATUS.md`](../VALIDATION_STATUS.md) | Doğrulama durumu, bilinen sınırlar ve makine üretimi korelasyon tablosu. **Bir sayıyı alıntılamadan önce belgenin başındaki künye satırını okuyun.** |
| [`docs/VALIDATION_SOURCES.md`](../VALIDATION_SOURCES.md) | Doğrulama veri kümelerinin kaynak künyesi (Claim / Evidence / Confidence / Date checked biçiminde). |
| [`docs/STANDART_ATIFLARI.md`](../STANDART_ATIFLARI.md) | Kodda kullanılan standart atıflarının tam adları ve doğrulanma durumu. `DOĞRULANMADI` etiketli satırların başlığı doğru varsayılmamalıdır. |
| [`docs/USER_MANUAL.md`](../USER_MANUAL.md) | Arayüz kullanımı. |
| [`LICENSE`](../../LICENSE) | MIT lisansı ve garanti reddi. |

---

## Bu belgeleri okurken

1. **Bir sayı gördüğünüzde kaynağını sorun.** HRMA çıktılarının çoğu `_basis`
   veya `basis` alanında hangi bağıntıdan ve hangi kaynaktan geldiğini
   söyler (depoda 116 ayrı `_basis` künyesi ölçüldü).
2. **`NOT_MODELLED` bir hata değildir.** Modelin, elinde o sayıyı üretecek
   bir temel olmadığını söylemesidir. Ayrıntı: [gecerlilik-zarfi.md](gecerlilik-zarfi.md).
3. **Boş alan ile sıfır aynı şey değildir.** Hesaplanamayan büyüklükler
   `null` döner ve arayüzde tire olarak görünür; sıfır olarak gösterilmez.
4. **HRMA'nın çıktısı bir teste girdi, testin yerine geçen bir belge
   değildir.** Ateşleme öncesi bağımsız çapraz kontrol ve fiziksel test
   şarttır — bkz. [kullanim-alanlari.md](kullanim-alanlari.md).
