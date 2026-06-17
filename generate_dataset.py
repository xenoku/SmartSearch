import os
import re
import json
import urllib.request
import wikipedia
from wikipedia.exceptions import DisambiguationError, PageError

def get_random_wiki_titles(lang, count):
    """Получение списка случайных заголовков через официальное API API Википедии"""
    url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=random&rnnamespace=0&rnlimit={count}&format=json"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; SmartSearchBot/1.0)'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return [page['title'] for page in data['query']['random']]
    except Exception as e:
        print(f"Ошибка API ({lang.upper()}): {e}")
        return []

def create_wiki_dataset(count_per_lang=50):
    print("Старт генерации Wiki-датасета...")
    output_dir = "wiki_dataset"
    os.makedirs(output_dir, exist_ok=True)
    
    wikipedia.requests.utils.default_headers().update({
        'User-Agent': 'Mozilla/5.0 SmartSearchBot/1.0 (VKR Project; Hybrid Search Dataset Generator)'
    })
    
    for lang in ["ru", "en"]:
        print(f"\nСбор документов для языка: {lang.upper()}")
        wikipedia.set_lang(lang)
        downloaded = 0
        
        while downloaded < count_per_lang:
            titles = get_random_wiki_titles(lang, 20)
            if not titles:
                print("Не удалось получить заголовки, повторная попытка...")
                continue
                
            for title in titles:
                if downloaded >= count_per_lang:
                    break
                try:
                    page = wikipedia.page(title, auto_suggest=False)
                    
                    if not page.content or len(page.content.strip()) < 500: 
                        continue
                    
                    clean_title = re.sub(r'[\/*?:"<>|]', '', title).strip()[:50]
                    fn = f"{lang}_{clean_title}.txt"
                    
                    with open(os.path.join(output_dir, fn), "w", encoding="utf-8") as f:
                        f.write(f"TITLE: {title}\nURL: {page.url}\n{'-'*40}\n\n{page.content}")
                    
                    downloaded += 1
                    print(f"[{downloaded}/{count_per_lang}] Скачано: {fn}")
                    
                except (DisambiguationError, PageError):
                    continue
                except Exception as e:
                    continue
                    
    print("\nГенерация успешно завершена! В папке 'wiki_dataset' собрано 100 файлов.")

if __name__ == "__main__":
    create_wiki_dataset(50)