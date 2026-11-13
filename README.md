# OCR de documents

API FastAPI avec lecture locale Tesseract et analyse Claude via AWS Bedrock.

## Installation locale (Ubuntu / Debian)

Exécuter depuis la racine du dépôt (le dossier contenant `main.py`) :

```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
tesseract --list-langs
fastapi dev main.py
```

Les dépendances Python ne sont pas encore verrouillées. Les langues `fra` et
`eng` doivent apparaître dans la liste Tesseract.

`fastapi[standard]` inclut la commande `fastapi` et Uvicorn. Le mode `dev`
recharge automatiquement le serveur après modification du code.
Pour lancer sans rechargement en restant sur l'interface locale :

```bash
fastapi run main.py --host 127.0.0.1
```

## Lire une image

Ouvrir http://127.0.0.1:8000/docs et essayer `POST /documents/ocr`, ou :

```bash
curl -X POST http://127.0.0.1:8000/documents/ocr \
  -F 'file=@/chemin/document.png'
```

La réponse contient `text`, `source`, `language` et `duration_ms`.
JPEG/PNG uniquement, maximum 10 Mo et 25 mégapixels. Délai OCR : 60 secondes.
Les fichiers temporaires sont supprimés après traitement. Aucun appel AWS
n'est effectué pour cette route. Le texte n'est pas stocké et les cinq champs
métier ne sont pas encore structurés.

Les routes `/documents/classify` et `/documents/analyse` restent disponibles
avec les identifiants et autorisations AWS Bedrock configurés sur la machine.
Le client AWS est initialisé seulement lors de leur première utilisation.

## Tests du service OCR

```bash
python3 -m unittest discover -s tests -v
```

Ces tests simulent Tesseract ; vérifier séparément l'extraction réelle sur une
image synthétique après installation du moteur.

Documentation du moteur : https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html
