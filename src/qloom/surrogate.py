"""Safe JSON inference for a compact ExtraTrees ensemble; no pickle loading."""

import json
from hashlib import sha256
from pathlib import Path

from .features import FEATURE_NAMES, features
from .routing import CONFIGS

DEFAULT_MODEL = Path(__file__).with_name("data") / "surrogate.json"


class Surrogate:
    def __init__(self, path=None):
        self.path = Path(path or DEFAULT_MODEL)
        if not self.path.exists():
            raise ValueError("Trained model not found. Run qloom train or install the packaged model.")
        content = self.path.read_bytes()
        self.data = json.loads(content)
        if self.data.get("feature_names") != FEATURE_NAMES:
            raise ValueError("Model feature schema does not match this QLOOM version.")
        self.sha256 = sha256(content).hexdigest()

    def predict_row(self, row):
        values = []
        for tree in self.data["trees"]:
            node = 0
            while tree["left"][node] != -1:
                node = (
                    tree["left"][node]
                    if row[tree["feature"][node]] <= tree["threshold"][node]
                    else tree["right"][node]
                )
            values.append(tree["value"][node])
        return sum(values) / len(values)

    def rank(self, qc, device, graph_aware=True):
        scores = [self.predict_row(features(qc, device, c, graph_aware)) for c in CONFIGS]
        return sorted(range(len(CONFIGS)), key=lambda i: (scores[i], i)), scores

    def metadata(self):
        return {
            "name": self.data["name"],
            "training_rows": self.data["training_rows"],
            "training_circuits": self.data["training_circuits"],
            "features": len(FEATURE_NAMES),
            "sha256": self.sha256,
            "training": self.data.get("training", {}),
        }


def export_forest(model, metadata, path):
    data = {"name": "QLOOM graph-aware ExtraTrees", "feature_names": FEATURE_NAMES, **metadata, "trees": []}
    for estimator in model.estimators_:
        t = estimator.tree_
        data["trees"].append(
            {
                "left": t.children_left.tolist(),
                "right": t.children_right.tolist(),
                "feature": t.feature.tolist(),
                "threshold": t.threshold.tolist(),
                "value": t.value[:, 0, 0].tolist(),
            }
        )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, separators=(",", ":")) + "\n")
