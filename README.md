Create local environment
````bash
  python -m venv .venv
````
Activation of venv:\
Windows
````bash
   .venv\Scripts\activate
````
macOS and Linux
````bash
  source .venv/bin/activate
````
Install dependencies
````bash
  pip install -r requirements.txt
````
Command for generating .exe file
```bash
  python -m PyInstaller --name Nextcloud_CLI --distpath build_pyinstaller/dist --workpath build_pyinstaller/build --clean --upx-dir=.venv/Scripts/ --exclude-module=tkinter --exclude-module=unittest --exclude-module=PyQt5 --exclude-module=PySide6 --exclude-module=pydoc_data --upx-exclude=_uuid.pyd --upx-exclude=python3.dll --upx-exclude=VCRUNTIME140.dll --upx-exclude=VCRUNTIME140_1.dll nextcloud_cli.py 
```
