# Guide d'utilisation — Facturo v2

**Pour l'utilisateur — Demo Transport Inc. (entreprise fictive)**

## Démarrage

1. Ouvrez `Factures.exe`
2. Allez à **Paramètres** (coin inférieur)
3. Entrez votre jeton de synchronisation (fourni une fois)
4. Cliquez **Recevoir** pour télécharger les données existantes

Vous êtes prêt à commencer !

## Onglets principaux

### Accueil — Factures récentes

- Voyez les 10 dernières factures
- Cliquez sur une facture pour l'éditer ou exporter en Excel

### Historique — Recherche & filtres

- Cherchez par numéro, client, site, plaque, date
- Filtrez par statut: Toutes / Payées / Non payées / Partiellement payées
- Triez par montant ou date
- Exportez l'historique complet

### Factures — Créer & modifier

1. Sélectionnez un client
2. Ajoutez des billets (heures travaillées):
   - Numéro du billet
   - Date (jj-mm-aaaa)
   - Plaque du camion
   - Heures travaillées
   - Taux horaire
3. Appliquez une remise si nécessaire (% ou $, ou les deux)
4. Cliquez **Enregistrer**
5. Cliquez **Télécharger** pour obtenir un Excel avec taxes (TPS 5 % / TVQ 9.975 %)

### Scans — Reçus & factures fournisseurs

- Prenez une photo ou capturez un PDF d'une facture
- L'app lit les données automatiquement (OCR Ollama)
- Relisez & corrigez si nécessaire
- Les billets sont pré-remplis dans la facture

### Paiements — Importer & lier

1. Glissez-déposez des PDF (quittances, preuves de paiement)
2. L'app extrait automatiquement:
   - Emetteur, numéro de quittance, date
   - Billets listés
3. L'app essaie de lier chaque ligne aux billets de vos factures
4. Vérifiez le statut (lié / à vérifier / doublon)
5. Liez manuellement les lignes non reconnues si nécessaire
6. Les factures avec 100 % couverture sont marquées **Payées** automatiquement

**Statuts:**
- **Lié** — trouvé et associé
- **À vérifier** — introuvable, vérifiez manuellement
- **Doublon** — billet déjà lié à un autre paiement

### Paramètres — Configuration & synchronisation

**Jetons (une fois):**
- Jeton de synchro (Recevoir/Envoyer)
- Jeton de mise à jour (Mises à jour)

**Recevoir** — Télécharger les données de vos autres appareils

**Envoyer** — Envoyer vos changements à vos autres appareils

**Mises à jour** — Vérifier & installer une nouvelle version

## Remises

Vous pouvez appliquer deux types de remise:

- **Remise %** — Un pourcentage du sous-total
- **Remise $** — Un montant fixe en dollars

Les deux s'appliquent à chaque billet ET à chaque facture. L'Excel affiche deux lignes distinctes.

Exemple:
- Billet: 100 $ brut → 10 % de remise → 90 $
- Facture: 500 $ sous-total → 5 % de remise → 50 $ de remise → taxes → total

## Factures payées

Quand vous importez une quittance listant vos billets:

1. L'app reconnaît le numéro du billet (ou date + plaque + heures)
2. Lie la ligne au billet
3. Si TOUS les billets d'une facture sont liés → **Payée** automatique ✓

Si vous supprimez une preuve de paiement, la facture redevient **Non payée** (sauf si vous l'avez marquée manuellement).

## Synchronisation multi-appareils

Vous avez plusieurs ordinateurs/tablettes ?

1. **Appareil 1 (principal):** Envoyer → Recevoir
2. **Appareil 2:** Recevoir (obtient les données de l'appareil 1)
3. Continuez à Recevoir/Envoyer pour synchroniser

**Important:** Mettez à jour TOUS les appareils en v2.0.0 avant de synchroniser.

## Mises à jour

Quand une nouvelle version est disponible:

1. Allez à **Paramètres → Mises à jour**
2. Cliquez **Vérifier** (ou l'app vérifie automatiquement)
3. Si "Mise à jour disponible" s'affiche, cliquez **Installer**
4. L'app se ferme, se met à jour, redémarre automatiquement
5. Si la mise à jour échoue, l'app revient à la version précédente

**Aucune action de votre part** — l'app gère tout.

## En cas de problème

| Problème | Solution |
|----------|----------|
| "Jeton refusé" | Le jeton a expiré. Créez-en un nouveau dans GitHub Settings. |
| "Base de données plus récente" | Mettez à jour l'app (Paramètres → Mises à jour). |
| "Erreur de synchronisation" | Vérifiez votre connexion internet. Réessayez. |
| "LibreOffice ne s'ouvre pas" | Assurez-vous que `LibreOfficePortable/` est dans le dossier de l'app. |
| "La facture ne s'exporte pas" | Vérifiez que vous avez ajouté des billets et enregistré. |

---

**Questions?** Contactez votre équipe technique.

**Version:** 2.0+  
