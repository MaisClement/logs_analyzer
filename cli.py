#!/usr/bin/env python3
"""
Utilitaire en ligne de commande pour le système de suivi de flux
"""

import argparse
import json
import sys
from pathlib import Path
from main import LogFlowTracker

def cmd_process_file(args):
    """Traite un fichier de logs"""
    tracker = LogFlowTracker(args.config)
    
    if not Path(args.file).exists():
        print(f"Erreur: Fichier {args.file} non trouvé")
        return 1
    
    print(f"Traitement du fichier: {args.file}")
    stats = tracker.process_log_file(args.file)
    
    print(f"Résultats:")
    print(f"  - Lignes totales: {stats['total_lines']}")
    print(f"  - Lignes traitées: {stats['processed_lines']}")
    print(f"  - Lignes échouées: {stats['failed_lines']}")
    
    if stats['failed_lines'] > 0:
        print(f"  - Taux de succès: {(stats['processed_lines']/stats['total_lines'])*100:.1f}%")
    
    return 0

def cmd_process_line(args):
    """Traite une ligne de log unique"""
    tracker = LogFlowTracker(args.config)
    
    success = tracker.process_log_line(
        args.line, 
        force_flux_type=getattr(args, 'flux_type', None),
        force_application=getattr(args, 'application', None)
    )
    
    if success:
        print("✓ Ligne traitée avec succès")
        return 0
    else:
        print("✗ Échec du traitement de la ligne")
        return 1

def cmd_get_flux(args):
    """Récupère les détails d'un flux"""
    tracker = LogFlowTracker(args.config)
    
    details = tracker.get_flux_details(args.reference)
    
    if details:
        if args.json:
            print(json.dumps(details, indent=2, ensure_ascii=False))
        else:
            # Afficher les informations sur le sous-flux si applicable
            subflow_info = details.get('subflow_info', {})
            is_subflow = subflow_info.get('is_subflow', False)
            
            if is_subflow:
                print(f"=== Sous-flux {args.reference} (flux parent: {subflow_info['parent_reference']}) ===")
                print("⚠️  La référence demandée correspond à un sous-flux.")
                print(f"📄 Affichage des détails du flux parent: {subflow_info['parent_reference']}")
                print()
                
                # Détails du sous-flux spécifique
                subflow_details = subflow_info['subflow_details']
                print(f"🔹 Détails du sous-flux {args.reference}:")
                print(f"   Status: {subflow_details['status']}")
                print(f"   Créé: {subflow_details['created_at']}")
                print(f"   Modifié: {subflow_details['updated_at']}")
                
                # Logs spécifiques au sous-flux
                subflow_logs = subflow_info.get('subflow_logs', [])
                if subflow_logs:
                    print(f"\n🔹 Logs spécifiques au sous-flux ({len(subflow_logs)} entrées):")
                    for i, log in enumerate(subflow_logs, 1):
                        print(f"   {i}. [{log['timestamp']}] {log['application']}/{log['log_type']}")
                        print(f"      {log['raw_log'][:80]}...")
                
                print("\n" + "="*60)
                print(f"📋 Détails complets du flux parent: {subflow_info['parent_reference']}")
                print("="*60)
            else:
                print(f"=== Flux {args.reference} ===")
            
            # Afficher les détails du flux principal (parent si sous-flux, sinon le flux lui-même)
            flux = details['flux']
            print(f"Type: {flux['flux_type']}")
            print(f"Status: {flux['status']}")
            print(f"Créé: {flux['created_at']}")
            print(f"Modifié: {flux['updated_at']}")
            
            print(f"\nLogs du flux principal ({len(details['logs'])} entrées):")
            for i, log in enumerate(details['logs'], 1):
                print(f"  {i}. [{log['timestamp']}] {log['application']}/{log['log_type']}")
                print(f"     {log['raw_log'][:80]}...")
            
            if details['cross_references']:
                print(f"\nRéférences croisées ({len(details['cross_references'])}):")
                for ref in details['cross_references']:
                    print(f"  → {ref['target_reference']} ({ref['reference_field']})")
            
            if details['children']:
                print(f"\nSous-flux ({len(details['children'])}):")
                for child in details['children']:
                    # Marquer le sous-flux demandé s'il fait partie des enfants
                    marker = " ← (demandé)" if is_subflow and child['reference'] == args.reference else ""
                    print(f"  - {child['reference']} ({child['status']}){marker}")
    else:
        print(f"Flux '{args.reference}' non trouvé")
        return 1
    
    return 0

def cmd_process_json(args):
    """Traite des logs au format JSON"""
    tracker = LogFlowTracker(args.config)
    
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    else:
        json_data = json.loads(sys.stdin.read())
    
    print("Traitement des logs JSON...")
    stats = tracker.process_json_logs(json_data)
    
    print(f"Résultats:")
    print(f"  - Entrées totales: {stats['total_entries']}")
    print(f"  - Entrées traitées: {stats['processed_entries']}")
    print(f"  - Entrées échouées: {stats['failed_entries']}")
    
    return 0

def cmd_parse_test(args):
    """Teste le parsing d'une ligne sans l'enregistrer"""
    tracker = LogFlowTracker(args.config)
    
    parsed = tracker.parse_log_line(
        args.line,
        force_flux_type=getattr(args, 'flux_type', None),
        force_application=getattr(args, 'application', None)
    )
    
    if parsed:
        print("✓ Ligne parsée avec succès:")
        print(f"  Flux: {parsed.flux_type}")
        print(f"  Application: {parsed.application}")
        print(f"  Type: {parsed.log_type}")
        print(f"  Timestamp: {parsed.timestamp}")
        print(f"  Identifiants: {parsed.identifier_fields}")
        print(f"  Payload: {parsed.payload_fields}")
        if parsed.reference_links:
            print(f"  Références: {parsed.reference_links}")
    else:
        print("✗ Impossible de parser la ligne")
        return 1
    
    return 0

def cmd_list_config(args):
    """Liste les flux types et applications disponibles"""
    tracker = LogFlowTracker(args.config)
    
    print("=== Configuration des flux disponibles ===\n")
    
    for flux_name, flux_patterns in tracker.patterns.items():
        print(f"📋 Flux: {flux_name}")
        flux_config = tracker.config['flux_types'][flux_name]
        print(f"   Description: {flux_config.get('description', 'N/A')}")
        print(f"   Applications:")
        
        for app_name, app_patterns in flux_patterns.items():
            print(f"     • {app_name}")
            log_types = list(app_patterns.keys())
            print(f"       Types de logs: {', '.join(log_types)}")
        
        print()  # Ligne vide entre les flux
    
    return 0

def main():
    parser = argparse.ArgumentParser(description='Utilitaire de suivi de flux multi-applicatifs')
    parser.add_argument('--config', '-c', default='config.yaml', 
                       help='Fichier de configuration (défaut: config.yaml)')
    
    subparsers = parser.add_subparsers(dest='command', help='Commandes disponibles')
    
    # Commande process-file
    parser_file = subparsers.add_parser('process-file', help='Traite un fichier de logs')
    parser_file.add_argument('file', help='Chemin vers le fichier de logs')
    parser_file.set_defaults(func=cmd_process_file)
      # Commande process-line
    parser_line = subparsers.add_parser('process-line', help='Traite une ligne de log')
    parser_line.add_argument('line', help='Ligne de log à traiter')
    parser_line.add_argument('--flux-type', '-f', help='Forcer un type de flux spécifique')
    parser_line.add_argument('--application', '-a', help='Forcer une application spécifique')
    parser_line.set_defaults(func=cmd_process_line)
    
    # Commande get-flux
    parser_flux = subparsers.add_parser('get-flux', help='Récupère les détails d\'un flux')
    parser_flux.add_argument('reference', help='Référence du flux')
    parser_flux.add_argument('--json', action='store_true', help='Sortie en format JSON')
    parser_flux.set_defaults(func=cmd_get_flux)
    
    # Commande process-json
    parser_json = subparsers.add_parser('process-json', help='Traite des logs JSON')
    parser_json.add_argument('--file', '-f', help='Fichier JSON (sinon lecture depuis stdin)')
    parser_json.set_defaults(func=cmd_process_json)
      # Commande parse-test
    parser_test = subparsers.add_parser('parse-test', help='Teste le parsing d\'une ligne')
    parser_test.add_argument('line', help='Ligne de log à tester')
    parser_test.add_argument('--flux-type', '-f', help='Forcer un type de flux spécifique')
    parser_test.add_argument('--application', '-a', help='Forcer une application spécifique')
    parser_test.set_defaults(func=cmd_parse_test)
    
    # Commande list-config
    parser_list = subparsers.add_parser('list-config', help='Liste les flux et applications disponibles')
    parser_list.set_defaults(func=cmd_list_config)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        return args.func(args)
    except Exception as e:
        print(f"Erreur: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
