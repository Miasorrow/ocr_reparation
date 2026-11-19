-- Toutes les requêtes sont exécutables dans sqlite3. Remplacer 1 par l'identifiant de campagne voulu.
-- Documents et extractions, y compris les documents sans extraction.
SELECT d.id, d.nom_fichier, e.id AS extraction_id, e.statut FROM documents d LEFT JOIN extractions e ON e.document_id=d.id ORDER BY d.id,e.id;
-- Documents sans validation.
SELECT d.id,d.nom_fichier FROM documents d WHERE NOT EXISTS (SELECT 1 FROM validations v WHERE v.document_id=d.id);
-- Dernière révision par document.
SELECT v.* FROM validations v WHERE v.revision=(SELECT MAX(v2.revision) FROM validations v2 WHERE v2.document_id=v.document_id);
-- Nombre par modèle et statut.
SELECT m.id,m.fournisseur,m.nom,m.version,e.statut,COUNT(*) AS effectif FROM extractions e JOIN modeles m ON m.id=e.modele_id GROUP BY m.id,e.statut;
-- Durée moyenne disponible en millisecondes, extractions réussies seulement.
SELECT m.id,m.nom,AVG(e.duree_modele_ms) AS moyenne_ms,COUNT(e.duree_modele_ms) AS effectif FROM extractions e JOIN modeles m ON m.id=e.modele_id WHERE e.statut='succeeded' GROUP BY m.id;
-- Champs incorrects pour la campagne 1.
SELECT ev.extraction_id,ev.validation_id,ev.nom_champ FROM evaluations ev WHERE ev.campagne_id=1 AND ev.est_correct=0;
-- Taux sur les seules évaluations non exclues, par modèle et champ.
SELECT m.id,m.nom,ev.nom_champ,COUNT(ev.est_correct) AS effectif_evalue,AVG(CAST(ev.est_correct AS REAL)) AS taux_correct FROM evaluations ev JOIN extractions e ON e.id=ev.extraction_id JOIN modeles m ON m.id=e.modele_id WHERE ev.campagne_id=1 GROUP BY m.id,ev.nom_champ;
-- Observer le plan choisi, sans présumer de performance :
EXPLAIN QUERY PLAN SELECT * FROM validations WHERE document_id=1 ORDER BY revision DESC LIMIT 1;
