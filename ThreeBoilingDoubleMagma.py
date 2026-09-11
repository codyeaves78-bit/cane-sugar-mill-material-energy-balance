from Pan import Pan
from Centrifugal import Centrifugal
from Crystallizer_and_Reheater import Crystallizer, Reheater
from SugarStream import SugarStream
from condensate_utils import flash_condensate


def make_magma(sugar_stream: SugarStream, mingler_brix: float) -> SugarStream:
    magma = SugarStream.copy(sugar_stream)
    solids = magma.solids_flow
    magma.brix = mingler_brix
    magma.flow_lb_per_hr = solids / magma.brix * 100
    return magma # helper function

def make_remelt(magma=SugarStream(), remelt_brix=65):
    remelt = SugarStream.copy(magma)
    brix_flow = magma.solids_flow
    new_flow = brix_flow * 100 / remelt_brix
    new_brix = brix_flow / new_flow * 100
    remelt.flow_lb_per_hr = new_flow
    remelt.brix = new_brix
    return remelt


def dilute_molasses(mol: SugarStream, diluted_brix: float) -> SugarStream:
    """Dilute molasses to target brix by adding water. Solids are conserved."""
    diluted = SugarStream.copy(mol)
    diluted.brix = diluted_brix
    diluted.flow_lb_per_hr = mol.solids_flow / (diluted_brix / 100)
    return diluted

class ThreeBoilingDoubleMagma:
    """An object to do the Three Boiling Double Magma Balance
    When inputting the Pan and Centrifugal Object, user does not need to define inlet streams"""
    def __init__(
            self,
            syrup: SugarStream,
            A_pans: Pan,
            B_pans: Pan,
            C_pans: Pan,
            grain_pans: Pan,
            A_centrifugals: Centrifugal,
            B_centrifugals: Centrifugal,
            C_centrifugals: Centrifugal,
            C_crystallizers: Crystallizer = None,
            C_reheaters: Reheater = None,
            c_magma_remelt_pct: float = 20,
            b_magma_remelt_pct: float = 20,
            syrup_to_grain_pct: float = 5,
            a_mol_to_grain_pct: float = 5,
            b_mol_to_grain_pct: float = 10,
            a_mol_top_off_pct: float = 30,
            a_mol_dilution_brix: float = 70,
            b_mol_top_off_pct: float = 0,
            b_mol_dilution_brix: float = 70,
            b_magma_brix: float = 92,
            c_mol_top_off_pct: float = 0,
            c_mol_top_off_brix: float = 70,
            c_magma_brix: float = 92,
            b_remelt_brix: float = 65,
            c_remelt_brix: float = 65,
            injection_water_temp_F: float = 90,
            condenser_leg_temp_drop_F: float = 5,
            iterations: int = 20,
            ):

        self.syrup = syrup
        self.injection_water_temp_F = injection_water_temp_F
        self.condensor_leg_temp_drop_F = condenser_leg_temp_drop_F # degrees below the vapor temp
        # Store Pan/Centrifugal configs as templates; solved instances assigned in _solve()
        self._A_pans_cfg = A_pans
        self._B_pans_cfg = B_pans
        self._C_pans_cfg = C_pans
        self._grain_pans_cfg = grain_pans
        self._A_cen_cfg = A_centrifugals
        self._B_cen_cfg = B_centrifugals
        self._C_cen_cfg = C_centrifugals
        # Default: cool to 120°F / reheat to 130°F with no exhaustion (ml purity carried)
        self._C_crys_cfg = (C_crystallizers if C_crystallizers is not None
                            else Crystallizer(massecuite_in=None, massecuite_flow_lb_hr=0,
                                              name='C Crystallizers'))
        self._C_reheat_cfg = (C_reheaters if C_reheaters is not None
                              else Reheater(massecuite_in=None, massecuite_flow_lb_hr=0,
                                            name='C Reheaters'))

        self.c_magma_remelt_pct = c_magma_remelt_pct
        self.b_magma_remelt_pct = b_magma_remelt_pct
        self.syrup_to_grain_pct = syrup_to_grain_pct
        self.a_mol_to_grain_pct = a_mol_to_grain_pct
        self.b_mol_to_grain_pct = b_mol_to_grain_pct
        self.a_mol_top_off_pct = a_mol_top_off_pct
        self.b_mol_top_off_pct = b_mol_top_off_pct
        self.c_mol_top_off_pct = c_mol_top_off_pct
        self.a_mol_B_pans_pct = 100.0 - a_mol_top_off_pct - a_mol_to_grain_pct
        self.b_mol_C_pans_pct = 100.0 - b_mol_to_grain_pct - b_mol_top_off_pct
        self.a_mol_dilution_brix = a_mol_dilution_brix
        self.b_mol_dilution_brix = b_mol_dilution_brix
        self.c_mol_top_off_brix = c_mol_top_off_brix
        self.b_magma_brix = b_magma_brix
        self.c_magma_brix = c_magma_brix
        self.b_remelt_brix = b_remelt_brix
        self.c_remelt_brix = c_remelt_brix
        self.syrup_to_A_pans_pct = 100.0 - syrup_to_grain_pct

        self._solve(iterations)

    def _rebuild_pan(self, config: Pan, feed_streams: list) -> Pan:
        return Pan(
            feed_streams=feed_streams,
            heating_surface_ft2=config.heating_surface_ft2,
            inches_vacuum=config.inches_vacuum,
            supersaturation=config.supersaturation,
            head_ft=config.head_ft,
            masse_brix=config.masse_brix,
            ml_purity=config.ml_purity,
            calandria_pressure_psia=config.calandria_pressure_psia,
            heat_loss_factor=config.heat_loss_factor,
            name=config.name,
            steam_type=config.steam_type,
        )

    def _rebuild_centrifugal(self, config: Centrifugal, massecuite, massecuite_flow_lb_hr: float) -> Centrifugal:
        return Centrifugal(
            massecuite=massecuite,
            massecuite_flow_lb_hr=massecuite_flow_lb_hr,
            target_molasses_brix=config.target_molasses_brix,
            purity_rise=config.purity_rise,
            sugar_purity=config.sugar_purity,
            sugar_moisture=config.sugar_moisture,
            name=config.name,
            sugar_temp=config.sugar_temp,
            molasses_temp=config.molasses_temp,
        )

    def _rebuild_crystallizer(self, config: Crystallizer, massecuite_in, massecuite_flow_lb_hr: float) -> Crystallizer:
        return Crystallizer(
            massecuite_in=massecuite_in,
            massecuite_flow_lb_hr=massecuite_flow_lb_hr,
            masse_temp_out_deg_F=config.masse_temp_out_deg_F,
            ml_purity_out=config.ml_purity_out,
            water_temp_in_deg_F=config.water_temp_in_deg_F,
            water_temp_out_deg_F=config.water_temp_out_deg_F,
            name=config.name,
        )

    def _rebuild_reheater(self, config: Reheater, massecuite_in, massecuite_flow_lb_hr: float) -> Reheater:
        return Reheater(
            massecuite_in=massecuite_in,
            massecuite_flow_lb_hr=massecuite_flow_lb_hr,
            masse_temp_out_deg_F=config.masse_temp_out_deg_F,
            ml_purity_out=config.ml_purity_out,
            water_temp_in_deg_F=config.water_temp_in_deg_F,
            water_temp_out_deg_F=config.water_temp_out_deg_F,
            name=config.name,
        )

    def _solve(self, iterations: int = 20):
        # Dummy initial magma footings — zero flow so they don't distort the first A/B pan solve.
        # Both are overwritten each iteration: c_magma_B_pans from C centrifugals sugar stream,
        # b_magma_A_pans from B centrifugals sugar stream (via make_magma). Brix/purity/temp
        # are placeholders only; the loop replaces them before they matter.
        c_magma_B_pans = SugarStream(brix=self.c_magma_brix, purity=85, flow_lb_per_hr=0, temp_deg_F=130)
        b_magma_A_pans = SugarStream(brix=self.b_magma_brix, purity=92, flow_lb_per_hr=0, temp_deg_F=130)

        syrup_as_fed = SugarStream.copy(self.syrup)

        syrup_to_A_pans = SugarStream.copy(self.syrup)
        syrup_to_A_pans.flow_lb_per_hr = self.syrup_to_A_pans_pct / 100 * self.syrup.flow_lb_per_hr

        # Dummy top-off A molasses — zero flow for the first A pan solve.
        # Overwritten each iteration from A centrifugals molasses_stream.
        # NOTE: molasses_stream.temp_deg_F is fixed to _A_cen_cfg.molasses_temp (not computed
        # from the centrifugal thermodynamics), so temperature is constant across iterations.
        top_off_a_mol = SugarStream(brix=70, purity=70, flow_lb_per_hr=0, temp_deg_F=140)
        top_off_b_mol = SugarStream(brix=70, purity=55, flow_lb_per_hr=0, temp_deg_F=140)
        top_off_c_mol = SugarStream(brix=80, purity=35, flow_lb_per_hr=0, temp_deg_F=140)

        for _ in range(iterations):
            self.A_pans = self._rebuild_pan(
                self._A_pans_cfg, [syrup_to_A_pans, b_magma_A_pans, top_off_a_mol]
            )
            self.A_centrifugals = self._rebuild_centrifugal(
                self._A_cen_cfg, self.A_pans.massecuite, self.A_pans.massecuite_flow_lb_hr
            )

            a_mol_diluted = dilute_molasses(self.A_centrifugals.molasses_stream, self.a_mol_dilution_brix)

            top_off_a_mol = SugarStream.copy(a_mol_diluted)
            top_off_a_mol.flow_lb_per_hr = self.a_mol_top_off_pct / 100 * top_off_a_mol.flow_lb_per_hr

            a_mol_B_pans = SugarStream.copy(a_mol_diluted)
            a_mol_B_pans.flow_lb_per_hr = self.a_mol_B_pans_pct / 100 * a_mol_B_pans.flow_lb_per_hr

            self.B_pans = self._rebuild_pan(
                self._B_pans_cfg, [c_magma_B_pans, a_mol_B_pans, top_off_b_mol]
            )
            self.B_centrifugals = self._rebuild_centrifugal(
                self._B_cen_cfg, self.B_pans.massecuite, self.B_pans.massecuite_flow_lb_hr
            )

            b_mol_diluted = dilute_molasses(self.B_centrifugals.molasses_stream, self.b_mol_dilution_brix)

            top_off_b_mol = SugarStream.copy(b_mol_diluted)
            top_off_b_mol.flow_lb_per_hr = self.b_mol_top_off_pct / 100 * top_off_b_mol.flow_lb_per_hr

            b_mol_grain = SugarStream.copy(b_mol_diluted)
            b_mol_grain.flow_lb_per_hr = self.b_mol_to_grain_pct / 100 * b_mol_grain.flow_lb_per_hr

            a_mol_grain = SugarStream.copy(a_mol_diluted)
            a_mol_grain.flow_lb_per_hr = self.a_mol_to_grain_pct / 100 * a_mol_grain.flow_lb_per_hr

            syrup_to_grain = SugarStream.copy(syrup_as_fed)
            syrup_to_grain.flow_lb_per_hr = self.syrup_to_grain_pct / 100 * syrup_as_fed.flow_lb_per_hr

            self.grain_pans = self._rebuild_pan(
                self._grain_pans_cfg, [syrup_to_grain, a_mol_grain, b_mol_grain]
            )

            grain_massecuite = SugarStream(
                brix=self.grain_pans.masse_brix,
                purity=self.grain_pans.masse_purity,
                flow_lb_per_hr=self.grain_pans.massecuite_flow_lb_hr,
                temp_deg_F=self.grain_pans.massecuite.massecuite_temp,
                pressure_psia=14.7,
                level_ft=0,
            )

            b_mol_C_pans = SugarStream.copy(b_mol_diluted)
            b_mol_C_pans.flow_lb_per_hr = self.b_mol_C_pans_pct / 100 * b_mol_C_pans.flow_lb_per_hr

            self.C_pans = self._rebuild_pan(
                self._C_pans_cfg, [grain_massecuite, b_mol_C_pans, top_off_c_mol]
            )

            # C massecuite: cooling crystallizer → reheater → centrifugals.
            # Mass flow is conserved (non-contact water); the crystallizer's ml purity
            # drop carries into the centrifugal and lowers final molasses purity.
            self.C_crystallizers = self._rebuild_crystallizer(
                self._C_crys_cfg, self.C_pans.massecuite, self.C_pans.massecuite_flow_lb_hr
            )
            self.C_reheaters = self._rebuild_reheater(
                self._C_reheat_cfg, self.C_crystallizers.massecuite_out,
                self.C_pans.massecuite_flow_lb_hr
            )
            self.C_centrifugals = self._rebuild_centrifugal(
                self._C_cen_cfg, self.C_reheaters.massecuite_out, self.C_pans.massecuite_flow_lb_hr
            )

            top_off_c_mol_non_dilute = self.C_centrifugals.molasses_stream
            top_off_c_mol_non_dilute.flow_lb_per_hr = self.C_centrifugals.molasses_stream.flow_lb_per_hr * self.c_mol_top_off_pct / 100
            top_off_c_mol = dilute_molasses(top_off_c_mol_non_dilute, self.c_mol_top_off_brix)

            final_molasses_out = self.C_centrifugals.molasses_stream
            final_molasses_out.flow_lb_per_hr = self.C_centrifugals.molasses_stream.flow_lb_per_hr - top_off_c_mol_non_dilute.flow_lb_per_hr
            

            b_magma = make_magma(self.B_centrifugals.sugar_stream, mingler_brix=self.b_magma_brix)
            c_magma = make_magma(self.C_centrifugals.sugar_stream, mingler_brix=self.c_magma_brix)

            b_magma_A_pans = SugarStream.copy(b_magma)
            b_magma_A_pans.flow_lb_per_hr = (100 - self.b_magma_remelt_pct) / 100 * b_magma_A_pans.flow_lb_per_hr

            c_magma_B_pans = SugarStream.copy(c_magma)
            c_magma_B_pans.flow_lb_per_hr = (100 - self.c_magma_remelt_pct) / 100 * c_magma_B_pans.flow_lb_per_hr

            b_magma_to_rmlt = SugarStream.copy(b_magma)
            b_magma_to_rmlt.flow_lb_per_hr = self.b_magma_remelt_pct / 100 * b_magma_to_rmlt.flow_lb_per_hr
            b_remelt = make_remelt(b_magma_to_rmlt, remelt_brix=self.b_remelt_brix)

            c_magma_to_rmlt = SugarStream.copy(c_magma)
            c_magma_to_rmlt.flow_lb_per_hr = self.c_magma_remelt_pct / 100 * c_magma_to_rmlt.flow_lb_per_hr
            c_remelt = make_remelt(c_magma_to_rmlt, remelt_brix=self.c_remelt_brix)

            total_flows = self.syrup.flow_lb_per_hr + c_remelt.flow_lb_per_hr + b_remelt.flow_lb_per_hr
            total_solids = self.syrup.solids_flow + c_remelt.solids_flow + b_remelt.solids_flow
            total_pols = self.syrup.pol_flow + b_remelt.pol_flow + c_remelt.pol_flow

            syrup_as_fed = SugarStream.copy(self.syrup)
            syrup_as_fed.flow_lb_per_hr = total_flows
            syrup_as_fed.brix = total_solids / total_flows * 100
            syrup_as_fed.purity = total_pols / total_solids * 100

            syrup_to_A_pans = SugarStream.copy(syrup_as_fed)
            syrup_to_A_pans.flow_lb_per_hr = self.syrup_to_A_pans_pct / 100 * syrup_to_A_pans.flow_lb_per_hr

        self.syrup_as_fed = syrup_as_fed

        # Save final-iteration magma/remelt/dilution streams for water accounting
        self._b_magma          = b_magma
        self._c_magma          = c_magma
        self._b_magma_A_pans   = b_magma_A_pans
        self._c_magma_B_pans   = c_magma_B_pans
        self._b_magma_to_rmlt  = b_magma_to_rmlt
        self._c_magma_to_rmlt  = c_magma_to_rmlt
        self._b_remelt         = b_remelt
        self._c_remelt         = c_remelt
        self._a_mol_diluted    = a_mol_diluted
        self._b_mol_diluted    = b_mol_diluted
        self._final_molasses_out = final_molasses_out
        self._c_mol_top_off_non_dilute = top_off_c_mol_non_dilute
        self._c_mol_top_off = top_off_c_mol

    @property
    def pan_condensers(self):
        """Each pan's vapor goes to its own barometric condenser: [(name, Condenser)]."""
        from Condenser import Condenser
        return [
            (pan.name, Condenser(pan.vapor_evaporated, self.injection_water_temp_F, self.condensor_leg_temp_drop_F))
            for pan in (self.A_pans, self.B_pans, self.grain_pans, self.C_pans)
        ]

    @property
    def _pans(self):
        return (self.A_pans, self.B_pans, self.grain_pans, self.C_pans)

    def _steam_demand_lb_hr(self, steam_type: int) -> float:
        return sum(pan.steam_flow_lb_hr for pan in self._pans if pan.steam_type == steam_type)

    @property
    def total_raw_sugar(self) -> SugarStream:
        """Object of combined Sugars leaving process, in this case, just A sugar"""
        return SugarStream.copy(self.A_centrifugals.sugar_stream)

    @property
    def total_exhaust_steam_lb_hr(self) -> float:
        """Total live/exhaust steam consumed by pans on steam_type 0 (lb/hr)."""
        return self._steam_demand_lb_hr(0)

    @property
    def total_V1_steam_lb_hr(self) -> float:
        """Total V1 vapor consumed by pans on steam_type 1 (lb/hr)."""
        return self._steam_demand_lb_hr(1)

    @property
    def total_V2_steam_lb_hr(self) -> float:
        """Total V2 vapor consumed by pans on steam_type 2 (lb/hr)."""
        return self._steam_demand_lb_hr(2)

    @property
    def total_V3_steam_lb_hr(self) -> float:
        """Total V3 vapor consumed by pans on steam_type 3 (lb/hr)."""
        return self._steam_demand_lb_hr(3)

    @property
    def total_V4_steam_lb_hr(self) -> float:
        """Total V4 vapor consumed by pans on steam_type 4 (lb/hr)."""
        return self._steam_demand_lb_hr(4)

    @property
    def clean_condensate(self) -> float:
        """Post-flash condensate from pans on exhaust steam (steam_type 0) (lb/hr)."""
        return sum(flash_condensate(pan.steam_flow_lb_hr, pan.calandria_T_sat_F)
                   for pan in self._pans if pan.steam_type == 0)

    @property
    def dirty_condensate(self) -> float:
        """Post-flash condensate from pans on vapor bleed steam (steam_type 1-4) (lb/hr)."""
        return sum(flash_condensate(pan.steam_flow_lb_hr, pan.calandria_T_sat_F)
                   for pan in self._pans if pan.steam_type != 0)

    @property
    def total_water(self) -> SugarStream:
        """All fresh water added to the pan floor (lb/hr): centrifugal wash + magma minglers + remelts."""
        cen_wash     = (self.A_centrifugals.wash_water_lb_hr
                      + self.B_centrifugals.wash_water_lb_hr
                      + self.C_centrifugals.wash_water_lb_hr)
        b_mingler    = self._b_magma.flow_lb_per_hr    - self.B_centrifugals.sugar_stream.flow_lb_per_hr
        c_mingler    = self._c_magma.flow_lb_per_hr    - self.C_centrifugals.sugar_stream.flow_lb_per_hr
        b_rmlt_water = self._b_remelt.flow_lb_per_hr   - self._b_magma_to_rmlt.flow_lb_per_hr
        c_rmlt_water = self._c_remelt.flow_lb_per_hr   - self._c_magma_to_rmlt.flow_lb_per_hr
        a_dil_water  = self._a_mol_diluted.flow_lb_per_hr - self.A_centrifugals.molasses_stream.flow_lb_per_hr
        b_dil_water  = self._b_mol_diluted.flow_lb_per_hr - self.B_centrifugals.molasses_stream.flow_lb_per_hr
        c_top_off_dil_water = self._c_mol_top_off.flow_lb_per_hr - self._c_mol_top_off_non_dilute.flow_lb_per_hr
        total_lb_hr  = (cen_wash + b_mingler + c_mingler + b_rmlt_water + c_rmlt_water
                        + a_dil_water + b_dil_water + c_top_off_dil_water)
        return SugarStream(brix=0, purity=0, flow_lb_per_hr=total_lb_hr)

    def generate_pfd(self, show=True, save_path=None, include_table=True):
        """Generate a process flow diagram with a stream table. Returns the Figure."""
        from three_boiling_diagram import plot_three_boiling
        return plot_three_boiling(self, show=show, save_path=save_path,
                                  include_table=include_table)

    def to_excel(self, workbook):
        """Write the full floor balance to its own styled sheet: the PFD
        (diagram only), the numbered stream table, the water streams not
        drawn, the overall balance, and every station from neat_display."""
        import matplotlib.pyplot as plt
        from excel_export import SheetWriter
        from three_boiling_diagram import _collect_streams, _collect_water
        from pan_floor_excel import (HDRS, FMTS, srow, wrow, totals_rows,
                                     pan_table, cen_table, dil_table, heatx_table,
                                     condenser_table, magma_table, magma_split_table,
                                     remelt_table, syrup_recombination_table)

        a_sugar = self.A_centrifugals.sugar_stream
        c_mol   = self._final_molasses_out
        total_evap = (self.A_pans.water_evaporated_lb_hr + self.B_pans.water_evaporated_lb_hr
                      + self.grain_pans.water_evaporated_lb_hr + self.C_pans.water_evaporated_lb_hr)
        pol_extr = a_sugar.pol_flow / self.syrup.pol_flow * 100

        sw = SheetWriter(workbook, "Pan Floor - Three Boiling", ncols=9)
        sw.title("Three Boiling Double Magma — Pan Floor",
                 f"Syrup {self.syrup.flow_lb_per_hr:,.0f} lb/hr @ {self.syrup.brix:.1f} Bx "
                 f"| Pol recovered in raw sugar = {pol_extr:.2f}%")

        sw.section("PROCESS FLOW DIAGRAM")
        sw.blank()
        fig = self.generate_pfd(show=False, include_table=False)
        sw.image(fig, width_in=10.00)
        plt.close(fig)

        sw.page_break()
        sw.section("STREAM TABLE  (tags match the diagram)")
        sw.table(["#", "Stream", "Flow (lb/hr)", "Brix %", "Purity %"],
                 _collect_streams(self),
                 fmts=["0", "@", "#,##0", "0.0", "0.0"])

        sw.page_break()
        sw.section("STREAMS NOT SHOWN — WATER")
        wleft, wright, (total_in, total_evap_chk) = _collect_water(self)
        sw.table(["Stream", "Flow (lb/hr)"], wleft + wright, fmts=["@", "#,##0"],
                 totals=[("Total Fresh Water In (wash + mingler + remelt + dilution)", total_in),
                         ("Total Water Evaporated (all pans)", total_evap_chk)])

        sw.section("OVERALL FLOOR BALANCE")
        tw = self.total_water
        in_f  = self.syrup.flow_lb_per_hr + tw.flow_lb_per_hr
        in_s  = self.syrup.solids_flow
        in_p  = self.syrup.pol_flow
        out_f = a_sugar.flow_lb_per_hr + c_mol.flow_lb_per_hr + total_evap
        out_s = a_sugar.solids_flow + c_mol.solids_flow
        out_p = a_sugar.pol_flow + c_mol.pol_flow
        sw.table(HDRS, [
            srow("Syrup From Evaporators", "In", self.syrup),
            wrow("Wash and Dilution Water", "In", tw.flow_lb_per_hr),
            srow("A Product Sugar", "Out", a_sugar),
            srow("C Final Molasses", "Out", c_mol),
            wrow("Evaporated (all pans)", "Out", total_evap),
        ], fmts=FMTS, totals=totals_rows(in_f, in_s, in_p, in_f - in_s,
                                         out_f, out_s, out_p, out_f - out_s))
        sw.row("Pol % recovered in raw sugar (A sugar / feed)", pol_extr, "%", col=4)

        sw.section("PAN FLOOR SYRUP  (Evaporator Syrup + Remelt)")
        syrup_recombination_table(sw, self.syrup,
                                  [("B", self._b_remelt), ("C", self._c_remelt)],
                                  self.syrup_as_fed)

        # ── Stations ───────────────────────────────────────────────────────
        sw.page_break()
        sw.section(f"A PANS  [{self.A_pans.name}]")
        pan_table(sw, self.A_pans, ["Syrup", "B Magma", "A Molasses Top-off"])
        sw.section(f"A CENTRIFUGALS  [{self.A_centrifugals.name}]")
        cen_table(sw, self.A_centrifugals)
        sw.section(f"A MOLASSES DILUTION  (target {self.a_mol_dilution_brix:.1f} Bx)")
        dil_table(sw, self.A_centrifugals.molasses_stream, self._a_mol_diluted, "A Molasses")

        sw.section(f"B PANS  [{self.B_pans.name}]")
        pan_table(sw, self.B_pans, ["C Magma", "A Molasses", "B Molasses Top-off"])
        sw.section(f"B CENTRIFUGALS  [{self.B_centrifugals.name}]")
        cen_table(sw, self.B_centrifugals)
        sw.section(f"B MAGMA  (mingler target {self.b_magma_brix:.1f} Bx)")
        magma_table(sw, self.B_centrifugals.sugar_stream, self._b_magma, "B")
        sw.section("B MAGMA DISTRIBUTION")
        magma_split_table(sw, self._b_magma, [
            ("B Magma to A Footing", self._b_magma_A_pans),
            ("B Magma to Remelt",    self._b_magma_to_rmlt),
        ])
        sw.section(f"B REMELT  (target {self.b_remelt_brix:.1f} Bx)")
        remelt_table(sw, self._b_magma_to_rmlt, self._b_remelt, "B", self.b_remelt_brix)
        sw.section(f"B MOLASSES DILUTION  (target {self.b_mol_dilution_brix:.1f} Bx)")
        dil_table(sw, self.B_centrifugals.molasses_stream, self._b_mol_diluted, "B Molasses")

        sw.page_break()
        sw.section(f"GRAIN PANS  [{self.grain_pans.name}]")
        pan_table(sw, self.grain_pans, ["Syrup", "A Molasses", "B Molasses"])

        sw.section(f"C PANS  [{self.C_pans.name}]")
        pan_table(sw, self.C_pans, ["Grain Massecuite", "B Molasses", "C Molasses Top-off"])
        sw.section(f"C MOLASSES TOP-OFF DILUTION  (target {self.c_mol_top_off_brix:.1f} Bx)")
        dil_table(sw, self._c_mol_top_off_non_dilute, self._c_mol_top_off, "C Molasses Top-off")
        sw.section(f"C CRYSTALLIZERS  [{self.C_crystallizers.name}]")
        heatx_table(sw, self.C_crystallizers, "Cooling Water")
        sw.section(f"C REHEATERS  [{self.C_reheaters.name}]")
        heatx_table(sw, self.C_reheaters, "Hot Water")
        sw.section(f"C CENTRIFUGALS  [{self.C_centrifugals.name}]")
        cen_table(sw, self.C_centrifugals)

        sw.section(f"C MAGMA  (mingler target {self.c_magma_brix:.1f} Bx)")
        magma_table(sw, self.C_centrifugals.sugar_stream, self._c_magma, "C")
        sw.section("C MAGMA DISTRIBUTION")
        magma_split_table(sw, self._c_magma, [
            ("C Magma to B Footing", self._c_magma_B_pans),
            ("C Magma to Remelt",    self._c_magma_to_rmlt),
        ])
        sw.section(f"C REMELT  (target {self.c_remelt_brix:.1f} Bx)")
        remelt_table(sw, self._c_magma_to_rmlt, self._c_remelt, "C", self.c_remelt_brix)

        sw.section("PAN VAPOR CONDENSERS  (one per pan)")
        condenser_table(sw, self.pan_condensers, self.injection_water_temp_F)
        cooling_note_row = sw.r
        sw.row("Note: if using CoolingTowerSystem, ignore these injection water "
               "demands - they are re-solved there at the delivered water temp.", "")

        sw.section("CONDENSATE RETURN")
        sw.row("Clean condensate (Exhaust steam pans)",  self.clean_condensate, "lb/hr", fmt="#,##0")
        sw.row("Dirty condensate (V1-V4 steam pans)",    self.dirty_condensate, "lb/hr", fmt="#,##0")
        sw.row("Total condensate", self.clean_condensate + self.dirty_condensate, "lb/hr", fmt="#,##0")

        ws = sw.finish()
        col_widths_px = {'A': 164, 'B': 142, 'C': 93, 'D': 78, 'E': 109,
                         'F': 98, 'G': 96, 'H': 87, 'I': 98}
        for letter, px in col_widths_px.items():
            ws.column_dimensions[letter].width = (px - 5) / 7
        from openpyxl.styles import Alignment
        ws.cell(row=cooling_note_row, column=1).alignment = Alignment(
            horizontal='left', vertical='center', wrap_text=True)
        return ws

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def neat_display(self):
        W = 115
        HEAVY = "=" * W
        LIGHT = "-" * W

        LBL = 32   # label column width
        NUM = 13   # numeric column width
        VOL = 10   # ft³/hr column width
        PCT = 8    # brix/purity/crystal content column width

        def _row(label, flow, solids, pol, water, brix=None, purity=None, vol_ft3_hr=None):
            b = f"{brix:6.1f}" if brix is not None else "     -"
            p = f"{purity:6.1f}" if purity is not None else "     -"
            v = f"{vol_ft3_hr:{VOL},.0f}" if vol_ft3_hr is not None else " " * (VOL - 1) + "-"
            return (f"  {label:<{LBL}} {flow:{NUM},.0f} {solids:{NUM},.0f}"
                    f" {pol:{NUM},.0f} {water:{NUM},.0f} {b} {p} {v}")

        def _hdr():
            return (f"  {'Stream':<{LBL}} {'Flow (lb/hr)':{NUM}} {'Solids (lb/hr)':{NUM}}"
                    f" {'Pol (lb/hr)':{NUM}} {'Water (lb/hr)':{NUM}} {'Brix%':>6} {'Pur%':>6} {'ft3/hr':>{VOL}}")

        def _stream(label, s):
            sol = s.solids_flow
            return _row(label, s.flow_lb_per_hr, sol, s.pol_flow,
                        s.flow_lb_per_hr - sol, s.brix, s.purity, vol_ft3_hr=s.cu_ft_hr)

        def _section(title):
            return f"\n{LIGHT}\n  {title}\n{LIGHT}"

        def _pan_station(pan):
            lines = []
            lines.append("  ENTERING")
            for i, f in enumerate(pan.feed_streams, 1):
                sol = f.solids_flow
                lines.append(_row(f"    Feed {i}  (Bx={f.brix:.1f} Pu={f.purity:.1f})",
                                  f.flow_lb_per_hr, sol, f.pol_flow,
                                  f.flow_lb_per_hr - sol, f.brix, f.purity, vol_ft3_hr=f.cu_ft_hr))
            ff = pan.feed_flow_lb_hr
            fs = pan.feed_solids_lb_hr
            fp = sum(f.pol_flow for f in pan.feed_streams)
            lines.append(LIGHT)
            lines.append(_row("  Total Feed In", ff, fs, fp, ff - fs))
            lines.append("")
            lines.append("  LEAVING")
            masse_sol = fs          # solids conserved through evaporation
            masse_pol = fp          # pol conserved through evaporation
            masse_water = pan.massecuite_flow_lb_hr - masse_sol
            masse_vol = pan.massecuite_flow_lb_hr / pan.massecuite.density
            lines.append(_row("  Massecuite Out", pan.massecuite_flow_lb_hr,
                               masse_sol, masse_pol, masse_water,
                               pan.masse_brix, pan.masse_purity, vol_ft3_hr=masse_vol))
            lines.append(f"  {'Predicted ML Purity (Birkett):':<{LBL}} {pan.predicted_ml_purity:6.1f} %"
                         f"   (input ml_purity: {pan.ml_purity:.1f} %)")
            lines.append(_row("  Evaporated Water", pan.water_evaporated_lb_hr,
                               0, 0, pan.water_evaporated_lb_hr))
            lines.append(LIGHT)
            net = ff - pan.massecuite_flow_lb_hr - pan.water_evaporated_lb_hr
            lines.append(f"  {'Net (In - Out):':<{LBL}} {net:{NUM},.0f} lb/hr")
            return lines

        def _cen_station(cen):
            lines = []
            ms  = cen.massecuite_solids_lb_hr
            mw  = cen.massecuite_flow_lb_hr - ms
            mp  = cen.pol_in_lb_hr
            ww  = cen.wash_water_lb_hr
            s_sol  = cen.crystals_to_sugar_lb_hr
            s_wat  = cen.sugar_wet_lb_hr - s_sol
            m_sol  = cen.molasses_solids_lb_hr
            m_wat  = cen.molasses_flow_lb_hr - m_sol
            masse_vol = cen.massecuite_flow_lb_hr / cen.massecuite.density
            lines.append("  ENTERING")
            lines.append(_row("    Massecuite", cen.massecuite_flow_lb_hr, ms, mp, mw,
                               cen.massecuite.masse_brix, cen.massecuite.masse_purity,
                               vol_ft3_hr=masse_vol))
            lines.append(_row("    Wash Water", ww, 0, 0, ww))
            lines.append(LIGHT)
            lines.append(f"  {'Total In':<{LBL}} {cen.massecuite_flow_lb_hr + ww:{NUM},.0f}"
                         f" {ms:{NUM},.0f} {mp:{NUM},.0f} {mw + ww:{NUM},.0f}")
            lines.append("")
            lines.append("  LEAVING")
            lines.append(_row("    Sugar Out", cen.sugar_wet_lb_hr,
                               s_sol, cen.sugar_pol_lb_hr, s_wat,
                               cen.sugar_brix, cen.sugar_purity,
                               vol_ft3_hr=cen.sugar_stream.cu_ft_hr))
            lines.append(_row("    Molasses Out", cen.molasses_flow_lb_hr,
                               m_sol, cen.pol_to_molasses_lb_hr, m_wat,
                               cen.target_molasses_brix, cen.molasses_purity,
                               vol_ft3_hr=cen.molasses_stream.cu_ft_hr))
            lines.append(LIGHT)
            total_out = cen.sugar_wet_lb_hr + cen.molasses_flow_lb_hr
            net = (cen.massecuite_flow_lb_hr + ww) - total_out
            lines.append(f"  {'Net (In - Out):':<{LBL}} {net:{NUM},.0f} lb/hr")
            return lines

        def _dil_station(undiluted, diluted, label):
            lines = []
            water_added = diluted.flow_lb_per_hr - undiluted.flow_lb_per_hr
            lines.append("  ENTERING")
            lines.append(_stream(f"    {label} (undiluted)", undiluted))
            lines.append(_row("    Dilution Water", water_added, 0, 0, water_added))
            lines.append(LIGHT)
            lines.append(_row("  Total In", diluted.flow_lb_per_hr, undiluted.solids_flow,
                               undiluted.pol_flow, diluted.flow_lb_per_hr - undiluted.solids_flow))
            lines.append("")
            lines.append("  LEAVING")
            lines.append(_stream(f"    {label} (diluted)", diluted))
            lines.append(LIGHT)
            net = diluted.flow_lb_per_hr - (undiluted.flow_lb_per_hr + water_added)
            lines.append(f"  {'Net (In - Out):':<{LBL}} {net:{NUM},.2f} lb/hr")
            return lines

        def _heatx_station(unit, water_label):
            """Crystallizer/reheater station — non-contact water, mass conserved."""
            lines = []
            m_in, m_out = unit.massecuite_in, unit.massecuite_out
            flow = unit.massecuite_flow_lb_hr
            sol  = flow * m_in.masse_brix / 100
            pol  = flow * m_in.masse_purity * m_in.masse_brix / 10000
            lines.append("  ENTERING")
            lines.append(_row(f"    Massecuite In   (T={unit.masse_temp_in_deg_F:5.1f}F)",
                               flow, sol, pol, flow - sol,
                               m_in.masse_brix, m_in.masse_purity, vol_ft3_hr=flow / m_in.density))
            lines.append("")
            lines.append("  LEAVING")
            lines.append(_row(f"    Massecuite Out  (T={unit.masse_temp_out_deg_F:5.1f}F)",
                               flow, sol, pol, flow - sol,
                               m_out.masse_brix, m_out.masse_purity, vol_ft3_hr=flow / m_out.density))
            lines.append(LIGHT)
            lines.append(f"  {'ML purity in -> out:':<{LBL}} {m_in.ml_purity:6.1f} -> {m_out.ml_purity:6.1f} %"
                         f"     crystal content: {m_in.crystal_content:5.1f} -> {m_out.crystal_content:5.1f} %")
            lines.append(f"  {'Duty:':<{LBL}} {unit.duty_btu_hr:{NUM},.0f} BTU/hr")
            lines.append(f"  {water_label + ':':<{LBL}} {unit.water_lb_hr:{NUM},.0f} lb/hr"
                         f" ({unit.water_gpm:,.0f} gpm), {unit.water_temp_in_deg_F:.0f} -> "
                         f"{unit.water_temp_out_deg_F:.0f} F")
            return lines

        def _masse_row(label, vol, brix, purity, cc):
            v = f"{vol:{VOL},.0f}" if vol is not None else " " * (VOL - 1) + "-"
            b = f"{brix:{PCT}.1f}"    if brix    is not None else f"{'-':>{PCT}}"
            p = f"{purity:{PCT}.1f}"  if purity  is not None else f"{'-':>{PCT}}"
            c = f"{cc:{PCT}.1f}"      if cc      is not None else f"{'-':>{PCT}}"
            return f"  {label:<{LBL}} {v} {b} {p} {c}"

        # ── Totals needed for Overall section ────────────────────────────
        total_evap = (self.A_pans.water_evaporated_lb_hr + self.B_pans.water_evaporated_lb_hr
                      + self.C_pans.water_evaporated_lb_hr + self.grain_pans.water_evaporated_lb_hr)
        a_sugar  = self.A_centrifugals.sugar_stream
        c_mol    = self._final_molasses_out
        pol_extr = a_sugar.pol_flow / self.syrup.pol_flow * 100

        out = []
        out.append(HEAVY)
        out.append(f"{'THREE BOILING DOUBLE MAGMA - COMPLETE FLOOR BALANCE':^{W}}")
        out.append(HEAVY)

        # ── Overall ──────────────────────────────────────────────────────
        out.append(_section("OVERALL FLOOR BALANCE"))
        out.append(f"  (Feed = Evaporator syrup + Wash Water; Products = A sugar + C final molasses)")
        out.append("")
        out.append(_hdr())
        out.append("")
        out.append("  ENTERING")
        out.append(_stream("  Syrup From Evaporators", self.syrup))
        out.append(_stream("  Wash and Dilution Water", self.total_water))
        out.append("")
        out.append("  LEAVING")
        out.append(_stream("  A Product Sugar", a_sugar))
        out.append(_stream("  C Final Molasses", c_mol))
        out.append(_row("  Evaporated (all pans)", total_evap, 0, 0, total_evap))
        out.append("")
        tw = self.total_water
        in_flow    = self.syrup.flow_lb_per_hr + tw.flow_lb_per_hr
        in_solids  = self.syrup.solids_flow
        in_pol     = self.syrup.pol_flow
        in_water   = (self.syrup.flow_lb_per_hr - self.syrup.solids_flow) + tw.flow_lb_per_hr
        out_flow   = a_sugar.flow_lb_per_hr + c_mol.flow_lb_per_hr + total_evap
        out_solids = a_sugar.solids_flow    + c_mol.solids_flow
        out_pol    = a_sugar.pol_flow       + c_mol.pol_flow
        out_water  = ((a_sugar.flow_lb_per_hr - a_sugar.solids_flow)
                    + (c_mol.flow_lb_per_hr   - c_mol.solids_flow)
                    + total_evap)
        out.append(LIGHT)
        out.append(_row("  Total Entering", in_flow,  in_solids,  in_pol,  in_water))
        out.append(_row("  Total Leaving",  out_flow, out_solids, out_pol, out_water))
        out.append(LIGHT)
        out.append(_row("  Net (In - Out)", in_flow - out_flow, in_solids - out_solids,
                                            in_pol  - out_pol,  in_water  - out_water))
        out.append(f"  {'Pol% Recovered in Raw Sugar (A sugar / feed):':<{LBL+NUM}} {pol_extr:6.2f} %")
        out.append("")

        # ── Massecuite Volumetric Flow Summary ─────────────────────────────
        a_masse_vol     = self.A_pans.massecuite_flow_lb_hr / self.A_pans.massecuite.density
        b_masse_vol     = self.B_pans.massecuite_flow_lb_hr / self.B_pans.massecuite.density
        grain_masse_vol = self.grain_pans.massecuite_flow_lb_hr / self.grain_pans.massecuite.density
        c_masse_vol     = self.C_pans.massecuite_flow_lb_hr / self.C_pans.massecuite.density
        total_masse_vol = a_masse_vol + b_masse_vol + c_masse_vol
        out.append(_section("MASSECUITE VOLUMETRIC FLOW SUMMARY"))
        out.append(f"  {'Massecuite':<{LBL}} {'ft3/hr':>{VOL}} {'Brix%':>{PCT}} {'Pur%':>{PCT}} {'CC%':>{PCT}}")
        out.append("")
        out.append(_masse_row("A Massecuite", a_masse_vol,
                               self.A_pans.massecuite.masse_brix, self.A_pans.massecuite.masse_purity,
                               self.A_pans.massecuite.crystal_content))
        out.append(_masse_row("B Massecuite", b_masse_vol,
                               self.B_pans.massecuite.masse_brix, self.B_pans.massecuite.masse_purity,
                               self.B_pans.massecuite.crystal_content))
        out.append(_masse_row("Grain Massecuite (feeds C Pans)", grain_masse_vol,
                               self.grain_pans.massecuite.masse_brix, self.grain_pans.massecuite.masse_purity,
                               self.grain_pans.massecuite.crystal_content))
        out.append(_masse_row("C Massecuite", c_masse_vol,
                               self.C_pans.massecuite.masse_brix, self.C_pans.massecuite.masse_purity,
                               self.C_pans.massecuite.crystal_content))
        out.append(LIGHT)
        out.append(_masse_row("Total Massecuite (A + B + C)", total_masse_vol, None, None, None))
        out.append("")

        # ── A Pans ────────────────────────────────────────────────────────
        out.append(_section(f"A PANS  [{self.A_pans.name}]"))
        out.append(_hdr())
        out.append("")
        out.extend(_pan_station(self.A_pans))

        # ── A Centrifugals ─────────────────────────────────────────────────
        out.append(_section(f"A CENTRIFUGALS  [{self.A_centrifugals.name}]"))
        out.append(_hdr())
        out.append("")
        out.extend(_cen_station(self.A_centrifugals))

        # ── A Molasses Dilution ──────────────────────────────────────────
        out.append(_section(f"A MOLASSES DILUTION  (target {self.a_mol_dilution_brix:.1f} Bx)"))
        out.append(_hdr())
        out.append("")
        out.extend(_dil_station(self.A_centrifugals.molasses_stream, self._a_mol_diluted, "A Molasses"))

        # ── B Pans ────────────────────────────────────────────────────────
        out.append(_section(f"B PANS  [{self.B_pans.name}]"))
        out.append(_hdr())
        out.append("")
        out.extend(_pan_station(self.B_pans))

        # ── B Centrifugals ─────────────────────────────────────────────────
        out.append(_section(f"B CENTRIFUGALS  [{self.B_centrifugals.name}]"))
        out.append(_hdr())
        out.append("")
        out.extend(_cen_station(self.B_centrifugals))

        # ── B Molasses Dilution ──────────────────────────────────────────
        out.append(_section(f"B MOLASSES DILUTION  (target {self.b_mol_dilution_brix:.1f} Bx)"))
        out.append(_hdr())
        out.append("")
        out.extend(_dil_station(self.B_centrifugals.molasses_stream, self._b_mol_diluted, "B Molasses"))

        # ── Grain Pans ────────────────────────────────────────────────────
        out.append(_section(f"GRAIN PANS  [{self.grain_pans.name}]"))
        out.append(_hdr())
        out.append("")
        out.extend(_pan_station(self.grain_pans))

        # ── C Pans ────────────────────────────────────────────────────────
        out.append(_section(f"C PANS  [{self.C_pans.name}]"))
        out.append(_hdr())
        out.append("")
        out.extend(_pan_station(self.C_pans))

        # ── C Molasses Top-off Dilution ────────────────────────────────────
        out.append(_section(f"C MOLASSES TOP-OFF DILUTION  (target {self.c_mol_top_off_brix:.1f} Bx)"))
        out.append(_hdr())
        out.append("")
        out.extend(_dil_station(self._c_mol_top_off_non_dilute, self._c_mol_top_off, "C Molasses Top-off"))

        # ── C Crystallizers ──────────────────────────────────────────────
        out.append(_section(f"C CRYSTALLIZERS  [{self.C_crystallizers.name}]"))
        out.append(_hdr())
        out.append("")
        out.extend(_heatx_station(self.C_crystallizers, "Cooling Water"))

        # ── C Reheaters ──────────────────────────────────────────────────
        out.append(_section(f"C REHEATERS  [{self.C_reheaters.name}]"))
        out.append(_hdr())
        out.append("")
        out.extend(_heatx_station(self.C_reheaters, "Hot Water"))

        # ── C Centrifugals ─────────────────────────────────────────────────
        out.append(_section(f"C CENTRIFUGALS  [{self.C_centrifugals.name}]"))
        out.append(_hdr())
        out.append("")
        out.extend(_cen_station(self.C_centrifugals))

        # ── Pan Vapor Condensers ──────────────────────────────────────────
        out.append(_section(f"PAN VAPOR CONDENSERS  (one per pan, injection water @ "
                            f"{self.injection_water_temp_F:.0f} F)"))
        out.append(f"  {'Condenser':<16} {'Vapor lb/hr':>12} {'Sat T F':>8} {'h_fg':>8}"
                   f" {'MM BTU/hr':>10} {'Inj lb/hr':>13} {'Inj GPM':>9}"
                   f" {'Out T F':>8} {'Total lb/hr':>13}")
        out.append("")
        tot_v = tot_h = tot_w = tot_g = tot_t = 0.0
        for cname, cond in self.pan_condensers:
            inj = cond.injection_water_flow_lb_hr
            gpm = inj / 500.4
            out.append(f"  {cname:<16} {cond.vapor_flow_lb_hr:>12,.0f}"
                       f" {cond.vapor_sat_temp_F:>8.1f} {cond.vapor_h_fg_btu_lb:>8.1f}"
                       f" {cond.heat_load_btu_hr / 1e6:>10.3f} {inj:>13,.0f} {gpm:>9,.0f}"
                       f" {cond.water_outlet_temp_F:>8.1f} {cond.total_outlet_flow_lb_hr:>13,.0f}")
            tot_v += cond.vapor_flow_lb_hr
            tot_h += cond.heat_load_btu_hr / 1e6
            tot_w += inj
            tot_g += gpm
            tot_t += cond.total_outlet_flow_lb_hr
        out.append(LIGHT)
        out.append(f"  {'Total':<16} {tot_v:>12,.0f} {'':>8} {'':>8}"
                   f" {tot_h:>10.3f} {tot_w:>13,.0f} {tot_g:>9,.0f}"
                   f" {'':>8} {tot_t:>13,.0f}")
        out.append("")
        out.append("  Note: if using CoolingTowerSystem, ignore these injection water"
                   " demands - they are re-solved there at the delivered water temp.")

        out.append(_section("CONDENSATE RETURN"))
        out.append(f"  Clean condensate (Exhaust steam pans) : {self.clean_condensate:>12,.0f} lb/hr")
        out.append(f"  Dirty condensate (V1-V4 steam pans)   : {self.dirty_condensate:>12,.0f} lb/hr")
        out.append(f"  Total condensate                      : {self.clean_condensate + self.dirty_condensate:>12,.0f} lb/hr")

        out.append("")
        out.append(HEAVY)

        print("\n".join(out))


if __name__ == "__main__":
    pan_floor = ThreeBoilingDoubleMagma(
        syrup=SugarStream(brix=60, purity=80, flow_lb_per_hr=162_744, temp_deg_F=140),
        A_pans=Pan(
            feed_streams=None,
            heating_surface_ft2=22500,
            inches_vacuum=23.5,
            supersaturation=1.2,
            head_ft=2,
            masse_brix=92,
            ml_purity=65,
            calandria_pressure_psia=21.696,   # V1 (7 psig)
            heat_loss_factor=0.02, name='A Pans'),
        B_pans=Pan(
            feed_streams=None,
            heating_surface_ft2=7500,
            inches_vacuum=25,
            supersaturation=1.2,
            head_ft=2,
            masse_brix=94,
            ml_purity=48,
            calandria_pressure_psia=29.696,   # Exhaust (15 psig)
            heat_loss_factor=0.05, name='B Pans'),
        grain_pans=Pan(
            feed_streams=None,
            heating_surface_ft2=3000,
            inches_vacuum=25.5,
            supersaturation=1.2,
            head_ft=2,
            masse_brix=88,
            ml_purity=39,
            calandria_pressure_psia=29.696,   # Exhaust (15 psig)
            heat_loss_factor=0.05, name='Grain Pans'),
        C_pans=Pan(
            feed_streams=None,
            heating_surface_ft2=12000,
            inches_vacuum=26.5,
            supersaturation=1.2,
            head_ft=2,
            masse_brix=95.5,
            ml_purity=33,
            calandria_pressure_psia=21.696,   # V1 (7 psig)
            heat_loss_factor=0.05, name='C Pans'),
        A_centrifugals=Centrifugal(massecuite=None, massecuite_flow_lb_hr=0, target_molasses_brix=82, purity_rise=2, 
                                   sugar_moisture=0.2, sugar_purity=99.7, sugar_temp=150, molasses_temp=145, name="A Centrifugals"),
        B_centrifugals=Centrifugal(massecuite=None, massecuite_flow_lb_hr=0, target_molasses_brix=82, purity_rise=2, 
                                   sugar_moisture=5, sugar_purity=92, sugar_temp=150, molasses_temp=145, name="B Centrifugals"),
        C_centrifugals=Centrifugal(massecuite=None, massecuite_flow_lb_hr=0, target_molasses_brix=82, purity_rise=4,
                                   sugar_moisture=5, sugar_purity=82, sugar_temp=150, molasses_temp=145, name="C Centrifugals"),
        C_crystallizers=Crystallizer(massecuite_in=None, massecuite_flow_lb_hr=0,
                                     masse_temp_out_deg_F=120, ml_purity_out=30,
                                     water_temp_in_deg_F=85, water_temp_out_deg_F=105,
                                     name="C Crystallizers"),
        C_reheaters=Reheater(massecuite_in=None, massecuite_flow_lb_hr=0,
                             masse_temp_out_deg_F=130,
                             water_temp_in_deg_F=150, water_temp_out_deg_F=135,
                             name="C Reheaters"),
        b_magma_remelt_pct=20,
        c_magma_remelt_pct=20,
        a_mol_to_grain_pct=3,
        b_mol_to_grain_pct=10,
        syrup_to_grain_pct=1,
        a_mol_top_off_pct=0,
        b_mol_top_off_pct=20,
        c_mol_top_off_pct=20,
    )

    pan_floor.neat_display()
    pan_floor.A_pans.neat_display()
    pan_floor.generate_pfd(show=True, save_path=None)

    # Excel export demo — one workbook, this unit on its own sheet
    from excel_export import new_workbook
    wb = new_workbook()
    pan_floor.to_excel(wb)
    wb.save("three_boiling.xlsx")
    print("\nSaved three_boiling.xlsx")


