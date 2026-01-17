# Genome Traits

This package contains a scaffolded implementation of the genome-to-traits system described in `genome_traits_spec.md`.

## Quick start

```bash
python -m genome_traits.src.inference.predict --fasta path/to/genome.fa --out results.json --mode sampled --n_windows 256
```

## Training

```bash
python -m genome_traits.src.training.train --config genome_traits/configs/train.yaml
```

## Evaluation

```bash
python -m genome_traits.src.training.evaluate --checkpoint checkpoint.pt --split family_holdout
```

## Repository layout

See `genome_traits_spec.md` for the detailed design and requirements.
