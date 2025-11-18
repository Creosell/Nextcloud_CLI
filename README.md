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
Command for generating .exe file and upload version. Instead of @version put required version number (1.0.0, for example)
```bash
  python build_and_upload.py files build/dist/Nextcloud_CLI nextcloud_cli @version --upload
  ```
