#!/usr/bin/env python3
"""
Système de suivi de flux multi-applicatifs
Traite les logs ligne par ligne et suit les flux avec références croisées
"""

import re
import json
import yaml
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sqlalchemy.exc import IntegrityError

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

Base = declarative_base()

# Modèles SQLAlchemy
class FluxType(Base):
    __tablename__ = 'flux_types'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    
    flux_instances = relationship("FluxInstance", back_populates="flux_type")

class Application(Base):
    __tablename__ = 'applications'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    flux_type_id = Column(Integer, ForeignKey('flux_types.id'))
    
    logs = relationship("LogEntry", back_populates="application")

class FluxInstance(Base):
    __tablename__ = 'flux_instances'
    
    id = Column(Integer, primary_key=True)
    flux_type_id = Column(Integer, ForeignKey('flux_types.id'))
    reference = Column(String(200), nullable=False, index=True)
    status = Column(String(50), default='ACTIF')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    parent_id = Column(Integer, ForeignKey('flux_instances.id'))
    
    flux_type = relationship("FluxType", back_populates="flux_instances")
    logs = relationship("LogEntry", back_populates="flux_instance")
    children = relationship("FluxInstance", back_populates="parent")
    parent = relationship("FluxInstance", back_populates="children", remote_side=[id])
    cross_references = relationship("CrossReference", foreign_keys="CrossReference.source_flux_id", back_populates="source_flux")

class LogEntry(Base):
    __tablename__ = 'log_entries'
    
    id = Column(Integer, primary_key=True)
    flux_instance_id = Column(Integer, ForeignKey('flux_instances.id'))
    application_id = Column(Integer, ForeignKey('applications.id'))
    log_type = Column(String(50), nullable=False)  # ENTREE_FLUX, TRAITEMENT_APP, etc.
    timestamp = Column(DateTime, nullable=False)
    raw_log = Column(Text, nullable=False)
    parsed_data = Column(Text)  # JSON des données extraites
    processed_at = Column(DateTime, default=datetime.utcnow)
    
    flux_instance = relationship("FluxInstance", back_populates="logs")
    application = relationship("Application", back_populates="logs")

class CrossReference(Base):
    __tablename__ = 'cross_references'
    
    id = Column(Integer, primary_key=True)
    source_flux_id = Column(Integer, ForeignKey('flux_instances.id'))
    target_flux_id = Column(Integer, ForeignKey('flux_instances.id'))
    reference_field = Column(String(100), nullable=False)
    reference_value = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    source_flux = relationship("FluxInstance", foreign_keys=[source_flux_id], back_populates="cross_references")
    target_flux = relationship("FluxInstance", foreign_keys=[target_flux_id])

@dataclass
class LogPattern:
    regex: str
    timestamp_format: str
    identifier_fields: List[str]
    payload_fields: List[str]
    reference_links: List[str] = None
    
    def __post_init__(self):
        if self.reference_links is None:
            self.reference_links = []

@dataclass
class ParsedLog:
    timestamp: datetime
    log_type: str
    application: str
    flux_type: str
    identifier_fields: Dict[str, str]
    payload_fields: Dict[str, str]
    reference_links: Dict[str, str]
    raw_log: str

class LogFlowTracker:
    """Système principal de suivi des flux multi-applicatifs"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.engine = create_engine(self.config['database']['url'], echo=self.config['database']['echo'])
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.patterns = self._compile_patterns()
        
        # Créer les tables
        Base.metadata.create_all(self.engine)
        
        # Initialiser les flux types et applications
        self._init_database()
    
    def _load_config(self, config_path: str) -> Dict:
        """Charge la configuration YAML"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _compile_patterns(self) -> Dict[str, Dict[str, Dict[str, LogPattern]]]:
        """Compile les patterns regex pour chaque flux/app/type"""
        patterns = {}
        
        for flux_name, flux_config in self.config['flux_types'].items():
            patterns[flux_name] = {}
            
            for app_name, app_config in flux_config['applications'].items():
                patterns[flux_name][app_name] = {}
                
                for log_type, pattern_config in app_config['patterns'].items():
                    patterns[flux_name][app_name][log_type] = LogPattern(
                        regex=pattern_config['regex'],
                        timestamp_format=pattern_config['timestamp_format'],
                        identifier_fields=pattern_config['identifier_fields'],
                        payload_fields=pattern_config['payload_fields'],
                        reference_links=pattern_config.get('reference_links', [])
                    )
        
        return patterns
    
    def _init_database(self):
        """Initialise les types de flux et applications dans la DB"""
        session = self.SessionLocal()
        try:
            for flux_name, flux_config in self.config['flux_types'].items():
                # Créer ou récupérer le type de flux
                flux_type = session.query(FluxType).filter_by(name=flux_name).first()
                if not flux_type:
                    flux_type = FluxType(name=flux_name, description=flux_config['description'])
                    session.add(flux_type)
                    session.flush()
                  # Créer ou récupérer les applications
                for app_name in flux_config['applications'].keys():
                    app = session.query(Application).filter_by(
                        name=app_name, 
                        flux_type_id=flux_type.id
                    ).first()
                    if not app:
                        app = Application(name=app_name, flux_type_id=flux_type.id)
                        session.add(app)
            
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Erreur lors de l'initialisation de la DB: {e}")
            raise
        finally:
            session.close()
    
    def parse_log_line(self, log_line: str, force_flux_type: str = None, force_application: str = None) -> Optional[ParsedLog]:
        """Parse une ligne de log selon les patterns configurés
        
        Args:
            log_line: La ligne de log à parser
            force_flux_type: Forcer un type de flux spécifique
            force_application: Forcer une application spécifique
        """
        log_line = log_line.strip()
        if not log_line:
            return None
        
        # Si flux et application sont forcés, ne tester que ces patterns
        if force_flux_type and force_application:
            if force_flux_type in self.patterns and force_application in self.patterns[force_flux_type]:
                app_patterns = {force_application: self.patterns[force_flux_type][force_application]}
                flux_patterns_to_test = {force_flux_type: app_patterns}
            else:
                logger.error(f"Combinaison flux/app non trouvée: {force_flux_type}/{force_application}")
                return None
        # Si seul le flux est forcé
        elif force_flux_type:
            if force_flux_type in self.patterns:
                flux_patterns_to_test = {force_flux_type: self.patterns[force_flux_type]}
            else:
                logger.error(f"Type de flux non trouvé: {force_flux_type}")
                return None
        # Si seule l'application est forcée
        elif force_application:
            flux_patterns_to_test = {}
            for flux_name, flux_patterns in self.patterns.items():
                if force_application in flux_patterns:
                    if flux_name not in flux_patterns_to_test:
                        flux_patterns_to_test[flux_name] = {}
                    flux_patterns_to_test[flux_name][force_application] = flux_patterns[force_application]
            
            if not flux_patterns_to_test:
                logger.error(f"Application non trouvée: {force_application}")
                return None
        else:
            # Tester tous les patterns
            flux_patterns_to_test = self.patterns
        
        # Tenter de parser avec les patterns sélectionnés
        for flux_name, flux_patterns in flux_patterns_to_test.items():
            for app_name, app_patterns in flux_patterns.items():
                for log_type, pattern in app_patterns.items():
                    match = re.search(pattern.regex, log_line)
                    if match:
                        try:                            # Extraire les données
                            groups = match.groupdict()
                            
                            # Parser le timestamp avec gestion flexible
                            timestamp = self._parse_timestamp_flexible(
                                groups['timestamp'], 
                                pattern.timestamp_format
                            )
                            
                            # Extraire les champs identifiants
                            identifier_fields = {
                                field: groups.get(field, '') 
                                for field in pattern.identifier_fields
                            }
                            
                            # Extraire les champs payload
                            payload_fields = {
                                field: groups.get(field, '') 
                                for field in pattern.payload_fields                            }
                            
                            # Extraire les références croisées
                            reference_links = {
                                field: groups.get(field, '') 
                                for field in pattern.reference_links
                            }
                            
                            return ParsedLog(
                                timestamp=timestamp,
                                log_type=log_type,
                                application=app_name,
                                flux_type=flux_name,
                                identifier_fields=identifier_fields,
                                payload_fields=payload_fields,
                                reference_links=reference_links,
                                raw_log=log_line
                            )
                        
                        except Exception as e:
                            logger.warning(f"Erreur parsing log: {e} - Line: {log_line}")
                            continue
        
        logger.debug(f"Ligne non reconnue: {log_line}")
        return None
    
    def process_log_line(self, log_line: str, force_flux_type: str = None, force_application: str = None) -> bool:
        """Traite une ligne de log complète"""
        parsed_log = self.parse_log_line(log_line, force_flux_type, force_application)
        if not parsed_log:
            return False
        
        session = self.SessionLocal()
        try:
            # Récupérer les entités de base
            flux_type = session.query(FluxType).filter_by(name=parsed_log.flux_type).first()
            application = session.query(Application).filter_by(
                name=parsed_log.application,
                flux_type_id=flux_type.id
            ).first()
            
            if not flux_type or not application:
                logger.error(f"Type de flux ou application non trouvé: {parsed_log.flux_type}, {parsed_log.application}")
                return False
            
            # Gérer l'instance de flux
            flux_instance = self._get_or_create_flux_instance(
                session, flux_type, parsed_log
            )
            
            # Créer l'entrée de log
            log_entry = LogEntry(
                flux_instance_id=flux_instance.id,
                application_id=application.id,
                log_type=parsed_log.log_type,
                timestamp=parsed_log.timestamp,
                raw_log=parsed_log.raw_log,
                parsed_data=json.dumps({
                    'identifier_fields': parsed_log.identifier_fields,
                    'payload_fields': parsed_log.payload_fields,
                    'reference_links': parsed_log.reference_links
                })
            )
            
            session.add(log_entry)
            
            # Gérer les références croisées
            self._handle_cross_references(session, flux_instance, parsed_log)
            
            # Gérer les sous-flux
            self._handle_sub_flows(session, flux_instance, parsed_log)
            
            session.commit()
            logger.debug(f"Log traité avec succès: {parsed_log.flux_type}/{parsed_log.application}")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Erreur traitement log: {e}")
            return False
        finally:
            session.close()
    
    def _get_or_create_flux_instance(self, session: Session, flux_type: FluxType, parsed_log: ParsedLog) -> FluxInstance:
        """Récupère ou crée une instance de flux"""
        # Déterminer la référence principale
        main_reference = None
        for field_name, field_value in parsed_log.identifier_fields.items():
            if field_value:
                main_reference = field_value
                break
        
        if not main_reference:
            raise ValueError("Aucune référence principale trouvée")
        
        # Chercher l'instance existante
        flux_instance = session.query(FluxInstance).filter_by(
            flux_type_id=flux_type.id,
            reference=main_reference
        ).first()
        
        # Créer si nécessaire
        if not flux_instance:
            flux_instance = FluxInstance(
                flux_type_id=flux_type.id,
                reference=main_reference,
                status='ACTIF'
            )
            session.add(flux_instance)
            session.flush()
        
        return flux_instance
    def _handle_cross_references(self, session: Session, flux_instance: FluxInstance, parsed_log: ParsedLog):
        """Gère les références croisées entre flux"""
        for ref_field, ref_value in parsed_log.reference_links.items():
            if not ref_value:
                continue
            
            # Chercher un flux cible avec cette référence
            target_flux = session.query(FluxInstance).filter_by(reference=ref_value).first()
            
            # Si le flux cible n'existe pas, le créer automatiquement
            if not target_flux:
                # Déterminer le type de flux pour la référence
                # Par défaut, utiliser le même type que le flux source
                target_flux = FluxInstance(
                    flux_type_id=flux_instance.flux_type_id,
                    reference=ref_value,
                    status='ACTIF'
                )
                session.add(target_flux)
                session.flush()  # Pour obtenir l'ID
                logger.debug(f"Flux cible créé automatiquement: {ref_value}")
            
            if target_flux and target_flux.id != flux_instance.id:
                # Créer la référence croisée si elle n'existe pas
                existing_ref = session.query(CrossReference).filter_by(
                    source_flux_id=flux_instance.id,
                    target_flux_id=target_flux.id,
                    reference_field=ref_field,
                    reference_value=ref_value
                ).first()
                
                if not existing_ref:
                    cross_ref = CrossReference(
                        source_flux_id=flux_instance.id,
                        target_flux_id=target_flux.id,
                        reference_field=ref_field,
                        reference_value=ref_value
                    )
                    session.add(cross_ref)
                    logger.debug(f"Référence croisée créée: {flux_instance.reference} → {target_flux.reference}")
    
    def _handle_sub_flows(self, session: Session, flux_instance: FluxInstance, parsed_log: ParsedLog):
        """Gère les sous-flux (relations parent-enfant)"""
        if parsed_log.log_type == 'CREATION_ENFANTS':
            # Extraire les IDs des enfants
            enfants_ids = parsed_log.payload_fields.get('enfants_ids', '')
            if enfants_ids:
                # Parser les IDs (format: "ART_001, ART_002, ART_003")
                ids_list = [id.strip() for id in enfants_ids.split(',')]
                
                for child_id in ids_list:
                    # Créer l'instance enfant
                    child_instance = FluxInstance(
                        flux_type_id=flux_instance.flux_type_id,
                        reference=child_id,
                        status='ACTIF',
                        parent_id=flux_instance.id
                    )
                    session.add(child_instance)
        
        elif parsed_log.log_type == 'TRAITEMENT_ENFANT':
            # Lier à l'instance parent si nécessaire
            parent_ref = parsed_log.payload_fields.get('parent_ref')
            if parent_ref:
                parent_flux = session.query(FluxInstance).filter_by(reference=parent_ref).first()
                if parent_flux and not flux_instance.parent_id:
                    flux_instance.parent_id = parent_flux.id
    
    def process_log_file(self, file_path: str) -> Dict[str, int]:
        """Traite un fichier de logs ligne par ligne"""
        stats = {
            'total_lines': 0,
            'processed_lines': 0,
            'failed_lines': 0
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    stats['total_lines'] += 1
                    
                    if self.process_log_line(line):
                        stats['processed_lines'] += 1
                    else:
                        stats['failed_lines'] += 1
                    
                    # Log des progrès
                    if stats['total_lines'] % 1000 == 0:
                        logger.info(f"Traité {stats['total_lines']} lignes...")
        
        except Exception as e:
            logger.error(f"Erreur lecture fichier {file_path}: {e}")
            raise
        
        logger.info(f"Traitement terminé: {stats}")
        return stats
    
    def process_json_logs(self, json_data: Union[str, List[Dict]]) -> Dict[str, int]:
        """Traite des logs au format JSON (ex: depuis Elasticsearch)"""
        stats = {
            'total_entries': 0,
            'processed_entries': 0,
            'failed_entries': 0
        }
        
        # Parser JSON si c'est une string
        if isinstance(json_data, str):
            json_data = json.loads(json_data)
        
        # Traiter chaque entrée
        for entry in json_data:
            stats['total_entries'] += 1
            
            # Extraire le message de log (adapter selon le format)
            log_message = entry.get('message', '') or entry.get('_source', {}).get('message', '')
            
            if log_message and self.process_log_line(log_message):
                stats['processed_entries'] += 1
            else:
                stats['failed_entries'] += 1
        
        logger.info(f"Traitement JSON terminé: {stats}")
        return stats
    
    def get_flux_details(self, reference: str) -> Optional[Dict]:
        """Récupère les détails complets d'un flux
        Si la référence est un sous-flux, retourne les détails du flux parent avec indication du sous-flux
        """
        session = self.SessionLocal()
        try:
            flux = session.query(FluxInstance).filter_by(reference=reference).first()
            if not flux:
                return None
            
            # Vérifier si c'est un sous-flux
            is_subflow = flux.parent_id is not None
            target_flux = flux
            
            if is_subflow:
                # Si c'est un sous-flux, récupérer le flux parent
                target_flux = session.query(FluxInstance).filter_by(id=flux.parent_id).first()
                if not target_flux:
                    # Fallback si le parent n'existe pas
                    target_flux = flux
                    is_subflow = False
            
            # Récupérer les logs du flux cible (parent si sous-flux, sinon le flux lui-même)
            logs = session.query(LogEntry).filter_by(flux_instance_id=target_flux.id).order_by(LogEntry.timestamp).all()
            
            # Récupérer les références croisées
            cross_refs = session.query(CrossReference).filter_by(source_flux_id=target_flux.id).all()
            
            # Récupérer les enfants
            children = session.query(FluxInstance).filter_by(parent_id=target_flux.id).all()
            
            result = {
                'flux': {
                    'id': target_flux.id,
                    'reference': target_flux.reference,
                    'status': target_flux.status,
                    'flux_type': target_flux.flux_type.name,
                    'created_at': target_flux.created_at.isoformat(),
                    'updated_at': target_flux.updated_at.isoformat()
                },
                'logs': [
                    {
                        'timestamp': log.timestamp.isoformat(),
                        'application': log.application.name,
                        'log_type': log.log_type,
                        'raw_log': log.raw_log,
                        'parsed_data': json.loads(log.parsed_data) if log.parsed_data else {}
                    }
                    for log in logs
                ],
                'cross_references': [
                    {
                        'target_reference': ref.target_flux.reference,
                        'reference_field': ref.reference_field,
                        'reference_value': ref.reference_value
                    }
                    for ref in cross_refs
                ],
                'children': [
                    {
                        'reference': child.reference,
                        'status': child.status
                    }
                    for child in children
                ]
            }
            
            # Ajouter des informations sur le sous-flux si applicable
            if is_subflow:
                result['subflow_info'] = {
                    'is_subflow': True,
                    'requested_reference': reference,
                    'subflow_details': {
                        'id': flux.id,
                        'reference': flux.reference,
                        'status': flux.status,
                        'created_at': flux.created_at.isoformat(),
                        'updated_at': flux.updated_at.isoformat()
                    },
                    'parent_reference': target_flux.reference
                }
                
                # Récupérer les logs spécifiques au sous-flux
                subflow_logs = session.query(LogEntry).filter_by(flux_instance_id=flux.id).order_by(LogEntry.timestamp).all()
                result['subflow_info']['subflow_logs'] = [
                    {
                        'timestamp': log.timestamp.isoformat(),
                        'application': log.application.name,
                        'log_type': log.log_type,
                        'raw_log': log.raw_log,
                        'parsed_data': json.loads(log.parsed_data) if log.parsed_data else {}
                    }
                    for log in subflow_logs
                ]
            else:
                result['subflow_info'] = {
                    'is_subflow': False,
                    'requested_reference': reference
                }
            
            return result
        finally:
            session.close()
    
    def get_incomplete_flows(self, max_age_hours: int = None) -> Dict[str, List[Dict]]:
        """Analyse les flux incomplets (qui n'ont pas fait le parcours complet)
        
        Args:
            max_age_hours: Limite d'âge en heures pour considérer un flux (optionnel)
            
        Returns:
            Dictionnaire avec les flux incomplets par type
        """
        session = self.SessionLocal()
        try:
            incomplete_flows = {}
            
            # Pour chaque type de flux défini dans la configuration
            for flux_type_name, flux_config in self.config['flux_types'].items():
                # Récupérer les étapes requises depuis la configuration
                required_steps = flux_config.get('required_steps', [])
                optional_steps = flux_config.get('optional_steps', [])
                
                # Si aucune étape requise n'est définie, ignorer ce flux
                if not required_steps:
                    continue                
                flux_type = session.query(FluxType).filter_by(name=flux_type_name).first()
                if not flux_type:
                    continue
                
                # Récupérer tous les flux de ce type
                query = session.query(FluxInstance).filter_by(flux_type_id=flux_type.id)
                
                # Filtrer par âge si spécifié
                if max_age_hours:
                    cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
                    query = query.filter(FluxInstance.created_at >= cutoff_time)
                
                # Exclure les sous-flux (on analyse seulement les flux principaux)
                query = query.filter(FluxInstance.parent_id.is_(None))
                
                flux_instances = query.all()
                
                incomplete_list = []
                
                for flux_instance in flux_instances:
                    # Récupérer tous les types de logs pour ce flux
                    logs = session.query(LogEntry).filter_by(flux_instance_id=flux_instance.id).all()
                    log_types_present = set(log.log_type for log in logs)
                    
                    # Vérifier quelles étapes requises manquent
                    missing_required_stages = []
                    for required_stage in required_steps:
                        if required_stage not in log_types_present:
                            missing_required_stages.append(required_stage)
                    
                    # Un flux est incomplet si des étapes requises manquent
                    if missing_required_stages:
                        # Calculer l'âge du flux
                        age_hours = (datetime.utcnow() - flux_instance.created_at).total_seconds() / 3600
                        
                        # Récupérer le dernier log pour avoir une idée de l'état
                        last_log = session.query(LogEntry).filter_by(
                            flux_instance_id=flux_instance.id
                        ).order_by(LogEntry.timestamp.desc()).first()
                        
                        # Compter les enfants si applicable
                        children_count = session.query(FluxInstance).filter_by(
                            parent_id=flux_instance.id
                        ).count()
                        
                        # Calcul du taux de complétion basé sur les étapes requises uniquement
                        total_required = len(required_steps)
                        completed_required = total_required - len(missing_required_stages)
                        completion_rate = round((completed_required / total_required) * 100, 1) if total_required > 0 else 100
                        
                        # Identifier toutes les étapes manquantes (requises + optionnelles présentes dans d'autres flux)
                        all_possible_stages = required_steps + optional_steps
                        missing_stages = [stage for stage in all_possible_stages if stage not in log_types_present]
                        
                        incomplete_info = {
                            'reference': flux_instance.reference,
                            'status': flux_instance.status,
                            'created_at': flux_instance.created_at.isoformat(),
                            'updated_at': flux_instance.updated_at.isoformat(),
                            'age_hours': round(age_hours, 2),
                            'missing_stages': missing_stages,
                            'missing_required_stages': missing_required_stages,
                            'present_stages': list(log_types_present),
                            'required_stages': required_steps,
                            'optional_stages': optional_steps,
                            'last_activity': last_log.timestamp.isoformat() if last_log else None,
                            'last_log_type': last_log.log_type if last_log else None,
                            'children_count': children_count,
                            'completion_rate': completion_rate
                        }
                        
                        incomplete_list.append(incomplete_info)
                
                # Trier par âge (plus anciens en premier)
                incomplete_list.sort(key=lambda x: x['age_hours'], reverse=True)
                
                if incomplete_list:
                    incomplete_flows[flux_type_name] = incomplete_list
            
            return incomplete_flows
            
        finally:
            session.close()

    # ...existing code...
def main():
    """Fonction principale pour démonstration"""
    tracker = LogFlowTracker()
    
    # Exemple d'utilisation
    print("=== Système de suivi de flux multi-applicatifs ===")
    
    # Traiter un fichier de logs
    try:
        if Path("exemples_logs/traitement_commande.log").exists():
            print("\nTraitement du fichier d'exemple...")
            stats = tracker.process_log_file("exemples_logs/traitement_commande.log")
            print(f"Résultats: {stats}")
        
        # Exemple de traitement ligne par ligne
        print("\nTest de traitement ligne par ligne...")
        test_logs = [
            "[2024-01-15 10:30:00] COMMANDE_RECU CMD_001 client=CLI_123 articles=[ART_001, ART_002, ART_003]",
            "[2024-01-15 10:30:05] VALIDATION_COMMANDE CMD_001 → ordre=ORD_001 status=VALIDE"
        ]
        
        for log_line in test_logs:
            success = tracker.process_log_line(log_line)
            print(f"Log traité: {success} - {log_line[:50]}...")
        
        # Afficher les détails d'un flux
        print("\nDétails du flux CMD_001:")
        details = tracker.get_flux_details("CMD_001")
        if details:
            print(json.dumps(details, indent=2, ensure_ascii=False))
        
        # Analyser les flux incomplets
        print("\nAnalyse des flux incomplets:")
        incomplete_flows = tracker.get_incomplete_flows(max_age_hours=24)
        for flux_type, instances in incomplete_flows.items():
            print(f"Flux incomplets pour {flux_type}:")
            for instance in instances:
                print(f"- {instance['reference']} (Âge: {instance['age_hours']}h)")
    
    except Exception as e:
        logger.error(f"Erreur dans main: {e}")

if __name__ == "__main__":
    main()