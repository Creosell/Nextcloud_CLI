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
  pyinstaller nextcloud_cli.py --onefile --name "Nextcloud_CLI" --distpath .
```
