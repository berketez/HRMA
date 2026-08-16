# v3 CFD tasarımı — lüle iç akışı (Aşama 1)

**Tarih:** 15 Ağustos 2026 · **Karar sahibi:** Berke (FINAL stratejisi) + ana model (sayısal tasarım)
**Bağlam:** FINAL yayınının ön şartı analiz platformunun tam olması (FEA + termal + mesh bitti);
kalan büyük kulvar F1 gerçek CFD. Eski `cfd_analysis.py` SİLİNDİ (parti 16, `c48628b`:
kütle korunumsuz, 3 iterasyonda ıraksaktı) — bu çözücü onun halefi DEĞİLDİR, sıfırdan ve
doğrulama-önce kurulur.

## 1. Kapsam ve kapsam DIŞI (Aşama 1)

| Kapsamda | Kapsam DIŞI (beyanla) |
|---|---|
| 2B eksenel simetrik, sıkıştırılabilir, **Euler** (viskoz yok) | Sınır tabakası / türbülans (Aşama 2: RANS-SA ya da entegral BL) |
| Şok yakalama (aşırı-genişlemiş lülede iç şok) | Kimyasal tepkime / gerçek gaz (kalorik mükemmel, γ çözücüden) |
| Kararlı hâle koşum (yerel zaman adımı) | Zamana bağlı geçişler (start-up transient) |
| Duvar basınç dağılımı p_w(x) → `flow/separation.py` ampirik kriterine GERÇEK girdi | Ayrılmış bölgenin kendisinin çözümü (Euler ayrılmayı çözemez — beyan) |
| Kesit ortalamalarının yarı-1B (`flow/quasi1d.py`) ile çapraz doğrulaması | 3B, plume/dış akış, taban akışı |

**Dürüstlük sözleşmesi:** her koşu `not_modelled` listesi + korunum bütçesi (kütle/momentum/enerji
akı dengesi) yayımlar; yakınsamayan koşu `converged=False` + kalıntı geçmişiyle döner, sonuç
gizlenmez ama hüküm de verilmez (FEA yakınsama beyanı deseni).

## 2. Sayısal şema (kararlar kesin)

- **Ayrıklaştırma:** hücre-merkezli sonlu hacim (FVM), yapısal H-tipi ızgara.
- **Akı:** HLLC yaklaşık Riemann çözücüsü (Toro 3. baskı §10.4).
- **İkinci mertebe:** MUSCL kenar dışdeğerlemesi + minmod sınırlayıcı (TVD); birinci mertebeye
  düşüş anahtarı ayarla değil TESTLE kanıtlanır (Sod'da mertebe ölçümü).
- **Eksenel simetri:** silindirik koordinatta kaynak terimli form — r·U korunum değişkenleriyle
  akılar, r→0 ekseninde simetri sınırı (yansıma); eksen hücrelerinde 0/0 muamelesi geometrik
  (hücre hacmi/yüzeyleri gerçek dönel hacimlerden, seri açılım değil).
- **Zaman:** kararlı hâl için yerel zaman adımı + CFL rampası (0,5 → 0,9); yakınsama ölçütü
  yoğunluk kalıntısının L2 normu, tepe-değer bekçisiyle (FEA kabul-ölçütü dersinin izdüşümü:
  hüküm metriği = kullanıcının okuduğu büyüklükler — itki/Isp/şok konumu — kalıntı ikincil).
- **Sınırlayıcı dondurma (Aşama 1A'da ölçülüp eklendi):** minmod salınımı kararlı-hâl
  kalıntısını ~1e-2 bağılda platoda bırakır (ölçüldü; birinci mertebe 6 basamak inerken).
  Plato tespitinde eğimler dondurulup çözüm derin yakınsamaya sürülür (Venkatakrishnan,
  AIAA J. 33(5), 1995 gerekçesi); an, `limiter_frozen_at_iter` + `convergence_basis`
  alanlarıyla BEYANLIDIR. Bu olmadan korunum bütçesi sözleşmesi (1e-10 sınıfı) fiziksel
  olarak ulaşılmaz.
  *Aşama 1B eki:* dondurma TAZELENEBİLİR (plato sürerse eğimler güncel durumdan
  yeniden alınır) ve basınç-tabanlı KOLON şok sensörü şok kolonlarında eğimleri
  sıfırlar (eşik `SHOCK_SENSOR_THRESHOLD=0,25`, ölçümden: pürüzsüz 0,041 / şok 0,96;
  pürüzsüz akışta hiç tetiklenmez, sonuç bit-özdeş) — iç şoklu kararlı hâl ancak bu
  ikisiyle derin yakınsar (ölçüldü; beyanları `limiter_freeze_count` +
  `shock_sensor_columns`/`shock_sensor_basis`).
- **Gaz modeli:** kalorik mükemmel; γ ve R motor çözücüsünün yayımladığı değerlerden
  (`chamber_temperature`, `gamma`, `molecular_weight`) — sabit uydurulmaz, eksikse red (köprü deseni).
- **Sınır koşulları:** giriş = rezervuar (P0, T0, subsonik karakteristik); duvar = kayma (Euler);
  eksen = simetri; çıkış = süpersonikte dışdeğerleme, arka-basınçlıda ses-altı çıkışa statik
  basınç dayatması (Aşama 1B ölçümü: çıkış kesit basıncı Pb'ye %0,03 — karakteristik
  yükseltme GEREKMEDİ, gerekirse Aşama 2).

## 3. Izgara

`sample_nozzle_inner_contour` (üç motorun TEK geometri kaynağı) → duvar; eksen r=0 → iç sınır;
i-yönü eksenel, j-yönü radyal; radyal dağılım duvara doğru sıkıştırılabilir (Aşama 2 BL hazırlığı),
Aşama 1'de düzgün. Hedef çözünürlük 10⁵ hücre sınıfı; kaba→ince yakınsama çalışması zorunlu
(FEA inceltme beyanı deseni).

## 4. Doğrulama merdiveni (test-first; her basamak kendi bekçisiyle, mutasyon kanıtlı)

1. **Sod şok tüpü (1B):** yoğunluk/hız/basınç profilleri analitik Riemann çözümüne karşı;
   L1 hata eşiği + ÇÖZÜNÜRLÜKLE DÜŞTÜĞÜ (mertebe) ölçülür.
2. **İzantropik yakınsak-ıraksak lüle:** kesit ortalamalı M(x), p(x) analitik izantropik bağıntılara
   ve `flow/quasi1d.py`'ye karşı (aynı geometri, aynı γ); boğaz kütle debisi ±%1.
3. **Aşırı-genişlemiş lülede normal şok:** şok konumu analitik 1B çözüme karşı (kesit ortalaması).
4. **Korunum bütçesi:** giriş-çıkış akı farkları kapalı bütçede (kütle bağıl artık < 1e-10 sınıfı).
5. **Eksen simetri sağlığı:** eksende türev/parazit basınç salınımı bekçisi.

## 5. Performans yolu (mimari karar 4 Ağu, değişmedi)

NumPy vektörize ilk sürüm → `cProfile` ile ölç → sıcak çekirdek numba/Cython → gerekirse pybind11
C++. Aşama 1 hedefi: 64×256 ızgarada kararlı hâl < ~1 dk (M4 Max, tek süreç). Optimizasyon
ölçümden ÖNCE yapılmaz.

## 6. Dosya düzeni

```
hrma/cfd/__init__.py      # sürüm + NOT_MODELLED beyan çekirdeği
hrma/cfd/riemann.py       # HLLC (saf fonksiyon, 1B durum vektörü)
hrma/cfd/euler_core.py    # 1B/2B FVM güncelleme çekirdeği (MUSCL+minmod)
hrma/cfd/grid_axisym.py   # kontur → yapısal ızgara + metrikler
hrma/cfd/steady.py        # yerel-Δt sürücü, CFL rampası, kalıntı/hüküm beyanı
tests/cfd/                # doğrulama merdiveni (basamak başına dosya)
```

UI/uç bağlaması Aşama 1'de YOK — çözücü önce doğrulama merdivenini tırmanır; panel/uç Aşama 1B
(FEA'daki D5 deseniyle). `app.py`'ye bu aşamada dokunulmaz.

## 7. Aşamalar

- **1A (TAMAM, `d4a213e`):** riemann + euler_core 1B + Sod (basamak 1) → 2B axisym ızgara +
  çekirdek + izantropik lüle (basamak 2) + korunum bütçesi (basamak 4). 18 bekçi.
- **1B çözücü tarafı (TAMAM, parti 25):** şok vakası (basamak 3: analitiğe 0,33 mm,
  `tests/cfd/test_normal_sok.py`) + eksen sağlığı (5: `test_eksen.py`) + çözünürlük
  merdiveni (`test_cozunurluk.py`, debi hatası %0,247→%0,038) + performans
  (`test_performans.py`: numba 1,98×, bit-özdeş, isteğe bağlı —
  `HRMA_CFD_DISABLE_NUMBA=1` saf NumPy yolu bekçili) + p_w(x) sözleşmesi
  (`wall_pressure_Pa` + `wall_pressure_z_m` + `wall_pressure_basis`).
  Toplam 36 bekçi.
- **1B ürün tarafı (dalga B, sırada):** p_w → separation.py entegrasyonu +
  `/api/cfd/nozzle` ucu + Analiz Merkezi'nin ilk kiracısı olarak panel
  (analiz-merkezi-tasarimi.md).
- **Lean biçimsel ayak (Berke talimatı, 15 Ağu):** CFD'nin kapalı-form bağıntıları
  `formal/LeanLab` platformuna eklenir — aday teoremler: izantropik alan-Mach/
  basınç bağıntıları, normal şok sıçrama bağıntıları (Rankine-Hugoniot tutarlılığı),
  HLLC ara-durum özdeşlikleri, boğulmuş debi formülü. Sayısal çözücünün kendisi
  ispatlanmaz (ayrıklaştırma testle doğrulanır); ispat, TESTLERİN karşılaştırdığı
  analitik referans formüllerin türetimlerini kilitler.
- **2 — viskoz/türbülans (Berke kararı, 16 Ağu 2026): FINAL KAPSAMINDA.**
  "Tamamen çalışır vaziyette istiyorum, onları da dahil et" — FINAL, Euler +
  beyan ile DEĞİL, viskoz/türbülanslı çözücüyle çıkar. Tasarım turu 16 Ağu'da
  başlatıldı (RANS-SA vs entegral BL kararı dahil; çıktı:
  `cfd-viskoz-tasarimi.md`); uygulama F2 ile birlikte FINAL öncesi kuyrukta.
