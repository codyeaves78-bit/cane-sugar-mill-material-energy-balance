# PFD + Excel export for CogenTurbine.
#
# Same sideways-trapezoid turbine glyph as turbine_diagram.py, plus a
# generator on the shaft so the electrical output (kW) is drawn explicitly:
#   (1) live steam in at the top-left corner,
#   (2) exhaust out of the bottom-right corner,
#   (G) shaft power into the generator, electrical output out the right.

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def _fmt_x(x):
    return "Superheat" if x is None or x >= 1.0 else x


def plot_cogen_turbine(turbine, show: bool = True, save_path: str = None) -> plt.Figure:
    """Draw the cogen turbine + generator with tagged streams and a
    performance table below. Returns the matplotlib Figure."""
    exhaust = turbine.exhaust_steam

    STMC = '#c0392b'   # live steam
    EXHC = '#d35400'   # exhaust
    HPC  = '#2c3e50'   # shaft power
    ELC  = '#1e8449'   # electrical output
    EQ_EC, EQ_FC = '#2471a3', '#d6eaf8'
    GEN_EC, GEN_FC = '#7d6608', '#fef9e7'

    DW, DH = 15.5, 8.2
    fig = plt.figure(figsize=(12.5, 8.6))
    gs  = fig.add_gridspec(2, 1, height_ratios=[5.1, 3.0], hspace=0.05)
    ax  = fig.add_subplot(gs[0])
    axt = fig.add_subplot(gs[1])
    axt.axis('off')
    fig.patch.set_facecolor('#f8f9fa')

    ax.set_xlim(0, DW)
    ax.set_ylim(0, DH)
    ax.set_aspect('equal')
    ax.axis('off')

    def arr(x1, y1, x2, y2, color, lw=2.0):
        ann = ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                          arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                                          shrinkA=0, shrinkB=0), clip_on=False)
        ann.arrow_patch.set_zorder(4)

    def seg(pts, color, lw=2.0):
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=color, lw=lw, zorder=3, clip_on=False,
                solid_joinstyle='miter')

    def tag(x, y, text, color):
        ax.add_patch(mpatches.Circle((x, y), 0.32, facecolor='white',
                                     edgecolor=color, lw=1.6, zorder=6))
        ax.text(x, y, str(text), ha='center', va='center',
                fontsize=7.5 if len(str(text)) < 2 else 6.5,
                fontweight='bold', color=color, zorder=7)

    def lbl(x, y, text, fs=9, color='#1c2833', bold=False, ha='center', va='center'):
        ax.text(x, y, text, ha=ha, va=va, fontsize=fs, color=color,
                fontweight='bold' if bold else 'normal', zorder=7, clip_on=False)

    # ── Turbine: sideways trapezoid, small face left / large face right ───
    ax.add_patch(mpatches.Polygon([(4.6, 4.3), (4.6, 5.7), (8.0, 6.7), (8.0, 3.3)],
                                  closed=True, facecolor=EQ_FC, edgecolor=EQ_EC,
                                  lw=2.0, zorder=2))
    lbl(6.3, 5.0, 'Turbine', fs=10, bold=True, color='#1a3a5c')

    # ── Generator: circle on the shaft ─────────────────────────────────────
    ax.add_patch(mpatches.Circle((10.4, 5.0), 1.15, facecolor=GEN_FC,
                                 edgecolor=GEN_EC, lw=2.0, zorder=2))
    lbl(10.4, 5.0, 'G', fs=15, bold=True, color=GEN_EC)
    lbl(10.4, 3.55, 'Generator', fs=8.5, color=GEN_EC)

    # (1) live steam in at the top-left corner
    seg([(0.8, 7.3), (4.6, 7.3)], STMC)
    arr(4.6, 7.3, 4.6, 5.75, STMC)
    lbl(0.8, 7.7, 'Live Steam', fs=9.5, bold=True, color=STMC, ha='left')
    tag(2.5, 7.3, 1, STMC)

    # (2) exhaust out of the bottom-right corner
    seg([(8.0, 3.3), (8.0, 1.6)], EXHC)
    arr(8.0, 1.6, 12.4, 1.6, EXHC)
    lbl(12.4, 2.0, 'Exhaust', fs=9.5, bold=True, color=EXHC, ha='right')
    tag(9.6, 1.6, 2, EXHC)

    # (G) shaft power out of the turbine into the generator
    arr(8.0, 5.0, 9.2, 5.0, HPC)
    lbl(8.6, 5.6, 'Shaft', fs=8, color=HPC)

    # electrical output out of the generator
    arr(11.55, 5.0, 14.4, 5.0, ELC)
    lbl(14.4, 5.5, 'Electrical Output', fs=9.5, bold=True, color=ELC, ha='right')
    lbl(14.4, 4.5, f'{turbine.kw_output:,.0f} kW', fs=9.5, bold=True, color=ELC, ha='right')
    tag(12.9, 5.0, 'kW', ELC)

    lbl(DW / 2, DH - 0.15, f'{turbine.name} — PFD', fs=14, bold=True)

    # ── Tables ───────────────────────────────────────────────────────────
    def style(tab):
        tab.auto_set_font_size(False)
        tab.set_fontsize(8.5)
        for (r, c), cell in tab.get_celld().items():
            cell.set_edgecolor('#bfbfbf')
            if r == 0:
                cell.set_facecolor('#305496')
                cell.set_text_props(color='white', fontweight='bold', ha='center')
            elif r % 2 == 0:
                cell.set_facecolor('#f2f2f2')
            if c == 0 and r > 0:
                cell.set_text_props(ha='left')

    def fmt_x_str(x):
        return "Superheat" if x is None or x >= 1.0 else f'{x:.4f}'

    stream_rows = [
        ['Live Steam (1)', f'{turbine.inlet_steam.P:,.1f}', f'{turbine.inlet_steam.T:,.1f}',
         f'{turbine.h_in:,.2f}', fmt_x_str(turbine.inlet_steam.x), f'{turbine.steam_flow_lb_hr:,.0f}'],
        ['Exhaust (2)', f'{turbine.outlet_pressure_psia:,.1f}', f'{exhaust.T:,.1f}',
         f'{turbine.h_out_actual:,.2f}', fmt_x_str(exhaust.x), f'{turbine.exhaust_available:,.0f}'],
    ]
    tab1 = axt.table(cellText=stream_rows,
                     colLabels=['Stream', 'psia', 'temp °F', 'enthalpy\nBTU/lb', 'quality', 'flow\nlb/hr'],
                     cellLoc='right', bbox=[0.03, 0.55, 0.94, 0.4])
    style(tab1)

    perf_rows = [[
        f'{turbine.kw_output:,.0f}',
        f'{turbine.hp_demand:,.0f}',
        f'{turbine.isentropic_efficiency:.1%}',
        f'{turbine.steam_rate_kw:,.2f}',
        f'{turbine.steam_flow_lb_hr:,.0f}',
    ]]
    tab2 = axt.table(cellText=perf_rows,
                     colLabels=['Electrical\nOutput (kW)', 'Shaft\nHP', 'Isentropic\nEff.',
                                'Steam Rate\n(lb/kW-hr)', 'Steam Flow\n(lb/hr)'],
                     cellLoc='center', bbox=[0.03, 0.03, 0.94, 0.4])
    style(tab2)

    if save_path:
        fig.savefig(save_path, dpi=170, bbox_inches='tight')
    if show:
        plt.show()
    return fig


def cogen_turbine_to_excel(turbine, workbook, sheet_writer=None, name=None):
    """Write this cogen turbine to its own styled sheet: PFD, stream table,
    and performance. Pass an existing SheetWriter to append onto a shared
    sheet instead of creating a new one."""
    from excel_export import SheetWriter

    name = name or turbine.name
    exhaust = turbine.exhaust_steam
    is_superheated = exhaust.x is None or exhaust.x >= 1.0

    standalone = sheet_writer is None
    sw = sheet_writer or SheetWriter(workbook, name, ncols=6)
    if standalone:
        sw.title(name,
                 f"{turbine.kw_output:,.0f} kW | "
                 f"{turbine.outlet_pressure_psia:.1f} psia exhaust | "
                 f"eta = {turbine.isentropic_efficiency:.0%}")

    sw.section(f"{name} — PROCESS FLOW DIAGRAM")
    sw.blank()
    fig = plot_cogen_turbine(turbine, show=False)
    sw.image(fig, scale=0.5)
    plt.close(fig)

    sw.section(f"{name} — STREAMS")
    sw.table(
        ["Stream", "psia", "Temp (°F)", "Enthalpy (BTU/lb)", "Quality", "Flow (lb/hr)"],
        [
            ("Live Steam", turbine.inlet_steam.P, turbine.inlet_steam.T, turbine.h_in,
             _fmt_x(turbine.inlet_steam.x), turbine.steam_flow_lb_hr),
            ("Exhaust", turbine.outlet_pressure_psia, exhaust.T, turbine.h_out_actual,
             _fmt_x(exhaust.x), turbine.exhaust_available),
        ],
        fmts=["@", "0.0", "0.0", "0.00", "0.0000", "#,##0"],
    )

    sw.section(f"{name} — PERFORMANCE")
    sw.row("Electrical output",       turbine.kw_output,          "kW",         fmt="#,##0")
    sw.row("Shaft power",             turbine.hp_demand,          "HP",         fmt="#,##0")
    sw.row("Isentropic efficiency",   turbine.isentropic_efficiency, "",        fmt="0.0%")
    sw.row("Steam rate",              turbine.steam_rate_kw,      "lb/kW-hr",   fmt="0.00")
    sw.row("Steam flow",              turbine.steam_flow_lb_hr,   "lb/hr",      fmt="#,##0")
    sw.row("Exhaust available",       turbine.exhaust_available,  "lb/hr",      fmt="#,##0")
    if is_superheated:
        dsw = turbine.exhaust_available - exhaust.flow_lb_per_hr
        sw.row("Desuperheater water",  dsw,                        "lb/hr",      fmt="#,##0")

    return sw.finish() if standalone else sw
