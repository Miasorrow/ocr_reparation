import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from persistence.database import Database, FIELDS


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Database(Path(self.tmp.name) / 'test.sqlite')
        self.db.initialize()
        self.d = self.db.document('a' * 64, '/fictif/image.png')['id']
        self.m = self.db.modele('fictif', 'modele')['id']
        self.x = self.db.creer_extraction(self.d, self.m, '1', {})
        self.values = dict.fromkeys(FIELDS)
        self.values['marque'] = 'Fictive'
        self.states = {f: ('known' if f == 'marque' else 'absent') for f in FIELDS}

    def validation(self, doc=None, extraction=None):
        return self.db.valider(doc or self.d, self.values, self.states, extraction)

    def test_initialisation_doublons_et_cles(self):
        self.db.initialize()
        self.assertEqual(self.d, self.db.document('a' * 64, '/autre')['id'])
        self.assertEqual(self.m, self.db.modele('fictif', 'modele', None)['id'])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.creer_extraction(999, self.m, '1', {})
        self.assertEqual(len(self.db.documents()), 1)

    def test_historique_validation_et_immutabilite(self):
        self.db.etat_extraction(self.x, 'running')
        self.db.etat_extraction(self.x, 'succeeded', marque='Originale')
        self.db.creer_extraction(self.d, self.m, '1', {})
        self.validation(extraction=self.x)
        self.values['marque'] = 'Corrigee'
        v2 = self.validation(extraction=self.x)
        self.assertEqual(self.db.derniere_validation(self.d)['id'], v2)
        history = self.db.historique(self.d)
        self.assertEqual(len(history['extractions']), 2)
        self.assertEqual(history['extractions'][0]['marque'], 'Originale')
        self.assertEqual(len(history['validations']), 2)
        with self.assertRaises(sqlite3.IntegrityError), self.db.connect() as c:
            c.execute('UPDATE validations SET marque=? WHERE id=?', ('x', v2))
        output = Path(self.tmp.name) / 'export.csv'
        self.db.exporter_csv(output)
        with output.open(encoding='utf-8', newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['marque'], 'Corrigee')

    def test_coherence_et_taux(self):
        other = self.db.document('b' * 64, '/fictif/autre')['id']
        with self.assertRaises(sqlite3.IntegrityError):
            self.validation(other, self.x)
        v = self.validation(extraction=self.x)
        v2 = self.validation(extraction=self.x)
        other_v = self.validation(other)
        campaign = self.db.campagne('fictive', '1', 'fictif', '1')
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.evaluer(campaign, self.x, other_v, 'marque', 1)
        self.db.evaluer(campaign, self.x, v, 'marque', 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.evaluer(campaign, self.x, v2, 'marque', 0)
        x2 = self.db.creer_extraction(self.d, self.m, '1', {})
        self.db.evaluer(campaign, x2, v, 'marque', 0)
        x3 = self.db.creer_extraction(self.d, self.m, '1', {})
        self.db.evaluer(campaign, x3, v, 'marque', None, 'illisible')
        with self.db.connect() as c:
            n, rate = c.execute('SELECT COUNT(est_correct), AVG(CAST(est_correct AS REAL)) FROM evaluations WHERE campagne_id=? AND nom_champ=?', (campaign, 'marque')).fetchone()
        self.assertEqual((n, rate), (2, 0.5))

    def test_suppression_et_rollback(self):
        v = self.validation(extraction=self.x)
        campaign = self.db.campagne('fictive', '1', 'fictif', '1')
        self.db.evaluer(campaign, self.x, v, 'marque', 1)
        with self.db.connect() as c:
            c.execute("CREATE TRIGGER bloque_suppression BEFORE DELETE ON documents BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.supprimer_document(self.d)
        with self.db.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM campagnes').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM evaluations').fetchone()[0], 1)
            c.execute('DROP TRIGGER bloque_suppression')
        self.assertTrue(self.db.supprimer_document(self.d))
        with self.db.connect() as c:
            for table in ('documents', 'extractions', 'validations', 'campagnes', 'evaluations'):
                self.assertEqual(c.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)

    def test_requetes_executables(self):
        sql = (Path(__file__).resolve().parents[1] / 'persistence' / 'requetes.sql').read_text()
        with self.db.connect() as c:
            for statement in sql.split(';'):
                if statement.strip():
                    c.execute(statement).fetchall()


if __name__ == '__main__':
    unittest.main()
