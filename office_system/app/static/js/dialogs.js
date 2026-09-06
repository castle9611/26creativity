/* Keyboard and focus lifecycle for standalone modal dialogs. ES5. */
(function () {
    var active = null;
    var opener = null;
    function controls(dialog) {
        var nodes = dialog.querySelectorAll('a[href], button, input, select, textarea, [tabindex]');
        var visible = [];
        for (var i = 0; i < nodes.length; i++) {
            if (!nodes[i].disabled && nodes[i].tabIndex >= 0 && nodes[i].getClientRects().length) visible.push(nodes[i]);
        }
        return visible;
    }
    window.OADialog = {
        open: function (dialog) {
            if (active === dialog) return;
            if (active) this.close(active);
            opener = document.activeElement;
            active = dialog;
            dialog.style.display = 'block';
            dialog.setAttribute('aria-hidden', 'false');
            var items = controls(dialog);
            (items[0] || dialog).focus();
        },
        close: function (dialog) {
            dialog.style.display = 'none';
            dialog.setAttribute('aria-hidden', 'true');
            if (active !== dialog) return;
            active = null;
            if (opener && document.documentElement.contains(opener)) opener.focus();
            opener = null;
        }
    };
    document.addEventListener('keydown', function (event) {
        if (!active) return;
        if (event.keyCode === 27) {
            event.preventDefault();
            window.OADialog.close(active);
        } else if (event.keyCode === 9) {
            var items = controls(active);
            var first = items[0] || active;
            var last = items[items.length - 1] || active;
            if (!items.length || !active.contains(document.activeElement) ||
                (event.shiftKey && (document.activeElement === first || document.activeElement === active)) ||
                (!event.shiftKey && document.activeElement === last)) {
                event.preventDefault();
                (event.shiftKey ? last : first).focus();
            }
        }
    });
    document.addEventListener('focusin', function (event) {
        if (active && !active.contains(event.target)) (controls(active)[0] || active).focus();
    });
})();
