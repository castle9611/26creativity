(function () {
    var scripts = document.getElementsByTagName('script');
    var enabled = scripts[scripts.length - 1].getAttribute('data-autoplay') === '1';
    var videos = document.getElementsByTagName('video');
    for (var i = 0; i < videos.length; i++) {
        videos[i].autoplay = enabled;
        videos[i].controls = true;
        if (enabled) {
            videos[i].muted = true;
            videos[i].defaultMuted = true;
            videos[i].setAttribute('muted', 'muted');
            videos[i].setAttribute('playsinline', 'playsinline');
            videos[i].setAttribute('autoplay', 'autoplay');
            try {
                var playback = videos[i].play();
                if (playback && typeof playback['catch'] === 'function') {
                    playback['catch'](function () {});
                }
            } catch (ignore) {}
        } else {
            videos[i].removeAttribute('autoplay');
            videos[i].pause();
        }
    }
})();
