"""
run_estimate.py — LANCAST Agent 2 Runner
Corre el estimador para un proceso específico y envía resultado por email.

Uso:
  python run_estimate.py --mode boq --input "cuadro_cantidades.txt"
  python run_estimate.py --mode description --title "Pavimentación Choloma" --desc "..."
  python run_estimate.py --mode test   # Corre el caso de prueba Choloma
"""

import os
import sys
import json
import argparse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from estimator import (
    estimate_from_boq,
    estimate_from_description,
    format_estimate_email,
    format_estimate_text
)

load_dotenv(override=True)

# ── Email sender ──────────────────────────────────────────────────────────────
def send_estimate_email(estimate: dict, subject: str) -> bool:
    """Send estimate via SendGrid or Gmail."""
    sendgrid_key = os.environ.get("SENDGRID_API_KEY")
    gmail_addr = os.environ.get("GMAIL_ADDRESS")
    alert_email = os.environ.get("ALERT_EMAIL", "gerencia@lancast.biz")

    html_body = format_estimate_email(estimate)
    text_body = format_estimate_text(estimate)

    if sendgrid_key:
        return _send_sendgrid(sendgrid_key, gmail_addr, alert_email, subject, html_body, text_body)
    else:
        print("[email] No SendGrid key — printing to console only")
        print(text_body)
        return True


def _send_sendgrid(api_key, from_email, to_email, subject, html, text):
    import json
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email, "name": "LANCAST Estimador"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text},
            {"type": "text/html", "value": html}
        ]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            print(f"[email] ✅ Enviado a {to_email} — HTTP {resp.status}")
            return True
    except urllib.error.HTTPError as e:
        print(f"[email] ❌ Error {e.code}: {e.read().decode()}")
        return False


# ── Test case: Choloma LPN (known project) ───────────────────────────────────
CHOLOMA_TEST = """
CUADRO DE CANTIDADES — LPN Choloma LPuNBS-MCH-001-2026
Municipalidad de Choloma — Pavimentación Carretera Principal a Sector Bajos

LOTE 1 — CARRETERA PRINCIPAL SECTOR BAJOS (0+000 a 0+266.19):
  Sección típica: Calzada 7.70m, e=0.175m concreto hidráulico, e=0.15m sub-base

  1. Replanteo y trazado de calle | ML | 266.19
  2. Sub-base granular e=0.15m | M3 | 308.07
  3. Concreto hidráulico f'c=280kg/cm² (4000PSI) e=0.175m | M3 | 358.84
  4. Bordillo de concreto 0.15x0.15m | ML | 532.38
  5. Juntas de pavimento cortadas | ML | 800.00
  6. Limpieza general | M2 | 2050.00

LOTE 2 — COL. LA GARCIA SECTOR NORTE (0+000 a 0+170):
  Sección típica: Calzada 7.20m, e=0.15m concreto hidráulico, e=0.15m sub-base

  1. Replanteo y trazado de calle | ML | 170.00
  2. Sub-base granular e=0.15m | M3 | 183.60
  3. Concreto hidráulico f'c=280kg/cm² (4000PSI) e=0.15m | M3 | 183.60
  4. Bordillo de concreto 0.15x0.15m | ML | 340.00
  5. Juntas de pavimento cortadas | ML | 510.00
  6. Limpieza general | M2 | 1224.00

LOTE 3 — BAJADA LAS PILAS COL. CHAPARRO (0+000 a 0+800 aprox.):
  Sección típica: Calzada 7.20m, e=0.15m concreto hidráulico

  1. Replanteo y trazado de calle | ML | 800.00
  2. Sub-base granular e=0.15m | M3 | 864.00
  3. Concreto hidráulico f'c=280kg/cm² (4000PSI) e=0.15m | M3 | 864.00
  4. Bordillo de concreto 0.15x0.15m | ML | 1600.00
  5. Juntas de pavimento cortadas | ML | 2400.00

LOTE 4 — CALLE ADICIONAL SECTOR BAJOS:
  1. Concreto hidráulico f'c=280kg/cm² (4000PSI) | M3 | 908.00
  2. Sub-base granular | M3 | 500.00
  3. Bordillo de concreto | ML | 800.00
"""

CHOLOMA_PROJECT = {
    'titulo': 'Pavimentación Carretera Principal a Sector Bajos — Choloma',
    'institucion': 'Municipalidad de Choloma',
    'ubicacion': 'Choloma, Cortés',
    'datos_tecnicos': 'Sección típica: calzada 7.70m, e=0.175m concreto hidráulico f\'c=280kg/cm², sub-base 0.15m'
}


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='LANCAST Agent 2 — Estimador')
    parser.add_argument('--mode', choices=['boq', 'description', 'test'], default='test')
    parser.add_argument('--input', help='Archivo con cuadro de cantidades (modo boq)')
    parser.add_argument('--title', help='Título del proyecto (modo description)')
    parser.add_argument('--desc', help='Descripción del alcance (modo description)')
    parser.add_argument('--institution', help='Institución contratante')
    parser.add_argument('--no-email', action='store_true', help='Solo imprimir, no enviar email')
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"[Agent 2] LANCAST Estimador de Presupuesto")
    print(f"{'='*60}")

    if args.mode == 'test':
        print("[Agent 2] Corriendo caso de prueba: LPN Choloma...")
        estimate = estimate_from_boq(CHOLOMA_TEST, CHOLOMA_PROJECT)

    elif args.mode == 'boq':
        if not args.input:
            print("ERROR: --input requerido para modo boq")
            sys.exit(1)
        with open(args.input, 'r', encoding='utf-8') as f:
            boq_text = f.read()
        project_info = {
            'titulo': args.title or 'Proyecto sin título',
            'institucion': args.institution or 'No especificada',
            'ubicacion': 'Honduras'
        }
        estimate = estimate_from_boq(boq_text, project_info)

    elif args.mode == 'description':
        project_info = {
            'titulo': args.title or 'Proyecto sin título',
            'institucion': args.institution or 'No especificada',
            'ubicacion': 'Honduras'
        }
        estimate = estimate_from_description(args.desc or '', project_info)

    # Print summary
    print(format_estimate_text(estimate))

    # Save JSON
    output_file = f"estimado_{estimate.get('titulo_proyecto','proyecto')[:30].replace(' ','_')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(estimate, f, ensure_ascii=False, indent=2)
    print(f"\n[Agent 2] JSON guardado: {output_file}")

    # Send email
    if not args.no_email:
        conf = estimate.get('confianza', 'Media')
        conf_emoji = {'Alta': '🟢', 'Media': '🟡', 'Baja': '🔴'}.get(conf, '🟡')
        precio = estimate.get('resumen', {}).get('precio_oferta', 0)
        try:
            precio_fmt = f"L {float(precio):,.0f}"
        except:
            precio_fmt = str(precio)

        subject = f"🏗️ LANCAST — Estimado: {estimate.get('titulo_proyecto','')[:40]} | {precio_fmt} {conf_emoji}"
        send_estimate_email(estimate, subject)

    print(f"[Agent 2] ✅ Completado.")
