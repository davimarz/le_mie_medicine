from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors


def build_inventory_pdf(rows: list[dict], owner: str) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, title="Le mie medicine")
    styles = getSampleStyleSheet()
    story = [Paragraph("Le mie medicine", styles["Title"]), Paragraph(f"Intestatario: {owner}", styles["Normal"]), Spacer(1, 12)]
    data = [["Farmaco", "Principio attivo", "Quantità", "Scadenza", "AIC"]]
    for row in rows:
        data.append([
            str(row.get("nome") or ""), str(row.get("principio_attivo") or ""),
            f"{row.get('quantita', 0)} {row.get('tipo', '')}", str(row.get("scadenza") or ""), str(row.get("aic") or ""),
        ])
    table = Table(data, repeatRows=1, colWidths=[130, 120, 70, 70, 70])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1696d2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.extend([table, Spacer(1, 16), Paragraph("Documento organizzativo: non sostituisce medico, farmacista o prescrizione.", styles["Italic"])])
    doc.build(story)
    return output.getvalue()
