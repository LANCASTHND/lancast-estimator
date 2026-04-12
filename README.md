# LANCAST Estimador de Presupuesto 🏗️

**Agent 2** del stack LANCAST — estima automáticamente el presupuesto de licitaciones hondureñas usando la tabla maestra de precios unitarios LANCAST + CHICO IV-2025.

## Características

- Detecta automáticamente si el contrato es **Suministro** u **Obra**
- 90 precios unitarios LANCAST de 6 proyectos reales (2024-2026)
- Referencia CHICO IV-2025 para validación de mercado
- Email HTML con cuadro completo + semáforo de confianza
- Integración con Agent 1 (Monitor HonduCompras)

## Archivos

```
lancast-estimator/
├── estimator.py        # Motor de estimación con Claude AI
├── run_estimate.py     # Ejecutor con casos de prueba
├── integration.py      # Conector Agent 1 + Agent 2
├── precios_unitarios.csv  # Base de datos de precios LANCAST
├── requirements.txt
└── README.md
```

## Uso

```bash
# Instalar
pip install -r requirements.txt --user

# Caso de prueba (Choloma LPN)
python run_estimate.py --mode test

# Con cuadro de cantidades en texto
python run_estimate.py --mode boq --input cantidades.txt --title "Proyecto X" --institution "FHIS"

# Solo con descripción narrativa
python run_estimate.py --mode description --title "Pavimentación SPS" --desc "Pavimentación de 500ml..."
```

## Variables de entorno (.env)

```
ANTHROPIC_API_KEY=sk-ant-...
SENDGRID_API_KEY=SG....
GMAIL_ADDRESS=licitaciones@lancast.biz
ALERT_EMAIL=gerencia@lancast.biz
```

## Stack LANCAST — Roadmap

- ✅ **Agent 1**: Monitor HonduCompras → alerta email diaria
- ✅ **Agent 2**: Estimador de presupuesto automático
- 🔄 **Agent 3**: Inteligencia de reuniones (próximo)
- 📋 **Agent 4**: Monitor de ejecución PMR (post-adjudicación)

---
LANCAST | Constructora Lanza Castillo S. de R.L. | Honduras
