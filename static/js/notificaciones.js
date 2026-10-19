// static/js/notificaciones.js
// Sistema de notificaciones: campanita + polling + toasts
// Heredado por todos los templates via base.html

(function () {
    'use strict';

    var POLL_MS         = 30000;   // 30 segundos
    var TOAST_AUTOCLOSE = 8000;    // 8 segundos
    var URL_LISTAR      = '/especificaciones-pdf/api/notificaciones';
    var URL_LEER        = '/especificaciones-pdf/api/notificaciones/leer';

    var badge        = document.getElementById('notif-badge');
    var lista        = document.getElementById('notif-list');
    var btnMarcar    = document.getElementById('btn-marcar-todas');
    var toastCont    = document.getElementById('toast-container');

    if (!badge || !lista) return;

    // IDs que ya vimos en esta sesión (para no spamear toasts de viejas)
    var seenIds = new Set();
    var primeraCarga = true;

    // ─── Utilidades ───
    function tiempoRelativo(fechaStr) {
        if (!fechaStr) return '';
        // "YYYY-MM-DD HH:MM:SS" en UTC (SQLite datetime('now'))
        var f = new Date(fechaStr.replace(' ', 'T') + 'Z');
        var diff = Math.floor((Date.now() - f.getTime()) / 1000);
        if (diff < 60)     return 'hace unos segundos';
        if (diff < 3600)   return 'hace ' + Math.floor(diff / 60) + ' min';
        if (diff < 86400)  return 'hace ' + Math.floor(diff / 3600) + ' h';
        return 'hace ' + Math.floor(diff / 86400) + ' d';
    }

    function escapeHtml(s) {
        var d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    // ─── Render ───
    function renderBadge(n) {
        if (n > 0) {
            badge.textContent = n > 99 ? '99+' : String(n);
            badge.classList.add('visible');
        } else {
            badge.classList.remove('visible');
        }
    }

    function renderLista(notifs) {
        if (!notifs.length) {
            lista.innerHTML =
                '<div class="notif-empty">' +
                '<i class="fas fa-bell-slash fa-2x mb-2"></i><br>' +
                'Sin notificaciones nuevas' +
                '</div>';
            return;
        }

        var html = '';
        notifs.forEach(function (n) {
            html +=
                '<div class="notif-item unread" data-id="' + n.id + '" ' +
                (n.url ? 'data-url="' + escapeHtml(n.url) + '"' : '') + '>' +
                '<div class="notif-msg">' + escapeHtml(n.mensaje) + '</div>' +
                '<div class="notif-time"><i class="far fa-clock mr-1"></i>' +
                tiempoRelativo(n.fecha) + '</div>' +
                '</div>';
        });
        lista.innerHTML = html;
    }

    // ─── Toast ───
    function mostrarToast(n) {
        if (!toastCont) return;

        var t = document.createElement('div');
        t.className = 'notif-toast';
        t.innerHTML =
            '<div class="toast-title">' +
            '<span><i class="fas fa-bell text-warning mr-1"></i>Notificación</span>' +
            '<span class="toast-close" title="Cerrar">&times;</span>' +
            '</div>' +
            '<div class="toast-body">' + escapeHtml(n.mensaje) + '</div>';

        // Auto-cerrar
        var timer = setTimeout(function () { cerrarToast(t); }, TOAST_AUTOCLOSE);

        // Cerrar a mano
        t.querySelector('.toast-close').addEventListener('click', function (e) {
            e.stopPropagation();
            clearTimeout(timer);
            cerrarToast(t);
        });

        // Click en el toast → navegar + marcar leída
        t.addEventListener('click', function () {
            marcarLeidas([n.id]);
            if (n.url) {
                window.location.href = n.url;
            } else {
                cerrarToast(t);
            }
        });

        toastCont.appendChild(t);
    }

    function cerrarToast(t) {
        t.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
        t.style.opacity = '0';
        t.style.transform = 'translateX(120%)';
        setTimeout(function () {
            if (t.parentNode) t.parentNode.removeChild(t);
        }, 220);
    }

    // ─── API ───
    function cargar() {
        fetch(URL_LISTAR, { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) return;
                var notifs = data.notificaciones || [];

                renderBadge(notifs.length);
                renderLista(notifs);

                // Toasts solo para notifs nuevas (post-primera-carga)
                if (primeraCarga) {
                    notifs.forEach(function (n) { seenIds.add(n.id); });
                    primeraCarga = false;
                } else {
                    notifs.forEach(function (n) {
                        if (!seenIds.has(n.id)) {
                            seenIds.add(n.id);
                            mostrarToast(n);
                        }
                    });
                }
            })
            .catch(function () { /* silencioso */ });
    }

    function marcarLeidas(ids) {
        var body = ids && ids.length ? { ids: ids } : {};
        fetch(URL_LEER, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(function () {
            // Recargar inmediatamente para reflejar el cambio
            cargar();
        }).catch(function () {});
    }

    // ─── Eventos UI ───
    // Click en item del dropdown
    lista.addEventListener('click', function (e) {
        var item = e.target.closest('.notif-item');
        if (!item) return;
        var id  = parseInt(item.getAttribute('data-id'), 10);
        var url = item.getAttribute('data-url');
        marcarLeidas([id]);
        if (url) window.location.href = url;
    });

    // Botón "Marcar todas como leídas"
    if (btnMarcar) {
        btnMarcar.addEventListener('click', function (e) {
            e.stopPropagation();
            marcarLeidas([]);
        });
    }

    // ─── Iniciar ───
    cargar();
    setInterval(cargar, POLL_MS);

    // Recargar cuando la pestaña vuelve a estar visible
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) cargar();
    });
})();