(function() {
  var themes = { blue: true, forest: true, sepia: true };
  var storageKey = 'prison_oa_theme';

  function savedTheme() {
    var value = 'blue';
    try { value = localStorage.getItem(storageKey) || 'blue'; } catch (e) {}
    return themes[value] ? value : 'blue';
  }

  function applyTheme(theme, save) {
    var value = themes[theme] ? theme : 'blue';
    document.documentElement.setAttribute('data-theme', value);
    if (document.body) document.body.setAttribute('data-theme', value);
    if (save !== false) {
      try { localStorage.setItem(storageKey, value); } catch (e) {}
    }
    return value;
  }

  applyTheme(savedTheme(), false);

  if (window.addEventListener) {
    window.addEventListener('DOMContentLoaded', function() { applyTheme(savedTheme(), false); });
    window.addEventListener('DOMContentLoaded', ensureBackNavigation);
    window.addEventListener('DOMContentLoaded', enableAutoFilters);
    window.addEventListener('message', function(event) {
      var data = event.data || {};
      if (data.type === 'oa-theme-change') applyTheme(data.theme, false);
    });
  } else if (window.attachEvent) {
    window.attachEvent('onload', function() { applyTheme(savedTheme(), false); });
    window.attachEvent('onload', ensureBackNavigation);
    window.attachEvent('onload', enableAutoFilters);
  }

  window.OATheme = {
    apply: function(theme) { return applyTheme(theme, true); },
    current: savedTheme
  };

  function enableAutoFilters() {
    var selects = document.querySelectorAll('.oa-filter-panel form select');
    for (var i = 0; i < selects.length; i++) {
      if (selects[i].getAttribute('data-auto-filter') === '1') continue;
      selects[i].setAttribute('data-auto-filter', '1');
      selects[i].addEventListener('change', function() {
        var form = this.form;
        if (!form) return;
        var submitEvent = document.createEvent('Event');
        submitEvent.initEvent('submit', true, true);
        if (form.dispatchEvent(submitEvent)) form.submit();
      });
    }
  }

  function ensureBackNavigation() {
    if (!document.body) return;
    var path = window.location.pathname || '';
    if (path === '/' || path === '/login' || path === '/workbench') return;
    if (document.querySelector('.breadcrumb, .back-btn, .auto-back-nav, .detail-top')) return;

    var wrap = document.createElement('div');
    wrap.className = 'auto-back-nav';
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'back-btn';
    button.textContent = '返回上一页';
    button.addEventListener('click', function() {
      if (window.history.length > 1) {
        window.history.back();
      } else {
        window.location.href = '/workbench';
      }
    });
    wrap.appendChild(button);
    document.body.insertBefore(wrap, document.body.firstChild);
  }
})();
