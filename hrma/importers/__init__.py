"""Dış dosya biçimlerinden HRMA'ya veri aktarım paketi.

Modüller:
- ``motor_file``: RASP (.eng) ve RockSim (.rse) itki eğrisi dosyaları.
- ``ork_import``: OpenRocket (.ork) tasarım dosyaları.
- ``api``: Flask Blueprint (``importers_api``) — /api/import/* uçları.

Tasarım ilkesi (projenin uydurma-veri-yasağı kimliği): dosyada OLMAYAN hiçbir
alan sessizce doldurulmaz; tahmin edilen her değer ``estimated`` işareti ve
``warnings`` kaydıyla döner.
"""
