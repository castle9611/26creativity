(function() {
    var field = document.getElementById('richContent') || document.getElementById('taskContent');
    if (!field) return;
    var editor = null;

    function html() {
        return editor ? editor.html() : field.value;
    }

    function sync() {
        if (editor) editor.sync();
        var value = html();
        var hidden = document.getElementById('hiddenContent');
        if (hidden) hidden.value = value;
        return value;
    }

    function focus() {
        if (editor) editor.focus();
        else field.focus();
    }

    function insertLocalImage(input) {
        var file = input.files && input.files[0];
        if (!file) return;
        if (!/^image\/(png|jpeg|gif|bmp|webp)$/i.test(file.type)) {
            alert('请选择 PNG、JPEG、GIF、BMP 或 WebP 图片');
            input.value = '';
            return;
        }
        if (file.size > 5 * 1024 * 1024) {
            alert('图片大小不能超过 5MB');
            input.value = '';
            return;
        }
        if (!window.FileReader) {
            alert('当前浏览器不支持插入本地图片');
            input.value = '';
            return;
        }
        var reader = new FileReader();
        reader.onload = function(event) {
            var src = event.target.result;
            if (editor) {
                editor.focus();
                editor.insertHtml('<img src="' + src + '" alt="">');
            } else {
                field.value += '<img src="' + src + '" alt="">';
            }
            input.value = '';
        };
        reader.readAsDataURL(file);
    }

    window.OARichEditor = {
        html: html,
        sync: sync,
        focus: focus,
        insertLocalImage: insertLocalImage
    };

    if (!window.KindEditor) return;
    if (field.id === 'taskContent' && field.value && !/<[a-z][\s\S]*>/i.test(field.value)) {
        var text = document.createElement('div');
        text.appendChild(document.createTextNode(field.value));
        field.value = text.innerHTML.replace(/\r\n|\r|\n/g, '<br>');
    }
    KindEditor.ready(function(K) {
        editor = K.create('#' + field.id, {
            width: '100%',
            height: '320px',
            resizeType: 1,
            langType: 'zh-CN',
            filterMode: true,
            allowFileManager: false,
            allowImageUpload: false,
            allowMediaUpload: false,
            allowFlashUpload: false,
            items: [
                'source', 'undo', 'redo', '|', 'formatblock', 'fontname', 'fontsize', '|',
                'forecolor', 'hilitecolor', 'bold', 'italic', 'underline', 'strikethrough',
                'removeformat', '|', 'justifyleft', 'justifycenter', 'justifyright', '|',
                'insertorderedlist', 'insertunorderedlist', 'indent', 'outdent', '|',
                'table', 'hr', 'link', 'unlink', 'fullscreen'
            ]
        });
    });
})();
