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
