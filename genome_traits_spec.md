# Genome-to-Traits Deep Learning System Specification

## 1) Purpose and Goals

### Objective

Build a system that ingests an animal genome assembly (FASTA, up to **3 billion base pairs**) and outputs predicted organism features (“traits”), e.g.:

- habitat: aquatic / terrestrial / aerial (multi-label allowed)
- taxonomy: order/family/class (classification)
- mass: continuous regression (predict log-mass, convert to kg/tons)

### Design intent

- **Scales to whole genomes** by chunking and hierarchical aggregation.
- Supports training on many species and inference on one genome at a time.
- Produces predictions with **confidence/uncertainty**.
- Provides evaluation tooling that avoids “cheating” via close phylogenetic leakage.

### Non-goals (v1)

- Not trying to prove causal genotype-to-phenotype mechanisms.
- Not modeling environment, epigenetics, gene expression, development.
- Not guaranteeing exact body mass (will be approximate).

---

## 2) High-Level Approach

### Core strategy

Use a **hierarchical model**:

1. **Windowing:** split genome into many sequence windows (e.g., 100k bp).
2. **Window encoder:** convert each window to an embedding using a pretrained DNA foundation model (initially frozen).
3. **Genome aggregator:** compress a variable number of window embeddings into a fixed genome embedding using a Perceiver-style latent bottleneck (cross-attention from latents to windows).
4. **Multi-task heads:** predict traits from the genome embedding.

This approach avoids quadratic attention over billions of tokens and supports variable genome sizes.

---

## 3) System Components

### 3.1 Data Ingestion

**Inputs:**

- Genome assembly in FASTA format (single file or multiple contigs).
- Optional metadata: species scientific name, taxon ID, assembly accession.

**Responsibilities:**

- Parse FASTA, normalize to uppercase, validate bases (A/C/G/T/N).
- Track contig lengths, total length, and N-content rate.
- Support compressed FASTA (.gz) if feasible.

**Output artifact:**

- A standardized internal “GenomeRecord” with contig list + metadata.

---

### 3.2 Window Generator

**Purpose:** Create sequence windows for training and inference.

**Configurable parameters:**

- `window_len` (default 100,000 bp)
- `stride` (default 50,000 bp for full coverage mode)
- `n_windows_per_epoch` (default 1024 windows/species for training sampling)
- `sampling_mode`:

  - `random_uniform`: randomly sample contig then position
  - `full_coverage`: deterministic sliding windows (used for inference or precompute)
  - `quality_filtered`: reject windows with >X% Ns (default X=20%)

**Training behavior:**

- Use stochastic sampling to cover the genome over multiple epochs.
- Ensure windows are sampled across contigs proportional to contig length.

**Inference behavior:**

- Two supported inference modes:

  - `sampled`: sample N windows for fast inference
  - `full`: cover entire assembly for best accuracy

---

### 3.3 Window Encoder (Pretrained Model Wrapper)

**Purpose:** Convert windows to embeddings.

**Requirements:**

- Implement an abstraction layer so the encoder can be swapped:

  - Encoder A: Nucleotide Transformer family
  - Encoder B: HyenaDNA family
  - Future: custom encoder

**Encoder wrapper interface:**

- Input: list of DNA strings (windows)
- Output: tensor of shape `[B, D]` window embeddings
- Must support GPU and batching.

**Pooling requirement:**

- Must define pooling from token-level outputs to window-level embedding:

  - v1: mean pooling over non-pad tokens
  - (Optional) alternative pooling: CLS token or attention pooling

**Performance:**

- Batch inference for windows (configurable batch size).
- Caching option:

  - `cache_embeddings=true`: persist computed window embeddings per genome for faster training iterations (optional but recommended).

---

### 3.4 Genome Aggregator

**Purpose:** Aggregate many window embeddings into a genome representation.

**Model design (v1): Perceiver-style latent bottleneck**

- Learnable latents: `M=256` (configurable)
- Layers: `L=2` cross-attention blocks (configurable)
- Attention: latents query window embeddings (key/value)
- Output: pooled genome vector `[D]` (mean of latents or CLS-latent)

**Why this choice:**

- Handles variable number of windows.
- Computation scales roughly with `O(M*N)` not `O(N^2)`.

---

### 3.5 Prediction Heads (Multi-task)

**Traits supported in v1:**

1. **Taxonomy head** (classification)

   - e.g. Order or Family
2. **Habitat head** (multi-label classification)

   - aquatic / terrestrial / aerial (extendable)
3. **Mass head** (regression)

   - predict `log10(mass_grams)` or `log10(mass_kg)`

**Losses:**

- Taxonomy: cross-entropy
- Habitat: binary cross entropy with logits (multi-label)
- Mass: MSE or Huber on log-mass

**Loss weighting:**

- Configurable weights (default: taxonomy 1.0, habitat 1.0, mass 1.0)
- Include class imbalance handling:

  - taxonomy: optional class weights
  - habitat: positive class weighting

---

### 3.6 Uncertainty Estimation

At least one of:

- Monte Carlo dropout at aggregator + heads
- Deep ensembles (multiple head models)
- Calibration metrics (ECE) for classification tasks

Output should include:

- predicted value
- confidence/probability
- uncertainty estimate for regression (e.g. predictive stddev)

---

## 4) Data Requirements and Label Pipeline

### 4.1 Sources

**Genomes:**

- NCBI assemblies or Ensembl genomes
- Programmer should implement one source first, with an adapter for the other.

**Trait labels:**

- Mammals v1: PanTHERIA (or comparable species-level trait dataset)
- Taxonomy: NCBI taxonomy or Ensembl metadata

### 4.2 Label Join Logic

- Must map genome → species identifier reliably.
- Use scientific name normalization and/or taxon ID when possible.
- Provide a “label audit report”:

  - number of genomes
  - number successfully matched to labels
  - dropped items and reasons (no label, ambiguous name, etc.)

### 4.3 Output training table

A canonical dataset table with one row per species:

- `species_id`
- `scientific_name`
- `assembly_path`
- `taxon_rank_labels` (order/family/etc)
- `habitat_labels` (multi-label vector)
- `log_mass` (float)
- additional traits optional

---

## 5) Training and Evaluation

### 5.1 Train/Validation/Test Splits (Leakage Avoidance)

**Critical requirement:** Do not random-split by species only.

Provide at least these split strategies:

1. **Family-held-out split** (recommended default)
2. **Order-held-out split** (harder, more honest)
3. Random split (allowed only for quick dev sanity checks)

### 5.2 Metrics

**Classification:**

- accuracy (taxonomy)
- macro F1 (habitat)
- AUROC (habitat, per label)
- calibration ECE (optional)

**Regression:**

- MAE on log-mass
- RMSE on log-mass
- Spearman correlation (optional)
- Report also in human units (kg/tons) for readability

### 5.3 Baselines (must implement)

- Taxonomy baseline: majority class
- Mass baseline: mean mass
- Smarter baseline: mean mass per family/order (if available in split)

### 5.4 Training phases

- Phase 1: freeze window encoder, train aggregator + heads
- Phase 2 (optional): partial fine-tune encoder (top layers only or LoRA)

### 5.5 Reproducibility

- Seed control for window sampling and training
- Log all configs, commit hash, dataset version, and splits

---

## 6) Inference Product Requirements

### 6.1 CLI

Provide a command-line tool:

- `predict --fasta path/to/genome.fa --out results.json --mode sampled --n_windows 2048`
- `predict --mode full` for full coverage
- `train --config config.yaml`
- `evaluate --checkpoint ckpt.pt --split order_holdout`

### 6.2 Outputs

JSON output schema must include:

- metadata (genome length, contig count, N%)
- model info (checkpoint id, encoder name)
- predictions:

  - taxonomy probabilities
  - habitat probabilities
  - mass prediction in kg and tons
  - uncertainty estimates
- runtime info (windows processed, time, GPU used)

Example (structure only):

```json
{
  "genome": {"total_bp": 2987000000, "contigs": 412, "n_fraction": 0.032},
  "model": {"encoder": "nt_v2_100m", "checkpoint": "2026-01-17_abc123"},
  "predictions": {
    "taxonomy": {"order_top1": "Cetacea", "order_top1_prob": 0.91},
    "habitat": {"aquatic": 0.98, "terrestrial": 0.05, "aerial": 0.01},
    "mass": {"kg": 27000, "tons": 27, "uncertainty_kg_std": 8000}
  }
}
```

### 6.3 Runtime Modes

- Sampled mode must run on a single GPU in a reasonable time (developer-defined target, but should be practical).
- Full mode may be slower but must be robust and memory-safe.

---

## 7) Implementation Requirements

### 7.1 Language/Framework

- Python 3.10+
- PyTorch
- Transformers (if using NT)
- BioPython or pyfaidx for FASTA parsing
- Hydra / YAML configs recommended

### 7.2 Hardware Support

- Must run on:

  - single-GPU workstation (consumer GPU acceptable)
  - CPU fallback for small tests (slow is fine)

### 7.3 Memory and Performance Constraints

- Must not load full genome into GPU memory.
- Window sampling must stream from disk (or memory-map).
- Must support mixed precision (fp16/bf16) where available.

### 7.4 Checkpointing and Logging

- Save checkpoints: best val, last epoch
- TensorBoard or Weights & Biases logging:

  - losses, metrics, learning rate
  - split type and leakage strategy
  - window sampling parameters

### 7.5 Error Handling

Must fail loudly and clearly if:

- FASTA invalid
- no valid windows (contigs too small)
- labels missing/unmatched
- checkpoint/encoder mismatch

---

## 8) Repository Layout (Recommended)

```
genome_traits/
  README.md
  configs/
    train.yaml
    predict.yaml
  data/
    raw/                 # optional, not committed
    processed/
    splits/
  src/
    ingest/
      fasta_reader.py
      window_sampler.py
    encoders/
      base.py
      nucleotide_transformer.py
      hyenadna.py
    models/
      aggregator.py
      heads.py
      multitask_model.py
    training/
      train.py
      evaluate.py
      losses.py
      metrics.py
    inference/
      predict.py
      output_schema.py
    utils/
      config.py
      logging.py
      seed.py
  scripts/
    download_genomes.py
    build_labels_table.py
    make_splits.py
  tests/
    test_window_sampler.py
    test_output_schema.py
```

---

## 9) Acceptance Criteria (Definition of Done)

### Functional

- Can train from a dataset table (species → fasta + traits)
- Produces a saved checkpoint
- Can run inference on a new FASTA and output JSON predictions
- Provides evaluation with honest splits (family/order-held-out)

### Quality

- Baselines implemented and reported
- Training is reproducible given fixed seeds/config
- Clear documentation and example commands
- Unit tests for:

  - FASTA parsing
  - window sampling
  - JSON output schema
  - split logic sanity checks

### Minimum performance expectations (v1)

- Must beat “mean mass per family/order” baseline on at least one honest split, otherwise it’s basically just a taxonomy lookup with extra steps.

---

## 10) Milestones (Suggested Work Plan)

1. **M0: scaffolding**

   - repo layout, config system, CLI skeleton
2. **M1: ingestion + window sampler**

   - FASTA parsing, sampling modes, tests
3. **M2: encoder wrapper**

   - NT integration, batch embedding, pooling
4. **M3: aggregator + heads**

   - Perceiver-style aggregator, multi-task outputs
5. **M4: training + eval**

   - datasets, splits, baselines, metrics
6. **M5: inference tool**

   - JSON outputs, sampled vs full coverage
7. **M6: polish**

   - caching, uncertainty, docs, packaging

---

## 11) Risks and Mitigations

- **Phylogenetic leakage** makes results look amazing.

  - Mitigation: family/order-held-out splits, taxonomy baselines.
- **Genome assembly quality varies** (N-rich scaffolds).

  - Mitigation: N% filtering and reporting, quality flags.
- **“Mass from genome” is noisy**.

  - Mitigation: predict log-mass, include uncertainty, present as approximate.
- **Compute cost**

  - Mitigation: sampling, freezing encoder, caching embeddings.
