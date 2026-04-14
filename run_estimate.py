import os, sys, json, argparse
from dotenv import load_dotenv
from estimator import estimate, format_email_html, format_text
load_dotenv(override=True)
CHOLOMA_BOQ = """
OBJETO: Suministro de Concreto Hidráulico 4000 PSI — 4 Lotes
INSTITUCION: Municipalidad de Choloma
TIPO: Suministro unicamente — mano de obra municipal
Lote 1 Pavimentacion 3ra Calle Col. Victoria | M3 | 356
Lote 2 Carretera Principal Sector Bajos | M3 | 866
Lote 3 Bajadas Las Pilas Col. Chaparro | M3 | 896
Lote 4 Col. La Garcia 3ra Etapa | M3 | 197
TOTAL: 2315 M3
"""
CHOLOMA_INFO = {'titulo': 'LPuNBS-MCH-001-2026 Suministro Concreto Hidraulico', 'institucion': 'Municipalidad de Choloma', 'ubicacion': 'Choloma, Cortes'}
parser = argparse.ArgumentParser()
parser.add_argument('--mode', default='test')
parser.add_argument('--no-email', action='store_true')
args = parser.parse_args()
print("\n" + "="*60)
print("[Agent 2] LANCAST Estimador de Presupuesto")
print("="*60)
est = estimate(CHOLOMA_BOQ, CHOLOMA_INFO)
print(format_text(est))
with open('estimado_choloma.json', 'w') as f:
    json.dump(est, f, ensure_ascii=False, indent=2)
print("\n[Agent 2] JSON guardado: estimado_choloma.json")
print("[Agent 2] Completado.")
