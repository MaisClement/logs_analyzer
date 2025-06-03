# Configuration des Flux Multi-Applicatifs

Ce document explique comment définir et configurer des flux dans le système de suivi multi-applicatifs.

## Structure Générale

La configuration se fait dans le fichier `config.yaml` avec la structure suivante :

```yaml
flux_types:
  NomDuFlux:
    description: "Description du flux"
    applications:
      NomApplication1:
        patterns:
          TYPE_LOG:
            regex: '...'
            timestamp_format: '%Y-%m-%d %H:%M:%S'
            identifier_fields: [...]
            payload_fields: [...]
            reference_links: [...]  # optionnel
      NomApplication2:
        patterns:
          # ...
```

## Types de Logs Recommandés

- **ENTREE_FLUX** : Point d'entrée du flux
- **TRAITEMENT_APP** : Traitement par une application
- **SORTIE_FLUX** : Fin du flux
- **CREATION_ENFANTS** : Création de sous-flux
- **TRAITEMENT_ENFANT** : Traitement d'un sous-flux

## Éléments de Configuration

### 1. Regex Pattern

Le pattern regex doit capturer les groupes nommés suivants :

```regex
\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{3})?)\] (?P<log_type>\w+) (?P<reference>\w+) ...
```

**Groupes obligatoires :**
- `timestamp` : Horodatage du log
- Un ou plusieurs champs d'identification (ex: `reference`, `user_id`, etc.)

**Groupes optionnels :**
- Champs de payload pour données métier
- Champs de référence pour liens inter-flux

### 2. Format de Timestamp

```yaml
timestamp_format: '%Y-%m-%d %H:%M:%S'
```

Le système supporte automatiquement les millisecondes optionnelles.

### 3. Champs d'Identification

```yaml
identifier_fields: ['reference']
```

Définissent l'identifiant unique du flux. Le premier champ non-vide sera utilisé comme référence principale.

### 4. Champs de Payload

```yaml
payload_fields: ['client_id', 'montant', 'status']
```

Contiennent les données métier extraites du log.

### 5. Liens de Référence (Optionnel)

```yaml
reference_links: ['ordre_id', 'transaction_id']
```

Permettent de créer des références croisées entre flux.

## Exemples Pratiques

### Exemple 1 : Flux de Commande Simple

```yaml
flux_types:
  TraitementCommande:
    description: "Traitement d'une commande e-commerce"
    applications:
      Frontend:
        patterns:
          ENTREE_FLUX:
            regex: '\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] COMMANDE_RECU (?P<reference>\w+) client=(?P<client_id>\w+)'
            timestamp_format: '%Y-%m-%d %H:%M:%S'
            identifier_fields: ['reference']
            payload_fields: ['client_id']
      
      BackendCommande:
        patterns:
          TRAITEMENT_APP:
            regex: '\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] VALIDATION (?P<reference>\w+) → ordre=(?P<ordre_id>\w+)'
            timestamp_format: '%Y-%m-%d %H:%M:%S'
            identifier_fields: ['reference']
            payload_fields: ['ordre_id']
            reference_links: ['ordre_id']  # Créera un lien vers le flux ordre
```

### Exemple 2 : Flux avec Sous-flux

```yaml
flux_types:
  GestionArticles:
    description: "Gestion des articles avec sous-flux"
    applications:
      Frontend:
        patterns:
          ENTREE_FLUX:
            regex: '\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] COMMANDE_RECU (?P<reference>\w+) articles=\[(?P<articles>[^\]]+)\]'
            timestamp_format: '%Y-%m-%d %H:%M:%S'
            identifier_fields: ['reference']
            payload_fields: ['articles']
          
          CREATION_ENFANTS:
            regex: '\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] CREATION_ARTICLES (?P<reference>\w+) articles=\[(?P<enfants_ids>[^\]]+)\]'
            timestamp_format: '%Y-%m-%d %H:%M:%S'
            identifier_fields: ['reference']
            payload_fields: ['enfants_ids']
      
      BackendStock:
        patterns:
          TRAITEMENT_ENFANT:
            regex: '\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] TRAITEMENT_ARTICLE (?P<article_id>\w+) parent=(?P<parent_ref>\w+)'
            timestamp_format: '%Y-%m-%d %H:%M:%S'
            identifier_fields: ['article_id']
            payload_fields: ['parent_ref']
```

### Exemple 3 : Flux de Paiement

```yaml
flux_types:
  TraitementPaiement:
    description: "Processus de paiement"
    applications:
      GatewayPaiement:
        patterns:
          ENTREE_FLUX:
            regex: '\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] PAIEMENT_RECU (?P<reference>\w+) montant=(?P<montant>[\d.]+) devise=(?P<devise>\w+)'
            timestamp_format: '%Y-%m-%d %H:%M:%S'
            identifier_fields: ['reference']
            payload_fields: ['montant', 'devise']
      
      ProcesseurPaiement:
        patterns:
          TRAITEMENT_APP:
            regex: '\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] AUTORISATION (?P<reference>\w+) → transaction=(?P<transaction_id>\w+) status=(?P<status>\w+)'
            timestamp_format: '%Y-%m-%d %H:%M:%S'
            identifier_fields: ['reference']
            payload_fields: ['transaction_id', 'status']
            reference_links: ['transaction_id']
      
      Comptabilite:
        patterns:
          SORTIE_FLUX:
            regex: '\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] ECRITURE_COMPTABLE transaction=(?P<transaction_id>\w+) compte=(?P<compte>\w+)'
            timestamp_format: '%Y-%m-%d %H:%M:%S'
            identifier_fields: ['transaction_id']
            payload_fields: ['compte']
```

## Logs Correspondants

Pour les exemples ci-dessus, voici des logs qui seraient traités :

```log
[2024-01-15 10:30:00] COMMANDE_RECU CMD_001 client=CLI_123
[2024-01-15 10:30:05] VALIDATION CMD_001 → ordre=ORD_456
[2024-01-15 10:30:10] PAIEMENT_RECU PAY_001 montant=99.99 devise=EUR
[2024-01-15 10:30:15] AUTORISATION PAY_001 → transaction=TXN_789 status=APPROUVE
[2024-01-15 10:30:20] ECRITURE_COMPTABLE transaction=TXN_789 compte=RECETTES
```

## Bonnes Pratiques

### 1. Nommage des Flux
- Utilisez des noms descriptifs et cohérents
- Préférez `PascalCase` pour les noms de flux
- Exemples : `TraitementCommande`, `InscriptionUtilisateur`, `GestionStock`

### 2. Nommage des Applications
- Utilisez des noms clairs et courts
- Préférez `PascalCase`
- Exemples : `Frontend`, `BackendCommande`, `ServicePaiement`

### 3. Types de Logs
- Utilisez des noms en MAJUSCULES avec underscores
- Soyez cohérent dans votre nomenclature
- Exemples : `ENTREE_FLUX`, `TRAITEMENT_APP`, `CREATION_ENFANTS`

### 4. Références
- Utilisez des préfixes clairs : `CMD_`, `ORD_`, `PAY_`, `USR_`
- Gardez une cohérence dans le format
- Évitez les caractères spéciaux

### 5. Regex
- Testez vos regex avec des logs réels
- Utilisez des groupes nommés explicites
- Préférez `\w+` pour les identifiants simples
- Utilisez `[^\]]+` pour capturer du contenu entre crochets

## Test de Configuration

Utilisez la commande CLI pour tester vos patterns :

```bash
# Tester le parsing d'une ligne
python cli.py parse-test "[2024-01-15 10:30:00] COMMANDE_RECU CMD_001 client=CLI_123"

# Forcer un flux spécifique
python cli.py parse-test "votre_log" --flux-type TraitementCommande

# Forcer une application spécifique
python cli.py parse-test "votre_log" --application Frontend

# Lister la configuration
python cli.py list-config
```

## Dépannage

### Problèmes Courants

1. **Log non reconnu** : Vérifiez que votre regex capture bien tous les groupes obligatoires
2. **Timestamp invalide** : Assurez-vous que le format correspond exactement
3. **Référence manquante** : Vérifiez que `identifier_fields` contient au moins un champ capturé
4. **Liens non créés** : Vérifiez que `reference_links` pointe vers des champs existants dans la regex

### Validation

Lancez les tests de robustesse pour valider votre configuration :

```bash
python test_robustesse.py
```

---

## Support

Pour plus d'informations ou en cas de problème :
- Consultez les logs du système
- Utilisez `python cli.py parse-test` pour déboguer
- Vérifiez la base de données avec `python cli.py get-flux <reference>`
