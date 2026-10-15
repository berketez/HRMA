# data/cfd_referans — Euler yolunun bit-özdeşlik referansları

Viskoz kampanyanın (`docs/mimari/cfd-viskoz-tasarimi.md` §11.3) taşıyıcı
sözleşmesi. Viskoz katman Euler çekirdeğinin **içine** yazılmaz, ayrı bir
kalıntı olarak eklenir (§5.1 kompozisyon ilkesi); bu sözün ölçülebilir
karşılığı, bugünkü çözücüyle dondurulan dört referans alandır. Her viskoz
evre bu dosyalara karşı `np.array_equal` verir — "Euler yolu hâlâ yeşil"
ifadesi davranışsal değil **bit düzeyinde** olur.

## YENİDEN DONDURULDU — ÖH D37 A3a cfd-kok-a (24 Eylül 2026, commit `3f1d9e1e`)

Euler çekirdeği bilerek değişti (kanıt paketi
`docs/scofield/raw/OH/A3a/cfd-kok-a/rapor.md`; ÖNEMLİ sınıf — birleşme
Berke'nin önce/sonra onayına bağlı):

- **F-05 / P6B1-10 kapatıldı:** kayma duvarı akısının yıldız basıncı akustik
  `p·(1+γM_n)` → iki-genişleme (TRRS) `p·[1+(γ−1)M_n/2]^(2γ/(γ−1))` (Toro
  §4.3.2; Lean `HRMA.wallStarTR_pos`). Yakınsamış alanlarda etkisi duvar
  basıncında ≤ 1,4e-4 bağıl, debide ≤ 3e-7.
- **OH-DK-14:** şok sensörü kolon → hücre (Jameson-Schmidt-Turkel, sürekli,
  yalnız sıkışmada).
- **OH-DK-12/13:** açık yol plato-dondurma tetiği iniş kapılı + ölçekli
  pencere + kalıcı stall yolu; şoklu akışta dondurma yok.

Eski dosyalar (2026-08-18 dondurması, künye yenilemesi D32) ve dizi
sha256'ları `tests/test_d32_fea_cfd_a2.py::DIZI_SHA256` içindeydi; yeni
sha256'lar kulvar raporunda (§(e)). Üretici bu kez
`docs/scofield/raw/OH/A3a/cfd-kok-a/referans_dondur_a3a.py` (aracın künye
biçimini ithal eder; aracın `converged` kapısı üç durumlu hükmü tanımadığı
için — `not_evaluated` → ret — cfd-kok-b'ye DEVİR).

## Dosyalar

| Dosya | Izgara | Vaka | Iterasyon | Hüküm | Son kalıntı (yay. / şema) | Boyut |
|---|---|---|---|---|---|---|
| `euler_izantropik_60x12.npz` | 60×12 | tam süpersonik (Pb = 2 kPa) | 8874 | converged | 9,947e-11 / 9,947e-11 | 24,9 KiB |
| `euler_izantropik_120x24.npz` | 120×24 | tam süpersonik (Pb = 2 kPa) | 9010 | not_evaluated (donma 4455, iniş 2,59 mertebe) | 7,221e-12 / 2,118e-4 | 89,1 KiB |
| `euler_sok_60x12.npz` | 60×12 | aşırı-genişlemiş, iç normal şok (Pb = 2,75 MPa) | 19513 | **converged** (eski: 26896 not_evaluated) | 1,996e-6 / 1,996e-6 | 24,8 KiB |
| `euler_sok_120x24.npz` | 120×24 | aşırı-genişlemiş, iç normal şok (Pb = 2,75 MPa) | 18909 | **converged** (eski: 21870 not_evaluated) | 1,999e-6 / 1,999e-6 | 87,6 KiB |

Toplam **226,4 KiB** + `euler_pb_none_kalinti.npz` (222,1 KiB; dört
referansın Pb=None türev kalıntısı, aynı koşuda tazelendi). Bekçi 5 MB üst
sınırını ayrıca ölçer.

## İçerik

Her `.npz` iki dizi taşır:

- `U` — yakınsanan **korunumlu durum** dizisi `(ni, nj, 4)` float64:
  `[ρ, ρu_z, ρu_r, E]`, SI. Çözücünün yayımladığı alanlardan
  `euler_core.prim_to_cons_axisym` ile türetilir (bekçi de aynı dönüşümden
  geçer — karşılaştırma tek yolludur).
- `meta_json` — künye: git commit, üretim tarihi (UTC), platform/mimari,
  Python/NumPy/numba sürümleri, arka uç, ızgara, **çözücü ayarlarının
  tamamı**, koşum sonuçları (iterasyon, hüküm, kalıntı, şema kalıntısı,
  dondurma bloğu `limiter_freeze`, sensör hücre sayısı, duvar p* minimumu,
  debiler, bütçe artıkları), **yenileme gerekçesi**.

Türetilebilir alanlar (M, T, kesit ortalamaları) ve kalıntı geçmişi
**yazılmaz** — depo şişmesin.

## Üretim / yeniden üretim

```bash
PYTHONPATH=. python3 tools/cfd_referans_dondur.py            # eksikleri üret
PYTHONPATH=. python3 tools/cfd_referans_dondur.py --zorla    # hepsini yenile
```

Vaka kurulumu bu betikte **yazılı değildir**: tek kaynak
`tests/cfd/conftest.py` içindeki `EULER_REFERANS_VAKALARI` kaydıdır (aynı
kaydı oturum fikstürleri ve bekçi de okur). Bekçi künyedeki çözücü
ayarlarını kayıtla karşılaştırır; kurulum kayarsa kırmızı olur. DİKKAT
(24 Eyl 2026): araç `converged=None` (not_evaluated) alanı reddeder; üç
durumlu sözleşmeyle uyumlu üretici yukarıdaki A3a betiğidir.

## Bekçi

`tests/cfd/test_euler_bit_ozdesligi.py` (17 bekçi; `HRMA_CFD_BIT_TAM=1` ile
19). Arka uç: referanslar numba ile donduruldu; NumPy yolu bekçide ayrıca
zorlanır. Ölçülen mutasyon ısırığı (2026-08-18): `residual_axisym` içinde
`net / vol` → `net * (1/vol)` dört vakanın dördünü de kırmızıya düşürdü.

## Yenileme kuralı

`--zorla` ile yenilemek **Euler yolunun değiştiğini kabul etmektir**.
Gerekçesi partinin kaydına yazılmadan yapılmaz: bekçinin kırmızısını
susturmanın en kolay yolu budur ve sözleşmenin anlamını yok eder. Bu
yenilemenin gerekçesi: yukarıdaki üç kalem + kulvar raporu; yayımlanan sayı
değişikliği önce/sonra tablosuyla Berke'ye sunulur.

## Platform KAPSAMI (ÖH D31 / defter P13B1-03 ile yeniden kuruldu)

Dosyalar macOS 15 / arm64 (Apple M4 Max), Python 3.12, NumPy 1.26.4,
numba 0.61.0 ile üretildi. Envanterin **beşi de** `darwin/arm64`
künyelidir, yani bu sözleşmenin **kapsamı** o platformdur. Kapsam bekçide
elle yazılmaz, künyelerden okunur
(`test_euler_bit_ozdesligi.referans_platform_kapsami`).

**Kapsam içinde:** bit-özdeşlik **şarttır** (tek ULP kırmızıdır).

**Kapsam dışında** (CI `ubuntu` koşar): bekçi **atlamaz**, ama saklı
referansla karşılaştırma **hüküm vermez** — hüküm `not_evaluated`tır ve
ölçülen sapma sayıyla rapora yazılır (`PLATFORM_SAPMA_RAPORU`;
`HRMA_CFD_PLATFORM_SAPMA_RAPORU=<yol>` ile dosyaya dökülür). Kapsam
dışında bağlayıcı sözleşme çözücünün o platformdaki **belirlenimi**dir
(`tools/cfd_ci_bit_ozdeslik.py`; bekçide `belirlenim_sozlesmesi`
fikstürü). Envantere ikinci platform referansı **eklenmedi** (P10B4-14
gerekçesi).
