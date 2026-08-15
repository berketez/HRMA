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
| Soğuk-cidar Bartz akısının Q\* modeline doğrudan beslenmesi (ablatif ~109× fazla tahmin, 278,8 mm astar) | `test_hibrit_baglama_a5a8a2.py::test_a5_astar_boyutlari_gercek_akidan` + `test_sivi_baglama_beyan.py` enerji dengesi sözleşmesi |
| Üfleme blokajının sabit 0,5 alınması (yanlış rejim: ψ=0,5 ⇒ B′≈1,6-2,5 atmosferik giriş; APCP boğazında akının İŞARETİNİ ters çevirip ölçülen 0,124-0,139 mm/s yerine 0 üretiyordu) | `test_kati_ablatif_baglama.py` mutasyon denetimi (sabit-ψ yaması bekçiyi kırar) + `test_thermal_protection.py` öz-tutarlılık testleri |
| `no_net_heating` rejiminde 0,0 mm'nin `sized` diye yayımlanması (gerileme sıfırken kalınlığı iletim/bond sınırı belirler — 0,0 mm sessiz tehlike) | `test_hibrit_baglama_a5a8a2.py::_sozlesme` hüküm 2 + `test_thermal_protection.py` no_net testleri |
| Katı kapak astarının boğaz akısıyla ve tek malzemeyle boyutlanması (ön/arka aynı sayı; KNDX'te ṡ=0,36-0,92 mm/s zarf-dışı sayı `sized` basılıyordu; kapakta karbon-fenolik yanlış malzeme ailesi — SP-8093 kubbe yalıtımı elastomerdir) | `test_solid_wiring_v2626.py::TestInsulationSystem` (istasyon/malzeme ayrımı) + `test_kati_ablatif_baglama.py` |
| TM-107041 ölçüm bandının 10× yanlış okunması (0,082 — tablo sütunu ×10⁻² çarpanlıydı, gerçek üst uç 0,00822 mm/s; yanlış bant doğrulama testinin ölçütüydü) | `test_thermal_protection.py` bandı modül sabitlerinden (`TM107041_TABLE2_*`) import eder — tek tanım noktası |
| Yanlış monograf künyesi: "SP-8091 Solid Rocket Motor Internal Insulation" (SP-8091 = "The Planet Saturn"; doğrusu SP-8093, nozul için SP-8115) | künye düzeltme notu `thermal_protection.py` modül başlığında; kod içi atıflar taranarak düzeltildi |
| `solid.html` sayfa varsayılanının katalog yanma hızını ezmesi (`value="0.005"` + toplama `\|\| 0.005` düşüşü; ölçülen etki: aynı APCP motoru yanma 2,67→1,17 s ≈ 2,3×, kullanıcı kendi yazmadığı sayı için katalog-dışı uyarısı görüyordu) | `test_solid_yanma_hizi_varsayilani.py` — şablon tarafı (sabit değer + sessiz düşüş yasağı) ve API sözleşmesi (alan yokluğu = katalog çözümü) + mutasyon denetimi |

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
| Sürüm dizesi `2.6.26` kalmış (2.6.27'nin 9 partisi işlenmiş; kaydedilen `.hrma` dosyaları kendini yanlış künyeliyor) | Sürüm numaralama + CITATION.cff eşitlemesi yayın kapısına bağlı — Berke kararı | Bekçisi yok — açık |
| `gimbal_mount` (742 satır) hiçbir üründen çağrılmıyor; sayfada gimbal seçeneği var, arkasında hesap yok | C3 kulvarı bağlaması ayrı iş kalemi | `docs/mimari/teknik-borc.md` |
| `no_net_heating` durumunda iletim/char kalınlık payının hesaplanmaması (astar iletim ölçütü) | Ablatif malzemelerin k/cp verisi tabloda yok; uydurmak yasak — `heat_sink_transient`'a malzeme verisi eklenince kapanabilir | `thermal_protection.py::ablative_thickness` no_net validity_note |
| Sıvı/hibrit ablatif blokajında c_p bağlandı ama ölçülü uçtan uca tur yapılmadı (yalnız bekçiler yeşil) | Tam süit + görsel tur onuncu parti kapanışında | bu defter |
| `skip_distance`, `secondary_holes` (hibrit enjektör) | Yayımlanmış korelasyon yok; katsayı uydurmak yasak | `test_field_wiring_layer_a.py::DECLARED_UNMODELLED` |
| Lüle kütlesinin "kamara kütlesinin %30'u" olması | Geometri hesabı değil başparmak kuralı; çıktıda `nozzle_weight_basis` ile beyan ediliyor | `structural_analysis.py::_calculate_weight` |
| Güvenlik panelinin `defaults_applied` alanını okumaması | Uç nokta hangi sayının kullanıcıdan gelmediğini bildiriyor, panel göstermiyor; kullanıcı kendi verisi olmayan sayıyı ayırt edemiyor | Bekçisi yok — açık |
| Ortak sözlükteki (`i18n_common.js`) son çıplak Isp/akı etiketleri | Isp/akı adlandırma borcunun şablon ve sayfa-sözlüğü ayağı kapandı (yukarıdaki iki bekçi); ortak sözlükte üç etiket kaldı: `app.metric.isp`/`app.rep.ispLong` (hibrit metrik kartı, tasarım Isp'sini "Specific Impulse" diye basar), `panel.thermal.cardQThroat` + `panel.thermal.heatFluxSeries` (AYNI panelde referans-cidar tasarım akısı ile denge-cidar akısı), `panel.regen.cardPeakFlux`. `i18n_common.js` bu iş kaleminde dokunulamaz kapsam dışıydı (çok sayfalı ortak sözlük, kendi çift yönlü bekçisi var) | Bekçisi yok — açık |

## Kural

Bu defterde bir satırın "kapandı" tarafına geçmesi için tek ölçüt vardır:
**kusuru yeniden üretecek bir değişiklik yapıldığında kırılan bir test.**
Kod okunarak varılan kanaat yeterli değildir.
