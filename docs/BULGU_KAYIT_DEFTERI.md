# Bulgu kayıt defteri

Bu dosya HRMA'nın **bakım altyapısının** çekirdeğidir. Amacı tek bir soruyu her
zaman cevaplanabilir tutmak:

> Bir denetimde bulunan kusur gerçekten kapandı mı, ve bir daha geri gelirse
> bunu ne yakalayacak?

Kayıt defteri bir yapılacaklar listesi değildir. Her satırı bir **bekçi teste**
bağlanmış bir kusur geçmişidir. Bekçisi olmayan bir "kapandı" kaydı, kapandığın
kanıtı değil, yalnızca iddiasıdır.

## Neden gerekli

Bu kod tabanında bulunan ciddi kusurların neredeyse tamamı aynı sınıftan:
**iki parça tek başına doğru, aralarındaki sözleşme yanlış.** Bu sınıf tek
dosyaya bakarak görülmez ve elle süpürmeyle güvenilir biçimde bulunmaz —
nitekim aynı uydurma sabitler üç ayrı elle süpürmeden sağ çıkmıştı.

Ayrıca bu kusurlar **geri gelir**. Bir sözleşme bir kez kurulduktan sonra
başka bir çağrı yeri aynı hatayı tekrarlayabilir: v2.6.26'da ısı transferi
çağrısı boğaz çapını göndermiyordu, oysa aynı dosyadaki lüle malzemesi çağrısı
gönderiyordu. Yani sözleşme bir çağrıda kurulu, diğerinde atlanmıştı.

Bu yüzden kayıt defterinin kuralı şudur:

> **Kapatılan her kusur, o kusurun kendisini yakalayan bir teste bağlanır.
> Test yoksa kusur kapanmamıştır.**

## Bekçi katmanları

Bekçiler kusur sınıfına göre katmanlıdır. Yeni bir kusur bulunduğunda önce
"bu hangi katmanın göremediği bir şey?" diye sorulur; cevap "hiçbirinin" ise
yeni bir katman gerekir.

| Katman | Soru | Dosya |
|---|---|---|
| A | Arayüzdeki her form alanı bir toplayıcıda okunuyor mu? | `tests/test_field_wiring_layer_a.py` |
| B | Payload'daki her anahtar çıktıyı gerçekten değiştiriyor mu? Hiçbir girdiden etkilenmeyen sayısal çıktı var mı? | `tests/test_field_wiring_layer_b.py` |
| Birim | Paneller çözücünün verdiği değeri doğru birimde okuyor mu? | `tests/test_panel_units_v2626.py` |
| Dürüstlük | Hesaplanmamış bir şey hesaplanmış gibi sunuluyor mu? | `test_no_fabrication.py`, `test_safety_honesty.py`, `test_cad_notes_honesty.py`, `test_liquid_manufacturing_honesty.py` |
| Tutarlılık | Aynı fiziksel büyüklük iki panelde aynı değeri veriyor mu? | katı / sıvı / CAD tutarlılık bekçileri (aşağıdaki tabloya bakınız) |
| Davranış | Belirli bir kusur, kendi somut senaryosuyla geri geldi mi? | `tests/test_hybrid_wired_fields_v2626.py` ve kusura özel dosyalar |

**Katman A ile B birbirinin yerine geçmez.** A geçip B kırılabilir (toplayıcı
gönderiyor, çözücü okumuyor) ya da B geçip A kırılabilir (çözücü okuyor,
arayüz göndermiyor). v2.6.25'te tam olarak ikincisi yaşandı ve HTTP katmanını
sınayan her test "bağlandı" diyordu.

## Vaka listelemek yerine taramak

`test_no_fabrication.py` 17 **bilinen** vakayı sabitler. Vaka listelemek yeni
uydurmayı yakalamaz. Katman B vaka listelemez, **tarar**: her girdiyi sarsar ve

- satır hiç değişmiyorsa girdi ölüdür,
- sütun hiçbir girdiyle değişmiyorsa çıktı uydurma sabittir.

Yeni bir kusur sınıfı bulunduğunda tercih sırası şudur:

1. Taranabilir mi? Tarayıcı yaz (kalıcı, yeni vakaları da yakalar).
2. Taranamıyorsa vaka testi yaz (dar, ama hiç yoktan iyi).

## Beyaz liste disiplini

Bekçilerin çoğunda "bu alan bilerek bağlı değil" diyen gerekçeli listeler var.
Bu listeler kusuru meşrulaştırmanın en kolay yoludur, bu yüzden iki kuralları
vardır:

1. **Her girişin bir gerekçesi olmak zorundadır** ve gerekçe "sonra bağlarız"
   olamaz — o durumda alan arayüzden kaldırılır.
2. **Liste çürüyemez.** Listedeki alan sonradan bağlanırsa ya da arayüzden
   kalkarsa bekçi KIRILIR (`test_declared_lists_do_not_rot`). Aksi hâlde liste
   zamanla anlamını yitirir ve gerçekten ölü olan alanı gizlemeye başlar.

## Sürüm öncesi kapı

Yayın kapısı (`packaging/release_gate.sh`) mekanik olarak durdurur; ikna
edilemez. Kapılar:

1. Sürüm numarası tutarlılığı (`hrma.__version__` ile changelog)
2. Çalışma ağacının temizliği
3. CI'nin tam commit üzerinde YEŞİL olması (atlanamaz)
4. Tam test takımı
5. Yayın notlarının iki dilli ve imli olması
6. macOS paket imzasının doğrulanması

## Bir bulgu nasıl kapatılır

1. **Ölç.** Kusuru gerçek bir istekle yeniden üret ve sayıyı yaz. "Muhtemelen"
   ile başlayan bulgu bulgu değildir.
2. **Kök nedeni bul.** Belirti değil sözleşme kırığı düzeltilir.
3. **Düzelt.**
4. **Yeniden ölç.** Öncesi/sonrası sayıları yan yana koy.
5. **Bekçi yaz.** Kusurun kendisini yakalayan test.
6. **Deftere işle.** Aşağıdaki tabloya satır ekle.

Adım 5 atlanırsa kusur kapanmış sayılmaz.

## Kapatılan bulgular

Sütunlar: kusurun ne olduğu, hangi sürümde kapandığı, ve **geri gelirse neyin
kıracağı**.

### v2.6.26

| Kusur | Bekçi |
|---|---|
| Arayüzdeki alan hiçbir toplayıcıda okunmuyor | `test_field_wiring_layer_a.py::test_every_field_is_collected_or_declared` |
| Beyan listesi çürümüş (alan bağlandı ama listede kaldı) | `test_field_wiring_layer_a.py::test_declared_lists_do_not_rot` |
| Payload anahtarı çıktıyı hiç değiştirmiyor (ölü girdi) | `test_field_wiring_layer_b.py::test_no_dead_inputs_in_hybrid` |
| Girdi yalnız kendi yankısını değiştiriyor (fiilen ölü) | `test_field_wiring_layer_b.py::test_no_echo_only_inputs_in_hybrid` |
| Hiçbir girdiden etkilenmeyen sayısal çıktı (uydurma sabit) | `test_field_wiring_layer_b.py::test_no_fabricated_constant_outputs` |
| Ölçüm kapsamının sessizce daralması | `test_field_wiring_layer_b.py::test_shake_covers_a_meaningful_share_of_the_form` |
| Emniyet katsayısının totolojik olması (kullanıcının girdisinin geri okunması) | `test_hybrid_wired_fields_v2626.py::test_safety_factor_is_not_tautological` |
| Kamara boyu ezmesinin sessizce kırpılması | `test_hybrid_wired_fields_v2626.py::test_chamber_length_override_too_short_is_rejected_loudly` |
| Yayımlanmış verisi olmayan malzemeye erozyon katsayısı uydurulması | `test_hybrid_wired_fields_v2626.py::test_nozzle_material_erosion_only_when_published_data_exists` |
| Enjektör plaka gerilmesinin malzemeden bağımsız hesaplanması | `test_hybrid_wired_fields_v2626.py::test_injector_plate_safety_factor_depends_on_material` |
| Kaldırılan yinelenen alanların geri gelmesi | `test_hybrid_wired_fields_v2626.py::test_removed_duplicate_fields_stay_removed` |
| Impingement enjektöründe HTTP 500 çökmesi | `test_field_wiring_layer_b.py::test_impingement_without_angle_does_not_crash` |
| Devre modeli boyutlandıramayınca uydurma delik planı üretilmesi | `test_field_wiring_layer_b.py::test_injector_detail_never_fabricates_a_hole_plan` |
| Arayüz sözcüğü ile modül sözcüğü arasındaki eşlemenin kopması | `test_field_wiring_layer_b.py::test_injector_type_vocabulary_is_mapped` |
| Panellerin uzunluk birimlerini yanlış çevirmesi | `test_panel_units_v2626.py` |
| Sürüm notlarının dil eşleşmemesi | `test_release_notes_language.py` |
| macOS paketinin imzasız çıkması | `test_packaging_signature.py` + yayın kapısı 6/6 |

### v2.6.27 (geliştirme sürüyor)

| Kusur | Bekçi |
|---|---|
| **F5-1 (KRİTİK)** Hibritte İKİ kamara cidarı: ısı zinciri sessiz 0,005 m varsayılanını, yapısal/CAD zinciri kendi boyutlandırdığı 18,79 mm'yi kullanıyordu; ürün yine de "çizilen cidardaki emniyet katsayısı = 2,1523" yayımlıyordu (ısı zincirinin hiç görmediği cidar için). Kapandı: cidarın TEK kaynağı kullanıcı değeri ya da yapısal boyutlandırma; ısı(t)→cidar sıcaklıkları→derating→t sabit-nokta döngüsü (2 yinelemede kalıntı 0,0). Ölçüldü: ısı = yapısal = CAD = 18,7886 mm; maskelenen gerçek SF 0,9410, cidar ΔT 9,4→33,4 K | `test_scofield_hibrit.py::TestF51TekCidar` (6 test; mutasyon: sessiz 5 mm geri → 4 kırmızı) |
| **F3-1** C_D=0,98 boğaz alanına gömülüyken iki zaman serisi onu geri okumuyordu: t=0'da itki 3000⟷3061 N, oda basıncı 30,00⟷29,40 bar. Kapandı: tek C_D sözleşmesi (adlandırılmış `THROAT_DISCHARGE_COEFFICIENT`), debi C_D taşır, itki geometrik boğazla kurulur. Ölçüldü: özdeşlik her istasyonda kalıntı 1,8e-16 | `test_scofield_hibrit.py::TestF31TekCD` + `test_scofield_analiz.py::TestF31TekCdSozlesmesi` (mutasyon: 2+2 kırmızı) |
| **F3-2** `total_mass_kg` yüklenen değil YANAN yakıtla toplanıyordu (97,23 vs 102,48 kg; %5,1 sliver uçuş bütçesinden düşüyordu) — üstelik aynı yanıtın `oxidizer_mass_basis` alanı kuralı yazıyordu | `test_scofield_hibrit.py::TestF32YuklenenKutle` (mutasyon: 1 kırmızı) |
| **F4-3** `thrust=0` sessizce 1000 N oluyor, üstelik `supplied=['thrust']` deniyordu — deponun kendi `input_guard.py:9-12` ilkesinin ÖRNEK verdiği hata | `test_scofield_hibrit.py::TestF43SifirGirdi` (7 test; mutasyon: 4 kırmızı) |
| **F4-1** `analyze_heat_transfer(motor_data={})` boş girdiyle 155 yaprağın tamamını dolduruyordu (`heat_flux` 13,03 MW/m², `risk_level` HIGH); docstring bunların fizikten türediğini söylüyordu. Kapandı: `HEAT_TRANSFER_REQUIRED_FIELDS` + boğaz ölçeği kapısı, `MissingHeatTransferInput` eksik alanları adıyla sayar | `test_scofield_analiz.py::TestF41IsiTransferiGirdiKapisi` (mutasyon: 15 kırmızı) |
| **F4-4 / F4-5** Çalkalanma negatif yoğunlukla NEGATİF sıvı kütlesi yayımlıyordu; `analyze_combustion` `of_ratio=-6` ile tam performans sonucu (negatif eşdeğerlik oranı dâhil) üretiyordu | `test_scofield_analiz.py::TestF44CalkalanmaGirdiKapisi` + `TestF45KarisimOraniKapisi` (mutasyon: 8+5 kırmızı) |
| **F3-3** `vacuum_isp` vakumda değil irtifa tablosunun EN ÜST satırındaydı (20 km, 0,055 bar); doğru sayı aynı fonksiyonun `thrust_vacuum` alanında zaten duruyordu. Kapandı: Pa=0 limiti, irtifa listesinden BAĞIMSIZ (uzun/kısa liste rel=1e-12 özdeş) | `test_scofield_analiz.py::TestF33VakumIspTanimi` (mutasyon: 3 kırmızı) |
| **F1-2** Basınç-beslemeli tank marjı yanlış terimden kuruluyordu: +4,402 bar yayımlanırken aynı yanıtın çevrim çözücüsü −3,576 bar ve `pressure_fed_infeasible / critical` diyordu. Kapandı: tek kaynak `cycle_power_balance.py:613` | `test_scofield_sivi.py::TestF12TankMarji` (mutasyon: 2 kırmızı) |
| **F1-1 / F5-3 / F5-4** Sıvıda üç çelişki: başlık Isp'si çevrim çözümüyle 3,415 s ayrışıyordu (beyansız); aynı turbopompa 169,55 ⟷ 110,21 kW; aynı kanal devresi 52,15 ⟷ 10,95 MW/m² ve 820 ⟷ 422 K. Kapandı: `cycle_isp_accounting` bloğu, türbin gücü üç yayında TEK değer (110,208 kW), `channel_circuit_reconciliation` iki kümeyi ADIYLA uzlaştırır | `test_scofield_sivi.py` (12 test; mutasyon: 3+2+3 kırmızı) |
| **F2-1 / F2-2 / F4-2** Katıda: tek kasa ÜÇ malzeme kimliği taşıyordu; `isp_vacuum` P_c'yi hiç görmeyen ampirik log-fit çarpanından geliyor ve yanıtın kendi C_F fiziğiyle ~%7 çelişiyordu; yapısal hüküm modülün kendi "totolojik" işaretli adayından türüyordu | `test_scofield_kati.py` (24 test; mutasyon: HEAD davranışı geri → kırmızı) |
| **F5-2 / F5-5** Güverte yapısal paneli cidar sıcaklığı devrini hiç göndermiyordu (artık motorun sayısıyla bit-aynı); sıvı sayfası her koşuda `Reliability: NaN%` basıyordu (artık "yayımlanmıyor" beyanı) | `test_scofield_arayuz.py` (mutasyon: 3+2 kırmızı) |
| **T2-1** 17 STEP/CAD bekçisi CI'da HİÇBİR YERDE koşmuyordu: `step-export` işi fail-closed ama ELLE yazılmış 5 dosyalık listeyle koşuyordu ve liste çürümüştü (2026-08-03 node deliğinin aynı sınıfı). Kapandı: 8 dosya (248 test) + **liste türetilir** | `test_ci_kapsam_kapisi.py::TestStepExportKapsami` — build123d'ye kapılı her dosya AST ile taranır, işe girmemişse KIRILIR (mutasyon: dosya çıkarıldı → 1 kırmızı) |
| **T2-2 / T2-3 / T2-4** Atlama gerekçesi yalan söylüyordu: bağımlılık KURULU ama ürün yolu bozukken testler "kurulu değil" diyerek atlıyordu (cantera 39, CoolProp 5 bekçi); numba hiçbir requirements dosyasında olmadığı için bit-özdeşlik bekçisi CI'da hiç koşamıyordu. Kapandı: yokluk ile bozukluk AYRILDI (bozuksa KIRMIZI), numba requirements-dev'e girdi | `test_ci_kapsam_kapisi.py::TestAtlamaGerekcesiDurust` + `test_pressurant.py` + `tests/cfd/test_performans.py` (ölçüldü: bozuk cantera 0 atlama/38 hata; bozuk CoolProp 4 kırmızı) |
| **T1-1** NaN bekçisi totolojikti (`... or 'NaN' not in flat` — Python NaN'ı daima küçük harf yazar, sağ taraf daima doğru): sonucun TAMAMI NaN olsa test yeşildi | `test_leckner_radiation.py` — özyinelemeli sonluluk denetimi, sonlu olmayan yaprağı ADIYLA listeler (mutasyon: 100 yaprak NaN → eski assert geçiyor, yeni kırılıyor) |
| **T1-2 / T1-3 / T3-1 / T3-2** Dört bekçi ölçtüğünü sanıp ölçmüyordu: doğrulama süitinin APCP referansı katalogun 2,2387 katıydı ve "typical APCP" etiketliydi; RS-25 bandı beyanı 80-160 derken kapı 80-200'dü; TM-107041 kilidi TEK YÖNLÜYDÜ (tarihi 10× kusuru geri gelse 48/48 yeşil); SF totoloji bekçisi etikete bakıyordu (SF girdiden koparılınca 30/30 yeşil) | sırasıyla `test_solid_rocket_validation.py`, `test_heat_transfer_validation.py`, `test_thermal_protection.py`, `test_hybrid_wired_fields_v2626.py` — dördü de mutasyonla ölçüldü |
| **Ana model dikişi:** katı emniyet zinciri F4-1 kapısı devreye girince `try/except` içinde sessizce ORTAM sıcaklığına düşüyordu (cidar 293,15 K, "soğutma cidarı değiştirir" bekçisi ölçtüğünü sanıyordu). Üç test aslında uydurma davranışı kilitliyormuş | `test_solid_safety_real.py` — yardımcıya gerçek `chamber_length`+`throat_diameter` verildi (kapı GEVŞETİLMEDİ), varsayım dalı `_dus` ile açıkça sınanır |
| Paraşüt üçlüsü hibritte kapısızdı (2,0 m²/1,4/2,0 s düzeltilemez varsayılan) — parti 25'te kapı açıldı (optNum sözleşmesi, boş→anahtar yok); 16 Ağu taze bağlama haritasında `parachute_area/cd/deploy_delay` hibritte ÖLÇÜLÜ BAĞLI | parti 25 paraşüt bekçileri (11 bekçi + mutasyon: uydurma 2,0 m² geri gelirse 4 kırmızı) + `docs/dev/wiring_map_hybrid.html` 16 Ağu koşumu |
| Katı `port_area` dizisi yayımlanmıyordu; animasyon kütle-denge türetmesine mahkûmdu — parti 26'da yayımlandı (basis'li), animasyon türetmesiz gerçek seriden (`solid_port_area` kipi), eski sonuçlara kütle-denge yedeği beyanla | `tests/test_yanma_animasyonu.py` 42→71 (M1 mutasyonu: yayın silinirse 13 kırmızı) + `TestCozucuPortAlaniAnlami` (BATES-dışı eşdeğer-port gerçeği bekçili) |
| 3B ızgara rozeti `_gridBadge` ekran dışındaydı (NDC v=+11,5, üstelik kameranın ARKASINDA) — parti 26'da çip çapası desenine alındı (u=−0,505, v=+0,045; L 150-6000 mm taramasında en kötü \|NDC\|=0,867) | `tests/test_viz3d_gorsel_kalite.py::TestIzgaraRozetiGorunurlugu` (52→60; tarama tabanlı) |
| Soğuk-cidar Bartz akısının Q\* modeline doğrudan beslenmesi (ablatif ~109× fazla tahmin, 278,8 mm astar) | `test_hibrit_baglama_a5a8a2.py::test_a5_astar_boyutlari_gercek_akidan` + `test_sivi_baglama_beyan.py` enerji dengesi sözleşmesi |
| Üfleme blokajının sabit 0,5 alınması (yanlış rejim: ψ=0,5 ⇒ B′≈1,6-2,5 atmosferik giriş; APCP boğazında akının İŞARETİNİ ters çevirip ölçülen 0,124-0,139 mm/s yerine 0 üretiyordu) | `test_kati_ablatif_baglama.py` mutasyon denetimi (sabit-ψ yaması bekçiyi kırar) + `test_thermal_protection.py` öz-tutarlılık testleri |
| `no_net_heating` rejiminde 0,0 mm'nin `sized` diye yayımlanması (gerileme sıfırken kalınlığı iletim/bond sınırı belirler — 0,0 mm sessiz tehlike) | `test_hibrit_baglama_a5a8a2.py::_sozlesme` hüküm 2 + `test_thermal_protection.py` no_net testleri |
| Katı kapak astarının boğaz akısıyla ve tek malzemeyle boyutlanması (ön/arka aynı sayı; KNDX'te ṡ=0,36-0,92 mm/s zarf-dışı sayı `sized` basılıyordu; kapakta karbon-fenolik yanlış malzeme ailesi — SP-8093 kubbe yalıtımı elastomerdir) | `test_solid_wiring_v2626.py::TestInsulationSystem` (istasyon/malzeme ayrımı) + `test_kati_ablatif_baglama.py` |
| TM-107041 ölçüm bandının 10× yanlış okunması (0,082 — tablo sütunu ×10⁻² çarpanlıydı, gerçek üst uç 0,00822 mm/s; yanlış bant doğrulama testinin ölçütüydü) | `test_thermal_protection.py` bandı modül sabitlerinden (`TM107041_TABLE2_*`) import eder — tek tanım noktası |
| Yanlış monograf künyesi: "SP-8091 Solid Rocket Motor Internal Insulation" (SP-8091 = "The Planet Saturn"; doğrusu SP-8093, nozul için SP-8115) | künye düzeltme notu `thermal_protection.py` modül başlığında; kod içi atıflar taranarak düzeltildi |
| `solid.html` sayfa varsayılanının katalog yanma hızını ezmesi (`value="0.005"` + toplama `\|\| 0.005` düşüşü; ölçülen etki: aynı APCP motoru yanma 2,67→1,17 s ≈ 2,3×, kullanıcı kendi yazmadığı sayı için katalog-dışı uyarısı görüyordu) | `test_solid_yanma_hizi_varsayilani.py` — şablon tarafı (sabit değer + sessiz düşüş yasağı) ve API sözleşmesi (alan yokluğu = katalog çözümü) + mutasyon denetimi |
| Katı sayfası yanma animasyonunun SAHTE olması (motor_viz3d `sqrt(lerp)` uydurma yasası + solid.html'in ÜRETTİĞİ bitiş çapı `0,9×dış` — "kabuk görünsün diye"; kullanıcı kendi motorunun yanışını izlediğini sanıyordu, eğrinin hesapla bağı yoktu). Parti 25'te gerçek seriye bağlandı: r_b = ṁ/(ρ_p·A_b) özdeşliğinin tersinden w(t) (iki bağımsız kanıt: web_burnout'a %0,001; burn_area geri-kurulumu %0,0023); BATES dışı kesit donuk + beyanlı | `test_yanma_animasyonu.py` — 42 bekçi, 10 mutasyon kanıtı (uydurma yasa/bitiş çapı geri gelirse kırmızı; kip çipi yalan söyleyemez) |
| 3B beyan çiplerinin v2.6.27'den beri EKRAN DIŞINA çizilmesi (çapa ızgara köşesinde ±0,42·2200 mm, kamera motoru çerçeveliyor — NDC x=−2,05…−2,34; "veri yok / yerel üretim" beyanları hiç görünmüyordu) — parti 25'te çapa motor boyuna bağlandı, tarayıcıda doğrulandı | `test_yanma_animasyonu.py` çip çapası/boyu bekçileri (M9/M10 mutasyonları) |
| Sürüm dizesi `2.6.26` kalması (`.hrma` dosyaları kendini yanlış künyeliyordu) — parti 10'da (`d36624e`) 2.6.27'ye eşitlendi | Yayın kapısı 1/8 (paket sürümü = changelog en üst girdi = sürüm notu dosyası, mekanik) |
| `gimbal_mount` (742 satır) hiçbir üründen çağrılmaması — parti 13'te (`76cf8ca`) `/api/gimbal-mount` + sıvı sayfası paneli bağlandı | `test_gimbal_baglama.py` (17 test: uç sözleşmesi, 422 eksik-girdi beyanı, panel bağlaması) |
| EN `fea.intro` sözlük girdisinin cümle ortasında kesik olması ("…wall of " — birleştirmenin yalnız ilk dizesi sözlüğe kopyalanmış; TR tamdı, EN kullanıcı yarım cümle görüyordu; FEA ürün turu ölçümü, 15 Ağu; tarama aynı hastalığı 9 girdide daha buldu, parti 20'de tamamı onarıldı) | `test_i18n_parca_kopya.py` — EN sözlük girdisi kodun tam fallback'inin kesik ön eki olamaz (TR 'Kerosen' istisnası gerekçeli; mutasyonla kanıtlı) |
| Sıvı cidar FEA'sının üründe olmaması + varsayılan sıvı örneğinde sınırsız büyüyen tepe (1742 MPa, %16-17/tur — kökü köşe/mesh değil, DIŞ YÜZEY kuruluşu: normal öteleme boğaz vadisinde dış eğrilik yarıçapını Rn−t≈0,45 mm'ye çökertip yapay jilet-çentik üretiyordu; yayımlanan 68 noktalı kontur poligonunun tepe köşeleri ötelemede keskinleşiyordu — hibritteki eski 16,8 MPa tepenin bile kısmen aynı kusur olduğu ölçüldü, 12,5 MPa'ya indi) | `test_mesh_disyuzey_egrilik_tabani.py` (14 bekçi: V-vadi taban ihlali/kapama/iç yüzey değişmezliği, silindir-koni bit-özdeşliği, sıvı deterministik vakası + beyan akışı; mutasyon kanıtlı) + parti 24'te panel sıvıya açıldı, görsel tur sıvıda FEA denetimiyle 3/3 (converged=True %0,63, 65536 eleman, SF 1,23) |

### Önceki sürümlerden devralınan bekçiler

| Kusur | Bekçi |
|---|---|
| Bilinen uydurma sabitlerin geri gelmesi | `test_no_fabrication.py` |
| Güvenlik modülünün dayanaksız hüküm vermesi | `test_safety_honesty.py` |
| CAD notlarının motor verisinden kopması | `test_cad_notes_honesty.py` |
| Sıvı imalat çıktılarının şablon olması | `test_liquid_manufacturing_honesty.py` |
| Geçersiz sayının 0'a çevrilmesi | `test_invalid_value_semantics.py` |
| Egzoz görselinin uydurma sabitlerle çizilmesi | `test_plume_physics.py` |
| Arşiv girdi adı enjeksiyonu ve formül enjeksiyonu | `test_export_injection_guard.py` |
| Kimyasal veritabanının import anında diske yazması | `test_chemical_db_no_write.py` |
| Farklı Isp tanımlarının şablonlarda çıplak "Isp"/"Specific Impulse" etiketiyle sunulması (tasarım noktası, vakum, deniz seviyesi, irtifada teslim edilen, anlık, ima edilen — hepsi tek ada sıkışıyordu) | `test_sivi_form_alanlari.py::test_ciplak_isp_etiketi_kalmadi` |
| Boğaz ısı akısının cidar referansı söylenmeden basılması (referans soğutulmuş cidar tasarım yükü ile denge cidarındaki akı — 2,5 kat fark — aynı adı taşıyordu) | `test_sivi_form_alanlari.py::test_ciplak_isi_akisi_etiketi_kalmadi` |
| Sıvı motorda okunan ama formda kapısı olmayan girdiler (kapak cıvataları, hat cidarı, vana kapanma süresi, hat malzemesi, basınçlandırma gazı) | `test_sivi_form_alanlari.py::test_motorda_okunan_her_anahtarin_formda_kapisi_var` |

## Açık borç

Kapatılmamış ama **bilinen ve gerekçelendirilmiş** kalemler. Bu liste
kısaltılmak içindir; uzuyorsa bir şey yanlış gidiyordur.

| Kalem | Neden açık | Nerede kayıtlı |
|---|---|---|
| Wall-profile ekseni bazı hibrit noktalarında konturla uyuşmuyor (2 kN/30 bar hibritte profil 150,3 mm vs kontur 124,3 mm — termal uç domain bekçisine takılıyor; parti 24 tekillik ajanının ön-var bulgusu, sıvı işinden bağımsız) | Çıkarım katmanı kalemi: profil üreticisiyle köprü konturunun geometri girdileri bazı alanlarda farklı kaynaktan besleniyor; uç dürüstçe reddettiği için kullanıcıya yanlış sayı gitmiyor, ama D2 paneli o noktalarda koşamıyor | bu defter |
| Örnekleyicinin yayımladığı 68 noktalı kontur POLİGONUNUN tepe köşeleri deterministik cidar vakasında mesh inceldikçe büyüyen vM konsantrasyonu üretmeye devam ediyor (parti 25 ölçümü: 662→671→679 MPa; dış yüzey eğrilik tabanı dış eğriyi çözdü, İÇ yüzey poligon köşeleri ayrı kalem). Canlı motor vakası etkilenmiyor (5. turda %0,65 yakınsıyor) — kusur örnekleyici çözünürlüğü/iç yüzey pürüzsüzlüğü sınıfında | İç kontur örneklemesinin yoğunlaştırılması ya da köşe-farkındalıklı istasyon yerleşimi — sample_nozzle_inner_contour n_conv/n_arc/n_div kararıyla birlikte değerlendirilecek; deterministik bekçi vakası hüküm beyanını dürüstçe YAKINSAMADI taşıyor | bu defter; parti 25 radyal-politika ajan raporu |
| Termal FEA (D2) varsayılan mesh'i 16×4 = 64 eleman — kontur ekrana ilk kez bağlanırken çözünürlük kararı (n_axial/n_radial uç parametresi var, UI hangi değerle çağıracak?) | D2 UI bağlaması bu oturumda iniyor; çözünürlük/süre dengesi ürün turunda gözle doğrulanacak | bu defter |
| Durum çipleri yığını hâlâ EVRENSEL değil: parti 25 düzeltmesi ölçülen vakayı kurtardı ama tıknaz gövde + geniş pencerede (L=400 mm, R=60 mm, en-boy 2,0) çip #0 NDC v=−1,02 ölçüldü (parti 26 S6 yan bulgusu) | Rozet için yazılan tarama-tabanlı bekçi deseni (`TestIzgaraRozetiGorunurlugu`) çip YIĞININA uygulanacak — küçük, kendi partisinde | bu defter; parti 26 S6 raporu |
| `phases.coasting.apogee_time` = 26,62 s FAZ-YEREL saatte yayımlanıyor; küresel apoje 38,62 s (12,0+26,62; küresel diziyle doğrulandı) — kullanıcı bunu uçuş zamanı okur (parti 26 S7 yan bulgusu) | Yayın katmanında küresel saat + faz-yerel ayrımı beyanla; sarsım bekçisiyle | bu defter; parti 26 S7 raporu |
| Hibrit `mass_flow_rel_diff` çapraz kontrolü TOTOLOJİK: künye "termokimya çaprazı, birkaç yüzde fark beklenir" diyor ama fark 55 alanda 1e-16'ya kadar tam `1/0,98−1` — quasi-1B, A_t'yi CD'siz geri okuyor (hybrid_rocket_engine.py:1378 + 4670) | Ya CD quasi-1B'ye de geçirilir (fark gerçekten termokimyasal olur) ya künye "boğaz CD'sinin geri okunması" diye düzeltilir; ime alınMADI (yanlış künyeyi kilitlerdi) — sabit-borç sayımındaki 4 yaprağın 2'si bu | bu defter; parti 26 S7 raporu |
| `index.html`'de `ambient_temp` alanı YOK ama `app.py:1419` okuyor — iki yaprak 293,15 K'de donuk (paraşüt üçlüsüyle aynı "kanal var kapı yok" sınıfı) | Forma alan + HYBRID_CONTEXTS girdisi; kapanınca sabit-borç eşiği 4→2 iner | bu defter; parti 26 S7 raporu |
| `injector_design.discharge_coefficient` AD ÇAKIŞMASI: kullanıcı 0,70 gönderirken yanıt 0,78 yazıyor (yük canlı ama hibrit formunda alan yok; parti 25 Isp/akı etiket sınıfının enjektör kopyası) | Anahtar bölünür (`injector_model_cd` vb.) veya alan forma açılır | bu defter; parti 26 S7 raporu |
| Düşük-Mach rejiminde yakınsama HIZI: giriş BC onarıldı (parti 26) ama MUSCL sınırlayıcı gevelemesi 60×12'de 4596→23893 iterasyon fark yaratıyor; 120×24'te plato-dondurma tetiklenince 8002'ye iniyor — hızın kilidi sınırlayıcı dondurma politikası + akustik/taşınım ölçek ayrışması. **Parti 27 V0-int güncellemesi:** satır-örtük gevşetme girdi (opt-in) — şoklu üretim vakasında 3,9× iterasyon kazandı, kazanç nj ile büyüyor; AMA düşük-Mach MUSCL örtükte de YAKINSAMIYOR (sınırlayıcı limit döngüsü ölçüldü) — kilidin sınırlayıcı politikası olduğu doğrulandı | Düşük-Mach ön-koşullama viskoz V1 kuyruğunda; örtük yol numba turu da sonraki parti (adım 2-7× pahalı, saf NumPy) | bu defter; parti 26 S9 §10 + parti 27 V0-int raporu |
| AÇIK yolun plato-donması 60×96'da ERKEN ateşliyor (1001. iterasyon) — bayat-kök riski açık yolda da var: analitiğe %0,075 (açık-erken-donmuş) vs %0,053 (örtük-oturma-donmuş; ölçüm parti 27 V0-int) | V0-int'in oturma-tetikli kalıcı dondurma deseni (tetik = hüküm bantlarının kendisi, yeni eşik yok) açık yola da taşınabilir — viskoz partisiyle birlikte | bu defter; parti 27 V0-int raporu |
| Chug eşiğinin 4. ve 5. kopyası hâlâ duruyor: `hrma/engines/injector_design.py:62-63` + `hrma/utils/injector_design.py:187` (uyarı DİZESİ içinde gömülü %15) — parti 27 F2b-2 tekleştirmesi 3 ana kullanıcıyı kimlik-bekçisiyle tek kaynağa bağladı, bu ikisi dosya sahipliği dışıydı | Dar devir bekçisi kurulu (tavan 1 dosya; ithal başlarsa muafiyet silinmeye zorlanır) — kapanış küçük, kendi kaleminde | bu defter; parti 27 F2b-2 raporu |
| Sıvı motorda ṁ ↔ c* tutarsızlığı: τ_c = L*/(c*Γ²) ile yayımlanan kalış süresi (ρV/ṁ) cebirsel aynı büyüklük ama fark %2,55 ölçüldü (ṁ = 3,4176 vs P_c·A_t/c* = 3,4874) — kök, debi/c* zincirinde | `tau_c_vs_residence_time` alanı beyanla yayımlı + [1,00-1,10] bant bekçili; KÖK düzeltmesi motor sayılarını değiştirir, kendi partisinde | bu defter; parti 27 F2b-2 raporu |
| Sıvı teslim-Isp zinciri `eta_f`'i uydurma sabitten üretiyor (liquid_rocket_engine.py:2794) — sürtünme göçü (parti 26 V6) yarı-1B katmanı ölçüme bağladı ama sıvı zincirinin kendi BL çözümü yok | Sıvı zincirine BL bağlaması ayrı karar/parti; sabit değeri bilinçli korunmuştur | bu defter; parti 26 V6 raporu |
| CFD uç iterasyon tavanı üst sınırı çözücü sabiti `DEFAULT_MAX_ITERS=20000`'e kilitli — bugün doğru (tavana dayanan koşu beyanla, kullanılabilir alanla dönüyor; H1 ölçtü) ama VİSKOZ katman gelince çağıranın tavanı YÜKSELTEMEMESİ "süre tavanı yok" kararına (cfd-viskoz-tasarimi.md §13-1) aykırılaşır | Viskoz uygulama partisinde üst sınır çözücünün viskoz varsayılanıyla birlikte yeniden ele alınır | bu defter; parti 26 H1 hakem raporu |
| Hibritin yayımladığı `nozzle_wetted_area` jenerik lüle üstünden integre ediliyor (`hybrid_rocket_engine.py:1704` `ht_input` çıkış çapını/lüle tipini geçirmiyor) — ölçülen: konikte %43,1, bell'de %39,9 FAZLA; `total_heat_rate` %3,8-4,5 fazla (muhafazakâr yön, kullanıcı aleyhine değil). Parti 25 wall-profile ajanının yan bulgusu | Sayı susturulmadı; künyesi `gas_side_analysis.wetted_integral_contour_basis` alanında YANINDA beyan ediliyor. Kapanış: ht_input'a yayımlanan kontur alanlarının geçirilmesi + integralin yayımlanan kontur üstünden alınması — motor sonuç sayılarını değiştiren fizik düzeltmesi olduğundan kendi partisinde, sarsım/beyan bekçileriyle | bu defter; kanıt `tests/test_wall_profile_ekseni.py` ölçüm notları |
| `no_net_heating` durumunda iletim/char kalınlık payının hesaplanmaması (astar iletim ölçütü) | Ablatif malzemelerin k/cp verisi tabloda yok; uydurmak yasak — `heat_sink_transient`'a malzeme verisi eklenince kapanabilir | `thermal_protection.py::ablative_thickness` no_net validity_note |
| Sıvı/hibrit ablatif blokajında c_p bağlandı ama ölçülü uçtan uca tur yapılmadı (yalnız bekçiler yeşil) | Tam süit + görsel tur onuncu parti kapanışında | bu defter |
| `skip_distance`, `secondary_holes` (hibrit enjektör) | Yayımlanmış korelasyon yok; katsayı uydurmak yasak | `test_field_wiring_layer_a.py::DECLARED_UNMODELLED` |
| Lüle kütlesinin "kamara kütlesinin %30'u" olması | Geometri hesabı değil başparmak kuralı; çıktıda `nozzle_weight_basis` ile beyan ediliyor | `structural_analysis.py::_calculate_weight` |
| Güvenlik panelinin `defaults_applied` alanını okumaması | Uç nokta hangi sayının kullanıcıdan gelmediğini bildiriyor, panel göstermiyor; kullanıcı kendi verisi olmayan sayıyı ayırt edemiyor | Bekçisi yok — açık |
| Ortak sözlükteki (`i18n_common.js`) son çıplak Isp/akı etiketleri | Isp/akı adlandırma borcunun şablon ve sayfa-sözlüğü ayağı kapandı (yukarıdaki iki bekçi); ortak sözlükte üç etiket kaldı: `app.metric.isp`/`app.rep.ispLong` (hibrit metrik kartı, tasarım Isp'sini "Specific Impulse" diye basar), `panel.thermal.cardQThroat` + `panel.thermal.heatFluxSeries` (AYNI panelde referans-cidar tasarım akısı ile denge-cidar akısı), `panel.regen.cardPeakFlux`. `i18n_common.js` bu iş kaleminde dokunulamaz kapsam dışıydı (çok sayfalı ortak sözlük, kendi çift yönlü bekçisi var) | Bekçisi yok — açık |

| Besleme hattı çap anahtarı AD AYRIŞMASI: hibrit `feed_line_inner_diameter_mm` (feed_water_hammer.required_inputs'un 2026-08-05'ten beri yayımladığı ad, dalga6 bekçili) ile sıvı `feed_line_diameter_mm` aynı kavramı iki adla taşıyor — parti 28 hibrit chug bağlaması yayımlanmış sözleşmeyi bozmamak için birleştirmedi | Ayrı bir göç kalemi: takma-ad dönemi + beyan + iki uçta bekçi; tek başına küçük ama iki motorun form/proje yükleme dosyalarını etkiler | bu defter; parti 28 A3 raporu |
| Hibritte KAPISIZ_BILINEN beş anahtar: `ambient_temp`, `chamber_temperature`, `gamma`, `gas_constant`, `thrust_coefficient` /calculate'ta kurucuya ulaşıyor ama advanced.html'de kapısı yok — parti 28'in yapısal bekçisi iki yönlü eşikle dondurdu (büyüyemez; kapı açılırsa satır silinmek zorunda) ama beşinin gerekçesi (CEA çözümünün ezme kanalı mı, ölü kanal mı) araştırılmadı | Anahtar başına hüküm: ya form kapısı açılır ya gerekçeli istisna yazılır; sarsım ölçümü karar verdirir | bu defter; parti 28 A3 raporu + tests/test_stability_hibrit_chug.py yapısal bekçisi |
| Hibrit τ_c çaprazı eksik: sıvıdaki `tau_c_vs_residence_time` ölçümünün (ṁ↔c* tutarlılığı, %2,55 bulgusunu yakalayan) hibrit ikizi kurulmadı; girdileri mevcut (`chamber_volume_actual_m3`, `mdot_total`) — hibrit τ_c `l_star_achieved` ile kuruldu ve `tau_c_source` beyanlı | Küçük kalem: aynı alan + [1,00-1,10] bant bekçisi hibrit chug_loop'una eklenir | bu defter; parti 28 A3 raporu |

| Mod haritasında TAM örtüşen frekanslı modların elmas imleri tek im gibi görünür: etiketler kademelenir (parti 29 K1) ama im konumu VERİDİR, jitter sahte veri olurdu; dondurulmuş anlık-görüntü bekçisi de x/y/text dizilerini kilitliyor | Kabul edilebilir; istenirse im boyutu/saydamlıkla çakışma sayısı gösterilebilir — kozmetik, kendi kaleminde | bu defter; parti 29 A1 raporu |
| Mod haritası etiket kademeleri KOŞUM anında çizim genişliğinden hesaplanır: pencere yeniden boyutlanınca Plotly izleri akar ama kademeler bir sonraki çizime kadar eskir; ayrıca tarayıcı measureText ile node bekçisinin 0,6 em font metriği arasında küçük fark olabilir (6 px tampon örter, font yüklenmezse sapabilir) | Plotly relayout kancasına kademe tazeleme bağlanabilir — küçük kalem | bu defter; parti 29 A1 raporu |
| Kök yer eğrisi X-ekseni başlığı ('Dominant root growth rate sigma...') yatay ve uzun — çok dar sütunda taşabilir; parti 29 K2 envanterinin dışındaydı, bilerek dokunulmadı | K2a'nın wrapAxisTitle deseni aynı grafiğe uygulanır — küçük kalem | bu defter; parti 29 A1 raporu |
| analysis_center.css şablon `<link>`'i YOK — analysis_center.js init() head'e enjekte ediyor (parti 29'da şablon dosyaları A3'ün kapsam dışıydı; A2'nin ölü-link bekçisi bu köprüyle tutarlı) | Şablonlara gerçek `<link>` girecek partide A2'nin bekçisi halefine çevrilir ve enjeksiyon sökülür — tarif A3 raporunda | bu defter; parti 29 A2+A3 raporları |
| Merkez içindekiler şeridi kiracı başlıklarını üç idiomla tarar (h1-h6 / data-ac-section / uppercase-div): YENİ bir kiracı farklı başlık deseni kullanırsa şeritte görünmez; bağ iki kiracı için bekçili ama sözleşme metnine yazılmadı. Canlı sticky-sütun turu da browser_harness denetimlerine eklenmedi (fixture bekçileri yeşil) | Kiracı kayıt sözleşmesine idiom notu + tur genişletmesi — dokümantasyon partisinde | bu defter; parti 29 A3 raporu |

| ~~**Bebek-Scofield ön taraması: 25 doğrulanmış bulgu açık**~~ **KAPANDI (17 Ağu 2026, parti 31)** — 25'inin tamamı bekçiye bağlandı, yukarıdaki v2.6.27 tablosuna işlendi. Tarama kaydı ölçüm geçmişi olarak durur (öncesi/sonrası sayıları orada). Eski satır: 25 doğrulanmış bulgu — ürün 18 (1 kritik: hibritte ısı zinciri 5,0 mm ⟷ yapısal/CAD 18,79 mm cidar, üstelik "çizilen cidarda SF=2,152" yayımlanıyor) + bekçi 7 (en ağırı: 17 STEP/CAD bekçisi CI'da hiçbir yerde koşmuyor — `step-export` işinin elle yazılmış 5 dosyalık listesi çürüdü, ölçüldü: build123d gizliyken 30 passed/17 skipped, açıkken 47 passed) | Tarama örneklem tabanlıdır ve Operasyon Scofield'ın (yol haritası §3.5) yerine geçmez; bulguların bir kısmı motor sayılarını değiştiren fizik düzeltmeleridir ve kendi partilerini ister. Her bulgunun ölçümü, komutu ve dosya:satırı kayıtlı | [`docs/scofield-bebek-2026-08-17.md`](scofield-bebek-2026-08-17.md) |

## Kural

Bu defterde bir satırın "kapandı" tarafına geçmesi için tek ölçüt vardır:
**kusuru yeniden üretecek bir değişiklik yapıldığında kırılan bir test.**
Kod okunarak varılan kanaat yeterli değildir.
