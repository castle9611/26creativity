(function() {
  var storageKey = 'prison_oa_theme';
  var themes = [
    { id: 'blue', name: '清爽蓝' },
    { id: 'forest', name: '墨绿' },
    { id: 'sepia', name: '暖棕' },
    { id: 'night', name: '夜间' }
  ];

  function safeGetTheme() {
    try {
      return localStorage.getItem(storageKey) || 'blue';
    } catch (e) {
      return 'blue';
    }
  }

  function safeSetTheme(theme) {
    try {
      localStorage.setItem(storageKey, theme);
    } catch (e) {}
  }

  function isKnownTheme(theme) {
    for (var i = 0; i < themes.length; i++) {
      if (themes[i].id === theme) return true;
    }
    return false;
  }

  function applyTheme(theme) {
    if (!isKnownTheme(theme)) theme = 'blue';
    document.documentElement.setAttribute('data-theme', theme);
    if (document.body) document.body.setAttribute('data-theme', theme);
    var selects = document.querySelectorAll ? document.querySelectorAll('[data-theme-select]') : [];
    for (var i = 0; i < selects.length; i++) {
      selects[i].value = theme;
    }
  }

  function syncChildFrames(theme) {
    var frames = document.getElementsByTagName('iframe');
    for (var i = 0; i < frames.length; i++) {
      try {
        frames[i].contentWindow.postMessage({ type: 'oa-theme-change', theme: theme }, '*');
        if (frames[i].contentDocument) {
          frames[i].contentDocument.documentElement.setAttribute('data-theme', theme);
          if (frames[i].contentDocument.body) frames[i].contentDocument.body.setAttribute('data-theme', theme);
        }
      } catch (e) {}
    }
  }

  function setTheme(theme) {
    if (!isKnownTheme(theme)) theme = 'blue';
    safeSetTheme(theme);
    applyTheme(theme);
    syncChildFrames(theme);
  }

  function buildSwitcher() {
    if (window.top !== window.self) return;
    if (document.querySelector && document.querySelector('[data-theme-select]')) return;

    var select = document.createElement('select');
    select.className = 'theme-switcher-select';
    select.setAttribute('data-theme-select', '1');
    select.title = '切换界面主题';

    for (var i = 0; i < themes.length; i++) {
      var opt = document.createElement('option');
      opt.value = themes[i].id;
      opt.appendChild(document.createTextNode(themes[i].name));
      select.appendChild(opt);
    }

    select.value = safeGetTheme();
    select.onchange = function() { setTheme(this.value); };

    var slot = document.querySelector ? document.querySelector('[data-theme-slot]') : null;
    if (slot) {
      var slotWrap = document.createElement('span');
      slotWrap.className = 'theme-switcher-inline';
      slotWrap.appendChild(select);
      slot.appendChild(slotWrap);
      return;
    }

    var headerRight = document.querySelector ? document.querySelector('.header-right') : null;
    if (headerRight) {
      var wrap = document.createElement('span');
      wrap.className = 'theme-switcher-inline';
      wrap.appendChild(select);
      headerRight.insertBefore(wrap, headerRight.firstChild);
    } else {
      var floating = document.createElement('div');
      floating.className = 'theme-switcher-floating';
      floating.appendChild(select);
      document.body.appendChild(floating);
    }
  }

  applyTheme(safeGetTheme());

  if (window.addEventListener) {
    window.addEventListener('message', function(event) {
      var data = event.data || {};
      if (data.type === 'oa-theme-change') applyTheme(data.theme);
    });
    window.addEventListener('storage', function(event) {
      if (event.key === storageKey) applyTheme(event.newValue || 'blue');
    });
    window.addEventListener('DOMContentLoaded', function() {
      applyTheme(safeGetTheme());
      buildSwitcher();
    });
  } else if (window.attachEvent) {
    window.attachEvent('onload', function() {
      applyTheme(safeGetTheme());
      buildSwitcher();
    });
  }

  window.OATheme = {
    apply: setTheme,
    current: safeGetTheme
  };
})();
