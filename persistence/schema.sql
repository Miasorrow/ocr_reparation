PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS documents (
 id INTEGER PRIMARY KEY, nom_fichier TEXT NOT NULL, chemin_image TEXT NOT NULL,
 empreinte_sha256 TEXT NOT NULL UNIQUE CHECK(length(empreinte_sha256)=64 AND empreinte_sha256 NOT GLOB '*[^0-9a-f]*'), date_import TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS modeles (
 id INTEGER PRIMARY KEY, nom TEXT NOT NULL, version TEXT NOT NULL DEFAULT '', fournisseur TEXT NOT NULL,
 UNIQUE(fournisseur,nom,version)
);
CREATE TABLE IF NOT EXISTS extractions (
 id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 modele_id INTEGER NOT NULL REFERENCES modeles(id), texte_ocr TEXT, reponse_brute TEXT,
 version_prompt TEXT NOT NULL, configuration_json TEXT NOT NULL CHECK(json_valid(configuration_json)),
 immatriculation TEXT, date_premiere_immatriculation TEXT CHECK(date_premiere_immatriculation IS NULL OR (length(date_premiere_immatriculation)=10 AND date(date_premiere_immatriculation,'+0 days') IS date_premiere_immatriculation)),
 marque TEXT, modele_vehicule TEXT, numero_formule TEXT,
 duree_ocr_ms INTEGER CHECK(duree_ocr_ms IS NULL OR (typeof(duree_ocr_ms)='integer' AND duree_ocr_ms>=0)),
 duree_modele_ms INTEGER CHECK(duree_modele_ms IS NULL OR (typeof(duree_modele_ms)='integer' AND duree_modele_ms>=0)),
 statut TEXT NOT NULL CHECK(statut IN ('pending','running','succeeded','failed','interrupted')),
 code_erreur TEXT, date_execution TEXT NOT NULL, UNIQUE(id,document_id)
);
CREATE TABLE IF NOT EXISTS validations (
 id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 extraction_id INTEGER, revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>0),
 immatriculation TEXT, date_premiere_immatriculation TEXT CHECK(date_premiere_immatriculation IS NULL OR (length(date_premiere_immatriculation)=10 AND date(date_premiere_immatriculation,'+0 days') IS date_premiere_immatriculation)),
 marque TEXT, modele_vehicule TEXT, numero_formule TEXT,
 etats_champs_json TEXT NOT NULL CHECK(json_valid(etats_champs_json)), date_validation TEXT NOT NULL,
 UNIQUE(document_id,revision), UNIQUE(id,document_id), FOREIGN KEY(extraction_id,document_id) REFERENCES extractions(id,document_id) ON DELETE CASCADE,
 CHECK(json_type(etats_champs_json)='object')
);
CREATE TRIGGER IF NOT EXISTS validations_verifier BEFORE INSERT ON validations BEGIN
 SELECT CASE WHEN (SELECT count(*) FROM json_each(NEW.etats_champs_json)) != 5 OR EXISTS (
 SELECT 1 FROM json_each(NEW.etats_champs_json) WHERE key NOT IN ('immatriculation','date_premiere_immatriculation','marque','modele_vehicule','numero_formule') OR value NOT IN ('known','absent','unreadable') OR type != 'text'
 ) THEN RAISE(ABORT,'etats de champs invalides') END;
 SELECT CASE WHEN EXISTS (
 SELECT 1 FROM json_each(NEW.etats_champs_json) WHERE
 (value='known') != (CASE key WHEN 'immatriculation' THEN NEW.immatriculation WHEN 'date_premiere_immatriculation' THEN NEW.date_premiere_immatriculation WHEN 'marque' THEN NEW.marque WHEN 'modele_vehicule' THEN NEW.modele_vehicule WHEN 'numero_formule' THEN NEW.numero_formule END IS NOT NULL)
 ) THEN RAISE(ABORT,'etat et valeur incoherents') END;
END;
CREATE TRIGGER IF NOT EXISTS validations_immuables BEFORE UPDATE ON validations BEGIN SELECT RAISE(ABORT,'validation immuable'); END;
CREATE TABLE IF NOT EXISTS campagnes (
 id INTEGER PRIMARY KEY, nom TEXT NOT NULL, version_protocole TEXT NOT NULL,
 empreinte_jeu_reference TEXT NOT NULL, version_code TEXT NOT NULL, date_creation TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluations (
 id INTEGER PRIMARY KEY, campagne_id INTEGER NOT NULL REFERENCES campagnes(id) ON DELETE CASCADE,
 extraction_id INTEGER NOT NULL REFERENCES extractions(id) ON DELETE CASCADE,
 validation_id INTEGER NOT NULL REFERENCES validations(id) ON DELETE CASCADE,
 nom_champ TEXT NOT NULL CHECK(nom_champ IN ('immatriculation','date_premiere_immatriculation','marque','modele_vehicule','numero_formule')),
 est_correct INTEGER CHECK(est_correct IS NULL OR (typeof(est_correct)='integer' AND est_correct IN (0,1))),
 motif_exclusion TEXT, CHECK(est_correct IS NOT NULL OR (motif_exclusion IS NOT NULL AND length(trim(motif_exclusion))>0)),
 UNIQUE(campagne_id,extraction_id,validation_id,nom_champ)
);
CREATE TRIGGER IF NOT EXISTS evaluations_verifier_insert BEFORE INSERT ON evaluations BEGIN
 SELECT CASE WHEN (SELECT document_id FROM extractions WHERE id=NEW.extraction_id) IS NOT (SELECT document_id FROM validations WHERE id=NEW.validation_id) THEN RAISE(ABORT,'documents differents') END;
 SELECT CASE WHEN EXISTS(SELECT 1 FROM evaluations e JOIN extractions x ON x.id=e.extraction_id WHERE e.campagne_id=NEW.campagne_id AND x.document_id=(SELECT document_id FROM extractions WHERE id=NEW.extraction_id) AND e.validation_id!=NEW.validation_id) THEN RAISE(ABORT,'reference contradictoire') END;
END;
CREATE TRIGGER IF NOT EXISTS evaluations_immuables BEFORE UPDATE ON evaluations BEGIN SELECT RAISE(ABORT,'evaluation immuable'); END;
CREATE INDEX IF NOT EXISTS idx_extractions_document ON extractions(document_id,id);
CREATE INDEX IF NOT EXISTS idx_extractions_modele_statut ON extractions(modele_id,statut);
CREATE INDEX IF NOT EXISTS idx_validations_document_revision ON validations(document_id,revision DESC);
CREATE INDEX IF NOT EXISTS idx_validations_extraction ON validations(extraction_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_extraction ON evaluations(extraction_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_validation ON evaluations(validation_id);
-- Une extraction conserve son document et son modèle, même via SQL direct.
CREATE TRIGGER IF NOT EXISTS extraction_identite_immuable BEFORE UPDATE OF document_id,modele_id ON extractions BEGIN
 SELECT RAISE(ABORT,'identite extraction immuable');
END;
