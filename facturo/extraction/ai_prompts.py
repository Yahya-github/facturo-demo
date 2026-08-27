"""The structured-output schema and the French prompts for billet extraction.

Pure data, kept apart from facturo/extraction/ai_extract.py (which talks to
Ollama) so the prompts can be read and tuned on their own.

Layout names below are neutral stand-ins: "Transport Alpha" and "Vrac Beta Inc."
are third-party layouts, and the company's own layout (and the carrier name
printed on the others) is facturo.brand.COMPANY_NAME.
"""

from facturo.brand import COMPANY_NAME

# Forced via Ollama's structured-output `format=` param — the model must return
# JSON matching this shape, not a "please return JSON" prompt hint. Per-field
# descriptions matter a lot in practice: without them the model confuses
# numero_billet with quantite (both being "numbers near the start of the
# text").
#
# IMPORTANT: this schema never includes a client_id / invoice-client field, and
# never should. The invoice's client (which of the app's registered clients
# this invoice belongs to) is always a manual user choice — the AI only ever
# fills per-billet fields for review, it never decides who the invoice is for.
EXTRACT_SCHEMA = {
    "type": "object",
    # FIELD ORDER IS LOAD-BEARING, and it is not obvious which order wins.
    # Structured output generates the keys in the order written here, so each
    # field is answered with only the earlier ones in view. Putting
    # lieu_travail ahead of chantier is the intuitive fix for the address
    # landing in the renter field — and measuring it made things worse, not
    # better (chantier 5/6 -> 4/6 on a two-layout sample set: the company-layout
    # page then returned an empty renter). The order below is the measured best.
    # Re-run the billet benchmark before changing it; do not sort these keys.
    "properties": {
        "numero_billet": {
            "type": "string",
            "maxLength": 20,
            "description": (
                "Numero du billet imprime (souvent en rouge) en HAUT A DROITE, "
                "apres 'No. billet:', 'N° BILLET', ou seul sans etiquette. "
                "C'est un identifiant de document, generalement 4 a 6 "
                "chiffres : 50742, 34338, 1605, 4211. PAS le numero de "
                "travail/contrat/projet (format '26-108', '#26-112'), PAS le "
                "numero d'unite, PAS la quantite, PAS la plaque."
            ),
        },
        "chantier": {
            "type": "string",
            "maxLength": 60,
            "description": (
                "Recopie le NOM inscrit sur la ligne etiquetee 'Loue a', "
                "'Rented to' ou 'Client :'. C'est un nom court de personne ou "
                "d'entreprise, sans adresse : ROXDALE, NORIX, M. RIVARD, "
                "PAVEX, SUMMIT EXCAVATION, LAKESIDE. Omets toute parenthese."
            ),
        },
        "lieu_travail": {
            "type": "string",
            "maxLength": 120,
            "description": (
                "Recopie l'ADRESSE du chantier, ligne 'Lieu de travail', 'Work "
                "emplacement', 'Lieu des travaux' ou 'Adresse :'. Contient "
                "typiquement un numero civique, une rue ou une ville : '7400 CH "
                "DU LAC NORD', '8100 rue Fictive Anjou', 'Aeroport Central'. "
                "Si la ligne 'Lieu de travail' est vide mais que la ligne "
                "'Adresse' est remplie, recopie la ligne 'Adresse'."
            ),
        },
        "date_billet": {
            "type": "string",
            "maxLength": 30,
            "description": (
                "Recopie EXACTEMENT les caracteres de la date manuscrite, dans "
                "la premiere ligne de la colonne 'Date' du tableau (ou apres "
                "'Date :' en haut a droite), sans rien reformater. Recopie tel "
                "quel, par exemple : '23/06/2026', '25 6 2026', '29 JUIN 2026', "
                "'22-06-2026', '10/07/2026'. L'annee est 2026, pas 2016."
            ),
        },
        "quantite": {
            "type": "string",
            "maxLength": 20,
            "description": (
                "Recopie EXACTEMENT les caracteres du TOTAL des heures, tels "
                "qu'ils sont ecrits, SANS convertir et SANS arrondir. Recopie "
                "tel quel, par exemple : '8,25', '10,5 h', '11,75', '6,5H', "
                "'9H', '9h15', '6h45', '7h'. Si tu lis '9h15', ecris '9h15' — "
                "n'ecris PAS 9.15 ni 9,25 : la conversion est faite ensuite. "
                "Prends la valeur dans le champ 'Total Heures' / 'TOTAL "
                "HEURES :' / 'Total des heures :' / 'Heures total de travail'. "
                "Si ce champ est vide, additionne les lignes de la colonne "
                "'Hrs' / 'HRES' / 'Heures'. Ce n'est PAS le nombre de voyages."
            ),
        },
        "plaque": {
            "type": "string",
            "maxLength": 20,
            "description": (
                "Plaque d'immatriculation du camion. Cherche dans le BAS du "
                "billet un code manuscrit fait de 1 ou 2 LETTRES suivies de 5 "
                "a 6 CHIFFRES, par exemple : AB12345, AB10234, A123456, "
                "CD45678, A987654. Ce code se trouve apres l'une de ces "
                "etiquettes : 'No. Plaque / Plate no.', 'PLAQUE :', "
                "'Plaque :', 'N° License :', 'No License'. "
                "Recopie-le meme s'il est ecrit un peu au-dessus ou a droite "
                "de la ligne, ou colle au nom du transporteur. Ne rends une "
                "chaine vide QUE si aucun code lettres+chiffres n'apparait "
                "dans le bas du billet. N'y mets jamais un nom d'entreprise "
                f"(ex: '{COMPANY_NAME}' est le transporteur, pas la plaque) et ignore "
                "les cases 'Plaque:' vides a cote de Semi 2SS/3SS/4SS."
            ),
        },
        "taux": {
            "type": "number",
            "description": (
                "Taux horaire en dollars, UNIQUEMENT si des chiffres sont "
                "ecrits a la main directement a cote du champ imprime "
                "'Taux' / 'Rate $' (ex: 95$ -> 95). Ce champ est PRESQUE "
                "TOUJOURS LAISSE VIDE par le chauffeur (le taux est convenu "
                "separement avec le client). Si aucun chiffre n'est ecrit a "
                "cote de 'Taux'/'Rate $', retourne EXACTEMENT 0 — ne devine "
                "jamais un taux a partir des heures, du total, du numero de "
                "billet, de la plaque, ou de tout autre nombre du billet."
            ),
        },
        "description": {
            "type": "string",
            "maxLength": 200,
            "description": (
                "Autre precision utile ecrite sur le billet (ex: materiel "
                "transporte, 'no lunch', nombre de voyages). Vide si rien."
            ),
        },
    },
    # Every field the invoice line needs is required, because an optional field
    # is one the model simply drops: asking for only `quantite` came back with
    # no numero_billet, no plaque and no date at all. Required + an explicit
    # "leave it empty" instruction gets a considered answer per field.
    #
    # taux stays OUT of this list on purpose. Forcing it meant the model always
    # had to invent a number even when the billet's Taux/Rate box is genuinely
    # blank (the common case — the rate is agreed separately, not handwritten).
    # Leaving it optional gives the model an explicit "I don't know" out;
    # _parse_and_validate treats a missing taux the same as 0.
    "required": [
        "lieu_travail", "chantier", "plaque", "numero_billet", "quantite",
        "date_billet",
    ],
}

_INSTRUCTIONS_FR = (
    "Tu extrais les informations d'un billet de transport/camionnage quebecois. "
    "Remplis exactement les champs du schema JSON fourni, en respectant leur "
    "description precise. Si une information est absente, laisse le champ vide "
    "(chaine) ou 0 (nombre). N'invente jamais de valeur.\n\n"
    "Trois mises en page existent, avec les memes informations :\n"
    "- 'Transport Alpha' : le loueur est sur la ligne 'Loue a / Rented to:', le "
    "numero de billet est imprime en rouge en haut a droite apres 'No. billet:', "
    "la plaque est en bas a droite apres 'No. Plaque / Plate no.'.\n"
    f"- '{COMPANY_NAME}' : le loueur est sur la ligne 'CLIENT :', le "
    "numero est apres 'N° BILLET' en haut a droite, la plaque apres 'PLAQUE :'.\n"
    "- 'BILLET DE LOCATION' : le loueur est sur la ligne 'Client :', la plaque "
    "sur la ligne 'Plaque :' de l'en-tete, le total sur 'Total des heures :', et "
    "le numero est imprime en rouge en haut a droite, seul (sans etiquette). "
    "Attention : '#Projet' et '#Unite' ne sont PAS le numero de billet.\n"
    "- 'Vrac Beta Inc.' : le loueur est sur 'Loue a:', l'adresse sur "
    "'Adresse:' et 'Lieu de travail:', le numero est imprime en rouge dans un "
    "cadre arrondi en haut a droite sous le mot 'BILLET', et le total sur "
    "'Total Heures'. TRES IMPORTANT sur ce modele : la plaque du camion est "
    "sur la ligne 'N° License:' (il n'y a aucune ligne 'Plaque'), et la ligne "
    f"'Transporteur:' contient le nom du transporteur (souvent '{COMPANY_NAME}') qui "
    f"n'est PAS le loueur — ne mets JAMAIS '{COMPANY_NAME}' dans chantier.\n\n"
    "Le champ 'chantier' decrit uniquement le nom ecrit a la main sur la ligne "
    "'Loue a' / 'CLIENT'. Ce n'est jamais le client de la facture : celui-ci est "
    "toujours choisi par l'utilisateur, jamais par toi.\n\n"
    "Pour 'quantite', la reponse est le TOTAL des heures : lis 'Total Heures' "
    "s'il est rempli, sinon additionne toutes les lignes de la colonne 'Hrs'.\n\n"
    "Si le texte ou l'image ne contient aucune information de billet (ex: une "
    "image sans rapport, une facture deja imprimee, un texte vide), retourne "
    "TOUS les champs vides/0."
)

_VISION_PROMPT_FR = (
    f"{_INSTRUCTIONS_FR}\n\n"
    "Lis la photo du billet papier ci-jointe et extrait les champs demandes. "
    "L'ecriture est manuscrite : prends le temps de distinguer les chiffres."
)
