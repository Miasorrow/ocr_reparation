# OCR de documents

API FastAPI avec lecture locale Tesseract et analyse d’images locale avec Ollama.

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

## Configurer Ollama

Installer Ollama selon https://docs.ollama.com puis démarrer le serveur local :

```bash
ollama serve
```

Si Ollama fonctionne déjà en arrière-plan, cette commande est inutile.
Dans un autre terminal, télécharger votre modèle **vision**, capable de traiter
les images et les sorties JSON structurées, puis lancer l’API :

```bash
# Nom fictif : remplacer par le nom réel du modèle choisi.
export OLLAMA_MODEL="mon-modele-vision:latest"
ollama pull "$OLLAMA_MODEL"
ollama list
fastapi dev main.py
```

`mon-modele-vision:latest` est uniquement un exemple de configuration : aucun
modèle factice n’est exécuté et ce nom ne correspond pas à un modèle à télécharger.
Remplacer sa valeur avant `ollama pull`. Vous pouvez aussi modifier la valeur
par défaut dans `config.py`. Aucune clé AWS ou Anthropic n’est nécessaire.

Variables optionnelles (à exporter avant le lancement de FastAPI) :

- `OLLAMA_BASE_URL` : `http://127.0.0.1:11434` par défaut.
- `OLLAMA_TIMEOUT_SECONDS` : `120` par défaut, à augmenter si le modèle est lent.

Les routes `POST /documents/classify` et `POST /documents/analyse` envoient
l’image prétraitée à Ollama. La classification retourne `source: "ollama_vision"`.
L’analyse conserve ses champs métier et impose leur schéma JSON au modèle.
Un serveur inaccessible renvoie 503, un délai dépassé 504, et un modèle absent
ou une réponse invalide 502. L’OCR Tesseract reste indépendant d’Ollama.

Documentation : https://docs.ollama.com/api/chat et
https://docs.ollama.com/capabilities/structured-outputs

## Tests du service OCR

```bash
python3 -m unittest discover -s tests -v
```

Ces tests simulent Tesseract ; vérifier séparément l'extraction réelle sur une
image synthétique après installation du moteur.

Documentation du moteur : https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html

## Pré-saisie locale par OCR et modèle texte

La commande synchrone `python -m extraction_cli ID` analyse un document déjà enregistré : fichier JPEG/PNG → Tesseract → texte OCR → Ollama → cinq champs → SQLite. Elle crée une extraction à chaque lancement, conserve les étapes réussies en cas d'échec et ne crée ni ne modifie de validation humaine. La sortie de commande ne contient pas les données extraites. La relecture humaine reste nécessaire ; la qualité dépend de l'image et de Tesseract. Ce traitement ne vérifie aucune conformité administrative.

Depuis `app/`, installer les dépendances Python de `requirements.txt` comme indiqué plus haut. Sur Debian/Ubuntu, si nécessaire :

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-fra
# Installer Ollama en suivant https://ollama.com/download si nécessaire.
ollama serve                 # dans un terminal dédié, si le serveur n'est pas déjà lancé
ollama pull qwen3:4b-instruct # dans un autre terminal ; téléchargement explicite
ollama list
curl http://localhost:11434/api/version
```

La commande utilise le modèle texte `qwen3:4b-instruct` par défaut ; les routes vision historiques ont leurs propres besoins et peuvent nécessiter un autre modèle. Le fichier `.env.example` répertorie les paramètres. Il n'est pas chargé automatiquement : exporter les variables souhaitées, par exemple `set -a; . ./.env.example; set +a`. `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_NUM_CTX` et `OLLAMA_TEMPERATURE` configurent le modèle. `TESSERACT_LANG` (défaut `fra`), `TESSERACT_TIMEOUT_SECONDS`, `OCR_MAX_BYTES` et `OCR_MAX_PIXELS` configurent l'OCR. La préparation se limite à la validation du format, à la correction EXIF et à la conversion RGB ; Tesseract utilise `--psm 3`. Pour les routes historiques, leur comportement OCR par défaut reste `fra+eng`.

Le connecteur utilise `/api/tags` pour relever le digest réellement disponible du modèle, et `/api/chat` sans streaming, avec schéma JSON et options `num_ctx`, `temperature` et `num_predict`. La disponibilité de ces options dépend de la version du serveur Ollama. Une limite conservatrice en octets UTF-8, incluant prompt et schéma et réservant 1024 unités, rejette les entrées susceptibles de dépasser le contexte avec `LLM_CONTEXT_EXCEEDED` ; elle peut refuser des textes qui tiendraient après tokenisation. Aucun texte n'est tronqué par ce module. Dans Docker, `localhost` désigne le conteneur : configurer `OLLAMA_BASE_URL` avec une adresse accessible du serveur hôte, par exemple `http://host.docker.internal:11434` si cette résolution est configurée.

Pour un test réel sur une image fournie, initialiser la base, importer le document puis lancer la commande. Remplacer le chemin par une image accessible :

```bash
python3 -m persistence.database
python3 - /chemin/vers/image.png <<'PY'
import hashlib
import sys
from pathlib import Path
from persistence.database import Database
image = Path(sys.argv[1]).resolve()
with image.open('rb') as f:
    digest = hashlib.file_digest(f, 'sha256').hexdigest()
print(Database().document(digest, image)['id'])
PY
python3 -m extraction_cli ID_A_REMPLACER
```

Le code de sortie vaut 0 en cas de succès et 1 en cas d'échec de traitement. Consulter les résultats via `Database().historique(ID)` ; ils peuvent contenir des données personnelles. Le fichier SQLite et l'image doivent être protégés localement. Les tests simulés, indépendants d'Ollama et de Tesseract, se lancent par `python3 -m unittest discover -s tests -v`. Voir [la documentation SQLite](persistence/README.md) pour les opérations, la configuration et les limites.

### Envoyer directement une image à l'API

Démarrer l'API et le serveur Ollama comme indiqué ci-dessus, puis ouvrir `http://127.0.0.1:8000/docs`. Dans **Pré-saisie**, choisir `POST /documents/extraire`, cliquer sur **Try it out**, sélectionner une image JPEG ou PNG, puis **Execute**. En ligne de commande :

```bash
curl -X POST http://127.0.0.1:8000/documents/extraire \
  -F 'file=@/chemin/vers/image.png'
```

L'API vérifie l'image, l'enregistre sous un nom généré dans `app/var/images/` et initialise SQLite si nécessaire. Le répertoire peut être modifié avec `OCR_IMAGE_DIR`, et la base avec `OCR_DB_PATH`. L'envoi est synchrone : la réponse arrive après l'OCR et Ollama et peut prendre plusieurs minutes selon les délais configurés. Elle indique `document_id`, `extraction_id`, `statut`, `code_erreur` et les cinq champs. `statut: succeeded` indique un résultat enregistré ; `statut: failed` indique un échec enregistré, détaillé par `code_erreur` (par exemple `OLLAMA_UNAVAILABLE`). Une image invalide est rejetée avant enregistrement avec une erreur HTTP.

Un fichier identique retrouve le même document grâce à son empreinte et crée une nouvelle extraction. Si l'image enregistrée précédemment a disparu, le nouvel envoi restaure son chemin. Le nom d'origine n'est pas utilisé. Les résultats sont des propositions à relire, pas des validations humaines. Les images et la base peuvent contenir des données personnelles ; leur suppression et leur protection doivent être organisées localement. La suppression SQLite seule ne supprime pas le fichier image.

Pour `/documents/extraire` et la commande d'extraction, Tesseract tente également de détecter les rotations de 90°, 180° ou 270° avec ses données `osd`, après correction EXIF. Si la détection échoue ou que sa confiance est inférieure au seuil, l'image reste inchangée. Le délai OCR couvre les deux étapes. Sur Debian/Ubuntu, installer au besoin `tesseract-ocr-osd` ; `tesseract --list-langs` doit afficher `osd`. La rotation peut être désactivée avec `TESSERACT_AUTO_ROTATE=0`, et le seuil ajusté avec `TESSERACT_ORIENTATION_CONFIDENCE` (4 par défaut). Un seuil bas peut entraîner des rotations incorrectes ; contrôler le résultat. La route historique `/documents/ocr` conserve son comportement initial.
