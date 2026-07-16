/* Shared form safety and feedback helpers. ES5 for legacy intranet browsers. */
(function () {
    var dirty = false;
    var submitting = false;

    function hasClass(el, name) {
        return (' ' + el.className + ' ').indexOf(' ' + name + ' ') >= 0;
    }

    function isEditableTarget(el) {
        if (!el || !el.form) return false;
        if ((el.form.method || 'get').toLowerCase() !== 'post') return false;
        if (hasClass(el.form, 'no-dirty-guard')) return false;
        return el.type !== 'hidden' && el.type !== 'submit' && el.type !== 'button';
    }

    function markDirty(event) {
        event = event || window.event;
        if (isEditableTarget(event.target || event.srcElement)) dirty = true;
    }

    function lockForm(form) {
        var buttons = form.getElementsByTagName('button');
        var i;
        submitting = true;
        dirty = false;
        for (i = 0; i < buttons.length; i++) {
            if (buttons[i].type === 'submit' || !buttons[i].type) {
                buttons[i].disabled = true;
                buttons[i].setAttribute('data-old-text', buttons[i].innerHTML);
                buttons[i].innerHTML = '正在提交...';
            }
        }
    }

    function bindForms() {
        var forms = document.getElementsByTagName('form');
        var i;
        for (i = 0; i < forms.length; i++) {
            if ((forms[i].method || 'get').toLowerCase() === 'post' && !hasClass(forms[i], 'no-submit-lock')) {
                forms[i].onsubmit = (function (form, oldHandler) {
                    return function (event) {
                        if (submitting) return false;
                        if (oldHandler && oldHandler.call(form, event) === false) return false;
                        lockForm(form);
                        return true;
                    };
                })(forms[i], forms[i].onsubmit);
            }
        }
    }

    if (document.addEventListener) {
        document.addEventListener('change', markDirty, false);
        document.addEventListener('input', markDirty, false);
        document.addEventListener('DOMContentLoaded', bindForms, false);
    } else {
        document.attachEvent('onchange', markDirty);
        window.attachEvent('onload', bindForms);
    }

    window.onbeforeunload = function () {
        if (dirty && !submitting) return '当前页面还有未保存的修改，确定要离开吗？';
    };
})();
