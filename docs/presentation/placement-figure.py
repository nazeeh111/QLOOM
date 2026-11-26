import html
import json
import pathlib

r = pathlib.Path(__file__).resolve().parents[2]
out = pathlib.Path(__file__).resolve().parent
q = json.loads((r / "examples/live-studio/report.json").read_text())
b = next(x for x in q["candidates"] if x["id"] == q["best_id"])
assert (
    q["budget"] == 2
    and q["input"]["operations"][1] == {"gate": "cx", "qubits": [0, 2], "params": []}
    and q["device"]["edges"] == [[0, 1], [1, 2]]
    and b["initial_mapping"] == b["final_mapping"] == [1, 2, 0]
    and b["verification"]["passed"]
    and len(b["operations"]) == 3
)
assert [(o["gate"], o["qubits"]) for o in b["operations"]] == [("u", [1]), ("u", [2]), ("cx", [1, 0])]
assert b["verification"]["max_error"] == 1.401642967028923e-16
assert b["verification"]["tolerance"] == 1e-8
assert q["input"]["operations"][2] == {"gate": "ry", "qubits": [1], "params": [0.31]}
p = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630"><rect width="1200" height="630" fill="#f7f8fa"/><g font-family="Arial,Helvetica,sans-serif" fill="#142136">'
]


def txt(x, y, t, size=20, weight=400, color="#142136"):
    p.append(
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}">{html.escape(str(t))}</text>'
    )


def line(x1, y1, x2, y2, color="#8291a5", w=3, dash=""):
    p.append(
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{w}" stroke-dasharray="{dash}"/>'
    )


def node(x, y, label, sub):
    p.append(f'<circle cx="{x}" cy="{y}" r="35" fill="#fff" stroke="#1b53cf" stroke-width="4"/>')
    txt(x - 18, y + 8, label, 22, 700)
    txt(x - 22, y + 70, sub, 16)


txt(55, 70, "QLOOM", 19, 700, "#2755cf")
txt(55, 120, "Placement makes the operation adjacent.", 39, 700)
txt(55, 160, "Recorded three-qubit example · synthetic line-3 · two candidates", 20)
txt(70, 230, "LOGICAL INPUT", 17, 700)
txt(715, 230, "PHYSICAL CONNECTIVITY", 17, 700)
# Logical pair q0->q2 and isolated q1. Lines express interaction, not connectivity.
line(140, 330, 475, 330, "#2456d3", 6)
node(140, 330, "q0", "control")
node(307, 430, "q1", "Ry(0.31)")
node(475, 330, "q2", "target")
txt(200, 298, "CX(q0, q2)", 21, 700, "#2456d3")
# Device line, active edge from p1 to p0
line(745, 330, 910, 330, "#2456d3", 6)
line(910, 330, 1075, 330, "#9aa8b8", 4)
node(745, 330, "p0", "q2")
node(910, 330, "p1", "q0")
node(1075, 330, "p2", "q1")
txt(768, 298, "CX(p1, p0)", 21, 700, "#2456d3")
line(535, 345, 667, 345, "#1a2738", 3)
p.append('<path d="M655 337 L668 345 L655 353" fill="none" stroke="#1a2738" stroke-width="3"/>')
txt(538, 325, "map", 17, 700)
line(55, 515, 1145, 515, "#bcc6d2", 2)
txt(55, 558, "q0 → p1    q1 → p2    q2 → p0", 22, 700)
txt(55, 590, "Same initial and final mapping · no SWAP in the selected physical circuit", 17)
txt(800, 558, "Numerical check passed", 22, 700, "#2456d3")
txt(800, 590, "max error 1.40 × 10⁻¹⁶  /  tolerance 10⁻⁸", 16)
p.append("</g></svg>")
(out / "placement.svg").write_text("".join(p))
# Narrow layout uses the same selected report, with stacked diagrams.
p = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="930" viewBox="0 0 720 930"><rect width="720" height="930" fill="#f7f8fa"/><g font-family="Arial,Helvetica,sans-serif" fill="#142136">'
]
txt(40, 65, "QLOOM", 24, 700, "#2755cf")
txt(40, 118, "Placement makes the", 41, 700)
txt(40, 167, "operation adjacent.", 41, 700)
txt(40, 208, "Recorded example · synthetic line-3", 23)
txt(40, 276, "LOGICAL INTERACTION", 20, 700)
line(100, 365, 510, 365, "#2456d3", 7)
node(100, 365, "q0", "control")
node(510, 365, "q2", "target")
txt(240, 338, "CX(q0, q2)", 24, 700, "#2456d3")
txt(40, 483, "PHYSICAL CONNECTIVITY", 20, 700)
line(100, 575, 310, 575, "#2456d3", 7)
line(310, 575, 520, 575, "#9aa8b8", 4)
node(100, 575, "p0", "q2")
node(310, 575, "p1", "q0")
node(520, 575, "p2", "q1")
txt(143, 548, "CX(p1, p0)", 24, 700, "#2456d3")
line(40, 690, 680, 690, "#bcc6d2", 2)
txt(40, 740, "q0 → p1   q1 → p2   q2 → p0", 25, 700)
txt(40, 781, "No SWAP in the selected circuit", 22)
txt(40, 838, "Numerical check passed", 26, 700, "#2455cf")
txt(40, 875, "Max error 1.40 × 10⁻¹⁶ · tolerance 10⁻⁸", 20)
p.append("</g></svg>")
(out / "placement-mobile.svg").write_text("".join(p))
