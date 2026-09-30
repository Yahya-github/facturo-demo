"""Génération, modification, suppression et export PDF des factures.

Les fragments `err.stored_*` sont en minuscules volontairement : api/factures.py
les assemble dans une phrase plus longue, et c'est cette phrase entière que le
navigateur affiche.
"""

MESSAGES = {
    # Recherches
    "err.invoice_not_found": "Facture introuvable",

    # Génération
    "err.billet_required": "Au moins un billet est requis",
    "err.generate_failed": "Erreur lors de la génération: {detail}",
    "err.regenerate_failed": "Erreur lors de la régénération: {detail}",
    "err.concurrent_invoice_created": (
        "Des factures ont été créées entre-temps pour ce client ; rien n'a été enregistré. Réessayez."
    ),

    # Persistance. Chacun de ces messages promet que le fichier ou la ligne est intact.
    "err.invoice_not_saved": (
        "La facture {numero} n'a pas pu être enregistrée dans la base de données ; "
        "aucun fichier n'a été conservé pour elle. Réessayez."
    ),
    "err.invoice_not_saved_after_edit": (
        "La facture {numero} n'a pas pu être enregistrée dans la base de données ; "
        "elle est restée telle qu'avant la modification. Réessayez."
    ),
    "err.invoice_not_deleted": (
        "La facture {numero} n'a pas pu être supprimée ; elle est restée intacte. Réessayez."
    ),

    # Avis de factures déjà créées, ajoutés après le message de ligne
    "err.invoice_already_created": "Facture déjà créée : {numeros}.",
    "err.invoices_already_created": "Factures déjà créées : {numeros}.",

    # Relecture des billets dans un classeur enregistré
    "err.billets_unreadable": (
        "Impossible de lire les billets de cette facture. Le fichier d'origine n'a pas été modifié."
    ),
    "err.save_would_overwrite": "Enregistrer maintenant écraserait la facture existante.",
    "err.stored_billets_unreadable": "billets enregistrés illisibles",
    "err.excel_unreadable": "fichier Excel illisible",
    "err.excel_not_found": "fichier Excel introuvable",

    # Export PDF, via LibreOffice (invoicing/excel_generator.py)
    "err.pdf_conversion_failed": "Erreur lors de la conversion PDF: {detail}",
    "invoice.soffice_missing": (
        "LibreOffice est requis pour l'export PDF mais est introuvable. "
        "Installez LibreOffice (gratuit) depuis libreoffice.org, puis "
        "réessayez. L'export Excel fonctionne sans LibreOffice."
    ),
    "invoice.source_file_not_found": "Fichier source introuvable: {path}",
    "invoice.pdf_conversion_error": "Échec de la conversion PDF: {detail}",
}
