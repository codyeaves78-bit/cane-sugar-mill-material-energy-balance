# Process flow diagram for EvaporatorSet objects.
#
# Vapor routing between effects (4-segment inverted-U):
#   1. UP   from body top-centre to Y_ROUTE (above all bodies)
#   2. RIGHT along Y_ROUTE to the midpoint of the gap between bodies
#   3. DOWN  in the open gap space (x_turn) to Y_MID
#   4. RIGHT with arrowhead into the centre of the next body's left side
#
# Bleeds exit from slightly LEFT of body top-centre so they never cross
# the rightward horizontal routing segment, and are drawn last (on top).
#
# Pressure labels show psia on one line and psig (>atm) or "Hg Vac (<atm)
# on the next line.  Bodies also show BPE, U-calc, and U-dessin.

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from EvaporatorSet import EvaporatorSet
from evaporator_functions import convert_psia_to_inHgVac


def _fmt_p2(psia: float) -> str:
    """Secondary pressure label: psig above atm, inches-Hg vacuum below."""
    if psia >= 14.696:
        return f'{psia - 14.696:.2f} psig'
    return f'{convert_psia_to_inHgVac(psia):.2f}" Hg Vac'


def plot_set_diagram(
    evap_set: EvaporatorSet,
    set_name: str = "",
    show: bool = True,
    save_path: str = None,
    pre_evap=None,
) -> plt.Figure:
    """
    Draw a process flow diagram for a single EvaporatorSet.
    Returns the matplotlib Figure.
    """
    n     = evap_set.number_of_effects
    evaps = evap_set.evaporator_list
    steam = evap_set.supply_steam

    # ── Layout ────────────────────────────────────────────────────────────
    BOX_W   = 3.0
    BOX_GAP = 2.0
    L_PAD   = 3.6
    R_PAD   = 3.6

    PRE_SHIFT = (BOX_W + BOX_GAP) if pre_evap else 0
    pre_cx    = (L_PAD + BOX_W / 2) if pre_evap else None

    DW = L_PAD + PRE_SHIFT + n * BOX_W + (n - 1) * BOX_GAP + R_PAD
    DH = 11.8

    Y_TTL   = DH - 0.25
    Y_BLEED = DH - 0.85
    Y_ROUTE = DH - 1.70   # horizontal vapor pipe level above bodies
    Y_TOP   = 8.10        # TOP  edge of body = vapor exit
    Y_BOT   = 2.70        # BOT  edge of body = juice connection (lowered for label room)
    Y_MID   = (Y_TOP + Y_BOT) / 2   # MID height = steam/vapor inlet
    Y_COND  = 1.45
    Y_FLASH = 0.55        # condensate flash-recovery routing level, below the condensate labels
    Y_FOOT  = -0.15

    centers = [L_PAD + PRE_SHIFT + BOX_W / 2 + i * (BOX_W + BOX_GAP) for i in range(n)]
    x_lft   = 0.12 * L_PAD
    x_rgt   = DW - 0.12 * R_PAD

    SC = '#c0392b'
    VC = '#d35400'
    JC = '#154360'
    CC = '#7f8c8d'
    BC = '#1e8449'
    HLC = '#e67e22'   # heat loss (vessel shell -> room)
    GBC = '#8e44ad'   # incondensable gas bleed (calandria vent)
    FVC = '#16a085'   # condensate flash vapor recovered to next effect
    BOX_EC = '#2471a3'
    BOX_FC = '#d6eaf8'

    fig_w_in = max(10.0, DW * 0.72)
    fig, ax  = plt.subplots(figsize=(fig_w_in, 9.5))
    ax.set_xlim(0, DW)
    ax.set_ylim(-0.5, DH)
    ax.axis('off')
    fig.patch.set_facecolor('#f8f9fa')

    # ── Drawing helpers ───────────────────────────────────────────────────
    def arr(x1, y1, x2, y2, color, lw=1.8, ls='solid'):
        ann = ax.annotate(
            '', xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                            linestyle=ls, shrinkA=0, shrinkB=0),
            clip_on=False,
        )
        ann.arrow_patch.set_zorder(5)

    def seg(x1, y1, x2, y2, color, lw=1.8, ls='solid'):
        ax.plot([x1, x2], [y1, y2], color=color, lw=lw, ls=ls,
                zorder=4, clip_on=False)

    def lbl(x, y, text, ha='center', va='center',
            fs=8.5, color='black', bold=False):
        ax.text(x, y, text, ha=ha, va=va, fontsize=fs,
                color=color, fontweight='bold' if bold else 'normal',
                clip_on=False, zorder=6)

    # ── Title ─────────────────────────────────────────────────────────────
    lbl(DW / 2, Y_TTL, set_name or 'Evaporator Set', fs=14, bold=True, color='#1c2833')

    # ── Effect bodies ──────────────────────────────────────────────────────
    for i, (cx, evap) in enumerate(zip(centers, evaps)):
        rect = mpatches.FancyBboxPatch(
            (cx - BOX_W / 2, Y_BOT), BOX_W, Y_TOP - Y_BOT,
            boxstyle='round,pad=0.06', lw=2.0,
            edgecolor=BOX_EC, facecolor=BOX_FC, zorder=3)
        ax.add_patch(rect)

        vp = evap.vapor_pressure_psia

        lbl(cx, Y_MID + 1.95, f'Effect {i + 1}',           fs=11,  bold=True, color='#1a3a5c')
        lbl(cx, Y_MID + 1.32, f'{evap.area_ft2:,.0f} ft²', fs=9,   color='#566573')

        # Pressure — psia then psig / Hg-vac
        lbl(cx, Y_MID + 0.70, f'P: {vp:.2f} psia',  fs=8.5, color='#1a5276')
        lbl(cx, Y_MID + 0.30, _fmt_p2(vp),           fs=8,   color='#1a5276')

        # Temperatures
        lbl(cx, Y_MID - 0.15, f'Cald: {evap.calandria_side.sat_temp_deg_F:.1f} °F', fs=8, color=SC)
        lbl(cx, Y_MID - 0.55, f'Juice: {evap.juice_side_out.temp_deg_F:.1f} °F',    fs=8, color=JC)

        # Boiling point elevation
        lbl(cx, Y_MID - 0.92, f'BPE: {evap.bpe_juice:.2f} °F', fs=7.5, color='#6c3483')

        # Heat transfer coefficients
        lbl(cx, Y_MID - 1.28, f'U = {evap.heat_xfer_U:.1f}', fs=7.5, color='#117a65')
        lbl(cx, Y_MID - 1.63,
            f'Ud = {evap.dessin_U:.1f}  BTU/hr·ft²·°F', fs=7, color='#555555')

        # Latent heats
        lbl(cx, Y_MID - 1.98,
            f'hfg stm: {evap.calandria_side.h_fg:.1f} BTU/lb', fs=7, color='#922b21')
        lbl(cx, Y_MID - 2.32,
            f'hfg vap: {evap.juice_side_out.latent_heat_btu_per_lb:.1f} BTU/lb', fs=7, color='#1a5276')

    # ── Supply steam ───────────────────────────────────────────────────────
    if pre_evap:
        # Pre-evap steam from far left
        arr(x_lft, Y_MID, pre_cx - BOX_W / 2, Y_MID, color=SC, lw=2.2)
        lbl(x_lft, Y_MID + 0.68, 'Supply Steam (Pre)',                                   ha='left', fs=8.5, color=SC, bold=True)
        lbl(x_lft, Y_MID + 0.28, f'{pre_evap.exhaust_required_lb_per_hr:,.0f} lb/hr',   ha='left', fs=8,   color=SC)
        lbl(x_lft, Y_MID - 0.10, f'{pre_evap.supply_steam.P_psia:.1f} psia',            ha='left', fs=7.5, color=SC)
        lbl(x_lft, Y_MID - 0.44, _fmt_p2(pre_evap.supply_steam.P_psia),                 ha='left', fs=7.5, color=SC)
        # Main set steam drops from Y_ROUTE into the gap between pre-evap and effect 1
        x_stm = (pre_cx + centers[0]) / 2
        seg(x_stm, Y_ROUTE, x_stm, Y_MID, color=SC, lw=2.2)
        arr(x_stm, Y_MID, centers[0] - BOX_W / 2, Y_MID, color=SC, lw=2.2)
        lbl(x_stm, Y_ROUTE + 0.55, 'Supply Steam',                        ha='center', fs=8.5, color=SC, bold=True)
        lbl(x_stm, Y_ROUTE + 0.18, f'{steam.flow_lb_per_hr:,.0f} lb/hr', ha='center', fs=8,   color=SC)
        lbl(x_stm, Y_ROUTE - 0.18, f'{steam.P_psia:.1f} psia',           ha='center', fs=7.5, color=SC)
        lbl(x_stm, Y_ROUTE - 0.48, _fmt_p2(steam.P_psia),                ha='center', fs=7.5, color=SC)
    else:
        arr(x_lft, Y_MID, centers[0] - BOX_W / 2, Y_MID, color=SC, lw=2.2)
        lbl(x_lft, Y_MID + 0.68, 'Supply Steam',                           ha='left', fs=9,   color=SC, bold=True)
        lbl(x_lft, Y_MID + 0.28, f'{steam.flow_lb_per_hr:,.0f} lb/hr',    ha='left', fs=8.5, color=SC)
        lbl(x_lft, Y_MID - 0.10, f'{steam.P_psia:.1f} psia',              ha='left', fs=7.5, color=SC)
        lbl(x_lft, Y_MID - 0.44, _fmt_p2(steam.P_psia),                   ha='left', fs=7.5, color=SC)

    # ── Condensate ────────────────────────────────────────────────────────
    for i, (cx, evap) in enumerate(zip(centers, evaps)):
        arr(cx, Y_BOT, cx, Y_COND + 0.12, color=CC, lw=1.5)
        lbl(cx, Y_COND - 0.10,
            f'Condensate\n{evap.condensate_out:,.0f} lb/hr', fs=7.5, color=CC)

    # ── Pre-evaporator body ────────────────────────────────────────────────
    if pre_evap:
        rect = mpatches.FancyBboxPatch(
            (pre_cx - BOX_W / 2, Y_BOT), BOX_W, Y_TOP - Y_BOT,
            boxstyle='round,pad=0.06', lw=2.0,
            edgecolor=BOX_EC, facecolor=BOX_FC, zorder=3)
        ax.add_patch(rect)

        vp_pre = pre_evap.vapor_pressure_psia
        lbl(pre_cx, Y_MID + 1.95, 'Pre-Evaporator',                                       fs=11,  bold=True, color='#1a3a5c')
        lbl(pre_cx, Y_MID + 1.32, f'{pre_evap.area_ft2:,.0f} ft²',                        fs=9,   color='#566573')
        lbl(pre_cx, Y_MID + 0.70, f'P: {vp_pre:.2f} psia',                                fs=8.5, color='#1a5276')
        lbl(pre_cx, Y_MID + 0.30, _fmt_p2(vp_pre),                                        fs=8,   color='#1a5276')
        lbl(pre_cx, Y_MID - 0.15, f'Cald: {pre_evap.supply_steam.sat_temp_deg_F:.1f} °F', fs=8,   color=SC)
        lbl(pre_cx, Y_MID - 0.55, f'Juice: {pre_evap.liquid_temp_deg_F:.1f} °F',          fs=8,   color=JC)
        lbl(pre_cx, Y_MID - 0.92, f'Ud = {pre_evap.dessin_U:.1f}  BTU/hr·ft²·°F',        fs=7,   color='#555555')
        lbl(pre_cx, Y_MID - 1.28, f'U ratio = {pre_evap.U_ratio:.3f}',                    fs=7.5, color='#117a65')

        # Pre-evap condensate
        arr(pre_cx, Y_BOT, pre_cx, Y_COND + 0.12, color=CC, lw=1.5)
        lbl(pre_cx, Y_COND - 0.10,
            f'Condensate\n{pre_evap.exhaust_required_lb_per_hr:,.0f} lb/hr', fs=7.5, color=CC)

        # Pre-evap vapor bleed: exits top, routes LEFT toward heaters/pans
        seg(pre_cx, Y_TOP, pre_cx, Y_BLEED, color=BC, lw=1.8)
        arr(pre_cx, Y_BLEED, x_lft, Y_BLEED, color=BC, lw=1.8, ls='dashed')
        lbl(x_lft, Y_BLEED + 0.30, 'Bleed → Heaters / Pans',                                ha='left', fs=8.5, color=BC, bold=True)
        lbl(x_lft, Y_BLEED - 0.08, f'{pre_evap.vapor_bleed_lb_per_hr:,.0f} lb/hr',          ha='left', fs=8,   color=BC)
        lbl(x_lft, Y_BLEED - 0.38, f'{vp_pre:.2f} psia | {pre_evap.vapor_temp_deg_F:.1f} °F', ha='left', fs=7.5, color=BC)

    # ── Vapor routing: top-centre exit, inverted-U path, then bleed ───────
    for i, (cx, evap) in enumerate(zip(centers, evaps)):
        bleed     = evap.vapor_bleed.flow_lb_per_hr
        vapor_fwd = evap.vapor_out.flow_lb_per_hr - bleed

        if i < n - 1:
            next_cx = centers[i + 1]
            x_gap_l = cx      + BOX_W / 2   # right edge of body i
            x_gap_r = next_cx - BOX_W / 2   # left  edge of body i+1
            x_turn  = (x_gap_l + x_gap_r) / 2   # centre of gap — descent here

            # Segment 1 — UP
            seg(cx, Y_TOP, cx, Y_ROUTE, color=VC, lw=1.8)
            # Segment 2 — RIGHT to gap centre
            seg(cx, Y_ROUTE, x_turn, Y_ROUTE, color=VC, lw=1.8)
            # Segment 3 — DOWN in open gap space
            seg(x_turn, Y_ROUTE, x_turn, Y_MID, color=VC, lw=1.8)
            # Segment 4 — RIGHT with arrowhead into next body
            arr(x_turn, Y_MID, x_gap_r, Y_MID, color=VC, lw=1.8)

            # Labels on segment 2 (horizontal above body i — clear of both bodies)
            mid_x = (cx + x_turn) / 2
            lbl(mid_x, Y_ROUTE + 0.30, f'Vapor {i + 1}→{i + 2}', fs=8, color=VC, bold=True)
            lbl(mid_x, Y_ROUTE - 0.12, f'{vapor_fwd:,.0f} lb/hr',  fs=8, color=VC)

        else:
            # Last body — exits top, routes right to condenser
            seg(cx, Y_TOP, cx, Y_ROUTE, color=VC, lw=1.8)
            arr(cx, Y_ROUTE, x_rgt, Y_ROUTE, color=VC, lw=1.8, ls='dashed')
            lbl(x_rgt, Y_ROUTE + 0.52, 'To Condenser',             ha='right', fs=9,   color=VC, bold=True)
            lbl(x_rgt, Y_ROUTE + 0.14, f'{vapor_fwd:,.0f} lb/hr',  ha='right', fs=8.5, color=VC)
            lbl(x_rgt, Y_ROUTE - 0.22,
                f'{evap.vapor_pressure_psia:.2f} psia | {evap.vapor_temperature:.1f} °F',
                ha='right', fs=7.5, color=VC)

        # Vapor bleed — drawn AFTER vapor routing so it renders on top.
        # Exit from slightly LEFT of body top-centre so it never crosses the
        # rightward horizontal routing segment (which starts at cx and goes right).
        if bleed > 0.1:
            bx = cx - BOX_W * 0.20   # left of centre → clear of the rightward routing
            arr(bx, Y_TOP, bx, Y_BLEED, color=BC, lw=1.5)
            lbl(bx - 0.18, (Y_TOP + Y_BLEED) / 2 + 0.08,
                f'Bleed\n{bleed:,.0f} lb/hr', ha='right', fs=7.5, color=BC)

        # Incondensable gas bleed — vents from the calandria (steam side), drawn as a
        # short exit from top-RIGHT of body-centre, mirroring the process-vapor bleed
        # (top-LEFT) but shorter so it stays clear of the rightward routing segment.
        gas_bleed_flow = evap.calandria_side.flow_lb_per_hr - evap.condensing_steam_lb_per_hr
        if gas_bleed_flow > 0.5:
            gx = cx + BOX_W * 0.20
            gy = Y_TOP + 0.95
            arr(gx, Y_TOP, gx, gy, color=GBC, lw=1.5, ls='dashed')
            lbl(gx + 0.18, gy,
                f'Gas Bleed\n{evap.calandria_bleed_pec:.1f}% | {gas_bleed_flow:,.0f} lb/hr',
                ha='left', va='bottom', fs=7, color=GBC)

        # Vessel shell heat loss — not a process stream, so drawn as a short outward
        # arrow from the RIGHT side of the body rather than a piped exit.
        if evap.heat_loss_percent > 0.001:
            hx0, hy0 = cx + BOX_W / 2, Y_MID + 1.55
            hx1, hy1 = hx0 + 0.55, hy0 + 0.45
            arr(hx0, hy0, hx1, hy1, color=HLC, lw=1.5, ls='dashed')
            lbl(hx1 + 0.10, hy1,
                f'Heat Loss\n{evap.heat_loss_percent:.1f}% | {evap.heat_loss_btu_per_hr:,.0f} BTU/hr',
                ha='left', fs=7, color=HLC)

        # Condensate flash recovery — calandria condensate self-flashes down to the
        # next effect's pressure; the recovered vapor feeds that calandria as extra
        # heating steam. Routed BELOW the juice line (clear of it) then up into the
        # gap just short of the next body's steam inlet.
        if i < n - 1:
            flash = evap.condensate_flash_vapor_lb_per_hr
            if evap.cond_flash_to_next and flash > 0.5:
                x_next_lft = centers[i + 1] - BOX_W / 2
                fx         = x_next_lft - 0.25
                seg(cx, Y_COND - 0.55, cx, Y_FLASH, color=FVC, lw=1.4, ls='dashed')
                seg(cx, Y_FLASH, fx, Y_FLASH, color=FVC, lw=1.4, ls='dashed')
                arr(fx, Y_FLASH, fx, Y_MID - 0.55, color=FVC, lw=1.4, ls='dashed')
                lbl((cx + fx) / 2, Y_FLASH - 0.25,
                    f'Flash → Next Calandria\n{flash:,.0f} lb/hr', fs=7, color=FVC)

    # ── Juice stream at Y_BOT ─────────────────────────────────────────────
    if pre_evap:
        orig_juice = pre_evap.juice_in
        arr(x_lft, Y_BOT, pre_cx - BOX_W / 2, Y_BOT, color=JC, lw=2.2)
        lbl(x_lft, Y_BOT + 0.62, 'Juice In',                                              ha='left', fs=9,   color=JC, bold=True)
        lbl(x_lft, Y_BOT + 0.22, f'{orig_juice.flow_lb_per_hr:,.0f} lb/hr',               ha='left', fs=8.5, color=JC)
        lbl(x_lft, Y_BOT - 0.17,
            f'{orig_juice.brix:.2f}° Brix | {orig_juice.temp_deg_F:.1f} °F',
            ha='left', fs=7.5, color=JC)
        # Pre-evap juice out → effect 1 — this set's own allocated share of the
        # pre-evaporator's total output, not pre_evap.juice_out (that's the
        # combined total across every set fed from this shared Pre-Evaporator).
        pre_out  = evap_set.juice_in
        mid_pre  = (pre_cx + centers[0]) / 2
        arr(pre_cx + BOX_W / 2, Y_BOT, centers[0] - BOX_W / 2, Y_BOT, color=JC, lw=1.8)
        lbl(mid_pre, Y_BOT - 0.25, f'{pre_out.flow_lb_per_hr:,.0f} lb/hr', fs=8,   color=JC)
        lbl(mid_pre, Y_BOT - 0.60, f'{pre_out.brix:.2f}° Brix',            fs=8,   color=JC)
    else:
        juice_in = evap_set.juice_in
        arr(x_lft, Y_BOT, centers[0] - BOX_W / 2, Y_BOT, color=JC, lw=2.2)
        lbl(x_lft, Y_BOT + 0.62, 'Juice In',                                ha='left', fs=9,   color=JC, bold=True)
        lbl(x_lft, Y_BOT + 0.22, f'{juice_in.flow_lb_per_hr:,.0f} lb/hr',  ha='left', fs=8.5, color=JC)
        lbl(x_lft, Y_BOT - 0.17,
            f'{juice_in.brix:.2f}° Brix | {juice_in.temp_deg_F:.1f} °F',
            ha='left', fs=7.5, color=JC)

    for i in range(n - 1):
        cx, next_cx = centers[i], centers[i + 1]
        jout  = evaps[i].juice_side_out
        mid_x = (cx + next_cx) / 2
        arr(cx + BOX_W / 2, Y_BOT, next_cx - BOX_W / 2, Y_BOT, color=JC, lw=1.8)
        lbl(mid_x, Y_BOT - 0.25, f'{jout.flow_lb_per_hr:,.0f} lb/hr', fs=8, color=JC)
        lbl(mid_x, Y_BOT - 0.60, f'{jout.brix:.2f}° Brix',            fs=8, color=JC)

    last_out = evaps[-1].juice_side_out
    arr(centers[-1] + BOX_W / 2, Y_BOT, x_rgt, Y_BOT, color=JC, lw=2.2)
    lbl(x_rgt, Y_BOT + 0.62, 'Syrup Out',                               ha='right', fs=9,   color=JC, bold=True)
    lbl(x_rgt, Y_BOT + 0.22, f'{last_out.flow_lb_per_hr:,.0f} lb/hr',  ha='right', fs=8.5, color=JC)
    lbl(x_rgt, Y_BOT - 0.17,
        f'{last_out.brix:.2f}° Brix | {last_out.temp_deg_F:.1f} °F',
        ha='right', fs=7.5, color=JC)

    # ── Footer ────────────────────────────────────────────────────────────
    u_parts = [f'Eff {i + 1}: U={e.U_ratio:.3f}' for i, e in enumerate(evaps)]
    lbl(DW / 2, Y_FOOT,
        'U Ratios (calc / dessin)  —  ' + '   |   '.join(u_parts),
        fs=8, color='#666666')

    fig.tight_layout(pad=0.4)
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
    if show:
        plt.show()
    return fig


def plot_pre_diagram(
    pre,
    pre_name: str = "Pre Evaporator",
    show: bool = True,
    save_path: str = None,
) -> plt.Figure:
    """Draw a PFD for a single-effect PreEvaporator."""
    SC = '#c0392b'
    VC = '#d35400'
    JC = '#154360'
    CC = '#7f8c8d'
    BC = '#1e8449'
    BOX_EC = '#2471a3'
    BOX_FC = '#d6eaf8'

    DW    = 12.0
    DH    = 11.8
    cx    = DW / 2
    BOX_W = 3.8

    Y_TTL   = DH - 0.25
    Y_ROUTE = DH - 1.70
    Y_TOP   = 8.10
    Y_BOT   = 2.70
    Y_MID   = (Y_TOP + Y_BOT) / 2
    Y_COND  = 1.45
    Y_FOOT  = 0.40

    x_lft = 1.0
    x_rgt = DW - 1.0

    fig, ax = plt.subplots(figsize=(10.0, 9.5))
    ax.set_xlim(0, DW)
    ax.set_ylim(0.2, DH)
    ax.axis('off')
    fig.patch.set_facecolor('#f8f9fa')

    def arr(x1, y1, x2, y2, color, lw=1.8, ls='solid'):
        ann = ax.annotate(
            '', xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                            linestyle=ls, shrinkA=0, shrinkB=0),
            clip_on=False,
        )
        ann.arrow_patch.set_zorder(5)

    def seg(x1, y1, x2, y2, color, lw=1.8, ls='solid'):
        ax.plot([x1, x2], [y1, y2], color=color, lw=lw, ls=ls, zorder=4, clip_on=False)

    def lbl(x, y, text, ha='center', va='center', fs=8.5, color='black', bold=False):
        ax.text(x, y, text, ha=ha, va=va, fontsize=fs,
                color=color, fontweight='bold' if bold else 'normal',
                clip_on=False, zorder=6)

    # Title
    lbl(DW / 2, Y_TTL, pre_name, fs=14, bold=True, color='#1c2833')

    # Body
    rect = mpatches.FancyBboxPatch(
        (cx - BOX_W / 2, Y_BOT), BOX_W, Y_TOP - Y_BOT,
        boxstyle='round,pad=0.06', lw=2.0,
        edgecolor=BOX_EC, facecolor=BOX_FC, zorder=3)
    ax.add_patch(rect)

    # Labels inside body
    lbl(cx, Y_MID + 1.95, 'Pre Evaporator',             fs=11, bold=True, color='#1a3a5c')
    lbl(cx, Y_MID + 1.32, f'{pre.area_ft2:,.0f} ft²',   fs=9,  color='#566573')
    lbl(cx, Y_MID + 0.70, f'P: {pre.vapor_pressure_psia:.2f} psia', fs=8.5, color='#1a5276')
    lbl(cx, Y_MID + 0.30, _fmt_p2(pre.vapor_pressure_psia),          fs=8,   color='#1a5276')
    lbl(cx, Y_MID - 0.15, f'Cald: {pre.supply_steam.sat_temp_deg_F:.1f} °F', fs=8, color=SC)
    lbl(cx, Y_MID - 0.55, f'Juice: {pre.liquid_temp_deg_F:.1f} °F',          fs=8, color=JC)
    lbl(cx, Y_MID - 1.28, f'Ud = {pre.dessin_U:.1f}  BTU/hr·ft²·°F',        fs=7.5, color='#555555')
    lbl(cx, Y_MID - 1.68, f'hfg stm: {pre.supply_steam.h_fg:.1f} BTU/lb',   fs=7,   color='#922b21')

    # Supply steam (enters left side)
    arr(x_lft, Y_MID, cx - BOX_W / 2, Y_MID, color=SC, lw=2.2)
    lbl(x_lft, Y_MID + 0.68, 'Supply Steam',                                    ha='left', fs=9,   color=SC, bold=True)
    lbl(x_lft, Y_MID + 0.28, f'{pre.exhaust_required_lb_per_hr:,.0f} lb/hr',   ha='left', fs=8.5, color=SC)
    lbl(x_lft, Y_MID - 0.10, f'{pre.supply_steam.P_psia:.1f} psia',            ha='left', fs=7.5, color=SC)
    lbl(x_lft, Y_MID - 0.44, _fmt_p2(pre.supply_steam.P_psia),                 ha='left', fs=7.5, color=SC)

    # Condensate exits bottom of body
    arr(cx, Y_BOT, cx, Y_COND + 0.12, color=CC, lw=1.5)
    lbl(cx, Y_COND - 0.10,
        f'Condensate\n{pre.exhaust_required_lb_per_hr:,.0f} lb/hr', fs=7.5, color=CC)

    # V1 vapor bleed exits top, routes right (dashed — to V1 header)
    bx = cx - BOX_W * 0.10
    seg(bx, Y_TOP, bx, Y_ROUTE, color=BC, lw=1.8)
    arr(bx, Y_ROUTE, x_rgt, Y_ROUTE, color=BC, lw=1.8, ls='dashed')
    lbl(x_rgt, Y_ROUTE + 0.52, 'V1 Vapor Bleed',                            ha='right', fs=9,   color=BC, bold=True)
    lbl(x_rgt, Y_ROUTE + 0.14, f'{pre.vapor_bleed_lb_per_hr:,.0f} lb/hr',   ha='right', fs=8.5, color=BC)
    lbl(x_rgt, Y_ROUTE - 0.22,
        f'{pre.vapor_pressure_psia:.2f} psia  |  {pre.vapor_temp_deg_F:.1f} °F',
        ha='right', fs=7.5, color=BC)

    # Juice In (bottom left)
    arr(x_lft, Y_BOT, cx - BOX_W / 2, Y_BOT, color=JC, lw=2.2)
    lbl(x_lft, Y_BOT + 0.62, 'Juice In',                                             ha='left', fs=9,   color=JC, bold=True)
    lbl(x_lft, Y_BOT + 0.22, f'{pre.juice_in.flow_lb_per_hr:,.0f} lb/hr',           ha='left', fs=8.5, color=JC)
    lbl(x_lft, Y_BOT - 0.17,
        f'{pre.juice_in.brix:.2f}° Brix  |  {pre.juice_in.temp_deg_F:.1f} °F',
        ha='left', fs=7.5, color=JC)

    # Juice Out (bottom right)
    arr(cx + BOX_W / 2, Y_BOT, x_rgt, Y_BOT, color=JC, lw=2.2)
    lbl(x_rgt, Y_BOT + 0.62, 'Juice Out',                                            ha='right', fs=9,   color=JC, bold=True)
    lbl(x_rgt, Y_BOT + 0.22, f'{pre.juice_out.flow_lb_per_hr:,.0f} lb/hr',          ha='right', fs=8.5, color=JC)
    lbl(x_rgt, Y_BOT - 0.17,
        f'{pre.juice_out.brix:.2f}° Brix  |  {pre.juice_out.temp_deg_F:.1f} °F',
        ha='right', fs=7.5, color=JC)

    # Footer
    lbl(DW / 2, Y_FOOT,
        f'Heat Duty: {pre.heat_duty_btu_per_hr:,.0f} BTU/hr   |   '
        f'U dessin: {pre.dessin_U:.1f} BTU/hr·ft²·°F   |   '
        f'Area: {pre.area_ft2:,.0f} ft²',
        fs=8, color='#666666')

    fig.tight_layout(pad=0.4)
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
    if show:
        plt.show()
    return fig


def plot_all_diagrams(
    evap_sets: list,
    online: list,
    set_names: list = None,
    show: bool = True,
    save_prefix: str = None,
) -> list:
    """
    Plot one process flow diagram per active EvaporatorSet.
    Returns list of Figure objects (one per active set).
    """
    figs = []
    for i, (evap_set, on) in enumerate(zip(evap_sets, online)):
        if not on:
            continue
        name = set_names[i] if (set_names and i < len(set_names)) else f'Set {i + 1}'
        path = f'{save_prefix}_set{i + 1}.png' if save_prefix else None
        figs.append(plot_set_diagram(evap_set, set_name=name, show=show, save_path=path))
    return figs
