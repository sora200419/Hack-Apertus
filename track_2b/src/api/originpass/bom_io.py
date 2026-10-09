"""Load demo products and parse BOM CSV uploads."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from .models import BomLine, Product

CSV_COLUMNS = ["line_id", "description", "hs6", "origin_country", "value_chf", "supplier"]


class BomParseError(ValueError):
    pass


def normalise_hs6(raw: str | None) -> str | None:
    """'8413.70' / '8413 70' / '841370' -> '841370'; anything else -> None."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits[:6] if len(digits) >= 6 else None


def parse_bom_csv(
    text: str,
    name: str,
    ex_works_chf: float,
    hs6: str | None = None,
    description: str = "",
    product_id: str = "upload",
) -> Product:
    reader = csv.DictReader(io.StringIO(text.strip()))
    missing = {"description", "origin_country", "value_chf"} - set(reader.fieldnames or [])
    if missing:
        raise BomParseError(f"missing CSV columns: {', '.join(sorted(missing))}")
    lines: list[BomLine] = []
    for i, row in enumerate(reader, start=1):
        try:
            value = float(str(row["value_chf"]).replace("'", "").replace(",", "."))
        except ValueError as exc:
            raise BomParseError(f"row {i}: value_chf is not a number") from exc
        lines.append(
            BomLine(
                line_id=(row.get("line_id") or f"L{i:02d}").strip(),
                description=row["description"].strip(),
                hs6=normalise_hs6(row.get("hs6")),
                origin_country=row["origin_country"].strip().upper(),
                value_chf=value,
                supplier=(row.get("supplier") or "").strip() or None,
            )
        )
    if not lines:
        raise BomParseError("the CSV has no BOM lines")
    ids = [ln.line_id for ln in lines]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise BomParseError(f"duplicate line_id(s): {', '.join(dupes)}")
    return Product(
        product_id=product_id,
        name=name,
        description=description or name,
        hs6=normalise_hs6(hs6),
        ex_works_chf=ex_works_chf,
        bom=lines,
    )


def load_demo_products(data_dir: Path) -> dict[str, Product]:
    products: dict[str, Product] = {}
    for path in sorted((data_dir / "bom" / "demo").glob("*.json")):
        product = Product.model_validate(json.loads(path.read_text(encoding="utf-8")))
        products[product.product_id] = product
    return products
