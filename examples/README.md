# HRMA Örnek Projeleri

Bu dizinde, uygulamayı ilk kez açan kullanıcının boş formla uğraşmadan
"program çalışıyor mu?" sorusuna hızla yanıt alabilmesi için üç hazır
`.hrma` projesi bulunur. Üçü de açılıp doğrudan hesaplanabilir; girdi
değerleri uygulamanın kendi kataloglarından gelir, hiçbir sayı uydurma
değildir.

| Dosya | Motor tipi | Tasarım | `results_summary` (v3.0.0 ile ÜRÜNÜN KENDİ uçlarından ölçüldü) |
|---|---|---|---|
| `Example Hybrid N2O-HTPB 3kN.hrma` | Hibrit | N2O/HTPB, 3 kN, 10 s, 30 bar, O/F 7 | Isp 236,034 s, toplam impuls 29926,591 N·s |
| `Example Solid KNDX BATES 75mm.hrma` | Katı | KNDX (KNO3/dekstroz 65/35), 3xBATES, 75 mm, 40 bar | tepe itki 1499,678 N, yanma 2,277 s, toplam impuls 2960,332 N·s, Isp 125,431 s |
| `Example Liquid LOX-RP1 25kN.hrma` | Sıvı | LOX/RP-1, 25 kN, 70 bar, O/F 2.3, gaz jeneratörü çevrimi | Isp(deniz) 277,449 s, Isp(vakum) 309,182 s |

Bu tablo **elle yazılmaz**: sayılar üç `.hrma` dosyasının `results_summary`
alanından birebir alınmıştır ve o alan da örnek üretilirken ilgili hesap
ucundan gerçekten geçirilerek doldurulur. Sürüm yükseldiğinde örnekler
yeniden üretilir (`python3 examples/generate_examples.py`) ve bu tablo da
onunla birlikte güncellenir; bekçisi
`tests/test_example_projects.py::test_readme_tablosu_ozetlerle_ayni`.

> **Neden bu not var:** 16 Eylül 2026'da ölçüldü, bu tablo **v2.6.25** ile
> hesaplanmış sayıları taşıyordu, `.hrma` dosyaları ise v2.6.26 ile. Aradaki
> onarımlar sayıları kaydırmıştı: katı örneğin tepe itkisi 1926,8 N'den
> 1641,9 N'ye (%-14,8), yanma süresi 2,024 s'den 2,323 s'ye gitti. Yani hem
> README hem proje şeridi, ürünün artık üretmediği sayıları gösteriyordu.

> **22 Eylül 2026 · ÖH D35 (OH-ON-03) — katı örneğin sayıları neden düştü:**
> ölçüldü ki katı örnek yüklenip **Hesapla**'ya basıldığında sayfa, dosyada
> OLMAYAN 51 sayı alanını kendi varsayılanıyla gönderiyordu; bunlardan altısı
> (c\*, lüle, Cf ve kinetik verimler + boğaz erozyonu + itici başlangıç
> sıcaklığı) sonucu oynatıyordu. Proje şeridi **Isp 140,109 s** yazarken
> Hesapla **125,401 s** veriyordu (%-10,5) — aynı proje için iki sayı.
> Örnek artık o altı alanı da taşır; değerler sayfanın kendi `value=`
> varsayılanlarıdır (`solid.html`), uydurma değildir. Tablodaki sayılar bu
> yüzden düştü: **gösterilen sayı, kullanıcının gerçekten aldığı sayıdır.**
> 125,4 s, KN-şeker motorlarının deneysel teslim Isp bandındadır (Nakka
> 1999: ~115-130 s); eski 140,1 s verimsiz-kayıpsız ideal değerdi.
> Bekçi: `tests/test_d35_onemli_kati_cad_a1.py`.

## Nasıl açılır

HRMA projeleri kullanıcının proje dizininden okunur:

- macOS/Windows/Linux: `~/Documents/HRMA/projects`
  (Documents dizini yoksa `~/HRMA/projects`)

1. Bu dizindeki `.hrma` dosyalarını yukarıdaki proje dizinine kopyalayın.
2. HRMA'yı başlatın ve örneğin motor tipine uyan tasarım sayfasına gidin
   (Hybrid / Solid / Liquid).
3. Sayfanın üstündeki **Project (Proje)** şeridinde **Open (Aç)**
   düğmesine basın ve örneği seçin — form alanları dolar.
4. Yükleme kendi başına hesap YAPMAZ; **Calculate** düğmesine basarak
   sonucu üretin.

Ana sayfadaki "Recent Projects" şeridi de kayıtlı projeleri listeler;
oradan tıklamak doğru tasarım sayfasını `?project=<ad>` ile açar ve
projeyi otomatik yükler.

Not: `.hrma` dosyasında bulunmayan form alanları sayfanın kendi
varsayılanında kalır; örnekler tasarımı tanımlayan alan kümesini taşır.

## Girdi değerlerinin kaynağı

- **Hibrit:** HTPB regresyon katsayıları (a = 3.68e-5, n = 0.555)
  uygulamanın HTPB/N2O varsayılanıdır (Doran et al., AIAA 2007-5352);
  N2O yoğunluk/viskozitesi uygulamanın oksitleyici kataloğundan
  (`/api/oxidizer-properties`, 293 K) alınmıştır.
- **Katı:** KNDX termokimyası (yoğunluk, alev sıcaklığı, gama, molekül
  ağırlığı, c*) `hrma/data/propellants_db.py` kataloğundan; yanma hızı
  katsayıları `hrma/data/burn_rate_db.py` rejim fitinden (Nakka
  1999/2001) 40 bar tasarım basıncında çözülmüştür. `burn_rate_preset:
  kndx` alanı sayesinde çözücü yanma boyunca parçalı rejim yasasını
  kullanır.
- **Sıvı:** RP-1/LOX yoğunlukları sayfanın kendi varsayılanlarıdır;
  O/F 2.3, 70 bar ve gaz jeneratörü çevrimi LOX/RP-1 sınıfının bilinen
  çalışma noktasıdır ve sonuçlar uygulamanın CEA-tabanlı çözücüsünden
  gelir.

`results_summary` alanları elle yazılmamıştır: her dosya üretilirken örnek
ilgili hesap ucundan gerçekten geçirilmiş ve özet o koşunun çıktısından
doldurulmuştur.

## Yeniden üretme ve test

Dosyalar uygulamanın kendi kayıt yolu (`hrma/utils/projects.py`) ile
üretilir; elle JSON yazılmaz:

```bash
python3 examples/generate_examples.py
python3 -m pytest tests/test_example_projects.py -q
```

Test bekçisi üç şeyi doğrular: dosyalar proje deposundan şema
doğrulamasıyla yüklenir, örnekteki her alan ilgili şablonda gerçekten
vardır ve her örnek kendi hesap ucundan HTTP 200 ile geçip fiziksel
olarak makul aralıkta sonuç üretir.
