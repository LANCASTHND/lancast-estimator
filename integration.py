"""
integration.py — Conecta Agent 1 (Monitor) con Agent 2 (Estimador)
Cuando Agent 1 detecta una licitación relevante, Agent 2 genera el estimado
automáticamente y lo incluye en el mismo email de alerta.
"""

import os
import json
import urllib.request
import urllib.error
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv(override=True)

# Import estimator
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from estimator import estimate, format_email_html, format_text

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
GMAIL_ADDRESS    = os.environ.get("GMAIL_ADDRESS")
ALERT_EMAIL      = os.environ.get("ALERT_EMAIL", "gerencia@lancast.biz")


def build_boq_from_tender(tender_data: Dict) -> tuple:
    """
    Build a best-effort BOQ from OCDS tender data.
    Returns (boq_text, project_info)
    """
    tender = tender_data.get('tender', {})
    buyer  = tender_data.get('buyer', {})

    title       = tender.get('title', 'Sin título')
    description = tender.get('description', '')
    items       = tender.get('items', [])
    value       = tender.get('value', {})
    budget_str  = f"L {value.get('amount', 'No especificado'):,}" if value.get('amount') else 'No especificado'

    project_info = {
        'titulo':      title,
        'institucion': buyer.get('name', 'No especificada'),
        'ubicacion':   'Honduras',
        'datos_tecnicos': description[:500] if description else 'No disponible',
    }

    # Build BOQ text from OCDS items
    if items:
        boq_lines = [f"CUADRO DE CANTIDADES — {title}"]
        boq_lines.append(f"Institución: {buyer.get('name', '')}")
        boq_lines.append(f"Presupuesto referencial: {budget_str}")
        boq_lines.append("")
        for i, item in enumerate(items[:20], 1):
            desc  = item.get('description', f'Ítem {i}')
            unit  = item.get('unit', {}).get('name', 'GLB')
            qty   = item.get('quantity', 1)
            boq_lines.append(f"{i}. {desc} | {unit} | {qty}")
        boq_text = '\n'.join(boq_lines)
    else:
        # No items — use description only
        boq_text = f"""
DESCRIPCIÓN DEL PROYECTO: {title}
INSTITUCIÓN: {buyer.get('name', '')}
PRESUPUESTO REFERENCIAL: {budget_str}
ALCANCE: {description[:1000] if description else 'Ver pliego oficial'}
CATEGORÍA: {tender.get('mainProcurementCategory', 'No especificada')}
MÉTODO: {tender.get('procurementMethodDetails', '')}
"""

    return boq_text, project_info


def send_combined_alert(tenders_with_estimates: List[Dict]) -> bool:
    """
    Send a single email with tender alerts + estimates combined.
    """
    if not tenders_with_estimates:
        return False

    subject = _build_subject(tenders_with_estimates)
    html    = _build_combined_html(tenders_with_estimates)
    text    = _build_combined_text(tenders_with_estimates)

    return _send_via_sendgrid(subject, html, text)


def _build_subject(items: List[Dict]) -> str:
    from datetime import datetime
    today = datetime.now().strftime('%d/%m/%Y')
    count = len(items)
    total_offer = sum(
        i.get('estimate', {}).get('resumen', {}).get('precio_oferta', 0)
        for i in items
        if i.get('estimate')
    )
    try:
        total_str = f" | ~L {total_offer:,.0f} estimado"
    except:
        total_str = ""
    return f"🏗️ LANCAST — {count} Licitación{'es' if count > 1 else ''} + Estimado ({today}){total_str}"


def _build_combined_html(items: List[Dict]) -> str:
    from datetime import datetime
    today = datetime.now().strftime('%d/%m/%Y')

    sections = ''
    for item in items:
        tender    = item.get('tender', {})
        estimate_data = item.get('estimate')

        conf     = tender.get('confidence', 'Media')
        conf_col = {'Alta':'#22c55e','Media':'#f59e0b','Baja':'#ef4444'}.get(conf,'#f59e0b')
        url      = tender.get('tender_url','')
        link     = f'<a href="{url}" style="color:#1a5c2a;">Ver pliego →</a>' if url else ''

        # Tender card
        sections += f"""
<div style="border:1px solid #e0e0e0;border-radius:8px;margin-bottom:24px;overflow:hidden;">
  <div style="background:#1a5c2a;padding:12px 16px;">
    <h3 style="color:white;margin:0;font-size:14px;">{tender.get('title','')}</h3>
    <span style="background:{conf_col};color:white;padding:2px 8px;border-radius:10px;font-size:11px;">{conf}</span>
  </div>
  <div style="padding:12px 16px;background:#fafafa;">
    <table style="width:100%;font-size:12px;color:#555;">
      <tr><td style="width:120px;padding:3px 0;"><b>Institución</b></td><td>{tender.get('institution','')}</td></tr>
      <tr><td style="padding:3px 0;"><b>Presupuesto</b></td><td>{tender.get('budget','N/A')}</td></tr>
      <tr><td style="padding:3px 0;"><b>Fecha límite</b></td><td>{tender.get('deadline','N/A')}</td></tr>
      <tr><td style="padding:3px 0;"><b>Categoría</b></td><td>{tender.get('category','N/A')}</td></tr>
    </table>
    <p style="font-size:12px;margin:8px 0;">{tender.get('summary','')}</p>
    {link}
  </div>"""

        # Estimate section
        if estimate_data:
            res       = estimate_data.get('resumen', {})
            est_conf  = estimate_data.get('confianza','Media')
            est_col   = {'Alta':'#22c55e','Media':'#f59e0b','Baja':'#ef4444'}.get(est_conf,'#f59e0b')
            tipo      = estimate_data.get('tipo_contrato','Obra')

            def lps(n):
                try: return f"L {float(n):,.2f}"
                except: return "N/A"

            items_rows = ''
            for it in estimate_data.get('items', []):
                bg = '#f9fbe7' if it.get('estado')=='Encontrado' else '#fff8e1'
                items_rows += f"<tr style='background:{bg};'><td style='padding:4px 6px;border:1px solid #eee;font-size:11px;'>{it.get('descripcion','')}</td><td style='padding:4px 6px;border:1px solid #eee;font-size:11px;text-align:center;'>{it.get('unidad','')}</td><td style='padding:4px 6px;border:1px solid #eee;font-size:11px;text-align:right;'>{it.get('cantidad',0):,.1f}</td><td style='padding:4px 6px;border:1px solid #eee;font-size:11px;text-align:right;'>{lps(it.get('precio_unitario',0))}</td><td style='padding:4px 6px;border:1px solid #eee;font-size:11px;text-align:right;font-weight:bold;'>{lps(it.get('total',0))}</td></tr>"

            sections += f"""
  <div style="padding:12px 16px;border-top:2px solid #8dc641;background:#f0fff4;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <strong style="color:#1a5c2a;font-size:13px;">📊 Estimado LANCAST — {tipo}</strong>
      <span style="background:{est_col};color:white;padding:2px 8px;border-radius:10px;font-size:11px;">Confianza {est_conf}</span>
    </div>
    <table style="width:100%;border-collapse:collapse;margin-bottom:8px;">
      <thead><tr style="background:#1a5c2a;color:white;">
        <th style="padding:5px 6px;font-size:11px;text-align:left;">Descripción</th>
        <th style="padding:5px 6px;font-size:11px;">Und</th>
        <th style="padding:5px 6px;font-size:11px;text-align:right;">Cant.</th>
        <th style="padding:5px 6px;font-size:11px;text-align:right;">P.U.</th>
        <th style="padding:5px 6px;font-size:11px;text-align:right;">Total</th>
      </tr></thead>
      <tbody>{items_rows}</tbody>
    </table>
    <table style="width:100%;border-collapse:collapse;">
      <tr style="background:#e8f5e9;"><td style="padding:6px 8px;font-size:12px;border:1px solid #ddd;">Costo Directo</td><td style="padding:6px 8px;font-size:12px;border:1px solid #ddd;text-align:right;">{lps(res.get('costo_directo',0))}</td></tr>
      <tr style="background:#1a5c2a;color:white;"><td style="padding:8px;font-size:13px;font-weight:bold;">OFERTA ESTIMADA</td><td style="padding:8px;font-size:13px;font-weight:bold;text-align:right;">{lps(res.get('precio_oferta',0))}</td></tr>
    </table>
    {"<p style='margin:8px 0 0 0;font-size:11px;color:#d97706;'>⚠️ " + " | ".join(estimate_data.get('alertas',[])) + "</p>" if estimate_data.get('alertas') else ""}
  </div>"""

        sections += "</div>"

    return f"""<html><body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;color:#333;">
<div style="background:#1a5c2a;padding:20px;border-radius:8px 8px 0 0;">
  <h2 style="color:white;margin:0;">🏗️ LANCAST — Monitor + Estimador</h2>
  <p style="color:#a7d7b0;margin:4px 0 0 0;font-size:13px;">{today} | {len(items)} licitación(es) con estimado</p>
</div>
<div style="padding:20px;background:#fafafa;border:1px solid #e0e0e0;border-radius:0 0 8px 8px;">
  {sections}
  <p style="color:#999;font-size:11px;border-top:1px solid #eee;padding-top:10px;margin:0;">
    LANCAST Agent 1 + Agent 2 | Powered by Claude AI | Fuente: HonduCompras ONCAE
  </p>
</div></body></html>"""


def _build_combined_text(items: List[Dict]) -> str:
    lines = ["LANCAST — MONITOR + ESTIMADOR", "="*50, ""]
    for i, item in enumerate(items, 1):
        t = item.get('tender', {})
        e = item.get('estimate', {})
        lines += [
            f"{i}. {t.get('title','')}",
            f"   Institución: {t.get('institution','')}",
            f"   Fecha límite: {t.get('deadline','')}",
        ]
        if e:
            res = e.get('resumen', {})
            try:
                lines.append(f"   ESTIMADO: L {float(res.get('precio_oferta',0)):,.2f} (Confianza {e.get('confianza','')})")
            except:
                pass
        lines.append("")
    return '\n'.join(lines)


def _send_via_sendgrid(subject, html, text) -> bool:
    if not SENDGRID_API_KEY:
        print("[integration] No SendGrid key — printing only")
        print(text)
        return True

    payload = json.dumps({
        "personalizations": [{"to": [{"email": ALERT_EMAIL}]}],
        "from": {"email": GMAIL_ADDRESS, "name": "LANCAST Monitor"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text},
            {"type": "text/html",  "value": html}
        ]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=payload,
        headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"[integration] ✅ Email enviado a {ALERT_EMAIL} — HTTP {resp.status}")
            return True
    except urllib.error.HTTPError as e:
        print(f"[integration] ❌ Error {e.code}: {e.read().decode()}")
        return False
