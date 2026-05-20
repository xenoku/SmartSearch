function setUIState(isLoading, loadingText = '') {
    const buttons = document.querySelectorAll('button');
    buttons.forEach(btn => btn.disabled = isLoading);
    
    const loader = document.querySelector('.loader-container');
    const textElem = document.querySelector('.loader-text');
    
    if (isLoading) {
        textElem.innerText = loadingText;
        loader.style.display = 'flex';
    } else {
        loader.style.display = 'none';
    }
}

async function executePost(url, statusMessage) {
    setUIState(true, statusMessage);
    try {
        const response = await fetch(url, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Ошибка сервера');
        alert(data.message);
    } catch (e) { 
        alert('Ошибка: ' + e.message); 
    } finally { 
        setUIState(false); 
    }
}

async function manageIndex(action, statusMessage) {
    setUIState(true, statusMessage);
    try {
        const response = await fetch(`/api/system/index?action=${action}`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Ошибка сервера');
        alert(data.message);
    } catch (e) { 
        alert('Ошибка: ' + e.message); 
    } finally { 
        setUIState(false); 
    }
}

async function addDocument() {
    const inputElem = document.querySelector('.js-doc-input');
    const text = inputElem.value;
    if (!text) return alert('Введите текст!');
    
    setUIState(true, 'Векторизация нейросетью и запись в БД...');
    try {
        const response = await fetch('/api/add', { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ text_data: text })
        });
        
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Ошибка сервера');
        alert(data.message);
        inputElem.value = '';
    } catch (e) { 
        alert('Ошибка: ' + e.message); 
    } finally { 
        setUIState(false); 
    }
}

async function searchDocuments() {
    const query = document.querySelector('.js-search-input').value;
    const limit = document.querySelector('.limit-select').value;
    if (!query) return;
    
    setUIState(true, 'Семантический анализ запроса...');
    try {
        const response = await fetch(`/api/search?query=${encodeURIComponent(query)}&limit=${limit}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Ошибка сервера');
        
        document.querySelector('.metrics-output').innerText = `Время запроса в СУБД: ${data.execution_time_ms} мс (Выведено записей: ${data.results.length})`;
        
        const container = document.querySelector('.js-results-container');
        container.innerHTML = '';
        data.results.forEach(doc => {
            const div = document.createElement('div');
            div.className = 'result-item';
            div.innerHTML = `<div>${doc.text}</div><div class="meta-info">ID записи: ${doc.id}</div>`;
            container.appendChild(div);
        });
    } catch (e) { 
        alert('Ошибка: ' + e.message); 
    } finally { 
        setUIState(false); 
    }
}