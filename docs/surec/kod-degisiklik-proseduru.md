# Kod değişikliği prosedürü

**Son güncelleme:** 2026-08-14
**Kapsam:** Tek bir değişikliğin öncesinde ve sonrasında zorunlu adımlar;
riskli dosyalar ve onlara dokunma kuralları; değişiklik sırasında geçerli
içerik kuralları; geri alma; "bitti" tanımı.
**Kapsam dışı:** İşin nereden geldiği ve nasıl parçalandığı
(`gelistirme-akisi.md`), test yazımı (`test-disiplini.md`), yayın
(`surum-ve-yayin.md`), kurulum (`CONTRIBUTING.md` §1).

---

## 1. Değişiklik öncesi

### 1.1 Neyi değiştirdiğini bil

| Adım | Nasıl |
|---|---|
| Değişecek dosyaları listele | Değişiklik başlamadan yazılır; sonradan büyürse dur ve kapsamı yeniden konuş |
| Sayının zincirini gör | `tools/wiring_map.py` çıktısı (`docs/dev/wiring_map_*.html`): "bu alan nereye gidiyor", "bu sayıyı hangi girdiler belirliyor" |
| Daha önce düzeltilmiş mi | `docs/BULGU_KAYIT_DEFTERI.md`'de ara — aynı kusur ikinci çağrı yerinde tekrar edebilir |
| Fizik değişiyorsa | `docs/VALIDATION_STATUS.md` okunur: neyin doğrulandığı, neyin doğrulanmadığı |
| Standart atfı ekleniyorsa | Önce `docs/STANDART_ATIFLARI.md`'ye `DOĞRULANDI` satırı. Doğrulayamıyorsan atfı koyma |

### 1.2 Taban ölçümü al

Değişiklikten **önce** çalışan hâlin sayısı alınır. Bu, sonradan "ne değişti"
sorusunun tek dürüst cevabıdır.

```bash
git status --porcelain                       # ağaç temiz mi
MPLBACKEND=Agg PYTHONPATH=. python3 -m pytest tests/ -q   # taban yeşil mi
PYTHONPATH=. python3 tools/sabit_tarayici.py --sayfa <sayfa>   # ilgiliyse
```

Ağaç kirliyken başlanan değişiklik, geri alınamayan değişikliktir: `git diff`
kimin işi olduğunu ayırt edemez.

### 1.3 Sahiplik ve sıra

Aynı dosyaya iki yazıcı dokunmaz. Kesişim varsa **sıralı** çalışılır
(`gelistirme-akisi.md` §5). `CODEOWNERS` alan sahipliğini belgeler; dürüst
sınırı da kendi içinde yazar: `main` korumalı olmadığı için CODEOWNERS bir
**kapı değil**, belgelenmiş sahipliktir.

---

## 2. Risk sınıfı

Risk, dosyanın ne kadar merkezde olduğuyla ölçülür. Aşağıdaki tablo
2026-08-14'te ölçüldü (son 60 commit'teki dokunma sayısı + dosya boyutu).

| Dosya | Dokunma / 60 commit | Satır | Neden riskli |
|---|---:|---:|---|
| `hrma/engines/liquid_rocket_engine.py` | 21 | 9674 | En büyük çözücü; çoğu bulgunun yoğunlaştığı yer |
| `hrma/app.py` | 20 | 9579 | Tüm uçların birleştiği hub; her sayfa buradan geçer |
| `hrma/templates/liquid.html` | 17 | — | Form alanı ↔ toplayıcı sözleşmesi |
| `hrma/templates/advanced.html` | 15 | — | Aynı |
| `hrma/templates/solid.html` | 14 | — | Aynı |
| `hrma/engines/solid_rocket_engine.py` | 14 | 9374 | Çözücü |
| `hrma/engines/hybrid_rocket_engine.py` | 14 | 5786 | Çözücü |
| `hrma/static/js/i18n_common.js` | 12 | 3480 | İki dilin ortak sözlüğü; eksik anahtar arayüzde ham metin olarak sızar |
| `hrma/static/js/i18n_pages.js` | 10 | 2908 | Aynı |
| `hrma/constants.py` | — | 206 | Merkezî sabitler; buradaki bir değişiklik her modüle yayılır |

**Kural:**

* `app.py` ve şablonlar **tek elden** işlenir; paralel yazıma açılmaz.
* Çözücü dosyalarına aynı anda birden fazla yazıcı girmez; parti sınırı dosya
  düzeyindedir.
* `constants.py`, `hrma/data/*_db.py`, `packaging/*`, `.github/*` değişiklikleri
  ayrı ve küçük commit'lerde yapılır — büyük bir partiye gömülürse geri almak
  imkânsızlaşır.
* Yapısal (toplu) kod değişikliği metinsel desenle değil **AST** ile yapılır:
  metinsel desen kırılgandır (`V2.6.26_BITIRME_PLANI` §10, cmd-41 dersi).

---

## 3. Değişiklik sırasında geçerli içerik kuralları

Bunlar "stil" değil; her biri ölçülmüş bir kusur sınıfını kapatıyor.

### 3.1 Sayı uydurma

Hesaplanamayan değer **varsayılanla doldurulup sonuç gibi sunulmaz**. Üç meşru
çıkış vardır: `None` döndür, hata yükselt, ya da `NOT_MODELLED` /
`not_analyzed` beyanını **arayüze kadar** taşı.

Şablon, el kitabı veya yer tutucudan gelen bir değer varsa `_basis` /
`_source` alanı taşır. `OPTIMIZED`, `CALCULATED`, `PASS` gibi dizgeler
**hükümdür**: yakınsamayan bir koşu `CALCULATED` diyemez.

Ölçülmüş örnek: uç katmanı eksik cidara 5 mm, eksik malzemeye `steel_4130`
enjekte edip motorun dürüstlük kapısını deviriyordu; katıda ayrıca Pc 40/80/150
bar'da cidar 2,4/4,8/9,0 mm değişirken emniyet katsayısı `3,000000` sabit
çıkıyordu — hesap değil ekoydu (commit `116b4ea`).

### 3.2 Birim sözleşmenin parçasıdır

İki ayrı 1000× hata elle süpürmelerden sağ çıktı: STL metre yazılırken
dokümantasyon milimetre diyordu; DXF `$INSUNITS` metreye ayarlıyken geometri
milimetreydi. Termal panelde de milimetre değerleri metre alanına basılmıştı
(commit `3ab83b4`).

Kural: geometri, dışa aktarım ya da modüller arası herhangi bir arayüze
dokunuyorsan birimi **ada ya da yorumda** yaz ve artefaktı geri okuyup mutlak
bir ölçüyü sınayan test ekle.

### 3.3 Sabit sayı tek yerde durur

Birden fazla dosyada geçen eşik/katsayı `hrma/constants.py` (206 satır) ya da
ilgili veri modülünde tanımlanır ve **import edilir**. Eşiğin betiğe/koda
dağılması, sonradan "hangi değer doğru" sorusunu cevaplanamaz hâle getirir;
`release_gate.sh` bile boyut sapması eşiğini tek yerde tutmayı ayrıca
gerekçelendiriyor.

### 3.4 İki dil aynı anda

Arayüz metni eklendiğinde EN ve TR karşılıkları birlikte eklenir
(`i18n_common.js` / `i18n_pages.js`). Eksik anahtar sessiz kalmaz, kullanıcıya
ham anahtar ya da yanlış dil olarak sızar; v2.6.27'de "son i18n sızıntısı"
ayrı bir parti kalemi oldu (commit `7c38dfe`).

### 3.5 Arayüzde sahte veri ve sahte animasyon yok

Yer tutucu gösterge, uydurma sayı, gerçek ilerlemeye bağlı olmayan animasyon
eklenmez. Veri yoksa gösterge **hiç konmaz**; yerine beyan konur. Bu kural
`CONTRIBUTING.md` §3.1'in son maddesiyle aynıdır ve tarayıcı denetiminin
(Faz 6) hüküm ölçütüdür.

### 3.6 Yorum "neden"i ve ölçümü yazar

Türkçe yorum serbesttir (ve baskındır); Türkçe karakterler doğru kullanılır
(ç ğ ı İ ö ş ü). Kod sembolleri İngilizce kalır. Yorumun içeriği ölçümdür:

```python
# Ölçüm: analiz 124,0 mm cidar veriyor, STEP 109,0 mm yazıyordu — katıda
# anahtar adı 'case_analysis', export 'chamber_analysis' arıyordu.
```

### 3.7 Kazanılmamış hüküm yok

"NASA-grade accurate", "validated", "professional-grade" gibi ifadeler
`tools/iddia_lint.py` tarafından reddedilir. Düzeltme yorumunun kaldırdığı
kusuru alıntılaması gerekiyorsa `IDDIA-LINT-MUAF` işareti kullanılır — muafiyet
istisnadır, alışkanlık değil.

---

## 4. Silmeden önce bak

Bu depoda `rmtree` üç kez çalışma ağacını uçurdu. Bunun prosedür karşılığı:

* Toplu silme/taşıma öncesi ağaç yedeği alınır (`V2.6.26_BITIRME_PLANI` Faz 0:
  73 MB, ~5 sn).
* Sessiz `except` ve `ignore_errors` kullanımı bir hata sınıfıdır; taranır ve
  gerekçesiz olanı kaldırılır.
* "Ölü" sanılan dosya silinmeden önce **ölçülür** (bağlama haritası, `grep`,
  test toplama). `tank_blowdown.py` yıllarca hiçbir yere bağlı değildi ama ölü
  değildi — eksik olan bağlamaydı.

---

## 5. Değişiklik sonrası: zorunlu ölçümler

```bash
MPLBACKEND=Agg PYTHONPATH=. python3 -m pytest tests/ -q   # TAM takım, alt küme değil
python3 tools/iddia_lint.py                               # çıkış kodu 0 olmalı
git diff --stat                                           # kapsam beyanı
```

| Ölçüm | Kabul ölçütü |
|---|---|
| Tam test takımı | Yeşil. **Alt küme yeşilliği kabul edilmez** — bir sürüm tam olarak bu yüzden kırmızı çıktı |
| Yeni bekçi | Düzeltmesiz kodda **kırmızı** görüldü (`test-disiplini.md` §5.2) |
| İddia lint | 0 kayıtsız isabet |
| `git diff` | Belirtilen amaç dışında hiçbir şey içermiyor |
| Önce/sonra | Bulgunun sayısı yeniden ölçüldü ve fark yazıldı |
| Defter | `docs/BULGU_KAYIT_DEFTERI.md` satırı eklendi; `tests/test_findings_registry.py` yeşil |
| Commit gövdesi | Ölçümleri, kök nedeni ve "hiçbir iddia gevşetilmedi" beyanını taşıyor |

Performans değişikliğinde ek olarak: **önce-sonra tablosu olmadan hiçbir
optimizasyon "yapıldı" sayılmaz.**

Opsiyonel ama önerilir:

```bash
pre-commit run --all-files     # hızlı denetimler; test takımının yerine geçmez
```

---

## 6. Geri alma

| Durum | Yol |
|---|---|
| Değişiklik henüz commit edilmedi | `git diff` ile gözden geçir, `git checkout --` ile dosya bazında dön |
| Parti/faz commit edildi, hatalı çıktı | Commit'ler faz/parti düzeyinde atıldığı için `git revert <sha>` okunabilir bir birim geri alır — bu, "her faz sonunda commit" kuralının asıl sebebidir |
| Yarım iş korunacak | `wip-<amaç>-<tarih>` etiketi (ölçülmüş örnek: `wip-mola-20260814`); etiket mesajı **ne bitti / ne kaldı** yazar |
| Toplu değişiklik öncesi ağ | Faz 0 kalıbı: tam ağaç yedeği + taban ölçüm çıktısı |

Depoda tek dal var (`main`, uzak `origin/main`) ve 2026-08-14 ölçümünde 3
commit push edilmemişti. Yani güvenlik ağı dal değil, **commit sıklığı ve
etiketlerdir**; bu yüzden ara kayıt almadan uzun süre çalışmak riskli sayılır.

---

## 7. "Bitti" tanımı

Aşağıdakilerin hepsi doğruysa değişiklik bitmiştir; biri eksikse bitmemiştir.

- [ ] Belirti ölçüldü, kök neden bulundu, düzeltme belirtiyi açıklıyor
- [ ] Önce/sonra sayıları yazıldı
- [ ] Bekçi yazıldı ve düzeltmesiz kodda kırmızı görüldü
- [ ] Hesaplanamayan hiçbir şey sayı olarak gösterilmiyor (beyan var)
- [ ] Birim, ad ve kaynak sözleşmesi sınandı
- [ ] Tam takım yeşil, `iddia_lint` 0
- [ ] `git diff` kapsam dışı değişiklik içermiyor
- [ ] Defter satırı eklendi
- [ ] Commit başlığı kusuru/kapsamı söylüyor; doğrulanmamış kısım varsa
      başlıkta veya gövdede **açıkça beyanlı**
