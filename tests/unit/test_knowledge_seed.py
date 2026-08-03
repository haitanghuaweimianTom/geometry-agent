def test_curated_entries_have_required_fields():
    from geometry_agent.knowledge.curated import PLANE_ENTRIES
    assert len(PLANE_ENTRIES) >= 10
    for e in PLANE_ENTRIES[:5]:
        assert hasattr(e, "formal_id")
        assert hasattr(e, "proof_hint")


def test_all_three_grades_present():
    from geometry_agent.knowledge.curated import CURATED_ENTRIES
    from geometry_agent.types import GradeLevel
    grades = {e.grade for e in CURATED_ENTRIES}
    assert GradeLevel.JUNIOR in grades
    assert GradeLevel.SENIOR in grades
    assert GradeLevel.COMPETITION in grades


def test_new_seed_entries_count():
    from geometry_agent.knowledge.curated import CURATED_ENTRIES
    from geometry_agent.types import GradeLevel
    junior_seeds = [e for e in CURATED_ENTRIES if e.grade == GradeLevel.JUNIOR and e.proof_hint]
    senior_seeds = [e for e in CURATED_ENTRIES if e.grade == GradeLevel.SENIOR and e.proof_hint]
    comp_seeds = [e for e in CURATED_ENTRIES if e.grade == GradeLevel.COMPETITION]
    assert len(junior_seeds) >= 10
    assert len(senior_seeds) >= 15
    assert len(comp_seeds) >= 10


def test_required_junior_seed_ids():
    from geometry_agent.knowledge.curated import CURATED_ENTRIES
    required = {
        "pg-angle-bisector-theorem", "pg-median-length", "pg-projection-theorem",
        "pg-tangent-chord-angle", "pg-power-of-point", "pg-ceva", "pg-menelaus",
        "pg-heron", "pg-midpoint-coord", "pg-parallel-proportional",
    }
    ids = {e.id for e in CURATED_ENTRIES}
    assert required.issubset(ids)


def test_required_senior_seed_ids():
    from geometry_agent.knowledge.curated import CURATED_ENTRIES
    required = {
        "sg-ellipse-focal-triangle-area", "sg-hyperbola-asymptote",
        "sg-parabola-focal-chord", "sg-vector-collinear", "sg-plane-perpendicular",
        "sg-normal-dihedral", "sg-derivative-extremum-shift", "sg-stars-bars",
        "sg-normal-3sigma", "sg-parametric-max", "sg-sine-area",
        "sg-point-line-distance", "sg-vieta-conic", "sg-space-vector-angle",
        "sg-sequence-telescoping",
    }
    ids = {e.id for e in CURATED_ENTRIES}
    assert required.issubset(ids)


def test_required_competition_seed_ids():
    from geometry_agent.knowledge.curated import CURATED_ENTRIES
    required = {
        "cp-desargues", "cp-pascal", "cp-pole-polar", "cp-inversion",
        "cp-complex-rotation", "cp-schur", "cp-weighted-amgm", "cp-harmonic-range",
        "cp-area-elimination", "cp-universal-substitution",
    }
    ids = {e.id for e in CURATED_ENTRIES}
    assert required.issubset(ids)
