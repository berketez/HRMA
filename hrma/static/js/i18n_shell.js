/* HRMA kabuk sözlüğü — i18n_shell.js
 * ---------------------------------------------------------------
 * Ana sayfa kabuğuna sonradan eklenen ögelerin çevirileri:
 *   - aux-links satırındaki "Sürüm Notları" ve "Ayarlar" bağlantıları
 *   - Sürüm Notları modalı (release_notes.js)
 *   - Ayarlar paneli (settings_panel.js)
 * Kalıp: i18n.js başlığındaki ÇOK-PARÇALI SÖZLÜK SÖZLEŞMESİ — birebir.
 * Sürüm notu GÖVDESİ bilinçli olarak çevrilmez (ham release metni).
 */
(function (global) {
    'use strict';
    var DICT = {
        en: {
            'link.releaseNotes': 'Release Notes',
            'link.settings': 'Settings',
            'link.userGuide': 'User Guide',

            'shell.close': 'Close',

            'shell.releaseNotes.title': 'RELEASE NOTES',
            'shell.releaseNotes.loading': 'Loading release notes…',
            'shell.releaseNotes.empty': 'No release notes found.',
            'shell.releaseNotes.error': 'Release notes could not be loaded.',

            'shell.settings.title': 'SETTINGS',
            'shell.settings.language': 'Language',
            'shell.settings.languageDesc': 'Interface language. The selector on the home page stays in sync.',
            'shell.settings.updates': 'Updates',
            'shell.settings.autoCheck': 'Check for updates at startup',
            'shell.settings.autoCheckDesc': 'When off, HRMA does not contact the update server at startup.',
            'shell.settings.checkNow': 'Check now',
            'shell.settings.checking': 'Checking…',
            'shell.settings.upToDate': 'You are up to date: v{version}',
            'shell.settings.updateFound': 'New version found: v{version} — opening the update window.',
            'shell.settings.checkFailed': 'Could not reach the update server.',
            'shell.settings.rateLimited': 'GitHub is rate limiting this network — try again in a few minutes.',
            'shell.settings.skippedVersion': 'Skipped version: v{version}',
            'shell.settings.noSkipped': 'No skipped version.',
            'shell.settings.skipReset': 'Reset skipped version',
            'shell.settings.skipCleared': 'Skipped version cleared — it will be offered again.',
            'shell.settings.app': 'Application',
            'shell.settings.version': 'Version',
            'shell.settings.githubLink': 'HRMA on GitHub'
        },
        tr: {
            'link.releaseNotes': 'Sürüm Notları',
            'link.settings': 'Ayarlar',
            'link.userGuide': 'Kullanma Kılavuzu',

            'shell.close': 'Kapat',

            'shell.releaseNotes.title': 'SÜRÜM NOTLARI',
            'shell.releaseNotes.loading': 'Sürüm notları yükleniyor…',
            'shell.releaseNotes.empty': 'Sürüm notu bulunamadı.',
            'shell.releaseNotes.error': 'Sürüm notları yüklenemedi.',

            'shell.settings.title': 'AYARLAR',
            'shell.settings.language': 'Dil',
            'shell.settings.languageDesc': 'Arayüz dili. Ana sayfadaki seçici ile eşzamanlı kalır.',
            'shell.settings.updates': 'Güncellemeler',
            'shell.settings.autoCheck': 'Açılışta güncelleme denetle',
            'shell.settings.autoCheckDesc': 'Kapalıyken HRMA açılışta güncelleme sunucusuna bağlanmaz.',
            'shell.settings.checkNow': 'Şimdi denetle',
            'shell.settings.checking': 'Denetleniyor…',
            'shell.settings.upToDate': 'Güncelsiniz: v{version}',
            'shell.settings.updateFound': 'Yeni sürüm bulundu: v{version} — güncelleme penceresi açılıyor.',
            'shell.settings.checkFailed': 'Güncelleme sunucusuna ulaşılamadı.',
            'shell.settings.rateLimited': 'GitHub bu ağa istek sınırı uyguluyor — birkaç dakika sonra tekrar deneyin.',
            'shell.settings.skippedVersion': 'Atlanan sürüm: v{version}',
            'shell.settings.noSkipped': 'Atlanan sürüm yok.',
            'shell.settings.skipReset': 'Atlanan sürümü sıfırla',
            'shell.settings.skipCleared': 'Atlanan sürüm sıfırlandı — bir sonraki denetimde yeniden sorulur.',
            'shell.settings.app': 'Uygulama',
            'shell.settings.version': 'Sürüm',
            'shell.settings.githubLink': 'GitHub üzerinde HRMA'
        }
    };
    if (global.I18N && global.I18N.register) {
        global.I18N.register(DICT, 'i18n_shell.js');
    } else {
        (global.__I18N_PENDING = global.__I18N_PENDING || []).push(DICT);
    }
})(typeof window !== 'undefined' ? window : this);
