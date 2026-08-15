# Ne Yapmaz — Kapsam Dışı Olanlar

**Son güncelleme: 2026-08-14**
**Kapsam:** HRMA'nın *yapmadığı* şeyler. Her madde, kodda nerede beyan
edildiğiyle birlikte verilmiştir. Bu belge bir özür listesi değil, bir
sınır tanımıdır: bir aracın ne olmadığını bilmek, ne olduğunu bilmek kadar
gereklidir.

**Ölçüm tabanı:** `2e2375d`.

---

## 1. HRMA bir CFD çözücüsü değildir

`hrma/analysis/cfd_analysis.py` içindeki 2B çözücü **emekliye
ayrılmıştır**. `/api/cfd-analysis` uç noktası, işleyicisine hiç
girmeden HTTP **501** döner (`hrma/app.py:7770-7784`). Koddaki gerekçe
birebir şudur: çözücü kütleyi korumuyor, üç iterasyonda ıraksıyor
(|u| → 7.5e10 m/s) ve `NaN` üretiyordu.

Halefi bir CFD çözücüsü değil, **indirgenmiş mertebeli** bir modeldir:
`/api/flow-analysis` → yarı-1B sıkıştırılabilir lüle akışı
(`hrma/flow/quasi1d.py`). Bu modelin kendi beyanına göre
(`hrma/flow/quasi1d.py:123`) modellenmeyen fizik:

- cidar sürtünmesi ve sınır tabaka (Fanno etkisi yok),
- cidara ısı kaybı (akış adyabatik, T₀ sabit),
- iki boyutlu etkiler: akım çizgisi eğriliği, eğik şoklar, şok–sınır
  tabaka etkileşimi, lambda-şok yapısı,
- gerçek gaz ve sıcaklığa bağlı özgül ısı (kalorik mükemmel gaz, donmuş
  kompozisyon).

Ayrılma değerlendirmesi de aynı disiplinle sınırlıdır
(`hrma/flow/separation.py:101`): yanal (side-load) kuvvetler, FSS/RSS
ayrımı, sınır tabaka durumu, ayrılma şoku yapısı ve ateşleme/söndürme
histerezisi **modellenmez**; yalnız ayrılma var/yok kararı ve konum
tahmini verilir.

**Sonuç:** Türbülans modeli, 3B alan çözümü veya şok–sınır tabaka
etkileşimi gereken bir soruyu HRMA cevaplamaz. O soru bir CFD paketinin
işidir.

## 2. HRMA bir CMA sınıfı ablasyon çözücüsü değildir

Termal koruma modülü, ablatif kalınlığı **Seviye-1 kararlı Q\*** (etkin
ablasyon ısısı) modeliyle boyutlandırır. Modül bunu kendi docstring'inde
söyler: *"Derinlemesine piroliz/char enerji dengesi (CMA sınıfı kodlar)
YOKTUR — panelde 'simplified model' etiketiyle sunulur"*
(`hrma/analysis/thermal_protection.py`, `_ablation_level1` docstring'i).

Modellenmeyenler: piroliz cephesi ilerlemesi, kömür tabakası içi gözenek
akışı ve gaz taşınımı, ayrışma kinetiği, malzeme içi tür taşınımı ve
derinlemesine enerji dengesi.

Model, zarfının dışına çıktığında kalınlık **üretmez**: geçerlilik
kapısı devreye girince `thickness_status='NOT_MODELLED'` olur ve
`validity_note` alanı kullanıcıyı doğrudan yönlendirir — *"Use an
in-depth pyrolysis/char (CMA-class) analysis, or change the design point
(flux, burn time, material)."* Ayrıntı ve tavanın tanımı:
[gecerlilik-zarfi.md](gecerlilik-zarfi.md).

> *Not:* Bu modül ölçüm anında etkin geliştirme altındaydı (üfleme
> blokajı sabit bir katsayı olmaktan çıkıp Aerotherm/CMA indirgeme
> bağıntısıyla B′'den çözülür hâle getirilmişti). Bu yüzden burada satır
> numarası değil **sembol adı** verilmiştir; kodda `RECESSION_VALID_MAX_MM_S`
> ve `BLOWING_LAMBDA` adlarını arayın.

## 3. HRMA bir sertifikasyon, kalifikasyon veya uygunluk aracı değildir

Yazılım hiçbir mevzuat uygunluğu değerlendirmesi yapmaz ve yapabileceğini
iddia etmez. `_check_safety_compliance` bugün şunu döner
(`hrma/analysis/safety_analysis.py:1177-1207`):

```
nfpa_compliance      : NOT_EVALUATED
osha_compliance      : NOT_EVALUATED
dot_compliance       : NOT_EVALUATED
local_regulations    : NOT_EVALUATED
insurance_requirements: NOT_EVALUATED
```

Fonksiyonun kendi docstring'i, bu alanların eskiden **koşulsuz `True`**
döndüğünü ve arayüzde motor büyüklüğünden, iticisinden ve kullanım
yerinden bağımsız olarak yeşil "NFPA: OK" rozeti çizildiğini kayıt altına
alır. Gerçek uygunluk değerlendirmesi madde madde gereksinim
karşılaştırması, tesis ve saha bilgisi, yerel mevzuat ve **yetkili bir
değerlendirici** ister; bunların hiçbiri yazılıma girdi olarak
verilmemektedir.

Aynı disiplin dil düzeyinde de zorlanır: `tools/iddia_lint.py`,
"NASA-grade", "NASA-validated", "flight-certified", "manufacturing-ready",
"safe for operation", "professional-grade", "guaranteed" gibi
kazanılmamış hüküm kalıplarını `hrma/` ağacında ve kullanıcıya giden
belgelerde makinece tarar ve kayıtta olmayan bir isabet bulursa çıkış
kodu 1 verir.

## 4. HRMA bir emniyet kapısı değildir

`hrma/analysis/safety_limits.py` modülünün ilk cümlesi doğrudan şudur:
burası bir güvenlik kapısı **değildir**. Ölçüm de belgede kayıtlıdır:
üretimdeki tek canlı giriş `check_throat_diameter`'dır
(`hrma/engines/liquid_rocket_engine.py:2956-2963`) ve sonucu yalnız
`print()` ile konsola yazılır; `violations` listesi hiçbir HTTP yanıtına,
dışa aktarıma veya panele girmez.

> *Künye kayması notu:* `safety_limits.py` docstring'i bu çağrı yerini
> `liquid_rocket_engine.py:2723` olarak gösterir; ölçüm sırasında
> (`2e2375d`) gerçek satır **2960**'tır. Docstring'deki satır numarası
> bayattır; çağrının kendisi yerindedir.

Sınıf kendi hükmünü de sınırlar: "İşletme emniyeti hükmü VERMEZ; yalnız
model girdisinin fiziksel olarak anlamlı bir aralıkta olup olmadığına
bakar" (`safety_limits.py:44-45`). Rapor metnindeki "MOTOR SAFE FOR
OPERATION" ifadesi kaldırılmıştır; hiç kontrol koşmadıysa çıktı
"NOT EVALUATED" der — "hiç değerlendirilmedi" ile "tümü geçti" artık
ayırt edilebilir (`safety_limits.py:98-113`).

## 5. HRMA imalat toleransı, imalat kabulü veya güvenilirlik hükmü vermez

- **Yıldız tanesi profil toleransı:** sayı üretilmez. Modül,
  "önceki sabit ±0,05 mm her motora uygulanıyordu ve hiçbir şeyden
  türetilmemişti; bunu kendi detay resminizde belirleyin" der
  (`hrma/engines/solid_rocket_engine.py:5423-5429`).
- **Çekirdek konumlandırma toleransı:** aynı biçimde
  `NOT_MODELLED` (`solid_rocket_engine.py:5528-5534`).
- **Bağlantı güvenilirliği (olasılıksal):** HRMA'nın olasılıksal bir
  bağlantı modeli yoktur — dayanım ve yük dağılımları yok, dolayısıyla
  bir güvenilirlik yüzdesi hesaplanamaz. Yerine deterministik cıvata
  emniyet katsayıları verilir (`solid_rocket_engine.py:4477-4484`).

## 6. HRMA ateşleme geçici rejimini modellemez

Ateşleyici yanma süresi motorun basınç yükselme süresine uymalıdır; HRMA'nın
ateşleme geçici modeli olmadığı için **sayı raporlanmaz**
(`hrma/engines/solid_rocket_engine.py:6039-6044`). Ateşleyici modülü de
kendi kapsamını sayar (`hrma/analysis/igniter_sizing.py:151`):
tutuşma kimyası, alev yayılımı, sert başlangıç (hard-start) dinamiği,
hipergolik tutuşma, elektriksel ateşleme zinciri (kıvılcım enerjisi,
köprü teli, no-fire/all-fire akımları, emniyet-kurma cihazı), torç
iç yapısı, ateşleyici donanımı ve yeniden ateşleme — hiçbiri modellenmez.

## 7. HRMA bir kontrol sistemi veya TVC tasarım aracı değildir

Gimbal modülü **yük** verir, aktüatör vermez
(`hrma/analysis/gimbal_mount.py:132`). Modellenmeyenler: aktüatör
dinamiği (bant genişliği, esneklik, boşluk, durma kuvveti, hız sınırı),
kontrol döngüsü (kazanç, faz payı, aktüatör–araç–çalkalanma–yapı
etkileşimi, tail-wags-dog), yatak sürtünmesi, esnek yakıt hattı direnci,
yapısal kapasite, araç düzeyi aerodinamik/ataletsel yükler, lüle yanal
yükleri, ısıl etkiler ve jiroskopik bağlaşım.

## 8. HRMA yanma kararsızlığı hükmü vermez

Akustik modül, hazne akustik modlarının **nerede** olduğunu söyler; yanmanın
onları kararsızlığa **sürükleyip sürüklemeyeceğini** söylemez
(`hrma/analysis/acoustic_modes.py:134-139`). Yanma tepki fonksiyonu
(basınç/hız bağlaşımı, n-tau zaman gecikmesi modelleri) ve Rayleigh
ölçütü değerlendirmesi modellenmez. Sönümleme de modellenmez: baffle,
akustik boşluk/rezonatör, lüle admitansı, viskoz ve tanecik kayıpları
kapsam dışıdır — frekanslar sönümsüz, rijit cidarlı öz değerlerdir.

## 9. HRMA gaz besleme hattı boyutlandırmaz

Vana ve besleme hattı modülü sıkıştırılamaz Darcy-Weisbach bütçesi ve
IEC 60534 **sıvı** boyutlandırma denklemi kullanır. Modülün kendi
uyarısı: "Bu sonuçları bir gaz hattı için kullanmayın"
(`hrma/analysis/valve_feedline.py:290-296`). Ayrıca modellenmeyenler:
iki fazlı/flaşlı akışın basınç düşümü ve akış debisi, geçici rejimler
(başlatma, priming, soğutma, sürgün dalgasının kendisi), vana iç
geometrisi (trim, strok, sızdırma, aktüatör torku), kavitasyon hasar
eşikleri (ISA RP75.23 vana özel test verisi), termodinamik kavitasyon
bastırma (B-faktörü), ani daralma/genişleme K değerleri, körüklü/örgülü
esnek hortum pürüzlülüğü, akışkan özellikleri (çağıran verir) ve besleme
sistemi dinamiği (POGO, hat akustiği, akış kaynaklı titreşim).

## 10. HRMA turbopompa haritası veya rotordinamiği vermez

Turbopompa modülü **tek tasarım noktası** boyutlandırmasıdır
(`hrma/analysis/turbopump_sizing.py:227`). Modellenmeyenler: kavitasyon
dinamiği (kabarcık büyümesi, termodinamik bastırma başı, indüser geri
akışı, POGO bağlaşımı), off-design performans haritaları (pompa H-Q
eğrisi, türbin haritası, kısma davranışı), rotordinamik (şaft kritik
hızları, yatak DN sınırları, salmastralar, eksenel itki dengesi),
yapısal marjlar (çark patlaması, kanat kökü gerilmesi) ve türbin akış
ayrıntıları (kısmi giriş, kanat profil kayıpları, kademe reaksiyonu).
Rapor edilen NPSH marjı kararlı hâl tasarım kuralı karşılaştırmasıdır,
bir kavitasyon kararlılık beyanı değildir.

## 11. HRMA katı yakıt tanesi kesitini sonlu elemanla çözmez

FEA çekirdeği eksenel simetriktir. Yıldız ve finocyl gibi kesitler eksenel
simetrik olmadığından 2B düzlemsel kip gerekir; bu çözücü henüz yoktur ve
paket bunu makine okunur biçimde ilan eder:
`MODULE_STATUS['planar_grain'] = 'NOT_IMPLEMENTED'`
(`hrma/fea/__init__.py`). Uygulanmamış çözücünün çıktısı çizilmez.

Ayrıca balistik çözümü **daire-eşdeğer port** ile yapılır; yıldız,
çok portlu ve finocyl kesitleri alan-eşdeğer görselleştirmedir (kök
`README.md` bunu açıkça söyler).

## 12. HRMA uçuş dinamiğinde büyük hücum açısını ve kurtarmayı çözmez

- 6-DOF katmanının aerodinamiği **lineer küçük-α Barrowman** teorisidir
  (α ≲ 15°). Takla atan veya büyük hücum açılı uçuş için kullanılmaz;
  aeroelastisite, spin-kanat etkileşimi ve türbülans modeli yoktur
  (`docs/VALIDATION_STATUS.md`, bilinen sınırlar #8).
- Fırlatma rayı verilmediyse ray kısıtı ve yönelim dinamiği
  **modellenmez**: itki tüm yanma boyunca fırlatma yönelimi üzerinde
  tutulur ve pitch-over hesaplanmaz
  (`hrma/analysis/trajectory_analysis.py:604-607`).
- İniş fazı koşmadıysa kurtarma sistemi çözümün parçası değildir:
  `descent_model = 'NOT_MODELLED'`
  (`hrma/analysis/trajectory_analysis.py:656-663`).
- Dünya dönüşünün **taşıma hızı** bileşeni kapsam dışıdır (Coriolis ve
  merkezkaç dahildir); yerel yerçekimi anomalileri ve gerçek gün
  atmosferi (nem, cepheler, mevsimsel profiller) modellenmez
  (`hrma/analysis/launch_site.py:108-122`).

## 13. HRMA katı motorda tanecik dinamiğini çözmez

İki fazlı akış Isp kaybı kestiricisi tek bir d43 çapı kullanır; tanecik
boyut dağılımı, lüle boyunca birleşme/kırılma, tanecik–duvar çarpması ve
donma gecikmesi + gizli ısı geri kazanımı modellenmez
(`hrma/analysis/two_phase_loss.py:181-186`).

## 14. HRMA katı yakıt üretimi, işlenmesi veya test güvenliği hakkında
talimat vermez

Yazılım geometri ve performans hesaplar. Yakıt hazırlama, karıştırma,
dökme/presleme, depolama, taşıma, ateşleyici hazırlığı, test standı
kurulumu, güvenlik mesafesi ve tahliye planı **kapsam dışıdır** ve HRMA
bunlar hakkında hiçbir çıktı üretmez. Bu konular yerel mevzuatın,
yetkili kurumların ve deneyimli bir sorumlunun alanıdır — bkz.
[yasaklar-ve-sorumluluk.md](yasaklar-ve-sorumluluk.md).

## 15. HRMA insanlı sistem, uçuş yazılımı veya gerçek zamanlı denetleyici
değildir

HRMA masaüstünde çalışan bir çevrimdışı analiz uygulamasıdır. Uçuş
donanımına gömülmez, gerçek zamanlı bir döngüde koşmaz, uçuş sonlandırma
veya emniyet kilidi işlevi görmez ve insanlı sistem gereksinimlerine
(tasarım güvence düzeyi, bağımsız doğrulama ve geçerleme süreci) tabi
tutulmamıştır.

---

## Özet tablo

| Alan | HRMA'nın verdiği | HRMA'nın vermediği |
|---|---|---|
| Lüle içi akış | Yarı-1B rejim, P(x), M(x), CF | 2B/3B alan, türbülans, SBLI |
| Termal koruma | Q\* tabanlı ablatif kalınlık, ısı yutucu, ışınım dengesi | Piroliz cephesi, CMA sınıfı çözüm |
| Yapı | Lamé, SP-8007, yorulma, eksenel simetrik FEA | Olasılıksal güvenilirlik, imalat kabulü |
| Emniyet | Model limit kontrolü, tehlike listesi | Uygunluk hükmü, işletme emniyeti kararı |
| Besleme | Sıvı hat basınç bütçesi, vana Cv | Gaz hattı, iki fazlı akış debisi, POGO |
| Turbopompa | Tek nokta boyutlandırma | Harita, rotordinamik, yapısal marj |
| Ateşleme | Enerji/debi bütçesi | Tutuşma kimyası, hard-start, elektrik zinciri |
| Uçuş | Nokta-kütle + küçük-α 6-DOF | Büyük-α, takla, aeroelastisite, kurtarma tasarımı |
| Yanma kararsızlığı | Mod frekansları | Kararsızlık hükmü, sönümleme |
