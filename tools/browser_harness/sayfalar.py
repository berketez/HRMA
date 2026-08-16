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
    beklenen_imzalar=('mesh_bozulmasi', 'uzamis_elemanlar'),
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
    beklenen_imzalar=('tepe_cidar_sicakligi',),
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
    beklenen_imzalar=('kabul_olcutu', 'mesh_bozulmasi'),
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
    beklenen_imzalar=('cfd_yakinsama_hukmu', 'cfd_ayrilma_hukmu',
                      'cfd_kutle_artigi', 'cfd_enerji_artigi',
                      'cfd_cekirdek', 'cfd_sok_sensoru',
                      'cfd_sinirlayici', 'cfd_sure'),
    yasak_imzalar=('cfd_bayat_giris_uyarisi', 'cfd_bayat_mach_esigi'),
    notr_imzalar=('cfd_kutle_artigi', 'cfd_enerji_artigi'),
    notlar=('analysis_center.js domKey: componentId + "_" + analysisId; '
            'çizim kimlikleri cfd_panel.js:1135-1137 (drawSeq ile artar).'),
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
    #: de en az bir panel var (sıvıdaki yapısal panel 2026-08-15'te bağlandı
    #: — köşe tekilliği borcu mesh_axisym dış yüzey eğrilik tabanıyla
    #: kapandı). Boş liste "denetlenmedi" değil "denetlenecek panel yok"
    #: demek olurdu; bugün öyle bir sayfa kalmadı.
    fea_panelleri: Tuple[FeaPaneli, ...] = field(default_factory=tuple)
    #: Sayfada Analiz Merkezi kuruluyor mu (``AnalysisCenter.init``)? Üç
    #: sayfanın üçünde de kuruluyor (advanced.html:889, solid.html:6077,
    #: liquid.html:6791 — ölçüldü). Kurulmayan bir sayfada çerçeve denetimi
    #: ÜRETİLMEZ; hayalet denetim "kaldı" demekten daha kötüdür, çünkü
    #: kusuru olmayan bir sayfayı kırmızıya boyar.
    merkez_var: bool = False
    #: Merkez'de koşturulup denetlenecek kiracılar.
    merkez_kiracilari: Tuple[MerkezKiracisi, ...] = field(default_factory=tuple)


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
        merkez_kiracilari=(CFD_KIRACISI,),
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
        merkez_kiracilari=(CFD_KIRACISI,),
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
        # Yapısal FEA paneli 2026-08-15'te bağlandı: eski "köşe tekilliği
        # yakınsamıyor" borcu (1742 MPa, tur başına %16) mesh_axisym'in dış
        # yüzey eğrilik tabanıyla (yuvarlanan-top kapaması) kapandı; panel
        # liquid.html'de #analysis-dock-anchor önüne kurulur. Termal ve
        # tane panelleri sıvıya BİLEREK eklenmedi: termal zincir bu sayfada
        # yok, tane paneli katıya özgü.
        fea_panelleri=(YAPISAL_FEA,),
        # Analiz Merkezi liquid.html:6791'de kuruluyor (motorType 'liquid').
        merkez_var=True,
        merkez_kiracilari=(CFD_KIRACISI,),
    ),
}

#: Argüman verilmediğinde gezilecek sıra.
VARSAYILAN_SIRA = ('hybrid', 'solid', 'liquid')


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
