"""
estimator.py — LANCAST Agent 2: Estimador de Presupuesto v2
Detecta automáticamente si el contrato es SUMINISTRO u OBRA
y aplica la estructura de precio correcta.
"""

import os, csv, json
import anthropic
from typing import Dict, List
from dotenv import load_dotenv
from datetime import datetime

load_dotenv(override=True)

# ── Factores por tipo de contrato ─────────────────────────────────────────────
FACTORES_OBRA = {
    'indirectos': 0.10,
    'utilidad':   0.12,
    'imprev':     0.01,
}
# Suministro: precio unitario ya incluye margen — solo validamos

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRICES_CSV = os.path.join(SCRIPT_DIR, 'precios_unitarios.csv')

def load_price_db():
    items = []
    with open(PRICES_CSV, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            row['precio_cd'] = float(row['precio_cd']) if row['precio_cd'] else None
            row['precio_pu'] = float(row['precio_pu']) if row['precio_pu'] else None
            items.append(row)
    return items

PRICE_DB = load_price_db()

def get_best_price(item):
    return item['precio_cd'] or item['precio_pu'] or 0.0

def format_price_db_for_claude():
    lines = ["TABLA PRECIOS UNITARIOS LANCAST (Lempiras, incluye CD):"]
    cat = ''
    for item in PRICE_DB:
        if item['categoria'] != cat:
            cat = item['categoria']
            lines.append(f"\n{cat.upper()}:")
        p = get_best_price(item)
        lines.append(f"  [{item['codigo']}] {item['descripcion']} | {item['unidad']} | L {p:,.2f}")
    return '\n'.join(lines)

CHICO_REFERENCE = """
PRECIOS MERCADO CHICO IV-2025 (Dic 2025, incluyen ISV 15%):
MANO DE OBRA TGC: Trazo L35.40/m | Remoción capa L157.50/m3 | Excavación manual L135/m3
EQUIPO TGC: Excavadora 20T L2,053/hr | Volqueta 12m3 L1,684/hr | Vibrocompactador L1,700/hr
COSTO REFERENCIAL M²: Social L13,500-15,000 | Media L16,000-19,000 | Alta L20,000-25,000
"""

SYSTEM_PROMPT = f"""Eres el agente estimador de LANCAST (Constructora Lanza Castillo S. de R.L.).

{format_price_db_for_claude()}

{CHICO_REFERENCE}

REGLAS CRÍTICAS:
1. Detecta si el contrato es SUMINISTRO (solo materiales) u OBRA (construcción completa)
2. SUMINISTRO: precio unitario directo sin factores adicionales. El margen ya está en el PU.
3. OBRA: CD = Σ(cant×PU) → + Indirectos 10% + Utilidad 12% + Imprevistos 1%
4. Busca cada ítem en la tabla LANCAST. Si no hay exacto, usa el más similar.
5. Marca ítems como: Encontrado / Aproximado / Sin precio
6. Si precio difiere >20% del CHICO, genera alerta.
7. Responde SOLO con JSON válido, sin texto adicional.

FORMATO JSON:
{{
  "tipo_contrato": "Suministro|Obra|Mixto",
  "titulo_proyecto": "string",
  "institucion": "string",
  "fecha_estimado": "string",
  "confianza": "Alta|Media|Baja",
  "motivo_confianza": "string",
  "items": [{{
    "descripcion": "string", "unidad": "string", "cantidad": number,
    "precio_unitario": number, "codigo_lancast": "string",
    "total": number, "estado": "Encontrado|Aproximado|Sin precio"
  }}],
  "resumen": {{
    "costo_directo": number, "indirectos": number, "utilidad": number,
    "imprevistos": number, "precio_oferta": number,
    "precio_unitario_promedio": number,
    "items_sin_precio": number, "items_aproximados": number
  }},
  "alertas": ["string"],
  "recomendaciones": ["string"]
}}"""


def estimate(boq_text: str, project_info: Dict) -> Dict:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    
    user_msg = f"""PROYECTO: {project_info.get('titulo', 'Sin título')}
INSTITUCIÓN: {project_info.get('institucion', 'No especificada')}
UBICACIÓN: {project_info.get('ubicacion', 'No especificada')}
DATOS TÉCNICOS: {project_info.get('datos_tecnicos', 'No disponibles')}

CUADRO DE CANTIDADES:
{boq_text}

Genera estimado preliminar."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}]
    )
    raw = response.content[0].text.strip().replace('```json','').replace('```','').strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[estimator] JSON parse error: {e}")
        print(f"[estimator] Raw response (first 300 chars): {raw[:300]}")
        # Return a safe fallback structure
        return {
            "tipo_contrato": "Obra",
            "titulo_proyecto": project_info.get('titulo', 'Error'),
            "institucion": project_info.get('institucion', ''),
            "fecha_estimado": "",
            "confianza": "Baja",
            "motivo_confianza": f"Error de parsing JSON: {str(e)[:100]}",
            "items": [],
            "resumen": {"costo_directo": 0, "indirectos": 0, "utilidad": 0,
                        "imprevistos": 0, "precio_oferta": 0,
                        "precio_unitario_promedio": 0, "items_sin_precio": 0, "items_aproximados": 0},
            "alertas": [f"ERROR: No se pudo parsear respuesta de Claude. {str(e)}"],
            "recomendaciones": ["Revisar manualmente el cuadro de cantidades"]
        }


def format_email_html(est: Dict) -> str:
    conf = est.get('confianza','Media')
    conf_color = {'Alta':'#22c55e','Media':'#f59e0b','Baja':'#ef4444'}.get(conf,'#f59e0b')
    conf_emoji = {'Alta':'🟢','Media':'🟡','Baja':'🔴'}.get(conf,'🟡')
    res = est.get('resumen',{})
    items = est.get('items',[])
    tipo = est.get('tipo_contrato','Obra')

    def lps(n):
        try: return f"L {float(n):,.2f}"
        except: return "N/A"

    rows = ''
    for it in items:
        bg = '#fff' if it.get('estado')=='Encontrado' else ('#fffde7' if it.get('estado')=='Aproximado' else '#ffebee')
        rows += f"<tr style='background:{bg};'><td style='padding:5px 8px;border:1px solid #ddd;font-size:12px;'>{it.get('descripcion','')}</td><td style='padding:5px 8px;border:1px solid #ddd;font-size:12px;text-align:center;'>{it.get('unidad','')}</td><td style='padding:5px 8px;border:1px solid #ddd;font-size:12px;text-align:right;'>{it.get('cantidad',0):,.2f}</td><td style='padding:5px 8px;border:1px solid #ddd;font-size:12px;text-align:right;'>{lps(it.get('precio_unitario',0))}</td><td style='padding:5px 8px;border:1px solid #ddd;font-size:12px;text-align:right;font-weight:bold;'>{lps(it.get('total',0))}</td><td style='padding:5px 8px;border:1px solid #ddd;font-size:12px;text-align:center;'>{it.get('estado','')}</td></tr>"

    alertas_html = ''.join([f'<li style="color:#d97706;font-size:13px;">{a}</li>' for a in est.get('alertas',[])])
    recs_html = ''.join([f'<li style="font-size:13px;">{r}</li>' for r in est.get('recomendaciones',[])])

    # Resumen rows
    fin_rows = f"""
    <tr style='background:#f5f5f5;'><td style='padding:8px;border:1px solid #ddd;'>Costo Directo</td><td style='padding:8px;border:1px solid #ddd;text-align:right;font-weight:bold;'>{lps(res.get('costo_directo',0))}</td></tr>"""
    if tipo != 'Suministro':
        fin_rows += f"""
    <tr><td style='padding:8px;border:1px solid #ddd;'>Indirectos (10%)</td><td style='padding:8px;border:1px solid #ddd;text-align:right;'>{lps(res.get('indirectos',0))}</td></tr>
    <tr style='background:#f5f5f5;'><td style='padding:8px;border:1px solid #ddd;'>Utilidad (12%)</td><td style='padding:8px;border:1px solid #ddd;text-align:right;'>{lps(res.get('utilidad',0))}</td></tr>
    <tr><td style='padding:8px;border:1px solid #ddd;'>Imprevistos (1%)</td><td style='padding:8px;border:1px solid #ddd;text-align:right;'>{lps(res.get('imprevistos',0))}</td></tr>"""

    return f"""<html><body style="font-family:Arial,sans-serif;max-width:800px;margin:0 auto;color:#333;">
<div style="background:#1a5c2a;padding:20px;border-radius:8px 8px 0 0;">
  <h2 style="color:white;margin:0;">🏗️ LANCAST — Estimado Preliminar</h2>
  <p style="color:#a7d7b0;margin:4px 0 0 0;font-size:12px;">{datetime.now().strftime('%d/%m/%Y %H:%M')} | Tipo: {tipo}</p>
</div>
<div style="padding:20px;background:#fafafa;border:1px solid #e0e0e0;border-radius:0 0 8px 8px;">
  <table style="width:100%;margin-bottom:16px;"><tr>
    <td><h3 style="margin:0 0 4px 0;">{est.get('titulo_proyecto','')}</h3>
    <p style="margin:0;color:#666;font-size:13px;">{est.get('institucion','')}</p></td>
    <td style="text-align:right;vertical-align:top;">
      <span style="background:{conf_color};color:white;padding:4px 12px;border-radius:20px;font-size:13px;font-weight:bold;">{conf_emoji} Confianza {conf}</span>
      <p style="margin:4px 0 0 0;font-size:11px;color:#999;">{est.get('motivo_confianza','')}</p>
    </td>
  </tr></table>

  <h4 style="color:#1a5c2a;border-bottom:2px solid #8dc641;padding-bottom:4px;">📋 Cuadro de Cantidades</h4>
  <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
    <thead><tr style="background:#1a5c2a;color:white;">
      <th style="padding:8px;font-size:12px;text-align:left;">Descripción</th>
      <th style="padding:8px;font-size:12px;">Und</th>
      <th style="padding:8px;font-size:12px;text-align:right;">Cantidad</th>
      <th style="padding:8px;font-size:12px;text-align:right;">P.U. (L.)</th>
      <th style="padding:8px;font-size:12px;text-align:right;">Total (L.)</th>
      <th style="padding:8px;font-size:12px;">Estado</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>

  <h4 style="color:#1a5c2a;border-bottom:2px solid #8dc641;padding-bottom:4px;">💰 Resumen Financiero</h4>
  <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
    {fin_rows}
    <tr style="background:#1a5c2a;color:white;"><td style="padding:10px;font-weight:bold;font-size:15px;">PRECIO DE OFERTA ESTIMADO</td>
    <td style="padding:10px;text-align:right;font-weight:bold;font-size:15px;">{lps(res.get('precio_oferta',0))}</td></tr>
  </table>

  <div style="background:#e8f5e9;padding:10px 14px;border-radius:6px;margin-bottom:12px;">
    <strong>P.U. Promedio:</strong> {lps(res.get('precio_unitario_promedio',0))} &nbsp;|&nbsp;
    <strong>Ítems sin precio:</strong> {res.get('items_sin_precio',0)} &nbsp;|&nbsp;
    <strong>Aproximados:</strong> {res.get('items_aproximados',0)}
  </div>

  {"<div style='background:#fff8e1;padding:12px;border-radius:6px;border-left:4px solid #f59e0b;margin-bottom:12px;'><strong style='color:#c9a84c;'>⚠️ Alertas</strong><ul style='margin:6px 0 0 0;padding-left:18px;'>" + alertas_html + "</ul></div>" if alertas_html else ""}
  {"<div style='background:#f0f4f8;padding:12px;border-radius:6px;margin-bottom:12px;'><strong style='color:#1a5c2a;'>📌 Recomendaciones</strong><ul style='margin:6px 0 0 0;padding-left:18px;'>" + recs_html + "</ul></div>" if recs_html else ""}

  <p style="color:#999;font-size:11px;border-top:1px solid #eee;padding-top:10px;margin:0;">
    LANCAST Agent 2 Estimador | Powered by Claude AI<br>
    Estimado preliminar — verificar con pliego oficial antes de presentar oferta.
  </p>
</div></body></html>"""


def format_text(est: Dict) -> str:
    res = est.get('resumen',{})
    def lps(n):
        try: return f"L {float(n):,.2f}"
        except: return "N/A"
    lines = [
        f"LANCAST — ESTIMADO PRELIMINAR ({est.get('tipo_contrato','Obra')})",
        "="*50,
        f"Proyecto: {est.get('titulo_proyecto','')}",
        f"Institución: {est.get('institucion','')}",
        f"Confianza: {est.get('confianza','')} — {est.get('motivo_confianza','')}",
        "",
        f"RESUMEN:",
        f"  Costo Directo:    {lps(res.get('costo_directo',0))}",
    ]
    if est.get('tipo_contrato') != 'Suministro':
        lines += [
            f"  Indirectos 10%:   {lps(res.get('indirectos',0))}",
            f"  Utilidad 12%:     {lps(res.get('utilidad',0))}",
            f"  Imprevistos 1%:   {lps(res.get('imprevistos',0))}",
        ]
    lines += [
        f"  OFERTA ESTIMADA:  {lps(res.get('precio_oferta',0))}",
        f"  P.U. Promedio:    {lps(res.get('precio_unitario_promedio',0))}",
        f"  Sin precio: {res.get('items_sin_precio',0)} | Aproximados: {res.get('items_aproximados',0)}",
    ]
    if est.get('alertas'):
        lines += ["", "ALERTAS:"] + [f"  ⚠️  {a}" for a in est['alertas']]
    if est.get('recomendaciones'):
        lines += ["", "RECOMENDACIONES:"] + [f"  • {r}" for r in est['recomendaciones']]
    return '\n'.join(lines)
