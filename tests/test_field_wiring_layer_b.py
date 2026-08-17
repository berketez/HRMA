"""KATMAN B bekçisi: payload girdisi çıktıyı gerçekten değiştiriyor mu?

Katman A (``test_field_wiring_layer_a.py``) şablon ile payload arasındaki
dikişi ölçer: "her form alanı bir toplayıcıda okunuyor mu?". Bu dosya bir
sonraki dikişi ölçer: **payload ile çıktı arasındaki** dikişi.

İkisi ayrı kusur sınıfıdır ve biri diğerini yakalamaz:

* Katman A geçer, B kırılır: toplayıcı alanı gönderiyor ama çözücü okumuyor.
  (``contraction_ratio`` v2.6.26'ya kadar tam buydu — arayüz gönderiyordu,
  motora hiç geçirilmiyordu.)
* Katman B geçer, A kırılır: çözücü okuyor ama arayüz göndermiyor.
  (v2.6.25'te hibritin üç termal alanı tam buydu.)

Ölçüm tek bir matristir ve ondan İKİ hata sınıfı çıkar:

    her payload anahtarı x her çıktı yaprağı -> değişti mi?

* **Satır hiç değişmiyorsa** girdi ÖLÜDÜR.
* **Sütun hiçbir girdiyle değişmiyorsa** çıktı UYDURMA SABİTTİR.

Neden vaka listesi yetmez: ``tests/test_no_fabrication.py`` 17 BİLİNEN vakayı
sabitler. Vaka listelemek yeni uydurmayı yakalamaz; bu dosya vaka listelemez,
tarar. Nitekim ilk koşusunda yayınlanmış sürümde duran iki kusur çıktı:
``IMPINGEMENT_HALF_ANGLE_DEG`` import edilmediği için impingement yolunda
HTTP 500, ve devre modeli hata verdiğinde üretilen uydurma "12 delikli
showerhead" yedeği.

Sarsım aralıkları şablonun KENDİ ``min``/``max`` özniteliklerinden okunur
(``tests/support/inventory.field_specs_for``). Elle tutulan bir aralık
listesi çürür: yeni alan listeye girmez, değişen aralık eskir ve alan
YALANCI ÖLÜ görünür.
"""

import pytest

from tests.support import inventory, shake


# ---------------------------------------------------------------------------
# Taban motor — geçerli, tipik bir hibrit tasarım
#
# Bu sözlük bir HTTP YÜKÜDÜR: ``/calculate``e POST edilir ve app.py tarafından
# normalleştirilir (mm -> m, faz/malzeme çözümü). Motor kurucusuna doğrudan
# verilemez — 12 anahtarı (motor_type, tank_pressure, oxidizer_density,
# hole_diameter_min/max, target_velocity, ...) ``HybridRocketEngine.__init__``
# imzasında yoktur, ``HybridRocketEngine(**HYBRID_BASE)`` TypeError verir.
# Kurucuya doğrudan giden hibrit girdileri için ``test_uncertainty.HYBRID_CTOR``
# ayrı bir kavramdır (v2.6.27'de ad ayrıştırıldı); ikisi teklenemez, çalışma
# noktaları da bilerek farklıdır.
#
# TEK KAYNAK: buradaki tanımı dört test dosyası ve ``tools/wiring_map.py``
# içe aktarır. Kopyalanmaz, buradan import edilir.
# ---------------------------------------------------------------------------
HYBRID_BASE = {
    'motor_type': 'hybrid', 'motor_name': 'LAYER-B', 'motor_description': '',
    'thrust': 5000, 'burn_time': 10, 'chamber_pressure': 20,
    'tank_pressure': 50, 'of_ratio': 2.5, 'atmospheric_pressure': 1.013,
    'l_star': 1.0, 'expansion_ratio': 4.0, 'nozzle_type': 'conical',
    'combustion_type': 'infinite', 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'oxidizer_phase': 'liquid',
    'oxidizer_density': 1220, 'oxidizer_temp': 293,
    'oxidizer_viscosity': 0.0002, 'fuel_density': 920,
    'regression_a': 3.68e-5, 'regression_n': 0.555,
    'injector_type': 'showerhead', 'target_velocity': 30,
    'hole_diameter_min': 0.3, 'hole_diameter_max': 2.0, 'plate_thickness': 3.0,
    'chamber_material': 'steel_4130', 'wall_thickness': 5,
    'cooling_channels': 'none', 'chamber_temperature': 3000,
    'safety_factor': 4.0, 'nozzle_material': 'graphite',
    'injector_material': 'stainless_steel', 'discharge_coefficient': 0.7,
}

# Bazı alanlar yalnız kendi dalında canlıdır; o dal kurulmadan ölçülürse
# YALANCI ÖLÜ görünürler. Refakat alanları burada bildirilir.
HYBRID_CONTEXTS = {
    # v2.6.26 — rüzgâr YÖNÜ yalnız rüzgâr HIZI sıfırdan büyükken anlamlıdır:
    # vx_wind = -wind_speed * cos(yön) (trajectory_analysis.py:300). Taban
    # yükte wind_speed=0 olduğu için yönü tek başına sarsmak hiçbir şeyi
    # oynatmaz ve alan YALANCI "yalnız-yankı" görünür. Dal kurulmadan ölçülen
    # alan yanlış hüküm verir — star_points / slot_width ile aynı sınıf.
    'wind_direction': {'wind_speed': 15.0, 'wind_direction': 90.0},
    # v2.6.27 yirmi sekizinci parti — chug atalet kapıları ÇİFT hâlde
    # canlıdır: τ_f = L·ṁ/(2A·ΔP) hem hat uzunluğu hem iç çapı (kesiti)
    # ister (hybrid_rocket_engine._feed_line_inertance_inputs; çekirdek
    # hrma/stability/chug.feed_inertance_time_constant). Taban yükte ikisi
    # de boş olduğundan alanı TEK başına sarsmak chug çevrimini ataletsiz
    # bırakır ve alan YALANCI ölü görünür — wind_direction ile aynı sınıf.
    # Ölçüldü (parti 28): 1,5 m + 12 mm → chug_loop.tau_f_s = 8,507e-4 s,
    # inertance_included=true; tek alan → değişen yaprak sıfır.
    'feed_line_length_m': {'feed_line_length_m': 1.5,
                           'feed_line_inner_diameter_mm': 12.0},
    'feed_line_inner_diameter_mm': {'feed_line_length_m': 1.5,
                                    'feed_line_inner_diameter_mm': 12.0},
    'outer_diameter': {'injector_type': 'pintle', 'pintle_diameter': 25,
                       'outer_diameter': 50},
    'pintle_diameter': {'injector_type': 'pintle', 'pintle_diameter': 25,
                        'outer_diameter': 50},
    # v2.6.27: 'secondary_holes' YALNIZ pintle dalında anlamlıdır. Varsayılan
    # yükte injector_type='showerhead' olduğu için alanı tek başına sarsmak
    # hiçbir şeyi oynatmaz ve alan YALANCI 'ölü girdi' görünür — outer_diameter
    # / pintle_diameter ile aynı sınıf. Dal kurulunca gerçekten canlı:
    # ölçüldü, none -> 0 delik (TMR tanımsız), radial -> 182 delik,
    # tangential -> aynı geometri + teğetsel momentumun modellenmediği beyanı;
    # üç seçimin enjektör bloğu birbirinden farklı.
    'secondary_holes': {'injector_type': 'pintle', 'pintle_diameter': 25,
                        'outer_diameter': 50, 'secondary_holes': 'radial'},
    'n_slots': {'injector_type': 'swirl', 'n_slots': 6},
    'slot_width': {'injector_type': 'swirl', 'n_slots': 6,
                   'slot_width': 1.0, 'slot_height': 2.0},
    'slot_height': {'injector_type': 'swirl', 'n_slots': 6,
                    'slot_width': 1.0, 'slot_height': 2.0},
    'swirl_chamber_diameter': {'injector_type': 'swirl', 'n_slots': 6,
                               'swirl_chamber_diameter': 20},
    'swirl_angle': {'injector_type': 'swirl', 'n_slots': 6,
                    'swirl_angle': 45},
    'element_pairs': {'injector_type': 'impingement', 'element_pairs': 8,
                      'impingement_angle': 60},
    'impingement_angle': {'injector_type': 'impingement', 'element_pairs': 8,
                          'impingement_angle': 60},
    'inner_diameter': {'injector_type': 'coaxial', 'inner_diameter': 5,
                       'outer_annulus_diameter': 10},
    'outer_annulus_diameter': {'injector_type': 'coaxial',
                               'inner_diameter': 5,
                               'outer_annulus_diameter': 10},
    'mass_flux_chamber': {'combustion_type': 'finite',
                          'mass_flux_chamber': 300},
    'contraction_ratio': {'combustion_type': 'finite',
                          'contraction_ratio': 4},
    # Payload birimi MİLİMETRE (app.py::_mm_to_m_optional). Metre değeri
    # vermek 3.6 mm demek olur, geometrik alt sınırın altında kalır ve alan
    # YALANCI ÖLÜ görünür — ölçüm hatası olarak bir kez yaşandı.
    'chamber_length_override': {'chamber_length_override': 3600},
    'chamber_diameter_input': {'chamber_diameter_input': 150},
    'initial_port_diameter': {'initial_port_diameter': 0.03},
    'n_holes': {'n_holes': 20},
    'pressure_drop': {'pressure_drop': 4.0},
    # --- KURTARMA ÜÇLÜSÜ (2.6.27, yirmi ikinci parti artçısı) -------------
    # Bu üç alanın ŞABLON VARSAYILANI YOKTUR ve bu bilinçlidir: boş alanın
    # anahtarı isteğe hiç konmaz, çözücü varsayımını 'assumed' damgasıyla
    # beyan eder (advanced.html/solid.html paraşüt bloğu). Taban yükte de
    # anahtar bulunmadığı için sarsıcı "mevcut değer" göremez ve alan
    # ÖLÇÜLEMEDİ görünürdü — chamber_length_override ile aynı sınıf.
    # Bağlam değeri olarak çözücünün KENDİ belgelenmiş varsayımı verildi
    # (trajectory_analysis.py DEFAULT_PARACHUTE_*): sarsım böylece
    # "kullanıcı varsayımın kendisini yazsa bile onu değiştirebiliyor mu"
    # sorusunu ölçer. Uçtan uca kanıt ayrı dosyada
    # (tests/test_parasut_alanlari.py): 2,0 m²/Cd 1,4/2,0 s -> iniş
    # 22,62 m/s, 9,0/0,9/5,0 -> 13,29 m/s.
    'parachute_area': {'parachute_area': 2.0},
    'parachute_cd': {'parachute_cd': 1.4},
    'parachute_deploy_delay': {'parachute_deploy_delay': 2.0},
    # --- KISIT ALANLARI: yalnız KISIT BAĞLADIĞINDA sonucu değiştirirler ---
    # İmalat bandı, çözümün doğal çapını kapsıyorsa bandı değiştirmek hiçbir
    # şeyi değiştirmez ve bu DOĞRUDUR (kısıt bağlamıyor). Alanın canlı
    # olduğunu görebilmek için sarsımın bağlayıcı bölgede kalması gerekir.
    # Ölçüldü: 0.3 -> 0.45 hiçbir şey değiştirmiyor (çözüm çapı 0.965 mm,
    # ikisinin de üstünde); 1.0 -> 1.5 on yaprak değiştiriyor.
    'hole_diameter_min': {'hole_diameter_min': 1.0, 'hole_diameter_max': 2.0},
    'hole_diameter_max': {'hole_diameter_min': 0.3, 'hole_diameter_max': 0.6},
    # Aynı gerekçe: 8 ve 12 çift, çap bandın dışına düştüğü için ikisi de
    # 15'e yeniden çözülüyordu. 16 üstü bölgede kullanıcının değeri korunur.
    'element_pairs': {'injector_type': 'impingement', 'element_pairs': 16,
                      'impingement_angle': 60},
    'orifice_diameter': {'injector_type': 'impingement', 'element_pairs': 16,
                         'impingement_angle': 60, 'orifice_diameter': 1.0},
}

#: Çözücünün "bu alanı TÜKETMİYORUM" diye AÇIKÇA beyan ettiği alanlar.
#: Beyan ``app.py`` içinde yapılır ve kullanıcıya yanıttaki ``unused_inputs``
#: ile ULAŞIR — yani sessiz değildir. Bu liste o beyanın kopyasıdır ve
#: aşağıdaki test ikisinin AYNI kaldığını doğrular; beyan kaldırılıp alan
#: bağlanmadan kalırsa bekçi kırılır.
DECLARED_UNUSED_IN_APP = {
    'impingement_distance': 'model bu mesafeyi çarpışma açısı ve delik çapından hesaplar',
    'momentum_ratio': 'benzer-akışkan doublet modeli; MR ölçütü farklı-akışkan içindir',
    'impingement_pattern': 'yalnız like_on_like/doublet modelleniyor',
    'recess_length': 'model girintiyi iç jet çapından hesaplar',
    'n_elements': 'bu yol tek koaksiyel eleman boyutlandırır',
    # v2.6.26 — gaz fazı enjeksiyonu MODELLENMİYOR. Alan yalnız uyarı
    # üretiyor (fiziksel yaprak oynatmıyor) ve bu artık kullanıcıya açıkça
    # söyleniyor: 'gas' seçilirse delik boyutlandırması sıvı SPI modeliyle
    # yapılmış demektir. Sıkıştırılabilir çözüm depoda var
    # (engines/injector_design.py::compressible_orifice_flow), bağlanması
    # ayrı bir iş olarak kayıtlı.
    'oxidizer_phase': 'gaz fazı enjeksiyonu modellenmiyor; alan yalnız uyarı '
                      'üretir ve durumu açıkça bildirir',
}

# Şablon alan adı ile payload anahtarı AYRI olan alanlar. Toplayıcı bu
# dönüşümü yapar; Katman B payload anahtarını sarsar, çünkü çözücünün
# gördüğü ad odur. (Şablon adını sarsmak alanı yalancı ölü gösterirdi.)
TEMPLATE_TO_PAYLOAD = {
    'n_holes_override': 'n_holes',
    'pressure_drop_percent': 'pressure_drop',
    'single_pressure': 'atmospheric_pressure',
    'thrust_impulse': 'total_impulse',
    'burn_time_impulse': 'burn_time',
}

#: Yeniden adlandırılan alanın şablon aralığı payload BİRİMİNDE geçerli
#: OLMAYABİLİR. Örnek: ``pressure_drop_percent`` şablonda yüzdedir
#: (min 10, max 50) ama payload'a BAR olarak gider (20 bar odada 4 bar).
#: Şablon aralığını körü körüne devralmak sarsımı "aralık dışı" diye
#: engelliyor ve alan ÖLÇÜLEMEDİ görünüyordu. Birimi değişen her alan
#: burada payload birimiyle bildirilir.
PAYLOAD_RANGE = {
    'pressure_drop': (1.0, 15.0),        # bar (odanın %5-75'i)
}

# Ayrı uç noktaya giden ya da istemci tarafında kalan alanlar Katman B'nin
# konusu değildir; Katman A onları kendi gerekçeli listesinde tutar.
NOT_IN_CALCULATE = {
    'alt_start', 'alt_end', 'alt_points',        # altitude_profile alt sözlüğü
    'traj_alt_start', 'traj_alt_end', 'traj_points',
    'initial_mass', 'final_mass', 'reference_area',
    'viz_ds_dch', 'viz_ds_eps', 'viz_ds_lstar',
    'motor_name', 'motor_description',           # metin: sarsılamaz
    'total_impulse',                             # thrust/burn_time ile çelişir
    'injector_type',                             # dal seçici: refakatsiz 400
}

#: Sabit olması MEŞRU çıktı alt ağaçları. Bu liste DAR tutulmalıdır;
#: genişletmek uydurmayı gizlemenin en kolay yoludur. Her giriş bir
#: GEREKÇE taşır ve gerekçe "sonra bakarız" olamaz.
LEGITIMATE_CONSTANTS = (
    # Sabit irtifa ızgarası: standart atmosferden gelir, motordan değil.
    'altitude_performance',
    # Malzeme kaydı: veritabanı tablosu, hesap değil.
    'material_properties',
    'materials',
    # Kimyasal bileşim: HTPB/N2O'da alüminyum vb. sıfırdır (gerçek sıfır).
    'elemental_composition',
    # Sürüm/şema numaraları.
    'schema_version', 'version',
    # Fiziksel sabitler ve birim çarpanları.
    'g0', 'standard_gravity',
    # v2.6.27 (Dalga 6, akustik modların bağlanması): mod ETİKETLERİ.
    # 'indices.longitudinal_q/radial_n/tangential_m' bir hesabın sonucu
    # değil, modu ADLANDIRAN tam sayılardır (1L, 1T, 2R...); girdiye göre
    # değişmemeleri doğru davranıştır. Aynı şekilde 'alpha' Bessel
    # denkleminin köküdür — matematiksel bir sabit, motor çıktısı değil.
    # Bu iki aile işaretlenmezse bekçi, uydurma sabit ile mod numarasını
    # ayırt edemez ve gerçek uydurmaları listenin dibine gömer.
    'acoustic_modes.modes',
    'acoustic_modes.inputs.n_modes',
    # v2.6.27: modülün BEYAN ETTİĞİ ölçüt eşikleri. Bunlar hesabın sonucu
    # değil, hesabın hangi literatür ölçütüne göre hüküm verdiğinin
    # yayımıdır (Summerfield ayrılma oranı, chug alt sınırları, screech
    # bandı). Şeffaflık için basılıyorlar; girdiye göre değişmemeleri
    # tanımları gereğidir. Eşiğin KENDİSİ değişirse bu satırlar değişir,
    # yani bekçi hâlâ gerçek bir sözleşmeyi koruyor.
    'hard_min_ratio', 'recommended_min_ratio', 'screech_band_min_hz',
    'pressure_ratio_threshold',
    # v2.6.27 parti 27 (F2b-1 hibrit LFI yayını): Karabeyoglu 2005 Eq. 15
    # korelasyonunun KÜNYELİ literatür sabitleri — hesabın sonucu değil,
    # hangi kalibre katsayıyla konuştuğunun beyanı (0,2341 = 0,48/2,050;
    # kaynak: hybrid_lfi.py modül sabitleri, motor dosyasına kopyalanmadığı
    # test_stability_baglamalar.py'de kaynak-kanıtlı). rt_corr BİLEREK
    # imlenmedi: oksitleyiciyle değişiyor (n2o 4,47e5 / lox 6,38e5 — canlı,
    # F2b-1 sarsımla ölçtü). Önek 'combustion_stability.lfi.' ile DAR.
    'combustion_stability.lfi.coefficient',
    'combustion_stability.lfi.delay_constant_c_prime',
    # v2.6.27 (Cantera beyanı): mekanizmanın termo verisi geçerlilik tavanı
    # (gri30 için min(species.max_temp) = 3000 K — ÖLÇÜLÜYOR, uydurulmuyor).
    # Yukarıdaki ölçüt-eşiği ailesiyle aynı doğa: modelin hangi sınıra kadar
    # konuştuğunun beyanı; girdiye göre değişmemesi tanımı gereği, mekanizma
    # değişirse değer de değişir (bekçi gerçek sözleşmeyi korumaya devam eder).
    'mechanism_T_ceiling_K',
    # v2.6.27 (ablasyon blokaj denetimi): astar bloğunun MALZEME TABLOSU ve
    # BEYAN sabitleri. Bunlar hesabın sonucu değil, hesabın hangi malzeme
    # kaydı ve hangi model sabitiyle yapıldığının yayımıdır (silika-fenolik
    # T_s = 2050 K, char yayıcılığı, Q* bandı ucu, Aerotherm lambda = 0.4,
    # gazlaşan kütle payı, 1.5 tasarım payı; q_reradiated = eps*sigma*T_s^4
    # yalnız bu tablo sabitlerinden türer). Girdiye göre değişmemeleri
    # tanımları gereğidir; malzeme kaydı değişirse değerler de değişir.
    # DİKKAT: '_liner.' önekiyle DAR tutuldu — başka blokların aynı adlı
    # alanları bu muafiyetten YARARLANAMAZ. Çözülen alanlar (blowing_blockage,
    # b_prime, q_net, gerileme) BİLEREK işaretlenmedi: onlar girdiyle
    # değişmek zorundadır ve bekçi onları korumaya devam eder.
    '_liner.T_surface_K', '_liner.emissivity', '_liner.q_star_mj_kg',
    '_liner.design_margin', '_liner.q_reradiated_kw_m2',
    '_liner.blowing_lambda', '_liner.blowing_gas_fraction',
    # Çıplak cidar geçmişinin BAŞLANGIÇ KOŞULU: t = 0 anı, T(0) = ortam.
    # Başlangıç koşulunun girdiden bağımsızlığı tanımı gereğidir.
    'wall_temperature_history.T_initial_K',
    'wall_temperature_history.time_s[0]',
    'wall_temperature_history.wall_inner_temperature_K[0]',
    # ------------------------------------------------------------------
    # v2.6.27 (sabit-çıktı borç kapanışı). Aşağıdaki imlerin TAMAMI DARDIR:
    # her im tek bir yaprağı ya da tek tip bir ızgara ailesini işaretler.
    # Blok geneli im ('oxidizer_tank_slosh' gibi) YASAKTIR — bloğa sonradan
    # eklenecek uydurmayı da örter; dar-im disiplini ayrıca ölçülür
    # (test_whitelist_markers_stay_narrow).
    # ------------------------------------------------------------------
    # Çalkantı süpürme IZGARASININ EKSENİ: sweep_heights = linspace(0.02,
    # 1.0, 25) x fill_height (slosh_analysis.py:363-364) -> fill_ratio =
    # beyanlı kesirler x (h_doluluk/R). h/R = 2 x doluluk x (L/D) olup iki
    # çarpan da beyanlı sabittir (hybrid_rocket_engine.py:132
    # TANK_FILL_FRACTION_DEFAULT, :146 OX_TANK_LD_RATIO; ikisi de _basis
    # alanlarıyla yanıtta beyan edilir). Izgara ekseninin girdiyle
    # değişmemesi tanımı gereğidir; aynı satırların f1_hz / omega1 /
    # pendulum_length / slosh_mass_kg sütunları CANLIDIR ve bekçi onları
    # korumaya devam eder.
    'oxidizer_tank_slosh.slosh.fill_sweep.fill_ratio[',
    # Çalkantı MOD ETİKETLERİ: SP-106 anti-simetrik mod numarası 1..4
    # (slosh_analysis.py:359-361, 'mode': m) — bir hesabın sonucu değil,
    # modu ADLANDIRAN tam sayı. 'acoustic_modes.modes' imiyle aynı gerekçe;
    # kardeş omega / f_hz alanları CANLI kalır.
    'oxidizer_tank_slosh.slosh.modes[0].mode',
    'oxidizer_tank_slosh.slosh.modes[1].mode',
    'oxidizer_tank_slosh.slosh.modes[2].mode',
    'oxidizer_tank_slosh.slosh.modes[3].mode',
    # Miles/SP-8009 perde (baffle) TASARIM HEDEFLERİ — beşi de beyanlı
    # varsayılanların salt fonksiyonudur, tank geometrisi HİÇ girmez:
    # target_damping_ratio = 0.01 hedef (slosh_analysis.py:235 imza, :259),
    # depth_ratio = 0.10 çağrı varsayılanı (:335, :262),
    # amplitude_ratio = _MILES_DEFAULT_AMPLITUDE_RATIO = 0.05 (:100, :263),
    # blocked_area_ratio = (hedef / (C·e^{-4.6·d}·sqrt(eta)))^(2/3) — yalnız
    # bu üç beyandan türer (:254-255),
    # recommended_width_ratio = 1 - sqrt(1 - alan_oranı) (:256).
    # Boyutlu kardeş recommended_width_m = (w/R)·R CANLIDIR (tank
    # yarıçapıyla değişir) ve bekçi onu korumaya devam eder.
    'oxidizer_tank_slosh.slosh.baffle.target_damping_ratio',
    'oxidizer_tank_slosh.slosh.baffle.depth_ratio',
    'oxidizer_tank_slosh.slosh.baffle.amplitude_ratio',
    'oxidizer_tank_slosh.slosh.baffle.blocked_area_ratio',
    'oxidizer_tank_slosh.slosh.baffle.recommended_width_ratio',
    # 1 g BEYANI: g_eff sabit standart yerçekimidir ve öyle BEYAN edilir
    # (hybrid_rocket_engine.py:4132-4140 g_eff_basis: uçuş ivmesi bağlaşımı
    # NOT_MODELLED). Çözücüye g_eff=self.g0 geçirilir (:4107-4108) ve sonuç
    # sözlüğü aynı değeri yankılar (slosh_analysis.py:390).
    'oxidizer_tank_slosh.g_eff_m_s2',
    'oxidizer_tank_slosh.slosh.g_eff',
    # Beyanlı tank L/D tasarım oranı: OX_TANK_LD_RATIO = 2.5
    # (hybrid_rocket_engine.py:146; :4125-4126'da _basis ile yayımlanır).
    'oxidizer_tank_slosh.tank_ld_ratio',
    # t = 0 BAŞLANGIÇ ÖRNEĞİ: zaman-adımlı çözücü t_now = i·dt ile başlar
    # (hybrid_rocket_engine.py:2642-2644, :2669) ve yayın seyreltmesi ilk
    # örneği HER ZAMAN korur (curve_sampling.py::decimate_curve_indices,
    # zorunlu = {0, n-1}) -> time[0] = 0.0 tanımı gereği.
    # 'wall_temperature_history.time_s[0]' emsali.
    'of_shift_performance.time[0]',
    'port_history.time[0]',
    'thrust_curve.time[0]',
    # Yayın örnekleme TAVANI: THRUST_CURVE_MAX_POINTS = 400
    # (curve_sampling.py:40; sampling_block :157'de yayımlar) — iki motorun
    # ortak, beyanlı yayın sözleşmesi. Kardeş points_published /
    # points_computed alanları CANLIDIR.
    'of_shift_performance.sampling.max_points',
    'thrust_curve.sampling.max_points',
    # Kontur/istasyon ORİJİNİ: örnekleyicinin İLK noktası konverjan girişi
    # z = 0'dır (ORİJİN SÖZLEŞMESİ, hybrid_rocket_engine.py:5675-5677;
    # bekçisi tests/test_motor_geometri_yayimi.py). Quasi-1D istasyon
    # ızgarası AYNI örnekleyiciden alınır (hybrid_rocket_engine.py:
    # 4573-4575) -> x_m[0] = 0.0 tanımı gereği. Konturun geri kalan
    # noktaları ve istasyonların basınç/sıcaklık sütunları CANLIDIR.
    'nozzle_contour.points[0][0]',
    'nozzle_flow_quasi1d.stations.x_m[0]',
    # O/F interpolasyon BEYANI: ızgara adımı ve hata sınırı modül
    # sabitleridir (hybrid_rocket_engine.py:88 OF_PERF_GRID_STEP, :94
    # OF_PERF_INTERP_ERROR_BOUND_PCT; :1979-1980 ve :2031-2037'de
    # yayımlanır) — 'hard_min_ratio' ölçüt-eşiği ailesiyle aynı doğa:
    # modelin hangi çözünürlük/hata sözleşmesiyle konuştuğunun yayımı.
    'of_shift.interpolation.grid_step_of',
    'of_shift.interpolation.error_bound_pct',
    # Yapısal BEYAN sabitleri (dördü de kendi _basis alanıyla yayımlanır):
    # design_pressure_factor = çağıran motorun geçtiği 1.5 çarpanı
    # (structural_analysis.py:531 imza; :745-756 beyan),
    # manufacturing_allowance_factor = modül sabiti
    # (structural_analysis.py:959-969),
    # stress_ratio_R = 0.0 ÇEVRİM MODELİ GEREĞİ — her ateşleme 0->P->0
    # tam basınç çevrimi sayılır (structural_analysis.py:1538-1547),
    # design_cycles = beyanlı tasarım hedefi 25 (structural_analysis.py:
    # 1459-1461; :1551) — hesap değil, tasarım girdisinin yayımı.
    'structural_analysis.design_parameters.design_pressure_factor',
    'structural_analysis.chamber_analysis.manufacturing_allowance_factor',
    'structural_analysis.fatigue_analysis.stress_ratio_R',
    'structural_analysis.fatigue_analysis.design_cycles',
    # Lüle AYRIK KAYIP MODELİ beyanları (nozzle_design.py:161-164 imza;
    # :665+ _basis alanlarıyla yayımlanır): friction_efficiency model
    # sabitidir (Sutton & Biblarz sınır-tabaka bandına kalibre, bu
    # tasarımdan HESAPLANMAZ); hibritte metal partikül yok ->
    # particle_mass_fraction = 0 ve two_phase_efficiency = 1 - k·0 = TAM 1
    # (tanımı gereği, basis alanı açıkça söylüyor); two_phase_loss_coeff =
    # k = 0.12 birinci-derece model sabiti. Kardeş divergence_efficiency /
    # kinetic_efficiency / nozzle_efficiency CANLIDIR.
    'nozzle_design.performance.friction_efficiency',
    'nozzle_design.performance.particle_mass_fraction',
    'nozzle_design.performance.two_phase_efficiency',
    'nozzle_design.performance.two_phase_loss_coeff',
) + tuple(
    # İtki-irtifa TARAMA IZGARASI ve standart atmosfer sütunları:
    # altitudes_thrust = [0, 1000, 5000, 10000, 15000, 20000] m SABİT
    # ızgaradır (hybrid_rocket_engine.py:1657); pressure/temperature o
    # irtifadaki ISA değerleridir (combustion_analysis.py:1708-1710,
    # isa_temperature/isa_pressure) — motordan değil atmosfer standardından
    # gelir; mevcut 'altitude_performance' imiyle aynı gerekçe. İm ALAN
    # DÜZEYİNDE dardır: aynı satırların thrust / isp / exit_velocity /
    # effective_total_impulse / impulse_efficiency sütunları CANLIDIR.
    # Izgara 6 noktadır ve im 6 noktaya sabitlenmiştir: ızgara büyürse yeni
    # satır imlenmemiş kalır ve bekçi ızgara değişikliğini GÖRÜR.
    'thrust_altitude_analysis.thrust_altitude_data[%d].%s' % (i, alan)
    for i in range(6) for alan in ('altitude', 'pressure', 'temperature')
) + (
    # Deniz seviyesi kazancı ÖZDEŞLİĞİ: tarama teslim edilen deniz-seviyesi
    # itkisine KENETLİDİR (combustion_analysis.py:2141-2143,
    # thrust_sea_level=base_thrust) ve kazanç = etkin/toplam impuls
    # (:2165-2167) -> 0 m satırında TAM 1.0, kenetin kendisi. Diğer
    # satırların kazançları CANLIDIR.
    'thrust_altitude_analysis.thrust_altitude_data[0].impulse_gain_vs_sea_level',
    # Beyanlı IZGARA UCU: sabit geometrili lülede itki irtifayla monoton
    # arttığı için argmax daima son ızgara noktasıdır; alanın kendi _basis'i
    # bunu "top of the altitude sweep grid, not an optimum" diye yazar
    # (combustion_analysis.py:2181-2189). Kardeş max_thrust CANLIDIR.
    'thrust_altitude_analysis.max_thrust_altitude',
    # ==================================================================
    # v2.6.27 (yirmi altıncı parti — sabit-çıktı borcu 59 -> 4).
    # Aşağıdaki imlerin TAMAMI TEK YAPRAK imidir; tek istisna 25 noktalı
    # süpürme ızgarasıdır ve o da alan düzeyinde dardır. Her im iki
    # kanıttan en az birini taşır:
    #   (1) KOD KANITI — dosya:satır, sabitin nereden geldiği,
    #   (2) GEÇİŞ ÖLÇÜMÜ — bandı/kelepçeyi AÇAN bir çalışma noktası:
    #       "sabit görünüyor ama hesaplanıyor" iddiası, değerin DEĞİŞTİĞİ
    #       bir koşu gösterilerek kanıtlandı.
    # Bandı/kelepçesi gösterilemeyen kalemler İMLENMEDİ; onlar gerçek borç
    # olarak sayımda kaldı (bkz. test_no_fabricated_constant_outputs).
    # ==================================================================
    # ISO 2768-1 BANT BASAMAĞI: genel tolerans, nominal ölçünün BASAMAK
    # fonksiyonudur. Tablonun depodaki tek tanım noktası
    # liquid_rocket_engine.py:243+ (ISO2768_* + _iso2768_feature);
    # cad_visualization.py:112-150 o tabloyu ÇAĞIRIR ve tablo okunamazsa
    # sayı UYDURMAZ ('NOT_AVAILABLE' döner). Yaprağın kendi
    # tolerance_basis'i "the tolerance is a step function of the nominal
    # and stays constant while the nominal stays inside one size band"
    # diye yazar. ÖLÇÜLDÜ (bant geçişi): chamber_diameter_input 150 ve
    # 400 mm -> 0,2 mm; 900 mm -> 0,3 mm. Kardeş 'length.tolerance_mm'
    # BİLEREK imlenmedi ve zaten sabit DEĞİL (2,0 mm) — aynı yardımcının
    # canlı olduğunun bu koşudaki kanıtı.
    'technical_drawings.chamber.tolerances.diameter.tolerance_mm',
    'technical_drawings.chamber.tolerances.outer_diameter.tolerance_mm',
    # ISLAK YÜZEY İNTEGRALİNİN İSTASYON SAYISI: gas_side[
    # 'wetted_integral_stations'] = int(x.size), yani örneklenmiş kontur
    # ızgarasının nokta sayısı (heat_transfer_analysis.py:1564) — hesabın
    # sonucu değil, integralin hangi ÇÖZÜNÜRLÜKLE alındığının beyanı;
    # 'sampling.max_points' ailesiyle aynı doğa. ÖLÇÜLDÜ: conical/bell x
    # eps 4..25'te 41'de sabit, kardeş nozzle_wetted_area /
    # nozzle_heat_rate ise CANLI (ızgara sabitken geometri oynuyor).
    'gas_side_analysis.wetted_integral_stations',
    # ENJEKTÖR Cd BANT TABLOSU: Cd, (giriş tipi, L/D bandı) çiftinden
    # okunur (injector_design.py:51-60; 'sharp', L/D 1-5 -> 0,78) ve
    # yaprak gerekçesini kendisi taşır (discharge_coefficient_basis /
    # cd_basis: "keskin giriş, yeniden yapışan (L/D 1-5); L/D=1,22113 ->
    # Cd=0,78, SP-8089 / Lefebvre & McDonell Böl. 5").
    # ÖLÇÜLDÜ (bant geçişi): plate_thickness 3 -> 20 mm ile L/D
    # 1,2211 -> 8,0550 olur ve Cd 0,78 -> 0,84'e ATLAR; sayı sabit
    # yazılmış değil, bandın içinde duruyor. Kardeş l_over_d /
    # orifice_d_mm / velocity_m_s CANLIDIR.
    # DİKKAT — AYNI AD, İKİ TANIM: bu Cd, kullanıcının gönderdiği
    # 'discharge_coefficient' yükü DEĞİLDİR (yük 0,70 iken model 0,78
    # kullanır). O yük ölçüldü ve CANLI (0,70 -> 0,45 sarsımı 29 yaprak
    # oynatıyor), ama hibrit ŞABLONUNDA karşılığı olmadığı için Katman
    # B'nin sarsım kümesine hiç girmiyor — ayrı bir kalem olarak raporlu.
    'injector_design.discharge_coefficient',
    'injector_design_detail.ox_circuit.cd',
    # MANİFOLD HIZ ORANI HEDEFİ: MANIFOLD_V_RATIO_TARGET modül sabiti
    # (injector_design.py:943) ve yanıt bunun bir HEDEF olduğunu makine
    # okur biçimde beyan eder ('v_ratio_target_is_target': True, :944).
    # Gerçekleşen kardeş 'v_ratio' (0,1399) CANLIDIR; bekçi onu korur.
    'injector_design_detail.ox_circuit.manifold.v_ratio_target',
    # AYRILMA ÖLÇÜTÜ KATSAYISI: SUMMERFIELD_FACTOR_DEFAULT
    # (hrma/flow/separation; hybrid_rocket_engine.py:28 import,
    # :2248 yayım) — modelin hangi literatür ölçütüyle hüküm verdiğinin
    # beyanı; mevcut 'hard_min_ratio' / 'pressure_ratio_threshold'
    # ailesiyle aynı doğa. Kardeş separation_pressure_bar (= katsayı x
    # ortam basıncı) ve separation_limit_expansion_ratio CANLIDIR.
    'nozzle_expansion_screen.summerfield_factor',
    # BOĞAZ İSTASYONUNDA M = 1 ÖZDEŞLİĞİ: boğaz istasyonu alan dizisinin
    # argmin'idir (quasi1d.py:345) ve boğulmuş çözümde o istasyonun Mach
    # sayısı TANIMI GEREĞİ 1'dir. ÖLÇÜLDÜ: stations.area_m2[26] =
    # 0,0018621899299176496, yayımlanan throat_area ile son basamağına
    # kadar aynı; 26 indeksi örnekleyicinin ızgarasından gelir ve
    # conical/bell x eps 4..25'te değişmiyor. İm İNDEKSE SABİTLENMİŞTİR:
    # ızgara değişirse im eşleşmez ve bekçi değişikliği GÖRÜR (6 noktalı
    # 'thrust_altitude' ızgara imiyle aynı disiplin). Kardeş
    # mach[0..25] ve mach[27..41] CANLIDIR.
    'nozzle_flow_quasi1d.stations.mach[26]',
    # KENETLİ ARTIK OKSİTLEYİCİ: ox_artik = max(0, yüklenen - harcanan)
    # (hybrid_rocket_engine.py:4953-4955). Yüklenen = mdot_ox x
    # t_istenen, harcanan = mdot_ox x t_etkin; ikisi de yanıtta yayımlı
    # ve CANLI. Web erken tükenmedikçe t_etkin = t_istenen olduğundan
    # artık TAM sıfırdır ve 'oxidizer_mass_basis' bunu açıkça yazar.
    # ÖLÇÜLDÜ (kelepçe açılıyor): burn_time=200 s, initial_port_diameter
    # =0,12 m, chamber_diameter_input=170 mm -> web 13,95 s'de tükeniyor,
    # burn_time_clipped=True ve artık 366,06 kg. Yani bu sıfır,
    # HESAPLANMIŞ sıfırdır; eksik model değil.
    'oxidizer_mass_residual_kg',
    # BEYANLI TANK DOLULUK KESRİ: TANK_FILL_FRACTION_DEFAULT = 0,85
    # (hybrid_rocket_engine.py:132; :3064-3065 kendi _basis'iyle
    # yayımlanır, :4127 çalkantı bloğuna girer) — mevcut
    # 'oxidizer_tank_slosh.tank_ld_ratio' (L/D = 2,5) imiyle İKİZ gerekçe.
    'oxidizer_tank_slosh.liquid_fill_fraction',
    # ÇALKANTI IZGARASININ SKALER EKSENİ: h/R = 2 x doluluk x (L/D) =
    # 2 x 0,85 x 2,5 = 4,25 (ÖLÇÜLDÜ: yayımlanan 4,249999999999999) —
    # iki çarpan da yukarıdaki beyanlı sabitlerdir. Zaten imli olan
    # 'fill_sweep.fill_ratio[' ızgara ailesinin skaler kardeşi.
    'oxidizer_tank_slosh.slosh.fill_ratio',
    # SP-106 BOYUTSUZ ÇALKANTI KÜTLE ORANI: m_s/m = (2R/(lam1 h
    # (lam1^2 - 1))) tanh(lam1 h/R) (slosh_analysis.py:164-169) — YALNIZ
    # h/R'nin fonksiyonudur, h/R ise yukarıdaki iki beyanlı sabitten
    # türer; bu yüzden tank geometrisi oynasa da oran oynamaz.
    # ÖLÇÜLDÜ: formül yalnız h/R'den 0,1069396825822474 veriyor,
    # yayımlanan değer 0,10693968258224738 (1e-16 fark).
    # Kardeş BOYUTLU 'slosh_mass_kg' (2,104 kg) CANLIDIR ve bekçi onu
    # korumaya devam eder: sabitlik boyutsuz orandadır, kütlede değil.
    'oxidizer_tank_slosh.slosh.fill_sweep.slosh_mass_ratio[',
    'oxidizer_tank_slosh.slosh.slosh_mass_ratio',
    # KENETLİ NET EKSENEL BASMA: max(F/(2*pi*r*t) - p*r/(2t), 0)
    # (structural_analysis.py:499-517; kodda zaten "SABİT ÇIKTI BEYANI"
    # başlıklı yorumla işaretli). İki bileşen de yanıtta ayrı yayımlanır
    # (axial_compression_force_N, pressure_stabilizing_stress_MPa) ve
    # kardeş applied_axial_stress_unpressurized_MPa CANLIDIR (2,09 MPa).
    # ÖLÇÜLDÜ (kelepçe açılıyor, doğrudan _check_buckling çağrısı):
    # p=20 bar + F=500 kN -> 194,21 MPa (= 209,41 - 15,20). /calculate
    # ile ulaşılabilen bantta iç basınç çekmesi (15,2 MPa) itki basmasını
    # (2,09 MPa) daima aştığı için yaprak sıfırda duruyor.
    'buckling_analysis.applied_axial_stress_pressurized_MPa',
    # CIVATA İZİN GERİLMESİ = STANDART TABLO KAYDI: ISO 898-1:2013
    # Table 3 proof gerilmesi, sınıf 8.8 (structural_analysis.py:1264
    # varsayılan sınıf, :1395 yayım; tablonun tek tanım noktası
    # hrma/analysis/bolted_joint._bolt_class_props). Yaprak kaynağını
    # kendisi beyan eder (bolt_property_class '8.8' +
    # bolt_allowable_stress_basis 'ISO 898-1:2013 Table 3'), yani mevcut
    # 'material_properties' imiyle aynı doğa: standart kaydı, hesap değil.
    # ÖLÇÜLDÜ (bant geçişi): thrust 5 kN -> gerekli çap 8,96 mm ve
    # 580 MPa; thrust 80 kN -> 25,23 mm ve 600 MPa (d > 16 mm bandı).
    'fastener_analysis.bolt_allowable_stress_MPa',
    # DIŞA AKTARICI VARSAYILANLARI: bu üç ayar OpenRocket dosyasının
    # ÇÖZÜCÜ AYARIDIR, bu motorun bir hesabı değil
    # (openrocket_integration.py:488-513; time_step/max_altitude için kod
    # yorumu "fiziksel bir iddia değil, OpenRocket'a önerilen çözücü
    # ayarlarıdır" diyor). Beyan MAKİNE OKUR biçimdedir ve aynı yanıtta
    # durur: simulation_settings_source.<anahtar> = 'exporter_default' +
    # simulation_settings_source_labels "no input field feeds this
    # setting - check it in OpenRocket". Kullanıcının gerçekten
    # girebildiği ayarlar (launch_altitude, launch_angle, wind_*) bu
    # yoldan GEÇMEZ; onlar 'request'/'not_supplied' damgası alır ve
    # sayısal olduklarında bu bekçi tarafından ölçülmeye devam eder.
    'flight_profile.simulation_settings.launch_rod_length',
    'flight_profile.simulation_settings.max_altitude',
    'flight_profile.simulation_settings.time_step',
    # ÇÖZÜCÜ ZAMAN PENCERELERİ: COASTING_TIME_LIMIT_S = 300,0 ve
    # DESCENT_TIME_LIMIT_S = 3600,0 (trajectory_analysis.py:87 ve :95),
    # t_span üst sınırı olarak kullanılıp (:1068, :1188) aynı adla
    # yayımlanırlar (:1104, :1221). Bunlar entegrasyon PENCERESİNİN
    # beyanıdır, uçuşun bir sonucu değil; pencere bağlarsa kardeş
    # 'end_reason' bunu söyler (:1337-1341) — bu koşuda 'apogee' ve
    # 'ground', yani pencere bağlamıyor.
    'trajectory.trajectory.phases.coasting.time_limit_s',
    'trajectory.trajectory.phases.descent.time_limit_s',
) + tuple(
    # BAŞLANGIÇ KOŞULU (t = 0): çözücü y0 = [0, launch_altitude, 0, 0,
    # toplam kütle] ile başlar (trajectory_analysis.py:868) — roket
    # rampada duruyor, yani x = vx = vz = 0 ve |v| = 0. Faz dizileri
    # KENDİ YEREL SAATLERİYLE yayımlanır (her faz t_span = (0, limit) ile
    # entegre edilir: :1068, :1188), bu yüzden coasting/descent zaman
    # dizileri de 0,0'dan başlar. Mevcut 'wall_temperature_history.
    # time_s[0]' ve 'thrust_curve.time[0]' imleriyle aynı emsal.
    # İM DARLIĞININ ÖLÇÜLEN KANITI — aynı fazların ÖTEKİ [0] yaprakları
    # imlenmedi ve zaten SABİT DEĞİL: altitude[0] ve position_z[0]
    # launch_altitude girdisiyle oynuyor; coasting.position_x[0] =
    # 268,31 m, descent.velocity_x[0] = 28,25 m/s gibi faz başlangıç
    # durumları önceki fazın sonundan miras alınıyor (:1052, :1178) ve
    # canlı ölçülüyor. Yani bu ailede donan tek şey SIFIR olan başlangıç
    # koşulu ile faz saatinin sıfırlanmasıdır.
    'trajectory.trajectory%s.%s[0]' % (faz, alan)
    for faz, alanlar in (
        ('', ('time', 'position_x', 'velocity_x', 'velocity_z',
              'velocity_magnitude')),
        ('.phases.powered', ('time', 'position_x', 'velocity_x',
                             'velocity_z')),
        ('.phases.coasting', ('time',)),
        ('.phases.descent', ('time',)),
    )
    for alan in alanlar
)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def hybrid_report(client):
    """Hibrit sarsım matrisi (bir kez koşar, testler paylaşır)."""
    template_specs = inventory.field_specs_for('hybrid')
    collected = inventory.build('hybrid').collected_fields
    specs = []
    seen = set()
    for name in sorted(collected & set(template_specs)):
        payload_key = TEMPLATE_TO_PAYLOAD.get(name, name)
        if payload_key in NOT_IN_CALCULATE or payload_key in seen:
            continue
        field = template_specs[name]
        if field.kind == 'text':
            continue
        seen.add(payload_key)
        # Birimi değişen alanlarda şablon aralığı devralınmaz (bkz. PAYLOAD_RANGE)
        lo, hi = PAYLOAD_RANGE.get(
            payload_key,
            (None, None) if payload_key != name else (field.minimum,
                                                      field.maximum))
        specs.append(shake.FieldSpec(
            name=payload_key,
            kind=field.kind,
            lo=lo,
            hi=hi,
            options=tuple(field.options or ()),
            context=HYBRID_CONTEXTS.get(payload_key, {}),
        ))
    return shake.run(client, '/calculate', HYBRID_BASE, specs,
                     declared_unwired=DECLARED_UNUSED_IN_APP)


def test_shake_covers_a_meaningful_share_of_the_form(hybrid_report):
    """Ölçüm kapsamı çökerse bu dosya sessizce anlamsızlaşır.

    Kapsam düşerse 'ölü girdi yok' sonucu güven vermez: ölçülmeyen alan
    ölü olmadığı için değil, bakılmadığı için temiz görünür.
    """
    measured = (len(hybrid_report.live_inputs)
                + len(hybrid_report.dead_inputs)
                + len(hybrid_report.echo_only_inputs))
    assert measured >= 30, hybrid_report.summary()


def test_no_dead_inputs_in_hybrid(hybrid_report):
    """Sarsılan her girdi çıktının en az bir yaprağını değiştirmeli."""
    assert not hybrid_report.dead_inputs, (
        'Su girdiler /calculate cikitisinda HICBIR sey degistirmiyor '
        '(kullanici degeri giriyor, sonuca girmiyor):\n  '
        + '\n  '.join(hybrid_report.dead_inputs)
        + '\n\nYa cozucuye baglayin, ya arayuzden kaldirin, ya da '
          'gerekcesiyle bu dosyadaki uygun listeye ekleyin.')


def test_no_echo_only_inputs_in_hybrid(hybrid_report):
    """Yalnız kendi yankısını değiştiren girdi de fiilen ölüdür.

    Bir alanı sarsınca çıktıda yalnız "girdiğiniz değer şuydu" yankısı
    değişiyorsa o alan hesaba girmiyor demektir. Yankı, ölü alanı canlı
    göstermenin en kolay yoludur; bu yüzden ayrı sınıflanır.
    """
    allowed = {
        # oxidizer_phase 'gas' secilince cozucu ayni yolu kullanir; faz
        # yalniz yogunluk/Cd gerekcesini etkiler ve o da girdi yankisidir.
        'oxidizer_phase',
        # hole_pattern (14 Agu 2026 baglamasi): /calculate yanitinda deseni
        # TASIYAN tek alan injector_design.hole_pattern'dir ve bu bir
        # yankidir — TASARIMI GEREGI. Desenin yanki disi etkisi ayri uctadir:
        # cizici (visualization.py, SHOWERHEAD_PATTERNS) plaka yerlesimini
        # bu alandan okur. Performans modeli yoktur ve uydurulmaz
        # (test_hole_pattern_baglama.py bu zinciri ayrica kilitler).
        'hole_pattern',
    }
    unexpected = sorted(set(hybrid_report.echo_only_inputs) - allowed)
    assert not unexpected, (
        'Su girdiler yalnizca kendi yankilarini degistiriyor: %s' % unexpected)


def test_every_field_is_measurable(hybrid_report):
    """Ölçülemeyen alan sessizce kapsam dışı kalmamalı.

    'Sarsilamadi' ya da 'HTTP 400' diyen her alan ya refakat alanlarıyla
    ölçülebilir hale getirilmeli ya da gerekçesiyle listelenmeli — aksi
    hâlde ölçüm kapsamı sessizce daralır.
    """
    explained = {
        # Bu iki alan 0 = "otomatik" demektir ve sablonda min/max tasimaz;
        # baglam sozlugunde acik deger verilerek olculuyorlar.
        'chamber_diameter_input',
        'chamber_length_override',
    }
    unexplained = {k: v for k, v in hybrid_report.unmeasurable.items()
                   if k not in explained}
    assert not unexplained, (
        'Su alanlar olculemedi: %s' % unexplained)


def test_no_fabricated_constant_outputs(hybrid_report):
    """Hiçbir girdiden etkilenmeyen SAYISAL çıktı uydurma sabittir.

    ``strand_burner_tests: 5``, ``dimensional_accuracy_percent: 99.5`` ve
    ``$500-800`` bu sınıftandı ve üç ayrı elle süpürmeden sağ çıkmışlardı;
    hiçbiri bir hesabın sonucu değildi.

    Not: bu test yalnızca ÖLÇÜLEN girdi kümesi için anlamlıdır. Sarsılmayan
    bir girdinin etkilediği çıktı burada 'sabit' görünür; bu yüzden
    kapsam testi (yukarıda) bu testin ön koşuludur.
    """
    suspicious = [p for p in hybrid_report.constant_outputs
                  if not any(marker in p for marker in LEGITIMATE_CONSTANTS)]
    # Teşhis kancası (davranış değiştirmez): borç ayıklama turlarında tam
    # listeye ihtiyaç var, assert mesajı yalnız ilk 25'i basıyor.
    import os
    dump = os.environ.get('HRMA_DUMP_CONSTANTS')
    if dump:
        with open(dump, 'w', encoding='utf-8') as f:
            f.write('\n'.join(suspicious))
    # Ölçüm kapsamı tam olmadığı sürece bu liste boşalmaz; eşik, kapsam
    # büyüdükçe DÜŞÜRÜLMELİDİR. Yükseltmek uydurmayı gizlemektir.
    #
    # v2.6.27 borç kapanışı — eşik 330 -> 70 (ÖLÇÜLDÜ):
    #   * Yankı tekilleştirme: 372 bayrağın 372 kopyası (trajectory.
    #     motor_data + openrocket.flight_profile.motor_data, sayısal sabit
    #     olsun olmasın) kanonik motor.* yoluna indirgendi — aynı sabit üç
    #     kez sayılıyordu (bkz. shake.ECHO_CANONICAL_PREFIXES).
    #   * Kod kanıtlı dar imler (yukarıdaki v2.6.27 bloğu) beyanlı ızgara/
    #     etiket/model-sabiti ailelerini düşürdü.
    #   * Kalan 70 kalemin dökümü ve tek tek hükümleri parti kaydında;
    #     çoğunluğu 'beyanlı sabit — ime taşınabilir' (fill_sweep.
    #     slosh_mass_ratio evrensel SP-106 eğrisi, kenetli-sıfır özdeşlikleri,
    #     t=0 başlangıç koşulları, ISO tablo basamakları) + paraşüt üçlüsü
    #     GERÇEK form borcu (hibrit sayfasında alan yok; API bağlı).
    #
    # v2.6.27 yirmi beşinci parti artçısı — eşik 70 -> 59 (ÖLÇÜLDÜ, YASTIKSIZ).
    # O 70'in içindeki "gerçek form borcu" ödendi ve iki sınıflandırma
    # düzeltmesi girdi; düşüşün 11 kaleminin TAMAMI ayrı ayrı mutasyonla
    # doğrulandı (her mutasyon bu bekçiyi kırmızı yapıyor):
    #   * -9 KURTARMA AİLESİ: paraşüt üçlüsü hibrit sayfasına açıldığı ve
    #     HYBRID_CONTEXTS'e girdiği için kurtarma yaprakları artık sarsım
    #     altında KIPIRDIYOR. Düşen 9 yaprak ADIYLA (döküm farkı):
    #     trajectory.recovery.{parachute_area_m2, parachute_cd,
    #     parachute_deploy_delay_s}, aynı üçlünün trajectory.phases.descent
    #     kopyası, performance.trajectory_metrics.{parachute_area_m2,
    #     parachute_cd} ve warnings[1].params.cd. Bu 9 yaprak "uydurma
    #     sabit" değildi, ÖLÇÜLEMEYEN sabitti: kullanıcının onları
    #     oynatacak kapısı yoktu.
    #     Karşı-ölçüm: üç bağlam silinince sayı 68'e çıkar.
    #     NOT: warnings[1].params.area SABİT KALMAYA DEVAM EDİYOR ve bilerek
    #     imlenmedi — alan verilince uyarının kendisi kaybolduğu için yaprak
    #     'değişti' sayılmıyor. Sayımda kalması muhafazakâr yöndedir.
    #   * -1 BEYAN YANKISI: .inputs_not_used[0].submitted, kullanıcının
    #     gönderdiği sayının kendisidir (shake.is_declaration_echo).
    #     Karşı-ölçüm: sınıflandırma kaldırılınca 60.
    #   * -1 ÜÇÜNCÜ KOPYA: .injector_design, .motor.injector_design'ın
    #     bit-aynı kopyası (11/11 yaprak ölçüldü); tek SABİT yaprağı
    #     discharge_coefficient ikinci kez sayılıyordu.
    #     Karşı-ölçüm: önek kaldırılınca 60.
    #
    # v2.6.27 yirmi altıncı parti — eşik 59 -> 4 (ÖLÇÜLDÜ, YASTIKSIZ).
    # O 59'un TAMAMI tek tek sınıflandırıldı (döküm + kardeş alan + kaynak
    # kodu) ve 55'i dar imle kapandı. Kapananların hepsi yukarıdaki
    # v2.6.27 bloğunda kendi kod kanıtıyla ve mümkün olduğunda BANDI/
    # KELEPÇEYİ AÇAN ölçümüyle duruyor; kabaca:
    #   * 28 çalkantı: 25 noktalı SP-106 boyutsuz kütle oranı ızgarası +
    #     h/R ekseni + beyanlı doluluk kesri + skaler oran (hepsi yalnız
    #     beyanlı sabitlerin fonksiyonu; boyutlu kardeş slosh_mass_kg
    #     CANLI kaldı),
    #   * 11 yörünge başlangıç koşulu (y0 = [0, launch_altitude, 0, 0, m]
    #     ve faz-yerel saatler),
    #   *  5 tablo/bant basamağı (ISO 2768-1 x2, enjektör Cd x2, ISO 898-1
    #      cıvata) — beşi de geçiş ölçümüyle CANLI olduğu gösterildi,
    #   *  3 OpenRocket dışa aktarıcı ayarı (yanıtta 'exporter_default'
    #      damgalı),
    #   *  2 kelepçeli sıfır (artık oksitleyici, net eksenel basma) —
    #      ikisi de kelepçe açılarak sıfırdan çıkarıldı,
    #   *  6 tekil beyan/özdeşlik (boğazda M=1, ıslak istasyon sayısı,
    #      Summerfield katsayısı, manifold hedefi, iki zaman penceresi).
    # Toplam 28+11+5+3+2+6 = 55; 59 - 55 = 4.
    # GERİYE 4 KALDI ve dördü de BİLEREK imlenmedi — her biri gerçek bir
    # borcun izidir, im onları görünmez yapardı:
    #   1-2. heat_transfer_analysis'in ambient_temperature ve
    #        heat_sink_initial_temperature_K yaprakları: ikisi de
    #        'ambient_temp' GİRDİSİNİN yankısı (alanların kendi _basis
    #        metinleri bunu yazıyor) ama hibrit şablonunda ambient_temp
    #        alanı YOK (templates/index.html'de tek geçiş bile yok;
    #        app.py:1419 data.get('ambient_temp') ile API'den okuyor).
    #        Yani kullanıcının 293,15 K'yi oynatacak kapısı yok —
    #        paraşüt üçlüsünün yirmi beşinci partide kapanan borcuyla
    #        AYNI sınıf. Alan forma eklenince bu iki yaprak kendiliğinden
    #        kıpırdar ve eşik 2 düşer.
    #   3.   nozzle_flow_quasi1d.mass_flow_rel_diff: yaprağın kendi
    #        mass_flow_check_basis'i bunu "kalorik olarak kusursuz gaz ile
    #        denge c* zincirinin ÇAPRAZ KONTROLÜ, birkaç yüzde fark
    #        beklenir" diye satıyor. ÖLÇÜM bu beyanı çürütüyor: fark 55
    #        alanın hepsinde 1e-16'ya kadar AYNI (0,020408163265306) ve
    #        tam olarak 1/0,98 - 1'dir; çünkü boğaz alanı
    #        A_t = mdot x c* / (Pc x CD) ile, CD = 0,98 SABİT KODLU
    #        (hybrid_rocket_engine.py:1378) kuruluyor ve quasi-1B aynı
    #        A_t'den CD'siz ideal debiyi hesaplıyor. Yani ölçüm
    #        termokimyayı değil, o sabit CD'yi geri okuyor: totoloji.
    #        İmlemek yanlış beyanı kilitlemek olurdu.
    #   4.   trajectory.warnings[1].params.area: yirmi beşinci partinin
    #        gerekçesiyle imlenmedi — paraşüt alanı verilince uyarının
    #        KENDİSİ kaybolduğu için yaprak hiçbir sarsımda 'değişti'
    #        sayılmıyor. Sayımda kalması muhafazakâr yöndür.
    # Eşik ölçülen sayının KENDİSİDİR — yeni bir sabit eklendiği anda
    # kırmızı. (Sayım HRMA_DUMP_CONSTANTS dökümünden okunacaksa dikkat:
    # döküm son satırı sonlandırmaz, 'wc -l' bir eksik sayar.)
    #
    # v2.6.27 yirmi sekizinci parti — eşik 4 -> 8 (ÖLÇÜLDÜ, gerekçeli):
    # hibrit chug çevrimi bağlanınca (combustion_stability.chug_loop) dört
    # YENİ sabit yaprak classical_rule_cross_check'ten geldi, ADIYLA
    # (HRMA_DUMP_CONSTANTS dökümünden, ölçüldü):
    #   * rule_min_ratio = 0,15 ve rule_recommended_ratio = 0,20 — klasik
    #     oran kuralının YAYIMLANMIŞ eşikleri (acoustic_modes tek kaynağı,
    #     künye CHUG_THRESHOLD_SOURCE: Sutton & Biblarz RPE 9. baskı
    #     %15-25 bandı). Eşik sabiti eşik sabitidir: girdiyle oynamaması
    #     kusur değil sözleşmedir.
    #   * model_neutral_tau_over_tau_c_at_rule_min ve
    #     model_neutral_tau_over_tau_c_at_rule_recommended — nötr eğrinin
    #     TAM O eşiklerdeki kapalı-form değerleri; girdileri yukarıdaki iki
    #     sabit olduğu için tanım gereği sabittirler. Çekirdek assess_chug
    #     sözlüğü AYNEN taşınır (yeniden adlandırma yasağı).
    # Dördü de sıvı motorun /calculate_liquid çıktısında AYNI adlarla zaten
    # yayımlanıyor (parti 27 F2b-2); hibritte görünmeleri yeni uydurma
    # değil, aynı beyanlı ailenin ikinci motora bağlanması. İm (marker)
    # eklenMEDİ: ime taşımak alt-sınır bekçisini köreltirdi; sayımda
    # kalmaları muhafazakâr yöndür.
    assert len(suspicious) <= 8, (
        'Sabit sayisal cikti yapragi beklenenden fazla (%d). Yeni uydurma '
        'sabit eklenmis olabilir. Ilk 25:\n  %s'
        % (len(suspicious), '\n  '.join(suspicious[:25])))
    # YASTIKSIZ EŞİK İKİ YÖNLÜ OLMAK ZORUNDA (v2.6.27 yirmi altıncı parti).
    # Üst sınır yalnız YENİ uydurmayı yakalar; borcu BEYAZ LİSTEYE ALARAK
    # gizlemeyi yakalamaz — bu tur ölçüldü: gerçek borç yapraklarından biri
    # (mass_flow_rel_diff) LEGITIMATE_CONSTANTS'a eklenince sayı 4 -> 3
    # düşüyor ve tek yönlü eşik SESSİZ kalıyordu. Yani "im ekleyerek borç
    # kapatma" tam da bu dosyanın en çok korkması gereken hamleydi ve
    # mekanik bir bekçisi yoktu. Alt sınır onu kırmızıya çevirir:
    #   * borç gerçekten ödendiyse (ör. ambient_temp forma eklenirse)
    #     eşik AYNI commit'te bu satırda düşürülür ve gerekçesi yazılır;
    #   * bir yaprak sessizce imlendiyse test bunu söyler.
    # Eşiğin iki yanı da ÖLÇÜLEN sayıdır, tahmin değil.
    assert len(suspicious) >= 8, (
        'Sabit yaprak sayisi esigin ALTINA dustu (%d < 8). Bu iyi haber '
        'olabilir (borc odendi) ama sessiz kalamaz: ya urun kodunda bir '
        'girdi baglandi -> esigi bu satirda olculen yeni degere indirin ve '
        'gerekcesini yazin; ya da bir borc yapragi LEGITIMATE_CONSTANTS ile '
        'ortuldu -> imi geri alin. Kalan liste:\n  %s'
        % (len(suspicious), '\n  '.join(suspicious)))


def test_motor_echo_copies_never_diverge(hybrid_report):
    """motor bloğunun yankı kopyaları BİT-AYNI kalmak zorundadır.

    /calculate yanıtı motor.* bloğunu iki yerde daha taşır:
    trajectory.motor_data ve openrocket.flight_profile.motor_data.
    P-5 denetimi bunları "bit-aynı kopya" diye belgelemişti; bu bekçi o
    sözleşmeyi ÖLÇER (shake.run kopya geçişi): tabanda bit-aynılık + sarsım
    altında birlikte değişme. Ayrışan kopya, uçuş simülasyonunun BAYAT ya da
    VARSAYILAN motor verisiyle beslenmesi demektir — sahte-roket sınıfı.
    Ayrışma varsa tekilleştirme de o yaprak için iptal edilir (sabit sayımı
    kopyayı adıyla göstermeye devam eder), yani bu bekçi kırmızıyken sabit
    bekçisi sessiz kalamaz.
    """
    assert not hybrid_report.yanki_ayristi, (
        'Su yanki yapraklari kanonik motor.* yapragindan AYRISTI '
        '(bayat/varsayilan kopya suphesi):\n  '
        + '\n  '.join(hybrid_report.yanki_ayristi[:40]))
    # Tekilleştirmenin gerçekten iş yaptığı da ölçülür: kopya sözleşmesi
    # sağlamken sayaç sıfırsa ya kopyalar kayboldu ya indirgeme koptu.
    assert hybrid_report.echo_constant_dedup > 0, hybrid_report.summary()


def test_whitelist_markers_stay_narrow(hybrid_report):
    """Tek im, sabit listeden en çok 30 yaprak yutabilir.

    Geniş im ('oxidizer_tank_slosh' gibi blok adı) bloğa SONRADAN eklenecek
    uydurma sabiti de örter — beyaz listeyi genişletmek uydurmayı gizlemenin
    en kolay yoludur ve bunu talimat değil ölçüm durdurur.

    Tavan tautoloji değildir, ÖLÇÜMDEN türedi: bu koşuda en geniş MEŞRU
    imler 25'er yaprak yutuyor (fill_sweep.fill_ratio[ ve yirmi altıncı
    partide eklenen fill_sweep.slosh_mass_ratio[ — aynı 25 noktalı beyanlı
    süpürme ızgarasının iki sütunu), ardından acoustic_modes.modes 22 ve
    altitude_performance 18; gerisi <= 6. Tavan 30 = en büyük meşru aile
    + küçük pay. Karşı-ölçüm: kasıtlı geniş im 'oxidizer_tank_slosh' aynı
    koşuda 65 yaprak yutuyor ve burada KIRMIZI verir (mutasyonla kanıtlandı).
    Yeni bir ızgara ailesi imlenecekse ya alan düzeyinde imlenir ya da bu
    tavan ölçümüyle birlikte güncellenir — sessizce genişletilemez.

    v2.6.27 yirmi altıncı parti notu: eklenen 31 imin 30'u TEK yaprak
    yutuyor (ölçüldü), yani bu tavan onlar için bağlayıcı değil; tavanı
    zorlayan tek aile yukarıdaki süpürme ızgarasıdır (25).
    """
    emilim = {m: sum(1 for p in hybrid_report.constant_outputs if m in p)
              for m in LEGITIMATE_CONSTANTS}
    genis = {m: n for m, n in emilim.items() if n > 30}
    assert not genis, (
        'Su imler tek baslarina 30\'dan fazla sabit yapragi yutuyor '
        '(blok-genel im suphesi, dar imlere bolun): %s' % genis)


# ---------------------------------------------------------------------------
# Katman B'nin ilk koşusunda bulduğu iki yayın hatasının gerileme bekçileri
# ---------------------------------------------------------------------------

def test_impingement_without_angle_does_not_crash(client):
    """``impingement_angle`` boş gelince /calculate çökmemeli.

    Yayınlanmış sürümde ``IMPINGEMENT_HALF_ANGLE_DEG`` app.py'de
    kullanılıyor ama import edilmiyordu; alanı temizleyen kullanıcı ya da
    bu anahtarı göndermeyen API çağrısı NameError ile HTTP 500 alıyordu.
    """
    payload = dict(HYBRID_BASE, injector_type='impingement',
                   element_pairs=8, orifice_diameter=1.0)
    payload.pop('target_velocity', None)
    resp = client.post('/calculate', json=payload, headers=shake.HEADERS)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]


def test_injector_detail_never_fabricates_a_hole_plan(client):
    """Devre modeli boyutlandıramazsa delik planı UYDURULMAZ.

    Eski yedek yol her hatada ``n_orifices = 12`` ("typical showerhead
    pattern") ve ``Cd = 0.65`` üretiyor, sonucu kullanıcının seçtiği
    enjektör tipiyle etiketliyordu: 'coaxial' yazan 12 delikli bir
    showerhead. Uyarı yalnız sunucu günlüğüne gidiyordu.
    """
    payload = dict(HYBRID_BASE, injector_type='coaxial',
                   inner_diameter=5, outer_annulus_diameter=10)
    resp = client.post('/calculate', json=payload, headers=shake.HEADERS)
    assert resp.status_code == 200
    motor = resp.get_json()['motor']
    detail = motor['injector_design']
    assert detail['status'] == 'not_analyzed'
    # Uydurulan alanların hiçbiri bulunmamalı
    for fabricated in ('number_of_orifices', 'orifice_diameter_mm',
                       'manifold_diameter_mm', 'discharge_coefficient'):
        assert fabricated not in detail, fabricated
    # ve kullanıcı bunu EKRANDA görmeli
    codes = {w.get('code') for w in (motor.get('design_warnings') or [])
             if isinstance(w, dict)}
    assert 'warn.hybrid.injector_detail_unavailable' in codes


@pytest.mark.parametrize('ui_type,expect_detail', [
    ('showerhead', True),
    ('pintle', True),
    ('swirl', True),
    ('impingement', True),   # v2.6.26: like_impinging'e eşlendi
    ('coaxial', False),      # devre modeli hibritte koaksiyel desteklemiyor
])
def test_injector_type_vocabulary_is_mapped(client, ui_type, expect_detail):
    """Arayüz sözcüğü ile modül sözcüğü arasındaki eşleme çürümemeli.

    Eşleme kopunca çağrı ValueError atar ve motor yedek yola düşer; eskiden
    o yedek uydurma üretiyordu, şimdi 'not_analyzed' diyor. İki durumda da
    kullanıcı seçtiği tipin gerçek analizini KAYBEDER, bu yüzden eşleme
    bekçisi ayrıca gerekir.
    """
    extras = {
        'showerhead': {'target_velocity': 30},
        'pintle': {'outer_diameter': 50, 'pintle_diameter': 25},
        'swirl': {'n_slots': 6},
        'impingement': {'element_pairs': 8, 'impingement_angle': 60},
        'coaxial': {'inner_diameter': 5, 'outer_annulus_diameter': 10},
    }[ui_type]
    payload = dict(HYBRID_BASE, injector_type=ui_type, **extras)
    resp = client.post('/calculate', json=payload, headers=shake.HEADERS)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    body = resp.get_json()
    detail = body['motor']['injector_design']
    if expect_detail:
        assert detail.get('status') != 'not_analyzed', detail
        assert detail['number_of_orifices'] > 0
    else:
        assert detail['status'] == 'not_analyzed'
    # Kullanıcının seçtiği ad her durumda korunur (iç sözcük sızmamalı)
    assert detail['injector_type'] == ui_type
    # Enjektörün kendisi her tipte boyutlandırılır — kullanıcı sonuçsuz kalmaz
    assert body['injector']['type'] == ui_type
