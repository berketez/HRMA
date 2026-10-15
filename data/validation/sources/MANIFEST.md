# Doğrulama kaynakları — indirme künyesi

**Oluşturma:** 3 Ağustos 2026 · **Son ekleme:** 18 Ağustos 2026 (CFD viskoz kaynakları, parti 39) · **Kapsam:** `data/validation/*.json` kayıtlarının dayandığı belgeler

## Bu dizin neden PDF içermiyor

Belgeler indirildi, metinleri çıkarıldı ve sayılar `data/validation/*.json`
kayıtlarına işlendi. **PDF'lerin kendisi depoya konmadı.** İki sebep:

1. **Telif.** Aşağıdaki listede `AIAA` işaretli iki belge telifli dergi/konferans
   yayınıdır. Yayıncının kendi sitesinden veya kurumsal arşivinden okunabilir,
   ancak açık bir depoda yeniden dağıtılamaz. Kayıtlara yalnız **sayılar,
   bağıntılar ve künyeler** alındı — bunlar telif kapsamında değildir; uzun metin
   kopyalanmadı.
2. **Depo boyutu.** Beş belge toplam **~28 MB**. Deponun `.git` dizini şu an
   42 MB; PDF'leri eklemek onu kalıcı olarak ~%67 büyütürdü ve hiçbir kod bu
   dosyaları okumuyor.

Bunun yerine aşağıdaki tablo her belgenin **boyutunu ve SHA-256 özetini** taşır.
`fetch_sources.sh` belgeleri aynı adreslerden indirir ve özetleri doğrular —
yani kaynak zinciri yeniden üretilebilir, sadece binary depoda durmuyor.

## Belgeler

| # | Belge | Telif | Boyut (bayt) | SHA-256 |
|---|---|---|---:|---|
| 1 | Design Report for RL10A-3-3 Rocket Engine, PWA FR-1769 (1966) | NASA / kamu malı | 4 220 156 | `c7a2199ec4deadb30b2ff0960b7f576e2aaa227f47315efe85268da654576120` |
| 2 | RL10A-3-3A Rocket Engine Modeling Project, NASA TM-107318 (1997) | NASA / kamu malı | 6 731 522 | `2d25422c6b9d4635f3209cfb79c160d160d229aeded17a3e12abe4330153a8c7` |
| 3 | A Comparison of Experimental Heat-Transfer Coefficients … Bartz's Methods, NTRS 19710011726 (1971) | NASA / kamu malı | 3 613 262 | `62d165ed0710e515c56ed993eed3871deb5b96662d141d180b0cb93d697904df` |
| 4 | Stark, *Flow Separation in Rocket Nozzles, a Simple Criteria*, AIAA 2005-3940 | **AIAA** (DLR eLib açık kopya) | 3 906 549 | `58260ab8a9c6454e9aeecf6c34dafde21071e2b6e0f12efe53afe2be7a10687b` |
| 5 | Oefelein & Yang, *Comprehensive Review of Liquid-Propellant Combustion Instabilities in F-1 Engines*, JPP 9(5) 1993 | **AIAA** | 3 839 650 | `3dcc4f2c4b1dfdc73f9af6034b7c422f249721c51fc0b9fe1acea6ed89aa15be` |
| 7 | Back, Massier, Gier, *Convective Heat Transfer in a Convergent-Divergent Nozzle* (Rev. 1), JPL TR 32-415, NTRS 19650010083 (1965) — **CFD birincil capa; Tablolar B-1/B-2/B-3** | NASA / kamu malı (PUBLIC) | 7 620 243 | `bf8d2961b2aecc53f08920e86a5b7dfc2d7efbde19d26599693fd48fffc6a198` |
| 8 | Aynı makalenin daktilo taslağı, NTRS 19650026963 (1963/64) — veri eki YOK, yalnız künye teyidi | NASA / kamu malı (PUBLIC) | 1 600 162 | `46c0b115a679554ea7a6a1805a8dd188bdce27e6e85e434be946bdcfffe266cb` |
| 9 | Boldman, Schmidt, Gallagher, *Laminarization of a Turbulent Boundary Layer…*, NASA TN D-4788, NTRS 19680024170 (1968) — çapraz teyit; geometri tabloları | NASA / kamu malı (PUBLIC) | 1 696 735 | `950ae9cf4ab2d03233873036503663f6f14b9b6187ee6bffd7544ee63ab10b36` |
| 10 | Wang ve ark., *A Fluid-Thermal Analysis of Partial Admission Axial Turbines*, GPPS-TC-2021-0105 (2021) — yayımlanmış ANSYS Fluent/SST çözümü (Şekil 3b sayısallaştırıldı) | **CC BY 4.0** | 727 599 | `14b1c565dfabf5bb124ecd5042995ead53a39235093da5e04832cabd4328ce89` |

Ayrıca indirilen ama **hiçbir kayda sayı vermeyen** belge (yalnız arka plan
okuması, künye tamlığı için kayıtta):

| # | Belge | Boyut (bayt) | SHA-256 |
|---|---|---:|---|
| 6 | Wall pressure unsteadiness and side loads in overexpanded rocket nozzles, NTRS 20120014182 | 9 812 294 | `ade4c795a7630c1b2ea9f2777bf2b6f047e27ef88c4481ac982f192112f60dc2` |
| 11 | Makhija, Bodi, Chakraborty, *Numerical Estimation of Convective Heat Transfer…*, Def. Sci. J. 74(2) 2024, doi:10.14429/dsj.74.19633 — BMG vakasını **OpenFOAM** ile çözer (ANSYS değil); kayda sayı girmedi, çapraz-CFD literatür kanıtı | 1 764 630 | `0f716f493d4463a03307cdbe2ff43f69353d13270cfb7d7bda0354ec47031125` |

## İndirilemeyen kaynaklar

Bu turda denenip **alınamayan** belgeler — bir sonraki tur boşa arama yapmasın:

| Belge | Sonuç |
|---|---|
| Huzel & Huang, NASA SP-125, *Design of Liquid Propellant Rocket Engines* | Stanford kopyası (12 MB) indirme zaman aşımına uğradı; turbopompa örnek hesabı (Bölüm 6) **alınamadı** |
| DTIC AD/A-004 666, *Specific Impulse Losses in Solid Propellant Rockets* | DTIC bağlantısı PDF yerine 1.4 KB yönlendirme sayfası döndü; iki-faz gecikme bağıntısı **alınamadı** |
| Sutton & Biblarz, *Rocket Propulsion Elements* | Telifli kitap; iki-faz bölümü bu turda **açılmadı** (bkz. `twophase_particle_loading_loss.json`, confidence: low) |
| NPO Energomash RD-180 datasheet | Erişilemedi (depoda 2026-07-23'te de aynı sonuç kayıtlı) |

## Doğrulama

```bash
bash data/validation/sources/fetch_sources.sh        # indir + özetleri doğrula
```

Bir özet tutmazsa belge yayıncı tarafından değiştirilmiş demektir; o zaman ilgili
JSON kaydının `retrieved` tarihi ve değerleri **yeniden kontrol edilmelidir**.
