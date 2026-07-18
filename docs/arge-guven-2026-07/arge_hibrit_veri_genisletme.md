# Hibrit Veri Genişletme Dalgası — 2026-07-18

Üç paralel araştırma ajanıyla (HTPB/N2O-GOX avı, parafin/ABS avı, büyük
ölçek/ajans avı) yürütülen açık-kaynak taraması. **63 yeni kayıt** eklendi:
88 → 151 hibrit, 136 → 199 toplam. Tüm kayıtlar `experiment_db` doğrulayıcısından
geçti; sayılar kaynak birimleriyle, belirsizlik yalnız kaynak veriyorsa.

## Eklenen kaynaklar

| Kaynak | Kayıt | Yakıt/Oksitleyici | Tür | Güven | Not |
|---|---|---|---|---|---|
| Cardillo 2023 (Napoli/CIRA, Aerospace 10:546) | 14 | parafin(SASOL 0907)/GOX | static_fire | high | Tablo 2+3, belirsizlikli; 6S anomali (PT tıkalı), 1MU/2MU/8MU salınım anomalisi |
| Battista 2019 (CIRA 1000 N, Aerospace 6:89) | 4 | parafin/GOX | static_fire | high | EUCASS2019-541 ile çapraz teyit; L1 yakıt-debisi baskı hatası işaretli; L4 (throttling, yalnız aralık) alınmadı |
| Scaramuzzino/Carmicino 2013 (EUCASS) | 25 | HTPB(+CB/nAl/µAl)/**gaz** N2O | static_fire | high | Tablo A1+A2; C* birimi kaynakta hatalı "mm/s" basılı (m/s alındı); boğaz 9.6/12 mm test-bazında belirsiz |
| Heydari 2017 (IJAE 3174140) | 10 | HTPB/sıvı N2O | static_fire | high | 5 eksenel + bench + 4 swirl; swirl serisi anomaly bayraklı (v1 eksenel kapsam dışı) |
| HPDP 2003 (NTRS 20030068416) | 4 | HTPB+PCPD/LOX | engine_test_point | high | 250K lbf sınıfı, 4 yakma; M1T1 kararsız, M2T2 salınımlı |
| AMROC DM-01 (NTRS 20060047689) | 4 | HTPB/LOX | engine_test_point | medium | İkinci el (birincil AIAA-93-2551 paywall); boğaz erozyonu yakma-başına ölçülü |
| Sims 1998 (NTRS 19980236002) | 1 | HTPB/LOX | engine_test_point | high | %95 güven aralıklı c* — veritabanındaki tek belirsizlik-nicelenmiş büyük ölçek c* |
| Knowles 2004 (NTRS 20050185550) | 1 | HTPB/LOX | static_fire | medium | 10-inç, yalnız regresyon sayısal |

## Korelasyon etkisi (dürüstlük özeti)

- **Ana istatistik seti DEĞİŞMEDİ** — taban değerleri aynı, yalnız db_hash
  güncellendi (`c64e8d7b…`). Bekçi dosyasında gerekçe var.
- 59 kayıt `insufficient_inputs`: v1 hibrit adaptörü tam koşu için
  mdot_ox + burn_time + O/F + **başlangıç port çapı** + **boğaz çapı** +
  yakıt anahtarı ister. Cardillo port çapını yayımlamamış (ref [9] JPP
  paywall; MDPI açık kopyalarında da test-bazında yok — UYDURULMADI),
  Carmicino boğazı test-bazında vermemiş, Battista geometriyi hiç
  tablolamamış, büyük-ölçek NTRS kayıtları İngiliz-birim nokta-kıyas yolu
  ister (hibritte v1'de yok).
- 4 kayıt (Heydari S4A1 swirl) skorlanabiliyor ama **anomaly bayraklı**:
  swirl enjeksiyon v1 eksenel modelin kapsamı dışında (kaynağın kendi
  fitleri: eksenel r=0.40·Gox^0.37, swirl r=0.14·Gox^1.40). Anomali
  katmanında izleniyor; bekçi testi karantinayı kilitliyor.

## Adaptör v2 iş listesi (bu kayıtları skorlanabilir kılar)

1. Hibrit `engine_test_point` İngiliz-birim nokta-kıyas yolu (HPDP/AMROC/Sims
   → c*, Isp_vac, Pc kıyası; `ftps` ve `milps` birim sonekleri de eksik).
2. Boğaz-çapı-belirsiz kayıtlar için iki-değerli duyarlılık koşusu
   (Carmicino 9.6/12 mm) — VEYA kaynak yazarlarına e-posta.
3. Cardillo port çapı: Di Martino JPP 2019 (10.2514/1.B37017) paywall —
   üniversite erişimi olan biri bakarsa 14 test Pc/c*/itki/regresyon
   hücrelerine girer (Berke: İTÜ erişimi?).

## Erişilemeyen adaylar (gelecek dalga)

- **Spurrier 2016 USU tezi (GOX/ABS)** — USU DigitalCommons CAPTCHA;
  **Berke tarayıcıdan indirirse en iyi ABS kaynağı** (digitalcommons.usu.edu/etd/5020).
- George ve ark. JPP 2001 (HTPB/GOX tablolu) — AIAA paywall.
- Lohner/Doran Stanford N2O serisi (AIAA 2006-4671, 2007-5352) — paywall.
- Zilliac Peregrine motor testleri (AIAA 2014-3870) — paywall.
- Heeg 2020 (HYDRA 4X, HTPB/N2O, Tablo 5 hazır) — Aerospace 7(5):57 açık;
  ilk ajanın kapsam listesi dışında kaldı, SONRAKI dalgada eklenebilir.
- Thomas Texas A&M (HTPB-parafin karışımları/GOX) — yalnız figür
  (figure_digitized gerekir).

## Süreç notları

- Ajan raporlarındaki tüm sayılar ajanların gerçekten açıp okuduğu
  PDF/HTML tablolarından; abstract'tan sayı alınmadı.
- CIRA/Napoli grubu (Cardillo+Battista) tek araştırma grubu sayılmalı;
  Carmicino/Scaramuzzino da Napoli kökenli ama farklı motor/ekip.
- jina-ai MCP anahtarı bu oturumda 401 verdi; ajanlar curl + r.jina.ai +
  NTRS PDF indirme + taranmış sayfa görüntüsü okumasıyla çalıştı.
