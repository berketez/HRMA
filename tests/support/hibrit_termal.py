"""v3.0.1 (V301/H-termal) — hibritin FAIL-CLOSED termal yolunu kuran yardımcı.

V301/H-termal'den sonra hibrit kamara cidarı üç bölgedir: yakıt bloğu altı
yanma boyunca korunur (beyanlı), ön/son yanma odasında hüküm HRMA'nın
boyutlandırdığı astarla verilir ve yapı zinciri beyanlı kasa sıcaklığını
kullanır. Çıplak cidarın kararlı (≈ adyabatik) sıcaklığıyla yapılan eski
değerlendirme artık YALNIZ astar boyutlandırması koşmadığında görülür
(``hybrid_rocket_engine._chamber_wall_zones_block``: ``BARE_WALL_CRITICAL``,
fail-closed — kritik hüküm AYNEN kalır, yapı zinciri çıplak cidar
sıcaklıklarını kullanır).

Bazı bekçiler (model geçerlilik sınırı, kritik termal hükmün teslim kanalı,
imalat kapısı) bu SICAK CİDAR değerlendirmesini senaryo olarak kullanır. Bu
yardımcı ürünün fail-closed yolunu açıkça kurar: kamara astarı istasyonu
"boyutlandırma koşmadı" (``thickness_status = NOT_MODELLED``) döner; geri
kalan her şey ürün kodudur. Bekçilerin iddiası değişmez, yalnız hangi ürün
yolunu sınadıkları adıyla yazılır.
"""
import contextlib


@contextlib.contextmanager
def astar_boyutlandirmasi_kosmaz():
    """Hibrit kamara astarı boyutlandırmasını 'koşmadı' durumuna getirir."""
    from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
    asil = HybridRocketEngine._thermal_protection_block

    def astarsiz(self, isi, yalniz_kamara_astari=False):
        blok = asil(self, isi, yalniz_kamara_astari)
        if isinstance(blok, dict):
            blok = dict(blok, chamber_liner={
                'thickness': None, 'thickness_status': 'NOT_MODELLED',
                'model_valid': False,
                'basis': ('test scenario: chamber liner sizing did not run '
                          '(hybrid fail-closed thermal path)')})
        return blok

    HybridRocketEngine._thermal_protection_block = astarsiz
    try:
        yield
    finally:
        HybridRocketEngine._thermal_protection_block = asil
