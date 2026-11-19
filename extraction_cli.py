"""Analyser un document déjà importé : python -m extraction_cli ID."""
import argparse
from persistence.database import Database
from services.extraction_pipeline import ExtractionPipeline


def main():
    parser = argparse.ArgumentParser(description='Extraction locale d’un document déjà enregistré')
    parser.add_argument('document_id', type=int)
    args = parser.parse_args()
    db = Database()
    db.initialize()
    try:
        extraction_id = ExtractionPipeline(db).run(args.document_id)
    except ValueError as exc:
        parser.exit(2, f'{exc}\n')
    record = next(row for row in db.historique(args.document_id)['extractions'] if row['id'] == extraction_id)
    print(f"Extraction {extraction_id} : {record['statut']}" + (f" ({record['code_erreur']})" if record['code_erreur'] else ''))
    return 0 if record['statut'] == 'succeeded' else 1


if __name__ == '__main__':
    raise SystemExit(main())
