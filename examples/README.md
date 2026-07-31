# HRMA Örnek Projeleri

Bu dizinde, uygulamayı ilk kez açan kullanıcının boş formla uğraşmadan
"program çalışıyor mu?" sorusuna hızla yanıt alabilmesi için üç hazır
`.hrma` projesi bulunur. Üçü de açılıp doğrudan hesaplanabilir; girdi
değerleri uygulamanın kendi kataloglarından gelir, hiçbir sayı uydurma
değildir.

| Dosya | Motor tipi | Tasarım | Beklenen sonuç (v2.6.25 ile hesaplandı) |
|---|---|---|---|
| `Example Hybrid N2O-HTPB 3kN.hrma` | Hibrit | N2O/HTPB, 3 kN, 10 s, 30 bar, O/F 7 | Isp ≈ 242 s, c* ≈ 1616 m/s, Tc ≈ 3389 K |
| `Example Solid KNDX BATES 75mm.hrma` | Katı | KNDX (KNO3/dekstroz 65/35), 3×BATES, 75 mm, 40 bar | Ortalama itki ≈ 1.67 kN, 2.0 s, 3382 N·s (L sınıfı), Isp ≈ 143 s |
| `Example Liquid LOX-RP1 25kN.hrma` | Sıvı | LOX/RP-1, 25 kN, 70 bar, O/F 2.3, gaz jeneratörü çevrimi | Isp(deniz) ≈ 277 s, Isp(vakum) ≈ 309 s, c* ≈ 1756 m/s |

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
