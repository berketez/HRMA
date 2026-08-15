# Analiz Merkezi tasarımı — "nerenin, ne analizi" (ANSYS-akışı)

**Tarih:** 15 Ağustos 2026 · **İstek:** Berke ("analiz kısmı ANSYS arayüzüne benzer olmalı;
nerenin analizini yapacak, ne analizini yapacak seçilebilmeli") · **Tasarım:** ana model.
**Bağlam:** analiz yetenekleri bugün sayfalara dağılmış panellerde (yapısal FEA hibritte +
sıvıda, tane FEA katıda, termal FEA hibritte, CFD geliyor). FINAL kullanıcısına tek,
seçimli analiz yüzü gerekiyor.

## 1. Kavram

Workbench mantığı, üç sütun + geçmiş şeridi:

```
┌─ BİLEŞEN AĞACI ─┬─ KOŞUM KARTI ────────┬─ SONUÇ GÖRÜNTÜLEYİCİ ─┐
│ ▸ Kamara+lüle    │ Analiz: Yapısal      │ kontur + tel kafes    │
│   cidarı         │ Girdiler (otomatik,  │ + kalite haritası     │
│ ▸ Tane kesiti    │  azınlık düzenlenir) │ + rozetler            │
│ ▸ Lüle iç akışı  │ [Çalıştır]           │ + NOT_MODELLED beyanı │
│ ▸ Tank/birleşim  │ gerçek yakınsama     │ + yakınsama geçmişi   │
│ ▸ Kamara akustiği│ logu (kalıntı akışı) │                       │
├─ KOŞUM GEÇMİŞİ (oturum içi; E4 karşılaştırmayla entegre) ──────┤
```

## 2. Bileşen × analiz matrisi (v1 — bugün hazır çekirdeklerle)

| Bileşen | Analiz | Çekirdek/uç | Motor kapsamı |
|---|---|---|---|
| Kamara+lüle cidarı | Yapısal (statik lineer, eksenel simetrik) | `/api/fea/structural` (D1+D4) | hibrit · katı · sıvı |
| Kamara+lüle cidarı | Termal (geçici iletim, Bartz BC) | `/api/analysis/wall-profile` → `/api/fea/thermal` (D2) | hibrit (diğerleri profil kaynağı genişleyince) |
| Katı tane kesiti | Düzlemsel gerinim (SP-8073 kabul ölçütü) | `/api/fea/planar-grain` | katı |
| Lüle iç akışı | CFD (Euler, şok yakalama, p_w → ayrılma hükmü) | `/api/cfd/nozzle` (dalga B) | hibrit · katı · sıvı |
| Tank / cıvatalı birleşim / hat | Modül kartları (pressure_vessel, bolted_joint, water_hammer — kontur-FEA'sı DEĞİL, mevcut kart çıktıları) | mevcut analiz uçları | motor tipine göre |
| Kamara akustiği | Mod tablosu (F2 çekirdeği); görselleştirme F2 tepki modeliyle | acoustic_modes | hibrit · katı |

## 3. Kurallar (ürün felsefesinin izdüşümü)

1. **Uygulanabilirlik beyanlıdır:** motor tipine/mevcut veriye göre uygulanamayan satır
   GİZLENMEZ — gri gösterilir ve nedeni adlandırılır ("bu sonuç X alanını taşımıyor").
   Sahte veri/uydurma girdi yasağı aynen geçerli.
2. **Mesh kurulumu yok, mesh görünür:** kullanıcı mesh ayarlamaz; tel kafes + kalite
   haritası + yakınsama her analizde ekranda (D5 sözleşmesi).
3. **Sahte ilerleme yok:** koşum sırasında gerçek durum (koşuyor/işlem beyanı) ve
   bitişte GERÇEK yakınsama geçmişi; yüzde çubuğu ancak gerçek iterasyon akışı
   sunulabiliyorsa (SSE/poll) gösterilir — uydurma animasyon yasak.
4. **Her sonuç beyan zinciriyle gelir:** NOT_MODELLED listesi, korunum/enerji bütçesi,
   hüküm rozetleri (converged/kabul ölçütü) panelin eşit vatandaşıdır.
5. **Koşum geçmişi** oturum içi tutulur; iki koşum E4 karşılaştırma altyapısıyla yan
   yana konabilir.

## 4. Uygulama sırası (mevcut planla çakışmasız)

- **Dalga B (CFD ürünleşme):** Analiz Merkezi ÇERÇEVESİ kurulur (yeni sekme/pano;
  bileşen ağacı + koşum kartı + görüntüleyici iskeleti) ve İLK kiracı CFD paneli olur
  (`/api/cfd/nozzle` + kontur/yakınsama-logu görünümü). Mevcut paneller YERİNDE KALIR.
- **Sonraki partiler:** FEA yapısal → termal → tane panelleri tek tek Merkez'e taşınır;
  her taşıma görsel tur denetimiyle doğrulanır, doğrulanmadan eski yerinden kaldırılmaz.
- **F2 sonrası:** akustik satırı görselleşir. Tank/birleşim kontur-FEA'sı ayrı tasarım
  turu (bulgu defterindeki flanş/cıvata yerel gerilme notuyla birlikte).

## 5. Kararlar

- **Yerleşim (Berke onayı, 15 Ağu):** sayfa içi dock — motor bağlamı kaybolmaz,
  sonuç sözlüğü zaten sayfada.
- Koşum geçmişi kalıcılığı: AÇIK — yalnız oturum içi mi, .hrma dosyasına da mı?

## 6. Kapsam stratejisi ve ANSYS-teyit hattı (Berke kararı, 15 Ağu)

**Kapsam:** ANSYS "her şeyi" analiz eder ama alan bilgisi taşımaz; HRMA yalnız
roket motoru analiz eder ve motorun İHTİYAÇ DUYDUĞU analizlerin tamamını
taşımayı hedefler. Tam liste literatürden çıkarılır (NASA SP monografları,
Sutton, Huzel-Huang, SP-194, AIAA) — tarama sonucu ayrı katalogda:
`docs/mimari/motor-analiz-katalogu.md` (bileşen×analiz matrisi §2 o katalogdan
büyüyecek; boşluk analizi = katalogda olup üründe olmayan satırlar).

**Akış aşağı entegrasyon:** ayrıntı tasarım CATIA/SolidWorks/ANSYS'e akar:
1. Geometri: STEP dışa aktarımı (VAR — dürüstlük kapılı).
2. **ANSYS-teyit çıktısı (yeni hat):** HRMA'nın kendi FEA koşusunu kullanıcının
   ANSYS'te YENİDEN KOŞABİLECEĞİ paket: mesh + malzeme + yükler + sınır
   koşulları (hedef format: APDL .inp/.cdb, eksenel simetrik eleman karşılığı;
   CFD için CGNS/Fluent .msh) + bizim sonuçların beyan zincirli karşılaştırma
   sayfası. Güven stratejisi: "bize güven" değil, "işte kontrol et".
   Format ayrıntıları tarama dönünce bu belgeye işlenecek; uygulama sırası
   kataloğun boşluk analiziyle birlikte önceliklendirilecek.
