"""Import de preuves de paiement et liaison à un billet (facture -> paiement).

Les refus de lecture viennent de payments/pdf_text.py, ceux de liaison de
payments/store.py.
"""

MESSAGES = {
    # Import
    "err.bill_refused": (
        "Ce document est une facture adressée à {company}, pas une preuve de paiement. "
        "Seules les preuves de paiement peuvent être importées."
    ),
    "err.payment_save_failed": (
        "Enregistrement du fichier impossible ; rien n'a été importé. "
        "Vérifiez l'espace disque puis réessayez."
    ),

    # Lecture de la preuve (payments/pdf_text.py)
    "err.payment_pdf_protected": (
        "Ce PDF est protégé par un mot de passe. Retirez la protection puis importez-le à nouveau."
    ),
    "err.payment_pdf_unreadable": "Ce fichier n'est pas un PDF lisible.",
    "err.payment_pdf_no_text": (
        "Ce PDF ne contient pas de texte lisible (document numérisé ?). "
        "Importez le PDF original produit par le logiciel de l'émetteur."
    ),

    # Liaison à un billet
    "err.payment_not_found": "Paiement introuvable",
    "err.payment_line_not_found": "Ligne introuvable",
    "err.ticket_number_required": "Numéro de billet requis",
    "err.not_a_ticket_number": (
        "Ce n'est pas un numéro de billet valide (un numéro de projet, par exemple)."
    ),
    "err.choose_ticket": "Choisissez un billet",
    "err.ticket_not_on_invoice": "Ce billet n'existe pas sur cette facture",
    "err.ticket_already_linked": "Ce billet est déjà lié au paiement #{payment_id}.",
}
