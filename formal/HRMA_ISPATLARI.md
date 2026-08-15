# HRMA — biçimsel olarak doğrulanmış varsayımlar

**Tarih:** 2 Ağustos 2026 · **Lean:** 4.32.2 · **Mathlib:** v4.32.2 (pinli)
**Denetlenen depo:** `/Users/apple/HRMA`, commit `48f2f37`

> **Not (14 Ağustos 2026):** Bu dosya, ispatların yazıldığı güne ait **tarihî
> anlık görüntüdür**; içindeki Python satır numaraları `48f2f37` commit'ine
> göredir ve o günden beri kaymıştır. **Güncel ve makine-denetimli bağ**
> `formal/registry.json`'dadır; denetim `python3 formal/check.py` ile yapılır.
> Çalıştırma komutları için `formal/README.md`'ye bak (proje artık
> `~/Desktop/dosyalar/lean-lab`'dan bu depoya taşındı).

Bu dosya, HRMA'nın koduna gömülü **sözlü varsayımların** hangilerinin makine
düzeyinde ispatlandığını gösterir. Her teorem genel matematik değil, koddaki
belirli bir satırın gerekçesidir.

## Neden

HRMA'nın hesap zincirinde çözücüye "bu fonksiyonun tek kökü var", "bu formül
kesin", "bu tablo sürekli" gibi varsayımlar veriliyor. Bunlar yorum satırında
yazılı ama hiçbir yerde **denetlenmiyor**. Yanlışlarsa çözücü sessizce yanlış
dala oturur — test yeşil kalır, sayı yanlış çıkar.

Denetimlerimizde bu sınıftan üç somut hata bulundu ve düzeltildi:
ISA tablosunun 100 km satırı elle `1000 K` yazılmıştı (doğrusu `186,946 K`);
lüle kütlesi ince kabukla hesaplanıyordu (aynı parçaya 2,5 kat farklı iki
kütle); enjektör buhar basıncını yanlış akışkandan alıyordu. Aşağıdaki
teoremler bu üç sınıfın **tekrar oluşamayacağını** gösteriyor.

## Doğrulanma durumu

Her teoremin altında `#print axioms` çalıştırıldı. Çıktının hepsi
`[propext, Classical.choice, Quot.sound]` — yani **hiçbirinde `sorryAx` yok**,
ispatlarda delik bırakılmadı.

```bash
cd ~/Desktop/dosyalar/lean-lab && lake build
```

## Teoremler

### 1. Alan–Mach bağıntısının tek kökü — `LeanLab/HRMA.lean`

Koruduğu satır: `hrma/analysis/transient_ballistics.py:314-319`

```python
Me = brentq(area_ratio, 1.0001, 50.0)
```

`brentq` aralıkta **tek kök** varsayar. Varsayım geçerli değilse çözücü
sessizce yanlış dala oturur.

| Teorem | Ne diyor |
|---|---|
| `areaRatio_strictMonoOn` | Alan oranı `γ > 1` için `[1, ∞)` üzerinde kesin monoton artandır |
| `areaRatio_root_unique` | Dolayısıyla o aralıkta iki kök varsa eşittirler |

### 2. `brentq` alt sınırının gerekçesi — `LeanLab/HRMANozzleBranch.lean`

Aynı satır, ama bu sefer **neden `1` değil `1.0001`** sorusu.

| Teorem | Ne diyor |
|---|---|
| `areaRatio_strictAntiOn` | Aynı fonksiyon `(0, 1]` üzerinde kesin monoton **azalan**dır |
| `areaRatio_subsonic_root_unique` | Subsonik kök de tektir |
| `branches_disjoint` | Subsonik kök ile süpersonik kök asla aynı sayı değildir |
| `bracket_excludes_subsonic` | `1 < a` seçilen `[a, b]` aralığı subsonik dalın hiçbir noktasını içermez |

Sonuç: `1.0001` sihirli sayı değil, ispatlanmış bir dal ayrımının sayısal
karşılığı. `M = 1` dönüm noktası olduğu için tipik `ε > 1`'de denklemin **iki**
kökü vardır; diverjan lülede fiziksel olan süpersonik olandır.

### 3. Kesik koni halkasının hacmi — `LeanLab/HRMAGeometry.lean`

Koruduğu satır: `hrma/engines/nozzle_design.py:838-843`

```python
#   V = π·(2·t·r_ort + t²)·L
vol_div = np.pi * (2.0 * t_w * (rt + re) / 2.0 + t_w ** 2) * L_div
```

| Teorem | Ne diyor |
|---|---|
| `frustumAnnulusVolume_eq_integral` | Kapalı biçim, disk integraliyle **birebir** aynı — yaklaşım değil, kesin |
| `frustum_minus_thinShell` | İnce kabuk yaklaşımının hatası **tam olarak** `π·t²·L` |
| `thinShell_lt_frustum` | Hata tek yönlü: ince kabuk her zaman **eksik** tahmin eder |
| `thinShell_relative_error` | Bağıl hata `t²/(2·t·r_ort + t²)` — cidar/yarıçap oranıyla büyür |

`t²` terimi "ikinci mertebeden, ihmal edilebilir" görünür. Ölçülen 2,5 katlık
kütle farkı bunun neden yanlış olduğunu gösteriyor; son teorem bunun kapalı
biçimi.

### 4. ISA katman tablosunun tutarlılığı — `LeanLab/HRMAAtmosphere.lean`

Koruduğu satır: `hrma/constants.py:49-62`, `isa_temperature`

Parçalı tanımlı fonksiyonda her katmanın taban sıcaklığı, bir öncekinin o
irtifadaki değerine eşit olmak zorundadır. Değilse fonksiyon sınırda sıçrar ve
aynı irtifayı 10999 m / 11001 m diye sorduğunda farklı atmosfer alırsın.

| Teorem | Ne diyor |
|---|---|
| `isaLayers_all_continuous` | Altı katman sınırının **hepsi** sürekli (0/11/20/32/47/51/71 km) |
| `isaTopTemperature` | Tablo tepesi (84,852 km) sıcaklığı `186,946 K` |
| `isaTop_not_1000` | Elle yazılan `1000 K` yanlıştı ve doğru değerin **5 katından fazlası** |
| `boundary_choice_irrelevant` | Sınırda hangi katmanın seçildiği sonucu değiştirmez |

Ses hızı `√T` ile ölçeklendiği için `1000 K` hatası o irtifadaki Mach ve
sürükleme hesabını kökten bozuyordu.

### 5. Kavitasyon uyarısının hata yönü — `LeanLab/HRMAInjector.lean`

Koruduğu satır: `hrma/utils/injector_design.py:903-905`

```python
k_c = (self.P_tank - self.p_vapor_bar) / max(self.P_tank - self.P_c, 1e-9)
if k_c < NURICK_KC_LIMIT:      # 1.5
```

`p_vapor_bar` her zaman kesin bilinmez. Kritik soru: yanlış tahmin edersek
hata hangi yöne düşer?

| Teorem | Ne diyor |
|---|---|
| `cavitationNumber_strictAnti` | `K_c`, `P_v`'nin kesin azalan fonksiyonudur |
| `underestimate_inflates_kc` | `P_v` küçük tahmin edilirse `K_c` büyük çıkar |
| `conservative_when_overestimated` | `P_v`'yi **büyük** alıp eşiği geçmek **güvenli** — gerçek `K_c` de eşiğin üstünde |
| `underestimate_can_miss_warning` | `P_v`'yi **küçük** alıp eşiği geçmek **hiçbir şey kanıtlamaz** (somut karşı örnek) |
| `kc_below_limit_iff` | Eşik ölçütünün kapalı biçimi: `K_c < 1,5 ⟺ P_v > P₁ − 1,5(P₁ − P₂)` |

Karşı örnek: `P₁ = 50 bar`, `P₂ = 20 bar`. Varsayılan `P_v = 4` → `K_c ≈ 1,53`
(uyarı yok); gerçek `P_v = 10` → `K_c ≈ 1,33` (uyarı gerekli). Program "risk
yok" der, gerçekte kavitasyon vardır.

**Mühendislik sonucu:** `p_vapor_bar` belirsizken "K_c ≥ 1,5, risk yok" çıktısı
**kazanılmamış bir hükümdür**. Hata güvensiz tarafa düşer.

## Toplam

| Dosya | Teorem |
|---|---:|
| `HRMA.lean` | 2 |
| `HRMANozzleBranch.lean` | 4 |
| `HRMAGeometry.lean` | 4 |
| `HRMAAtmosphere.lean` | 4 |
| `HRMAInjector.lean` | 5 |
| **Toplam** | **19** |

## Sınır — bu ispatlar neyi kanıtlamaz

Dürüst olmak gerekirse:

* İspatlar **Lean'de yeniden yazılmış** ifadeler üzerinedir. Python kodunun
  o ifadeyi doğru uyguladığı ayrıca sınanmalıdır (bunun için test paketi var).
  Lean ile Python arasında otomatik bağ yoktur; bağ, dosya başındaki alıntı ve
  satır numarasıdır ve **elle** korunur.
* Fiziksel modelin kendisi değil, modelin **matematiksel tutarlılığı**
  ispatlanır. "Nurick ölçütü doğru ölçüttür" bir deney sorusudur, ispat
  sorusu değil.
* Kayan nokta aritmetiği modellenmez; teoremler gerçel sayılarda geçerlidir.
  Yuvarlama davranışı ayrı bir konudur.
