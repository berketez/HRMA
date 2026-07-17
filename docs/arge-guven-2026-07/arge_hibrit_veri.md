# ARGE: Açık Literatürden Gerçek Hibrit Motor Static-Fire Verisi (v2.5.0 Doğrulama Veritabanı)

Tarih: 2026-07-17
Yöntem: Tüm sayılar, aksi işaretlenmedikçe, kaynak PDF'in ilgili sayfası/tablosu bu oturumda indirilip DOĞRUDAN OKUNARAK alınmıştır (confidence: high). PDF'ler scratchpad/pdf/ altında saklanmaktadır. Erişilemeyen kaynaklar "erişim yolu" ile işaretlenmiştir; hiçbir sayı ikincil atıftan aktarılmamıştır.

Confidence tanımı:
- high: sayı kaynak tablo/metinden bu oturumda okundu
- medium: abstract/özet düzeyi
- low: ikincil atıf (bu dosyada veri tablosuna SOKULMADI)

---

## KAMPANYA 1 — Rezaei, Soltani, Mohammadi 2018: HTPB/N2O laboratuvar motoru (HRMA'nın mevcut çapası)

Künye: H. Rezaei, M.R. Soltani, A.R. Mohammadi, "Experimental Study of Fuel Regression Rate in a HTPB/N2O Hybrid Rocket Motor", Scientia Iranica B, 25(1), 253-265, 2018.
Erişim: AÇIK — https://scientiairanica.sharif.edu/article_4317_fd78e20a70c3a59449b0ca1fd11047c3.pdf (indirildi: pdf/rezaei2018.pdf)
Confidence: high | Date checked: 2026-07-17

Motor: HTPB grain (ρf = 983 kg/m³), N2O, ön/art yanma odası 25/25 mm, enjektör alanı 1.766 mm², boğaz çapı 8.9 mm (Tablo 2). Ölçüm belirsizlikleri (Tablo 1): basınç %0.14, itki %0.22, mdot_ox %0.74, Isp %0.81, C* %0.81, rdot %0.33.

Regresyon fit'leri (makalede):
- Eş. (10): rdot = 0.3977 · Go^0.3667  (mm/s; Go g/cm²·s)
- Eş. (11): rdot = 0.07577 · Go^0.364 · L^0.293  (L mm — yakıt boyu etkisi dahil)

### Tablo 4 (s.259) — Regresyon korelasyonu testleri (17 test)
| Test | Dp_i (mm) | L (mm) | Dp_f (mm) | mdot_ox (g/s) | t_b (s) | Pc (bar) | İtki (kgf) | mdot_f (g/s) | rdot (mm/s) | O/F | Gox (g/cm²s) | C* (m/s) | Isp (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 26 | 37.0 | 250.4 | 47.2 | 95.77 | 6.55 | 28.60 | 24.78 | 25.36 | 0.779 | 3.78 | 6.88 | 1514 | 204.6 |
| 43 | 26.3 | 250.0 | 37.7 | 96.15 | 6.41 | 28.26 | 25.30 | 21.91 | 0.891 | 4.39 | 11.95 | 1535 | 214.3 |
| 44 | 25.9 | 252.4 | 39.8 | 98.28 | 6.65 | 30.12 | 26.29 | 28.38 | 1.044 | 3.46 | 11.61 | 1522 | 207.6 |
| 47 | 39.8 | 249.0 | 42.4 | 101.98 | 1.50 | 30.96 | 29.12 | 28.40 | 0.882 | 3.59 | 7.70 | 1519 | 223.3 |
| 48 | 42.0 | 249.0 | 44.4 | 93.26 | 1.52 | 26.49 | 23.72 | 26.25 | 0.775 | 3.55 | 6.36 | 1424 | 198.5 |
| 49 | 44.4 | 249.0 | 46.7 | 96.70 | 1.44 | 29.31 | 25.56 | 28.96 | 0.810 | 3.34 | 5.93 | 1494 | 203.4 |
| 50 | 46.7 | 249.0 | 48.8 | 83.26 | 1.55 | 25.70 | 21.32 | 24.45 | 0.653 | 3.41 | 4.65 | 1535 | 197.9 |
| 51 | 48.8 | 249.0 | 50.7 | 94.97 | 1.33 | 29.07 | 24.55 | 28.87 | 0.740 | 3.29 | 4.89 | 1504 | 198.2 |
| 52 | 25.6 | 251.5 | 38.9 | 94.64 | 6.63 | 28.71 | 24.41 | 25.02 | 1.006 | 3.78 | 11.61 | 1538 | 204.0 |
| 54 | 25.9 | 248.5 | 38.4 | 71.23 | 6.63 | 20.86 | 17.04 | 21.93 | 0.940 | 3.25 | 8.79 | 1451 | 182.9 |
| 55 | 38.4 | 248.5 | 45.7 | 75.94 | 5.18 | 21.14 | 17.99 | 21.68 | 0.710 | 3.50 | 5.47 | 1403 | 184.3 |
| 58 | 26.0 | 251.0 | 37.7 | 95.64 | 6.49 | 27.69 | 24.48 | 20.99 | 0.899 | 4.56 | 12.02 | 1524 | 209.9 |
| 59 | 38.9 | 251.0 | 48.0 | 75.91 | 6.60 | 23.47 | 19.85 | 23.20 | 0.693 | 3.27 | 5.12 | 1528 | 200.3 |
| 63 | 37.5 | 251.0 | 47.4 | 87.43 | 6.67 | 25.64 | 22.91 | 22.98 | 0.739 | 3.80 | 6.19 | 1528 | 207.5 |
| 65 | 25.7 | 250.0 | 38.2 | 69.20 | 6.55 | 20.35 | 16.51 | 22.23 | 0.953 | 3.11 | 8.64 | 1477 | 180.6 |
| 67 | 25.4 | 250.0 | 37.8 | 79.92 | 6.54 | 24.52 | 20.56 | 21.87 | 0.948 | 3.65 | 10.20 | 1487 | 202.0 |
| 68 | 37.8 | 249.0 | 47.5 | 66.51 | 6.61 | 19.95 | 15.37 | 22.68 | 0.732 | 2.93 | 4.66 | 1485 | 172.3 |
| 69 | 47.5 | 249.0 | 55.4 | 67.32 | 6.48 | 19.87 | 15.07 | 22.95 | 0.613 | 2.93 | 3.24 | 1462 | 166.9 |

İç tutarlılık kontrolü (bu oturumda yapıldı): rdot = (Dp_f - Dp_i)/(2·t_b) formülü test 26 (0.779), 44 (1.045), 47 (0.867) için tablo değerleriyle uyuşuyor — tablo kendi içinde tutarlı.

### Tablo 5 (s.260) — Yakıt boyu etkisi ek testleri (11 test)
| Test | L (mm) | mdot_ox (g/s) | t_b (s) | Pc (bar) | İtki (kgf) | mdot_f (g/s) | rdot (mm/s) | O/F | Gox (g/cm²s) | C* (m/s) | Isp (s) | Std Isp (s) | Vak Isp (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20 | 147.7 | 88.62 | 6.64 | 22.85 | 17.82 | 11.22 | 0.605 | 7.90 | 6.83 | 1478 | 178.5 | 241.1 | 290.5 |
| 21 | 195.5 | 84.46 | 6.57 | 24.45 | 15.79 | 15.49 | 0.635 | 5.45 | 6.54 | 1576 | 158.0 | 257.1 | 309.7 |
| 23 | 312.0 | 94.62 | 6.54 | 29.06 | 21.56 | 29.82 | 0.745 | 3.17 | 6.94 | 1496 | 173.3 | 244.1 | 294.0 |
| 24 | 311.2 | 94.42 | 6.58 | 28.73 | 22.89 | 30.90 | 0.760 | 3.06 | 6.67 | 1469 | 182.7 | 239.7 | 288.8 |
| 56 | 250.0 | 106.48 | 4.69 | 31.80 | 28.24 | 22.84 | 0.654 | 4.66 | 6.62 | 1572 | 218.4 | 256.4 | 308.8 |
| 62 | 310.0 | 95.40 | 6.63 | 28.28 | 25.65 | 29.20 | 1.007 | 3.27 | 11.85 | 1488 | 205.9 | 242.8 | 292.5 |
| 64 | 251.0 | 83.39 | 6.59 | 24.90 | 21.39 | 21.50 | 0.557 | 3.88 | 3.83 | 1563 | 203.9 | 255.0 | 307.2 |
| 66 | 250.0 | 83.10 | 6.54 | 24.88 | 21.59 | 21.54 | 0.691 | 3.86 | 5.80 | 1566 | 206.3 | 255.4 | 307.6 |
| 70 | 250.0 | 72.36 | 6.33 | 21.46 | 16.66 | 23.90 | 0.802 | 3.03 | 5.53 | 1476 | 173.1 | 240.8 | 290.0 |
| 71 | 202.0 | 73.83 | 5.83 | 22.04 | 17.50 | 18.70 | 0.662 | 3.95 | 4.11 | 1576 | 189.1 | 257.0 | 309.6 |
| 72 | 201.8 | 67.39 | 6.31 | 19.98 | 15.81 | 17.34 | 0.643 | 3.89 | 4.10 | 1566 | 186.6 | 255.4 | 307.7 |

### Tablo 3 (s.258) — Tekrarlanabilirlik (3 test, aynı koşul)
| Test | L (mm) | mdot_ox (g/s) | t_b (s) | Pc (bar) | İtki (kgf) | mdot_f (g/s) | rdot (mm/s) | O/F | C* (m/s) | Isp (s) | Vak Isp (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A1 | 249.0 | 66.51 | 6.61 | 19.95 | 15.37 | 22.68 | 0.732 | 2.93 | 1485 | 172.3 | 291.9 |
| A2 | 249.0 | 67.35 | 6.48 | 19.86 | 15.11 | 22.93 | 0.721 | 2.94 | 1461 | 167.4 | 287.1 |
| A3 | 250.0 | 68.75 | 6.33 | 20.25 | 15.94 | 23.90 | 0.745 | 2.88 | 1450 | 172.0 | 285.0 |
| Ortalama | 249.3 | 67.54 | 6.47 | 20.02 | 15.47 | 23.17 | 0.733 | 2.92 | 1466 | 170.6 | 288.0 |
| Std sapma | 0.577 | 1.133 | 0.140 | 0.204 | 0.425 | 0.646 | 0.012 | 0.034 | 17.934 | 2.787 | 3.524 |

Yanma verimi: %94-98 (metin, s.260). Örnek test 26 tam girdi seti Tablo 2'de (s.257): başlangıç yakıt kütlesi 847.3 g, son 681.2 g.

HRMA simüle edilebilirlik: TAM. Geometri (port, L, boğaz, enjektör alanı), mdot_ox, ρf hepsi var → HRMA ile Pc, itki, O/F, C*, Isp, rdot uçtan uca karşılaştırılabilir. Tekrarlanabilirlik tablosu (Tablo 3) UQ ayağı için deneysel gürültü tabanı sağlar (ör. Pc std %1, rdot std %1.6). Bu kampanya zaten repoda kısmen kullanılıyor (hrma/data/propellant_database.py, satır 25 civarı) — artık 31 noktalık tam tablo mevcut.

---

## KAMPANYA 2 — Karabeyoglu ve ark. 2003: Parafin SP-1a/GOX ölçek büyütme (NASA Ames HCF)

Künye: M.A. Karabeyoglu, G. Zilliac, P. Castellucci, P. Urbanczyk, J. Stevens, G. Inalhan, B.J. Cantwell, "Scale-up Tests of High Regression Rate Liquefying Hybrid Rocket Fuels", AIAA 2003-1162, 41st Aerospace Sciences Meeting, 2003.
Erişim: AÇIK — Stanford AA284A ders deposu: https://web.stanford.edu/~cantwell/AA284A_Course_Material/AA284A_Resources/ (indirildi: pdf/karabeyoglu2003_scaleup.pdf)
Confidence: high | Date checked: 2026-07-17

Tesis: NASA Ames Hybrid Combustion Facility. Grain OD 7.5 inç; yanma odası 47.3 inç uzunluk, iç çap 7.672 inç; GOX (16 kg/s'ye kadar), Pc aralığı ~10-68 atm. Yakıt: SP-1a parafin formülasyonu (erime 69 C), santrifüj döküm. 29 motor testi (23'ü regresyon indirgemesinde kullanıldı; HCF grain boyları 33 ve 45 inç, s.6). Ek olarak Stanford'da 2.38 inç ölçeğinde ~200 laboratuvar testi (bu makalede tablo halinde değil).

Regresyon yasası (Eş. 2, s.6): rdot = 0.488 · Gox^0.62 (mm/s; g/cm²·s), geçerli O/F 1.7-2.3; O/F düzeltmeli biçim Eş. (3): rdot = 0.163·Gox^0.62 / ([(1+1/(O/F))^0.38 - 1]·(O/F)). Basınç etkisi ihmal edilebilir bulundu (s.6). c* verimi hesabı Ek'te (Cd = 0.99).

### Tablo 2 + Tablo 3 birleşik (s.11-12) — motor testleri
(orijinal birimler: port/boğaz çapı inç; Gox g/cm²·s; rdot mm/s; Pc psi)
| Test | Port_i (in) | Boğaz_i (in) | t_b (s) | mdot_ox (kg/s) | Gox_i | Gox_ort | rdot (mm/s) | O/F | Pc (psi) | eta_c* | Not |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ST | 3.972 | 1.98 | 7.00 | 2.07 | 27.12 | 16.66 | 3.59 | 2.18 | 307 | 0.78 | Çatlak grain |
| 4F-2 | 3.620 | 1.45 | 9.25 | 2.06 | 31.65 | 18.33 | 3.09 | 2.67 | 163 | - | Lüle arızası |
| 4F-1 | 4.412 | 1.46 | 9.35 | 2.03 | 20.87 | 14.47 | 2.40 | 3.05 | 527 | 0.85 | Başarılı |
| 4F-1a | 5.098 | 1.98 | 7.60 | 4.02 | - | 21.75 | 3.37 | 3.89 | 501 | 0.91 | Lüle erozyonu/iyi |
| 4F-4 | 3.943 | 1.98 | 8.50 | 4.24 | - | 30.92 | 4.04 | 3.97 | 527 | 0.90 | Lüle erozyonu/iyi |
| 4F-5 | 3.591 | 1.98 | 8.20 | 4.32 | 64.32 | 33.89 | 4.69 | 3.54 | 551 | 0.88 | Lüle erozyonu/iyi |
| 4F-1b | 4.415 | 1.45 | 9.50 | 2.13 | 21.58 | 14.22 | 2.65 | 2.72 | 562 | 0.85 | Başarılı |
| 4Thr-1 | 3.501 | 1.45 | 10.50 | 1.56 | 35.00 | 13.76 | 2.97 | 2.02 | 417 | 0.77 | Başarılı/kısma (throttling) |
| 4F-1c | 5.131 | 1.45 | 10.35 | 2.07 | 15.88 | 11.45 | 2.15 | 3.00 | 542 | 0.89 | Başarılı |
| 4F-3a | 4.464 | 1.98 | 8.30 | 4.39 | 44.89 | 27.13 | 3.90 | 3.84 | 568 | 0.90 | Başarılı |
| 4L-01 | 4.450 | 1.98 | 8.45 | 4.40 | 44.49 | 27.05 | 3.66 | 2.57 | 671 | 0.88 | Başarılı |
| 4P-01 | 4.482 | 2.80 | 8.40 | 4.43 | 44.36 | 27.41 | 3.52 | 2.69 | 318 | 0.82 | Başarılı |
| 4P-02 | 4.600 | 1.62 | 7.25 | 4.42 | 39.23 | 26.96 | 3.82 | 2.48 | 994 | 0.87 | Başarılı |
| 4P-03 | 4.423 | 1.62 | 8.25 | 4.41 | 43.31 | 27.88 | 3.58 | 2.65 | 939 | 0.88 | Başarılı |
| 4L-03 | 5.536 | 1.98 | 6.20 | 4.45 | 29.11 | 22.05 | 3.18 | 2.69 | 642 | 0.84 | Başarılı |
| 4L-04 | 3.517 | 1.98 | 8.30 | 4.44 | 72.46 | 36.80 | 4.17 | 2.66 | 657 | 0.85 | Başarılı |
| 4L-05 | 3.941 | 1.98 | 8.25 | 4.43 | 57.57 | 32.44 | 3.84 | 2.72 | 649 | 0.85 | Başarılı |
| 4L-06 | 3.009 | 1.98 | 8.20 | 4.40 | 98.80 | 36.87 | 5.72 | 1.97 | 679 | 0.80 | Port yapısal arıza |
| 4L-07 | 2.968 | 2.040 | 8.00 | 4.43 | 102.73 | 33.77 | 6.73 | 1.63 | 652 | 0.80 | Port yapısal arıza |
| 4L-08 | 4.055 | 2.212 | 8.15 | 4.42 | 54.32 | 31.29 | 3.82 | 2.64 | 525 | 0.85 | Başarılı |
| 4I-01 | 4.434 | 2.808 | 8.25 | 4.47 | 43.62 | 26.76 | 4.02 | 2.40 | 319 | 0.78 | Başarılı |
| 4P-04 | 4.433 | 2.817 | 8.15 | 2.11 | 22.79 | 14.69 | 2.74 | 1.78 | 159 | 0.78 | Başarılı |
| 4L-09 | 3.544 | 2.190 | 8.15 | 2.05 | 32.85 | 19.21 | 3.26 | 1.70 | 265 | 0.80 | Başarılı |
| 4L-10 | 4.454 | 2.415 | 8.20 | 5.55 | 55.25 | 34.66 | 4.25 | 2.89 | 590 | 0.88 | Başarılı |
| 4L-11 | 6.057 | 2.020 | 2.55 | 1.47 | 8.68 | 7.43 | 2.00 | 1.56 | 213 | 0.78 | Kontrol sistemi arızası |
| 4L-12 | 4.055 | 2.020 | 7.30 | 2.08 | 11.06 | 9.40 | 1.96 | 2.01 | 301 | 0.79 | Başarılı |
(4F-2a-1, 4F-2a-2, 4F-3: veri indirgemesi yok — erken kapanma / yeniden ateşleme / enjektör yangını)

HRMA simüle edilebilirlik: YÜKSEK. Port çapı, boğaz çapı, t_b, mdot_ox, O/F, Pc, eta_c* test başına mevcut; grain boyu test başına tablo halinde verilmemiş (33/45 inç, metinden) — L ataması notlanarak yapılmalı. Parafin/GOX kombinasyonu için HRMA'nın entrainment/regresyon modelini 8-68 bar aralığında sınar. Lüle erozyonlu ve arızalı testler etiketlenip filtrelenebilir (arıza etiketleri güvenlik analizi için ayrıca değerli).

---

## KAMPANYA 3 — Whitmore & Stoddard 2020: GOX/ABS ve Nytrox87/ABS küçük itici (USU)

Künye: S.A. Whitmore, D.P. Stoddard, "Nytrox as 'Drop-in' Replacement for Gaseous Oxygen in SmallSat Hybrid Propulsion Systems", Aerospace 2020, 7(4), 43. doi:10.3390/aerospace7040043 (hakemli, açık erişim).
Erişim: AÇIK — MDPI CDN (indirildi: pdf/whitmore_nytrox2020.pdf; not: mdpi.com ana sitesi botları 403'lüyor, mdpi-res.com CDN çalışıyor)
Confidence: high | Date checked: 2026-07-17

### Tablo 1 (s.11) — Motor geometrisi
| Bileşen | Değer |
|---|---|
| Enjektör (tek port) | çap 0.127 cm |
| ABS grain | çap 3.168 cm, boy 5.1 cm, başlangıç kütle 45.0 g, başlangıç port çapı 0.53 cm, baskı yoğunluğu ~1.04 g/cm³ |
| Motor gövdesi | çap 3.8 cm, boy 7.92 cm |
| Lüle (grafit) | boğaz 0.345 cm, çıkış 0.483 cm, oran 2.07:1 konik, çıkış açısı 5 derece |

### Tablo 3 (s.22) — Test istatistikleri (ortalama μ, std σ, %95 güven)
GOX/ABS taban çizgisi (13 yakma):
| Büyüklük | μ | σ | %95 güven |
|---|---|---|---|
| İtki (yük hücresi) [N] | 10.70 | 0.645 | 0.339 |
| İtki (P0'dan) [N] | 10.90 | 0.617 | 0.373 |
| CF (yük/P0) | 1.262 / 1.273 | 0.031 / 0.026 | 0.019 / 0.016 |
| Isp (yük/P0) [s] | 224.9 / 224.8 | 7.52 / 8.83 | 4.54 / 5.34 |
| c* [m/s] | 1751.4 | 23.84 | 14.40 |
| Yanma verimi | 0.919 | 0.089 | 0.054 |
| O/F | 1.772 | 0.228 | 0.178 |
| P0 [kPa] | 762.9 | 62.82 | 37.94 |
| Toplam debi [g/s] | 4.85 | 0.349 | 0.211 |

Nytrox87/ABS (19 yakma):
| Büyüklük | μ | σ | %95 güven |
|---|---|---|---|
| İtki (yük/P0) [N] | 11.75 / 11.70 | 0.749 / 0.759 | 0.358 / 0.366 |
| CF (yük/P0) | 1.227 / 1.222 | 0.034 / 0.039 | 0.017 / 0.019 |
| Isp (yük/P0) [s] | 204.4 / 198.4 | 10.29 / 11.10 | 54.96* / 5.34 |
| c* [m/s] | 560.84 (baskı hatası; fiziksel olarak 1560.84 olmalı — bkz. not) | 57.46 | 27.68 |
| Yanma verimi | 0.927 | 0.106 | 0.051 |
| O/F | 3.464 | 0.463 | 0.223 |
| P0 [kPa] | 809.7 | 32.84 | 15.82 |
| Toplam debi [g/s] | 6.14 | 0.356 | 0.171 |

Not (dürüstlük kaydı): Makale tablosunda Nytrox c* değeri "560.84" basılmıştır; Şekil 16b (1400-1800 m/s ekseni) ve Isp = c*·CF/g0 tutarlılığı (1560.84 · 1.222 / 9.81 ≈ 194 s ≈ tablodaki 198.4) değerin 1560.84 m/s olduğunu gösteriyor — baş "1" rakamı dizgide düşmüş. Aynı şekilde GOX satırındaki 1751.4 · 1.262 / 9.81 ≈ 225 s = tablodaki Isp; tablo kendi içinde bu şekilde doğrulanıyor. (*) 54.96 değeri de büyük olasılıkla 4.96'nın baskı hatasıdır; ham olarak kaydedildi.

### Tablo 4 (s.26) — Güç yasası fit parametreleri (rdot = a·Gox^n; rdot cm/s, Gox g/cm²·s)
| Yakıt/Oksitleyici | a | n |
|---|---|---|
| GOX/ABS | 0.0428 | 0.524 |
| Nytrox87/ABS | 0.0354 | 0.455 |
| N2O/ABS | 0.00742 | 0.799 |
| N2O/HTPB | 0.00795 | 0.773 |
| Parafin/LOX | 0.0488 | 0.491 |
| LOX/HTPB | 0.0146 | 0.681 |
| LOX/HTPB-Escorez | 0.0099 | 0.680 |
| LOX/HDPE | 0.0098 | 0.620 |
(Birim çapraz kontrolü: Parafin/LOX 0.0488 cm/s = Zilliac 2006'daki 0.488 mm/s ile birebir tutarlı.)

HRMA simüle edilebilirlik: TAM (küçük itici sınıfı). Tam geometri + istatistikler; tek nokta enjektör. 13+19 = 32 yakmanın ortalama/σ değerleri UQ doğrulaması için birebir kullanılabilir (HRMA Monte Carlo çıktısındaki dağılım, deneysel σ ile karşılaştırılır). N2O/ABS ve N2O/HTPB a-n katsayıları HRMA regresyon kütüphanesine doğrudan girer.

---

## KAMPANYA 4 — Hansen & Edwards 2012: O-sınıfı Parafin-HTPB/N2O blowdown motoru (Univ. of Washington SARP)

Künye: V.K. Hansen, T.C. Edwards, "Development of an O-Class Paraffin/HTPB-N2O Hybrid Rocket Motor", University of Washington SARP, 2012 (AIAA formatlı konferans/rapor; hakemli dergi değil — hiyerarşide konferans/rapor düzeyi).
Erişim: AÇIK — http://vkhansen.pbworks.com/w/file/fetch/59877871/Development_of_an_O_Class_Paraffin_HTPB-N2O_Hybrid_Rocket_Motor(2012).pdf (indirildi: pdf/hansen2012_oclass.pdf)
Confidence: high (tablo doğrudan okundu) | Date checked: 2026-07-17

Sistem: 25 L, 6061-T6 alüminyum N2O tankı (blowdown), polikarbonat diyafram + piroteknik ateşleme. Test 2-4 grain: 10.16 cm OD x 7.1 cm iç çap x 30 cm, 1.5 kg; %88 parafin / %10 HTPB / %2 karbon karası. Test 5 grain: 11.43 cm OD x 5.8 cm iç çap x 42.5 cm, 2.9 kg; %80 parafin / %10 HTPB / %8 Al (3 mikron) / %2 CB; lüle genişleme 1:4 (test 5: 1:4.9); tasarım Pc 2000 kPa (test 5: 2750 kPa).

### Ek tablo (s.10) — Tam ölçekli test serisi
| Test | Tarih | İtki ort (N) | σ | N2O tank P ort (kPa abs) | N2O T_i (C) | N2O yoğunluk ort (kg/m³) | Pc ort (kPa abs) | Pc σ | Enjektör alanı (m²) | Enj. ΔP (kPa) | Boğaz alanı (m²) | Genişleme | Cd | mdot ort (kg/s) | N2O tüketimi (kg) | Sıvı enjeksiyon süresi (s) | Toplam impuls (N·s) | Yakıt kütlesi (kg) | Isp sıvı faz (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2 | 6/8/2011 | 1765.19 | 397.54 | 3354.76 | 8.6 | 892.4 | 1586.79 | 325.00 | 3.74804E-05 | 1767.98 | 0.000993208 | 4 | 0.8 | 1.68 | 16.15 | 9.59 | 16928.19 | 1.5 | 97.75 |
| 3 | 6/11/2011 | 1812.13 | 352.25 | 3438.38 | 9.4 | 887.2 | 1917.96 | 301.33 | 3.74804E-05 | 1520.42 | 0.00079178 | 4 | 0.8 | 1.56 | 15.29 | 9.82 | 17795.08 | 1.5 | 108.01 |
| 4 | 6/18/2011 | 1676.57 | 249.17 | 3906.47 | 14.17 | 858.1 | 1887.57 | 197.25 | 3.74804E-05 | 2018.89 | 0.00079178 | 4 | 0.8 | 1.76 | 14.53 | 8.23 | 13798.19 | 1.5 | 87.77 |
| 5 | 2/27 (ek tabloda; Şekil 9 başlığı 2/26/2012) | 1637.55 | 272.03 | 2625.28 | -2.2 | 939.8 | 2026.77 | 268.44 | 5.11097E-05 | 598.50 | 0.00079178 | 4.9 | 0.8 | 1.37 | 10.53 | 7.68 | 12576.40 | 2.9 | 95.44 |

Regresyon ölçümü (test 5, flaş X-ray, s.8): önce/sonra karşılaştırması 2.33 mm/s; önce/sırasında 1.99 mm/s. Karşılaştırma amaçlı kullandıkları Stanford parafin/N2O katsayıları: a = 0.155, n = 0.5 (kaynak: McCormick ve ark. AIAA 2003-6475) → tahmini 2.49 mm/s. Uyarılar: test 5'te grain alt yarısı ayrılıp lüleden atıldı (yapısal arıza, X-ray ile belgelendi); test 2-4'te yanma kararsızlıkları (ilk yarı) — ön kenar basamağı yokluğuna bağlanıyor. Isp değerleri düşük çünkü motor tasarım O/F'sinden çok uzak çalıştı (mdot_ox 1.68 kg/s'e karşı mdot_f ~0.16 kg/s → O/F ~10).

HRMA simüle edilebilirlik: YÜKSEK ve ÖZEL DEĞERLİ — HRMA'nın blowdown/transient modülü için uçtan uca senaryo: tank hacmi, N2O sıcaklık/yoğunluk, enjektör alanı + Cd, boğaz alanı, grain geometrisi hepsi var; itki/Pc/tank basıncı zaman izleri Şekil 8-9'da (sayısallaştırma gerekir). Kusurlu testler kararsızlık/arıza senaryoları için etiketli tutulmalı.

---

## KAMPANYA 5 — Wei ve ark. 2025: N2O ve Nytrox blowdown HRE (NCKU/NYCU Tayvan)

Künye: S.-S. Wei, J.-C. Hsu ve ark., "Investigation of Performance Stability of a Nytrox Hybrid Rocket Propulsion System", Aerospace 2025, 12(5), 372. doi:10.3390/aerospace12050372 (hakemli, açık erişim).
Erişim: AÇIK — MDPI CDN (indirildi: pdf/nytrox_stability2025.pdf)
Confidence: high | Date checked: 2026-07-17

Motor: Polipropilen (PP) tek portlu grain, OD 80 mm, başlangıç port 26 mm, boy 240 mm; girdaplı (swirling) enjektör; tasarım 45 kgf itki, Pc 40 barA, O/F ~7 (saf N2O), Isp 220 s; 8 s yanma; yatay statik test.

### Tablo 3 (s.13) — Saf N2O testleri (6 test; blowdown, tank = buhar basıncı)
| N2O buhar basıncı (barA) | 40.9 | 45.5 | 48.5 | 52.4 | 58.0 | 63.1 |
|---|---|---|---|---|---|---|
| Ort. Pc (barA) | 26.2 | 31.7 | 34.1 | 35.5 | 38.3 | 41.6 |
| Toplam impuls (kgf·s) | 188.1 | 228.4 | 249.8 | 259.5 | 284.8 | 314.3 |
| Ort. itki (kgf) | 26.7 | 33.8 | 35.9 | 38.5 | 43.6 | 45.0 |
| Ort. deniz sev. Isp (s) | 193.3 | 205.3 | 211.7 | 203.2 | 215.6 | 216.5 |
| Sıvı N2O sıcaklığı (C) | 10.8 | 14.9 | 18.1 | 21.5 | 26.3 | 29.8 |

### Tablo 4 (s.15) — Nytrox testleri (5 test; tank ~60 barA O2 basınçlandırmalı)
| N2O buhar basıncı (barA) | 36.3 | 41.3 | 46.0 | 48.0 | 53.6 |
|---|---|---|---|---|---|
| Test öncesi tank (barA) | 60.6 | 60.4 | 60.0 | 60.8 | 60.6 |
| Ort. Pc (barA) | 37.3 | 38.4 | 37.8 | 37.1 | 38.8 |
| Toplam impuls (kgf·s) | 310.7 | 306.2 | 305.9 | 311.7 | 303.7 |
| Ort. itki (kgf) | 45.3 | 45.1 | 45.7 | 45.6 | 44.6 |
| Ort. deniz sev. Isp (s) | 229.1 | 222.6 | 227.1 | 216.7 | 219.2 |
| Sıvı N2O sıcaklığı (C) | 5.9 | 11.3 | 15.9 | 18.3 | 22.6 |
| Çözünmüş O2 kütle oranı (%) | 2.9 | 2.7 | 2.6 | 2.2 | 1.2 |

Ek bulgular: saf N2O'da itki, buhar basıncıyla neredeyse doğrusal (fit: y = 0.7977x - 3.7422, R² = 0.9499, Şekil 15); Nytrox'ta itki ~sabit 45.3 ± 0.7 kgf, impuls 307.6 ± 3.9 kgf·s; Pc/itki/impuls varyasyon katsayıları %1.9/%1.0/%1.1. İtki-zaman, Pc-zaman ve tank basıncı izleri Şekil 13-14'te.

HRMA simüle edilebilirlik: YÜKSEK — özellikle HRMA'nın blowdown + N2O buhar basıncı (sıcaklık bağımlılığı) modeli için birebir: oksitleyici sıcaklığı girdisiyle Pc/itki tahmini bu 11 test noktasına karşı korele edilebilir. Ortam sıcaklığı duyarlılığı UQ senaryosu olarak hazır (aynı motor, 6 farklı sıcaklık). Eksik: mdot_ox test başına tablo halinde verilmemiş (izlerden türetilebilir), rdot ölçümü rapor edilmemiş.

---

## KAMPANYA 6 — Zilliac & Karabeyoglu 2006: GOX regresyon a-n derlemesi (14 yakıt)

Künye: G. Zilliac, M.A. Karabeyoglu, "Hybrid Rocket Fuel Regression Rate Data and Modeling", AIAA 2006-4504, 42nd Joint Propulsion Conference, 2006.
Erişim: AÇIK — Stanford AA284A deposu (indirildi: pdf/zilliac2006.pdf; resmi: doi 10.2514/6.2006-4504)
Confidence: high | Date checked: 2026-07-17

### Tablo 2 (s.16) — Oksijenle ortalama regresyon testleri özeti
(rdot = a·Gox^n·x^m, m = 0; Gox g/cm²·s → rdot mm/s. DA: çap-ortalamalı, OA: diğer)
| No | Yakıt | a | n | Test sayısı | Pc aralığı (MPa) | O/F aralığı | Veri indirgeme | Gox aralığı (g/cm²s) | Kaynak (makale ref) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Parafin SP1A | 0.488 | 0.62 | 65 | 1.1-6.9 | 1.0-4.0 | DA | 1.6-36.9 | 15 |
| 2 | HTPB (Thiokol) | 0.146 | 0.681 | 16 | - | - | - | 3.8-30.2 | 16 |
| 3 | HTPB+%19.7 Al | 0.117 | 0.956 | 2 | 1.2 | - | OA | 5.1-23.0 | 17 |
| 4 | HTPB | 0.304 | 0.527 | 3 | 2.0 | - | OA | 6.2-31.0 | 17 |
| 5 | HTPB+%20 GAT | 0.473 | 0.439 | 5 | - | - | - | - | 18 |
| 6 | PMMA | 0.087 | 0.615 | 8 | 0.3-2.6 | - | - | 3.3-26.6 | 19 |
| 7 | HDPE | 0.132 | 0.498 | 4 | 0.7-1.3 | 3.8-5.9 | DA | 7.7-26.1 | 20 |
| 8 | PE Wax, Marcus 200 | 0.188 | 0.781 | 4 | 0.5-1.2 | 2.2-3.2 | DA | 4.8-15.8 | 20 |
| 9 | PE Wax, Polyflo 200 | 0.134 | 0.703 | 3 | 0.6-1.2 | 1.6-1.7 | DA | 4.4-16.3 | 20 |
| 10 | HTPB | 0.194 | 0.670 | 6 | - | - | OA | 17.5-32.0 | 21 |
| 11 | HTPB+%13 nano Al | 0.145 | 0.775 | 12 | - | - | OA | 16.5-34.2 | 21 |
| 12 | Parafin FR5560+%13 nano Al | 0.602 | 0.730 | 8 | - | - | OA | 14.5-29.0 | 21 |
| 13 | Parafin FR5560 | 0.672 | 0.600 | 4 | - | - | OA | 6.3-12.3 | 21 |
| 14 | Parafin FR4550 | 0.427 | 0.748 | 3 | 0.7-? | 1.3-1.8 | DA | 4.3-11.9 | 20 |

Makalenin kendi uyarısı (s.17, aynen özet): ölçek, O/F, enjektör, yakıt formülasyonu ve veri indirgeme tekniği rapor edilen regresyon verisini güçlü etkiler; veriler "yalnızca tasarım amaçlı" kullanılmalı, uygulamaya özgü kombinasyon bağımsız doğrulanmalı. Ayrıca k (ReD üssü) -0.50 ile -0.25 arasında ölçülüyor; k=-0.2 ile k=-0.5 farkı regresyonda 10 kata varan fark yaratabilir (s.13) — bu cümleler HRMA UQ'sunda regresyon belirsizlik aralığının gerekçesi olarak birebir kullanılabilir. Tablo 3 (s.18): PMMA/HDPE/HTPB fiziksel özellik seti (ρf, hg, Ts, O/F_stoic vb.) model girdisi olarak mevcut.

HRMA simüle edilebilirlik: DOĞRUDAN — bu tablo bir "test kampanyası" değil, 133 testin fit özeti; HRMA'nın regresyon katsayı kütüphanesi + UQ önsel (prior) dağılımları için temel kaynak. Nokta bazlı doğrulama için değil, katsayı bandı için kullanılmalı.

---

## KAMPANYA 7 — McFarland & Antunes 2019: 7 farklı FDM baskı yakıtı, küçük ölçek (James Cook Univ.)

Künye: M. McFarland, E. Antunes, "Small-Scale Static Fire Tests of 3D Printing Hybrid Rocket Fuel Grains Produced from Different Materials", Aerospace 2019, 6(7), 81. doi:10.3390/aerospace6070081 (hakemli, açık erişim).
Erişim: AÇIK — MDPI CDN (indirildi: pdf/mcfarland2019.pdf)
Confidence: high (tablo değerleri) | Date checked: 2026-07-17

Grain: 100 mm boy, 20 mm OD, 6 mm düz dairesel port; 3 s yakmalar; deneyler üçer tekrar. Pc sensörü Honeywell 10 bar (değerler tabloda rapor edilmemiş); 1.0 MPa emniyet valfi.

### Tablo 2 (s.7) — Sonuçlar (zaman-ortalamalı)
| Malzeme | ρ (kg/m³) | mdot_ox (kg/s) | mdot_fuel (kg/s) | O/F | mdot_total (kg/s) | rdot (mm/s) |
|---|---|---|---|---|---|---|
| ABS | 1010 | 0.0100 | 0.0023 | 4.35 | 0.0123 | 1.05 |
| ASA | 1000 | 0.0125 | 0.0030 | 4.17 | 0.0155 | 1.59 |
| AL (PLA+Al) | 1330 | 0.0108 | 0.0025 | 4.32 | 0.0133 | 1.20 |
| PLA | 1225 | 0.0100 | 0.0025 | 4.00 | 0.0125 | 1.23 |
| PETG | 1230 | 0.0108 | 0.0035 | 3.09 | 0.0143 | 0.94 |
| Nylon | 1150 | 0.0100 | 0.0027 | 3.70 | 0.0127 | 1.51 |
| PP | 890 | 0.0100 | 0.0023 | 4.35 | 0.0123 | 1.23 |

KRİTİK VERİ BOŞLUĞU (bu oturumda tam metin taranarak doğrulandı): Makale OKSİTLEYİCİ TÜRÜNÜ HİÇBİR YERDE adlandırmıyor ("oxidizer bottle" ifadesi geçiyor; USU GOX/ABS literatürüne atıf yapıyor, muhtemelen oksijen ama metinde yok). Ayrıca Tablo 1'de PP yoğunluğu 980, Tablo 2'de 890 kg/m³ — makale içi tutarsızlık. Pc değerleri rapor edilmemiş.

HRMA simüle edilebilirlik: SINIRLI — oksitleyici türü doğrulanmadan simülasyona SOKULMAMALI (yazara e-posta veya JCU tez versiyonu ile teyit gerekir). Teyit edilirse ABS/PLA regresyon karşılaştırması için 7 nokta.

---

## KAMPANYA 8 — Jens ve ark. 2019: Yüksek basınçta hibrit yanma görselleştirmesi (Stanford/JPL)

Künye: E.T. Jens, A.C. Karp, V.A. Miller, G.S. Hubbard, B.J. Cantwell, "Experimental Visualization of Hybrid Combustion: Results at Elevated Pressures", Journal of Propulsion and Power (2019), doi:10.2514/1.B37416 (hakemli).
Erişim: AÇIK KOPYA — Stanford AA284A deposu (indirildi: pdf/jens2019_elevated.pdf)
Confidence: high | Date checked: 2026-07-17

Düzenek: GOX ile dikdörtgen kesitli görselleştirme yanma odası (slab yakıt; itki üretmez). Yakıtlar: PMMA (klasik) ve karartılmış parafin (FR5560 + %0.5 siyah boya). Pc 101.3-1524.2 kPa; Gox 20.4-74.4 kg/m²·s (= 2.04-7.44 g/cm²·s).

### Tablo A1 (s.11) — Test özeti (16 test)
| Test | Tarih | Yakıt | Maks Pc kPa (psi) | Gox (kg/m²s) | t_b (s) | Yanan yakıt (g) |
|---|---|---|---|---|---|---|
| 7 | 30 Haz 2014 | Parafin | 294.9 (42.8) | 20.5 | 3.5 | 2.3 |
| 8 | 30 Haz 2014 | Parafin | 490.0 (71.1) | 36.6 | 3.5 | 5.1 |
| 9 | 1 Tem 2014 | Parafin | 835.8 (121.2) | 20.4 | 3.5 | 6.7 |
| 10 | 4 Tem 2014 | Parafin | 1175.0 (170.4) | 36.3 | 3.5 | 8.2 |
| 14 | 18 Tem 2014 | Parafin | 616.8 (89.5) | 43.4 | 3.5 | 6.7 |
| 16 | 23 Tem 2014 | PMMA | 444.0 (64.4) | 43.3 | 3.5 | 2.1 |
| 17 | 25 Tem 2014 | Parafin | 1524.2 (221.1) | 43.3 | 3.5 | 17.5 |
| 19 | 4 Ağu 2014 | HDPE | 101.3 (14.7) | 43.2 | 3.5 | 0.9 |
| 21 | 5 Ağu 2014 | PMMA | 101.3 (14.7) | 43.3 | 5 | 2.0 |
| 22 | 6 Ağu 2014 | Parafin | 101.3 (14.7) | 43.5 | 3.5 | 4.1 |
| 23 | 6 Ağu 2014 | PMMA | 948.3 (137.5) | 43.3 | 3.5 | 4.0 |
| 29 | 8 Ağu 2014 | Parafin-üst | 1455.7 (211.1) | 54.3 | 3.5 | 12.9 |
| 30 | 2 Haz 2015 | Parafin | 101.3 (14.7) | 74.4 | 4 | 6.1 |
| 31 | 3 Haz 2015 | Parafin | 582.7 (84.5) | 73.1 | 3.5 | 8.5 |
| 34 | 8 Haz 2015 | Parafin | 1430.3 (207.4) | 73.1 | 3.5 | 13.5 |
| 35 | 9 Haz 2015 | Parafin | 1423.2 (206.4) | 73.0 | 3.5 | 13.4 |

HRMA simüle edilebilirlik: ORTA-DÜŞÜK — slab geometri, lüle/itki yok; motor düzeyi korelasyona girmez. Değeri: parafinin süperkritik basınç (>~6.7 bar) üstündeki damlacık/entrainment davranışının nitel doğrulaması ve yakıt kütle kaybı-Gox-Pc üçlüsünden basınç etkisi kontrolü. Ayrıca Tablo 1'de (s.3) test 34 için CEA'lı alev/serbest akım özellik örneği (T = 3466 K, O/F 3.45, 1379 kPa) HRMA termokimya karşılaştırmasına birebir mini-vaka.

---

## KAMPANYA 9 — Palacz & Cieślik 2023: N2O/HDPE Vortex Flow Pancake motoru (AGH Krakow)

Künye: T. Palacz, J. Cieślik, "Testing of the N2O/HDPE Vortex Flow Pancake Hybrid Rocket Engine with Augmented Spark Igniter", Aerospace 2023, 10(8), 727. doi:10.3390/aerospace10080727 (hakemli, açık erişim).
Erişim: AÇIK — MDPI CDN (indirildi: pdf/vortex_pancake2023.pdf)
Confidence: high | Date checked: 2026-07-17

Tasarım (Tablo 2, s.5): N2O/HDPE; yanma odası çapı 85 mm; grain boyları 40 (üst) / 35 (alt) mm; alt port 20 mm; boğaz 4/6/6.4 mm; enjektör orifisi 0.5/0.8/1.2 mm; 2 enjektör. Ön tasarım balistiği için kullandıkları katsayı: rdot = 0.111·Gox^0.677 (keyfi seçim, kendi uyarılarıyla).

### Tablo 5 (s.13) — Sıcak test sonuçları (11 test)
| Test | Dt (mm) | Dinj (mm) | t_ign (s) | t_b (s) | Δm_üst (g) | Δm_alt (g) | Go_vorteks (g/cm²s) | rdot_üst (mm/s) | rdot_alt (mm/s) | mdot_f (g/s) | mdot_ox (g/s) | O/F | Pc_ort (bar) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 4.0 | 0.5 | 3.0 | 4.96 | 6.7 | 6.8 | 1.22 | 0.25 | 0.09 | 2.72 | 4.03 | 1.48 | 6.71 |
| 2 | 4.0 | 0.5 | 3.0 | 5.66 | 7.0 | 6.9 | 1.83 | 0.23 | 0.08 | 2.45 | 6.07 | 2.48 | 8.54 |
| 3 | 6.0 | 0.8 | 3.0 | 4.27 | 7.3 | 8.2 | 4.20 | 0.31 | 0.16 | 3.62 | 13.93 | 3.84 | 9.32 |
| 4 | 6.0 | 0.8 | 3.0 | 4.27 | 12.6 | 15 | 3.84 | 0.54 | 0.48 | 6.45 | 12.72 | 1.97 | 12.71 |
| 5 | 6.4 | 1.2 | 10.0 | 5.2 | 23.3 | 28.5 | 7.67 | 0.86 | 0.72 | 10.36 | 26.45 | 2.55 | 20.17 |
| 6 | 6.4 | 1.2 | 10.0 | 5.2 | 22.8 | 28.2 | 7.79 | 0.84 | 0.72 | 10.20 | 26.86 | 2.64 | 20.07 |
| 7 | 6.4 | 1.2 | 10.0 | 5.2 | 22.5 | 28 | 7.62 | 0.83 | 0.71 | 10.10 | 26.26 | 2.60 | 19.71 |
| 8 | 6.4 | 1.2 | 10.0 | 2.2 | 10.7 | 13 | 7.14 | 0.98 | 0.82 | 11.85 | 26.05 | 2.20 | 18.18 |
| 9 | 6.4 | 1.2 | 10.0 | 2.2 | 11.4 | 14 | 7.27 | 1.05 | 0.88 | 12.70 | 26.50 | 2.09 | 19.44 |
| 10 | 6.4 | 1.2 | 10.0 | 2.2 | 11.3 | 14.6 | 6.50 | 1.04 | 0.92 | 12.95 | 23.70 | 1.83 | 20.08 |
| 11 | 6.4 | 1.2 | 10.0 | 5.1 | 27.9 | 32.8 | 7.03 | 1.00 | 0.94 | 11.90 | 23.29 | 1.96 | 19.6 |

HRMA simüle edilebilirlik: DÜŞÜK (motor balistiği için) — VFP (pancake/vorteks) geometrisi HRMA'nın silindirik port modeline uymaz. Değeri: (1) N2O besleme/blowdown ve enjektör orifis boyutlandırma doğrulaması (Şekil 9: tank/besleme/Pc izleri + N2O kütle izi), (2) HRMA'nın kapsam sınırlarını belgeleyen "modellenemeyen geometri" negatif örneği.

---

## Değerlendirilip ELENEN kaynaklar (yeniden iş yapılmasın diye)

1. Srivastava, Ingenito, Andriani, "Numerical and Experimental Study of a 230 N Paraffin/N2O hybrid rocket", EUCASS 2019, doi:10.13009/EUCASS2019-866 — indirildi ve tamamı okundu: içerik CFD + boyutlandırma; ÖLÇÜLMÜŞ static-fire tablosu YOK (test sehpası şeması var, veri yok). Doğrulama DB'sine girmez.
2. Marquardt & Majdalani, "A Primer on Classical Regression Rate Modeling in Hybrid Rockets" (par.nsf.gov/servlets/purl/10274228) — indirildi: teori derlemesi, deney tablosu yok. Model referansı olarak faydalı, veri kaynağı değil.
3. Blog/forum/haber kaynakları (Dewesoft, ScienceDaily vb.) — kural gereği alınmadı.

## Erişilemeyen / insan eliyle indirilecek yüksek değerli hedefler

| Kaynak | İçerik beklentisi | Erişim yolu | Durum |
|---|---|---|---|
| Whitmore, Peterson, Eilers, "Deep Throttle of a Nitrous Oxide and HTPB Hybrid Rocket Motor", JPP (USU mae_facpub/34) | ~800 N N2O/HTPB motorun 8:1 üzeri kısma testleri (abstract: 800 N → <12 N, kararlı) | https://digitalcommons.usu.edu/mae_facpub/34/ — site otomatik istemcilere 403 veriyor; tarayıcıyla indirilebilir | medium (abstract düzeyi), tablolar okunmadı — SAYI ALINMADI |
| Peterson USU yüksek lisans tezi "Closed-Loop Thrust and Pressure Profile Throttling of an N2O/HTPB Hybrid" | Aynı motorun tam test verisi | https://digitalcommons.usu.edu/etd/1400/ (viewcontent article=2407) — aynı 403 engeli | tablolar okunmadı |
| Lohner ve ark., "Fuel Regression Rate Characterization Using a Laboratory Scale Nitrous Oxide Hybrid Propulsion System", AIAA 2006-4671 | N2O/HTPB lab regresyon serisi (Rezaei Şekil 11'de karşılaştırılan eğrilerden) | AIAA ARC (ücretli) doi:10.2514/6.2006-4671; Stanford deposunda yok | SAYI ALINMADI |
| Karabeyoglu ve ark., "Scale-Up Tests of High Regression Rate Paraffin-Based Hybrid Rocket Fuels", JPP 21(6), 2004 | 2003-1162'nin hakemli dergi versiyonu (aynı kampanya, ek analiz) | doi:10.2514/1.7521 (ücretli); konferans versiyonu elimizde | konferans versiyonu yeterli |
| Doran, Dyer ve ark. Stanford parafin/N2O (Peregrine öncesi) serileri | Parafin/N2O a-n (Hansen'in kullandığı a=0.155, n=0.5'in birincil kaynağı: McCormick ve ark. AIAA 2003-6475) | AIAA ARC (ücretli) | SAYI ALINMADI (Hansen'de ikincil atıf olarak duruyor) |
| ODTÜ/İTÜ hibrit tezleri (YÖK Tez) | Türkçe kampanya verisi | tez.yok.gov.tr üzerinden manuel arama gerekli (otomatik erişim yok) | taranamadı |

---

## ÖNERİLEN İLK 5 KAMPANYA (veri bütünlüğü + HRMA uyumu sırasıyla)

1. Rezaei 2018 (HTPB/N2O) — 31 test noktası; tam girdi seti + ölçüm belirsizlikleri + tekrarlanabilirlik istatistiği; HRMA'da zaten çapa. UQ için deneysel gürültü tabanı da veriyor.
2. Karabeyoglu 2003-1162 (Parafin SP-1a/GOX, NASA Ames) — 26 satır (23 geçerli); Pc 11-68 bar bandı, c* verimleri, arıza etiketleri; parafin entrainment modelinin ana sınavı.
3. Whitmore & Stoddard 2020 (GOX/ABS + Nytrox87/ABS, USU) — 32 yakmanın μ/σ/%95 istatistikleri + tam geometri + 8 kombinasyonluk a-n tablosu; HRMA Monte Carlo çıktısının dağılım karşılaştırması için biçilmiş kaftan.
4. Wei 2025 (PP/N2O + PP/Nytrox, blowdown) — 11 test; oksitleyici sıcaklığı taramalı; HRMA transient/blowdown modülünün doğrudan doğrulaması.
5. Hansen & Edwards 2012 (Parafin-HTPB/N2O, uçuş ölçeği blowdown) — 4 test; tank+enjektör+lüle tam parametreli uçtan uca blowdown senaryosu; büyük ölçek + off-design O/F + arıza modları.

Yedek/iyileştirme: Zilliac 2006 (a-n kütüphanesi + UQ önselleri), Jens 2019 (basınç etkisi/termokimya mini-vakası), Palacz 2023 (besleme hattı + kapsam-dışı geometri örneği), McFarland 2019 (oksitleyici teyidi şartıyla).

## Toplam beklenen test noktası

- Motor düzeyi, doğrudan simüle edilebilir (yüksek güven): Rezaei 31 + Karabeyoglu 23 (geçerli) + Wei 11 + Hansen 4 = 69 nokta
- İstatistik düzeyi (dağılım karşılaştırması): Whitmore 32 yakma (2 konfigürasyonun μ/σ seti)
- Katsayı düzeyi (a-n bandı/önsel): Zilliac 14 fit (≈133 testin özeti) + Whitmore Tablo 4 (8 kombinasyon) + Rezaei/Karabeyoglu fit'leri
- Sınırlı kullanım: Jens 16 (slab), Palacz 11 (VFP), McFarland 7 (oksitleyici teyidi bekliyor) = 34 nokta

TOPLAM: ~101 doğrudan + ~34 sınırlı ≈ 135 gerçek test noktası; ilk sürüm korelasyon raporu için gerçekçi hedef 69 motor-düzeyi nokta + Whitmore istatistik seti.

## HRMA v2.5.0 için uygulama notları

1. Veritabanı şeması her kayıtta şu alanları taşımalı: künye (yazar/yıl/yayın/tablo no), confidence, date_checked, ölçüm belirsizliği (varsa), arıza/anomali etiketi, birim orijinali. Bu dosyadaki tablolar o şemaya birebir dökülebilir.
2. Karabeyoglu 2003 ve Hansen 2012'de zaman izleri (Şekil 5/8/9) sayısallaştırılırsa transient doğrulama seti 2 kampanya büyür — ama sayısallaştırma yapılan her değer "digitized" etiketiyle düşük güvene indirilmeli.
3. Whitmore Nytrox c* baskı hatası (560.84 → 1560.84) gibi kaynak hataları veritabanında "source_erratum" notuyla taşınmalı; sessiz düzeltme yapılmamalı.
4. Rezaei Eş. 11'deki L bağımlılığı (L^0.293), HRMA'nın mevcut rdot = a·Gox^n modelinin bilinen bir eksikliğini nicelleştiriyor — UQ'da model-form belirsizliği terimi olarak kullanılabilir.
5. McFarland oksitleyici teyidi: elsa.antunes1@jcu.edu.au (makalede yazışma adresi) — teyit gelmeden 7 nokta karantinada.
