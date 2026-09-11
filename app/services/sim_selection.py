"""SIM is a selectable offer variant, not a separate device model."""
import re
from collections import defaultdict

from app.models.product import ProductCandidate
from app.services.variant_matching import sim_configuration

SIM_PATTERN = re.compile(
    r"\b(?:dual\s*e[-\s]?sim|dual\s*sim|single\s*sim|"
    r"(?:nano[-\s]?)?sim\s*\+\s*e[-\s]?sim|"
    r"(?:только\s+)?e[-\s]?sim|2\s*(?:x\s*)?(?:nano[-\s]?)?sim)\b", re.I
)
SIM_LABELS = {
    "dual_sim": "Dual SIM",
    "dual_esim": "Dual eSIM",
    "hybrid": "SIM + eSIM",
    "esim_only": "eSIM",
    "single_sim": "Single SIM",
    "unknown": "SIM не указана продавцом",
}


def without_sim(title: str) -> str:
    value = SIM_PATTERN.sub(" ", title)
    value = re.sub(r"\(\s*\)", " ", value)
    return " ".join(value.split()).strip(" ,-/")


def sim_groups(products: list[ProductCandidate]) -> list[tuple[str, list[ProductCandidate]]]:
    grouped = defaultdict(list)
    for product in products:
        grouped[sim_configuration(product.title) or "unknown"].append(product)
    return sorted(grouped.items(), key=lambda item: (item[0] == "unknown", SIM_LABELS[item[0]]))
