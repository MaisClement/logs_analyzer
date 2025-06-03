#!/usr/bin/env python3
"""
Script de test automatisé pour valider la robustesse du système
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from main import LogFlowTracker
from cli import main as cli_main

class TestRunner:
    def __init__(self):
        self.tracker = LogFlowTracker()
        self.test_results = {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'details': []
        }
    
    def log_test(self, test_name: str, success: bool, details: str = ""):
        """Enregistre le résultat d'un test"""
        self.test_results['total_tests'] += 1
        if success:
            self.test_results['passed_tests'] += 1
            status = "✓ PASS"
        else:
            self.test_results['failed_tests'] += 1
            status = "✗ FAIL"
        
        print(f"{status} - {test_name}")
        if details:
            print(f"     {details}")
        
        self.test_results['details'].append({
            'test_name': test_name,
            'status': 'PASS' if success else 'FAIL',
            'details': details
        })
    
    def test_file_processing(self):
        """Test du traitement des fichiers de logs"""
        print("\n=== Test du traitement des fichiers ===")
        
        test_files = [
            'exemples_logs/traitement_commande.log',
            'exemples_logs/test_complexe.log',
            'exemples_logs/test_stress.log',
            'exemples_logs/test_erreurs.log',
            'exemples_logs/test_concurrent.log'
        ]
        
        for file_path in test_files:
            if Path(file_path).exists():
                try:
                    stats = self.tracker.process_log_file(file_path)
                    success = stats['processed_lines'] > 0
                    details = f"Lignes: {stats['total_lines']}, Traitées: {stats['processed_lines']}, Échouées: {stats['failed_lines']}"
                    self.log_test(f"Fichier {file_path}", success, details)
                except Exception as e:
                    self.log_test(f"Fichier {file_path}", False, f"Erreur: {e}")
            else:
                self.log_test(f"Fichier {file_path}", False, "Fichier non trouvé")
    
    def test_json_processing(self):
        """Test du traitement des logs JSON"""
        print("\n=== Test du traitement JSON ===")
        
        json_files = [
            'exemples_logs/elasticsearch_logs.json',
            'exemples_logs/elasticsearch_complexe.json'
        ]
        
        for file_path in json_files:
            if Path(file_path).exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        json_data = json.load(f)
                    
                    stats = self.tracker.process_json_logs(json_data)
                    success = stats['processed_entries'] > 0
                    details = f"Entrées: {stats['total_entries']}, Traitées: {stats['processed_entries']}, Échouées: {stats['failed_entries']}"
                    self.log_test(f"JSON {file_path}", success, details)
                except Exception as e:
                    self.log_test(f"JSON {file_path}", False, f"Erreur: {e}")
            else:
                self.log_test(f"JSON {file_path}", False, "Fichier non trouvé")
    
    def test_individual_lines(self):
        """Test du traitement ligne par ligne"""
        print("\n=== Test ligne par ligne ===")
        
        test_lines = [
            # Ligne normale
            ("[2024-01-15 10:30:00] COMMANDE_RECU CMD_TEST_001 client=CLI_TEST articles=[ART_TEST]", True),
            
            # Ligne avec caractères spéciaux
            ("[2024-01-15 10:30:00] COMMANDE_RECU CMD_SPÉCIAL_001 client=CLI_ÉMOJI_😀 articles=[ART_中文_001]", True),
            
            # Ligne malformée
            ("Cette ligne n'est pas un log valide", False),
            
            # Ligne avec date invalide
            ("[2024-13-45 25:99:99] COMMANDE_RECU CMD_BAD client=CLI_001 articles=[ART_001]", False),
            
            # Ligne vide
            ("", False),
            
            # Ligne avec données manquantes
            ("[2024-01-15 10:30:00] COMMANDE_RECU  client= articles=[]", False),
        ]
        
        for line, expected_success in test_lines:
            try:
                result = self.tracker.process_log_line(line)
                success = (result == expected_success)
                details = f"Attendu: {'succès' if expected_success else 'échec'}, Obtenu: {'succès' if result else 'échec'}"
                self.log_test(f"Ligne: {line[:50]}...", success, details)
            except Exception as e:
                success = not expected_success  # Si exception et échec attendu, c'est bon
                details = f"Exception: {e}"
                self.log_test(f"Ligne: {line[:50]}...", success, details)
    
    def test_forced_application(self):
        """Test du forçage d'application"""
        print("\n=== Test forçage d'application ===")
        
        # Test avec application forcée correcte
        line = "[2024-01-15 10:30:00] COMMANDE_RECU CMD_FORCE_001 client=CLI_001 articles=[ART_001]"
        try:
            result = self.tracker.process_log_line(line, force_application="Frontend")
            self.log_test("Forçage Frontend valide", result, "Application forcée correctement")
        except Exception as e:
            self.log_test("Forçage Frontend valide", False, f"Erreur: {e}")
        
        # Test avec application forcée incorrecte
        try:
            result = self.tracker.process_log_line(line, force_application="ApplicationInexistante")
            self.log_test("Forçage application inexistante", not result, "Rejet attendu pour application inexistante")
        except Exception as e:
            self.log_test("Forçage application inexistante", True, "Exception attendue")
    
    def test_cross_references(self):
        """Test des références croisées"""
        print("\n=== Test des références croisées ===")
        
        # Créer une séquence de logs avec références croisées
        lines = [
            "[2024-01-15 10:30:00] COMMANDE_RECU CMD_REF_001 client=CLI_001 articles=[ART_001]",
            "[2024-01-15 10:30:05] VALIDATION_COMMANDE CMD_REF_001 → ordre=ORD_REF_001 status=VALIDE",
            "[2024-01-15 10:30:10] ORDRE_TRAITE ORD_REF_001 → livraison=LIV_REF_001"
        ]
        
        try:
            all_success = True
            for line in lines:
                if not self.tracker.process_log_line(line):
                    all_success = False
            
            # Vérifier que les références croisées ont été créées
            details = self.tracker.get_flux_details("CMD_REF_001")
            has_cross_refs = details and len(details['cross_references']) > 0
            
            success = all_success and has_cross_refs
            details_msg = f"Tous logs traités: {all_success}, Références trouvées: {has_cross_refs}"
            self.log_test("Références croisées", success, details_msg)
            
        except Exception as e:
            self.log_test("Références croisées", False, f"Erreur: {e}")
    
    def test_sub_flows(self):
        """Test des sous-flux"""
        print("\n=== Test des sous-flux ===")
        
        lines = [
            "[2024-01-15 10:30:00] COMMANDE_RECU CMD_SUB_001 client=CLI_001 articles=[ART_SUB_001, ART_SUB_002]",
            "[2024-01-15 10:30:02] CREATION_ARTICLES CMD_SUB_001 articles=[ART_SUB_001, ART_SUB_002]",
            "[2024-01-15 10:30:05] TRAITEMENT_ARTICLE ART_SUB_001 parent=CMD_SUB_001 stock=DISPONIBLE",
            "[2024-01-15 10:30:06] TRAITEMENT_ARTICLE ART_SUB_002 parent=CMD_SUB_001 stock=DISPONIBLE"
        ]
        
        try:
            all_success = True
            for line in lines:
                if not self.tracker.process_log_line(line):
                    all_success = False
            
            # Vérifier que les sous-flux ont été créés
            details = self.tracker.get_flux_details("CMD_SUB_001")
            has_children = details and len(details['children']) > 0
            
            success = all_success and has_children
            details_msg = f"Tous logs traités: {all_success}, Enfants trouvés: {has_children}"
            self.log_test("Sous-flux", success, details_msg)
            
        except Exception as e:
            self.log_test("Sous-flux", False, f"Erreur: {e}")
    
    def test_database_integrity(self):
        """Test de l'intégrité de la base de données"""
        print("\n=== Test d'intégrité DB ===")
        
        try:
            # Vérifier que la DB existe et contient des données
            conn = sqlite3.connect('logs_flow.db')
            cursor = conn.cursor()
            
            # Compter les enregistrements dans chaque table
            tables = ['flux_types', 'applications', 'flux_instances', 'log_entries', 'cross_references']
            counts = {}
            
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cursor.fetchone()[0]
            
            conn.close()
            
            # Vérifier qu'il y a des données
            has_data = all(count > 0 for count in [counts['flux_types'], counts['applications'], counts['flux_instances']])
            
            details_msg = f"Compteurs: {counts}"
            self.log_test("Intégrité base de données", has_data, details_msg)
            
        except Exception as e:
            self.log_test("Intégrité base de données", False, f"Erreur: {e}")
    
    def test_performance(self):
        """Test de performance basique"""
        print("\n=== Test de performance ===")
        
        import time
        
        # Test avec 1000 lignes de log similaires
        start_time = time.time()
        
        try:
            count = 0
            for i in range(1000):
                line = f"[2024-01-15 10:30:{i%60:02d}] COMMANDE_RECU CMD_PERF_{i:03d} client=CLI_{i:03d} articles=[ART_{i:03d}]"
                if self.tracker.process_log_line(line):
                    count += 1
            
            end_time = time.time()
            duration = end_time - start_time
            rate = count / duration if duration > 0 else 0
            
            success = count > 0 and duration < 60  # Moins d'une minute pour 1000 logs
            details_msg = f"Traité {count}/1000 logs en {duration:.2f}s ({rate:.1f} logs/s)"
            self.log_test("Performance 1000 logs", success, details_msg)
            
        except Exception as e:
            self.log_test("Performance 1000 logs", False, f"Erreur: {e}")
    
    def run_all_tests(self):
        """Lance tous les tests"""
        print("🚀 Début des tests de robustesse")
        print("=" * 50)
        
        # Supprimer l'ancienne DB pour repartir à zéro
        if Path('logs_flow.db').exists():
            os.remove('logs_flow.db')
        
        # Réinitialiser le tracker
        self.tracker = LogFlowTracker()
        
        # Lancer tous les tests
        self.test_file_processing()
        self.test_json_processing()
        self.test_individual_lines()
        self.test_forced_application()
        self.test_cross_references()
        self.test_sub_flows()
        self.test_database_integrity()
        self.test_performance()
        
        # Résumé final
        print("\n" + "=" * 50)
        print("📊 RÉSUMÉ DES TESTS")
        print("=" * 50)
        print(f"Total: {self.test_results['total_tests']}")
        print(f"✓ Réussis: {self.test_results['passed_tests']}")
        print(f"✗ Échecs: {self.test_results['failed_tests']}")
        
        if self.test_results['failed_tests'] > 0:
            print(f"📉 Taux de réussite: {(self.test_results['passed_tests']/self.test_results['total_tests'])*100:.1f}%")
        else:
            print("🎉 Tous les tests ont réussi !")
        
        return self.test_results['failed_tests'] == 0

def main():
    """Point d'entrée principal"""
    runner = TestRunner()
    success = runner.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
