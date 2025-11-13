# setup.py
import sys
from cx_Freeze import setup, Executable

# Target OS setup
base = None

# Options for the build
build_exe_options = {
    # Сохраняем исключения
    "excludes": ["tkinter", "unittest", "test", "PyQt5", "PySide6", "PySide2", "pydoc", "distutils"],

    # !!! Ключевое ИСПРАВЛЕНИЕ: Включаем все скрытые зависимости, выявленные pip !!!
    "includes": [
        "loguru", "nc_py_api", "dotenv", "os", "sys", "pathlib", "argparse",
        "requests", "urllib3", "idna",

        # Добавляем модули, выявленные через pip:
        "fastapi", "httpx", "pydantic", "httpcore", "anyio", "sniffio"
    ],
    "silent": True,  # Suppress some output during build

    # Дополнительная настройка: включение пакетов
    # Это может быть более надежным способом, чем "includes"
    "packages": [
        "httpx",
        "pydantic",
        "httpcore",
        "anyio",
        "loguru"
    ]
}

setup(
    name="Nextcloud_CLI",
    version="1.0",
    description="Nextcloud Uploader/Downloader CLI",
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "nextcloud_cli.py",
            base=base,
            target_name="Nextcloud_CLI.exe"
        )
    ]
)