"""Accès SQLite autonome ; aucune donnée métier n'est journalisée."""
import csv
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

FIELDS = ('immatriculation', 'date_premiere_immatriculation', 'marque', 'modele_vehicule', 'numero_formule')
DEFAULT_PATH = Path(__file__).resolve().parent.parent / 'var' / 'ocr_evaluation.sqlite3'


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


class Database:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('OCR_DB_PATH', DEFAULT_PATH))

    @contextmanager
    def connect(self, immediate=False):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA foreign_keys = ON')
            if immediate:
                conn.execute('BEGIN IMMEDIATE')
            else:
                conn.execute('BEGIN')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # executescript commits first; include an explicit transaction in the script.
        conn = sqlite3.connect(self.path, timeout=30)
        try:
            conn.execute('PRAGMA foreign_keys = ON')
            conn.executescript('BEGIN IMMEDIATE;\n' + (Path(__file__).parent / 'schema.sql').read_text(encoding='utf-8') + '\nCOMMIT;')
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def document(self, empreinte_sha256, chemin_image):
        if not re.fullmatch(r'[0-9a-f]{64}', empreinte_sha256):
            raise ValueError('empreinte SHA-256 hexadécimale minuscule attendue')
        with self.connect(immediate=True) as c:
            c.execute('INSERT INTO documents(nom_fichier,chemin_image,empreinte_sha256,date_import) VALUES(?,?,?,?) ON CONFLICT(empreinte_sha256) DO NOTHING', (uuid4().hex, str(chemin_image), empreinte_sha256, utc_now()))
            return dict(c.execute('SELECT * FROM documents WHERE empreinte_sha256=?', (empreinte_sha256,)).fetchone())

    def importer_image(self, empreinte_sha256, chemin_image):
        """Déduplique et répare le chemin si le fichier d'origine a disparu."""
        if not re.fullmatch(r'[0-9a-f]{64}', empreinte_sha256):
            raise ValueError('empreinte SHA-256 invalide')
        with self.connect(immediate=True) as c:
            row = c.execute('SELECT * FROM documents WHERE empreinte_sha256=?', (empreinte_sha256,)).fetchone()
            if row is None:
                c.execute('INSERT INTO documents(nom_fichier,chemin_image,empreinte_sha256,date_import) VALUES(?,?,?,?)', (Path(chemin_image).name, str(chemin_image), empreinte_sha256, utc_now()))
            elif not Path(row['chemin_image']).is_file():
                c.execute('UPDATE documents SET nom_fichier=?, chemin_image=? WHERE id=?', (Path(chemin_image).name, str(chemin_image), row['id']))
            return dict(c.execute('SELECT * FROM documents WHERE empreinte_sha256=?', (empreinte_sha256,)).fetchone())

    def modele(self, fournisseur, nom, version=None):
        if not fournisseur or not nom:
            raise ValueError('fournisseur et nom obligatoires')
        version = version or ''
        with self.connect(immediate=True) as c:
            c.execute('INSERT INTO modeles(fournisseur,nom,version) VALUES(?,?,?) ON CONFLICT(fournisseur,nom,version) DO NOTHING', (fournisseur, nom, version))
            return dict(c.execute('SELECT * FROM modeles WHERE fournisseur=? AND nom=? AND version=?', (fournisseur, nom, version)).fetchone())

    def creer_extraction(self, document_id, modele_id, version_prompt, configuration):
        config = json.dumps(configuration, ensure_ascii=False, allow_nan=False)
        with self.connect() as c:
            return c.execute('INSERT INTO extractions(document_id,modele_id,version_prompt,configuration_json,statut,date_execution) VALUES(?,?,?,?,?,?)', (document_id, modele_id, version_prompt, config, 'pending', utc_now())).lastrowid

    def etat_extraction(self, extraction_id, statut, **valeurs):
        allowed = set(FIELDS) | {'texte_ocr', 'reponse_brute', 'duree_ocr_ms', 'duree_modele_ms', 'code_erreur'}
        if set(valeurs) - allowed:
            raise ValueError('champ de résultat inconnu')
        if 'code_erreur' in valeurs and valeurs['code_erreur'] is not None and not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', valeurs['code_erreur']):
            raise ValueError('code erreur symbolique attendu')
        transitions = {'pending': {'running', 'failed', 'interrupted'}, 'running': {'succeeded', 'failed', 'interrupted'}}
        with self.connect(immediate=True) as c:
            row = c.execute('SELECT statut FROM extractions WHERE id=?', (extraction_id,)).fetchone()
            if row is None:
                raise ValueError('extraction inconnue')
            if statut not in transitions.get(row['statut'], set()):
                raise ValueError('transition de statut invalide')
            if statut != 'succeeded' and set(valeurs) & set(FIELDS):
                raise ValueError('les champs métier sont réservés au résultat réussi')
            assignments = ','.join(f'{key}=?' for key in valeurs)
            c.execute('UPDATE extractions SET statut=?' + (',' + assignments if assignments else '') + ' WHERE id=?', (statut, *valeurs.values(), extraction_id))

    def document_par_id(self, document_id):
        with self.connect() as c:
            row = c.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
            return dict(row) if row else None

    def enregistrer_ocr(self, extraction_id, texte, duree_ms):
        with self.connect(immediate=True) as c:
            result = c.execute("UPDATE extractions SET texte_ocr=?, duree_ocr_ms=? WHERE id=? AND statut='running'", (texte, duree_ms, extraction_id))
            if not result.rowcount:
                raise ValueError('extraction non active')

    def valider(self, document_id, valeurs, etats, extraction_id=None):
        if set(valeurs) != set(FIELDS) or set(etats) != set(FIELDS):
            raise ValueError('les cinq champs et leurs états sont obligatoires')
        for field in FIELDS:
            value, state = valeurs[field], etats[field]
            if state not in ('known', 'absent', 'unreadable') or (state == 'known' and (not isinstance(value, str) or not value.strip())) or (state != 'known' and value is not None):
                raise ValueError('état et valeur incohérents pour ' + field)
        with self.connect(immediate=True) as c:
            revision = c.execute('SELECT COALESCE(MAX(revision),0)+1 FROM validations WHERE document_id=?', (document_id,)).fetchone()[0]
            return c.execute('INSERT INTO validations(document_id,extraction_id,revision,immatriculation,date_premiere_immatriculation,marque,modele_vehicule,numero_formule,etats_champs_json,date_validation) VALUES(?,?,?,?,?,?,?,?,?,?)', (document_id, extraction_id, revision, *(valeurs[f] for f in FIELDS), json.dumps(etats, ensure_ascii=False), utc_now())).lastrowid

    def derniere_validation(self, document_id):
        with self.connect() as c:
            row = c.execute('SELECT * FROM validations WHERE document_id=? ORDER BY revision DESC LIMIT 1', (document_id,)).fetchone()
            return dict(row) if row else None

    def documents(self, limit=50, offset=0):
        if not isinstance(limit, int) or not isinstance(offset, int) or limit < 1 or offset < 0:
            raise ValueError('pagination invalide')
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM documents ORDER BY id LIMIT ? OFFSET ?', (limit, offset))]

    def historique(self, document_id):
        with self.connect() as c:
            return {table: [dict(r) for r in c.execute(f'SELECT * FROM {table} WHERE document_id=? ORDER BY id', (document_id,))] for table in ('extractions', 'validations')}

    def campagne(self, nom, version_protocole, empreinte_jeu_reference, version_code):
        with self.connect() as c:
            return c.execute('INSERT INTO campagnes(nom,version_protocole,empreinte_jeu_reference,version_code,date_creation) VALUES(?,?,?,?,?)', (nom, version_protocole, empreinte_jeu_reference, version_code, utc_now())).lastrowid

    def evaluer(self, campagne_id, extraction_id, validation_id, nom_champ, est_correct, motif_exclusion=None):
        if nom_champ not in FIELDS or est_correct not in (None, 0, 1):
            raise ValueError('évaluation invalide')
        if est_correct is None and (not motif_exclusion or not motif_exclusion.strip()):
            raise ValueError('motif d’exclusion obligatoire')
        with self.connect() as c:
            return c.execute('INSERT INTO evaluations(campagne_id,extraction_id,validation_id,nom_champ,est_correct,motif_exclusion) VALUES(?,?,?,?,?,?)', (campagne_id, extraction_id, validation_id, nom_champ, est_correct, motif_exclusion)).lastrowid

    def exporter_csv(self, chemin):
        with self.connect() as c, open(chemin, 'w', encoding='utf-8', newline='') as output:
            writer = csv.writer(output)
            writer.writerow(('document_id', 'revision', *FIELDS, 'etats_champs_json', 'date_validation'))
            writer.writerows(c.execute('SELECT v.document_id,v.revision,v.immatriculation,v.date_premiere_immatriculation,v.marque,v.modele_vehicule,v.numero_formule,v.etats_champs_json,v.date_validation FROM validations v WHERE v.revision=(SELECT MAX(v2.revision) FROM validations v2 WHERE v2.document_id=v.document_id) ORDER BY v.document_id'))

    def supprimer_document(self, document_id):
        with self.connect(immediate=True) as c:
            c.execute('DELETE FROM campagnes WHERE id IN (SELECT e.campagne_id FROM evaluations e JOIN extractions x ON x.id=e.extraction_id WHERE x.document_id=?)', (document_id,))
            return c.execute('DELETE FROM documents WHERE id=?', (document_id,)).rowcount > 0


if __name__ == '__main__':
    Database().initialize()
