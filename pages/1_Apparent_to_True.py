"""Standalone Streamlit helper: apparent measurements -> estimated true values.

Open from the sidebar when running streamlit_app.py, or run directly:
    python -m streamlit run pages/1_Apparent_to_True.py
Uses Streamlit and Matplotlib; no balance-model imports.

Hoekstra correlations discussed by Love (2002), Proc S Afr Sug Technol Ass
76:526-532, and reproduced in Guest (2018), section 3.8, pp. 21-22:
    DS = Brix * (1 - 0.00066 * (Brix - Pol))
    Sucrose = Pol + H * (DS - Pol)
The default H=0.0636 is an illustrative coefficient calculated from Guest's
Table 3.4 mean C-molasses analyses, not a Louisiana-fitted coefficient.
"""

import math

DEFAULT_H = 0.0636


def apparent_to_true(brix, apparent_purity, h=DEFAULT_H, measured_ds=None):
    """Return composition percentages; all concentrations are g/100 g stream.

    brix must be refractometer Brix, not hydrometer Brix. Purities are on
    a 0-100 scale. measured_ds, if supplied, replaces the estimated DS in
    both the sucrose and purity calculations. H is dimensionless.
    Inputs refer to the same sample on an insoluble-solids-free basis.
    """
    if not all(math.isfinite(x) for x in (brix, apparent_purity, h)):
        raise ValueError("Inputs must be finite numbers.")
    if not 0 < brix <= 100:
        raise ValueError("Refractometer Brix must be greater than 0 and at most 100.")
    if not 0 <= apparent_purity <= 100:
        raise ValueError("Apparent purity must be between 0 and 100%.")
    if not 0 <= h <= 1:
        raise ValueError("H must be between 0 and 1 for this correction.")

    pol = brix * apparent_purity / 100
    estimated_ds = brix * (1 - 0.00066 * (brix - pol))
    ds = estimated_ds if measured_ds is None else measured_ds
    if not math.isfinite(ds) or not 0 < ds <= 100:
        raise ValueError("Dry solids must be greater than 0 and at most 100 wt%.")
    if ds < pol:
        raise ValueError("Dry solids are below pol; this correction is unsuitable for these inputs.")

    sucrose = pol + h * (ds - pol)
    return {
        "pol": pol,
        "estimated_ds": estimated_ds,
        "dry_solids": ds,
        "sucrose": sucrose,
        "true_purity": 100 * sucrose / ds,
        "sucrose_on_rds": 100 * sucrose / brix,
        "nonsucrose": ds - sucrose,
        "water": 100 - ds,
    }


def main():
    import streamlit as st

    st.set_page_config(page_title="Apparent to True", layout="wide")
    st.title("Apparent to true measurements")
    st.caption("Hoekstra/Love correction - estimated composition of one sample.")

    left, right = st.columns(2)
    brix = left.number_input(
        "Refractometer Brix", min_value=0.0, max_value=100.0,
        value=81.8, step=0.1, format="%.2f", key="att_brix",
    )
    ap = right.number_input(
        "Apparent purity (%)", min_value=0.0, max_value=100.0,
        value=35.5, step=0.1, format="%.2f", key="att_ap",
        help="100 x pol / refractometer Brix. Use measurements from the same sample.",
    )
    h = st.number_input(
        "H correction factor", min_value=0.0, max_value=1.0,
        value=DEFAULT_H, step=0.001, format="%.4f", key="att_h",
    )
    measured_ds = None
    if st.checkbox("Use measured dry solids", key="att_use_ds"):
        measured_ds = st.number_input(
            "Measured dry solids (wt%)", min_value=0.0, max_value=100.0,
            value=80.9, step=0.1, format="%.2f", key="att_ds",
            help="Replaces estimated solids in both sucrose and true-purity calculations.",
        )

    st.info(
        "H = 0.0636 is provisional. In the 2025 Louisiana survey, purity agreed "
        "better than the separate solids and sucrose estimates. Use measured "
        "solids when available and calibrate H for your samples."
    )
    try:
        result = apparent_to_true(brix, ap, h, measured_ds)
    except ValueError as exc:
        st.error(str(exc))
        return

    cols = st.columns(3)
    cols[0].metric(
        "Dry solids (wt%)" if measured_ds is not None else "Estimated dry solids (wt%)",
        f"{result['dry_solids']:.2f}",
    )
    cols[1].metric("Estimated sucrose (wt%)", f"{result['sucrose']:.2f}")
    cols[2].metric("Estimated true purity (%)", f"{result['true_purity']:.2f}")
    st.write(f"Calculated pol: **{result['pol']:.2f} wt%**")
    st.write(
        f"Estimated sucrose / refractometer Brix: **{result['sucrose_on_rds']:.2f}%** "
        "(for comparison with syrup reports that use RDS as the denominator)."
    )
    st.caption(
        f"Estimated nonsucrose: {result['nonsucrose']:.2f} wt%; "
        f"water: {result['water']:.2f} wt%. All concentrations are on the same sample basis."
    )

    st.subheader("True purity vs. apparent purity")
    st.caption(
        "Brix 15 and 80 using the selected H and estimated dry solids. "
        "The measured dry-solids override applies only to the sample above."
    )
    import matplotlib.pyplot as plt

    purities = list(range(101))
    fig, ax = plt.subplots(figsize=(8, 5))
    for curve_brix in [15, 80]:
        true_purities = [
            apparent_to_true(curve_brix, purity, h)["true_purity"]
            for purity in purities
        ]
        ax.plot(purities, true_purities, label=f"Brix {curve_brix}")
    ax.plot([0, 100], [0, 100], "--", color="gray", label="True = apparent")
    ax.set(xlabel="Apparent purity (%)", ylabel="True purity (%)",
           xlim=(0, 100), ylim=(0, 100))
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    with st.expander("Equations and basis"):
        st.latex(r"Pol = Brix\times AP/100")
        st.latex(r"DS_{est}=Brix[1-0.00066(Brix-Pol)]")
        st.latex(r"Sucrose=Pol+H(DS-Pol)")
        st.latex(r"True\ purity=100\times Sucrose/DS")
        st.markdown(
            "Use refractometer Brix and measurements on an insoluble-solids-free basis. "
            "These are estimates, not substitutes for sucrose and dry-solids assays. "
            "With paired assays, calculate **H = (sucrose - pol) / (DS - pol)** "
            "when DS differs from pol. Changing DS can require recalibration of H."
        )
        st.caption(
            "Reference: Love (2002), Estimating Dry Solids and True Purity from Brix "
            "and Apparent Purity, SASTA 76, 526-532. Equations and default-factor "
            "data reproduced in Guest (2018), section 3.8, Table 3.4."
        )


if __name__ == "__main__":
    main()
