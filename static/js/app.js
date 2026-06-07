document.addEventListener("DOMContentLoaded", () => {
    const searchForm = document.getElementById("js-search-form");
    if (searchForm) {
        searchForm.addEventListener("submit", (e) => {
            e.preventDefault();
            searchDocuments();
        });
    }
    const searchInput = document.querySelector('.js-search-input');
    if (searchInput) {
        searchInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                searchDocuments();
            }
        });
    }
});

function setUIState(isLoading, message = "") {
    const btn = document.querySelector('.btn-success');
    const metrics = document.querySelector('.metrics-output');
    
    if (btn) btn.disabled = isLoading;
    if (metrics && isLoading) metrics.innerText = message;
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

async function searchDocuments() {
    const query = document.querySelector('.js-search-input').value;
    const limit = document.querySelector('.limit-select-count').value;
    
    if (!query) return;
    
    const filterAuthor = document.querySelector('.js-filter-author').value;
    const filterFileName = document.querySelector('.js-filter-filename').value;
    const createdAfter = document.querySelector('.js-created-after').value;
    const createdBefore = document.querySelector('.js-created-before').value;
    const addedAfter = document.querySelector('.js-added-after').value;
    const addedBefore = document.querySelector('.js-added-before').value;
    
    const queryParams = new URLSearchParams({ query: query, limit: limit });
    
    if (filterAuthor) queryParams.append('filter_author', filterAuthor);
    if (filterFileName) queryParams.append('filter_file_name', filterFileName);
    if (createdAfter) queryParams.append('created_after', createdAfter);
    if (createdBefore) queryParams.append('created_before', createdBefore);
    if (addedAfter) queryParams.append('added_after', addedAfter);
    if (addedBefore) queryParams.append('added_before', addedBefore);
    
    setUIState(true, 'Интеллектуальный гибридный поиск...');
    try {
        const response = await fetch(`/api/search?${queryParams.toString()}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Ошибка сервера поискового ядра');
        
        const metricsElem = document.querySelector('.metrics-output');
        if (metricsElem) {
            metricsElem.innerText = `Найдено документов: ${data.results.length} | Время поиска в СУБД: ${data.execution_time_ms} мс`;
        }
        
        const container = document.querySelector('.js-results-container');
        container.innerHTML = '';
        
        if (data.results.length === 0) {
            container.innerHTML = '<div class="results-empty-stub">По вашему запросу ничего не найдено</div>';
            return;
        }
        
        data.results.forEach(doc => {
            const semRank = doc.semantic_rank ? `#${doc.semantic_rank}` : '—';
            const keyRank = doc.keyword_rank ? `#${doc.keyword_rank}` : '—';
            const tooltipText = "Индекс взаимного слияния рангов (Reciprocal Rank Fusion) — интегральный показатель релевантности текстового и семантического контуров.";
            
            const authorStr = doc.author ? `Автор: ${doc.author}` : 'Автор: Внешняя система';
            const dateStr = doc.created_at ? `Дата публикации: ${doc.created_at}` : 'Дата публикации: н/д';
            
            const displayTitle = doc.title || doc.file_name || `Документ #${doc.id}`;
            const fileStr = `📄 <a href="${doc.file_url}" target="_blank" class="result-title-link">${displayTitle}</a>`;
            
            const div = document.createElement('div');
            div.className = 'result-item';
            
            div.innerHTML = `
                <div class="result-item-header">
                    <div>
                        ${fileStr}
                        <div class="result-item-sub-meta">
                            ${authorStr} | ${dateStr}
                        </div>
                    </div>
                    <div title="${tooltipText}" class="vsr-tooltip-trigger vsr-score-badge">
                        Индекс ВСР: <span class="vsr-score-val">${doc.rrf_score}</span>
                    </div>
                </div>
                <div class="result-meta-block rank-info-block">
                    Служебные ранги СУБД // Векторная выдача: <span class="rank-semantic-val">${semRank}</span> | Лексическая выдача: <span class="rank-keyword-val">${keyRank}</span>
                </div>
            `;
            container.appendChild(div);
        });
    } catch (e) { 
        showToast(e.message, 'error', 0); 
    } finally { 
        setUIState(false); 
    }
}
