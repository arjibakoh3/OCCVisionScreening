# Vision Screening App (Streamlit)

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Community Cloud
1) Create a GitHub repo and push this folder.
2) Go to https://share.streamlit.io (or Streamlit Cloud).
3) New app -> select your repo -> set `app.py`.
4) Add Secrets if you use Firebase / Google Drive (see below).

## Secrets (Streamlit Cloud)
Add these in the Streamlit Cloud "Secrets" UI (not in the repo):

```
[firebase]
service_account_json = "PASTE_JSON_HERE"
collection = "vision_records"
```

If you want Google Drive too:
```
[gdrive]
service_account_json = "PASTE_JSON_HERE"
folder_id = "YOUR_FOLDER_ID"
```

Note: In the app UI you can also paste JSON, but for Cloud use secrets.
