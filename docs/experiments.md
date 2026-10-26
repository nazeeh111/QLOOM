# Reproducing QLOOM's experiments

QLOOM uses a small CPU-trained ExtraTrees surrogate to rank 24 explicit compiler
configurations. It does not claim a new learning algorithm, a graph neural
network, or a universal improvement over existing quantum compilers. Its graph
features describe the circuit interaction graph, the hardware graph, and the
proposed placement. The model chooses a configuration evaluation order; the
native compiler and independent verifier establish the measured outcomes.

## Training evidence

`models/training-evaluations.jsonl` contains 2,880 real native compilations: every
one of the 24 configurations on 120 distinct numerical circuit-device inputs.
All training candidates pass full complex unitary comparison, including global
phase, and eight seeded randomized input checks in the independent NumPy
interpreter. Training stops on a failed check rather than fitting a failed label.
The 120 circuit inputs have distinct recorded SHA-256 hashes. Training circuits
use random, commuting-mirror, and QAOA families on 3–6 qubits with line, ring,
and grid processors. Seeded input rotations and global phases prevent a changed
seed from merely renaming the same numerical circuit.

The regression target is the measured hardware objective divided by the input
two-qubit gate count plus one. Normalization has no effect on ranking candidates
within a fixed circuit-device instance. Forty-eight ExtraTrees estimators have a
maximum depth of ten and a minimum leaf size of three. The random seed is
20261025. Exact versions, feature names, source fingerprint, input QASM,
phase, device, raw labels, and model hashes are retained in `models/`.

The graph-free ablation is a separate estimator fitted to the same numerical
labels after removing all thirteen graph summaries. It is not an inference-only
mask applied to the main model. Both models are exported to JSON trees; normal
inference loads no pickle and requires no scikit-learn installation.

An in-sample fit score is recorded for diagnostics. It is not a generalization
claim. The training time is measured CPU wall time on the recorded environment,
not a guarantee for another machine.

## Held-out protocol

The full protocol uses 24 circuit-device instances, six families by four
processor topologies, with four or five qubits. Test circuit seeds are separate
from training seeds, and input hashes are checked for exact overlap before any
benchmark is accepted. The entire star processor topology is absent from the
training labels. GHZ, Fourier, and star-phase families are absent from training.
Results are explicitly small-scale, synthetic-device experiments.

Requested seeds 0, 1, and 2 repeat the same circuit-device instances. Some
GHZ, QAOA, and Fourier numerical inputs also repeat across processor topologies.
The exact count of unique input hashes is reported separately; all observations
sharing an input hash form one uncertainty cluster. The learned ranker and heuristic are
deterministic. Random search varies with the seed. QMAP's interface has no
random-seed parameter, so repeated seed requests do not imply independent QMAP
randomness. Qiskit and BQSKit receive their documented seed parameters.

All native configurations are compiled and independently checked to establish a
24-configuration oracle for each test instance. This oracle is the best of
QLOOM's search space, not a global optimum over all quantum circuits. Separately,
real online search calls evaluate exactly four candidates for learned search,
seeded random search, a distance heuristic, and the retrained graph-free model.
The no-rewrite ablation evaluates four ranked configurations from the restricted
rewrite-disabled space. The same device, basis, semantics checks, and hardware
objective apply to every successful output.

The benchmark also records a budget curve at 1, 2, 4, 8, 12, and 24 evaluations by
replaying saved exhaustive numerical labels. Those points describe selection
quality only and make no online wall-time claim. The four-evaluation main rows
come from actual search runs, including feature extraction, model inference,
compilation, and independent verification wall time.

Qiskit optimization levels 0–3 and the QMAP heuristic mapper are evaluated on all
instances. BQSKit level 1, two-qubit synthesis blocks, one worker, and a 45-second
wall-time cap are evaluated on four named instances across all three seeds:

- `test-random-line-4`
- `test-mirror-star-5`
- `test-qft-ring-5`
- `test-starphase-grid-5`

BQSKit's subset is deliberately reported separately. It must not be aggregated
as if it covered all 24 instances. Failed imports, timeouts, unsupported outputs,
and failed equivalence checks are explicit failure rows and never wins for
QLOOM. A single external compiler invocation has an internal budget that differs
from four native candidate evaluations. Read quality and measured wall time
together; this is not a claim of identical compiler internals or equal search
effort. QMAP/BQSKit phase corrections are recorded, and strict complex-amplitude
equivalence is checked again after restoring that scalar.

## Metrics and uncertainty

Each successful row reports two-qubit gate count, depth, ASAP-scheduled synthetic
duration, compilation time, total search/verification time, and an independent
no-error product estimate. The optimization objective is

```text
CX count + 0.04 × depth + 8 × (−log estimated gate success probability)
```

The success estimate is the product of independent gate no-error probabilities.
It is not a measured fidelity. The device's U and CX error probabilities and
durations are explicit. There are no real processor calibrations, pulse-level
models, crosstalk, T1/T2 terms, or real QPU runs in this experiment.

The report includes mean relative objective regret against the native oracle,
oracle-hit rates, and paired differences against each applicable method.
Ninety-five-percent intervals use 2,000 cluster-bootstrap draws over unique
circuit input hashes. All repeated-topology and seed observations sharing an
input hash remain together when a cluster is resampled. Cluster weights preserve
the reported circuit-device case mean. This avoids treating the same numerical
circuit on two devices as two independent circuit samples. Negative external regret is valid: an external compiler can beat the
best circuit found anywhere in QLOOM's restricted native search space.

Exact density-matrix simulations compare QLOOM's output with Qiskit level 0 for a
zero logical input. The reported fidelity is the squared Bhattacharyya overlap
between ideal and noisy output distributions. Readout is modeled by independent
symmetric flips. This distribution metric can conceal coherent errors and is
never used as proof of logical equivalence. Strict matrix checks remain a
separate requirement.

## Commands and artifacts

From an installed editable checkout with research dependencies:

```sh
qloom train --out models/surrogate.json
qloom benchmark --out benchmarks
python scripts/plot_results.py --root .
```

The `training.train_model` and `experiments.run_experiments` Python functions
provide the same reproducible routes. A quick smoke mode uses fewer training
circuits or test families; its output must not replace a full result without
updating the denominator and report.

Artifacts:

- `models/training-manifest.json`: numerical inputs, processors, seeds, hashes.
- `models/training-evaluations.jsonl`: every verified training label and feature.
- `models/surrogate.json`, `models/surrogate-no-graph.json`: safe inference trees.
- `benchmarks/manifest.json`: test inputs, split evidence, seeds, BQSKit subset.
- `benchmarks/results.jsonl`: real online methods, compiler outcomes, failures,
  measured timing, independent verification, and noise comparisons.
- `benchmarks/exhaustive.jsonl`: full verified native search-space labels.
- `benchmarks/budget-replay.jsonl`: explicitly labeled offline budget replay.
- `benchmarks/summary.json`: denominators, uncertainty, unsuccessful cases,
  compiler versions, environment, model and result hashes.
- `docs/figures/`: plots generated directly from those saved numerical results.

A protocol source file is not evidence that the experiment completed. Use the
saved result files and their recorded statuses to establish what actually ran.

## Observed full-run results

The saved run evaluated **24 circuit-device instances, 18 unique numerical circuit
inputs, and three requested seeds**. It produced 2,016 freshly verified held-out
native candidates, in addition to the 2,880 verified training labels. The initial
full run took 424.76 seconds on the recorded CPU environment. A targeted QMAP
adapter recheck is recorded separately. These are measured local results, not
claims about larger circuits or physical quantum processors.

All rows below cover the same 24 instances. Native methods use four candidate
evaluations, except the 24-candidate oracle. Values are means across the recorded
cases and requested seeds; lower objective is better.

| Method | CX gates | Objective | Total wall time (s) | Native-oracle hit rate |
|---|---:|---:|---:|---:|
| learned | 13.625 | 15.666 | 0.245 | 83.3% |
| random | 14.264 | 16.401 | 0.091 | 68.1% |
| heuristic | 13.583 | 15.619 | 0.147 | 87.5% |
| no-graph | 13.708 | 15.761 | 0.228 | 83.3% |
| no-rewrite | 16.708 | 19.177 | 0.127 | 25.0% |
| oracle-24 | 13.542 | 15.568 | 0.440 | 100.0% |
| qiskit-0 | 19.042 | 21.872 | 0.028 | 8.3% |
| qiskit-1 | 15.167 | 17.428 | 0.040 | 23.6% |
| qiskit-2 | 11.139 | 12.799 | 0.055 | 15.3% |
| qiskit-3 | 11.139 | 12.799 | 0.070 | 15.3% |

The learned policy reaches the native oracle in 83.3% of the seeded runs while
evaluating four of 24 configurations. Its mean relative regret is 0.982%,
compared with 4.396% for random search. The paired objective difference, learned
minus random, is −0.734 with a circuit-cluster 95% interval of [−1.519, −0.153].
Across 72 requested-seed runs this is 19 wins, 48 ties, and five losses. Seeds
are repeated observations; the interval resamples the 18 unique input clusters.

The strongest simple heuristic is slightly better than the learned policy on
this suite: 69 ties and three learned-policy losses. Qiskit levels 2 and 3 also
produce materially better circuits, with mean objective 12.799 versus QLOOM's
15.666. Qiskit level 3 beats QLOOM in 53 of 72 seeded runs, ties in 12, and loses
in seven. QLOOM is slower than random and heuristic search because graph feature
extraction and JSON forest inference have measurable overhead. These results
support a working budgeted learned compiler experiment, not superiority over
strong established compilers or the best simple heuristic.

The retrained graph-free ablation has mean objective 15.761, versus 15.666 for
the graph-aware model. The paired difference interval crosses zero, so this
suite does not establish a reliable graph-feature benefit. On the six unseen
star-topology instances, the learned objective is 14.017, compared with 13.911
for random and 13.828 for the heuristic. Generalization to that held-out
topology is an unsuccessful case. The seen-topology learned and heuristic means
are both 16.216, compared with 17.230 for random.

Removing the native rewrites increases mean objective from 15.666 to 19.177.
Relative regret can become very large when the oracle has nearly eliminated a
commuting mirror circuit, so absolute objective and gate count should be read
alongside mean ratios. The saved unsuccessful-case list includes every selected
example of the learned policy missing its own native oracle.

BQSKit has 12 successful runs on its four named instances. On that matched
subset, QLOOM has six wins and six losses; the paired mean objective interval
crosses zero. Do not compare its four-instance raw mean directly with a
24-instance mean. QMAP has 69 successful verified runs and three rejected
QFT-ring-five outputs under its documented default dynamic placement policy.
The QMAP input conversion passes an independent check, but the output mapping
metadata does not establish the same unitary for that case. The baseline remains
rejected; no reference-dependent permutation search or selective static-policy
fallback is used to rescue its score. The nine initial QMAP verification
failures are retained: six were traced to an idle-wire conversion issue, fixed
with exact identity markers, and then independently rechecked. All three QFT
failures remain explicit limitations of this adapter/policy combination.

The zero-input synthetic-noise comparison has mean output-distribution fidelity
0.95638 for QLOOM and 0.94224 for Qiskit level 0 over the 24 instances. This is
a limited comparison with level 0 under the stated artificial noise model. It
provides no evidence of superiority to Qiskit level 3, general input-state
fidelity, logical equivalence, or real QPU performance.

The current figures are generated directly from the saved records. The
quality-versus-time plot includes complete-coverage methods only. QMAP and
BQSKit are excluded from that plot because their accepted circuit mix differs.

A second fresh native run reproduces all 72 learned-search selections and all
five recorded deterministic metrics exactly. It independently checks the 288
selected candidates again. A complete new 120-circuit, 2,880-candidate training
run with the final source reproduces every parameter array in all 48 shipped
forest trees exactly. Source/timing provenance changes the model-file metadata
hash, as expected. `benchmarks/reproduction.json` records both source digests,
model hashes, counts, equality checks, and 241.80 seconds of measured wall time.
The shipped model remains unchanged. `scripts/reproduce_native.py` provides the
same independent rerun; temporary retraining outputs go to the specified work
directory, and the evidence report goes to `benchmarks/reproduction.json`.

`benchmarks/diagnostics/qmap-qft-ring-5-rejection.json` retains the actual rejected
QMAP output, source input, mappings, phase correction, metadata, and independent
verification details. The compiler has no seed parameter, so this diagnostic
applies to all three repeated requested-seed rows.
