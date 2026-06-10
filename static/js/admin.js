/**
 * Административный интерфейс экосистемы умного поиска.
 * Управление жизненным циклом событий, сессионными Cookie и авторизацией.
 */

let currentPage = 1;
let totalPages = 1;
let currentSortBy = "id";
let currentSortOrder = "desc";
let activeEditingDocId = null;

// Централизованная регистрация слушателей событий (DOM Event Listeners)
document.addEventListener("DOMContentLoaded", () => {
    if (getCookie("admin_session")) {
        showAdminPanel();
    }

    // Аутентификация администратора
    const loginForm = document.getElementById("js-admin-login-form");
    if (loginForm) {
        loginForm.addEventListener("submit", (e) => {
            e.preventDefault();
            loginAdmin();
        });
    }
    
    const btnLogout = document.getElementById("js-btn-logout");
    if (btnLogout) btnLogout.addEventListener("click", logoutAdmin);

    // Конфигурация и обслуживание СУБД
    const btnSeed = document.getElementById("js-btn-seed");
    if (btnSeed) btnSeed.addEventListener("click", seedDatabase);
    
    const btnHNSWEnable = document.getElementById("js-btn-hnsw-enable");
    if (btnHNSWEnable) btnHNSWEnable.addEventListener("click", () => toggleHNSWIndex(true));
    
    const btnHNSWDisable = document.getElementById("js-btn-hnsw-disable");
    if (btnHNSWDisable) btnHNSWDisable.addEventListener("click", () => toggleHNSWIndex(false));
    
    const btnClear = document.getElementById("js-btn-clear");
    if (btnClear) btnClear.addEventListener("click", clearSystemData);

    // Загрузка новых документов
    const btnUpload = document.getElementById("js-btn-upload");
    if (btnUpload) btnUpload.addEventListener("click", uploadFile);
    
    const chkFolderMode = document.getElementById("js-upload-folder-mode");
    if (chkFolderMode) chkFolderMode.addEventListener("change", (e) => toggleFolderMode(e.target));

    // Маска живого поиска по таблице документов
    const tableMask = document.getElementById("js-table-mask");
    if (tableMask) tableMask.addEventListener("input", () => loadTableData(1));

    // Управление пагинацией репозитория
    const btnPrev = document.getElementById("js-btn-prev");
    if (btnPrev) btnPrev.addEventListener("click", () => changePage(-1));
    
    const btnNext = document.getElementById("js-btn-next");
    if (btnNext) btnNext.addEventListener("click", () => changePage(1));

    // Сортировка колонок таблицы
    document.querySelectorAll(".js-th-sort").forEach(th => {
        th.addEventListener("click", () => handleSort(th.getAttribute("data-sort")));
    });

    // Модальное окно редактирования записей
    const btnModalCancel = document.getElementById("js-modal-btn-cancel");
    if (btnModalCancel) btnModalCancel.addEventListener("click", closeEditModal);
    
    const btnModalSubmit = document.getElementById("js-modal-btn-submit");
    if (btnModalSubmit) btnModalSubmit.addEventListener("click", submitEditModal);
});

function getCookie(name) {
    let matches = document.cookie.match(new RegExp(
        "(?:^|; )" + name.replace(/([\.$?*|{}\(\)\[\]\\\/\+^])/g, '\\$1') + "=([^;]*)"
    ));
    return matches ? decodeURIComponent(matches[1]) : undefined;
}

/**
 * Фабрика формирования защищенных заголовков авторизации Bearer (M2M / API Shield).
 * Обеспечивает стабильность API при переходе СУБД и бэкенда на HttpOnly сессии.
 */
function getAuthHeaders(contentType = "application/json") {
    const token = getCookie("admin_session");
    const headers = {};
    if (contentType) headers["Content-Type"] = contentType;
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
}

function showAdminPanel() {
    const authBlock = document.getElementById("admin-auth-block");
    const panelBlock = document.getElementById("admin-panel-block");
    
    if (authBlock) authBlock.classList.add("hidden");
    if (panelBlock) panelBlock.classList.remove("hidden");
    
    loadTableData(1);
}

function showToast(message, type = "success", duration = 4000) {
    const container = document.getElementById("js-toast-container");
    if (!container) return;
    
    const toast = document.createElement("div");
    toast.className = `toast-item toast-${type}`;
    
    if (duration === 0) {
        toast.innerHTML = `<span>${message}</span><span class="toast-close-btn" onclick="this.parentElement.remove()">×</span>`;
    } else {
        toast.innerText = message;
    }
    
    container.appendChild(toast);
    setTimeout(() => toast.classList.add("show"), 10);
    
    if (duration > 0) {
        setTimeout(() => {
            toast.classList.remove("show");
            toast.addEventListener("transitionend", () => toast.remove());
        }, duration);
    }
}

/**
 * Динамический рендеринг репозитория СУБД, постраничная пагинация и сортировка.
 */

async function loadTableData(page = 1) {
    currentPage = page;
    const mask = document.getElementById("js-table-mask").value;
    
    const queryParams = new URLSearchParams({ 
        page: page, 
        size: 10, 
        sort_by: currentSortBy, 
        sort_order: currentSortOrder 
    });
    if (mask) queryParams.append('search_mask', mask);
    
    try {
        const response = await fetch(`/api/admin/documents?${queryParams.toString()}`, {
            headers: getAuthHeaders()
        });
        if (!response.ok) throw new Error("Ошибка загрузки данных репозитория документов");
        const data = await response.json();
        
        totalPages = Math.ceil(data.total / data.size) || 1;
        
        document.getElementById("js-pagination-info").innerText = `Страница ${data.page} из ${totalPages} (Всего документов: ${data.total})`;
        document.getElementById("js-btn-prev").disabled = (currentPage === 1);
        document.getElementById("js-btn-next").disabled = (currentPage === totalPages);
        
        const tbody = document.getElementById("js-admin-table-body");
        tbody.innerHTML = "";
        
        if (data.items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="table-empty-stub-cell">Документы отсутствуют</td></tr>`;
            return;
        }
        
        data.items.forEach(doc => {
            const tr = document.createElement("tr");
            const docTitle = doc.title || doc.file_name || 'Без названия';
            const docAuthor = doc.author || '—';
            
            tr.innerHTML = `
                <td class="cell-bold">${doc.id}</td>
                <td>
                    <div class="text-ellipsis-block" title="${docTitle}">
                        <a href="${doc.file_url}" target="_blank" class="table-doc-link">📑 ${docTitle}</a>
                    </div>
                    <span class="table-locale-badge">[Локаль: ${doc.language}]</span>
                </td>
                <td>
                    <div class="text-ellipsis-block" title="${docAuthor}">
                        ${docAuthor}
                    </div>
                </td>
                <td class="text-muted-gray">${doc.created_at || '—'}</td>
                <td class="text-muted-gray">${doc.added_at || '—'}</td>
                <td>
                    <div class="actions-flex-container">
                        <button class="btn-table-edit data-btn-edit" 
                                data-id="${doc.id}" 
                                data-title="${docTitle.replace(/'/g, "\\'")}" 
                                data-author="${docAuthor.replace(/'/g, "\\'")}" 
                                data-created="${doc.created_at || ''}" 
                                data-added="${doc.added_at || ''}">Изменить</button>
                        <button class="btn-table-delete data-btn-delete" data-id="${doc.id}">Удалить</button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });

        tbody.querySelectorAll(".data-btn-edit").forEach(btn => {
            btn.addEventListener("click", () => editDocument(
                btn.getAttribute("data-id"), btn.getAttribute("data-title"),
                btn.getAttribute("data-author"), btn.getAttribute("data-created"), btn.getAttribute("data-added")
            ));
        });
        tbody.querySelectorAll(".data-btn-delete").forEach(btn => {
            btn.addEventListener("click", () => deleteDocument(btn.getAttribute("data-id")));
        });

    } catch (e) {
        showToast(e.message, "error", 0);
    }
}

function changePage(direction) {
    const targetPage = currentPage + direction;
    if (targetPage >= 1 && targetPage <= totalPages) {
        loadTableData(targetPage);
    }
}

function handleSort(columnName) {
    if (currentSortBy === columnName) {
        currentSortOrder = currentSortOrder === "asc" ? "desc" : "asc";
    } else {
        currentSortBy = columnName;
        currentSortOrder = "asc";
    }
    updateSortIcons();
    loadTableData(currentPage);
}

function updateSortIcons() {
    const columns = ["id", "file_name", "author", "created_at", "added_at"];
    columns.forEach(col => {
        const iconElem = document.getElementById(`sort-icon-${col}`);
        if (!iconElem) return;
        if (col === currentSortBy) {
            iconElem.innerText = currentSortOrder === "asc" ? " ▲" : " ▼";
        } else {
            iconElem.innerText = "";
        }
    });
}

async function deleteDocument(docId) {
    if (!confirm(`Вы действительно хотите удалить документ ID #${docId} из базы данных и хранилища?`)) return;
    try {
        const response = await fetch(`/api/admin/documents/${docId}`, { 
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Ошибка удаления");
        
        showToast(data.message, "success");
        loadTableData(currentPage);
    } catch (e) {
        showToast(e.message, "error", 0);
    }
}

/**
 * Модальные окна, авторизация, каскадная очистка, сидирование и пакетный конвейер.
 */

function editDocument(docId, title, author, createdDate, addedDate) {
    activeEditingDocId = docId;
    document.getElementById("modal-doc-id").innerText = docId;
    document.getElementById("modal-input-title").value = title;
    document.getElementById("modal-input-author").value = author === '—' ? '' : author;
    document.getElementById("modal-input-created").value = createdDate;
    document.getElementById("modal-input-added").value = addedDate;
    document.getElementById("js-edit-modal").classList.add("active");
}

function closeEditModal() {
    activeEditingDocId = null;
    document.getElementById("js-edit-modal").classList.remove("active");
}

async function submitEditModal() {
    if (!activeEditingDocId) return;
    const title = document.getElementById("modal-input-title").value.trim();
    const author = document.getElementById("modal-input-author").value.trim();
    const created_at = document.getElementById("modal-input-created").value;
    const added_at = document.getElementById("modal-input-added").value;
    
    if (!title) return showToast("Название документа не может быть пустым!", "error");
    
    try {
        const response = await fetch(`/api/admin/documents/${activeEditingDocId}`, {
            method: 'PUT', 
            headers: getAuthHeaders(),
            body: JSON.stringify({ 
                title: title, 
                author: author || null, 
                created_at: created_at ? `${created_at}T00:00:00` : null,
                added_at: added_at ? `${added_at}T00:00:00` : null
            })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Ошибка обновления");
        
        showToast("Метаданные успешно обновлены", "success"); 
        closeEditModal(); 
        loadTableData(currentPage);
    } catch (e) { 
        showToast(e.message, "error", 0); 
    }
}

async function loginAdmin() {
    const passElem = document.getElementById("js-admin-pass");
    const rememberElem = document.getElementById("js-remember-me");
    const password = passElem.value;
    const rememberMe = rememberElem ? rememberElem.checked : false;
    
    if (!password) return showToast("Введите пароль!", "error");
    try {
        const response = await fetch("/api/admin/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password: password, remember_me: rememberMe })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Ошибка авторизации");
        
        window.location.reload();
    } catch (e) {
        showToast(e.message, "error", 0);
    }
}

async function logoutAdmin() {
    try {
        await fetch("/api/admin/logout", { method: "POST", headers: getAuthHeaders() });
    } catch (e) {
        console.error("Не удалось закрыть сессию на сервере:", e);
    } finally {
        document.cookie = "admin_session=; max-age=-1; path=/;";
        window.location.reload();
    }
}

async function seedDatabase() {
    if (!confirm("Вы уверены, что хотите сгенерировать 10 000 тестовых записей?")) return;
    const btnSeed = document.getElementById("js-btn-seed");
    const metrics = document.querySelector('.admin-metrics');
    
    btnSeed.disabled = true;
    const oldBtnText = btnSeed.innerText;
    btnSeed.innerText = "Идет генерация базы...";
    if (metrics) metrics.innerText = "Генерация 10,000 чанков в СУБД...";
    
    try {
        const response = await fetch("/api/admin/seed", { method: "POST", headers: getAuthHeaders() });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Ошибка сидирования датасета");
        
        showToast(data.message, "success");
        if (metrics) metrics.innerText = "База успешно заполнена.";
        loadTableData(1);
    } catch (e) {
        showToast(e.message, "error", 0);
        if (metrics) metrics.innerText = "";
    } finally {
        btnSeed.disabled = false;
        btnSeed.innerText = oldBtnText;
    }
}

async function toggleHNSWIndex(isEnable) {
    const method = isEnable ? "POST" : "DELETE";
    const btnEnable = document.getElementById("js-btn-hnsw-enable");
    const btnDisable = document.getElementById("js-btn-hnsw-disable");
    const metrics = document.querySelector('.admin-metrics');
    
    if (btnEnable) btnEnable.disabled = true;
    if (btnDisable) btnDisable.disabled = true;
    if (metrics) metrics.innerText = isEnable ? "Построение графа HNSW в PostgreSQL..." : "Удаление индекса...";
    
    try {
        const response = await fetch("/api/admin/index/hnsw", { method: method, headers: getAuthHeaders() });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Ошибка индексов СУБД");
        
        showToast(data.message, "success");
        if (metrics) metrics.innerText = isEnable ? "HNSW-индекс активен." : "HNSW-индекс отключен.";
    } catch (e) {
        showToast(e.message, "error", 0);
        if (metrics) metrics.innerText = "";
    } finally {
        if (btnEnable) btnEnable.disabled = false;
        if (btnDisable) btnDisable.disabled = false;
    }
}

async function clearSystemData() {
    if (!confirm("ВНИМАНИЕ! Вы собираетесь стереть БД и удалить все файлы из storage. Продолжить?")) return;
    if (!confirm("ПОДТВЕРДИТЕ ЕЩЕ РАЗ: Вы действительно хотите уничтожить данные?")) return;
    
    const btnClear = document.getElementById("js-btn-clear");
    const metrics = document.querySelector('.admin-metrics');
    
    if (btnClear) btnClear.disabled = true;
    if (metrics) metrics.innerText = "Идет каскадное удаление данных...";
    
    try {
        const response = await fetch("/api/admin/clear", { method: "DELETE", headers: getAuthHeaders() });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Ошибка при очистке системы");
        
        showToast(data.message, "success");
        if (metrics) metrics.innerText = "Система полностью очищена.";
        currentPage = 1;
        totalPages = 1;
        await loadTableData(1);
    } catch (e) {
        showToast(e.message, "error", 0);
        if (metrics) metrics.innerText = "";
    } finally {
        if (btnClear) btnClear.disabled = false;
    }
}

function toggleFolderMode(checkbox) {
    const fileElem = document.getElementById('js-file-selector');
    if (!fileElem) return;
    if (checkbox.checked) {
        fileElem.setAttribute('webkitdirectory', '');
        fileElem.setAttribute('directory', '');
        fileElem.setAttribute('multiple', '');
    } else {
        fileElem.removeAttribute('webkitdirectory');
        fileElem.removeAttribute('directory');
        fileElem.removeAttribute('multiple');
    }
    fileElem.value = "";
}

async function uploadFile() {
    const fileElem = document.getElementById('js-file-selector');
    const titleElem = document.querySelector('.js-doc-title');
    const authorElem = document.querySelector('.js-doc-author');
    const createdElem = document.querySelector('.js-doc-created');
    const btnSubmit = document.getElementById("js-btn-upload");
    
    if (!fileElem || !fileElem.files || fileElem.files.length === 0) {
        return showToast('Пожалуйста, выберите файл или папку для загрузки!', "error");
    }
    
    const formData = new FormData();
    let validFilesCount = 0;
    const allowedExtensions = ['.txt', '.pdf', '.docx'];
    
    for (let i = 0; i < fileElem.files.length; i++) {
        const file = fileElem.files[i];
        const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
        if (allowedExtensions.includes(ext)) {
            formData.append('files', file); 
            validFilesCount++;
        }
    }
    
    if (validFilesCount === 0) {
        return showToast('Не найдено поддерживаемых файлов (.txt, .pdf, .docx)!', "error");
    }
    
    if (titleElem && titleElem.value) formData.append('custom_title', titleElem.value);
    if (authorElem && authorElem.value) formData.append('author', authorElem.value);
    if (createdElem && createdElem.value) formData.append('created_at', `${createdElem.value}T00:00:00`);
    
    btnSubmit.disabled = true;
    const oldBtnText = btnSubmit.innerText;
    btnSubmit.innerText = `Обработка пакета (${validFilesCount} файлов)...`;
    
    try {
        const response = await fetch('/api/upload/bulk', { 
            method: 'POST', 
            headers: getAuthHeaders(null), 
            body: formData 
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Ошибка обработки пакета');
        
        showToast(data.message, "success");
        fileElem.value = '';
        if (titleElem) titleElem.value = '';
        if (authorElem) authorElem.value = '';
        if (createdElem) createdElem.value = '';
        loadTableData(1);
    } catch (e) {
        showToast(e.message, "error", 0);
    } finally {
        btnSubmit.disabled = false;
        btnSubmit.innerText = oldBtnText;
    }
}