# HRMA Örnek Projeleri

Bu dizinde, uygulamayı ilk kez açan kullanıcının boş formla uğraşmadan
"program çalışıyor mu?" sorusuna hızla yanıt alabilmesi için üç hazır
`.hrma` projesi bulunur. Üçü de açılıp doğrudan hesaplanabilir; girdi
değerleri uygulamanın kendi kataloglarından gelir, hiçbir sayı uydurma
değildir.

| Dosya | Motor tipi | Tasarım | `results_summary` (v3.0.5 ile, sayfanın GERÇEK Hesapla gövdesiyle ölçüldü) |
|---|---|---|---|
| `Example Hybrid N2O-HTPB 3kN.hrma` | Hibrit | N2O/HTPB, 3 kN, 10 s, 30 bar, O/F 6 | Isp 209,755 s, toplam impuls 29955,628 N·s |
| `Example Solid KNDX BATES 75mm.hrma` | Katı | KNDX (KNO3/dekstroz 65/35), 3xBATES, 75 mm, 40 bar | tepe itki 1498,194 N, yanma 2,277 s, toplam impuls 2956,883 N·s, Isp 125,284 s |
| `Example Liquid LOX-RP1 25kN.hrma` | Sıvı | LOX/RP-1, 25 kN, 50 bar, O/F 2.0, gaz jeneratörü çevrimi, 1,0 mm CuCrZr astar + dış kabuk, 30 s yanma (örnek girdisi) | Isp(deniz) 257,114 s, Isp(vakum) 301,099 s, toplam impuls 750000,000 N·s |

Bu tablo **elle yazılmaz**: sayılar üç `.hrma` dosyasının `results_summary`
alanından birebir alınmıştır (üç ondalığa yuvarlanmış). O alan proje
şeridinin kendi özetidir: örnek üretilirken gerçek sayfada açılır,
**Hesapla**'ya basılır ve şerit belgeyi kendisi kaydeder. Sürüm yükseldiğinde örnekler
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

Not: örnek dosyalar sayfanın BÜTÜN form alanlarını taşır (proje şeridinin
kaydettiği belge). Yani örneği açıp **Calculate**'e basan kullanıcı, dosyanın
özetindeki sayıyı alır ve Fırlatma Sahası örnek dosyadan aynı motoru uçurur.

> **27 Ekim 2026 · v3.0.5 (V301/ÖRNEK) — örnekler neden yeniden üretildi:**
> örnekler eskiden şablon varsayılanlarının bir aynasıyla üretiliyordu ve
> ayna sayfanın gönderdiği gövdeden sapıyordu. Ölçüldü: proje şeridi hibrit
> örnek için **Isp 236,0 s** yazarken Hesapla **210,1 s** veriyordu;
> Fırlatma Sahası katı örnek dosyadan 3,090 kg kuru kütleli, 83 mm çaplı bir
> motor uçuruyordu (sayfadaki motor 3,734 kg, 89 mm). Sıvı örnek Inconel 718
> astarla KRİTİK açılıyordu (ısıl SF 1,04, cidar 1119 K > 977 K izin).
> Girdiler: hibrit O/F 7 → 6 (O/F 7'de grafit boğaz 3304 K ile 3300 K izin
> sınırını aşıyordu); sıvı iki katmanlı cidarın geçerli noktası (CuCrZr astar
> 1,0 mm, O/F 2,0, 50 bar) ve 30 s yanma süresi (örnek girdisi, HRMA seçimi:
> itici kütlesi, toplam itki, tanklar ve .eng bundan hesaplanır).

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
- **Sıvı:** RP-1/LOX yoğunlukları formda boş bırakılır; sayfa ve çözücü
  onları itici tablosundan alır ve kaynağını yanıtta beyan eder
  (`fuel_density_source`, `oxidizer_density_source`). Cidar iki katmanlıdır:
  1,0 mm CuCrZr astar ve kalınlığını HRMA'nın boyutlandırdığı dış kabuk
  (varsayılan malzeme). O/F 2,0 ve 50 bar bu cidarın geçerli noktasıdır
  (V301/L-KABUK ölçümü): O/F 2,1'de dökülen birikim altındaki yerel cidar
  sıcaklığı yine erime sınırını aşar. Yanma süresi 30 s bir örnek
  girdisidir (HRMA seçimi). Sonuçlar uygulamanın CEA-tabanlı çözücüsünden
  gelir.

`results_summary` alanları elle yazılmamıştır: her dosya üretilirken örnek
gerçek sayfada hesaplanmış ve özet proje şeridinin o hesaptan kurduğu
özettir; üretici aynı gövdeyi test istemcisiyle de koşar ve özetin her
sayısının yanıtla bit-aynı olduğunu denetler.

## Yeniden üretme ve test

Dosyalar elle yazılmaz. Üretici örneği kendi sunucusunda (kopya proje
dizini) gerçek sayfada açar, Hesapla'ya basar, proje şeridinin belgesini
şeridin Kaydet isteğiyle yazar ve belge kendini aynı gövdeyle yeniden
üretene dek (sabit nokta) tekrarlar; Playwright ve Chrome for Testing
gerekir:

```bash
python3 examples/generate_examples.py
python3 -m pytest tests/test_example_projects.py -q
```

Üretici sayfanın gönderdiği gövdeyi `tests/support/kabul_sayfa_yukleri.py`
hasadına da yazar; testler bu gövdeyle koşar. Test bekçisi şunları doğrular:
dosyalar proje deposundan şema doğrulamasıyla yüklenir, örnekteki her alan
ilgili şablonda gerçekten vardır, hasat bu örnek dosyanın gövdesidir, her
örnek kendi hesap ucundan HTTP 200 ile geçip fiziksel olarak makul aralıkta
sonuç üretir ve özet sayfanın hesabıyla aynı sayıyı söyler.
