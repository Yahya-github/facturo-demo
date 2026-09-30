"""Curation du vocabulaire chantiers / plaques (core/known_values.py).

`KnownValueError` porte l'un de ces messages jusqu'au navigateur : chacun dit
ce que l'utilisateur a mal fait, pas quel test interne l'a rattrapé.
"""

MESSAGES = {
    "known_values.invalid_kind": "Type invalide",
    "known_values.empty_value": "Valeur vide",
    "known_values.duplicate": "Cette valeur existe déjà.",
    "known_values.not_found": "Valeur introuvable",
    "known_values.merge_into_itself": "Impossible de fusionner une valeur avec elle-même",
    "known_values.kind_mismatch": "Les deux valeurs doivent être du même type",
    "known_values.target_merged": "La valeur cible a déjà été fusionnée ailleurs",
}
