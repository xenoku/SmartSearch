from pathlib import Path

def get_project_files(root_dir: str | Path, ignore_list: set[str]) -> list[str]:
    root = Path(root_dir).resolve()
    file_paths = []
    
    for path in root.rglob("*"):
        if any(ignored in path.relative_to(root).parts for ignored in ignore_list):
            continue
            
        if path.is_file():
            relative_path = path.relative_to(root).as_posix()
            file_paths.append(relative_path)
            
    return sorted(file_paths)

if __name__ == "__main__":
    IGNORED_ITEMS = {
        ".git", 
        ".venv", 
        "venv", 
        "__pycache__", 
        ".idea", 
        ".vscode",
        "tree.py",
        "wiki_dataset"
    }
    
    project_root = "." 
    files = get_project_files(project_root, IGNORED_ITEMS)
    
    print(f"Найдено файлов: {len(files)}\n")
    for file in files:
        print(file)