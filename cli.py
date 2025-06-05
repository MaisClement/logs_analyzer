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
    
    # Vérifier si des références croisées existent pour ce flux
    details = tracker.get_flux_details(args.reference)
    if not details:
        print(f"Flux '{args.reference}' non trouvé")
        return 1      # Si des références croisées existent, récupérer tous les flux liés
    has_cross_references = ((details.get('cross_references') and len(details['cross_references']) > 0) or 
                           (details.get('incoming_references') and len(details['incoming_references']) > 0))
    if has_cross_references:
        # Utiliser la nouvelle méthode pour récupérer tous les flux liés
        linked_flows_data = tracker.get_all_linked_flows(args.reference)
        
        if args.json:
            print(json.dumps(linked_flows_data, indent=2, ensure_ascii=False))
        else:
            print(f"RÉFÉRENCES CROISÉES DÉTECTÉES - Affichage de tous les flux liés")
            print("=" * 80)
            print(f"Flux initial demandé: {args.reference}")
            print(f"Total des flux liés: {linked_flows_data['total_linked_flows']}")
            print()
            
            # Afficher le résumé des connexions
            cross_ref_map = linked_flows_data['cross_reference_map']
            if cross_ref_map['summary']['total_connections'] > 0:
                print(f"📊 Résumé des connexions:")
                print(f"   • Total des connexions: {cross_ref_map['summary']['total_connections']}")
                if cross_ref_map['summary']['bidirectional_pairs']:
                    print(f"   • Paires bidirectionnelles: {len(cross_ref_map['summary']['bidirectional_pairs'])}")
                print()
            
            print("-" * 60)
              # Collecter tous les logs de tous les flux pour un affichage unifié
            all_logs = []
            main_flux_ref = None
            main_flux_data = None
            subflow_source = None
            requested_flux_data = None
              # Identifier le flux demandé et collecter les informations
            for ref, flux_data in linked_flows_data['linked_flows'].items():
                subflow_info = flux_data.get('subflow_info', {})
                is_subflow = subflow_info.get('is_subflow', False)
                
                # Identifier si c'est le flux demandé ou si la référence demandée est un sous-flux de ce flux
                flux_contains_requested = (ref == args.reference or 
                                         (is_subflow and subflow_info.get('requested_reference') == args.reference))
                
                if flux_contains_requested:
                    requested_flux_data = flux_data
                    if is_subflow and subflow_info.get('requested_reference') == args.reference:
                        subflow_source = subflow_info['parent_reference']
                    elif ref == args.reference and not is_subflow:
                        # Le flux demandé est le flux principal lui-même
                        requested_flux_data = flux_data
                
                # Chercher si args.reference est dans les enfants de ce flux
                children = flux_data.get('children', [])
                for child in children:
                    if child['reference'] == args.reference:
                        subflow_source = ref
                        # Créer les infos du sous-flux pour l'affichage
                        if not requested_flux_data:
                            requested_flux_data = {
                                'subflow_info': {
                                    'is_subflow': True,
                                    'requested_reference': args.reference,
                                    'parent_reference': ref,
                                    'subflow_details': {
                                        'reference': child['reference'],
                                        'status': child['status']
                                    }
                                }
                            }
                        break
                
                # Identifier le flux principal de la chaîne (celui qui a des références sortantes mais pas entrantes, ou le plus ancien)
                incoming_refs = flux_data.get('incoming_references', [])
                outgoing_refs = flux_data.get('outgoing_references', [])
                
                # Le flux principal est typiquement celui qui démarre la chaîne (pas de références entrantes)
                if not main_flux_ref:
                    main_flux_ref = ref
                    main_flux_data = flux_data
                elif not incoming_refs and outgoing_refs:
                    # Flux qui génère des références mais n'en reçoit pas = flux principal
                    main_flux_ref = ref
                    main_flux_data = flux_data
                elif incoming_refs and not outgoing_refs and not main_flux_data.get('outgoing_references'):
                    # Si le flux actuel principal n'a pas de références sortantes, prendre celui qui en a
                    continue
                
                # Ajouter les logs avec préfixe de flux
                for log in flux_data['logs']:
                    log_with_prefix = log.copy()
                    log_with_prefix['flux_prefix'] = ref
                    all_logs.append(log_with_prefix)
            
            # Si on a une source de sous-flux, s'assurer que c'est bien le flux principal affiché
            if subflow_source and subflow_source in linked_flows_data['linked_flows']:
                main_flux_ref = subflow_source
                main_flux_data = linked_flows_data['linked_flows'][subflow_source]            # Informations sur le sous-flux si applicable
            if subflow_source:
                print(f"⚠️  Sous-flux de: {subflow_source}")
                print(f"📄 Affichage des informations parentes (flux principal)")
                print()
            
            # Informations principales du flux (parent ou principal de la chaîne)
            if main_flux_data:
                flux = main_flux_data['flux']
                print(f"Flux: {main_flux_ref}")
                print(f"Type: {flux['flux_type']}")
                print(f"Status: {flux['status']}")
                print(f"Créé: {flux['created_at']}")
                print(f"Modifié: {flux['updated_at']}")
                
                # Si c'est un sous-flux qui a été demandé, afficher aussi ses détails spécifiques
                if subflow_source and requested_flux_data:
                    subflow_info = requested_flux_data.get('subflow_info', {})
                    if subflow_info.get('is_subflow'):
                        subflow_details = subflow_info.get('subflow_details', {})
                        print()
                        print(f"🔹 Détails du sous-flux demandé ({args.reference}):")
                        print(f"   Status: {subflow_details.get('status', 'N/A')}")
                        print(f"   Créé: {subflow_details.get('created_at', 'N/A')}")
                        print(f"   Modifié: {subflow_details.get('updated_at', 'N/A')}")
                        
                        # Logs spécifiques au sous-flux
                        subflow_logs = subflow_info.get('subflow_logs', [])
                        if subflow_logs:
                            print(f"   Logs spécifiques: {len(subflow_logs)} entrées")
                
                print()
            
            # Affichage condensé des logs avec préfixe du flux
            if all_logs:
                print(f"Logs ({len(all_logs)} entrées):")
                # Trier les logs par timestamp
                all_logs.sort(key=lambda x: x['timestamp'])
                
                for j, log in enumerate(all_logs, 1):
                    print(f"[{log['flux_prefix']}]  {j}. [{log['timestamp']}] {log['application']}/{log['log_type']}")
                    print(f"[{log['flux_prefix']}]     {log['raw_log'][:80]}...")
                print()
            
            # Références sortantes consolidées
            all_outgoing_refs = []
            for ref, flux_data in linked_flows_data['linked_flows'].items():
                for ref_out in flux_data['outgoing_references']:
                    ref_info = f"  → {ref_out['target_reference']} ({ref_out['reference_field']})"
                    if ref_info not in all_outgoing_refs:
                        all_outgoing_refs.append(ref_info)
            
            if all_outgoing_refs:
                print(f"Références sortantes ({len(all_outgoing_refs)}):")
                for ref_out in all_outgoing_refs:
                    print(ref_out)
                print()
            
            # Sous-flux consolidés (sans doublons)
            all_children = set()
            for ref, flux_data in linked_flows_data['linked_flows'].items():
                for child in flux_data['children']:
                    all_children.add(f"  - {child['reference']} ({child['status']})")
            
            if all_children:
                print(f"Sous-flux ({len(all_children)}):")
                for child in sorted(all_children):
                    print(child)
                print()
            
            # Afficher la carte des connexions
            if cross_ref_map['connections']:
                print("🗺️  CARTE DES CONNEXIONS:")
                print("-" * 40)
                for connection in cross_ref_map['connections']:
                    print(f"  {connection['source_reference']} → {connection['target_reference']}")
                    print(f"    via {connection['reference_field']} = {connection['reference_value']}")
                print()
    
    else:
        # Pas de références croisées, utiliser l'affichage standard
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

def cmd_incomplete_flows(args):
    """Analyse les flux incomplets"""
    tracker = LogFlowTracker(args.config)
    
    # Récupérer les flux incomplets
    incomplete_flows = tracker.get_incomplete_flows(max_age_hours=getattr(args, 'max_age_hours', None))
    
    if not incomplete_flows:
        print("✅ Aucun flux incomplet trouvé !")
        return 0
    
    if args.json:
        print(json.dumps(incomplete_flows, indent=2, ensure_ascii=False))
        return 0
    
    # Affichage formaté
    total_incomplete = sum(len(instances) for instances in incomplete_flows.values())
    print(f"🔍 Analyse des flux incomplets - {total_incomplete} flux détectés")
    print("=" * 60)
    
    for flux_type, instances in incomplete_flows.items():
        print(f"\n📋 {flux_type} ({len(instances)} flux incomplets)")
        print("-" * 40)
        
        for i, instance in enumerate(instances, 1):
            # Icône selon l'âge
            if instance['age_hours'] > 24:
                age_icon = "🚨"  # Très ancien
            elif instance['age_hours'] > 8:
                age_icon = "⚠️"   # Ancien
            else:
                age_icon = "🕐"  # Récent
            
            print(f"{i:2d}. {age_icon} {instance['reference']}")
            print(f"     Âge: {instance['age_hours']}h | Complétion: {instance['completion_rate']}%")
            print(f"     Status: {instance['status']}")
            
            if instance['last_activity']:
                print(f"     Dernière activité: {instance['last_activity'][:19]} ({instance['last_log_type']})")
            
            if instance['missing_stages']:
                missing_str = ", ".join(instance['missing_stages'])
                print(f"     ❌ Étapes manquantes: {missing_str}")
            
            if instance['present_stages']:
                present_str = ", ".join(instance['present_stages'])
                print(f"     ✅ Étapes présentes: {present_str}")
            
            if instance['children_count'] > 0:
                print(f"     👥 Sous-flux: {instance['children_count']}")
            
            print()
    
    # Statistiques globales
    print("=" * 60)
    print("📊 STATISTIQUES GLOBALES")
    print("=" * 60)
    
    # Compter par type d'étape manquante
    missing_stages_count = {}
    total_age = 0
    oldest_flux = None
    
    for flux_type, instances in incomplete_flows.items():
        for instance in instances:
            total_age += instance['age_hours']
            
            if not oldest_flux or instance['age_hours'] > oldest_flux['age_hours']:
                oldest_flux = instance
            
            for missing_stage in instance['missing_stages']:
                missing_stages_count[missing_stage] = missing_stages_count.get(missing_stage, 0) + 1
    
    if total_incomplete > 0:
        avg_age = total_age / total_incomplete
        print(f"Âge moyen des flux incomplets: {avg_age:.1f}h")
        
        if oldest_flux:
            print(f"Flux le plus ancien: {oldest_flux['reference']} ({oldest_flux['age_hours']}h)")
        
        print("\nÉtapes les plus souvent manquantes:")
        for stage, count in sorted(missing_stages_count.items(), key=lambda x: x[1], reverse=True):
            print(f"  • {stage}: {count} fois")
    
    return 0

def cmd_stats(args):
    """Affiche les statistiques des flux par étapes"""
    tracker = LogFlowTracker(args.config)
    
    # Récupérer les statistiques avec ou sans détails
    include_details = getattr(args, 'details', False)
    stats = tracker.get_stats(include_details=include_details)
    
    if args.json:
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return 0
    
    # Affichage formaté
    print("📊 STATISTIQUES DES FLUX")
    print("=" * 60)
    
    # Vue d'ensemble
    print(f"Total des flux: {stats['total_flux']}")
    if stats['database_overview']['total_subflows'] > 0:
        main_flux_count = stats['total_flux'] - stats['database_overview']['total_subflows']
        print(f"  • Flux principaux: {main_flux_count}")
        print(f"  • Sous-flux: {stats['database_overview']['total_subflows']}")
    
    print(f"Total des entrées de log: {stats['database_overview']['total_log_entries']}")
    print(f"Total des références croisées: {stats['database_overview']['total_cross_references']}")
    print()
    
    # Flux par type
    if stats['flux_by_type']:
        print("📋 FLUX PAR TYPE")
        print("-" * 40)
        for flux_type, info in stats['flux_by_type'].items():
            print(f"{flux_type}: {info['count']} flux")
            if info['description']:
                print(f"  └─ {info['description']}")
        print()
    
    # Flux par statut
    if stats['flux_by_status']:
        print("🔄 FLUX PAR STATUT")
        print("-" * 40)
        for status, count in stats['flux_by_status'].items():
            print(f"{status}: {count} flux")
        print()
    
    # Analyse des étapes par type de flux
    if stats['stages_analysis']:
        print("🎯 ANALYSE DES ÉTAPES PAR TYPE DE FLUX")
        print("-" * 40)
        
        for flux_type, analysis in stats['stages_analysis'].items():
            print(f"\n📊 {flux_type} ({analysis['total_flux']} flux)")
            print("─" * 30)
            
            # Étapes requises
            if analysis['required_stages']:
                print("  Étapes requises:")
                for stage in analysis['required_stages']:
                    if stage in analysis['stages']:
                        stage_info = analysis['stages'][stage]
                        print(f"    ✅ {stage}: {stage_info['count']}/{analysis['total_flux']} ({stage_info['percentage']}%)")
                    else:
                        print(f"    ❌ {stage}: 0/{analysis['total_flux']} (0%)")
            
            # Étapes optionnelles présentes
            optional_present = [stage for stage in analysis['stages'].keys() if stage in analysis['optional_stages']]
            if optional_present:
                print("  Étapes optionnelles présentes:")
                for stage in optional_present:
                    stage_info = analysis['stages'][stage]
                    print(f"    🔹 {stage}: {stage_info['count']}/{analysis['total_flux']} ({stage_info['percentage']}%)")
            
            # Autres étapes observées
            other_stages = [stage for stage in analysis['stages'].keys() 
                          if stage not in analysis['required_stages'] and stage not in analysis['optional_stages']]
            if other_stages:
                print("  Autres étapes observées:")
                for stage in other_stages:
                    stage_info = analysis['stages'][stage]
                    print(f"    📝 {stage}: {stage_info['count']}/{analysis['total_flux']} ({stage_info['percentage']}%)")
    
    # Statistiques globales des étapes
    if stats['global_stage_counts']:
        print(f"\n🌐 ÉTAPES LES PLUS UTILISÉES (tous types confondus)")
        print("-" * 40)
        
        # Trier par nombre d'occurrences
        sorted_stages = sorted(stats['global_stage_counts'].items(), key=lambda x: x[1], reverse=True)
        
        for stage, count in sorted_stages[:10]:  # Top 10
            print(f"  {stage}: {count} occurrences")
    
    # Statistiques sur les relations
    print(f"\n🔗 RELATIONS ENTRE FLUX")
    print("-" * 40)
    print(f"Flux avec références croisées: {stats['flux_with_cross_references']}")
    print(f"Flux avec sous-flux: {stats['flux_with_subflows']}")
    
    if stats['total_flux'] > 0:
        cross_ref_percentage = (stats['flux_with_cross_references'] / stats['total_flux']) * 100
        subflow_percentage = (stats['flux_with_subflows'] / stats['total_flux']) * 100
        print(f"  • {cross_ref_percentage:.1f}% des flux ont des références croisées")
        print(f"  • {subflow_percentage:.1f}% des flux ont des sous-flux")
    
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
      # Commande incomplete-flows
    parser_incomplete = subparsers.add_parser('incomplete-flows', help='Analyse les flux incomplets')
    parser_incomplete.add_argument('--max-age-hours', type=int, help='Âge maximum des flux à considérer (en heures)')
    parser_incomplete.add_argument('--json', action='store_true', help='Sortie en format JSON')
    parser_incomplete.set_defaults(func=cmd_incomplete_flows)    # Commande stats
    parser_stats = subparsers.add_parser('stats', help='Affiche les statistiques des flux par étapes')
    parser_stats.add_argument('--json', action='store_true', help='Sortie en format JSON')
    parser_stats.add_argument('--details', action='store_true', help='Inclut la liste des flux pour chaque étape (format JSON uniquement)')
    parser_stats.set_defaults(func=cmd_stats)
    
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
