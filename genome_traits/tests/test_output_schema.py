from __future__ import annotations

from genome_traits.src.inference.output_schema import GenomeMetadata, ModelMetadata, build_output


def test_output_schema():
    output = build_output(
        genome=GenomeMetadata(total_bp=10, contigs=1, n_fraction=0.1),
        model=ModelMetadata(encoder="test", checkpoint="ckpt"),
        predictions={"taxonomy": {"order_top1": "X"}},
        runtime={"seconds": 1.2},
    )
    assert output["genome"]["total_bp"] == 10
    assert output["model"]["encoder"] == "test"
    assert "taxonomy" in output["predictions"]
