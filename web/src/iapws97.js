// IAPWS-IF97 steam property engine (subset: Regions 1, 2 and 4 only).
//
// This mill never sees pressure above ~900 psig (~6.4 MPa) or temperature
// above ~800 F (~700 K) -- both are far inside Region 1 (compressed liquid)
// and Region 2 (superheated vapor), and well below the P <= 16.529 MPa
// boundary where Region 3 (near-critical) would ever need to be considered.
// Region 3 and Region 5 are intentionally NOT implemented.
//
// Coefficient tables are transcribed from the public IAPWS-IF97 standard
// ("Revised Release on the IAPWS Industrial Formulation 1997 for the
// Thermodynamic Properties of Water and Steam", IAPWS, August 2007),
// cross-checked against the `iapws` Python package (jjgomera/iapws) that
// the rest of this project's Python code already depends on, so results
// match to solver tolerance. See web/dev/validate.mjs for the comparison
// harness against that same Python package.
//
// All functions here use SI units (K, MPa, kJ/kg, kJ/kg-K, m^3/kg) to match
// the standard. English-unit conversion lives in SteamStream (steam_stream.js).

(function (root) {
  'use strict';

  const R = 0.461526;      // kJ/(kg K)
  const Tc = 647.096;      // K
  const Pc = 22.064;       // MPa
  const Ps_623 = 16.5291642526777; // MPa, PSat(623.15 K) -- our permanent ceiling

  // ---------------------------------------------------------------------
  // Region 1: compressed / subcooled liquid
  // ---------------------------------------------------------------------

  const R1_I = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 4, 4, 4,
    5, 8, 8, 21, 23, 29, 30, 31, 32];
  const R1_J = [-2, -1, 0, 1, 2, 3, 4, 5, -9, -7, -1, 0, 1, 3, -3, 0, 1, 3, 17, -4, 0, 6,
    -5, -2, 10, -8, -11, -6, -29, -31, -38, -39, -40, -41];
  const R1_n = [0.14632971213167, -0.84548187169114, -3.756360367204, 3.3855169168385,
    -0.95791963387872, 0.15772038513228, -0.016616417199501, 0.00081214629983568,
    0.00028319080123804, -0.00060706301565874, -0.018990068218419, -0.032529748770505,
    -0.021841717175414, -0.00005283835796993, -0.00047184321073267, -0.00030001780793026,
    0.000047661393906987, -0.0000044141845330846, -7.2694996297594e-16,
    -0.000031679644845054, -0.0000028270797985312, -8.5205128120103e-10,
    -0.0000022425281908, -0.00000065171222895601, -1.4341729937924e-13,
    -0.00000040516996860117, -1.2734301741641e-9, -1.7424871230634e-10,
    -6.8762131295531e-19, 1.4478307828521e-20, 2.6335781662795e-23,
    -1.1947622640071e-23, 1.8228094581404e-24, -9.3537087292458e-26];

  function region1(T, P) {
    const Tr = 1386 / T;
    const Pr = P / 16.53;
    const pi = 7.1 - Pr;
    const tau = Tr - 1.222;
    let g = 0, gp = 0, gpp = 0, gt = 0, gtt = 0, gpt = 0;
    for (let k = 0; k < R1_n.length; k++) {
      const I = R1_I[k], J = R1_J[k], n = R1_n[k];
      const piI = Math.pow(pi, I);
      const tauJ = Math.pow(tau, J);
      g += n * piI * tauJ;
      gp += -n * I * Math.pow(pi, I - 1) * tauJ;
      gpp += n * I * (I - 1) * Math.pow(pi, I - 2) * tauJ;
      gt += n * J * piI * Math.pow(tau, J - 1);
      gtt += n * J * (J - 1) * piI * Math.pow(tau, J - 2);
      gpt += -n * I * J * Math.pow(pi, I - 1) * Math.pow(tau, J - 1);
    }
    return {
      T, P,
      v: Pr * gp * R * T / P / 1000,
      h: Tr * gt * R * T,
      s: R * (Tr * gt - g),
      region: 1, x: 0,
    };
  }

  // Backward1 T(P,h)
  const B1PH_I = [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 2, 2, 3, 3, 4, 5, 6];
  const B1PH_J = [0, 1, 2, 6, 22, 32, 0, 1, 2, 3, 4, 10, 32, 10, 32, 10, 32, 32, 32, 32];
  const B1PH_n = [-238.72489924521, 404.21188637945, 113.49746881718, -5.8457616048039,
    -0.0001528548241314, -1.0866707695377e-6, -13.391744872602, 43.211039183559,
    -54.010067170506, 30.535892203916, -6.5964749423638, 0.0093965400878363,
    1.157364750534e-7, -0.000025858641282073, -4.0644363084799e-9,
    0.000066456186191635, 8.0670734103027e-11, -9.3477771213947e-13,
    5.8265442020601e-15, -1.5020185953503e-17];

  function backward1_T_Ph(P, h) {
    const nu = h / 2500;
    let T = 0;
    for (let k = 0; k < B1PH_n.length; k++) {
      T += B1PH_n[k] * Math.pow(P, B1PH_I[k]) * Math.pow(nu + 1, B1PH_J[k]);
    }
    return T;
  }

  // Backward1 T(P,s)
  const B1PS_I = [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 4];
  const B1PS_J = [0, 1, 2, 3, 11, 31, 0, 1, 2, 3, 12, 31, 0, 1, 2, 9, 31, 10, 32, 32];
  const B1PS_n = [174.78268058307, 34.806930892873, 6.5292584978455, 0.33039981775489,
    -1.9281382923196e-7, -2.4909197244573e-23, -0.26107636489332, 0.22592965981586,
    -0.064256463395226, 0.0078876289270526, 3.5672110607366e-10, 1.7332496994895e-24,
    0.00056608900654837, -0.00032635483139717, 0.000044778286690632,
    -5.1322156908507e-10, -4.2522657042207e-26, 2.6400441360689e-13,
    7.8124600459723e-29, -3.0732199903668e-31];

  function backward1_T_Ps(P, s) {
    const sigma = s;
    let T = 0;
    for (let k = 0; k < B1PS_n.length; k++) {
      T += B1PS_n[k] * Math.pow(P, B1PS_I[k]) * Math.pow(sigma + 2, B1PS_J[k]);
    }
    return T;
  }

  // ---------------------------------------------------------------------
  // Region 2: superheated / dry saturated vapor
  // ---------------------------------------------------------------------

  const R2_I = [1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4, 5, 6, 6, 6, 7, 7, 7,
    8, 8, 9, 10, 10, 10, 16, 16, 18, 20, 20, 20, 21, 22, 23, 24, 24, 24];
  const R2_J = [0, 1, 2, 3, 6, 1, 2, 4, 7, 36, 0, 1, 3, 6, 35, 1, 2, 3, 7, 3, 16, 35, 0,
    11, 25, 8, 36, 13, 4, 10, 14, 29, 50, 57, 20, 35, 48, 21, 53, 39, 26, 40, 58];
  const R2_n = [-0.0017731742473213, -0.017834862292358, -0.045996013696365,
    -0.057581259083432, -0.05032527872793, -0.000033032641670203, -0.00018948987516315,
    -0.0039392777243355, -0.043797295650573, -0.000026674547914087, 2.0481737692309e-8,
    4.3870667284435e-7, -0.000032277677238570, -0.0015033924542148, -0.040668253562649,
    -7.8847309559367e-10, 1.2790717852285e-8, 4.8225372718507e-7, 2.2922076337661e-6,
    -1.6714766451061e-11, -0.0021171472321355, -23.895741934104, -5.905956432427e-18,
    -1.2621808899101e-6, -0.038946842435739, 1.1256211360459e-11, -8.2311340897998,
    1.9809712802088e-8, 1.0406965210174e-19, -1.0234747095929e-13, -1.0018179379511e-9,
    -8.0882908646985e-11, 0.10693031879409, -0.33662250574171, 8.918584535542e-25,
    3.0629316876232e-13, -0.0000042002467698208, -5.9056029685639e-26,
    0.0000037826947613457, -1.2768608934681e-15, 7.3087610595061e-29,
    5.5414715350778e-17, -0.00000094369707241210];

  const R2_cp0_J = [0, 1, -5, -4, -3, -2, -1, 2, 3];
  const R2_cp0_n = [-9.6927686500217, 10.086655968018, -0.005608791128302,
    0.071452738081455, -0.40710498223928, 1.4240819171444, -4.383951131945,
    -0.28408632460772, 0.021268463753307];

  function region2(T, P) {
    const Tr = 540 / T;
    const Pr = P;

    // ideal-gas part
    let go = Math.log(Pr), got = 0, gott = 0;
    for (let k = 0; k < R2_cp0_n.length; k++) {
      const J = R2_cp0_J[k], n = R2_cp0_n[k];
      go += n * Math.pow(Tr, J);
      got += n * J * Math.pow(Tr, J - 1);
      gott += n * J * (J - 1) * Math.pow(Tr, J - 2);
    }

    // residual part
    const tau = Tr - 0.5;
    let gr = 0, grp = 0, grt = 0;
    for (let k = 0; k < R2_n.length; k++) {
      const I = R2_I[k], J = R2_J[k], n = R2_n[k];
      const PrI = Math.pow(Pr, I);
      const tauJ = Math.pow(tau, J);
      gr += n * PrI * tauJ;
      grp += n * I * Math.pow(Pr, I - 1) * tauJ;
      grt += n * J * PrI * Math.pow(tau, J - 1);
    }

    return {
      T, P,
      v: Pr * (1 / Pr + grp) * R * T / P / 1000,
      h: Tr * (got + grt) * R * T,
      s: R * (Tr * (got + grt) - (go + gr)),
      region: 2, x: 1,
    };
  }

  // Backward2a/b/c T(P,h)
  const B2aPH_I = [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 3,
    3, 4, 4, 4, 5, 5, 5, 6, 6, 7];
  const B2aPH_J = [0, 1, 2, 3, 7, 20, 0, 1, 2, 3, 7, 9, 11, 18, 44, 0, 2, 7, 36, 38, 40, 42,
    44, 24, 44, 12, 32, 44, 32, 36, 42, 34, 44, 28];
  const B2aPH_n = [1089.8952318288, 849.51654495535, -107.81748091826, 33.153654801263,
    -7.4232016790248, 11.765048724356, 1.844574935579, -4.1792700549624, 6.2478196935812,
    -17.344563108114, -200.58176862096, 271.96065473796, -455.11318285818, 3091.9688604755,
    252266.40357872, -0.0061707422868339, -0.31078046629583, 11.670873077107,
    128127984.04046, -985549096.23276, 2822454697.3002, -3594897141.0703,
    1722734991.3197, -13551.334240775, 12848734.66465, 1.3865724283226, 235988.32556514,
    -13105236.545054, 7399.9835474766, -551966.9703006, 3715408.5996233, 19127.72923966,
    -415351.64835634, -62.459855192507];

  const B2bPH_I = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3,
    4, 4, 4, 4, 4, 4, 5, 5, 5, 6, 7, 7, 9, 9];
  const B2bPH_J = [0, 1, 2, 12, 18, 24, 28, 40, 0, 2, 6, 12, 18, 24, 28, 40, 2, 8, 18, 40,
    1, 2, 12, 24, 2, 12, 18, 24, 28, 40, 18, 24, 40, 28, 2, 28, 1, 40];
  const B2bPH_n = [1489.5041079516, 743.07798314034, -97.708318797837, 2.4742464705674,
    -0.63281320016026, 1.1385952129658, -0.47811863648625, 0.0085208123431544,
    0.93747147377932, 3.3593118604916, 3.3809355601454, 0.16844539671904,
    0.73875745236695, -0.47128737436186, 0.15020273139707, -0.0021764114219750,
    -0.021810755324761, -0.10829784403677, -0.046333324635812, 0.000071280351959551,
    0.00011032831789999, 0.00018955248387902, 0.0030891541160537, 0.0013555504554949,
    2.8640237477456e-7, -0.000010779857357512, -0.000076462712454814, 0.000014052392818316,
    -0.000031083814331434, -0.0000010302738212103, 2.821728163504e-7, 1.2704902271945e-6,
    7.3803353468292e-8, -1.1030139238909e-8, -8.1456365207833e-14, -2.518054568296e-11,
    -1.7565233969407e-18, 8.6934156344163e-15];

  const B2cPH_I = [-7, -7, -6, -6, -5, -5, -2, -2, -1, -1, 0, 0, 1, 1, 2, 6, 6, 6, 6, 6, 6, 6, 6];
  const B2cPH_J = [0, 4, 0, 2, 0, 2, 0, 1, 0, 2, 0, 1, 4, 8, 4, 0, 1, 4, 10, 12, 16, 20, 22];
  const B2cPH_n = [-3236839855.5242, 7326335090.2181, 358250899454.47, -583401318515.90,
    -10783068217.470, 20825544563.171, 610747.83564516, 859777.22535580, -25745.723604170,
    31081.088422714, 1208.2315865936, 482.19755109255, 3.7966001272486, -10.842984880077,
    -0.045364172676660, 1.4559115658698e-13, 1.126159740723e-12, -1.7804982240686e-11,
    1.2324579690832e-7, -1.1606921130984e-6, 0.000027846367088554, -0.00059270038474176,
    0.0012918582991878];

  function backward2a_T_Ph(P, h) {
    const nu = h / 2000 - 2.1;
    let T = 0;
    for (let k = 0; k < B2aPH_n.length; k++) T += B2aPH_n[k] * Math.pow(P, B2aPH_I[k]) * Math.pow(nu, B2aPH_J[k]);
    return T;
  }
  function backward2b_T_Ph(P, h) {
    const nu = h / 2000 - 2.6;
    const pr = P - 2;
    let T = 0;
    for (let k = 0; k < B2bPH_n.length; k++) T += B2bPH_n[k] * Math.pow(pr, B2bPH_I[k]) * Math.pow(nu, B2bPH_J[k]);
    return T;
  }
  function backward2c_T_Ph(P, h) {
    const nu = h / 2000 - 1.8;
    const pr = P + 25;
    let T = 0;
    for (let k = 0; k < B2cPH_n.length; k++) T += B2cPH_n[k] * Math.pow(pr, B2cPH_I[k]) * Math.pow(nu, B2cPH_J[k]);
    return T;
  }

  function hbc_P(P) {
    return 2652.6571908428 + Math.sqrt((P - 4.5257578905948) / 0.00012809002730136);
  }

  function backward2_T_Ph(P, h) {
    let T;
    if (P <= 4) {
      T = backward2a_T_Ph(P, h);
    } else if (P <= 6.546699678) {
      T = backward2b_T_Ph(P, h);
    } else {
      const hf = hbc_P(P);
      T = h >= hf ? backward2b_T_Ph(P, h) : backward2c_T_Ph(P, h);
    }
    if (P <= 22.064) T = Math.max(tSatP(P), T);
    return T;
  }

  // Backward2a/b/c T(P,s)
  const B2aPS_I = [-1.5, -1.5, -1.5, -1.5, -1.5, -1.5, -1.25, -1.25, -1.25, -1.0, -1.0, -1.0,
    -1.0, -1.0, -1.0, -0.75, -0.75, -0.5, -0.5, -0.5, -0.5, -0.25, -0.25, -0.25, -0.25,
    0.25, 0.25, 0.25, 0.25, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.75, 0.75, 0.75, 0.75,
    1.0, 1.0, 1.25, 1.25, 1.5, 1.5];
  const B2aPS_J = [-24, -23, -19, -13, -11, -10, -19, -15, -6, -26, -21, -17, -16, -9, -8,
    -15, -14, -26, -13, -9, -7, -27, -25, -11, -6, 1, 4, 8, 11, 0, 1, 5, 6, 10, 14, 16,
    0, 4, 9, 17, 7, 18, 3, 15, 5, 18];
  const B2aPS_n = [-392359.83861984, 515265.73827270, 40482.443161048, -321.93790923902,
    96.961424218694, -22.867846371773, -449429.14124357, -5011.8336020166,
    0.35684463560015, 44235.335848190, -13673.388811708, 421632.60207864,
    22516.925837475, 474.42144865646, -149.31130797647, -197811.26320452,
    -23554.399470760, -19070.616302076, 55375.669883164, 3829.3691437363,
    -603.91860580567, 1936.3102620331, 4266.0643698610, -5978.0638872718,
    -704.01463926862, 338.36784107553, 20.862786635187, 0.033834172656196,
    -0.000043124428414893, 166.53791356412, -139.86292055898, -0.78849547999872,
    0.072132411753872, -0.0059754839398283, -0.000012141358953904, 2.3227096733871e-7,
    -10.538463566194, 2.0718925496502, -0.072193155260427, 2.074988708112e-7,
    -0.018340657911379, 2.9036272348696e-7, 0.21037527893619, 0.00025681239729999,
    -0.012799002933781, -0.0000082198102652018];
  function backward2a_T_Ps(P, s) {
    const sigma = s / 2 - 2;
    let T = 0;
    for (let k = 0; k < B2aPS_n.length; k++) T += B2aPS_n[k] * Math.pow(P, B2aPS_I[k]) * Math.pow(sigma, B2aPS_J[k]);
    return T;
  }

  const B2bPS_I = [-6, -6, -5, -5, -4, -4, -4, -3, -3, -3, -3, -2, -2, -2, -2, -1, -1, -1,
    -1, -1, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 5, 5, 5];
  const B2bPS_J = [0, 11, 0, 11, 0, 1, 11, 0, 1, 11, 12, 0, 1, 6, 10, 0, 1, 5, 8, 9, 0, 1, 2,
    4, 5, 6, 9, 0, 1, 2, 3, 7, 8, 0, 1, 5, 0, 1, 3, 0, 1, 0, 1, 2];
  const B2bPS_n = [316876.65083497, 20.864175881858, -398593.99803599, -21.816058518877,
    223697.85194242, -2784.1703445817, 9.9207436071480, -75197.512299157, 2970.8605951158,
    -3.4406878548526, 0.38815564249115, 17511.295085750, -1423.7112854449, 1.0943803364167,
    0.89971619308495, -3375.9740098958, 471.62885818355, -1.9188241993679, 0.41078580492196,
    -0.33465378172097, 1387.0034777505, -406.63326195838, 41.727347159610, 2.1932549434532,
    -1.0320050009077, 0.35882943516703, 0.0052511453726066, 12.838916450705,
    -2.8642437219381, 0.56912683664855, -0.099962954584931, -0.0032632037778459,
    0.00023320922576723, -0.15334809857450, 0.029072288239902, 0.00037534702741167,
    0.0017296691702411, -0.00038556050844504, -0.000035017712292608, -0.000014566393631492,
    0.0000056420857267269, 4.1286150074605e-8, -2.0684671118824e-8, 1.6409393674725e-9];
  function backward2b_T_Ps(P, s) {
    const sigma = 10 - s / 0.7853;
    let T = 0;
    for (let k = 0; k < B2bPS_n.length; k++) T += B2bPS_n[k] * Math.pow(P, B2bPS_I[k]) * Math.pow(sigma, B2bPS_J[k]);
    return T;
  }

  const B2cPS_I = [-2, -2, -1, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5,
    6, 6, 7, 7, 7, 7, 7];
  const B2cPS_J = [0, 1, 0, 0, 1, 2, 3, 0, 1, 3, 4, 0, 1, 2, 0, 1, 5, 0, 1, 4, 0, 1, 2, 0,
    1, 0, 1, 3, 4, 5];
  const B2cPS_n = [909.68501005365, 2404.5667088420, -591.62326387130, 541.45404128074,
    -270.98308411192, 979.76525097926, -469.66772959435, 14.399274604723, -19.104204230429,
    5.3299167111971, -21.252975375934, -0.31147334413760, 0.60334840894623,
    -0.042764839702509, 0.0058185597255259, -0.014597008284753, 0.0056631175631027,
    -0.000076155864584577, 0.00022440342919332, -0.000012561095013413, 6.3323132660934e-7,
    -0.0000020541989675375, 3.6405370390082e-8, -2.9759897789215e-9, 1.0136618529763e-8,
    5.9925719692351e-12, -2.0677870105164e-11, -2.0874278181886e-11, 1.0162166825089e-10,
    -1.6429828281347e-10];
  function backward2c_T_Ps(P, s) {
    const sigma = 2 - s / 2.9251;
    let T = 0;
    for (let k = 0; k < B2cPS_n.length; k++) T += B2cPS_n[k] * Math.pow(P, B2cPS_I[k]) * Math.pow(sigma, B2cPS_J[k]);
    return T;
  }

  function backward2_T_Ps(P, s) {
    let T;
    if (P <= 4) T = backward2a_T_Ps(P, s);
    else if (s >= 5.85) T = backward2b_T_Ps(P, s);
    else T = backward2c_T_Ps(P, s);
    if (P <= 22.064) T = Math.max(tSatP(P), T);
    return T;
  }

  // ---------------------------------------------------------------------
  // Region 4: saturation curve (Eq 30 / its P<->T inverse)
  // ---------------------------------------------------------------------

  const SAT_n = [0, 1167.0521452767, -724213.16703206, -17.073846940092, 12020.824702470,
    -3232555.0322333, 14.915108613530, -4823.2657361591, 405113.40542057,
    -0.23855557567849, 650.17534844798];

  function pSatT(T) {
    const theta = T + SAT_n[9] / (T - SAT_n[10]);
    const A = theta * theta + SAT_n[1] * theta + SAT_n[2];
    const B = SAT_n[3] * theta * theta + SAT_n[4] * theta + SAT_n[5];
    const C = SAT_n[6] * theta * theta + SAT_n[7] * theta + SAT_n[8];
    return Math.pow(2 * C / (-B + Math.sqrt(B * B - 4 * A * C)), 4);
  }

  function tSatP(P) {
    const beta = Math.pow(P, 0.25);
    const E = beta * beta + SAT_n[3] * beta + SAT_n[6];
    const F = SAT_n[1] * beta * beta + SAT_n[4] * beta + SAT_n[7];
    const G = SAT_n[2] * beta * beta + SAT_n[5] * beta + SAT_n[8];
    const D = 2 * G / (-F - Math.sqrt(F * F - 4 * E * G));
    return (SAT_n[10] + D - Math.sqrt(Math.pow(SAT_n[10] + D, 2) - 4 * (SAT_n[9] + SAT_n[10] * D))) / 2;
  }

  function region4(P, x) {
    const T = tSatP(P);
    const liq = region1(T, P);
    const vap = region2(T, P);
    return {
      T, P, x,
      v: liq.v + x * (vap.v - liq.v),
      h: liq.h + x * (vap.h - liq.h),
      s: liq.s + x * (vap.s - liq.s),
      region: 4,
    };
  }

  // ---------------------------------------------------------------------
  // Newton refinement: the backward equations are already accurate to a
  // few mK, but a couple of Newton steps on the forward equation tighten
  // that further and match the Python `iapws` reference more closely.
  // ---------------------------------------------------------------------

  function refineByH(regionFn, P, h, T0) {
    let T = T0;
    for (let i = 0; i < 3; i++) {
      const dT = 0.01;
      const f = regionFn(T, P).h - h;
      const fp = (regionFn(T + dT, P).h - regionFn(T - dT, P).h) / (2 * dT);
      if (!isFinite(fp) || fp === 0) break;
      const step = f / fp;
      T -= step;
      if (Math.abs(step) < 1e-8) break;
    }
    return T;
  }

  function refineByS(regionFn, P, s, T0) {
    let T = T0;
    for (let i = 0; i < 3; i++) {
      const dT = 0.01;
      const f = regionFn(T, P).s - s;
      const fp = (regionFn(T + dT, P).s - regionFn(T - dT, P).s) / (2 * dT);
      if (!isFinite(fp) || fp === 0) break;
      const step = f / fp;
      T -= step;
      if (Math.abs(step) < 1e-8) break;
    }
    return T;
  }

  // ---------------------------------------------------------------------
  // Public solver: mirrors iapws.IAPWS97's flexible 2-property input,
  // restricted to the P <= Ps_623 (~16.53 MPa / ~2398 psia) envelope this
  // mill always operates within, and to Regions 1/2/4.
  // ---------------------------------------------------------------------

  function assertInRange(P) {
    if (P < 0.000611212677444 || P > Ps_623) {
      throw new Error(`IAPWS97: pressure ${P} MPa is outside the supported 0.000611-16.53 MPa range (Regions 1/2/4 only)`);
    }
  }

  function fromTP(T, P) {
    assertInRange(P);
    const Tsat = tSatP(P);
    return T <= Tsat ? region1(T, P) : region2(T, P);
  }

  function fromPh(P, h) {
    assertInRange(P);
    const Tsat = tSatP(P);
    const h14 = region1(Tsat, P).h;
    const h24 = region2(Tsat, P).h;
    if (h <= h14) {
      const T = refineByH(region1, P, h, backward1_T_Ph(P, h));
      return region1(T, P);
    } else if (h < h24) {
      const x = (h - h14) / (h24 - h14);
      return region4(P, x);
    } else {
      const T = refineByH(region2, P, h, backward2_T_Ph(P, h));
      return region2(T, P);
    }
  }

  function fromPs(P, s) {
    assertInRange(P);
    const Tsat = tSatP(P);
    const s14 = region1(Tsat, P).s;
    const s24 = region2(Tsat, P).s;
    if (s <= s14) {
      const T = refineByS(region1, P, s, backward1_T_Ps(P, s));
      return region1(T, P);
    } else if (s < s24) {
      const x = (s - s14) / (s24 - s14);
      return region4(P, x);
    } else {
      const T = refineByS(region2, P, s, backward2_T_Ps(P, s));
      return region2(T, P);
    }
  }

  function fromPx(P, x) {
    assertInRange(P);
    return region4(P, x);
  }

  function fromTx(T, x) {
    const P = pSatT(T);
    return region4(P, x);
  }

  function solve(kwargs) {
    const { T, P, h, s, x } = kwargs;
    if (T !== undefined && P !== undefined) return fromTP(T, P);
    if (P !== undefined && h !== undefined) return fromPh(P, h);
    if (P !== undefined && s !== undefined) return fromPs(P, s);
    if (P !== undefined && x !== undefined) return fromPx(P, x);
    if (T !== undefined && x !== undefined) return fromTx(T, x);
    throw new Error('IAPWS97.solve: pass exactly one supported pair of {T,P,h,s,x} (TP, Ph, Ps, Px, Tx)');
  }

  const IAPWS97 = { solve, pSatT, tSatP, region1, region2, region4, R, Tc, Pc, Ps_623 };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = IAPWS97;
  } else {
    root.IAPWS97 = IAPWS97;
  }
})(typeof window !== 'undefined' ? window : globalThis);
