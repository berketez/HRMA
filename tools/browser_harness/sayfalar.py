"""Gezilecek sayfaların tanımı — hangi düğme, hangi bekleme, hangi tuval.

Seçiciler ``onclick`` özniteliğine bakar, görünen METNE değil: arayüz
çevrilebilir (``data-i18n``), metne bağlanan bir iskele dil değişince
sessizce kör olur. ``onclick="calculateSolid()"`` ise sözlükten bağımsızdır.

Sayfa adları ``tests/support/inventory.py::PAGES`` ile AYNI kümedir; bir
sayfa eklenip biri unutulursa ``tests/test_browser_harness.py`` yakalar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

from tools.browser_harness import esikler


@dataclass(frozen=True)
class FeaPaneli:
    """Bir FEA panelinin gezinti tarifi — koşum düğmesi, çizimler, rozetler.

    Panel elemanları JS ile üretiliyor (``fea_panel.js`` /
    ``thermal_fea_panel.js``), yani şablonda aranacak bir ``onclick`` yok;
    kimlikler (``id``) tek dayanaktır ve sözlükten bağımsızdır.

    ``api_adi`` panelin ``window`` üzerine astığı nesnedir
    (``window.FeaPanel.payload`` vb.). Hüküm ÇİZİMİN ve YÜKÜN varlığına
    bakar; "düğmeye basıldı" tek başına yeterli sayılmaz.
    """

    ad: str
    #: Panelin kabı — sayfada var mı, görünür mü.
    panel_kimligi: str
    #: Koşumu başlatan düğme (CSS seçici).
    kosum_secicisi: str
    #: Koşum sürerken görünen "meşgul" göstergesi (yüzde YOK, nabız var).
    mesgul_kimligi: str
    #: Koşum başarısızsa gerekçenin basıldığı çip kabı.
    cip_kimligi: str
    #: Rozetlerin basıldığı kap (``[data-badge]`` kutuları burada).
    rozet_kimligi: str
    #: ``window`` üzerindeki panel nesnesinin adı; ``payload`` alanı okunur.
    api_adi: str
    #: Koşum başarılıysa EKRANDA olması beklenen çizim kaplarının kimlikleri.
    cizim_kimlikleri: Tuple[str, ...]
    #: Rozetlerde aranan imzalar (``esikler.ROZET_IMZALARI`` anahtarları).
    beklenen_imzalar: Tuple[str, ...] = ()
    #: Rozetlerde GÖRÜLMEMESİ gereken imzalar (geri gelen kusur bekçisi).
    yasak_imzalar: Tuple[str, ...] = ()
    #: Koşumun bitmesi için üst sınır (ms).
    kosum_zaman_asimi_ms: int = esikler.FEA_KOSUM_ZAMAN_ASIMI_MS
    notlar: str = ''


#: ``/hybrid`` + ``/liquid`` — eksenel simetrik cidar yapısal FEA'sı
#: (fea_panel.js:453; sıvıya 2026-08-15'te bağlandı).
#: Dört çizim de koşum başarılıyken çizilir: gerilme alanı, emniyet katsayısı
#: alanı, eleman kalitesi haritası ve yakınsama geçmişi. Biri çizilmiyorsa
#: sebebi ya eksik malzeme kaydıdır (emniyet katsayısı) ya da tek turda
#: bitmiş bir yakınsamadır (geçmiş grafiği ≥2 tur ister) — ikisi de rapora
#: yazılır, sessizce geçilmez.
YAPISAL_FEA = FeaPaneli(
    ad='yapisal',
    panel_kimligi='feaPanel',
    kosum_secicisi='#fea_run',
    mesgul_kimligi='fea_busy',
    cip_kimligi='fea_chip',
    rozet_kimligi='fea_badges',
    api_adi='FeaPanel',
    cizim_kimlikleri=('fea_plot_vm', 'fea_plot_sf', 'fea_plot_quality',
                      'fea_plot_conv'),
    beklenen_imzalar=('mesh_bozulmasi', 'uzamis_elemanlar', 'sf_hukmu'),
    yasak_imzalar=('birlesik_kalite_alarmi',),
    notlar=('advanced.html:827 — FeaPanel.init(anchorId: trajectoryPanel); '
            'liquid.html — FeaPanel.init(anchorId: analysis-dock-anchor). '
            'Kimlikler panel JS tarafından üretildiği için iki sayfada da '
            'aynıdır.'),
)

#: ``/hybrid`` — geçici cidar sıcaklık alanı (thermal_fea_panel.js:426).
#: Panel ``#feaPanel``in hemen ALTINA kurulur. Başlangıç/ortam sıcaklığı
#: alanı 293,15 K ön-dolu gelir; tur ona DOKUNMAZ — panelin varsayılanıyla
#: koşmak, kullanıcının gördüğü yolu denetlemektir.
TERMAL_FEA = FeaPaneli(
    ad='termal',
    panel_kimligi='thermalFeaPanel',
    kosum_secicisi='#fea_t_run',
    mesgul_kimligi='fea_t_busy',
    cip_kimligi='fea_t_chip',
    rozet_kimligi='fea_t_badges',
    api_adi='ThermalFeaPanel',
    cizim_kimlikleri=('fea_t_plot_field', 'fea_t_plot_inner',
                      'fea_t_plot_hist'),
    beklenen_imzalar=('tepe_cidar_sicakligi', 'termal_sinir_hukmu'),
    kosum_zaman_asimi_ms=esikler.FEA_TERMAL_KOSUM_ZAMAN_ASIMI_MS,
    notlar='advanced.html:837 — ThermalFeaPanel.init(anchorId: feaPanel).',
)

#: ``/solid`` — tane kesitinin düzlemsel (plane-strain) FEA'sı
#: (fea_panel.js:1255). Kabul ölçütü tepe von Mises DEĞİL port lif
#: gerinimidir; rozet imzası bunu ekranda arar.
TANE_FEA = FeaPaneli(
    ad='tane',
    panel_kimligi='grainFeaPanel',
    kosum_secicisi='#grainfea_run',
    mesgul_kimligi='grainfea_busy',
    cip_kimligi='grainfea_chip',
    rozet_kimligi='grainfea_badges',
    api_adi='GrainFeaPanel',
    cizim_kimlikleri=('grainfea_plot_vm', 'grainfea_plot_bore',
                      'grainfea_plot_conv'),
    beklenen_imzalar=('kabul_olcutu', 'mesh_bozulmasi',
                      'tane_gerinim_marji_hukmu'),
    yasak_imzalar=('birlesik_kalite_alarmi',),
    notlar='solid.html:5956 — GrainFeaPanel.init(anchorId: trajectoryPanel).',
)


@dataclass(frozen=True)
class MerkezKiracisi:
    """Analiz Merkezi'ne kayıtlı bir analizin (kiracının) gezinti tarifi.

    FEA panellerinden farkı: kiracının kendi paneli, kendi düğmesi ve kendi
    rozet kabı YOKTUR. Merkez tek bir koşum kartı (``#ac_run``) ve tek bir
    görüntüleyici kabı (``#ac_view_root``) sunar; kiracı oraya çizer. Bu
    yüzden tarif "hangi satır seçilecek" + "kabın içinde ne aranacak"
    üstünedir.

    ``cizim_onekleri``: kap kimlikleri koşum sayacıyla değişiyor
    (``cfd_wall_1``, ``cfd_wall_2``, …), o yüzden TAM kimlik yazılamaz —
    kaplar ``cizim_secicisi`` ile toplanır, ÖNEKLE eşleştirilir. Önek
    ürünün kimlik ürettiği tek yere bağlıdır (cfd_panel.js:1135-1137).
    """

    ad: str
    #: Merkez'in satır anahtarı: ``componentId.analysisId``.
    satir_anahtari: str
    #: Satır düğmesinin CSS seçicisi (``#ac_row_<componentId>_<analysisId>``).
    satir_secicisi: str
    #: Görüntüleyici kabında çizim kaplarını toplayan seçici.
    cizim_secicisi: str
    #: Beklenen çizimlerin kimlik önekleri (her önekten EN AZ bir kap).
    cizim_onekleri: Tuple[str, ...]
    #: Rozetleri toplayan seçici (renk sınıfı özniteliğin DEĞERİDİR).
    rozet_secicisi: str
    #: Rozet renk sınıfını taşıyan öznitelik adı.
    rozet_ozniteligi: str
    #: HER koşumda ekranda olması beklenen imzalar (fizikten bağımsız).
    beklenen_imzalar: Tuple[str, ...] = ()
    #: Ekranda GÖRÜLMEMESİ gereken imzalar (emekli sözleşme bekçisi).
    yasak_imzalar: Tuple[str, ...] = ()
    #: Nötr renkte kalması gereken rozetler (eşiksiz sayı → renksiz beyan).
    notr_imzalar: Tuple[str, ...] = ()
    #: Koşumun bitmesi için üst sınır (ms).
    kosum_zaman_asimi_ms: int = esikler.MERKEZ_KOSUM_ZAMAN_ASIMI_MS
    #: ÖH D23 / P10B3-03 — YÜKÜN NEREDE DURDUĞU. Merkez'in geçmiş kaydında
    #: yanıt ``son.data`` altındadır; CFD kiracısı onu bir alt anahtara
    #: (``son.data.cfd``) sarar, kararlılık kiracıları SARMAZ (ölçüldü,
    #: 4 Eylül 2026 canlı sondası). Boş dize = ``son.data``'nın kendisi.
    #: Bu alan olmadan ölçüm gövdesi tek bir kiracıya gömülü kalıyordu.
    yuk_anahtari: str = ''
    #: Yükten okunacak alanlar: ``(ad, noktalı_yol, dönüşüm)``.
    #:
    #: Dönüşümler (``tur.JS_MERKEZ_KIRACI`` uygular):
    #:   ``deger``      — ham değer; yol yoksa ``null``
    #:   ``dolu_deger`` — ham değer ama boş/0/'' ise ``null`` (eski ``|| null``)
    #:   ``mantiksal``  — SADECE gerçek bool; başka her şey ``null``
    #:                    (FAIL-CLOSED: eksik alan "false" sayılmaz)
    #:   ``bool``       — ``!!v`` (varlık bayrağı)
    #:   ``uzunluk``    — dizi uzunluğu; dizi değilse 0
    #:
    #: Boş demet = yük okunmaz (kiracının yükü henüz ölçülmemiştir).
    yuk_alanlari: Tuple[Tuple[str, str, str], ...] = ()
    notlar: str = ''


#: Merkez'in İLK canlı kiracısı: lüle iç akışı × CFD
#: (panels/cfd_panel.js — POST /api/cfd/nozzle).
#:
#: Tur bu kiracıyı sayfa başına BİR kez koşturur ve alanlara DOKUNMAZ:
#: çözünürlük varsayılanı 'coarse'tur (cfd_panel.js SPEC.fields), sayısal
#: alanlar motorun kendi sonucundan önerilir. Kullanıcının gördüğü yol budur.
#:
#: Beklenen imzalar BİLEREK fizikten bağımsız seçildi: koşunun yakınsayıp
#: yakınsamadığı, akışın ayrılıp ayrılmadığı tasarım noktasının fiziğidir —
#: turun ölçtüğü şey o beyanların EKRANDA olup olmadığıdır. Fizik bağımlı iki
#: imza (bütçe uyarısı, şüpheli hüküm) yanıtın kendi alanlarına bakılarak
#: KOŞULLU aranır (bkz. denetimler.merkez_rozet_denetimi).
CFD_KIRACISI = MerkezKiracisi(
    ad='cfd',
    satir_anahtari='nozzle_flow.cfd',
    satir_secicisi='#ac_row_nozzle_flow_cfd',
    cizim_secicisi='[data-cfd-plot]',
    cizim_onekleri=('cfd_wall_', 'cfd_field_', 'cfd_res_'),
    rozet_secicisi='[data-cfd-badge]',
    rozet_ozniteligi='data-cfd-badge',
    # ÖH D21 / P17B1-14 — 'cfd_viskozsuz_beyani' EKLENDİ. Canlı turda
    # (4 Eylül 2026) üç sayfanın üçünde de basılıyordu, beklenen listede
    # yoktu: fixture 9 rozette kilitliyken ürün 10 basıyordu ve eksik olan
    # tam da modelin kapsam sınırı beyanıydı.
    #
    # ÖH D26 / P17B1-14 (Fable ŞARTI) — İMZA BU LİSTEDEN ÇIKTI, çünkü
    # KOŞULLUDUR. D21'de koşulsuz eklenmişti; ürün onu yalnız
    # `viscous.enabled` yanlışken basar (cfd_panel.js::viscousBadgesHtml),
    # viskoz koşumda yerine `cfd_viskoz_kipi` basar. Koşulsuz beklemek iki
    # yönden de yanlış hüküm üretiyordu (ölçüm once_viskoz.json):
    #   A) viskoz koşumda INVISCID basılı  -> denetim YEŞİL (yalancı yeşil;
    #      ürünün en ağır beyanı tersine dönmüş olurdu, kimse görmezdi)
    #   B) viskoz koşumda VISCOUS basılı   -> denetim KIRMIZI (yalancı
    #      kırmızı; harness viskoz yapılandırmada hiç koşturulamazdı)
    # Çift artık `denetimler.merkez_rozet_denetimi` içindeki KOŞULLU BEYAN
    # kuralıyla, yükün `viscous_enabled` alanına bakılarak seçilir.
    beklenen_imzalar=('cfd_yakinsama_hukmu', 'cfd_ayrilma_hukmu',
                      'cfd_kutle_artigi', 'cfd_enerji_artigi',
                      'cfd_cekirdek', 'cfd_sok_sensoru',
                      'cfd_sinirlayici', 'cfd_sure'),
    yasak_imzalar=('cfd_bayat_giris_uyarisi', 'cfd_bayat_mach_esigi'),
    notr_imzalar=('cfd_kutle_artigi', 'cfd_enerji_artigi'),
    # ÖH D23 / P10B3-03 — yük okuma listesi tur.py'nin JS gövdesinden BURAYA
    # taşındı (davranış birebir aynı; alanlar ve dönüşümler eski gövdenin
    # aynası). Böylece "hangi kiracıdan ne okunuyor" tek yerde durur ve
    # ikinci bir kiracı eklemek JS düzenlemeyi gerektirmez.
    yuk_anahtari='cfd',
    yuk_alanlari=(
        ('converged', 'converged', 'mantiksal'),
        ('iterations', 'iterations', 'deger'),
        ('kernel', 'kernel_backend', 'dolu_deger'),
        ('judgment_confidence', 'separation.judgment_confidence', 'dolu_deger'),
        ('separated', 'separation.separated', 'mantiksal'),
        ('bridge_refused', 'separation.bridge_refused', 'bool'),
        ('budget_advisory', 'inlet_conditioning.budget_advisory', 'bool'),
        ('budget_advisory_reasons', 'inlet_conditioning.budget_advisory_reasons',
         'dolu_deger'),
        ('contraction_ratio', 'inlet_conditioning.contraction_ratio', 'deger'),
        ('alan_bloklu', 'field', 'bool'),
        ('kalinti_noktalari', 'residual_history.iteration', 'uzunluk'),
        ('resolution', 'inputs.resolution', 'dolu_deger'),
        # ÖH D26 / P17B1-14 (Fable ŞARTI) — viskoz beyanın KOŞULU. Ürünün
        # kendi alanı (`cfd.viscous.enabled`) okunur; harness hangi rozetin
        # beklendiğine bu alandan karar verir. Canlı ölçüm GEREKMEZ: koşul
        # ürünün yayımladığı yükün içindedir. `turbulence`/`wall_thermal`
        # rozetin METNİNİ üretir (badgeViscousMode {turb}/{wall}), o yüzden
        # onlar da okunur — beyanın içi boş çıkarsa görülebilsin.
        ('viscous_enabled', 'viscous.enabled', 'bool'),
        ('viscous_turbulence', 'viscous.turbulence', 'dolu_deger'),
        ('viscous_wall_thermal', 'viscous.wall_thermal', 'dolu_deger'),
    ),
    notlar=('analysis_center.js domKey: componentId + "_" + analysisId; '
            'çizim kimlikleri cfd_panel.js:1135-1137 (drawSeq ile artar).'),
)


#: ÖH D23 / altyapi — defter P10B3-03 + P17B1-15.
#:
#: ÖLÇÜLDÜ (a2/once.json, taban ef527ae): Merkez'de canlı READY ölçülen
#: dört kiracıdan tur YALNIZ CFD'yi koşturuyordu. Aşağıdaki iki kiracı
#: 4 Eylül 2026 canlı sondasında (sistem Chrome kanalı, /hybrid; kayıt
#: ``docs/scofield/raw/OH/D22/altyapi/a1/canli_kiraci_olcumu.json``)
#: GERÇEKTEN koşturuldu; satır seçicisi, çizim kimlikleri, rozet metinleri
#: ve yük anahtarları o ölçümden alındı — hiçbiri tahmin değildir.
ACOUSTIC_MODES_KIRACISI = MerkezKiracisi(
    ad='acoustic_modes',
    satir_anahtari='chamber_acoustics.acoustic_modes',
    satir_secicisi='#ac_row_chamber_acoustics_acoustic_modes',
    cizim_secicisi='[data-stab-plot]',
    # Ölçülen kimlikler: stab_map_1 (mod haritası) ve stab_bars_1 (mod başına
    # sönüm bütçesi). Sayaç koşumla arttığı için ÖNEK eşleşmesi kullanılır.
    cizim_onekleri=('stab_map_', 'stab_bars_'),
    rozet_secicisi='[data-stab-badge]',
    rozet_ozniteligi='data-stab-badge',
    # Üçü de HER koşumda basılır (fizikten bağımsız): iki sayı beyanı ve
    # yolun kapsam sınırı.
    beklenen_imzalar=('kararlilik_nozul_sonumu', 'kararlilik_toplam_kayip',
                      'kararlilik_hukum_yok'),
    # Bu yol bir kararlılık HÜKMÜ yayımlamaz; sönüm sayıları eşiksizdir,
    # dolayısıyla kabul rengi (yeşil) alamazlar.
    notr_imzalar=('kararlilik_nozul_sonumu', 'kararlilik_toplam_kayip'),
    yuk_anahtari='',
    yuk_alanlari=(
        ('status', 'status', 'dolu_deger'),
        ('mode', 'mode', 'dolu_deger'),
        ('nozul_sonumu_1_s', 'nozzle.damping_1_s', 'deger'),
        ('nozul_dayanagi', 'nozzle.basis', 'dolu_deger'),
        ('toplam_kayip_1_s', 'budget.total_loss_1_s', 'deger'),
        ('toplam_sonum_1_s', 'budget.total_damping_1_s', 'deger'),
        ('butce_terim_sayisi', 'budget.terms', 'uzunluk'),
        ('modellenmeyen_sayisi', 'budget.not_modelled', 'uzunluk'),
        ('yanlilik_dayanagi', 'budget.bias_basis', 'dolu_deger'),
    ),
    notlar=('stability_panel.js SPEC_ACOUSTIC; analysis_center.js:233 '
            "motorTypes ['hybrid','solid','liquid']. Canlı ölçümde /hybrid'de "
            'READY ve koşum başarılı (veri anahtarları: budget, mode, '
            'nozzle, status).'),
)

COMBUSTION_STABILITY_KIRACISI = MerkezKiracisi(
    ad='combustion_stability',
    satir_anahtari='chamber_acoustics.combustion_stability',
    satir_secicisi='#ac_row_chamber_acoustics_combustion_stability',
    cizim_secicisi='[data-stab-plot]',
    # Ölçülen kimlikler: stab_neutral_2 (nötr eğri + çalışma noktası) ve
    # stab_locus_2 (baskın kök yer eğrisi).
    cizim_onekleri=('stab_neutral_', 'stab_locus_'),
    rozet_secicisi='[data-stab-badge]',
    rozet_ozniteligi='data-stab-badge',
    # YALNIZ kapsam beyanı beklenir. Hüküm rozeti ("STABLE — feed-coupled
    # chug …") BİLEREK dışarıda: kampanya bu ailenin hükmünü TERS ölçtü
    # (P17B1-15); ölçülmemiş bir hükmü bekçiye yazmak onu sabitlemek olur.
    beklenen_imzalar=('kararlilik_besleme_ataleti',),
    yuk_anahtari='',
    yuk_alanlari=(
        ('status', 'status', 'dolu_deger'),
        ('mode', 'mode', 'dolu_deger'),
        ('model', 'assessment.model', 'dolu_deger'),
        ('verdict', 'assessment.verdict', 'dolu_deger'),
        ('inertance_included', 'assessment.inertance_included', 'mantiksal'),
        ('unconditionally_stable', 'assessment.unconditionally_stable',
         'mantiksal'),
        ('dp_ratio_j', 'assessment.dp_ratio_j', 'deger'),
        ('tau_over_tau_c', 'assessment.tau_over_tau_c', 'deger'),
        ('growth_rate_1_s', 'assessment.growth_rate_1_s', 'deger'),
        ('varsayim_sayisi', 'assessment.assumptions', 'uzunluk'),
        ('modellenmeyen_sayisi', 'assessment.not_modelled', 'uzunluk'),
        ('notr_egri_var', 'neutral_curve', 'bool'),
        ('kok_egrisi_var', 'root_locus', 'bool'),
    ),
    notlar=('stability_panel.js SPEC_CHUG; canlı ölçümde /hybrid\'de READY, '
            "hüküm anahtarı 'panel.stab.verdictScoped' (veri anahtarları: "
            'assessment, mode, neutral_curve, operating_point, root_locus, '
            'status).'),
)


@dataclass(frozen=True)
class Sayfa:
    """Tek bir sayfanın gezinti tarifi."""

    ad: str
    yol: str
    #: Hesabı tetikleyen düğme (CSS seçici).
    hesapla_secici: str
    #: Hesabın BİTTİĞİNİ söyleyen sayfa içi koşul (JS ifadesi, bool döner).
    #: Ekranda "bir şeyler belirdi" değil, sayfanın kendi sonuç nesnesinin
    #: dolduğu sorulur — yükleme animasyonu hükmü yanıltmasın.
    sonuc_kosulu: str
    #: 3B sahne kendiliğinden kurulmuyorsa basılacak düğmeler. Sırayla
    #: denenir ve YALNIZ sahne henüz kurulmamışsa tıklanır.
    viz_acma_secicileri: Tuple[str, ...] = ()
    #: Sahnenin kurulduğu kabın kimliği — yalnız insanın raporu okuması
    #: için; ölçüm ``MotorViz3D.get()`` üzerinden yapılır.
    viz_kap_kimligi: str = ''
    notlar: str = ''
    #: Bu sayfada ölçülmesi beklenmeyen denetimler (ad kümesi). Şu an boş:
    #: üç sayfanın üçü de 3B sahne ve egzoz gösterdiğini iddia ediyor.
    beklenmeyen_denetimler: Tuple[str, ...] = field(default_factory=tuple)
    #: Bu sayfada koşturulup denetlenecek FEA panelleri. Üç sayfanın üçünde
    #: de en az bir panel var (sıvıdaki yapısal panel 2026-08-15'te
    #: bağlandı; köşe tekilliği borcu AÇIK — gerekçesi ve ölçülen sayıları
    #: ``'liquid'`` girdisinin yanındaki notta). Boş liste "denetlenmedi"
    #: değil "denetlenecek panel yok" demek olurdu; bugün öyle bir sayfa
    #: kalmadı.
    fea_panelleri: Tuple[FeaPaneli, ...] = field(default_factory=tuple)
    #: Sayfada Analiz Merkezi kuruluyor mu (``AnalysisCenter.init``)? Üç
    #: sayfanın üçünde de kuruluyor (advanced.html:889, solid.html:6077,
    #: liquid.html:6791 — ölçüldü). Kurulmayan bir sayfada çerçeve denetimi
    #: ÜRETİLMEZ; hayalet denetim "kaldı" demekten daha kötüdür, çünkü
    #: kusuru olmayan bir sayfayı kırmızıya boyar.
    merkez_var: bool = False
    #: Merkez'de koşturulup denetlenecek kiracılar.
    merkez_kiracilari: Tuple[MerkezKiracisi, ...] = field(default_factory=tuple)
    #: Sayfanın HESAP akışı var mı? ÖH D21 / defter P17B1-16: turun
    #: açmadığı üç sayfanın (``/``, ``/formulas``, ``/launch-site``)
    #: üçünde de "Hesapla" düğmesi, 3B sahne, FEA paneli ve Analiz Merkezi
    #: YOKTUR. ``False`` iken tur hesabı, sahneyi, yanmayı, FEA'yı ve
    #: Merkez'i ATLAR; geriye kullanıcının o sayfada gerçekten maruz
    #: kaldığı dört ölçüm kalır: konsol hatası, ekrana sızan iç değer
    #: (``[object Object]``/NaN), yerleşim taşması/örtüşmesi ve tam sayfa
    #: görüntüsünün SAHTE olup olmadığı. Hayalet denetim üretilmez:
    #: 3B tuvali olmayan bir sayfayı "tuval boş" diye kırmızıya boyamak,
    #: kusuru olmayan sayfayı suçlamaktır.
    hesap_var: bool = True
    #: Sayfada HESAP AKIŞINDAN BAĞIMSIZ bir çizim tuvali var mı, varsa
    #: hangisi? ÖH D27 / OH-D25-02(a): ``hesap_var=False`` dalı tuval
    #: ölçümünü TOPTAN atlıyordu ve gerekçesi "sayfada 3B sahne yok" idi.
    #: ``/launch-site`` için bu gerekçe YANLIŞ ölçüldü (ham kanıt
    #: ``docs/scofield/raw/OH/D27/altyapi/a1/once_canli.json``, sistem
    #: Chrome 152): sayfada ``#ls-globe`` kabının içinde 1600×946 piksellik
    #: canlı bir WebGL tuvali var (``window.launchGlobe`` kuruluyor), yani
    #: kullanıcının o sayfada gördüğü ASIL yüzey oydu ve tur onu hiç
    #: ölçmüyordu — küre siyah/boş çıksa yayına kadar görünmezdi.
    #: Seçici DOLU ise tur tuvali bekler, anlık görüntüsünü alır ve
    #: ``tuval_dolu`` denetimini ÜRETİR (fail-closed: beyan edilen tuval
    #: ölçülemezse kırmızı). Boş ise hiçbir tuval denetimi üretilmez
    #: (hayalet denetim yok).
    tuval_secici: str = ''
    #: Beyan edilen tuval ÇİZİLMİŞ sayılmadan önce sağlanması gereken
    #: sayfa ölçütü (``page.wait_for_function`` ifadesi). Sabit bir uyku
    #: yerine sayfanın KENDİ hazırlık işareti beklenir; boşsa yalnız
    #: tuvalin görünür olması beklenir.
    tuval_hazir_kosulu: str = ''


#: Sonuç nesnesi üç sayfada da ``currentResults`` adıyla, betiğin en üst
#: kapsamında tanımlı (advanced: app.js:169, solid.html:3551,
#: liquid.html:2163) — yani ``window.currentResults`` olarak okunabilir.
_HIBRIT_SONUC = '() => !!(window.currentResults && window.currentResults.motor)'
_SONUC_VAR = '() => !!window.currentResults'


SAYFALAR: Dict[str, Sayfa] = {
    'hybrid': Sayfa(
        ad='hybrid',
        yol='/hybrid',
        hesapla_secici='button[onclick="calculate()"]',
        sonuc_kosulu=_HIBRIT_SONUC,
        # Hesap sonucu gösterilirken ``mountMotorViz`` kendiliğinden çağrılır
        # (app.js:668) — kullanıcının gördüğü yol budur. İkinci bir yol
        # (``#generateCADBtn`` -> ``generateCAD()``) BİLEREK denenmez: o düğme
        # tam tasarım paketi üretir ve ``window.open`` ile bir popup açar
        # (advanced.html:4273). Denetim turu, ölçtüğü sayfada yan etki
        # yaratmamalı. Kendiliğinden kurulum başarısızsa hüküm KALIR — bu,
        # kullanıcının ekranında da 3B ikizin görünmediği anlamına gelir.
        viz_acma_secicileri=(),
        viz_kap_kimligi='motor_viz3d_viewport',
        notlar='advanced.html — MotorViz3D doğrudan kurulur (güverte yok).',
        fea_panelleri=(YAPISAL_FEA, TERMAL_FEA),
        # Analiz Merkezi advanced.html:889'da kuruluyor (motorType 'hybrid').
        merkez_var=True,
        # ÖH D23 / P10B3-03: iki kararlılık kiracısı EKLENDİ. Yalnız BURAYA
        # eklendi çünkü canlı sonda (4 Eylül 2026) yalnız /hybrid'i ölçtü;
        # /solid ve /liquid'de aynı satırlar analysis_center.js:233,243'e
        # göre KAYITLI ama READY oldukları ÖLÇÜLMEDİ. Ölçülmemiş sayfaya
        # kiracı yazmak, kapıyı ölçüme değil tahmine bağlamak olurdu.
        merkez_kiracilari=(CFD_KIRACISI, ACOUSTIC_MODES_KIRACISI,
                           COMBUSTION_STABILITY_KIRACISI),
    ),
    'solid': Sayfa(
        ad='solid',
        yol='/solid',
        hesapla_secici='button[onclick="calculateSolid()"]',
        sonuc_kosulu=_SONUC_VAR,
        # Katıda sahne KULLANICI düğmesine bağlı: show3DVisualization()
        # önce CAD sekmesini açar, sonra güverteyi kurar (solid.html:4907).
        viz_acma_secicileri=('button[onclick="show3DVisualization()"]',),
        viz_kap_kimligi='cad_3d_view',
        notlar='solid.html — MotorVizDeck güvertesi, CAD sekmesinin içinde.',
        # Tane FEA paneli ``#trajectoryPanel``in ÖNÜNE kuruluyor; o panel
        # sekmelerin DIŞINDA olduğu için CAD sekmesi açılsa da görünür
        # kalır (solid.html:1785 üst düzey ``.panel``).
        fea_panelleri=(TANE_FEA,),
        # Analiz Merkezi solid.html:6077'de kuruluyor (motorType 'solid').
        merkez_var=True,
        # ÖH D24 / P17B1-15 — ``acoustic_modes`` EKLENDİ. D23'ün açık
        # bıraktığı kapı buydu: satır ``analysis_center.js:233``e göre katıda
        # da kayıtlı ama READY olduğu ÖLÇÜLMEMİŞTİ. 5 Eylül 2026 canlı
        # sondası (docs/scofield/raw/OH/D24/altyapi/a2/once_p17b115.json)
        # /solid'de dört READY satır ölçtü: structural, planar_grain, cfd,
        # acoustic_modes. ``combustion_stability`` katıda BLOCKED'dır
        # ("A solid motor has no injector and no feed system…") ve bilerek
        # EKLENMEDİ — ürünün kendi uygulanabilirlik hükmü budur.
        merkez_kiracilari=(CFD_KIRACISI, ACOUSTIC_MODES_KIRACISI),
    ),
    'liquid': Sayfa(
        ad='liquid',
        yol='/liquid',
        hesapla_secici='button[onclick="calculateLiquid()"]',
        sonuc_kosulu=_SONUC_VAR,
        # Sıvıda güverte sonuç akışında kendiliğinden kurulur
        # (liquid.html:2244 -> generateCADVisualization).
        viz_acma_secicileri=(),
        viz_kap_kimligi='liquid_3d_view',
        notlar='liquid.html — MotorVizDeck güvertesi, ana sonuç panelinde.',
        # Yapısal FEA paneli 2026-08-15'te bağlandı; panel liquid.html'de
        # #analysis-dock-anchor önüne kurulur.
        #
        # KÖŞE TEKİLLİĞİ BORCU AÇIK (ÖH D25 altyapı a2, defter P17B1-17).
        # Bu not eskiden borcun mesh_axisym'in dış yüzey eğrilik tabanıyla
        # (yuvarlanan-top kapaması) ÇÖZÜLDÜĞÜNÜ söylüyordu. ÖLÇÜLDÜ
        # (docs/scofield/raw/OH/D25/altyapi/a2/once_p17b117.json), iki
        # bağımsız kanıtla ve iddia İKİ AYRI YERDEN tutmuyor:
        #
        #  (1) GERİLME TEKİLLİĞİ DURUYOR. Sayfanın kendi varsayılanıyla
        #      koşan canlı tur (sistem Chrome, ÖH D24 altyapı a2 kaydı
        #      docs/scofield/raw/OH/D24/altyapi/a2/tur_p17b115/
        #      tour_report.json) sıvıda TEPE von MISES 1763,7 MPa ve MIN
        #      SAFETY FACTOR 0,07 basıyor. Borcun açıldığı gündeki tepe
        #      1742 MPa idi: tekillik %1,2 BÜYÜDÜ, yok olmadı. (Aynı turda
        #      hibrit 28,4 MPa / SF 7,56 — kusur sıvıya özgü.)
        #  (2) YAKINSAMA YALNIZ O NOKTADA KAZANILDI. Canlı tur o yükte
        #      "CONVERGED in 10 rounds to 0.68%" basıyor, yani P17'nin
        #      ölçtüğü "NOT CONVERGED after 11 rounds" artık O NOKTADA
        #      üremiyor — kazanım gerçek. Ama köprü taramasında (üç sıvı
        #      tasarım noktası, run_structural_from_motor) 3'ten 2'si
        #      YAYIMLANAN KİPTE yakınsamıyor: 2 kN/15 bar/eps=5 ve
        #      1 kN/10 bar/eps=4 vakalarında converged=False (ikisinde de
        #      converged_birincil_kip=True). Yani eski iddia yalnız TEK bir
        #      tasarım noktasının hükmüdür, panelin hükmü değil.
        #
        # Bu tarif dosyası bir GEZİNTİ tarifidir; borcu kapatmak fizik
        # kulvarının işidir (mesh üçlüsü). Burada yalnız gerçeği söyler.
        # Yakınsama beyanı turda ZATEN çaprazlanıyor (denetimler.py:860
        # 'yakınsama hükmü' beklentisi, renk + tur + yüzde), yani rozet
        # silinirse ya da yeşile boyanırsa tur kırmızı verir — bu notun
        # yalanı o kapıyı atlatmıştı, kapı değil künye kusurluydu.
        #
        # Termal ve tane panelleri sıvıya BİLEREK eklenmedi: termal zincir
        # bu sayfada yok, tane paneli katıya özgü.
        fea_panelleri=(YAPISAL_FEA,),
        # Analiz Merkezi liquid.html:6791'de kuruluyor (motorType 'liquid').
        merkez_var=True,
        # ÖH D24 / P17B1-15 — iki kararlılık kiracısı EKLENDİ. Aynı canlı
        # sonda /liquid'de de dört READY satır ölçtü: structural, cfd,
        # acoustic_modes, combustion_stability. Sıvıda enjektör ve besleme
        # hattı VARDIR, o yüzden ``combustion_stability`` katının aksine
        # BLOCKED değil READY'dir.
        merkez_kiracilari=(CFD_KIRACISI, ACOUSTIC_MODES_KIRACISI,
                           COMBUSTION_STABILITY_KIRACISI),
    ),
}


#: ÖH D24 / P17B1-15 — ÜÇ SAYFANIN CANLI ``ready`` ÖLÇÜMÜ (5 Eylül 2026).
#:
#: D23 aşama-2 bu ölçümü yalnız ``/hybrid`` için almıştı; ``/solid`` ve
#: ``/liquid``de satırların READY olup olmadığı BİLİNMİYORDU ve kalemin
#: kalan yarısı buydu. Kanıt (sistem Chrome 152.0.7977.82, her sayfada
#: hesap koşturulup ``[data-ac-row]`` düğümlerinin ``data-ac-state``
#: değeri okundu):
#:
#:     docs/scofield/raw/OH/D24/altyapi/a2/once_p17b115.json
#:
#: Bu sözlük ölçümün KENDİSİDİR, hedef değil: bir satır buraya ancak
#: ölçüldüğü için yazılır. ``blocked``/``absent`` satırlar (ör. katıda
#: ``combustion_stability`` — "A solid motor has no injector and no feed
#: system…") BİLEREK yoktur; ürünün kendi uygulanabilirlik hükmü budur.
CANLI_READY_SATIRLAR: Dict[str, Tuple[str, ...]] = {
    'hybrid': ('chamber_acoustics.acoustic_modes',
               'chamber_acoustics.combustion_stability',
               'chamber_nozzle_wall.structural',
               'nozzle_flow.cfd'),
    'solid': ('chamber_acoustics.acoustic_modes',
              'chamber_nozzle_wall.structural',
              'grain_section.planar_grain',
              'nozzle_flow.cfd'),
    'liquid': ('chamber_acoustics.acoustic_modes',
               'chamber_acoustics.combustion_stability',
               'chamber_nozzle_wall.structural',
               'nozzle_flow.cfd'),
}


def kapsanmayan_ready() -> Dict[str, Tuple[str, ...]]:
    """Ölçülen READY satırlardan turun KOŞTURMADIKLARI — sayfa başına.

    Kapsam beyanı TEK KAYNAKTAN türetilir: ölçüm (``CANLI_READY_SATIRLAR``)
    eksi tanım (``Sayfa.merkez_kiracilari``). Elle tutulan ikinci bir liste
    olsaydı kapsam büyüdükçe sessizce yalan söylerdi.
    """
    cikti: Dict[str, Tuple[str, ...]] = {}
    for ad, satirlar in CANLI_READY_SATIRLAR.items():
        sayfa = SAYFALAR.get(ad)
        kosan = {k.satir_anahtari for k in (sayfa.merkez_kiracilari or ())} \
            if sayfa is not None else set()
        cikti[ad] = tuple(sorted(set(satirlar) - kosan))
    return cikti


def merkez_kapsami() -> Dict[str, int]:
    """Kalemin sayısı: ölçülen READY satır ⟷ turun koşturduğu kiracı."""
    ready = sum(len(v) for v in CANLI_READY_SATIRLAR.values())
    kosan = sum(len([k for k in (SAYFALAR[a].merkez_kiracilari or ())
                     if k.satir_anahtari in CANLI_READY_SATIRLAR[a]])
                for a in CANLI_READY_SATIRLAR if a in SAYFALAR)
    return {'ready_satir': ready, 'kosturulan_kiraci': kosan,
            'kapsanmayan': ready - kosan}


#: Hiçbir sayfada tarifi YAZILMAMIŞ ama canlıda READY görülen satırlar.
#: Sözleşmeleri yazılmadı çünkü canlı sondada koşturulmadılar: ölçülmemiş
#: bir kiracıya tarif yazmak, ölçmeden hüküm kurmaktır (fail-closed).
#: İkisi de FEA panellerinin Merkez'e kayıtlı ikizidir
#: (``fea_panel.js`` SPEC_STRUCTURAL / SPEC_PLANAR_GRAIN); tur onların
#: PANEL yolunu zaten koşturuyor, Merkez KARTI yolunu değil.
OLCULMEMIS_HAZIR_KIRACILAR: Tuple[str, ...] = tuple(sorted(
    {satir for satirlar in kapsanmayan_ready().values() for satir in satirlar}))

#: ÖH D21 / defter P17B1-16 — GÖRSEL KAPININ AÇMADIĞI ÜÇ SAYFA.
#:
#: Ölçüldü (``hrma/app.py``, ``render_template`` dönen uçlar): ürünün
#: kullanıcıya açık altı HTML sayfası var (sekizdi; ``/simple`` ve
#: ``/uzaytek`` ÖH D36'da söküldü — Berke, 23 Eyl 2026, dalga36/sokum);
#: üçünü (motor sayfaları) tur zaten geziyordu. Aşağıdaki üçü hiç açılmıyordu —
#: yani bu sayfalarda bir konsol hatası, ekrana sızmış bir ``undefined``
#: ya da üst üste binmiş bir metin bloğu yayına kadar görünmezdi.
#:
#: Hesap akışı YOK: üçünde de "Hesapla" düğmesi, ``currentResults``
#: nesnesi, 3B sahne, FEA paneli ve Analiz Merkezi bulunmuyor (ölçüldü).
#: Bu yüzden ``hesap_var=False`` ve ``sonuc_kosulu`` boş; tur bu
#: sayfalarda YALNIZ maruz kalınan yüzeyi ölçer.
STATIK_SAYFALAR: Dict[str, Sayfa] = {
    'index': Sayfa(
        ad='index',
        yol='/',
        hesapla_secici='',
        sonuc_kosulu='',
        hesap_var=False,
        notlar=('index.html — giriş/karşılama sayfası; motor seçim kartları '
                've iddia metinleri burada (P10B4-02 iddia envanterinin '
                'taşıyıcılarından biri).'),
    ),
    'formulas': Sayfa(
        ad='formulas',
        yol='/formulas',
        hesapla_secici='',
        sonuc_kosulu='',
        hesap_var=False,
        notlar=('formulas.html — formül/denklem referansı; KaTeX/MathJax '
                'kurulumu kırılırsa ekranda ham işaretleme kalır ve bunu '
                'yalnız göz görür.'),
    ),
    'launch-site': Sayfa(
        ad='launch-site',
        yol='/launch-site',
        hesapla_secici='',
        sonuc_kosulu='',
        hesap_var=False,
        # ÖH D27 / OH-D25-02(a): küre tuvali ``LaunchSiteGlobe`` tarafından
        # çalışma anında üretilir (launch_site_globe.js:334
        # ``this.container.appendChild(renderer.domElement)``), şablonda
        # ``<canvas>`` etiketi YOKTUR — bu yüzden seçici KAP üstünden verilir.
        tuval_secici='#ls-globe canvas',
        # Three.js WebGLRenderer çizilen KARE sayısını kendisi tutar
        # (``renderer.info.render.frame``); küre en az bir kare çizmeden
        # ölçmek boş tuval okumak olurdu. Nesne launch_site.html:531'de
        # ``window.launchGlobe`` olarak yayımlanıyor.
        tuval_hazir_kosulu=(
            '() => !!(window.launchGlobe && window.launchGlobe.renderer'
            ' && window.launchGlobe.renderer.info'
            ' && window.launchGlobe.renderer.info.render.frame > 0)'),
        notlar=('launch_site.html — fırlatma sahası haritası (savcı C.7: '
                'turun hiç açmadığı sayfa). Harita katmanları sürekli '
                'istek attığı için ağ sessizliği beklenmeyebilir; tur bunu '
                'zaten hüküm değil NOT olarak kaydeder.'),
    ),
}

SAYFALAR.update(STATIK_SAYFALAR)

#: Hesap akışı olan sayfalar — ``tests/support/inventory.py::PAGES`` ile
#: AYNI kümedir (form envanteri yalnız bu sayfalar için kurulur).
#:
#: TEK KAYNAK: üçlü LİTERAL olarak yazılmaz, tanımlardan TÜRETİLİR. Eski
#: ``VARSAYILAN_SIRA = ('hybrid', 'solid', 'liquid')`` biçimi motor türü
#: üçlüsünün adlandırılmış bir ikizi olduğu için
#: ``tests/test_sabit_tek_kaynak.py::_MOTOR_TYPE_IKIZLERI`` listesinde
#: muafiyet taşıyordu; türetme o ikizi tamamen kapatır (ÖH D21 / altyapi).
HESAPLI_SIRA = tuple(ad for ad, tanim in SAYFALAR.items() if tanim.hesap_var)

#: Argüman verilmediğinde gezilecek sıra. ÖH D21 / P17B1-16: üç statik
#: sayfa SONA eklendi — motor sayfaları ağırdır, statik sayfalar saniyeler
#: sürer; sıra hızlı geri bildirimi bozmasın diye ağır olanlar önde kalır.
VARSAYILAN_SIRA = HESAPLI_SIRA + tuple(STATIK_SAYFALAR)


def sayfalari_coz(istek: str) -> Tuple[Sayfa, ...]:
    """``"hybrid,solid"`` gibi bir listeyi ``Sayfa`` demetine çevirir.

    Bilinmeyen ad sessizce atlanmaz — ``ValueError`` yükselir; yazım hatası
    yüzünden "hepsi geçti" raporu üretmek en kötü sonuçtur.
    """
    adlar = [p.strip() for p in istek.split(',') if p.strip()]
    if not adlar:
        raise ValueError('sayfa listesi boş')
    bilinmeyen = [a for a in adlar if a not in SAYFALAR]
    if bilinmeyen:
        raise ValueError(
            'bilinmeyen sayfa: %s (geçerli: %s)'
            % (', '.join(bilinmeyen), ', '.join(sorted(SAYFALAR))))
    return tuple(SAYFALAR[a] for a in adlar)
